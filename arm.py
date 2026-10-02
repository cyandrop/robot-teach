# -*- coding: utf-8 -*-
"""
机械臂控制模块：逆运动学(IK)移动 + 夹爪开合 + 抓取/释放。

为什么用 IK 而不是强化学习：
IK 是解析/数值求解，给定目标位姿直接算出各关节角度，稳定、可复现、不需要训练；
强化学习(PPO)在抓取这种稀疏奖励任务上需要长时间训练且结果不稳定，
10 天周期内不适合作为主控方案（可作为扩展实验单独展示）。
"""

import math
import random

import numpy as np
import pybullet as p

from config import (FINGER_OPEN, FINGER_CLOSE, MAX_MOVE_STEPS, MOVE_TOL,
                    EE_DOWN_EULER, HOME_JOINTS, IK_ITERATIONS, IK_RESIDUAL,
                    IK_FORCE, MAX_JOINT_VEL, SAFE_Z, TIME_STEP)


class Arm:
    def __init__(self, robot_id):
        self.robot = robot_id
        self.num_joints = p.getNumJoints(robot_id)

        self.ee = None                 # 末端执行器（panda_hand）
        self.arm_joints = []           # 7 个手臂关节
        self.finger_joints = []        # 2 个手指关节
        self.movable = []              # 所有可动关节（IK 需要按顺序给参数）

        for i in range(self.num_joints):
            info = p.getJointInfo(robot_id, i)
            name = info[12].decode() if isinstance(info[12], bytes) else str(info[12])
            jtype = info[2]
            if jtype == p.JOINT_FIXED:
                # panda_hand 是固定关节连接的连杆，它的索引就是末端 link 索引
                if "hand" in name.lower() and self.ee is None:
                    self.ee = i
            else:
                self.movable.append(i)
                if "finger" in name:
                    self.finger_joints.append(i)
                else:
                    self.arm_joints.append(i)

        if self.ee is None:            # 兜底：用最后一个手臂连杆
            self.ee = self.arm_joints[-1]

        # ★ 实测要点：pybullet 的逆运动学会跳过固定关节，实际把 panda_link8
        #   （腕部法兰，最后一个非固定连杆）送到目标位姿。所以 EE 必须用 link8，
        #   否则「手」永远比 IK 目标低 0.1034m（hand 相对 link8 的固定偏移）。
        self.ee = self.arm_joints[-1]

        self.lower = [p.getJointInfo(robot_id, i)[8] for i in self.movable]
        self.upper = [p.getJointInfo(robot_id, i)[9] for i in self.movable]
        self.ranges = [u - l for l, u in zip(self.lower, self.upper)]
        self.down_quat = p.getQuaternionFromEuler(EE_DOWN_EULER)
        self.go_home()

    # ---------- 基础动作 ----------
    def go_home(self, step_cb=None):
        """回到 home 位姿。所有动作都从这里起步，保证 IK 有好的迭代初值。"""
        self._ramp({j: v for j, v in zip(self.arm_joints, HOME_JOINTS)},
                   step_cb=step_cb)
        return self.get_ee_pose()[0]
    def set_fingers(self, open_gripper=True):
        target = FINGER_OPEN if open_gripper else FINGER_CLOSE
        for j in self.finger_joints:
            p.setJointMotorControl2(self.robot, j, p.POSITION_CONTROL,
                                    targetPosition=target, force=20)
        return target

    def step(self, n=1):
        for _ in range(n):
            p.stepSimulation()

    def get_ee_pose(self):
        """
        ★ 关键坑：pybullet 的 getLinkState 返回两个位置——
          st[0]/st[1] = 质心（惯性系）位姿，会带上局部惯性偏移（panda_link7 是 +0.08m）；
          st[4]/st[5] = URDF 连杆帧位姿，这才是 calculateInverseKinematics 真正瞄准的帧。
        之前用 st[0] 量位置，导致末端「看起来」永远比目标低 8cm，怎么闭环都补不掉。
        """
        st = p.getLinkState(self.robot, self.ee)
        return st[4], st[5]

    def _ik(self, pos, orn, rest):
        """
        解 IK。★ 实测最大的坑：residualThreshold 一旦设成 1e-4 这种"看起来很小"的值，
        pybullet 会在残差还有 10cm 时就判定收敛并退出，末端直接偏 100mm 以上。
        必须给 1e-9（等价于跑满迭代）——实测 5 个工作点误差立刻降到 0.3~1.2mm。
        """
        return p.calculateInverseKinematics(
            self.robot, self.ee, list(pos), orn,
            self.lower, self.upper, self.ranges, rest,
            maxNumIterations=IK_ITERATIONS, residualThreshold=IK_RESIDUAL)

    def _ramp(self, joint_targets, step_cb=None, done=None, max_steps=MAX_MOVE_STEPS):
        """
        限速的关节空间插值推进：每一步关节角变化不超过 MAX_JOINT_VEL*dt。

        ★ 为什么不直接把位控目标设成终点让它自己冲过去：
        setJointMotorControlArray 不支持 maxVelocity，不限速时机械臂会在十几帧内
        "甩"到目标，末端贴着桌面横扫，把沿途方块撞飞（实测蓝方块被扫出桌沿）。
        插值是匀速直线（关节空间），末端轨迹平滑，速度可控，也更接近真实机械臂。
        """
        joints = list(joint_targets)
        start = np.array([p.getJointState(self.robot, j)[0] for j in joints], float)
        end = np.array([joint_targets[j] for j in joints], float)
        dv = max(MAX_JOINT_VEL * TIME_STEP, 1e-6)
        n = int(np.ceil(float(np.max(np.abs(end - start))) / dv))
        n = max(2, min(n, max_steps))
        for i in range(1, n + 1):
            a = start + (end - start) * (i / n)
            p.setJointMotorControlArray(self.robot, joints, p.POSITION_CONTROL,
                                        targetPositions=list(a),
                                        forces=[IK_FORCE] * len(joints))
            p.stepSimulation()
            if step_cb:
                step_cb()
            if done and done():
                return True
        # 走完插值再稳一会儿，让位控把残差吃掉
        for _ in range(min(120, max_steps)):
            p.stepSimulation()
            if step_cb:
                step_cb()
            if done and done():
                return True
        return False

    def move_to(self, pos, orn=None, tol=MOVE_TOL, max_steps=MAX_MOVE_STEPS,
                step_cb=None, rounds=3):
        """
        闭环补偿的 IK 移动。

        ★ 两个实测要点：
        1) getLinkState 的 st[0] 是质心帧、st[4] 才是 IK 瞄准的 URDF 帧（差 80mm），
           位置测量必须用 st[4]（见 get_ee_pose）。
        2) 走完一步后测量真实误差，小的残差直接补回 IK 目标再走一轮，可收敛到 <1mm；
           若偏差很大说明这次 IK 掉进局部极小，换个种子重来，而不是把大误差累加进去。
        """
        if orn is None:
            orn = self.down_quat
        goal = np.array(pos, dtype=float)
        target = goal.copy()
        cur = np.array(self.get_ee_pose()[0])

        for attempt in range(max(rounds, 1)):
            rest = [p.getJointState(self.robot, i)[0] for i in self.movable]
            if attempt and np.linalg.norm(goal - cur) > 0.02:
                # 上一轮明显跑偏 → 抖动种子，跳出局部极小
                rest = [r + random.uniform(-0.35, 0.35) for r in rest]
                target = goal.copy()

            ik = self._ik(target, orn, rest)
            targets = {j: ik[k] for k, j in enumerate(self.movable)
                       if j in self.arm_joints}

            def done():
                c = np.array(self.get_ee_pose()[0])
                return bool(np.linalg.norm(goal - c) < tol)

            self._ramp(targets, step_cb=step_cb, done=done, max_steps=max_steps)
            cur = np.array(self.get_ee_pose()[0])
            if np.linalg.norm(goal - cur) < tol:
                return True
            if np.linalg.norm(goal - cur) > 0.02:
                continue                      # 大偏差：换种子重解，不累加
            target = target + (target - cur)  # 小偏差：闭环微调

        cur = np.array(self.get_ee_pose()[0])
        return bool(np.linalg.norm(goal - cur) < tol * 3)

    def settle(self, steps=60, step_cb=None):
        for _ in range(steps):
            self.step(1)
            if step_cb:
                step_cb()

    # ---------- 抓取 / 释放 ----------
    def grab(self, obj_id):
        """用固定约束把物体「粘」在末端上（等效于吸盘/夹紧），保证不掉落"""
        # ★ 又一个同一类坑：createConstraint 的父连杆帧用的是「质心/惯性帧」
        #   （即 getLinkState 的 st[0]/st[1]），而 IK 用的是 URDF 帧 st[4]/st[5]。
        #   如果这里也按 URDF 帧算相对位姿，物体会被整体拽低 0.08m（panda_link7 的
        #   局部惯性偏移），搬运时方块直接插进桌面，下降到位会失败。
        st = p.getLinkState(self.robot, self.ee)
        hand_pos, hand_orn = st[0], st[1]
        inv_p, inv_o = p.invertTransform(hand_pos, hand_orn)
        obj_pos, obj_orn = p.getBasePositionAndOrientation(obj_id)
        local_p, local_o = p.multiplyTransforms(inv_p, inv_o, obj_pos, obj_orn)

        # 约束点的定义：parent 侧 = 物体在父帧中的位置/姿态，child 侧 = 物体自身原点。
        # 所以旋转量要给 parentFrameOrientation，child 保持单位姿态。
        cid = p.createConstraint(self.robot, self.ee, obj_id, -1,
                                 p.JOINT_FIXED, [0, 0, 0],
                                 list(local_p), [0, 0, 0],
                                 parentFrameOrientation=list(local_o))
        # 抓取期间：手掌/小臂等连杆与方块关闭碰撞（手掌离方块顶只有 1mm，
        # 稍有误差就会把方块顶飞）；但**保留手指与方块的碰撞**，
        # 这样夹爪是真的"夹"在方块两侧，演示视频里不会出现穿模。
        for i in range(self.num_joints):
            enable = 1 if i in self.finger_joints else 0
            p.setCollisionFilterPair(self.robot, obj_id, i, -1,
                                     enableCollision=enable)
        self.set_fingers(open_gripper=False)
        return cid

    def release(self, obj_id, cid, step_cb=None):
        """
        ★ 释放顺序很关键：抓取期间关掉了手臂与物体的碰撞，手指是「穿过」方块闭合的。
        如果先恢复碰撞再张开手指，接触求解器会把互相穿透的手指和方块猛地弹开，
        实测方块落点被弹偏 10mm。正确顺序：先张指 → 再解约束 → 最后恢复碰撞。
        """
        self.set_fingers(open_gripper=True)
        self.settle(30, step_cb)          # 碰撞仍关闭，张指不会顶到方块
        p.removeConstraint(cid)
        self.settle(30, step_cb)          # 方块自然落到区域板上
        for i in range(self.num_joints):
            p.setCollisionFilterPair(self.robot, obj_id, i, -1, enableCollision=1)
        self.settle(30, step_cb)

    # ---------- 完整抓取放置动作 ----------
    def travel_to(self, xy, step_cb=None):
        """
        ★ 安全转运：先竖直抬到 SAFE_Z，再在高处平移，最后才由调用方下降。
        直接从停靠位斜着插到目标上方的话，末端是贴着桌面横扫过去的
        （指尖离方块顶只有几毫米），实测会把沿途方块撞飞，蓝方块甚至被扫出桌沿。
        """
        cur = self.get_ee_pose()[0]
        ok = self.move_to((cur[0], cur[1], SAFE_Z), step_cb=step_cb)
        ok &= self.move_to((xy[0], xy[1], SAFE_Z), step_cb=step_cb)
        return ok

    def pick_and_place(self, obj_id, pick_xy, place_xy, pick_z, place_z,
                       step_cb=None):
        """
        标准 pick-and-place 时序：
        抬升 → 平移 → 下降 → 闭合夹爪 → 抬起 → 平移 → 下降 → 张开 → 抬起
        """
        log = []
        ok = True

        self.set_fingers(open_gripper=True)
        self.settle(30, step_cb)

        ok &= self.travel_to(pick_xy, step_cb=step_cb)
        log.append("抬升并移动到目标上方")
        ok &= self.move_to((pick_xy[0], pick_xy[1], pick_z + 0.08), step_cb=step_cb)
        ok &= self.move_to((pick_xy[0], pick_xy[1], pick_z), step_cb=step_cb)
        log.append("下降到抓取位")
        self.settle(30, step_cb)

        cid = self.grab(obj_id)
        self.settle(40, step_cb)
        log.append("夹爪闭合，抓取物体")

        ok &= self.move_to((pick_xy[0], pick_xy[1], SAFE_Z), step_cb=step_cb)
        log.append("抬起物体")
        ok &= self.travel_to(place_xy, step_cb=step_cb)
        log.append("搬运到目标区域上方")
        ok &= self.move_to((place_xy[0], place_xy[1], place_z + 0.08), step_cb=step_cb)
        ok &= self.move_to((place_xy[0], place_xy[1], place_z), step_cb=step_cb)
        log.append("下降到放置位")
        self.settle(30, step_cb)

        self.release(obj_id, cid, step_cb)
        self.settle(120, step_cb)      # 多等一会儿让方块落稳再复位
        log.append("夹爪张开，释放物体")

        ok &= self.move_to((place_xy[0], place_xy[1], SAFE_Z), step_cb=step_cb)
        self.settle(30, step_cb)
        log.append("机械臂复位")
        return ok, log

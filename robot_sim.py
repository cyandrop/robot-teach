# -*- coding: utf-8 -*-
"""
仿真世界：搭建场景（地面 / 机械臂 / 桌子 / 彩色方块 / 放置区域），
并提供「感知 → 抓取 → 放置」的一次完整执行。
"""

import math
import pybullet as p
import pybullet_data

from config import (TABLE_CENTER, TABLE_HALF, TABLE_TOP, TABLE_RGB,
                    BLOCK_HALF, BLOCK_COLORS, ZONE_HALF, ZONE_COLORS,
                    GRASP_Z, PLACE_Z, TIME_STEP, GRAVITY,
                    PEDESTAL_CENTER, PEDESTAL_HALF, ROBOT_BASE_POS)
from vision import Camera, detect, draw_overlay
from arm import Arm

HOME_JOINTS = None  # 已统一到 config.HOME_JOINTS，由 Arm.go_home() 负责


class Sim:
    def __init__(self, gui=True):
        self.client = p.connect(p.GUI if gui else p.DIRECT)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, GRAVITY)
        p.setTimeStep(TIME_STEP)
        p.setRealTimeSimulation(0)

        p.loadURDF("plane.urdf")
        # 机械臂底座（把机械臂垫高到 0.35m，工作范围更舒服）
        self._add_box(PEDESTAL_CENTER, PEDESTAL_HALF, (0.30, 0.30, 0.32), mass=0)
        self.robot = p.loadURDF("franka_panda/panda.urdf", list(ROBOT_BASE_POS),
                                useFixedBase=True)
        self.arm = Arm(self.robot)
        self._home()

        self.table = self._add_box(TABLE_CENTER, TABLE_HALF, TABLE_RGB, mass=0)

        self.blocks = {}
        self.block_home = {}
        for name, (rgb, xy) in BLOCK_COLORS.items():
            pos = (xy[0], xy[1], TABLE_TOP + BLOCK_HALF)
            self.blocks[name] = self._add_box(pos, (BLOCK_HALF,) * 3, rgb, mass=0.2)
            self.block_home[name] = pos

        self.zones = {}
        self.zone_center = {}
        for name, (rgb, xy) in ZONE_COLORS.items():
            pos = (xy[0], xy[1], TABLE_TOP + ZONE_HALF[2])
            self.zones[name] = self._add_box(pos, ZONE_HALF, rgb, mass=0)
            self.zone_center[name] = pos

        self.cam = Camera()
        self.grasped = {}

        for _ in range(120):
            p.stepSimulation()

    # ---------- 场景搭建 ----------
    def _add_box(self, pos, half, rgb, mass=0.0):
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=list(half))
        vis = p.createVisualShape(p.GEOM_BOX, halfExtents=list(half),
                                  rgbaColor=list(rgb) + [1.0])
        return p.createMultiBody(baseMass=mass, baseCollisionShapeIndex=col,
                                 baseVisualShapeIndex=vis,
                                 basePosition=list(pos))

    def _home(self):
        # 用 config.HOME_JOINTS 做位控回家（而不是 resetJointState 硬掰），
        # 这样物理状态连续，IK 初值也好。
        self.arm.go_home()
        self.arm.set_fingers(open_gripper=True)
        self.arm.settle(60)

    def home(self, step_cb=None):
        """任务之间复位：回家 + 张开夹爪"""
        self.arm.go_home(step_cb=step_cb)
        self.arm.set_fingers(open_gripper=True)
        self.arm.settle(60, step_cb)

    def reset_blocks(self):
        """把方块放回初始位置（连续测试时用）"""
        for name, pos in self.block_home.items():
            p.resetBasePositionAndOrientation(self.blocks[name], list(pos), [0, 0, 0, 1])

    # ---------- 感知 ----------
    def perceive(self, name):
        """识别某个物体的世界坐标，失败返回 None"""
        rgb, depth = self.cam.render()
        pos, dbg = detect(self.cam, rgb, depth, name, name in self.blocks)
        return pos, dbg.get("像素中心"), rgb

    def snapshot(self, obj_name=None, zone_name=None):
        """返回带识别标记的图像（演示视频用）"""
        rgb, depth = self.cam.render()
        pts = []
        for name, color in ((obj_name, (255, 255, 255)), (zone_name, (0, 255, 255))):
            if not name:
                continue
            pos, dbg = detect(self.cam, rgb, depth, name, name in self.blocks)
            uv = dbg.get("像素中心")
            if uv:
                pts.append((uv, color, name))
        return draw_overlay(rgb, pts)

    # ---------- 执行 ----------
    def execute(self, obj_name, zone_name, step_cb=None):
        """
        完整执行一次「把 X 放到 Y」。
        返回 (是否成功, 日志列表, 误差信息)
        """
        info = {}
        # 先停靠：手臂在相机上方会遮挡桌面目标，感知前必须先让开
        self.home(step_cb=step_cb)
        obj_pos, uv_obj, img = self.perceive(obj_name)
        zone_pos, uv_zone, _ = self.perceive(zone_name)
        if obj_pos is None:
            return False, ["视觉未识别到 %s" % obj_name], info
        if zone_pos is None:
            return False, ["视觉未识别到 %s" % zone_name], info

        # 与仿真真值对比（只用于统计识别误差，不参与控制）
        gt = p.getBasePositionAndOrientation(self.blocks[obj_name])[0]
        info["识别误差"] = round(math.dist(obj_pos[:2], gt[:2]) * 1000, 1)  # 毫米
        info["识别到的坐标"] = [round(v, 3) for v in obj_pos[:2]]
        info["区域坐标"] = [round(v, 3) for v in zone_pos[:2]]

        ok, log = self.arm.pick_and_place(
            self.blocks[obj_name],
            obj_pos[:2], zone_pos[:2],
            GRASP_Z, PLACE_Z, step_cb=step_cb)

        final = p.getBasePositionAndOrientation(self.blocks[obj_name])[0]
        dist = math.dist(final[:2], self.zone_center[zone_name][:2])
        info["放置偏差"] = round(dist * 1000, 1)
        success = ok and dist < 0.09 and final[2] > TABLE_TOP - 0.02
        log.append("放置完成，与目标区域中心偏差 %.1f mm" % (dist * 1000))
        return success, log, info

    def close(self):
        p.disconnect()

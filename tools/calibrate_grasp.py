# -*- coding: utf-8 -*-
"""标定 GRASP_Z：下降探测首次接触，并打印末端坐标系链"""
import os, sys
import numpy as np
import pybullet as p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TABLE_TOP, BLOCK_HALF, BLOCK_COLORS, FINGER_OPEN
from robot_sim import Sim

sim = Sim(gui=False)
arm = sim.arm
robot = sim.robot

name = "红色方块"
bid = sim.blocks[name]
bx, by, _ = p.getBasePositionAndOrientation(bid)[0]
print("方块", name, "中心 xy =", (round(bx, 3), round(by, 3)),
      "顶面 z =", round(TABLE_TOP + 2 * BLOCK_HALF, 4))

# --- 1. 打印坐标系链（在 home 位姿） ---
print("\n=== 坐标系链（home 位姿，euler=pi,0,0 朝下）===")
for li in (5, 6, 7, 8, 9, 10):
    st = p.getLinkState(robot, li)
    info = p.getJointInfo(robot, li)
    print("  joint%-2d %-18s URDF帧 z=%.4f  质心 z=%.4f"
          % (li, info[12].decode(), st[4][2], st[0][2]))

# --- 2. 悬停到方块正上方，张开夹爪 ---
arm.set_fingers(open_gripper=True)
arm.settle(60)
arm.move_to((bx, by, TABLE_TOP + 0.25))
arm.settle(60)
print("\n悬停后 link7 URDF 帧 =", np.round(arm.get_ee_pose()[0], 4))

# --- 3. 逐毫米下降，检测接触 ---
print("\n=== 下降接触探测 ===")
contact_z = None
z = TABLE_TOP + 0.25
while z > TABLE_TOP + 0.05:
    ok = arm.move_to((bx, by, z))
    arm.settle(20)
    cur = np.array(arm.get_ee_pose()[0])
    pts = p.getContactPoints(robot, bid)
    if pts:
        contact_z = cur[2]
        print("  ★ 首次接触：link7 z = %.4f（命令 z=%.4f）" % (contact_z, z))
        for c in pts[:3]:
            print("     接触：机械臂 link%d ↔ 方块，法向力=%.3f，接触点 z=%.4f"
                  % (c[3], c[9], c[6][2]))
        break
    print("  z=%.4f  无接触（link7 实际 z=%.4f, ok=%s）" % (z, cur[2], ok))
    z -= 0.01

if contact_z is not None:
    print("\n结论：link7 URDF 帧首次接触方块时 z = %.4f" % contact_z)
    print("      方块顶面 z = %.4f" % (TABLE_TOP + 2 * BLOCK_HALF))
    print("      两者差 = %.4f" % (contact_z - (TABLE_TOP + 2 * BLOCK_HALF)))
    # 指尖位置
    st_l = p.getLinkState(robot, 9)
    st_r = p.getLinkState(robot, 10)
    print("      左指尖 z = %.4f, 右指尖 z = %.4f" % (st_l[4][2], st_r[4][2]))

sim.close()

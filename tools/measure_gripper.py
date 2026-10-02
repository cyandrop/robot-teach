# -*- coding: utf-8 -*-
"""测夹爪真实几何：hand / 左右手指 的 AABB 相对 link7 帧的位置"""
import os, sys
import numpy as np
import pybullet as p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TABLE_TOP, BLOCK_HALF, FINGER_OPEN
from robot_sim import Sim

sim = Sim(gui=False)
arm, robot = sim.arm, sim.robot
bid = sim.blocks["红色方块"]

bx, by, _ = p.getBasePositionAndOrientation(bid)[0]
arm.set_fingers(open_gripper=True)
arm.settle(60)
arm.move_to((bx, by, TABLE_TOP + 0.25))
arm.settle(60)

l7 = np.array(arm.get_ee_pose()[0])
print("link7 URDF 帧 =", np.round(l7, 4))
print("\n=== 相对 link7 帧 z 的偏移（负数=在下方）===")
for li, nm in ((8, "panda_hand"), (9, "leftfinger"), (10, "rightfinger")):
    a, b = p.getAABB(robot, li)
    print("  %-14s AABB z: %.4f ~ %.4f  (相对link7: %+.4f ~ %+.4f) 长=%.4f"
          % (nm, a[2], b[2], a[2] - l7[2], b[2] - l7[2], b[2] - a[2]))

ba, bb = p.getAABB(bid)
print("  方块          AABB z: %.4f ~ %.4f（高 %.4f）" % (ba[2], bb[2], bb[2] - ba[2]))

print("\n=== 张开 %.3f m 时两指内侧间距 ===" % FINGER_OPEN)
al, bl = p.getAABB(robot, 9)
ar, br = p.getAABB(robot, 10)
print("  左指 x: %.4f~%.4f  右指 x: %.4f~%.4f  内间距=%.4f"
      % (al[0], bl[0], ar[0], br[0], ar[0] - bl[0]))
print("  方块宽 = %.4f" % (2 * BLOCK_HALF))

# 夹爪闭合后
arm.set_fingers(open_gripper=False)
arm.settle(60)
al, bl = p.getAABB(robot, 9)
ar, br = p.getAABB(robot, 10)
print("  闭合后内间距 = %.4f" % (ar[0] - bl[0]))

# 手指指尖最低点相对 link7
print("\n指尖(最低点)相对 link7 = %+.4f" % (min(al[2], ar[2]) - l7[2]))
print("手掌底(最低点)相对 link7 = %+.4f" % (p.getAABB(robot, 8)[0][2] - l7[2]))

sim.close()

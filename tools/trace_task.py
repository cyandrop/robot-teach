# -*- coding: utf-8 -*-
"""单独追踪某个方块的完整搬运过程，打印每步接触情况"""
import os, sys
import numpy as np
import pybullet as p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GRASP_Z, PLACE_Z
from robot_sim import Sim
from vision import detect

obj = sys.argv[1] if len(sys.argv) > 1 else "绿色方块"
zone_xy = (0.62, -0.12)

sim = Sim(gui=False)
arm, robot = sim.arm, sim.robot
bid = sim.blocks[obj]

sim.home()
rgb, depth = sim.cam.render()
pos, dbg = detect(sim.cam, rgb, depth, obj, True)
print("目标 %s 识别 = %s（真值 %s）" % (obj, np.round(pos[:2], 4),
      np.round(p.getBasePositionAndOrientation(bid)[0][:2], 4)))


def contacts():
    out = []
    for c in p.getContactPoints(robot, bid):
        out.append("link%d/%s" % (c[3], p.getJointInfo(robot, c[3])[12].decode()
                                  if c[3] >= 0 else "base"))
    return set(out)


def show(tag):
    l7 = np.array(arm.get_ee_pose()[0])
    b = np.array(p.getBasePositionAndOrientation(bid)[0])
    print("  %-14s link7=%s 方块=%s Δxy=%.1fmm Δz=%+.4f  接触:%s"
          % (tag, np.round(l7, 4), np.round(b, 4),
             np.linalg.norm(b[:2] - l7[:2]) * 1000, b[2] - l7[2], contacts()))


arm.set_fingers(True)
arm.settle(30)
arm.move_to((pos[0], pos[1], GRASP_Z + 0.12)); arm.settle(30); show("悬停")
arm.move_to((pos[0], pos[1], GRASP_Z)); arm.settle(30); show("下降到位")
cid = arm.grab(bid); arm.settle(40); show("抓取后")
arm.move_to((pos[0], pos[1], GRASP_Z + 0.10)); arm.settle(30); show("抬起")
arm.move_to((zone_xy[0], zone_xy[1], PLACE_Z + 0.10)); arm.settle(30); show("搬运上方")
arm.move_to((zone_xy[0], zone_xy[1], PLACE_Z)); arm.settle(30); show("下降放置")
arm.release(bid, cid); arm.settle(120); show("释放后")
print("\n最终偏差 = %.1f mm" % (np.linalg.norm(
    np.array(p.getBasePositionAndOrientation(bid)[0][:2]) - np.array(zone_xy)) * 1000))
sim.close()

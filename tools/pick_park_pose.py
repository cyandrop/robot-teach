# -*- coding: utf-8 -*-
"""扫描候选 home(停靠)位姿，找一个不遮挡 5 个目标的位姿"""
import os, sys
import numpy as np
import pybullet as p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BLOCK_COLORS, ZONE_COLORS
from robot_sim import Sim
from vision import detect

sim = Sim(gui=False)
arm = sim.arm

CAND = [
    (0.45, 0.30, 0.72),
    (0.50, 0.32, 0.78),
    (0.30, 0.30, 0.80),
    (0.55, 0.28, 0.70),
    (0.20, 0.20, 0.85),
    (0.62, 0.30, 0.72),
    (0.50, 0.00, 0.92),
    (0.15, 0.00, 0.90),
    (0.62, -0.30, 0.75),
    (0.40, -0.34, 0.72),
]

for pose in CAND:
    ok_mv = arm.move_to(pose)
    arm.settle(60)
    got, miss, errs = 0, [], []
    for name in list(BLOCK_COLORS) + list(ZONE_COLORS):
        rgb, depth = sim.cam.render()
        pos, dbg = detect(sim.cam, rgb, depth, name, name in BLOCK_COLORS)
        body = sim.blocks.get(name) or sim.zones.get(name)
        gt = p.getBasePositionAndOrientation(body)[0]
        if pos is None:
            miss.append(name[:2])
            continue
        got += 1
        errs.append(np.linalg.norm(np.array(pos[:2]) - np.array(gt[:2])) * 1000)
    flag = "★★全部命中★★" if got == 5 else ("漏:%s" % ",".join(miss))
    print("EE%-20s move=%-5s %s  平均误差 %.1f mm 最大 %.1f mm"
          % (str(pose), ok_mv, flag,
             sum(errs) / len(errs) if errs else -1, max(errs) if errs else -1))
    if got == 5:
        js = [round(p.getJointState(sim.robot, j)[0], 4) for j in arm.arm_joints]
        print("     → 关节角 =", js)

sim.close()

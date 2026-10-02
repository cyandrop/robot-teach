# -*- coding: utf-8 -*-
"""GUI 模式自检：能开窗口、能渲染、能跑一次抓取"""
import os, sys, time
import numpy as np
import pybullet as p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from robot_sim import Sim

sim = Sim(gui=True)
p.resetDebugVisualizerCamera(cameraDistance=1.9, cameraYaw=42,
                             cameraPitch=-32, cameraTargetPosition=[0.45, 0.0, 0.5])
print("GUI 已连接，末端 =", np.round(sim.arm.get_ee_pose()[0], 4))
sim.home()
t0 = time.time()
ok, log, info = sim.execute("红色方块", "黄色区域")
print("GUI 模式抓取：", "成功" if ok else "失败",
      "｜放置偏差 %.1f mm｜耗时 %.1f s" % (info.get("放置偏差", -1), time.time() - t0))
for _ in range(120):
    p.stepSimulation()
    time.sleep(1.0 / 120)
sim.close()
print("closed")

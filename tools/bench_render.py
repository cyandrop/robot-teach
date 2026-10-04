# -*- coding: utf-8 -*-
"""渲染速度探针：测 3D 帧 / 相机帧 / 一次完整动作 的耗时，用来推算能做多长的视频。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pybullet as p

from robot_sim import Sim

VW, VH = 640, 480
EYE = (1.15, -0.95, 0.95)
TGT = (0.50, 0.00, 0.45)


def bench_3d(sim, n=60):
    view = p.computeViewMatrix(EYE, TGT, (0.0, 0.0, 1.0))
    proj = p.computeProjectionMatrixFOV(55.0, VW / float(VH), 0.05, 3.0)
    # 预热
    p.getCameraImage(VW, VH, view, proj, renderer=p.ER_BULLET_HARDWARE_OPENGL)
    t0 = time.time()
    for _ in range(n):
        p.getCameraImage(VW, VH, view, proj, renderer=p.ER_BULLET_HARDWARE_OPENGL)
    dt = (time.time() - t0) / n
    print("3D 渲染(OpenGL 640x480): %.1f ms/帧  -> 每秒 %.0f 帧" % (dt * 1000, 1.0 / dt))
    return dt


def bench_cam(sim, n=60):
    sim.cam.render()
    t0 = time.time()
    for _ in range(n):
        sim.cam.render()
    dt = (time.time() - t0) / n
    print("相机渲染(640x480):      %.1f ms/帧  -> 每秒 %.0f 帧" % (dt * 1000, 1.0 / dt))
    return dt


def bench_snapshot(sim, n=30):
    sim.snapshot("红色方块", "紫色区域")
    t0 = time.time()
    for _ in range(n):
        sim.snapshot("红色方块", "紫色区域")
    dt = (time.time() - t0) / n
    print("snapshot(带识别圈):     %.1f ms/帧" % (dt * 1000))
    return dt


def bench_execute(sim):
    n = {"c": 0}
    t0 = time.time()
    ok, log, info = sim.execute("红色方块", "紫色区域", step_cb=lambda: n.update(c=n["c"] + 1))
    dt = time.time() - t0
    print("一次完整动作(纯步进,不渲染): %d 步 | %.1f s | ok=%s" % (n["c"], dt, ok))
    return n["c"], dt


def bench_execute_render(sim):
    view = p.computeViewMatrix(EYE, TGT, (0.0, 0.0, 1.0))
    proj = p.computeProjectionMatrixFOV(55.0, VW / float(VH), 0.05, 3.0)

    def cb():
        p.getCameraImage(VW, VH, view, proj, renderer=p.ER_BULLET_HARDWARE_OPENGL)
        sim.snapshot("红色方块", "紫色区域")

    t0 = time.time()
    ok, log, info = sim.execute("红色方块", "紫色区域", step_cb=cb)
    dt = time.time() - t0
    print("一次完整动作(每步都渲染):   %.1f s | ok=%s" % (dt, ok))
    return dt


def bench_write(sim, n=200):
    import cv2
    vw = cv2.VideoWriter("_bench_tmp.mp4", cv2.VideoWriter_fourcc(*"mp4v"), 30, (1280, 720))
    frame = np.zeros((720, 1280, 3), np.uint8)
    t0 = time.time()
    for _ in range(n):
        vw.write(frame)
    vw.release()
    os.remove("_bench_tmp.mp4")
    dt = (time.time() - t0) / n
    print("写视频帧(1280x720 mp4v):  %.1f ms/帧" % (dt * 1000))
    return dt


if __name__ == "__main__":
    print("=" * 60)
    sim = Sim(gui=False)
    d3 = bench_3d(sim)
    dc = bench_cam(sim)
    ds = bench_snapshot(sim)
    dw = bench_write(sim)
    steps, dt_exec = bench_execute(sim)
    sim.reset_blocks()
    dt_exec_render = bench_execute_render(sim)
    sim.close()
    print("=" * 60)
    print("推算：动作段若每 8 步抓 1 帧 -> 一次动作约 %d 帧" % (steps // 8))
    print("      渲染这些帧约需 %.0f 秒" % (steps // 8 * (d3 + ds)))
    print("      两段动作合计约 %.0f 秒" % (steps // 8 * (d3 + ds) * 2))
    print("      一帧素材成本(3D+相机) = %.1f ms" % ((d3 + ds) * 1000))

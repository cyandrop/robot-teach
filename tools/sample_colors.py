# -*- coding: utf-8 -*-
"""直接采样每个目标在图像里的真实像素颜色，判断是阈值问题还是遮挡问题"""
import os, sys
import numpy as np
import cv2
import pybullet as p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BLOCK_COLORS, ZONE_COLORS
from robot_sim import Sim

sim = Sim(gui=False)
sim.home()
rgb, depth = sim.cam.render()
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)

print("%-10s %-18s %-16s %-18s %-14s" % ("目标", "世界坐标", "像素", "RGB采样", "HSV采样"))
for name in list(BLOCK_COLORS) + list(ZONE_COLORS):
    body = sim.blocks.get(name) or sim.zones.get(name)
    gt = p.getBasePositionAndOrientation(body)[0]
    u, v = sim.cam.world_to_pixel(gt)
    u, v = int(round(u)), int(round(v))
    inside = 0 <= u < 640 and 0 <= v < 480
    if not inside:
        print("%-10s %-18s (%d,%d) ★不在画面内★" % (name, np.round(gt[:3], 3), u, v))
        continue
    # 取 5x5 邻域中位数，避开边缘
    patch = rgb[max(0, v - 2):v + 3, max(0, u - 2):u + 3].reshape(-1, 3)
    med_rgb = np.median(patch, axis=0).astype(int)
    patch_h = hsv[max(0, v - 2):v + 3, max(0, u - 2):u + 3].reshape(-1, 3)
    med_hsv = np.median(patch_h, axis=0).astype(int)
    print("%-10s %-18s (%3d,%3d)  RGB%-15s HSV%-16s 深度%.3f"
          % (name, np.round(gt[:3], 3), u, v, med_rgb, med_hsv,
             depth[v, u]))

print("\n整幅图的颜色分布（统计各色块像素数）:")
from vision import detect
from config import HSV_RANGES
for name, ranges in HSV_RANGES.items():
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    n = int(mask.sum())
    ys, xs = np.nonzero(mask)
    print("  %-8s 阈值内像素 %6d %s" % (name, n,
          ("重心(%d,%d)" % (xs.mean(), ys.mean())) if n else "——"))

cv2.imwrite("results/dbg_blue.png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
print("\n已保存 results/dbg_blue.png")
sim.close()

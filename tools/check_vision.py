# -*- coding: utf-8 -*-
"""
视觉自检：一次性检查 5 个目标（红/绿/蓝方块 + 黄/紫区域）能不能都被稳定识别。

用法：
    python tools/check_vision.py

产出：
  1. 屏幕上打印每个目标的识别结果和误差（可直接抄进报告）
  2. 生成 results/vision_check.png —— 带识别框的相机画面（演示/验收用）

退出码 0 = 五个全识别到；非 0 = 有漏检，去看 config.py 的 HSV_RANGES。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2
import pybullet as p

from config import BLOCK_COLORS, ZONE_COLORS, MIN_CONTOUR_AREA
from robot_sim import Sim
from vision import detect, draw_overlay

# OpenCV 画中文会乱码，用英文标签
LABEL = {
    "红色方块": "red block",
    "绿色方块": "green block",
    "蓝色方块": "blue block",
    "黄色区域": "yellow zone",
    "紫色区域": "purple zone",
}


def main():
    sim = Sim(gui=False)
    rgb, depth = sim.cam.render()

    rows = []
    pts = []
    miss = []

    for name in list(BLOCK_COLORS) + list(ZONE_COLORS):
        is_block = name in BLOCK_COLORS
        pos, dbg = detect(sim.cam, rgb, depth, name, is_block)
        if pos is None:
            miss.append(name)
            rows.append((name, "FAIL", "-", "-", dbg.get("原因", "?")))
            continue
        gt = p.getBasePositionAndOrientation(sim.blocks[name])[0] if is_block \
            else sim.zone_center[name]
        err = float(np.hypot(pos[0] - gt[0], pos[1] - gt[1]) * 1000)
        uv = dbg.get("像素中心")
        pts.append((uv, (255, 255, 255) if is_block else (0, 255, 255), LABEL[name]))
        rows.append((name, "OK", "%.1f mm" % err,
                     "(%d, %d)" % (int(uv[0]), int(uv[1])), "%d px" % dbg.get("像素数", 0)))

    print("\n目标总数 5 ｜ 识别成功 %d ｜ 漏检 %d" % (5 - len(miss), len(miss)))
    print("-" * 62)
    print("%-10s %-6s %-10s %-14s %s" % ("目标", "结果", "误差", "像素中心", "备注"))
    print("-" * 62)
    for r in rows:
        print("%-10s %-6s %-10s %-14s %s" % r)
    print("-" * 62)

    out = os.path.join("results", "vision_check.png")
    ok, buf = cv2.imencode(".png", cv2.cvtColor(draw_overlay(rgb, pts), cv2.COLOR_RGB2BGR))
    if ok:
        buf.tofile(out)          # cv2.imwrite 不支持中文路径
        print("识别效果图已保存:", os.path.abspath(out))

    if miss:
        print("\n漏检：%s" % "、".join(miss))
        print("处理：把 config.py 里对应颜色的 HSV_RANGES 放宽，或调小 MIN_CONTOUR_AREA")
        print("      看目标像素实际颜色：python tools/sample_colors.py")
    sim.close()
    return 0 if not miss else 1


if __name__ == "__main__":
    sys.exit(main())

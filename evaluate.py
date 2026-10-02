# -*- coding: utf-8 -*-
"""
效果验证脚本 —— 比赛材料里「效果验证数据」这一项就靠它。

输出三组量化指标：
1. 相机标定自检：像素↔世界坐标换算误差（应接近 0）
2. 视觉识别精度：识别成功率 + 平均定位误差（毫米）
3. 抓取成功率：pick-and-place 成功率 + 放置偏差（毫米）
4. 指令解析准确率：测试集上的解析正确率

用法：
    python evaluate.py                 # 默认每类 10 次
    python evaluate.py --vision 50     # 视觉识别测 50 次
    python evaluate.py --grasp 20      # 抓取测 20 次
结果会写入 results/metrics.csv
"""

import argparse
import csv
import math
import os
import random
import time

import pybullet as p

from config import (BLOCK_COLORS, ZONE_COLORS, TABLE_TOP, BLOCK_HALF,
                    ZONE_HALF)
from robot_sim import Sim
from vision import detect
from planner import parse

TEST_COMMANDS = [
    ("把红色方块放到黄色区域", "红色方块", "黄色区域"),
    ("把红色方块放到紫色区域", "红色方块", "紫色区域"),
    ("把绿色方块放到黄色区域", "绿色方块", "黄色区域"),
    ("把绿色方块放到紫色区域", "绿色方块", "紫色区域"),
    ("把蓝色方块放到黄色区域", "蓝色方块", "黄色区域"),
    ("把蓝色方块放到紫色区域", "蓝色方块", "紫色区域"),
    ("帮我把红色的那个搬到紫色那边", "红色方块", "紫色区域"),
    ("请把绿色方块拿起来放到黄色区域", "绿色方块", "黄色区域"),
    ("蓝色方块放到紫区", "蓝色方块", "紫色区域"),
    ("把红方块移到黄区域", "红色方块", "黄色区域"),
]


def check_calibration(sim):
    """标定自检：世界→像素→世界 往返一致性（像素误差应≈0）"""
    import numpy as np
    _, depth = sim.cam.render()
    errs = []
    for u in range(60, 640, 90):
        for v in range(60, 480, 70):
            d = depth[v, u]
            if d <= 0 or d >= 0.999:
                continue
            pt = sim.cam.unproject_points([u], [v], [d])[0]
            uu, vv = sim.cam.world_to_pixel(pt)
            errs.append(math.hypot(uu - u, vv - v))
    return max(errs), sum(errs) / len(errs)


def eval_vision(sim, trials):
    """随机扰动方块位置，统计识别成功率与定位误差"""
    rows = []
    # ★ 先把机械臂停靠到不遮挡的位置，否则手臂会遮住桌面目标导致"识别失败"
    sim.home()
    for name in BLOCK_COLORS:
        hit, errs = 0, []
        for _ in range(trials):
            home = sim.block_home[name]
            dx = random.uniform(-0.06, 0.06)
            dy = random.uniform(-0.06, 0.06)
            newpos = (home[0] + dx, home[1] + dy, home[2])
            p.resetBasePositionAndOrientation(sim.blocks[name], list(newpos),
                                              [0, 0, 0, 1])
            for _ in range(10):
                p.stepSimulation()
            rgb, depth = sim.cam.render()
            pos, _ = detect(sim.cam, rgb, depth, name, True)
            gt = p.getBasePositionAndOrientation(sim.blocks[name])[0]
            if pos is None:
                continue
            hit += 1
            errs.append(math.dist(pos[:2], gt[:2]) * 1000)
        rate = 100.0 * hit / trials
        mean_err = sum(errs) / len(errs) if errs else float("nan")
        rows.append((name, rate, mean_err))
        print("  %-8s 识别成功率 %5.1f%%   平均定位误差 %5.1f mm"
              % (name, rate, mean_err))
    return rows


def eval_grasp(sim, trials):
    """执行完整抓取放置，统计成功率与放置偏差"""
    names = list(BLOCK_COLORS)
    zones = list(ZONE_COLORS)
    ok_count = 0
    devs = []
    times = []
    for i in range(trials):
        obj = names[i % len(names)]
        zone = zones[(i // len(names)) % len(zones)]
        sim.reset_blocks()
        for _ in range(30):
            p.stepSimulation()
        t0 = time.time()
        success, _, info = sim.execute(obj, zone)
        times.append(time.time() - t0)
        if success:
            ok_count += 1
        if info.get("放置偏差") is not None:
            devs.append(info["放置偏差"])
        print("  第 %2d 次  %s → %s  %s（偏差 %.1f mm）"
              % (i + 1, obj, zone, "成功" if success else "失败",
                 info.get("放置偏差", -1)))
    return (100.0 * ok_count / trials,
            sum(devs) / len(devs) if devs else float("nan"),
            sum(times) / len(times))


def eval_planner(use_llm):
    correct = 0
    for text, obj, zone in TEST_COMMANDS:
        r = parse(text, use_llm=use_llm)
        if r["object"] == obj and r["target"] == zone:
            correct += 1
        else:
            print("  解析错误：%s → %s" % (text, r))
    rate = 100.0 * correct / len(TEST_COMMANDS)
    print("  指令解析准确率 %.1f%%（%d/%d）"
          % (rate, correct, len(TEST_COMMANDS)))
    return rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vision", type=int, default=20, help="视觉识别测试次数/物体")
    ap.add_argument("--grasp", type=int, default=6, help="抓取测试总次数")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    random.seed(0)
    sim = Sim(gui=False)
    os.makedirs("results", exist_ok=True)
    summary = {}

    print("\n[1/4] 相机标定自检")
    mx, mean = check_calibration(sim)
    print("  往返误差：最大 %.4f px，平均 %.4f px（应接近 0）" % (mx, mean))
    summary["相机标定往返误差(px)"] = round(mean, 4)

    print("\n[2/4] 视觉识别精度（每类 %d 次）" % args.vision)
    vrows = eval_vision(sim, args.vision)
    summary["视觉识别成功率(%)"] = round(sum(r[1] for r in vrows) / len(vrows), 1)
    summary["平均定位误差(mm)"] = round(sum(r[2] for r in vrows) / len(vrows), 1)

    print("\n[3/4] 抓取放置成功率（共 %d 次）" % args.grasp)
    if args.grasp > 0:
        rate, dev, tmean = eval_grasp(sim, args.grasp)
        print("  成功率 %.1f%%，平均放置偏差 %.1f mm，单次平均耗时 %.1f s"
              % (rate, dev, tmean))
        summary["抓取成功率(%)"] = round(rate, 1)
        summary["平均放置偏差(mm)"] = round(dev, 1)
        summary["单次任务平均耗时(s)"] = round(tmean, 1)
    else:
        print("  跳过（--grasp 0）")

    print("\n[4/4] 指令解析准确率")
    summary["指令解析准确率(%)"] = round(eval_planner(not args.no_llm), 1)

    with open(os.path.join("results", "metrics.csv"), "w",
              newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["指标", "数值"])
        for k, v in summary.items():
            w.writerow([k, v])

    print("\n===== 汇总（已写入 results/metrics.csv）=====")
    for k, v in summary.items():
        print("  %-22s %s" % (k, v))
    sim.close()


if __name__ == "__main__":
    main()

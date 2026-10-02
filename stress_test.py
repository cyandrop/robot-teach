# -*- coding: utf-8 -*-
"""
连续任务压力测试 —— 比赛的「测试与验证」要的不是"跑通一次"，而是"反复跑都稳"。

和 evaluate.py 的区别：
  evaluate.py  = 精度测试（识别误差、放置偏差）
  stress_test.py = 稳定性测试（连续跑很多次不复位，看成功率衰减、是否扰动其他物体、
                             是否出现卡死/超时）

额外统计一项很能说明问题的指标：**连带扰动**——
执行任务时有没有把桌上其他方块撞歪。真实课堂里一次只能动一个物体，
撞歪别人就是失败，评审也一定会问。

用法：
    python stress_test.py --rounds 30
    python stress_test.py --rounds 30 --perturb 0.03   # 每轮随机挪动方块，更接近真实
输出：results/stress.csv
"""

import argparse
import csv
import math
import os
import random
import time

import numpy as np
import pybullet as p

from config import BLOCK_COLORS, ZONE_COLORS, TABLE_TOP
from robot_sim import Sim

# 连续执行超过这个秒数就判定为卡死（正常一次 1.7s）
TIMEOUT_S = 25.0


def snapshot_blocks(sim):
    return {n: np.array(p.getBasePositionAndOrientation(b)[0])
            for n, b in sim.blocks.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=30, help="连续任务轮数")
    ap.add_argument("--perturb", type=float, default=0.0,
                    help="每轮随机挪动方块的幅度（米），0=不挪")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    random.seed(20261001)
    np.random.seed(20261001)

    sim = Sim(gui=False)
    os.makedirs("results", exist_ok=True)

    names = list(BLOCK_COLORS)
    zones = list(ZONE_COLORS)
    rows = []
    ok_n = 0
    disturbed_n = 0
    timeout_n = 0

    print("连续执行 %d 次任务（扰动幅度 %.3f m）\n" % (args.rounds, args.perturb))
    print("%3s  %-18s %6s %8s %8s %6s" % ("#", "任务", "结果", "偏差mm", "耗时s", "扰动"))
    print("-" * 62)

    for i in range(args.rounds):
        obj = names[i % len(names)]
        zone = zones[(i // len(names)) % len(zones)]

        sim.reset_blocks()
        # 可选：随机扰动，模拟真实课堂里物体不会被摆得一模一样
        if args.perturb > 0:
            for n in names:
                home = sim.block_home[n]
                d = (random.uniform(-args.perturb, args.perturb),
                     random.uniform(-args.perturb, args.perturb), 0.0)
                p.resetBasePositionAndOrientation(
                    sim.blocks[n],
                    [home[0] + d[0], home[1] + d[1], home[2]], [0, 0, 0, 1])
        for _ in range(30):
            p.stepSimulation()

        before = snapshot_blocks(sim)

        t0 = time.time()
        success, log, info = sim.execute(obj, zone)
        dt = time.time() - t0
        timeout = dt > TIMEOUT_S

        after = snapshot_blocks(sim)
        # 连带扰动：非本次任务目标的方块是否被挪动超过 5mm
        disturb = 0.0
        for n in names:
            if n == obj:
                continue
            disturb = max(disturb, float(np.linalg.norm(after[n][:2] - before[n][:2])) * 1000)

        if timeout:
            timeout_n += 1
        if success:
            ok_n += 1
        if disturb > 5.0:
            disturbed_n += 1

        dev = info.get("放置偏差", -1)
        print("%3d  %-18s %6s %8.1f %8.1f %6.1f"
              % (i + 1, "%s→%s" % (obj, zone),
                 "成功" if success else "失败", dev, dt, disturb))
        rows.append([i + 1, obj, zone, "成功" if success else "失败",
                     round(dev, 1), round(dt, 1), round(disturb, 1),
                     "是" if timeout else "否"])

    n = args.rounds
    devs = [r[4] for r in rows if r[4] >= 0]
    times = [r[5] for r in rows]
    rate = 100.0 * ok_n / n
    print("-" * 62)
    print("成功率        %.1f%%  (%d/%d)" % (rate, ok_n, n))
    print("平均放置偏差  %.1f mm（最大 %.1f mm）" % (sum(devs) / len(devs), max(devs)))
    print("平均耗时      %.1f s（最长 %.1f s）" % (sum(times) / len(times), max(times)))
    print("连带扰动次数  %d 次（非目标方块被挪动 >5mm）" % disturbed_n)
    print("超时/卡死     %d 次" % timeout_n)

    with open(os.path.join("results", "stress.csv"), "w",
              newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["轮次", "物体", "目标区域", "结果", "放置偏差(mm)",
                    "耗时(s)", "连带扰动(mm)", "是否超时"])
        w.writerows(rows)
        w.writerow([])
        w.writerow(["汇总", "成功率%%", round(rate, 1),
                    "平均偏差mm", round(sum(devs) / len(devs), 1),
                    "平均耗时s", round(sum(times) / len(times), 1)])
        w.writerow(["汇总", "连带扰动次数", disturbed_n, "超时次数", timeout_n])
    print("\n已写入 results/stress.csv")

    sim.close()
    return 0 if rate >= 90.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

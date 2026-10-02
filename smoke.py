# -*- coding: utf-8 -*-
"""
冒烟测试：验证「场景搭建 → 视觉识别 → 抓取放置」整条链路。

用法：
    python smoke.py              # 无界面模式跑一遍
    python smoke.py --gui        # 带 PyBullet 窗口跑

输出：
    results/smoke_raw.png      相机原始画面
    results/smoke_before.png   识别标记画面
    results/smoke_after.png    抓取完成后的画面
"""

import argparse
import math
import os
import sys

import cv2
import numpy as np
import pybullet as p

from robot_sim import Sim
from vision import detect
from config import BLOCK_COLORS, ZONE_COLORS, GRASP_Z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gui", action="store_true", help="显示 PyBullet 窗口")
    ap.add_argument("--no-grasp", action="store_true", help="只测识别，不测抓取")
    args = ap.parse_args()

    os.makedirs("results", exist_ok=True)
    sim = Sim(gui=args.gui)

    print("\n===== [1] 机械臂结构 =====")
    print("  关节总数   :", sim.arm.num_joints)
    print("  末端 link  :", sim.arm.ee)
    print("  手臂关节   :", sim.arm.arm_joints)
    print("  手指关节   :", sim.arm.finger_joints)
    ee_pos, ee_orn = sim.arm.get_ee_pose()
    print("  末端当前位置:", [round(x, 3) for x in ee_pos])
    rot = np.array(p.getMatrixFromQuaternion(ee_orn)).reshape(3, 3)
    print("  末端 z 轴指向:", [round(x, 3) for x in rot @ np.array([0, 0, 1.0])])
    # 手指尖相对手部中心的偏移方向（判断手指朝哪边伸）
    if sim.arm.finger_joints:
        hand = p.getLinkState(sim.robot, sim.arm.ee)[4]
        fin = p.getLinkState(sim.robot, sim.arm.finger_joints[0])[4]
        print("  指尖相对手部偏移:", [round(b - a, 3) for a, b in zip(hand, fin)])

    print("\n===== [2] 相机与标定自检 =====")
    rgb, depth = sim.cam.render()
    print("  RGB:", rgb.shape, " 深度范围: %.3f ~ %.3f" % (depth.min(), depth.max()))
    errs_px = []
    for u in range(60, 640, 115):
        for v in range(60, 480, 90):
            d = depth[v, u]
            if d <= 0 or d >= 0.999:
                continue
            pt = sim.cam.unproject_points([u], [v], [d])[0]
            uu, vv = sim.cam.world_to_pixel(pt)
            errs_px.append(math.hypot(uu - u, vv - v))
    print("  像素↔世界往返误差: 最大 %.4f px，平均 %.4f px（应≈0）"
          % (max(errs_px), sum(errs_px) / len(errs_px)))
    cv2.imwrite("results/smoke_raw.png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    print("\n===== [3] 视觉识别 =====")
    ok_detect = True
    for name in list(BLOCK_COLORS) + list(ZONE_COLORS):
        pos, dbg = detect(sim.cam, rgb, depth, name, name in BLOCK_COLORS)
        body = sim.blocks.get(name) or sim.zones.get(name)
        gt = p.getBasePositionAndOrientation(body)[0]
        if pos is None:
            print("  %-8s ✗ 未识别: %s（真值 %s）"
                  % (name, dbg.get("原因", "?"), [round(x, 3) for x in gt[:2]]))
            ok_detect = False
            continue
        err = math.dist(pos[:2], gt[:2]) * 1000
        flag = "✓" if err < 25 else "△误差偏大"
        print("  %-8s %s 识别 %s 真值 %s 误差 %5.1f mm  像素%s  点云%d"
              % (name, flag, [round(x, 3) for x in pos[:2]],
                 [round(x, 3) for x in gt[:2]], err,
                 tuple(round(x) for x in dbg.get("像素中心", (0, 0))),
                 dbg.get("点云数", 0)))
        if err > 25:
            ok_detect = False

    cv2.imwrite("results/smoke_before.png",
                cv2.cvtColor(sim.snapshot("红色方块", "黄色区域"), cv2.COLOR_RGB2BGR))
    print("  已保存 results/smoke_before.png（带识别标记）")
    print("  识别环节：", "通过" if ok_detect else "★有问题★")

    if args.no_grasp:
        sim.close()
        return 0 if ok_detect else 1

    print("\n===== [4] 抓取几何自检（只悬停，不接触方块，避免扰动）=====")
    obj = "红色方块"
    gt = p.getBasePositionAndOrientation(sim.blocks[obj])[0]
    ok_reach = sim.arm.move_to((gt[0], gt[1], GRASP_Z + 0.08))
    ee2, _ = sim.arm.get_ee_pose()
    print("  悬停到达:", [round(x, 3) for x in ee2],
          " 水平误差 %.1f mm" % (math.dist(ee2[:2], gt[:2]) * 1000))
    # 用 AABB 算实际间隙（相对 link7 帧）
    l7z = ee2[2]
    hand_low = p.getAABB(sim.robot, 8)[0][2] - l7z
    tip_low = min(p.getAABB(sim.robot, 9)[0][2], p.getAABB(sim.robot, 10)[0][2]) - l7z
    print("  手掌底相对 link7: %+.4f ｜ 指尖最低相对 link7: %+.4f" % (hand_low, tip_low))
    print("  GRASP_Z=%.3f 时 → 手掌底 %.4f（方块顶 %.4f，余量 %+.1f mm）"
          % (GRASP_Z, GRASP_Z + hand_low, gt[2] + 0.022,
             (GRASP_Z + hand_low - (gt[2] + 0.022)) * 1000))
    print("                     指尖   %.4f（方块底 %.4f，余量 %+.1f mm）"
          % (GRASP_Z + tip_low, gt[2] - 0.022,
             (GRASP_Z + tip_low - (gt[2] - 0.022)) * 1000))
    print("  可达性：", "✓" if ok_reach else "★不可达★")

    print("\n===== [5] 抓取放置 =====")
    # ★ 必须先把机械臂移开再感知：相机在上方俯视，手臂悬在方块正上方会把方块挡住，
    #   视觉就识别不到了（这不是算法问题，是遮挡）。
    sim.home()
    zone = "黄色区域"
    ok, log, info = sim.execute(obj, zone)
    for line in log:
        print("  ·", line)
    print("  识别误差 %.1f mm ｜ 放置偏差 %.1f mm"
          % (info.get("识别误差", -1), info.get("放置偏差", -1)))
    final = p.getBasePositionAndOrientation(sim.blocks[obj])[0]
    print("  方块最终位置:", [round(v, 3) for v in final])
    print("  目标区域中心:", [round(v, 3) for v in sim.zone_center[zone]])
    print("  抓取环节：", "成功" if ok else "★失败★")

    cv2.imwrite("results/smoke_after.png",
                cv2.cvtColor(sim.cam.render()[0], cv2.COLOR_RGB2BGR))
    print("  已保存 results/smoke_after.png")

    sim.close()
    return 0 if (ok and ok_detect) else 1


if __name__ == "__main__":
    sys.exit(main())

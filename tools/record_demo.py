# -*- coding: utf-8 -*-
"""
自动录制演示视频（无声，动作素材）。

画面布局：左侧 = 三维仿真视角，右侧 = 相机视角（带识别圈）。
连续执行三条指令：红→黄、绿→紫、蓝→黄，动作按真实速度播放。

用法：
    python tools/record_demo.py
    python tools/record_demo.py --out results/demo.mp4

产出：MP4 文件（默认 results/demo.mp4），可直接作为备用演示视频或插进 PPT。
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2
import pybullet as p

from config import TIME_STEP, CAM_W, CAM_H
from robot_sim import Sim
from vision import draw_overlay

W, H = CAM_W, CAM_H
FPS = 30.0
EVERY = 8                      # 每 8 个仿真步抓一帧 → 30fps（240/8=30）
EYE_3D = (1.15, -0.95, 0.95)   # 三维视角机位
TGT_3D = (0.50, 0.00, 0.45)
UP_3D = (0.0, 0.0, 1.0)

LABEL = {"红色方块": "red block", "绿色方块": "green block", "蓝色方块": "blue block",
         "黄色区域": "yellow zone", "紫色区域": "purple zone"}


class Recorder:
    def __init__(self, sim, out):
        self.sim = sim
        self.count = 0
        self.view = p.computeViewMatrix(EYE_3D, TGT_3D, UP_3D)
        self.proj = p.computeProjectionMatrixFOV(55.0, W / H, 0.05, 3.0)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.vw = cv2.VideoWriter(out, fourcc, FPS, (W * 2, H))
        if not self.vw.isOpened():
            raise RuntimeError("无法创建视频文件，检查 opencv 是否带 ffmpeg：" + out)
        self.out = out

    def _grab(self, obj=None, zone=None):
        try:
            _, _, rgb3, _, _ = p.getCameraImage(W, H, self.view, self.proj,
                                                renderer=p.ER_BULLET_HARDWARE_OPENGL)
        except Exception:
            _, _, rgb3, _, _ = p.getCameraImage(W, H, self.view, self.proj,
                                                renderer=p.ER_TINY_RENDERER)
        rgb3 = np.asarray(rgb3)
        if rgb3.ndim == 1:
            rgb3 = rgb3.reshape(H, W, -1)
        left = rgb3[:, :, :3].astype(np.uint8)

        if obj or zone:
            right = self.sim.snapshot(obj, zone)
        else:
            right = self.sim.cam.render()[0]
        right = np.asarray(right)[:, :, :3].astype(np.uint8)

        for img, txt in ((left, "3D SIMULATION"), (right, "CAMERA VIEW")):
            cv2.putText(img, txt, (12, 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (255, 255, 255), 1, cv2.LINE_AA)
        frame = np.hstack([left, right])
        self.vw.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

    def tick(self):
        time.sleep(TIME_STEP)          # 真实速度播放
        self.count += 1
        if self.count % EVERY == 0:
            self._grab()

    def hold(self, seconds, obj=None, zone=None):
        """静止停留若干秒（让观众看清识别结果/指令）"""
        frames = int(seconds * FPS)
        for _ in range(frames):
            self._grab(obj, zone)
            time.sleep(1.0 / FPS)

    def close(self):
        self.vw.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("results", "demo.mp4"))
    args = ap.parse_args()

    sim = Sim(gui=False)
    rec = Recorder(sim, args.out)

    script = [("红色方块", "黄色区域"),
              ("绿色方块", "紫色区域"),
              ("蓝色方块", "黄色区域")]

    rec.hold(1.0)                       # 开场：整体画面
    for obj, zone in script:
        rec.hold(0.6)                   # 展示当前指令前的画面
        ok, steps, info = sim.execute(obj, zone, step_cb=rec.tick)
        print("%s → %s：%s，偏差 %.1f mm，识别误差 %.1f mm"
              % (obj, zone, "成功" if ok else "失败",
                 info.get("放置偏差", 0), info.get("识别误差", 0)))
        rec.hold(0.8, obj, zone)        # 展示识别圈与放置结果
        sim.reset_blocks()
        sim.home()
    rec.hold(1.0)
    rec.close()
    sim.close()
    print("视频已生成:", os.path.abspath(args.out),
          os.path.getsize(args.out), "bytes")


if __name__ == "__main__":
    main()

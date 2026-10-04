# -*- coding: utf-8 -*-
"""
HSV 阈值调参工具（真实场景版）

跑在【项目的真实场景 + 真实相机】里，看到的画面和 vision.py 识别时完全一致，
调出来的数字可以直接抄进 config.py。

用法：
    python tools/tune_hsv.py               # 默认调 红色方块
    python tools/tune_hsv.py 绿色方块
    python tools/tune_hsv.py 紫色区域
    python tools/tune_hsv.py --check       # 不弹窗：用 config 里的当前阈值自检 5 个目标

操作：
    拖动滑块 → 看 mask 窗口（目标是白色、背景是黑色）
    按 q    → 按 config.py 的格式打印当前阈值
    按 ESC  → 直接退出

注意：红色在 HSV 色环上跨 0，需要两组区间，脚本会自动给两组滑块。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from config import HSV_RANGES
from robot_sim import Sim

TARGETS = list(HSV_RANGES.keys())
WIN_SLIDER = "sliders"
WIN_MASK = "mask (白=选中)"
WIN_RESULT = "result"
WIN_ORIG = "original"


def nothing(_):
    pass


class Tuner:
    """交互式调参。interactive=False 时不建窗口，只用 config 里的值（自检用）。"""

    def __init__(self, sim, target, interactive=True):
        if target not in HSV_RANGES:
            raise SystemExit("未知目标 %r，可选：%s" % (target, " / ".join(TARGETS)))
        self.sim = sim
        self.target = target
        self.ranges = HSV_RANGES[target]
        self.interactive = interactive
        self.names = []
        if interactive:
            self._build_sliders()

    def _build_sliders(self):
        cv2.namedWindow(WIN_SLIDER)
        for i, (lo, hi) in enumerate(self.ranges):
            tag = "" if len(self.ranges) == 1 else str(i + 1)
            for key, val, vmax in (("Hmin", lo[0], 179), ("Hmax", hi[0], 179),
                                   ("Smin", lo[1], 255), ("Smax", hi[1], 255),
                                   ("Vmin", lo[2], 255), ("Vmax", hi[2], 255)):
                name = "%s%s" % (key, tag)
                cv2.createTrackbar(name, WIN_SLIDER, int(val), vmax, nothing)
                self.names.append(name)

    def _read(self):
        """返回 [((lo),(hi)), ...]"""
        if not self.interactive:
            return [(np.array(lo, np.uint8), np.array(hi, np.uint8))
                    for lo, hi in self.ranges]
        out = []
        step = 6
        for i in range(len(self.ranges)):
            vals = [cv2.getTrackbarPos(n, WIN_SLIDER)
                    for n in self.names[i * step:(i + 1) * step]]
            out.append((np.array(vals[0::2], np.uint8),
                        np.array(vals[1::2], np.uint8)))
        return out

    def frame(self):
        rgb, _ = self.sim.cam.render()
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        mask = None
        for lo, hi in self._read():
            m = cv2.inRange(hsv, lo, hi)
            mask = m if mask is None else cv2.bitwise_or(mask, m)
        return rgb, mask

    def run(self):
        print("正在调：%s　（按 q 打印 config 格式，ESC 退出）" % self.target)
        while True:
            rgb, mask = self.frame()
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            cv2.imshow(WIN_ORIG, bgr)
            cv2.imshow(WIN_MASK, mask)
            cv2.imshow(WIN_RESULT, cv2.bitwise_and(bgr, bgr, mask=mask))
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                self.report()
                break
            if key == 27:
                print("未保存，退出")
                break
        cv2.destroyAllWindows()

    def report(self):
        print("\n# 抄进 config.py 的 HSV_RANGES.%s" % self.target)
        print('"%s": [' % self.target)
        for lo, hi in self._read():
            print("    ((%d, %d, %d), (%d, %d, %d)),"
                  % (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]))
        print("],")


def check_all():
    """无窗口自检：一个场景渲染一次，5 个目标分别套 config 里的阈值数像素。"""
    sim = Sim(gui=False)
    rgb, _ = sim.cam.render()
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    ok = True
    for name in TARGETS:
        mask = None
        for lo, hi in HSV_RANGES[name]:
            m = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            mask = m if mask is None else cv2.bitwise_or(mask, m)
        cnt = int((mask > 0).sum())
        ys, xs = np.nonzero(mask)
        extra = "，中心=(%.0f, %.0f)" % (xs.mean(), ys.mean()) if cnt else ""
        print("[%s] 像素数=%d%s" % (name, cnt, extra))
        ok &= cnt > 0
    sim.close()
    print("\n自检结果：", "全部目标都有像素命中" if ok else "有目标没命中，阈值需要调")
    return ok


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--check":
        check_all()
        return
    target = argv[0] if argv else TARGETS[0]
    sim = Sim(gui=False)
    Tuner(sim, target, interactive=True).run()
    sim.close()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
离线渲染「无声演示素材」（用于后期配音）。

输出：1280x720 / 30fps，**H.264**（直接可发微信/剪映，不用二次转码）
布局：上 = 标题字幕带 ； 中 = 左 3D 仿真视角 / 右 相机视角（带识别圈）； 下 = 说明字幕带

两遍做法（只渲染一遍）：
  第 1 遍：不渲染，只数仿真步数，算出动作段占多少秒；
  第 2 遍：按最终时间轴渲染并写视频（字幕卡便宜，动作段逐帧渲染）。
  最后打印精确时间轴，直接粘进配音指南。

用法：
    python tools/make_demo_video.py                      # 默认 240 秒 = 4 分钟
    python tools/make_demo_video.py --duration 210
    python tools/make_demo_video.py --slow 4             # 动作放慢 4 倍
    python tools/make_demo_video.py --dry-run            # 只算时间轴，不渲染
"""

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pybullet as p
from PIL import Image, ImageDraw, ImageFont

from robot_sim import Sim

W, H = 1280, 720
VW, VH = 640, 480
TOP_H = 100
FPS = 30
EVERY = 8                      # 每 8 个仿真步抓一帧
EYE_3D = (1.15, -0.95, 0.95)
TGT_3D = (0.50, 0.00, 0.45)
UP_3D = (0.0, 0.0, 1.0)

F_TITLE = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 40)
F_SUB = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 25)
F_TAG = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 20)
BG = (14, 16, 20)


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def zoom_center(img, z):
    if abs(z - 1.0) < 1e-3:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0.0, z)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR)


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def base_canvas(title, sub):
    canvas = np.zeros((H, W, 3), np.uint8)
    canvas[:] = BG
    img = Image.fromarray(canvas)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, TOP_H], fill=(22, 26, 34))
    d.rectangle([0, TOP_H + VH, W, H], fill=(22, 26, 34))
    d.line([0, TOP_H, W, TOP_H], fill=(70, 80, 95), width=2)
    d.line([0, TOP_H + VH, W, TOP_H + VH], fill=(70, 80, 95), width=2)
    d.line([VW, TOP_H, VW, TOP_H + VH], fill=(70, 80, 95), width=2)
    d.text((40, 26), title, font=F_TITLE, fill=(255, 255, 255))
    y = TOP_H + VH + 20
    for ln in wrap(d, sub, F_SUB, W - 80):
        d.text((40, y), ln, font=F_SUB, fill=(198, 208, 222))
        y += 33
    return np.asarray(img).copy()


def stamp(canvas, left, right, zoom, progress):
    out = canvas.copy()
    out[TOP_H:TOP_H + VH, 0:VW] = zoom_center(left, zoom)
    out[TOP_H:TOP_H + VH, VW:W] = zoom_center(right, zoom)
    img = Image.fromarray(out)
    d = ImageDraw.Draw(img)
    d.text((12, TOP_H + 10), "3D SIMULATION", font=F_TAG, fill=(255, 255, 255))
    d.text((VW + 12, TOP_H + 10), "CAMERA VIEW / 视觉识别", font=F_TAG, fill=(140, 255, 255))
    out = np.array(img)          # 必须是可写数组（PIL 转出来是只读的）
    bw = int(W * max(0.0, min(1.0, progress)))
    if bw > 0:
        out[H - 5:H, 0:bw] = (90, 200, 255)
    return out


class Maker:
    def __init__(self, sim, out_path, total_frames):
        self.sim = sim
        self.view = p.computeViewMatrix(EYE_3D, TGT_3D, UP_3D)
        self.proj = p.computeProjectionMatrixFOV(55.0, VW / float(VH), 0.05, 3.0)
        self.out = out_path
        self.total = total_frames
        self.written = 0
        self.timeline = []       # (起始秒, 标题) 供配音指南用
        self._t_start = self.written

        ff = ffmpeg_exe()
        cmd = [ff, "-y",
               "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", "%dx%d" % (W, H), "-r", str(FPS), "-i", "-",
               "-an",
               "-vcodec", "libx264", "-pix_fmt", "yuv420p",
               "-crf", "23", "-preset", "medium",
               "-movflags", "+faststart",
               out_path]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        self.ff = ff

    def render_3d(self):
        try:
            _, _, rgb, _, _ = p.getCameraImage(VW, VH, self.view, self.proj,
                                               renderer=p.ER_BULLET_HARDWARE_OPENGL)
        except Exception:
            _, _, rgb, _, _ = p.getCameraImage(VW, VH, self.view, self.proj,
                                               renderer=p.ER_TINY_RENDERER)
        rgb = np.asarray(rgb)
        if rgb.ndim == 1:
            rgb = rgb.reshape(VH, VW, -1)
        return rgb[:, :, :3].astype(np.uint8)

    def render_pair(self, obj=None, zone=None):
        left = self.render_3d()
        right = self.sim.snapshot(obj, zone) if (obj or zone) else self.sim.cam.render()[0]
        return left, np.asarray(right)[:, :, :3].astype(np.uint8)

    def write(self, frame):
        self.proc.stdin.write(frame.tobytes())
        self.written += 1
        if self.written % 600 == 0:
            print("      已写 %d/%d 帧（%.0f 秒）"
                  % (self.written, self.total, self.written / float(FPS)), flush=True)

    @property
    def progress(self):
        return self.written / float(max(1, self.total))

    def mark(self, title):
        self.timeline.append((self.written / float(FPS), title))
        self._t_start = self.written

    def card(self, seconds, title, sub, pair, zoom_to=1.06):
        self.mark(title)          # 记段首，不是段末
        base = base_canvas(title, sub)
        frames = max(1, int(round(seconds * FPS)))
        for i in range(frames):
            t = i / float(max(1, frames - 1))
            self.write(stamp(base, pair[0], pair[1], 1.0 + (zoom_to - 1.0) * t, self.progress))

    def motion(self, title, sub, obj, zone, slow):
        self.mark(title)          # 记段首，不是段末
        base = base_canvas(title, sub)
        buf = []
        cnt = {"n": 0}

        def cb():
            if cnt["n"] % EVERY == 0:
                buf.append(self.render_pair(obj, zone))
            cnt["n"] += 1

        t0 = time.time()
        ok, log, info = self.sim.execute(obj, zone, step_cb=cb)
        print("      动作 %s→%s %s｜仿真 %d 步｜渲染 %d 帧｜耗时 %.0fs"
              % (obj, zone, "成功" if ok else "失败", cnt["n"], len(buf), time.time() - t0),
              flush=True)
        if not buf:
            buf = [self.render_pair(obj, zone)]
        for pair in buf:
            for _ in range(slow):
                self.write(stamp(base, pair[0], pair[1], 1.0, self.progress))

    def close(self):
        self.proc.stdin.close()
        rc = self.proc.wait()
        if rc != 0:
            print("      [warn] ffmpeg 返回码 %d，请检查输出文件" % rc, flush=True)


def count_frames(sim, obj, zone):
    n = {"c": 0}

    def cb():
        n["c"] += 1

    sim.execute(obj, zone, step_cb=cb)
    return n["c"] // EVERY


# 字幕卡权重（相对时长）。动作段时长由仿真帧数决定，剩下的都分给字幕卡。
WEIGHTS = [26, 22, 24, 28, 34, 24, 22, 20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=240.0)
    ap.add_argument("--slow", type=int, default=4)
    ap.add_argument("--out", default=os.path.join("results", "demo_4min_silent.mp4"))
    ap.add_argument("--dry-run", action="store_true", help="只算时间轴，不渲染")
    args = ap.parse_args()

    os.makedirs("results", exist_ok=True)

    # ---------- 第 1 遍：只数帧数（不渲染，很快） ----------
    print("[1/2] 先算时间轴（不渲染）...", flush=True)
    sim = Sim(gui=False)
    f1 = count_frames(sim, "红色方块", "紫色区域")
    sim.reset_blocks()
    f2 = count_frames(sim, "绿色方块", "黄色区域")
    sim.close()
    motion_frames = (f1 + f2) * args.slow
    motion_sec = motion_frames / float(FPS)
    cards_total = max(40.0, args.duration - motion_sec)
    scale = cards_total / float(sum(WEIGHTS))
    durs = [w * scale for w in WEIGHTS]
    total_frames = int(round((motion_frames + sum(durs) * FPS)))
    print("      动作段 %.1fs（%d 帧）｜字幕卡 %.1fs｜总计 %.1fs"
          % (motion_sec, motion_frames, cards_total, total_frames / float(FPS)), flush=True)

    t = 0.0
    plan = [
        ("① 机器人教学的真实困境", durs[0]),
        ("② 我们的方案：零硬件成本", durs[1]),
        ("③ 输入中文指令", durs[2]),
        ("④ 解析成结构化指令", durs[3]),
        ("⑤ 视觉识别：不是读仿真坐标", durs[4]),
        ("【动作】红方块 → 紫区域（慢放 %d 倍）" % args.slow, f1 * args.slow / float(FPS)),
        ("⑥ 结果与量化验证", durs[5]),
        ("【动作】绿方块 → 黄区域（慢放 %d 倍）" % args.slow, f2 * args.slow / float(FPS)),
        ("⑦ 可扩展：改场景只改 config.py", durs[6]),
        ("⑧ 零硬件 · 可复现 · 有量化数据", durs[7]),
    ]
    print("  ---- 时间轴 ----")
    for name, d in plan:
        print("      %d:%02d – %d:%02d  (%.1fs)  %s"
              % (int(t) // 60, int(t) % 60, int(t + d) // 60, int(t + d) % 60, d, name))
        t += d

    if args.dry_run:
        print("\n[dry-run] 到此为止，未渲染。")
        return

    # ---------- 第 2 遍：正式渲染 ----------
    print("[2/2] 正式渲染并写视频 ...", flush=True)
    sim = Sim(gui=False)
    mk = Maker(sim, args.out, total_frames)
    sim.home()
    pair_plain = mk.render_pair()
    pair_cam = mk.render_pair("红色方块", "紫色区域")

    mk.card(durs[0], "机器人教学的真实困境",
            "一台工业机械臂 15~30 万　｜　一个班 40 人　｜　一学期人均上手不到 20 分钟", pair_plain)
    mk.card(durs[1], "我们的方案：零硬件成本",
            "一台普通笔记本，用中文自然语言指挥虚拟机械臂，完成识别 · 抓取 · 搬运 · 放置", pair_plain)
    mk.card(durs[2], "输入中文指令",
            "「把红色方块放到紫色区域」—— 不选颜色、不填坐标、不写代码", pair_cam)
    mk.card(durs[3], "解析成结构化指令",
            "物体 = 红色方块　目标 = 紫色区域　（离线关键词规则，断网可用；大模型接口已预留）", pair_cam)
    mk.card(durs[4], "视觉识别：不是读仿真坐标",
            "HSV 颜色分割 → 深度反投影 → 点云质心　定位误差约 2 毫米", pair_cam)

    mk.motion("逆运动学执行：抬升 → 平移 → 下降 → 夹取 → 搬运 → 放置",
              "关节空间限速插值，轨迹与真实机械臂一致（本段慢放，便于配音讲解）",
              "红色方块", "紫色区域", args.slow)
    pair_result = mk.render_pair("红色方块", "紫色区域")
    mk.card(durs[5], "结果与量化验证",
            "放置偏差 3.4 mm　｜　连续 30 次成功率 100%　｜　连带扰动 0 次", pair_result)

    mk.motion("换一条指令：把绿色方块放到黄色区域",
              "无需重新标定、无需改代码，连续下达任务即可", "绿色方块", "黄色区域", args.slow)
    pair_end = mk.render_pair("绿色方块", "黄色区域")
    mk.card(durs[6], "可扩展：改场景只改 config.py",
            "换颜色 / 换数量 / 换桌面高度 / 换相机位姿，全部集中在一个配置文件里", pair_end)
    mk.card(durs[7], "零硬件 · 可复现 · 有量化数据",
            "参数集中在 config.py　｜　代码与验证数据已开源：github.com/cyandrop/robot-teach", pair_end)

    mk.close()
    sim.close()
    size = os.path.getsize(args.out) / 1048576.0 if os.path.exists(args.out) else 0
    print("视频已生成：%s（%.1f 秒，%.1f MB）"
          % (os.path.abspath(args.out), mk.written / float(FPS), size), flush=True)
    print("  ---- 实际时间轴（粘给配音用） ----")
    for i, (start, name) in enumerate(mk.timeline):
        end = mk.timeline[i + 1][0] if i + 1 < len(mk.timeline) else mk.written / float(FPS)
        print("      %d:%02d – %d:%02d  %s"
              % (int(start) // 60, int(start) % 60, int(end) // 60, int(end) % 60, name))


if __name__ == "__main__":
    main()

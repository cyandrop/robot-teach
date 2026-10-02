# -*- coding: utf-8 -*-
"""
主程序入口。

用法：
    python main.py                  # 图形界面（推荐演示用）
    python main.py --console        # 命令行输入指令
    python main.py --no-llm         # 不联网，只用关键词解析
    python main.py --cam            # 额外弹出相机画面窗口（演示视频很好用）
    python main.py --demo           # 自动跑一遍预设指令（录视频用）
"""

import argparse
import sys
import time

import cv2

from config import BLOCK_COLORS, ZONE_COLORS, TIME_STEP
from robot_sim import Sim
from planner import parse, OBJECTS, ZONES


class CameraWindow:
    """相机画面窗口：实时显示识别结果，演示/录像用"""

    def __init__(self, sim, enabled=True, every=8, realtime=False):
        self.sim = sim
        self.enabled = enabled
        self.every = every
        self.realtime = realtime      # True = 按仿真时间步节流，动作看起来是真实速度
        self.count = 0

    def tick(self):
        # 每个仿真步都调用；realtime 模式下睡 1 个步长，让画面按 1:1 真实速度播放
        if self.realtime:
            time.sleep(TIME_STEP)
        if not self.enabled:
            return
        self.count += 1
        if self.count % self.every:
            return
        img = self.sim.cam.render()[0]      # render 返回 (rgb, depth)，取 rgb
        cv2.imshow("camera", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        cv2.waitKey(1)

    def show_detection(self, obj_name, zone_name):
        if not self.enabled:
            return
        img = self.sim.snapshot(obj_name, zone_name)
        cv2.imshow("camera", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        cv2.waitKey(1)


def run_command(sim, text, use_llm, camwin, log):
    """执行一次指令，打印/返回执行过程"""
    plan = parse(text, use_llm=use_llm)
    log.append("指令：%s" % text)
    log.append("解析结果：%s → %s（解析方式：%s）"
               % (plan["object"], plan["target"],
                  "大模型 Qwen" if plan["source"] == "llm" else "关键词规则"))
    camwin.show_detection(plan["object"], plan["target"])
    t0 = time.time()
    ok, steps, info = sim.execute(plan["object"], plan["target"],
                                  step_cb=camwin.tick)
    for s in steps:
        log.append("  · %s" % s)
    if info:
        log.append("  识别误差 %.1f mm ｜ 放置偏差 %.1f mm"
                   % (info.get("识别误差", 0), info.get("放置偏差", 0)))
    log.append("结果：%s（耗时 %.1f 秒）" % ("成功" if ok else "失败", time.time() - t0))
    camwin.show_detection(None, None)
    return ok


def console_mode(sim, use_llm, camwin):
    print("\n可用物体：%s" % "、".join(OBJECTS))
    print("可用区域：%s" % "、".join(ZONES))
    print("示例指令：把红色方块放到紫色区域")
    print("输入 q 退出\n")
    log = []
    while True:
        try:
            text = input("请输入指令 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("q", "quit", "exit", "退出"):
            break
        if not text:
            continue
        log.clear()
        run_command(sim, text, use_llm, camwin, log)
        print("\n".join(log))
        print()


def gui_mode(sim, use_llm, camwin):
    import tkinter as tk
    from tkinter import scrolledtext

    root = tk.Tk()
    root.title("面向机器人教学的虚拟仿真智能体平台")
    root.geometry("620x420")

    tk.Label(root, text="输入自然语言指令，机械臂会自动识别并搬运",
             font=("Microsoft YaHei", 11)).pack(pady=8)
    tk.Label(root, text="可用：%s ｜ %s" % ("、".join(OBJECTS), "、".join(ZONES)),
             fg="#666666").pack()

    entry = tk.Entry(root, width=52, font=("Microsoft YaHei", 12))
    entry.pack(pady=8)
    entry.insert(0, "把红色方块放到紫色区域")

    area = scrolledtext.ScrolledText(root, width=70, height=16,
                                     font=("Consolas", 10))
    area.pack(padx=10, fill=tk.BOTH, expand=True)

    def say(line):
        area.insert(tk.END, line + "\n")
        area.see(tk.END)
        root.update()

    def on_submit(event=None):
        text = entry.get().strip()
        if not text:
            return
        btn.config(state=tk.DISABLED)
        say("=" * 60)
        run_command(sim, text, use_llm, camwin,
                    type("L", (), {"append": say})())
        btn.config(state=tk.NORMAL)

    btn = tk.Button(root, text="执行（回车）", command=on_submit,
                    font=("Microsoft YaHei", 11), height=1)
    btn.pack(pady=6)
    root.bind("<Return>", on_submit)
    say("系统就绪。机械臂窗口为 PyBullet 仿真，相机窗口显示识别结果。")
    root.mainloop()


def demo_mode(sim, use_llm, camwin):
    script = ["把红色方块放到黄色区域",
              "把绿色方块放到紫色区域",
              "把蓝色方块放到黄色区域"]
    log = []
    for s in script:
        run_command(sim, s, use_llm, camwin, log)
        sim.reset_blocks()
    print("\n".join(log))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--console", action="store_true", help="命令行模式")
    ap.add_argument("--no-llm", action="store_true", help="不调用大模型")
    ap.add_argument("--cam", action="store_true", help="显示相机画面窗口")
    ap.add_argument("--demo", action="store_true", help="自动演示（录视频用）")
    ap.add_argument("--headless", action="store_true", help="不显示 PyBullet 窗口")
    ap.add_argument("--realtime", action="store_true",
                    help="按真实速度播放（录演示视频时用，否则瞬间跑完）")
    args = ap.parse_args()

    sim = Sim(gui=not args.headless)
    camwin = CameraWindow(sim, enabled=args.cam, realtime=args.realtime)

    try:
        if args.demo:
            demo_mode(sim, not args.no_llm, camwin)
        elif args.console:
            console_mode(sim, not args.no_llm, camwin)
        else:
            gui_mode(sim, not args.no_llm, camwin)
    finally:
        if args.cam:
            cv2.destroyAllWindows()
        sim.close()


if __name__ == "__main__":
    main()

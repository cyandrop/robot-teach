# -*- coding: utf-8 -*-
"""
问卷分析脚本 —— 把回收的 CSV 变成「可直接贴进比赛报告」的图表和表格。

只依赖标准库（环境里没有 matplotlib/pandas，图表用内联 SVG 手绘，
产出的 report.html 是单文件，双击就能看，也能直接截图放进报告/PPT）。

用法：
    python analyze.py                       # 读 survey/answers.csv
    python analyze.py --csv 别的名字.csv
    python analyze.py --demo                # 用内置模拟数据跑一遍，先看效果

输出：
    survey/report.html      单文件可视化报告（含所有图表）
    屏幕打印一份 Markdown 表格，可直接复制进方案文档
"""

import argparse
import csv
import html
import io
import os
import random
import sys

# 题号 → (标题, 类型)  类型：single=单选/分类  multi=多选  likert=1~5 量表
QUESTIONS = [
    ("Q1",  "身份", "single"),
    ("Q2",  "专业相关程度", "likert"),
    ("Q3",  "是否修过相关课程", "single"),
    ("Q4",  "实际操作实体机械臂次数", "single"),
    ("Q5",  "影响上手的原因", "multi"),
    ("Q6",  "最难理解的环节", "multi"),
    ("Q7",  "面对实体机械臂最担心什么", "single"),
    ("Q8",  "平台上手难度", "likert"),
    ("Q9",  "对理解视觉伺服抓取的帮助", "likert"),
    ("Q10", "使用意愿", "likert"),
    ("Q11", "推荐意愿 NPS", "likert"),
    ("Q12", "希望增加的功能", "multi"),
]

# ★ 只认这几种分隔符。千万不要把「、」「,」加进来——多选题的选项名本身常带它们
#   （例如"控制算法（PID、轨迹规划）"），一加就会把选项切碎，统计全错。
#   腾讯问卷常见分隔符是「┋」或「;」，问卷星常见「;」。
MULTI_SPLIT = ["┋", "；", ";", "|"]


def split_multi(v):
    v = str(v or "")
    for sep in MULTI_SPLIT[1:]:
        v = v.replace(sep, MULTI_SPLIT[0])
    return [x.strip() for x in v.split(MULTI_SPLIT[0]) if x.strip()]


def read_csv(path):
    with io.open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def find_col(rows, qid):
    """按题号或标题匹配列名（问卷导出的表头往往带题号或整句题干）"""
    keys = rows[0].keys()
    for k in keys:
        if k.strip().upper() == qid:
            return k
    for k in keys:
        if qid in k:
            return k
    return None


def tally(rows, qid, qtype):
    col = find_col(rows, qid)
    if col is None:
        return None
    if qtype == "multi":
        cnt = {}
        for r in rows:
            for x in split_multi(r.get(col, "") or ""):
                cnt[x] = cnt.get(x, 0) + 1
        return sorted(cnt.items(), key=lambda kv: -kv[1])
    cnt = {}
    for r in rows:
        v = (r.get(col, "") or "").strip()
        if not v:
            continue
        cnt[v] = cnt.get(v, 0) + 1
    if qtype == "likert":
        order = [str(i) for i in range(1, 6)]
        items = sorted(cnt.items(), key=lambda kv: float(kv[0]) if kv[0].replace('.', '').isdigit() else 99)
        return items
    return sorted(cnt.items(), key=lambda kv: -kv[1])


def likert_mean(items, n):
    s = 0.0
    tot = 0
    for k, c in items:
        try:
            s += float(k) * c
            tot += c
        except ValueError:
            pass
    return (s / tot if tot else 0.0), tot


# ---------------- SVG 图表（纯手绘，无第三方依赖） ----------------
PALETTE = ["#4C78C8", "#F58518", "#54A24B", "#E45756", "#B279A2",
           "#72B7B2", "#EEDA77", "#9D755D", "#BAB0AC"]


def bar_chart_svg(items, title, width=560, unit="人"):
    if not items:
        return "<p class='empty'>暂无数据</p>"
    total = sum(c for _, c in items) or 1
    rowh = 30
    left = 210
    height = rowh * len(items) + 46
    barw = width - left - 66
    parts = ["<svg viewBox='0 0 %d %d' class='chart'>" % (width, height)]
    parts.append("<text x='0' y='16' class='ct'>%s</text>" % html.escape(title))
    for i, (k, c) in enumerate(items):
        y = 34 + i * rowh
        w = barw * c / total
        parts.append("<text x='0' y='%d' class='lb'>%s</text>"
                     % (y + 14, html.escape(str(k)[:18])))
        parts.append("<rect x='%d' y='%d' width='%.1f' height='17' rx='3' fill='%s'/>"
                     % (left, y, max(w, 1.5), PALETTE[i % len(PALETTE)]))
        parts.append("<text x='%d' y='%d' class='vl'>%d%s %.0f%%</text>"
                     % (left + max(w, 1.5) + 7, y + 14, c, unit, 100.0 * c / total))
    parts.append("</svg>")
    return "".join(parts)


def likert_chart_svg(items, title, width=560):
    if not items:
        return "<p class='empty'>暂无数据</p>"
    total = sum(c for _, c in items) or 1
    height = 132
    bw = (width - 40) / 5.0
    parts = ["<svg viewBox='0 0 %d %d' class='chart'>" % (width, height)]
    parts.append("<text x='0' y='16' class='ct'>%s</text>" % html.escape(title))
    maxc = max(c for _, c in items) or 1
    for i in range(1, 6):
        c = dict(items).get(str(i), dict(items).get(i, 0))
        h = 74.0 * c / maxc
        x = 20 + (i - 1) * bw
        parts.append("<rect x='%.1f' y='%.1f' width='%.1f' height='%.1f' rx='3' fill='%s'/>"
                     % (x + 8, 100 - h, bw - 16, h, PALETTE[(i - 1) % len(PALETTE)]))
        parts.append("<text x='%.1f' y='%.1f' class='vl'>%d (%.0f%%)</text>"
                     % (x + 8, 96 - h, c, 100.0 * c / total))
        parts.append("<text x='%.1f' y='116' class='ax'>%d 分</text>" % (x + 8, i))
    mean, tot = likert_mean(items, total)
    parts.append("<text x='%d' y='16' class='mean'>均值 %.2f</text>" % (width - 96, mean))
    parts.append("</svg>")
    return "".join(parts)


def render_html(rows, out):
    n = len(rows)
    cards = []
    md = ["| 题号 | 题目 | 结果 |", "|---|---|---|"]
    for qid, title, qtype in QUESTIONS:
        items = tally(rows, qid, qtype)
        if items is None:
            continue
        if qtype == "likert":
            mean, tot = likert_mean(items, n)
            cards.append(likert_chart_svg(items, "%s %s" % (qid, title)))
            top = "；".join("%s分 %d人(%.0f%%)" % (k, c, 100.0 * c / (tot or 1))
                            for k, c in items)
            md.append("| %s | %s | **均值 %.2f / 5**（n=%d）<br>%s |"
                      % (qid, title, mean, tot, top))
        else:
            cards.append(bar_chart_svg(items, "%s %s" % (qid, title)))
            if qtype == "multi":
                top = "；".join("%s %d人(%.0f%%)" % (k, c, 100.0 * c / n)
                               for k, c in items[:5])
                md.append("| %s | %s | 多选，top5：%s |" % (qid, title, top))
            else:
                top = "；".join("%s %d人(%.0f%%)" % (k, c, 100.0 * c / n)
                               for k, c in items[:5])
                md.append("| %s | %s | %s |" % (qid, title, top))

    css = """
    body{font-family:'Microsoft YaHei',system-ui,sans-serif;background:#f6f7f9;
         margin:0;padding:28px;color:#1f2328}
    .wrap{max-width:1000px;margin:0 auto}
    h1{font-size:22px;margin:0 0 4px}
    .sub{color:#6b7280;font-size:13px;margin-bottom:22px}
    .cards{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px}
    .chart{width:100%;height:auto}
    .ct{font-size:13px;font-weight:600;fill:#111827}
    .lb{font-size:12px;fill:#374151}
    .vl{font-size:11px;fill:#6b7280}
    .ax{font-size:11px;fill:#9ca3af;text-anchor:middle}
    .mean{font-size:12px;fill:#b45309;font-weight:600}
    .empty{color:#9ca3af;font-size:12px}
    table{border-collapse:collapse;width:100%;background:#fff;margin-top:20px;
          border:1px solid #e5e7eb;font-size:13px}
    th,td{border:1px solid #e5e7eb;padding:7px 10px;text-align:left}
    th{background:#f3f4f6}
    """
    body = "\n".join("<div class='card'>%s</div>" % c for c in cards)
    doc = ("<html><head><meta charset='utf-8'><title>需求调研分析报告</title>"
           "<style>%s</style></head><body><div class='wrap'>"
           "<h1>需求调研分析报告</h1>"
           "<div class='sub'>样本量 %d 份 ｜ 面向机器人教学的虚拟仿真智能体平台</div>"
           "<div class='cards'>%s</div></div></body></html>" % (css, n, body))
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    return "\n".join(md)


def make_demo_csv(path, n=60):
    """生成一份模拟答卷，先看清楚产出长什么样（正式使用前请用真实数据替换）"""
    random.seed(7)
    rows = []
    ident = ["本科生（低年级）", "本科生（高年级）", "硕士研究生", "博士研究生"]
    q5 = ["设备数量少，排队等很久", "实验课时有限，做不完一个完整流程",
          "担心操作失误损坏设备", "缺少循序渐进的教程/示例",
          "场地、耗材、维护成本高", "需要专人指导，不敢自己试"]
    q6 = ["正运动学 / 逆运动学", "坐标系变换", "相机标定与手眼标定",
          "控制算法（PID、轨迹规划）", "视觉识别与定位",
          "多模块系统集成（感知→决策→执行串起来）"]
    q12 = ["语音下达指令", "更多机器人型号", "更多任务（码垛、装配、分拣）",
           "强化学习训练可视化", "故障注入与排错练习", "实验报告自动生成"]
    for _ in range(n):
        rows.append({
            "Q1": random.choice(ident),
            "Q2": str(random.randint(3, 5)),
            "Q3": random.choice(["是", "否"]),
            "Q4": random.choice(["从未", "1-2 次（演示课看过或摸过）", "3-5 次", "5 次以上"]),
            "Q5": "；".join(random.sample(q5, random.randint(1, 3))),
            "Q6": "；".join(random.sample(q6, random.randint(1, 3))),
            "Q7": random.choice(["撞坏设备", "编程太难", "不知道从哪开始", "没什么好担心的"]),
            "Q8": str(random.randint(3, 5)),
            "Q9": str(random.randint(3, 5)),
            "Q10": str(random.randint(3, 5)),
            "Q11": str(random.randint(2, 5)),
            "Q12": "；".join(random.sample(q12, random.randint(1, 3))),
        })
    with io.open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(here, "answers.csv"))
    ap.add_argument("--demo", action="store_true", help="用模拟数据先跑一遍看效果")
    ap.add_argument("--out", default=os.path.join(here, "report.html"))
    args = ap.parse_args()

    if args.demo:
        # 写到一个单独的名字，避免和真实回收数据 answers.csv 混在一起
        demo_csv = os.path.join(here, "answers_demo.csv")
        make_demo_csv(demo_csv)
        args.csv = demo_csv
        args.out = os.path.join(here, "report_demo.html")
        print("已生成模拟数据 %s（60 份），仅用于预览效果\n" % demo_csv)

    if not os.path.exists(args.csv):
        print("找不到 %s" % args.csv)
        print("  1) 把腾讯问卷/问卷星导出的 CSV 改名放到这里，或")
        print("  2) 先跑 python analyze.py --demo 看一眼产出")
        return 1

    rows = read_csv(args.csv)
    if not rows:
        print("CSV 是空的")
        return 1
    md = render_html(rows, args.out)
    print("样本量 %d 份\n" % len(rows))
    print("===== 可直接复制进方案文档的表格 =====\n")
    print(md)
    print("\n可视化报告：%s（双击打开 / 截图放进 PPT）" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
指令解析模块：把自然语言指令转成结构化的 {物体, 目标区域}。

两种模式：
1. LLM 模式（默认，需联网 + API Key）：调用通义千问 Qwen，输出 JSON
2. 规则模式（无需联网）：关键词匹配，保证任何情况下系统都能演示

比赛演示时建议：联网正常走 LLM，断网自动降级到规则模式 —— 这在报告里可以写成
「系统鲁棒性设计」，是加分项而不是缺陷。
"""

import json
import os
import re
import urllib.request

from config import BLOCK_COLORS, ZONE_COLORS

OBJECTS = list(BLOCK_COLORS.keys())
ZONES = list(ZONE_COLORS.keys())

API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
API_MODEL = "qwen-plus"

# 大模型额外输出的动作序列（用于报告展示「大模型输出可执行动作序列」）
DEFAULT_ACTIONS = ["move_above_obj", "down", "grab", "lift",
                   "move_above_zone", "down", "place"]

SYSTEM_PROMPT = (
    "你是机械臂任务规划助手。用户会下达物体搬运指令，你需要从中提取被搬运的物体和"
    "放置的目标区域，并严格按 JSON 输出，不要输出任何解释文字。\n"
    "可选物体：%s\n可选区域：%s\n"
    "输出格式：{\"object\":\"<物体>\",\"target\":\"<区域>\","
    "\"action_sequence\":[...],\"msg\":\"<简短中文提示>\"}\n"
    "示例：用户说“帮我把红色的那个搬到紫色那边” → "
    "{\"object\":\"红色方块\",\"target\":\"紫色区域\","
    "\"action_sequence\":%s,\"msg\":\"将红色方块搬运到紫色区域\"}"
) % ("、".join(OBJECTS), "、".join(ZONES), json.dumps(DEFAULT_ACTIONS, ensure_ascii=False))


def _clean_json_text(content):
    """清洗大模型返回：剥离 markdown 围栏，截取 JSON 主体。

    大模型有时会返回 ```json ... ``` 或以「好的，结果如下：」开头，
    直接正则找 {...} 容易把解释文字也卷进去，这里先做一次清洗。
    """
    if content is None:
        return ""
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) >= 2:
            content = parts[1]
        if content.lstrip().lower().startswith("json"):
            content = content.lstrip()[4:]
        content = content.strip()
    l, r = content.find("{"), content.rfind("}")
    if l != -1 and r != -1 and r > l:
        content = content[l:r + 1]
    return content


def _validate_schema(result):
    """校验大模型返回的结构，缺字段就补默认值，非法返回 None。"""
    if not isinstance(result, dict):
        return None
    if result.get("object") not in OBJECTS or result.get("target") not in ZONES:
        return None
    # action_sequence 缺失或类型不对时补默认值，不因此整体失败
    seq = result.get("action_sequence")
    result["action_sequence"] = seq if isinstance(seq, list) and seq else DEFAULT_ACTIONS
    result["msg"] = result.get("msg") or "将%s搬运到%s" % (result["object"], result["target"])
    result["source"] = "llm"
    return result


def parse_by_rules(text):
    """关键词兜底解析"""
    obj, zone = None, None
    for name in OBJECTS:
        if name[:2] in text:          # 红/绿/蓝 + 方块
            obj = name
            break
    if obj is None:
        for kw, name in (("红", "红色方块"), ("绿", "绿色方块"), ("蓝", "蓝色方块")):
            if kw in text:
                obj = name
                break
    for name in ZONES:
        if name[:2] in text:
            zone = name
            break
    if zone is None:
        for kw, name in (("黄", "黄色区域"), ("紫", "紫色区域")):
            if kw in text:
                zone = name
                break
    return {
        "object": obj or OBJECTS[0],
        "target": zone or ZONES[0],
        "action_sequence": DEFAULT_ACTIONS,
        "msg": "将%s搬运到%s" % (obj or OBJECTS[0], zone or ZONES[0]),
        "source": "rule",
    }


def parse_by_llm(text, api_key=None, timeout=8.0):
    """调用 Qwen 解析指令，失败返回 None"""
    api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = _clean_json_text(data["choices"][0]["message"]["content"])
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return None
        try:
            result = json.loads(m.group(0))
        except ValueError:
            return None
        return _validate_schema(result)
    except Exception as e:
        print("[LLM] 调用失败：%s（自动降级为规则解析）" % e)
        return None


def parse(text, use_llm=True, api_key=None):
    """统一入口：LLM 优先，失败自动降级"""
    if use_llm:
        r = parse_by_llm(text, api_key=api_key)
        if r:
            return r
    return parse_by_rules(text)


if __name__ == "__main__":
    for t in ["把红色方块放到紫色区域",
              "帮忙把那个绿色的搬到黄色那边",
              "蓝色方块拿起来放到黄区"]:
        print(t, "→", parse(t, use_llm=False))

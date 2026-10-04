# 新版 planner / vision：改对了一大半，还有两个致命 bug

> 先说好消息：**你这次改的方向全对**——区域改成颜色名、绿蓝映射修好了、
> `green_block` 的下划线也统一了。照这个速度再改一处就能合了。
> 但下面两处不改，演示现场一定会挂，而且挂得莫名其妙。

---

## 一、你已经改对的（确认一下）

| 项目 | 之前 | 现在 |
| --- | --- | --- |
| 区域命名 | `zoneA / zoneB` | ✅ `yellow_area / purple_area` |
| 绿色映射 | → `blue_block` ❌ | ✅ → `green_block` |
| 蓝色映射 | → `yellow_block` ❌ | ✅ → `blue_block` |
| vision 里的 key | `green-block`（短横线） | ✅ `green_block` |
| 区域命名（vision） | `zoneA / zoneB` | ✅ `yellow_area / purple_area` |

`planner` 里那个没用的 `\bA\b` 正则和 `import re` 也删掉了，对。

---

## 二、致命 bug 1：兜底分支没跟着改

```python
if target_zone is None:
    if "黄色" in text:
        target_zone = "yellow_block"    # ← 还是 block，应该是 yellow_area
    elif "紫色" in text:
        target_zone = "purple_block"    # ← 还是 block，应该是 purple_area
```

主词典你改对了，这个兜底分支漏了。**后果是：用户只要不说"区域"两个字，就挂。**

实测：

```
把红色方块放到紫色区域        -> purple_area     ✅
把绿色方块放到黄色区域        -> yellow_area     ✅

帮我把绿色的那个搬到黄色那边   -> yellow_block    ❌ 不存在
把蓝色方块放到黄色            -> yellow_block    ❌ 不存在
红色方块搬到紫色那边          -> purple_block    ❌ 不存在
把红色方块放到紫色            -> purple_block    ❌ 不存在
```

真人不会老老实实每次都说"区域"——「搬到黄色那边」才是正常说话方式。
而离线路径不做校验，会 `valid=True` 返回一个不存在的区域，机械臂不知道往哪放。

改成：

```python
if target_zone is None:
    if "黄色" in text:
        target_zone = "yellow_area"
    elif "紫色" in text:
        target_zone = "purple_area"
```

顺便加一句兜底（更稳）：

```python
ZONE_KEYWORDS = {
    "黄色区域": "yellow_area", "黄色": "yellow_area", "黄区": "yellow_area",
    "紫色区域": "purple_area", "紫色": "purple_area", "紫区": "purple_area",
}
```

这样连兜底分支都不用写了。

---

## 三、致命 bug 2：LLM 的 prompt 被删坏了

现在 prompt 只剩这些：

```
action_sequence: [...]
valid: true/false
msg: 简短中文提示
只输出JSON，不要别的文字。
```

**`target_obj` 和 `target_zone` 两段说明没了。**

你的 `_validate_schema` 要求必须有这两个字段（`REQUIRED_KEYS`），
但你既没告诉模型该输出哪两个字段，也没告诉它合法取值有哪些。
模型大概率瞎填或者不填 → 校验失败 → 降级到关键词。

**结果是云端路径几乎必然失败**，报告里"用了大模型"就只是写了没跑通。

补回去：

```
机械臂任务解析器。用户指令是把某个方块放到某个区域。输出 JSON，字段：
target_obj: red_block / green_block / blue_block / null
target_zone: yellow_area / purple_area / null
action_sequence: ["move_above_obj","down","grab","lift","move_above_zone","down","place"]
valid: true/false
msg: 简短中文提示
只输出JSON，不要别的文字。
用户指令：{}
```

---

## 四、残留的小尾巴（顺手清掉）

- `vision.py` 顶部注释还写着「3方块 + 2放置区域A、B」
- `HSV_RANGES` 那行末尾还挂着 `# zoneA yellow  zoneB purple    可以改`
- `planner.py` 注释掉的测试用例是「把红色方块放到紫色」——正好会命中 bug 1，
  你跑一下就能自己发现

---

## 五、还是没改的三条（不急，但要知道）

1. **Qwen 还是旧接口** —— `text-generation/generation` + `qwen-turbo`（已下线）。
   主线用的是 `compatible-mode/v1/chat/completions` + `qwen-plus`
2. **`requests` 我们环境里没装** —— 主线用标准库 `urllib`
3. **vision 的 HSV_RANGES 还是脱离 `config.py` 另起一套** —— 两处并存必然不同步

---

## 六、一个能一次消灭一类 bug 的建议

你的英文命名现在内部是统一的，但跟 `config.py` 对不上（`red_block` vs `红色方块`）。
**建议直接用中文，跟 `config.py` 一字不差**：

```
BLOCK_COLORS = 红色方块 / 绿色方块 / 蓝色方块
ZONE_COLORS  = 黄色区域 / 紫色区域
```

这样「名字对不上」这类 bug 一次性全消掉，也不用再维护映射表。

---

## 七、验证办法（跑通主线之后）

```bat
python main.py --no-llm
```

然后输这两条，看能不能都成功：

```
把红色方块放到紫色区域
帮我把绿色的那个搬到黄色那边
```

第二条现在会挂——改完上面 bug 1 就应该能过。

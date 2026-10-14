#!/usr/bin/env python3
"""讲解示意图：文档里的例子都能画、文字互不重叠，新增的数轴/配对弧/字母十字交叉按约定工作。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import draw_diagram as dd


def fails(spec, words):
    try:
        dd.render(spec)
    except dd.SpecError as exc:
        assert words in str(exc), (words, str(exc))
        return
    raise AssertionError(f"应当拒绝：{words}")


# 1. 说明文档里的每个例子都能出图，且没有文字重叠——文档和脚本不会悄悄脱节
doc = (HERE.parent / "hermes-skills/gd-gongkao-coach/references/diagram-drawing.md").read_text("utf-8")
examples = re.findall(r"```json\n(.*?)```", doc, re.S) + re.findall(r'`(\{"template":.*?\})`', doc)
assert len(examples) >= 19, len(examples)
for raw in examples:
    spec = json.loads(raw)
    assert not dd.layout_problems(dd.render(spec)), spec.get("title")

# 2. 原来会叠字的数轴：标签自动折成“数值 / 说明”两行，一层放下
drone = {"template": "line", "title": "无人机往返掉头位置规律", "length": 150,
         "points": [{"at": 30, "label": "原点 0"}, {"at": 45, "label": "+15 (第1次)"}, {"at": 15, "label": "-15 (第2次)"},
                    {"at": 60, "label": "+30 (第3次)"}, {"at": 0, "label": "-30 (第4次)"}, {"at": 150, "label": "+120 (目标)"}],
         "arrows": [{"from": 30, "to": 45, "label": "东15", "row": 1}, {"from": 45, "to": 15, "label": "西30", "row": -1},
                    {"from": 15, "to": 60, "label": "东45", "row": 2}, {"from": 60, "to": 0, "label": "西60", "row": -2}]}
svg = dd.render(drone)
assert ">(第4次)<" in svg and ">-30<" in svg, "标签应折成两行"
assert not dd.layout_problems(svg)

# 3. 真实坐标（负数）、断轴、刻度、长度验算
real = {"template": "line", "title": "往返", "range": [-30, 120], "breaks": [[40, 110]], "ticks": 15,
        "points": [{"at": -30, "label": "-30"}, {"at": 0, "label": "原点"}, {"at": 120, "label": "+120", "role": "answer"}],
        "arrows": [{"from": 0, "to": 15, "label": "东 15", "check": 15}, {"from": 15, "to": -15, "label": "西 30", "row": -1}]}
svg = dd.render(real)
assert svg.count('stroke-width="1.6"/>') >= 2, "断轴处要画双斜线"
fails({**real, "arrows": [{"from": 0, "to": 15, "check": 20}]}, "check")
fails({**real, "points": [{"at": 60, "label": "缝里"}]}, "breaks")
fails({**real, "range": [5, 1]}, "range")
fails({**real, "breaks": [[100, 130]]}, "breaks")

# 4. 同一行的箭头区间重叠时自动挪到下一行；说明字挤不下的短箭头也会挪
two = {"template": "line", "range": [0, 100],
       "arrows": [{"from": 0, "to": 60, "label": "甲走了很长的一段路程"}, {"from": 50, "to": 100, "label": "乙"}]}
ys = sorted({float(y) for y in re.findall(r'<line x1="[\d.]+" y1="([\d.]+)" x2="[\d.]+" y2="\1" stroke="#6b5428" '
                                          r'stroke-width="1.2" marker-end', dd.render(two))})
assert len(ys) == 2, ys
short = {"template": "line", "range": [0, 180],
         "arrows": [{"from": 54, "to": 120, "label": "前段剩余: 60 - 600/11 = 60/11"}, {"from": 120, "to": 136, "label": "后段增加: 180/11"}]}
assert not dd.layout_problems(dd.render(short))

# 5. 点密到三层都放不下就拒绝，并给出改法
crowd = {"template": "line", "range": [0, 10], "points": [{"at": i, "label": f"第{i}个非常非常长的标签"} for i in range(11)]}
fails(crowd, "点太密")

# 6. 最后一道检查：文字叠在一起或伸出画布都拒绝
overlap = ('<svg viewBox="0 0 200 100">'
           + dd.svg_text(50, 50, "甲乙丙丁", 15) + dd.svg_text(60, 52, "戊己庚", 15) + "</svg>")
assert dd.layout_problems(overlap)
assert dd.layout_problems('<svg viewBox="0 0 100 100">' + dd.svg_text(95, 50, "很长很长的字", 15) + "</svg>")
fails({"template": "venn2", "regions": {"a": {"text": "左边这块写得特别特别长"}, "ab": {"text": "中间这块也写得特别长"}}}, "叠在一起")
long_note = {"template": "cross", "a": {"label": "甲", "value": 20}, "b": {"label": "乙", "value": 50},
             "mix": {"label": "混合", "value": 30},
             "notes": ["1. 很长的一行说明：" + "，".join(["交叉作差得到份数"] * 8)]}
assert not dd.layout_problems(dd.render(long_note)), "过长的 notes 应自动折行"

# 7. 十字交叉：数字照常算比；写字母时只摆结构，适合知识点页的通用图
assert "2 : 1" in dd.render({"template": "cross", "a": {"name": "甲", "value": 20}, "b": {"name": "乙", "value": 50},
                             "mix": {"value": 30}})
sym = dd.render({"template": "cross", "a": {"name": "组1", "label": "组1均值", "value": "x1"},
                 "b": {"name": "组2", "label": "组2均值", "value": "x2"}, "mix": {"label": "总体均值", "value": "X"}})
assert "|X − x2|" in sym and "组1 : 组2 = |X − x2| : |X − x1|" in sym
fails({"template": "cross", "a": {"value": 20}, "b": {"value": 50}, "mix": {"value": 60}}, "介于")
fails({"template": "cross", "a": {"value": ""}, "b": {"value": 50}, "mix": {"value": 30}}, "value")

# 8. slots 配对弧：套在里面的弧更矮，弧顶说明不重叠
pairs = {"template": "slots", "items": [f"a{i}" for i in range(1, 11)],
         "links": [{"from": 0, "to": 9, "label": "a1 + a10", "role": "key"}, {"from": 1, "to": 8, "label": "a2 + a9"},
                   {"from": 2, "to": 7, "label": "a3 + a8"}, {"from": 3, "to": 6, "label": "a4 + a7"}]}
svg = dd.render(pairs)
assert svg.count("<path d=\"M") >= 4 and not dd.layout_problems(svg)
fails({**pairs, "links": [{"from": 3, "to": 3}]}, "link")
fails({**pairs, "bundles": [{"from": 0, "to": 1, "label": "绑"}]}, "links")

# 9. gantt 挨得近的时刻标注错层；捆绑框说明挨得近也错层
gantt = {"template": "gantt", "length": 10, "rows": [{"label": "甲", "segments": [{"from": 0, "to": 3.2}]}],
         "marks": [{"at": 3, "label": "乙加入"}, {"at": 3.2, "label": "丙离开"}, {"at": 3.4, "label": "完工"}]}
assert not dd.layout_problems(dd.render(gantt))
slots = {"template": "slots", "items": list("甲乙丙丁戊"),
         "bundles": [{"from": 0, "to": 1, "label": "甲乙内部 A(2,2) = 2"}, {"from": 2, "to": 3, "label": "丙丁内部 A(2,2) = 2"}]}
assert not dd.layout_problems(dd.render(slots))

# 10. 环形：12 点方向的刻度字不再顶到副标题
clock = {"template": "circle", "title": "10点区间两针真实的两次直角", "subtitle": "首次在 10:05(5/11)，再次在 10:38(2/11)",
         "length": 360, "points": [{"at": 0, "label": "12点整(0°)"}, {"at": 33, "label": "首次直角: 10:05(33°)"}],
         "arcs": [{"from": 0, "to": 33, "label": "追30°", "role": "answer", "ring": 1},
                  {"from": 0, "to": 229, "label": "追210°", "role": "key", "ring": 2}]}
assert not dd.layout_problems(dd.render(clock))

print("draw diagram ok")

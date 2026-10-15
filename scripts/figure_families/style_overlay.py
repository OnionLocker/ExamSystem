"""样式规律·叠加：九宫格，每格是方框里的若干条线段，每行第三格 = 前两格叠加（去同存异、去异存同、全部保留、求同……）。

和黑白块同一套办法，只是「块」换成方框内固定的 12 条线段位置（中横线、中竖线各两段，8 条半对角线）。
判题器只读 SVG：线段按端点坐标对回 12 个位置；规则族穷举行/列 16 种逐段布尔运算与线段数加减，推出的答案必须唯一。
干扰项按 I-RAVEN 两两平衡：正确叠加、换一种叠加方式、二者各错同一条线。
"""

from __future__ import annotations

import itertools
import random
import sys

from .core import LETTERS, Svg, options_sheet, parse

NAME = "style_overlay"
TAG = "判断推理-图形推理-样式规律"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "样式规律-叠加"
VERSION = 1
MAX_TRIES = 80
PARTS = ("figure", "options")
DEFINITION = ("样式规律·叠加：前两个图形叠在一起得到第三个——去同存异（相同的线去掉、不同的保留）、去异存同（只留相同的）、"
              "全部保留。逐条线比较前两图，归纳出是哪一种，再套到第三行。")
STEM = "从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性："

# 方框 [0,2]×[0,2] 内 12 条可选线段（不含外框）
SLOTS = [((0, 1), (1, 1)), ((1, 1), (2, 1)), ((1, 0), (1, 1)), ((1, 1), (1, 2))]
for (x, y) in ((0, 0), (1, 0), (0, 1), (1, 1)):
    SLOTS += [((x, y), (x + 1, y + 1)), ((x, y + 1), (x + 1, y))]
NS = len(SLOTS)
COMBOS = ((0, 0), (0, 1), (1, 0), (1, 1))
OPS = {
    "去同存异": (0, 1, 1, 0),
    "去异存同": (0, 0, 0, 1),
    "全部叠加": (0, 1, 1, 1),
    "第一图去掉第二图有的线": (0, 0, 1, 0),
}
ALL_OPS = list(itertools.product((0, 1), repeat=4))


def apply_op(t, a, b):
    return tuple(t[COMBOS.index((x, y))] for x, y in zip(a, b))


def generate(rng, difficulty):
    tier = difficulty if difficulty in ("easy", "mid", "hard") else rng.choice(("easy", "mid", "hard"))
    names = ("去同存异", "全部叠加") if tier == "easy" else tuple(OPS)
    name = rng.choice(names)
    op = OPS[name]
    p = rng.uniform(0.3, 0.5)
    rows = []
    for _ in range(3):
        a = tuple(int(rng.random() < p) for _ in range(NS))
        b = tuple(int(rng.random() < p) for _ in range(NS))
        rows.append([a, b, apply_op(op, a, b)])
    seen = {(x, y) for r in rows[:2] for x, y in zip(r[0], r[1])}
    panels = [c for r in rows for c in r]
    if len(seen) < 4 or len(set(panels)) < 9 or not all(1 <= sum(c) <= NS - 2 for c in panels):
        return None
    answer = rows[2][2]
    a, b = rows[2][0], rows[2][1]
    others = [apply_op(OPS[n], a, b) for n in OPS if n != name]
    others = [o for o in others if o != answer and sum(o) >= 1]
    if not others:
        return None
    wrong = rng.choice(others)
    same = [i for i in range(NS) if answer[i] == wrong[i]]
    if not same:
        return None
    cell = rng.choice(same)
    flip = lambda bits: tuple(v ^ (i == cell) for i, v in enumerate(bits))
    options = [answer, wrong, flip(answer), flip(wrong)]
    if len(set(options)) < 4 or not all(sum(o) >= 1 for o in options):
        return None
    matrix = [[list(c) for c in r] for r in rows]
    matrix[2][2] = None
    return {"stem": STEM, "rule": name, "matrix": matrix, "options": [list(o) for o in options], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
U = 30
BOX = 2 * U


def _panel(svg, x0, y0, bits, data):
    svg.rect(x0, y0, BOX, BOX, sw=2.2, data={**data, "frame": "1", "unit": U})
    to = lambda p: (x0 + p[0] * U, y0 + (2 - p[1]) * U)
    for i, on in enumerate(bits or []):
        if on:
            a, b = SLOTS[i]
            svg.line(to(a), to(b), w=2.4, data={**data, "seg": "1"})


def render(draft, order):
    gap, pad = 28, 14
    size = 2 * pad + 3 * BOX + 2 * gap
    figure = Svg(size, size)
    for r, c in itertools.product(range(3), range(3)):
        x0, y0 = pad + c * (BOX + gap), pad + r * (BOX + gap)
        bits = draft["matrix"][r][c]
        if bits is None:
            figure.rect(x0, y0, BOX, BOX, sw=2.2)
            figure.text((x0 + BOX / 2, y0 + BOX / 2), "?", size=30)
        else:
            _panel(figure, x0, y0, bits, {"slot": f"{r},{c}"})
    cells = {LETTERS[i]: (lambda svg, b=draft["options"][j]: _panel(svg, 8, 8, b, {})) for i, j in enumerate(order)}
    sheet = options_sheet(cells, BOX + 16, BOX + 16, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def _read(prims, key):
    frames, bits = {}, {}
    for p in prims:
        gid = p.data.get(key)
        if gid is not None and p.data.get("frame"):
            frames[gid] = (p.local()[0], float(p.data["unit"]))
    for gid in frames:
        bits[gid] = [0] * NS
    for p in prims:
        gid = p.data.get(key)
        if gid in frames and p.data.get("seg"):
            (x0, y0), u = frames[gid]
            ends = [(round((x - x0) / u, 3), round(2 - (y - y0) / u, 3)) for x, y in p.local()]
            seg = tuple(sorted(ends))
            match = [i for i, s in enumerate(SLOTS) if tuple(sorted(s)) == seg]
            if len(match) != 1:
                raise ValueError(f"线段画在约定位置之外：{seg}")
            bits[gid][match[0]] = 1
    return {k: tuple(v) for k, v in bits.items()}


def predictions(m):
    out = []
    for t in ALL_OPS:
        if all(apply_op(t, m[r][0], m[r][1]) == m[r][2] for r in (0, 1)):
            out.append((f"行：逐线运算{t}", apply_op(t, m[2][0], m[2][1])))
        if all(apply_op(t, m[0][c], m[1][c]) == m[2][c] for c in (0, 1)):
            out.append((f"列：逐线运算{t}", apply_op(t, m[0][2], m[1][2])))
    for label, f in (("和", lambda x, y: x + y), ("差", lambda x, y: abs(x - y))):
        if all(f(sum(m[r][0]), sum(m[r][1])) == sum(m[r][2]) for r in (0, 1)):
            out.append((f"行：线条数第三格=前两格之{label}", f(sum(m[2][0]), sum(m[2][1]))))
    if all(sum(m[r][0]) == sum(m[r][1]) == sum(m[r][2]) for r in (0, 1)):
        out.append(("行：线条数相同", sum(m[2][0])))
    return out


def judge(svgs, pngs=None, stem=None, texts=None):
    cells = _read(parse(svgs["figure"]), "slot")
    options = _read(parse(svgs["options"]), "option")
    if len(cells) != 8 or sorted(options) != list(LETTERS):
        raise ValueError("九宫格或选项不全")
    m = [[cells.get(f"{r},{c}") for c in range(3)] for r in range(3)]
    rules = []
    for rule, pred in predictions(m):
        chosen = sorted(k for k, o in options.items() if (sum(o) == pred if isinstance(pred, int) else o == pred))
        if 0 < len(chosen) < 4:
            rules.append((rule, chosen))
    issues = []
    picks = {tuple(c) for _, c in rules}
    if len(picks) > 1 or any(len(c) > 1 for _, c in rules):
        issues.append("规律不唯一：" + "；".join(f"{r}→{''.join(c)}" for r, c in rules))
    if len(set(options.values())) < 4:
        issues.append("有两个选项画得一样")
    correct = list(rules[0][1]) if len(picks) == 1 and rules else sorted({k for _, c in rules for k in c})
    if len(correct) == 1:
        key = correct[0]
        dist = {k: sum(sum(x != y for x, y in zip(v, w)) for o, w in options.items() if o != k) for k, v in options.items()}
        if dist[key] < min(v for k, v in dist.items() if k != key):
            issues.append("只看选项就能猜：答案是四个选项的「中心」")
    tables = [t for t in ALL_OPS if all(apply_op(t, m[r][0], m[r][1]) == m[r][2] for r in (0, 1))]
    return {"correct": correct, "issues": issues, "table": list(tables[0]) if len(tables) == 1 else None}


def explain(verdict, key):
    table = verdict.get("table")
    if not table:
        return "每行前两个图形叠加得到第三个图形。"
    name = next((n for n, t in OPS.items() if list(t) == table), None)
    how = {"去同存异": "相同的线去掉、不同的线保留", "去异存同": "只保留两图相同的线", "全部叠加": "两图的线全部保留",
           "第一图去掉第二图有的线": "第一图去掉与第二图重合的线"}.get(name, "按同一种方式叠加")
    return (f"每行前两个图形叠加得到第三个图形，规律是{name or '固定叠加'}：{how}。"
            f"第三行前两个图形照此叠加得到 {key} 项。其余选项或换了一种叠加方式，或多/少了一条线，排除。")


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]

    def build(draft, order):
        svgs = render(draft, order)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    draft, order, svgs, pngs = verified(me, "self-test", "mid", "D")
    issues, _ = check(me, svgs, pngs, "D")
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "A")
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    broken = dict(draft, matrix=[[r[0], r[1], r[2]] for r in draft["matrix"]])
    first = list(broken["matrix"][0][2])
    k = first.index(1)
    first[k] = 0
    broken["matrix"][0][2] = first
    issues, _ = check(me, *build(broken, order), "D")
    out.append(("第一行结果少画一条线", bool(issues), "；".join(issues)))
    return out

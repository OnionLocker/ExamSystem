"""位置规律：方格里的黑点、白圈、黑三角按固定规律移动。

规律族：沿外圈顺/逆时针走 k 格、按行（从左到右、到头换行）走 k 格、按列走 k 格、原地不动、
整个方格每次顺/逆时针转 90°。每种标记各走各的规律。五格一行，最后一格是问号。

判题器只读 SVG：按画出的坐标把每个标记放回方格，对每种标记穷举规律族里所有规律，
和前四格对得上的都推一个第五格；不同规律推出不同选项就打回。干扰项是「少走一步、多走一步、两种标记对调」。
"""

from __future__ import annotations

import random
import sys

from .core import LETTERS, Svg, options_sheet, parse

NAME = "position"
TAG = "判断推理-图形推理-位置规律"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "位置规律"
VERSION = 1
MAX_TRIES = 80
PARTS = ("figure", "options")
DEFINITION = ("位置规律：元素在方格中平移（沿外圈或按行列走固定步数）、旋转或翻转。"
              "先分开看每种元素，数相邻两图之间走了几格、往哪个方向，再推下一步。")
STEM = "从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性："

MARKS = ("dot", "ring", "tri")
NAMES = {"dot": "黑点", "ring": "白圈", "tri": "黑三角"}


def border(n):
    """外圈格子按顺时针排的序列（行列从左上角 (0,0) 开始，r 向下）。"""
    out = [(0, c) for c in range(n)] + [(r, n - 1) for r in range(1, n)]
    out += [(n - 1, c) for c in range(n - 2, -1, -1)] + [(r, 0) for r in range(n - 2, 0, -1)]
    return out


def rules(n):
    """规律族：名字 -> 走一步的函数 (r, c) -> (r, c)。"""
    ring = border(n)
    out = {"不动": lambda p: p}
    for k in (1, 2, 3):
        for sign, way in ((1, "顺"), (-1, "逆")):
            out[f"沿外圈{way}时针走 {k} 格"] = (lambda p, k=k * sign: ring[(ring.index(p) + k) % len(ring)] if p in ring else None)
        out[f"按行从左往右走 {k} 格"] = (lambda p, k=k: divmod((p[0] * n + p[1] + k) % (n * n), n))
        out[f"按行从右往左走 {k} 格"] = (lambda p, k=k: divmod((p[0] * n + p[1] - k) % (n * n), n))
        out[f"按列从上往下走 {k} 格"] = (lambda p, k=k: tuple(reversed(divmod((p[1] * n + p[0] + k) % (n * n), n))))
        out[f"按列从下往上走 {k} 格"] = (lambda p, k=k: tuple(reversed(divmod((p[1] * n + p[0] - k) % (n * n), n))))
    out["整体顺时针转 90°"] = lambda p: (p[1], n - 1 - p[0])
    out["整体逆时针转 90°"] = lambda p: (n - 1 - p[1], p[0])
    return out


TIER = {"easy": (3, 1), "mid": (4, 2), "hard": (4, 3)}


def generate(rng, difficulty):
    tier = difficulty if difficulty in TIER else rng.choice(("easy", "mid", "mid", "hard"))
    n, kinds = TIER[tier]
    family = rules(n)
    names = [k for k in family if k != "不动"]
    marks = rng.sample(MARKS, kinds)
    plan = {}
    for m in marks:
        rule = rng.choice(names)
        if rule.startswith("沿外圈"):
            start = rng.choice(border(n))
        else:
            start = (rng.randrange(n), rng.randrange(n))
        path = [start]
        for _ in range(4):
            nxt = family[rule](path[-1])
            if nxt is None:
                return None
            path.append(nxt)
        plan[m] = (rule, path)
    panels = [{m: list(plan[m][1][i]) for m in marks} for i in range(5)]
    # 同一格不能放两个标记
    if any(len({tuple(v) for v in p.values()}) < len(p) for p in panels):
        return None
    answer = panels[4]
    wrong = []
    for m in marks:
        rule, path = plan[m]
        wrong.append({**answer, m: list(path[3])})  # 少走一步
        after = family[rule](path[4])
        if after is not None:
            wrong.append({**answer, m: list(after)})  # 多走一步
    if len(marks) >= 2:
        a, b = marks[:2]
        wrong.append({**answer, a: answer[b], b: answer[a]})
    wrong.append({m: [p[1], p[0]] for m, p in answer.items()})  # 沿对角线翻
    picked = []
    for w in wrong:
        if len({tuple(v) for v in w.values()}) < len(w) or w == answer or w in picked:
            continue
        picked.append(w)
    rng.shuffle(picked)
    if len(picked) < 3:
        return None
    return {"stem": STEM, "n": n, "plan": {m: r for m, (r, _) in plan.items()}, "panels": panels[:4],
            "options": [answer] + picked[:3], "answer": 0, "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
CELL = 22


def _grid(svg, n, x0, y0, marks, data):
    svg.rect(x0, y0, n * CELL, n * CELL, sw=2.0, data={**data, "grid": str(n), "cell": CELL})
    for k in range(1, n):
        svg.line((x0 + k * CELL, y0), (x0 + k * CELL, y0 + n * CELL), w=1.2)
        svg.line((x0, y0 + k * CELL), (x0 + n * CELL, y0 + k * CELL), w=1.2)
    for m, (r, c) in marks.items():
        cx, cy = x0 + (c + 0.5) * CELL, y0 + (r + 0.5) * CELL
        if m == "dot":
            svg.circle((cx, cy), CELL * 0.3, fill="#111111", w=0, data={**data, "mark": m})
        elif m == "ring":
            svg.circle((cx, cy), CELL * 0.3, w=2.0, data={**data, "mark": m})
        else:
            h = CELL * 0.32
            svg.poly([(cx, cy - h), (cx + h, cy + h * 0.8), (cx - h, cy + h * 0.8)], closed=True, fill="#111111", w=0,
                     data={**data, "mark": m})


def render(draft, order):
    n = draft["n"]
    size = n * CELL
    gap = 16
    figure = Svg(5 * size + 4 * gap + 20, size + 20)
    for i, marks in enumerate(draft["panels"]):
        _grid(figure, n, 10 + i * (size + gap), 10, {k: tuple(v) for k, v in marks.items()}, {"panel": str(i)})
    x = 10 + 4 * (size + gap)
    figure.rect(x, 10, size, size, sw=2.0)
    figure.text((x + size / 2, 10 + size / 2), "?", size=30)
    cells = {LETTERS[i]: (lambda svg, mk=draft["options"][j]: _grid(svg, n, 8, 8, {k: tuple(v) for k, v in mk.items()}, {}))
             for i, j in enumerate(order)}
    sheet = options_sheet(cells, size + 16, size + 16, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def _read(prims, key):
    grids, marks = {}, {}
    for p in prims:
        gid = p.data.get(key)
        if gid is None:
            continue
        if p.data.get("grid"):
            x0, y0 = p.local()[0]
            grids[gid] = (x0, y0, int(p.data["grid"]), float(p.data["cell"]))
    for p in prims:
        gid = p.data.get(key)
        if gid in grids and p.data.get("mark"):
            x0, y0, n, cell = grids[gid]
            pts = p.local()
            cx = sum(x for x, _ in pts) / len(pts)
            cy = sum(y for _, y in pts) / len(pts)
            if p.tag == "polygon":  # 三角形的形心偏下，按外接框中心算
                xs, ys = [x for x, _ in pts], [y for _, y in pts]
                cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            r, c = int((cy - y0) // cell), int((cx - x0) // cell)
            if not (0 <= r < n and 0 <= c < n):
                raise ValueError("标记画到方格外面了")
            cell_marks = marks.setdefault(gid, {})
            if p.data["mark"] in cell_marks:
                raise ValueError("同一种标记画了两个")
            cell_marks[p.data["mark"]] = (r, c)
    return grids, marks


def judge(svgs, pngs=None, stem=None, texts=None):
    grids, panels = _read(parse(svgs["figure"]), "panel")
    ogrids, options = _read(parse(svgs["options"]), "option")
    if sorted(panels) != ["0", "1", "2", "3"] or sorted(options) != list(LETTERS):
        raise ValueError("方格或选项不全")
    n = grids["0"][2]
    family = rules(n)
    seq = [panels[str(i)] for i in range(4)]
    kinds = set(seq[0])
    issues = []
    if any(set(p) != kinds for p in seq):
        issues.append("各图标记种类不一致")
    predictions = {}
    for m in kinds:
        preds = {}
        for name, step in family.items():
            ok = True
            for i in range(3):
                nxt = step(seq[i][m])
                if nxt is None or tuple(nxt) != seq[i + 1][m]:
                    ok = False
                    break
            if ok:
                nxt = step(seq[3][m])
                if nxt is not None:
                    preds.setdefault(tuple(nxt), []).append(name)
        if len(preds) > 1:
            issues.append(f"{NAMES[m]}的走法不唯一：" + "；".join(v[0] for v in preds.values()))
        predictions[m] = preds
    if any(not preds for preds in predictions.values()):
        correct = []
    else:
        target = {m: next(iter(p)) for m, p in predictions.items()}
        correct = [k for k, o in options.items() if set(o) == kinds and all(o[m] == target[m] for m in kinds)]
    if len({tuple(sorted(o.items())) for o in options.values()}) < 4:
        issues.append("有两个选项一样")
    return {"correct": correct, "issues": issues,
            "rules": {m: next(iter(p.values()))[0] for m, p in predictions.items() if len(p) == 1}}


def explain(verdict, key):
    parts = [f"{NAMES[m]}每次{rule}" for m, rule in sorted(verdict["rules"].items())]
    return ("分开看每种标记：" + "；".join(parts) + f"。按此推出问号处，{key} 项各标记位置都对，当选。"
            "其余选项有标记少走或多走了一步，或两种标记位置对调，排除。")


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]

    def build(draft, order):
        svgs = render(draft, order)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    ring = border(4)
    out.append(("4×4 外圈 12 格顺时针", len(ring) == 12 and ring[3] == (0, 3) and ring[6] == (3, 3), str(ring[:7])))
    draft, order, svgs, pngs = verified(me, "self-test", "mid", "C")
    issues, _ = check(me, svgs, pngs, "C")
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "D")
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    moved = [dict(p) for p in draft["panels"]]
    m = next(iter(moved[2]))
    r, c = moved[2][m]
    spot = next((rr, cc) for rr in range(draft["n"]) for cc in range(draft["n"])
                if [rr, cc] not in moved[2].values() and (rr, cc) != (r, c))
    moved[2][m] = list(spot)
    issues, _ = check(me, *build(dict(draft, panels=moved), order), "C")
    out.append(("题干第三格标记画错位置", bool(issues), "；".join(issues)))
    twin = dict(draft, options=[draft["options"][0], draft["options"][0], draft["options"][2], draft["options"][3]])
    issues, _ = check(me, *build(twin, order), "C")
    out.append(("两个选项一样", bool(issues), "；".join(issues)))
    return out

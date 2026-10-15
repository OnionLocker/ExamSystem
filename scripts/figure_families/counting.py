"""数量规律：点、线、面、笔画、部分数。图形由格点上的线段和圆组成，数量用平面图精确计算。

生成器：挑一种数量（面数、直线数、曲线数、笔画数、部分数、交点数）和一条规律（逐个加一、加二、
减一、恒定），按目标数值反复随机构图；干扰项是同风格、只是这个数量不对的图。

判题器只读 SVG：线段和圆按画出的坐标重建平面图（在交点处打断），算出每张图的全部数量；
在写明的规则族里穷举（每种数量 × 恒定/等差±1/±2），凡是和前几张对得上的规律都推一个答案，
四个选项里只能有一个被推中。答案不能只靠「它和别的选项长得不一样」就猜出来。
"""

from __future__ import annotations

import itertools
import math
import random
import sys

from shapely.geometry import LineString, Point
from shapely.ops import polygonize

from .core import LETTERS, Svg, options_sheet, parse

NAME = "counting"
TAG = "判断推理-图形推理-数量规律"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "数量规律"
VERSION = 1
MAX_TRIES = 120
PARTS = ("figure", "options")
DEFINITION = ("数量规律：数点、线、面、笔画、部分。面数数封闭区域；直线数拐弯算两条；笔画数看奇点个数（0 或 2 个奇点一笔画成，"
              "否则笔画数 = 奇点数 ÷ 2）；部分数数互不相连的块。先看图形是否都封闭、是否都相连，定下数什么再找规律。")
STEM = "从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性："

PROPS = {"faces": "面数（封闭区域）", "lines": "直线数", "curves": "曲线数", "strokes": "笔画数",
         "parts": "部分数", "points": "交点数"}


# ---------------------------------------------------------------- 数量计算（生成器和判题器共用的定义；判题器只喂它从 SVG 读回的几何）
TOL = 1e-3  # 网格单位；SVG 坐标保留两位小数，读回来的误差远小于它


def _snap(p):
    return (round(p[0] / TOL) * TOL, round(p[1] / TOL) * TOL)


def _primitives(segments, circles):
    """每个图元拆成直线小段：线段一段；圆用 96 边形近似（四个正方向和斜方向都是顶点）。"""
    prims = []
    for a, b in segments:
        prims.append([(tuple(a), tuple(b))])
    for (cx, cy), r in circles:
        ring = [(cx + r * math.cos(2 * math.pi * k / 96), cy + r * math.sin(2 * math.pi * k / 96)) for k in range(96)]
        prims.append([(ring[k], ring[(k + 1) % 96]) for k in range(96)])
    return prims


def _node(prims):
    """在所有交点和 T 字接头处打断，坐标吸附到 TOL 网格，返回 (小段列表, 交点 -> 涉及的图元集合)。"""
    edges = [(i, LineString(e)) for i, prim in enumerate(prims) for e in prim]
    boxes = []
    for _, e in edges:
        x0, y0, x1, y1 = e.bounds
        boxes.append((x0 - TOL, y0 - TOL, x1 + TOL, y1 + TOL))
    cuts = {k: {0.0, edge.length} for k, (_, edge) in enumerate(edges)}
    touch = {}
    for a in range(len(edges)):
        ia, ea = edges[a]
        ax0, ay0, ax1, ay1 = boxes[a]
        for b in range(a + 1, len(edges)):
            ib, eb = edges[b]
            if ia == ib and len(prims[ia]) > 1:
                continue  # 同一个圆上的小段本来就首尾相接
            bx0, by0, bx1, by1 = boxes[b]
            if bx0 > ax1 or bx1 < ax0 or by0 > ay1 or by1 < ay0:
                continue
            if ea.distance(eb) > TOL:
                continue
            found = []
            for q in (Point(ea.coords[0]), Point(ea.coords[-1])):
                if eb.distance(q) < TOL:
                    found.append(q)
            for q in (Point(eb.coords[0]), Point(eb.coords[-1])):
                if ea.distance(q) < TOL:
                    found.append(q)
            inter = ea.intersection(eb)
            for g in getattr(inter, "geoms", [inter]):
                if g.is_empty:
                    continue
                if g.geom_type != "Point":
                    if ia != ib:
                        raise ValueError("两条线重叠，数不清")
                    continue
                found.append(g)
            for q in found:
                cuts[a].add(ea.project(q))
                cuts[b].add(eb.project(q))
                if ia != ib:
                    touch.setdefault(_snap((q.x, q.y)), set()).update((ia, ib))
    pieces = []
    for k, (_, edge) in enumerate(edges):
        ts = sorted(cuts[k])
        for t0, t1 in zip(ts, ts[1:]):
            if t1 - t0 < TOL:
                continue
            p0, p1 = edge.interpolate(t0), edge.interpolate(t1)
            a, b = _snap((p0.x, p0.y)), _snap((p1.x, p1.y))
            if a != b:
                pieces.append((a, b))
    return list(dict.fromkeys(tuple(sorted(pc)) for pc in pieces)), touch


def measure(segments, circles):
    """segments: [((x1,y1),(x2,y2))]，circles: [((cx,cy), r)]。返回各数量（面、直线、曲线、笔画、部分、交点）。"""
    prims = _primitives(segments, circles)
    if not prims:
        return {**{k: 0 for k in PROPS}, "crowd": ""}
    pieces, touch = _node(prims)
    faces = len(list(polygonize([LineString(pc) for pc in pieces])))
    degree, parent = {}, {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in pieces:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
        parent[find(a)] = find(b)
    comps = {}
    for node, deg in degree.items():
        comps.setdefault(find(node), []).append(deg)
    strokes = sum(max(1, sum(d % 2 for d in degs) // 2) for degs in comps.values())
    return {"faces": faces, "lines": len(segments), "curves": len(circles), "strokes": strokes,
            "parts": len(comps), "points": len(touch), "crowd": _crowd(pieces, degree, segments)}


def _crowd(pieces, degree, segments):
    """看不看得清：交接点离得太近、夹角太小、一个点连太多线，考生都数不准。返回问题描述或空串。"""
    ends = {_snap(tuple(c)) for s in segments for c in s}
    feature = [n for n, d in degree.items() if d != 2 or n in ends]
    for i, a in enumerate(feature):
        for b in feature[i + 1:]:
            if math.dist(a, b) < 0.35:
                return "两个交接点挨得太近"
    spokes = {}
    for a, b in pieces:
        spokes.setdefault(a, []).append(math.atan2(b[1] - a[1], b[0] - a[0]))
        spokes.setdefault(b, []).append(math.atan2(a[1] - b[1], a[0] - b[0]))
    for node, dirs in spokes.items():
        if degree.get(node, 0) >= 5:
            return "一个点上连了太多条线"
        if degree.get(node, 0) >= 2 and (degree[node] >= 3 or node in ends):
            dirs = sorted(dirs)
            gaps = [(dirs[(k + 1) % len(dirs)] - dirs[k]) % (2 * math.pi) for k in range(len(dirs))]
            if min(gaps) < math.radians(14):
                return "有两条线夹角太小"
    return ""


# ---------------------------------------------------------------- 构图：先放一个规整外框（正方形、长方形、三角形、菱形、圆），再加内部连线
GRID = 5  # 格点 0..4


KINDS = ("square", "rect", "tri", "rtri", "diamond", "circle")


def _outline(rng, kinds=KINDS, area=(0, 0, 4, 4)):
    x0, y0, x1, y1 = area
    kind = rng.choice(kinds)
    if kind == "circle":
        r = rng.choice((1.0, 1.5, 2.0))
        cx = rng.choice([v / 2 for v in range(int(2 * (x0 + r)), int(2 * (x1 - r)) + 1)] or [None])
        cy = rng.choice([v / 2 for v in range(int(2 * (y0 + r)), int(2 * (y1 - r)) + 1)] or [None])
        if cx is None or cy is None:
            return None
        return [], [((cx, cy), r)], kind
    w = rng.randint(2, x1 - x0)
    h = w if kind in ("square", "diamond") else rng.randint(2, y1 - y0)
    if w > x1 - x0 or h > y1 - y0:
        return None
    ax = rng.randint(x0, x1 - w)
    ay = rng.randint(y0, y1 - h)
    if kind in ("square", "rect"):
        pts = [(ax, ay), (ax + w, ay), (ax + w, ay + h), (ax, ay + h)]
    elif kind == "tri":
        if w % 2:
            return None
        pts = [(ax, ay), (ax + w, ay), (ax + w // 2, ay + h)]
    elif kind == "rtri":
        pts = [(ax, ay), (ax + w, ay), (ax, ay + h)]
    else:
        if w % 2:
            return None
        cx, cy = ax + w // 2, ay + h // 2
        pts = [(cx, ay), (ax + w, cy), (cx, ay + h), (ax, cy)]
    segs = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    return segs, [], kind


def _boundary_points(segs, circs):
    """外框上可以连弦的点：多边形边上的格点；圆上取八个方向的点（坐标都是 0.5 的倍数，画出来不失真）。"""
    if circs:
        (cx, cy), r = circs[0]
        out = [(cx + r, cy), (cx - r, cy), (cx, cy + r), (cx, cy - r)]
        return [q for q in out if all(abs(v * 2 - round(v * 2)) < 1e-9 for v in q)]
    pts = set()
    for (ax, ay), (bx, by) in segs:
        n = max(abs(bx - ax), abs(by - ay))
        for k in range(n + 1):
            x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
            if abs(x - round(x)) < 1e-9 and abs(y - round(y)) < 1e-9:
                pts.add((round(x), round(y)))
    return sorted(pts)


def _figure(rng, extra, kinds=KINDS):
    base = _outline(rng, kinds)
    if base is None:
        return None
    segs, circs, kind = base
    segs = list(segs)
    pts = _boundary_points(segs, circs)
    goal = len(segs) + extra
    for _ in range(extra * 8):
        if len(segs) >= goal or len(pts) < 2:
            break
        a, b = rng.sample(pts, 2)
        cand = (min(a, b), max(a, b))
        if any(_collinear_overlap(cand, t) for t in segs):
            continue
        segs.append(cand)  # 弦的两端都在外框上，不留悬空线头
    return segs, circs


def _parts(rng, n):
    """n 个互不相连的小图形（部分数题用）。"""
    cells = rng.sample([(0, 0), (2, 0), (0, 2), (2, 2), (1, 1), (3, 1), (1, 3), (3, 3)], n)
    segs, circs = [], []
    for cx, cy in cells:
        kind = rng.choice(("sq", "tri", "circ", "line"))
        if kind == "sq":
            segs += [((cx, cy), (cx + 1, cy)), ((cx + 1, cy), (cx + 1, cy + 1)), ((cx + 1, cy + 1), (cx, cy + 1)), ((cx, cy + 1), (cx, cy))]
        elif kind == "tri":
            segs += [((cx, cy), (cx + 1, cy)), ((cx + 1, cy), (cx, cy + 1)), ((cx, cy + 1), (cx, cy))]
        elif kind == "circ":
            circs.append(((cx + 0.5, cy + 0.5), 0.45))
        else:
            segs.append(((cx, cy), (cx + 1, cy + 1)))
    return segs, circs


def _collinear_overlap(s, t):
    a, b = LineString(s), LineString(t)
    inter = a.intersection(b)
    return inter.geom_type in ("LineString", "MultiLineString") and inter.length > 1e-9


def _figure_with(rng, prop, value, style, tries=600):
    for _ in range(tries):
        if prop == "parts":
            if value > 4:
                return None
            fig = _parts(rng, value)
        else:
            fig = _figure(rng, rng.randint(*style["extra"]), style["kinds"])
        if fig is None:
            continue
        segs, circs = fig
        try:
            m = measure(segs, circs)
        except ValueError:
            continue
        if m[prop] == value and not m["crowd"] and (prop == "parts" or m["parts"] == 1):
            return segs, circs, m
    return None


TIERS = {"easy": ("faces", "lines", "parts"), "mid": ("faces", "lines", "strokes", "parts"),
         "hard": ("strokes", "points", "faces")}


RANGE = {  # 每种数量在这种构图下稳定画得出来的范围
    "easy": {"faces": (1, 5), "lines": (3, 6), "parts": (1, 4)},
    "mid": {"faces": (1, 6), "lines": (3, 7), "strokes": (1, 4), "parts": (1, 4)},
    "hard": {"faces": (1, 7), "strokes": (1, 4), "points": (2, 9)},
}


def generate(rng, difficulty):
    tier = difficulty if difficulty in TIERS else rng.choice(("easy", "mid", "mid", "hard"))
    prop = rng.choice(TIERS[tier])
    lo, hi = RANGE[tier][prop]
    steps = [st for st in (1, 1, 0, -1, 2) if hi - lo >= 4 * abs(st)]
    step = rng.choice(steps)
    first = rng.randint(lo + max(0, -4 * step), hi - max(0, 4 * step))
    values = [first + step * i for i in range(5)]
    rule = {1: "+1", 2: "+2", -1: "-1", 0: "const"}[step]
    kinds = rng.sample(KINDS, rng.choice((1, 2)))  # 一道题里的图风格统一：只用一两种外框
    style = {"extra": (0, 3) if tier != "hard" else (1, 4), "kinds": kinds}
    if prop == "strokes":  # 笔画数靠弦端点造奇点，弦要多一些
        style["extra"] = (1, 4)
        style["kinds"] = [k for k in kinds if k != "circle"] or ["square"]
    panels = []
    for v in values[:4]:
        made = _figure_with(rng, prop, v, style)
        if made is None:
            return None
        panels.append(made[:2])
    answer = values[4]
    wrong_values = [v for v in (answer + 1, answer - 1, answer + 2, answer - 2) if lo <= v <= hi and v != answer]
    if len(wrong_values) < 3:
        wrong_values += [v for v in range(lo, hi + 1) if v != answer and v not in wrong_values]
    rng.shuffle(wrong_values)
    made = _figure_with(rng, prop, answer, style)
    if made is None:
        return None
    options = [made[:2]]
    for v in wrong_values:
        made = _figure_with(rng, prop, v, style)
        if made is not None:
            options.append(made[:2])
        if len(options) == 4:
            break
    if len(options) < 4:
        return None
    return {"stem": STEM, "prop": prop, "rule": rule, "values": values,
            "panels": [_dump(p) for p in panels], "options": [_dump(o) for o in options], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


def _dump(fig):
    segs, circs = fig
    return {"segs": [[list(a), list(b)] for a, b in segs], "circs": [[list(c), r] for c, r in circs]}


# ---------------------------------------------------------------- 渲染
CELL = 22  # 格点间距
BOX = CELL * 4 + 28


def _draw(svg, fig, x0, y0, data):
    to = lambda p: (x0 + 14 + p[0] * CELL, y0 + 14 + (4 - p[1]) * CELL)
    svg.rect(x0, y0, BOX, BOX, sw=1.6, data={**data, "frame": "1", "cell": CELL, "ox": x0 + 14, "oy": y0 + 14 + 4 * CELL})
    for a, b in fig["segs"]:
        svg.line(to(a), to(b), w=2.4, data={**data, "seg": "1"})
    for c, r in fig["circs"]:
        svg.circle(to(c), r * CELL, w=2.4, data={**data, "circ": "1", "r": r * CELL})


def render(draft, order):
    gap = 14
    figure = Svg(5 * BOX + 4 * gap + 20, BOX + 20)
    for i, fig in enumerate(draft["panels"]):
        _draw(figure, fig, 10 + i * (BOX + gap), 10, {"panel": str(i)})
    x = 10 + 4 * (BOX + gap)
    figure.rect(x, 10, BOX, BOX, sw=1.6, data={"panel": "?"})
    figure.text((x + BOX / 2, 10 + BOX / 2), "?", size=36)
    cells = {LETTERS[i]: (lambda svg, f=draft["options"][j]: _draw(svg, f, 0, 0, {})) for i, j in enumerate(order)}
    sheet = options_sheet(cells, BOX, BOX, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def _read(prims, key):
    figs = {}
    frames = {}
    for p in prims:
        gid = p.data.get(key)
        if gid is None or gid == "?":
            continue
        if p.data.get("frame"):
            frames[gid] = (float(p.data["ox"]), float(p.data["oy"]), float(p.data["cell"]))
    for p in prims:
        gid = p.data.get(key)
        if gid not in frames:
            continue
        ox, oy, cell = frames[gid]
        to = lambda q: ((q[0] - ox) / cell, (oy - q[1]) / cell)
        fig = figs.setdefault(gid, {"segs": [], "circs": []})
        if p.data.get("seg"):
            a, b = p.local()
            fig["segs"].append((to(a), to(b)))
        elif p.data.get("circ"):
            fig["circs"].append((to(p.local()[0]), float(p.data["r"]) / cell))
    return figs


def judge(svgs, pngs=None, stem=None, texts=None):
    panels = _read(parse(svgs["figure"]), "panel")
    options = _read(parse(svgs["options"]), "option")
    if sorted(panels) != ["0", "1", "2", "3"] or sorted(options) != list(LETTERS):
        raise ValueError("图形或选项不全")
    pm = [measure(panels[str(i)]["segs"], panels[str(i)]["circs"]) for i in range(4)]
    om = {k: measure(v["segs"], v["circs"]) for k, v in options.items()}
    rules = []
    for prop in PROPS:
        seq = [m[prop] for m in pm]
        diffs = {seq[i + 1] - seq[i] for i in range(3)}
        if len(diffs) == 1 and (step := diffs.pop()) in (-2, -1, 0, 1, 2):
            pred = seq[-1] + step
            chosen = sorted(k for k, m in om.items() if m[prop] == pred)
            if 0 < len(chosen) < 4:  # 四个选项都满足或都不满足的规律不提供信息
                rules.append((prop, step, pred, chosen))
    issues = []
    for name, m in [(f"第 {i + 1} 张图", m) for i, m in enumerate(pm)] + [(f"{k} 项", m) for k, m in sorted(om.items())]:
        if m["crowd"]:
            issues.append(f"{name}{m['crowd']}，看不清")
    picks = {tuple(r[3]) for r in rules}
    if len(picks) > 1 or any(len(r[3]) > 1 for r in rules):
        issues.append("规律不唯一：" + "；".join(f"{PROPS[r[0]]}→{''.join(r[3])}" for r in rules))
    correct = list(rules[0][3]) if rules and len(picks) == 1 else sorted({k for r in rules for k in r[3]})
    return {"correct": correct, "issues": issues, "panels": pm, "options": om,
            "rule": rules[0][:3] if len(picks) == 1 and rules else None}


def explain(verdict, key):
    rule = verdict.get("rule")
    if not rule:
        return "按图形数量找规律。"
    prop, step, pred = rule
    seq = [m[prop] for m in verdict["panels"]]
    how = "相同" if step == 0 else f"依次{'增加' if step > 0 else '减少'} {abs(step)}"
    lines = [f"题干各图的{PROPS[prop]}分别为 {'、'.join(map(str, seq))}，{how}，问号处应为 {pred}。"]
    if prop == "strokes":
        lines.append("笔画数看奇点（连着奇数条线的点）：0 或 2 个奇点可一笔画成，否则笔画数 = 奇点数 ÷ 2。")
    for letter in LETTERS:
        v = verdict["options"][letter][prop]
        lines.append(f"{letter} 项：{PROPS[prop]}为 {v}，" + ("符合，当选。" if letter == key else "不符，排除。"))
    return "\n".join(lines)


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]

    def build(draft, order):
        svgs = render(draft, order)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    # 数量计算本身：几个手算过的图
    square = [((0, 0), (2, 0)), ((2, 0), (2, 2)), ((2, 2), (0, 2)), ((0, 2), (0, 0))]
    m = measure(square + [((0, 0), (2, 2))], [])
    out.append(("正方形加一条对角线：2 面、5 线、1 笔、1 部分", m["faces"] == 2 and m["lines"] == 5 and m["strokes"] == 1 and m["parts"] == 1, str(m)))
    m = measure(square + [((0, 0), (2, 2)), ((0, 2), (2, 0))], [])
    out.append(("正方形加两条对角线：4 面、4 个奇点 2 笔", m["faces"] == 4 and m["strokes"] == 2, str(m)))
    m = measure([((0, 0), (1, 0)), ((2, 2), (3, 3))], [((1.5, 1.5), 0.5)])
    out.append(("两段线加一个圆：3 部分、1 面", m["parts"] == 3 and m["faces"] == 1 and m["curves"] == 1, str(m)))
    # 坐标带小数偏移时 T 字接头也要打断（这个例子曾经数错成 3 面）
    off = lambda pts: [((a[0] + 12.5454, a[1] - 0.2727), (b[0] + 12.5454, b[1] - 0.2727)) for a, b in pts]
    diamond = [((2, 0), (4, 2)), ((4, 2), (2, 4)), ((2, 4), (0, 2)), ((0, 2), (2, 0))]
    m = measure(off(diamond + [((1, 1), (2, 4)), ((1, 1), (3, 1)), ((0, 2), (3, 3))]), [])
    out.append(("菱形加三条弦（小数坐标）：5 面", m["faces"] == 5, str(m)))
    m = measure([((0, 1), (2, 1))], [((1, 1), 1.0)])
    out.append(("圆加一条直径：2 面、1 笔、2 交点", m["faces"] == 2 and m["strokes"] == 1 and m["points"] == 2, str(m)))
    m = measure([((0, 0), (2, 0)), ((2, 0), (2, 1)), ((2, 1), (0, 1)), ((0, 1), (0, 0)), ((1, 0), (1, 1))], [])
    out.append(("日字：2 面、1 笔", m["faces"] == 2 and m["strokes"] == 1, str(m)))
    tian = square + [((1, 0), (1, 2)), ((0, 1), (2, 1))]
    m = measure(tian, [])
    out.append(("田字：4 面、2 笔", m["faces"] == 4 and m["strokes"] == 2, str(m)))
    m = measure([((0, 0), (1, 0)), ((1, 0), (0, 1)), ((0, 1), (0, 0)), ((3, 3), (4, 3)), ((4, 3), (3, 4)), ((3, 4), (3, 3))], [])
    out.append(("两个分开的三角形：2 部分、2 面、2 笔", m["parts"] == 2 and m["faces"] == 2 and m["strokes"] == 2, str(m)))
    draft, order, svgs, pngs = verified(me, "self-test", "mid", "B")
    issues, _ = check(me, svgs, pngs, "B")
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "A")
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    wrong = draft["options"][1]
    broken = dict(draft, options=[wrong] + draft["options"][1:])  # 正确项换成一个数量不对的图
    issues, _ = check(me, *build(broken, order), "B")
    out.append(("正确项画成数量不对的图", bool(issues), "；".join(issues)))
    twin = dict(draft, options=[draft["options"][0], draft["options"][0], draft["options"][2], draft["options"][3]])
    issues, _ = check(me, *build(twin, order), "B")
    out.append(("两个选项都对", bool(issues), "；".join(issues)))
    return out

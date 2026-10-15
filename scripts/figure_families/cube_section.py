"""正方体截面：在正方体棱上标出 P、Q、R，过三点的平面截正方体，截面是什么形状。

生成器：三点取在顶点、棱中点或三等分点上，算出截面多边形（平面与正方体求交，精确几何）；
干扰项是「换掉其中一点」的平面截出来的形状，只保留与答案不相似的。选项按真实比例画多边形。

判题器只读 SVG：按画法参数把 P、Q、R 的屏幕位置对回正方体的哪条棱、棱上哪个位置（必须只对得上一条棱），
重新求平面与正方体的交，再把每个选项画出的多边形与它比相似（边长比和角度，允许旋转翻转）。
"""

from __future__ import annotations

import itertools
import math
import random
import sys

import numpy as np

from .core import LETTERS, Svg, options_sheet, parse

NAME = "cube_section"
TAG = "判断推理-图形推理-空间类-截面"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "空间类-截面"
VERSION = 2
MAX_TRIES = 80
PARTS = ("figure", "options")
DEFINITION = ("正方体截面：过棱上三点的平面截正方体。同一个面上的两点直接连；平行面上的截线互相平行；"
              "截面与几个面相交就是几边形（三角形到六边形），再看边长与平行关系定形状。")
STEM = "如图，P、Q、R 分别在正方体的棱上。用过 P、Q、R 三点的平面截这个正方体，截面的形状是："

CORNERS = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
EDGES = [(a, b) for a, b in itertools.combinations(CORNERS, 2) if sum(abs(p - q) for p, q in zip(a, b)) == 1]
TS = {"easy": (0.0, 0.5, 1.0), "mid": (0.0, 0.5, 1.0), "hard": (0.0, 1 / 3, 0.5, 2 / 3, 1.0)}


def point_on(edge, t):
    a, b = np.array(edge[0], float), np.array(edge[1], float)
    return a + (b - a) * t


def section(p, q, r):
    """过三点平面截单位正方体的凸多边形（3D 顶点，按环序）。三点共线返回 None。"""
    p, q, r = map(np.array, (p, q, r))
    n = np.cross(q - p, r - p)
    if np.linalg.norm(n) < 1e-9:
        return None
    n = n / np.linalg.norm(n)
    d = n.dot(p)
    pts = []
    for a, b in EDGES:
        a, b = np.array(a, float), np.array(b, float)
        fa, fb = n.dot(a) - d, n.dot(b) - d
        if abs(fa) < 1e-9:
            pts.append(a)
        if abs(fb) < 1e-9:
            pts.append(b)
        if fa * fb < -1e-12:
            pts.append(a + (b - a) * (fa / (fa - fb)))
    uniq = []
    for v in pts:
        if all(np.linalg.norm(v - u) > 1e-7 for u in uniq):
            uniq.append(v)
    if len(uniq) < 3:
        return None
    c = sum(uniq) / len(uniq)
    u = uniq[0] - c
    u = u / np.linalg.norm(u)
    w = np.cross(n, u)
    uniq.sort(key=lambda v: math.atan2((v - c).dot(w), (v - c).dot(u)))
    return uniq


def flat(poly3):
    """3D 平面多边形 -> 2D（保持形状）。"""
    c = sum(poly3) / len(poly3)
    u = poly3[0] - c
    u = u / np.linalg.norm(u)
    n = np.cross(poly3[1] - poly3[0], poly3[2] - poly3[0])
    n = n / np.linalg.norm(n)
    w = np.cross(n, u)
    return [((v - c).dot(u), (v - c).dot(w)) for v in poly3]


def shape_seq(poly2):
    """按顶点顺序：(该顶点内角, 到下一顶点的边长/周长)。"""
    n = len(poly2)
    pts = [np.array(p, float) for p in poly2]
    sides = [np.linalg.norm(pts[(i + 1) % n] - pts[i]) for i in range(n)]
    per = sum(sides)
    out = []
    for i in range(n):
        v1, v2 = pts[i - 1] - pts[i], pts[(i + 1) % n] - pts[i]
        cos = v1.dot(v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        out.append((math.degrees(math.acos(max(-1.0, min(1.0, cos)))), sides[i] / per))
    return out


def same_shape(pa, pb):
    """两个多边形是否相似（允许旋转、翻转、缩放）。"""
    if len(pa) != len(pb):
        return False
    sa = shape_seq(pa)
    n = len(pa)
    for pts in (list(pb), list(pb)[::-1]):
        sb = shape_seq(pts)
        for k in range(n):
            rot = sb[k:] + sb[:k]
            if all(abs(x[0] - y[0]) <= 3 and abs(x[1] - y[1]) <= 0.02 for x, y in zip(sa, rot)):
                return True
    return False


NAMES = {3: "三角形", 4: "四边形", 5: "五边形", 6: "六边形"}


# 截面坐标是精确值，选项从 SVG 读回只有两位小数的舍入；容差放到 3% 时，腰长差 2.9% 的梯形会被叫成等腰梯形
def _close(a, b, rel=0.005):
    return abs(a - b) <= rel * max(a, b)


def _parallel(u, v):
    return abs(u[0] * v[1] - u[1] * v[0]) <= 0.005 * np.linalg.norm(u) * np.linalg.norm(v)


def _right(angle):
    return abs(angle - 90) <= 0.5


def describe(poly2):
    n = len(poly2)
    pts = [np.array(p, float) for p in poly2]
    sides = [np.linalg.norm(pts[(i + 1) % n] - pts[i]) for i in range(n)]
    angles = [x[0] for x in shape_seq(poly2)]
    equal = all(_close(x, sides[0]) for x in sides)
    if n == 3:
        if equal:
            return "正三角形"
        iso = any(_close(sides[i], sides[j]) for i in range(3) for j in range(i + 1, 3))
        right = any(_right(a) for a in angles)
        return "等腰直角三角形" if iso and right else "等腰三角形" if iso else "直角三角形" if right else "三角形"
    if n == 4:
        d = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
        pairs = int(_parallel(d[0], d[2])) + int(_parallel(d[1], d[3]))
        right = all(_right(a) for a in angles)
        if pairs == 2:
            return "正方形" if right and equal else "矩形" if right else "菱形" if equal else "平行四边形"
        if pairs == 1:
            legs = (sides[1], sides[3]) if _parallel(d[0], d[2]) else (sides[0], sides[2])
            if any(_right(a) for a in angles):
                return "直角梯形"
            return "等腰梯形" if _close(*legs) else "梯形"
        return "四边形"
    if n == 6 and equal and all(abs(a - 120) <= 0.5 for a in angles):
        return "正六边形"
    if n == 5 and equal and all(abs(a - 108) <= 0.5 for a in angles):
        return "正五边形"
    return NAMES[n]


def _regular(n, r=1.0, phase=0.0):
    return [(r * math.cos(phase + 2 * math.pi * k / n), r * math.sin(phase + 2 * math.pi * k / n)) for k in range(n)]


LIBRARY = {
    "正三角形": _regular(3),
    "等腰三角形": [(0, 0), (2, 0), (1, 2.2)],
    "直角三角形": [(0, 0), (2, 0), (0, 1.3)],
    "正方形": [(0, 0), (1, 0), (1, 1), (0, 1)],
    "矩形": [(0, 0), (2, 0), (2, 1), (0, 1)],
    "菱形": [(0, 0), (1, 0), (1.5, 0.866), (0.5, 0.866)],
    "平行四边形": [(0, 0), (2, 0), (2.6, 1), (0.6, 1)],
    "等腰梯形": [(0, 0), (3, 0), (2.2, 1.2), (0.8, 1.2)],
    "直角梯形": [(0, 0), (3, 0), (1.8, 1.2), (0, 1.2)],
    "五边形": [(0, 0), (2, 0), (2.4, 1.1), (1.0, 1.8), (-0.3, 1.0)],
    "正五边形": _regular(5, phase=math.pi / 2),
    "正六边形": _regular(6),
}


def _pick_points(rng, tier):
    edges = rng.sample(EDGES, 3)
    ts = [rng.choice(TS[tier]) for _ in edges]
    pts = [point_on(e, t) for e, t in zip(edges, ts)]
    if any(np.linalg.norm(a - b) < 1e-6 for a, b in itertools.combinations(pts, 2)):
        return None
    return list(zip(edges, ts)), pts


def generate(rng, difficulty):
    tier = difficulty if difficulty in TS else rng.choice(("easy", "mid", "mid", "hard"))
    picked = _pick_points(rng, tier)
    if picked is None:
        return None
    marks, pts = picked
    if sum(0 < t < 1 for _, t in marks) < (2 if tier == "easy" else 1):
        return None  # 三个点都在顶点上的截法太平常
    poly = section(*pts)
    if poly is None or len(poly) < 3:
        return None
    normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    if sum(abs(c) > 1e-9 for c in normal) == 1:
        return None  # 平行于某个面的截法（截面就是正方形），太平常
    if tier == "easy" and len(poly) not in (3, 4):
        return None
    answer = flat(poly)
    shapes = [answer]
    for _ in range(60):
        alt = _pick_points(rng, "hard")
        if alt is None:
            continue
        keep = rng.sample(pts, 2)
        other = section(keep[0], keep[1], alt[1][0])
        if other is None:
            continue
        f = flat(other)
        # 干扰项按「形状类别」区分（三角形/矩形/梯形/五边形……），不出只差比例的同类形状
        if len(f) > 6 or describe(f) in {describe(s) for s in shapes}:
            continue
        shapes.append(f)
        if len(shapes) == 4:
            break
    if len(shapes) < 4:  # 截不出够多不同类的形状，就从常见形状里补
        library = list(LIBRARY.values())
        rng.shuffle(library)
        for f in library:
            if describe(f) not in {describe(s) for s in shapes}:
                shapes.append(f)
            if len(shapes) == 4:
                break
    if len(shapes) < 4:
        return None
    labels = ["P", "Q", "R"]
    return {"stem": STEM, "marks": [{"edge": [list(e[0]), list(e[1])], "t": t, "label": labels[i]}
                                    for i, (e, t) in enumerate(marks)],
            "options": [[list(map(float, p)) for p in s] for s in shapes], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
K = 0.42
FIG = 260
S = 150


def _proj(p, ox, oy, s=S):
    x, y, z = p
    return ox + s * (x + K * y), oy - s * (z + K * y)


HIDDEN = {(0, 1, 0)}  # 后左下角：从前右上方看被挡住，过它的三条棱画虚线


def render(draft, order):
    ox, oy = 36, FIG + 4
    figure = Svg(FIG + 40, FIG + 40)
    with figure.group({"cube": "1", "ox": ox, "oy": oy, "s": S}):
        for a, b in EDGES:
            dash = "7 5" if (tuple(a) in HIDDEN or tuple(b) in HIDDEN) else None
            figure.line(_proj(a, ox, oy), _proj(b, ox, oy), w=2.0, dash=dash, data={"edge": "1"})
        for m in draft["marks"]:
            p = point_on((tuple(m["edge"][0]), tuple(m["edge"][1])), m["t"])
            sx, sy = _proj(p, ox, oy)
            figure.circle((sx, sy), 4.5, fill="#111111", w=0, data={"pt": m["label"]})
            figure.text((sx + 14, sy - 12), m["label"], size=20, data={"label": m["label"]})
    cells = {}
    size = 150
    for i, j in enumerate(order):
        def draw(svg, poly=draft["options"][j]):
            pts = np.array(poly)
            # 最长边放水平：先转，再缩放到格子里
            n = len(pts)
            k = max(range(n), key=lambda i: np.linalg.norm(pts[(i + 1) % n] - pts[i]))
            d = pts[(k + 1) % n] - pts[k]
            ang = -math.atan2(d[1], d[0])
            rot = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
            q = pts @ rot.T
            q -= q.min(axis=0)
            span = q.max(axis=0)
            sc = (size - 30) / max(span)
            q = q * sc + (np.array([size, size]) - span * sc) / 2
            svg.poly([(float(x), float(size - y)) for x, y in q], closed=True, w=2.4, data={"shape": "1"})
        cells[LETTERS[i]] = draw
    sheet = options_sheet(cells, size, size, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def _seg_param(p, a, b):
    a, b, p = np.array(a), np.array(b), np.array(p)
    ab = b - a
    t = float((p - a).dot(ab) / ab.dot(ab))
    dist = float(np.linalg.norm(a + ab * min(max(t, 0), 1) - p))
    return t, dist


def judge(svgs, pngs=None, stem=None, texts=None):
    prims = parse(svgs["figure"])
    cube = next((p for p in prims if p.data.get("cube")), None)
    if cube is None:
        raise ValueError("正方体缺画法参数")
    ox, oy, s = (float(cube.data[k]) for k in ("ox", "oy", "s"))
    marks = {p.data["pt"]: p.points[0] for p in prims if p.tag == "circle" and "pt" in p.data}
    if sorted(marks) != ["P", "Q", "R"]:
        raise ValueError("截点不全")
    issues = []
    pts = []
    for label, (sx, sy) in sorted(marks.items()):
        hits = []
        for a, b in EDGES:
            t, dist = _seg_param((sx, sy), _proj(a, ox, oy, s), _proj(b, ox, oy, s))
            if dist < 1.5 and -0.01 <= t <= 1.01:
                hits.append((a, b, t))
        if not hits:
            raise ValueError(f"{label} 不在任何棱上")
        spots = [point_on((a, b), min(max(t, 0.0), 1.0)) for a, b, t in hits]
        if any(np.linalg.norm(q - spots[0]) > 0.02 for q in spots):
            issues.append(f"{label} 点对得上 {len(hits)} 条棱上的不同位置，有歧义")
        pts.append(spots[0])
    poly = section(*pts)
    if poly is None:
        raise ValueError("三点共线，截不出平面")
    answer = flat(poly)
    options = {}
    for p in parse(svgs["options"]):
        if p.data.get("shape"):
            options[p.data["option"]] = [(x, -y) for x, y in p.local()]
    if sorted(options) != list(LETTERS):
        raise ValueError("选项不全")
    correct = [k for k, v in options.items() if same_shape(v, answer)]
    for a, b in itertools.combinations(LETTERS, 2):
        if same_shape(options[a], options[b]):
            issues.append(f"{a}、{b} 两项形状相同")
    faces = len(poly)
    return {"correct": correct, "issues": issues, "sides": faces, "name": describe(answer),
            "names": {k: describe(v) for k, v in options.items()}, "counts": {k: len(v) for k, v in options.items()}}


def explain(verdict, key):
    n, name = verdict["sides"], verdict["name"]
    lines = [f"同一个面上的两个截点直接相连；与已画出的截线平行的面，截线也与它平行。照此连下去，"
             f"截面与正方体的 {n} 个面相交，是{name}。"]
    for letter in LETTERS:
        if letter == key:
            lines.append(f"{letter} 项：与截出的{name}形状一致，当选。")
        elif verdict["counts"][letter] != n:
            lines.append(f"{letter} 项：是{verdict['names'][letter]}，边数不对，排除。")
        else:
            lines.append(f"{letter} 项：是{verdict['names'][letter]}，边数虽同，但边长比例或角度与截面不符，排除。")
    return "\n".join(lines)


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]

    def build(draft, order):
        svgs = render(draft, order)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    draft, order, svgs, pngs = verified(me, "self-test", "mid", "B")
    issues, _ = check(me, svgs, pngs, "B")
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "C")
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    shifted = [dict(m) for m in draft["marks"]]
    shifted[0]["t"] = 0.25 if shifted[0]["t"] != 0.25 else 0.75
    issues, _ = check(me, *build(dict(draft, marks=shifted), order), "B")
    out.append(("截点画错位置", bool(issues), "；".join(issues)))
    twin = dict(draft, options=[draft["options"][0], draft["options"][0], draft["options"][2], draft["options"][3]])
    issues, _ = check(me, *build(twin, order), "B")
    out.append(("两个选项形状相同", bool(issues), "；".join(issues)))
    return out

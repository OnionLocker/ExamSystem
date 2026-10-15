"""折纸剪纸：正方形纸按图对折 1–3 次，沿虚线剪掉一块，展开后是什么样。

生成器：选折法（对角线、中线），在最后折好的形状里放一个剪口（可以贴着折痕，展开后连成一个大洞）。
正确项 = 按折痕逐层对称展开；干扰项 = 沿错的折痕展开、少展开一层、整体转 90°/镜像。

判题器只读 SVG：先核对每一步画出的形状确实是上一步沿画出的折痕对折的结果（两边哪边留下都试），
再把最后一步画出的剪口沿折痕倒着逐层对称展开，和每个选项画出的洞逐一比面积差。
"""

from __future__ import annotations

import math
import random
import sys

from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from .core import LETTERS, Svg, options_sheet, parse

NAME = "paper_cut"
TAG = "判断推理-图形推理-空间类-折纸剪纸"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "空间类-折纸剪纸"
VERSION = 1
MAX_TRIES = 60
PARTS = ("figure", "options")
DEFINITION = ("折纸剪纸：纸对折几次后剪去一块再展开。倒着逐层展开：每展开一次，剪口沿这次的折痕对称复制一份；"
              "贴着折痕的剪口展开后连成一个对称的大洞。")
STEM = "如图所示，将一张正方形纸片按图示方向依次对折，再沿虚线剪去阴影部分后展开，得到的图形是："

SQUARE = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])


def reflect(geom, line):
    (x1, y1), (x2, y2) = line
    dx, dy = x2 - x1, y2 - y1
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    # 关于直线的反射矩阵：先平移到原点，再用 2uu^T - I
    a, b, d = 2 * ux * ux - 1, 2 * ux * uy, 2 * uy * uy - 1
    moved = affinity.translate(geom, -x1, -y1)
    return affinity.translate(affinity.affine_transform(moved, [a, b, b, d, 0, 0]), x1, y1)


def half(line, sign):
    """直线一侧的大半平面（多边形）。"""
    (x1, y1), (x2, y2) = line
    dx, dy = x2 - x1, y2 - y1
    nx, ny = -dy * sign, dx * sign
    far = 50
    return Polygon([(x1 - dx * far, y1 - dy * far), (x2 + dx * far, y2 + dy * far),
                    (x2 + dx * far + nx * far, y2 + dy * far + ny * far), (x1 - dx * far + nx * far, y1 - dy * far + ny * far)])


def fold(shape, line, keep):
    kept = shape.intersection(half(line, keep))
    moved = reflect(shape.intersection(half(line, -keep)), line)
    return unary_union([kept, moved]).buffer(0)


def unfold(hole, steps):
    """steps = [(折痕, 折前形状)...]；倒着展开，每层剪口沿折痕对称复制。"""
    for line, before in reversed(steps):
        hole = unary_union([hole, reflect(hole, line)]).intersection(before).buffer(0)
    return hole


FOLDS = {"easy": 1, "mid": 2, "hard": 3}


def axes(shape):
    """当前形状的对称轴（过形心、0°/45°/90°/135° 方向），沿它对折两半正好重合。"""
    c = shape.centroid
    out = []
    for deg in (0, 45, 90, 135):
        dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        line = ((c.x - 2 * dx, c.y - 2 * dy), (c.x + 2 * dx, c.y + 2 * dy))
        if _same(reflect(shape, line), shape, tol=1e-6):
            out.append(line)
    return out


def _hole(rng, folded):
    """在折好的形状里放一个剪口：小三角、小方块、贴边半圆或贴折痕的缺口。"""
    minx, miny, maxx, maxy = folded.bounds
    for _ in range(80):
        kind = rng.choice(("tri", "sq", "circle", "notch"))
        r = rng.uniform(0.07, 0.12)
        cx, cy = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if kind == "tri":
            a = rng.uniform(0, 2 * math.pi)
            poly = Polygon([(cx + r * math.cos(a + k * 2 * math.pi / 3), cy + r * math.sin(a + k * 2 * math.pi / 3)) for k in range(3)])
        elif kind == "sq":
            poly = Polygon([(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)])
        else:
            poly = Polygon([(cx + r * math.cos(k * math.pi / 12), cy + r * math.sin(k * math.pi / 12)) for k in range(24)])
        if kind == "notch":  # 剪口压在边界上：展开后形成跨折痕的洞或边缘缺口
            cut = poly.intersection(folded)
            if cut.area < 0.4 * poly.area or cut.area > 0.85 * poly.area or cut.geom_type != "Polygon":
                continue
            return cut
        if folded.buffer(-0.03).contains(poly):
            return poly
    return None


def _same(a, b, tol=0.004):
    return a.symmetric_difference(b).area < tol


def generate(rng, difficulty):
    tier = difficulty if difficulty in FOLDS else rng.choice(("easy", "mid", "mid", "hard"))
    shape, steps = SQUARE, []
    for _ in range(FOLDS[tier]):
        choices = axes(shape)
        if not choices:
            return None
        line = rng.choice(choices)
        keep = rng.choice((1, -1))
        nxt = fold(shape, line, keep)
        steps.append((line, keep, shape, nxt))
        shape = nxt
    hole = _hole(rng, shape)
    if hole is None:
        return None
    seq = [(line, before) for line, _, before, _ in steps]
    answer = unfold(hole, seq)
    wrong = []
    angle = lambda l: round(math.degrees(math.atan2(l[1][1] - l[0][1], l[1][0] - l[0][0]))) % 180
    for line in axes(seq[-1][1]):  # 最后一层沿错的轴展开
        if angle(line) != angle(seq[-1][0]):
            bad = list(seq)
            bad[-1] = (line, seq[-1][1])
            wrong.append(unfold(hole, bad).intersection(SQUARE))
    if len(seq) > 1:
        wrong.append(unfold(hole, seq[1:]))  # 少展开第一层
    wrong.append(affinity.rotate(answer, 90, origin=(0.5, 0.5)))
    wrong.append(affinity.scale(answer, -1, 1, origin=(0.5, 0.5)))
    wrong.append(affinity.scale(answer, 1, -1, origin=(0.5, 0.5)))
    rng.shuffle(wrong)
    picked = []
    for w in wrong:
        if w.is_empty or w.area < 0.004:
            continue
        if _same(w, answer) or any(_same(w, p) for p in picked):
            continue
        picked.append(w)
        if len(picked) == 3:
            break
    if len(picked) < 3 or answer.area > 0.6 or answer.area < 0.01:
        return None
    return {"stem": STEM,
            "steps": [{"line": [list(line[0]), list(line[1])], "keep": keep, "before": _coords(b), "after": _coords(a)}
                      for line, keep, b, a in steps],
            "hole": _coords(hole), "options": [_coords(g) for g in [answer] + picked], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


def _coords(geom):
    geom = geom.buffer(0)
    polys = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
    return [[list(map(lambda v: round(v, 5), p)) for p in poly.exterior.coords[:-1]] for poly in polys if poly.area > 1e-6]


def _poly(coords):
    return unary_union([Polygon(c) for c in coords if len(c) >= 3]).buffer(0)


# ---------------------------------------------------------------- 渲染
P = 110  # 纸面在每个小格里画多大


def _paper(svg, geom_coords, x0, y0, data, fill="#e9e9e9"):
    for c in geom_coords:
        svg.poly([(x0 + x * P, y0 + (1 - y) * P) for x, y in c], closed=True, fill=fill, w=2.2, data=data)


def render(draft, order):
    steps = draft["steps"]
    n = len(steps) + 1
    gap = 34
    figure = Svg(n * P + (n - 1) * gap + 30, P + 40)
    x = 15
    for i, step in enumerate(steps):
        with figure.group({"step": str(i), "px": x, "py": 20, "scale": P}):
            _paper(figure, step["before"], x, 20, {"shape": "before"})
            (x1, y1), (x2, y2) = step["line"]
            seg = LineString([(x1, y1), (x2, y2)]).intersection(_poly(step["before"]))
            (a, b) = list(seg.coords)[0], list(seg.coords)[-1]
            figure.line((x + a[0] * P, 20 + (1 - a[1]) * P), (x + b[0] * P, 20 + (1 - b[1]) * P), w=2.0, dash="6 4",
                        data={"fold": str(i)})
        figure.text((x + P + gap / 2, 20 + P / 2), "→", size=26)
        x += P + gap
    with figure.group({"step": "final", "px": x, "py": 20, "scale": P}):
        _paper(figure, steps[-1]["after"], x, 20, {"shape": "after"})
        for c in draft["hole"]:
            figure.poly([(x + px * P, 20 + (1 - py) * P) for px, py in c], closed=True, fill="#555555", w=1.6,
                        dash="4 3", data={"hole": "cut"})
    cells = {}
    for i, j in enumerate(order):
        def draw(svg, holes=draft["options"][j]):
            with svg.group({"paper": "1", "px": 10, "py": 10, "scale": P}):
                _paper(svg, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 10, 10, {"shape": "paper"})
                for c in holes:
                    svg.poly([(10 + px * P, 10 + (1 - py) * P) for px, py in c], closed=True, fill="#ffffff", w=1.8,
                             data={"hole": "open"})
        cells[LETTERS[i]] = draw
    sheet = options_sheet(cells, P + 20, P + 20, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def _to_paper(points, px, py, scale):
    return [((x - px) / scale, 1 - (y - py) / scale) for x, y in points]


def judge(svgs, pngs=None, stem=None, texts=None):
    prims = parse(svgs["figure"])
    steps = {}
    for p in prims:
        if "step" not in p.data:
            continue
        sid = p.data["step"]
        g = steps.setdefault(sid, {"shape": [], "fold": None, "hole": [],
                                   "frame": (float(p.data["px"]), float(p.data["py"]), float(p.data["scale"]))})
        pts = _to_paper(p.points, *g["frame"])
        if p.data.get("shape"):
            g["shape"].append(pts)
        elif p.data.get("fold"):
            g["fold"] = pts
        elif p.data.get("hole"):
            g["hole"].append(pts)
    order = sorted((k for k in steps if k != "final"), key=int)
    if not order or "final" not in steps:
        raise ValueError("折纸步骤不全")
    issues = []
    seq = []
    shape = _poly(steps[order[0]]["shape"])
    if not _same(shape, SQUARE):
        issues.append("第一步不是完整的正方形纸")
    for k, sid in enumerate(order):
        g = steps[sid]
        drawn = _poly(g["shape"])
        if not _same(drawn, shape):
            issues.append(f"第 {k + 1} 步画出的形状和上一步折完的不一致")
        if not g["fold"]:
            raise ValueError("缺折痕")
        a, b = g["fold"][0], g["fold"][-1]
        line = (a, b)
        nxt_id = order[k + 1] if k + 1 < len(order) else "final"
        nxt = _poly(steps[nxt_id]["shape"])
        results = [fold(drawn, line, s) for s in (1, -1)]
        if not any(_same(r, nxt) for r in results):
            issues.append(f"第 {k + 1} 步的折痕和下一步画出的形状对不上")
        seq.append((line, drawn))
        shape = nxt
    hole = _poly(steps["final"]["hole"])
    if hole.is_empty or not shape.buffer(0.002).contains(hole):
        issues.append("剪口不在折好的纸上")
    unfolded = unfold(hole, seq)
    options = {}
    for p in parse(svgs["options"]):
        if p.data.get("hole") == "open":
            frame = (float(p.data["px"]), float(p.data["py"]), float(p.data["scale"]))
            options.setdefault(p.data["option"], []).append(_to_paper(p.local(), *frame))
    if sorted(options) != list(LETTERS):
        raise ValueError("选项不全")
    shapes = {k: _poly(v) for k, v in options.items()}
    correct = [k for k, g in shapes.items() if _same(g, unfolded)]
    for a in LETTERS:
        for b in LETTERS:
            if a < b and _same(shapes[a], shapes[b]):
                issues.append(f"{a}、{b} 两项画得一样")
    holes = len(getattr(unfolded, "geoms", [unfolded]))
    return {"correct": correct, "issues": issues, "folds": len(seq), "holes": holes,
            "touch": any(LineString(l).distance(hole) < 1e-6 for l, _ in seq)}


def explain(verdict, key):
    n, holes = verdict["folds"], verdict["holes"]
    lines = [f"纸共对折 {n} 次，倒着展开：每展开一次，剪口就沿那次的折痕对称复制一份，共 {2 ** n} 份。"]
    if verdict["touch"]:
        lines.append("剪口贴着折痕，展开后与对称的那份连在一起，形成一个更大的对称洞。")
    lines.append(f"展开后共有 {holes} 个洞，位置和形状与 {key} 项一致，选 {key}。其余选项或沿错了折痕、少展开了一层，或整体转了方向，排除。")
    return "\n".join(lines)


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]

    def build(draft, order):
        svgs = render(draft, order)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    draft, order, svgs, pngs = verified(me, "self-test", "mid", "A")
    issues, _ = check(me, svgs, pngs, "A")
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "B")
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    moved = dict(draft, hole=[[[x + 0.05, y] for x, y in c] for c in draft["hole"]])
    issues, _ = check(me, *build(moved, order), "A")
    out.append(("剪口画错位置", bool(issues), "；".join(issues)))
    swapped = [dict(st) for st in draft["steps"]]
    first = swapped[0]
    (x1, y1), (x2, y2) = first["line"]
    first["line"] = [[x1, y2], [x2, y1]] if (x1, y1) != (x1, y2) else [[y1, x1], [y2, x2]]  # 换成另一条轴
    issues, _ = check(me, *build(dict(draft, steps=swapped), order), "A")
    out.append(("折痕画错", bool(issues), "；".join(issues)))
    twin = dict(draft, options=[draft["options"][0], draft["options"][0], draft["options"][2], draft["options"][3]])
    issues, _ = check(me, *build(twin, order), "A")
    out.append(("两个选项一样", bool(issues), "；".join(issues)))
    return out

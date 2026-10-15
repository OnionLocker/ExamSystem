"""六面体折纸盒：展开图 → 哪个立方体能折出来。面内图案带方向。

生成器：11 种展开图任取一个摆法，六面各放一个图案并随机转向，按「面框架」规则折叠，
取 24 个保向旋转之一作正确视图。干扰项三类：两面换位（时针方向反）、图案转向（公共边错）、
放进另一可见面的相对面（相对面同时出现）。四个选项按 I-RAVEN 两两平衡，只看选项猜不出。

判题器只读 SVG：从展开图反解每格图案与朝向，按铰链真转坐标折叠（和生成器不是一套算法）；
选项按斜二测反投影回 3D 朝向，24 个旋转逐一比对。
"""

from __future__ import annotations

import itertools
import math
import random
import sys

import numpy as np

from .core import LETTERS, Svg, by, options_sheet, parse
from .geom import ROTATIONS, apply, chamfer, cross, dot, neg, rodrigues, sample

NAME = "cube_net"
TAG = "判断推理-图形推理-空间类-六面体"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "空间类-六面体"
VERSION = 1
PARTS = ("figure", "options")
DEFINITION = ("六面体折纸盒：给定外表面展开图，判断哪个立方体能由它折成。先用相对面排除"
              "（同行同列隔一格、Z 字两端），再用时针法核对三面的相邻顺序，最后用公共边/公共点核对面内图案方向。")
STEM = "左边给定的是纸盒的外表面，下列哪一项能由它折叠而成？"

X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


# ---------------------------------------------------------------- 图案库（单位正方形，u 右 v 上）
def _ring(cx, cy, r, n=40):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


# name: (中文名, period, [(points, closed, filled)])；period = 转几个 90° 与自身重合（4 = 无对称）
GLYPHS = {
    "circle": ("圆", 1, [(_ring(0.5, 0.5, 0.27), True, False)]),
    "plus": ("十字", 1, [([(0.5, 0.2), (0.5, 0.8)], False, False), ([(0.2, 0.5), (0.8, 0.5)], False, False)]),
    "dot": ("黑点", 1, [(_ring(0.5, 0.5, 0.13, 24), True, True)]),
    "diag": ("对角线", 2, [([(0.0, 0.0), (1.0, 1.0)], False, False)]),
    "half": ("半黑", 4, [([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)], True, True)]),
    "vee": ("V 形线", 4, [([(0.0, 1.0), (0.5, 0.0), (1.0, 1.0)], False, False)]),
    "arrow": ("箭头", 4, [([(0.5, 0.18), (0.5, 0.82)], False, False),
                          ([(0.3, 0.6), (0.5, 0.82), (0.7, 0.6)], False, False)]),
    "corner": ("角黑", 4, [([(0.0, 1.0), (0.36, 1.0), (0.0, 0.64)], True, True)]),
    "slash": ("中点斜线", 4, [([(0.0, 0.0), (0.5, 1.0)], False, False)]),
}


def turn_uv(point, k):
    """绕面中心逆时针转 k 个 90°。"""
    u, v = point
    for _ in range(k % 4):
        u, v = 1 - v, u
    return u, v


def period(glyph):
    return GLYPHS[glyph][1]


_TEMPLATES = {(g, k): sample([([turn_uv(p, k) for p in pts], closed) for pts, closed, _ in GLYPHS[g][2]])
              for g in GLYPHS for k in range(4)}


def _match(points):
    best = (None, None, 9.0)
    for (g, k), tpl in _TEMPLATES.items():
        score = chamfer(points, tpl)
        if score < best[2]:
            best = (g, k, score)
    return best


# ---------------------------------------------------------------- 展开图
def _normalize(cells):
    mx = min(x for x, _ in cells)
    my = min(y for _, y in cells)
    return tuple(sorted((x - mx, y - my) for x, y in cells))


def _polyominoes(n):
    shapes = {((0, 0),)}
    for _ in range(n - 1):
        grown = set()
        for shape in shapes:
            occupied = set(shape)
            for x, y in shape:
                for dx, dy in DIRS:
                    cell = (x + dx, y + dy)
                    if cell not in occupied:
                        grown.add(_normalize(occupied | {cell}))
        shapes = grown
    return sorted(shapes)


def _free_form(cells):
    forms = []
    for sx, sy, swap in itertools.product((1, -1), (1, -1), (False, True)):
        forms.append(_normalize([((y if swap else x) * sx, (x if swap else y) * sy) for x, y in cells]))
    return min(forms)


# 生成器的「面框架」：(a, b, n) = 展开图 +x、+y 方向和印刷面法向在 3D 里的像；盒子折在纸下方，印刷面朝外。
MOVES = {
    (1, 0): lambda a, b, n: (neg(n), b, a),
    (-1, 0): lambda a, b, n: (n, b, neg(a)),
    (0, 1): lambda a, b, n: (a, neg(n), b),
    (0, -1): lambda a, b, n: (a, n, neg(b)),
}
MIRROR_BUG = {(1, 0): MOVES[(-1, 0)], (-1, 0): MOVES[(1, 0)], (0, 1): MOVES[(0, 1)], (0, -1): MOVES[(0, -1)]}


def frames_of(cells, moves=MOVES):
    cells = set(cells)
    root = min(cells)
    frames = {root: (X, Y, Z)}
    todo = [root]
    while todo:
        cell = todo.pop()
        for d, move in moves.items():
            nb = (cell[0] + d[0], cell[1] + d[1])
            if nb in cells and nb not in frames:
                frames[nb] = move(*frames[cell])
                todo.append(nb)
    return frames


def is_net(cells):
    frames = frames_of(cells)
    return len(frames) == 6 and len({n for _, _, n in frames.values()}) == 6


NETS = [cells for cells in _polyominoes(6) if is_net(cells)]
assert len({_free_form(c) for c in NETS}) == 11, "正方体展开图应恰好 11 种"

# 视图：x 右、y 纵深、z 上；看得见顶面、前面、右面。basis = (面内右, 面内上)，右 × 上 = 外法向。
SLOTS = {
    "top": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "front": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    "right": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
}


def _up_index(U, slot):
    _, r, u = SLOTS[slot]
    return [u, neg(r), neg(u), r].index(U)


def _view_of(faces, R):
    view = {}
    for slot, (normal, _, _) in SLOTS.items():
        cell = next(c for c, (_, n, _) in faces.items() if apply(R, n) == normal)
        glyph, _, up = faces[cell]
        view[slot] = (glyph, _up_index(apply(R, up), slot))
    return view


def _norm_view(view):
    return tuple(sorted((s, g, k % period(g)) for s, (g, k) in view.items()))


TIER_PLAN = {
    "easy": (3, ("swap+opposite", "turn+opposite")),
    "mid": (4, ("swap+turn", "swap+opposite", "turn+turn", "turn+opposite")),
    "hard": (5, ("swap+turn", "turn+turn")),
}


def generate(rng, difficulty, moves=MOVES):
    tier = difficulty if difficulty in TIER_PLAN else rng.choice(("easy", "mid", "mid", "hard"))
    chiral_n, plans = TIER_PLAN[tier]
    cells = rng.choice(NETS)
    chiral = [g for g in GLYPHS if period(g) > 1]
    plain = [g for g in GLYPHS if period(g) == 1]
    names = rng.sample(chiral, chiral_n) + rng.sample(plain, 6 - chiral_n)
    rng.shuffle(names)
    net = {cell: (names[i], rng.randrange(4)) for i, cell in enumerate(cells)}
    faces = {}
    for cell, (a, b, n) in frames_of(cells, moves).items():
        glyph, q = net[cell]
        faces[cell] = (glyph, n, [b, neg(a), neg(b), a][q])
    opposite = {g1: g2 for g1, n1, _ in faces.values() for g2, n2, _ in faces.values() if n2 == neg(n1)}
    answer = _view_of(faces, rng.choice(ROTATIONS))
    side = ["top", "front", "right"]
    rng.shuffle(side)
    plan = rng.choice(plans)

    def turned(slot):
        glyph, k = answer[slot]
        turns = [dk for dk in (1, 2, 3) if (k + dk) % period(glyph) != k % period(glyph)]
        return (glyph, (k + rng.choice(turns)) % 4) if turns else None

    if plan.startswith("swap"):
        v1 = {**answer, side[0]: answer[side[1]], side[1]: answer[side[0]]}
        target = side[2]
    else:
        value = turned(side[0])
        if value is None:
            return None
        v1, target = {**answer, side[0]: value}, side[1]
    if plan.endswith("turn"):
        value = turned(target)
    else:
        other = next(s for s in side if s != target)
        value = (opposite[answer[other][0]], rng.randrange(4))
    if value is None:
        return None
    options = [answer, v1, {**answer, target: value}, {**v1, target: value}]
    if len({_norm_view(v) for v in options}) < 4:
        return None
    return {"stem": STEM, "net": {f"{c[0]},{c[1]}": list(v) for c, v in net.items()},
            "cells": [list(c) for c in sorted(cells)], "options": [{s: list(v) for s, v in o.items()} for o in options],
            "answer": 0, "plan": plan, "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
NET_CELL = 56
CUBE_S, CUBE_K, CUBE_M = 84, 0.42, 14
CUBE_SIZE = round(CUBE_S * (1 + CUBE_K) + 2 * CUBE_M)


def _glyph(svg, data, glyph, k, to_screen):
    for points, closed, filled in GLYPHS[glyph][2]:
        screen = [to_screen(*turn_uv(p, k)) for p in points]
        svg.poly(screen, closed=closed, fill="#111111" if filled else "none", w=2.2, data=data)


def render_net(net_cells, net):
    m = 16
    maxx = max(x for x, _ in net_cells)
    maxy = max(y for _, y in net_cells)
    svg = Svg((maxx + 1) * NET_CELL + 2 * m, (maxy + 1) * NET_CELL + 2 * m)
    for cx, cy in net_cells:
        x0, y0 = m + cx * NET_CELL, m + (maxy - cy) * NET_CELL
        svg.rect(x0, y0, NET_CELL, NET_CELL, sw=2.4, data={"cell": f"{cx},{cy}"})
        glyph, q = net[f"{cx},{cy}"]
        _glyph(svg, {"cell": f"{cx},{cy}"}, glyph, q,
               lambda u, v, x0=x0, y0=y0: (x0 + u * NET_CELL, y0 + (1 - v) * NET_CELL))
    return svg


def _face_maps(mirror_right=False):
    """渲染器自己的屏幕仿射：slot -> (原点, 面内右, 面内上)。"""
    s, k, m = CUBE_S, CUBE_K, CUBE_M
    ox, oy = m, m + s * (1 + k)
    d = (k * s, -k * s)
    maps = {"front": ((ox, oy), (s, 0.0), (0.0, -s)),
            "right": ((ox + s, oy), d, (0.0, -s)),
            "top": ((ox, oy - s), (s, 0.0), d)}
    if mirror_right:  # 负例：右面贴图镜像
        maps["right"] = ((ox + s + d[0], oy + d[1]), (-d[0], -d[1]), (0.0, -s))
    return maps


def draw_cube(svg, view, mirror_right=False):
    s, k, m = CUBE_S, CUBE_K, CUBE_M
    ox, oy = m, m + s * (1 + k)
    dx, dy = k * s, -k * s
    for outline in (
        [(ox, oy), (ox + s, oy), (ox + s, oy - s), (ox, oy - s)],
        [(ox, oy - s), (ox + s, oy - s), (ox + s + dx, oy - s + dy), (ox + dx, oy - s + dy)],
        [(ox + s, oy), (ox + s + dx, oy + dy), (ox + s + dx, oy - s + dy), (ox + s, oy - s)],
    ):
        svg.poly(outline, closed=True, fill="#ffffff", w=2.4)
    for slot, (origin, right, up) in _face_maps(mirror_right).items():
        glyph, kk = view[slot]
        _glyph(svg, {"face": slot}, glyph, kk,
               lambda u, v, o=origin, r=right, w=up: (o[0] + u * r[0] + v * w[0], o[1] + u * r[1] + v * w[1]))


def render(draft, order, mirror_right=False):
    cells = [tuple(c) for c in draft["cells"]]
    figure = render_net(cells, draft["net"])
    views = {LETTERS[i]: {s: tuple(v) for s, v in draft["options"][j].items()} for i, j in enumerate(order)}
    sheet = options_sheet({letter: (lambda svg, v=view: draw_cube(svg, v, mirror_right)) for letter, view in views.items()},
                          CUBE_SIZE, CUBE_SIZE)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器：只读 SVG
def _read_net(svg_text):
    prims = parse(svg_text)
    net = {}
    for rect in [p for p in prims if p.tag == "rect" and "cell" in p.data]:
        key = rect.data["cell"]
        x0, y0 = rect.points[0]
        polys = [([((x - x0) / NET_CELL, 1 - (y - y0) / NET_CELL) for x, y in p.points], p.tag == "polygon")
                 for p in by(prims, cell=key) if p.tag != "rect"]
        glyph, q, score = _match(sample(polys))
        if score > 0.02:
            raise ValueError(f"展开图格 {key} 认不出图案（距离 {score:.3f}）")
        cx, cy = map(int, key.split(","))
        net[(cx, cy)] = (glyph, q)
    return net


def _unproject(slot, sx, sy):
    """判题器自己的斜二测反投影：屏幕点 -> 该面上的 (面内右, 面内上)。"""
    s, k, m = CUBE_S, CUBE_K, CUBE_M
    ox, oy = m, m + s * (1 + k)
    px, pz = (sx - ox) / s, (oy - sy) / s  # px = x + k*y, pz = z + k*y
    if slot == "front":
        return px, pz
    if slot == "right":
        y = (px - 1) / k
        return y, pz - k * y
    y = (pz - 1) / k
    return px - k * y, y


def _read_options(svg_text):
    prims = parse(svg_text)
    views = {}
    for letter in LETTERS:
        group = by(prims, option=letter)
        if not group:
            continue
        view = {}
        for slot in SLOTS:
            polys = [([_unproject(slot, x, y) for x, y in p.local()], p.tag == "polygon")
                     for p in group if p.data.get("face") == slot]
            glyph, kk, score = _match(sample(polys))
            if score > 0.02:
                raise ValueError(f"{letter} 项 {slot} 面认不出图案（距离 {score:.3f}）")
            _, r, u = SLOTS[slot]
            view[slot] = (glyph, [u, neg(r), neg(u), r][kk])  # 回到 3D 朝向，不再用 k
        views[letter] = view
    return views


def hinge_fold(net):
    """铰链真转坐标折叠。net = cell -> (glyph, q)。返回 cell -> {glyph, normal, up}。"""
    cells = set(net)
    root = min(cells)
    parent, order = {root: None}, [root]
    for cell in order:
        for dx, dy in DIRS:
            nb = (cell[0] + dx, cell[1] + dy)
            if nb in cells and nb not in parent:
                parent[nb] = cell
                order.append(nb)
    if len(order) != 6:
        raise ValueError("展开图不连通或不是 6 格")
    hinges = {}
    for cell in order[1:]:
        p = parent[cell]
        dx, dy = cell[0] - p[0], cell[1] - p[1]
        corner = cell if (dx, dy) in ((1, 0), (0, 1)) else p
        a0 = np.array([corner[0], corner[1], 0.0])
        axis = (0, 1, 0) if dx else (1, 0, 0)
        centre = (cell[0] + 0.5, cell[1] + 0.5, 0.0)
        hinges[cell] = next((a0, axis, ang) for ang in (math.pi / 2, -math.pi / 2)
                            if rodrigues(centre, a0, axis, ang)[2] < -0.25)

    def fold(cell, point):
        point = np.array(point, float)
        while parent[cell] is not None:
            point = rodrigues(point, *hinges[cell])
            cell = parent[cell]
        return point

    lo = np.array([root[0], root[1], -1.0])
    faces, seen = {}, set()
    for cell, (glyph, q) in net.items():
        corners = [fold(cell, (cell[0] + i, cell[1] + j, 0)) for i, j in ((0, 0), (1, 0), (1, 1), (0, 1))]
        rel = np.array(corners) - lo
        if not np.allclose(rel, np.round(rel), atol=1e-6) or rel.min() < -1e-6 or rel.max() > 1 + 1e-6:
            raise ValueError(f"格 {cell} 折不到单位正方体表面上")
        fixed = [axis for axis in range(3) if np.ptp(rel[:, axis]) < 1e-6]
        if len(fixed) != 1:
            raise ValueError(f"格 {cell} 折叠后不贴在正方体某个面上")
        normal = [0, 0, 0]
        normal[fixed[0]] = 1 if rel[0, fixed[0]] > 0.5 else -1
        normal = tuple(normal)
        if normal in seen:
            raise ValueError("两格折到了同一个面上：不是正方体展开图")
        seen.add(normal)
        centre = (cell[0] + 0.5, cell[1] + 0.5, 0.0)
        printed = fold(cell, (centre[0], centre[1], 0.1)) - fold(cell, centre)
        if not np.allclose(printed / np.linalg.norm(printed), normal, atol=1e-6):
            raise ValueError("印刷面没有朝外")
        up_net = [(0, 1), (-1, 0), (0, -1), (1, 0)][q]
        up = fold(cell, (centre[0] + 0.25 * up_net[0], centre[1] + 0.25 * up_net[1], 0)) - fold(cell, centre)
        faces[cell] = {"glyph": glyph, "normal": normal,
                       "up": tuple(int(c) for c in np.round(up / np.linalg.norm(up)))}
    return faces


def _same_up(u1, u2, p):
    return p == 1 or u1 == u2 or (p == 2 and u1 == neg(u2))


def realizable(faces, view):
    for R in ROTATIONS:
        ok = True
        for slot, (glyph, U) in view.items():
            face = next(f for f in faces.values() if apply(R, f["normal"]) == SLOTS[slot][0])
            if face["glyph"] != glyph or not _same_up(apply(R, face["up"]), U, period(glyph)):
                ok = False
                break
        if ok:
            return R
    return None


def _feature(slot, glyph, U):
    p = period(glyph)
    return (slot, glyph, None if p == 1 else (max(U, neg(U)) if p == 2 else U))


def judge(svgs, pngs=None, stem=None, texts=None):
    faces = hinge_fold(_read_net(svgs["figure"]))
    views = _read_options(svgs["options"])
    if sorted(views) != list(LETTERS):
        raise ValueError(f"选项图不全：{sorted(views)}")
    issues = []
    correct = [letter for letter, view in views.items() if realizable(faces, view)]
    feats = {letter: frozenset(_feature(s, g, U) for s, (g, U) in v.items()) for letter, v in views.items()}
    if len(set(feats.values())) < 4:
        issues.append("有两个选项画得一样")
    if len(correct) == 1:
        key = correct[0]
        score = {letter: sum(sum(f in feats[o] for o in feats if o != letter) for f in fs) for letter, fs in feats.items()}
        if score[key] > max(v for letter, v in score.items() if letter != key):
            issues.append("只看选项就能猜出答案（答案和其余选项共享的特征最多）")
    return {"correct": correct, "issues": issues,
            "faces": {f"{c[0]},{c[1]}": f for c, f in faces.items()},
            "views": {k: {s: [g, list(U)] for s, (g, U) in v.items()} for k, v in views.items()}}


# ---------------------------------------------------------------- 解析：只用判题事实
def _sit(face, by_normal, name):
    up, n = face["up"], face["normal"]
    right = cross(up, n)
    near = lambda v: name[by_normal[v]["glyph"]] + "面"
    glyph = face["glyph"]
    if glyph == "arrow":
        return f"箭头指向与{near(up)}相邻的那条边"
    if glyph == "vee":
        return f"V 形开口朝向与{near(up)}相邻的那条边"
    if glyph == "slash":
        return f"斜线的中点端落在与{near(up)}相邻的那条边上"
    if glyph == "corner":
        return f"黑角夹在与{near(up)}、{near(neg(right))}相邻的两条边之间"
    if glyph == "half":
        return f"半黑三角的直角夹在与{near(neg(up))}、{near(neg(right))}相邻的两条边之间"
    if glyph == "diag":
        return f"对角线的一端是{near(neg(up))}、{near(neg(right))}与本面的公共点"
    return ""


def explain(verdict, key):
    faces = [{"glyph": f["glyph"], "normal": tuple(f["normal"]), "up": tuple(f["up"])} for f in verdict["faces"].values()]
    views = {k: {s: (g, tuple(U)) for s, (g, U) in v.items()} for k, v in verdict["views"].items()}
    name = {f["glyph"]: GLYPHS[f["glyph"]][0] for f in faces}
    by_normal = {f["normal"]: f for f in faces}
    by_glyph = {f["glyph"]: f for f in faces}
    pairs = sorted({tuple(sorted((name[f["glyph"]], name[by_normal[neg(f["normal"])]["glyph"]]))) for f in faces})
    lines = ["相对面：" + "、".join(f"{a}与{b}" for a, b in pairs) + "，相对面不能同时看到。"]
    for letter, view in sorted(views.items()):
        shown = [view[s][0] for s in ("top", "front", "right")]
        opp = [(a, b) for a, b in itertools.combinations(shown, 2) if by_glyph[a]["normal"] == neg(by_glyph[b]["normal"])]
        if letter == key:
            tip = next((_sit(by_glyph[g], by_normal, name) for g in shown if period(g) > 1), "")
            lines.append(f"{letter} 项：三面两两相邻，绕公共顶点的时针顺序和各面图案方向都与展开图一致"
                         + (f"（例如{tip}）" if tip else "") + "，当选。")
            continue
        if opp:
            a, b = opp[0]
            lines.append(f"{letter} 项：{name[a]}面与{name[b]}面是相对面，不能同时看到，排除。")
            continue
        normals = [by_glyph[g]["normal"] for g in shown]
        if dot(normals[0], cross(normals[1], normals[2])) != 1:
            lines.append(f"{letter} 项：{name[shown[0]]}、{name[shown[1]]}、{name[shown[2]]}三面绕公共顶点的"
                         "时针方向与展开图相反，排除。")
            continue
        R = next(R for R in ROTATIONS if all(apply(R, by_glyph[view[s][0]]["normal"]) == SLOTS[s][0] for s in SLOTS))
        for slot in SLOTS:
            glyph, U = view[slot]
            if not _same_up(apply(R, by_glyph[glyph]["up"]), U, period(glyph)):
                lines.append(f"{letter} 项：三面位置对，但{name[glyph]}面方向不对——按展开图，"
                             f"{_sit(by_glyph[glyph], by_normal, name)}，排除。")
                break
    return "\n".join(lines)


# ---------------------------------------------------------------- 自检：每条都必须拦下
def self_test():
    from .core import check, place_answer, rasterize

    def build(draft, order, **kw):
        svgs = render(draft, order, **kw)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    rng = random.Random(9001)
    draft = None
    while draft is None:
        draft = generate(rng, "mid")
    order = place_answer(0, 4, "B", rng)
    svgs, pngs = build(draft, order)
    ok, _ = check(sys.modules[__name__], svgs, pngs, "B")
    out.append(("正常题能过", not ok, "；".join(ok) or "通过"))
    issues, _ = check(sys.modules[__name__], svgs, pngs, "C")
    out.append(("答案键写错", bool(issues), "；".join(issues)))

    bad_cells = [[0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [3, 1]]
    bad_net = {f"{c[0]},{c[1]}": [list(GLYPHS)[i], 0] for i, c in enumerate(bad_cells)}
    try:
        hinge_fold(_read_net(str(render_net([tuple(c) for c in bad_cells], bad_net))))
        out.append(("非法展开图（含 2×2 块）", False, "判题器没报错"))
    except ValueError as exc:
        out.append(("非法展开图（含 2×2 块）", True, str(exc)))

    mirrored = dict(draft)
    view = dict(draft["options"][0])
    view["front"], view["right"] = view["right"], view["front"]
    mirrored["options"] = [view] + draft["options"][1:]
    svgs2, pngs2 = build(mirrored, order)
    issues, _ = check(sys.modules[__name__], svgs2, pngs2, "B")
    out.append(("正确项画成镜像三面", bool(issues), "；".join(issues)))

    caught = 0
    for i in range(30):
        r = random.Random(10_000 + i)
        d = None
        while d is None:
            d = generate(r, "mid", moves=MIRROR_BUG)
        o = place_answer(0, 4, "A", r)
        s, p = build(d, o)
        issues, _ = check(sys.modules[__name__], s, p, "A")
        caught += bool(issues)
    out.append(("生成器折叠规则写反（30 题）", caught == 30, f"拦下 {caught}/30"))

    changed = caught = 0
    for i in range(30):
        r = random.Random(20_000 + i)
        d = None
        while d is None:
            d = generate(r, "mid")
        o = place_answer(0, 4, "A", r)
        good, _ = build(d, o)
        bad, badp = build(d, o, mirror_right=True)
        issues, _ = check(sys.modules[__name__], bad, badp, "A")
        try:
            same = _read_options(good["options"])["A"] == _read_options(bad["options"])["A"]
        except ValueError:
            same = False
        if not same:
            changed += 1
            caught += bool(issues)
    out.append(("渲染器右面贴图镜像（30 题）", caught == changed, f"正确项被画错 {changed} 题，拦下 {caught}"))
    return out

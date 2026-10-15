"""平面拼接：给几块由小方格组成的图形，不旋转、不翻转，只平移，能拼成哪个选项的轮廓。

生成器：先长出目标轮廓并切成 3–4 块，再造干扰轮廓：整体旋转 90°、镜像（这两种都需要旋转/翻转小块才能拼）、
挪动一个小格的近似轮廓。干扰项必须真的拼不出来（判题器会穷举验证）。

判题器只读 SVG：小块按画出的方格坐标读成格点；选项只画外轮廓，用格心是否落在轮廓内读成格点；
然后只用平移做精确覆盖搜索，每个选项各拼一次。
"""

from __future__ import annotations

import random
import sys

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from .core import LETTERS, Svg, options_sheet, parse

NAME = "plane_tiling"
TAG = "判断推理-图形推理-特殊规律-平面拼接"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "特殊规律-平面拼接"
VERSION = 1
MAX_TRIES = 60
PARTS = ("figure", "options")
DEFINITION = ("平面拼接：几块小图形按要求（通常不旋转、不翻转）拼成目标图形。先比总格数，"
              "再从最难放的块（凸出最多或最长）和目标的尖角、凹口对位置，旋转或镜像过的轮廓拼不出来。")
STEM = "左边给出的几块图形，不经过旋转或翻转，只通过平移，可以拼接成下列哪个图形？"

TIER = {"easy": (3, (9, 11)), "mid": (4, (12, 14)), "hard": (4, (14, 16))}
NB = ((1, 0), (-1, 0), (0, 1), (0, -1))


def norm(cells):
    cells = list(cells)
    mx, my = min(c[0] for c in cells), min(c[1] for c in cells)
    return frozenset((x - mx, y - my) for x, y in cells)


def connected(cells):
    cells = set(cells)
    seen, todo = set(), [next(iter(cells))]
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        todo.extend((c[0] + dx, c[1] + dy) for dx, dy in NB if (c[0] + dx, c[1] + dy) in cells)
    return seen == cells


def tile(pieces, target):
    """只平移的精确覆盖：每步取最小空格，只试能盖住它的块与位置。"""
    target = frozenset(target)
    if sum(len(p) for p in pieces) != len(target):
        return None
    order = sorted(target)
    places = []
    for p in pieces:
        p = sorted(p)
        options = []
        for t in target:
            dx, dy = t[0] - p[0][0], t[1] - p[0][1]
            placed = frozenset((x + dx, y + dy) for x, y in p)
            if placed <= target:
                options.append(placed)
        places.append(options)

    def solve(used, done):
        if len(done) == len(pieces):
            return used == target
        cell = next(c for c in order if c not in used)
        for i, opts in enumerate(places):
            if i in done:
                continue
            for placed in opts:
                if cell in placed and not (placed & used):
                    if solve(used | placed, done | {i}):
                        return True
        return False

    return solve(frozenset(), frozenset())


def _grow(rng, n, width=5, height=5):
    shape = {(rng.randrange(width), rng.randrange(height))}
    while len(shape) < n:
        frontier = sorted({(x + dx, y + dy) for x, y in shape for dx, dy in NB} - shape)
        frontier = [c for c in frontier if 0 <= c[0] < width and 0 <= c[1] < height]
        if not frontier:
            return None
        shape.add(rng.choice(frontier))
    return frozenset(shape)


def _split(rng, target, parts):
    cells = sorted(target)
    for _ in range(30):
        owner = {}
        for i, s in enumerate(rng.sample(cells, parts)):
            owner[s] = i
        while len(owner) < len(cells):
            grow = [(c, (c[0] + dx, c[1] + dy)) for c in owner for dx, dy in NB
                    if (c[0] + dx, c[1] + dy) in target and (c[0] + dx, c[1] + dy) not in owner]
            if not grow:
                break
            sizes = [sum(v == i for v in owner.values()) for i in range(parts)]
            grow.sort(key=lambda cn: sizes[owner[cn[0]]] + rng.random() * 2)
            c, n = grow[0]
            owner[n] = owner[c]
        if len(owner) < len(cells):
            continue
        pieces = [norm(c for c, v in owner.items() if v == i) for i in range(parts)]
        if all(2 <= len(p) <= 6 for p in pieces) and len(set(pieces)) == parts:
            return pieces
    return None


def has_hole(cells):
    union = unary_union([Polygon([(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]) for x, y in cells])
    return union.geom_type != "Polygon" or len(union.interiors) > 0


def _rot(cells):
    return norm((y, -x) for x, y in cells)


def _mir(cells):
    return norm((-x, y) for x, y in cells)


def generate(rng, difficulty):
    tier = difficulty if difficulty in TIER else rng.choice(("easy", "mid", "mid", "hard"))
    parts, (lo, hi) = TIER[tier]
    target = _grow(rng, rng.randint(lo, hi))
    if target is None:
        return None
    target = norm(target)
    if has_hole(target):
        return None
    pieces = _split(rng, target, parts)
    if not pieces:
        return None
    cands = [_rot(target), _rot(_rot(target)), _mir(target), _mir(_rot(target))]
    for _ in range(12):
        cells = set(target)
        out = rng.choice(sorted(cells))
        rest = cells - {out}
        spots = sorted({(x + dx, y + dy) for x, y in rest for dx, dy in NB} - cells)
        if rest and spots and connected(rest):
            cand = rest | {rng.choice(spots)}
            if connected(cand):
                cands.append(norm(cand))
    rng.shuffle(cands)
    wrong = []
    for c in cands:
        if c == target or c in wrong or has_hole(c) or tile(pieces, c):
            continue
        wrong.append(c)
        if len(wrong) == 3:
            break
    if len(wrong) < 3:
        return None
    return {"stem": STEM, "pieces": [sorted(map(list, p)) for p in pieces],
            "options": [sorted(map(list, o)) for o in [target] + wrong], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
U = 20  # 小格边长


def _extent(cells):
    return max(x for x, _ in cells) + 1, max(y for _, y in cells) + 1


def render(draft, order):
    pieces = [[tuple(c) for c in p] for p in draft["pieces"]]
    widths = [_extent(p)[0] for p in pieces]
    height = max(_extent(p)[1] for p in pieces)
    figure = Svg(sum(w * U for w in widths) + 30 * (len(pieces) - 1) + 40, height * U + 60)
    x = 20
    for i, p in enumerate(pieces):
        w, h = _extent(p)
        y0 = 20 + (height - h) * U
        for cx, cy in p:
            figure.rect(x + cx * U, y0 + (h - 1 - cy) * U, U, U, fill="#bdbdbd", sw=1.6, data={"piece": str(i), "unit": U})
        figure.text((x + w * U / 2, height * U + 42), "①②③④"[i], size=20)
        x += w * U + 30
    cells = {}
    size = 7 * U
    for i, j in enumerate(order):
        def draw(svg, shape=[tuple(c) for c in draft["options"][j]]):
            w, h = _extent(shape)
            x0, y0 = (size - w * U) / 2, (size - h * U) / 2
            union = unary_union([Polygon([(x0 + cx * U, y0 + (h - 1 - cy) * U), (x0 + (cx + 1) * U, y0 + (h - 1 - cy) * U),
                                          (x0 + (cx + 1) * U, y0 + (h - cy) * U), (x0 + cx * U, y0 + (h - cy) * U)])
                                 for cx, cy in shape])
            polys = [union] if union.geom_type == "Polygon" else list(union.geoms)
            for poly in polys:
                svg.poly(list(poly.exterior.coords)[:-1], closed=True, fill="#ffffff", w=2.4,
                         data={"outline": "1", "unit": U, "ox": round(x0, 3), "oy": round(y0, 3), "rows": h})
        cells[LETTERS[i]] = draw
    sheet = options_sheet(cells, size, size, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def judge(svgs, pngs=None, stem=None, texts=None):
    raw = {}
    for p in parse(svgs["figure"]):
        if "piece" in p.data:
            raw.setdefault(p.data["piece"], []).append((p.points[0], float(p.data["unit"])))
    pieces = []
    for _, rects in sorted(raw.items()):
        x0 = min(pt[0] for pt, _ in rects)
        y0 = min(pt[1] for pt, _ in rects)
        pieces.append(norm((round((pt[0] - x0) / u), -round((pt[1] - y0) / u)) for pt, u in rects))
    if len(pieces) < 2:
        raise ValueError("小块不全")
    options = {}
    for p in parse(svgs["options"]):
        if p.data.get("outline"):
            u, ox, oy = float(p.data["unit"]), float(p.data["ox"]), float(p.data["oy"])
            poly = Polygon(p.local())
            minx, miny, maxx, maxy = poly.bounds
            cells = set()
            for cx in range(int((minx - ox) // u) - 1, int((maxx - ox) // u) + 2):
                for cy in range(int((miny - oy) // u) - 1, int((maxy - oy) // u) + 2):
                    if poly.contains(Point(ox + (cx + 0.5) * u, oy + (cy + 0.5) * u)):
                        cells.add((cx, -cy))
            options.setdefault(p.data["option"], set()).update(cells)
    if sorted(options) != list(LETTERS):
        raise ValueError("选项不全")
    shapes = {k: norm(v) for k, v in options.items()}
    fits = {k: bool(tile(pieces, s)) for k, s in shapes.items()}
    issues = []
    if len(set(shapes.values())) < 4:
        issues.append("有两个选项轮廓一样")
    total = sum(len(p) for p in pieces)
    return {"correct": [k for k, v in fits.items() if v], "issues": issues, "fits": fits,
            "sizes": {k: len(s) for k, s in shapes.items()}, "total": total, "pieces": [len(p) for p in pieces]}


def explain(verdict, key):
    sizes = verdict["sizes"]
    lines = [f"几块共 {verdict['total']} 个小方格（{'、'.join(map(str, verdict['pieces']))}），先排除格数不对的选项，"
             "再从最长、最凸出的那块对准目标的尖角和凹口，按原方向平移拼放。"]
    for letter in LETTERS:
        if letter == key:
            lines.append(f"{letter} 项：格数相同，各块按原方向平移后正好拼满，当选。")
        elif sizes[letter] != verdict["total"]:
            lines.append(f"{letter} 项：共 {sizes[letter]} 格，格数就不对，排除。")
        else:
            lines.append(f"{letter} 项：格数相同，但必须旋转或翻转某块才能放下（或总有一格放不进去），排除。")
    return "\n".join(lines)


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
    rotated_piece = [sorted(map(list, _rot([tuple(c) for c in draft["pieces"][0]])))] + draft["pieces"][1:]
    issues, _ = check(me, *build(dict(draft, pieces=rotated_piece), order), "D")
    out.append(("把一块画成旋转后的样子", bool(issues), "；".join(issues)))
    extra = [list(c) for c in draft["pieces"][0]] + [[max(x for x, _ in draft["pieces"][0]) + 1, 0]]
    issues, _ = check(me, *build(dict(draft, pieces=[extra] + draft["pieces"][1:]), order), "D")
    out.append(("小块多画一格", bool(issues), "；".join(issues)))
    return out

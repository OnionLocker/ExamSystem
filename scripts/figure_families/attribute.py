"""属性规律：对称（轴对称、中心对称、对称轴条数与方向）、曲直、开闭。两种问法：
  找规律：五格一行，前四个图同属性（或按对称轴方向转），问号处选同类的；
  分组：六个图分两类，选项给四种分法，只有一种按同一属性分得开（真题「把下面的六个图形分为两类」）。

图形由格点上的折线、多边形和圆弧组成。属性由判题器按画出的几何重新计算：
对称轴在过中心的 0°/45°/90°/135° 四个方向上逐一做反射比对；中心对称做 180° 旋转比对；
曲直看有没有圆或弧；开闭看有没有闭合区域。规则族里每个属性都试，推出的答案必须唯一。
"""

from __future__ import annotations

import itertools
import math
import random
import sys

import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import polygonize, unary_union

from .core import LETTERS, Svg, options_sheet, parse

NAME = "attribute"
TAG = "判断推理-图形推理-属性规律"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "属性规律"
VERSION = 1
MAX_TRIES = 150
PARTS = ("figure", "options")
DEFINITION = ("属性规律：对称性（轴对称、中心对称、对称轴条数与方向）、曲直性（全直线 / 有曲线）、开闭性（有无封闭区域）。"
              "先看所有图共有的属性，分组题看哪一个属性正好把六个图分成两类。")
STEM_SEQ = "从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性："
STEM_GROUP = "把下面的六个图形分为两类，使每一类图形都有各自的共同特征或规律，分类正确的一项是："

PROPS = {"axis": "是轴对称图形", "central": "是中心对称图形", "curved": "含曲线", "closed": "有封闭区域"}


# ---------------------------------------------------------------- 属性计算（判题器只喂从 SVG 读回的几何）
def _lines(fig):
    out = [LineString(p) for p in fig["polys"]]
    for (cx, cy), r, a0, a1 in fig["arcs"]:
        n = max(8, int(abs(a1 - a0) / 7.5))
        out.append(LineString([(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
                                cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]))
    return MultiLineString(out)


def _same(a, b, tol=0.06):
    # GEOS 的 Hausdorff 只比顶点；不加密的话，Z 字和正方形四个顶点一样就会被当成对称
    return shapely.hausdorff_distance(a, b, densify=0.05) < tol


def properties(fig):
    geom = _lines(fig)
    c = geom.centroid
    minx, miny, maxx, maxy = geom.bounds
    centre = ((minx + maxx) / 2, (miny + maxy) / 2)
    axes = []
    for deg in (0, 45, 90, 135):
        dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        x1, y1 = centre[0] - dx, centre[1] - dy
        ux, uy = dx, dy
        a, b, d = 2 * ux * ux - 1, 2 * ux * uy, 2 * uy * uy - 1
        moved = affinity.translate(geom, -x1, -y1)
        refl = affinity.translate(affinity.affine_transform(moved, [a, b, b, d, 0, 0]), x1, y1)
        if _same(refl, geom):
            axes.append(deg)
    central = _same(affinity.rotate(geom, 180, origin=centre), geom)
    closed = len(list(polygonize(unary_union(geom)))) > 0
    del c
    return {"axis": bool(axes), "axes": axes, "central": central, "curved": bool(fig["arcs"]), "closed": closed}


# ---------------------------------------------------------------- 构图
def _sym_poly(rng, kind):
    """按要求的对称类型造一条折线/多边形（格点坐标 0..4）。"""
    for _ in range(60):
        if kind == "vertical":  # 关于 x=2 轴对称
            half = [(rng.randint(0, 2), rng.randint(0, 4)) for _ in range(rng.randint(2, 3))]
            half.sort(key=lambda p: p[1])
            pts = half + [(4 - x, y) for x, y in reversed(half)]
        elif kind == "central":  # 关于 (2,2) 中心对称
            half = [(rng.randint(0, 4), rng.randint(0, 4)) for _ in range(rng.randint(2, 3))]
            pts = half + [(4 - x, 4 - y) for x, y in half]
        elif kind == "both":  # 两条轴：x=2、y=2
            q = [(rng.randint(0, 1), rng.randint(0, 1)) for _ in range(1)]
            x, y = q[0]
            pts = [(x, y), (4 - x, y), (4 - x, 4 - y), (x, 4 - y)]
        else:  # 不对称
            pts = [(rng.randint(0, 4), rng.randint(0, 4)) for _ in range(rng.randint(3, 5))]
        if len(set(pts)) >= 3:
            return pts
    return None


def _figure(rng, want):
    """want: {属性: True/False}，随机造图直到属性都满足。"""
    for _ in range(200):
        kind = rng.choice(("vertical", "central", "both", "none"))
        pts = _sym_poly(rng, kind)
        if pts is None:
            continue
        closed = rng.random() < 0.5
        polys = [pts + [pts[0]]] if closed else [pts]
        arcs = []
        if rng.random() < 0.4:
            r = rng.choice((0.8, 1.0, 1.5))
            if kind in ("vertical", "both"):
                arcs.append(((2, rng.choice((1, 2, 3))), r, 0, 180))
            elif kind == "central":
                arcs += [((2, 2), r, 0, 90), ((2, 2), r, 180, 270)]
            else:
                arcs.append(((rng.randint(1, 3), rng.randint(1, 3)), r, rng.choice((0, 90)), rng.choice((180, 270))))
        fig = {"polys": [[list(p) for p in poly] for poly in polys], "arcs": [[list(c), r, a0, a1] for c, r, a0, a1 in arcs]}
        try:
            props = properties({"polys": polys, "arcs": arcs})
        except Exception:  # noqa: BLE001
            continue
        if LineString(pts).length < 3:
            continue
        if all(props[k] == v for k, v in want.items()):
            return fig, props
    return None


def generate(rng, difficulty):
    tier = difficulty if difficulty in ("easy", "mid", "hard") else rng.choice(("easy", "mid", "mid", "hard"))
    mode = "group" if tier != "easy" and rng.random() < 0.5 else "seq"
    prop = rng.choice(("axis", "central", "curved", "closed"))
    if mode == "seq":
        panels = []
        for _ in range(4):
            made = _figure(rng, {prop: True})
            if made is None:
                return None
            panels.append(made[0])
        made = _figure(rng, {prop: True})
        if made is None:
            return None
        options = [made[0]]
        for _ in range(3):
            made = _figure(rng, {prop: False})
            if made is None:
                return None
            options.append(made[0])
        return {"stem": STEM_SEQ, "mode": mode, "prop": prop, "panels": panels, "options": options, "answer": 0,
                "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}
    figs = []
    for value in (True, True, True, False, False, False):
        made = _figure(rng, {prop: value})
        if made is None:
            return None
        figs.append(made[0])
    order = list(range(6))
    rng.shuffle(order)
    figs = [figs[i] for i in order]
    yes = sorted(k + 1 for k, i in enumerate(order) if i < 3)
    true_split = _split(yes)
    others = set()
    for combo in itertools.combinations(range(1, 7), 3):
        if 1 not in combo:
            continue
        split = _split(list(combo))
        if split != true_split:
            others.add(split)
    wrong = rng.sample(sorted(others), 3)
    return {"stem": STEM_GROUP, "mode": mode, "prop": prop, "figs": figs, "options": [true_split] + wrong,
            "answer": 0, "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


def _split(first):
    a = tuple(sorted(first))
    b = tuple(sorted(set(range(1, 7)) - set(a)))
    return (a, b) if 1 in a else (b, a)


def option_texts(draft, order):
    if draft["mode"] != "group":
        return [f"图{letter}" for letter in LETTERS]
    nums = "①②③④⑤⑥"
    return ["".join(nums[i - 1] for i in a) + "，" + "".join(nums[i - 1] for i in b)
            for a, b in (draft["options"][j] for j in order)]


# ---------------------------------------------------------------- 渲染
CELL = 20
BOX = CELL * 4 + 28


def _draw(svg, fig, x0, y0, data):
    to = lambda p: (x0 + 14 + p[0] * CELL, y0 + 14 + (4 - p[1]) * CELL)
    svg.rect(x0, y0, BOX, BOX, sw=1.4, data={**data, "frame": "1", "cell": CELL, "ox": x0 + 14, "oy": y0 + 14 + 4 * CELL})
    for poly in fig["polys"]:
        svg.poly([to(p) for p in poly], w=2.4, data={**data, "path": "1"})
    for c, r, a0, a1 in fig["arcs"]:
        n = max(8, int(abs(a1 - a0) / 7.5))
        pts = [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
               for k in range(n + 1)]
        svg.poly([to(p) for p in pts], w=2.4, data={**data, "arc": "1"})


def render(draft, order):
    gap = 14
    if draft["mode"] == "seq":
        figure = Svg(5 * BOX + 4 * gap + 20, BOX + 20)
        for i, fig in enumerate(draft["panels"]):
            _draw(figure, fig, 10 + i * (BOX + gap), 10, {"panel": str(i)})
        x = 10 + 4 * (BOX + gap)
        figure.rect(x, 10, BOX, BOX, sw=1.4)
        figure.text((x + BOX / 2, 10 + BOX / 2), "?", size=34)
        cells = {LETTERS[i]: (lambda svg, f=draft["options"][j]: _draw(svg, f, 0, 0, {})) for i, j in enumerate(order)}
        sheet = options_sheet(cells, BOX, BOX, cols=4)
        return {"figure": str(figure), "options": str(sheet)}
    figure = Svg(3 * BOX + 2 * gap + 20, 2 * (BOX + 34) + 10)
    for i, fig in enumerate(draft["figs"]):
        r, c = divmod(i, 3)
        x0, y0 = 10 + c * (BOX + gap), 8 + r * (BOX + 34)
        _draw(figure, fig, x0, y0, {"panel": str(i + 1)})
        figure.text((x0 + BOX / 2, y0 + BOX + 16), "①②③④⑤⑥"[i], size=20)
    return {"figure": str(figure)}


PARTS_BY_MODE = {"seq": ("figure", "options"), "group": ("figure",)}


# ---------------------------------------------------------------- 判题器
def _read(prims, key):
    frames, figs = {}, {}
    for p in prims:
        gid = p.data.get(key)
        if gid is not None and p.data.get("frame"):
            frames[gid] = (float(p.data["ox"]), float(p.data["oy"]), float(p.data["cell"]))
    for p in prims:
        gid = p.data.get(key)
        if gid not in frames:
            continue
        ox, oy, cell = frames[gid]
        pts = [((x - ox) / cell, (oy - y) / cell) for x, y in p.local()]
        fig = figs.setdefault(gid, {"polys": [], "arcs": []})
        if p.data.get("path"):
            fig["polys"].append(pts)
        elif p.data.get("arc"):
            fig["polys"].append(pts)
            fig["arcs"].append(None)  # 曲线已作为折线并入，标记一下「有曲线」
    return figs


def _props(fig):
    geom_fig = {"polys": fig["polys"], "arcs": []}
    out = properties(geom_fig)
    out["curved"] = bool(fig["arcs"])
    return out


def judge(svgs, pngs=None, stem=None, texts=None):
    panels = _read(parse(svgs["figure"]), "panel")
    issues = []
    if "options" in svgs:  # 找规律
        options = _read(parse(svgs["options"]), "option")
        if sorted(panels) != ["0", "1", "2", "3"] or sorted(options) != list(LETTERS):
            raise ValueError("图形或选项不全")
        pp = [_props(panels[str(i)]) for i in range(4)]
        op = {k: _props(v) for k, v in options.items()}
        rules = []
        for prop in PROPS:
            for value in (True, False):
                if all(p[prop] == value for p in pp):
                    chosen = sorted(k for k, o in op.items() if o[prop] == value)
                    if 0 < len(chosen) < 4:
                        rules.append((prop, value, chosen))
        picks = {tuple(r[2]) for r in rules}
        if len(picks) > 1 or any(len(r[2]) > 1 for r in rules):
            issues.append("规律不唯一：" + "；".join(f"{'都' if v else '都不'}{PROPS[p][1:] if p != 'curved' else '含曲线'}→{''.join(c)}" for p, v, c in rules))
        correct = list(rules[0][2]) if len(picks) == 1 and rules else sorted({k for r in rules for k in r[2]})
        return {"correct": correct, "issues": issues, "mode": "seq", "rule": rules[0][:2] if len(picks) == 1 and rules else None,
                "options": {k: {p: o[p] for p in PROPS} for k, o in op.items()}}
    # 分组：选项文字给分法
    if sorted(panels, key=int) != [str(i) for i in range(1, 7)]:
        raise ValueError("六个图不全")
    pp = {int(k): _props(v) for k, v in panels.items()}
    splits = {}
    nums = "①②③④⑤⑥"
    for letter, text in zip(LETTERS, texts or []):
        halves = text.split("，")
        if len(halves) != 2:
            raise ValueError(f"分组选项格式不对：{text}")
        splits[letter] = tuple(tuple(sorted(nums.index(ch) + 1 for ch in h)) for h in halves)
    good = {}
    for prop in PROPS:
        yes = tuple(sorted(i for i, p in pp.items() if p[prop]))
        if len(yes) == 3:
            good[prop] = _split(list(yes))
    correct = [k for k, sp in splits.items() if _split(list(sp[0])) in good.values()]
    if len(set(good.values())) > 1:
        issues.append("有两种属性都能把六个图分成三三两组，分法不唯一")
    return {"correct": correct, "issues": issues, "mode": "group",
            "rule": next((p for p, sp in good.items() if [k for k, s in splits.items() if _split(list(s[0])) == sp]), None),
            "props": {i: {p: v for p, v in pp[i].items() if p in PROPS} for i in pp}}


def explain(verdict, key):
    word = {"axis": "轴对称图形", "central": "中心对称图形", "curved": "含曲线的图形", "closed": "有封闭区域的图形"}
    if verdict["mode"] == "seq":
        prop, value = verdict["rule"]
        lines = [f"题干四个图都{'是' if value else '不是'}{word[prop]}，问号处也应{'是' if value else '不是'}。"]
        for letter in LETTERS:
            ok = verdict["options"][letter][prop] == value
            lines.append(f"{letter} 项：{'是' if verdict['options'][letter][prop] else '不是'}{word[prop]}，"
                         + ("符合，当选。" if letter == key else "不符，排除。" if not ok else "排除。"))
        return "\n".join(lines)
    prop = verdict["rule"]
    nums = "①②③④⑤⑥"
    yes = "".join(nums[i - 1] for i, p in sorted(verdict["props"].items()) if p[prop])
    no = "".join(nums[i - 1] for i, p in sorted(verdict["props"].items()) if not p[prop])
    return f"{yes}都是{word[prop]}，{no}都不是，按这一属性分为两类，选 {key}。"


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]
    out = []
    sq = {"polys": [[(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]], "arcs": []}
    p = properties(sq)
    out.append(("正方形：两条以上对称轴、中心对称、封闭", p["axis"] and len(p["axes"]) == 4 and p["central"] and p["closed"], str(p)))
    z = {"polys": [[(0, 4), (4, 4), (0, 0), (4, 0)]], "arcs": []}
    p = properties(z)
    out.append(("Z 字：中心对称、不轴对称、不封闭", p["central"] and not p["axis"] and not p["closed"], str(p)))
    arrow = {"polys": [[(2, 0), (2, 4)], [(0, 2), (2, 4), (4, 2)]], "arcs": []}
    p = properties(arrow)
    out.append(("箭头：只有竖直一条对称轴", p["axes"] == [90] and not p["central"], str(p)))
    for mode in ("seq", "group"):
        seed = 0
        draft, order, svgs, pngs = verified(me, f"self-test-{mode}", "mid", "B")
        while draft["mode"] != mode:
            seed += 1
            draft, order, svgs, pngs = verified(me, f"self-test-{mode}-{seed}", "mid", "B")
        from .core import option_texts as texts_of
        texts = texts_of(me, draft, order)
        issues, _ = check(me, svgs, pngs, "B", draft["stem"], texts)
        out.append((f"{mode}：正常题能过", not issues, "；".join(issues) or "通过"))
        issues, _ = check(me, svgs, pngs, "C", draft["stem"], texts)
        out.append((f"{mode}：答案键写错", bool(issues), "；".join(issues)))
    return out

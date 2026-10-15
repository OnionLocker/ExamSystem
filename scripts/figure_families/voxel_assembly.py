"""立体拼接：小正方体组成的几块立体，拼成长方体/正方体，或判断哪个组合体拼不出来。

两种问法（都是广东近年真题问法）：
  补全：给两块，问选项里哪一块能和它们拼成指定大小的长方体/正方体（可旋转，不可翻转镜像）。
  选非：给两块，问哪个组合体最不可能由这两块拼成。
生成器先切块/先拼，再造近似干扰项（镜像块、挪一个小正方体）；每块都换到所有小正方体都露得出来的摆法再画。

判题器：从 SVG 读出每块画了哪些小正方体，射线求交逐点核对 PNG，并要求每个小正方体都看得见；
然后用判题器自己的精确覆盖搜索去拼，每个选项各拼一次。
"""

from __future__ import annotations

import random
import re
import sys

from . import voxel
from .core import LETTERS, Svg, options_sheet, parse
from .geom import ROTATIONS

NAME = "voxel_assembly"
TAG = "判断推理-图形推理-空间类-立体拼接"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "空间类-立体拼接"
VERSION = 1
MAX_TRIES = 80
PARTS = ("figure", "options")
DEFINITION = ("立体拼接：几块由小正方体组成的立体，在可旋转、不可翻转、不重叠不留空的条件下拼成目标立体。"
              "先数小正方体个数是否守恒，再找最难放的那块（凸出最多、带凹口）定位置，最后核对镜像。")

BOXES = {"easy": (2, 2, 3), "mid": (2, 3, 3), "hard": (2, 3, 3)}


def _box(dims):
    a, b, c = dims
    return frozenset((x, y, z) for x in range(a) for y in range(b) for z in range(c))


def _partition(rng, dims, parts=3):
    cells = sorted(_box(dims))
    owner = {}
    seeds = rng.sample(cells, parts)
    frontier = []
    for i, s in enumerate(seeds):
        owner[s] = i
        frontier.append(s)
    while len(owner) < len(cells):
        growable = [(c, n) for c in owner for n in voxel.neighbors(c) if n in set(cells) and n not in owner]
        if not growable:
            return None
        sizes = [sum(1 for v in owner.values() if v == i) for i in range(parts)]
        # 偏向给小块长、往外伸（同块邻居少的格子先长），块不至于抱成一团、画出来每个小正方体都看得见
        crowd = lambda cn: sum(owner.get(m) == owner[cn[0]] for m in voxel.neighbors(cn[1]))
        growable.sort(key=lambda cn: sizes[owner[cn[0]]] + 0.8 * crowd(cn) + rng.random() * 2.5)
        c, n = growable[0]
        owner[n] = owner[c]
    pieces = [voxel.normalize(c for c, v in owner.items() if v == i) for i in range(parts)]
    return pieces


def _interesting(piece):
    (x0, x1), (y0, y1), (z0, z1) = voxel.bounds(piece)
    spans = sorted((x1 - x0, y1 - y0, z1 - z0))
    return spans[1] >= 2 and len(piece) >= 3


def _display(piece, rng):
    """挑一个每个小正方体都露得出来的摆法；渲染后判题器还会对着 PNG 再核对一次。"""
    forms = list(voxel.orientations(piece))
    rng.shuffle(forms)
    for form in forms:
        cells = set(form)
        if not all((x, y - 1, z) not in cells or (x + 1, y, z) not in cells or (x, y, z + 1) not in cells
                   for x, y, z in cells):
            continue
        if min(voxel.visible_counts(form, s=24.0, step=4.0).values()) >= 3:
            return form
    return None


def _moved(piece, rng):
    cells = set(piece)
    for _ in range(40):
        out = rng.choice(sorted(cells))
        rest = cells - {out}
        if not voxel.connected(rest):
            continue
        spots = sorted({n for c in rest for n in voxel.neighbors(c)} - cells)
        if not spots:
            continue
        cand = voxel.normalize(rest | {rng.choice(spots)})
        if voxel.signature(cand) != voxel.signature(piece) and voxel.signature(cand) != voxel.signature(voxel.mirror(piece)):
            return cand
    return None


def generate(rng, difficulty):
    tier = difficulty if difficulty in BOXES else rng.choice(("easy", "mid", "mid", "hard"))
    mode = rng.choice(("complete", "complete", "impossible")) if tier != "easy" else "complete"
    if mode == "complete":
        return _complete(rng, tier)
    return _impossible(rng, tier)


def _complete(rng, tier):
    dims = list(BOXES[tier])
    rng.shuffle(dims)
    dims = tuple(dims)
    pieces = _partition(rng, dims)
    if not pieces or not all(_interesting(p) for p in pieces):
        return None
    sigs = [voxel.signature(p) for p in pieces]
    if len(set(sigs)) < 3:
        return None
    given, third = pieces[:2], pieces[2]
    distract = []
    mirrored = voxel.mirror(third)
    if voxel.signature(mirrored) != voxel.signature(third):
        distract.append(mirrored)
    while len(distract) < 3:
        cand = _moved(rng.choice([third] + distract), rng)
        if cand is None:
            return None
        if voxel.signature(cand) not in {voxel.signature(d) for d in distract} | {voxel.signature(third)}:
            distract.append(cand)
    shown = [_display(p, rng) for p in given + [third] + distract]
    if any(s is None for s in shown):
        return None
    name = "正方体" if len(set(dims)) == 1 else "长方体"
    size = "×".join(map(str, sorted(dims)))
    stem = (f"左边两个立体图形均由相同的小正方体组成。下列选项中，能与它们拼合成一个 {size} 的{name}的是"
            "（可以旋转，不能翻转，不能重叠，不留空隙）：")
    return {"stem": stem, "mode": "complete", "dims": list(dims),
            "given": [sorted(map(list, s)) for s in shown[:2]],
            "options": [sorted(map(list, s)) for s in shown[2:]], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


def _impossible(rng, tier):
    sizes = {"mid": (4, 5), "hard": (5, 6)}[tier]
    a = voxel.grow(rng, rng.randint(*sizes))
    b = voxel.grow(rng, rng.randint(3, sizes[0]))
    if not a or not b or not _interesting(a) or voxel.signature(a) == voxel.signature(b):
        return None
    combos = {}
    for form in voxel.orientations(b):
        for anchor in a:
            for n in voxel.neighbors(anchor):
                for cell in form:
                    delta = tuple(n[i] - cell[i] for i in range(3))
                    placed = {tuple(c[i] + delta[i] for i in range(3)) for c in form}
                    if placed & set(a):
                        continue
                    union = voxel.normalize(set(a) | placed)
                    combos.setdefault(voxel.signature(union), union)
    valid = list(combos.values())
    rng.shuffle(valid)
    picked = []
    for shape in valid:
        if _display(shape, rng):
            picked.append(shape)
        if len(picked) == 3:
            break
    if len(picked) < 3:
        return None
    bad = None
    for _ in range(30):
        cand = _moved(rng.choice(picked), rng)
        if cand and voxel.signature(cand) not in combos and _display(cand, rng) and not voxel.pack([a, b], cand):
            bad = cand
            break
    if bad is None:
        return None
    shown = [_display(p, rng) for p in (a, b, bad, *picked)]
    if any(s is None for s in shown):
        return None
    stem = "左边是两个由相同小正方体组成的立体图形，下列立体图形中，最不可能由这两个立体图形拼接而成的是（可以旋转，不能翻转）："
    return {"stem": stem, "mode": "impossible", "dims": None,
            "given": [sorted(map(list, s)) for s in shown[:2]],
            "options": [sorted(map(list, s)) for s in shown[2:]], "answer": 0,
            "difficulty": {"mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
PANEL_W, PANEL_H = 210, 190
OPT = 170


def _draw_piece(svg, cells, w, h, data, dx=0.0, dy=0.0):
    cells = [tuple(c) for c in cells]
    ox, oy, s = voxel.layout(cells, w, h, margin=14, s_max=40)
    with svg.group({**data, "ox": round(ox, 3), "oy": round(oy, 3), "s": round(s, 3)}, dx, dy):
        voxel.draw(svg, cells, ox, oy, s)


def render(draft, order):
    figure = Svg(2 * PANEL_W + 30, PANEL_H + 40)
    for i, piece in enumerate(draft["given"]):
        _draw_piece(figure, piece, PANEL_W, PANEL_H, {"piece": str(i + 1)}, dx=10 + i * (PANEL_W + 10), dy=4)
        figure.text((10 + i * (PANEL_W + 10) + PANEL_W / 2, PANEL_H + 22), "①②"[i], size=22)
    cells = {LETTERS[i]: draft["options"][j] for i, j in enumerate(order)}
    sheet = options_sheet({k: (lambda svg, c=v: _draw_piece(svg, c, OPT, OPT, {"shape": "1"})) for k, v in cells.items()},
                          OPT, OPT, cols=4)
    if draft["mode"] == "complete":
        figure.body.insert(1, f'<desc data-dims="{",".join(map(str, draft["dims"]))}"/>')
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def _read_groups(svg_text, png, key):
    prims = parse(svg_text)
    groups = {}
    for p in prims:
        if key in p.data and "voxel" in p.data:
            gid = p.data[key] if key != "shape" else p.data["option"]
            g = groups.setdefault(gid, {"cells": set(), "params": (float(p.data["ox"]), float(p.data["oy"]), float(p.data["s"])),
                                        "offset": p.offset})
            g["cells"].add(tuple(map(int, p.data["voxel"].split(","))))
    issues = []
    for gid, g in groups.items():
        ox, oy, s = g["params"]
        bad, seen = voxel.verify_drawing(png, g["cells"], ox, oy, s, shift=g["offset"])
        issues += [f"{gid}：{b}" for b in bad]
        hidden = [c for c, n in seen.items() if n < 2]
        if hidden:
            issues.append(f"{gid}：有 {len(hidden)} 个小正方体看不见")
    return {gid: voxel.normalize(g["cells"]) for gid, g in groups.items()}, issues


def judge(svgs, pngs=None, stem=None, texts=None):
    given, issues = _read_groups(svgs["figure"], pngs["figure"], "piece")
    options, more = _read_groups(svgs["options"], pngs["options"], "shape")
    issues += more
    if sorted(given) != ["1", "2"] or sorted(options) != list(LETTERS):
        raise ValueError("拼接图的块或选项不全")
    dims = re.search(r'data-dims="([\d,]+)"', svgs["figure"])
    if len({voxel.signature(o) for o in options.values()}) < 4:
        issues.append("有两个选项是同一个立体")
    if dims:
        box = _box(tuple(map(int, dims.group(1).split(","))))
        fits = {k: bool(voxel.pack([given["1"], given["2"], o], box)) for k, o in options.items()}
        correct = [k for k, ok in fits.items() if ok]
        mode = "complete"
    else:
        fits = {k: bool(voxel.pack([given["1"], given["2"]], o)) for k, o in options.items()}
        correct = [k for k, ok in fits.items() if not ok]
        mode = "impossible"
    sizes = {k: len(o) for k, o in options.items()}
    answer_sig = voxel.signature(options[correct[0]]) if len(correct) == 1 else None
    return {"correct": correct, "issues": issues, "mode": mode, "fits": fits, "sizes": sizes,
            "given_sizes": [len(given["1"]), len(given["2"])],
            "box": dims.group(1) if dims else None,
            "mirror": {k: voxel.signature(voxel.mirror(o)) == answer_sig for k, o in options.items()}}


def explain(verdict, key):
    n1, n2 = verdict["given_sizes"]
    lines = []
    if verdict["mode"] == "complete":
        a, b, c = map(int, verdict["box"].split(","))
        total = a * b * c
        lines.append(f"目标是 {a}×{b}×{c}，共 {total} 个小正方体；①②分别 {n1}、{n2} 个，第三块应为 {total - n1 - n2} 个。")
        for letter in LETTERS:
            n = verdict["sizes"][letter]
            if letter == key:
                lines.append(f"{letter} 项：{n} 个，旋转后能和①②严丝合缝拼满，当选。")
            elif n != total - n1 - n2:
                lines.append(f"{letter} 项：{n} 个，个数就不对，排除。")
            else:
                lines.append(f"{letter} 项：个数对，但怎么转都会留空或重叠"
                             + ("（它和正确的那块互为镜像，题目不允许翻转）" if verdict["mirror"][letter] else "") + "，排除。")
    else:
        lines.append(f"①②共 {n1 + n2} 个小正方体，选项要先满足个数，再看能否拆成①和②两块。")
        for letter in LETTERS:
            n = verdict["sizes"][letter]
            if letter == key:
                lines.append(f"{letter} 项：" + (f"{n} 个，个数就不对" if n != n1 + n2 else "个数对，但拆不出①和②两块")
                             + "，最不可能，当选。")
            else:
                lines.append(f"{letter} 项：可以拆成①和②两块，能拼成，排除。")
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
    twin = dict(draft, options=[draft["options"][0], draft["options"][0], draft["options"][2], draft["options"][3]])
    issues, _ = check(me, *build(twin, order), "B")
    out.append(("两个选项是同一块", bool(issues), "；".join(issues)))
    hidden = dict(draft, given=[sorted(map(list, voxel.normalize([(x, y, z) for x in range(2) for y in range(2) for z in range(2)]))),
                                draft["given"][1]])
    issues, _ = check(me, *build(hidden, order), "B")
    out.append(("给的块里有小正方体完全被挡住（按看得见的拼不成）", bool(issues), "；".join(issues)))
    svgs2 = dict(svgs)
    svgs2["figure"] = re.sub(r'<polygon [^>]*data-vface="front"/>', "", svgs["figure"], count=2)
    issues, _ = check(me, svgs2, {k: rasterize(v) for k, v in svgs2.items()}, "B")
    out.append(("立体图漏画两个面", bool(issues), "；".join(issues)))
    return out

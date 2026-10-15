"""三视图（小正方体堆成的立体）：从任一角度看，哪个选项不可能是它的视图；或哪个是主视图。

立体是放在桌面上的「堆叠」：每格一摞，从桌面往上连续。画法保证每摞的顶面都看得见，
所以画出来的图唯一确定这个立体。视图按初中三视图画法，用单位正方形格子表示。

判题器：从立体图 SVG 读出每个面属于哪个小正方体，再用射线求交逐点核对 PNG 上看到的确实是这些面
（画家算法画错、漏画、多画都会对不上），并核对每摞顶面都露出来；选项格子按矩形坐标读成格点；
视图用判题器自己的投影代码算。
"""

from __future__ import annotations

import math
import random
import re
import sys

from . import voxel
from .core import LETTERS, Svg, options_sheet, parse

NAME = "voxel_views"
TAG = "判断推理-图形推理-空间类-三视图"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "空间类-三视图"
VERSION = 1
MAX_TRIES = 120
PARTS = ("figure", "options")
DEFINITION = ("三视图：小正方体堆成的立体，从前、后、左、右、上、下看到的平面图形。"
              "主视图看每列最高几层，左视图看每排最高几层，俯视图看占了哪些格；选非题找哪个方向都看不到的那张。")
STEM_ANY = "下图为给定的立体图形，从任一角度看，下列选项最不可能是该立体图形视图的是："
STEM_FRONT = "下图为给定的立体图形，箭头所指为正面，下列选项中是该立体图形主视图的是："


def heights_to_cells(h):
    return voxel.normalize((x, y, z) for (x, y), n in h.items() for z in range(n))


def views(cells):
    """判题器与生成器共用的视图定义：方向 -> 平面格点集合（列, 行），行 0 在下。"""
    cells = set(cells)
    out = {
        "前": {(x, z) for x, y, z in cells},
        "后": {(-x, z) for x, y, z in cells},
        "左": {(-y, z) for x, y, z in cells},
        "右": {(y, z) for x, y, z in cells},
        "上": {(x, y) for x, y, z in cells},
        "下": {(-x, y) for x, y, z in cells},
    }
    return {k: norm2(v) for k, v in out.items()}


def norm2(cells):
    cells = list(cells)
    mx, my = min(c[0] for c in cells), min(c[1] for c in cells)
    return frozenset((x - mx, y - my) for x, y in cells)


def symmetries2(cells):
    out = set()
    pts = list(cells)
    for k in range(4):
        rot = pts
        for _ in range(k):
            rot = [(y, -x) for x, y in rot]
        out.add(norm2(rot))
        out.add(norm2([(-x, y) for x, y in rot]))
    return out


def _skyline(cells):
    cols = {}
    for x, y in cells:
        cols.setdefault(x, set()).add(y)
    return all(rows == set(range(max(rows) + 1)) for rows in cols.values())


def _connected2(cells):
    cells = set(cells)
    seen, todo = set(), [next(iter(cells))]
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        x, y = c
        todo.extend(n for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if n in cells and n not in seen)
    return seen == cells


TIER = {"easy": ((2, 3), 3, (5, 8)), "mid": ((3, 3), 3, (7, 11)), "hard": ((3, 4), 3, (9, 14))}


def generate(rng, difficulty):
    tier = difficulty if difficulty in TIER else rng.choice(("easy", "mid", "mid", "hard"))
    (a, b), hmax, (lo, hi) = TIER[tier]
    if rng.random() < 0.5:
        a, b = b, a
    # 同一列从前往后不变矮，后排顶面才露得出来（斜二测从前上方看，前排高了会整个挡住后排）
    h = {}
    for x in range(a):
        for y, n in enumerate(sorted(rng.choice((0, 1, 1, 2, 2, 3)) for _ in range(b))):
            h[(x, y)] = n
    h = {k: min(v, hmax) for k, v in h.items() if v > 0}
    if not h or not lo <= sum(h.values()) <= hi or not _connected2(h.keys()):
        return None
    cells = heights_to_cells(h)
    vs = views(cells)
    if len(set(vs.values())) < 4:  # 太对称，几个方向长一样，题没意思
        return None
    polarity = "front" if tier == "easy" and rng.random() < 0.5 else "any"
    closure = set().union(*(symmetries2(v) for v in vs.values()))
    if polarity == "any":
        shown = rng.sample([k for k in vs if k not in ("下",)], 3)
        valid = [vs[k] for k in shown]
        if len(set(valid)) < 3:
            return None
        base = rng.choice(valid)
        bad = None
        for _ in range(60):
            cell = rng.choice(sorted(base))
            grow_or_cut = rng.random() < 0.5
            if grow_or_cut:
                x, y = cell
                cand = set(base) | {rng.choice(((x + 1, y), (x - 1, y), (x, y + 1)))}
            else:
                cand = set(base) - {cell}
            if not cand or not _connected2(cand):
                continue
            side = base in (vs["前"], vs["后"], vs["左"], vs["右"])
            if side and not _skyline(norm2(cand)):
                continue
            cand = norm2(cand)
            if cand not in closure and cand not in valid:
                bad = cand
                break
        if bad is None:
            return None
        options = [bad] + valid
        meta = {"shown": shown}
    else:
        front = vs["前"]
        others = [vs[k] for k in ("后", "左", "右", "上") if vs[k] != front]
        others = list(dict.fromkeys(others))
        if len(others) < 3:
            return None
        options = [front] + rng.sample(others, 3)
        meta = {}
    if len(set(options)) < 4:
        return None
    return {"stem": STEM_ANY if polarity == "any" else STEM_FRONT, "polarity": polarity,
            "heights": [[x, y, n] for (x, y), n in sorted(h.items())],
            "options": [sorted(map(list, o)) for o in options], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier], **meta}


# ---------------------------------------------------------------- 渲染
FIG_W, FIG_H = 360, 280
OPT = 150


def _draw_view(svg, cells):
    cells = list(map(tuple, cells))
    w = max(x for x, _ in cells) + 1
    h = max(y for _, y in cells) + 1
    s = min(32, (OPT - 30) / max(w, h))
    x0 = (OPT - s * w) / 2
    y0 = (OPT - s * h) / 2
    for x, y in cells:
        svg.rect(x0 + x * s, y0 + (h - 1 - y) * s, s, s, sw=2.0, data={"vcell": "1"})


def render(draft, order):
    h = {(x, y): n for x, y, n in draft["heights"]}
    cells = heights_to_cells(h)
    ox, oy, s = voxel.layout(cells, FIG_W, FIG_H, margin=24, s_max=52)
    figure = Svg(FIG_W, FIG_H)
    with figure.group({"solid": "1", "ox": round(ox, 3), "oy": round(oy, 3), "s": round(s, 3)}):
        voxel.draw(figure, cells, ox, oy, s)
    if draft["polarity"] == "front":  # 箭头沿纵深方向指向正面，表示从正面看
        (x0, x1), (y0, _), (z0, _) = voxel.bounds(cells)
        bx, by_ = voxel.project(((x0 + x1) / 2, y0, z0), ox, oy, s)
        ux, uy = voxel.K / (2 * voxel.K * voxel.K) ** 0.5, -voxel.K / (2 * voxel.K * voxel.K) ** 0.5
        head = (bx - 8 * ux, by_ - 8 * uy)
        tail = (bx - 70 * ux, by_ - 70 * uy)
        figure.line(tail, head, w=2.4, data={"mark": "front"})
        wing = lambda a: (head[0] - 11 * (ux * math.cos(a) - uy * math.sin(a)),
                          head[1] - 11 * (ux * math.sin(a) + uy * math.cos(a)))
        figure.poly([wing(0.45), head, wing(-0.45)], w=2.4, data={"mark": "front"})
        figure.text((tail[0] - 8, tail[1] + 14), "正面", size=18)
    cellsets = {LETTERS[i]: draft["options"][j] for i, j in enumerate(order)}
    sheet = options_sheet({k: (lambda svg, c=v: _draw_view(svg, c)) for k, v in cellsets.items()}, OPT, OPT, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def read_solid(svg_text):
    prims = parse(svg_text)
    group = next((p for p in prims if p.data.get("solid")), None)
    if group is None:
        raise ValueError("立体图缺少画法参数")
    ox, oy, s = (float(group.data[k]) for k in ("ox", "oy", "s"))
    seen = {tuple(map(int, p.data["voxel"].split(","))) for p in prims if "voxel" in p.data}
    if not seen:
        raise ValueError("立体图没有小正方体")
    # 像考生一样理解这张图：每摞从桌面堆到看得见的最高一层，被挡住的下层按实心算
    tops = {}
    for x, y, z in seen:
        tops[(x, y)] = max(tops.get((x, y), -1), z)
    cells = {(x, y, z) for (x, y), top in tops.items() for z in range(top + 1)}
    return cells, ox, oy, s, any(p.data.get("mark") == "front" for p in prims)


def read_views(svg_text):
    out = {}
    for letter in LETTERS:
        rects = [p for p in parse(svg_text) if p.data.get("option") == letter and p.data.get("vcell")]
        if not rects:
            continue
        size = rects[0].points[1][0] - rects[0].points[0][0]
        xs = [p.local()[0][0] for p in rects]
        ys = [p.local()[0][1] for p in rects]
        x0, ybot = min(xs), max(ys)
        out[letter] = norm2((round((x - x0) / size), round((ybot - y) / size)) for x, y in zip(xs, ys))
    return out


def judge(svgs, pngs=None, stem=None, texts=None):
    cells, ox, oy, s, has_front = read_solid(svgs["figure"])
    issues, seen = voxel.verify_drawing(pngs["figure"], cells, ox, oy, s)
    tops = {}
    for x, y, z in cells:
        tops[(x, y)] = max(tops.get((x, y), -1), z)
    hidden = [c for c, z in tops.items() if seen.get((c[0], c[1], z), 0) < 3]
    if hidden:
        issues.append(f"有 {len(hidden)} 摞的顶面被挡住，图不能唯一确定立体")
    vs = views(cells)
    options = read_views(svgs["options"])
    if sorted(options) != list(LETTERS):
        raise ValueError("选项不全")
    if len(set(options.values())) < 4:
        issues.append("有两个选项画得一样")
    exact = {k: [d for d, v in vs.items() if v == o] for k, o in options.items()}
    closure = {d: symmetries2(v) for d, v in vs.items()}
    if has_front:
        correct = [k for k, ds in exact.items() if "前" in ds]
    else:
        congruent = {k: [d for d, c in closure.items() if o in c] for k, o in options.items()}
        correct = [k for k in options if not congruent[k]]
        vague = [k for k in options if congruent[k] and not exact[k]]
        if vague:
            issues.append(f"{vague} 只有转过或翻过才像某个视图，说不清能不能看到")
    return {"correct": correct, "issues": issues, "front": has_front,
            "exact": {k: v for k, v in exact.items()},
            "views": {d: sorted(map(list, v)) for d, v in vs.items()},
            "options": {k: sorted(map(list, v)) for k, v in options.items()}}


def _columns(cells):
    cols = {}
    for x, y in cells:
        cols[x] = max(cols.get(x, 0), y + 1)
    return [cols.get(x, 0) for x in range(max(cols) + 1)]


def explain(verdict, key):
    exact = verdict["exact"]
    lines = []
    if verdict["front"]:
        lines.append("主视图从箭头所指的正面看，看每一列最高有几层。")
        for letter in LETTERS:
            ds = exact.get(letter) or []
            if letter == key:
                lines.append(f"{letter} 项：每列层数与正面看到的一致，当选。")
            elif ds:
                lines.append(f"{letter} 项：是从{ds[0]}面看到的图形，不是主视图，排除。")
            else:
                lines.append(f"{letter} 项：哪个方向都看不到这样的图形，排除。")
        return "\n".join(lines)
    lines.append("立体放在桌面上，前后、左右看到的是每列（排）的最高层数，上下看到的是占了哪些格。")
    for letter in LETTERS:
        ds = exact.get(letter) or []
        if letter == key:
            opt = [tuple(c) for c in verdict["options"][letter]]
            near = min(verdict["views"].items(),
                       key=lambda kv: len(set(map(tuple, kv[1])) ^ set(opt)))
            lines.append(f"{letter} 项：从哪个方向都看不到。它和从{near[0]}面看到的图形最像，"
                         f"但差了 {len(set(map(tuple, near[1])) ^ set(opt))} 个小方块，当选。")
        else:
            lines.append(f"{letter} 项：是从{'、'.join(ds)}面看到的图形，可能，排除。")
    return "\n".join(lines)


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]

    def build(draft, order):
        svgs = render(draft, order)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    draft, order, svgs, pngs = verified(me, "self-test-any", "mid", "D")
    seed = 0
    while draft["polarity"] != "any":
        seed += 1
        draft, order, svgs, pngs = verified(me, f"self-test-any-{seed}", "mid", "D")
    issues, _ = check(me, svgs, pngs, "D")
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "A")
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    # 把「不可能」的那项换成一个真能看到的视图：变成没有答案
    vs = views(heights_to_cells({(x, y): n for x, y, n in draft["heights"]}))
    spare = next(v for v in vs.values() if sorted(map(list, v)) not in draft["options"])
    bad = dict(draft, options=[sorted(map(list, spare))] + draft["options"][1:])
    issues, _ = check(me, *build(bad, order), "D")
    out.append(("选非题四项都看得到", bool(issues), "；".join(issues)))
    # 渲染器漏画一个小正方体的顶面：射线核对应发现
    svgs3 = dict(svgs)
    svgs3["figure"] = re.sub(r'<polygon [^>]*data-vface="top"/>', "", svgs["figure"], count=1)
    issues, _ = check(me, svgs3, {k: rasterize(v) for k, v in svgs3.items()}, "D")
    out.append(("立体图漏画一个顶面", bool(issues), "；".join(issues)))
    # 后排一摞被前排挡住：图不能确定立体
    hidden = {"stem": STEM_ANY, "polarity": "any", "heights": [[0, 0, 3], [1, 0, 3], [0, 1, 1], [1, 1, 3]],
              "options": draft["options"], "answer": 0, "difficulty": 3}
    issues, _ = check(me, *build(hidden, order), "D")
    out.append(("后排一摞被挡住", any("挡住" in i for i in issues), "；".join(issues)))
    return out

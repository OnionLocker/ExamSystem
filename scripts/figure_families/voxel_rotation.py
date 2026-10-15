"""立体旋转（同一物体）：给一个小正方体组成的立体，问哪个选项是（或不可能是）同一个物体转过来的样子。

真题两种问法都有：「最可能与左侧立体图形是同一物体的是」「与所给立体图形不可能是同一图形的是」。
干扰项：镜像体（左右手，转不过来）、挪动一个小正方体的近似体。所有图都换到每个小正方体都露得出来的摆法。

判题器：从 SVG 读出各图画了哪些小正方体，射线求交逐点核对 PNG、要求每个小正方体都看得见；
再在 24 个保向旋转里比对是不是同一物体；题干说「不可能」就找唯一不同的那个，否则找唯一相同的那个。
"""

from __future__ import annotations

import random
import re
import sys

from . import voxel
from .core import LETTERS, Svg, options_sheet

NAME = "voxel_rotation"
TAG = "判断推理-图形推理-空间类-立体旋转"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "空间类-立体旋转"
VERSION = 1
MAX_TRIES = 80
PARTS = ("figure", "options")
DEFINITION = ("立体旋转：同一个立体从不同角度看。抓住最有特征的一段（凸出的那块、拐角方向），"
              "转过去看相对位置是否一致；左右镜像的立体怎么转都重合不了。")
STEM_SAME = "下列选项中，最可能与左侧立体图形是同一物体的是："
STEM_NOT = "下列选项中，与左侧立体图形不可能是同一物体的是："

SIZES = {"easy": (5, 5), "mid": (6, 7), "hard": (7, 8)}


def _display(shape, rng, avoid=()):
    forms = list(voxel.orientations(shape))
    rng.shuffle(forms)
    for form in forms:
        if form in avoid:
            continue
        cells = set(form)
        if not all((x, y - 1, z) not in cells or (x + 1, y, z) not in cells or (x, y, z + 1) not in cells
                   for x, y, z in cells):
            continue
        if min(voxel.visible_counts(form, s=24.0, step=4.0).values()) >= 3:
            return form
    return None


def _moved(shape, rng):
    cells = set(shape)
    bad = {voxel.signature(shape), voxel.signature(voxel.mirror(shape))}
    for _ in range(40):
        out = rng.choice(sorted(cells))
        rest = cells - {out}
        if not voxel.connected(rest):
            continue
        spots = sorted({n for c in rest for n in voxel.neighbors(c)} - cells)
        cand = voxel.normalize(rest | {rng.choice(spots)})
        if voxel.signature(cand) not in bad:
            return cand
    return None


def generate(rng, difficulty):
    tier = difficulty if difficulty in SIZES else rng.choice(("easy", "mid", "mid", "hard"))
    shape = voxel.grow(rng, rng.randint(*SIZES[tier]))
    if shape is None:
        return None
    (x0, x1), (y0, y1), (z0, z1) = voxel.bounds(shape)
    if sorted((x1 - x0, y1 - y0, z1 - z0))[1] < 2:
        return None  # 太扁，看不出立体感
    mirrored = voxel.mirror(shape)
    if voxel.signature(mirrored) == voxel.signature(shape) or len(voxel.orientations(shape)) < 12:
        return None  # 对称的立体没有镜像陷阱
    polarity = rng.choice(("same", "not"))
    stem_form = _display(shape, rng)
    if stem_form is None:
        return None
    if polarity == "same":
        moved = _moved(shape, rng)
        moved_mirror = _moved(mirrored, rng)
        candidates = [shape, mirrored, moved, moved_mirror]
    else:
        moved = _moved(mirrored, rng) if rng.random() < 0.3 else None
        candidates = [moved or mirrored, shape, shape, shape]
    if any(c is None for c in candidates):
        return None
    shown = []
    for i, c in enumerate(candidates):
        form = _display(c, rng, avoid=set(shown) | {stem_form})
        if form is None:
            return None
        shown.append(form)
    if len({tuple(f) for f in shown}) < 4:
        return None
    return {"stem": STEM_SAME if polarity == "same" else STEM_NOT, "polarity": polarity,
            "shape": sorted(map(list, stem_form)), "options": [sorted(map(list, f)) for f in shown],
            "answer": 0, "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
FIG = 230
OPT = 170


def _draw(svg, cells, w, h, data):
    cells = [tuple(c) for c in cells]
    ox, oy, s = voxel.layout(cells, w, h, margin=16, s_max=40)
    with svg.group({**data, "ox": round(ox, 3), "oy": round(oy, 3), "s": round(s, 3)}):
        voxel.draw(svg, cells, ox, oy, s)


def render(draft, order):
    figure = Svg(FIG, FIG)
    _draw(figure, draft["shape"], FIG, FIG, {"solid": "stem"})
    cells = {LETTERS[i]: draft["options"][j] for i, j in enumerate(order)}
    sheet = options_sheet({k: (lambda svg, c=v: _draw(svg, c, OPT, OPT, {"solid": "option"})) for k, v in cells.items()},
                          OPT, OPT, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器
def _read(svg_text, png, by_option):
    from .core import parse

    groups = {}
    for p in parse(svg_text):
        if "voxel" not in p.data:
            continue
        gid = p.data.get("option") if by_option else "stem"
        g = groups.setdefault(gid, {"cells": set(), "params": tuple(float(p.data[k]) for k in ("ox", "oy", "s")),
                                    "offset": p.offset})
        g["cells"].add(tuple(map(int, p.data["voxel"].split(","))))
    issues = []
    for gid, g in groups.items():
        bad, seen = voxel.verify_drawing(png, g["cells"], *g["params"], shift=g["offset"])
        issues += [f"{gid}：{b}" for b in bad]
        if any(n < 2 for n in seen.values()):
            issues.append(f"{gid}：有小正方体看不见")
    return {gid: voxel.normalize(g["cells"]) for gid, g in groups.items()}, issues


def judge(svgs, pngs, stem=None, texts=None):
    stems, issues = _read(svgs["figure"], pngs["figure"], False)
    options, more = _read(svgs["options"], pngs["options"], True)
    issues += more
    if "stem" not in stems or sorted(options) != list(LETTERS):
        raise ValueError("立体图或选项不全")
    shape = stems["stem"]
    sig, mirror_sig = voxel.signature(shape), voxel.signature(voxel.mirror(shape))
    same = {k: voxel.signature(o) == sig for k, o in options.items()}
    mirror = {k: voxel.signature(o) == mirror_sig for k, o in options.items()}
    not_polarity = "不可能" in (stem or "")
    correct = [k for k, v in same.items() if (not v if not_polarity else v)]
    if len({tuple(o) for o in options.values()}) < 4:
        issues.append("有两个选项画得一模一样")
    return {"correct": correct, "issues": issues, "not": not_polarity, "same": same, "mirror": mirror,
            "sizes": {k: len(o) for k, o in options.items()}, "size": len(shape)}


def explain(verdict, key):
    lines = [f"左侧立体由 {verdict['size']} 个小正方体组成。先找最有特征的部分（凸出的一块、拐角方向），"
             "转到选项的角度后核对相对位置；左右镜像的立体怎么转都重合不了。"]
    for letter in LETTERS:
        if verdict["same"][letter]:
            what = "是同一个立体转过来的样子"
        elif verdict["mirror"][letter]:
            what = "与左侧立体互为镜像，旋转无法重合"
        elif verdict["sizes"][letter] != verdict["size"]:
            what = f"小正方体个数是 {verdict['sizes'][letter]} 个，对不上"
        else:
            what = "有一个小正方体的位置不同，旋转无法重合"
        end = "当选" if letter == key else ("可能，排除" if verdict["same"][letter] else "排除")
        lines.append(f"{letter} 项：{what}，{end}。")
    return "\n".join(lines)


def self_test():
    from .core import check, rasterize, verified

    me = sys.modules[__name__]

    def build(draft, order):
        svgs = render(draft, order)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    draft, order, svgs, pngs = verified(me, "self-test", "mid", "C")
    issues, _ = check(me, svgs, pngs, "C", draft["stem"])
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "D", draft["stem"])
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    flipped = STEM_NOT if draft["polarity"] == "same" else STEM_SAME
    issues, _ = check(me, svgs, pngs, "C", flipped)
    out.append(("题干问法与选项设计对不上", bool(issues), "；".join(issues)))
    mirror_stem = dict(draft, shape=sorted(map(list, voxel.mirror([tuple(c) for c in draft["shape"]]))))
    issues, _ = check(me, *build(mirror_stem, order), "C", draft["stem"])
    out.append(("题干立体画成镜像", bool(issues), "；".join(issues)))
    svgs2 = dict(svgs)
    last = list(re.finditer(r'<polygon [^>]*data-vface="top"/>', svgs["options"]))[-1]  # 最后画的最靠前，一定看得见
    svgs2["options"] = svgs["options"][:last.start()] + svgs["options"][last.end():]
    issues, _ = check(me, svgs2, {k: rasterize(v) for k, v in svgs2.items()}, "C", draft["stem"])
    out.append(("选项图漏画一个面", bool(issues), "；".join(issues)))
    return out

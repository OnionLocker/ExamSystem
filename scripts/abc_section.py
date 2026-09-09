#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exam-style: mark A,B,C on a cube stack; choose the section among four shapes."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from pathlib import Path

from figure_lab import BG, INK, Svg, draw_voxels, fit_iso, iso, voxel_corners
from oblique_section import (
    border_edges,
    cube_cut,
    grow_voxels,
    order_poly,
    plane_basis,
    project_to_plane,
    to2d,
)
from program_figure import svg_to_png


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def plane_from_abc(a, b, c):
    n = _cross(_sub(b, a), _sub(c, a))
    if _len(n) < 1e-8:
        return None
    return (n[0], n[1], n[2], _dot(n, a))


def collinear(a, b, c):
    return _len(_cross(_sub(b, a), _sub(c, a))) < 1e-6


def same_axis_face(a, b, c):
    return a[0] == b[0] == c[0] or a[1] == b[1] == c[1] or a[2] == b[2] == c[2]


def visible_corners(voxels):
    occ = set(voxels)
    pts = set()
    for x, y, z in occ:
        if (x, y, z + 1) not in occ:
            pts.update(((x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)))
        if (x + 1, y, z) not in occ:
            pts.update(((x + 1, y, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x + 1, y, z + 1)))
        if (x, y + 1, z) not in occ:
            pts.update(((x, y + 1, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)))
    return list(pts)


def section_pieces(voxels, plane):
    u, v = plane_basis(plane)
    pieces = []
    hits = []
    for x, y, z in voxels:
        poly = cube_cut(x, y, z, plane)
        if poly:
            hits.extend(poly)
            pieces.append(poly)
    if len(hits) < 3:
        return None
    origin = project_to_plane(
        (sum(p[0] for p in hits) / len(hits), sum(p[1] for p in hits) / len(hits), sum(p[2] for p in hits) / len(hits)),
        plane,
    )
    ordered = [order_poly(poly, u, v, origin) for poly in pieces]
    flat = [[to2d(p, origin, u, v) for p in poly] for poly in ordered]
    return {"u": u, "v": v, "origin": origin, "ordered": ordered, "flat": flat, "hits": hits}


def stitch_loops(flat):
    edges = border_edges(flat)

    def q(p):
        return (round(p[0], 3), round(p[1], 3))

    adj = defaultdict(list)
    raw = {}
    for a, b in edges:
        qa, qb = q(a), q(b)
        if qa == qb:
            continue
        adj[qa].append(qb)
        adj[qb].append(qa)
        raw.setdefault(qa, a)
        raw.setdefault(qb, b)
    loops = []
    seen = set()
    for start in list(adj):
        if start in seen:
            continue
        loop = [start]
        prev = None
        cur = start
        seen.add(start)
        for _ in range(len(adj) + 2):
            nxts = [n for n in adj[cur] if n != prev]
            if not nxts:
                break
            nxt = nxts[0]
            loop.append(nxt)
            seen.add(nxt)
            if nxt == start:
                break
            prev, cur = cur, nxt
        if len(loop) >= 4:
            loops.append([raw.get(p, p) for p in loop[:-1]])
    return loops or [[p for poly in flat for p in poly[:1]]]


def outer_n(flat):
    return sum(len(loop) for loop in stitch_loops(flat))


def shape_key(flat):
    loops = stitch_loops(flat)
    pts = tuple(sorted((round(p[0], 2), round(p[1], 2)) for loop in loops for p in loop))
    return (len(pts), pts)


def pick_abc(voxels, rng, tries=320):
    corners = visible_corners(voxels)
    if len(corners) < 3:
        return None
    best = None
    for _ in range(tries):
        a, b, c = rng.sample(corners, 3)
        if collinear(a, b, c) or same_axis_face(a, b, c):
            continue
        if min(_len(_sub(a, b)), _len(_sub(a, c)), _len(_sub(b, c))) < 1.2:
            continue
        plane = plane_from_abc(a, b, c)
        if plane is None:
            continue
        sec = section_pieces(voxels, plane)
        if not sec:
            continue
        n = outer_n(sec["flat"])
        if n < 4 or n > 8:
            continue
        score = (n, len(sec["ordered"]))
        if best is None or score > best[0]:
            best = (score, (a, b, c), plane, sec)
            if n >= 5:
                break
    return best


def fit_loops(loops, box):
    xs = [p[0] for loop in loops for p in loop]
    ys = [p[1] for loop in loops for p in loop]
    x0, y0, w, h = box
    sc = min(w / max(max(xs) - min(xs), 1e-6), h / max(max(ys) - min(ys), 1e-6)) * 0.72
    cx, cy = x0 + w / 2, y0 + h / 2
    mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [[(cx + (p[0] - mx) * sc, cy + (p[1] - my) * sc) for p in loop] for loop in loops]


def draw_flat(s, flat, box):
    loops = stitch_loops(flat)
    drawn = fit_loops(loops, box)
    for poly in drawn:
        if len(poly) >= 3:
            s.polygon(poly, fill="url(#hatch)", w=2.4)


def convex_flat(flat):
    pts = [(p[0], p[1]) for poly in flat for p in poly]
    pts = list({(round(p[0], 4), round(p[1], 4)): p for p in pts}.values())
    pts = sorted(pts)
    if len(pts) < 3:
        return [pts]

    def side(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and side(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and side(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [lower[:-1] + upper[:-1]]


def distractors(voxels, abc, truth, rng):
    a, b, c = abc
    cands = []
    triangle = [[to2d(p, truth["origin"], truth["u"], truth["v"]) for p in (a, b, c)]]
    cands.append(triangle)
    hull = convex_flat(truth["flat"])
    cands.append(hull)
    horiz = section_pieces(voxels, (0.0, 0.0, 1.0, 0.5))
    if horiz:
        cands.append(horiz["flat"])
    corners = visible_corners(voxels)
    guard = 0
    while len(cands) < 8 and guard < 80:
        guard += 1
        x, y, z = rng.sample(corners, 3)
        if collinear(x, y, z) or same_axis_face(x, y, z):
            continue
        plane = plane_from_abc(x, y, z)
        if plane is None:
            continue
        sec = section_pieces(voxels, plane)
        if sec:
            cands.append(sec["flat"])
    uniq = []
    keys = {shape_key(truth["flat"])}
    for item in cands:
        if outer_n(item) < 3:
            continue
        key = shape_key(item)
        if key in keys:
            continue
        keys.add(key)
        uniq.append(item)
        if len(uniq) == 3:
            return uniq
    raise SystemExit("not enough distinct distractors")


def label_pos(p, box_center):
    dx = 26 if p[0] >= box_center[0] else -26
    dy = -20 if p[1] <= box_center[1] else 26
    return (p[0] + dx, p[1] + dy)


def render_question(voxels, abc, options, width=1100, height=640) -> Svg:
    s = Svg(width, height)
    s.text((550, 36), "过 A、B、C 三点切开，截面是？", 26)
    ox, oy, sc = fit_iso(voxel_corners(voxels) + list(abc), (90, 54, 920, 300), pad=30)
    draw_voxels(s, voxels, ox, oy, sc)
    pts2 = [iso(*p, ox, oy, sc) for p in abc]
    mid = (sum(p[0] for p in pts2) / 3, sum(p[1] for p in pts2) / 3)
    for name, p2 in zip("ABC", pts2):
        s.circle(p2, 5.4, fill=INK, w=1)
        s.text(label_pos(p2, mid), name, 24)
    boxes = ((40, 390, 240, 210), (300, 390, 240, 210), (560, 390, 240, 210), (820, 390, 240, 210))
    for key, flat, box in zip("ABCD", options, boxes):
        s.rect(box[0], box[1], box[2], box[3], fill=BG, sw=2.0)
        s.text((box[0] + 28, box[1] + 28), key, 22)
        draw_flat(s, flat, (box[0] + 28, box[1] + 40, box[2] - 56, box[3] - 58))
    return s


def make(seed: int = 11, n: int = 7):
    rng = random.Random(seed)
    voxels = grow_voxels(n, rng)
    picked = pick_abc(voxels, rng)
    if picked is None:
        raise SystemExit(f"no ABC cut for seed={seed}")
    _score, abc, plane, truth = picked
    wrongs = distractors(voxels, abc, truth, rng)
    placed = [truth["flat"], *wrongs]
    keys = list("ABCD")
    rng.shuffle(keys)
    answer = keys[0]
    options = [None] * 4
    slot = {k: i for i, k in enumerate("ABCD")}
    options[slot[answer]] = placed[0]
    for key, flat in zip((k for k in keys if k != answer), placed[1:]):
        options[slot[key]] = flat
    return {
        "voxels": voxels,
        "abc": abc,
        "plane": plane,
        "truth": truth,
        "options": options,
        "answer": answer,
        "seed": seed,
        "n_edge": outer_n(truth["flat"]),
    }


def render_stem(voxels, abc, width=1100, height=560) -> Svg:
    s = Svg(width, height)
    s.text((550, 36), "过 A、B、C 三点切开，截面是？", 26)
    ox, oy, sc = fit_iso(voxel_corners(voxels) + list(abc), (80, 60, 940, 460), pad=28)
    draw_voxels(s, voxels, ox, oy, sc)
    pts2 = [iso(*p, ox, oy, sc) for p in abc]
    mid = (sum(p[0] for p in pts2) / 3, sum(p[1] for p in pts2) / 3)
    for name, p2 in zip("ABC", pts2):
        s.circle(p2, 5.4, fill=INK, w=1)
        s.text(label_pos(p2, mid), name, 24)
    return s


def render_option_svg(flat, width=720, height=420) -> Svg:
    s = Svg(width, height)
    draw_flat(s, flat, (48, 40, 624, 340))
    return s


def place_for_letter(truth, wrongs, letter: str):
    options = [None] * 4
    slot = "ABCD".index(letter if letter in "ABCD" else "A")
    options[slot] = truth
    rest = [item for item in wrongs][:3]
    wi = 0
    for i in range(4):
        if options[i] is None:
            options[i] = rest[wi]
            wi += 1
    return options, "ABCD"[slot]


def draw(seed: int, dest: Path, n: int = 7) -> dict:
    quiz = make(seed, n)
    s = render_question(quiz["voxels"], quiz["abc"], quiz["options"])
    dest = Path(dest)
    s.write(dest.with_suffix(".svg"))
    svg_to_png(dest.with_suffix(".svg"), dest)
    quiz["path"] = str(dest)
    quiz["ok"] = True
    return quiz


if __name__ == "__main__":
    import sys

    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 11
    info = draw(seed, Path(f"/tmp/abc-section-{seed}.png"))
    print(seed, info["answer"], "edges", info["n_edge"], info["path"])

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Random voxel pile + oblique cut. Auto-fit so nothing is clipped."""

from __future__ import annotations

import math
import random
from pathlib import Path

from figure_lab import BG, Svg, draw_voxels, fit_iso, iso, iso_inside, voxel_corners
from program_figure import svg_to_png

EDGES = (
    ((0, 0, 0), (1, 0, 0)),
    ((0, 0, 0), (0, 1, 0)),
    ((0, 0, 0), (0, 0, 1)),
    ((1, 0, 0), (1, 1, 0)),
    ((1, 0, 0), (1, 0, 1)),
    ((0, 1, 0), (1, 1, 0)),
    ((0, 1, 0), (0, 1, 1)),
    ((0, 0, 1), (1, 0, 1)),
    ((0, 0, 1), (0, 1, 1)),
    ((1, 1, 0), (1, 1, 1)),
    ((1, 0, 1), (1, 1, 1)),
    ((0, 1, 1), (1, 1, 1)),
)


def grow_voxels(n: int, rng: random.Random) -> set[tuple[int, int, int]]:
    cells = {(0, 0, 0)}
    dirs = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1))
    guard = 0
    while len(cells) < n and guard < 500:
        guard += 1
        if rng.random() < 0.4:
            x, y, z = max(cells, key=lambda c: (c[2], rng.random()))
        else:
            x, y, z = rng.choice(tuple(cells))
        dx, dy, dz = rng.choice(dirs)
        nxt = (x + dx, y + dy, z + dz)
        if nxt[2] < 0:
            continue
        cells.add(nxt)
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    zs = [c[2] for c in cells]
    mx, my, mz = min(xs), min(ys), min(zs)
    return {(c[0] - mx, c[1] - my, c[2] - mz) for c in cells}


def _f(p, plane):
    a, b, c, d = plane
    return a * p[0] + b * p[1] + c * p[2] - d


def _hit(p0, p1, plane):
    f0, f1 = _f(p0, plane), _f(p1, plane)
    if abs(f0) < 1e-8:
        return p0
    if abs(f1) < 1e-8:
        return p1
    if f0 * f1 > 0:
        return None
    t = f0 / (f0 - f1)
    return (
        p0[0] + t * (p1[0] - p0[0]),
        p0[1] + t * (p1[1] - p0[1]),
        p0[2] + t * (p1[2] - p0[2]),
    )


def _uniq(pts, eps=1e-6):
    out = []
    for p in pts:
        if all(abs(p[0] - q[0]) + abs(p[1] - q[1]) + abs(p[2] - q[2]) > eps for q in out):
            out.append(p)
    return out


def cube_cut(x, y, z, plane):
    hits = []
    for a, b in EDGES:
        p0 = (x + a[0], y + a[1], z + a[2])
        p1 = (x + b[0], y + b[1], z + b[2])
        h = _hit(p0, p1, plane)
        if h:
            hits.append(h)
    hits = _uniq(hits)
    return hits if len(hits) >= 3 else []


def plane_basis(plane):
    a, b, c, _d = plane
    nlen = math.sqrt(a * a + b * b + c * c) or 1
    n = (a / nlen, b / nlen, c / nlen)
    tmp = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (tmp[1] * n[2] - tmp[2] * n[1], tmp[2] * n[0] - tmp[0] * n[2], tmp[0] * n[1] - tmp[1] * n[0])
    ul = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2) or 1
    u = (u[0] / ul, u[1] / ul, u[2] / ul)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
    return u, v


def project_to_plane(p, plane):
    a, b, c, d = plane
    nlen = math.sqrt(a * a + b * b + c * c) or 1
    n = (a / nlen, b / nlen, c / nlen)
    dist = (a * p[0] + b * p[1] + c * p[2] - d) / nlen
    return (p[0] - n[0] * dist, p[1] - n[1] * dist, p[2] - n[2] * dist)


def order_poly(pts, u, v, origin):
    def key(p):
        d = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
        return math.atan2(
            d[0] * v[0] + d[1] * v[1] + d[2] * v[2],
            d[0] * u[0] + d[1] * u[1] + d[2] * u[2],
        )

    return sorted(pts, key=key)


def to2d(p, origin, u, v):
    d = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    return (d[0] * u[0] + d[1] * u[1] + d[2] * u[2], -(d[0] * v[0] + d[1] * v[1] + d[2] * v[2]))


def q2(p, nd=4):
    return (round(p[0], nd), round(p[1], nd))


def border_edges(polys):
    counts: dict[tuple, int] = {}
    lookup: dict[tuple, tuple] = {}
    for poly in polys:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            e = tuple(sorted((q2(a), q2(b))))
            counts[e] = counts.get(e, 0) + 1
            lookup[e] = (a, b)
    return [lookup[e] for e, n in counts.items() if n == 1]


def plane_quad(voxels, plane, pad=0.55):
    u, v = plane_basis(plane)
    corners = voxel_corners(voxels)
    cx = sum(p[0] for p in corners) / len(corners)
    cy = sum(p[1] for p in corners) / len(corners)
    cz = sum(p[2] for p in corners) / len(corners)
    origin = project_to_plane((cx, cy, cz), plane)
    us, vs = [], []
    for p in corners:
        d = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
        us.append(d[0] * u[0] + d[1] * u[1] + d[2] * u[2])
        vs.append(d[0] * v[0] + d[1] * v[1] + d[2] * v[2])
    umin, umax = min(us) - pad, max(us) + pad
    vmin, vmax = min(vs) - pad, max(vs) + pad
    quad = []
    for uu, vv in ((umin, vmin), (umax, vmin), (umax, vmax), (umin, vmax)):
        quad.append((origin[0] + uu * u[0] + vv * v[0], origin[1] + uu * u[1] + vv * v[1], origin[2] + uu * u[2] + vv * v[2]))
    return quad, u, v, origin


def mid_plane(voxels, a=1.0, b=0.28, c=1.0):
    vals = [a * (x + 0.5) + b * (y + 0.5) + c * (z + 0.5) for x, y, z in voxels]
    return (a, b, c, (min(vals) + max(vals)) / 2)


def render_svg(voxels, plane, width=1100, height=560) -> tuple:
    voxels = set(map(tuple, voxels))
    u, v = plane_basis(plane)
    pieces = []
    hits = []
    for x, y, z in voxels:
        poly = cube_cut(x, y, z, plane)
        if poly:
            hits.extend(poly)
            pieces.append(poly)
    if not hits:
        raise SystemExit("plane misses the stack")
    ox0 = sum(p[0] for p in hits) / len(hits)
    oy0 = sum(p[1] for p in hits) / len(hits)
    oz0 = sum(p[2] for p in hits) / len(hits)
    origin = project_to_plane((ox0, oy0, oz0), plane)
    ordered = [order_poly(poly, u, v, origin) for poly in pieces]
    quad, _, _, _ = plane_quad(voxels, plane)
    extra = hits + quad
    left = (24, 56, 700, 430)
    ox, oy, sc = fit_iso(voxel_corners(voxels) + extra, left, pad=28)

    s = Svg(width, height)
    s.text((370, 40), "斜切截面", 26)
    draw_voxels(s, voxels, ox, oy, sc)
    q2d = [iso(*p, ox, oy, sc) for p in quad]
    for a, b in zip(q2d, q2d[1:] + q2d[:1]):
        s.line(a, b, 1.7, dash="7 6")
    screen = []
    for poly in ordered:
        pts = [iso(*p, ox, oy, sc) for p in poly]
        screen.append(pts)
        s.polygon(pts, fill="url(#hatch)", w=0)
    for a, b in border_edges(screen):
        s.line(a, b, 2.6, dash="11 7")

    s.rect(768, 70, 308, 400, fill=BG, sw=2.2)
    s.text((922, 108), "截面", 24)
    flat = [[to2d(p, origin, u, v) for p in poly] for poly in ordered]
    xs = [p[0] for poly in flat for p in poly]
    ys = [p[1] for poly in flat for p in poly]
    box = (798, 140, 248, 280)
    sc2 = min(box[2] / max(max(xs) - min(xs), 1e-6), box[3] / max(max(ys) - min(ys), 1e-6)) * 0.86
    cx = box[0] + box[2] / 2
    cy = box[1] + box[3] / 2
    mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    drawn = []
    for poly in flat:
        pts = [(cx + (p[0] - mx) * sc2, cy + (p[1] - my) * sc2) for p in poly]
        drawn.append(pts)
        s.polygon(pts, fill="url(#hatch)", w=0)
    for a, b in border_edges(drawn):
        s.line(a, b, 2.6)
    s.text((922, 508), "虚线为斜切面", 20)

    used3 = voxel_corners(voxels) + extra
    meta = {
        "ok": iso_inside(used3, ox, oy, sc, width, height, margin=3),
        "voxels": len(voxels),
        "cuts": len(ordered),
    }
    return s, meta


def draw(voxels, plane, dest: Path, width=1100, height=560) -> dict:
    s, meta = render_svg(voxels, plane, width, height)
    dest = Path(dest)
    s.write(dest.with_suffix(".svg"))
    svg_to_png(dest.with_suffix(".svg"), dest)
    return meta


def sample(seed: int = 21, n: int = 10):
    rng = random.Random(seed)
    voxels = grow_voxels(n, rng)
    return voxels, mid_plane(voxels)


if __name__ == "__main__":
    import sys

    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 21
    voxels, plane = sample(seed)
    dest = Path(f"/tmp/oblique-{seed}.png")
    print(seed, draw(voxels, plane, dest), dest)

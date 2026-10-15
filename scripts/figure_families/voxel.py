"""小正方体体素：旋转、规范化、旋转签名、拼装（精确覆盖），斜二测画法与可见性核对。

画法与六面体选项一致：屏幕 x = ox + s*(x + K*y)，屏幕 y = oy - s*(z + K*y)，看得见前、右、顶三面。
渲染用画家算法（按纵深从远到近填色）；核对用另一套办法——沿投影方向做射线求交，
算出每个采样点应该看到哪一面，再去 PNG 上取色比对。两边对不上就说明画错了。
"""

from __future__ import annotations

import math

from .core import SCALE, png_image
from .geom import ROTATIONS, apply

K = 0.42
FILL = {"top": "#e6e6e6", "front": "#ffffff", "right": "#c8c8c8"}
# PNG 灰度：白 255、顶 230、右 200。判题器按最近的灰度归类。
GRAY = {"front": 255, "top": 230, "right": 200}


def normalize(cells):
    cells = list(cells)
    lo = [min(c[i] for c in cells) for i in range(3)]
    return tuple(sorted(tuple(c[i] - lo[i] for i in range(3)) for c in cells))


_FAST = [tuple((next(j for j in range(3) if R[i][j]), R[i][next(j for j in range(3) if R[i][j])]) for i in range(3))
         for R in ROTATIONS]


def rotate(cells, R):
    return normalize(apply(R, c) for c in cells)


def _fast_forms(cells):
    cells = list(cells)
    out = set()
    for (p0, s0), (p1, s1), (p2, s2) in _FAST:
        pts = [(s0 * c[p0], s1 * c[p1], s2 * c[p2]) for c in cells]
        lx = min(q[0] for q in pts)
        ly = min(q[1] for q in pts)
        lz = min(q[2] for q in pts)
        out.add(tuple(sorted((q[0] - lx, q[1] - ly, q[2] - lz) for q in pts)))
    return out


def orientations(cells):
    return _fast_forms(cells)


def signature(cells):
    return min(orientations(cells))


def mirror(cells):
    return normalize((-x, y, z) for x, y, z in cells)


def neighbors(c):
    x, y, z = c
    return [(x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)]


def connected(cells):
    cells = set(cells)
    if not cells:
        return False
    seen, todo = set(), [next(iter(cells))]
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        todo.extend(n for n in neighbors(c) if n in cells and n not in seen)
    return seen == cells


def grow(rng, count, bound=None, start=(0, 0, 0)):
    shape = {start}
    while len(shape) < count:
        frontier = sorted({n for c in shape for n in neighbors(c)} - shape)
        if bound:
            frontier = [n for n in frontier if all(0 <= n[i] < bound[i] for i in range(3))]
        if not frontier:
            return None
        shape.add(rng.choice(frontier))
    return normalize(shape)


def placements(piece, target, rotations=True):
    """piece 的所有（旋转后）平移落在 target 内的摆法。"""
    target = set(target)
    forms = orientations(piece) if rotations else {normalize(piece)}
    out = set()
    for form in forms:
        anchor = form[0]
        for t in target:
            delta = tuple(t[i] - anchor[i] for i in range(3))
            placed = frozenset(tuple(c[i] + delta[i] for i in range(3)) for c in form)
            if placed <= target:
                out.add(placed)
    return list(out)


def pack(pieces, target, rotations=True):
    """能否用 pieces（各用一次，可旋转、不可镜像）恰好拼成 target。返回一种拼法或 None。

    精确覆盖：每一步取最小的空格，只试能盖住它的摆法，剪枝很快。
    """
    target = frozenset(target)
    if sum(len(p) for p in pieces) != len(target):
        return None
    cover = {c: [] for c in target}
    for i, piece in enumerate(pieces):
        for placed in placements(piece, target, rotations):
            for c in placed:
                cover[c].append((i, placed))
    order = sorted(target)

    def solve(used, pieces_used, chosen):
        if len(pieces_used) == len(pieces):
            return chosen if len(used) == len(target) else None
        cell = next(c for c in order if c not in used)
        for i, placed in cover[cell]:
            if i in pieces_used or placed & used:
                continue
            found = solve(used | placed, pieces_used | {i}, chosen + [(i, placed)])
            if found:
                return found
        return None

    return solve(frozenset(), frozenset(), [])


# ---------------------------------------------------------------- 画法
def bounds(cells):
    xs, ys, zs = zip(*cells)
    return (min(xs), max(xs) + 1), (min(ys), max(ys) + 1), (min(zs), max(zs) + 1)


def layout(cells, box_w, box_h, margin=10, s_max=48):
    """在 box_w×box_h 的格子里放下这个体素体，返回 (ox, oy, s)。"""
    (x0, x1), (y0, y1), (z0, z1) = bounds(cells)
    width = (x1 - x0) + K * (y1 - y0)
    height = (z1 - z0) + K * (y1 - y0)
    s = min(s_max, (box_w - 2 * margin) / width, (box_h - 2 * margin) / height)
    ox = (box_w - s * width) / 2 - s * (x0 + K * y0)
    oy = (box_h + s * height) / 2 + s * (z0 + K * y0)
    return ox, oy, s


def project(p, ox, oy, s):
    x, y, z = p
    return ox + s * (x + K * y), oy - s * (z + K * y)


def faces_of(cells):
    cells = set(cells)
    out = []
    for c in cells:
        x, y, z = c
        if (x, y - 1, z) not in cells:
            out.append((c, "front", [(x, y, z), (x + 1, y, z), (x + 1, y, z + 1), (x, y, z + 1)]))
        if (x + 1, y, z) not in cells:
            out.append((c, "right", [(x + 1, y, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x + 1, y, z + 1)]))
        if (x, y, z + 1) not in cells:
            out.append((c, "top", [(x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)]))
    return out


def draw(svg, cells, ox, oy, s, data=None, shift=(0, 0)):
    """画家算法：纵深 y - K*x - K*z 大的先画。每个面带 data-voxel 与 data-face。"""
    dx, dy = shift
    depth = lambda c: c[1] - K * c[0] - K * c[2]
    for c, kind, quad in sorted(faces_of(cells), key=lambda f: (-depth(f[0]), {"front": 2, "right": 0, "top": 1}[f[1]])):
        pts = [project(p, ox, oy, s) for p in quad]
        svg.poly([(x + dx, y + dy) for x, y in pts], closed=True, fill=FILL[kind], w=1.6,
                 data={**(data or {}), "voxel": f"{c[0]},{c[1]},{c[2]}", "vface": kind})


def ray_face(cells, px, pz):
    """沿投影方向找最先碰到的外露面：返回 (面类型, 体素, 离面边界的最小距离) 或 None。"""
    cells = set(cells)
    (x0, x1), (y0, y1), (z0, z1) = bounds(cells)
    best = None
    for j in range(y0, y1 + 1):  # 前面：y = j 的平面，属于体素 (., j, .)
        x, z = px - K * j, pz - K * j
        c = (math.floor(x), j, math.floor(z))
        if c in cells and (c[0], j - 1, c[2]) not in cells:
            edge = min(x - c[0], c[0] + 1 - x, z - c[2], c[2] + 1 - z)
            best = min(best, (j, "front", c, edge)) if best else (j, "front", c, edge)
    for i in range(x0, x1 + 1):  # 右面：x = i 的平面，属于体素 (i-1, ., .)
        t = (px - i) / K
        y, z = t, pz - K * t
        c = (i - 1, math.floor(y), math.floor(z))
        if c in cells and (i, c[1], c[2]) not in cells:
            edge = min(y - c[1], c[1] + 1 - y, z - c[2], c[2] + 1 - z)
            cand = (t, "right", c, edge)
            best = min(best, cand) if best else cand
    for k in range(z0, z1 + 1):  # 顶面：z = k 的平面，属于体素 (., ., k-1)
        t = (pz - k) / K
        x, y = px - K * t, t
        c = (math.floor(x), math.floor(y), k - 1)
        if c in cells and (c[0], c[1], k) not in cells:
            edge = min(x - c[0], c[0] + 1 - x, y - c[1], c[1] + 1 - y)
            cand = (t, "top", c, edge)
            best = min(best, cand) if best else cand
    return None if best is None else (best[1], best[2], best[3])


KINDS = ("front", "right", "top")


def hit_grid(cells, px, pz):
    """ray_face 的向量化版本：px、pz 是同形数组。返回 (面类型下标, x, y, z)，没碰到的面类型为 -1。"""
    import numpy as np

    (x0, x1), (y0, y1), (z0, z1) = bounds(cells)
    occ = np.zeros((x1 - x0 + 3, y1 - y0 + 3, z1 - z0 + 3), bool)
    for x, y, z in cells:
        occ[x - x0 + 1, y - y0 + 1, z - z0 + 1] = True

    def filled(ix, iy, iz):
        ix, iy, iz = ix - x0 + 1, iy - y0 + 1, iz - z0 + 1
        ok = (ix >= 0) & (ix < occ.shape[0]) & (iy >= 0) & (iy < occ.shape[1]) & (iz >= 0) & (iz < occ.shape[2])
        out = np.zeros(ix.shape, bool)
        out[ok] = occ[ix[ok], iy[ok], iz[ok]]
        return out

    best_t = np.full(px.shape, np.inf)
    kind = np.full(px.shape, -1)
    cx = np.zeros(px.shape, int)
    cy = np.zeros(px.shape, int)
    cz = np.zeros(px.shape, int)

    def take(t, k, ix, iy, iz, valid):
        better = valid & (t < best_t)
        best_t[better] = t[better] if np.ndim(t) else t
        kind[better] = k
        cx[better], cy[better], cz[better] = ix[better], iy[better], iz[better]

    for j in range(y0, y1 + 1):
        ix = np.floor(px - K * j).astype(int)
        iz = np.floor(pz - K * j).astype(int)
        iy = np.full(px.shape, j)
        take(np.full(px.shape, float(j)), 0, ix, iy, iz, filled(ix, iy, iz) & ~filled(ix, iy - 1, iz))
    for i in range(x0, x1 + 1):
        t = (px - i) / K
        iy = np.floor(t).astype(int)
        iz = np.floor(pz - K * t).astype(int)
        ix = np.full(px.shape, i - 1)
        take(t, 1, ix, iy, iz, filled(ix, iy, iz) & ~filled(ix + 1, iy, iz))
    for k in range(z0, z1 + 1):
        t = (pz - k) / K
        ix = np.floor(px - K * t).astype(int)
        iy = np.floor(t).astype(int)
        iz = np.full(px.shape, k - 1)
        take(t, 2, ix, iy, iz, filled(ix, iy, iz) & ~filled(ix, iy, iz + 1))
    return kind, cx, cy, cz


def _interior_hits(cells, ox, oy, s, step=3.0):
    """网格采样做射线求交；只留下周围 8 个邻点都落在同一个面上的点（避开所有棱线和遮挡边）。"""
    import numpy as np

    (x0, x1), (y0, y1), (z0, z1) = bounds(cells)
    left, right = ox + s * (x0 + K * y0), ox + s * (x1 + K * y1)
    top, bottom = oy - s * (z1 + K * y1), oy - s * (z0 + K * y0)
    xs = left + step * np.arange(int((right - left) / step) + 1)
    ys = top + step * np.arange(int((bottom - top) / step) + 1)
    SX, SY = np.meshgrid(xs, ys)
    kind, cx, cy, cz = hit_grid(cells, (SX - ox) / s, (oy - SY) / s)
    code = np.where(kind >= 0, ((kind * 64 + (cx + 8)) * 64 + (cy + 8)) * 64 + (cz + 8), -1)
    pad = np.pad(code, 1, constant_values=-2)
    same = np.ones(code.shape, bool)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            same &= pad[1 + di:1 + di + code.shape[0], 1 + dj:1 + dj + code.shape[1]] == code
    same &= kind >= 0
    for r, c in zip(*np.nonzero(same)):
        yield float(SX[r, c]), float(SY[r, c]), KINDS[kind[r, c]], (int(cx[r, c]), int(cy[r, c]), int(cz[r, c]))


def visible_counts(cells, s=40.0, step=3.0):
    """只看几何：每个小正方体有多少个内部采样点看得见（生成器挑摆法用）。"""
    cells = set(cells)
    seen = {c: 0 for c in cells}
    for _, _, _, cell in _interior_hits(cells, 0.0, 0.0, s, step):
        seen[cell] += 1
    return seen


def verify_drawing(png, cells, ox, oy, s, shift=(0, 0), step=3.0):
    """射线求交算出每个采样点该是哪一面，对 PNG 取色比对。返回 (问题列表, 每个体素可见的采样点数)。"""
    image = png_image(png)
    dx, dy = shift
    seen = {c: 0 for c in cells}
    wrong = total = 0
    for sx, sy, kind, cell in _interior_hits(set(cells), ox, oy, s, step):
        value = image.getpixel((int((sx + dx) * SCALE), int((sy + dy) * SCALE)))
        got = min(GRAY, key=lambda name: abs(GRAY[name] - value))
        total += 1
        if got != kind:
            wrong += 1
        else:
            seen[cell] += 1
    issues = []
    if total == 0:
        issues.append("立体图没有可采样的面")
    elif wrong > 2:  # 允许个别采样点碰巧压在抗锯齿像素上
        issues.append(f"立体图与体素对不上：{wrong}/{total} 个采样点颜色不符")
    return issues, seen

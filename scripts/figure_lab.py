#!/usr/bin/env python3
"""公考图样预览：统一黑白线稿 SVG。先画给肉眼看，不进题库。"""

from __future__ import annotations

import json
import math
from pathlib import Path

INK = "#111111"
BG = "#ffffff"
SW = 1.8
C30 = 3**0.5 / 2
S30 = 0.5
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "figure-lab"


def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Svg:
    def __init__(self, w=720, h=420):
        self.w, self.h = w, h
        self.buf: list[str] = [
            f'<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse">'
            f'<path d="M0 6 L6 0" stroke="{INK}" stroke-width="1"/></pattern>'
            f'<pattern id="hatch2" width="6" height="6" patternUnits="userSpaceOnUse">'
            f'<path d="M0 0 H6 M0 3 H6" stroke="{INK}" stroke-width="1"/></pattern>'
            f'<pattern id="dots" width="6" height="6" patternUnits="userSpaceOnUse">'
            f'<circle cx="2" cy="2" r="0.9" fill="{INK}"/></pattern></defs>'
        ]

    def add(self, chunk: str) -> None:
        self.buf.append(chunk)

    def line(self, a, b, w=SW, dash=None) -> None:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<line x1="{_n(a[0])}" y1="{_n(a[1])}" x2="{_n(b[0])}" y2="{_n(b[1])}" '
            f'stroke="{INK}" stroke-width="{w}" stroke-linecap="round"{extra}/>'
        )

    def polyline(self, pts, w=SW, close=False) -> None:
        d = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
        extra = f" {_n(pts[0][0])},{_n(pts[0][1])}" if close and pts else ""
        self.add(
            f'<polyline points="{d}{extra}" fill="none" stroke="{INK}" '
            f'stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    def polygon(self, pts, fill="none", w=SW) -> None:
        d = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
        self.add(
            f'<polygon points="{d}" fill="{fill}" stroke="{INK}" '
            f'stroke-width="{w}" stroke-linejoin="round"/>'
        )

    def circle(self, c, r, fill="none", w=SW) -> None:
        self.add(
            f'<circle cx="{_n(c[0])}" cy="{_n(c[1])}" r="{_n(r)}" fill="{fill}" '
            f'stroke="{INK}" stroke-width="{w}"/>'
        )

    def ellipse(self, c, rx, ry, fill="none", w=SW) -> None:
        self.add(
            f'<ellipse cx="{_n(c[0])}" cy="{_n(c[1])}" rx="{_n(rx)}" ry="{_n(ry)}" '
            f'fill="{fill}" stroke="{INK}" stroke-width="{w}"/>'
        )

    def rect(self, x, y, w, h, fill="none", sw=SW) -> None:
        self.add(
            f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" '
            f'fill="{fill}" stroke="{INK}" stroke-width="{sw}"/>'
        )

    def arrow(self, a, b, w=SW) -> None:
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L = (dx * dx + dy * dy) ** 0.5 or 1
        ux, uy = dx / L, dy / L
        self.line(a, b, w)
        self.polygon(
            [
                (bx, by),
                (bx - ux * 11 - uy * 6, by - uy * 11 + ux * 6),
                (bx - ux * 11 + uy * 6, by - uy * 11 - ux * 6),
            ],
            fill=INK,
            w=1,
        )

    def text(self, p, s, size=14, anchor="middle") -> None:
        safe = (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self.add(
            f'<text x="{_n(p[0])}" y="{_n(p[1])}" fill="{INK}" font-size="{size}" '
            f'text-anchor="{anchor}" font-family="Noto Sans CJK SC, Source Han Sans SC, sans-serif">'
            f"{safe}</text>"
        )

    def write(self, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(self.buf)
        dest.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">\n'
            f'<rect width="100%" height="100%" fill="{BG}"/>\n{body}\n</svg>\n',
            encoding="utf-8",
        )


def iso(x, y, z, ox, oy, s):
    return (ox + (x - y) * s * C30, oy + (x + y) * s * S30 - z * s)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def uv(quad, u, v):
    p00, p10, p11, p01 = quad
    return lerp(lerp(p00, p10, u), lerp(p01, p11, u), v)


def face_poly(s: Svg, quad, pts, fill="none") -> None:
    s.polygon([uv(quad, u, v) for u, v in pts], fill=fill)


def face_circle(s: Svg, quad, r=0.28) -> None:
    face_poly(s, quad, [(0.5 + r * math.cos(t), 0.5 + r * math.sin(t)) for t in [i * math.tau / 24 for i in range(24)]])


def face_plus(s: Svg, quad) -> None:
    s.polyline([uv(quad, 0.22, 0.5), uv(quad, 0.78, 0.5)])
    s.polyline([uv(quad, 0.5, 0.22), uv(quad, 0.5, 0.78)])


def face_x(s: Svg, quad) -> None:
    s.polyline([uv(quad, 0.25, 0.25), uv(quad, 0.75, 0.75)])
    s.polyline([uv(quad, 0.75, 0.25), uv(quad, 0.25, 0.75)])


def face_sq(s: Svg, quad, filled=False) -> None:
    face_poly(s, quad, [(0.3, 0.3), (0.7, 0.3), (0.7, 0.7), (0.3, 0.7)], fill=INK if filled else "none")


def face_pent(s: Svg, quad) -> None:
    face_poly(
        s,
        quad,
        [(0.5 + 0.3 * math.sin(i * math.tau / 5), 0.48 - 0.3 * math.cos(i * math.tau / 5)) for i in range(5)],
    )


def face_dia(s: Svg, quad) -> None:
    face_poly(s, quad, [(0.5, 0.22), (0.78, 0.5), (0.5, 0.78), (0.22, 0.5)])


MARK = {
    "circle": face_circle,
    "plus": face_plus,
    "x": face_x,
    "sq": face_sq,
    "pent": face_pent,
    "dia": face_dia,
}


def cube_faces(x, y, z, ox, oy, s):
    p = {(i, j, k): iso(x + i, y + j, z + k, ox, oy, s) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    # 相机沿 +x+y+z，可见的是 +z 顶、+x 右、+y 左。
    top = [p[0, 0, 1], p[1, 0, 1], p[1, 1, 1], p[0, 1, 1]]
    east = [p[1, 0, 0], p[1, 1, 0], p[1, 1, 1], p[1, 0, 1]]
    south = [p[0, 1, 0], p[1, 1, 0], p[1, 1, 1], p[0, 1, 1]]
    return {"top": top, "east": east, "south": south}


def draw_cube(s: Svg, ox, oy, size, marks: dict) -> None:
    faces = cube_faces(0, 0, 0, ox, oy, size)
    for name in ("south", "east", "top"):
        s.polygon(faces[name], fill=BG)
    for name, kind in marks.items():
        MARK[kind](s, faces[name])


def draw_voxels(s: Svg, voxels: set, ox, oy, size) -> None:
    occ = set(voxels)
    for x, y, z in sorted(occ, key=lambda t: (t[0] + t[1] + t[2])):
        faces = cube_faces(x, y, z, ox, oy, size)
        if (x, y + 1, z) not in occ:
            s.polygon(faces["south"], fill=BG)
        if (x + 1, y, z) not in occ:
            s.polygon(faces["east"], fill=BG)
        if (x, y, z + 1) not in occ:
            s.polygon(faces["top"], fill=BG)


# ---------- 资料 ----------
def fig_table() -> Svg:
    s = Svg(720, 320)
    s.text((360, 28), "表1  某市快递业务量", 16)
    rows = [["区域", "2024年", "2025年"], ["东部", "80.0", "96.0"], ["西部", "20.0", "28.0"], ["合计", "100.0", "124.0"]]
    x0, y0, cw, rh = 120, 50, 160, 52
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            s.rect(x0 + c * cw, y0 + r * rh, cw, rh)
            s.text((x0 + c * cw + cw / 2, y0 + r * rh + 34), cell, 15)
    s.text((360, 300), "单位：亿件", 12)
    return s


def fig_bars() -> Svg:
    s = Svg(720, 400)
    s.text((360, 28), "图1  业务量", 16)
    s.line((80, 340), (680, 340))
    s.line((80, 340), (80, 50))
    vals = [80, 96, 20, 28]
    labels = ["东24", "东25", "西24", "西25"]
    for i, (v, lab) in enumerate(zip(vals, labels)):
        h = v * 2.6
        x = 140 + i * 130
        s.rect(x, 340 - h, 70, h, fill="url(#hatch)" if i % 2 else BG)
        s.text((x + 35, 362), lab, 13)
        s.text((x + 35, 330 - h), str(v), 13)
    return s


def fig_line() -> Svg:
    s = Svg(720, 400)
    s.text((360, 28), "图2  同比增速", 16)
    s.line((80, 340), (680, 340))
    s.line((80, 340), (80, 50))
    pts = [(140, 220), (280, 160), (420, 190), (560, 120)]
    s.polyline(pts, 2.2)
    for p, lab in zip(pts, ["1月", "2月", "3月", "4月"]):
        s.circle(p, 4, fill=INK, w=1)
        s.text((p[0], 362), lab, 13)
    return s


def fig_pie() -> Svg:
    s = Svg(720, 400)
    s.text((360, 28), "图3  结构占比", 16)
    cx, cy, r = 280, 220, 120
    parts = [(0.45, "url(#hatch)"), (0.30, "url(#hatch2)"), (0.25, "url(#dots)")]
    a = -math.pi / 2
    for frac, fill in parts:
        b = a + frac * math.tau
        pts = [(cx, cy)]
        for i in range(24):
            t = a + (b - a) * i / 23
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
        s.polygon(pts, fill=fill)
        a = b
    s.circle((cx, cy), r, fill="none")
    for y, name, pat in ((140, "东部 45%", "url(#hatch)"), (200, "西部 30%", "url(#hatch2)"), (260, "其他 25%", "url(#dots)")):
        s.rect(480, y, 28, 20, fill=pat)
        s.text((530, y + 16), name, 14, "start")
    return s


def fig_combo() -> Svg:
    s = Svg(720, 400)
    s.text((360, 28), "图4  柱+折", 16)
    s.line((80, 340), (640, 340))
    s.line((80, 340), (80, 50))
    bars = [60, 80, 70, 90]
    line = [200, 160, 180, 120]
    for i, h in enumerate(bars):
        x = 140 + i * 130
        s.rect(x, 340 - h * 2.4, 50, h * 2.4)
    s.polyline([(165 + i * 130, line[i]) for i in range(4)], 2.2)
    for i, y in enumerate(line):
        s.circle((165 + i * 130, y), 4, fill=INK, w=1)
    return s


# ---------- 图推平面 ----------
def fig_faces() -> Svg:
    s = Svg(720, 280)
    boxes = [(40, 50), (190, 50), (340, 50), (490, 50)]
    for i, (x, y) in enumerate(boxes):
        s.rect(x, y, 140, 180)
        cx, cy = x + 70, y + 100
        if i == 0:
            s.circle((cx, cy), 40)
        elif i == 1:
            s.rect(x + 30, y + 50, 80, 100)
            s.line((cx, y + 50), (cx, y + 150))
        elif i == 2:
            s.polygon([(cx, y + 40), (x + 30, y + 160), (x + 110, y + 160)])
            s.line((cx, y + 40), (x + 55, y + 160))
            s.line((cx, y + 40), (x + 85, y + 160))
        else:
            s.text((cx, cy + 10), "?", 48)
    return s


def fig_arrows() -> Svg:
    s = Svg(720, 260)
    cells = [(50 + i * 130, 50) for i in range(5)]
    dirs = [(0, -1), (-1, 0), (0, 1), (1, 0)]
    for i, (x, y) in enumerate(cells):
        s.rect(x, y, 110, 160)
        if i == 4:
            s.text((x + 55, y + 95), "?", 40)
            continue
        dx, dy = dirs[i]
        cx, cy = x + 55 + dx * 22, y + 80 + dy * 22
        s.line((x + 55 - dx * 28, y + 80 - dy * 28), (cx, cy), 2.4)
        s.polygon(
            [
                (cx, cy),
                (cx - dx * 12 - dy * 7, cy - dy * 12 + dx * 7),
                (cx - dx * 12 + dy * 7, cy - dy * 12 - dx * 7),
            ],
            fill=INK,
        )
    return s


def fig_xor() -> Svg:
    s = Svg(720, 280)

    def cell(x, y, keys):
        s.rect(x, y, 120, 120)
        segs = {
            "N": ((x + 20, y + 20), (x + 100, y + 20)),
            "S": ((x + 20, y + 100), (x + 100, y + 100)),
            "W": ((x + 20, y + 20), (x + 20, y + 100)),
            "E": ((x + 100, y + 20), (x + 100, y + 100)),
            "V": ((x + 60, y + 20), (x + 60, y + 100)),
        }
        for k in keys:
            s.line(*segs[k])

    cell(60, 80, "NEWV")
    cell(220, 80, "NEV")
    cell(380, 80, "W")
    s.text((500, 150), "→", 28)
    s.rect(540, 80, 120, 120)
    s.text((600, 155), "?", 36)
    return s


def fig_symmetry() -> Svg:
    s = Svg(720, 300)
    s.rect(80, 40, 240, 220)
    s.polygon([(200, 70), (120, 220), (280, 220)])
    s.rect(400, 40, 240, 220)
    s.polygon([(450, 80), (610, 80), (580, 220), (430, 220)])
    s.text((200, 280), "轴对称", 14)
    s.text((520, 280), "中心对称", 14)
    return s


def fig_open_close() -> Svg:
    s = Svg(720, 260)
    s.circle((200, 130), 70)
    s.add(
        f'<path d="M470 80 A70 70 0 1 1 470 180" fill="none" stroke="{INK}" '
        f'stroke-width="{SW}" stroke-linecap="round"/>'
    )
    s.text((200, 240), "封闭", 14)
    s.text((500, 240), "开放", 14)
    return s


def fig_grid() -> Svg:
    s = Svg(640, 280)
    pattern = [
        "1100110011",
        "1000000001",
        "1011111101",
        "1010000101",
        "1010110101",
        "1010000101",
        "1011111101",
        "1000000001",
        "1100110011",
    ]
    x0, y0, a = 170, 20, 24
    for r, row in enumerate(pattern):
        for c, ch in enumerate(row):
            s.rect(x0 + c * a, y0 + r * a, a, a, fill=INK if ch == "1" else BG, sw=1)
    return s


# ---------- 空间 ----------
def fig_cube_net() -> Svg:
    s = Svg(640, 400)
    cell, ox, oy = 70, 150, 80
    places = {"pent": (1, 0), "circle": (0, 1), "plus": (1, 1), "dia": (2, 1), "x": (3, 1), "sq": (1, 2)}
    for kind, (c, r) in places.items():
        x, y = ox + c * cell, oy + r * cell
        s.rect(x, y, cell, cell)
        q = [(x, y), (x + cell, y), (x + cell, y + cell), (x, y + cell)]
        MARK[kind](s, q)
    return s


def fig_cube_iso() -> Svg:
    s = Svg(720, 360)
    draw_cube(s, 220, 230, 90, {"top": "pent", "south": "circle", "east": "x"})
    draw_cube(s, 520, 230, 90, {"top": "dia", "south": "plus", "east": "sq"})
    s.text((220, 340), "可见三面贴纸随面剪切", 13)
    s.text((520, 340), "另一取向", 13)
    return s


def fig_voxels() -> Svg:
    s = Svg(640, 400)
    voxels = {(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0)}
    draw_voxels(s, voxels, 320, 280, 52)
    return s


def draw_views_grids(s: Svg, left, front, top, left_h=None, front_h=None, top_h=None) -> None:
    cell, gap, y0 = 72, 88, 130
    blocks = (
        (70, left, left_h or set(), "左视图"),
        (70 + 3 * cell + gap, front, front_h or set(), "主视图"),
        (70 + 2 * (3 * cell + gap), top, top_h or set(), "俯视图"),
    )
    for x, cells, hatched, title in blocks:
        s.text((x + 1.5 * cell, y0 - 32), title, 36)
        for r in range(3):
            for c in range(3):
                key = (c, 2 - r)
                fill = "url(#hatch)" if key in hatched else INK if key in cells else BG
                s.rect(x + c * cell, y0 + r * cell, cell, cell, fill=fill, sw=2.6)


def fig_views() -> Svg:
    s = Svg(1100, 540)
    draw_views_grids(
        s,
        {(0, 0), (0, 1), (1, 0)},
        {(0, 0), (1, 0), (0, 1), (1, 1)},
        {(0, 0), (1, 0), (0, 1)},
        {(1, 0)},
        {(1, 1)},
        {(0, 1)},
    )
    return s


def fig_section() -> Svg:
    s = Svg(720, 380)
    voxels = {(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1)}
    draw_voxels(s, voxels, 200, 280, 48)
    cut = [iso(x, y, 0.5, 200, 280, 48) for x, y in ((0, 0), (2, 0), (2, 2), (0, 2))]
    s.polygon(cut, fill="url(#hatch)")
    s.rect(460, 80, 80, 80)
    s.line((460, 120), (540, 120), 1.6)
    s.line((500, 80), (500, 160), 1.6)
    s.text((500, 200), "水平截面", 22)
    return s


def fig_section_abc() -> Svg:
    s = Svg(720, 400)
    ox, oy, sc = 280, 300, 70
    # 长方体 2x1x1 + 前凸 0.5
    corners = {
        "A": iso(0, 0, 1, ox, oy, sc),
        "B": iso(2, 1, 1, ox, oy, sc),
        "C": iso(2, 0, 0, ox, oy, sc),
    }
    # box wire
    v = lambda x, y, z: iso(x, y, z, ox, oy, sc)
    edges = [
        ((0, 0, 0), (2, 0, 0)),
        ((2, 0, 0), (2, 1, 0)),
        ((2, 1, 0), (0, 1, 0)),
        ((0, 1, 0), (0, 0, 0)),
        ((0, 0, 1), (2, 0, 1)),
        ((2, 0, 1), (2, 1, 1)),
        ((2, 1, 1), (0, 1, 1)),
        ((0, 1, 1), (0, 0, 1)),
        ((0, 0, 0), (0, 0, 1)),
        ((2, 0, 0), (2, 0, 1)),
        ((2, 1, 0), (2, 1, 1)),
        ((0, 1, 0), (0, 1, 1)),
        ((0, 0, 0), (0.6, -0.5, 0)),
        ((0.6, -0.5, 0), (0.6, -0.5, 0.5)),
        ((0, 0, 0.5), (0.6, -0.5, 0.5)),
        ((0.6, -0.5, 0), (0.6, 0, 0)),
    ]
    for a, b in edges:
        s.line(v(*a), v(*b))
    s.polygon([corners["A"], corners["B"], corners["C"]], fill="url(#hatch)")
    for name, p in corners.items():
        s.circle(p, 3, fill=INK, w=1)
        s.text((p[0] - 12, p[1] - 8), name, 14)
    s.polygon([(560, 140), (680, 140), (700, 250), (540, 250)], fill="url(#hatch)")
    s.text((620, 290), "截面", 22)
    return s


# ---------- 科推 ----------
def fig_lever(fig=None) -> Svg:
    fig = fig or {}
    left_slot = int(fig.get("left_slot") or 2)
    left_n = int(fig.get("left_n") or 3)
    ticks = int(fig.get("ticks") or 5)
    s = Svg(1100, 500)
    ox, oy, span = 550, 300, 420
    s.line((ox - span, oy), (ox + span, oy), 4.2)
    s.polygon([(ox, oy + 10), (ox - 32, oy + 78), (ox + 32, oy + 78)], fill=BG, w=2.8)
    s.text((ox, oy + 120), "O", 28)
    step = span / ticks
    for i in range(1, ticks + 1):
        for sign in (-1, 1):
            x = ox + sign * i * step
            s.line((x, oy - 16), (x, oy + 16), 2.6)
            s.text((x, oy + 52), str(i), 22)
    xw = ox - left_slot * step
    for i in range(left_n):
        s.rect(xw - 24, oy - 40 - i * 42, 48, 38, fill=BG, sw=2.6)
    s.text((xw, oy - 48 - left_n * 42), f"{left_n}个钩码", 24)
    return s


def fig_circuit(fig=None) -> Svg:
    fig = fig or {}
    left = str(fig.get("left") or "L1")
    right = str(fig.get("right") or "L2")
    branch_meter = str(fig.get("meter") or ("A" if left.startswith("L") else "A1"))
    main_meter = str(fig.get("main_meter") or "")
    volt = fig.get("voltmeter")
    if volt is None:
        volt = left.startswith("L")
    s = Svg(1100, 560)

    def lamp(c, name):
        s.circle(c, 22, w=2.6)
        s.line((c[0] - 15, c[1] - 15), (c[0] + 15, c[1] + 15), 2.2)
        s.line((c[0] + 15, c[1] - 15), (c[0] - 15, c[1] + 15), 2.2)
        s.text((c[0], c[1] - 36), name, 24)

    def resistor(c, name):
        s.rect(c[0] - 28, c[1] - 18, 56, 36, sw=2.6)
        s.text((c[0], c[1] + 8), name, 24)

    def part(c, name):
        (lamp if str(name).startswith("L") else resistor)(c, name)

    def meter_box(c, name):
        s.circle(c, 24, w=2.6)
        s.text((c[0], c[1] + 8), name, 22)

    s.line((90, 80), (90, 460), 2.8)
    s.line((74, 210), (106, 210), 5)
    s.line((80, 236), (100, 236), 3.2)
    s.text((54, 200), "+", 22)
    s.line((90, 80), (272, 80), 2.8)
    s.circle((272, 80), 5, fill=INK, w=1)
    s.circle((312, 80), 5, fill=INK, w=1)
    s.line((272, 80), (306, 54), 2.8)
    s.text((292, 42), "S", 24)
    s.line((312, 80), (980, 80), 2.8)
    s.line((980, 80), (980, 460), 2.8)
    s.line((980, 460), (90, 460), 2.8)
    if main_meter:
        s.line((90, 460), (200, 460), 2.8)
        meter_box((256, 460), main_meter)
        s.line((282, 460), (980, 460), 2.8)
    s.line((480, 80), (480, 200), 2.8)
    meter_box((480, 222), branch_meter)
    s.line((480, 244), (480, 280), 2.8)
    part((480, 320), left)
    s.line((480, 344), (480, 460), 2.8)
    s.line((780, 80), (780, 280), 2.8)
    part((780, 320), right)
    s.line((780, 344), (780, 460), 2.8)
    if volt:
        s.line((90, 160), (200, 160), 2.4)
        s.rect(200, 136, 56, 48, sw=2.4)
        s.text((228, 168), "V", 24)
        s.line((228, 184), (228, 400), 2.4)
        s.line((228, 400), (90, 400), 2.4)
    return s


def _one_tank(s: Svg, cx: float, label: str, obj_name: str, state: str, cylinder: bool, water: float | None = None) -> None:
    rx, rim, floor = (150, 90, 450) if cylinder else (170, 80, 450)
    if water is None:
        water = 285 if state in {"suspend", "悬"} else 315
    if cylinder:
        s.line((cx - rx, rim + 16), (cx - rx, floor), 3.2)
        s.line((cx + rx, rim + 16), (cx + rx, floor), 3.2)
        s.ellipse((cx, rim + 16), rx, 22)
        s.polygon(
            [(cx - rx, water), (cx + rx, water), (cx + rx, floor), (cx - rx, floor)],
            fill="url(#hatch)",
        )
        s.ellipse((cx, water), rx, 18)
        s.ellipse((cx, floor), rx, 22)
    else:
        s.polyline([(cx - rx, 70), (cx - rx, floor), (cx + rx, floor), (cx + rx, 70)], 3.2)
        s.line((cx - rx, water), (cx + rx, water), 2.6)
        s.polygon(
            [(cx - rx, water), (cx + rx, water), (cx + rx, floor), (cx - rx, floor)],
            fill="url(#hatch)",
        )
    s.text((cx, 64), label or "薄壁容器", 26)
    if obj_name:
        if "球" in obj_name:
            if state in {"suspend", "悬"}:
                cy = water + 70
            elif state in {"sink", "沉", "底"}:
                cy = floor - 36
            else:
                cy = water - 8
            s.circle((cx, cy), 28, fill=BG, w=2.6)
            s.text((cx + 46, cy + 8), obj_name, 22, "start")
        elif state in {"sink", "沉", "底"}:
            s.rect(cx - 40, floor - 70, 80, 56, fill=INK, sw=2.6)
            s.text((cx, floor - 82), obj_name, 22)
        else:
            s.rect(cx - 40, water - 40, 80, 56, fill=BG, sw=2.6)
            s.text((cx, water - 52), obj_name, 22)


def fig_tank(fig=None) -> Svg:
    fig = fig or {}
    shape = str(fig.get("shape") or fig.get("vessel") or "cylinder").lower()
    cylinder = any(token in shape for token in ("cyl", "圆"))
    vessels = fig.get("vessels")
    if not vessels:
        names = [str(item) for item in (fig.get("names") or fig.get("labels") or []) if str(item)]
        if len(names) >= 2:
            vessels = [
                {"name": names[0], "object": "小球", "state": "float"},
                {"name": names[1], "object": "小球", "state": "suspend"},
            ]
        else:
            raw = fig.get("objects")
            if raw is None:
                objects = [{"name": "木块", "state": "float"}]
            else:
                objects = [item for item in raw if item]
            vessels = [{"name": "薄壁容器", "objects": objects}]
    s = Svg(1100 if len(vessels) > 1 else 1000, 540)
    s.line((80, 500), (s.w - 80, 500), 3.4)
    s.text((s.w / 2, 528), "水平桌面", 22)
    centers = [s.w / 2] if len(vessels) == 1 else [s.w * 0.30, s.w * 0.70]
    for vessel, cx in zip(vessels, centers):
        if not isinstance(vessel, dict):
            vessel = {"name": str(vessel)}
        objs = vessel.get("objects") or [
            {"name": vessel.get("object") or vessel.get("obj") or "", "state": vessel.get("state") or "float"}
        ]
        first = objs[0] if objs else {}
        name = first.get("name") if isinstance(first, dict) else str(first)
        state = first.get("state") if isinstance(first, dict) else "float"
        _one_tank(s, cx, str(vessel.get("name") or ""), str(name or ""), str(state or "float"), cylinder)
    return s


def fig_motion(fig=None) -> Svg:
    fig = fig or {}
    ylabel = str(fig.get("ylabel") or "s/m")
    xlabel = str(fig.get("xlabel") or "t/s")
    xmax = float(fig.get("xmax") or 4)
    ymax = float(fig.get("ymax") or 6)
    xticks = [float(x) for x in (fig.get("xticks") or [0, 1, 2, 3, 4])]
    yticks = [float(y) for y in (fig.get("yticks") or [0, 2, 3, 4, 6])]
    series = fig.get("series") or [
        {"name": "甲", "points": [[0, 6], [4, 0]]},
        {"name": "乙", "points": [[0, 0], [4, 6]]},
    ]
    s = Svg(1100, 620)
    ox, oy, width, height = 120, 540, 860, 440

    def xy(px: float, py: float) -> tuple[float, float]:
        return (ox + (px / xmax) * width, oy - (py / ymax) * height)

    s.line((ox, oy), (ox + width + 40, oy), 3.2)
    s.line((ox, oy), (ox, oy - height - 20), 3.2)
    s.text((ox - 8, oy - height - 28), ylabel, 26)
    s.text((ox + width + 56, oy + 28), xlabel, 26)
    for tick in xticks:
        x, _y = xy(tick, 0)
        s.line((x, oy), (x, oy + 10), 2.2)
        s.text((x, oy + 36), str(int(tick)) if tick == int(tick) else str(tick), 22)
    for tick in yticks:
        _x, y = xy(0, tick)
        s.line((ox - 10, y), (ox, y), 2.2)
        s.text((ox - 28, y + 8), str(int(tick)) if tick == int(tick) else str(tick), 22)
    index = 0
    for item in series:
        if not isinstance(item, dict):
            continue
        pts = [
            xy(float(p[0]), float(p[1]))
            for p in (item.get("points") or [])
            if isinstance(p, (list, tuple)) and len(p) >= 2
        ]
        if len(pts) < 2:
            continue
        s.polyline(pts, 3.2)
        a, b = pts[0], pts[1]
        lx = a[0] + (b[0] - a[0]) * 0.45
        ly = a[1] + (b[1] - a[1]) * 0.45 + (-32 if index == 0 else 36)
        s.text((lx, ly), str(item.get("name") or ""), 32)
        index += 1
    return s


def _contours(fn, x0, x1, y0, y1, nx, ny, levels):
    xs = [x0 + i * (x1 - x0) / nx for i in range(nx + 1)]
    ys = [y0 + j * (y1 - y0) / ny for j in range(ny + 1)]
    z = [[fn(xs[i], ys[j]) for i in range(nx + 1)] for j in range(ny + 1)]
    out = {lv: [] for lv in levels}
    for j in range(ny):
        for i in range(nx):
            corners = [(0, z[j][i]), (1, z[j][i + 1]), (2, z[j + 1][i + 1]), (3, z[j + 1][i])]
            pos = {
                0: (xs[i], ys[j]),
                1: (xs[i + 1], ys[j]),
                2: (xs[i + 1], ys[j + 1]),
                3: (xs[i], ys[j + 1]),
            }
            edges = ((0, 1), (1, 2), (2, 3), (3, 0))
            for lv in levels:
                hits = []
                for a, b in edges:
                    za, zb = corners[a][1], corners[b][1]
                    if (za - lv) * (zb - lv) > 0 or za == zb:
                        continue
                    t = (lv - za) / (zb - za)
                    pa, pb = pos[a], pos[b]
                    hits.append((pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t))
                if len(hits) >= 2:
                    out[lv].append((hits[0], hits[1]))
    return out


def fig_contour(fig=None) -> Svg:
    s = Svg(1080, 640)

    def f(x, y):
        return 12 * math.exp(-((x - 3.2) ** 2 + (y - 3.4) ** 2) / 3.2) + 8 * math.exp(
            -((x - 7.0) ** 2 + (y - 6.2) ** 2) / 2.8
        )

    def to_sc(p):
        return (70 + p[0] * 96, 560 - p[1] * 52)

    levels = [2, 4, 6, 8, 10]
    for lv, segs in _contours(f, 0.2, 9.8, 0.2, 9.2, 28, 24, levels).items():
        for a, b in segs:
            s.line(to_sc(a), to_sc(b), 2.2)
    s.polygon([to_sc((3.2, 3.4)), to_sc((3.5, 3.1)), to_sc((2.9, 3.1))], fill=INK)
    s.text(to_sc((3.2, 2.55)), "400", 28)
    s.text(to_sc((7.0, 6.55)), "200", 28)
    s.line(to_sc((5.05, 1.05)), to_sc((5.2, 8.15)), 3.6, dash="14 9")
    s.text(to_sc((5.85, 4.6)), "甲", 40)
    s.line(to_sc((3.2, 3.4)), to_sc((1.05, 7.35)), 3.6, dash="14 9")
    s.text(to_sc((1.45, 6.55)), "乙", 40)
    s.text((540, 618), "等高线（单位：m，等高距 50m）", 24)
    return s


def fig_front(fig=None) -> Svg:
    """冷/暖锋剖面：气团楔、锋面、雨区、推进箭头。禁止拿等高线顶替。"""
    fig = fig or {}
    warm = str(fig.get("front") or fig.get("type") or "cold").lower() in {"warm", "暖锋"}
    s = Svg(1100, 620)
    s.line((50, 500), (1050, 500), 3.4)
    if warm:
        # 暖锋：坡缓，暖气团从右向左爬升，雨区在锋前（冷气团一侧）
        s.polygon([(50, 500), (780, 500), (50, 280)], fill="url(#hatch)")
        s.line((50, 280), (780, 500), 3.6)
        for t in (0.25, 0.45, 0.65):
            x = 50 + (780 - 50) * t
            y = 280 + (500 - 280) * t
            s.circle((x + 18, y - 22), 14, fill=INK)
        s.arrow((920, 430), (760, 360), 3.0)
        s.arrow((880, 360), (720, 300), 3.0)
        s.arrow((200, 430), (80, 430), 3.0)
        for x, y in ((220, 200), (300, 230), (380, 260), (260, 250)):
            s.line((x, y), (x - 8, y + 22), 2.2)
        s.text((220, 400), "冷气团", 32)
        s.text((860, 240), "暖气团", 32)
        s.text((300, 180), "雨区", 28)
        s.text((550, 580), "锋面剖面示意图", 26)
    else:
        # 冷锋：坡陡，冷气团从左向右插入，雨区在锋后
        s.polygon([(50, 500), (640, 500), (210, 150)], fill="url(#hatch)")
        s.line((210, 150), (640, 500), 3.6)
        s.arrow((90, 430), (260, 430), 3.0)
        s.arrow((110, 350), (280, 350), 3.0)
        s.arrow((860, 220), (720, 160), 3.0)
        s.arrow((900, 300), (760, 220), 3.0)
        for x, y in ((280, 200), (340, 230), (400, 260), (310, 250)):
            s.line((x, y), (x + 6, y + 22), 2.2)
        s.text((250, 400), "冷气团", 32)
        s.text((820, 260), "暖气团", 32)
        s.text((360, 180), "雨区", 28)
        s.text((550, 580), "锋面剖面示意图", 26)
    return s


def fig_reflex(fig=None) -> Svg:
    """膝跳/缩手反射弧：解剖示意，只标①–⑤，不画传导箭头。"""
    fig = fig or {}
    s = Svg(1100, 560)
    s.ellipse((550, 210), 78, 120)
    s.ellipse((550, 210), 38, 72, fill="url(#hatch)")
    s.text((550, 72), "③", 32)
    s.circle((190, 410), 28)
    s.text((190, 468), "①", 32)
    s.line((214, 396), (490, 250), 2.8)
    s.circle((330, 338), 16)
    s.text((300, 300), "②", 32)
    s.line((610, 250), (880, 396), 2.8)
    s.text((780, 300), "④", 32)
    s.ellipse((920, 410), 52, 30)
    s.text((920, 468), "⑤", 32)
    s.text((550, 530), "反射弧", 26)
    return s


def fig_food(fig=None) -> Svg:
    fig = fig or {}
    raw = fig.get("nodes")
    if raw:
        nodes = []
        for item in raw:
            if isinstance(item, dict):
                nodes.append((str(item.get("name") or ""), float(item["x"]), float(item["y"])))
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                nodes.append((str(item[0]), float(item[1]), float(item[2])))
    else:
        nodes = [("草", 540, 90), ("兔", 280, 250), ("虫", 800, 250), ("狐", 280, 430), ("鸟", 800, 430)]
    edges = fig.get("edges") or ((0, 1), (0, 2), (1, 3), (2, 4), (1, 4))
    s = Svg(1080, max(560, int(max(y for _name, _x, y in nodes) + 90)))
    box_h = 68
    widths = []
    for name, x, y in nodes:
        box_w = max(120, 30 * len(name) + 40)
        widths.append(box_w)
        s.rect(x - box_w / 2, y - box_h / 2, box_w, box_h, sw=2.8)
        s.text((x, y + 10), name, 28)
    for a, b in edges:
        _n1, x1, y1 = nodes[int(a)]
        _n2, x2, y2 = nodes[int(b)]
        w1, w2 = widths[int(a)] / 2, widths[int(b)] / 2
        if abs(y2 - y1) < 30:
            sign = 1 if x2 > x1 else -1
            s.arrow((x1 + sign * w1, y1), (x2 - sign * w2, y2), 2.8)
        elif y2 > y1:
            s.arrow((x1, y1 + box_h / 2), (x2, y2 - box_h / 2), 2.8)
        else:
            s.arrow((x1, y1 - box_h / 2), (x2, y2 + box_h / 2), 2.8)
    return s


def fig_pedigree() -> Svg:
    s = Svg(640, 340)
    s.rect(160, 40, 36, 36)
    s.circle((300, 58), 18)
    s.line((196, 58), (282, 58))
    s.line((248, 58), (248, 120))
    s.line((180, 120), (420, 120))
    kids = [(180, True, False), (280, False, True), (380, True, True)]
    for x, male, aff in kids:
        s.line((x, 120), (x, 160))
        if male:
            s.rect(x - 18, 160, 36, 36, fill=INK if aff else BG)
        else:
            s.circle((x, 178), 18, fill=INK if aff else BG)
    s.text((320, 250), "方男圆女，实心为患者", 22)
    return s


def fig_pulley() -> Svg:
    s = Svg(640, 300)
    s.line((200, 40), (440, 40), 2.2)
    s.circle((260, 90), 28)
    s.circle((380, 90), 28)
    s.line((232, 90), (232, 200))
    s.line((408, 90), (408, 160))
    s.rect(210, 200, 44, 36)
    s.rect(388, 160, 40, 28)
    s.text((232, 256), "G", 14)
    s.text((408, 210), "F", 14)
    return s


def fig_nine() -> Svg:
    s = Svg(640, 420)
    glyphs = [
        lambda x, y: s.circle((x + 28, y + 28), 16),
        lambda x, y: (s.circle((x + 28, y + 28), 16), s.circle((x + 28, y + 28), 8)),
        lambda x, y: s.text((x + 28, y + 36), "?", 28),
        lambda x, y: s.polygon([(x + 28, y + 8), (x + 8, y + 48), (x + 48, y + 48)]),
        lambda x, y: (
            s.polygon([(x + 28, y + 8), (x + 8, y + 48), (x + 48, y + 48)]),
            s.line((x + 28, y + 8), (x + 28, y + 48)),
        ),
        lambda x, y: s.text((x + 28, y + 36), "?", 28),
        lambda x, y: s.rect(x + 10, y + 10, 36, 36),
        lambda x, y: (s.rect(x + 10, y + 10, 36, 36), s.line((x + 10, y + 28), (x + 46, y + 28))),
        lambda x, y: s.text((x + 28, y + 36), "?", 28),
    ]
    for i, draw in enumerate(glyphs):
        r, c = divmod(i, 3)
        x, y = 160 + c * 110, 40 + r * 110
        s.rect(x, y, 90, 90)
        draw(x + 17, y + 17)
    return s


def fig_bool() -> Svg:
    s = Svg(720, 280)

    def grid(x, y, cells, title):
        s.text((x + 48, y - 10), title, 13)
        for r in range(3):
            for c in range(3):
                s.rect(x + c * 32, y + r * 32, 32, 32, fill=INK if (r, c) in cells else BG, sw=1.3)

    a = {(0, 0), (0, 1), (1, 1), (2, 2)}
    b = {(0, 1), (1, 1), (1, 2), (2, 0)}
    grid(50, 70, a, "图1")
    grid(200, 70, b, "图2")
    grid(350, 70, a & b, "求同")
    grid(500, 70, a ^ b, "求异")
    return s


def fig_stroke() -> Svg:
    s = Svg(720, 260)
    s.polyline([(80, 80), (160, 80), (160, 180), (80, 180)])
    s.polyline([(250, 70), (250, 190), (340, 190), (340, 70)])
    s.polygon([(430, 70), (510, 70), (510, 190), (430, 190)])
    s.text((620, 150), "?", 36)
    s.text((120, 230), "一笔", 13)
    s.text((295, 230), "一笔", 13)
    s.text((470, 230), "两笔", 13)
    return s


def fig_curve() -> Svg:
    s = Svg(720, 240)
    s.polygon([(80, 50), (200, 50), (200, 190), (80, 190)])
    s.add(
        f'<path d="M280 190 C280 70 420 70 420 190" fill="none" stroke="{INK}" '
        f'stroke-width="{SW}"/>'
    )
    s.polygon([(500, 50), (620, 50), (620, 190), (500, 190)])
    s.add(
        f'<path d="M520 80 Q560 140 600 80" fill="none" stroke="{INK}" stroke-width="{SW}"/>'
    )
    s.text((140, 220), "直线", 13)
    s.text((350, 220), "曲线", 13)
    s.text((560, 220), "曲直混合", 13)
    return s


def fig_dots() -> Svg:
    s = Svg(720, 240)
    s.polygon([(90, 50), (210, 50), (210, 180), (90, 180)])
    s.circle((150, 115), 4, fill=INK, w=1)
    s.polygon([(280, 50), (420, 50), (350, 180)])
    s.circle((320, 90), 4, fill=INK, w=1)
    s.circle((380, 90), 4, fill=INK, w=1)
    s.circle((350, 150), 4, fill=INK, w=1)
    s.rect(500, 50, 140, 130)
    s.line((500, 115), (640, 115))
    s.line((570, 50), (570, 180))
    s.circle((535, 82), 4, fill=INK, w=1)
    s.circle((605, 82), 4, fill=INK, w=1)
    s.circle((535, 148), 4, fill=INK, w=1)
    s.circle((605, 148), 4, fill=INK, w=1)
    s.text((150, 220), "1 点", 13)
    s.text((350, 220), "3 点", 13)
    s.text((570, 220), "4 点", 13)
    return s


def fig_tetra() -> Svg:
    s = Svg(640, 360)
    a = 110
    h = a * (3 ** 0.5) / 2
    cx, y0 = 320, 46
    faces = [
        [(cx, y0), (cx - a / 2, y0 + h), (cx + a / 2, y0 + h)],
        [(cx - a / 2, y0 + h), (cx - a, y0 + 2 * h), (cx, y0 + 2 * h)],
        [(cx - a / 2, y0 + h), (cx + a / 2, y0 + h), (cx, y0 + 2 * h)],
        [(cx + a / 2, y0 + h), (cx, y0 + 2 * h), (cx + a, y0 + 2 * h)],
    ]
    for poly, kind in zip(faces, ("circle", "plus", "x", "sq")):
        s.polygon(poly)
        gx = sum(p[0] for p in poly) / 3
        gy = sum(p[1] for p in poly) / 3
        MARK[kind](s, [(gx - 16, gy - 16), (gx + 16, gy - 16), (gx + 16, gy + 16), (gx - 16, gy + 16)])
    s.text((320, 340), "四面体展开", 13)
    return s


def fig_solid() -> Svg:
    s = Svg(720, 340)
    # 圆柱：上下椭圆 + 侧棱
    top = [(180 + 70 * math.cos(t), 90 + 22 * math.sin(t)) for t in [i * math.tau / 32 for i in range(33)]]
    bot = [(180 + 70 * math.cos(t), 230 + 22 * math.sin(t)) for t in [i * math.tau / 32 for i in range(33)]]
    s.polyline(top)
    s.polyline(bot)
    s.line((110, 90), (110, 230))
    s.line((250, 90), (250, 230))
    # 圆锥
    s.polyline([(500 + 80 * math.cos(t), 240 + 24 * math.sin(t)) for t in [i * math.tau / 32 for i in range(33)]])
    s.line((500, 70), (420, 240))
    s.line((500, 70), (580, 240))
    s.text((180, 310), "圆柱", 13)
    s.text((500, 310), "圆锥", 13)
    return s


def fig_hanzi() -> Svg:
    s = Svg(720, 240)
    for i, ch in enumerate("日田回"):
        s.rect(40 + i * 170, 40, 140, 140)
        s.text((110 + i * 170, 130), ch, 64)
    s.rect(40 + 3 * 170, 40, 140, 140)
    s.text((110 + 3 * 170, 130), "?", 48)
    return s


def fig_clock() -> Svg:
    s = Svg(720, 260)
    for i, hm in enumerate(((3, 0), (6, 15), (9, 30), None)):
        cx, cy = 90 + i * 180, 130
        s.circle((cx, cy), 50)
        s.circle((cx, cy), 3, fill=INK, w=1)
        if hm is None:
            s.text((cx, cy + 10), "?", 28)
            continue
        h, m = hm
        ha = math.radians(h * 30 - 90)
        ma = math.radians(m * 6 - 90)
        s.line((cx, cy), (cx + 22 * math.cos(ha), cy + 22 * math.sin(ha)), 2.4)
        s.line((cx, cy), (cx + 36 * math.cos(ma), cy + 36 * math.sin(ma)), 1.6)
    return s


def fig_func() -> Svg:
    s = Svg(720, 240)
    boxes = [(50, 50), (220, 50), (390, 50), (560, 50)]
    for i, (x, y) in enumerate(boxes[:3]):
        s.rect(x, y, 120, 140)
        s.polygon([(x + 20, y + 40), (x + 100, y + 40), (x + 60, y + 110)])
        px = x + 30 + i * 30
        s.circle((px, y + 70), 5, fill=INK, w=1)
    s.rect(boxes[3][0], boxes[3][1], 120, 140)
    s.text((boxes[3][0] + 60, 130), "?", 28)
    return s


def fig_cube_views() -> Svg:
    s = Svg(720, 360)
    marks = [
        {"south": "circle", "east": "x", "top": "pent"},
        {"south": "x", "east": "sq", "top": "circle"},
        {"south": "pent", "east": "circle", "top": "plus"},
    ]
    for i, m in enumerate(marks):
        draw_cube(s, 140 + i * 220, 230, 72, m)
        s.text((140 + i * 220, 340), f"取向 {i + 1}", 13)
    return s


def fig_hidden() -> Svg:
    s = Svg(640, 380)
    voxels = {(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 2), (1, 0, 1)}
    draw_voxels(s, voxels, 300, 280, 46)
    s.text((320, 360), "计数：可见 + 被挡", 13)
    return s


def fig_lblock() -> Svg:
    s = Svg(720, 360)
    a = {(0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 0, 1)}
    b = {(0, 0, 0), (0, 1, 0), (0, 2, 0), (0, 2, 1)}
    draw_voxels(s, a, 180, 250, 48)
    draw_voxels(s, b, 500, 250, 48)
    s.text((180, 340), "L 形", 13)
    s.text((500, 340), "旋转后", 13)
    return s


def fig_lens() -> Svg:
    s = Svg(720, 280)
    s.line((80, 140), (640, 140), 1.2)
    s.add(
        f'<path d="M300 50 C360 50 360 230 300 230 C340 180 340 100 300 50" fill="none" '
        f'stroke="{INK}" stroke-width="{SW}"/>'
    )
    s.arrow((120, 90), (300, 90))
    s.line((300, 90), (520, 200))
    s.arrow((120, 190), (300, 190))
    s.line((300, 190), (520, 80))
    s.circle((420, 140), 3, fill=INK, w=1)
    s.text((420, 128), "F", 12)
    return s


def fig_vessels() -> Svg:
    s = Svg(720, 300)
    s.polyline([(80, 80), (80, 240), (200, 240), (200, 160), (320, 160), (320, 240), (440, 240), (440, 80)], 2.2)
    s.line((80, 180), (200, 180))
    s.line((320, 180), (440, 180))
    s.polygon([(80, 180), (200, 180), (200, 240), (80, 240)], fill="url(#hatch)")
    s.polygon([(320, 180), (440, 180), (440, 240), (320, 240)], fill="url(#hatch)")
    s.text((360, 280), "连通器，液面等高", 13)
    return s


def fig_buoy() -> Svg:
    s = Svg(640, 320)
    s.polyline([(160, 60), (160, 280), (480, 280), (480, 60)], 2.2)
    s.line((160, 200), (480, 200))
    s.polygon([(160, 200), (480, 200), (480, 280), (160, 280)], fill="url(#hatch)")
    s.rect(270, 140, 100, 90)
    s.line((160, 200), (480, 200), 1.2)
    s.text((320, 130), "物块", 13)
    return s


def fig_force() -> Svg:
    s = Svg(640, 300)
    s.rect(270, 140, 100, 70)
    s.arrow((320, 140), (320, 60))
    s.arrow((320, 210), (320, 270))
    s.arrow((270, 175), (190, 175))
    s.arrow((370, 175), (450, 175))
    s.text((332, 52), "N", 13)
    s.text((332, 286), "G", 13)
    s.text((180, 168), "f", 13)
    s.text((460, 168), "F", 13)
    return s


def fig_spring() -> Svg:
    s = Svg(640, 240)
    s.line((80, 80), (200, 80), 2)
    zig = [(200, 80)]
    for i in range(8):
        zig.append((220 + i * 18, 50 if i % 2 == 0 else 110))
    zig.append((370, 80))
    s.polyline(zig, 2)
    s.rect(370, 55, 50, 50)
    s.arrow((500, 80), (430, 80))
    s.text((520, 86), "F", 14)
    return s


def fig_gears() -> Svg:
    s = Svg(640, 300)

    def gear(c, r, n):
        s.circle(c, r)
        s.circle(c, 8, fill=INK, w=1)
        for i in range(n):
            t = i * math.tau / n
            s.line(
                (c[0] + r * math.cos(t), c[1] + r * math.sin(t)),
                (c[0] + (r + 10) * math.cos(t), c[1] + (r + 10) * math.sin(t)),
                2,
            )

    gear((220, 150), 56, 12)
    gear((400, 150), 40, 8)
    s.arrow((140, 150), (160, 150))
    s.text((220, 250), "主动", 13)
    s.text((400, 250), "从动", 13)
    return s


def fig_mirror() -> Svg:
    s = Svg(640, 280)
    s.line((320, 40), (320, 240), 2.2)
    for y in range(50, 240, 16):
        s.line((320, y), (308, y + 10), 1)
    s.arrow((120, 80), (318, 140))
    s.arrow((318, 140), (140, 210))
    s.text((200, 70), "入射", 12)
    s.text((200, 230), "反射", 12)
    return s


def fig_st(fig=None) -> Svg:
    payload = dict(fig or {})
    payload.setdefault("ylabel", "s/m")
    return fig_motion(payload)


def fig_stackbar() -> Svg:
    s = Svg(720, 400)
    s.text((360, 28), "堆积柱状图", 16)
    s.line((80, 340), (680, 340))
    s.line((80, 340), (80, 50))
    lows = [40, 55, 35, 60]
    highs = [30, 25, 40, 20]
    for i, (lo, hi) in enumerate(zip(lows, highs)):
        x = 140 + i * 130
        s.rect(x, 340 - lo * 2.4, 70, lo * 2.4)
        s.rect(x, 340 - (lo + hi) * 2.4, 70, hi * 2.4, fill="url(#hatch)")
        s.text((x + 35, 362), f"{i + 1}月", 13)
    s.rect(500, 70, 18, 14)
    s.text((530, 82), "东部", 12, "start")
    s.rect(500, 96, 18, 14, fill="url(#hatch)")
    s.text((530, 108), "西部", 12, "start")
    return s


def fig_donut() -> Svg:
    s = Svg(640, 360)
    s.text((320, 28), "环形图", 16)
    cx, cy, r, ri = 250, 200, 110, 55
    parts = [(0.5, "url(#hatch)"), (0.3, "url(#hatch2)"), (0.2, "url(#dots)")]
    a = -math.pi / 2
    for frac, fill in parts:
        b = a + frac * math.tau
        pts = []
        for i in range(20):
            t = a + (b - a) * i / 19
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
        for i in range(20):
            t = b - (b - a) * i / 19
            pts.append((cx + ri * math.cos(t), cy + ri * math.sin(t)))
        s.polygon(pts, fill=fill)
        a = b
    s.circle((cx, cy), r)
    s.circle((cx, cy), ri, fill=BG)
    s.text((250, 206), "100", 16)
    s.text((480, 160), "A 50%", 14, "start")
    s.text((480, 200), "B 30%", 14, "start")
    s.text((480, 240), "C 20%", 14, "start")
    return s


def fig_venn() -> Svg:
    s = Svg(640, 340)
    s.circle((250, 170), 90)
    s.circle((350, 170), 90)
    s.text((210, 174), "A", 16)
    s.text((390, 174), "B", 16)
    s.text((300, 174), "A∩B", 13)
    s.text((320, 310), "容斥 / 韦恩图", 13)
    return s


def fig_circle_tan() -> Svg:
    s = Svg(640, 340)
    s.circle((260, 180), 80)
    s.line((80, 300), (560, 80))
    s.line((260, 180), (200, 250))
    s.rect(194, 244, 14, 14)
    s.text((260, 168), "O", 13)
    s.text((190, 270), "切点", 12)
    return s


def fig_meet() -> Svg:
    s = Svg(720, 220)
    s.line((80, 110), (640, 110), 2)
    s.circle((140, 110), 8)
    s.circle((560, 110), 8)
    s.arrow((160, 80), (300, 80))
    s.arrow((540, 150), (400, 150))
    s.text((140, 150), "甲", 13)
    s.text((560, 80), "乙", 13)
    s.text((360, 190), "相遇 / 追及示意", 13)
    return s


def fig_similar() -> Svg:
    s = Svg(640, 340)
    s.polygon([(80, 300), (560, 300), (320, 50)])
    s.line((200, 200), (440, 200))
    s.text((70, 318), "A", 13)
    s.text((570, 318), "B", 13)
    s.text((320, 40), "C", 13)
    s.text((320, 220), "DE ∥ AB", 12)
    return s


# ---------- 数量 ----------
def fig_triangle() -> Svg:
    s = Svg(640, 340)
    a, b, c = (140, 280), (500, 280), (280, 70)
    s.polygon([a, b, c])
    d = (280, 280)
    s.line(c, d)
    s.rect(d[0], d[1] - 16, 16, 16)
    s.text((130, 300), "A", 14)
    s.text((510, 300), "B", 14)
    s.text((280, 58), "C", 14)
    s.text((300, 300), "D", 14)
    return s


def fig_box() -> Svg:
    s = Svg(640, 340)
    ox, oy, sc = 300, 250, 80
    v = lambda x, y, z: iso(x, y, z, ox, oy, sc)
    for a, b in [
        ((0, 0, 0), (2, 0, 0)),
        ((2, 0, 0), (2, 1, 0)),
        ((2, 1, 0), (0, 1, 0)),
        ((0, 1, 0), (0, 0, 0)),
        ((0, 0, 1), (2, 0, 1)),
        ((2, 0, 1), (2, 1, 1)),
        ((2, 1, 1), (0, 1, 1)),
        ((0, 1, 1), (0, 0, 1)),
        ((0, 0, 0), (0, 0, 1)),
        ((2, 0, 0), (2, 0, 1)),
        ((2, 1, 0), (2, 1, 1)),
        ((0, 1, 0), (0, 1, 1)),
    ]:
        s.line(v(*a), v(*b))
    return s


CATALOG = [
    ("资料分析", "table", "统计表", fig_table),
    ("资料分析", "bars", "柱状图", fig_bars),
    ("资料分析", "line", "折线图", fig_line),
    ("资料分析", "pie", "饼图（剖面线）", fig_pie),
    ("资料分析", "combo", "柱折复合", fig_combo),
    ("资料分析", "stackbar", "堆积柱状图", fig_stackbar),
    ("资料分析", "donut", "环形图", fig_donut),
    ("图形推理", "faces", "封闭面", fig_faces),
    ("图形推理", "arrows", "箭头平移旋转", fig_arrows),
    ("图形推理", "xor", "去同存异", fig_xor),
    ("图形推理", "symmetry", "对称性", fig_symmetry),
    ("图形推理", "open_close", "开闭性", fig_open_close),
    ("图形推理", "grid", "黑白宫格", fig_grid),
    ("图形推理", "nine", "九宫格", fig_nine),
    ("图形推理", "bool", "黑白运算", fig_bool),
    ("图形推理", "stroke", "一笔画", fig_stroke),
    ("图形推理", "curve", "曲直性", fig_curve),
    ("图形推理", "dots", "点线面", fig_dots),
    ("图形推理", "hanzi", "汉字笔画", fig_hanzi),
    ("图形推理", "clock", "时钟指针", fig_clock),
    ("图形推理", "func", "功能元素", fig_func),
    ("图形推理", "cube_net", "六面体展开图", fig_cube_net),
    ("图形推理", "cube_iso", "六面体立体（贴纸随面）", fig_cube_iso),
    ("图形推理", "voxels", "小方块堆叠", fig_voxels),
    ("图形推理", "views", "三视图色块", fig_views),
    ("图形推理", "section", "水平截面", fig_section),
    ("图形推理", "section_abc", "过三点截面", fig_section_abc),
    ("图形推理", "cube_views", "同一立方体多取向", fig_cube_views),
    ("图形推理", "hidden", "隐藏方块计数", fig_hidden),
    ("图形推理", "lblock", "L 形积木旋转", fig_lblock),
    ("图形推理", "tetra", "四面体展开", fig_tetra),
    ("图形推理", "solid", "圆柱圆锥", fig_solid),
    ("科学推理", "lever", "杠杆", fig_lever),
    ("科学推理", "pulley", "滑轮", fig_pulley),
    ("科学推理", "circuit", "串并联电路", fig_circuit),
    ("科学推理", "tank", "容器液面", fig_tank),
    ("科学推理", "motion", "v-t 图像", fig_motion),
    ("科学推理", "contour", "等高线", fig_contour),
    ("科学推理", "front", "锋面剖面", fig_front),
    ("科学推理", "food", "食物网", fig_food),
    ("科学推理", "reflex", "反射弧", fig_reflex),
    ("科学推理", "pedigree", "遗传系谱", fig_pedigree),
    ("科学推理", "lens", "凸透镜光路", fig_lens),
    ("科学推理", "vessels", "连通器", fig_vessels),
    ("科学推理", "buoy", "浮力", fig_buoy),
    ("科学推理", "force", "受力分析", fig_force),
    ("科学推理", "spring", "弹簧", fig_spring),
    ("科学推理", "gears", "齿轮传动", fig_gears),
    ("科学推理", "mirror", "平面镜反射", fig_mirror),
    ("科学推理", "st", "s-t 图像", fig_st),
    ("数量关系", "triangle", "平面几何", fig_triangle),
    ("数量关系", "box", "立体几何线框", fig_box),
    ("数量关系", "venn", "韦恩图", fig_venn),
    ("数量关系", "circle_tan", "圆与切线", fig_circle_tan),
    ("数量关系", "meet", "行程示意", fig_meet),
    ("数量关系", "similar", "相似三角形", fig_similar),
]


def build(dest: Path = OUT) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list] = {}
    for group, key, title, fn in CATALOG:
        svg = fn()
        name = f"{key}.svg"
        svg.write(dest / name)
        groups.setdefault(group, []).append({"id": key, "title": title, "file": name})
    catalog = {
        "style": "black-white-line",
        "groups": [{"id": name, "title": name, "items": items} for name, items in groups.items()],
    }
    (dest / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog


if __name__ == "__main__":
    data = build()
    n = sum(len(g["items"]) for g in data["groups"])
    print(f"wrote {n} figures → {OUT}")

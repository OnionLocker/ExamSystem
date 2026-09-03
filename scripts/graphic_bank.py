#!/usr/bin/env python3
"""确定性图推：先算答案再画图。不走 Gemini 出像素。"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from image_kinds import GRAPHIC_KIND_BY_MOVE

INK = (20, 20, 20)
GRAY = (120, 120, 120)
LIGHT = (245, 245, 245)
MID = (150, 158, 168)
DARK = (70, 76, 84)
BG = (255, 255, 255)
DASH = (80, 80, 80)

STEM_LAW = "从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性："
STEM_CLASS = "把下面的六个图形分为两类，使每一类图形都有各自的共同特征或规律，分类正确的一项是："
STEM_NET = "左边给定的是纸盒的外表面展开图，右边哪一项能由它折叠而成？"
STEM_CUT = "左图为小立方体堆成的立体图形，沿虚线所示平面切开，正确的截面是："
STEM_VIEW = "左图为小立方体堆成的立体图形，其正确的俯视图是："
STEM_FRONT = "左图为小立方体堆成的立体图形，其正确的主视图是："

# 只用 90° 对称贴纸，折叠后不用追箭头朝向
MARK_SETS = (
    {"1": "dot", "2": "plus", "3": "ring", "4": "x", "5": "sq", "6": "fill"},
    {"1": "plus", "2": "x", "3": "fill", "4": "dot", "5": "ring", "6": "sq"},
    {"1": "ring", "2": "dot", "3": "sq", "4": "plus", "5": "fill", "6": "x"},
    {"1": "sq", "2": "fill", "3": "dot", "4": "ring", "5": "x", "6": "plus"},
)

# 展开图：中间 1–4，上 5 下 6。相对面 1↔3、2↔4、5↔6。
# 默认折完：2 前(-Y)、3 右(+X)、5 上(+Z)。可见三面要满足 south×east=top。
NET_CORRECT = (
    {"south": "2", "top": "5", "east": "3"},
    {"south": "3", "top": "5", "east": "4"},
    {"south": "2", "top": "6", "east": "1"},
    {"south": "4", "top": "5", "east": "1"},
)

FACE_DIR = {
    "1": (-1, 0, 0),
    "3": (1, 0, 0),
    "2": (0, -1, 0),
    "4": (0, 1, 0),
    "5": (0, 0, 1),
    "6": (0, 0, -1),
}

STEM_NETS = (
    "左边给定的是纸盒的外表面展开图，右边哪一项能由它折叠而成？",
    "下图是正方体纸盒的外表面展开图，折叠后可以得到的是：",
    "将左边的展开图折成正方体，正确的一项是：",
    "左边为立方体的展开图，折叠成正方体后对应正确的是：",
)
STEM_CUTS = (
    "左图为小立方体堆成的立体图形，沿虚线所示平面切开，正确的截面是：",
    "下图立体由小正方体堆成，虚线平面截出的图形是：",
    "沿立体图中虚线平面切开，所得截面是：",
)
STEM_TOPS = (
    "左图为小立方体堆成的立体图形，其正确的俯视图是：",
    "下图立体由小正方体堆成，从正上方看到的图形是：",
    "左图立体的俯视图是：",
)
STEM_FRONTS = (
    "左图为小立方体堆成的立体图形，其正确的主视图是：",
    "下图立体由小正方体堆成，从正面看到的图形是：",
    "左图立体的主视图是：",
)

SECTION_RECIPES = (
    {
        "voxels": {(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1)},
        "plane": "z=0.5",
        "note": "虚线水平穿过底层四块，截面是 2×2 正方形",
    },
    {
        "voxels": {(0, 0, 0), (1, 0, 0), (0, 1, 0)},
        "plane": "z=0.5",
        "note": "虚线水平穿过底层 L 形三块，截面是 L 形",
    },
    {
        "voxels": {(0, 0, 0), (1, 0, 0), (0, 0, 1), (1, 0, 1)},
        "plane": "z=0.5",
        "note": "虚线水平穿过一堵两块宽的墙，截面是 1×2 矩形",
    },
)

VIEW_RECIPES = (
    {"voxels": {(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)}, "mode": "top", "note": "俯视占格为左前、右前、左后"},
    {"voxels": {(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 1)}, "mode": "top", "note": "俯视占格为左前、右前、右后"},
    {"voxels": {(0, 0, 0), (1, 0, 0), (0, 0, 1)}, "mode": "front", "note": "主视看 y=0 面：左一格高 2、右一格高 1"},
)


def _font(size: int):
    for name in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        path = Path(name)
        if not path.is_file():
            continue
        if path.suffix == ".ttc":
            for index in (0, 1, 2):
                try:
                    return ImageFont.truetype(str(path), size, index=index)
                except OSError:
                    continue
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _canvas(w=1100, h=720):
    im = Image.new("RGB", (w, h), BG)
    return im, ImageDraw.Draw(im)


def _box(draw, xy, label=""):
    x, y, w, h = xy
    draw.rectangle((x, y, x + w, y + h), outline=INK, width=2)
    if label:
        draw.text((x + 6, y + 4), label, fill=GRAY, font=_font(16))


def _poly(draw, pts, width=3, fill=None):
    if fill:
        draw.polygon(pts, fill=fill, outline=INK)
    else:
        draw.line(pts + [pts[0]], fill=INK, width=width)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def valid_visible_triple(south: str, top: str, east: str) -> bool:
    return _cross(FACE_DIR[south], FACE_DIR[east]) == FACE_DIR[top]


def _iso(x, y, z, ox, oy, s=26):
    return (ox + (x - y) * s, oy + (x + y) * s * 0.5 - z * s * 0.92)


def _cube_faces(x, y, z, ox, oy, s=26):
    p = {(i, j, k): _iso(x + i, y + j, z + k, ox, oy, s) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    top = [p[0, 0, 1], p[1, 0, 1], p[1, 1, 1], p[0, 1, 1]]
    east = [p[1, 0, 0], p[1, 1, 0], p[1, 1, 1], p[1, 0, 1]]
    south = [p[0, 0, 0], p[1, 0, 0], p[1, 0, 1], p[0, 0, 1]]
    return top, east, south


def _stroke(draw, pts, width=3):
    draw.line(pts + [pts[0]], fill=INK, width=width)


def _draw_voxels(draw, voxels, ox, oy, s=26):
    for x, y, z in sorted(voxels, key=lambda t: (t[0] + t[1], t[2])):
        top, east, south = _cube_faces(x, y, z, ox, oy, s)
        draw.polygon(south, fill=MID, outline=INK)
        draw.polygon(east, fill=DARK, outline=INK)
        draw.polygon(top, fill=LIGHT, outline=INK)
        for face in (south, east, top):
            _stroke(draw, face)


def _place_answer(options: list[str], letter: str) -> tuple[list[str], str]:
    letter = (letter or "A").upper()
    idx = "ABCD".index(letter) if letter in "ABCD" else 0
    correct = options[0]
    rest = options[1:4]
    out = [""] * 4
    out[idx] = correct
    j = 0
    for i in range(4):
        if i == idx:
            continue
        out[i] = rest[j]
        j += 1
    return out, letter


def _save(im: Image.Image, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest)
    return f"images/{dest.name}"


def _question(
    slot: dict,
    stem: str,
    texts: list[str],
    letter: str,
    analysis: str,
    image: str,
    option_images: list[str] | None = None,
) -> dict:
    options = []
    for i, key in enumerate("ABCD"):
        text = texts[i] if i < len(texts) else key
        opt = {"key": key, "text": text}
        if option_images and i < len(option_images) and option_images[i]:
            opt["images"] = [option_images[i]]
            if len(str(text)) <= 2:
                opt["text"] = ""
        options.append(opt)
    return {
        "category": "判断推理",
        "sub_category": "图形推理",
        "tags": [slot["tag"]],
        "exam_move": slot.get("exam_move"),
        "stem": stem,
        "stem_images": [image],
        "options": options,
        "answer": letter,
        "analysis": analysis,
        "explanation": analysis,
        "difficulty": int(slot.get("difficulty") or 3),
        "figure": {"kind": GRAPHIC_KIND_BY_MOVE.get(slot.get("exam_move") or "", "faces")},
    }


def render_faces(dest: Path, letter: str) -> tuple[list[str], str, str]:
    im, d = _canvas()
    cells = [(40 + i * 200, 70, 180, 180) for i in range(5)]
    for cell, lab in zip(cells, list("1234") + ["?"]):
        _box(d, cell, lab)
    # 1 circle
    x, y, w, h = cells[0]
    d.ellipse((x + 35, y + 40, x + 145, y + 150), outline=INK, width=3)
    # 2 rect + mid
    x, y, w, h = cells[1]
    _poly(d, [(x + 30, y + 40), (x + 150, y + 40), (x + 150, y + 150), (x + 30, y + 150)])
    d.line([(x + 90, y + 40), (x + 90, y + 150)], fill=INK, width=3)
    # 3 triangle + 2
    x, y, w, h = cells[2]
    apex, bl, br = (x + 90, y + 35), (x + 25, y + 155), (x + 155, y + 155)
    _poly(d, [apex, bl, br])
    d.line([apex, (x + 70, y + 155)], fill=INK, width=3)
    d.line([apex, (x + 110, y + 155)], fill=INK, width=3)
    # 4 grid
    x, y, w, h = cells[3]
    _poly(d, [(x + 30, y + 40), (x + 150, y + 40), (x + 150, y + 150), (x + 30, y + 150)])
    d.line([(x + 90, y + 40), (x + 90, y + 150)], fill=INK, width=3)
    d.line([(x + 30, y + 95), (x + 150, y + 95)], fill=INK, width=3)
    opts = [(40 + i * 250, 400, 200, 200) for i in range(4)]
    labels, letter = _place_answer(["A", "B", "C", "D"], letter)
    # pentagon 5 / grid4 / hex6 / tri3 mapped onto ABCD by labels meaning we draw by target
    shapes = {
        letter: "pent",
        [k for k in "ABCD" if k != letter][0]: "grid",
        [k for k in "ABCD" if k != letter][1]: "hex",
        [k for k in "ABCD" if k != letter][2]: "tri",
    }
    for cell, key in zip(opts, "ABCD"):
        _box(d, cell, key)
        x, y, w, h = cell
        cx, cy = x + w / 2, y + h / 2 + 8
        kind = shapes[key]
        if kind == "pent":
            pts = [
                (cx + 62 * math.sin(i * 2 * math.pi / 5), cy - 62 * math.cos(i * 2 * math.pi / 5))
                for i in range(5)
            ]
            _poly(d, pts)
            for p in pts:
                d.line([(cx, cy), p], fill=INK, width=3)
        elif kind == "grid":
            _poly(d, [(x + 40, y + 45), (x + 160, y + 45), (x + 160, y + 165), (x + 40, y + 165)])
            d.line([(x + 100, y + 45), (x + 100, y + 165)], fill=INK, width=3)
            d.line([(x + 40, y + 105), (x + 160, y + 105)], fill=INK, width=3)
        elif kind == "hex":
            pts = [
                (cx + 64 * math.cos(i * math.pi / 3), cy + 64 * math.sin(i * math.pi / 3))
                for i in range(6)
            ]
            _poly(d, pts)
            for p in pts:
                d.line([(cx, cy), p], fill=INK, width=3)
        else:
            _poly(d, [(cx, y + 45), (x + 40, y + 165), (x + 160, y + 165)])
            d.line([(cx, cy + 20), (cx, y + 45)], fill=INK, width=3)
            d.line([(cx, cy + 20), (x + 40, y + 165)], fill=INK, width=3)
            d.line([(cx, cy + 20), (x + 160, y + 165)], fill=INK, width=3)
    _save(im, dest)
    analysis = (
        "题干封闭面数量依次为 1、2、3、4，问号处应为 5 个封闭面。"
        f"{letter} 项为正五边形连接中心，恰为 5 面。故选 {letter}。"
    )
    return ["A", "B", "C", "D"], letter, analysis


def render_arrows(dest: Path, letter: str) -> tuple[list[str], str, str]:
    im, d = _canvas()
    cells = [(40 + i * 200, 80, 180, 180) for i in range(5)]
    # 箭头绕四角顺时针，自身逆时针 90°：上左↑、上右←、下右↓、下左→，问号回上左↑
    seq = [
        ((0.28, 0.28), "up"),
        ((0.72, 0.28), "left"),
        ((0.72, 0.72), "down"),
        ((0.28, 0.72), "right"),
        None,
    ]
    for cell, lab, spec in zip(cells, list("1234") + ["?"], seq):
        _box(d, cell, lab)
        if spec is None:
            d.text((cell[0] + 70, cell[1] + 70), "?", fill=INK, font=_font(48))
            continue
        (fx, fy), direc = spec
        _arrow(d, (cell[0] + cell[2] * fx, cell[1] + cell[3] * fy), direc)
    opts = [
        ((0.28, 0.28), "down"),
        ((0.28, 0.28), "up"),
        ((0.72, 0.28), "down"),
        ((0.28, 0.72), "right"),
    ]
    texts, letter = _place_answer(["B", "A", "C", "D"], letter)  # dummy then remap draw
    # correct is top-left up
    correct = ((0.28, 0.28), "up")
    wrong = [((0.28, 0.28), "down"), ((0.72, 0.28), "down"), ((0.28, 0.72), "right")]
    placed, letter = _place_answer(["ok"] + ["w"] * 3, letter)
    draw_specs = []
    wi = 0
    for mark in placed:
        if mark == "ok":
            draw_specs.append(correct)
        else:
            draw_specs.append(wrong[wi])
            wi += 1
    for i, (cell_xy, spec) in enumerate(zip([(40 + i * 250, 400, 200, 200) for i in range(4)], draw_specs)):
        _box(d, cell_xy, "ABCD"[i])
        (fx, fy), direc = spec
        _arrow(d, (cell_xy[0] + cell_xy[2] * fx, cell_xy[1] + cell_xy[3] * fy), direc)
    _save(im, dest)
    return ["A", "B", "C", "D"], letter, (
        "箭头沿外框四角顺时针走一格，自身每次逆时针转 90°。"
        f"第五幅应回到左上且朝上，对应 {letter}。"
    )


def _arrow(draw, tip, direction, size=22):
    x, y = tip
    dxy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
    dx, dy = dxy
    px, py = -dy, dx
    tail = (x - dx * size, y - dy * size)
    left = (x + px * size * 0.45 - dx * 4, y + py * size * 0.45 - dy * 4)
    right = (x - px * size * 0.45 - dx * 4, y - py * size * 0.45 - dy * 4)
    draw.polygon([tip, left, right], fill=INK)
    draw.line([tail, (x - dx * 6, y - dy * 6)], fill=INK, width=3)


def render_xor(dest: Path, letter: str) -> tuple[list[str], str, str]:
    # 每行：图1 XOR 图2 = 图3。第三行缺图3，答案为竖中线
    segs = {
        "N": lambda x, y, w, h: ((x + 20, y + 20), (x + w - 20, y + 20)),
        "S": lambda x, y, w, h: ((x + 20, y + h - 20), (x + w - 20, y + h - 20)),
        "W": lambda x, y, w, h: ((x + 20, y + 20), (x + 20, y + h - 20)),
        "E": lambda x, y, w, h: ((x + w - 20, y + 20), (x + w - 20, y + h - 20)),
        "H": lambda x, y, w, h: ((x + 20, y + h / 2), (x + w - 20, y + h / 2)),
        "V": lambda x, y, w, h: ((x + w / 2, y + 20), (x + w / 2, y + h - 20)),
    }

    def draw_cell(draw, xy, keys, label=""):
        _box(draw, xy, label)
        x, y, w, h = xy
        for key in keys:
            a, b = segs[key](x, y, w, h)
            draw.line([a, b], fill=INK, width=3)

    def xor(a, b):
        return "".join(sorted(set(a) ^ set(b)))

    rows = [("NEWV", "NEV", None), ("NSH", "NH", None), ("EWV", "EW", "?")]
    im, d = _canvas(1000, 820)
    for r, (a, b, c) in enumerate(rows):
        y = 40 + r * 200
        draw_cell(d, (40, y, 160, 160), a, "1")
        draw_cell(d, (230, y, 160, 160), b, "2")
        if c == "?":
            _box(d, (420, y, 160, 160), "?")
            d.text((480, y + 55), "?", fill=INK, font=_font(48))
        else:
            draw_cell(d, (420, y, 160, 160), xor(a, b), "3")
    target = xor("EWV", "EW")  # V
    distractors = ["EWV", "EW", "H"]
    placed, letter = _place_answer(["V"] + distractors, letter)
    keymap = {"V": "V", "EWV": "EWV", "EW": "EW", "H": "H"}
    for i, mark in enumerate(placed):
        draw_cell(d, (40 + i * 230, 640, 180, 150), keymap[mark], "ABCD"[i])
    _save(im, dest)
    return ["A", "B", "C", "D"], letter, (
        "每行图1 与图2 去同存异得到图3。第三行保留竖中线。"
        f"故选 {letter}。"
    )


def render_symmetry(dest: Path, letter: str) -> tuple[list[str], str, str]:
    # ①③⑥ 轴对称，②④⑤ 中心对称
    im, d = _canvas(1100, 640)
    cells = [(40 + (i % 3) * 340, 40 + (i // 3) * 240, 300, 210) for i in range(6)]
    labels = "①②③④⑤⑥"
    # axis: isosceles triangle, kite, arrow-up
    # center: S, Z, parallelogram
    for i, cell in enumerate(cells):
        _box(d, cell, labels[i])
        x, y, w, h = cell
        cx, cy = x + w / 2, y + h / 2 + 8
        if i in (0, 2, 5):
            _poly(d, [(cx, y + 35), (x + 50, y + 170), (x + w - 50, y + 170)])
        else:
            _poly(d, [(x + 70, y + 50), (x + w - 50, y + 50), (x + w - 70, y + 170), (x + 50, y + 170)])
    texts = ["①③⑤，②④⑥", "①②⑤，③④⑥", "①③⑥，②④⑤", "①④⑥，②③⑤"]
    placed, letter = _place_answer(["①③⑥，②④⑤"] + [t for t in texts if t != "①③⑥，②④⑤"], letter)
    _save(im, dest)
    return placed, letter, (
        "①③⑥均为轴对称，②④⑤均为中心对称。"
        f"分类正确的是 {letter}。"
    )


def render_open_close(dest: Path, letter: str) -> tuple[list[str], str, str]:
    im, d = _canvas(1100, 640)
    cells = [(40 + (i % 3) * 340, 40 + (i // 3) * 240, 300, 210) for i in range(6)]
    labels = "①②③④⑤⑥"
    # ①③⑤ closed, ②④⑥ open
    for i, cell in enumerate(cells):
        _box(d, cell, labels[i])
        x, y, w, h = cell
        if i % 2 == 0:
            d.ellipse((x + 70, y + 45, x + w - 70, y + 175), outline=INK, width=3)
        else:
            d.arc((x + 70, y + 45, x + w - 70, y + 175), 40, 300, fill=INK, width=3)
    texts = ["①③⑤，②④⑥", "①②⑤，③④⑥", "①③⑥，②④⑤", "①④⑥，②③⑤"]
    placed, letter = _place_answer(["①③⑤，②④⑥"] + [t for t in texts if t != "①③⑤，②④⑥"], letter)
    _save(im, dest)
    return placed, letter, (
        "①③⑤为封闭图形，②④⑥为开放图形。"
        f"故选 {letter}。"
    )


def _mark(draw, box, kind):
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    if kind == "dot":
        draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=INK)
    elif kind == "tri":
        _poly(draw, [(cx, cy - 16), (cx - 16, cy + 14), (cx + 16, cy + 14)], fill=INK)
    elif kind == "plus":
        draw.line([(cx - 16, cy), (cx + 16, cy)], fill=INK, width=4)
        draw.line([(cx, cy - 16), (cx, cy + 16)], fill=INK, width=4)
    elif kind == "slash":
        draw.line([(x + 18, y + h - 18), (x + w - 18, y + 18)], fill=INK, width=4)
    elif kind == "arrow":
        _arrow(draw, (cx, cy - 8), "up", 18)
    elif kind == "ring":
        draw.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), outline=INK, width=3)
    elif kind == "x":
        draw.line([(cx - 14, cy - 14), (cx + 14, cy + 14)], fill=INK, width=4)
        draw.line([(cx + 14, cy - 14), (cx - 14, cy + 14)], fill=INK, width=4)
    elif kind == "fill":
        draw.rectangle((cx - 12, cy - 12, cx + 12, cy + 12), fill=INK)
    else:
        draw.rectangle((cx - 12, cy - 12, cx + 12, cy + 12), outline=INK, width=3)


def _quad_pt(pts, u, v):
    p00, p10, p11, p01 = pts
    ax, ay = p00[0] * (1 - u) + p10[0] * u, p00[1] * (1 - u) + p10[1] * u
    bx, by = p01[0] * (1 - u) + p11[0] * u, p01[1] * (1 - u) + p11[1] * u
    return (ax * (1 - v) + bx * v, ay * (1 - v) + by * v)


def _mark_quad(draw, pts, kind):
    if kind == "dot":
        c = _quad_pt(pts, 0.5, 0.5)
        r = max(5, int(abs(pts[2][0] - pts[0][0]) * 0.08))
        draw.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=INK)
    elif kind == "plus":
        draw.line([_quad_pt(pts, 0.28, 0.5), _quad_pt(pts, 0.72, 0.5)], fill=INK, width=4)
        draw.line([_quad_pt(pts, 0.5, 0.28), _quad_pt(pts, 0.5, 0.72)], fill=INK, width=4)
    elif kind == "ring":
        ring = [_quad_pt(pts, 0.5 + 0.18 * math.cos(i * math.pi / 4), 0.5 + 0.18 * math.sin(i * math.pi / 4)) for i in range(8)]
        _stroke(draw, ring, 3)
    elif kind == "x":
        draw.line([_quad_pt(pts, 0.3, 0.3), _quad_pt(pts, 0.7, 0.7)], fill=INK, width=4)
        draw.line([_quad_pt(pts, 0.7, 0.3), _quad_pt(pts, 0.3, 0.7)], fill=INK, width=4)
    elif kind == "fill":
        draw.polygon([_quad_pt(pts, u, v) for u, v in ((0.32, 0.32), (0.68, 0.32), (0.68, 0.68), (0.32, 0.68))], fill=INK)
    else:
        draw.polygon(
            [_quad_pt(pts, u, v) for u, v in ((0.32, 0.32), (0.68, 0.32), (0.68, 0.68), (0.32, 0.68))],
            outline=INK,
        )
        _stroke(draw, [_quad_pt(pts, u, v) for u, v in ((0.32, 0.32), (0.68, 0.32), (0.68, 0.68), (0.32, 0.68))], 3)


def _option_path(dest: Path, key: str) -> Path:
    return dest.with_name(f"{dest.stem}-{key}.png")


def _render_iso_option(dest: Path, visible: dict) -> str:
    im, d = _canvas(340, 300)
    top, east, south = _cube_faces(0, 0, 0, 170, 188, 68)
    d.polygon(south, fill=MID, outline=INK)
    d.polygon(east, fill=DARK, outline=INK)
    d.polygon(top, fill=LIGHT, outline=INK)
    for face in (south, east, top):
        _stroke(d, face, 3)
    faces = {"top": top, "east": east, "south": south}
    for name, kind in visible.items():
        _mark_quad(d, faces[name], kind)
    return _save(im, dest)


def _render_cells_option(dest: Path, cells: set, filled: bool) -> str:
    im, d = _canvas(300, 260)
    if not cells:
        return _save(im, dest)
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    cols, rows = maxx - minx + 1, maxy - miny + 1
    s = min(56, 200 // max(cols, rows))
    ox = (300 - cols * s) / 2
    oy = (260 - rows * s) / 2
    span = range(minx, maxx + 1), range(miny, maxy + 1)
    if filled:
        for x in span[0]:
            for y in span[1]:
                px = ox + (x - minx) * s
                py = oy + (maxy - y) * s
                fill = INK if (x, y) in cells else BG
                d.rectangle((px, py, px + s, py + s), fill=fill, outline=INK, width=3)
    else:
        for x, y in cells:
            px = ox + (x - minx) * s
            py = oy + (maxy - y) * s
            d.rectangle((px, py, px + s, py + s), outline=INK, width=3)
    return _save(im, dest)


def render_cube_net(dest: Path, letter: str, variant: int = 0) -> tuple[list[str], str, str, list[str]]:
    marks = MARK_SETS[variant % len(MARK_SETS)]
    visible_ids = NET_CORRECT[variant % len(NET_CORRECT)]
    im, d = _canvas(720, 520)
    cell = 100
    ox, oy = 160, 110
    places = {"5": (1, 0), "1": (0, 1), "2": (1, 1), "3": (2, 1), "4": (3, 1), "6": (1, 2)}
    for face, (c, r) in places.items():
        box = (ox + c * cell, oy + r * cell, cell, cell)
        d.rectangle((box[0], box[1], box[0] + cell, box[1] + cell), outline=INK, width=3)
        _mark(d, box, marks[face])
    _save(im, dest)

    def as_marks(face_ids: dict) -> dict:
        return {slot: marks[fid] for slot, fid in face_ids.items()}

    correct = as_marks(visible_ids)
    top_id = visible_ids["top"]
    south_id = visible_ids["south"]
    east_id = visible_ids["east"]
    opp = {"1": "3", "3": "1", "2": "4", "4": "2", "5": "6", "6": "5"}
    wrongs = [
        as_marks({"south": opp[east_id], "top": top_id, "east": east_id}),
        as_marks({"south": south_id, "top": top_id, "east": opp[south_id]}),
        as_marks({"south": south_id, "top": opp[top_id], "east": east_id}),
    ]
    placed, letter = _place_answer(["ok"] + ["w1", "w2", "w3"], letter)
    specs = []
    wi = 0
    for mark in placed:
        if mark == "ok":
            specs.append(correct)
        else:
            specs.append(wrongs[wi])
            wi += 1
    opt_rels = [_render_iso_option(_option_path(dest, key), spec) for key, spec in zip("ABCD", specs)]
    return ["A", "B", "C", "D"], letter, (
        "展开图呈“中间一排四格、上下各一格”。同一横排隔一格的是相对面，上下两格也是相对面，"
        f"相对面折叠后不能同时出现。{letter} 项三个可见面两两相邻，可以由该展开图折成。"
    ), opt_rels


def section_of_stack(voxels: set[tuple[int, int, int]], plane: str) -> set[tuple[int, int]]:
    axis, _, raw = plane.partition("=")
    height = float(raw)
    layer = int(height)  # 0.5 → 穿过 z=0 那一层
    if axis == "z":
        return {(x, y) for x, y, z in voxels if z == layer}
    if axis == "x":
        return {(y, z) for x, y, z in voxels if x == layer}
    if axis == "y":
        return {(x, z) for x, y, z in voxels if y == layer}
    raise ValueError(plane)


def _section_wrongs(correct: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    xs = [c[0] for c in correct]
    ys = [c[1] for c in correct]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    box = {(x, y) for x in range(minx, maxx + 1) for y in range(miny, maxy + 1)}
    row = {(x, miny) for x in range(minx, maxx + 1)}
    col = {(minx, y) for y in range(miny, maxy + 1)}
    extra = correct | {(maxx + 1, miny)}
    missing = set(list(sorted(correct))[:-1]) if len(correct) > 1 else {(minx + 1, miny)}
    cands = [box, row, col, extra, missing, {(0, 0), (1, 0)}, {(0, 0), (0, 1)}, {(0, 0), (1, 0), (0, 1)}, {(0, 0), (1, 0), (0, 1), (1, 1)}]
    out = []
    for item in cands:
        if item and item != correct and item not in out:
            out.append(item)
        if len(out) == 3:
            return out
    n = 0
    while len(out) < 3:
        cand = {(n, 0), (n, 1)}
        n += 1
        if cand != correct and cand not in out:
            out.append(cand)
    return out[:3]


def render_cube_section(dest: Path, letter: str, variant: int = 0) -> tuple[list[str], str, str, list[str]]:
    recipe = SECTION_RECIPES[variant % len(SECTION_RECIPES)]
    voxels = recipe["voxels"]
    cut = section_of_stack(voxels, recipe["plane"])
    im, d = _canvas(720, 560)
    _draw_voxels(d, voxels, 360, 380, 48)
    maxx = max(v[0] for v in voxels) + 1
    maxy = max(v[1] for v in voxels) + 1
    corners = [_iso(x, y, 0.5, 360, 380, 48) for x, y in ((0, 0), (maxx, 0), (maxx, maxy), (0, maxy))]
    d.polygon(corners, fill=(200, 220, 235), outline=DASH)
    d.line(corners + [corners[0]], fill=DASH, width=3)
    _save(im, dest)
    placed, letter = _place_answer(["ok"] + ["a", "b", "c"], letter)
    packs = []
    wi = 0
    wrongs = _section_wrongs(cut)
    for mark in placed:
        if mark == "ok":
            packs.append(cut)
        else:
            packs.append(wrongs[wi])
            wi += 1
    opt_rels = [_render_cells_option(_option_path(dest, key), cells, False) for key, cells in zip("ABCD", packs)]
    return ["A", "B", "C", "D"], letter, f"{recipe['note']}。故选 {letter}。", opt_rels


def top_view(voxels: set[tuple[int, int, int]]) -> set[tuple[int, int]]:
    return {(x, y) for x, y, _z in voxels}


def front_view(voxels: set[tuple[int, int, int]]) -> set[tuple[int, int]]:
    return {(x, z) for x, _y, z in voxels}


def render_cube_views(dest: Path, letter: str, variant: int = 0) -> tuple[list[str], str, str, list[str]]:
    recipe = VIEW_RECIPES[variant % len(VIEW_RECIPES)]
    voxels = recipe["voxels"]
    truth = top_view(voxels) if recipe["mode"] == "top" else front_view(voxels)
    im, d = _canvas(720, 560)
    _draw_voxels(d, voxels, 360, 380, 48)
    _save(im, dest)
    placed, letter = _place_answer(["ok"] + ["a", "b", "c"], letter)
    packs = []
    wi = 0
    wrongs = _section_wrongs(truth)
    for mark in placed:
        if mark == "ok":
            packs.append(truth)
        else:
            packs.append(wrongs[wi])
            wi += 1
    opt_rels = [_render_cells_option(_option_path(dest, key), cells, True) for key, cells in zip("ABCD", packs)]
    return ["A", "B", "C", "D"], letter, f"{recipe['note']}。故选 {letter}。", opt_rels


RENDERERS = {
    "faces": (render_faces, STEM_LAW),
    "arrows": (render_arrows, STEM_LAW),
    "xor": (render_xor, STEM_LAW),
    "symmetry": (render_symmetry, STEM_CLASS),
    "open_close": (render_open_close, STEM_CLASS),
    "cube_net": (render_cube_net, STEM_NET),
    "cube_section": (render_cube_section, STEM_CUT),
    "cube_views": (render_cube_views, STEM_VIEW),
}


def build_graphic_question(slot: dict, dest: Path) -> dict:
    kind = GRAPHIC_KIND_BY_MOVE.get(str(slot.get("exam_move") or ""), "faces")
    render, stem = RENDERERS[kind]
    variant = int(slot.get("variant") or 0)
    letter = str(slot.get("answer") or "A")
    if kind.startswith("cube_"):
        texts, letter, analysis, opt_imgs = render(dest, letter, variant)
    else:
        texts, letter, analysis = render(dest, letter)
        opt_imgs = None
    if kind == "cube_net":
        stem = STEM_NETS[variant % len(STEM_NETS)]
    elif kind == "cube_section":
        stem = STEM_CUTS[variant % len(STEM_CUTS)]
    elif kind == "cube_views":
        stems = STEM_FRONTS if VIEW_RECIPES[variant % len(VIEW_RECIPES)]["mode"] == "front" else STEM_TOPS
        stem = stems[variant % len(stems)]
    return _question(slot, stem, texts, letter, analysis, f"images/{dest.name}", opt_imgs)


def build_graphic_paper(slots: list[dict], batch_dir: Path, batch_id: str) -> list[dict]:
    images = batch_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    out = []
    for index, slot in enumerate(slots, 1):
        dest = images / f"{batch_id}_{index:02d}.png"
        row = build_graphic_question(slot, dest)
        row["external_id"] = f"{batch_id}_{index:02d}"
        out.append(row)
    return out


SPACE_TAG = "判断推理-图形推理-空间类"
SPACE_MOVES = (
    ("六面体展开还原", 0, "A", 3),
    ("立方体截面", 0, "B", 2),
    ("小方块三视图", 0, "C", 2),
    ("六面体展开还原", 1, "D", 3),
    ("立方体截面", 1, "A", 3),
    ("小方块三视图", 1, "B", 3),
    ("六面体展开还原", 2, "C", 4),
    ("立方体截面", 2, "D", 3),
    ("小方块三视图", 2, "A", 4),
    ("六面体展开还原", 3, "B", 3),
)


def space_slots() -> list[dict]:
    return [
        {
            "tag": SPACE_TAG,
            "exam_move": move,
            "variant": variant,
            "answer": answer,
            "difficulty": difficulty,
        }
        for move, variant, answer, difficulty in SPACE_MOVES
    ]


def _dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_spatial_batch(batch_dir: Path, batch_id: str, source: str) -> list[dict]:
    batch_dir.mkdir(parents=True, exist_ok=True)
    questions = build_graphic_paper(space_slots(), batch_dir, batch_id)
    for row in questions:
        row["source"] = source
        row["year"] = 2026
        row["region"] = "广东-省直"
        row["question_type"] = "single"
    specs = []
    for row in questions:
        kind = (row.get("figure") or {}).get("kind")
        facts = {
            "cube_net": ("十字展开图六面贴纸", "四个立体选项的三面贴纸"),
            "cube_section": ("小立方体堆叠与虚线切面", "四个截面多边形"),
            "cube_views": ("小立方体堆叠立体", "四个正交投影网格"),
        }.get(kind, ("题干立体图", "四个选项图"))
        specs.append(
            {
                "question_id": row["external_id"],
                "image_facts": [facts[0]],
                "image_only_facts": list(facts),
                "must_derive": [f"正确选项是 {row['answer']}"],
            }
        )
    _dump(batch_dir / "questions.json", questions)
    _dump(
        batch_dir / "manifest.json",
        {
            "batch_id": batch_id,
            "source": source,
            "region": "广东-省直",
            "year": 2026,
            "kind": "ai-generated",
            "difficulty_tier": "hard",
            "generation": {
                "style_marker": "GONGKAO-STYLE-v1",
                "batch_constraints": {
                    "all_original": True,
                    "spatial_drill": True,
                    "question_count": 10,
                    "tag_counts": {SPACE_TAG: 10},
                    "image_dependent_count": {"min": 10, "max": 10},
                    "answer_max_per_letter": 3,
                    "answer_min_letters": 4,
                },
                "generation_contexts": [],
                "evaluation_contexts": [],
            },
        },
    )
    _dump(batch_dir / "image-specs.json", {"questions": specs})
    return questions

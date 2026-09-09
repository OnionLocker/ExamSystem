#!/usr/bin/env python3
"""只出一张公考侧视光照样图，不接入日练流水线。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageChops, ImageDraw, ImageFont

INK = (20, 20, 20)
BG = (255, 255, 255)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "figure-lab" / "earth-rotation-exam.png"


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if path.is_file():
        return ImageFont.truetype(str(path), size, index=3)  # SC
    return ImageFont.load_default()


def dash(draw: ImageDraw.ImageDraw, a, b, width=3, on=10, off=8):
    x1, y1 = a
    x2, y2 = b
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    t = 0.0
    while t < length:
        t2 = min(t + on, length)
        draw.line((x1 + ux * t, y1 + uy * t, x1 + ux * t2, y1 + uy * t2), fill=INK, width=width)
        t += on + off


def arrow(draw: ImageDraw.ImageDraw, a, b, width=3, head=16):
    x1, y1 = a
    x2, y2 = b
    draw.line((a, b), fill=INK, width=width)
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    draw.polygon(
        [
            (x2, y2),
            (x2 - ux * head + px * head * 0.38, y2 - uy * head + py * head * 0.38),
            (x2 - ux * head - px * head * 0.38, y2 - uy * head - py * head * 0.38),
        ],
        fill=INK,
    )


def ellipse_pts(cx, cy, rx, ry, n=120):
    return [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in (i * math.tau / n for i in range(n))]


def circle_mask(size, cx, cy, r) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return mask


def night_mask(size, cx, cy, r) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).pieslice((cx - r, cy - r, cx + r, cy + r), 90, 270, fill=255)
    globe = circle_mask(size, cx, cy, r - 3)
    return ImageChops.multiply(mask, globe)


def night_hatch(size, cx, cy, r, step=16) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, h = size
    for x in range(-h, w + h, step):
        d.line((x, 0, x + h, h), fill=INK + (255,), width=2)
    layer.putalpha(ImageChops.multiply(layer.split()[-1], night_mask(size, cx, cy, r)))
    return layer


def draw_exam() -> Image.Image:
    scale = 2
    w, h = 1400 * scale, 720 * scale
    im = Image.new("RGB", (w, h), BG)
    cx, cy, r = 560 * scale, 350 * scale, 230 * scale
    d = ImageDraw.Draw(im)

    # 经纬网先画，夜半球斜线再盖上去（真题：阴影=夜，线仍隐约可见）
    globe = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = ImageDraw.Draw(globe)
    for k in (-0.72, -0.38, 0.38, 0.72):
        g.ellipse((cx - abs(k) * r, cy - r, cx + abs(k) * r, cy + r), outline=INK, width=2)
    g.ellipse((cx - r, cy - int(r * 0.30), cx + r, cy + int(r * 0.30)), outline=INK, width=3)
    g.ellipse((cx - r, cy - int(r * 0.62), cx + r, cy + int(r * 0.62)), outline=INK, width=2)
    globe.putalpha(ImageChops.multiply(globe.split()[-1], circle_mask((w, h), cx, cy, r - 2)))
    im.paste(globe, mask=globe.split()[-1])
    hatch = night_hatch((w, h), cx, cy, r, step=18)
    im.paste(hatch, mask=hatch.split()[-1])

    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=5)
    dash(d, (cx, cy - r + 4), (cx, cy + r - 4), width=4, on=14, off=10)
    d.line((cx, cy - r - 48, cx, cy + r + 48), fill=INK, width=3)
    d.polygon([(cx, cy - r - 70), (cx - 12, cy - r - 46), (cx + 12, cy - r - 46)], fill=INK)

    # 太阳与平行光线（在地球右侧，垂直于晨昏线）
    sx, sr = 1240 * scale, 36 * scale
    d.ellipse((sx - sr, cy - sr, sx + sr, cy + sr), outline=INK, width=4)
    for i in range(8):
        ang = i * math.tau / 8
        a = (sx + math.cos(ang) * (sr + 8), cy + math.sin(ang) * (sr + 8))
        b = (sx + math.cos(ang) * (sr + 28), cy + math.sin(ang) * (sr + 28))
        d.line((a, b), fill=INK, width=3)
    for dy in (-160, -80, 0, 80, 160):
        y = cy + dy * scale
        arrow(d, (sx - sr - 36, y), (cx + r + 28, y), width=4, head=22)

    # 自转箭头画在圆外下方，自西向东（夜→晨线→昼）
    y_ar = cy + r + 70
    arrow(d, (cx - 170, y_ar), (cx + 210, y_ar), width=5, head=24)

    def dot(p, label, ox, oy, size=34):
        x, y = p
        d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=BG, outline=INK, width=4)
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=INK)
        d.text((x + ox, y + oy), label, fill=INK, font=font(size), anchor="mm")

    # 甲：晨线与赤道交点（日出，地方时6时）
    # 乙：昼半球赤道（接近正午）
    # 丙：夜半球赤道
    # 丁：北半球昼侧
    dot((cx, cy), "甲", 36, 36)
    dot((cx + int(r * 0.78), cy), "乙", 0, 40)
    dot((cx - int(r * 0.72), cy), "丙", 0, 40)
    dot((cx + int(r * 0.42), cy - int(r * 0.52)), "丁", 36, -8)

    f24, f28 = font(28), font(32)
    d.text((cx - r - 70, cy), "夜半球", fill=INK, font=f28, anchor="mm")
    d.text((cx + r + 8, cy - r - 8), "昼半球", fill=INK, font=f28, anchor="mm")
    d.text((cx + 28, cy - r + 80), "晨昏线", fill=INK, font=f24, anchor="lt")
    d.text((cx, cy - r - 88), "N", fill=INK, font=f28, anchor="mm")
    d.text((cx, cy + r + 36), "S", fill=INK, font=f28, anchor="mm")
    d.text((sx, cy + sr + 48), "太阳", fill=INK, font=f28, anchor="mm")
    d.text((sx - 180, cy - 200 * scale), "太阳光线", fill=INK, font=f24, anchor="mm")
    d.text((cx + 20, y_ar + 40), "自转方向", fill=INK, font=f28, anchor="mm")

    return im.resize((1400, 720), Image.Resampling.LANCZOS)


def write_svg(dest: Path) -> None:
    from figure_lab import Svg

    cx, cy, r = 560, 350, 230
    sx, sr = 1240, 36
    s = Svg(1400, 720)
    s.add(
        '<defs>'
        '<clipPath id="globe"><circle cx="560" cy="350" r="228"/></clipPath>'
        '<clipPath id="night"><path d="M560,120 A230,230 0 0 0 560,580 Z"/></clipPath>'
        '</defs>'
    )
    s.add('<g clip-path="url(#globe)">')
    for k in (0.72, 0.38):
        s.ellipse((cx, cy), abs(k) * r, r, w=1.4)
    s.ellipse((cx, cy), r, r * 0.30, w=2.2)
    s.ellipse((cx, cy), r, r * 0.62, w=1.4)
    s.add("</g>")
    s.add('<g clip-path="url(#night)">')
    s.add('<rect x="320" y="110" width="250" height="480" fill="url(#hatch)"/>')
    s.add("</g>")
    s.circle((cx, cy), r, w=2.8)
    s.line((cx, cy - r + 2), (cx, cy + r - 2), 2.4, dash="10 8")
    s.line((cx, cy - r - 24), (cx, cy + r + 24), 1.8)
    s.polygon([(cx, cy - r - 36), (cx - 7, cy - r - 22), (cx + 7, cy - r - 22)], fill="#111111", w=1)
    s.circle((sx, cy), sr, w=2.4)
    for i in range(8):
        ang = i * math.tau / 8
        s.line(
            (sx + math.cos(ang) * (sr + 4), cy + math.sin(ang) * (sr + 4)),
            (sx + math.cos(ang) * (sr + 14), cy + math.sin(ang) * (sr + 14)),
            1.8,
        )
    for dy in (-160, -80, 0, 80, 160):
        s.arrow((sx - sr - 18, cy + dy), (cx + r + 16, cy + dy), 2.2)
    s.arrow((cx - 85, cy + r + 36), (cx + 105, cy + r + 36), 2.6)

    def mark(p, label, ox, oy):
        s.circle(p, 6, fill="#ffffff", w=2)
        s.circle(p, 2.4, fill="#111111", w=1)
        s.text((p[0] + ox, p[1] + oy + 6), label, 22)

    mark((cx, cy), "甲", 22, 22)
    mark((cx + r * 0.78, cy), "乙", 0, 28)
    mark((cx - r * 0.72, cy), "丙", 0, 28)
    mark((cx + r * 0.42, cy - r * 0.52), "丁", 22, -18)
    s.text((cx - r - 52, cy + 8), "夜半球", 22)
    s.text((cx + r + 8, cy - r + 4), "昼半球", 22)
    s.text((cx + 46, cy - r + 70), "晨昏线", 18)
    s.text((cx, cy - r - 44), "N", 22)
    s.text((cx, cy + r + 20), "S", 22)
    s.text((sx, cy + sr + 28), "太阳", 20)
    s.text((sx - 90, cy - 168), "太阳光线", 18)
    s.text((cx + 10, cy + r + 62), "自转方向", 20)
    dest.parent.mkdir(parents=True, exist_ok=True)
    s.write(dest)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    im = draw_exam()
    im.save(OUT)
    im.save(OUT.with_suffix(".jpg"), quality=92)
    im.save("/tmp/earth-rotation-exam.png")
    svg = OUT.with_suffix(".svg")
    write_svg(svg)
    html = OUT.with_name("earth-rotation-exam.html")
    html.write_text(
        "<!doctype html><meta charset=utf-8><title>地球自转样图</title>"
        "<body style='margin:0;background:#111;display:grid;place-items:center;min-height:100vh'>"
        f"<img src='earth-rotation-exam.svg' alt='地球自转' style='max-width:100%;background:#fff'/>"
        "</body>\n",
        encoding="utf-8",
    )
    print(svg)
    print(html)


if __name__ == "__main__":
    main()

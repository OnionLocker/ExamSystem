#!/usr/bin/env python3
import math
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from render_ziliao_figure import BG, INK, render_bars, render_pie, render_table

tmp = Path("/tmp/ziliao-render-test")
tmp.mkdir(exist_ok=True)
table = tmp / "t.png"
bars = tmp / "b.png"
pie = tmp / "p.png"
render_table("表1 测试", ["区域", "2024年"], [["东部", "80.0"], ["西部", "20.0"]], table, "单位：亿件")
render_bars("图1 测试", "亿件", ["东部", "西部"], [("2024年", [80.0, 20.0])], bars)
try:
    render_bars("图2 混合单位", "万人次/亿元", ["2025年"], [("诊疗", [20]), ("补助", [10])], tmp / "bad.png")
    raise AssertionError("mixed-unit ylabel should be rejected")
except ValueError as exc:
    assert "单位" in str(exc)
render_pie("图2 测试", [("快充", 27.0), ("慢充", 18.0)], pie)
assert Image.open(table).size[0] > 100
assert Image.open(bars).size[0] > 200
assert Image.open(pie).size[0] > 100
assert Image.open(table).getpixel((2, 2)) == BG

patterned = tmp / "pie-patterns.png"
render_pie("", [("甲", 40), ("乙", 25), ("丙", 20), ("丁", 15)], patterned, show_values=False)
pie_img = Image.open(patterned).convert("RGB")
box, pad_top = 220, 16
x0, y0 = (pie_img.width - box) // 2, pad_top
circle_colors = {pie_img.getpixel((x, y)) for y in range(y0, y0 + box) for x in range(x0, x0 + box)}
assert circle_colors <= {INK, BG}, circle_colors
cx, cy = x0 + box / 2, y0 + box / 2
radius = box / 2


def wedge_ink(start, sweep):
    black = []
    total = 0
    for y in range(int(y0) + 4, int(y0 + box) - 3):
        for x in range(int(x0) + 4, int(x0 + box) - 3):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            if dist > radius - 6 or dist < 10:
                continue
            delta = (math.degrees(math.atan2(dy, dx)) - start) % 360
            if delta < 2 or delta > sweep - 2:
                continue
            total += 1
            if pie_img.getpixel((x, y)) == INK:
                black.append((x, y))
    found = set()
    parts = 0
    black_set = set(black)
    for point in black:
        if point in found:
            continue
        parts += 1
        stack = [point]
        found.add(point)
        while stack:
            px, py = stack.pop()
            for nxt in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                if nxt in black_set and nxt not in found:
                    found.add(nxt)
                    stack.append(nxt)
    return (len(black) / total if total else 0), parts


shares = [40, 25, 20, 15]
densities, parts = [], []
cursor = -90.0
for share in shares:
    sweep = 360.0 * share / 100
    density, part = wedge_ink(cursor, sweep)
    densities.append(density)
    parts.append(part)
    cursor += sweep
# 实心、斜线、马赛克、网点：实心最满且连成一块，马赛克比斜线和网点更密，网点比斜线更碎。
assert densities[0] > 0.85 and parts[0] == 1, (densities, parts)
assert densities[2] > densities[1] + 0.08 and densities[2] > densities[3] + 0.08, (densities, parts)
assert parts[3] > parts[1] + 20, (densities, parts)

# Reproduce the long customs-category labels and near-ceiling value from a live batch.
drawn = []
original_text = ImageDraw.ImageDraw.text
def record_text(draw, xy, text, *args, **kwargs):
    drawn.append((text, draw.textbbox(xy, text, font=kwargs.get("font"), anchor=kwargs.get("anchor"))))
    return original_text(draw, xy, text, *args, **kwargs)

long_bars = tmp / "long-labels.png"
with patch.object(ImageDraw.ImageDraw, "text", record_text):
    render_bars("图3 测试", "亿元", ["一般贸易", "加工贸易", "保税物流", "跨境电商网购保税", "保税研发与维修", "其他"],
                [("2023年", [816.9, 372.45, 168.74, 54.63, 28.16, 13.85])], long_bars)
labels = [(text, box) for text, box in drawn if box[0] >= 64 and 320 < box[1] < Image.open(long_bars).height - 28]
assert "".join(text for text, _ in labels) == "一般贸易加工贸易保税物流跨境电商网购保税保税研发与维修其他"
for i, (_, a) in enumerate(labels):
    for _, b in labels[i + 1:]:
        assert a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1], (a, b)
assert next(box for text, box in drawn if text == "816.9")[1] > 74

# Monetary labels near a tick must remain clear: use axis ticks, not full-width grid lines.
lines = []
original_line = ImageDraw.ImageDraw.line
def record_line(draw, xy, *args, **kwargs):
    lines.append(xy)
    return original_line(draw, xy, *args, **kwargs)
with patch.object(ImageDraw.ImageDraw, "line", record_line):
    render_bars("出口额", "亿元", [str(y) for y in range(2018, 2024)],
                [("出口额", [8936.4, 9612.8, 10248.5, 11824.2, 12581.6, 13952.9])], tmp / "near-ticks.png")
assert sum(y0 == y1 and x1 - x0 > 100 for x0, y0, x1, y1 in lines) == 1  # Baseline only.

wide_headers = ["地区", "高新技术企业数（家）", "营业收入（亿元）", "营业收入同比增量（亿元）", "研发经费内部支出（亿元）", "研发经费内部支出同比增速（%）", "期末有效发明专利拥有量（件）"]
wide_table = tmp / "long-headers.png"
drawn.clear()
with patch.object(ImageDraw.ImageDraw, "text", record_text):
    render_table("长表头测试", wide_headers, [["珠三角九市合计", "71683", "86080.0", "5184.2", "3984.8", "10.3", "304000"]], wide_table)
assert Image.open(wide_table).width <= 1024
assert "".join(text for text, _ in drawn[1:]).startswith("".join(wide_headers))
for i, (_, a) in enumerate(drawn):
    for _, b in drawn[i + 1:]:
        assert a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1], (a, b)
print("ok", Image.open(table).size, Image.open(bars).size, Image.open(pie).size)

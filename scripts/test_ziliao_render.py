#!/usr/bin/env python3
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from render_ziliao_figure import BG, render_bars, render_pie, render_table

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
print("ok", Image.open(table).size, Image.open(bars).size, Image.open(pie).size)

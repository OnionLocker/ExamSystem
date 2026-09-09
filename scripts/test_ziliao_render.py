#!/usr/bin/env python3
from pathlib import Path
from PIL import Image
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
assert Image.open(bars).size[0] >= 600
assert Image.open(pie).size[0] > 100
assert Image.open(table).getpixel((2, 2)) == BG
print("ok", Image.open(table).size, Image.open(bars).size, Image.open(pie).size)

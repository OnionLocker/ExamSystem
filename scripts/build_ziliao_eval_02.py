import json
import os
import subprocess
from pathlib import Path

BATCH_ID = "20260920_hermes_ziliao_eval_02"
BATCH_DIR = Path("/home/ubuntu/ExamSystem/data/manual-ziliao/2026-09-20/20260920_hermes_ziliao_eval_02")
SOURCE = "广东省考行测-资料分析-20260920"

BATCH_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR = BATCH_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# 1. Render Figures
# Figure 1: m-02-table.png
cmd_m02 = [
    "python3", "scripts/render_ziliao_figure.py", "table",
    "--title", "2025年H省主要海洋产业增加值及增长情况",
    "--unit", "亿元",
    "--headers", "产业门类,增加值（亿元）,同比增速（%）",
    "--rows",
    "海洋渔业,1280.5,4.8",
    "海洋油气及矿业,465.2,8.5",
    "海洋船舶及工程装备制造,624.8,18.2",
    "海洋电力及新兴产业,382.5,24.6",
    "海洋旅游业,1568.0,12.5",
    "海洋交通运输业,986.0,6.4",
    "主要海洋产业合计,5307.0,10.5",
    "--out", str(IMAGES_DIR / "m-02-table.png")
]
subprocess.run(cmd_m02, check=True)

# Figure 2: m-03-bars.png
cmd_m03 = [
    "python3", "scripts/render_ziliao_figure.py", "bars",
    "--title", "2021—2025年G省农村居民人均可支配收入",
    "--ylabel", "元",
    "--categories", "2021年,2022年,2023年,2024年,2025年",
    "--series", "人均可支配收入:22306,23598,25142,26895,28912",
    "--out", str(IMAGES_DIR / "m-03-bars.png")
]
subprocess.run(cmd_m03, check=True)

# Figure 3: m-04-table.png
cmd_m04 = [
    "python3", "scripts/render_ziliao_figure.py", "table",
    "--title", "2025年H省软件业务收入细分领域构成",
    "--unit", "亿元",
    "--headers", "业务领域,收入（亿元）,同比增速（%）",
    "--rows",
    "软件产品,3450.0,14.5",
    "信息技术服务,6280.0,18.2",
    "信息安全,385.0,25.0",
    "嵌入式系统软件,1425.0,10.0",
    "合计,11540.0,16.2",
    "--out", str(IMAGES_DIR / "m-04-table.png")
]
subprocess.run(cmd_m04, check=True)

# Option figures for Q19:
# A (Correct): 967.0, 436.9, 129.5, 77.0
# B: 967.0, 129.5, 436.9, 77.0
# C: 967.0, 436.9, 77.0, 129.5
# D: 436.9, 967.0, 129.5, 77.0
for opt, s_val in [
    ("A", "增量:967.0,436.9,129.5,77.0"),
    ("B", "增量:967.0,129.5,436.9,77.0"),
    ("C", "增量:967.0,436.9,77.0,129.5"),
    ("D", "增量:436.9,967.0,129.5,77.0"),
]:
    cmd_opt = [
        "python3", "scripts/render_ziliao_figure.py", "bars",
        "--title", f"选项{opt}：2025年细分领域收入增量",
        "--ylabel", "亿元",
        "--categories", "信息技术,软件产品,嵌入式,信息安全",
        "--series", s_val,
        "--out", str(IMAGES_DIR / f"q-19-opt-{opt}.png")
    ]
    subprocess.run(cmd_opt, check=True)

print("All figures rendered successfully.")

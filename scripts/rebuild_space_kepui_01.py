#!/usr/bin/env python3
"""按题干重画 20260903_space_kepui_01 全部程序图。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from program_figure import build_svg, svg_to_png_many

BATCH = Path(__file__).resolve().parents[1] / "data/hermes-batches/2026-09-03/20260903_space_kepui_01"
PUBLIC = Path(__file__).resolve().parents[1] / "public/q-images/20260903_space_kepui_01"
BID = "20260903_space_kepui_01"

Q1_NET = {
    "kind": "cube_net",
    "faces": {"pent": [1, 0], "circle": [0, 1], "plus": [1, 1], "dia": [2, 1], "x": [3, 1], "sq": [1, 2]},
}
Q2_NET = {
    "kind": "cube_net",
    "faces": {"circle": [1, 0], "pent": [0, 1], "sq": [1, 1], "plus": [2, 1], "dia": [3, 1], "x": [1, 2]},
}

JOBS = {
    f"{BID}_01-stem.png": Q1_NET,
    f"{BID}_01-opt-a.png": {"kind": "cube_iso", "marks": {"top": "circle", "south": "dia", "east": "plus"}},
    f"{BID}_01-opt-b.png": {"kind": "cube_iso", "marks": {"top": "circle", "south": "plus", "east": "pent"}},
    f"{BID}_01-opt-c.png": {"kind": "cube_iso", "marks": {"top": "pent", "south": "sq", "east": "circle"}},
    f"{BID}_01-opt-d.png": {"kind": "cube_iso", "marks": {"top": "plus", "south": "x", "east": "circle"}},
    f"{BID}_02-stem.png": Q2_NET,
    f"{BID}_02-opt-a.png": {"kind": "cube_iso", "marks": {"top": "circle", "south": "x", "east": "sq"}},
    f"{BID}_02-opt-b.png": {"kind": "cube_iso", "marks": {"top": "pent", "south": "plus", "east": "sq"}},
    f"{BID}_02-opt-c.png": {"kind": "cube_iso", "marks": {"top": "sq", "south": "dia", "east": "plus"}},
    f"{BID}_02-opt-d.png": {"kind": "cube_iso", "marks": {"top": "circle", "south": "pent", "east": "sq"}},
    f"{BID}_03-stem.png": {
        "kind": "voxels",
        "voxels": [
            [0, 0, 0], [1, 0, 0], [2, 0, 0],
            [0, 1, 0], [1, 1, 0], [0, 2, 0],
            [0, 0, 1], [1, 0, 1], [0, 1, 1],
            [0, 0, 2], [1, 0, 2],
        ],
    },
    f"{BID}_04-stem.png": {
        "kind": "views",
        "left": [[0, 0], [0, 1], [1, 0]],
        "front": [[0, 0], [0, 1], [1, 0]],
        "top": [[0, 0], [1, 0], [0, 1]],
    },
    f"{BID}_05-stem.png": {"kind": "cube_iso", "marks": {}},
    f"{BID}_06-stem.png": {"kind": "lever", "left_slot": 2, "left_n": 3, "ticks": 5},
    f"{BID}_07-stem.png": {"kind": "tank"},
    f"{BID}_08-stem.png": {"kind": "circuit"},
    f"{BID}_09-stem.png": {
        "kind": "food",
        "nodes": [
            ["绿色植物", 540, 70],
            ["鼠", 260, 210],
            ["草食昆虫", 820, 210],
            ["蛇", 200, 370],
            ["青蛙", 880, 370],
            ["鹰", 540, 500],
        ],
        "edges": [[0, 1], [0, 2], [1, 3], [1, 5], [2, 4], [4, 3], [3, 5]],
    },
    f"{BID}_10-stem.png": {"kind": "contour"},
}


def main() -> None:
    dest = BATCH / "images"
    dest.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    pairs = []
    for name, fig in JOBS.items():
        png = dest / name
        svg = png.with_suffix(".svg")
        print("svg", name)
        build_svg(fig).write(svg)
        pairs.append((svg, png))
    svg_to_png_many(pairs)
    for svg, png in pairs:
        shutil.copy2(png, PUBLIC / png.name)
        shutil.copy2(svg, PUBLIC / svg.name)


if __name__ == "__main__":
    main()

"""程序出图题：每个题型族 = 生成器 + 渲染器 + 只看渲染结果的独立判题器 + 解析。

题型族模块约定（见 core.py 顶部说明）。这里只登记题型族、按标签找题型族。
"""

from __future__ import annotations

import importlib

# 模块名按出题价值排：先空间类，再规律类，最后科学推理。
_MODULES = (
    "cube_net",
    "voxel_views",
    "voxel_assembly",
    "voxel_rotation",
    "paper_cut",
    "plane_tiling",
    "cube_section",
    "bw_grid",
    "counting",
    "position",
    "attribute",
    "style_overlay",
)


def families() -> dict:
    """NAME -> 模块。导入失败直接抛错：题型族坏了不能静默跳过。"""
    out = {}
    for name in _MODULES:
        module = importlib.import_module(f"figure_families.{name}")
        out[module.NAME] = module
    return out


def by_tag() -> dict:
    out = {}
    for module in families().values():
        out.setdefault(module.TAG, []).append(module)
    return out

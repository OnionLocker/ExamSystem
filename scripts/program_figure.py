#!/usr/bin/env python3
"""Gemini 只出 figure spec，这里画黑白线稿 PNG。"""

from __future__ import annotations

from pathlib import Path

from figure_lab import (
    CATALOG,
    MARK,
    Svg,
    draw_cube,
    draw_views_grids,
    draw_voxels,
    fig_buoy,
    fig_circuit,
    fig_contour,
    fig_food,
    fig_front,
    fig_force,
    fig_gears,
    fig_lens,
    fig_lever,
    fig_mirror,
    fig_motion,
    fig_pedigree,
    fig_pulley,
    fig_reflex,
    fig_section_abc,
    fig_solid,
    fig_spring,
    fig_st,
    fig_tank,
    fig_tetra,
    fig_vessels,
    iso,
)

CATALOG_FN = {key: fn for _g, key, _t, fn in CATALOG}

ALIAS = {
    "cube_section": "section",
    "cube_stack": "voxels",
    "cube_views": "views",
    "motion_graph": "motion",
    "food_web": "food",
    "reflex_arc": "reflex",
}

PROGRAM_KINDS = set(CATALOG_FN) | set(ALIAS) | {
    "cube_iso",
    "voxels",
    "section",
    "views",
    "cube_net",
}


def is_program_kind(kind: str) -> bool:
    key = ALIAS.get(kind, kind)
    return key in HANDLERS or kind in HANDLERS


def _cells(raw) -> set[tuple[int, int]]:
    out = set()
    for item in raw or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.add((int(item[0]), int(item[1])))
    return out


def _voxels(raw) -> set[tuple[int, int, int]]:
    out = set()
    for item in raw or []:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            out.add((int(item[0]), int(item[1]), int(item[2])))
    return out or {(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)}


def _marks(raw) -> dict:
    allowed = set(MARK)
    if raw is None:
        return {"top": "pent", "south": "circle", "east": "x"}
    if not isinstance(raw, dict):
        return {"top": "pent", "south": "circle", "east": "x"}
    return {k: v for k, v in raw.items() if k in {"top", "south", "east"} and v in allowed}


def draw_cube_iso(fig: dict) -> Svg:
    s = Svg(1000, 560)
    draw_cube(s, 500, 360, 140, _marks(fig.get("marks")))
    return s


def draw_voxels_fig(fig: dict) -> Svg:
    s = Svg(1000, 620)
    draw_voxels(s, _voxels(fig.get("voxels")), 500, 460, 72)
    return s


def draw_net(fig: dict) -> Svg:
    s = Svg(1000, 640)
    cell, ox, oy = 120, 200, 90
    places = fig.get("faces") or {
        "pent": [1, 0],
        "circle": [0, 1],
        "plus": [1, 1],
        "dia": [2, 1],
        "x": [3, 1],
        "sq": [1, 2],
    }
    for kind, pos in places.items():
        if kind not in MARK or not isinstance(pos, (list, tuple)) or len(pos) < 2:
            continue
        c, r = int(pos[0]), int(pos[1])
        x, y = ox + c * cell, oy + r * cell
        s.rect(x, y, cell, cell, sw=2.8)
        MARK[kind](s, [(x, y), (x + cell, y), (x + cell, y + cell), (x, y + cell)])
    return s


def draw_views(fig: dict) -> Svg:
    s = Svg(1100, 540)
    draw_views_grids(
        s,
        _cells(fig.get("left")),
        _cells(fig.get("front")),
        _cells(fig.get("top")),
        _cells(fig.get("left_hatch")),
        _cells(fig.get("front_hatch")),
        _cells(fig.get("top_hatch")),
    )
    return s


def draw_section(fig: dict) -> Svg:
    s = Svg(1000, 580)
    voxels = _voxels(fig.get("voxels"))
    ox, oy, sc = 320, 430, 70
    draw_voxels(s, voxels, ox, oy, sc)
    z = float(fig.get("z") or 0.5)
    xs = [v[0] for v in voxels] or [0]
    ys = [v[1] for v in voxels] or [0]
    cut = [
        iso(min(xs), min(ys), z, ox, oy, sc),
        iso(max(xs) + 1, min(ys), z, ox, oy, sc),
        iso(max(xs) + 1, max(ys) + 1, z, ox, oy, sc),
        iso(min(xs), max(ys) + 1, z, ox, oy, sc),
    ]
    s.polygon(cut, fill="url(#hatch)")
    return s


HANDLERS = {
    "cube_iso": draw_cube_iso,
    "voxels": draw_voxels_fig,
    "cube_stack": draw_voxels_fig,
    "cube_net": draw_net,
    "views": draw_views,
    "cube_views": draw_views,
    "section": draw_section,
    "cube_section": draw_section,
    "section_abc": lambda _f: fig_section_abc(),
    "tetra": lambda _f: fig_tetra(),
    "solid": lambda _f: fig_solid(),
    "lever": fig_lever,
    "pulley": lambda _f: fig_pulley(),
    "circuit": fig_circuit,
    "tank": fig_tank,
    "motion": fig_motion,
    "motion_graph": fig_motion,
    "contour": fig_contour,
    "front": fig_front,
    "food": fig_food,
    "food_web": fig_food,
    "reflex": fig_reflex,
    "pedigree": lambda _f: fig_pedigree(),
    "lens": lambda _f: fig_lens(),
    "vessels": lambda _f: fig_vessels(),
    "buoy": lambda _f: fig_buoy(),
    "force": lambda _f: fig_force(),
    "spring": lambda _f: fig_spring(),
    "gears": lambda _f: fig_gears(),
    "mirror": lambda _f: fig_mirror(),
    "st": fig_st,
}


def build_svg(fig: dict) -> Svg:
    kind = ALIAS.get(str(fig.get("kind") or ""), str(fig.get("kind") or ""))
    fn = HANDLERS.get(kind) or HANDLERS.get(str(fig.get("kind") or ""))
    if fn:
        return fn(fig)
    catalog = CATALOG_FN.get(kind)
    if catalog:
        return catalog()
    raise ValueError(f"unsupported figure kind: {fig.get('kind')}")


PNG_SCALE = 2


def _svg_size(svg: str) -> tuple[int, int]:
    import re

    found = re.search(r'width="(\d+)"[^>]*height="(\d+)"', svg)
    if found:
        return int(found.group(1)), int(found.group(2))
    return 1100, 560


def _shot(page, svg: str, png_path: Path, scale: int) -> None:
    width, height = _svg_size(svg)
    page.set_viewport_size({"width": width + 16, "height": height + 16})
    page.set_content(svg)
    page.locator("svg").screenshot(path=str(png_path), type="png")


def svg_to_png(svg_path: Path, png_path: Path, scale: int = PNG_SCALE) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    svg = svg_path.read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium-browser",
            args=["--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page(device_scale_factor=scale)
        _shot(page, svg, png_path, scale)
        browser.close()


def svg_to_png_many(pairs: list[tuple[Path, Path]], scale: int = PNG_SCALE) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium-browser",
            args=["--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page(device_scale_factor=scale)
        for svg_path, png_path in pairs:
            png_path.parent.mkdir(parents=True, exist_ok=True)
            _shot(page, svg_path.read_text(encoding="utf-8"), png_path, scale)
        browser.close()


def render_program(fig: dict, dest: Path) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    svg_path = dest.with_suffix(".svg")
    build_svg(fig).write(svg_path)
    svg_to_png(svg_path, dest)

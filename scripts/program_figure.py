#!/usr/bin/env python3
"""Gemini 只出 figure spec，这里画黑白线稿 PNG。"""

from __future__ import annotations

import re

from pathlib import Path

from figure_lab import (
    CATALOG,
    MARK,
    Svg,
    draw_cube,
    draw_views_grids,
    draw_voxels,
    fit_iso,
    voxel_corners,
    fig_buoy,
    fig_circuit,
    fig_contour,
    fig_food,
    fig_front,
    fig_breeze,
    fig_earth,
    fig_latlon,
    fig_climate,
    fig_plate,
    fig_compose,
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
    "oblique_section": "section_oblique",
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
    "section_oblique",
    "section_abc_quiz",
    "views",
    "cube_net",
}



def kind_from_kepui_tag(tag: str) -> str:
    """考点决定图种，不因为某张图好画就改考点。"""
    blob = str(tag or "")
    rules = (
        (("锋面",), "front"),
        (("等高",), "contour"),
        (("海陆风",), "breeze"),
        (("自转", "昼夜"), "earth"),
        (("气候",), "climate"),
        (("板块",), "plate"),
        (("区域地理",), "earth"),
        (("反射", "人体调节"), "reflex"),
        (("遗传",), "pedigree"),
        (("食物", "生态"), "food"),
        (("滑轮",), "pulley"),
        (("杠杆",), "lever"),
        (("浮力", "阿基米德", "压强", "容器"), "tank"),
        (("摩擦", "惯性", "木板"), "force"),
        (("受力",), "force"),
        (("运动", "平抛"), "motion"),
        (("电路", "串并", "欧姆", "电功率", "故障"), "circuit"),
    )
    for tokens, kind in rules:
        if any(token in blob for token in tokens):
            return kind
    return ""


def kind_from_stem(stem: str) -> str:
    blob = stem or ""
    rules = (
        (("锋面", "冷锋", "暖锋", "冷气团", "暖气团"), "front"),
        (("海陆风", "海风", "陆风"), "breeze"),
        (("自转", "昼半球", "夜半球"), "earth"),
        (("反射弧", "膝跳"), "reflex"),
        (("电路", "并联", "串联", "电阻"), "circuit"),
        (("杠杆", "钩码", "支点"), "lever"),
        (("食物网",), "food"),
        (("经纬网", "经线", "纬线", "纬线圈"), "latlon"),
        (("等高线",), "contour"),
        (("容器", "圆柱", "浮力", "液面", "压强"), "tank"),
        (("木板", "物块", "摩擦", "惯性"), "force"),
        (("s-t", "v-t", "s/t", "v/t"), "motion"),
        (("气候", "月均温", "降水量", "降水"), "climate"),
    )
    for tokens, kind in rules:
        if any(token in blob for token in tokens):
            return kind
    return ""


def coerce_kepui_figure(stem: str, fig: dict | None, tag: str = "", extra: str = "") -> dict | None:
    blob = str(stem or "").replace("$", "").replace("\\_", "_") + " " + str(extra or "")
    blob = blob.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    blob = re.sub(r"([RLA])\s*_\s*([0-9]+)", r"\1\2", blob)
    base = dict(fig) if isinstance(fig, dict) else {}
    if base.get("elements") or str(base.get("kind") or "") == "compose":
        force_stem = any(token in blob for token in ("水平地面", "拉力")) and "物块" in blob
        if not force_stem:
            base["kind"] = "compose"
            return base
    locked = kind_from_kepui_tag(tag)
    inferred = kind_from_stem(blob)
    if locked:
        inferred = locked
        stem_kind = kind_from_stem(blob)
        if "区域地理" in str(tag or "") and stem_kind in {"latlon", "contour", "climate"}:
            inferred = stem_kind
    elif any(token in blob for token in ("降水", "月均温", "气温")) and "自转" not in blob:
        inferred = "climate"
    old_kind = str(base.get("kind") or "")
    if inferred and old_kind != inferred:
        keep = base.get("file")
        base = {"kind": inferred}
        if keep:
            base["file"] = keep
    elif inferred:
        base["kind"] = inferred
    elif not old_kind:
        return fig if isinstance(fig, dict) else None
    kind = str(base.get("kind") or "")
    if kind == "circuit":
        if "R1" in blob:
            base["left"] = "R1"
            base["right"] = "R2" if "R2" in blob else str(base.get("right") or "R2")
        elif "L1" in blob:
            base["left"] = "L1"
            base["right"] = "L2" if "L2" in blob else str(base.get("right") or "L2")
        if "A1" in blob:
            base["meter"] = "A1"
        if "A2" in blob:
            base["main_meter"] = "A2"
        elif "干路" in blob or re.search(r"电流表\s*A(?!\d)", blob):
            base["main_meter"] = "A"
        if "电压表" not in blob and "伏特表" not in blob:
            base["voltmeter"] = False
        if "U" in blob or "电压保持" in blob:
            base["show_u"] = True
        if "R3" in blob:
            base["r3"] = "R3"
            base["topology"] = "series_parallel"
            base["switches"] = 2
    elif kind == "tank":
        if "甲" in blob and "乙" in blob:
            base["names"] = ["甲", "乙"]
        if "圆柱" in blob:
            base["shape"] = "cylinder"
        if any(token in blob for token in ("上细下粗", "上窄下宽", "锥形")):
            base["shapes"] = ["cylinder", "wide_bottom"]
        obj = next((name for name in ("合金块", "金属块", "铁块", "木块", "小球") if name in blob), "")
        base["object"] = obj
        if not obj:
            base["objects"] = []
        if "细线" in blob:
            base["string"] = True
        found = re.search(r"=\s*(\d+)\s*:\s*(\d+)", blob)
        if found:
            a, b = max(int(found.group(1)), 1), max(int(found.group(2)), 1)
            ra, rb = a ** 0.5, b ** 0.5
            mid = (ra + rb) / 2 or 1
            base["widths"] = [round(ra / mid, 2), round(rb / mid, 2)]
        elif any(token in blob for token in ("底面积相同", "底面积相等", "相同底面积")):
            base["widths"] = [1.0, 1.0]
        hung = any(token in blob for token in ("浸没", "未接触容器底", "悬"))
        sunk = any(token in blob for token in ("沉底", "下沉", "沉至", "沉入"))
        if hung and sunk:
            base["states"] = ["suspend", "sink"]
        elif sunk:
            base["states"] = ["float", "sink"]
    elif kind == "climate":
        if "甲" in blob and "乙" in blob:
            base["names"] = ["甲", "乙"]
            base["pair"] = True
    elif kind == "lever":
        left = re.search(r"左侧第\s*(\d+)\s*格.*?(\d+)\s*个", blob)
        right = re.search(r"右侧第\s*(\d+)\s*格.*?(\d+)\s*个", blob)
        if left:
            base["left_slot"] = int(left.group(1))
            base["left_n"] = int(left.group(2))
        if right:
            base["right_slot"] = int(right.group(1))
            base["right_n"] = int(right.group(2))
        # A force/arm stem may name L1/L2 without drawing hook weights.
        if "钩码" not in blob:
            base.setdefault("left_slot", 2)
            base.setdefault("right_slot", 3)
            base["left_n"] = 0
            base["right_n"] = 0
    elif kind == "front":
        base["front"] = "warm" if "暖锋" in blob else "cold"
    elif kind == "force":
        base["stem"] = stem
        if "传送带" in blob:
            base["conveyor"] = True
        elif "小车" in blob:
            base["cart"] = True
        elif any(token in blob for token in ("地面", "水平地面", "拉力")):
            base["ground"] = True
    elif kind == "breeze":
        names = [token for token in ("甲", "乙", "丙", "丁") if token in blob]
        if names:
            base["names"] = names
        if any(token in blob for token in ("①", "②", "近地面", "高空")):
            base["numbered"] = True
    elif kind == "latlon":
        if "阴影" in blob and "甲" in blob and "乙" in blob:
            base["regions"] = [
                {"name": "甲", "lat0": 20, "lat1": 30, "lon0": 10, "lon1": 20},
                {"name": "乙", "lat0": 40, "lat1": 50, "lon0": 10, "lon1": 20},
            ]
            base["lats"] = [0, 20, 30, 40, 50]
            base["lons"] = [10, 20, 30, 40]
            base.pop("points", None)
        elif "甲" in blob and "乙" in blob:
            base.setdefault("points", [{"name": "甲", "lat": 20, "lon": 30}, {"name": "乙", "lat": 50, "lon": 90}])
    elif kind == "food":
        forest = ["绿色植物", "昆虫", "兔", "鼠", "食虫鸟", "蛇", "鹰"]
        mapping = (
            ("绿色植物", ("绿色植物",)),
            ("农作物", ("农作物",)),
            ("昆虫", ("昆虫", "植食昆虫")),
            ("害虫", ("害虫",)),
            ("兔", ("兔", "野兔")),
            ("鼠", ("鼠",)),
            ("青蛙", ("青蛙",)),
            ("食虫鸟", ("食虫鸟",)),
            ("猫头鹰", ("猫头鹰",)),
            ("蛇", ("蛇",)),
            ("鹰", ("鹰",)),
        )
        names = [label for label, tokens in mapping if any(token in blob for token in tokens)]
        if "绿色植物" not in names and "农作物" not in names and "植物" in blob:
            names.insert(0, "农作物")
        if "青蛙" not in names and "蛙" in blob and "青蛙" not in blob:
            names.insert(names.index("鼠") + 1 if "鼠" in names else len(names), "青蛙")
        if len(names) < 4:
            names = list(forest)
        base["names"] = names
        if set(forest) <= set(names):
            base["names"] = forest
            # 4 chains; 鹰 occupies 3rd and 4th; 鹰/蛇 compete for 鼠 so D is false.
            base["edges"] = [
                (0, 1), (0, 2), (0, 3), (1, 4), (2, 6), (3, 5), (3, 6), (4, 6), (5, 6),
            ]
            base["nodes"] = [
                {"name": "绿色植物", "x": 160, "y": 280},
                {"name": "昆虫", "x": 420, "y": 430},
                {"name": "兔", "x": 420, "y": 120},
                {"name": "鼠", "x": 420, "y": 280},
                {"name": "食虫鸟", "x": 720, "y": 430},
                {"name": "蛇", "x": 720, "y": 280},
                {"name": "鹰", "x": 960, "y": 180},
            ]
    return base

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
    from figure_lab import fit_iso, voxel_corners

    s = Svg(1000, 580)
    voxels = _voxels(fig.get("voxels"))
    z = float(fig.get("z") or 0.5)
    xs = [v[0] for v in voxels] or [0]
    ys = [v[1] for v in voxels] or [0]
    cut3 = [
        (min(xs), min(ys), z),
        (max(xs) + 1, min(ys), z),
        (max(xs) + 1, max(ys) + 1, z),
        (min(xs), max(ys) + 1, z),
    ]
    ox, oy, sc = fit_iso(voxel_corners(voxels) + cut3, (40, 40, 920, 500), pad=28)
    draw_voxels(s, voxels, ox, oy, sc)
    s.polygon([iso(*pt, ox, oy, sc) for pt in cut3], fill="url(#hatch)", w=0)
    for a, b in zip(cut3, cut3[1:] + cut3[:1]):
        s.line(iso(*a, ox, oy, sc), iso(*b, ox, oy, sc), 2.4, dash="10 7")
    return s



def draw_section_oblique(fig: dict) -> Svg:
    from oblique_section import render_svg, sample

    seed = int(fig.get("seed") or 11)
    n = int(fig.get("n") or 10)
    s, _meta = render_svg(*sample(seed, n))
    return s


def draw_abc_section(fig: dict) -> Svg:
    from abc_section import make, render_question
    seed = int(fig.get("seed") or 6)
    n = int(fig.get("n") or 7)
    quiz = make(seed, n)
    return render_question(quiz["voxels"], quiz["abc"], quiz["options"])

HANDLERS = {
    "cube_iso": draw_cube_iso,
    "voxels": draw_voxels_fig,
    "cube_stack": draw_voxels_fig,
    "cube_net": draw_net,
    "views": draw_views,
    "cube_views": draw_views,
    "section": draw_section,
    "cube_section": draw_section,
    "section_oblique": draw_section_oblique,
    "section_abc_quiz": draw_abc_section,
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
    "breeze": fig_breeze,
    "earth": fig_earth,
    "latlon": fig_latlon,
    "climate": fig_climate,
    "plate": fig_plate,
    "food": fig_food,
    "food_web": fig_food,
    "reflex": fig_reflex,
    "pedigree": lambda _f: fig_pedigree(),
    "lens": lambda _f: fig_lens(),
    "vessels": lambda _f: fig_vessels(),
    "buoy": lambda _f: fig_buoy(),
    "force": fig_force,
    "compose": fig_compose,
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

def _ensure_png_min(png_path: Path, min_w: int = 1400, min_h: int = 500) -> None:
    from PIL import Image
    png_path = Path(png_path)
    if not png_path.is_file():
        return
    with Image.open(png_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = max(min_w / max(w, 1), min_h / max(h, 1), 1)
        if scale <= 1:
            return
        out = im.resize((max(min_w, int(w * scale)), max(min_h, int(h * scale))), Image.Resampling.LANCZOS)
    out.save(png_path)




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


def _chromium_exe() -> str:
    exe = Path("/usr/bin/chromium-browser")
    if exe.is_file():
        return str(exe)
    return "chromium-browser"


def _svg_to_png_chromium(svg_path: Path, png_path: Path, scale: int) -> None:
    import subprocess
    import tempfile

    svg = svg_path.read_text(encoding="utf-8")
    width, height = _svg_size(svg)
    html = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    try:
        html.write(svg)
        html.close()
        subprocess.run(
            [
                _chromium_exe(),
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                f"--window-size={width * scale + 32},{height * scale + 32}",
                f"--screenshot={png_path}",
                Path(html.name).resolve().as_uri(),
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )
    finally:
        Path(html.name).unlink(missing_ok=True)


def svg_to_png(svg_path: Path, png_path: Path, scale: int = PNG_SCALE) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _svg_to_png_chromium(svg_path, png_path, scale)
        _ensure_png_min(png_path)
        return

    svg = svg_path.read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_chromium_exe(),
            args=["--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page(device_scale_factor=scale)
        _shot(page, svg, png_path, scale)
        browser.close()
    _ensure_png_min(png_path)


def svg_to_png_many(pairs: list[tuple[Path, Path]], scale: int = PNG_SCALE) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for svg_path, png_path in pairs:
            png_path.parent.mkdir(parents=True, exist_ok=True)
            _svg_to_png_chromium(svg_path, png_path, scale)
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_chromium_exe(),
            args=["--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page(device_scale_factor=scale)
        for svg_path, png_path in pairs:
            png_path.parent.mkdir(parents=True, exist_ok=True)
            _shot(page, svg_path.read_text(encoding="utf-8"), png_path, scale)
        browser.close()


def render_program(fig: dict, dest: Path, png: bool = True) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    svg_path = dest.with_suffix(".svg")
    build_svg(fig).write(svg_path)
    if png:
        svg_to_png(svg_path, dest)

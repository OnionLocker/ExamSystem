#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect 连打失败后换策略：能用程序图种就 render_kind，否则交出一份铺满画布的 compose。"""

from __future__ import annotations

import math

from draw_tools import compose_svg, render_kind
from program_figure import is_program_kind, kind_from_kepui_tag, kind_from_stem

SAFE_RENDER = {
    "breeze", "front", "food", "tank", "force", "cube_net",
    "views", "lever", "pulley", "reflex", "contour",
    "section", "section_oblique", "section_abc_quiz",
}


def infer_kind(request: dict) -> str:
    hint = str(request.get("kind_hint") or "")
    if is_program_kind(hint) and hint != "motion":
        return hint
    blob = " ".join(request.get("tags") or []) + " " + str(request.get("stem") or "")
    if "三点" in blob or "A、B、C" in blob:
        return "section_abc_quiz"
    if "斜切" in blob:
        return "section_oblique"
    if "截面" in blob:
        return "section"
    if any(token in blob for token in ("左视图", "主视图", "俯视图")):
        return "views"
    if "展开" in blob:
        return "cube_net"
    kind = kind_from_kepui_tag(" ".join(request.get("tags") or [])) or kind_from_stem(request.get("stem") or "")
    if kind == "motion" and "平抛" in blob:
        return "projectile"
    return kind


def _lamp(c, name, size=24):
    x, y = c
    return [
        {"type": "circle", "c": [x, y], "r": 22, "w": 2.6},
        {"type": "line", "from": [x - 15, y - 15], "to": [x + 15, y + 15], "w": 2.2},
        {"type": "line", "from": [x + 15, y - 15], "to": [x - 15, y + 15], "w": 2.2},
        {"type": "text", "p": [x, y - 36], "text": name, "size": size},
    ]


def _iso(x, y, z, ox=540.0, oy=400.0, sc=118.0):
    from figure_lab import C30, S30
    return [ox + (x - y) * sc * C30, oy + (x + y) * sc * S30 - z * sc]


def _cube_faces(x, y, z, ox=540.0, oy=400.0, sc=118.0):
    p = {(i, j, k): _iso(x + i, y + j, z + k, ox, oy, sc) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    return {
        "top": [p[0, 0, 1], p[1, 0, 1], p[1, 1, 1], p[0, 1, 1]],
        "east": [p[1, 0, 0], p[1, 1, 0], p[1, 1, 1], p[1, 0, 1]],
        "south": [p[0, 1, 0], p[1, 1, 0], p[1, 1, 1], p[0, 1, 1]],
    }


def _pedigree() -> list[dict]:
    return [
        {"type": "text", "p": [80, 90], "text": "Ⅰ", "size": 28},
        {"type": "text", "p": [80, 250], "text": "Ⅱ", "size": 28},
        {"type": "text", "p": [80, 420], "text": "Ⅲ", "size": 28},
        {"type": "rect", "x": 280, "y": 60, "w": 44, "h": 44},
        {"type": "circle", "c": [430, 82], "r": 22},
        {"type": "line", "from": [324, 82], "to": [408, 82], "w": 2.6},
        {"type": "line", "from": [366, 82], "to": [366, 160], "w": 2.6},
        {"type": "line", "from": [220, 160], "to": [700, 160], "w": 2.6},
        {"type": "line", "from": [240, 160], "to": [240, 220], "w": 2.6},
        {"type": "line", "from": [460, 160], "to": [460, 220], "w": 2.6},
        {"type": "line", "from": [680, 160], "to": [680, 220], "w": 2.6},
        {"type": "rect", "x": 218, "y": 220, "w": 44, "h": 44},
        {"type": "rect", "x": 438, "y": 220, "w": 44, "h": 44, "fill": "#111111"},
        {"type": "circle", "c": [680, 242], "r": 22},
        {"type": "text", "p": [240, 290], "text": "甲", "size": 28},
        {"type": "circle", "c": [560, 242], "r": 22},
        {"type": "line", "from": [482, 242], "to": [538, 242], "w": 2.6},
        {"type": "line", "from": [510, 242], "to": [510, 320], "w": 2.6},
        {"type": "line", "from": [400, 320], "to": [620, 320], "w": 2.6},
        {"type": "line", "from": [420, 320], "to": [420, 380], "w": 2.6},
        {"type": "line", "from": [510, 320], "to": [510, 380], "w": 2.6},
        {"type": "line", "from": [600, 320], "to": [600, 380], "w": 2.6},
        {"type": "rect", "x": 398, "y": 380, "w": 44, "h": 44},
        {"type": "rect", "x": 488, "y": 380, "w": 44, "h": 44, "fill": "#111111"},
        {"type": "circle", "c": [600, 402], "r": 22},
        {"type": "text", "p": [510, 450], "text": "乙", "size": 28},
        {"type": "rect", "x": 860, "y": 60, "w": 200, "h": 200},
        {"type": "text", "p": [960, 90], "text": "图例", "size": 24},
        {"type": "rect", "x": 880, "y": 110, "w": 28, "h": 28},
        {"type": "text", "p": [980, 132], "text": "正常男性", "size": 22},
        {"type": "circle", "c": [894, 168], "r": 14},
        {"type": "text", "p": [980, 176], "text": "正常女性", "size": 22},
        {"type": "rect", "x": 880, "y": 196, "w": 28, "h": 28, "fill": "#111111"},
        {"type": "text", "p": [980, 218], "text": "患病男性", "size": 22},
    ]


def _projectile() -> list[dict]:
    return [
        {"type": "line", "from": [80, 240], "to": [720, 240], "w": 3.4},
        {"type": "line", "from": [80, 240], "to": [80, 500], "w": 2.4},
        {"type": "line", "from": [80, 500], "to": [1040, 500], "w": 2.4},
        {"type": "text", "p": [280, 270], "text": "水平桌面", "size": 24},
        {"type": "circle", "c": [700, 220], "r": 16, "fill": "#111111"},
        {"type": "text", "p": [700, 190], "text": "甲", "size": 28},
        {"type": "line", "from": [700, 220], "to": [780, 260], "w": 2.6, "dash": True},
        {"type": "line", "from": [780, 260], "to": [860, 330], "w": 2.6, "dash": True},
        {"type": "line", "from": [860, 330], "to": [940, 420], "w": 2.6, "dash": True},
        {"type": "line", "from": [940, 420], "to": [1020, 500], "w": 2.6, "dash": True},
        {"type": "circle", "c": [400, 220], "r": 16},
        {"type": "text", "p": [400, 190], "text": "乙", "size": 28},
        {"type": "line", "from": [400, 236], "to": [400, 500], "w": 2.6, "dash": True},
        {"type": "text", "p": [470, 380], "text": "小球", "size": 22},
    ]


def _section() -> list[dict]:
    from figure_lab import fit_iso, voxel_corners

    voxels = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
    occ = set(voxels)
    cut3 = [(0, 0, 0.5), (2, 0, 0.5), (2, 1, 0.5), (1, 1, 0.5), (1, 2, 0.5), (0, 2, 0.5)]
    ox, oy, sc = fit_iso(voxel_corners(voxels) + cut3, (40, 88, 1020, 388), pad=16)
    els = [{"type": "text", "p": [550, 48], "text": "截面", "size": 28}]
    for x, y, z in sorted(occ, key=lambda t: (t[0] + t[1] + t[2])):
        faces = _cube_faces(x, y, z, ox, oy, sc)
        if (x, y + 1, z) not in occ:
            els.append({"type": "polygon", "pts": faces["south"], "fill": "#ffffff", "w": 2.4})
        if (x + 1, y, z) not in occ:
            els.append({"type": "polygon", "pts": faces["east"], "fill": "#ffffff", "w": 2.4})
        if (x, y, z + 1) not in occ:
            els.append({"type": "polygon", "pts": faces["top"], "fill": "#ffffff", "w": 2.4})
    cut = [_iso(*pt, ox, oy, sc) for pt in cut3]
    els.append({"type": "polygon", "pts": cut, "fill": "url(#hatch)", "w": 0})
    for a, b in zip(cut, cut[1:] + cut[:1]):
        els.append({"type": "line", "from": a, "to": b, "w": 3.0, "dash": True})
    els.append({"type": "text", "p": [550, 538], "text": "水平截面用虚线标出", "size": 22})
    return els
def _symmetry() -> list[dict]:
    return [
        {"type": "rect", "x": 50, "y": 40, "w": 1000, "h": 230},
        {"type": "text", "p": [140, 70], "text": "轴对称", "size": 26},
        {"type": "polygon", "pts": [[250, 100], [300, 210], [200, 210]]},
        {"type": "line", "from": [250, 95], "to": [250, 220], "w": 1.6, "dash": True},
        {"type": "rect", "x": 470, "y": 110, "w": 120, "h": 90},
        {"type": "line", "from": [530, 100], "to": [530, 220], "w": 1.6, "dash": True},
        {"type": "circle", "c": [800, 160], "r": 48},
        {"type": "line", "from": [800, 100], "to": [800, 220], "w": 1.6, "dash": True},
        {"type": "rect", "x": 50, "y": 300, "w": 1000, "h": 230},
        {"type": "text", "p": [150, 330], "text": "中心对称", "size": 26},
        {"type": "polygon", "pts": [[220, 360], [280, 380], [260, 450], [200, 430]]},
        {"type": "rect", "x": 500, "y": 360, "w": 70, "h": 50},
        {"type": "rect", "x": 560, "y": 430, "w": 70, "h": 50},
        {"type": "circle", "c": [800, 400], "r": 28},
        {"type": "circle", "c": [860, 460], "r": 28},
    ]


def _open_closed() -> list[dict]:
    return [
        {"type": "rect", "x": 60, "y": 40, "w": 980, "h": 230},
        {"type": "text", "p": [140, 70], "text": "封闭", "size": 26},
        {"type": "circle", "c": [260, 160], "r": 48},
        {"type": "rect", "x": 480, "y": 110, "w": 90, "h": 90},
        {"type": "polygon", "pts": [[760, 100], [830, 210], [690, 210]]},
        {"type": "rect", "x": 60, "y": 300, "w": 980, "h": 230},
        {"type": "text", "p": [140, 330], "text": "开放", "size": 26},
        {"type": "polyline", "pts": [[220, 380], [220, 480], [300, 480], [300, 400]]},
        {"type": "polyline", "pts": [[480, 390], [430, 470], [530, 470], [500, 390]]},
        {"type": "line", "from": [700, 380], "to": [820, 380], "w": 2.6},
        {"type": "line", "from": [700, 380], "to": [700, 470], "w": 2.6},
    ]


def _experiment() -> list[dict]:
    def kit(x: int, title: str, lamp: str) -> list[dict]:
        return [
            {"type": "rect", "x": x, "y": 60, "w": 460, "h": 440},
            {"type": "text", "p": [x + 230, 95], "text": title, "size": 28},
            {"type": "circle", "c": [x + 230, 150], "r": 28},
            {"type": "text", "p": [x + 330, 158], "text": lamp, "size": 22},
            {"type": "line", "from": [x + 230, 178], "to": [x + 230, 250], "w": 2.4},
            {"type": "polygon", "pts": [[x + 170, 320], [x + 230, 230], [x + 290, 320]]},
            {"type": "rect", "x": x + 150, "y": 320, "w": 160, "h": 90},
            {"type": "text", "p": [x + 230, 375], "text": "植物", "size": 22},
            {"type": "line", "from": [x + 360, 240], "to": [x + 360, 360], "w": 2.2},
            {"type": "circle", "c": [x + 360, 372], "r": 10, "fill": "#111111"},
            {"type": "text", "p": [x + 360, 420], "text": "温度计", "size": 20},
        ]
    return kit(50, "甲", "白光") + kit(560, "乙", "红光")


def _circuit() -> list[dict]:
    return [
        {"type": "line", "from": [140, 90], "to": [140, 470], "w": 2.8},
        {"type": "line", "from": [124, 210], "to": [156, 210], "w": 5},
        {"type": "line", "from": [130, 240], "to": [150, 240], "w": 3},
        {"type": "text", "p": [106, 200], "text": "+", "size": 22},
        {"type": "line", "from": [140, 90], "to": [300, 90], "w": 2.8},
        {"type": "circle", "c": [300, 90], "r": 5, "fill": "#111111", "w": 1},
        {"type": "circle", "c": [340, 90], "r": 5, "fill": "#111111", "w": 1},
        {"type": "line", "from": [300, 90], "to": [336, 58], "w": 2.6},
        {"type": "text", "p": [328, 46], "text": "S", "size": 24},
        {"type": "line", "from": [340, 90], "to": [760, 90], "w": 2.8},
        {"type": "line", "from": [140, 470], "to": [760, 470], "w": 2.8},
        {"type": "line", "from": [430, 90], "to": [430, 170], "w": 2.8},
        *_lamp([430, 210], "甲"),
        {"type": "line", "from": [430, 232], "to": [430, 300], "w": 2.8},
        {"type": "text", "p": [490, 348], "text": "断开", "size": 22},
        {"type": "line", "from": [430, 400], "to": [430, 470], "w": 2.8},
        {"type": "line", "from": [760, 90], "to": [760, 170], "w": 2.8},
        *_lamp([760, 210], "乙"),
        {"type": "line", "from": [760, 232], "to": [760, 300], "w": 2.8},
        *_lamp([760, 340], "丙"),
        {"type": "line", "from": [760, 362], "to": [760, 470], "w": 2.8},
    ]


def _earth() -> list[dict]:
    cx, cy, r = 500, 300, 170
    night = []
    for i in range(25):
        ang = math.pi / 2 + i * math.pi / 24
        night.append([cx + r * math.cos(ang), cy + r * math.sin(ang)])
    return [
        {"type": "circle", "c": [cx, cy], "r": r, "w": 3.2},
        {"type": "polygon", "pts": night, "fill": "url(#hatch)"},
        {"type": "line", "from": [cx, cy - r], "to": [cx, cy + r], "w": 2.4, "dash": True},
        {"type": "text", "p": [cx - 72, cy + 8], "text": "夜", "size": 28},
        {"type": "text", "p": [cx + 80, cy - 24], "text": "昼", "size": 28},
        {"type": "text", "p": [cx + 4, cy + 8], "text": "甲", "size": 26},
        {"type": "text", "p": [cx + 82, cy + 36], "text": "乙", "size": 26},
        {"type": "line", "from": [cx - 50, cy - r - 24], "to": [cx + 70, cy - r - 24], "w": 2.8},
        {"type": "polygon", "pts": [[cx + 70, cy - r - 24], [cx + 52, cy - r - 34], [cx + 52, cy - r - 14]], "fill": "#111111"},
        {"type": "text", "p": [cx + 130, cy - r - 28], "text": "自转", "size": 22},
        {"type": "line", "from": [980, 190], "to": [700, 210], "w": 2.6},
        {"type": "polygon", "pts": [[700, 210], [718, 202], [718, 218]], "fill": "#111111"},
        {"type": "line", "from": [980, 260], "to": [700, 270], "w": 2.6},
        {"type": "polygon", "pts": [[700, 270], [718, 262], [718, 278]], "fill": "#111111"},
        {"type": "line", "from": [980, 330], "to": [700, 330], "w": 2.6},
        {"type": "polygon", "pts": [[700, 330], [718, 322], [718, 338]], "fill": "#111111"},
        {"type": "text", "p": [910, 168], "text": "太阳光线", "size": 22},
        {"type": "text", "p": [cx, 540], "text": "地球自转", "size": 24},
    ]


CUSTOM = {
    "circuit": _circuit,
    "earth": _earth,
    "pedigree": _pedigree,
    "projectile": _projectile,
    "section": _section,
    "symmetry": _symmetry,
    "open_closed": _open_closed,
    "experiment": _experiment,
}


def fallback_name(request: dict) -> str:
    kind = infer_kind(request)
    blob = " ".join(request.get("tags") or []) + " " + str(request.get("stem") or "")
    if "轴对称" in blob or "中心对称" in blob:
        return "symmetry"
    if "封闭" in blob and "开放" in blob:
        return "open_closed"
    if "白光" in blob or "红光" in blob or "两套装置" in blob:
        return "experiment"
    if kind == "projectile" or "平抛" in blob:
        return "projectile"
    if kind == "pedigree" or "系谱" in blob or "遗传" in blob:
        return "pedigree"
    if kind == "section" or "截面" in blob:
        return "section"
    return kind


def apply_fallback(request: dict, dest, renderer=None) -> dict:
    name = fallback_name(request)
    if name in CUSTOM:
        compose_svg(CUSTOM[name](), dest, 1100, 560, renderer)
        return {"ok": dest.is_file(), "kind": name, "path": str(dest), "fallback": True}
    if name in SAFE_RENDER:
        params = dict(request.get("params") or {})
        if name == "breeze":
            params.setdefault("breeze", "night")
        if name == "front":
            params.setdefault("front", "cold")
        return {**render_kind(name, params, dest, renderer), "fallback": True}
    return {"ok": False, "kind": name or "compose", "issues": ["没有可用的打回兜底图种"]}

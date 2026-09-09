#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画图 Agent 可调用的本地工具：程序图种、组合图元、像素兜底、本地自检。"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops

from figure_lab import CATALOG
from figure_qa import MIN_H, MIN_W, PLACEHOLDER_FACTS, check_question
from program_figure import is_program_kind, render_program

PIXEL_BLOCKED = {
    "circuit",
    "lever",
    "tank",
    "motion",
    "motion_graph",
    "force",
    "pulley",
    "reflex",
}

Renderer = Callable[[dict, Path], None]
_SPEC_LOCK = threading.Lock()
PixelFn = Callable[[list[str], Path], None]


def list_kinds() -> dict:
    rows = [{"kind": key, "title": title, "group": group} for group, key, title, _fn in CATALOG]
    rows.append({"kind": "compose", "title": "按元素组合线稿", "group": "组合"})
    return {"kinds": rows}


def _clear(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    dest.with_suffix(".svg").unlink(missing_ok=True)


def render_kind(kind: str, params: dict | None, dest: Path, renderer: Renderer | None = None) -> dict:
    kind = str(kind or "").strip()
    if not kind:
        return {"ok": False, "issues": ["未指定 kind"]}
    fig = dict(params or {})
    fig["kind"] = kind
    _clear(dest)
    (renderer or render_program)(fig, dest)
    return {"ok": dest.is_file(), "kind": kind, "path": str(dest)}


def compose_svg(elements: list, dest: Path, width: int = 1100, height: int = 560, renderer: Renderer | None = None) -> dict:
    fig = {
        "kind": "compose",
        "width": int(width or 1100),
        "height": int(height or 560),
        "elements": list(elements or []),
    }
    _clear(dest)
    (renderer or render_program)(fig, dest)
    return {"ok": dest.is_file(), "kind": "compose", "path": str(dest)}


def pixel_draw(facts: list[str], dest: Path, pixel: PixelFn | None = None, kind_hint: str = "") -> dict:
    if is_program_kind(kind_hint) or kind_hint in PIXEL_BLOCKED:
        return {"ok": False, "issues": [f"{kind_hint} 禁止走像素生图，请用 render_kind 或 compose_svg"]}
    if not pixel:
        return {"ok": False, "issues": ["未配置像素渲染器"]}
    _clear(dest)
    pixel([str(item) for item in facts if str(item).strip()], dest)
    return {"ok": dest.is_file(), "kind": "pixel", "path": str(dest)}


def _layout_issues(png: Path) -> list[str]:
    with Image.open(png) as im:
        width, height = im.size
        gray = im.convert("L")
    if width < MIN_W or height < MIN_H:
        return [f"像素过低 {width}x{height}（至少 {MIN_W}x{MIN_H}）"]
    diff = ImageChops.difference(gray, Image.new("L", gray.size, 255))
    bbox = diff.getbbox()
    if not bbox:
        return ["画布是空白的"]
    left, top, right, bottom = bbox
    area = (right - left) * (bottom - top)
    if area < width * height * 0.16:
        return ["图挤在一角，大片空白"]
    if right < width * 0.55 and left < width * 0.12:
        return ["图偏在画布左侧"]
    ink = sum(gray.histogram()[:248])
    if ink < width * height * 0.008:
        return ["图上几乎只有空白和几个字"]
    corner = gray.crop((0, 0, min(40, width), min(40, height)))
    corner_ink = sum(1 for px in corner.getdata() if px < 240)
    if 12 <= corner_ink <= 220:
        band = gray.crop((0, 0, min(90, width), min(90, height)))
        band_ink = sum(1 for px in band.getdata() if px < 240)
        if band_ink < corner_ink * 3:
            return ["左上角有多余残片"]
    return []


def inspect_figure(request: dict, dest: Path, batch_dir: Path | None = None, *, vision: bool | None = None, flash_review=None) -> dict:
    issues: list[str] = []
    if not dest.is_file():
        return {"ok": False, "issues": ["缺图"]}
    try:
        with Image.open(dest) as im:
            im.load()
            size = im.size
    except Exception:
        return {"ok": False, "issues": ["PNG 无法打开"], "stub": True}

    if size[0] < 80 or dest.stat().st_size < 64:
        return {"ok": False, "issues": ["PNG 过小"], "stub": True}

    issues.extend(_layout_issues(dest))
    svg_early = dest.with_suffix(".svg")
    blob_early = svg_early.read_text(encoding="utf-8") if svg_early.is_file() else ""
    if (
        blob_early.count('x="0" y="0"') >= 2
        or blob_early.count('cx="0" cy="0"') >= 2
        or blob_early.count('x1="0" y1="0" x2="0" y2="0"') >= 3
    ):
        issues.append("origin-collapse")
    from figure_qa import _has_cancel_x
    if _has_cancel_x(blob_early):
        issues.append("cancel-x")
    if request.get("kind_locked"):
        issues = list(dict.fromkeys(issues))
        return {"ok": not issues, "issues": issues, "kind": request.get("kind_hint") or ""}
    qid = str(request.get("question_id") or dest.stem)
    question = {
        "external_id": qid,
        "category": request.get("module") or "",
        "tags": list(request.get("tags") or []),
        "stem": request.get("stem") or "",
        "stem_images": [dest.name if batch_dir is None else str(dest.relative_to(batch_dir))],
    }
    root = batch_dir or dest.parent
    spec_path = root / "image-specs.json"
    original = spec_path.read_text(encoding="utf-8") if spec_path.is_file() else None
    rows = []
    if original:
        try:
            parsed = json.loads(original)
            rows = list(parsed.get("questions") or []) if isinstance(parsed, dict) else []
        except json.JSONDecodeError:
            rows = []
    rows = [row for row in rows if str((row or {}).get("question_id")) != qid]
    rows.append(
        {
            "question_id": qid,
            "image_facts": [str(item) for item in (request.get("must_show") or []) if 0 < len(str(item)) <= 12],
            "must_derive": [],
        }
    )
    with _SPEC_LOCK:
        spec_path.write_text(json.dumps({"questions": rows}, ensure_ascii=False), encoding="utf-8")
        try:
            issues.extend(check_question(root, question))
        finally:
            if original is None:
                spec_path.unlink(missing_ok=True)
            else:
                spec_path.write_text(original, encoding="utf-8")

    svg = dest.with_suffix(".svg")
    blob = svg.read_text(encoding="utf-8") if svg.is_file() else ""
    labels = " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", blob))
    if (
        blob.count('x="0" y="0"') >= 2
        or blob.count('cx="0" cy="0"') >= 2
        or blob.count('x1="0" y1="0" x2="0" y2="0"') >= 3
    ):
        issues.append("图元坐标落在原点，请用 [x,y] 数组重画并铺满画布")
    for token in request.get("must_show") or []:
        if token in PLACEHOLDER_FACTS or token in PLACEHOLDER_SKIP:
            continue
        hay = labels or blob
        if len(token) > 4 or any(ch in token for ch in "为的是在与向示，。、"):
            continue
        if token not in hay and token not in str(request.get("stem") or ""):
            if hay and token not in hay:
                issues.append(f"清单有 {token}，图上没有")
    for token in request.get("must_not") or []:
        if token and token in (labels or ""):
            issues.append(f"禁止出现 {token}，图上有")
    if request.get("need_dash") and "stroke-dasharray" not in blob:
        issues.append("题干有虚线，图上没有")
    issues = list(dict.fromkeys(issues))
    if not issues:
        if vision is None:
            vision = os.environ.get("DRAW_FLASH_QA", "0") == "1"
        if vision:
            reviewer = flash_review
            if reviewer is None:
                from figure_flash_qa import review_figure_issues as reviewer
            issues.extend(reviewer(request, dest))
            issues = list(dict.fromkeys(issues))
    return {"ok": not issues, "issues": issues, "kind": request.get("kind_hint") or ""}


PLACEHOLDER_SKIP = {"程序绘制的图形", "题干图", "程序图形中的可见结构与标号"}

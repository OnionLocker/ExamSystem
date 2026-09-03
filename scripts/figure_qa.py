#!/usr/bin/env python3
"""程序作图本地质检：看得清、对得上题干、清单里的元素在图上。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

MIN_W = 1400
MIN_H = 500
MIN_FONT = 20
PLACEHOLDER_FACTS = {"程序绘制的图形", "题干图"}
NAMED = (
    "木块",
    "铁块",
    "钩码",
    "冷气团",
    "暖气团",
    "雨区",
    "薄壁容器",
    "水平桌面",
    "感受器",
    "传入神经",
    "神经中枢",
    "传出神经",
    "效应器",
    "反射弧",
)
FACT_TOKEN_RE = re.compile(
    r"甲|乙|丙|丁|"
    r"[①②③④⑤⑥⑦⑧⑨⑩]|"
    r"L[₁₂12]|R[₁₂12]|A1|"
    + "|".join(NAMED + ("小球",))
)
NEG_SPAN_RE = re.compile(r"不(?:出现|写|标|画)\s*([\u4e00-\u9fff、,/]{1,30})")
LEAK_WORDS = (
    "冷锋",
    "暖锋",
    "感受器",
    "传入神经",
    "神经中枢",
    "传出神经",
    "效应器",
)
COORD_RE = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)")
RANGE_RE = re.compile(r"范围\s*(\d+(?:\.\d+)?)\s*至\s*(\d+(?:\.\d+)?)")
TEQ_RE = re.compile(r"t\s*=\s*(\d+(?:\.\d+)?)")
AXIS_RE = re.compile(r"t/s|s/m|v/t|s-t|v-t")
NUM_LABEL_RE = re.compile(r">\s*(\d+(?:\.\d+)?)\s*<")
POLYLINE_RE = re.compile(r'<polyline points="([^"]+)"')
EXTRA_LABELS = (
    "铁块",
    "木块",
    "钩码",
    "草",
    "兔",
    "虫",
    "狐",
    "鸟",
    "小球",
    "感受器",
    "传入神经",
    "神经中枢",
    "传出神经",
    "效应器",
)


def _images(question: dict) -> list[str]:
    rels = [str(v) for v in question.get("stem_images") or []]
    rels.extend(str(v) for v in question.get("explanation_images") or [])
    for option in question.get("options") or []:
        rels.extend(str(v) for v in option.get("images") or [])
    return rels


def _svg_text(batch_dir: Path, rel: str) -> str:
    svg = (batch_dir / rel).with_suffix(".svg")
    if not svg.is_file():
        return ""
    return svg.read_text(encoding="utf-8")


def _spec_map(batch_dir: Path) -> dict[str, dict]:
    path = batch_dir / "image-specs.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("questions") if isinstance(raw, dict) else raw
    return {str(item.get("question_id")): item for item in items or [] if isinstance(item, dict)}


def _facts(spec: dict | None) -> str:
    if not spec:
        return ""
    parts = list(spec.get("image_facts") or []) + list(spec.get("image_only_facts") or [])
    return " ".join(str(item) for item in parts)


def _usable_facts(spec: dict | None) -> list[str]:
    if not spec:
        return []
    rows = [str(item).strip() for item in (spec.get("image_facts") or []) + (spec.get("image_only_facts") or [])]
    return [row for row in rows if row and row not in PLACEHOLDER_FACTS]


def _canon_num(value: str) -> str:
    number = float(value)
    if number == int(number):
        return str(int(number))
    return value


def _required_ticks(facts: str) -> list[str]:
    found: list[str] = []
    for match in COORD_RE.finditer(facts):
        found.extend(match.groups())
    for match in RANGE_RE.finditer(facts):
        found.extend(match.groups())
    for match in TEQ_RE.finditer(facts):
        found.append(match.group(1))
    out: list[str] = []
    for item in found:
        token = _canon_num(item)
        if token not in out:
            out.append(token)
    return out


def _polyline_pts(svg: str) -> list[list[tuple[float, float]]]:
    lines = []
    for match in POLYLINE_RE.finditer(svg):
        pts = []
        for pair in match.group(1).split():
            if "," not in pair:
                continue
            x, y = pair.split(",", 1)
            pts.append((float(x), float(y)))
        if len(pts) >= 2:
            lines.append(pts)
    return lines


def _orient(a, b, c) -> int:
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(value) < 1e-6:
        return 0
    return 1 if value > 0 else -1


def _on_seg(a, b, c) -> bool:
    return (
        min(a[0], b[0]) - 1e-6 <= c[0] <= max(a[0], b[0]) + 1e-6
        and min(a[1], b[1]) - 1e-6 <= c[1] <= max(a[1], b[1]) + 1e-6
    )


def _seg_hit(a, b, c, d) -> bool:
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_seg(a, b, c):
        return True
    if o2 == 0 and _on_seg(a, b, d):
        return True
    if o3 == 0 and _on_seg(c, d, a):
        return True
    if o4 == 0 and _on_seg(c, d, b):
        return True
    return False


def _polylines_cross(svg: str) -> bool:
    lines = _polyline_pts(svg)
    for i, left in enumerate(lines):
        for right in lines[i + 1 :]:
            for a, b in zip(left, left[1:]):
                for c, d in zip(right, right[1:]):
                    if _seg_hit(a, b, c, d):
                        return True
    return False


def _is_kepui(question: dict) -> bool:
    blob = " ".join(
        [
            str(question.get("category") or ""),
            str(question.get("sub_category") or ""),
            " ".join(str(value) for value in question.get("tags") or []),
        ]
    )
    return "科学推理" in blob


def _spec_issues(qid: str, stem: str, blob: str, question: dict, spec: dict | None) -> list[str]:
    issues: list[str] = []
    facts = _facts(spec)
    usable = _usable_facts(spec)
    if _is_kepui(question):
        if spec is None:
            issues.append(f"{qid}: 缺 image-specs，无法做图–清单校验")
            return issues
        if not usable:
            issues.append(f"{qid}: image_facts 未写清图上必现元素")
    if not facts:
        return issues
    forbidden = []
    for span in NEG_SPAN_RE.finditer(facts):
        forbidden.extend(FACT_TOKEN_RE.findall(span.group(0)))
    forbidden = list(dict.fromkeys(forbidden))
    positive = NEG_SPAN_RE.sub(" ", facts)
    missing = [
        token
        for token in dict.fromkeys(FACT_TOKEN_RE.findall(positive))
        if token not in blob and token not in forbidden
    ]
    if missing:
        issues.append(f"{qid}: 清单有 { '、'.join(missing) }，图上没有")
    for token in forbidden:
        if token in blob:
            issues.append(f"{qid}: 清单禁止写「{token}」，图上有")
    for axis in AXIS_RE.findall(facts):
        if axis not in blob:
            issues.append(f"{qid}: 清单有坐标轴 {axis}，图上没有")
    ticks = _required_ticks(facts)
    if ticks:
        labels = {_canon_num(item) for item in NUM_LABEL_RE.findall(blob)}
        absent = [item for item in ticks if item not in labels]
        if absent:
            issues.append(f"{qid}: 清单要求刻度 { '、'.join(absent) }，图上没有")
    if any(token in facts for token in ("相交", "交于", "交点")) and not _polylines_cross(blob):
        issues.append(f"{qid}: 清单要求交点，图上折线不相交")
    if "圆柱" in facts or "圆柱" in stem:
        if "<ellipse" not in blob:
            issues.append(f"{qid}: 清单/题干是圆柱容器，图上没有椭圆")
    derive = " ".join(str(item) for item in (spec.get("must_derive") or []))
    for token in LEAK_WORDS:
        if token in derive and token in blob:
            issues.append(f"{qid}: 图上写了 must_derive 的「{token}」")
    allowed = facts + stem
    for label in EXTRA_LABELS:
        if label in blob and label not in allowed:
            issues.append(f"{qid}: 图上多了清单/题干没有的「{label}」")
    return issues


def check_question(batch_dir: Path, question: dict) -> list[str]:
    qid = str(question.get("external_id") or "?")
    stem = str(question.get("stem") or "")
    issues: list[str] = []
    blob = ""
    for rel in _images(question):
        png = batch_dir / rel
        if not png.is_file():
            issues.append(f"{qid}: 缺图 {rel}")
            continue
        with Image.open(png) as im:
            width, height = im.size
        if width < MIN_W or height < MIN_H:
            issues.append(f"{qid}: 像素过低 {width}x{height}（至少 {MIN_W}x{MIN_H}）")
        svg = _svg_text(batch_dir, rel)
        blob += svg
        for size in re.findall(r'font-size="(\d+)"', svg):
            if int(size) < MIN_FONT:
                issues.append(f"{qid}: 字号 {size} 过小（至少 {MIN_FONT}）")
                break
    if "甲" in stem and "乙" in stem and ("甲" not in blob or "乙" not in blob):
        issues.append(f"{qid}: 题干有甲乙，图上没有")
    if "虚线" in stem and "stroke-dasharray" not in blob:
        issues.append(f"{qid}: 题干有虚线，图上没有")
    if "左视图" in stem and "左视图" not in blob:
        issues.append(f"{qid}: 题干有左视图，图上没有标注")
    if any(token in stem for token in ("L₁", "L1", "L₂", "L2")) and "L" not in blob:
        issues.append(f"{qid}: 题干有灯号，图上没有 L")
    if ("旋转" in stem or "折叠" in stem) and "展开" not in stem:
        issues.append(f"{qid}: 空间旋转/折叠题必须给展开图（六个面）")
    tags = " ".join(str(value) for value in question.get("tags") or [])
    front_stem = any(token in stem or token in tags for token in ("锋面", "冷锋", "暖锋", "气团"))
    contour_fig = "等高线" in blob or "等高距" in blob
    if front_stem and contour_fig:
        issues.append(f"{qid}: 锋面题配了等高线图")
    if front_stem and "冷气团" not in blob and "暖气团" not in blob:
        issues.append(f"{qid}: 锋面题图上没有气团标注")
    if "剖面" in stem and contour_fig and "锋" not in blob:
        issues.append(f"{qid}: 剖面题配了平面等高线图")
    if ("等高线" in stem or "等高距" in stem) and "等高" not in blob:
        issues.append(f"{qid}: 等高线题图上没有等高标注")
    spec = _spec_map(batch_dir).get(qid)
    facts = _facts(spec)
    reflex = "反射弧" in stem or "反射弧" in tags or "①" in facts
    if reflex:
        if not any(mark in blob for mark in "①②③④⑤"):
            issues.append(f"{qid}: 反射弧题图上没有①–⑤")
        if any(name in blob for name in ("草", "兔", "狐", "虫", "鸟")):
            issues.append(f"{qid}: 反射弧题配了食物网")
    issues.extend(_spec_issues(qid, stem, blob, question, spec))
    return issues


def check_batch(batch_dir: Path, questions: list[dict]) -> list[str]:
    issues: list[str] = []
    for question in questions:
        issues.extend(check_question(batch_dir, question))
    return issues

#!/usr/bin/env python3
"""讲解示意图：按模板把 JSON 规格渲染成 SVG，供 Hermes 在回答里用 Markdown 图片引用。

用法：
  python3 scripts/draw_diagram.py --spec-file spec.json
  python3 scripts/draw_diagram.py <<'EOF'
  {"template": "venn3", ...}
  EOF

成功时输出 {"ok": true, "markdown": "![...](/q-images/diagrams/...svg)", ...}；
数字自相矛盾或规格错误时输出 {"ok": false, "errors": [...]}，退出码 1，不出图。
模板与字段见 hermes-skills/gd-gongkao-coach/references/diagram-drawing.md。
"""
import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from fractions import Fraction
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "public" / "q-images" / "diagrams"
URL_PREFIX = "/q-images/diagrams"

FONT = ("'PingFang SC','Microsoft YaHei','Noto Sans CJK SC','Noto Sans CJK JP','Source Han Sans SC',"
        "'Droid Sans Fallback',sans-serif")
INK = "#1a1a1a"
INK_SOFT = "#6b5428"
MUTED = "#8a7a5c"
LINE = "#c4aa6a"
PAPER = "#fbf5e8"
FRAME = "#fffaf1"
ROLE = {  # 区域角色 -> (填充, 文字色)
    "base": ("#efe0bc", INK),
    "given": ("#dfb86a", INK),
    "key": ("#c9794a", "#fffaf0"),
    "answer": ("#9a7346", "#fffaf0"),
    "dim": ("#f7efdc", MUTED),
}
ROLE_LABEL = {"given": "题目给的", "key": "关键量", "answer": "所求"}


class SpecError(Exception):
    pass


def text_width(s, size):
    return sum(size if ord(ch) > 0x2E7F else size * 0.6 for ch in str(s))


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    return None


def fmt(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def svg_text(x, y, s, size=15, weight=400, color=INK, anchor="middle"):
    lines = str(s).split("\n")
    lh = size * 1.3
    y0 = y - (len(lines) - 1) * lh / 2
    out = []
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{x:.1f}" y="{y0 + i * lh:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}" text-anchor="{anchor}" dominant-baseline="central">{escape(line)}</text>'
        )
    return "".join(out)


def region(spec_regions, key):
    """区域可写成数字、字符串或 {v, text, role}。返回 (数值或None, 显示文字, 角色)。"""
    raw = spec_regions.get(key)
    if raw is None:
        return None, "", "base"
    if isinstance(raw, dict):
        v = num(raw.get("v"))
        text = raw.get("text")
        if text is None:
            text = fmt(raw["v"]) if raw.get("v") is not None else ""
        role = raw.get("role", "base")
    else:
        v = num(raw)
        text = fmt(raw)
        role = "base"
    if role not in ROLE:
        raise SpecError(f"区域 {key} 的 role 只能是 {sorted(ROLE)}，收到 {role!r}")
    return v, str(text), role


def header(spec, width):
    parts, y = [], 0
    if spec.get("title"):
        y += 34
        parts.append(svg_text(width / 2, y - 6, spec["title"], 20, 700, INK))
    if spec.get("subtitle"):
        y += 24
        parts.append(svg_text(width / 2, y - 6, spec["subtitle"], 14, 400, INK_SOFT))
    return "".join(parts), (y + 14 if y else 16)


def footer(spec, width, y):
    notes = spec.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    if len(notes) > 3:
        raise SpecError("notes 最多 3 行，讲解放到正文里")
    parts = []
    for i, line in enumerate(notes):
        parts.append(svg_text(width / 2, y + 14 + i * 24, line, 15, 700 if i == 0 else 400,
                              INK if i == 0 else INK_SOFT))
    return "".join(parts), y + (len(notes) * 24 + 20 if notes else 8)


def legend(roles_used, width, y):
    items = [r for r in ("given", "key", "answer") if r in roles_used]
    if not items:
        return "", y
    widths = [18 + text_width(ROLE_LABEL[r], 13) + 22 for r in items]
    x = (width - sum(widths)) / 2
    parts = []
    for r, w in zip(items, widths):
        parts.append(f'<rect x="{x:.1f}" y="{y - 6:.1f}" width="12" height="12" rx="3" '
                     f'fill="{ROLE[r][0]}" stroke="{INK}" stroke-width="0.8"/>')
        parts.append(svg_text(x + 18, y, ROLE_LABEL[r], 13, 400, INK_SOFT, "start"))
        x += w
    return "".join(parts), y + 22


def wrap(width, height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" height="{height:.0f}" font-family="{FONT}">'
            f'<rect width="100%" height="100%" rx="14" fill="{PAPER}"/>{body}</svg>')


# ---------------- 韦恩图（两集合 / 三集合共用的绘制） ----------------
def venn(spec, circles, label_pos, name_pos, keys, width, frame_box):
    """circles: {集合字母: (cx, cy, r)}；keys: 区域键 -> 所在集合字母串。"""
    regions = spec.get("regions") or {}
    unknown = set(regions) - set(keys) - {"none"}
    if unknown:
        raise SpecError(f"未知区域 {sorted(unknown)}，可用：{sorted(keys) + ['none']}")
    head, top = header(spec, width)
    dy = top
    defs, paint, labels, roles = [], [], [], set()
    letters = list(circles)
    for k in letters:
        cx, cy, r = circles[k]
        defs.append(f'<clipPath id="in{k}"><circle cx="{cx}" cy="{cy + dy}" r="{r}"/></clipPath>')
    for key, inside in keys.items():
        outside = [k for k in letters if k not in inside]
        mid = "x".join(outside) or "none"
        if outside and f'id="out{mid}"' not in "".join(defs):
            holes = "".join(f'<circle cx="{circles[k][0]}" cy="{circles[k][1] + dy}" r="{circles[k][2]}" '
                            f'fill="black"/>' for k in outside)
            defs.append(f'<mask id="out{mid}"><rect width="{width}" height="2000" fill="white"/>{holes}</mask>')
        v, text, role = region(regions, key)
        roles.add(role)
        fill, color = ROLE[role]
        shape = f'<rect width="{width}" height="2000" fill="{fill}"' + (
            f' mask="url(#out{mid})"/>' if outside else "/>")
        for k in reversed(inside):
            shape = f'<g clip-path="url(#in{k})">{shape}</g>'
        paint.append(shape)
        if text:
            x, y = label_pos[key]
            labels.append(svg_text(x, y + dy, text, 15, 700 if role != "base" else 500, color))
    rings = "".join(f'<circle cx="{cx}" cy="{cy + dy}" r="{r}" fill="none" stroke="{INK}" stroke-width="1.8"/>'
                    for cx, cy, r in circles.values())
    names = spec.get("names") or {}
    for k in letters:
        x, y, anchor = name_pos[k]
        labels.append(svg_text(x, y + dy, names.get(k, k), 15, 700, INK, anchor))
    fx, fy, fw, fh = frame_box
    frame = ""
    v_none, t_none, role_none = region(regions, "none")
    total = spec.get("total")
    if t_none or total is not None:
        frame = (f'<rect x="{fx}" y="{fy + dy}" width="{fw}" height="{fh}" rx="10" fill="{FRAME}" '
                 f'stroke="{LINE}" stroke-width="1.2"/>')
        if t_none:
            roles.add(role_none)
            labels.append(svg_text(fx + 14, fy + dy + fh - 18, f"都不 {t_none}" if num(regions.get("none")) is not None
                                   else t_none, 14, 500, INK_SOFT, "start"))
        if total is not None:
            labels.append(svg_text(fx + fw - 14, fy + dy + fh - 18, f"全集 {fmt(total)}", 14, 500, INK_SOFT, "end"))
    y = fy + dy + fh + 18
    leg, y = legend(roles, width, y)
    foot, y = footer(spec, width, y)
    body = f'<defs>{"".join(defs)}</defs>{head}{frame}{"".join(paint)}{rings}{"".join(labels)}{leg}{foot}'
    return wrap(width, y + 6, body)


def check_sets(spec, keys, letters):
    regions = spec.get("regions") or {}
    vals = {k: region(regions, k)[0] for k in keys}
    errors = []
    sets = spec.get("sets") or {}
    for s, expect in sets.items():
        if s not in letters:
            errors.append(f"sets 里只能写 {letters}，收到 {s}")
            continue
        parts = [vals[k] for k, inside in keys.items() if s in inside]
        if num(expect) is not None and all(p is not None for p in parts):
            got = sum(parts)
            if not math.isclose(got, expect):
                detail = " + ".join(f"{k}={fmt(vals[k])}" for k, inside in keys.items() if s in inside)
                errors.append(f"集合 {s}：{detail} = {fmt(got)}，但题目给的是 {fmt(expect)}")
    total = spec.get("total")
    v_none = region(regions, "none")[0]
    if num(total) is not None and all(v is not None for v in vals.values()) and v_none is not None:
        got = sum(vals.values()) + v_none
        if not math.isclose(got, total):
            errors.append(f"七/四块区域加都不 = {fmt(got)}，但全集是 {fmt(total)}")
    for k, v in vals.items():
        if v is not None and v < 0:
            errors.append(f"区域 {k} = {fmt(v)} 是负数")
    return errors


def draw_venn2(spec):
    keys = {"a": "A", "b": "B", "ab": "AB"}
    r = 110
    circles = {"A": (250, 160, r), "B": (390, 160, r)}
    label_pos = {"a": (195, 160), "b": (445, 160), "ab": (320, 160)}
    name_pos = {"A": (190, 30, "middle"), "B": (450, 30, "middle")}
    return draw_with_check(spec, keys, "AB", lambda: venn(
        spec, circles, label_pos, name_pos, keys, 640, (40, 4, 560, 316)))


def draw_venn3(spec):
    keys = {"a": "A", "b": "B", "c": "C", "ab": "AB", "ac": "AC", "bc": "BC", "abc": "ABC"}
    r, cx, ay = 110, 320, 130
    circles = {"A": (cx, ay, r), "B": (cx - 62, ay + 110, r), "C": (cx + 62, ay + 110, r)}
    label_pos = {
        "a": (cx, ay - 58), "b": (cx - 122, ay + 150), "c": (cx + 122, ay + 150),
        "ab": (cx - 52, ay + 30), "ac": (cx + 52, ay + 30), "bc": (cx, ay + 160), "abc": (cx, ay + 82),
    }
    name_pos = {"A": (cx + 108, ay - 98, "start"), "B": (cx - 175, ay + 222, "end"),
                "C": (cx + 175, ay + 222, "start")}
    return draw_with_check(spec, keys, "ABC", lambda: venn(
        spec, circles, label_pos, name_pos, keys, 640, (30, ay - 118, 580, 400)))


def draw_with_check(spec, keys, letters, render):
    errors = check_sets(spec, keys, letters)
    if errors:
        raise SpecError("；".join(errors))
    return render()


# ---------------- 分段条形图（反向极值、比例、工程分量） ----------------
def draw_bar(spec):
    segs = spec.get("segments") or []
    if not segs:
        raise SpecError("bar 需要 segments：[{label, value, role}]")
    total = spec.get("total")
    vals = [num(s.get("value")) for s in segs]
    if any(v is None or v < 0 for v in vals):
        raise SpecError("bar 的每段 value 必须是非负数字")
    used = sum(vals)
    if total is None:
        total = used
    if used > total + 1e-9:
        raise SpecError(f"各段合计 {fmt(used)} 超过总量 {fmt(total)}")
    rest = spec.get("rest")
    if rest and total - used > 1e-9:
        segs = segs + [{"label": rest.get("label", "剩余"), "value": total - used, "role": rest.get("role", "answer")}]
    width, x0, bar_w, bar_h = 760, 40, 680, 74
    head, top = header(spec, width)
    brackets = spec.get("brackets") or []
    y_bar = top + (40 if brackets else 8)
    scale = bar_w / total
    parts, roles, x = [head], set(), x0
    below = []
    offsets = []
    for s in segs:
        v = num(s["value"])
        role = s.get("role", "base")
        if role not in ROLE:
            raise SpecError(f"段 {s.get('label')} 的 role 只能是 {sorted(ROLE)}")
        roles.add(role)
        w = v * scale
        fill, color = ROLE[role]
        parts.append(f'<rect x="{x:.1f}" y="{y_bar}" width="{w:.1f}" height="{bar_h}" fill="{fill}" '
                     f'stroke="{INK}" stroke-width="1.2"/>')
        label = str(s.get("label", ""))
        value_text = s.get("text", "" if re.search(rf"(?<!\d){re.escape(fmt(v))}(?!\d)", label) else fmt(v))
        text = f"{label}\n{value_text}".strip()
        need = max(text_width(t, 14) for t in text.split("\n")) + 10
        if need <= w:
            parts.append(svg_text(x + w / 2, y_bar + bar_h / 2, text, 14, 700 if role != "base" else 500, color))
        else:
            below.append((x + w / 2, text.replace("\n", " ")))
        offsets.append(x)
        x += w
    offsets.append(x)
    y = y_bar + bar_h
    tick = [0.0]
    for v in vals:
        tick.append(tick[-1] + v)
    for i, b in enumerate(brackets):
        a = x0 + num(b.get("from", 0)) * scale
        e = x0 + num(b.get("to", total)) * scale
        by = y_bar - 14 - i * 26 if b.get("side", "top") == "top" else None
        if by is None:
            continue
        parts.append(f'<path d="M{a:.1f} {by + 6} V{by} H{e:.1f} V{by + 6}" fill="none" stroke="{INK_SOFT}" '
                     f'stroke-width="1.2"/>')
        parts.append(svg_text((a + e) / 2, by - 11, b.get("label", ""), 13, 500, INK_SOFT))
    for i, (cx, t) in enumerate(below):
        ly = y + 16 + i * 20
        parts.append(f'<path d="M{cx:.1f} {y} V{ly - 7}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(svg_text(cx, ly, t, 13, 500, INK_SOFT))
    y += (len(below) * 20 + 14) if below else 8
    if spec.get("total_label", True):
        label = spec["total_label"] if isinstance(spec.get("total_label"), str) else f"总量 {fmt(total)}"
        parts.append(f'<path d="M{x0} {y} V{y + 10} M{x0} {y + 5} H{x0 + bar_w} M{x0 + bar_w} {y} V{y + 10}" '
                     f'fill="none" stroke="{INK_SOFT}" stroke-width="1.2"/>')
        parts.append(svg_text(x0 + bar_w / 2, y + 24, label, 13, 500, INK_SOFT))
        y += 44
    leg, y = legend(roles, width, y + 4)
    foot, y = footer(spec, width, y)
    parts += [leg, foot]
    return wrap(width, y + 6, "".join(parts))


# ---------------- 线段图（行程、年龄、相对位置） ----------------
def draw_line(spec):
    length = num(spec.get("length"))
    if not length or length <= 0:
        raise SpecError("line 需要正数 length（全程或数轴长度）")
    points = spec.get("points") or []
    arrows = spec.get("arrows") or []
    width, x0, track = 760, 60, 640
    head, top = header(spec, width)
    up = max([a.get("row", 1) for a in arrows if a.get("row", 1) > 0] or [0])
    down = -min([a.get("row", 1) for a in arrows if a.get("row", 1) < 0] or [0])
    y_line = top + 20 + up * 34
    sx = lambda v: x0 + num(v) / length * track
    parts, roles = [head], set()
    parts.append(f'<line x1="{x0}" y1="{y_line}" x2="{x0 + track}" y2="{y_line}" stroke="{INK}" stroke-width="2.4"/>')
    for p in points:
        at = num(p.get("at"))
        if at is None or not 0 <= at <= length:
            raise SpecError(f"点 {p.get('label')} 的 at 必须在 0~{fmt(length)}")
        x = sx(at)
        parts.append(f'<line x1="{x:.1f}" y1="{y_line - 7}" x2="{x:.1f}" y2="{y_line + 7}" stroke="{INK}" '
                     f'stroke-width="2"/>')
        parts.append(svg_text(x, y_line + 20, p.get("label", ""), 14, 700, INK))
    parts.append('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                 f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{INK_SOFT}"/></marker></defs>')
    for a in arrows:
        f, t = num(a.get("from")), num(a.get("to"))
        if f is None or t is None:
            raise SpecError("arrow 需要数字 from / to")
        role = a.get("role", "base")
        if role not in ROLE:
            raise SpecError(f"箭头 {a.get('label')} 的 role 只能是 {sorted(ROLE)}")
        roles.add(role)
        row = a.get("row", 1)
        y = y_line - row * 34 if row > 0 else y_line + 22 - row * 30
        color = ROLE[role][0] if role != "base" else INK_SOFT
        parts.append(f'<rect x="{min(sx(f), sx(t)):.1f}" y="{y - 3}" width="{abs(sx(t) - sx(f)):.1f}" height="6" '
                     f'rx="3" fill="{color}"/>')
        parts.append(f'<line x1="{sx(f):.1f}" y1="{y}" x2="{sx(t):.1f}" y2="{y}" stroke="{INK_SOFT}" '
                     f'stroke-width="1.2" marker-end="url(#ah)"/>')
        ty = y - 14 if row > 0 else y + 15
        parts.append(svg_text((sx(f) + sx(t)) / 2, ty, a.get("label", ""), 13, 500, INK_SOFT))
    y = y_line + 44 + down * 30 + (14 if down else 0)
    leg, y = legend(roles, width, y)
    foot, y = footer(spec, width, y)
    parts += [leg, foot]
    return wrap(width, y + 6, "".join(parts))


# ---------------- 通用小件 ----------------
def item(raw, where):
    """元素可写成字符串/数字或 {text, role}。返回 (文字, 角色)。"""
    if isinstance(raw, dict):
        text, role = str(raw.get("text", "")), raw.get("role", "base")
    else:
        text, role = ("" if raw is None else fmt(raw)), "base"
    if role not in ROLE:
        raise SpecError(f"{where} 的 role 只能是 {sorted(ROLE)}，收到 {role!r}")
    return text, role


def box(x, y, w, h, role, rx=8, stroke=INK, sw=1.4):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{ROLE[role][0]}" stroke="{stroke}" stroke-width="{sw}"/>')


def finish(spec, parts, roles, width, y):
    leg, y = legend(roles if spec.get("legend", True) else set(), width, y)
    foot, y = footer(spec, width, y)
    return wrap(width, y + 6, "".join(parts) + leg + foot)


ARROW_DEF = ('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
             f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{INK_SOFT}"/></marker></defs>')


def to_fraction(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return Fraction(v).limit_denominator(1000)
    s = str(v).strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*%", s)
    if m:
        return Fraction(m.group(1)) / 100
    m = re.fullmatch(r"(-?\d+)\s*/\s*(\d+)", s)
    if m and int(m.group(2)):
        return Fraction(int(m.group(1)), int(m.group(2)))
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None


# ---------------- slots 格子与位置（排列组合） ----------------
def draw_slots(spec):
    items = spec.get("items") or []
    n = len(items)
    if not 1 <= n <= 14:
        raise SpecError("slots 的 items 需要 1~14 个")
    gaps = spec.get("gaps") or []
    if gaps == "all":
        gaps = list(range(n + 1))
    elif gaps == "inner":
        gaps = list(range(1, n))
    if any(not isinstance(g, int) or not 0 <= g <= n for g in gaps):
        raise SpecError(f"gaps 是空位序号 0~{n}（0 为最左、{n} 为最右），或写 \"all\" / \"inner\"")
    gap_style = spec.get("gap_style", "insert")
    if gap_style not in ("insert", "divider"):
        raise SpecError("gap_style 只能是 insert（插空）或 divider（隔板）")
    width = 760
    head, top = header(spec, width)
    gap_w = 30 if gaps else 10
    size = min(72, (width - 80 - gap_w * (n + 1)) / n)
    total_w = n * size + (n + 1) * gap_w
    x0 = (width - total_w) / 2
    bundles = spec.get("bundles") or []
    y_box = top + (34 if bundles else 6)
    parts, roles = [head], set()
    xs = [x0 + gap_w + i * (size + gap_w) for i in range(n)]
    for b in bundles:
        f, t = b.get("from"), b.get("to")
        if not (isinstance(f, int) and isinstance(t, int) and 0 <= f <= t < n):
            raise SpecError(f"bundle 的 from/to 是元素序号 0~{n - 1}")
        role = b.get("role", "given")
        if role not in ROLE:
            raise SpecError(f"bundle role 只能是 {sorted(ROLE)}")
        roles.add(role)
        bx, bw = xs[f] - 8, xs[t] + size - xs[f] + 16
        parts.append(f'<rect x="{bx:.1f}" y="{y_box - 8}" width="{bw:.1f}" height="{size + 16:.1f}" rx="12" '
                     f'fill="{ROLE[role][0]}" fill-opacity="0.45" stroke="{INK_SOFT}" stroke-width="1.4" '
                     f'stroke-dasharray="5 4"/>')
        parts.append(svg_text(bx + bw / 2, y_box - 20, b.get("label", ""), 13, 700, INK_SOFT))
    for i, raw in enumerate(items):
        text, role = item(raw, f"items[{i}]")
        roles.add(role)
        parts.append(box(xs[i], y_box, size, size, role))
        parts.append(svg_text(xs[i] + size / 2, y_box + size / 2, text, 15 if size >= 48 else 13,
                              700 if role != "base" else 500, ROLE[role][1]))
    for g in gaps:
        gx = x0 + g * (size + gap_w) + gap_w / 2
        if gap_style == "divider":
            parts.append(f'<line x1="{gx:.1f}" y1="{y_box - 4}" x2="{gx:.1f}" y2="{y_box + size + 4}" '
                         f'stroke="{ROLE["key"][0]}" stroke-width="4" stroke-linecap="round"/>')
        else:
            parts.append(f'<path d="M{gx - 7:.1f} {y_box + size + 22} L{gx:.1f} {y_box + size + 10} '
                         f'L{gx + 7:.1f} {y_box + size + 22} Z" fill="{ROLE["key"][0]}"/>')
    if gaps:
        roles.add("key")
    y = y_box + size + (30 if gaps and gap_style == "insert" else 14)
    caps = spec.get("captions") or []
    if caps:
        if len(caps) != n:
            raise SpecError("captions 个数要和 items 一样（不需要的写空字符串）")
        for i, c in enumerate(caps):
            parts.append(svg_text(xs[i] + size / 2, y + 10, c, 13, 500, INK_SOFT))
        y += 30
    if spec.get("gap_label") and gaps:
        parts.append(svg_text(width / 2, y + 8, spec["gap_label"], 13, 500, INK_SOFT))
        y += 26
    return finish(spec, parts, roles, width, y + 6)


# ---------------- tree 树状图（概率分步、分类计数） ----------------
def draw_tree(spec):
    root = spec.get("root")
    if not isinstance(root, dict):
        raise SpecError("tree 需要 root：{label, children:[{edge, label, role, result, children}]}")
    errors, leaves, depth = [], [], [0]

    def walk(node, d, path):
        depth[0] = max(depth[0], d)
        kids = node.get("children") or []
        if d > 4:
            raise SpecError("tree 最多 4 层")
        if spec.get("check") and kids:
            fr = [to_fraction(k.get("edge")) for k in kids]
            if all(f is not None for f in fr) and sum(fr) != 1:
                errors.append(f"“{path or node.get('label', '根')}”下各分支概率之和 = {sum(fr)}，不等于 1")
        if not kids:
            leaves.append(node)
        for k in kids:
            walk(k, d + 1, f"{path}→{k.get('label', '')}" if path else str(k.get("label", "")))

    walk(root, 0, "")
    if errors:
        raise SpecError("；".join(errors))
    if len(leaves) > 16:
        raise SpecError("tree 叶子最多 16 个，分支太多就只画一支代表、其余写在正文")
    node_w = lambda n: max(text_width(str(n.get("label", "")), 14) + 22, 36)
    depth_w = [0.0] * (depth[0] + 1)
    gap_w = [56.0] * (depth[0] + 1)
    result_w = [0.0] * (depth[0] + 1)

    def measure(node, d):
        depth_w[d] = max(depth_w[d], node_w(node))
        if node.get("result") and not node.get("children"):
            result_w[d] = max(result_w[d], text_width(node["result"], 13) + 16)
        for k in node.get("children") or []:
            if k.get("edge") is not None:
                gap_w[d] = max(gap_w[d], text_width(fmt(k["edge"]), 12) + 32)
            measure(k, d + 1)

    measure(root, 0)
    col_x = [24.0]
    for d in range(depth[0]):
        col_x.append(col_x[d] + depth_w[d] + gap_w[d])
    content_w = max(col_x[d] + depth_w[d] + result_w[d] for d in range(depth[0] + 1)) + 24
    if content_w > 1000:
        raise SpecError("tree 太宽：缩短节点文字或 result（每个节点建议 ≤12 字），或拆成两张图")
    width = max(760, content_w)
    shift = (width - content_w) / 2
    col_x = [x + shift for x in col_x]
    head, top = header(spec, width)
    row_h = 46
    pos, parts, roles = {}, [head], set()
    levels = spec.get("levels") or []
    if levels:
        for d, label in enumerate(levels[:depth[0] + 1]):
            parts.append(svg_text(col_x[d] + 4, top + 4, label, 12, 700, MUTED, "start"))
        if spec.get("result_title"):
            last = max(range(depth[0] + 1), key=lambda d: result_w[d])
            parts.append(svg_text(col_x[last] + depth_w[last] + 14, top + 4, spec["result_title"], 12, 700, MUTED, "start"))
        top += 26
    counter = [0]

    def place(node, d):
        kids = node.get("children") or []
        if kids:
            ys = [place(k, d + 1) for k in kids]
            y = (ys[0] + ys[-1]) / 2
        else:
            y = top + 20 + counter[0] * row_h
            counter[0] += 1
        pos[id(node)] = (col_x[d] + node_w(node) / 2, y, d)
        return y

    place(root, 0)
    edges, nodes = [], []

    def emit(node):
        x, y, d = pos[id(node)]
        text, role = item({"text": node.get("label", ""), "role": node.get("role", "base")}, "节点")
        roles.add(role)
        w = node_w(node)
        for k in node.get("children") or []:
            kx, ky, _ = pos[id(k)]
            kw = node_w(k)
            x1, x2 = x + w / 2, kx - kw / 2
            edges.append(f'<path d="M{x1:.1f} {y:.1f} C{(x1 + x2) / 2:.1f} {y:.1f} {(x1 + x2) / 2:.1f} {ky:.1f} '
                         f'{x2:.1f} {ky:.1f}" fill="none" stroke="{INK_SOFT}" stroke-width="1.3"/>')
            if k.get("edge") is not None:
                lx = x1 + (x2 - x1) * 0.62
                ly = y + (ky - y) * 0.62
                label = fmt(k["edge"])
                lw = text_width(label, 12) + 8
                edges.append(f'<rect x="{lx - lw / 2:.1f}" y="{ly - 9:.1f}" width="{lw:.1f}" height="18" rx="4" '
                             f'fill="{PAPER}"/>')
                edges.append(svg_text(lx, ly, label, 12, 500, INK_SOFT))
            emit(k)
        nodes.append(box(x - w / 2, y - 14, w, 28, role, rx=14))
        nodes.append(svg_text(x, y, text, 14, 700 if role != "base" else 500, ROLE[role][1]))
        if not node.get("children") and node.get("result"):
            nodes.append(svg_text(col_x[d] + depth_w[d] + 14, y, node["result"], 13, 500, INK_SOFT, "start"))

    emit(root)
    parts += edges + nodes
    return finish(spec, parts, roles, width, top + 20 + counter[0] * row_h)


# ---------------- chain 推理链（翻译推理、逆否） ----------------
def draw_chain(spec):
    rows = spec.get("rows") or []
    if not 1 <= len(rows) <= 5:
        raise SpecError("chain 的 rows 需要 1~5 行：[{label, nodes:[...], edges:[...]}]")
    width = 760
    head, top = header(spec, width)
    parts, roles = [head, ARROW_DEF], set()
    label_w = max([text_width(r.get("label", ""), 13) for r in rows] + [0])
    label_w = label_w + 20 if label_w else 0
    y = top + 10
    for ri, r in enumerate(rows):
        nodes = r.get("nodes") or []
        if not 1 <= len(nodes) <= 6:
            raise SpecError(f"第 {ri + 1} 行 nodes 需要 1~6 个")
        texts = [item(nd, f"rows[{ri}].nodes") for nd in nodes]
        edges = r.get("edges") or [""] * (len(nodes) - 1)
        if len(edges) != len(nodes) - 1:
            raise SpecError(f"第 {ri + 1} 行 edges 个数应为 nodes 个数 − 1")
        ws = [max(text_width(t, 14) + 24, 48) for t, _ in texts]
        gaps = [max(text_width(e, 12) + 24, 56) for e in edges]
        total = sum(ws) + sum(gaps)
        avail = width - 60 - label_w
        if total > avail:
            raise SpecError(f"第 {ri + 1} 行太长，拆成两行或缩短文字")
        x = 30 + label_w + (avail - total) / 2
        if r.get("label"):
            parts.append(svg_text(30, y + 20, r["label"], 13, 700, INK_SOFT, "start"))
        for i, (t, role) in enumerate(texts):
            roles.add(role)
            parts.append(box(x, y, ws[i], 40, role, rx=10))
            parts.append(svg_text(x + ws[i] / 2, y + 20, t, 14, 700 if role != "base" else 500, ROLE[role][1]))
            x += ws[i]
            if i < len(edges):
                parts.append(f'<line x1="{x + 4:.1f}" y1="{y + 20}" x2="{x + gaps[i] - 6:.1f}" y2="{y + 20}" '
                             f'stroke="{INK_SOFT}" stroke-width="1.6" marker-end="url(#ah)"/>')
                if edges[i]:
                    parts.append(svg_text(x + gaps[i] / 2, y + 6, edges[i], 12, 500, INK_SOFT))
                x += gaps[i]
        y += 62
    return finish(spec, parts, roles, width, y)


# ---------------- circle 环形跑道 ----------------
def draw_circle(spec):
    length = num(spec.get("length"))
    if not length or length <= 0:
        raise SpecError("circle 需要正数 length（一圈的长度）")
    width = 760
    head, top = header(spec, width)
    arcs = spec.get("arcs") or []
    rings = max([a.get("ring", 1) for a in arcs] + [1])
    cx, r0 = width / 2, 110
    cy = top + 40 + r0 + rings * 18
    parts, roles = [head, ARROW_DEF], set()
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r0}" fill="{FRAME}" stroke="{INK}" stroke-width="2.4"/>')

    def pt(at, r):
        ang = 2 * math.pi * at / length - math.pi / 2
        return cx + r * math.cos(ang), cy + r * math.sin(ang)

    for p in spec.get("points") or []:
        at = num(p.get("at"))
        if at is None:
            raise SpecError("points[].at 必须是数字")
        x, y = pt(at, r0)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{INK}"/>')
        lx, ly = pt(at, r0 - 26)
        parts.append(svg_text(lx, ly, p.get("label", ""), 13, 700, INK))
    for a in arcs:
        f, t = num(a.get("from", 0)), num(a.get("to"))
        if f is None or t is None:
            raise SpecError("arcs 需要数字 from / to")
        if abs(t - f) >= length:
            raise SpecError("单段弧长不能达到一整圈；跑了几圈写在 label 里，弧只画最后不满一圈的部分")
        role = a.get("role", "given")
        if role not in ROLE:
            raise SpecError(f"arc role 只能是 {sorted(ROLE)}")
        roles.add(role)
        r = r0 + 18 * a.get("ring", 1)
        (x1, y1), (x2, y2) = pt(f, r), pt(t, r)
        large = 1 if abs(t - f) > length / 2 else 0
        sweep = 1 if t > f else 0
        color = ROLE[role][0] if role != "base" else INK_SOFT
        parts.append(f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 {large} {sweep} {x2:.1f} {y2:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="6" stroke-linecap="round"/>')
        parts.append(f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 {large} {sweep} {x2:.1f} {y2:.1f}" fill="none" '
                     f'stroke="{INK_SOFT}" stroke-width="1.2" marker-end="url(#ah)"/>')
        mx, my = pt((f + t) / 2, r + 26)
        anchor = "start" if mx > cx + 10 else "end" if mx < cx - 10 else "middle"
        parts.append(svg_text(mx, my, a.get("label", ""), 13, 500, INK_SOFT, anchor))
    if spec.get("center"):
        parts.append(svg_text(cx, cy, spec["center"], 14, 700, INK_SOFT))
    return finish(spec, parts, roles, width, cy + r0 + rings * 18 + 40)


# ---------------- cross 十字交叉（浓度、混合平均） ----------------
def draw_cross(spec):
    a, b, m = spec.get("a") or {}, spec.get("b") or {}, spec.get("mix") or {}
    va, vb, vm = (to_fraction(x.get("value")) for x in (a, b, m))
    if None in (va, vb, vm):
        raise SpecError("cross 需要 a / b / mix 三个 {value, label}，value 是数字")
    if not min(va, vb) < vm < max(va, vb):
        raise SpecError(f"混合值 {fmt(float(vm))} 必须严格介于 {fmt(float(va))} 和 {fmt(float(vb))} 之间")
    unit = spec.get("unit", "")
    da, db = abs(vb - vm), abs(vm - va)
    ratio = da / db
    show = lambda f: fmt(float(f)) if f.denominator != 1 else str(f.numerator)
    width = 760
    head, top = header(spec, width)
    parts, roles = [head], {"given", "key", "answer"}
    y1, y2 = top + 40, top + 190
    xl, xm, xr = 170, 380, 590
    ym = (y1 + y2) / 2
    for x, y, txt, role in ((xl, y1, f'{a.get("label", "")}\n{show(va)}{unit}', "given"),
                            (xl, y2, f'{b.get("label", "")}\n{show(vb)}{unit}', "given"),
                            (xm, ym, f'{m.get("label", "混合")}\n{show(vm)}{unit}', "key"),
                            (xr, y1, f'|{show(vm)} − {show(vb)}|\n= {show(da)}', "answer"),
                            (xr, y2, f'|{show(vm)} − {show(va)}|\n= {show(db)}', "answer")):
        w = max(max(text_width(t, 14) for t in txt.split("\n")) + 26, 110)
        parts.append(box(x - w / 2, y - 26, w, 52, role, rx=10))
        parts.append(svg_text(x, y, txt, 14, 700, ROLE[role][1]))
    for (sx, sy), (ex, ey) in (((xl + 60, y1 + 10), (xr - 60, y2 - 10)), ((xl + 60, y2 - 10), (xr - 60, y1 + 10))):
        parts.insert(1, f'<line x1="{sx}" y1="{sy}" x2="{ex}" y2="{ey}" stroke="{LINE}" stroke-width="1.6" '
                        f'stroke-dasharray="6 5"/>')
    na, nb = a.get("name", "甲"), b.get("name", "乙")
    parts.append(svg_text(width / 2, y2 + 56, f"{na} : {nb} = {show(da)} : {show(db)} = "
                          f"{ratio.numerator} : {ratio.denominator}", 16, 700, INK))
    return finish(spec, parts, roles, width, y2 + 82)


# ---------------- grid 表格网格（样本空间、匹配推理、日历周期） ----------------
def draw_grid(spec):
    rows, cols = spec.get("rows") or [], spec.get("cols") or []
    cells = spec.get("cells") or []
    if not (1 <= len(rows) <= 12 and 1 <= len(cols) <= 12):
        raise SpecError("grid 的 rows / cols 各需 1~12 个表头")
    if len(cells) != len(rows) or any(len(r) != len(cols) for r in cells):
        raise SpecError(f"cells 必须是 {len(rows)} 行 × {len(cols)} 列的二维数组（空格写 \"\"）")
    width = 760
    head, top = header(spec, width)
    hw = max([text_width(r, 13) for r in map(str, rows)] + [30]) + 20
    cw = min(64, (width - 80 - hw) / len(cols))
    ch = min(44, max(30, cw * 0.7))
    gx = (width - hw - cw * len(cols)) / 2
    y0 = top + (34 if spec.get("col_title") else 10)
    parts, roles, counts = [head], set(), {}
    if spec.get("col_title"):
        parts.append(svg_text(gx + hw + cw * len(cols) / 2, y0 - 18, spec["col_title"], 13, 700, INK_SOFT))
    if spec.get("row_title"):
        parts.append(svg_text(gx + hw / 2, y0 + ch / 2, spec["row_title"], 12, 700, INK_SOFT))
    for j, c in enumerate(cols):
        parts.append(svg_text(gx + hw + j * cw + cw / 2, y0 + ch / 2, c, 13, 700, INK))
    for i, r in enumerate(rows):
        yy = y0 + ch * (i + 1)
        parts.append(svg_text(gx + hw / 2, yy + ch / 2, r, 13, 700, INK))
        for j in range(len(cols)):
            text, role = item(cells[i][j], f"cells[{i}][{j}]")
            roles.add(role)
            counts[role] = counts.get(role, 0) + 1
            parts.append(f'<rect x="{gx + hw + j * cw:.1f}" y="{yy:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                         f'fill="{ROLE[role][0] if role != "base" else FRAME}" stroke="{LINE}" stroke-width="1"/>')
            if text:
                parts.append(svg_text(gx + hw + j * cw + cw / 2, yy + ch / 2, text, 13 if cw >= 40 else 11,
                                      700 if role != "base" else 400, ROLE[role][1]))
    y = y0 + ch * (len(rows) + 1)
    parts.append(f'<rect x="{gx + hw:.1f}" y="{y0 + ch:.1f}" width="{cw * len(cols):.1f}" '
                 f'height="{ch * len(rows):.1f}" fill="none" stroke="{INK}" stroke-width="1.6"/>')
    count_role = spec.get("count_role")
    if count_role:
        total = len(rows) * len(cols)
        parts.append(svg_text(width / 2, y + 22, f"{ROLE_LABEL.get(count_role, count_role)} {counts.get(count_role, 0)} 格"
                              f" / 共 {total} 格", 14, 700, INK))
        y += 34
    return finish(spec, parts, roles, width, y + 16)


# ---------------- gantt 时间条（工程交替、统筹、分段） ----------------
def draw_gantt(spec):
    length = num(spec.get("length"))
    rows = spec.get("rows") or []
    if not length or length <= 0 or not 1 <= len(rows) <= 8:
        raise SpecError("gantt 需要正数 length（总时长）和 1~8 行 rows：[{label, segments:[{from,to,label,role}]}]")
    width, unit = 760, spec.get("unit", "")
    head, top = header(spec, width)
    lw = max(text_width(r.get("label", ""), 13) for r in rows) + 20
    x0, track = 30 + lw, width - 60 - lw
    sx = lambda v: x0 + v / length * track
    row_h = 44
    marks = spec.get("marks") or []
    y0 = top + (24 if marks else 8)
    parts, roles = [head], set()
    step = next(s for s in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 1e9) if length / s <= 12)
    for k in range(int(length // step) + 1):
        x = sx(k * step)
        parts.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y0 + row_h * len(rows)}" stroke="{LINE}" '
                     f'stroke-width="0.8" stroke-dasharray="3 4"/>')
        parts.append(svg_text(x, y0 + row_h * len(rows) + 14, fmt(k * step), 12, 400, INK_SOFT))
    for i, r in enumerate(rows):
        y = y0 + i * row_h
        parts.append(svg_text(30, y + row_h / 2, r.get("label", ""), 13, 700, INK, "start"))
        for s in r.get("segments") or []:
            f, t = num(s.get("from")), num(s.get("to"))
            if f is None or t is None or not 0 <= f < t <= length:
                raise SpecError(f"{r.get('label')} 的段 from/to 必须满足 0 ≤ from < to ≤ {fmt(length)}")
            role = s.get("role", "given")
            if role not in ROLE:
                raise SpecError(f"segment role 只能是 {sorted(ROLE)}")
            roles.add(role)
            parts.append(box(sx(f), y + 8, sx(t) - sx(f), row_h - 16, role, rx=6, sw=1.1))
            label = s.get("label", "")
            if label and text_width(label, 12) + 8 <= sx(t) - sx(f):
                parts.append(svg_text((sx(f) + sx(t)) / 2, y + row_h / 2, label, 12, 600, ROLE[role][1]))
            elif label:
                parts.append(svg_text((sx(f) + sx(t)) / 2, y + 3, label, 11, 500, INK_SOFT))
    for m in marks:
        at = num(m.get("at"))
        if at is None or not 0 <= at <= length:
            raise SpecError("marks[].at 必须在 0~length")
        x = sx(at)
        parts.append(f'<line x1="{x:.1f}" y1="{y0 - 4}" x2="{x:.1f}" y2="{y0 + row_h * len(rows)}" stroke="{INK}" '
                     f'stroke-width="1.4"/>')
        parts.append(svg_text(x, y0 - 14, m.get("label", ""), 12, 700, INK))
    y = y0 + row_h * len(rows) + 30
    if unit:
        parts.append(svg_text(x0 + track, y - 2, f"单位：{unit}", 12, 400, INK_SOFT, "end"))
        y += 10
    return finish(spec, parts, roles, width, y)


# ---------------- geometry 平面/立体几何 ----------------
def draw_geometry(spec):
    raw_pts = spec.get("points") or {}
    if not raw_pts:
        raise SpecError("geometry 需要 points：{\"A\":[x,y]} 或立体 {\"A\":[x,y,z]}")
    pts = {}
    for k, v in raw_pts.items():
        if not (isinstance(v, list) and len(v) in (2, 3) and all(num(c) is not None for c in v)):
            raise SpecError(f"点 {k} 的坐标要写成 [x, y] 或 [x, y, z]")
        pts[k] = [float(c) for c in v] + ([0.0] if len(v) == 2 else [])
    solid = any(len(v) == 3 for v in raw_pts.values())

    def need(name):
        if name not in pts:
            raise SpecError(f"用到了未定义的点 {name}")
        return pts[name]

    def dist(p, q):
        return math.dist(p, q)

    def angle(at, a, b):
        o, p, q = need(at), need(a), need(b)
        u = [p[i] - o[i] for i in range(3)]
        v = [q[i] - o[i] for i in range(3)]
        nu, nv = math.hypot(*u), math.hypot(*v)
        if not nu or not nv:
            raise SpecError(f"角 {a}{at}{b} 有重合的点")
        c = sum(u[i] * v[i] for i in range(3)) / nu / nv
        return math.degrees(math.acos(max(-1, min(1, c))))

    def area(names):
        ps = [need(n) for n in names]
        cx = cy = cz = 0.0
        for i in range(len(ps)):
            p, q = ps[i], ps[(i + 1) % len(ps)]
            cx += p[1] * q[2] - p[2] * q[1]
            cy += p[2] * q[0] - p[0] * q[2]
            cz += p[0] * q[1] - p[1] * q[0]
        return math.hypot(cx, cy, cz) / 2

    errors = []
    close = lambda got, want, rel: abs(got - want) <= max(rel * abs(want), 1e-6)
    for s in spec.get("segments") or []:
        if num(s.get("check")) is not None:
            got = dist(need(s["from"]), need(s["to"]))
            if not close(got, s["check"], 0.01):
                errors.append(f"线段 {s['from']}{s['to']} 按坐标长 {got:.3g}，但应为 {fmt(s['check'])}")
    for g in spec.get("polygons") or []:
        if num(g.get("check_area")) is not None:
            got = area(g["points"])
            if not close(got, g["check_area"], 0.01):
                errors.append(f"图形 {''.join(g['points'])} 按坐标面积 {got:.4g}，但应为 {fmt(g['check_area'])}")
    for a in spec.get("angles") or []:
        want = 90 if a.get("right") else num(a.get("check"))
        if want is not None:
            got = angle(a["at"], a["from"], a["to"])
            if abs(got - want) > 1:
                errors.append(f"角 {a['from']}{a['at']}{a['to']} 按坐标是 {got:.1f}°，但应为 {fmt(want)}°")
    if errors:
        raise SpecError("；".join(errors))

    k3 = 0.42

    def proj(p):
        x, y, z = p
        return (x + k3 * z * math.cos(math.radians(35)), y + k3 * z * math.sin(math.radians(35))) if solid else (x, y)

    flat = {k: proj(v) for k, v in pts.items()}
    extents = list(flat.values())
    for s in spec.get("sectors") or []:
        need(s.get("center"))
        r = num(s.get("r"))
        if not r or r <= 0:
            raise SpecError("sectors 需要正数 r")
        x, y = flat[s["center"]]
        a0, a1 = num(s.get("start", 0)), num(s.get("end", 90))
        span = (a1 - a0) % 360 or 360
        extents += [(x + r * math.cos(math.radians(a0 + span * i / 36)), y + r * math.sin(math.radians(a0 + span * i / 36)))
                    for i in range(37)]
    for c in (spec.get("circles") or []) + (spec.get("ellipses") or []):
        need(c.get("center"))
        rx, ry = (num(c.get("r")),) * 2 if "r" in c else (num(c.get("rx")), num(c.get("ry")))
        if not rx or not ry or rx <= 0 or ry <= 0:
            raise SpecError("circles / sectors 需要正数 r，ellipses 需要正数 rx、ry")
        x, y = flat[c["center"]]
        extents += [(x - rx, y - ry), (x + rx, y + ry)]
    for g in spec.get("polygons") or []:
        for n in g.get("points") or []:
            need(n)
    for s in spec.get("segments") or []:
        need(s.get("from")), need(s.get("to"))
    for a in spec.get("angles") or []:
        need(a.get("at")), need(a.get("from")), need(a.get("to"))
    xs, ys = [p[0] for p in extents], [p[1] for p in extents]
    w_u, h_u = max(max(xs) - min(xs), 1e-9), max(max(ys) - min(ys), 1e-9)
    width = 760
    head, top = header(spec, width)
    box_w, box_h = 520, 340
    sc = min(box_w / w_u, box_h / h_u)
    ox = (width - w_u * sc) / 2 - min(xs) * sc
    oy = top + 36 + h_u * sc + min(ys) * sc
    P = lambda p: (ox + p[0] * sc, oy - p[1] * sc)
    S = {k: P(v) for k, v in flat.items()}
    cen = (sum(p[0] for p in S.values()) / len(S), sum(p[1] for p in S.values()) / len(S))
    parts, roles = [head], set()

    def role_of(d, default="base"):
        r = d.get("role", default)
        if r not in ROLE:
            raise SpecError(f"role 只能是 {sorted(ROLE)}，收到 {r!r}")
        roles.add(r) if r != "base" else None
        return r

    for s in spec.get("sectors") or []:
        r = role_of(s, "given")
        cx, cy = S[s["center"]]
        rr = num(s["r"]) * sc
        a0, a1 = math.radians(num(s.get("start", 0))), math.radians(num(s.get("end", 90)))
        x0, y0 = cx + rr * math.cos(a0), cy - rr * math.sin(a0)
        x1, y1 = cx + rr * math.cos(a1), cy - rr * math.sin(a1)
        large = 1 if (num(s.get("end", 90)) - num(s.get("start", 0))) % 360 > 180 else 0
        parts.append(f'<path d="M{cx:.1f} {cy:.1f} L{x0:.1f} {y0:.1f} A{rr:.1f} {rr:.1f} 0 {large} 0 {x1:.1f} {y1:.1f} Z" '
                     f'fill="{ROLE[r][0]}" fill-opacity="0.85" stroke="{INK}" stroke-width="1.2"/>')
    for g in spec.get("polygons") or []:
        r = role_of(g, "given")
        d = "M" + " L".join(f"{S[n][0]:.1f} {S[n][1]:.1f}" for n in g["points"]) + " Z"
        parts.append(f'<path d="{d}" fill="{ROLE[r][0]}" fill-opacity="{0.85 if r != "base" else 0.6}" '
                     f'stroke="none"/>')
    for c in spec.get("circles") or []:
        cx, cy = S[c["center"]]
        r = c.get("role")
        fill = f'fill="{ROLE[role_of(c)][0]}" fill-opacity="0.6"' if r else 'fill="none"'
        dash = ' stroke-dasharray="6 5"' if c.get("dashed") else ""
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{num(c["r"]) * sc:.1f}" {fill} stroke="{INK}" '
                     f'stroke-width="1.8"{dash}/>')
    for e in spec.get("ellipses") or []:
        cx, cy = S[e["center"]]
        rx, ry = num(e["rx"]) * sc, num(e["ry"]) * sc
        if e.get("back_dashed"):
            parts.append(f'<path d="M{cx - rx:.1f} {cy:.1f} A{rx:.1f} {ry:.1f} 0 0 1 {cx + rx:.1f} {cy:.1f}" fill="none" '
                         f'stroke="{INK}" stroke-width="1.4" stroke-dasharray="6 5"/>')
            parts.append(f'<path d="M{cx - rx:.1f} {cy:.1f} A{rx:.1f} {ry:.1f} 0 0 0 {cx + rx:.1f} {cy:.1f}" fill="none" '
                         f'stroke="{INK}" stroke-width="1.8"/>')
        else:
            parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="none" '
                         f'stroke="{INK}" stroke-width="1.8"/>')
    for g in spec.get("polygons") or []:
        d = "M" + " L".join(f"{S[n][0]:.1f} {S[n][1]:.1f}" for n in g["points"]) + " Z"
        parts.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="1.8" stroke-linejoin="round"/>')
    for s in spec.get("segments") or []:
        (x1, y1), (x2, y2) = S[s["from"]], S[s["to"]]
        dash = ' stroke-dasharray="6 5"' if s.get("dashed") else ""
        color = ROLE["key"][0] if s.get("role") == "key" else INK
        if s.get("role") == "key":
            roles.add("key")
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
                     f'stroke-width="{2.6 if s.get("role") == "key" else 1.8}"{dash}/>')
        if s.get("label"):
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            nx, ny = -(y2 - y1), x2 - x1
            nl = math.hypot(nx, ny) or 1
            nx, ny = nx / nl, ny / nl
            if (mx + nx - cen[0]) ** 2 + (my + ny - cen[1]) ** 2 < (mx - cen[0]) ** 2 + (my - cen[1]) ** 2:
                nx, ny = -nx, -ny
            off = 12 + text_width(s["label"], 13) / 2 * abs(nx)
            parts.append(svg_text(mx + nx * off, my + ny * 14, s["label"], 13, 700, INK_SOFT))
    for a in spec.get("angles") or []:
        (ox_, oy_), (ax, ay), (bx, by) = S[a["at"]], S[a["from"]], S[a["to"]]
        ua, ub = math.atan2(ay - oy_, ax - ox_), math.atan2(by - oy_, bx - ox_)
        if a.get("right"):
            q = 13
            p1 = (ox_ + q * math.cos(ua), oy_ + q * math.sin(ua))
            p2 = (ox_ + q * math.cos(ub), oy_ + q * math.sin(ub))
            p3 = (p1[0] + p2[0] - ox_, p1[1] + p2[1] - oy_)
            parts.append(f'<path d="M{p1[0]:.1f} {p1[1]:.1f} L{p3[0]:.1f} {p3[1]:.1f} L{p2[0]:.1f} {p2[1]:.1f}" '
                         f'fill="none" stroke="{INK}" stroke-width="1.3"/>')
            continue
        rr = 22
        d = (ub - ua + math.pi) % (2 * math.pi) - math.pi
        x0, y0 = ox_ + rr * math.cos(ua), oy_ + rr * math.sin(ua)
        x1, y1 = ox_ + rr * math.cos(ua + d), oy_ + rr * math.sin(ua + d)
        parts.append(f'<path d="M{x0:.1f} {y0:.1f} A{rr} {rr} 0 0 {1 if d > 0 else 0} {x1:.1f} {y1:.1f}" '
                     f'fill="none" stroke="{ROLE["key"][0]}" stroke-width="2"/>')
        if a.get("label"):
            mid = ua + d / 2
            parts.append(svg_text(ox_ + 40 * math.cos(mid), oy_ + 40 * math.sin(mid), a["label"], 13, 700, INK_SOFT))
    hidden = set(spec.get("hide_labels") or [])
    for name, (x, y) in S.items():
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{INK}"/>')
        if name in hidden:
            continue
        dx, dy = x - cen[0], y - cen[1]
        dl = math.hypot(dx, dy) or 1
        parts.append(svg_text(x + dx / dl * 16, y + dy / dl * 16, name, 15, 700, INK))
    for g in spec.get("polygons") or []:
        if g.get("label"):
            gx = sum(S[n][0] for n in g["points"]) / len(g["points"])
            gy = sum(S[n][1] for n in g["points"]) / len(g["points"])
            r = g.get("role", "given")
            parts.append(svg_text(gx, gy, g["label"], 14, 700, ROLE[r][1]))
    for c in (spec.get("circles") or []) + (spec.get("sectors") or []):
        if c.get("label"):
            cx, cy = S[c["center"]]
            parts.append(svg_text(cx, cy + 18, c["label"], 13, 700, INK_SOFT))
    for t in spec.get("texts") or []:
        at = t.get("at")
        if not (isinstance(at, list) and len(at) in (2, 3)):
            raise SpecError("texts[].at 要写成坐标 [x, y]（立体写 [x, y, z]）")
        x, y = P(proj([float(c) for c in at] + ([0.0] if len(at) == 2 else [])))
        label = t.get("text", "")
        w = text_width(label, 13) + 12
        parts.append(f'<rect x="{x - w / 2:.1f}" y="{y - 11:.1f}" width="{w:.1f}" height="22" rx="6" '
                     f'fill="{PAPER}" fill-opacity="0.9"/>')
        parts.append(svg_text(x, y, label, 13, 700, INK))
    return finish(spec, parts, roles, width, oy - min(ys) * sc + 46)


TEMPLATES = {"geometry": draw_geometry, "venn2": draw_venn2, "venn3": draw_venn3, "bar": draw_bar, "line": draw_line,
             "slots": draw_slots, "tree": draw_tree, "chain": draw_chain, "circle": draw_circle,
             "cross": draw_cross, "grid": draw_grid, "gantt": draw_gantt}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec-file", help="JSON 规格文件；不给则读标准输入")
    ap.add_argument("--slug", help="文件名关键词（英文/拼音），默认取模板名")
    args = ap.parse_args()
    try:
        raw = Path(args.spec_file).read_text("utf-8") if args.spec_file else sys.stdin.read()
        spec = json.loads(raw)
        tpl = spec.get("template")
        def strings(v):
            if isinstance(v, str):
                yield v
            elif isinstance(v, dict):
                for x in v.values():
                    yield from strings(x)
            elif isinstance(v, list):
                for x in v:
                    yield from strings(x)
        bad = [m for s in strings(spec) for m in re.findall(r"[\u2070\u2074-\u209c]|\$|\\[a-zA-Z]+", s)]
        if bad:
            raise SpecError(f"图里的文字不渲染公式，发现 {sorted(set(bad))}：排列组合写成 A(4,2)、C(9,2)，"
                            "幂写 2^3 或 ²³，分数写 3/5，不要用上下标字符和 LaTeX")
        if tpl not in TEMPLATES:
            raise SpecError(f"template 只能是 {sorted(TEMPLATES)}，收到 {tpl!r}")
        svg = TEMPLATES[tpl](spec)
    except (SpecError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        sys.exit(1)
    slug = re.sub(r"[^a-z0-9-]+", "-", (args.slug or tpl).lower()).strip("-") or tpl
    day = datetime.now().strftime("%Y%m%d")
    name = f"{slug}-{hashlib.sha1(svg.encode()).hexdigest()[:8]}.svg"
    path = OUT_DIR / day / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, "utf-8")
    url = f"{URL_PREFIX}/{day}/{name}"
    alt = (spec.get("title") or tpl).replace("]", "")
    print(json.dumps({"ok": True, "markdown": f"![{alt}]({url})", "url": url, "path": str(path)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

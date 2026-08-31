#!/usr/bin/env python3
"""Render compact exam-style tables, bar charts, and pie charts as PNG."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc")
if not FONT_PATH.exists():
    FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
INK = (0, 0, 0)
LINE = (0, 0, 0)
RULE = (170, 170, 170)
BG = (255, 255, 255)
BAR_FILLS = [(30, 30, 30), (110, 110, 110), (190, 190, 190)]


def font(size: int) -> ImageFont.FreeTypeFont:
    last = None
    for index in (2, 0, 1, 3, 4):
        try:
            return ImageFont.truetype(str(FONT_PATH), size, index=index)
        except OSError as exc:
            last = exc
    raise SystemExit(f"CJK font missing: {FONT_PATH} ({last})")


def measure(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=face)
    return box[2] - box[0], box[3] - box[1]


def nice_max(value: float) -> float:
    if value <= 0:
        return 1
    mag = 10 ** math.floor(math.log10(value))
    for step in (1, 1.2, 1.5, 2, 2.5, 5, 10):
        cand = step * mag
        if cand >= value:
            return cand
    return 10 * mag


def render_table(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    out: Path,
    unit: str = "",
    note: str = "",
) -> None:
    face_title = font(22)
    face_unit = font(15)
    face = font(19)
    face_note = font(14)
    pad_x, pad_y = 14, 8
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10), BG))
    cols = list(zip(*([headers] + rows)))
    widths = [max(measure(probe, cell, face)[0] for cell in col) + pad_x * 2 for col in cols]
    row_h = max(measure(probe, "\u9ad8", face)[1] + pad_y * 2, 34)
    title_h = measure(probe, title, face_title)[1] + 14 if title else 0
    unit_h = measure(probe, unit, face_unit)[1] + 8 if unit else 0
    note_h = measure(probe, note, face_note)[1] + 12 if note else 0
    width = max(sum(widths) + 4, measure(probe, title, face_title)[0] + 24, measure(probe, note, face_note)[0] + 16)
    extra = width - (sum(widths) + 4)
    if extra > 0:
        widths = [w + extra // len(widths) for w in widths]
        widths[-1] += extra % len(widths)
    height = title_h + unit_h + row_h * (1 + len(rows)) + note_h + 6
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    y = 6
    if title:
        tw, _ = measure(draw, title, face_title)
        draw.text(((width - tw) // 2, y), title, fill=INK, font=face_title)
        y = title_h
    if unit:
        uw, _ = measure(draw, unit, face_unit)
        draw.text((width - uw - 8, y - 1), unit, fill=INK, font=face_unit)
        y += unit_h

    def cell(x0, y0, w, h, text, *, header=False, first=False, total=False):
        draw.rectangle((x0, y0, x0 + w, y0 + h), outline=LINE, width=1)
        cw, ch = measure(draw, text, face)
        tx = x0 + (w - cw) // 2 if header else x0 + 10 if first else x0 + w - cw - 10
        draw.text((tx, y0 + (h - ch) // 2 - 1), text, fill=INK, font=face)
        if header or total:
            draw.line((x0, y0 + h - 1, x0 + w, y0 + h - 1), fill=INK, width=2)

    x = 2
    for w, head in zip(widths, headers):
        cell(x, y, w, row_h, head, header=True)
        x += w
    y += row_h
    for row in rows:
        is_total = str(row[0]).startswith("\u5408\u8ba1")
        x = 2
        for i, (w, text) in enumerate(zip(widths, row)):
            cell(x, y, w, row_h, text, first=(i == 0), total=is_total)
            x += w
        y += row_h
    if note:
        draw.text((8, y + 6), note, fill=INK, font=face_note)
    img.save(out, "PNG")


def render_bars(
    title: str,
    ylabel: str,
    categories: list[str],
    series: list[tuple[str, list[float]]],
    out: Path,
) -> None:
    if len(series) > 1 and any(separator in ylabel for separator in ("/", "／")):
        raise ValueError("多系列柱状图不得把不同单位合并写在同一纵轴；请把单位分别写入系列名称")
    face_title = font(22)
    face = font(18)
    face_value = font(16)
    left, right, top, bottom = 64, 16, 70, 78
    plot_w, plot_h = 400, 250
    width, height = left + plot_w + right, top + plot_h + bottom
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    if title:
        tw, _ = measure(draw, title, face_title)
        draw.text(((width - tw) // 2, 12), title, fill=INK, font=face_title)

    values = [v for _, vals in series for v in vals]
    vmax = nice_max(max(values) * 1.08) if values else 1
    n_cat = max(len(categories), 1)
    n_ser = max(len(series), 1)
    group_w = plot_w / n_cat
    bar_w = group_w * 0.62 / n_ser
    origin_y = top + plot_h

    draw.line((left, top, left, origin_y), fill=LINE, width=2)
    draw.line((left, origin_y, left + plot_w, origin_y), fill=LINE, width=2)
    for i in range(1, 5):
        val = vmax * i / 4
        yy = origin_y - plot_h * i / 4
        draw.line((left, yy, left + plot_w, yy), fill=RULE, width=1)
        label = f"{val:.0f}" if val >= 10 else f"{val:.1f}"
        lw, lh = measure(draw, label, face)
        draw.text((left - lw - 8, yy - lh // 2), label, fill=INK, font=face)
    if ylabel:
        _, yh = measure(draw, ylabel, face)
        draw.text((left, top - yh - 8), ylabel, fill=INK, font=face)

    value_labels: list[tuple[float, float, str]] = []
    for ci, category in enumerate(categories):
        gx = left + group_w * ci + group_w * 0.19
        for si, (_, vals) in enumerate(series):
            val = vals[ci] if ci < len(vals) else 0
            h = plot_h * (val / vmax)
            x0 = gx + si * bar_w
            y0 = origin_y - h
            x1 = x0 + bar_w - 3
            draw.rectangle((x0, y0, x1, origin_y), fill=BAR_FILLS[si % 3], outline=INK)
            value_labels.append(((x0 + x1) / 2, y0, f"{val:g}"))
        cw, _ = measure(draw, category, face)
        draw.text((left + group_w * ci + (group_w - cw) / 2, origin_y + 10), category, fill=INK, font=face)

    # Draw value labels last so bars cannot cover them. A solid backing masks grid
    # lines, and a fixed gap keeps glyphs clear of each bar top after scaling.
    placed: list[tuple[int, int, int, int]] = []
    for center_x, bar_top, label in value_labels:
        label_y = bar_top - 6
        bbox = draw.textbbox((center_x, label_y), label, font=face_value, anchor="mb")
        while any(not (bbox[2] < box[0] or bbox[0] > box[2] or bbox[3] < box[1] or bbox[1] > box[3]) for box in placed):
            label_y -= bbox[3] - bbox[1] + 4
            bbox = draw.textbbox((center_x, label_y), label, font=face_value, anchor="mb")
        backing = (bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1)
        draw.rectangle(backing, fill=BG)
        draw.text((center_x, label_y), label, fill=INK, font=face_value, anchor="mb")
        placed.append(backing)

    lx = left
    ly = height - 28
    for si, (name, _) in enumerate(series):
        draw.rectangle((lx, ly, lx + 16, ly + 12), fill=BAR_FILLS[si % 3], outline=INK)
        draw.text((lx + 22, ly - 2), name, fill=INK, font=face)
        nw, _ = measure(draw, name, face)
        lx += 22 + nw + 18
    img.save(out, "PNG")


def render_pie(title: str, slices: list[tuple[str, float]], out: Path) -> None:
    face_title = font(20)
    face = font(15)
    total = sum(val for _, val in slices) or 1
    box = 220
    pad_top, pad_side, legend_h = 48, 20, 22 * max(len(slices), 1) + 16
    width = pad_side * 2 + box
    height = pad_top + box + legend_h
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    if title:
        tw, _ = measure(draw, title, face_title)
        draw.text(((width - tw) // 2, 10), title, fill=INK, font=face_title)
    x0, y0 = (width - box) // 2, pad_top
    bbox = (x0, y0, x0 + box, y0 + box)
    start = -90.0
    for index, (_, val) in enumerate(slices):
        sweep = 360.0 * val / total
        fill = BAR_FILLS[index % len(BAR_FILLS)]
        if sweep > 0:
            draw.pieslice(bbox, start, start + sweep, fill=fill, outline=INK)
        start += sweep
    draw.ellipse(bbox, outline=INK, width=2)
    ly = pad_top + box + 8
    for index, (name, val) in enumerate(slices):
        pct = 100.0 * val / total
        fill = BAR_FILLS[index % len(BAR_FILLS)]
        draw.rectangle((pad_side, ly + 4, pad_side + 14, ly + 16), fill=fill, outline=INK)
        label = f"{name}  {val:g} ({pct:.1f}%)"
        draw.text((pad_side + 22, ly), label, fill=INK, font=face)
        ly += 22
    img.save(out, "PNG")


def parse_rows(raw: list[str]) -> list[list[str]]:
    return [item.split(",") for item in raw]


def parse_series(raw: list[str]) -> list[tuple[str, list[float]]]:
    out = []
    for item in raw:
        name, nums = item.split(":", 1)
        out.append((name, [float(x) for x in nums.split(",")]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    table = sub.add_parser("table")
    table.add_argument("--title", default="")
    table.add_argument("--unit", default="")
    table.add_argument("--note", default="")
    table.add_argument("--headers", required=True)
    table.add_argument("--rows", nargs="+", required=True)
    table.add_argument("--out", type=Path, required=True)
    bars = sub.add_parser("bars")
    bars.add_argument("--title", default="")
    bars.add_argument("--ylabel", default="")
    bars.add_argument("--categories", required=True)
    bars.add_argument("--series", nargs="+", required=True)
    bars.add_argument("--out", type=Path, required=True)
    pie = sub.add_parser("pie")
    pie.add_argument("--title", default="")
    pie.add_argument("--slices", nargs="+", required=True)
    pie.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.cmd == "table":
        render_table(args.title, args.headers.split(","), parse_rows(args.rows), args.out, args.unit, args.note)
    elif args.cmd == "bars":
        render_bars(args.title, args.ylabel, args.categories.split(","), parse_series(args.series), args.out)
    else:
        render_pie(args.title, [(name, float(val)) for name, val in (item.rsplit(",", 1) for item in args.slices)], args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

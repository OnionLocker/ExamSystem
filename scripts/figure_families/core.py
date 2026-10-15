"""程序出图题的公共件：SVG 构造与解析、栅格化、「出题 → 只看图判题 → 不过就重出」。

题型族模块约定：
  NAME / TAG / CATEGORY / SUB_CATEGORY / TITLE / DEFINITION / VERSION / PARTS
  generate(rng, difficulty) -> draft
      draft = {"stem": 题干, "options": [选项结构...], "answer": 正确选项下标,
               "difficulty": 2|3|4, ...题型族自己的结构}
  render(draft, order) -> {part: svg}
      order[i] = 第 i 个字母（A、B、C、D）放哪个选项。PARTS 里的每张图都要给。
  judge(svgs, pngs) -> {"correct": [符合题意的字母], "issues": [...], 其余为判题事实}
      只读渲染结果（SVG 文本或 PNG），不读 draft。判不了就抛 ValueError。
  explain(verdict, key) -> 解析文本（只用判题事实）
  option_texts(draft, order) -> 每个字母的选项文字（可选；没有就写字母本身）
  self_test() -> [(用例, 是否拦下, 说明)]
"""

from __future__ import annotations

import io
import math
import random
import re
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field

import cairosvg
from PIL import Image, ImageOps

INK = "#111111"
LETTERS = "ABCD"
FONT = "Noto Sans CJK SC"
SCALE = 2  # PNG 按 2 倍像素出，iPad 上清楚
TIERS = {"easy": 2, "mid": 3, "hard": 4}


def _num(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _attrs(attrs: dict) -> str:
    parts = []
    for key, value in attrs.items():
        if value is None:
            continue
        text = _num(value) if isinstance(value, float) else str(value)
        text = text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
        parts.append(f'{key}="{text}"')
    return " ".join(parts)


def _data(data: dict | None) -> dict:
    return {f"data-{key}": value for key, value in (data or {}).items()}


class Svg:
    """只用 line/polyline/polygon/rect/circle/text 和带 translate 的 g，解析器只认这些。"""

    def __init__(self, width: float, height: float):
        self.width, self.height = width, height
        self.body: list[str] = [f'<rect width="{_num(width)}" height="{_num(height)}" fill="#fff"/>']

    def _el(self, tag: str, attrs: dict, text: str | None = None) -> None:
        if text is None:
            self.body.append(f"<{tag} {_attrs(attrs)}/>")
        else:
            safe = text.replace("&", "&amp;").replace("<", "&lt;")
            self.body.append(f"<{tag} {_attrs(attrs)}>{safe}</{tag}>")

    def line(self, p, q, *, w=2.2, dash=None, data=None, color=INK, cap="round"):
        self._el("line", {"x1": float(p[0]), "y1": float(p[1]), "x2": float(q[0]), "y2": float(q[1]),
                          "stroke": color, "stroke-width": w, "stroke-linecap": cap,
                          "stroke-dasharray": dash, **_data(data)})

    def poly(self, points, *, closed=False, fill="none", w=2.2, dash=None, data=None, color=INK):
        pts = " ".join(f"{_num(float(x))},{_num(float(y))}" for x, y in points)
        self._el("polygon" if closed else "polyline",
                 {"points": pts, "fill": fill, "stroke": color if w else "none", "stroke-width": w or None,
                  "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": dash, **_data(data)})

    def rect(self, x, y, w, h, *, fill="none", sw=2.2, data=None, dash=None):
        self._el("rect", {"x": float(x), "y": float(y), "width": float(w), "height": float(h), "fill": fill,
                          "stroke": INK if sw else "none", "stroke-width": sw or None,
                          "stroke-dasharray": dash, **_data(data)})

    def circle(self, c, r, *, fill="none", w=2.2, data=None, dash=None):
        self._el("circle", {"cx": float(c[0]), "cy": float(c[1]), "r": float(r), "fill": fill,
                            "stroke": INK if w else "none", "stroke-width": w or None,
                            "stroke-dasharray": dash, **_data(data)})

    def text(self, p, content, *, size=22, anchor="middle", data=None, weight=None, color=INK):
        # 竖直居中靠 dominant-baseline 不稳，这里统一按字号 0.36 下移近似居中
        self._el("text", {"x": float(p[0]), "y": float(p[1]) + size * 0.36, "font-size": size,
                          "font-family": FONT, "text-anchor": anchor, "fill": color,
                          "font-weight": weight, **_data(data)}, str(content))

    @contextmanager
    def group(self, data=None, dx=0.0, dy=0.0):
        transform = f"translate({_num(float(dx))},{_num(float(dy))})" if dx or dy else None
        self.body.append(f"<g {_attrs({'transform': transform, **_data(data)})}>")
        try:
            yield
        finally:
            self.body.append("</g>")

    def __str__(self) -> str:
        w, h = _num(self.width), _num(self.height)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
                f'viewBox="0 0 {w} {h}">' + "".join(self.body) + "</svg>")


# ---------------------------------------------------------------- 解析：判题器只看这个
@dataclass
class Prim:
    tag: str
    data: dict  # 自己和祖先 g 的 data-*（就近覆盖）
    points: list = field(default_factory=list)  # 绝对坐标
    text: str = ""
    attrs: dict = field(default_factory=dict)
    offset: tuple = (0.0, 0.0)  # 最近一个带 data 的祖先 g 的平移，用来换回该组局部坐标

    def local(self):
        ox, oy = self.offset
        return [(x - ox, y - oy) for x, y in self.points]


_TRANSLATE = re.compile(r"translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)")


def parse(svg: str) -> list[Prim]:
    root = ET.fromstring(svg)
    out: list[Prim] = []

    def walk(node, dx, dy, data, offset):
        tag = node.tag.rsplit("}", 1)[-1]
        own = {k[5:]: v for k, v in node.attrib.items() if k.startswith("data-")}
        if tag in ("g", "svg"):
            found = _TRANSLATE.search(node.attrib.get("transform", ""))
            if found:
                dx, dy = dx + float(found.group(1)), dy + float(found.group(2))
            if own:
                offset = (dx, dy)
            for child in node:
                walk(child, dx, dy, {**data, **own}, offset)
            return
        a = node.attrib
        merged = {**data, **own}
        if tag == "line":
            pts = [(float(a["x1"]), float(a["y1"])), (float(a["x2"]), float(a["y2"]))]
        elif tag in ("polyline", "polygon"):
            pts = [tuple(map(float, p.split(","))) for p in a.get("points", "").split()]
        elif tag == "rect":
            x, y, w, h = (float(a.get(k, 0)) for k in ("x", "y", "width", "height"))
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        elif tag == "circle":
            pts = [(float(a["cx"]), float(a["cy"]))]
        elif tag == "text":
            pts = [(float(a["x"]), float(a["y"]))]
        else:
            return
        pts = [(x + dx, y + dy) for x, y in pts]
        if tag == "rect" and not own and not data and float(a.get("x", 0)) == 0 and float(a.get("y", 0)) == 0:
            return  # 底色
        out.append(Prim(tag, merged, pts, (node.text or "").strip(), dict(a), offset))

    walk(root, 0.0, 0.0, {}, (0.0, 0.0))
    return out


def by(prims: list[Prim], **match) -> list[Prim]:
    return [p for p in prims if all(p.data.get(k) == v for k, v in match.items())]


# ---------------------------------------------------------------- 栅格化
def rasterize(svg: str, scale: int = SCALE) -> bytes:
    return cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=scale)


def png_image(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("L")


def raster_ok(png: bytes) -> bool:
    image = png_image(png)
    box = ImageOps.invert(image).getbbox()
    w, h = image.size
    return box is not None and box[0] >= 1 and box[1] >= 1 and box[2] <= w - 1 and box[3] <= h - 1


# ---------------------------------------------------------------- 选项排布：2×2，字母在格子下方
def options_sheet(cells: dict, cell_w: float, cell_h: float, *, cols: int = 2, gap: float = 18,
                  label_h: float = 34) -> Svg:
    """cells: 字母 -> 回调 draw(svg)，在 (0,0)-(cell_w,cell_h) 的局部坐标里画。"""
    rows = math.ceil(len(cells) / cols)
    svg = Svg(cols * cell_w + (cols - 1) * gap + 16, rows * (cell_h + label_h) + (rows - 1) * gap + 12)
    for index, letter in enumerate(LETTERS[: len(cells)]):
        r, c = divmod(index, cols)
        x0, y0 = 8 + c * (cell_w + gap), 6 + r * (cell_h + label_h + gap)
        with svg.group({"option": letter}, x0, y0):
            cells[letter](svg)
        svg.text((x0 + cell_w / 2, y0 + cell_h + label_h / 2), letter, size=24, data={"label": letter})
    return svg


# ---------------------------------------------------------------- 出题循环
def place_answer(answer: int, n: int, key: str, rng: random.Random) -> list[int]:
    others = [i for i in range(n) if i != answer]
    rng.shuffle(others)
    return [answer if letter == key else others.pop() for letter in LETTERS[:n]]


def check(family, svgs: dict, pngs: dict, key: str, stem: str | None = None,
          texts: list[str] | None = None) -> tuple[list[str], dict]:
    """渲染检查 + 判题器。stem / texts 是考生看到的题干与选项文字，文字选项的题型族要读它们。"""
    issues = [f"{part} 渲染越界或空白" for part, png in pngs.items() if not raster_ok(png)]
    try:
        verdict = family.judge(svgs, pngs, stem=stem, texts=texts)
    except (ValueError, KeyError) as exc:
        return issues + [f"判题器读图失败：{exc}"], {}
    issues += list(verdict.get("issues") or [])
    correct = list(verdict.get("correct") or [])
    if len(correct) != 1:
        issues.append(f"符合题意的选项有 {len(correct)} 个：{correct}")
    elif correct[0] != key:
        issues.append(f"答案键是 {key}，判题器得出 {correct[0]}")
    return issues, verdict


def option_texts(family, draft: dict, order: list[int]) -> list[str]:
    """选项文字：图选项写「图A」（选项画在题图里，与外采图推题同一写法），文字选项由题型族给。"""
    if hasattr(family, "option_texts"):
        return family.option_texts(draft, order)
    return [f"图{letter}" for letter in LETTERS[: len(order)]]


def make_item(family, seed: str, difficulty: str, key: str, max_tries: int | None = None) -> dict:
    """出一道：生成 → 渲染 → 只看图判题；不过就换子种子重出。"""
    max_tries = max_tries or getattr(family, "MAX_TRIES", 40)
    rejected = []
    for attempt in range(max_tries):
        rng = random.Random(f"{family.NAME}|{seed}|{attempt}")
        draft = family.generate(rng, difficulty)
        if draft is None:
            continue
        order = place_answer(draft["answer"], len(draft["options"]), key, rng)
        svgs = family.render(draft, order)
        pngs = {part: rasterize(svg) for part, svg in svgs.items()}
        texts = option_texts(family, draft, order)
        issues, verdict = check(family, svgs, pngs, key, draft["stem"], texts)
        if not issues:
            return {"draft": draft, "order": order, "svgs": svgs, "pngs": pngs, "verdict": verdict,
                    "attempt": attempt, "rejected": rejected, "option_texts": texts,
                    "explanation": family.explain(verdict, key)}
        rejected.append({"attempt": attempt, "issues": issues[:4]})
    raise RuntimeError(f"{family.NAME} 种子 {seed}：{max_tries} 次都没过判题器（最后一次：{rejected[-1]['issues'] if rejected else '无产出'}）")


def tier_of(difficulty: str | None, rng: random.Random) -> str:
    if difficulty in TIERS:
        return difficulty
    return rng.choice(("easy", "mid", "mid", "hard"))


def verified(family, seed: str, difficulty: str = "mid", key: str = "A") -> tuple[dict, list[int], dict, dict]:
    """自检用：拿一道已过审的题，返回 (draft, order, svgs, pngs)，负例在它上面改。"""
    item = make_item(family, seed, difficulty, key)
    return item["draft"], item["order"], item["svgs"], item["pngs"]

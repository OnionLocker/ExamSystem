#!/usr/bin/env python3
"""Generate a neutral black-and-white exam diagram through CLIPROXY."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageOps


BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("QUESTION_IMAGE_MODEL", "gemini-3.1-flash-image")
STYLE_GUARD = """你正在为中国公务员行测题绘制题目示意图，不是在制作解析图。
硬性要求：
- 只画下方规格明确允许出现的已知对象与关系，不补充推导、答案特征或解题步骤。
- 白底黑色线稿，接近纸质真题插图；紧凑留白，禁止彩色、渐变、阴影、纹理和装饰。
- 禁止教学标题、步骤编号、流程箭头、剪刀图标，以及规格未明确要求的字母、数字、公式和尺寸标签。
- 线条清晰，缩小到约 420 CSS 像素宽时仍能辨认。
- 图片中不要加入边框外说明、答案、解析或水印。

允许绘制的规格：
"""


def api_key() -> str:
    key = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if key:
        return key
    env_file = Path.home() / ".hermes" / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("CLIPROXY_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("CLIPROXY_API_KEY not found")


def data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def extract_image(payload: dict) -> bytes:
    message = payload.get("choices", [{}])[0].get("message", {})
    candidates: list[str] = []
    for image in message.get("images") or []:
        image_url = image.get("image_url", {}) if isinstance(image, dict) else {}
        url = image_url.get("url") if isinstance(image_url, dict) else image_url
        if isinstance(url, str):
            candidates.append(url)
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            image_url = part.get("image_url", {})
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if isinstance(url, str):
                candidates.append(url)
    elif isinstance(content, str):
        candidates.extend(re.findall(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", content))

    if not candidates:
        raise RuntimeError(payload.get("error", {}).get("message") or "model returned no image")
    src = candidates[0]
    if src.startswith("data:image/"):
        return base64.b64decode(src.split(",", 1)[1])
    with urllib.request.urlopen(src, timeout=120) as response:
        return response.read()


def make_exam_style(raw: bytes, output: Path) -> None:
    image = Image.open(io.BytesIO(raw))
    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    # Remove color/shading so generated art cannot use color as an unintended hint.
    mono = gray.point(lambda value: 255 if value > 205 else 0, mode="1").convert("L")
    diff = ImageChops.difference(mono, Image.new("L", mono.size, 255))
    if bbox := diff.getbbox():
        left, top, right, bottom = bbox
        margin = max(18, round(max(right - left, bottom - top) * 0.035))
        mono = mono.crop((
            max(0, left - margin),
            max(0, top - margin),
            min(mono.width, right + margin),
            min(mono.height, bottom + margin),
        ))
    if max(mono.size) > 1400:
        ratio = 1400 / max(mono.size)
        mono = mono.resize(
            (round(mono.width * ratio), round(mono.height * ratio)),
            Image.Resampling.LANCZOS,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    mono.save(output, "PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference", action="append", type=Path, default=[])
    parser.add_argument("--aspect-ratio", default="4:3")
    parser.add_argument("--resolution", choices=("512px", "1K", "2K"), default="1K")
    args = parser.parse_args()

    parts: list[dict] = [{
        "type": "text",
        "text": STYLE_GUARD + args.prompt_file.read_text(encoding="utf-8").strip(),
    }]
    for reference in args.reference[:3]:
        parts.append({"type": "image_url", "image_url": {"url": data_url(reference)}})

    payload = {
        "model": MODEL,
        "modalities": ["text", "image"],
        "messages": [{"role": "user", "content": parts}],
        "image_config": {
            "aspect_ratio": args.aspect_ratio,
            "image_size": args.resolution,
        },
    }
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key()}",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.loads(response.read().decode("utf-8"))
    make_exam_style(extract_image(result), args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()

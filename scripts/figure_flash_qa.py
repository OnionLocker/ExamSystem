#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把考生在练习页 iPad 上实际看到的那一张图丢给 Gemini Flash 质检。

不送原图，也不另送手机缩略图。只送一张：object-contain 进 768x480
（对齐练习页 max-w-full / sm:max-h-[480px]）。
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image


BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("FIGURE_FLASH_QA_MODEL") or os.environ.get(
    "QUALITY_GATE_MODEL", "gemini-3.6-flash-high"
)
IPAD_REVIEW_MAX_W = int(os.environ.get("FIGURE_FLASH_REVIEW_WIDTH", "768"))
IPAD_REVIEW_MAX_H = int(os.environ.get("FIGURE_FLASH_REVIEW_HEIGHT", "480"))
RETRIES = 2

SYSTEM_PROMPT = """你是广东公务员考试作图质检员。你只收到一张图：练习页 iPad 考生视图（最长边落入 768x480），就是考生在平板上看到的大小，不是 SVG，也不是放大后的原图像素。

只根据这一张图判断。禁止根据题干脑补「应该有导线/剖面」。原图像素再大也不算过。

必须 REJECT：
1. 几乎只有文字标签，没有装置线稿。电路看不到闭合导线和元件；系谱没有世代连线；锋面没有大块气团楔形剖面（不能用几个小箭头头充数）；海陆风没有环流箭头；地球自转没有地球圆面。
2. 图种和题干不是同一套考法（等高线平面图配锋面剖面、食物网配反射弧、海陆风配锋面）。
3. 几何自相矛盾：太阳光线方向冲突、声明相交但线不相交、昼夜与光线相反、元件叠在原点/一角、大片空白。
4. 练习页尺寸下甲/乙/丙、①②、刻度、虚线读不清或糊成一团。
5. 图上写出了 must_derive 或答案（冷锋、暖锋、感受器、传导方向等）。
6. 教学性多余物：清单/题干没有的木块、铁块、草兔狐。
7. 电路外框回线是干路，不算短路。短路仅指越过灯泡/电阻的直连导线。不要因为矩形回路就 REJECT。


PASS 必须五关全 true，且 issues 为空。只输出一个 JSON 对象，不要 Markdown：
{"verdict":"PASS 或 REJECT","checks":{"apparatus":true,"readable":true,"kind_match":true,"no_contradiction":true,"no_leak":true},"issues":["中文短句"]}
"""

CHECK_LABELS = {
    "apparatus": "缩小后看不见完整装置",
    "readable": "缩小后字或线读不清",
    "kind_match": "图种和题干对不上",
    "no_contradiction": "图上几何自相矛盾",
    "no_leak": "图上泄漏了答案",
}


def api_key() -> str:
    key = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if key:
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("CLIPROXY_API_KEY not found")


def image_part(data: bytes, mime: str = "image/png") -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


def resize_png(path: Path, width: int) -> bytes:
    with Image.open(path) as image:
        image = image.convert("RGB")
        height = max(1, round(image.height * width / image.width))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, "PNG")
        return output.getvalue()


def fit_ipad_png(path: Path) -> bytes:
    """Practice-page iPad view: object-contain into 768x480."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        src_w, src_h = image.size
        scale = min(IPAD_REVIEW_MAX_W / src_w, IPAD_REVIEW_MAX_H / src_h, 1.0)
        width = max(1, round(src_w * scale))
        height = max(1, round(src_h * scale))
        if (width, height) != (src_w, src_h):
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, "PNG")
        return output.getvalue()


def parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip(), flags=re.I)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError(f"Flash 看图未返回 JSON：{cleaned[:240]}")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("看图质检结果必须是 JSON 对象")
    return value


def response_text(payload: dict) -> str:
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    ).strip()


def issues_from_result(result: dict) -> list[str]:
    issues = [str(item).strip() for item in (result.get("issues") or []) if str(item).strip()]
    checks = result.get("checks") if isinstance(result.get("checks"), dict) else {}
    verdict = str(result.get("verdict") or "").upper()
    for key, label in CHECK_LABELS.items():
        if checks.get(key) is False and label not in issues:
            issues.append(label)
    if verdict == "PASS" and all(checks.get(key) is True for key in CHECK_LABELS) and not issues:
        return []
    if verdict != "PASS" and not issues:
        issues.append("Flash看图质检未通过")
    return list(dict.fromkeys(issues))


def _user_spec(request: dict, dest: Path) -> str:
    return json.dumps(
        {
            "question_id": request.get("question_id") or dest.stem,
            "module": request.get("module") or "",
            "tags": list(request.get("tags") or []),
            "exam_move": request.get("exam_move") or "",
            "stem": request.get("stem") or "",
            "must_show": list(request.get("must_show") or []),
            "must_not": list(request.get("must_not") or []),
            "must_derive": list(request.get("must_derive") or []),
            "review_width": IPAD_REVIEW_MAX_W,
            "review_height": IPAD_REVIEW_MAX_H,
        },
        ensure_ascii=False,
    )


def review_figure(
    request: dict,
    dest: Path,
    *,
    caller: Callable[..., dict] | None = None,
) -> dict:
    review = fit_ipad_png(dest)
    parts = [
        {"type": "text", "text": "作图规格（只作对照，不要脑补图上没有的装置）：\n" + _user_spec(request, dest)},
        {"type": "text", "text": f"练习页 iPad 视图 {IPAD_REVIEW_MAX_W}x{IPAD_REVIEW_MAX_H}："},
        image_part(review),
    ]
    if caller is not None:
        return caller(SYSTEM_PROMPT, parts)
    body = json.dumps(
        {
            "model": MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": parts},
            ],
        }
    ).encode("utf-8")
    error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/chat/completions",
                data=body,
                method="POST",
                headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return parse_json(response_text(payload))
        except Exception as exc:
            error = exc
            if attempt + 1 < RETRIES:
                time.sleep(1.5)
    raise RuntimeError(f"Flash 看图质检失败：{error}")


def review_figure_issues(
    request: dict,
    dest: Path,
    *,
    caller: Callable[..., dict] | None = None,
) -> list[str]:
    try:
        result = review_figure(request, dest, caller=caller)
    except Exception as exc:
        return [f"Flash看图质检失败：{exc}"]
    dest.with_suffix(".flash.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    issues = issues_from_result(result)
    return [f"Flash看图：{item}" for item in issues]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gemini Flash 看图质检（练习页 iPad 一张图）")
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--stem", default="")
    parser.add_argument("--tag", action="append", default=[])
    args = parser.parse_args()
    request = {"stem": args.stem, "tags": args.tag, "question_id": args.png.stem}
    print(json.dumps(review_figure(request, args.png), ensure_ascii=False, indent=2))

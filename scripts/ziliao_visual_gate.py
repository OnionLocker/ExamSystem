#!/usr/bin/env python3
"""Use Gemini Flash vision to reject unclear data-analysis figures."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image


BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("ZILIAO_VISUAL_REVIEW_MODEL", "gemini-3.7-flash-high")
MOBILE_WIDTH = 320
RETRIES = 2

SYSTEM_PROMPT = """你是独立的公考资料分析图表质检员。你看到的第一张图是原图，第二张图是按320px宽缩放后的考生视图。
只审查图表质量，不润色题目。逐项检查：
1. 标题、单位、图例、坐标轴、刻度、年份、行列名和数据标签是否完整；
2. 数字是否与柱形、折线、网格线、边框或其他文字重合、遮挡或被裁切；
3. 多系列的单位是否与系列一一对应，是否需要靠正文顺序猜测；
4. 原图和320px图中的全部关键信息是否都能直接辨认；
5. 图中可见数值是否与提供的材料和题目上下文冲突。
任何一项不清楚都必须判 REJECT。只输出一个JSON对象，不要Markdown：
{"verdict":"PASS或REJECT","checks":{"complete":true,"no_overlap":true,"units_mapped":true,"mobile_readable":true,"context_consistent":true},"issues":["具体问题"]}"""


def api_key() -> str:
    if key := os.environ.get("CLIPROXY_API_KEY", "").strip():
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("CLIPROXY_API_KEY not found")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_part(data: bytes, mime: str = "image/png") -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


def mobile_png(path: Path) -> bytes:
    with Image.open(path) as image:
        image = image.convert("RGB")
        height = max(1, round(image.height * MOBILE_WIDTH / image.width))
        image = image.resize((MOBILE_WIDTH, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, "PNG")
        return output.getvalue()


def response_text(payload: dict) -> str:
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    ).strip()


def parse_json(text: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"Gemini Flash 未返回 JSON：{text[:240]}")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("视觉质检结果必须是 JSON 对象")
    return value


def safe_image(batch_dir: Path, relative: str) -> Path:
    path = (batch_dir / relative).resolve()
    root = batch_dir.resolve()
    if root not in path.parents or not relative.startswith("images/"):
        raise ValueError(f"非法图片路径：{relative}")
    if not path.is_file():
        raise ValueError(f"图片不存在：{relative}")
    return path


def collect_images(batch_dir: Path) -> list[dict]:
    materials_path = batch_dir / "materials.json"
    questions_path = batch_dir / "questions.json"
    materials = json.loads(materials_path.read_text(encoding="utf-8")) if materials_path.exists() else []
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    questions_by_material: dict[str, list[dict]] = {}
    for question in questions:
        questions_by_material.setdefault(str(question.get("material_id") or ""), []).append(question)

    found: dict[str, dict] = {}

    def add(relative: str, context: dict) -> None:
        path = safe_image(batch_dir, relative)
        found.setdefault(relative, {"path": path, "contexts": []})["contexts"].append(context)

    for material in materials:
        material_id = str(material.get("external_id") or "")
        context = {
            "kind": "material",
            "material_id": material_id,
            "material": material.get("content") or "",
            "questions": [
                {
                    "id": q.get("external_id"),
                    "stem": q.get("stem"),
                    "options": [
                        {"key": option.get("key"), "text": option.get("text")}
                        for option in q.get("options") or []
                    ],
                }
                for q in questions_by_material.get(material_id, [])
            ],
        }
        for relative in material.get("images") or []:
            add(str(relative), context)

    for question in questions:
        base = {
            "kind": "question",
            "question_id": question.get("external_id"),
            "stem": question.get("stem"),
            "options": [
                {"key": option.get("key"), "text": option.get("text")}
                for option in question.get("options") or []
            ],
        }
        for relative in question.get("stem_images") or []:
            add(str(relative), base)
        for relative in question.get("explanation_images") or []:
            add(str(relative), base)
        for option in question.get("options") or []:
            for relative in option.get("images") or []:
                add(str(relative), {**base, "option_key": option.get("key")})
    return [found[key] for key in sorted(found)]


def review_image(item: dict, key: str) -> dict:
    path: Path = item["path"]
    mobile = mobile_png(path)
    with Image.open(path) as image:
        width, height = image.size
    context = json.dumps(item["contexts"], ensure_ascii=False, separators=(",", ":"))
    parts = [
        {
            "type": "text",
            "text": f"图片文件：{path.name}\n相关材料与题目上下文：{context}",
        },
        {"type": "text", "text": "原图："},
        image_part(path.read_bytes(), "image/png" if path.suffix.lower() == ".png" else "image/jpeg"),
        {"type": "text", "text": "320px宽考生视图："},
        image_part(mobile),
    ]
    body = json.dumps(
        {
            "model": MODEL,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": parts},
            ],
        }
    ).encode("utf-8")
    error = None
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(
                f"{BASE_URL}/chat/completions",
                data=body,
                method="POST",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = parse_json(response_text(payload))
            checks = result.get("checks") or {}
            passed = (
                str(result.get("verdict") or "").upper() == "PASS"
                and all(checks.get(name) is True for name in (
                    "complete", "no_overlap", "units_mapped", "mobile_readable", "context_consistent"
                ))
                and not (result.get("issues") or [])
            )
            return {
                "path": str(path.relative_to(path.parents[1])),
                "sha256": sha256(path),
                "width": width,
                "height": height,
                "mobile_width": MOBILE_WIDTH,
                "verdict": "PASS" if passed else "REJECT",
                "checks": checks,
                "issues": result.get("issues") or [],
                "raw_verdict": result.get("verdict"),
            }
        except Exception as exc:
            error = exc
            if attempt + 1 < RETRIES:
                time.sleep(2)
    raise RuntimeError(f"{path.name} 视觉质检调用失败：{error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    batch_dir = args.batch_dir.resolve()
    items = collect_images(batch_dir)
    if not items:
        raise SystemExit("批次没有需要检查的图表")
    results = [review_image(item, api_key()) for item in items]
    verdict = "PASS" if all(item["verdict"] == "PASS" for item in results) else "REJECT"
    evidence = {
        "version": 1,
        "kind": "ziliao-visual-quality",
        "batch_id": json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8")).get("batch_id"),
        "model": MODEL,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mobile_width": MOBILE_WIDTH,
        "verdict": verdict,
        "images": results,
    }
    output = args.output or batch_dir / "evidence" / "ziliao-visual-quality.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

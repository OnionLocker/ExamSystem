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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import sys
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_router

if not model_router.supports_vision():
    raise SystemExit("当前模型不支持图表质检（需要视觉能力）；请先在「模型」页签切换到支持视觉的模型（如 Gemini）。")

BASE_URL = model_router.resolve_base_url()
MODEL = model_router.resolve_model("ziliao")
# The target practice layout is iPad split view; 320px makes legitimate
# multi-column exam tables unreadable and is not the user's display target.
MOBILE_WIDTH = 768
RETRIES = 2

SYSTEM_PROMPT = """你是独立的公考资料分析图表质检员。你看到的第一张图是原图，第二张图是按768px宽缩放后的iPad考生视图。
只审查图表质量，不润色题目。逐项检查：
1. 标题、单位、图例、坐标轴、刻度、年份、行列名和数据标签是否完整；
2. 数字是否与柱形、折线、网格线、边框或其他文字重合、遮挡或被裁切；
3. 多系列的单位是否与系列一一对应，是否需要靠正文顺序猜测；
4. 原图和768px图中的全部关键信息是否都能直接辨认；
5. 图中可见数值是否与提供的材料和题目上下文冲突。
例外：上下文带 "chart_match_option": true 的是图表匹配题的选项图，按真题惯例故意不标数值和刻度，
只需检查图形、图例或分类标签清楚可辨，且形状与 figure_data 一致；缺少数值标签不算 complete=false。
任何一项不清楚都必须判 REJECT。只输出一个JSON对象，不要Markdown：
{"verdict":"PASS或REJECT","checks":{"complete":true,"no_overlap":true,"units_mapped":true,"mobile_readable":true,"context_consistent":true},"issues":["具体问题"]}"""


def api_key() -> str:
    try:
        return model_router.resolve_api_key()
    except RuntimeError:
        pass
    if key := os.environ.get("CLIPROXY_API_KEY", "").strip():
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("模型 API key not found（检查 ~/.hermes/.env）")


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
            figure = option.get("figure") if isinstance(option.get("figure"), dict) else None
            extra = {"chart_match_option": True,
                     "figure_data": {k: figure.get(k) for k in ("kind", "categories", "values")}} if figure else {}
            for relative in option.get("images") or []:
                add(str(relative), {**base, "option_key": option.get("key"), **extra})
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
        {"type": "text", "text": "768px宽iPad考生视图："},
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
            model_router.log_call("visual")
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


def cache_key(item: dict) -> str:
    """同一张图、同样的上下文、同一模型与规则才复用结论；材料图只看材料正文，不随题目变化，可在出题前先查。"""
    contexts = [{k: v for k, v in c.items() if not (c.get("kind") == "material" and k == "questions")}
                for c in item["contexts"]]
    digest = hashlib.sha256()
    for part in (MODEL, SYSTEM_PROMPT, json.dumps(contexts, ensure_ascii=False, sort_keys=True), sha256(item["path"])):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return "visual:" + digest.hexdigest()


def review_all(batch_dir: Path, items: list[dict]) -> list[dict]:
    import quality_memory
    cached = quality_memory.load(batch_dir)["reviews"]
    keys = [cache_key(item) for item in items]
    pending = [index for index, key in enumerate(keys) if not isinstance(cached.get(key), dict)]
    fresh: dict[int, dict] = {}
    if pending:
        key = api_key()
        with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
            fresh = dict(zip(pending, pool.map(lambda index: review_image(items[index], key), pending)))
    passed = {keys[i]: result for i, result in fresh.items() if result["verdict"] == "PASS"}
    if passed:
        quality_memory.update(batch_dir, reviews=passed)
    return [fresh.get(index) or cached[keys[index]] for index in range(len(items))]


def precheck_material_images(batch_dir: Path) -> list[dict]:
    """材料定稿后、出题同时先查材料图；结论按图片与材料正文记忆，篇内审核时直接命中。"""
    items = [item for item in collect_images(batch_dir.resolve())
             if all(context.get("kind") == "material" for context in item["contexts"])]
    return review_all(batch_dir.resolve(), items) if items else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    batch_dir = args.batch_dir.resolve()
    items = collect_images(batch_dir)
    if not items:
        raise SystemExit("批次没有需要检查的图表")
    results = review_all(batch_dir, items)
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

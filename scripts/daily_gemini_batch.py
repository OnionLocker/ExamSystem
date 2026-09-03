#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Direct cliproxy Gemini draft for the 04:00 daily batch. No Hermes agent."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from render_ziliao_figure import render_bars, render_pie, render_table
from scheduler_common import ROOT, daily_source_name, difficulty_tier


BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("DAILY_GEMINI_MODEL") or os.environ.get(
    "CLIPROXY_PDF_MODEL", "gemini-3.8-flash-high"
)
RETRIES = 3
SKILL_REF = ROOT / "hermes-skills" / "quiz-pipeline" / "references"
HARD_RULES = SKILL_REF / "module-hard-rules.md"
PRINCIPLES = SKILL_REF / "reference-style-principles.md"
ZILIAO_STYLES = SKILL_REF / "ziliao-paper-styles.md"
IMAGE_SCRIPT = ROOT / "scripts" / "generate-question-image.py"
GATE_SCRIPT = ROOT / "scripts" / "generation_gate.py"
IMPORT_SCRIPT = ROOT / "scripts" / "import-batch.mjs"
CAT_ZILIAO = "\u8d44\u6599\u5206\u6790"
CAT_KEPUI = "\u79d1\u5b66\u63a8\u7406"
REGION = "\u5e7f\u4e1c-\u7701\u76f4"


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


def parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"Gemini returned no JSON: {cleaned[:300]}")
        value = json.loads(cleaned[start : end + 1])
    if isinstance(value, list):
        value = {"questions": value}
    if not isinstance(value, dict):
        raise ValueError("draft must be a JSON object")
    return value


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def qid(batch_id: str, index: int) -> str:
    return f"{batch_id}_{index:02d}"


def options_list(raw: Any) -> list[dict]:
    if isinstance(raw, dict):
        return [{"key": str(key), "text": "" if value is None else str(value)} for key, value in raw.items()]
    out = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["key"] = str(row.get("key") or "")
        if "text" not in row:
            row["text"] = ""
        out.append(row)
    return out


def remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def call_gemini(prompt: str, deadline: float) -> dict:
    timeout = max(60, min(600, int(remaining(deadline) - 20)))
    if remaining(deadline) < 30:
        raise RuntimeError("timed out before Gemini draft")
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 32768,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    last = ""
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(
                f"{BASE_URL}/chat/completions",
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key()}",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            draft = parse_json(text)
            if not isinstance(draft.get("questions"), list) or not draft["questions"]:
                raise ValueError("Gemini returned no questions")
            return draft
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            if attempt + 1 == RETRIES or remaining(deadline) < 40:
                break
            wait = 20 * (attempt + 1)
            if isinstance(exc, urllib.error.HTTPError) and exc.code != 429:
                wait = 2
            time.sleep(min(wait, remaining(deadline) / 2))
    raise RuntimeError(last)


def augment_prompt(prompt: str, run: dict, batch_dir: Path, error: str | None = None) -> str:
    chunks = [prompt]
    for path in (HARD_RULES, PRINCIPLES):
        if path.is_file():
            chunks.append(f"\n# {path.name}\n{path.read_text(encoding='utf-8')}")
    if run["module"] == CAT_ZILIAO and ZILIAO_STYLES.is_file():
        chunks.append(f"\n# {ZILIAO_STYLES.name}\n{ZILIAO_STYLES.read_text(encoding='utf-8')}")
    existing = batch_dir / "questions.json"
    if existing.is_file():
        chunks.append(
            "\n# Existing unpublished draft (keep batch_id, fix this JSON):\n"
            + existing.read_text(encoding="utf-8")[:20000]
        )
    if error:
        chunks.append(
            "\n# Previous generation_gate failure. Output a complete corrected JSON object.\n"
            + error[-8000:]
        )
    return "\n".join(chunks)


def render_one(fig: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    kind = str(fig.get("kind") or "")
    title = str(fig.get("title") or "")
    if kind == "table":
        render_table(
            title,
            list(fig.get("headers") or []),
            [list(row) for row in (fig.get("rows") or [])],
            dest,
            str(fig.get("unit") or ""),
            str(fig.get("note") or ""),
        )
        return
    if kind == "bars":
        series = []
        for item in fig.get("series") or []:
            if isinstance(item, dict):
                series.append((str(item.get("name") or ""), [float(x) for x in item.get("values") or []]))
        render_bars(title, str(fig.get("ylabel") or ""), list(fig.get("categories") or []), series, dest)
        return
    if kind == "pie":
        slices = []
        for item in fig.get("slices") or []:
            if isinstance(item, dict):
                slices.append((str(item.get("name") or ""), float(item.get("value") or 0)))
        render_pie(title, slices, dest)
        return
    raise ValueError(f"unsupported figure kind: {kind}")


def generate_line_image(facts: list[str], dest: Path, deadline: float) -> None:
    if dest.is_file():
        return
    if remaining(deadline) < 40:
        raise RuntimeError(f"timed out before drawing {dest.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    prompt_file = dest.with_suffix(".prompt.txt")
    prompt_file.write_text("\n".join(str(item) for item in facts if str(item).strip()), encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(IMAGE_SCRIPT), "--prompt-file", str(prompt_file), "--output", str(dest)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max(60, min(300, int(remaining(deadline) - 10))),
        )
    finally:
        prompt_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "image generation failed").strip()[-1500:])


def pop_figure(holder: dict) -> dict | None:
    fig = holder.pop("figure", None)
    return fig if isinstance(fig, dict) else None


def render_assets(batch_dir: Path, draft: dict, deadline: float) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    specs = draft.get("image_specs") or draft.get("image-specs") or {}
    spec_rows = specs.get("questions") if isinstance(specs, dict) else specs
    by_id = {
        str(item.get("question_id") or ""): item
        for item in (spec_rows or [])
        if isinstance(item, dict)
    }

    # 收集所有需要生成的图像任务（需要 AI 生成的）
    ai_image_tasks = []  # (facts, dest, question, index)

    for index, question in enumerate(draft.get("questions") or [], 1):
        spec = by_id.get(str(question.get("external_id") or ""))
        facts = list((spec or {}).get("image_facts") or [])
        fig = pop_figure(question)
        if fig and not facts:
            dest = batch_dir / str(fig.get("file") or f"images/q-{index:02d}-stem.png")
            render_one(fig, dest)
            question["stem_images"] = [str(dest.relative_to(batch_dir))]
        elif facts:
            rel = (question.get("stem_images") or [f"images/q-{index:02d}-stem.png"])[0]
            dest = batch_dir / rel
            question["stem_images"] = [rel]
            ai_image_tasks.append((facts, dest))
        for option in question.get("options") or []:
            opt_fig = pop_figure(option)
            if not opt_fig:
                continue
            rel = str(opt_fig.get("file") or (option.get("images") or [None])[0] or "")
            if not rel:
                rel = f"images/q-{index:02d}-opt-{option.get('key')}.png"
            render_one(opt_fig, batch_dir / rel)
            option["images"] = [rel]

    # 并行生成所有 AI 图像（判断推理5张图 + 科学推理5张图可以同时生成）
    if ai_image_tasks:
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(generate_line_image, facts, dest, deadline)
                for facts, dest in ai_image_tasks
            ]
            for future in as_completed(futures):
                future.result()  # 抛出异常则整个批次失败

    for index, material in enumerate(draft.get("materials") or [], 1):
        fig = pop_figure(material)
        if not fig:
            continue
        rel = str(fig.get("file") or f"images/m-{index:02d}-{fig.get('kind') or 'table'}.png")
        render_one(fig, batch_dir / rel)
        images = [str(item) for item in (material.get("images") or []) if str(item)]
        if rel not in images:
            images.append(rel)
        material["images"] = images
    for fig in draft.get("figures") or []:
        if not isinstance(fig, dict):
            continue
        rel = str(fig.get("file") or "")
        if not rel:
            continue
        render_one(fig, batch_dir / rel)


def stamp_questions(run: dict, questions: list[dict]) -> list[dict]:
    source = daily_source_name(run["module"], run["plan_date"])
    year = int(str(run["plan_date"])[:4])
    out = []
    for index, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            continue
        row = dict(question)
        row["external_id"] = str(row.get("external_id") or qid(run["batch_id"], index))
        row["source"] = source
        row["year"] = year
        row["region"] = REGION
        row["category"] = str(row.get("category") or run["module"])
        row["options"] = options_list(row.get("options"))
        if not str(row.get("analysis") or "").strip() and row.get("explanation"):
            row["analysis"] = row["explanation"]
        if run["module"] == CAT_KEPUI:
            row["category"] = CAT_KEPUI
            row["sub_category"] = CAT_KEPUI
        out.append(row)
    return out


def write_batch(run: dict, batch_dir: Path, draft: dict) -> None:
    from normalize_ai_batch import generation_payload_extras

    batch_dir.mkdir(parents=True, exist_ok=True)
    questions = stamp_questions(run, list(draft.get("questions") or []))
    extras = generation_payload_extras(
        run["module"], int(run["planned_count"]), str(run["batch_id"])
    )
    materials = [item for item in (draft.get("materials") or []) if isinstance(item, dict)]
    source = daily_source_name(run["module"], run["plan_date"])
    for index, material in enumerate(materials, 1):
        material["external_id"] = str(
            material.get("external_id") or f"{run['batch_id']}-M{index:02d}"
        )
        material["source"] = source
    calculations = draft.get("calculations")
    specs = draft.get("image_specs") or draft.get("image-specs")
    dump(batch_dir / "questions.json", questions)
    dump(
        batch_dir / "manifest.json",
        {
            "batch_id": run["batch_id"],
            "source": source,
            "region": REGION,
            "year": int(str(run["plan_date"])[:4]),
            "kind": "ai-generated",
            "difficulty_tier": difficulty_tier(run["plan_date"]),
            "generation": {
                "style_marker": "GONGKAO-STYLE-v1",
                "batch_constraints": extras.get("batch_constraints") or {},
                "generation_contexts": [],
                "evaluation_contexts": [],
            },
        },
    )
    if materials:
        dump(batch_dir / "materials.json", materials)
    if isinstance(calculations, dict):
        dump(batch_dir / "calculations.json", calculations)
    elif isinstance(calculations, list):
        dump(batch_dir / "calculations.json", {"questions": calculations})
    if specs:
        dump(batch_dir / "image-specs.json", specs if isinstance(specs, dict) else {"questions": specs})
    draft["questions"] = questions
    draft["materials"] = materials


def run_cmd(command: list[str], deadline: float, env: dict[str, str]) -> str:
    timeout = max(30, int(remaining(deadline) - 5))
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"timed out: {' '.join(command)}") from exc
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed").strip()[-4000:])
    return (result.stdout or "").strip()


def parse_failed_question_ids(error_message: str) -> list[str]:
    """从 gate 错误信息中解析出失败的题目 ID"""
    import re
    # 匹配类似 "20260903_判断_01_03" 的题目 ID
    pattern = r'\b\d{8}_[^_\s]+_\d+_\d+\b'
    matches = re.findall(pattern, error_message)
    return list(set(matches))


def generate_and_import(
    run: dict,
    batch_dir: Path,
    db_path: Path,
    timeout: int,
    prompt: str,
) -> None:
    deadline = time.monotonic() + timeout
    env = {**os.environ, "EXAM_DB": str(db_path)}
    error = None
    for attempt in range(2):
        if attempt == 0:
            # 首次生成：完整批次
            draft = call_gemini(augment_prompt(prompt, run, batch_dir, error), deadline)
        else:
            # 第二次：尝试增量修复
            failed_ids = parse_failed_question_ids(error or "")
            if failed_ids and len(failed_ids) < int(run["planned_count"]) // 2:
                # 如果失败题目少于一半，尝试只修复这些题
                print(f"尝试增量修复 {len(failed_ids)} 道失败题: {', '.join(failed_ids[:3])}...")
                # 读取现有草稿，只重新生成失败的题
                existing = batch_dir / "questions.json"
                if existing.is_file():
                    import json
                    existing_draft = json.loads(existing.read_text(encoding='utf-8'))
                    # 提取失败题的索引
                    failed_indices = []
                    for i, q in enumerate(existing_draft.get("questions") or []):
                        if str(q.get("external_id")) in failed_ids:
                            failed_indices.append(i + 1)

                    if failed_indices:
                        # 构建增量修复 prompt
                        patch_prompt = augment_prompt(prompt, run, batch_dir, error)
                        patch_prompt += f"\n\n# 增量修复模式\n只需修复以下题号: {', '.join(map(str, failed_indices))}\n"
                        patch_prompt += "保持其他题目不变，只输出完整的 questions.json（包含修复后的题目）。\n"
                        draft = call_gemini(patch_prompt, deadline)
                    else:
                        # 无法定位失败题，全批重生成
                        draft = call_gemini(augment_prompt(prompt, run, batch_dir, error), deadline)
                else:
                    draft = call_gemini(augment_prompt(prompt, run, batch_dir, error), deadline)
            else:
                # 失败题目太多或无法解析，全批重生成
                draft = call_gemini(augment_prompt(prompt, run, batch_dir, error), deadline)

        write_batch(run, batch_dir, draft)
        render_assets(batch_dir, draft, deadline)
        dump(batch_dir / "questions.json", draft["questions"])
        if draft.get("materials"):
            dump(batch_dir / "materials.json", draft["materials"])
        try:
            run_cmd([sys.executable, str(GATE_SCRIPT), "issue", str(batch_dir)], deadline, env)
            error = None
            break
        except RuntimeError as exc:
            error = str(exc)
    if error:
        raise RuntimeError(error)
    run_cmd(["node", str(IMPORT_SCRIPT), str(batch_dir)], deadline, env)

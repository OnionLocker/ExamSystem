#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Direct cliproxy Gemini draft for the 04:00 daily batch. No Hermes agent."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from draw_contract import spec_from_question
from graphic_bank import build_graphic_paper, build_graphic_question
from question_flash_ops import issue_brief, is_graphic, preflight_draft
from normalize_ai_batch import generation_payload_extras
from kaodian_taxonomy import question_primary_tag
from program_figure import build_svg, coerce_kepui_figure, is_program_kind, kind_from_kepui_tag, kind_from_stem, render_program, svg_to_png_many
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
CAT_PANDUAN = "\u5224\u65ad\u63a8\u7406"
CAT_YANYU = "\u8a00\u8bed\u7406\u89e3\u4e0e\u8868\u8fbe"
SCIENCE_TEMPLATE_ORDER = (
    "circuit", "lever", "tank", "reflex", "contour", "front",
    "motion", "food", "pedigree", "force", "pulley",
    "breeze", "earth", "climate", "plate",
)
REGION = "\u5e7f\u4e1c-\u7701\u76f4"

_PIPE: list[dict] = []
_PIPE_T0 = 0.0
_PIPE_LOCK = threading.Lock()


def pipe_span(name: str):
    class _Span:
        def __enter__(self):
            self.t = time.monotonic()
            return self

        def __exit__(self, *_exc):
            with _PIPE_LOCK:
                _PIPE.append({"name": name, "sec": round(time.monotonic() - self.t, 3)})

    return _Span()


def dump_pipe(batch_dir: Path, extra: dict | None = None) -> None:
    events = list(_PIPE)
    jsonl = batch_dir / "pipeline-timing.jsonl"
    if jsonl.is_file():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    extra = dict(extra or {})
    locked_path = batch_dir / "locked-slots.json"
    if locked_path.is_file():
        rows = json.loads(locked_path.read_text(encoding="utf-8"))
        extra["slots"] = [str(item.get("tag") or "") for item in rows if isinstance(item, dict)]
    payload = {
        "elapsed_sec": round(time.monotonic() - _PIPE_T0, 3) if _PIPE_T0 else round(sum(item.get("sec") or 0 for item in events), 3),
        "events": events,
        **extra,
    }
    dump(batch_dir / "pipeline-timing.json", payload)



def science_template_for(stem: str, fallback: str) -> str:
    """Use the named science subject as the figure contract."""
    text = str(stem or "")
    for tokens, kind in (
        (("电路", "电阻", "电流表", "电压表", "串联", "并联"), "circuit"),
        (("杠杆", "钩码", "支点", "动力臂", "阻力臂"), "lever"),
        (("容器", "浮力", "漂浮", "悬浮", "液体", "木块", "小球"), "tank"),
        (("反射弧", "缩手反射", "膝跳"), "reflex"),
        (("锋面", "冷锋", "暖锋", "气团", "降水带"), "front"),
        (("等高线", "山谷", "山脊", "陡崖"), "contour"),
        (("海陆风", "海风", "陆风"), "breeze"),
        (("自转", "昼夜", "昼半球"), "earth"),
        (("气候", "气温年变化"), "climate"),
        (("板块",), "plate"),
    ):
        if any(token in text for token in tokens):
            return kind
    return fallback


def _science_label_text(text: str) -> str:
    value = str(text or "").replace("$", "").replace("\\_", "_")
    return re.sub(r"([RLA])\s*_\s*([0-9]+)", r"\1\2", value)


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
    with pipe_span("gemini_draft"):
        return _call_gemini(prompt, deadline)


def _call_gemini(prompt: str, deadline: float) -> dict:
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
    if error and existing.is_file():
        chunks.append(
            "\n# Existing unpublished draft (keep batch_id, fix this JSON):\n"
            + existing.read_text(encoding="utf-8")[:20000]
        )
    if error:
        from quality_ledger import retry_prompt_block

        chunks.append("\n" + retry_prompt_block(str(run.get("module") or ""), error))
    return "\n".join(chunks)


def figure_already_ok(dest: Path) -> bool:
    if not dest.is_file() or not dest.with_suffix(".svg").is_file():
        return False
    log = dest.with_suffix(".draw.json")
    if not log.is_file():
        return False
    try:
        data = json.loads(log.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("ok"))


def render_one(fig: dict, dest: Path, question: dict | None = None, spec: dict | None = None, batch_dir: Path | None = None, deadline: float | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    kind = str(fig.get("kind") or "")
    skip_draw = kind in {"table", "bars", "pie", "line", "combo", "stackbar", "donut"}
    if (
        question is not None
        and not skip_draw
        and os.environ.get("DRAW_IN_BATCH", "1") != "0"
        and (is_program_kind(kind) or not kind)
    ):
        from draw_agent import draw_figure
        from draw_contract import request_from_question

        if figure_already_ok(dest) and os.environ.get("DRAW_AGENT_FORCE", "0") != "1":
            return
        request = request_from_question(question, spec, fig, dest, batch_dir)
        draw_figure(request, dest, deadline=deadline, batch_dir=batch_dir)
        return
    if is_program_kind(kind):
        render_program(fig, dest)
        return
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
        ylabel = str(fig.get("ylabel") or "")
        # ponytail: series names already carry units; mixed ylabel is a draw error not a new chart
        if len(series) > 1 and any(sep in ylabel for sep in ("/", "\uFF0F")):
            ylabel = ""
        render_bars(title, ylabel, list(fig.get("categories") or []), series, dest)
        return
    if dest.is_file():
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

    # 收集扢�有需要生成的图像任务（需覄1�71ￄ1�77 AI 生成的）
    ai_image_tasks = []  # (facts, dest, question, index)
    locked_jobs = []

    for index, question in enumerate(draft.get("questions") or [], 1):
        qid = str(question.get("external_id") or f"q{index:02d}")
        try:
            spec = by_id.get(qid)
            facts = list((spec or {}).get("image_facts") or [])
            fig = pop_figure(question)
            template = str(question.get("figure_template") or "").strip()
            tag = question_primary_tag(question)
            locked = kind_from_kepui_tag(tag) or template
            if question.get("category") == CAT_KEPUI and locked and is_program_kind(locked):
                fig = {**(fig or {}), "kind": locked}
            extra_parts = []
            for option in question.get("options") or []:
                if isinstance(option, dict):
                    extra_parts.append(str(option.get("text") or ""))
                else:
                    extra_parts.append(str(option))
            extra_parts.extend(str(item) for item in (spec or {}).get("image_facts") or [])
            extra_parts.extend(str(item) for item in (spec or {}).get("image_only_facts") or [])
            contract = question.get("figure_contract") if isinstance(question.get("figure_contract"), dict) else {}
            extra_parts.extend(str(item) for item in (contract.get("must_show") or []))
            fig = coerce_kepui_figure(str(question.get("stem") or ""), fig, tag, extra=" ".join(extra_parts))
            if question.get("category") == CAT_KEPUI and fig and fig.get("kind"):
                question["figure_template"] = fig["kind"]
            if fig:
                dest = batch_dir / str(fig.get("file") or f"images/q-{index:02d}-stem.png")
                locked_kind = question.get("category") == CAT_KEPUI and is_program_kind(str(fig.get("kind") or "")) and bool(kind_from_kepui_tag(tag))
                if locked_kind:
                    locked_jobs.append((qid, fig, dest, question))
                    question["stem_images"] = [str(dest.relative_to(batch_dir))]
                else:
                    with pipe_span(f"draw {qid}"):
                        render_one(fig, dest, question=question, spec=spec, batch_dir=batch_dir, deadline=deadline)
                    question["stem_images"] = [str(dest.relative_to(batch_dir))]
            elif facts:
                rel = (question.get("stem_images") or [f"images/q-{index:02d}-stem.png"])[0]
                dest = batch_dir / rel
                question["stem_images"] = [rel]
                hint = locked or kind_from_stem(str(question.get("stem") or ""))
                if hint and is_program_kind(hint):
                    render_one({"kind": hint}, dest, question=question, spec=spec, batch_dir=batch_dir, deadline=deadline)
                else:
                    ai_image_tasks.append((facts, dest))
            for option in question.get("options") or []:
                opt_fig = pop_figure(option)
                if not opt_fig:
                    continue
                rel = str(opt_fig.get("file") or (option.get("images") or [None])[0] or "")
                if not rel:
                    rel = f"images/q-{index:02d}-opt-{option.get('key')}.png"
                render_one(opt_fig, batch_dir / rel, question=question, spec=spec, batch_dir=batch_dir, deadline=deadline)
                option["images"] = [rel]
        except Exception as exc:
            raise RuntimeError(f"{qid}: {exc}") from exc

    # 并行生成扢�朄1�71ￄ1�77 AI 图像（判断推琄1�71ￄ1�775张图 + 科学推理5张图可以同时生成＄1�71ￄ1�77
    if locked_jobs:
        pairs = []
        for qid, fig, dest, question in locked_jobs:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with pipe_span(f"draw_svg {qid}"):
                build_svg(fig).write(dest.with_suffix(".svg"))
            pairs.append((dest.with_suffix(".svg"), dest))
        with pipe_span("draw_png_batch"):
            svg_to_png_many(pairs)
        for qid, fig, dest, question in locked_jobs:
            dest.with_suffix(".draw.json").write_text(
                json.dumps(
                    {"ok": True, "kind": fig.get("kind"), "agent": False, "rounds": 0, "locked": True},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    if ai_image_tasks:
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(generate_line_image, facts, dest, deadline)
                for facts, dest in ai_image_tasks
            ]
            for future in as_completed(futures):
                future.result()  # 抛出异常则整个批次失贄1�71ￄ1�77

    for index, material in enumerate(draft.get("materials") or [], 1):
        mid = str(material.get("external_id") or f"M{index:02d}")
        fig = pop_figure(material)
        if not fig:
            continue
        rel = str(fig.get("file") or f"images/m-{index:02d}-{fig.get('kind') or 'table'}.png")
        try:
            render_one(fig, batch_dir / rel)
        except Exception as exc:
            raise RuntimeError(f"{mid}: {exc}") from exc
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



def locked_slot_tags(batch_dir: Path | None) -> list[str]:
    """Once a kepui pack is locked on disk, do not reshuffle slots on retry."""
    if not batch_dir:
        return []
    path = Path(batch_dir) / "locked-slots.json"
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    tags = [str(item.get("tag") or "") for item in rows or [] if isinstance(item, dict)]
    tags = [tag for tag in tags if tag]
    return tags if len(tags) == 5 else []


def kepui_slot_tags(run: dict, db_path: Path | None = None) -> list[str]:
    # 科推已从每日任务剔除；保留函数签名以兼容历史批次，但不再产生槽位
    return []


def stamp_questions(run: dict, questions: list[dict], db_path: Path | None = None, batch_dir: Path | None = None) -> list[dict]:
    source = run.get("source") or daily_source_name(run["module"], run["plan_date"])
    year = int(str(run["plan_date"])[:4])
    slot_tags = locked_slot_tags(batch_dir) or kepui_slot_tags(run, db_path)
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
        if not str(row.get("explanation") or "").strip() and row.get("analysis"):
            row["explanation"] = row["analysis"]
        diff = row.get("difficulty")
        if isinstance(diff, str) and diff.lower() in {"easy", "medium", "hard"}:
            row["difficulty"] = {"easy": 2, "medium": 3, "hard": 4}[diff.lower()]
        elif not isinstance(diff, int):
            row["difficulty"] = 2
        if run["module"] == CAT_KEPUI:
            row["category"] = CAT_KEPUI
            row["sub_category"] = CAT_KEPUI
            row["stem"] = _science_label_text(row.get("stem"))
            if index <= len(slot_tags) and slot_tags[index - 1]:
                tag = slot_tags[index - 1]
                rest = [str(item) for item in (row.get("tags") or []) if str(item) and str(item) != tag]
                row["tags"] = [tag, *rest]
            tag_now = question_primary_tag(row)
            row["figure_template"] = (
                (coerce_kepui_figure(row.get("stem"), {"kind": kind_from_kepui_tag(tag_now)}, tag_now) or {}).get("kind")
                or kind_from_kepui_tag(tag_now)
                or science_template_for(row.get("stem"), SCIENCE_TEMPLATE_ORDER[(index - 1) % 5])
            )
            # Always render a deterministic figure. Gemini may omit the optional
            # object even when the stem explicitly says "如图".
            kind = row["figure_template"]
            contract = row.get("figure_contract") if isinstance(row.get("figure_contract"), dict) else {}
            if contract.get("kind") and not kind_from_kepui_tag(question_primary_tag(row)):
                from program_figure import is_program_kind
                if is_program_kind(str(contract.get("kind") or "")):
                    kind = str(contract["kind"])
                    row["figure_template"] = kind
            if contract:
                contract = dict(contract)
                contract["kind"] = kind
                row["figure_contract"] = contract
            row["figure"] = {"kind": kind, **(row.get("figure") or {})}
            row["figure"]["kind"] = kind
        if run["module"] == CAT_YANYU:
            row.pop("sub_category", None)
        if run["module"] == CAT_ZILIAO:
            row.pop("sub_category", None)
        out.append(row)
    return out


def write_batch(run: dict, batch_dir: Path, draft: dict, db_path: Path | None = None) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    questions = stamp_questions(run, list(draft.get("questions") or []), db_path=db_path, batch_dir=batch_dir)
    draft["questions"] = questions
    extras = generation_payload_extras(
        run["module"],
        int(run["planned_count"]),
        str(run["batch_id"]),
        db_path,
        str(run.get("focus_tag") or ""),
    )
    extras.setdefault("batch_constraints", {})
    if run.get("figure_control"):
        n = int(run["planned_count"])
        extras["batch_constraints"]["program_figures"] = True
        extras["batch_constraints"]["image_dependent_count"] = {"min": n, "max": n}
        extras["batch_constraints"].pop("panduan_layout", None)
        extras["batch_constraints"].pop("kepui_layout", None)
    elif run.get("module") == CAT_KEPUI:
        extras["batch_constraints"]["program_figures"] = True
    materials = [item for item in (draft.get("materials") or []) if isinstance(item, dict)]
    source = run.get("source") or daily_source_name(run["module"], run["plan_date"])
    for index, material in enumerate(materials, 1):
        material["external_id"] = str(
            material.get("external_id") or f"{run['batch_id']}-M{index:02d}"
        )
        material["source"] = source
    calculations = draft.get("calculations")
    specs = draft.get("image_specs") or draft.get("image-specs")
    if run.get("module") == CAT_KEPUI or run.get("figure_control"):
        incoming = []
        if isinstance(specs, dict):
            incoming = list(specs.get("questions") or [])
        elif isinstance(specs, list):
            incoming = list(specs)
        by_id = {str(item.get("question_id") or ""): item for item in incoming if isinstance(item, dict)}
        specs = {"questions": [spec_from_question(question, by_id.get(str(question.get("external_id") or ""))) for question in questions]}
    dump(batch_dir / "questions.json", questions)
    if run.get("module") == CAT_KEPUI:
        dump(
            batch_dir / "locked-slots.json",
            [
                {
                    "index": index,
                    "tag": question_primary_tag(question),
                    "kind": str(question.get("figure_template") or ""),
                }
                for index, question in enumerate(questions, 1)
            ],
        )
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
    rows = []
    if isinstance(specs, dict):
        rows = list(specs.get("questions") or [])
    elif isinstance(specs, list):
        rows = list(specs)
    have = {str(item.get("question_id")) for item in rows if isinstance(item, dict)}
    for question in questions:
        qid = str(question.get("external_id") or "")
        has_img = question.get("stem_images") or any(
            option.get("images") for option in question.get("options") or []
        )
        if not qid or qid in have or not has_img:
            continue
        if run.get("module") == CAT_KEPUI:
            continue
        rows.append(
            {
                "question_id": qid,
                "image_facts": ["程序绘制的图彄1�71ￄ1�77"],
                "image_only_facts": ["题干囄1�71ￄ1�77"],
                "must_derive": [f"正确选项昄1�71ￄ1�77 {question.get('answer')}"],
            }
        )
    if rows:
        dump(batch_dir / "image-specs.json", {"questions": rows})
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



ITEM_ROUNDS = 8


def program_figure_gate_error(error: str) -> bool:
    """SVG/spec label mismatch. Flash cannot draw the program figure."""
    return "程序作图质检" in str(error or "")

QID_TAIL = re.compile(r"_(\d+)$")


def _ids_in_text(blob: str, ids: list[str]) -> list[str]:
    found: list[str] = []
    for qid in ids:
        if qid and qid in blob and qid not in found:
            found.append(qid)
    return found


def parse_rejected_question_ids(error: str, questions: list, materials: list | None = None) -> list[str]:
    ids = [str(q.get("external_id") or "") for q in questions if isinstance(q, dict)]
    idset = {item for item in ids if item}
    found: list[str] = []
    blob = str(error or "")
    payload = None
    try:
        start, end = blob.find("{"), blob.rfind("}")
        if 0 <= start < end:
            payload = json.loads(blob[start : end + 1])
            for qid in payload.get("rejected") or []:
                qid = str(qid)
                if qid in idset and qid not in found:
                    found.append(qid)
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = None
    found.extend(qid for qid in _ids_in_text(blob, ids) if qid not in found)
    for question in questions:
        if not isinstance(question, dict):
            continue
        qid = str(question.get("external_id") or "")
        mid = str(question.get("material_id") or "")
        if qid and qid not in found and mid and mid in blob:
            found.append(qid)
        for rel in question.get("stem_images") or []:
            if qid and qid not in found and str(rel) and str(rel) in blob:
                found.append(qid)
    for material in materials or []:
        if not isinstance(material, dict):
            continue
        mid = str(material.get("external_id") or "")
        hit = mid and mid in blob
        if not hit:
            hit = any(str(rel) and str(rel) in blob for rel in (material.get("images") or []))
        if not hit:
            continue
        for question in questions:
            if not isinstance(question, dict):
                continue
            qid = str(question.get("external_id") or "")
            if qid and qid not in found and str(question.get("material_id") or "") == mid:
                found.append(qid)
    # sit-together dump: prefer the named item/batch issues
    if payload and len(found) == len(idset) and len(idset) > 1:
        narrow: list[str] = []
        for issue in payload.get("batch_issues") or []:
            text = json.dumps(issue, ensure_ascii=False) if not isinstance(issue, str) else issue
            if isinstance(issue, dict):
                qid = str(issue.get("question_id") or "")
                if qid in idset and qid not in narrow:
                    narrow.append(qid)
            narrow.extend(qid for qid in _ids_in_text(text, ids) if qid not in narrow)
        for line in payload.get("item_issues") or []:
            narrow.extend(qid for qid in _ids_in_text(str(line), ids) if qid not in narrow)
        if 0 < len(narrow) < len(idset):
            return narrow
    return found


def expand_retry_ids(module: str, qids: list[str], questions: list) -> list[str]:
    """材料本身挂了时，parse_rejected_question_ids 已经按篇收齐；题错只打回错题〄1�71ￄ1�77"""
    return list(qids or [])


def merge_retry_questions(old: list, incoming: list, retry_ids: set[str]) -> list:
    by_id: dict[str, dict] = {}
    unused: list[dict] = []
    for row in incoming:
        if not isinstance(row, dict):
            continue
        qid = str(row.get("external_id") or "")
        if qid and qid in retry_ids:
            by_id[qid] = row
        else:
            unused.append(row)
    out = []
    for row in old:
        qid = str(row.get("external_id") or "")
        if qid not in retry_ids:
            out.append(row)
            continue
        repl = by_id.pop(qid, None)
        if repl is None and unused:
            repl = unused.pop(0)
        if repl is None:
            out.append(row)
            continue
        merged = dict(repl)
        merged["external_id"] = qid
        out.append(merged)
    return out


def _ziliao_slot_task(slot: int, question: dict) -> str:
    from kaodian_taxonomy import question_primary_tag

    tag = question_primary_tag(question)
    if slot == 5:
        return (
            f"本题是本篇第5题：根据现成材料和已过关题，只出综合判断"
            f"（四句陈述；属实/无法推出/正确的有/能推出）。tags[0] 仍用 {tag}。"
        )
    return (
        f"本题是本篇第{slot}题：根据现成材料和已过关题，按 tags[0]={tag} "
        "出对应计算/比较题，不要写成综合判断。"
    )


def ziliao_slot_keep_context(questions: list, retry_ids: list[str]) -> list[dict]:
    """材料过关时，按槽位重出失败题，并把同篇已过关题留给模型。"""
    idset = set(retry_ids)
    groups: dict[str, list[dict]] = {}
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            continue
        mid = str(question.get("material_id") or "") or f"block-{index // 5}"
        groups.setdefault(mid, []).append(question)
    context = []
    for mid, items in groups.items():
        for slot, question in enumerate(items, start=1):
            qid = str(question.get("external_id") or "")
            if qid not in idset:
                continue
            context.append(
                {
                    "replace_id": qid,
                    "material_id": mid,
                    "slot": slot,
                    "keep_questions": [
                        {
                            "external_id": item.get("external_id"),
                            "stem": item.get("stem"),
                            "answer": item.get("answer"),
                            # Keep the source numbers visible on slot retries;
                            # stems/answers alone let the model invent new data.
                            "analysis": item.get("analysis") or item.get("explanation"),
                        }
                        for item in items
                        if str(item.get("external_id") or "") not in idset
                    ],
                    "task": _ziliao_slot_task(slot, question)
                    + " 不要改材料，不要重出已过关题。",
                }
            )
    return context


def slot_retry_prompt(base: str, run: dict, questions: list, retry_ids: list[str], error: str) -> str:
    failed = [q for q in questions if str(q.get("external_id") or "") in set(retry_ids)]
    from quality_ledger import retry_prompt_block
    keep = ziliao_slot_keep_context(questions, retry_ids)

    return "\n".join(
        [
            base,
            "SLOT RETRY only. Output questions[] with exactly these external_id values.",
            "Keep tags[0], sub_category, material_id. Do not emit already-accepted items.",
            "figure.kind is locked by kepui_pack slot.tag / tags[0]. Do not switch the knowledge point "
            "to a familiar figure (front/reflex/contour/force). Draw that slot only. Do not invent extra 小球/木块. "
            "Circuit labels must be the stem R1/R2/A1/A. Distractors: no 一定是/必然/唯一/完全. "
            "Lever hooks hang below the bar; never stack them on top or draw L1/L2 unless the stem names them. "
            "Front stems must not say 冷锋/暖锋 or 冷气团主动/暖气团被迫抬升.",
            "资料材料过关时只重出失败题：1-4题按该槽考点出计算/比较，第5题出综合判断。"
            "不要改材料，不要重出已过关题。每个失败题必须同时返回对应 calculations.questions 记录，"
            "并且所有数字、单位、同比率必须逐字服从材料和 keep_questions 的解析；不得凭空改数。",
            "If a material chart is missing, also emit that materials[] row with a complete "
            "figure (kind table|bars|pie plus headers/rows or categories/series) so Python can redraw it.",
            json.dumps(
                {"replace_ids": retry_ids, "failed_questions": failed, "keep_slot_context": keep},
                ensure_ascii=False,
            )[:24000],
            issue_brief(error),
            retry_prompt_block(str(run.get("module") or ""), error),
        ]
    )


def _paper_index(qid: str) -> int | None:
    found = QID_TAIL.search(qid)
    if not found:
        return None
    return int(found.group(1))


def merge_materials(old: list, incoming: list, retry_ids: set[str], questions: list) -> list:
    wanted = {
        str(q.get("material_id") or "")
        for q in questions
        if str(q.get("external_id") or "") in retry_ids and q.get("material_id")
    }
    if not wanted:
        return old
    by_id = {str(item.get("external_id") or ""): item for item in incoming if isinstance(item, dict)}
    out = []
    for item in old:
        mid = str(item.get("external_id") or "")
        out.append(dict(by_id[mid]) if mid in wanted and mid in by_id else item)
    return out


def _spec_rows(blob) -> list:
    if isinstance(blob, dict):
        return [row for row in (blob.get("questions") or []) if isinstance(row, dict)]
    if isinstance(blob, list):
        return [row for row in blob if isinstance(row, dict)]
    return []



def merge_calculations(old, incoming, retry_ids: set[str]):
    def rows(blob):
        if isinstance(blob, dict):
            return [item for item in (blob.get("questions") or []) if isinstance(item, dict)]
        if isinstance(blob, list):
            return [item for item in blob if isinstance(item, dict)]
        return []
    by_id = {}
    for row in rows(old):
        qid = str(row.get("question_id") or "")
        if qid:
            by_id[qid] = row
    for row in rows(incoming):
        qid = str(row.get("question_id") or "")
        if qid and (not retry_ids or qid in retry_ids):
            by_id[qid] = row
    return {"questions": list(by_id.values())}


def merge_image_specs(old, incoming, retry_ids: set[str]):
    by_id = {}
    for row in _spec_rows(old):
        qid = str(row.get("question_id") or "")
        if qid:
            by_id[qid] = row
    for row in _spec_rows(incoming):
        qid = str(row.get("question_id") or "")
        if qid in retry_ids:
            by_id[qid] = row
    return {"questions": list(by_id.values())} if by_id else old


def _replace_question(questions: list, qid: str, row: dict) -> list:
    out = []
    found = False
    for item in questions:
        if str(item.get("external_id") or "") == qid:
            out.append(row)
            found = True
        else:
            out.append(item)
    if not found:
        out.append(row)
    return out


def reload_draft_files(draft: dict, batch_dir: Path) -> None:
    qpath = batch_dir / "questions.json"
    if qpath.is_file():
        draft["questions"] = json.loads(qpath.read_text(encoding="utf-8"))
    mpath = batch_dir / "materials.json"
    if mpath.is_file():
        draft["materials"] = json.loads(mpath.read_text(encoding="utf-8"))
    spath = batch_dir / "image-specs.json"
    if spath.is_file():
        draft["image_specs"] = json.loads(spath.read_text(encoding="utf-8"))
    cpath = batch_dir / "calculations.json"
    if cpath.is_file():
        draft["calculations"] = json.loads(cpath.read_text(encoding="utf-8"))


def generate_and_import(
    run: dict,
    batch_dir: Path,
    db_path: Path,
    timeout: int,
    prompt: str,
) -> None:
    deadline = time.monotonic() + timeout
    env = {**os.environ, "EXAM_DB": str(db_path)}
    env["PIPELINE_TIMING"] = str(batch_dir / "pipeline-timing.jsonl")
    global _PIPE_T0
    _PIPE.clear()
    _PIPE_T0 = time.monotonic()
    error = None
    draft: dict | None = None
    try:
        _generate_and_import_body(run, batch_dir, db_path, deadline, prompt, env)
        return
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        dump_pipe(
            batch_dir,
            {
                "status": "ok" if not error else "failed",
                "slots": kepui_slot_tags(run, db_path),
                "error": error,
            },
        )


def _generate_and_import_body(
    run: dict,
    batch_dir: Path,
    db_path: Path,
    deadline: float,
    prompt: str,
    env: dict,
) -> None:
    error = None
    draft: dict | None = None
    if (batch_dir / "questions.json").is_file():
        draft = {}
        reload_draft_files(draft, batch_dir)
        error = str(run.get("error") or "") or "resume previous draft"
    graphic_qs: list[dict] = []
    gslots: list[dict] = []
    if (
        run["module"] == CAT_PANDUAN
        and int(run["planned_count"]) == 20
        and not run.get("focus_tag")
    ):
        extras = generation_payload_extras(
            run["module"], int(run["planned_count"]), str(run["batch_id"]), db_path
        )
        gslots = [
            slot
            for slot in (extras.get("panduan_pack") or {}).get("slots") or []
            if slot.get("section") == "graphic"
        ]
        existing = list(draft.get("questions") or []) if draft else []
        if len(existing) >= len(gslots):
            graphic_qs = [dict(row) for row in existing[: len(gslots)]]
        else:
            graphic_qs = build_graphic_paper(gslots, batch_dir, str(run["batch_id"]))
    last_figure_error = ""
    figure_same = 0
    for _attempt in range(ITEM_ROUNDS):
        retry_ids = []
        if error and draft:
            retry_ids = expand_retry_ids(
                run["module"],
                parse_rejected_question_ids(
                    error,
                    draft.get("questions") or [],
                    draft.get("materials") or [],
                ) or [str(q.get('external_id') or '') for q in draft.get('questions') or []],
                draft.get("questions") or [],
            )
        if draft is None:
            draft = call_gemini(augment_prompt(prompt, run, batch_dir, error), deadline)
            if graphic_qs:
                logic = [
                    question
                    for question in draft.get("questions") or []
                    if str(question.get("sub_category") or "") == "\u903b\u8f91\u5224\u65ad"
                ]
                if len(logic) < 15:
                    logic = list(draft.get("questions") or [])[-15:]
                merged = []
                for row in graphic_qs + logic[:15]:
                    item = dict(row)
                    item.pop("external_id", None)
                    if item.get("stem_images"):
                        item.pop("figure", None)
                    merged.append(item)
                draft["questions"] = merged
        elif retry_ids:
            gemini_ids = list(retry_ids)
            retry_set = set(retry_ids)
            if program_figure_gate_error(error):
                figure_same = figure_same + 1 if error == last_figure_error else 1
                last_figure_error = error
                if figure_same >= 3:
                    raise RuntimeError(error)
                # 1st retry: rewrite specs / coerce labels and redraw. Flash cannot
                # paint SVG. 2nd retry: Gemini must change the stem or drop junk labels.
                if figure_same < 2:
                    gemini_ids = []
            else:
                pre = preflight_draft(draft, batch_dir, error, only_ids=gemini_ids)
                patched = set(pre.get("patched") or [])
                gemini_ids = [qid for qid in gemini_ids if qid not in patched]
            for question in draft.get("questions") or []:
                if str(question.get("external_id") or "") not in retry_set:
                    continue
                for rel in list(question.get("stem_images") or []):
                    path = batch_dir / rel
                    path.unlink(missing_ok=True)
                    path.with_suffix(".svg").unlink(missing_ok=True)
                question.pop("stem_images", None)
            if graphic_qs and gslots:
                keep_gemini = []
                for qid in list(retry_ids):
                    idx = _paper_index(qid)
                    if idx is None or not (1 <= idx <= len(gslots)):
                        if qid in gemini_ids:
                            keep_gemini.append(qid)
                        continue
                    dest = batch_dir / "images" / f"{run['batch_id']}_{idx:02d}.png"
                    dest.unlink(missing_ok=True)
                    row = build_graphic_question(gslots[idx - 1], dest)
                    row.pop('figure', None)
                    row["external_id"] = qid
                    graphic_qs[idx - 1] = row
                    draft["questions"] = _replace_question(list(draft.get("questions") or []), qid, row)
                gemini_ids = [qid for qid in keep_gemini if not any(is_graphic(q) and str(q.get("external_id") or "") == qid for q in draft.get("questions") or [])]
            if gemini_ids:
                patch = call_gemini(
                    slot_retry_prompt(prompt, run, draft.get("questions") or [], gemini_ids, error),
                    deadline,
                )
                gemini_set = set(gemini_ids)
                draft["questions"] = merge_retry_questions(
                    draft.get("questions") or [],
                    list(patch.get("questions") or []),
                    gemini_set,
                )
                if patch.get("materials") and draft.get("materials"):
                    draft["materials"] = merge_materials(
                        list(draft.get("materials") or []),
                        list(patch.get("materials") or []),
                        gemini_set,
                        draft.get("questions") or [],
                    )
                incoming_specs = patch.get("image_specs") or patch.get("image-specs")
                if incoming_specs:
                    draft["image_specs"] = merge_image_specs(
                        draft.get("image_specs") or draft.get("image-specs"),
                        incoming_specs,
                        gemini_set,
                    )
                if patch.get("calculations"):
                    draft["calculations"] = merge_calculations(
                        draft.get("calculations"),
                        patch.get("calculations"),
                        gemini_set,
                    )
        write_batch(run, batch_dir, draft, db_path=db_path)
        if not program_figure_gate_error(error or ""):
            pre = preflight_draft(draft, batch_dir, error)
            if pre.get("block_render"):
                error = pre.get("error") or error or "出题运维要求改题"
                dump(batch_dir / "questions.json", draft.get("questions") or [])
                continue
        try:
            render_assets(batch_dir, draft, deadline)
            dump(batch_dir / "questions.json", draft["questions"])
            if draft.get("materials"):
                dump(batch_dir / "materials.json", draft["materials"])
            if retry_ids:
                env["QUALITY_FOCUS_IDS"] = ",".join(retry_ids)
            else:
                env.pop("QUALITY_FOCUS_IDS", None)
            with pipe_span("gate_issue"):
                run_cmd([sys.executable, str(GATE_SCRIPT), "issue", str(batch_dir)], deadline, env)
            with pipe_span("import"):
                run_cmd(["node", str(IMPORT_SCRIPT), str(batch_dir)], deadline, env)
            error = None
            break
        except RuntimeError as exc:
            error = str(exc)
            reload_draft_files(draft, batch_dir)
    if error:
        raise RuntimeError(error)

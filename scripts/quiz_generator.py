#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes 专项出题入口：Gemini 出稿 → 闸门 → 入库。不要在会话里写 questions.json。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kaodian_taxonomy import canonicalize, validate_ai_primary_tag
from normalize_ai_batch import generation_payload_extras
from scheduler_common import DB, ROOT, difficulty_tier, load_snapshot, local_today
from spoken_quiz_intent import slug_of


MODEL = os.environ.get("DAILY_GEMINI_MODEL", "gemini-3.8-flash-high")
BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
RETRIES = 3
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)
FIGURE_HINT = re.compile(r"图形推理|科学推理|空间类")
HARD_RULES = ROOT / "hermes-skills" / "quiz-pipeline" / "references" / "module-hard-rules.md"
CANON_DIR = ROOT / "hermes-skills" / "gd-gongkao-coach" / "references" / "solver-canon"
CANON_FILES = {
    "判断推理": "05-panduan.md",
    "数量关系": "04-shuliang.md",
    "言语理解与表达": "03-yanyu.md",
}
SECTION = re.compile(r"^\*\*([^*：\n]+?)(?:（[^）\n]*）)?：\*\*", re.M)
BRIEF_LIMIT = 600
CANON_LIMIT = 1400

MODULES = {
    "判断推理",
    "数量关系",
    "言语理解与表达",
    "资料分析",
    "科学推理",
}


def api_key() -> str:
    if key := os.environ.get("CLIPROXY_API_KEY", "").strip():
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("CLIPROXY_API_KEY not found")


def parse_json(text: str) -> dict:
    text = FENCE.sub("", (text or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list) or not data["questions"]:
        raise ValueError("Gemini returned no questions")
    return data


def call_gemini(prompt: str, deadline: float) -> dict:
    timeout = max(60, min(600, int(deadline - time.monotonic() - 15)))
    if timeout < 30:
        raise RuntimeError("timed out before Gemini draft")
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 16384,
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
            return parse_json((data["choices"][0]["message"].get("content") or "").strip())
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            if attempt + 1 == RETRIES or deadline - time.monotonic() < 40:
                break
            wait = 8 if isinstance(exc, urllib.error.HTTPError) and exc.code != 429 else 20 * (attempt + 1)
            time.sleep(min(wait, max(1, deadline - time.monotonic()) / 2))
    raise RuntimeError(last)


def module_of(tag: str, fallback: str) -> str:
    if fallback in MODULES:
        return fallback
    head = (tag or "").split("-", 1)[0]
    if head in MODULES:
        return head
    raise ValueError(f"无法识别模块：module={fallback!r} tag={tag!r}")


def reject_unsupported(module: str, tag: str) -> None:
    blob = f"{module} {tag}"
    if module in {"科学推理", "资料分析"} or FIGURE_HINT.search(blob):
        raise ValueError(
            f"{module or tag} 带图/成套卷请走日练。本入口只出文字专项（逻辑/数量/言语）。"
        )


def infer_subcategory(tag: str, module: str) -> str:
    parts = [p for p in (tag or "").split("-") if p]
    if module == "判断推理":
        return "逻辑判断"
    if module == "数量关系":
        return "数字推理" if "数字推理" in tag else "数学运算"
    if module == "言语理解与表达":
        return "逻辑填空" if "逻辑填空" in tag else "片段阅读"
    return parts[1] if len(parts) > 1 else module


def _remap_calc_keys(calc: dict, current: str, want: str) -> dict:
    opts = calc.get("options")
    if not isinstance(opts, dict) or current not in opts or want not in opts:
        return calc
    swapped = dict(opts)
    swapped[current], swapped[want] = swapped[want], swapped[current]
    return {**calc, "options": swapped}


def align_answers(questions: list[dict], letters: list[str]) -> None:
    for question, want in zip(questions, letters):
        options = list(question.get("options") or [])
        current = str(question.get("answer") or "")
        if current == want or not options:
            continue
        correct = next((row for row in options if row.get("key") == current), None)
        other = next((row for row in options if row.get("key") == want), None)
        if not correct or not other:
            continue
        correct["key"], other["key"] = want, current
        question["options"] = sorted(options, key=lambda row: str(row.get("key") or ""))
        question["answer"] = want
        if isinstance(question.get("calculations"), dict):
            question["calculations"] = _remap_calc_keys(question["calculations"], current, want)
        for field in ("analysis", "explanation"):
            text = str(question.get(field) or "")
            if text:
                question[field] = re.sub(r"故选[ABCD]", f"故选{want}", text)


def expression_from_text(text: str) -> str | None:
    raw = str(text or "").strip().replace(",", "").replace("，", "")
    if not raw:
        return None
    if re.fullmatch(r"[\d+\-*/().\s]+", raw):
        return re.sub(r"\s+", "", raw)
    frac = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)", raw)
    if frac:
        return f"{frac.group(1)}/{frac.group(2)}"
    nums = re.findall(r"-?\d+(?:\.\d+)?", raw)
    if len(nums) == 1:
        return nums[0]
    return None


def build_calculations(questions: list[dict]) -> dict:
    rows = []
    for question in questions:
        calc = question.pop("calculations", None)
        if not isinstance(calc, dict):
            calc = {}
        src = calc.get("options") if isinstance(calc.get("options"), dict) else {}
        options = {}
        for opt in question.get("options") or []:
            key = str(opt.get("key") or "")
            expr = src.get(key) or expression_from_text(opt.get("text"))
            if not expr:
                raise ValueError(f"{question.get('external_id')} 缺 {key} 的验算式")
            options[key] = str(expr).strip()
        correct = calc.get("correct") or options.get(str(question.get("answer") or ""))
        if not correct:
            raise ValueError(f"{question.get('external_id')} 缺 correct 验算式")
        row = {
            "question_id": question["external_id"],
            "correct": str(correct).strip(),
            "options": options,
            "tolerance": float(calc.get("tolerance") or 0.01),
        }
        # 取整方向原样带下去：correct 停在取整前的小数上时，闸门靠它才判得出命中。
        direction = str(calc.get("round") or "").strip().lower()
        if direction:
            row["round"] = direction
        rows.append(row)
    return {"questions": rows}


def run_slots(run: dict) -> list[dict]:
    """没给 slots 就退回单槽，保持 --tag/--count 老调用不变。"""
    slots = run.get("slots")
    if slots:
        return list(slots)
    return [{"tag": str(run["focus_tag"]), "count": int(run["planned_count"])}]


def slot_tags(run: dict) -> list[str]:
    """按槽位展开成「每题一个规范主标签」，顺序即题号顺序。"""
    expanded: list[str] = []
    for slot in run_slots(run):
        expanded.extend([str(slot["tag"])] * int(slot["count"]))
    return expanded


def stamp_questions(run: dict, questions: list[dict], source: str) -> list[dict]:
    module = run["module"]
    per_item = slot_tags(run)
    stamped = []
    for index, raw in enumerate(questions[: int(run["planned_count"])], start=1):
        row = dict(raw)
        tag = per_item[index - 1]
        row["external_id"] = f"{run['batch_id']}_{index:02d}"
        row["category"] = module
        row["sub_category"] = infer_subcategory(tag, module)
        row["tags"] = [tag]
        row["question_type"] = "single"
        row["source"] = source
        row["year"] = 2026
        row["region"] = "广东-省直"
        row.pop("origin", None)
        if not str(row.get("analysis") or "").strip():
            row["analysis"] = str(row.get("explanation") or "").strip()
        if not str(row.get("explanation") or "").strip():
            row["explanation"] = row["analysis"]
        stamped.append(row)
    # 不在这里按计划表换字母：字母只要整批不扎堆就行，真扎堆了由闸门里的
    # normalize_batch → redistribute_answers 机械重排，并同步 calculations。
    return stamped


def card_sections(card: str) -> dict[str, str]:
    """把一张考点卡片按 **小节：** 切开。"""
    marks = [(m.group(1), m.start(), m.end()) for m in SECTION.finditer(card)]
    out = {}
    for index, (name, start, end) in enumerate(marks):
        stop = marks[index + 1][1] if index + 1 < len(marks) else len(card)
        out[name] = card[end:stop].strip()
    return out


def bullet_blocks(steps: str) -> list[str]:
    """按顶层 `- ` 分块，子行（缩进或 ①②③）跟着自己的父块走。"""
    blocks: list[list[str]] = []
    for line in steps.split("\n"):
        if line.startswith("- ") or not blocks:
            blocks.append([line])
        else:
            blocks[-1].append(line)
    return ["\n".join(block).strip() for block in blocks]


def canon_card(module: str, tag: str) -> str:
    """取 solver-canon 里该考法的固定识别/考场步骤/禁止，当生成器的考法底座。

    标签挂在某条考法 bullet 上时只取那一条，否则退回整张卡的考场步骤。
    """
    name = CANON_FILES.get(module)
    if not name or not (CANON_DIR / name).is_file():
        return ""
    text = (CANON_DIR / name).read_text(encoding="utf-8")
    card = next((part for part in text.split("\n### ") if f"`{tag}`" in part), None)
    if not card:
        return ""
    sections = card_sections(card)
    parts = [f"考点卡片：{card.split(chr(10), 1)[0].strip()}"]
    if sections.get("固定识别"):
        parts.append("固定识别：" + sections["固定识别"])
    steps = sections.get("考场步骤", "")
    if steps:
        own = [block for block in bullet_blocks(steps) if f"`{tag}`" in block]
        parts.append("考场步骤：\n" + "\n".join(own or bullet_blocks(steps)))
    if sections.get("禁止"):
        parts.append("禁止：" + sections["禁止"])
    return "\n".join(parts)[:CANON_LIMIT]


def slot_briefs(run: dict) -> str:
    """考法底座 + Hermes 本批次的命题指令。只能加约束，不能松约束。"""
    chunks = []
    for index, slot in enumerate(run_slots(run), start=1):
        tag = str(slot["tag"])
        body = [f"[slot {index}] {tag}"]
        card = canon_card(run["module"], tag)
        if card:
            body.append(card)
        if slot.get("brief"):
            body.append("本批次额外命题要求（Hermes 下达，只能收紧不得放宽既有规则）：" + str(slot["brief"]))
        if len(body) > 1:
            chunks.append("\n".join(body))
    if not chunks:
        return ""
    return (
        "\nPer-slot 考法口径。每个槽位严格按自己的固定识别与考场步骤命题，"
        "不要让别的槽位的模型渗进来：\n" + "\n\n".join(chunks) + "\n"
    )


def slot_rules(run: dict) -> str:
    """把槽位翻译成「第几题到第几题打哪个标签」的硬约束。"""
    slots = run_slots(run)
    if len(slots) == 1:
        return f"Every tags[0] must be exactly {slots[0]['tag']}.\n"
    lines, start = [], 1
    for slot in slots:
        end = start + int(slot["count"]) - 1
        span = f"item {start}" if start == end else f"items {start}-{end}"
        hint = f", difficulty {slot['difficulty']}" if slot.get("difficulty") else ""
        lines.append(f"  {span}: tags[0] = {slot['tag']} ({slot['count']} questions{hint})")
        start = end + 1
    return (
        "Split the batch into these slots by item index. Each slot is a DIFFERENT 考法 of the "
        "same 一级知识点 — do not let one slot's model leak into another:\n"
        + "\n".join(lines)
        + "\n"
    )


def build_prompt(run: dict, snapshot: dict, extras: dict, error: str | None = None) -> str:
    tag = run["focus_tag"]
    n = int(run["planned_count"])
    payload = {
        "module": run["module"],
        "focus_tag": tag,
        "slots": [
            {k: v for k, v in slot.items() if v not in (None, "")} for slot in run_slots(run)
        ],
        "question_count": n,
        "batch_id": run["batch_id"],
        "all_original": True,
        "difficulty_tier": run.get("difficulty") or difficulty_tier(run["plan_date"]),
        "learner_snapshot": {
            "as_of": snapshot.get("as_of"),
            "compact": snapshot.get("compact"),
        },
    }
    rules = ""
    if HARD_RULES.is_file():
        rules = HARD_RULES.read_text(encoding="utf-8")[:4000]
    extra = ""
    if "翻译" in tag:
        extra = (
            "翻译推理：正确项不得复述已知实例（含同义）。必须走逆否、选言否定肯定或两步连锁。"
            "主语用某企业/某团队。verify-logic 会拒 echo_given_fact（R029）。\n"
        )
    if run["module"] == "数量关系":
        extra += (
            "数量专项：每题必须紧扣 focus_tag，禁止改成数列或其他家族。"
            "每题另给 calculations："
            '{"correct":"纯四则","options":{"A":"...","B":"...","C":"...","D":"..."},"tolerance":0.01}。'
            "式子只能用数字和 + - * / ( )，排列组合写成 8*7*6/(3*2*1)，禁止 C()/P()/factorial。"
            "选项展示可带单位，calculations 必须能直接求值。\n"
            "答案要取整的题（和定最值、最不利原则这类），correct 写取整前的式子，"
            '另加 "round":"floor"（问最多向下取整）或 "round":"ceil"（问最少向上取整）；'
            "也可以直接把 correct 写成取整后的最终整数。两种都行，"
            "但不许让 correct 停在小数上又不交代取整方向——那样选项永远对不上。\n"
        )
    retry = f"\nPrevious gate error, rewrite the rejected items:\n{error[-4000:]}\n" if error else ""
    return (
        "You are ExamSystem's targeted-drill writer. Output one JSON object only. "
        "No markdown fences, no commentary.\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"Exactly {n} original questions. {slot_rules(run)}"
        "Do not emit a mixed daily paper, 真题, 定义判断, or 类比推理. No images.\n"
        f"{extra}"
        "Each item: external_id, category, sub_category, tags, stem, "
        'options [{"key":"A","text":"..."} x4], answer, analysis'
        + (", calculations" if run["module"] == "数量关系" else "")
        + ".\n"
        # 别再逐题点名正确项字母。一点名，模型就会算出真答案后发现落不到那个字母，
        # 转而去改解析里的数据来凑字母，题干却不跟着动。字母均衡改由整批约束 +
        # normalize_batch 的机械重排负责。
        f"Each item's keyed letter is your own choice. Spread them across the batch: "
        f"no single letter on more than {int(extras['batch_constraints']['answer_max_per_letter'])} "
        f"items, and use at least {int(extras['batch_constraints']['answer_min_letters'])} "
        "different letters. Never bend a question's data to land on a particular letter — "
        "solve the stem as written, then set the options around the true answer.\n"
        # 模型凑不出好看的选项时会中途改数据，却只改解析不改题干，还把草稿留在解析里。
        # 这是目前最高频的废题来源，且算式验算看不见（calculations 跟着改过的数据一起写）。
        "Solve the stem exactly as written, then build the options around that answer. "
        "If the options do not fit, change the options — never the stem's data, and never "
        "the data inside the analysis. The analysis is what the student reads: it must not "
        "contain your own revisions (\u300c\u4fee\u6539\u9898\u5e72\u300d\u300c\u8c03\u6574\u6570\u636e\u300d"
        "\u300c\u4e3a\u4e86\u8ba9\u7b54\u6848\u7b49\u4e8e\u2026\u300d). Any stem number quoted in the "
        "analysis must be the number that is actually in the stem.\n"
        "Do not invent extra questions.\n"
        f"{rules}\n"
        f"{slot_briefs(run)}"
        f"{retry}"
        'JSON: {"questions":[...]}\n'
    )


def holdout_matches(tag: str, data: dict) -> bool:
    refs = data.get("references") if isinstance(data, dict) else None
    if not isinstance(refs, list) or not refs:
        return False
    hay = " ".join(
        " ".join(str(item) for item in (row.get("tags") or [])) + " " + str(row.get("stem") or "")
        for row in refs
        if isinstance(row, dict)
    )
    tokens = [
        part
        for part in re.split(r"[-（）()、/]", tag)
        if len(part) >= 2 and part not in {"数量关系", "判断推理", "言语理解与表达", "数学运算", "逻辑判断"}
    ]
    return any(token in hay for token in tokens)


def evaluate_slot(run: dict, tag: str, ids: list[str], batch_dir: Path, index: int) -> dict | None:
    """给一个槽位捞一份真题 holdout；捞不到或对不上就返回 None。"""
    out = batch_dir / (f"evaluate-holdout-{index:02d}.json" if index else "evaluate-holdout.json")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "reference_style.py"),
        "context",
        "--role",
        "evaluate",
        "--category",
        run["module"],
        "--sub-category",
        infer_subcategory(tag, run["module"]),
        "--tag",
        tag,
        "--count",
        "1",
        "--images",
        "any",
        "--output",
        str(out),
    ]
    try:
        subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True, timeout=90)
        data = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return None
    context_id = str(data.get("context_id") or "").strip()
    if not context_id or not holdout_matches(tag, data):
        return None
    return {
        "context_id": context_id,
        "reference_ids": list(data.get("reference_ids") or []),
        "question_ids": ids,
    }


def attach_evaluate(run: dict, questions: list[dict], batch_dir: Path) -> list[dict]:
    """每个槽位各捞一份 holdout，避免整批被单一考法的真题风格带偏。"""
    slots = run_slots(run)
    contexts, cursor = [], 0
    for index, slot in enumerate(slots, start=1):
        count = int(slot["count"])
        ids = [row["external_id"] for row in questions[cursor : cursor + count]]
        cursor += count
        if not ids:
            continue
        context = evaluate_slot(run, str(slot["tag"]), ids, batch_dir, 0 if len(slots) == 1 else index)
        if context:
            contexts.append(context)
    return contexts


def write_batch(run: dict, batch_dir: Path, questions: list[dict], extras: dict, source: str) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    eval_contexts = attach_evaluate(run, questions, batch_dir)
    manifest = {
        "batch_id": run["batch_id"],
        "source": source,
        "region": "广东-省直",
        "year": 2026,
        "kind": "ai-generated",
        "difficulty_tier": run.get("difficulty") or difficulty_tier(run["plan_date"]),
        "generation": {
            "style_marker": "GONGKAO-STYLE-v1",
            "batch_constraints": extras["batch_constraints"],
            "generation_contexts": [],
            "evaluation_contexts": eval_contexts,
        },
    }
    calc = None
    if run["module"] == "数量关系":
        calc = build_calculations(questions)
    else:
        for question in questions:
            question.pop("calculations", None)
    (batch_dir / "questions.json").write_text(
        json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if calc:
        (batch_dir / "calculations.json").write_text(
            json.dumps(calc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def run_cmd(command: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(detail[-4000:])


def generate_and_import(run: dict, batch_dir: Path, db_path: Path, timeout: int, snapshot: dict) -> int:
    for slot in run_slots(run):
        reject_unsupported(run["module"], str(slot["tag"]))
    extras = generation_payload_extras(run["module"], int(run["planned_count"]), str(run["batch_id"]), db_path)
    extras["batch_constraints"]["targeted_drill"] = True
    extras["batch_constraints"]["no_images"] = True
    tag_counts: dict[str, int] = {}
    for slot in run_slots(run):
        tag_counts[str(slot["tag"])] = tag_counts.get(str(slot["tag"]), 0) + int(slot["count"])
    extras["batch_constraints"]["tag_counts"] = tag_counts
    if len(run_slots(run)) > 1:
        extras["batch_constraints"]["slot_plan"] = [
            {k: v for k, v in slot.items() if v not in (None, "")} for slot in run_slots(run)
        ]
    extras["batch_constraints"].pop("shuliang_layout", None)
    extras["batch_constraints"].pop("panduan_layout", None)
    run["answer_plan"] = extras["answer_plan"]
    topic = slug_of(run["focus_tag"])
    if topic == "专项" and run.get("focus_tag"):
        topic = run["focus_tag"].split("-")[-1]
    source = f"广东省考行测-{run['module']}-{topic}-{local_today():%Y%m%d}"
    env = {**os.environ, "EXAM_DB": str(db_path)}
    deadline = time.monotonic() + timeout
    error = None
    for _ in range(3):
        draft = call_gemini(build_prompt(run, snapshot, extras, error), deadline)
        questions = stamp_questions(run, draft["questions"], source)
        if len(questions) != int(run["planned_count"]):
            error = f"expected {run['planned_count']} questions, got {len(questions)}"
            continue
        write_batch(run, batch_dir, questions, extras, source)
        try:
            run_cmd([sys.executable, str(ROOT / "scripts" / "generation_gate.py"), "issue", str(batch_dir)], env)
            run_cmd(["node", str(ROOT / "scripts" / "import-batch.mjs"), str(batch_dir)], env)
            conn = sqlite3.connect(db_path, timeout=30)
            try:
                count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM questions WHERE batch_id=?", (run["batch_id"],)
                    ).fetchone()[0]
                )
            finally:
                conn.close()
            if count < int(run["planned_count"]):
                raise RuntimeError(f"imported only {count}/{run['planned_count']}")
            return count
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            if time.monotonic() > deadline - 40:
                break
    raise RuntimeError(error or "generation failed")


def load_blueprint(raw: str) -> list[dict]:
    """--blueprint 收内联 JSON 或 @文件路径，取出原始槽位列表。"""
    text = raw.strip()
    if text.startswith("@"):
        text = Path(text[1:]).expanduser().read_text(encoding="utf-8")
    data = json.loads(text)
    slots = data.get("slots") if isinstance(data, dict) else data
    if not isinstance(slots, list) or not slots:
        raise SystemExit("blueprint 需要非空的 slots 列表")
    return slots


def resolve_slots(args: argparse.Namespace) -> tuple[str, list[dict]]:
    """把 --tag/--count 或 --blueprint 统一成校验过的槽位列表。校验一视同仁，不因蓝图放宽。"""
    if args.blueprint:
        if args.tag or args.count:
            raise SystemExit("--blueprint 与 --tag/--count 互斥")
        raw_slots = load_blueprint(args.blueprint)
    else:
        if not args.tag or not args.count:
            raise SystemExit("需要 --tag 与 --count，或改用 --blueprint")
        raw_slots = [{"tag": args.tag, "count": args.count, "difficulty": args.difficulty}]

    slots: list[dict] = []
    modules: set[str] = set()
    for raw in raw_slots:
        if not isinstance(raw, dict):
            raise SystemExit(f"槽位必须是对象: {raw!r}")
        tag_in = str(raw.get("tag") or "").strip()
        count = int(raw.get("count") or 0)
        if not tag_in or count < 1:
            raise SystemExit(f"槽位缺 tag 或 count: {raw!r}")
        parts = [part for part in tag_in.split("-") if part]
        subtype = parts[1] if len(parts) > 1 else ""
        tag = validate_ai_primary_tag(canonicalize(tag_in, args.module, subtype), args.module)
        head = tag.split("-", 1)[0]
        modules.add(head if head in MODULES else module_of(tag, args.module))
        slot = {"tag": tag, "count": count}
        if raw.get("difficulty"):
            slot["difficulty"] = str(raw["difficulty"])
        if raw.get("brief"):
            slot["brief"] = str(raw["brief"]).strip()[:BRIEF_LIMIT]
        slots.append(slot)
    if len(modules) > 1:
        raise SystemExit(f"一个批次只能一个模块，收到: {sorted(modules)}")
    return modules.pop(), slots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes / CLI 专项出题")
    parser.add_argument("--module", default="", help="判断推理 / 数量关系 / 言语理解与表达")
    parser.add_argument("--tag", help="规范主标签，如 判断推理-逻辑判断-翻译推理")
    parser.add_argument("--count", type=int)
    parser.add_argument(
        "--blueprint",
        help='多考法编排，内联 JSON 或 @路径：{"slots":[{"tag":"...","count":3,"difficulty":"hard"}]}',
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--difficulty", choices=["easy", "hard"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "hermes-batches")
    parser.add_argument("--timeout", type=int, default=2400)
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--interactive", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    module, slots = resolve_slots(args)
    total = sum(int(slot["count"]) for slot in slots)
    if total < 1 or total > 15:
        raise SystemExit("专项题量必须是 1–15；成套卷走日练")
    today = local_today()
    run = {
        "module": module,
        "plan_date": today,
        "batch_id": args.batch_id,
        "planned_count": total,
        "focus_tag": slots[0]["tag"],
        "slots": slots,
        "difficulty": args.difficulty,
    }
    for slot in slots:
        reject_unsupported(module, str(slot["tag"]))
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        snapshot = load_snapshot(conn)
        exists = int(
            conn.execute("SELECT COUNT(*) FROM questions WHERE batch_id=?", (args.batch_id,)).fetchone()[0]
        )
    finally:
        conn.close()
    if exists:
        raise SystemExit(f"batch_id 已入库 {exists} 题，换一个序号")
    batch_dir = args.output_dir / today.isoformat() / args.batch_id
    try:
        imported = generate_and_import(run, batch_dir, args.db, args.timeout, snapshot)
        result = {
            "status": "success",
            "batch_id": args.batch_id,
            "imported": imported,
            "batch_dir": str(batch_dir),
            "tag": run["focus_tag"],
            "slots": slots,
            "message": f"已入库 {imported} 题，批次 {args.batch_id}",
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        result = {
            "status": "error",
            "batch_id": args.batch_id,
            "error": str(exc)[:2000],
            "message": f"出题失败：{str(exc)[:500]}",
        }
        print(json.dumps(result, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

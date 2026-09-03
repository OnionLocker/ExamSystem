#!/usr/bin/env python3
"""Mechanical pre-gate fixes for AI batches. Does not rewrite stems or facts."""

from __future__ import annotations

import json
import os
import random
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from scheduler_common import daily_source_for_batch, module_from_daily_batch
from kaodian_taxonomy import (
    question_primary_tag,
    validate_ziliao_paper_answers,
)


LETTERS = ("A", "B", "C", "D")
CAT_ZILIAO = "\u8d44\u6599\u5206\u6790"
CAT_PANDUAN = "\u5224\u65ad\u63a8\u7406"
CAT_KEPUI = "\u79d1\u5b66\u63a8\u7406"
CAT_SHULIANG = "\u6570\u91cf\u5173\u7cfb"
CAT_YANYU = "\u8a00\u8bed\u7406\u89e3\u4e0e\u8868\u8fbe"
ALLOWED_SUBS = {
    "\u6570\u91cf\u5173\u7cfb": ("\u6570\u5b57\u63a8\u7406", "\u6570\u5b66\u8fd0\u7b97"),
    "\u5224\u65ad\u63a8\u7406": (
        "\u56fe\u5f62\u63a8\u7406",
        "\u903b\u8f91\u5224\u65ad",
    ),
    "\u79d1\u5b66\u63a8\u7406": ("\u79d1\u5b66\u63a8\u7406",),
}

_MENTION = re.compile(
    r"(?P<pre>\u6545\u9009|\u5e94\u9009|\u7b54\u6848\u4e3a|\u7b54\u6848\u662f|"
    r"\u6b63\u786e\u7b54\u6848\u4e3a|\u6b63\u786e\u7b54\u6848\u662f|\u7b54\u6848[:\uff1a]|\u9009\u9879)"
    r"(?P<a>[ABCD])"
    r"|(?P<b>[ABCD])(?P<suf>\u9879|\u9009\u9879)"
    r"|(?P<pre2>\u9009)(?P<c>[ABCD])(?![A-Za-z])"
)


def is_zhenti(question: dict) -> bool:
    return str(question.get("origin") or "") == "zhenti" or str(
        question.get("external_id") or ""
    ).startswith("zhenti-")


def generated_questions(questions: list[dict]) -> list[dict]:
    return [question for question in questions if isinstance(question, dict) and not is_zhenti(question)]



def is_daily_batch(batch_id: str) -> bool:
    return str(batch_id or "").startswith("daily-")


def _paper_blob(question: dict) -> str:
    return f"{question.get('sub_category') or ''} {question_primary_tag(question)}"


def paper_rank(question: dict) -> tuple:
    cat = str(question.get("category") or "")
    blob = _paper_blob(question)
    if cat == CAT_SHULIANG:
        return (0 if "\u6570\u5b57\u63a8\u7406" in blob else 1, "")
    if cat == CAT_PANDUAN:
        if "\u56fe\u5f62\u63a8\u7406" in blob:
            return (0, "")
        return (1, "")
    if cat == CAT_KEPUI:
        return (0, "")
    if cat == CAT_YANYU:
        return (0 if "\u903b\u8f91\u586b\u7a7a" in blob else 1, "")
    if cat == CAT_ZILIAO:
        return (0, str(question.get("material_id") or ""))
    return (0, "")


def sort_daily_questions(questions: list[dict]) -> list[dict]:
    return [
        question
        for _, question in sorted(
            enumerate(questions),
            key=lambda item: (*paper_rank(item[1]), item[0]),
        )
    ]


def validate_daily_paper_order(batch_id: str, questions: list[dict]) -> None:
    if not is_daily_batch(batch_id):
        return
    generated = generated_questions(questions)
    if len(generated) == 15 and all(str(item.get("category") or "") == CAT_SHULIANG for item in generated):
        if any("\u6570\u5b57\u63a8\u7406" not in _paper_blob(item) for item in generated[:5]):
            raise ValueError("\u5e7f\u4e1c\u7701\u8003\u6570\u91cf\u5173\u7cfb\u5957\u9898\u524d 5 \u9898\u5fc5\u987b\u662f\u6570\u5b57\u63a8\u7406")
        if any("\u6570\u5b57\u63a8\u7406" in _paper_blob(item) for item in generated[5:]):
            raise ValueError("\u5e7f\u4e1c\u7701\u8003\u6570\u91cf\u5173\u7cfb\u5957\u9898\u540e 10 \u9898\u5fc5\u987b\u662f\u6570\u5b66\u8fd0\u7b97")


def letter_counts(n: int) -> tuple[int, int, int, int]:
    if n <= 0:
        return (0, 0, 0, 0)
    base, extra = divmod(n, 4)
    counts = [base] * 4
    for index in range(extra):
        counts[index] += 1
    return tuple(counts)


def default_answer_constraints(n: int) -> dict[str, int]:
    counts = letter_counts(n)
    return {
        "answer_max_per_letter": max(counts) or 1,
        "answer_min_letters": min(4, n) if n else 1,
    }


def planned_ziliao_groups(rng: random.Random) -> list[list[str]]:
    groups = [
        list("ABCDA"),
        list("ABCDB"),
        list("ABCDA"),
        list("BCCDD"),
    ]
    for group in groups:
        rng.shuffle(group)
    rng.shuffle(groups)
    validate_ziliao_paper_answers(groups)
    return groups


def planned_letters(module: str, n: int, seed: str) -> list[str]:
    rng = random.Random(seed)
    if module == CAT_ZILIAO and n == 20:
        return [key for group in planned_ziliao_groups(rng) for key in group]
    letters: list[str] = []
    for letter, count in zip(LETTERS, letter_counts(n)):
        letters.extend([letter] * count)
    rng.shuffle(letters)
    return letters


def compact_ziliao_pack(pack: dict) -> dict:
    materials = []
    for material in pack.get("materials") or []:
        materials.append(
            {
                "form": material.get("form"),
                "form_label": material.get("form_label"),
                "answers": list(material.get("answers") or []),
                "slots": [
                    {
                        "tag": slot.get("tag"),
                        "answer": slot.get("answer"),
                        "reason": slot.get("reason"),
                    }
                    for slot in material.get("slots") or []
                ],
            }
        )
    return {"paper_style": pack.get("paper_style") or "gd", "materials": materials}


def generation_payload_extras(
    module: str,
    n: int,
    seed: str,
    db_path: Path | None = None,
    focus_tag: str = "",
) -> dict:
    letters = planned_letters(module, n, seed)
    counts = Counter(letters)
    extras: dict[str, Any] = {
        "answer_plan": [{"index": index + 1, "answer": letter} for index, letter in enumerate(letters)],
        "batch_constraints": {
            "all_original": True,
            "question_count": n,
            **default_answer_constraints(n),
        },
    }
    extras["batch_constraints"]["answer_max_per_letter"] = max(counts.values()) if counts else 1
    extras["batch_constraints"]["answer_min_letters"] = len(counts)
    tag = str(focus_tag or "").strip()
    if tag:
        extras["batch_constraints"]["focus_tag"] = tag
        return extras
    if module == CAT_SHULIANG and n == 15:
        extras["batch_constraints"]["shuliang_layout"] = "5_sequence_plus_10_math"
    if module == CAT_PANDUAN and n == 20:
        extras["batch_constraints"]["panduan_layout"] = "5_graphic_plus_15_logic"
        from panduan_pack import compact_panduan_pack, select_panduan_paper

        packed = None
        if db_path is not None:
            try:
                from learner_snapshot import build_panduan_pack

                conn = sqlite3.connect(db_path)
                try:
                    packed = build_panduan_pack(conn, letters, seed)
                finally:
                    conn.close()
            except (sqlite3.Error, OSError, ImportError):
                packed = None
        if packed is None:
            packed = {
                "paper_style": "gd",
                "slots": select_panduan_paper({}, {}, letters=letters, rng=random.Random(seed)),
            }
        extras["panduan_pack"] = compact_panduan_pack(packed)
    if module == CAT_KEPUI and n == 5:
        extras["batch_constraints"]["kepui_layout"] = "5_kepui_distinct_subjects"
        extras["batch_constraints"]["kepui_subjects"] = [
            "\u529b\u5b66",
            "\u538b\u5f3a\u6d6e\u529b",
            "\u7535\u5b66",
            "\u751f\u7269",
            "\u5730\u7406",
        ]
        extras["batch_constraints"]["image_dependent_count"] = {"min": 5, "max": 5}
        from panduan_pack import compact_kepui_pack, select_kepui_paper

        packed = None
        if db_path is not None:
            try:
                from learner_snapshot import build_kepui_pack

                conn = sqlite3.connect(db_path)
                try:
                    packed = build_kepui_pack(conn, letters, seed)
                finally:
                    conn.close()
            except (sqlite3.Error, OSError, ImportError):
                packed = None
        if packed is None:
            packed = {
                "paper_style": "gd",
                "slots": select_kepui_paper({}, {}, letters=letters, rng=random.Random(seed)),
            }
        extras["kepui_pack"] = compact_kepui_pack(packed)
    if module == CAT_ZILIAO and n == 20:
        extras["ziliao_answer_groups"] = [letters[index : index + 5] for index in range(0, 20, 5)]
        if db_path is not None:
            try:
                from learner_snapshot import build_ziliao_pack

                conn = sqlite3.connect(db_path)
                try:
                    extras["ziliao_pack"] = compact_ziliao_pack(build_ziliao_pack(conn))
                finally:
                    conn.close()
            except (sqlite3.Error, OSError, ImportError):
                pass
    return extras



def is_kepui_batch(manifest: dict, questions: list[dict]) -> bool:
    batch_id = str(manifest.get("batch_id") or "")
    module = str(manifest.get("module") or manifest.get("category") or "")
    if "-kepui-" in batch_id or module == CAT_KEPUI:
        return True
    generated = generated_questions(questions)
    if len(generated) != 5:
        return False
    from panduan_pack import is_science_question

    return all(is_science_question(item) for item in generated)


def rewrite_kepui_category(manifest: dict, questions: list[dict]) -> int:
    """Force independent 科学推理 papers onto CAT_KEPUI; do not trust the LLM."""
    if not is_kepui_batch(manifest, questions):
        return 0
    changed = 0
    for question in generated_questions(questions):
        if str(question.get("category") or "") != CAT_KEPUI:
            question["category"] = CAT_KEPUI
            changed += 1
        if str(question.get("sub_category") or "").strip() != CAT_KEPUI:
            question["sub_category"] = CAT_KEPUI
            changed += 1
    return changed


def current_answer(question: dict) -> str:
    return str(question.get("answer") or question.get("correct_answer") or "").strip().upper()


def answer_counts(questions: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for question in generated_questions(questions):
        answer = current_answer(question)
        if answer:
            counts[answer] = counts.get(answer, 0) + 1
    return counts


def answer_distribution_ok(manifest: dict, questions: list[dict]) -> bool:
    generated = generated_questions(questions)
    constraints = (manifest.get("generation") or {}).get("batch_constraints") or {}
    defaults = default_answer_constraints(len(generated))
    max_per = int(constraints.get("answer_max_per_letter") or defaults["answer_max_per_letter"])
    min_letters = int(constraints.get("answer_min_letters") or 1)
    counts = answer_counts(questions)
    if not counts:
        return True
    if max(counts.values()) > max_per or len(counts) < min_letters:
        return False
    try:
        _assert_ziliao_layout(questions)
    except ValueError:
        return False
    return True


def _assert_ziliao_layout(questions: list[dict]) -> None:
    groups: dict[str, list[str]] = {}
    for question in generated_questions(questions):
        if str(question.get("category") or "") != CAT_ZILIAO:
            continue
        material_id = str(question.get("material_id") or "")
        if not material_id:
            continue
        groups.setdefault(material_id, []).append(current_answer(question))
    if len(groups) == 4 and all(len(keys) == 5 for keys in groups.values()):
        validate_ziliao_paper_answers(list(groups.values()))


def has_question_images(question: dict) -> bool:
    if question.get("stem_images"):
        return True
    return any(option.get("images") for option in question.get("options") or [])


def fill_bookkeeping(question: dict) -> list[str]:
    changed = []
    if not str(question.get("answer") or "").strip() and question.get("correct_answer"):
        question["answer"] = str(question["correct_answer"]).strip().upper()
        changed.append("answer")
    tags = question.get("tags")
    if not (isinstance(tags, list) and any(str(tag).strip() for tag in tags)):
        fallback = question.get("knowledge_point") or question.get("knowledge_points")
        if isinstance(fallback, str) and fallback.strip():
            question["tags"] = [fallback.strip()]
            changed.append("tags")
        elif isinstance(fallback, list):
            cleaned = [str(tag).strip() for tag in fallback if str(tag).strip()]
            if cleaned:
                question["tags"] = cleaned
                changed.append("tags")
    category = str(question.get("category") or "")
    allowed = ALLOWED_SUBS.get(category) or ()
    if allowed and not str(question.get("sub_category") or "").strip():
        tag = question_primary_tag(question)
        if "\u79d1\u5b66\u63a8\u7406" in tag:
            question["sub_category"] = "\u79d1\u5b66\u63a8\u7406"
            changed.append("sub_category")
        else:
            parts = [part for part in tag.split("-") if part]
            if len(parts) >= 2 and parts[1] in allowed:
                question["sub_category"] = parts[1]
                changed.append("sub_category")
    if not str(question.get("analysis") or "").strip():
        explanation = str(question.get("explanation") or "").strip()
        if explanation:
            question["analysis"] = explanation
            changed.append("analysis")
    if not str(question.get("question_type") or "").strip():
        question["question_type"] = "single"
        changed.append("question_type")
    return changed


def remap_letter_mentions(text: str, src: str, dst: str) -> str:
    if not text or src == dst:
        return text

    def swap(letter: str) -> str:
        if letter == src:
            return dst
        if letter == dst:
            return src
        return letter

    def repl(match: re.Match[str]) -> str:
        if match.group("a") is not None:
            return f"{match.group('pre')}{swap(match.group('a'))}"
        if match.group("b") is not None:
            return f"{swap(match.group('b'))}{match.group('suf')}"
        return f"{match.group('pre2')}{swap(match.group('c'))}"

    return _MENTION.sub(repl, text)


def swap_option_pair(question: dict, src: str, dst: str) -> bool:
    if src == dst:
        return False
    options = question.get("options") or []
    by_key = {str(option.get("key")): option for option in options if isinstance(option, dict)}
    left, right = by_key.get(src), by_key.get(dst)
    if left is None or right is None:
        return False

    def payload(option: dict) -> dict:
        return {key: value for key, value in option.items() if key != "key"}

    left_payload, right_payload = payload(left), payload(right)
    for option in (left, right):
        for key in list(option):
            if key != "key":
                del option[key]
    left.update(right_payload)
    right.update(left_payload)
    question["answer"] = dst
    if question.get("correct_answer"):
        question["correct_answer"] = dst
    for field in ("explanation", "analysis"):
        if field in question and isinstance(question[field], str):
            question[field] = remap_letter_mentions(question[field], src, dst)
    return True


def remap_calculation_spec(spec: dict, src: str, dst: str) -> None:
    options = spec.get("options")
    if isinstance(options, dict) and src in options and dst in options:
        options[src], options[dst] = options[dst], options[src]
    if str(spec.get("answer") or "").upper() == src:
        spec["answer"] = dst


def load_calculations(path: Path) -> tuple[Any, dict[str, dict]]:
    if not path.is_file():
        return None, {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    specs = raw.get("questions") if isinstance(raw, dict) else raw
    by_id = {
        str(item.get("question_id") or item.get("external_id") or ""): item
        for item in specs or []
        if isinstance(item, dict)
    }
    return raw, by_id


def assign_target_letters(questions: list[dict], manifest: dict) -> dict[str, str]:
    generated = generated_questions(questions)
    seed = str(manifest.get("batch_id") or "batch")
    targets: dict[str, str] = {}
    ziliao_groups: dict[str, list[dict]] = {}
    others: list[dict] = []
    for question in generated:
        if str(question.get("category") or "") == CAT_ZILIAO and str(question.get("material_id") or ""):
            ziliao_groups.setdefault(str(question["material_id"]), []).append(question)
        else:
            others.append(question)
    if len(ziliao_groups) == 4 and all(len(items) == 5 for items in ziliao_groups.values()):
        planned = planned_ziliao_groups(random.Random(seed))
        for items, keys in zip(ziliao_groups.values(), planned):
            for question, letter in zip(items, keys):
                targets[str(question.get("external_id"))] = letter
        others = [question for question in generated if str(question.get("external_id")) not in targets]
    if others:
        letters = planned_letters(str(generated[0].get("category") or ""), len(others), seed + "-rest")
        if len(letters) != len(others):
            letters = planned_letters("", len(others), seed + "-rest")
        for question, letter in zip(others, letters):
            targets[str(question.get("external_id"))] = letter
    return targets


def image_locks_option_letters(question: dict) -> bool:
    """Stem/option images already print A–D; swapping keys makes the figure lie."""
    has_image = bool(question.get("stem_images")) or any(
        option.get("images") for option in question.get("options") or []
    )
    if not has_image:
        return False
    texts = [str(option.get("text") or "").strip() for option in question.get("options") or []]
    return bool(texts) and all(len(text) <= 2 for text in texts)


def redistribute_answers(questions: list[dict], manifest: dict, calculations: dict[str, dict]) -> int:
    if answer_distribution_ok(manifest, questions):
        return 0
    targets = assign_target_letters(questions, manifest)
    rewritten = 0
    for question in generated_questions(questions):
        qid = str(question.get("external_id") or "")
        dst = targets.get(qid)
        src = current_answer(question)
        if not dst or not src or src == dst:
            continue
        if image_locks_option_letters(question):
            continue
        if swap_option_pair(question, src, dst):
            rewritten += 1
            spec = calculations.get(qid)
            if spec:
                remap_calculation_spec(spec, src, dst)
    return rewritten


def ensure_batch_constraints(manifest: dict, questions: list[dict]) -> None:
    generation = manifest.setdefault("generation", {})
    if not isinstance(generation, dict):
        manifest["generation"] = generation = {}
    constraints = generation.get("batch_constraints")
    if not isinstance(constraints, dict):
        constraints = {}
        generation["batch_constraints"] = constraints
    generated = generated_questions(questions)
    constraints.setdefault("all_original", True)
    constraints.setdefault("question_count", len(generated))
    defaults = default_answer_constraints(len(generated))
    constraints.setdefault("answer_max_per_letter", defaults["answer_max_per_letter"])
    constraints.setdefault("answer_min_letters", defaults["answer_min_letters"])
    if not generation.get("style_marker"):
        try:
            from reference_style import DIGEST_VERSION

            generation["style_marker"] = DIGEST_VERSION
        except Exception:
            generation["style_marker"] = "GONGKAO-STYLE-v1"


def _exam_db() -> sqlite3.Connection | None:
    path = Path(os.environ.get("EXAM_DB") or Path(__file__).resolve().parents[1] / "data" / "exam.db")
    if not path.is_file():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_context(conn: sqlite3.Connection, **kwargs) -> dict:
    from reference_style import select_context

    return select_context(conn, **kwargs)


def _context_target(conn: sqlite3.Connection, context_id: str) -> tuple[dict, str, list] | None:
    row = conn.execute(
        "SELECT role, target, reference_ids FROM reference_context_runs WHERE context_id = ?",
        (context_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        target = json.loads(row["target"] or "{}")
        refs = json.loads(row["reference_ids"] or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(target, dict):
        target = {}
    return target, str(row["role"] or ""), refs if isinstance(refs, list) else []


def _item_matches(item: dict, questions_by_id: dict[str, dict], role: str, conn: sqlite3.Connection) -> bool:
    context_id = str(item.get("context_id") or "")
    loaded = _context_target(conn, context_id)
    if loaded is None:
        return False
    target, stored_role, refs = loaded
    if stored_role != role:
        return False
    if refs != list(item.get("reference_ids") or []):
        return False
    for qid in item.get("question_ids") or []:
        question = questions_by_id.get(str(qid))
        if question is None:
            return False
        if target.get("category") != question.get("category"):
            return False
        if question.get("sub_category") and target.get("sub_category") != question.get("sub_category"):
            return False
        if target.get("tag") != question_primary_tag(question):
            return False
        if has_question_images(question) and target.get("image_mode") != "yes":
            return False
    return True


def _role_ok(items: list, ids: list[str], questions_by_id: dict[str, dict], role: str, conn: sqlite3.Connection) -> bool:
    covered = [str(qid) for item in items for qid in (item.get("question_ids") or [])]
    if set(covered) != set(ids) or len(covered) != len(ids):
        return False
    return all(_item_matches(item, questions_by_id, role, conn) for item in items)


def _group_questions(questions: list[dict]) -> list[tuple[tuple, list[str]]]:
    grouped: dict[tuple, list[str]] = {}
    order: list[tuple] = []
    for question in questions:
        tag = question_primary_tag(question)
        if not tag:
            continue
        key = (
            str(question.get("category") or ""),
            str(question.get("sub_category") or ""),
            tag,
            "yes" if has_question_images(question) else "any",
        )
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(str(question.get("external_id")))
    return [(key, grouped[key]) for key in order]


def repair_reference_contexts(manifest: dict, questions: list[dict]) -> bool:
    generated = generated_questions(questions)
    ids = [str(question.get("external_id")) for question in generated]
    if not ids:
        return False
    conn = _exam_db()
    if conn is None:
        return False
    questions_by_id = {str(question.get("external_id")): question for question in generated}
    changed = False
    try:
        conn.execute("SELECT 1 FROM reference_context_runs LIMIT 1")
    except sqlite3.Error:
        conn.close()
        return False
    try:
        generation = manifest.setdefault("generation", {})
        gen_items = generation.get("generation_contexts") or []
        valid_gen = [
            item for item in gen_items
            if _item_matches(item, questions_by_id, "generate", conn)
        ]
        if valid_gen != list(gen_items):
            generation["generation_contexts"] = valid_gen
            changed = True
            gen_items = valid_gen
        eval_items = generation.get("evaluation_contexts") or []
        exclude = {
            str(ref)
            for item in gen_items
            for ref in (item.get("reference_ids") or [])
        }
        rebuilt = []
        for item in eval_items:
            if _item_matches(item, questions_by_id, "evaluate", conn):
                rebuilt.append(item)
                exclude.update(str(ref) for ref in (item.get("reference_ids") or []))
        covered = {str(qid) for item in rebuilt for qid in (item.get("question_ids") or [])}
        for (category, sub, tag, image_mode), qids in _group_questions(generated):
            if all(qid in covered for qid in qids):
                continue
            try:
                result = _fetch_context(
                    conn,
                    role="evaluate",
                    category=category,
                    sub_category=sub,
                    target_tag=tag,
                    count=1,
                    image_mode=image_mode,
                    exclude_ids=exclude,
                )
            except (RuntimeError, sqlite3.Error, TypeError, ValueError):
                continue
            rebuilt.append(
                {
                    "context_id": result["context_id"],
                    "reference_ids": list(result.get("reference_ids") or []),
                    "question_ids": qids,
                }
            )
            exclude.update(str(ref) for ref in result.get("reference_ids") or [])
            covered.update(qids)
        if rebuilt != list(eval_items):
            generation["evaluation_contexts"] = rebuilt
            changed = True
        if changed:
            try:
                from reference_style import DIGEST_VERSION

                generation.setdefault("style_marker", DIGEST_VERSION)
            except Exception:
                generation.setdefault("style_marker", "GONGKAO-STYLE-v1")
        return changed
    finally:
        conn.close()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def collapse_material_blank_lines(text: str) -> str:
    raw = str(text or "").replace("\r\n", "\n")
    return re.sub(r"[ \t]*\n(?:[ \t]*\n)+", "\n", raw).strip("\n")


def normalize_materials(materials: list | None) -> int:
    changed = 0
    if not isinstance(materials, list):
        return 0
    for material in materials:
        if not isinstance(material, dict):
            continue
        content = material.get("content")
        if not isinstance(content, str):
            continue
        cleaned = collapse_material_blank_lines(content)
        if cleaned != content:
            material["content"] = cleaned
            changed += 1
    return changed


def stamp_daily_source(manifest: dict, questions: list[dict], materials: list | None = None) -> int:
    batch_id = str(manifest.get("batch_id") or "")
    module = module_from_daily_batch(batch_id)
    if not module:
        for question in questions:
            if isinstance(question, dict) and question.get("category"):
                module = str(question["category"])
                break
        module = module or str(manifest.get("category") or manifest.get("module") or "")
    name = daily_source_for_batch(batch_id, module)
    if not name:
        return 0
    changed = 0
    if manifest.get("source") != name:
        manifest["source"] = name
        changed += 1
    for question in generated_questions(questions):
        if question.get("source") != name:
            question["source"] = name
            changed += 1
    if isinstance(materials, list):
        for material in materials:
            if isinstance(material, dict) and material.get("source") != name:
                material["source"] = name
                changed += 1
    return changed

def normalize_batch(batch_dir: Path) -> dict[str, Any]:
    batch_dir = Path(batch_dir)
    questions_path = batch_dir / "questions.json"
    manifest_path = batch_dir / "manifest.json"
    if not questions_path.is_file() or not manifest_path.is_file():
        return {"changed": False}
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not isinstance(manifest, dict):
        return {"changed": False}
    materials_path = batch_dir / "materials.json"
    materials = None
    if materials_path.is_file():
        loaded = json.loads(materials_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            materials = loaded
    kepui_rewritten = rewrite_kepui_category(manifest, questions)
    filled = 0
    for question in generated_questions(questions):
        filled += len(fill_bookkeeping(question))
    ordered = False
    if is_daily_batch(str(manifest.get("batch_id") or "")):
        sorted_questions = sort_daily_questions(questions)
        if [id(item) for item in sorted_questions] != [id(item) for item in questions]:
            questions[:] = sorted_questions
            ordered = True
    ensure_batch_constraints(manifest, questions)
    calc_path = batch_dir / "calculations.json"
    raw_calc, by_id = load_calculations(calc_path)
    rewritten = redistribute_answers(questions, manifest, by_id)
    contexts = repair_reference_contexts(manifest, questions)
    sourced = stamp_daily_source(manifest, questions, materials)
    compacted = normalize_materials(materials)
    changed = bool(filled or rewritten or contexts or sourced or ordered or kepui_rewritten or compacted)
    if filled or rewritten or sourced or ordered or kepui_rewritten:
        write_json(questions_path, questions)
        if raw_calc is not None and rewritten:
            write_json(calc_path, raw_calc)
    if materials is not None and (sourced or compacted):
        write_json(materials_path, materials)
    if filled or rewritten or contexts or sourced:
        write_json(manifest_path, manifest)
    return {
        "changed": changed,
        "fields_filled": filled,
        "answers_rewritten": rewritten,
        "contexts_repaired": contexts,
        "source_stamped": sourced,
    }

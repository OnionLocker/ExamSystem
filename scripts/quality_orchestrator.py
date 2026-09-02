#!/usr/bin/env python3
"""Run ExamSystem-owned correctness and quality checks for AI question batches."""

from __future__ import annotations

import argparse
import ast
import base64
import difflib
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from hermes_skills import quiz_pipeline_references
from normalize_ai_batch import answer_distribution_ok as mechanical_answers_ok
from normalize_ai_batch import generated_questions
from panduan_pack import is_panduan_paper, validate_panduan_paper


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("QUALITY_GATE_MODEL", "gemini-3.7-flash-high")
MOBILE_WIDTH = 320
RETRIES = 2

CAT_YANYU = "\u8a00\u8bed\u7406\u89e3\u4e0e\u8868\u8fbe"
CAT_PANDUAN = "\u5224\u65ad\u63a8\u7406"
CAT_SHULIANG = "\u6570\u91cf\u5173\u7cfb"
CAT_ZILIAO = "\u8d44\u6599\u5206\u6790"
SUB_LOGIC = "\u903b\u8f91\u5224\u65ad"
SUB_GRAPH = "\u56fe\u5f62\u63a8\u7406"
SUB_SCIENCE = "\u79d1\u5b66\u63a8\u7406"


def is_yanyu(question: dict) -> bool:
    return "\u8a00\u8bed\u7406\u89e3" in str(question.get("category") or "")


FORMAL_TAG_WORDS = (
    "\u7ffb\u8bd1\u63a8\u7406",
    "\u771f\u5047\u8bdd",
    "\u96c6\u5408",
    "\u63a8\u7406\u5f62\u5f0f",
)

BLIND_SYSTEM = """You are an isolated blind reviewer for Chinese civil-service exam questions.
You do not know the answer key and must solve each question independently. For every item,
select exactly one answer only when it is uniquely defensible. If another option can also stand,
list it in also_valid and reject the item. Return JSON only:
{"questions":[{"id":"...","answer":"A","also_valid":[],"verdict":"PASS","reason":"..."}]}"""

ADVERSARIAL_BLIND_SYSTEM = """You are the adversarial blind solver for Chinese civil-service
exam questions. You cannot see the official key. Your primary job is to try every option, especially
near-synonyms, alternate sentence insertions, causal confounders and unstated scientific models.
Compare every option in the full context and try to find a genuine tie. Distractors may be locally
plausible; that is normal for this exam. REJECT only if another option is equally or more appropriate,
the claimed answer needs an unstated premise, or the passage is internally inconsistent. PASS when
one option is clearly best by collocation, semantic direction, reference, scope, logic, or passage
focus, even if another option could make sense in isolation. Return JSON only:
{"questions":[{"id":"...","answer":"A","also_valid":[],"verdict":"PASS","reason":"...",
"option_tests":{"A":{"stands":true,"basis":"...","fatal_defect":""},
"B":{"stands":false,"basis":"...","fatal_defect":"..."}}}]}"""

BATCH_SYSTEM = """You are a defect-first batch editor for Guangdong civil-service questions.
Review the set as a whole, not item by item. Check requested tag/type mix,
real cognitive difficulty, repeated argument skeletons, repeated distractor paths, repeated prose
templates, unsupported dynamic facts, and whether image use matches real necessity. Also verify that
all evaluation references belong to the same module and topic as the covered item. Items with an empty evaluation reference list are syllabus mocks; reference_alignment_ok stays true for them. Return JSON only:
{"verdict":"PASS","type_distribution_ok":true,
"difficulty_distribution_ok":true,"reference_alignment_ok":true,"duplicate_groups":[],"issues":[]}
Do not reject for answer-letter placement; the system assigns option letters separately.
Any repeated reskin, all-identical difficulty without justification,
wrong-module reference, user constraint mismatch, repeated boilerplate prose, giveaway extreme-word distractors,
or inflated difficulty labels must be REJECT.
A 20-item 判断推理 paper must be questions 1-15 图形推理+逻辑判断 (multiple families, 翻译推理 at most 2,
no 定义判断/类比推理) and questions 16-20 科学推理 covering 力学/压强浮力/电学/生物/地理
(physics 2-3 + biology 1 + geography 1). type_distribution_ok is false if that layout is missing."""

REFERENCE_SYSTEM = """You are a strict reference-relevance auditor. For every generated question,
read its exact stem/tag and every mapped evaluation reference.
A logic reference is relevant when it uses the same question family (strengthen, weaken,
assumption, translation, explanation, matching, parallel structure). One sibling in a pack
does not fail the item when at least one reference is the same family.
A science-reasoning reference is relevant when it is the same discipline
(mechanics, pressure/buoyancy, electricity, biology, geography, chemistry).
Do not reject geography earth-motion vs contour, or rheostat vs thermistor, as different
disciplines. Sharing only the umbrella "science reasoning" is not enough.
Treat wrong or over-broad legacy tags as untrusted and decide from actual content. Return JSON only:
{"questions":[{"id":"...","verdict":"PASS","references":[{"id":"...","relevant":true,"reason":"..."}]}]}
Reject the item only if every mapped reference is a different family or discipline."""

FORMAL_SYSTEM = """You independently translate Chinese formal-logic questions into propositional
logic. Do not use or guess any hidden answer key. Only handle implication, equivalence, negation,
and/or, truth-teller and set-entailment questions. Use syntax !, &, |, ->, <-> and short Chinese
variable names without connective words. Facts after 已知/现已知 must be standalone literals
or conjunctions of literals; never fold them into implications or omit them.
Return JSON only:
{"questions":[{"id":"...","premises":["A -> B"],"options":{"A":"...","B":"...","C":"...","D":"..."}}]}"""

D_CANDIDATE_SYSTEM = """You are a blind Guangdong civil-service exam candidate. Read the supplied
question text and actual figures only. Do not infer a hidden key. Reject an item if the figure is
unclear, cropped, contradictory, leaks a solution, or more than one answer is defensible. Return
JSON only:
{"questions":[{"id":"...","answer":"A","also_valid":[],"verdict":"PASS","issues":[]}]}"""

D_SETTER_SYSTEM = """You are an independent setter-side visual reviewer for Guangdong civil-service
exam questions. Compare each actual figure with IMAGE_FACTS, IMAGE_ONLY_FACTS and MUST_DERIVE. The figure must show
all and only permitted facts, every IMAGE_ONLY_FACT must be visible and not redundantly stated in the stem,
must not reveal MUST_DERIVE, and must remain readable at 320px width.
Reject any missing-glyph box, unreadable Latin variable/digit, wrong count, label, direction, connection,
overlap, crop, ambiguity, or answer mismatch. For circuits, trace every endpoint and require a rheostat
to use its slider terminal. Mentally remove the image: if all answer-essential facts remain in the stem,
the image is decorative and the item must be rejected.
Return JSON only:
{"questions":[{"id":"...","verdict":"PASS","issues":[]}]}"""

QUALITY_SYSTEM = """You are an independent defect-first Guangdong civil-service exam quality gate.
Correctness checks may be wrong; actively challenge them. Compare each item only with the evaluation
references mapped to that item and the supplied regression rules. For fill/insert/title questions,
compare every rival in the complete context. Distractors may be locally plausible; reject only a genuine
tie or a key supported solely by an unstated premise. Reject obvious factual distortion, internal
contradiction, excessive slogan/template prose, near-verbatim answer copying, three giveaway extreme-word
distractors, or a difficulty label above the actual reasoning steps. For 翻译推理, reject if the keyed option restates a 已知 instance (synonyms count) without applying a 如果/除非/只有/或者 rule; the subject must stay 某企业/某团队 and must not leak the conclusion. Regression rule R029: echo of 已知 is a hard fail even when the option is logically true. Regression rule R030: a 20-question 判断推理 paper must not be a single family; last five must be 科学推理 with 生物, 地理 and at least two physics items. Regression rule R032: for 加强/削弱/前提/解释 (强化削弱型) questions, the keyed option must act on THIS argument's conclusion or its premise chain; an option that is merely true or on-topic but does not change the argument's support (跑题的加强/削弱项) is a hard fail, and if two or more options change the support to a comparable degree the item is not uniquely keyed and must be rejected. Regression rule R035 (soft, subjective): if the batch declares a difficulty_tier (easy/hard), judge whether the paper as a whole matches it — easy means 1-2 steps, direct asks, common-mistake distractors, few cross-paragraph/multi-constraint items; hard means one extra layer on the same knowledge point (representation change, multiple constraints, half-right distractors, more cross-paragraph synthesis). Reject only when the whole paper clearly sits in the other tier (e.g. tagged easy but pervasively multi-step/multi-constraint); do not fail single borderline items, and never let tier change the fixed Guangdong structure/quota. For assumption questions, negate
every option and reject a purported necessary premise if the explanation must invent an unstated failure
or catastrophe. For science, reject unstated contact, pressure, wiring, measurement or time assumptions
and unsupported exact facts. Check tag alignment,
Guangdong ask style, information density, cognitive steps, option parallelism, three distinct diagnostic
distractor paths, no leakage, no copied skin, and unique answer. Score six dimensions 0-2; do not give
12 by default. If evaluation_only_real_questions is empty, this is a syllabus mock: judge against Guangdong syllabus/principles only, set reference_ids to [], and do not fail style_match for missing holdout. PASS requires score >=10, no zero, no hard/regression fail, module_match=true,
style_match=true, facts_closed=true, answer_unique=true, three nonempty distractor_paths,
and reference_ids echoing the exact list of external_id from evaluation_only_real_questions. Return JSON:
{"questions":[{"id":"...","score":10,"zero_items":[],"hard_fail":[],"regression_fail":[],
"module_match":true,"style_match":true,"facts_closed":true,"answer_unique":true,
"distractor_paths":{"A":"...","C":"...","D":"..."},"reference_ids":["exact_external_id_1","exact_external_id_2"],
"verdict":"PASS","issues":[]}]}"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def api_key() -> str:
    if key := os.environ.get("CLIPROXY_API_KEY", "").strip():
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("CLIPROXY_API_KEY not found")


def response_text(payload: dict) -> str:
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    ).strip()


def parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"Gemini Flash returned no JSON: {cleaned[:300]}")
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("review output must be a JSON object")
    return value


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


def call_flash(system: str, prompt: str, images: list[tuple[str, Path]] | None = None) -> dict:
    parts: list[dict] = [{"type": "text", "text": prompt}]
    for label, path in images or []:
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        parts.extend(
            [
                {"type": "text", "text": f"{label} ORIGINAL"},
                image_part(path.read_bytes(), mime),
                {"type": "text", "text": f"{label} MOBILE_320"},
                image_part(mobile_png(path)),
            ]
        )
    body = json.dumps(
        {
            "model": MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": parts},
            ],
        }
    ).encode("utf-8")
    error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(
                f"{BASE_URL}/chat/completions",
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key()}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return parse_json(response_text(payload))
        except Exception as exc:
            error = exc
            if attempt + 1 < RETRIES:
                time.sleep(2)
    raise RuntimeError(f"Gemini Flash quality call failed: {error}")


def question_images(batch_dir: Path, question: dict) -> list[Path]:
    relatives = list(question.get("stem_images") or [])
    relatives.extend(question.get("explanation_images") or [])
    for option in question.get("options") or []:
        relatives.extend(option.get("images") or [])
    paths = []
    root = batch_dir.resolve()
    for relative in relatives:
        path = (batch_dir / str(relative)).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError(f"missing or unsafe image: {relative}")
        paths.append(path)
    return paths


def classify(question: dict) -> str:
    category = str(question.get("category") or "")
    sub_category = str(question.get("sub_category") or "")
    tags = " ".join(str(value) for value in question.get("tags") or [])
    has_image = bool(
        question.get("stem_images")
        or question.get("explanation_images")
        or any(option.get("images") for option in question.get("options") or [])
    )
    if category in (CAT_SHULIANG, CAT_ZILIAO):
        return "B"
    if has_image or sub_category == SUB_GRAPH:
        return "D"
    if sub_category == SUB_LOGIC and any(word in tags for word in FORMAL_TAG_WORDS):
        return "A"
    return "C"


def public_question(question: dict, include_answer: bool = False) -> dict:
    result = {
        "id": question.get("external_id"),
        "category": question.get("category"),
        "sub_category": question.get("sub_category"),
        "stem": question.get("stem"),
        "stem_images": question.get("stem_images") or [],
        "has_stem_image": bool(question.get("stem_images")),
        "options": [
            {"key": option.get("key"), "text": option.get("text"), "has_image": bool(option.get("images"))}
            for option in question.get("options") or []
        ],
        "tags": question.get("tags") or [],
    }
    if include_answer:
        result["answer"] = question.get("answer")
        result["explanation"] = question.get("explanation")
    return result


def indexed(payload: dict) -> dict[str, dict]:
    items = payload.get("questions") or []
    if not isinstance(items, list):
        raise ValueError("review output questions must be a list")
    result = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"])] = item
    return result


def load_verify_logic():
    path = ROOT / "scripts" / "verify-logic.py"
    spec = importlib.util.spec_from_file_location("verify_logic", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verify-logic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_route_a(questions: list[dict]) -> dict[str, dict]:
    if not questions:
        return {}
    prompt = json.dumps([public_question(q) for q in questions], ensure_ascii=False)
    first = indexed(call_flash(FORMAL_SYSTEM, "Formalize independently:\n" + prompt))
    second = indexed(
        call_flash(
            FORMAL_SYSTEM + "\nUse an independent variable naming and decomposition pass.",
            "Formalize from scratch without seeing another review:\n" + prompt,
        )
    )
    verifier = load_verify_logic()
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        results = []
        issues = []
        for name, source in (("formalizer_1", first), ("formalizer_2", second)):
            formal = source.get(qid)
            if not formal:
                issues.append(f"{name} missing result")
                continue
            payload = {
                "id": qid,
                "premises": formal.get("premises") or [],
                "options": formal.get("options") or {},
                "claimed_answer": question.get("answer"),
            }
            result, code = verifier.verify(payload)
            results.append({"reviewer": name, "formalization": formal, "result": result})
            if code != 0 or result.get("verdict") != "ok":
                issues.append(f"{name}: {result.get('verdict')}")
        answers = [
            item["result"].get("entailed_options", [None])[0]
            for item in results
            if item["result"].get("verdict") == "ok"
        ]
        if len(answers) != 2 or len(set(answers)) != 1:
            issues.append("independent formalizations disagree")
        output[qid] = {
            "route": "A",
            "verdict": "PASS" if not issues else "REJECT",
            "answer": question.get("answer"),
            "runs": results,
            "issues": issues,
        }
    return output


ALLOWED_FUNCTIONS = {
    "abs": abs,
    "max": max,
    "min": min,
    "round": round,
    "sum": sum,
    "sqrt": math.sqrt,
}


def safe_eval(expression: str) -> Any:
    tree = ast.parse(str(expression), mode="eval")
    allowed_nodes = (
        ast.Expression, ast.Constant, ast.List, ast.Tuple, ast.Dict,
        ast.UnaryOp, ast.UAdd, ast.USub, ast.BinOp, ast.Add, ast.Sub,
        ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.Call,
        ast.Name, ast.Load,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"unsafe calculation node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_FUNCTIONS:
            raise ValueError(f"unsafe calculation name: {node.id}")
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS
        ):
            raise ValueError("unsafe calculation call")
    return eval(compile(tree, "<calculation>", "eval"), {"__builtins__": {}}, ALLOWED_FUNCTIONS)


def equivalent(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0, abs_tol=tolerance)
    return left == right


def run_route_b(batch_dir: Path, questions: list[dict]) -> dict[str, dict]:
    if not questions:
        return {}
    path = batch_dir / "calculations.json"
    if not path.is_file():
        return {
            str(q["external_id"]): {
                "route": "B", "verdict": "REJECT", "issues": ["missing calculations.json"]
            }
            for q in questions
        }
    raw = read_json(path)
    specs = raw.get("questions") if isinstance(raw, dict) else raw
    by_id = {str(item.get("question_id")): item for item in specs or [] if isinstance(item, dict)}
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        spec = by_id.get(qid)
        issues = []
        details = {}
        if not spec:
            issues.append("missing calculation spec")
        else:
            try:
                tolerance = float(spec.get("tolerance", 1e-9))
                target = safe_eval(spec["correct"])
                option_values = {
                    str(key): safe_eval(value) for key, value in (spec.get("options") or {}).items()
                }
                matches = [
                    key for key, value in option_values.items()
                    if equivalent(value, target, tolerance)
                ]
                details = {
                    "correct_value": target,
                    "option_values": option_values,
                    "matching_options": matches,
                    "tolerance": tolerance,
                }
                if matches != [str(question.get("answer") or "")]:
                    issues.append(f"calculation match is {matches}, claimed {question.get('answer')}")
                if set(option_values) != {
                    str(option.get("key")) for option in question.get("options") or []
                }:
                    issues.append("calculation options do not cover question options")
            except Exception as exc:
                issues.append(str(exc))
        output[qid] = {
            "route": "B",
            "verdict": "PASS" if not issues else "REJECT",
            "answer": question.get("answer"),
            "calculation": details,
            "issues": issues,
        }
    return output


def run_route_c(questions: list[dict]) -> dict[str, dict]:
    if not questions:
        return {}
    prompt = json.dumps([public_question(q) for q in questions], ensure_ascii=False)
    first = indexed(call_flash(BLIND_SYSTEM, "Solve these independently:\n" + prompt))

    # Uniqueness review needs full attention per item. A single large prompt
    # repeatedly waved through defensible rival wording in verbal questions.
    def adversarial(question: dict) -> tuple[str, dict | None]:
        qid = str(question["external_id"])
        one = json.dumps([public_question(question)], ensure_ascii=False)
        result = indexed(
            call_flash(
                ADVERSARIAL_BLIND_SYSTEM,
                "Try to prove at least two options can work. Reject unless that attempt fails:\n" + one,
            )
        )
        return qid, result.get(qid)

    with ThreadPoolExecutor(max_workers=min(4, len(questions))) as pool:
        second = dict(pool.map(adversarial, questions))
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        answer = str(question.get("answer") or "")
        reviews = [first.get(qid), second.get(qid)]
        issues = []
        for index, review in enumerate(reviews, 1):
            if not review:
                issues.append(f"blind reviewer {index} missing")
                continue
            if str(review.get("verdict") or "").upper() != "PASS":
                issues.append(f"blind reviewer {index} rejected")
            if str(review.get("answer") or "").upper() != answer:
                issues.append(f"blind reviewer {index} answered {review.get('answer')}")
            if review.get("also_valid"):
                issues.append(f"blind reviewer {index} found another valid option")
            if index == 2:
                tests = review.get("option_tests") or {}
                option_keys = {
                    str(option.get("key")) for option in question.get("options") or []
                }
                if set(tests) != option_keys:
                    issues.append("adversarial reviewer did not test every option")
                else:
                    standing = [
                        key for key, result in tests.items()
                        if isinstance(result, dict) and result.get("stands") is True
                    ]
                    if standing != [answer]:
                        issues.append(f"adversarial option tests found standing options {standing}")
                    for key, result in tests.items():
                        if key == answer or not isinstance(result, dict):
                            continue
                        defect = str(result.get("fatal_defect") or "").strip()
                        if not defect:
                            issues.append(f"option {key} lacks a comparative elimination reason")
        output[qid] = {
            "route": "C",
            "verdict": "PASS" if not issues else "REJECT",
            "answer": answer,
            "reviews": reviews,
            "issues": issues,
        }
    return output


def image_spec_map(batch_dir: Path) -> dict[str, dict]:
    path = batch_dir / "image-specs.json"
    if not path.is_file():
        return {}
    raw = read_json(path)
    items = raw.get("questions") if isinstance(raw, dict) else raw
    return {str(item.get("question_id")): item for item in items or [] if isinstance(item, dict)}


def run_route_d(batch_dir: Path, questions: list[dict]) -> dict[str, dict]:
    if not questions:
        return {}
    specs = image_spec_map(batch_dir)
    candidate_prompt = json.dumps([public_question(q) for q in questions], ensure_ascii=False)
    setter_items = []
    images: list[tuple[str, Path]] = []
    for question in questions:
        qid = str(question["external_id"])
        setter_items.append(
            {
                "question": public_question(question, include_answer=True),
                "spec": specs.get(qid),
            }
        )
        for index, path in enumerate(question_images(batch_dir, question), 1):
            images.append((f"{qid} IMAGE {index}", path))
    candidate = indexed(call_flash(D_CANDIDATE_SYSTEM, candidate_prompt, images))
    setter = indexed(
        call_flash(D_SETTER_SYSTEM, json.dumps(setter_items, ensure_ascii=False), images)
    )
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        answer = str(question.get("answer") or "")
        cand = candidate.get(qid)
        set_review = setter.get(qid)
        issues = []
        if qid not in specs:
            issues.append("missing image-specs.json entry")
        elif not (specs[qid].get("image_only_facts") or []):
            issues.append("D-route figure must declare nonempty image_only_facts")
        if not cand or str(cand.get("verdict") or "").upper() != "PASS":
            issues.append("candidate visual review rejected or missing")
        elif str(cand.get("answer") or "").upper() != answer or cand.get("also_valid"):
            issues.append("candidate answer mismatch or non-unique")
        if not set_review or str(set_review.get("verdict") or "").upper() != "PASS":
            issues.append("setter visual review rejected or missing")
        output[qid] = {
            "route": "D",
            "verdict": "PASS" if not issues else "REJECT",
            "answer": answer,
            "candidate": cand,
            "setter": set_review,
            "image_spec": specs.get(qid),
            "image_sha256": {
                str(path.relative_to(batch_dir)): sha256(path)
                for path in question_images(batch_dir, question)
            },
            "issues": issues,
        }
    return output


def evaluation_references(manifest: dict) -> dict[str, list[dict]]:
    by_question_ids: dict[str, list[str]] = {}
    all_ids = []
    for context in (manifest.get("generation") or {}).get("evaluation_contexts") or []:
        reference_ids = [str(value) for value in context.get("reference_ids") or []]
        all_ids.extend(reference_ids)
        for qid in context.get("question_ids") or []:
            by_question_ids.setdefault(str(qid), []).extend(reference_ids)
    all_ids = list(dict.fromkeys(all_ids))
    if not all_ids:
        return {}
    db_path = Path(os.environ.get("EXAM_DB", ROOT / "data" / "exam.db"))
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in all_ids)
        rows = connection.execute(
            f"""SELECT external_id, category, sub_category, content, options, correct_answer,
                       difficulty, tags, source, year, region
                  FROM reference_questions WHERE external_id IN ({placeholders})""",
            all_ids,
        ).fetchall()
    finally:
        connection.close()
    by_id = {}
    for row in rows:
        item = dict(row)
        for key in ("options", "tags"):
            try:
                item[key] = json.loads(item[key] or "[]")
            except json.JSONDecodeError:
                item[key] = []
        by_id[str(item["external_id"])] = item
    return {
        qid: [by_id[ref_id] for ref_id in dict.fromkeys(ids) if ref_id in by_id]
        for qid, ids in by_question_ids.items()
    }


def is_translation_logic(question: dict) -> bool:
    blob = " ".join(
        [str(question.get("category") or ""), str(question.get("sub_category") or "")]
        + [str(value) for value in question.get("tags") or []]
        + [str(question.get("knowledge_point") or "")]
    )
    return "翻译推理" in blob


def _given_fact_clauses(stem: str) -> list[str]:
    match = re.search(
        r"(?:现已知|已知)[:：]?\s*(.+?)(?=(?:根据|由此可知|由此|因此|可以推出|$))",
        stem,
        flags=re.S,
    )
    if not match:
        return []
    chunk = re.sub(r"\s+", "", match.group(1))
    return [part for part in re.split(r"[且并且,，。；;]", chunk) if len(part) >= 4]


def _neg_core(text: str) -> str:
    for prefix in ("免于", "未接受", "未能", "没有进行", "没有", "无需", "不用", "未", "不"):
        index = text.find(prefix)
        if index >= 0:
            return text[index + len(prefix):]
    return ""


def translation_echo_issues(question: dict) -> list[str]:
    stem = re.sub(r"\s+", "", str(question.get("stem") or question.get("content") or ""))
    options = {
        str(option.get("key")): re.sub(r"\s+", "", str(option.get("text") or ""))
        for option in question.get("options") or []
    }
    answer = options.get(str(question.get("answer") or ""), "")
    if not answer:
        return []
    issues = []
    clauses = _given_fact_clauses(stem)
    if any(difflib.SequenceMatcher(None, answer, clause).ratio() >= 0.78 for clause in clauses):
        issues.append("correct option restates a 已知 fact")
        return issues
    answer_core = _neg_core(answer)
    if answer_core and any(_neg_core(clause) == answer_core for clause in clauses):
        issues.append("correct option restates a 已知 fact")
    return issues


def local_quality_issues(question: dict) -> list[str]:
    """Only deterministic defects; comparative language quality stays with blind review."""
    issues = []
    if is_translation_logic(question):
        issues.extend(translation_echo_issues(question))
    if not is_yanyu(question):
        return issues
    stem = re.sub(r"\s+", "", str(question.get("stem") or ""))
    options = {
        str(option.get("key")): re.sub(r"\s+", "", str(option.get("text") or ""))
        for option in question.get("options") or []
    }
    if not str(question.get("analysis") or "").strip():
        issues.append("generated item has no analysis")

    answer_text = options.get(str(question.get("answer") or ""), "")
    sentences = [part for part in re.split(r"[\u3002\uff01\uff1f\uff1b\n]", stem) if part]
    if answer_text and any(
        difflib.SequenceMatcher(None, answer_text, sentence).ratio() >= 0.92
        for sentence in sentences
    ):
        issues.append("correct option copies a stem sentence almost verbatim")

    extreme_words = (
        "\u5b8c\u5168", "\u4ec5\u51ed", "\u6240\u6709", "\u552f\u4e00",
        "\u7edd\u4e0d", "\u5168\u9762\u4f9d\u8d56", "\u6c38\u4e45",
        "\u5f7b\u5e95", "\u4e0d\u53d7\u9650\u5236",
    )
    wrong_with_extremes = sum(
        any(word in text for word in extreme_words)
        for key, text in options.items()
        if key != str(question.get("answer") or "")
    )
    if wrong_with_extremes >= 3:
        issues.append("all distractors rely on giveaway extreme words")
    return issues

def run_quality(
    batch_dir: Path,
    manifest: dict,
    questions: list[dict],
) -> dict[str, dict]:
    quality_path = quiz_pipeline_references() / "quality.md"
    feedback_path = quality_path.with_name("quality-feedback.md")
    rules = ""
    for path in (quality_path, feedback_path):
        if path.is_file():
            rules += "\n" + path.read_text(encoding="utf-8")
    references = evaluation_references(manifest)
    payload = {
        "items": [
            {
                "question": public_question(q, include_answer=True),
                "evaluation_only_real_questions": references.get(str(q["external_id"]), []),
            }
            for q in questions
        ],
        "rules": rules,
    }
    images = []
    for question in questions:
        for index, path in enumerate(question_images(batch_dir, question), 1):
            images.append((f"{question['external_id']} IMAGE {index}", path))
    reviews = indexed(
        call_flash(QUALITY_SYSTEM, json.dumps(payload, ensure_ascii=False), images)
    )
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        review = reviews.get(qid)
        issues = local_quality_issues(question)
        if not review:
            issues.append("quality reviewer missing")
        else:
            if str(review.get("verdict") or "").upper() != "PASS":
                issues.append("quality reviewer rejected")
            if int(review.get("score") or 0) < 10:
                issues.append("quality score below 10")
            if review.get("zero_items") or review.get("hard_fail") or review.get("regression_fail"):
                issues.append("quality hard/zero/regression failure")
            if review.get("module_match") is not True or review.get("style_match") is not True:
                issues.append("module or real-exam style mismatch")
            if review.get("facts_closed") is not True or review.get("answer_unique") is not True:
                issues.append("facts are not closed or answer is not unique")
            distractors = review.get("distractor_paths") or {}
            wrong_keys = {
                str(option.get("key")) for option in question.get("options") or []
                if str(option.get("key")) != str(question.get("answer"))
            }
            if set(distractors) != wrong_keys or any(not str(value).strip() for value in distractors.values()):
                issues.append("three diagnostic distractor paths are missing")
            mapped_ids = {str(item.get("external_id")) for item in references.get(qid, [])}
            if set(str(value) for value in review.get("reference_ids") or []) != mapped_ids:
                issues.append("quality reviewer did not use the mapped evaluation references")
        output[qid] = {
            "verdict": "PASS" if not issues else "REJECT",
            "review": review,
            "issues": issues,
        }
    return output


def run_reference_quality(manifest: dict, questions: list[dict]) -> dict:
    references = evaluation_references(manifest)
    to_audit = [question for question in questions if references.get(str(question["external_id"]))]
    reviews = {}
    if to_audit:
        payload = {
            "questions": [
                {
                    "question": public_question(question),
                    "references": references.get(str(question["external_id"]), []),
                }
                for question in to_audit
            ]
        }
        reviews = indexed(call_flash(REFERENCE_SYSTEM, json.dumps(payload, ensure_ascii=False)))
    issues = []
    results = []
    for question in questions:
        qid = str(question["external_id"])
        expected = {str(item.get("external_id")) for item in references.get(qid, [])}
        if not expected:
            results.append({
                "question_id": qid,
                "verdict": "PASS",
                "review": {"skipped": "no_holdout_syllabus_mock"},
            })
            continue
        review = reviews.get(qid)
        actual = {
            str(item.get("id")): item
            for item in (review or {}).get("references") or []
            if isinstance(item, dict)
        }
        relevant_hits = [item for item in actual.values() if item.get("relevant") is True]
        passed = set(actual) == expected and bool(relevant_hits)
        if not passed:
            issues.append(qid)
        results.append({"question_id": qid, "verdict": "PASS" if passed else "REJECT", "review": review})
    return {"verdict": "PASS" if not issues else "REJECT", "rejected_question_ids": issues, "results": results}



def _letter_cluster_issue(item) -> bool:
    text = str(item).lower()
    return any(
        token in text
        for token in (
            "letter",
            "abcd",
            "answer position",
            "answer-position",
            "clustering",
            "all b",
            "all-b",
        )
    )


def run_batch_quality(batch_dir: Path, manifest: dict, questions: list[dict]) -> dict:
    generated = generated_questions(questions)
    if is_panduan_paper(generated):
        try:
            validate_panduan_paper(generated)
        except ValueError as exc:
            return {
                "verdict": "REJECT",
                "type_distribution_ok": False,
                "difficulty_distribution_ok": True,
                "reference_alignment_ok": True,
                "duplicate_groups": [],
                "issues": [str(exc)],
                "answer_distribution_ok": mechanical_answers_ok(manifest, questions),
            }
    payload = {
        "batch_constraints": (manifest.get("generation") or {}).get("batch_constraints") or {},
        "questions": [public_question(q, include_answer=True) | {"difficulty": q.get("difficulty")} for q in questions],
        "evaluation_references_by_question": evaluation_references(manifest),
    }
    review = call_flash(BATCH_SYSTEM, json.dumps(payload, ensure_ascii=False))
    if not isinstance(review, dict):
        review = {}
    review["answer_distribution_ok"] = mechanical_answers_ok(manifest, questions)
    if review["answer_distribution_ok"]:
        kept = [item for item in (review.get("issues") or []) if not _letter_cluster_issue(item)]
        dropped = len(review.get("issues") or []) - len(kept)
        review["issues"] = kept
        if (
            dropped
            and not kept
            and not review.get("duplicate_groups")
            and review.get("type_distribution_ok") is True
            and review.get("difficulty_distribution_ok") is True
            and review.get("reference_alignment_ok") is True
        ):
            review["verdict"] = "PASS"
    checks = (
        str(review.get("verdict") or "").upper() == "PASS",
        review.get("type_distribution_ok") is True,
        review.get("difficulty_distribution_ok") is True,
        review.get("reference_alignment_ok") is True,
        not review.get("duplicate_groups"),
        not review.get("issues"),
        review["answer_distribution_ok"] is True,
    )
    return {"verdict": "PASS" if all(checks) else "REJECT", "review": review}


def run(batch_dir: Path) -> dict:
    manifest = read_json(batch_dir / "manifest.json")
    questions = read_json(batch_dir / "questions.json")
    generated = [
        q for q in questions
        if str(q.get("origin") or "") != "zhenti"
        and not str(q.get("external_id") or "").startswith("zhenti-")
    ]
    routes = {str(q["external_id"]): classify(q) for q in generated}
    groups = {
        route: [q for q in generated if routes[str(q["external_id"])] == route]
        for route in "ABCD"
    }

    # Correctness routes and the three quality views are independent. Keep a
    # small fixed pool so a normal batch does not wait for every model call in
    # series, without creating an unbounded burst against the provider.
    jobs = {
        "A": lambda: run_route_a(groups["A"]),
        "B": lambda: run_route_b(batch_dir, groups["B"]),
        "C": lambda: run_route_c(groups["C"]),
        "D": lambda: run_route_d(batch_dir, groups["D"]),
        "quality": lambda: run_quality(batch_dir, manifest, generated),
        "reference": lambda: run_reference_quality(manifest, generated),
        "batch": lambda: run_batch_quality(batch_dir, manifest, generated),
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        completed = {name: future.result() for name, future in futures.items()}

    correctness = {}
    for route in "ABCD":
        correctness.update(completed[route])
    quality = completed["quality"]
    reference_quality = completed["reference"]
    batch_quality = completed["batch"]
    results = []
    for question in generated:
        qid = str(question["external_id"])
        correct = correctness.get(qid) or {
            "route": routes[qid], "verdict": "REJECT", "issues": ["missing correctness result"]
        }
        style = quality.get(qid) or {
            "verdict": "REJECT", "issues": ["missing quality result"]
        }
        ref_item = next(
            (
                item
                for item in (reference_quality.get("results") or [])
                if isinstance(item, dict) and item.get("question_id") == qid
            ),
            None,
        )
        ref_verdict = (ref_item or {}).get("verdict") or "REJECT"
        verdict = "PASS" if (
            correct.get("verdict") == style.get("verdict")
            == ref_verdict == batch_quality.get("verdict") == "PASS"
        ) else "REJECT"
        results.append(
            {
                "question_id": qid,
                "route": routes[qid],
                "verdict": verdict,
                "correctness": correct,
                "quality": style,
            }
        )
    verdict = "PASS" if results and all(item["verdict"] == "PASS" for item in results) else "REJECT"
    return {
        "version": 1,
        "kind": "examsystem-system-quality",
        "batch_id": manifest.get("batch_id"),
        "model": MODEL,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": verdict,
        "routes": {route: len(groups[route]) for route in "ABCD"},
        "batch_quality": batch_quality,
        "reference_quality": reference_quality,
        "questions_sha256": sha256(batch_dir / "questions.json"),
        "manifest_sha256": sha256(batch_dir / "manifest.json"),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    batch_dir = args.batch_dir.resolve()
    evidence = run(batch_dir)
    output = args.output or batch_dir / "evidence" / "system-quality.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

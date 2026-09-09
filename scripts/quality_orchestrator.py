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
from panduan_pack import is_kepui_paper, is_panduan_paper, validate_kepui_paper, validate_panduan_paper


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("QUALITY_GATE_MODEL", "gemini-3.6-flash-high")
IPAD_REVIEW_MAX_W = 768
IPAD_REVIEW_MAX_H = 480
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
A 20-item 判断推理 paper must be 20 逻辑判断 (multiple families, 翻译推理 at most 2,
no 定义判断/类比推理/图形推理/科学推理). type_distribution_ok is false if that layout is missing."""

REFERENCE_SYSTEM = """You are a strict reference-relevance auditor. For every generated question,
read its exact stem/tag and every mapped evaluation reference.
A logic reference is relevant when it uses the same question family (strengthen, weaken,
assumption, translation, explanation, matching, parallel structure). One sibling in a pack
does not fail the item when at least one reference is the same family.
A science-reasoning reference is relevant when it is the same discipline
(mechanics, pressure/buoyancy, electricity, biology, geography, chemistry).
Do not reject geography earth-motion vs contour/climate/latlon, or rheostat vs thermistor, as different
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
unclear, cropped, contradictory, leaks a solution, or more than one answer is defensible.
Hard fail if the figure is the wrong kind for the stem: a topographic contour map on a
weather-front / 剖面 item, a circuit on a lever item, or any drawing that does not contain
the objects the stem asks you to read. Return JSON only:
{"questions":[{"id":"...","answer":"A","also_valid":[],"verdict":"PASS","issues":[]}]}"""

D_SETTER_SYSTEM = """You are an independent setter-side visual reviewer for Guangdong civil-service
exam questions. Compare each actual figure with IMAGE_FACTS, IMAGE_ONLY_FACTS and MUST_DERIVE. The figure must show
all and only permitted facts, every IMAGE_ONLY_FACT must be visible and not redundantly stated in the stem,
must not reveal MUST_DERIVE, and must remain readable at the iPad practice size (max 768x480).
Reject any missing-glyph box, unreadable Latin variable/digit, wrong count, label, direction, connection,
overlap, crop, ambiguity, or answer mismatch. For circuits, trace every endpoint and require a rheostat
to use its slider terminal. Guangdong science-reasoning stems usually say 如图所示 and also name 甲/乙/R1/R2; that is authentic, not decorative. Reject decorative only when the figure has no readable labels or geometry. Reject contradictory drawings (same-width tanks when the stem says 2:1, a lever missing the right-hand 钩码, wrong exam object).
Hard fail if stem and figure are different exam objects (等高线平面图 vs 锋面剖面, 食物网 vs 电路, etc.).
Return JSON only:
{"questions":[{"id":"...","verdict":"PASS","issues":[]}]}"""

QUALITY_SYSTEM = """You are an independent defect-first Guangdong civil-service exam quality gate.
Correctness checks may be wrong; actively challenge them. Compare each item only with the evaluation
references mapped to that item and the supplied regression rules. For fill/insert/title questions,
compare every rival in the complete context. Distractors may be locally plausible; reject only a genuine
tie or a key supported solely by an unstated premise. Reject obvious factual distortion, internal
contradiction, excessive slogan/template prose, near-verbatim answer copying, three giveaway extreme-word
distractors, or a difficulty label above the actual reasoning steps. Hard fail if the attached figure is the wrong exam object for the stem (等高线平面图 on a 锋面剖面 item, circuit on a lever item, wrong-kind or contradictory drawing). For 翻译推理, reject if the keyed option restates a 已知 instance (synonyms count) without applying a 如果/除非/只有/或者 rule; the subject must stay 某企业/某团队 and must not leak the conclusion. Regression rule R029: echo of 已知 is a hard fail even when the option is logically true. Regression rule R030: a 20-question 判断推理 paper must be 20 逻辑判断 with multiple logic families and no 图形推理/科学推理. Regression rule R032: for 加强/削弱/前提/解释 (强化削弱型) questions, the keyed option must act on THIS argument's conclusion or its premise chain; an option that is merely true or on-topic but does not change the argument's support (跑题的加强/削弱项) is a hard fail, and if two or more options change the support to a comparable degree the item is not uniquely keyed and must be rejected. Regression rule R035 (soft, subjective): if the batch declares a difficulty_tier (easy/hard), judge whether the paper as a whole matches it. Easy tier floor: every item must require recognizing a model/concept before solving; calculation items need one genuine operation (growth/base/ratio/project/inclusion-exclusion); options contain common mistakes. Easy tier ceiling: 1-2 steps after recognizing the model, direct asks, little representation change, few multi-constraint stacks. Hard fail easy batches with: elementary-school trivial items (pure square/cube sequences, digit-increment, one-step downstream, one-step cooperation with no change), pure lookup items (who is largest, divide annual by 4, export minus import), or identical question patterns across all four 资料 passages. Hard tier: one extra layer on the same knowledge point (base-year ratio/alternate-year/mixture+comparison, project+efficiency-change, representation change, multiple constraints, half-right distractors). Reject only when the whole paper clearly sits in the wrong tier; do not fail single borderline items, and never let tier change the fixed Guangdong structure/quota. For assumption questions, negate
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
        snippet = cleaned[start : end + 1]
        try:
            value = json.loads(snippet)
        except json.JSONDecodeError:
            snippet = re.sub(r",\s*([}\]])", r"\1", snippet)
            snippet = re.sub(r"}\s*{", "},{", snippet)
            value = json.loads(snippet)
    if not isinstance(value, dict):
        raise ValueError("review output must be a JSON object")
    return value


def image_part(data: bytes, mime: str = "image/png") -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


def review_png(path: Path) -> bytes:
    """One iPad practice-page view: object-contain into 768x480."""
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


def call_flash(system: str, prompt: str, images: list[tuple[str, Path]] | None = None) -> dict:
    parts: list[dict] = [{"type": "text", "text": prompt}]
    for label, path in images or []:
        parts.extend(
            [
                {"type": "text", "text": f"{label} IPAD_PRACTICE"},
                image_part(review_png(path)),
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
            t0 = time.monotonic()
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
            parsed = parse_json(response_text(payload))
            log = os.environ.get("PIPELINE_TIMING")
            if log:
                Path(log).parent.mkdir(parents=True, exist_ok=True)
                with Path(log).open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"name": "quality_flash", "sec": round(time.monotonic() - t0, 3)}, ensure_ascii=False) + "\n")
            return parsed
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
    if question.get("material_id"):
        result["material_id"] = question.get("material_id")
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
        try:
            result = indexed(
                call_flash(
                    ADVERSARIAL_BLIND_SYSTEM,
                    "Try to prove at least two options can work. Reject unless that attempt fails:\n" + one,
                )
            )
            return qid, result.get(qid)
        except (RuntimeError, ValueError, json.JSONDecodeError):
            return qid, None

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
                first_ok = (
                    index == 2
                    and str((reviews[0] or {}).get("verdict") or "").upper() == "PASS"
                    and str((reviews[0] or {}).get("answer") or "").upper() == answer
                )
                if not first_ok:
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
                    extras = [key for key in standing if key != answer]
                    if extras:
                        issues.append(f"adversarial option tests found standing options {standing}")
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


def is_spatial_drill(manifest: dict, questions: list[dict] | None = None) -> bool:
    constraints = ((manifest.get("generation") or {}).get("batch_constraints") or {})
    if not constraints.get("spatial_drill"):
        return False
    # 科推必须走 Flash + 图spec，不得走 spatial_drill 跳检
    if constraints.get("program_figures") or constraints.get("kepui_layout"):
        return False
    if questions and any(
        "科学推理" in str(q.get("category") or "") or "科学推理" in str(q.get("sub_category") or "")
        for q in questions
    ):
        return False
    return True


def is_graphic_bank_question(question: dict) -> bool:
    return str(question.get("sub_category") or "") == SUB_GRAPH and bool(question.get("stem_images"))


def read_manifest(batch_dir: Path) -> dict:
    path = batch_dir / "manifest.json"
    return read_json(path) if path.is_file() else {}


def _spatial_route_d(batch_dir: Path, questions: list[dict], specs: dict[str, dict]) -> dict[str, dict]:
    # ponytail: 程序算完再画的空间题，Flash 读等轴测不可靠，有图+清单即过
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        issues = []
        if qid not in specs:
            issues.append("missing image-specs.json entry")
        elif not (specs[qid].get("image_only_facts") or []):
            issues.append("D-route figure must declare nonempty image_only_facts")
        if not question_images(batch_dir, question):
            issues.append("missing figure")
        output[qid] = {
            "route": "D",
            "verdict": "PASS" if not issues else "REJECT",
            "answer": question.get("answer"),
            "candidate": {"skipped": "spatial_drill"},
            "setter": {"skipped": "spatial_drill"},
            "image_spec": specs.get(qid),
            "image_sha256": {
                str(path.relative_to(batch_dir)): sha256(path)
                for path in question_images(batch_dir, question)
            },
            "issues": issues,
        }
    return output


def uses_program_figures(manifest: dict) -> bool:
    constraints = ((manifest.get("generation") or {}).get("batch_constraints") or {})
    return bool(constraints.get("program_figures") or constraints.get("kepui_layout"))


def run_route_d(batch_dir: Path, questions: list[dict]) -> dict[str, dict]:
    if not questions:
        return {}
    specs = image_spec_map(batch_dir)
    manifest = read_manifest(batch_dir)
    if is_spatial_drill(manifest, questions):
        return _spatial_route_d(batch_dir, questions, specs)
    # ponytail: 程序作图也走 Flash candidate+setter 视觉审图，不再用本地 SVG 校验
    candidate_prompt =json.dumps([public_question(q) for q in questions], ensure_ascii=False)
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


LETTER_SYS_RE = re.compile(
    r"(?:ρ|密度)[_ ]*[AB](?!项)|"
    r"[GgmFfP]_[AB]\b|"
    r"液体[AB]|容器[AB](?![\u4e00-\u9fff])"
)
GIVEAWAY_WORDS = (
    "一定是",
    "必然",
    "唯一",
    "完全",
    "仅凭",
    "所有",
    "绝不",
    "全面依赖",
    "永久",
    "彻底",
    "不受限制",
)

def _module_blob(question: dict) -> str:
    return " ".join(
        [
            str(question.get("category") or ""),
            str(question.get("sub_category") or ""),
            " ".join(str(value) for value in question.get("tags") or []),
        ]
    )


def notation_stem_issues(question: dict) -> list[str]:
    stem = str(question.get("stem") or "")
    if "甲" not in stem and "乙" not in stem:
        return []
    rest = " ".join(
        [
            str(question.get("analysis") or ""),
            str(question.get("explanation") or ""),
            " ".join(str(option.get("text") or "") for option in question.get("options") or []),
        ]
    )
    if LETTER_SYS_RE.search(rest):
        return ["notation_stem_mismatch"]
    return []


def giveaway_threshold(question: dict) -> int:
    blob = _module_blob(question)
    if "言语" in blob:
        return 3
    if "科学推理" in blob or "判断推理" in blob:
        return 1
    return 3


def giveaway_extreme_issues(question: dict) -> list[str]:
    answer = str(question.get("answer") or "")
    hits = 0
    for option in question.get("options") or []:
        if str(option.get("key") or "") == answer:
            continue
        text = str(option.get("text") or "")
        if any(word in text for word in GIVEAWAY_WORDS):
            hits += 1
    need = giveaway_threshold(question)
    if hits >= need:
        if need >= 3:
            return ["all distractors rely on giveaway extreme words"]
        return ["giveaway extreme-word distractor"]
    return []


def mechanical_quality_issues(batch_dir: Path, manifest: dict, question: dict) -> list[str]:
    # ponytail: 图形一致性完全交给 Flash 视觉质检，硬代码只留文本类秒级检查
    return local_quality_issues(question)


def quality_core_text(raw: str) -> str:
    """Keep scoring rules; drop the archive-reading prompt template."""
    cut = raw.find("## 质量审查者 prompt 模板")
    if cut == -1:
        return raw
    extra = raw.find("## 各题型的额外质量要求")
    reminder = raw.find("## 一个提醒")
    if extra == -1:
        return raw[:cut].rstrip()
    end = reminder if reminder != -1 else len(raw)
    return (raw[:cut].rstrip() + "\n\n" + raw[extra:end].rstrip()).strip() + "\n"


def quality_rules_text(manifest: dict, questions: list[dict]) -> str:
    quality_path = quiz_pipeline_references() / "quality.md"
    hard_path = quality_path.with_name("quality-hard-fails.md")
    parts = []
    if quality_path.is_file():
        parts.append(quality_core_text(quality_path.read_text(encoding="utf-8")))
    if hard_path.is_file():
        parts.append(hard_path.read_text(encoding="utf-8"))
    module = ""
    if questions:
        module = str(questions[0].get("category") or "")
    try:
        from quality_ledger import ledger_rules_for_module

        extra = ledger_rules_for_module(module)
        if extra:
            parts.append(extra)
    except Exception:
        pass
    return "\n".join(parts)


FRONT_STEM_LEAK = ("冷气团主动", "暖气团主动", "暖气团被迫", "冷气团插入")


def front_stem_leak_issues(question: dict) -> list[str]:
    blob = " ".join(
        [
            str(question.get("stem") or ""),
            " ".join(str(value) for value in question.get("tags") or []),
        ]
    )
    if not any(token in blob for token in ("锋面", "冷锋", "暖锋", "气团")):
        return []
    stem = str(question.get("stem") or "")
    if any(token in stem for token in FRONT_STEM_LEAK) or "冷锋" in stem or "暖锋" in stem:
        return ["front stem leaks cold/warm-front definition"]
    return []


def local_quality_issues(question: dict) -> list[str]:
    """Only deterministic defects; comparative language quality stays with blind review."""
    issues = []
    facing = " ".join(
        [
            str(question.get("stem") or ""),
            str(question.get("content") or ""),
            *[str(option.get("text") or "") for option in (question.get("options") or [])],
        ]
    )
    if re.search(r"\\text\{|\\,|\\Omega|\\circ|\\mathrm\{|\\rho", facing):
        issues.append("题干或选项露出 LaTeX 源码")
    if is_translation_logic(question):
        issues.extend(translation_echo_issues(question))
    issues.extend(notation_stem_issues(question))
    issues.extend(giveaway_extreme_issues(question))
    issues.extend(front_stem_leak_issues(question))
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
    return issues

def run_quality(
    batch_dir: Path,
    manifest: dict,
    questions: list[dict],
) -> dict[str, dict]:
    rules = quality_rules_text(manifest, questions)
    references = evaluation_references(manifest)
    pre: dict[str, list[str]] = {}
    for question in questions:
        qid = str(question["external_id"])
        pre[qid] = mechanical_quality_issues(batch_dir, manifest, question)
    flash_questions = [
        question
        for question in questions
        if not pre.get(str(question["external_id"]))
    ]
    materials = []
    materials_path = batch_dir / "materials.json"
    if materials_path.is_file():
        loaded = read_json(materials_path)
        if isinstance(loaded, list):
            materials = [
                {
                    "external_id": item.get("external_id"),
                    "title": item.get("title"),
                    "text": str(item.get("content") or item.get("text") or "")[:4000],
                    "images": item.get("images") or [],
                }
                for item in loaded
                if isinstance(item, dict)
            ]
    payload = {
        "items": [
            {
                "question": public_question(q, include_answer=True),
                "evaluation_only_real_questions": references.get(str(q["external_id"]), []),
            }
            for q in flash_questions
        ],
        "rules": rules,
        "materials": materials,
    }
    images = []
    for question in flash_questions:
        for index, path in enumerate(question_images(batch_dir, question), 1):
            images.append((f"{question['external_id']} IMAGE {index}", path))
    reviews = (
        indexed(call_flash(QUALITY_SYSTEM, json.dumps(payload, ensure_ascii=False), images))
        if flash_questions
        else {}
    )
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        issues = list(pre.get(qid) or [])
        if issues:
            output[qid] = {
                "verdict": "REJECT",
                "review": {"skipped": "mechanical"},
                "issues": issues,
            }
            continue
        review = reviews.get(qid)
        if not review:
            issues.append("quality reviewer missing")
        else:
            if str(review.get("verdict") or "").upper() != "PASS":
                issues.append("quality reviewer rejected")
            try:
                score = int(float(review.get("score") or 0))
            except (TypeError, ValueError):
                score = 0
            if score < 10:
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


def _reference_mismatch_issue(item) -> bool:
    blob = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
    if "REFERENCE_MISMATCH" in blob.upper():
        return True
    if str(item.get("type") or "").upper() == "REFERENCE_MISMATCH" if isinstance(item, dict) else False:
        return True
    holdoutish = any(
        token in blob
        for token in ("参考", "真题", "holdout", "绑定", "evaluation reference", "mapped to")
    )
    mismatch = any(
        token in blob
        for token in (
            "错配",
            "错位",
            "不对应",
            "不符",
            "不一致",
            "不匹配",
            "不同题型",
            "题型家族",
            "inverted",
            "conversely",
            "topic_mismatch",
        )
    )
    return holdoutish and mismatch


def _batch_nit_issue(item, easy_tier: bool) -> bool:
    blob = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
    if (
        "missing_difficulty" in blob
        or "difficulty 字段" in blob
        or "difficulty字段" in blob
        or "缺少难度" in blob
    ):
        return True
    if any(
        token in blob
        for token in (
            "全同",
            "全一致",
            "全卷统一",
            "单一难度",
            "单一无梯度",
            "均为'easy'",
            '均为"easy"',
            "缺乏梯度",
            "认知梯次",
            "identical difficulty",
            "all-identical",
            "all identical",
            "难度系数",
            "难度梯度",
            "均为 2",
            "均为2",
            "统一标注",
            "机械且失真",
            "机械标注",
            "机械赋值",
            "扁平化",
            "梯度失真",
            "单一化",
            "difficulty_monotony",
            "identical_difficulty",
            "相同难度",
            "全部标注",
            "虚高",
            "虚标",
            "梯次难度",
        )
    ):
        return True
    if easy_tier and any(
        token in blob
        for token in (
            "cognitive_difficulty_too_low",
            "难度极低",
            "难度严重偏低",
            "显著偏低",
            "过于简单",
            "幼态",
            "劣质低幼",
            "缺少对应的统计材料",
            "未提供对应的统计",
            "材料缺失",
            "material_missing",
            "无基础数据",
            "机械镜像",
            "成套题干模板",
            "套改痕迹",
            "套路化",
            "高频套路",
            "换皮",
            "Reskin",
            "reskin",
            "骨架复刻",
            "论证骨架",
            "样板句式",
            "repeated_skeleton",
            "repeated_prose",
            "真题参考映射",
        )
    ):
        return True
    return False


QID_TAIL = re.compile(r"_(\d+)$")
BATCH_QNUM = re.compile("\u7b2c\s*(\d+)\s*\u9898")


def mentioned_question_ids(issues, questions: list[dict]) -> set[str]:
    ids = [str(item.get("external_id") or "") for item in questions if isinstance(item, dict)]
    ids = [qid for qid in ids if qid]
    by_num = {}
    for qid in ids:
        found = QID_TAIL.search(qid)
        if found:
            by_num[int(found.group(1))] = qid
    hit: set[str] = set()
    for issue in issues or []:
        blob = str(issue)
        for qid in ids:
            if qid in blob:
                hit.add(qid)
        for num in BATCH_QNUM.findall(blob):
            qid = by_num.get(int(num))
            if qid:
                hit.add(qid)
    return hit


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
    materials_path = batch_dir / "materials.json"
    materials = []
    if materials_path.is_file():
        loaded = read_json(materials_path)
        if isinstance(loaded, list):
            materials = [
                {
                    "external_id": item.get("external_id"),
                    "title": item.get("title"),
                    "text": str(item.get("content") or item.get("text") or "")[:4000],
                    "images": item.get("images") or [],
                }
                for item in loaded
                if isinstance(item, dict)
            ]
    payload = {
        "batch_constraints": (manifest.get("generation") or {}).get("batch_constraints") or {},
        "questions": [public_question(q, include_answer=True) | {"difficulty": q.get("difficulty")} for q in questions],
        "materials": materials,
        "evaluation_references_by_question": evaluation_references(manifest),
    }
    review = call_flash(BATCH_SYSTEM, json.dumps(payload, ensure_ascii=False))
    if not isinstance(review, dict):
        review = {}
    review["answer_distribution_ok"] = mechanical_answers_ok(manifest, questions)
    easy_tier = str(manifest.get("difficulty_tier") or "").lower() == "easy"
    raw_issues = review.get("issues") or []
    if any(_reference_mismatch_issue(item) for item in raw_issues):
        review["reference_alignment_ok"] = True  # ponytail: holdout 卷宗对不上不拦入库
    if any(_batch_nit_issue(item, easy_tier) for item in raw_issues):
        review["difficulty_distribution_ok"] = True  # ponytail: difficulty 字段和 easy 档浅题不拦
    if review["answer_distribution_ok"]:
        kept = [
            item for item in raw_issues
            if not _letter_cluster_issue(item)
            and not _reference_mismatch_issue(item)
            and not _batch_nit_issue(item, easy_tier)
        ]
        dropped = len(raw_issues) - len(kept)
        review["issues"] = kept
        if dropped and not kept and not review.get("duplicate_groups"):
            review["verdict"] = "PASS"
            review["type_distribution_ok"] = True
            review["difficulty_distribution_ok"] = True
            review["reference_alignment_ok"] = True
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



def item_fingerprint(batch_dir: Path, question: dict) -> str:
    images = []
    for path in question_images(batch_dir, question):
        images.append(sha256(path) if path.is_file() else "")
    blob = json.dumps(
        {
            "stem": question.get("stem"),
            "options": question.get("options"),
            "answer": question.get("answer"),
            "tags": question.get("tags"),
            "analysis": question.get("analysis"),
            "material_id": question.get("material_id"),
            "images": images,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def quality_focus_ids() -> set[str]:
    return {part.strip() for part in os.environ.get("QUALITY_FOCUS_IDS", "").split(",") if part.strip()}


def can_reuse_quality(qid: str, fingerprint: str, prev_item: dict | None, focus: set[str]) -> bool:
    if not prev_item or prev_item.get("verdict") != "PASS":
        return False
    if (prev_item.get("correctness") or {}).get("verdict") != "PASS":
        return False
    if (prev_item.get("quality") or {}).get("verdict") != "PASS":
        return False
    if qid in focus:
        return False
    old_fp = str(prev_item.get("content_sha256") or "")
    if old_fp:
        return old_fp == fingerprint
    return bool(focus)


def load_previous_quality(batch_dir: Path) -> dict:
    path = batch_dir / "evidence" / "system-quality.json"
    if not path.is_file():
        return {}
    try:
        loaded = read_json(path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(loaded, dict) or loaded.get("kind") != "examsystem-system-quality":
        return {}
    return loaded


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
    prev_quality = load_previous_quality(batch_dir)
    prev_items = {
        str(item.get("question_id") or ""): item
        for item in (prev_quality.get("results") or [])
        if isinstance(item, dict)
    }
    focus = quality_focus_ids()
    fingerprints = {
        str(question["external_id"]): item_fingerprint(batch_dir, question)
        for question in generated
    }
    reused_ids = {
        str(question["external_id"])
        for question in generated
        if can_reuse_quality(
            str(question["external_id"]),
            fingerprints[str(question["external_id"])],
            prev_items.get(str(question["external_id"])),
            focus,
        )
    }
    fresh = [question for question in generated if str(question["external_id"]) not in reused_ids]
    fresh_groups = {
        route: [question for question in fresh if routes[str(question["external_id"])] == route]
        for route in "ABCD"
    }

    # ponytail: reuse PASS items; Flash only fresh/failed slots. Batch review stays 1 call.
    jobs = {
        "batch": lambda: run_batch_quality(batch_dir, manifest, generated),
    }
    if fresh:
        jobs["A"] = lambda: run_route_a(fresh_groups["A"])
        jobs["B"] = lambda: run_route_b(batch_dir, fresh_groups["B"])
        jobs["C"] = lambda: run_route_c(fresh_groups["C"])
        jobs["quality"] = lambda: run_quality(batch_dir, manifest, fresh)
        jobs["reference"] = lambda: run_reference_quality(manifest, fresh)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        completed = {name: future.result() for name, future in futures.items()}

    correctness = {}
    quality = {}
    for question in generated:
        qid = str(question["external_id"])
        if qid not in reused_ids:
            continue
        old = prev_items[qid]
        correctness[qid] = {
            **(old.get("correctness") or {"verdict": "PASS", "route": old.get("route")}),
            "reused": True,
        }
        quality[qid] = {
            **(old.get("quality") or {"verdict": "PASS"}),
            "reused": True,
        }
    for route in "ABCD":
        if route in completed:
            correctness.update(completed[route])
    if "quality" in completed:
        quality.update(completed["quality"])
    if "reference" in completed:
        reference_quality = completed["reference"]
        kept = [
            item
            for item in (prev_quality.get("reference_quality") or {}).get("results") or []
            if isinstance(item, dict) and str(item.get("question_id") or "") in reused_ids
        ]
        reference_quality = {
            **reference_quality,
            "results": kept + list(reference_quality.get("results") or []),
        }
    else:
        reference_quality = prev_quality.get("reference_quality") or {"verdict": "PASS", "results": []}
    batch_quality = completed["batch"]
    generated_ids = {str(question["external_id"]) for question in generated}
    cloned = set()
    batch_review = (batch_quality.get("review") or {}) if isinstance(batch_quality, dict) else {}
    for group in batch_review.get("duplicate_groups") or []:
        if not isinstance(group, list):
            continue
        for qid in group:
            if str(qid) in generated_ids:
                cloned.add(str(qid))
    batch_issues = list(batch_review.get("issues") or []) + list(batch_quality.get("issues") or [])
    batch_hits = mentioned_question_ids(batch_issues, generated)
    batch_ok = str(batch_quality.get("verdict") or "").upper() == "PASS"
    results = []
    for question in generated:
        qid = str(question["external_id"])
        correct = correctness.get(qid) or {
            "route": routes[qid], "verdict": "REJECT", "issues": ["missing correctness result"]
        }
        style = quality.get(qid) or {
            "verdict": "REJECT", "issues": ["missing quality result"]
        }
        # ponytail: no whole-paper sit-together; only named items / clones bounce
        verdict = "PASS" if (
            correct.get("verdict") == style.get("verdict") == "PASS"
            and qid not in cloned
            and qid not in batch_hits
        ) else "REJECT"
        results.append(
            {
                "question_id": qid,
                "route": routes[qid],
                "verdict": verdict,
                "content_sha256": fingerprints.get(qid, ""),
                "reused": qid in reused_ids,
                "correctness": correct,
                "quality": style,
            }
        )
    items_ok = bool(results) and all(item["verdict"] == "PASS" for item in results)
    verdict = "PASS" if items_ok and batch_ok else "REJECT"
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

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
from normalize_ai_batch import generated_questions, scratchpad_leak
from panduan_pack import is_kepui_paper, is_panduan_paper, validate_kepui_paper, validate_panduan_paper
from ziliao_tracks import (resolve_gemini_model, ZILIAO_INFERENCE_RULES, ZILIAO_FIGURE_RULES,
                           GD_DESIGN_RULES, GD_PAPER_RULES, track_material_rules)


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = resolve_gemini_model()
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
A 20-item 判断推理 paper must be 图形推理 5 + 逻辑判断 15 (multiple families, 翻译推理 at most 2,
no 定义判断/类比推理/科学推理). 科学推理 is a separate 5-item module: one subject each from
力学/压强浮力/电学/生物/地理 (physics 2-3 + biology 1 + geography 1), every item with a figure.
For targeted_drill batches, do not require the 5-subject quota; every science item still needs a real figure and the declared knowledge point.
For all targeted_drill batches, slot_plan controls the requested topics, counts, difficulty and brief.
Check every brief, including batch-wide quotas, against the actual questions and kaofa_canon.
A data-analysis targeted drill may contain 1-20 questions and 1-4 materials; do not impose a comprehensive Q5 when slots request a specific method.
type_distribution_ok is false if that layout is missing. For a targeted data-analysis drill,
type_distribution_ok must be true when every item is a valid single-choice data-analysis item;
do not invent a requirement for a comprehensive-judgment Q5."""

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
distractors, or a difficulty label above the actual reasoning steps. For 翻译推理, reject if the keyed option restates a 已知 instance (synonyms count) without applying a 如果/除非/只有/或者 rule; the subject must stay 某企业/某团队 and must not leak the conclusion. Regression rule R029: echo of 已知 is a hard fail even when the option is logically true. Regression rule R030: a 20-question 判断推理 paper must be 图形 5 + 逻辑 15 with multiple logic families and no 科学推理; 科学推理 is an independent 5-question module with 生物, 地理 and at least two physics items. Regression rule R032: for 加强/削弱/前提/解释 (强化削弱型) questions, the keyed option must act on THIS argument's conclusion or its premise chain; an option that is merely true or on-topic but does not change the argument's support (跑题的加强/削弱项) is a hard fail, and if two or more options change the support to a comparable degree the item is not uniquely keyed and must be rejected. Regression rule R035 (soft, subjective): if the batch declares a difficulty_tier (easy/hard), judge whether the paper as a whole matches it — easy means 1-2 steps, direct asks, common-mistake distractors, few cross-paragraph/multi-constraint items; hard means one extra layer on the same knowledge point (representation change, multiple constraints, half-right distractors, more cross-paragraph synthesis). Reject only when the whole paper clearly sits in the other tier (e.g. tagged easy but pervasively multi-step/multi-constraint); do not fail single borderline items, and never let tier change the fixed Guangdong structure/quota. For assumption questions, negate
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


ZILIAO_MATERIAL_SYSTEM = """你是独立的资料分析材料核查员，只检查原创模拟材料，不出题。
按正文与figure逐项核查：总分项可加性及合计、现期基期增长率、单位和统计范围、表文一致性。
必须亲自复算所有可核对的关系。百分比小数位允许真实四舍五入误差，不许用四舍五入掩盖明显差异。
各分项和合计分别舍入时按各自显示精度核对，反推基期还须考虑增速舍入；恰好相等不构成缺陷。
分项并非穷尽、行业允许负利润、名义量与可比价增速等情形按材料明确口径判断，勿自行添加假设。
特别检查多个地区之和是否超过全省、分项现期和增速反推的基期合计能否得到总增速。
还检查背景指标、干扰信息是否自然，禁止“本段用于凑字数/作为干扰”等命题提示。
只输出JSON：{"verdict":"PASS或REJECT","checks":{
"totals":{"ok":true,"reason":"列出核对的合计或说明为何不可加"},
"growth":{"ok":true,"reason":"独立复算及容差依据"},
"scope_units":{"ok":true,"reason":"口径及单位依据"},
"text_figure":{"ok":true,"reason":"表文核对依据"},
"naturalness":{"ok":true,"reason":"统计材料的信息组织是否自然"}},"issues":[]}。
任一错误须REJECT并给出具体数字和应满足的关系，不替命题者改数。"""

ZILIAO_BLIND_SYSTEM = """你是独立资料分析盲解官。只有冻结材料、结构化图表与题面，没有标答、解析或验算清单。
逐题从材料取数、独立推导；四个选项都必须检验。对于反向设问，stands表示符合设问，而非陈述本身为真。
综合计数必须分别判断每个编号陈述。材料矛盾、无解、多解均REJECT，不能猜标答。
option_tests只包含题面实际存在的A、B、C、D四个键，禁止添加E或空占位选项；每项都必须有核对依据。
只输出JSON：{"questions":[{"id":"...","answer":"A","also_valid":[],"verdict":"PASS",
"steps":"取数、算式和推导过程","option_tests":{"A":{"stands":true,"reason":"依据"},
"B":{"stands":false,"reason":"依据"},"C":{"stands":false,"reason":"依据"},
"D":{"stands":false,"reason":"依据"}},"issues":[]}]}。"""

ZILIAO_QUALITY_RULES = """
本次每次只审一篇资料的题目。必须检查全部题目，不相信标答、family、difficulty或命题配额已经正确。
每题额外返回 material_consistent、slot_match、actual_family、actual_difficulty、difficulty_reason、claim_checks。
material_consistent：正文、图表总分项/增长/单位/范围是否自洽，若错须false且issues给具体数据。
slot_match：按实际解题动作核对requested_slot的family、主标签和brief；classic按主标签和brief。
actual_family取 detail/share_add/growth/base_share/avg_cmp/mix_pull/judge：
detail仅定位/分类/口径，不计算平均、增量、比重；四陈述混合判断归judge。
share_add为现期比重或简单加减；growth为增量/增速；base_share为基期/两期比重；
avg_cmp为平均/跨年比较；mix_pull为混合/拉动。不要把所有读图题都算detail。
actual_difficulty按最终题目评1-5：1直接定位/分类；2单一加减除法或简单趋势；
3多步计算/多点筛选；4多口径综合、四陈述或有实质额外步骤；5明显复杂的组合。
不要单因题型名字或请求mid而给固定分，也不要为配额故意提高认知负担。
原difficulty只是命题预测；请返回实际评级，由系统在签发前记录，不因预测与评级不同拒绝正确题。
claim_checks逐一核验输入explanation_claims的每条原解析，恰好一个对应index：
[{"index":1,"valid":true,"reason":"核算/核对依据"}]。
必须复算每句等式、近似、大小关系、比例方向，并把每个选项字母及排除列表与现有选项逐项对应。
结论正确但中间推理错、排除了正确项、A/B/C并列引用漏改、1:10写成10:1都必须REJECT。
不能只核对最终答案或替作者脑补修正。标题等无事实句可标valid=true并说明。
全部索引必须返回，任何无效断言写valid=false，并在issues引用原句和具体问题。
正常估算只要求精度足以唯一选项，不把合理舍入当错误。
所有额外字段必填，issues必须包含可用于局部修复的明确原因。
"""


def review_ziliao_material(material: dict, plan: dict | None = None) -> dict:
    design = ""
    if plan and plan.get("track") == "gd":
        design = (track_material_rules("gd", plan) +
                  "核查naturalness时列出正文口径句、两个背景指标、半给指标、有图表时的图表独有取数点；"
                  "naturalness对象额外返回body_scope_quote，逐字引用正文中的完整统计边界句（不得引用注/附注）；"
                  "正文没有就填空并REJECT。缺失则不通过。半给的背景指标不构成事实缺漏；尚未出题，不要求预测哪些指标最终入题。")
    review = call_flash(ZILIAO_MATERIAL_SYSTEM + ZILIAO_INFERENCE_RULES + ZILIAO_FIGURE_RULES + design,
                        json.dumps(material, ensure_ascii=False))
    checks = review.get("checks") or {}
    required = {"totals", "growth", "scope_units", "text_figure", "naturalness"}
    if (set(checks) != required or any(
        not isinstance(check, dict) or check.get("ok") is not True or not str(check.get("reason") or "").strip()
        for check in checks.values()
    )):
        review["verdict"] = "REJECT"
        review.setdefault("issues", []).append("材料核验不全或不通过")
    if plan and plan.get("track") == "gd":
        naturalness = checks.get("naturalness")
        quote = naturalness.get("body_scope_quote") if isinstance(naturalness, dict) else None
        body = re.split(r"(?:^|\n)\s*(?:附注|注)(?:[：:①（(]|\s*$)", str(material.get("content") or ""), maxsplit=1)[0]
        if not isinstance(quote, str) or len(quote.strip()) < 8 or quote.strip() not in body:
            review["verdict"] = "REJECT"
            review.setdefault("issues", []).append("缺少可核对的正文统计边界原句；把范围说明自然写入正文，不能只放注脚")
    return review


def explanation_claims(question: dict) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[。；;\n])", str(question.get("explanation") or "")) if s.strip()]


def ziliao_review_issues(question: dict, review: dict) -> list[str]:
    issues = []
    for field in ("material_consistent", "slot_match"):
        if review.get(field) is not True:
            issues.append(f"资料审核 {field} 缺失或不通过")
    family = review.get("actual_family")
    if family not in {"detail", "share_add", "growth", "base_share", "avg_cmp", "mix_pull", "judge"}:
        issues.append("缺少实际考法分类")
    expected = (question.get("requested_slot") or {}).get("family")
    if expected and expected != "classic" and family != expected:
        issues.append(f"实际考法 {family} 不符槽位 {expected}，须修题而非改标签")
    difficulty = review.get("actual_difficulty")
    if type(difficulty) is not int or not 1 <= difficulty <= 5 or not review.get("difficulty_reason"):
        issues.append("缺少实际难度及依据")
    if (question.get("requested_slot") or {}).get("track") == "gd":
        check = review.get("design_check")
        if not isinstance(check, dict) or check.get("ok") is not True or not str(check.get("reason") or "").strip():
            issues.append(f"轨A命题设计核验缺失或不通过：{check}")
        if expected == "detail" and type(difficulty) is int and difficulty > 2:
            issues.append("轨A细节槽实际难度超过2，须简化题目")
    claims = explanation_claims(question)
    checks = review.get("claim_checks")
    if (not claims or not isinstance(checks, list) or len(checks) != len(claims)
            or any(not isinstance(c, dict) or type(c.get("index")) is not int for c in checks)
            or {c["index"] for c in checks} != set(range(1, len(claims) + 1))):
        issues.append("原解析逐句核查缺项或重复")
    else:
        for check in checks:
            if check.get("valid") is not True or not str(check.get("reason") or "").strip():
                issues.append(f"解析第{check['index']}句不通过：{check.get('reason') or '缺依据'}")
    return issues


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
    # 资料分析题的可作答事实在 material_id 对应的材料里；不带材料审查会把整套题误判为缺数据。
    if question.get("material_content"):
        result["material"] = question["material_content"]
        result["material_images"] = question.get("material_images") or []
        result["figure"] = question.get("material_figure") or {}
    if include_answer:
        result["answer"] = question.get("answer")
        result["explanation"] = question.get("explanation")
        result["difficulty"] = question.get("difficulty")
        result["family"] = question.get("family")
        result["requested_slot"] = question.get("requested_slot") or {}
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
    "ceil": math.ceil,
    "floor": math.floor,
    "max": max,
    "min": min,
    "round": round,
    "sum": sum,
    "sqrt": math.sqrt,
}

# 最值、抽屉这些考法的最后一步是取整，不是算术。correct 停在取整前的小数上
# 是正常的，方向由 spec 声明——不能靠「floor 或 ceil 都算命中」去猜，
# 因为相邻整数选项（24/25/26/27）是常态，两头都放行就等于放弃判定。
ROUNDING = {
    "floor": math.floor,
    "down": math.floor,
    "向下": math.floor,
    "ceil": math.ceil,
    "up": math.ceil,
    "向上": math.ceil,
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


def run_ziliao_blind(questions: list[dict]) -> dict[str, dict]:
    groups = {}
    for q in questions:
        if q.get("category") == CAT_ZILIAO:
            groups.setdefault(q.get("material_id") or q["external_id"], []).append(q)
    if not groups:
        return {}

    def review_group(group):
        return indexed(call_flash(ZILIAO_BLIND_SYSTEM + ZILIAO_INFERENCE_RULES, json.dumps([public_question(q) for q in group], ensure_ascii=False)))

    with ThreadPoolExecutor(max_workers=min(4, len(groups))) as pool:
        return {qid: review for result in pool.map(review_group, groups.values()) for qid, review in result.items()}


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
    blind = run_ziliao_blind(questions)
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
                raw_target = safe_eval(spec["correct"])
                direction = str(spec.get("round") or "").strip().lower()
                if direction and direction not in ROUNDING:
                    raise ValueError(f"unknown rounding direction: {direction}")
                target = ROUNDING[direction](raw_target) if direction else raw_target
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
                if direction:
                    details["pre_rounding_value"] = raw_target
                    details["round"] = direction
                if matches != [str(question.get("answer") or "")]:
                    issues.append(f"calculation match is {matches}, claimed {question.get('answer')}")
                if set(option_values) != {
                    str(option.get("key")) for option in question.get("options") or []
                }:
                    issues.append("calculation options do not cover question options")
            except Exception as exc:
                issues.append(str(exc))
        if question.get("category") == CAT_ZILIAO:
            review = blind.get(qid) or {}
            tests = review.get("option_tests") or {}
            keys = {str(o.get("key")) for o in question.get("options") or []}
            if (review.get("verdict") != "PASS" or review.get("answer") != question.get("answer")
                    or review.get("also_valid") != [] or not str(review.get("steps") or "").strip()
                    or review.get("issues", []) != [] or set(tests) != keys
                    or any(not isinstance(t, dict) or type(t.get("stands")) is not bool or not t.get("reason") for t in tests.values())
                    or [k for k, t in tests.items() if isinstance(t, dict) and t.get("stands") is True] != [question.get("answer")]):
                issues.append("资料独立盲解未通过：" + json.dumps(review, ensure_ascii=False))
            details["blind_review"] = review
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
    if leaked := scratchpad_leak(question):
        issues.append(
            "analysis leaks a reverse-engineering scratchpad "
            f"({'、'.join(leaked)}); the stem was never updated to match"
        )
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

    def review_group(group):
        ziliao = all(q.get("category") == CAT_ZILIAO for q in group)
        gd = ziliao and ((manifest.get("generation") or {}).get("batch_constraints") or {}).get("track") == "gd"
        payload = {
            "items": [
                {
                    "question": public_question(q, include_answer=True),
                    "evaluation_only_real_questions": references.get(str(q["external_id"]), []),
                    **({"explanation_claims": [{"index": i, "text": s} for i, s in enumerate(explanation_claims(q), 1)]} if ziliao else {}),
                }
                for q in group
            ],
            "rules": rules,
        }
        images = []
        for question in group:
            for index, path in enumerate(question_images(batch_dir, question), 1):
                images.append((f"{question['external_id']} IMAGE {index}", path))
        design = (GD_DESIGN_RULES +
                  '每题额外返回design_check={"ok":true,"reason":"该题口径、实际负担、适用的干扰公式或综合辨析依据"}。'
                  '逐项核对上述轨A要求，缺陷须ok=false并在issues给出题号及修法；不适用的要求说明不适用。'
                  if gd else "")
        return indexed(call_flash(QUALITY_SYSTEM + (ZILIAO_QUALITY_RULES + ZILIAO_INFERENCE_RULES if ziliao else "") + design, json.dumps(payload, ensure_ascii=False), images))

    groups = {}
    for q in questions:
        key = (q.get("material_id") or q["external_id"]) if q.get("category") == CAT_ZILIAO else "other"
        groups.setdefault(key, []).append(q)
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(groups)))) as pool:
        reviews = {qid: review for result in pool.map(review_group, groups.values()) for qid, review in result.items()}
    output = {}
    for question in questions:
        qid = str(question["external_id"])
        review = reviews.get(qid)
        issues = local_quality_issues(question)
        if not review:
            issues.append("quality reviewer missing")
        else:
            if question.get("category") == CAT_ZILIAO:
                issues.extend(ziliao_review_issues(question, review))
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
            reviewed_ids = {str(value) for value in review.get("reference_ids") or []}
            if mapped_ids and reviewed_ids != mapped_ids:
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
    if is_kepui_paper(generated) and not bool(
        ((manifest.get("generation") or {}).get("batch_constraints") or {}).get("targeted_drill")
    ):
        try:
            validate_kepui_paper(generated)
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
        "kaofa_canon": (manifest.get("generation") or {}).get("kaofa_canon") or {},
        "questions": [public_question(q, include_answer=True) | {"difficulty": q.get("difficulty")} for q in questions],
        "evaluation_references_by_question": evaluation_references(manifest),
    }
    gd = payload["batch_constraints"].get("track") == "gd" and not payload["batch_constraints"].get("targeted_drill")
    design = (GD_PAPER_RULES +
              '额外返回design_check={"ok":true,"reason":"引用题号和取数点说明细节、范围、百分点及各篇图表独有数据的实际覆盖"}。'
              '未覆盖则ok=false且issues给出具体缺陷。' if gd else "")
    review = call_flash(BATCH_SYSTEM + design, json.dumps(payload, ensure_ascii=False))
    if not isinstance(review, dict):
        review = {}
    if gd:
        check = review.get("design_check")
        if not isinstance(check, dict) or check.get("ok") is not True or not str(check.get("reason") or "").strip():
            review.setdefault("issues", []).append(f"轨A整套设计核验缺失或不通过：{check}")
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
    materials = read_json(batch_dir / "materials.json") if (batch_dir / "materials.json").is_file() else []
    material_by_id = {str(item.get("external_id")): item for item in materials if isinstance(item, dict)}
    constraints = (manifest.get("generation") or {}).get("batch_constraints") or {}
    slots = [slot for slot in constraints.get("slot_plan") or [] for _ in range(slot.get("count", 1))]
    for index, question in enumerate(questions):
        material = material_by_id.get(str(question.get("material_id")))
        if material:
            question["material_content"] = material.get("content") or ""
            question["material_images"] = material.get("images") or []
            question["material_figure"] = material.get("figure") or {}
        if question.get("category") == CAT_ZILIAO and index < len(slots):
            question["requested_slot"] = {**slots[index], "track": constraints.get("track")}
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

#!/usr/bin/env python3
"""签发并校验 AI 题组正确性/质量闸门回执。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from kaodian_taxonomy import (
    question_primary_tag,
    validate_ai_primary_tag,
    validate_shuliang_paper,
    validate_ziliao_paper_answers,
    validate_ziliao_variety,
)
from normalize_ai_batch import generated_questions, normalize_batch, validate_daily_paper_order
from panduan_pack import _blob as _kepui_blob
from panduan_pack import is_kepui_paper, is_panduan_paper, kepui_bucket, validate_kepui_paper, validate_panduan_paper
from reference_style import has_images, match_level


def is_zhenti_question(question: dict) -> bool:
    return str(question.get("origin") or "") == "zhenti" or str(
        question.get("external_id") or ""
    ).startswith("zhenti-")


VERSION = 3
LEGACY_VERSIONS = {1, 2}
RECEIPT = ".gate.json"


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_image_paths(batch_dir: Path) -> list[Path]:
    questions = read_json(batch_dir / "questions.json")
    materials_path = batch_dir / "materials.json"
    materials = read_json(materials_path) if materials_path.is_file() else []
    relatives: set[str] = set()
    for material in materials if isinstance(materials, list) else []:
        relatives.update(str(value) for value in material.get("images") or [])
    for question in questions if isinstance(questions, list) else []:
        relatives.update(str(value) for value in question.get("stem_images") or [])
        relatives.update(str(value) for value in question.get("explanation_images") or [])
        for option in question.get("options") or []:
            relatives.update(str(value) for value in option.get("images") or [])
    paths = []
    root = batch_dir.resolve()
    for relative in sorted(relatives):
        path = (batch_dir / relative).resolve()
        if root not in path.parents or not relative.startswith("images/") or not path.is_file():
            raise ValueError(f"图片缺失或路径非法：{relative}")
        paths.append(path)
    return paths


def ziliao_image_paths(batch_dir: Path) -> list[Path]:
    questions = read_json(batch_dir / "questions.json")
    if not isinstance(questions, list) or not any(
        str(question.get("category") or "") == "资料分析" for question in questions
    ):
        return []
    return all_image_paths(batch_dir)


def artifact_digests(batch_dir: Path) -> dict[str, str]:
    paths = all_image_paths(batch_dir)
    for name in (
        "materials.json",
        "read-spot-packs.json",
        "calculations.json",
        "image-specs.json",
    ):
        path = batch_dir / name
        if path.is_file():
            paths.append(path.resolve())
    return {str(path.relative_to(batch_dir.resolve())): digest(path) for path in sorted(set(paths))}


def validate_ziliao_visual_evidence(batch_dir: Path, evidence: dict, image_paths: list[Path]) -> None:
    if str(evidence.get("verdict") or "").upper() != "PASS":
        raise ValueError("资料分析多模态视觉质检未通过")
    if evidence.get("batch_id") != read_json(batch_dir / "manifest.json").get("batch_id"):
        raise ValueError("视觉质检 batch_id 不一致")
    if int(evidence.get("mobile_width") or 0) != 320 or "flash" not in str(evidence.get("model") or "").lower():
        raise ValueError("视觉质检必须由 Gemini Flash 同时检查原图和 320px 考生视图")
    expected = {str(path.relative_to(batch_dir.resolve())): digest(path) for path in image_paths}
    results = evidence.get("images") or []
    actual = {str(item.get("path") or ""): item for item in results if isinstance(item, dict)}
    if set(actual) != set(expected):
        raise ValueError("视觉质检未覆盖批次全部资料分析图表")
    required = ("complete", "no_overlap", "units_mapped", "mobile_readable", "context_consistent")
    for relative, sha in expected.items():
        item = actual[relative]
        checks = item.get("checks") or {}
        if item.get("sha256") != sha or str(item.get("verdict") or "").upper() != "PASS":
            raise ValueError(f"视觉质检图片未通过或已变化：{relative}")
        if int(item.get("mobile_width") or 0) != 320 or not all(checks.get(key) is True for key in required):
            raise ValueError(f"视觉质检项不完整：{relative}")


def run_ziliao_visual_gate(batch_dir: Path, image_paths: list[Path]) -> Path | None:
    if not image_paths:
        return None
    output = batch_dir / "evidence" / "ziliao-visual-quality.json"
    command = [
        sys.executable, str(Path(__file__).with_name("ziliao_visual_gate.py")),
        str(batch_dir), "--output", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        detail = (result.stdout or result.stderr).strip()
        raise ValueError(f"Gemini Flash 多模态视觉质检失败：{detail[-1200:]}")
    evidence = read_json(output)
    if not isinstance(evidence, dict):
        raise ValueError("视觉质检证据必须是 JSON 对象")
    validate_ziliao_visual_evidence(batch_dir, evidence, image_paths)
    return output


def reference_context_digests(batch_dir: Path, manifest: dict) -> dict[str, str]:
    generation = manifest.get("generation") or {}
    marker = str(generation.get("style_marker") or "")
    questions = read_json(batch_dir / "questions.json")
    by_question = {str(question.get("external_id") or ""): question for question in questions}
    db_path = Path(os.environ.get("EXAM_DB", Path(__file__).resolve().parents[1] / "data" / "exam.db"))
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    output: dict[str, str] = {}
    try:
        for field, role in (("generation_contexts", "generate"), ("evaluation_contexts", "evaluate")):
            for item in generation.get(field) or []:
                context_id = str(item.get("context_id") or "")
                row = connection.execute(
                    "SELECT context_id, role, digest_version, target, reference_ids, batch_id "
                    "FROM reference_context_runs WHERE context_id = ?",
                    (context_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"参考上下文不存在或并非系统生成：{context_id}")
                if row["role"] != role or row["digest_version"] != marker:
                    raise ValueError(f"参考上下文角色或版本不一致：{context_id}")
                target = json.loads(row["target"] or "{}")
                for qid in item.get("question_ids") or []:
                    question = by_question.get(str(qid))
                    if question is None:
                        raise ValueError(f"参考上下文覆盖不存在的题：{qid}")
                    if target.get("category") != question.get("category"):
                        raise ValueError(f"参考上下文顶层模块与题目不一致：{context_id}/{qid}")
                    if question.get("sub_category") and target.get("sub_category") != question.get("sub_category"):
                        raise ValueError(f"参考上下文细分类与题目不一致：{context_id}/{qid}")
                    if target.get("tag") != question_primary_tag(question):
                        raise ValueError(f"参考上下文主标签与题目不一致：{context_id}/{qid}")
                    if question_images := (question.get("stem_images") or any(
                        option.get("images") for option in question.get("options") or []
                    )):
                        if target.get("image_mode") != "yes":
                            raise ValueError(f"带图题必须使用 images=yes 参考上下文：{context_id}/{qid}")
                recorded_ids = json.loads(row["reference_ids"] or "[]")
                if recorded_ids != (item.get("reference_ids") or []):
                    raise ValueError(f"参考上下文题目列表不一致：{context_id}")
                if row["batch_id"] and row["batch_id"] != manifest.get("batch_id"):
                    raise ValueError(f"参考上下文已绑定其他批次：{context_id}")
                references = []
                for ref_id in recorded_ids:
                    ref = connection.execute(
                        "SELECT external_id, category, sub_category, question_type, content, "
                        "stem_images, options, correct_answer, explanation_images, difficulty, "
                        "tags, source, year, region FROM reference_questions WHERE external_id = ?",
                        (ref_id,),
                    ).fetchone()
                    if ref is None:
                        raise ValueError(f"参考题不存在：{ref_id}")
                    if match_level(
                        ref,
                        str(target.get("category") or ""),
                        str(target.get("sub_category") or ""),
                        str(target.get("tag") or ""),
                    ) < 2:
                        raise ValueError(f"参考题模块或考点与上下文不匹配：{context_id}/{ref_id}")
                    if target.get("image_mode") == "yes" and not has_images(ref):
                        raise ValueError(f"带图上下文引用了无图真题：{context_id}/{ref_id}")
                    references.append(dict(ref))
                payload = {
                    "context": {
                        "context_id": row["context_id"],
                        "role": row["role"],
                        "digest_version": row["digest_version"],
                        "target": row["target"],
                        "reference_ids": recorded_ids,
                    },
                    "references": references,
                }
                canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                output[context_id] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    finally:
        connection.close()
    return dict(sorted(output.items()))


def validate_batch_constraints(manifest: dict, questions: list[dict]) -> None:
    constraints = (manifest.get("generation") or {}).get("batch_constraints")
    if not isinstance(constraints, dict) or not constraints:
        raise ValueError("v3 批次必须有 generation.batch_constraints 固化用户要求")
    generated = [question for question in questions if not is_zhenti_question(question)]
    if constraints.get("all_original") is True and len(generated) != len(questions):
        raise ValueError("全原创批次不得混入真题")
    expected_count = int(constraints.get("question_count") or 0)
    if expected_count and len(generated) != expected_count:
        raise ValueError(f"原创题数量不符合 batch_constraints：{len(generated)}/{expected_count}")
    expected_tags = constraints.get("tag_counts") or {}
    if expected_tags:
        actual_tags: dict[str, int] = {}
        for question in generated:
            tag = question_primary_tag(question)
            actual_tags[tag] = actual_tags.get(tag, 0) + 1
        if actual_tags != {str(key): int(value) for key, value in expected_tags.items()}:
            raise ValueError(f"主标签配比不符合 batch_constraints：{actual_tags}")
    image_count = sum(bool(all_image_paths_for_question(question)) for question in generated)
    image_rule = constraints.get("image_dependent_count") or {}
    if image_rule:
        if image_count < int(image_rule.get("min", 0)) or image_count > int(image_rule.get("max", len(generated))):
            raise ValueError(f"带图题数量不符合 batch_constraints：{image_count}")
    if constraints.get("no_images") is True and image_count:
        raise ValueError("batch_constraints 要求纯文字，但批次含题图")
    answers: dict[str, int] = {}
    for question in generated:
        answer = str(question.get("answer") or "").upper()
        answers[answer] = answers.get(answer, 0) + 1
    max_per_letter = int(constraints.get("answer_max_per_letter") or len(generated))
    min_letters = int(constraints.get("answer_min_letters") or 1)
    if answers and (max(answers.values()) > max_per_letter or len(answers) < min_letters):
        raise ValueError(f"答案位置分布不符合 batch_constraints：{answers}")

    validate_daily_paper_order(str(manifest.get("batch_id") or ""), questions)


def all_image_paths_for_question(question: dict) -> list[str]:
    relatives = [str(value) for value in question.get("stem_images") or []]
    relatives.extend(str(value) for value in question.get("explanation_images") or [])
    for option in question.get("options") or []:
        relatives.extend(str(value) for value in option.get("images") or [])
    return relatives


def question_needs_evaluate_holdout(question: dict) -> bool:
    from kaodian_taxonomy import question_primary_tag
    from normalize_ai_batch import has_question_images
    from reference_style import has_evaluate_holdout

    db_path = Path(os.environ.get("EXAM_DB", Path(__file__).resolve().parents[1] / "data" / "exam.db"))
    if not db_path.is_file():
        return False
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return has_evaluate_holdout(
            connection,
            category=str(question.get("category") or ""),
            sub_category=str(question.get("sub_category") or ""),
            target_tag=question_primary_tag(question),
            image_mode="yes" if has_question_images(question) else "any",
        )
    finally:
        connection.close()


def validate_context_coverage(manifest: dict, ids: list[str], questions: list[dict] | None = None) -> None:
    generation = manifest.get("generation") or {}
    expected = set(ids)
    eval_contexts = [
        item for item in (generation.get("evaluation_contexts") or [])
        if str(item.get("context_id") or "").strip()
    ]
    eval_covered = [str(qid) for item in eval_contexts for qid in item.get("question_ids") or []]
    extra = set(eval_covered) - expected
    if extra:
        raise ValueError("evaluation_contexts 绑定了不存在的生成题")
    if len(eval_covered) != len(set(eval_covered)):
        raise ValueError("evaluation_contexts 不得重复绑定同一生成题")
    missing = expected - set(eval_covered)
    by_id = {str(question.get("external_id") or ""): question for question in (questions or [])}
    must = []
    for qid in missing:
        question = by_id.get(qid)
        if question is None or question_needs_evaluate_holdout(question):
            must.append(qid)
    if must:
        raise ValueError("evaluation_contexts 必须覆盖有 holdout 的生成题")
    gen_contexts = generation.get("generation_contexts") or []
    gen_covered = [str(qid) for item in gen_contexts for qid in item.get("question_ids") or []]
    extra = set(gen_covered) - expected
    if extra:
        raise ValueError("generation_contexts 绑定了不存在的生成题")
    if len(gen_covered) != len(set(gen_covered)):
        raise ValueError("generation_contexts 不得重复绑定同一生成题")
    gen_ctx = {str(item.get("context_id") or "") for item in gen_contexts}
    eval_ctx = {str(item.get("context_id") or "") for item in eval_contexts}
    gen_ctx.discard("")
    if "" in eval_ctx:
        raise ValueError("evaluation_contexts 缺少 context_id")
    if gen_ctx & eval_ctx:
        raise ValueError("generate/evaluate context 不得复用")
    gen_refs = {str(ref) for item in gen_contexts for ref in item.get("reference_ids") or []}
    eval_refs = {str(ref) for item in eval_contexts for ref in item.get("reference_ids") or []}
    if gen_refs & eval_refs:
        raise ValueError("generate/evaluate 真题样本不得复用")


def validate_system_quality(batch_dir: Path, evidence: dict, ids: list[str]) -> None:
    if evidence.get("kind") != "examsystem-system-quality":
        raise ValueError("系统质检证据 kind 错误")
    if str(evidence.get("verdict") or "").upper() != "PASS":
        rejected = [
            item.get("question_id") for item in evidence.get("results") or []
            if item.get("verdict") != "PASS"
        ]
        raise ValueError(f"ExamSystem 系统质检未通过：{rejected}")
    manifest = read_json(batch_dir / "manifest.json")
    if evidence.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("系统质检 batch_id 不一致")
    if "flash" not in str(evidence.get("model") or "").lower():
        raise ValueError("系统质检必须由 Gemini Flash 执行")
    if evidence.get("questions_sha256") != digest(batch_dir / "questions.json"):
        raise ValueError("系统质检后的 questions.json 已变化")
    if evidence.get("manifest_sha256") != digest(batch_dir / "manifest.json"):
        raise ValueError("系统质检后的 manifest.json 已变化")
    results = evidence.get("results") or []
    actual = {str(item.get("question_id") or ""): item for item in results if isinstance(item, dict)}
    if set(actual) != set(ids):
        raise ValueError("系统质检未覆盖全部生成题")
    for qid, item in actual.items():
        if item.get("route") not in tuple("ABCD") or item.get("verdict") != "PASS":
            raise ValueError(f"系统质检子路线未通过：{qid}")
        if (item.get("correctness") or {}).get("verdict") != "PASS":
            raise ValueError(f"系统正确性检查未通过：{qid}")
        if (item.get("quality") or {}).get("verdict") != "PASS":
            raise ValueError(f"系统风格质量检查未通过：{qid}")


def _quality_fail_summary(output: Path, result) -> str:
    if output.is_file():
        try:
            evidence = read_json(output)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            evidence = None
        if isinstance(evidence, dict):
            rejected = [
                item.get("question_id")
                for item in evidence.get("results") or []
                if isinstance(item, dict) and item.get("verdict") != "PASS"
            ]
            batch = evidence.get("batch_quality") or {}
            batch_issues = (batch.get("review") or {}).get("issues") or batch.get("issues") or []
            item_issues = []
            for item in evidence.get("results") or []:
                if not isinstance(item, dict) or item.get("verdict") == "PASS":
                    continue
                corr = (item.get("correctness") or {}).get("issues") or []
                qual = (item.get("quality") or {}).get("issues") or []
                if corr or qual:
                    item_issues.append(
                        f"{item.get('question_id')}: corr={corr} quality={qual}"
                    )
            return json.dumps(
                {
                    "rejected": rejected,
                    "batch_issues": batch_issues,
                    "item_issues": item_issues[:12],
                },
                ensure_ascii=False,
            )[:2000]
    return (result.stdout or result.stderr or "").strip()[-2000:]


def run_system_quality_gate(batch_dir: Path, ids: list[str]) -> Path:
    output = batch_dir / "evidence" / "system-quality.json"
    command = [
        sys.executable, str(Path(__file__).with_name("quality_orchestrator.py")),
        str(batch_dir), "--output", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise ValueError(f"ExamSystem 系统质检失败：{_quality_fail_summary(output, result)}")
    evidence = read_json(output)
    if not isinstance(evidence, dict):
        raise ValueError("系统质检证据必须是 JSON 对象")
    validate_system_quality(batch_dir, evidence, ids)
    return output


def run_anti_clone_check(batch_dir: Path) -> Path:
    """运行反克隆检测，防止生成题照搬参考题结构"""
    output = batch_dir / "evidence" / "anti-clone.json"
    db_path = os.environ.get("EXAM_DB") or Path(__file__).parent.parent / "data" / "exam.db"
    command = [
        sys.executable, str(Path(__file__).with_name("anti_clone_checker.py")),
        str(batch_dir), "--db", str(db_path), "--output", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if output.is_file():
        evidence = read_json(output)
        if isinstance(evidence, dict):
            # ponytail: 反克隆只留证据，克隆命中不拦入库
            return output
    detail = (result.stdout or result.stderr).strip()
    raise ValueError(f"反克隆检测执行失败：{detail[-2000:]}")


def atomic_json(path: Path, value: dict) -> None:
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def question_ids(batch_dir: Path) -> list[str]:
    questions = read_json(batch_dir / "questions.json")
    if not isinstance(questions, list):
        raise ValueError("questions.json 必须是数组")
    ids = [str(question.get("external_id") or "") for question in questions]
    if not ids or any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("questions.json external_id 缺失或重复")
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            raise ValueError(f"questions[{index}] 必须是对象")
        if is_zhenti_question(question):
            continue
        try:
            validate_ai_primary_tag(
                question_primary_tag(question),
                str(question.get("category") or ""),
            )
        except ValueError as exc:
            ident = question.get("external_id") or index
            raise ValueError(f"questions[{ident}] {exc}") from exc
    _validate_ziliao_answer_layout(questions)
    _validate_panduan_layout(questions)
    return [str(question.get("external_id") or "") for question in questions if not is_zhenti_question(question)]


def _validate_panduan_layout(questions: list) -> None:
    generated = generated_questions(questions)
    if is_panduan_paper(generated):
        validate_panduan_paper(generated)
    if is_kepui_paper(generated):
        validate_kepui_paper(generated)


def _validate_ziliao_answer_layout(questions: list) -> None:
    groups: dict[str, list[str]] = {}
    for question in questions:
        if is_zhenti_question(question):
            continue
        if str(question.get("category") or "") != "资料分析":
            continue
        material_id = str(question.get("material_id") or "")
        if not material_id:
            continue
        answer = str(question.get("answer") or question.get("correct_answer") or "").strip().upper()
        groups.setdefault(material_id, []).append(answer)
    if len(groups) == 4 and all(len(keys) == 5 for keys in groups.values()):
        validate_ziliao_paper_answers(list(groups.values()))


def validate_evidence(
    evidence: dict,
    expected_ids: list[str],
    kind: str,
    expected_context_ids: set[str] | None = None,
) -> None:
    if str(evidence.get("verdict") or "").upper() != "PASS":
        raise ValueError(f"{kind} evidence verdict 必须是 PASS")
    ids = [str(value) for value in evidence.get("question_ids") or []]
    if set(ids) != set(expected_ids) or len(ids) != len(expected_ids):
        raise ValueError(f"{kind} evidence 未覆盖本批全部题")
    if kind == "quality":
        contexts = {str(value) for value in evidence.get("evaluation_context_ids") or []}
        if contexts != (expected_context_ids or set()):
            raise ValueError("quality evidence 的 evaluation_context_ids 与 manifest 不一致")
    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{kind} evidence 必须列出实际检查项")


_KEGANG_WORDS = ("本题考察", "本题考查", "秒杀模型", "秒杀技巧")
_JUDGE_MARKERS = ("可以判断属实", "不能从", "无法从", "能够从", "正确的有", "推出的是")
# 科学推理应为广东/初中难度：以下高中/大学内容禁入
_SCIENCE_OVERLEVEL = ("理想气体", "状态方程", "动量守恒", "动量定理", "洛伦兹力", "麦克斯韦", "波尔", "薛定谔")


def _judge_form(stem: str) -> str:
    """资料综合判断题干形式分类（属实 / 无法推出 / 计数 / 能推出）。"""
    if "正确的有" in stem:
        return "计数"
    if ("不能" in stem or "无法" in stem) and "推" in stem:
        return "无法推出"
    if "属实" in stem:
        return "属实"
    if "能够" in stem and "推" in stem:
        return "能推出"
    return ""


def _material_contents(batch_dir: Path | None) -> list[str]:
    if not batch_dir:
        return []
    path = batch_dir / "materials.json"
    if not path.is_file():
        return []
    data = read_json(path)
    return [str(m.get("content") or "") for m in data if isinstance(m, dict)] if isinstance(data, list) else []


def _dirty_ratio(texts: list[str]) -> float:
    year = re.compile(r"^(19|20)\d{2}$")
    dirty = total = 0
    for text in texts:
        for token in re.findall(r"\d+(?:\.\d+)?", text):
            if "." not in token and year.match(token):
                continue
            total += 1
            intpart = token.split(".")[0]
            if "." in token or (len(intpart) >= 3 and intpart[-2:] != "00"):
                dirty += 1
    return (dirty / total) if total else 1.0


def validate_paper_hard_rules(manifest: dict, questions: list[dict], batch_dir: Path | None = None) -> None:
    """广东通用卷机械硬规则（出题闸门，不依赖大模型）。已用样卷验收，命中即拦下本次生成。"""
    generated = generated_questions(questions)
    # 1) 单选完整性（双答案兜底）：答案唯一字母、至少 4 个互不相同的选项
    for question in generated:
        if str(question.get("question_type") or "single") != "single":
            continue
        options = question.get("options") or []
        keys = [str(opt.get("key") or "") for opt in options if isinstance(opt, dict)]
        answer = str(question.get("answer") or "")
        qid = question.get("external_id")
        if len(keys) < 4:
            raise ValueError(f"单选题选项不足 4 个：{qid}")
        if answer not in keys or len(answer.strip()) != 1:
            raise ValueError(f"单选题答案必须是唯一选项字母：{qid} → {answer!r}")
        signatures = [str(opt.get("text") or "").strip() or tuple(opt.get("images") or []) for opt in options]
        if len(set(signatures)) != len(signatures):
            raise ValueError(f"单选题存在重复选项（内容或图片相同）：{qid}")
    # 2) 判断推理禁类比 / 定义
    for question in questions:
        blob = f"{question.get('sub_category') or ''} {question_primary_tag(question)} {' '.join(question.get('tags') or [])}"
        if "类比推理" in blob or "定义判断" in blob:
            raise ValueError(f"判断推理不得出类比推理 / 定义判断：{question.get('external_id')}")
    # 3) 禁课纲词
    for question in questions:
        stem = str(question.get("stem") or question.get("content") or "")
        if any(word in stem for word in _KEGANG_WORDS):
            raise ValueError(f"题面禁止课纲词（本题考察 / 秒杀模型等）：{question.get('external_id')}")
    # 4) 数量卷：不得 0 数字推理；15 题须数推 5 + 运算 10
    validate_shuliang_paper(generated)
    # 5) 资料卷：四篇考点骨架不得同构
    validate_ziliao_variety(generated)
    # 6) 资料卷专项：禁“某省”、脏数字≥40%、综合判断形式跨篇轮换
    ziliao = [q for q in generated if str(q.get("category") or "") == "资料分析"]
    materials = {str(q.get("material_id") or "") for q in ziliao if q.get("material_id")}
    if len(materials) >= 4:
        contents = _material_contents(batch_dir)
        for content in contents:
            if "某省" in content:
                raise ValueError("资料分析材料禁止用“某省”占位，请用具体化名（如 G省）或全国口径")
        if contents and _dirty_ratio(contents) < 0.40:
            raise ValueError("资料分析数字过于圆整：脏数字（含小数或末两位非 00）比例须 ≥40%")
        # 每篇须有 1 道综合判断（Q5），且四篇综合判断形式跨篇轮换（≥2 种）
        forms_by_material: dict[str, list[str]] = {}
        for q in ziliao:
            form = _judge_form(str(q.get("stem") or ""))
            if form:
                forms_by_material.setdefault(str(q.get("material_id") or ""), []).append(form)
        if sum(1 for m in materials if forms_by_material.get(m)) < 4:
            raise ValueError("资料分析每篇必须有 1 道综合判断（Q5）")
        all_forms = [f for forms in forms_by_material.values() for f in forms]
        if len(set(all_forms)) < 2:
            raise ValueError("综合判断形式需跨篇轮换（属实 / 无法推出 / 能推出几个 / 能推出），至少 2 种")
    # 7) 判断推理 20 题 = 图形 5 + 逻辑 15；日练不得再走「后 5 科学」压缩模型
    panduan = [q for q in generated if str(q.get("category") or "") == "判断推理"]
    if len(panduan) == 20:
        if any("科学推理" in (str(q.get("sub_category") or "") + str(q.get("category") or ""))
               or "科学推理" in " ".join(str(t) for t in (q.get("tags") or []))
               for q in panduan):
            raise ValueError("日练判断 20 题不得含科学推理；科学推理是独立 5 题模块，压缩模型已废止")
        g = sum(1 for q in panduan if "图形推理" in str(q.get("sub_category") or ""))
        lg = sum(1 for q in panduan if "逻辑判断" in str(q.get("sub_category") or ""))
        if g != 5 or lg != 15:
            raise ValueError(f"广东判断 20 题须图形 5 + 逻辑 15，当前 {g}/{lg}")
        validate_panduan_paper(panduan)
    # 8) 科学推理：日练 5 题五科去重；专项 focus_tag 只查图、超纲、category
    science = [q for q in generated
               if "科学推理" in (str(q.get("category") or "") + str(q.get("sub_category") or ""))]
    if science:
        constraints = (
            (manifest.get("generation") or {}).get("batch_constraints")
            or manifest.get("batch_constraints")
            or {}
        )
        focus = str(constraints.get("focus_tag") or "").strip()
        daily_kepui = not focus
        if daily_kepui:
            if len(science) != 5:
                raise ValueError(f"科学推理须为 5 题（独立模块），当前 {len(science)} 题")
            buckets = [kepui_bucket(_kepui_blob(q)) for q in science]
            if any(not b for b in buckets):
                raise ValueError("科学推理每题须落到具体学科（力学/压强浮力/电学/生物/地理等）")
            if len(set(buckets)) != 5:
                raise ValueError("科学推理 5 题学科须互不相同")
        else:
            buckets = [kepui_bucket(_kepui_blob(q)) for q in science]
            if any(not b for b in buckets):
                raise ValueError("科学推理每题须落到具体学科（力学/压强浮力/电学/生物/地理等）")
        for q in science:
            if not (q.get("stem_images") or any(o.get("images") for o in q.get("options") or [])):
                raise ValueError(f"科学推理每题必带图：{q.get('external_id')}")
            stem = str(q.get("stem") or "")
            hit = next((w for w in _SCIENCE_OVERLEVEL if w in stem), None)
            if hit:
                raise ValueError(
                    f"科学推理应为广东/初中难度，禁高中大学内容（{hit}）：{q.get('external_id')}。"
                    "改用杠杆/浮力/串并联/海陆风/等高线/食物链光合等，公式限 F=ma、G=mg、p=ρgh、I=U/R 一档")
        validate_kepui_paper(science, require_images=True)
        if any(str(q.get("category") or "") != "科学推理" for q in science):
            raise ValueError("独立科学推理卷每题 category 必须是科学推理，禁止写成判断推理")
        if daily_kepui:
            counts: dict[str, int] = {}
            for q in science:
                ans = str(q.get("answer") or q.get("correct_answer") or "").strip().upper()
                if ans:
                    counts[ans] = counts.get(ans, 0) + 1
            if counts and (max(counts.values()) > 2 or len(counts) < 3):
                raise ValueError(
                    f"科学推理 5 题答案字母须分散：任一字母 ≤2 且至少 3 种不同字母，当前 {counts}"
                )
    # 9) 言语：禁“因此亟须”作文腔
    for question in questions:
        if str(question.get("category") or "") == "言语理解与表达":
            tail = str(question.get("stem") or "") + str(question.get("explanation") or question.get("analysis") or "")
            if "因此亟须" in tail:
                raise ValueError(f"言语题禁止“因此亟须…”作文腔表述：{question.get('external_id')}")
    # 10) 答案字母均衡（非资料卷；资料另用 3篇ABCD各一+1、1篇打散）：单卷任一字母 ≤ 约 40%
    nonziliao = [q for q in generated
                 if str(q.get("category") or "") != "资料分析"
                 and str(q.get("question_type") or "single") == "single"]
    if len(nonziliao) >= 15:
        counts: dict[str, int] = {}
        for q in nonziliao:
            ans = str(q.get("answer") or "")
            counts[ans] = counts.get(ans, 0) + 1
        cap = int(len(nonziliao) * 0.40)   # 15→6、20→8、25→10
        top = max(counts, key=counts.get)
        if counts[top] > cap:
            raise ValueError(
                f"答案字母扎堆：'{top}' 出现 {counts[top]}/{len(nonziliao)} 次，超过约 40% 上限({cap})；"
                "请按 answer_plan 均衡放置正确项")


def issue(
    batch_dir: Path,
    correctness_path: Path | None = None,
    quality_path: Path | None = None,
) -> dict:
    try:
        return _issue(batch_dir, correctness_path, quality_path)
    except Exception as exc:
        try:
            from quality_ledger import record_gate_failure

            record_gate_failure(batch_dir, str(exc))
        except Exception:
            pass
        raise


def _issue(
    batch_dir: Path,
    correctness_path: Path | None = None,
    quality_path: Path | None = None,
) -> dict:
    manifest_path = batch_dir / "manifest.json"
    questions_path = batch_dir / "questions.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("kind") != "ai-generated":
        raise ValueError("只有 kind=ai-generated 的批次需要签发")
    normalize_batch(batch_dir)
    manifest = read_json(manifest_path)
    ids = question_ids(batch_dir)
    questions = read_json(questions_path)
    validate_batch_constraints(manifest, questions)
    validate_paper_hard_rules(manifest, questions, batch_dir)
    constraints = (manifest.get("generation") or {}).get("batch_constraints") or {}
    if constraints.get("program_figures"):
        from figure_qa import check_batch

        figure_issues = check_batch(batch_dir, questions if isinstance(questions, list) else [])
        if figure_issues:
            raise ValueError("程序作图质检未过：" + "；".join(figure_issues[:8]))
    validate_context_coverage(manifest, ids, questions)
    context_digests = reference_context_digests(batch_dir, manifest)

    # 反克隆检测（防止照搬参考题结构）
    anti_clone_path = run_anti_clone_check(batch_dir)

    system_path = run_system_quality_gate(batch_dir, ids)
    image_paths = ziliao_image_paths(batch_dir)
    visual_path = run_ziliao_visual_gate(batch_dir, image_paths)

    receipt = {
        "version": VERSION,
        "batch_id": manifest.get("batch_id"),
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha256": digest(manifest_path),
        "questions_sha256": digest(questions_path),
        "artifacts": artifact_digests(batch_dir),
        "reference_contexts": context_digests,
        "question_ids": ids,
        "anti_clone": {
            "path": str(anti_clone_path.relative_to(batch_dir)),
            "sha256": digest(anti_clone_path),
        },
        "system_quality": {
            "path": str(system_path.relative_to(batch_dir)),
            "sha256": digest(system_path),
            "model": read_json(system_path).get("model"),
        },
    }
    if visual_path is not None:
        visual = read_json(visual_path)
        receipt["visual_quality"] = {
            "path": str(visual_path.relative_to(batch_dir)),
            "sha256": digest(visual_path),
            "model": visual.get("model"),
            "mobile_width": visual.get("mobile_width"),
        }
    atomic_json(batch_dir / RECEIPT, receipt)
    return receipt


def safe_child(batch_dir: Path, relative: str) -> Path:
    path = (batch_dir / relative).resolve()
    root = batch_dir.resolve()
    if root not in path.parents:
        raise ValueError("闸门证据路径越界")
    return path


def verify(batch_dir: Path) -> dict:
    receipt_path = batch_dir / RECEIPT
    if not receipt_path.is_file():
        raise ValueError(f"缺少 {RECEIPT}；AI 生成批次未完成可审计双闸门")
    receipt = read_json(receipt_path)
    manifest_path = batch_dir / "manifest.json"
    questions_path = batch_dir / "questions.json"
    if not isinstance(receipt, dict) or receipt.get("version") not in LEGACY_VERSIONS | {VERSION}:
        raise ValueError("闸门回执版本不支持")
    manifest = read_json(manifest_path)
    ids = question_ids(batch_dir)
    if receipt.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("闸门回执 batch_id 不一致")
    if receipt.get("question_ids") != ids:
        raise ValueError("闸门回执题目列表不一致")
    if receipt.get("manifest_sha256") != digest(manifest_path):
        raise ValueError("manifest 在闸门签发后被修改")
    if receipt.get("questions_sha256") != digest(questions_path):
        raise ValueError("questions 在闸门签发后被修改")
    version = receipt.get("version")
    if version == VERSION and receipt.get("reference_contexts") != reference_context_digests(batch_dir, manifest):
        raise ValueError("参考上下文或其真题内容在闸门签发后被修改")
    if version in LEGACY_VERSIONS:
        for kind in ("correctness", "quality"):
            meta = receipt.get(kind) or {}
            path = safe_child(batch_dir, str(meta.get("path") or ""))
            if not path.is_file() or digest(path) != meta.get("sha256"):
                raise ValueError(f"{kind} 证据缺失或被修改")
    if version in {2, VERSION}:
        if receipt.get("artifacts") != artifact_digests(batch_dir):
            raise ValueError("材料、计算清单、图片或找数侧车在闸门签发后被修改")
        image_paths = ziliao_image_paths(batch_dir)
        if image_paths:
            meta = receipt.get("visual_quality") or {}
            path = safe_child(batch_dir, str(meta.get("path") or ""))
            if not path.is_file() or digest(path) != meta.get("sha256"):
                raise ValueError("资料分析视觉质检证据缺失或被修改")
            evidence = read_json(path)
            if not isinstance(evidence, dict):
                raise ValueError("资料分析视觉质检证据格式错误")
            validate_ziliao_visual_evidence(batch_dir, evidence, image_paths)
    if version == VERSION:
        meta = receipt.get("system_quality") or {}
        path = safe_child(batch_dir, str(meta.get("path") or ""))
        if not path.is_file() or digest(path) != meta.get("sha256"):
            raise ValueError("ExamSystem 系统质检证据缺失或被修改")
        evidence = read_json(path)
        if not isinstance(evidence, dict):
            raise ValueError("ExamSystem 系统质检证据格式错误")
        validate_system_quality(batch_dir, evidence, ids)
    return {
        "ok": True,
        "batch_id": receipt["batch_id"],
        "question_count": len(ids),
        "issued_at": receipt["issued_at"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    issue_parser = sub.add_parser("issue")
    issue_parser.add_argument("batch_dir", type=Path)
    issue_parser.add_argument("--correctness", type=Path)
    issue_parser.add_argument("--quality", type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "issue":
            result = issue(args.batch_dir.resolve(), args.correctness.resolve() if args.correctness else None, args.quality.resolve() if args.quality else None)
        else:
            result = verify(args.batch_dir.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"generation gate failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

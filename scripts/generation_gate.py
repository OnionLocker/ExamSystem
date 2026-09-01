#!/usr/bin/env python3
"""签发并校骄1�71ￄ1�771ￄ1�71ￄ1�777 AI 题组正确怄1�71ￄ1�771ￄ1�71ￄ1�777/质量闸门回执〄1�71ￄ1�771ￄ1�71ￄ1�777"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from kaodian_taxonomy import (
    question_primary_tag,
    validate_ai_primary_tag,
    validate_ziliao_paper_answers,
)
from normalize_ai_batch import generated_questions, normalize_batch, validate_daily_paper_order
from panduan_pack import is_panduan_paper, validate_panduan_paper
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
        raise ValueError("资料分析多模态视觉质棢�未��过")
    if evidence.get("batch_id") != read_json(batch_dir / "manifest.json").get("batch_id"):
        raise ValueError("视觉质检 batch_id 不一臄1�71ￄ1�771ￄ1�71ￄ1�777")
    if int(evidence.get("mobile_width") or 0) != 320 or "flash" not in str(evidence.get("model") or "").lower():
        raise ValueError("视觉质检必须甄1�71ￄ1�771ￄ1�71ￄ1�777 Gemini Flash 同时棢�查原图和 320px 考生视图")
    expected = {str(path.relative_to(batch_dir.resolve())): digest(path) for path in image_paths}
    results = evidence.get("images") or []
    actual = {str(item.get("path") or ""): item for item in results if isinstance(item, dict)}
    if set(actual) != set(expected):
        raise ValueError("视觉质检未覆盖批次全部资料分析图牄1�71ￄ1�771ￄ1�71ￄ1�777")
    required = ("complete", "no_overlap", "units_mapped", "mobile_readable", "context_consistent")
    for relative, sha in expected.items():
        item = actual[relative]
        checks = item.get("checks") or {}
        if item.get("sha256") != sha or str(item.get("verdict") or "").upper() != "PASS":
            raise ValueError(f"视觉质检图片未��过或已变化：{relative}")
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
        raise ValueError(f"Gemini Flash 多模态视觉质棢�失败：{detail[-1200:]}")
    evidence = read_json(output)
    if not isinstance(evidence, dict):
        raise ValueError("视觉质检证据必须昄1�71ￄ1�771ￄ1�71ￄ1�777 JSON 对象")
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
                    raise ValueError(f"参��上下文不存在或并非系统生成：{context_id}")
                if row["role"] != role or row["digest_version"] != marker:
                    raise ValueError(f"参��上下文角色或版本不丢�致：{context_id}")
                target = json.loads(row["target"] or "{}")
                for qid in item.get("question_ids") or []:
                    question = by_question.get(str(qid))
                    if question is None:
                        raise ValueError(f"参��上下文覆盖不存在的题：{qid}")
                    if target.get("category") != question.get("category"):
                        raise ValueError(f"参��上下文顶层模块与题目不丢�致：{context_id}/{qid}")
                    if question.get("sub_category") and target.get("sub_category") != question.get("sub_category"):
                        raise ValueError(f"参��上下文细分类与题目不一致：{context_id}/{qid}")
                    if target.get("tag") != question_primary_tag(question):
                        raise ValueError(f"参��上下文主标签与题目不一致：{context_id}/{qid}")
                    if question_images := (question.get("stem_images") or any(
                        option.get("images") for option in question.get("options") or []
                    )):
                        if target.get("image_mode") != "yes":
                            raise ValueError(f"带图题必须使甄1�71ￄ1�771ￄ1�71ￄ1�777 images=yes 参��上下文：{context_id}/{qid}")
                recorded_ids = json.loads(row["reference_ids"] or "[]")
                if recorded_ids != (item.get("reference_ids") or []):
                    raise ValueError(f"参��上下文题目列表不一致：{context_id}")
                if row["batch_id"] and row["batch_id"] != manifest.get("batch_id"):
                    raise ValueError(f"参��上下文已绑定其他批次：{context_id}")
                references = []
                for ref_id in recorded_ids:
                    ref = connection.execute(
                        "SELECT external_id, category, sub_category, question_type, content, "
                        "stem_images, options, correct_answer, explanation_images, difficulty, "
                        "tags, source, year, region FROM reference_questions WHERE external_id = ?",
                        (ref_id,),
                    ).fetchone()
                    if ref is None:
                        raise ValueError(f"参��题不存在：{ref_id}")
                    if match_level(
                        ref,
                        str(target.get("category") or ""),
                        str(target.get("sub_category") or ""),
                        str(target.get("tag") or ""),
                    ) < 2:
                        raise ValueError(f"参��题模块或��点与上下文不匹配：{context_id}/{ref_id}")
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
        raise ValueError("v3 批次必须圄1�71ￄ1�771ￄ1�71ￄ1�777 generation.batch_constraints 固化用户要求")
    generated = [question for question in questions if not is_zhenti_question(question)]
    if constraints.get("all_original") is True and len(generated) != len(questions):
        raise ValueError("全原创批次不得混入真预1�71ￄ1�771ￄ1�71ￄ1�777")
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
        raise ValueError(f"答案位置分布不符各1�71ￄ1�771ￄ1�71ￄ1�777 batch_constraints：{answers}")

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
        raise ValueError(f"ExamSystem 系统质检未��过：{rejected}")
    manifest = read_json(batch_dir / "manifest.json")
    if evidence.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("系统质检 batch_id 不一臄1�71ￄ1�771ￄ1�71ￄ1�777")
    if "flash" not in str(evidence.get("model") or "").lower():
        raise ValueError("系统质检必须甄1�71ￄ1�771ￄ1�71ￄ1�777 Gemini Flash 执行")
    if evidence.get("questions_sha256") != digest(batch_dir / "questions.json"):
        raise ValueError("系统质检后的 questions.json 已变匄1�71ￄ1�771ￄ1�71ￄ1�777")
    if evidence.get("manifest_sha256") != digest(batch_dir / "manifest.json"):
        raise ValueError("系统质检后的 manifest.json 已变匄1�71ￄ1�771ￄ1�71ￄ1�777")
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
            raise ValueError(f"系统风格质量棢�查未通过：{qid}")


def run_system_quality_gate(batch_dir: Path, ids: list[str]) -> Path:
    output = batch_dir / "evidence" / "system-quality.json"
    command = [
        sys.executable, str(Path(__file__).with_name("quality_orchestrator.py")),
        str(batch_dir), "--output", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        detail = (result.stdout or result.stderr).strip()
        raise ValueError(f"ExamSystem 系统质检失败：{detail[-2000:]}")
    evidence = read_json(output)
    if not isinstance(evidence, dict):
        raise ValueError("系统质检证据必须昄1�71ￄ1�771ￄ1�71ￄ1�777 JSON 对象")
    validate_system_quality(batch_dir, evidence, ids)
    return output


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
        raise ValueError("questions.json 必须是数组1�71ￄ1�771ￄ1�71ￄ1�777")
    ids = [str(question.get("external_id") or "") for question in questions]
    if not ids or any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("questions.json external_id 缺失或重处1�71ￄ1�771ￄ1�71ￄ1�777")
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            raise ValueError(f"questions[{index}] 必须是对豄1�71ￄ1�771ￄ1�71ￄ1�777")
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
        raise ValueError(f"{kind} evidence verdict 必须丄1�71ￄ1�771ￄ1�71ￄ1�777 PASS")
    ids = [str(value) for value in evidence.get("question_ids") or []]
    if set(ids) != set(expected_ids) or len(ids) != len(expected_ids):
        raise ValueError(f"{kind} evidence 未覆盖本批全部题")
    if kind == "quality":
        contexts = {str(value) for value in evidence.get("evaluation_context_ids") or []}
        if contexts != (expected_context_ids or set()):
            raise ValueError("quality evidence 的1�71ￄ1�771ￄ1�71ￄ1�777 evaluation_context_ids 丄1�71ￄ1�771ￄ1�71ￄ1�777 manifest 不一臄1�71ￄ1�771ￄ1�71ￄ1�777")
    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{kind} evidence 必须列出实际棢�查项")


def issue(
    batch_dir: Path,
    correctness_path: Path | None = None,
    quality_path: Path | None = None,
) -> dict:
    manifest_path = batch_dir / "manifest.json"
    questions_path = batch_dir / "questions.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("kind") != "ai-generated":
        raise ValueError("只有 kind=ai-generated 的批次需要签叄1�71ￄ1�771ￄ1�71ￄ1�777")
    normalize_batch(batch_dir)
    manifest = read_json(manifest_path)
    ids = question_ids(batch_dir)
    questions = read_json(questions_path)
    validate_batch_constraints(manifest, questions)
    validate_context_coverage(manifest, ids, questions)
    context_digests = reference_context_digests(batch_dir, manifest)
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
        raise ValueError(f"缺少 {RECEIPT}；AI 生成批次未完成可审计双闸闄1�71ￄ1�771ￄ1�71ￄ1�777")
    receipt = read_json(receipt_path)
    manifest_path = batch_dir / "manifest.json"
    questions_path = batch_dir / "questions.json"
    if not isinstance(receipt, dict) or receipt.get("version") not in LEGACY_VERSIONS | {VERSION}:
        raise ValueError("闸门回执版本不支挄1�71ￄ1�771ￄ1�71ￄ1�777")
    manifest = read_json(manifest_path)
    ids = question_ids(batch_dir)
    if receipt.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("闸门回执 batch_id 不一臄1�71ￄ1�771ￄ1�71ￄ1�777")
    if receipt.get("question_ids") != ids:
        raise ValueError("闸门回执题目列表不一臄1�71ￄ1�771ￄ1�71ￄ1�777")
    if receipt.get("manifest_sha256") != digest(manifest_path):
        raise ValueError("manifest 在闸门签发后被修攄1�71ￄ1�771ￄ1�71ￄ1�777")
    if receipt.get("questions_sha256") != digest(questions_path):
        raise ValueError("questions 在闸门签发后被修攄1�71ￄ1�771ￄ1�71ￄ1�777")
    version = receipt.get("version")
    if version == VERSION and receipt.get("reference_contexts") != reference_context_digests(batch_dir, manifest):
        raise ValueError("参��上下文或其真题内容在闸门签发后被修攄1�71ￄ1�771ￄ1�71ￄ1�777")
    if version in LEGACY_VERSIONS:
        for kind in ("correctness", "quality"):
            meta = receipt.get(kind) or {}
            path = safe_child(batch_dir, str(meta.get("path") or ""))
            if not path.is_file() or digest(path) != meta.get("sha256"):
                raise ValueError(f"{kind} 证据缺失或被修改")
    if version in {2, VERSION}:
        if receipt.get("artifacts") != artifact_digests(batch_dir):
            raise ValueError("材料、计算清单��图片或找数侧车在闸门签发后被修攄1�71ￄ1�771ￄ1�71ￄ1�777")
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

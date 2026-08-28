#!/usr/bin/env python3
"""签发并校验 AI 题组正确性/质量闸门回执。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from kaodian_taxonomy import question_primary_tag, validate_ai_primary_tag


VERSION = 1
RECEIPT = ".gate.json"


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        try:
            validate_ai_primary_tag(
                question_primary_tag(question),
                str(question.get("category") or ""),
            )
        except ValueError as exc:
            ident = question.get("external_id") or index
            raise ValueError(f"questions[{ident}] {exc}") from exc
    return ids


def validate_evidence(
    evidence: dict,
    expected_ids: list[str],
    kind: str,
    expected_context_ids: set[str] | None = None,
) -> None:
    if str(evidence.get("verdict") or "").upper() != "PASS":
        raise ValueError(f"{kind} evidence verdict 必须为 PASS")
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


def issue(batch_dir: Path, correctness_path: Path, quality_path: Path) -> dict:
    manifest_path = batch_dir / "manifest.json"
    questions_path = batch_dir / "questions.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("kind") != "ai-generated":
        raise ValueError("只有 kind=ai-generated 的批次需要签发")
    ids = question_ids(batch_dir)
    generation = manifest.get("generation") or {}
    expected_contexts = {
        str(item.get("context_id"))
        for item in generation.get("evaluation_contexts") or []
        if item.get("context_id")
    }
    correctness = read_json(correctness_path)
    quality = read_json(quality_path)
    if not isinstance(correctness, dict) or not isinstance(quality, dict):
        raise ValueError("闸门证据必须是 JSON 对象")
    validate_evidence(correctness, ids, "correctness")
    validate_evidence(quality, ids, "quality", expected_contexts)

    receipt = {
        "version": VERSION,
        "batch_id": manifest.get("batch_id"),
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha256": digest(manifest_path),
        "questions_sha256": digest(questions_path),
        "question_ids": ids,
        "correctness": {
            "path": str(correctness_path.relative_to(batch_dir)),
            "sha256": digest(correctness_path),
            "route": correctness.get("route"),
        },
        "quality": {
            "path": str(quality_path.relative_to(batch_dir)),
            "sha256": digest(quality_path),
            "evaluation_context_ids": sorted(expected_contexts),
        },
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
    if not isinstance(receipt, dict) or receipt.get("version") != VERSION:
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
    for kind in ("correctness", "quality"):
        meta = receipt.get(kind) or {}
        path = safe_child(batch_dir, str(meta.get("path") or ""))
        if not path.is_file() or digest(path) != meta.get("sha256"):
            raise ValueError(f"{kind} 证据缺失或被修改")
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
    issue_parser.add_argument("--correctness", type=Path, required=True)
    issue_parser.add_argument("--quality", type=Path, required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "issue":
            result = issue(args.batch_dir.resolve(), args.correctness.resolve(), args.quality.resolve())
        else:
            result = verify(args.batch_dir.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"generation gate failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

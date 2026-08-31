#!/usr/bin/env python3
"""Regression tests for the ExamSystem-owned v3 quality gate."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import generation_gate
import quality_orchestrator as qo


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def question(qid: str, category: str, sub_category: str, tag: str, answer: str = "A") -> dict:
    return {
        "external_id": qid,
        "category": category,
        "sub_category": sub_category,
        "question_type": "single",
        "stem": "Test stem",
        "options": [
            {"key": "A", "text": "one"},
            {"key": "B", "text": "two"},
            {"key": "C", "text": "three"},
            {"key": "D", "text": "four"},
        ],
        "answer": answer,
        "explanation": "Independent explanation",
        "tags": [tag],
    }


def test_routes_and_calculations(root: Path) -> None:
    yanyu = question(
        "Q-C", qo.CAT_YANYU, "", f"{qo.CAT_YANYU}-\u7247\u6bb5\u9605\u8bfb-\u4e3b\u65e8\u6982\u62ec"
    )
    logic = question(
        "Q-A", qo.CAT_PANDUAN, qo.SUB_LOGIC,
        f"{qo.CAT_PANDUAN}-{qo.SUB_LOGIC}-\u7ffb\u8bd1\u63a8\u7406",
    )
    quantity = question(
        "Q-B", qo.CAT_SHULIANG, "\u6570\u5b66\u8fd0\u7b97",
        f"{qo.CAT_SHULIANG}-\u6570\u5b66\u8fd0\u7b97-\u65b9\u7a0b\u95ee\u9898",
        "B",
    )
    image_q = question(
        "Q-D", qo.CAT_PANDUAN, qo.SUB_SCIENCE,
        f"{qo.CAT_PANDUAN}-{qo.SUB_SCIENCE}-\u529b\u5b66",
    )
    image_q["stem_images"] = ["images/q-d.png"]
    assert [qo.classify(item) for item in (yanyu, logic, quantity, image_q)] == list("CABD")

    assert qo.safe_eval("sum([10, 20]) / 3") == 10
    try:
        qo.safe_eval("(1).__class__")
        raise AssertionError("unsafe attribute access was accepted")
    except ValueError:
        pass

    write_json(
        root / "calculations.json",
        {
            "questions": [
                {
                    "question_id": "Q-B",
                    "correct": "100 / 2",
                    "options": {"A": "40", "B": "50", "C": "60", "D": "70"},
                    "tolerance": 0.001,
                }
            ]
        },
    )
    result = qo.run_route_b(root, [quantity])["Q-B"]
    assert result["verdict"] == "PASS"
    write_json(
        root / "calculations.json",
        {
            "questions": [
                {
                    "question_id": "Q-B",
                    "correct": "50",
                    "options": {"A": "50", "B": "50", "C": "60", "D": "70"},
                }
            ]
        },
    )
    assert qo.run_route_b(root, [quantity])["Q-B"]["verdict"] == "REJECT"


def test_blind_conflict_and_image_requirements(root: Path) -> None:
    verbal = question(
        "Q-C", qo.CAT_YANYU, "", f"{qo.CAT_YANYU}-\u7247\u6bb5\u9605\u8bfb-\u4e3b\u65e8\u6982\u62ec"
    )
    calls = [
        {"questions": [{"id": "Q-C", "answer": "A", "also_valid": [], "verdict": "PASS"}]},
        {"questions": [{"id": "Q-C", "answer": "B", "also_valid": [], "verdict": "PASS"}]},
    ]
    with patch.object(qo, "call_flash", side_effect=calls):
        assert qo.run_route_c([verbal])["Q-C"]["verdict"] == "REJECT"

    image_path = root / "images" / "science.png"
    image_path.parent.mkdir()
    Image.new("RGB", (640, 360), "white").save(image_path)
    science = question(
        "Q-D", qo.CAT_PANDUAN, qo.SUB_SCIENCE,
        f"{qo.CAT_PANDUAN}-{qo.SUB_SCIENCE}-\u529b\u5b66",
    )
    science["stem_images"] = ["images/science.png"]
    calls = [
        {"questions": [{"id": "Q-D", "answer": "A", "also_valid": [], "verdict": "PASS"}]},
        {"questions": [{"id": "Q-D", "verdict": "PASS", "issues": []}]},
    ]
    with patch.object(qo, "call_flash", side_effect=calls):
        assert qo.run_route_d(root, [science])["Q-D"]["verdict"] == "REJECT"
    write_json(
        root / "image-specs.json",
        {"questions": [{"question_id": "Q-D", "image_facts": ["one line"], "must_derive": ["direction"]}]},
    )
    with patch.object(qo, "call_flash", side_effect=RuntimeError("API down")):
        try:
            qo.run_route_d(root, [science])
            raise AssertionError("Gemini failure did not close the gate")
        except RuntimeError:
            pass


def test_context_and_v3_tamper(root: Path) -> None:
    tag = f"{qo.CAT_YANYU}-\u7247\u6bb5\u9605\u8bfb-\u4e3b\u65e8\u6982\u62ec"
    target = json.dumps(
        {
            "category": qo.CAT_YANYU,
            "sub_category": None,
            "tag": tag,
            "image_mode": "any",
        },
        ensure_ascii=False,
    )
    db_path = root / "exam.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE reference_context_runs (
          context_id TEXT PRIMARY KEY, role TEXT, digest_version TEXT, target TEXT,
          reference_ids TEXT, batch_id TEXT
        );
        CREATE TABLE reference_questions (
          external_id TEXT PRIMARY KEY, category TEXT, sub_category TEXT,
          question_type TEXT, content TEXT, stem_images TEXT, options TEXT,
          correct_answer TEXT, explanation_images TEXT, difficulty INTEGER,
          tags TEXT, source TEXT, year INTEGER, region TEXT
        );
        """
    )
    for ref_id in ("R1", "R2"):
        connection.execute(
            "INSERT INTO reference_questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ref_id, qo.CAT_YANYU, "", "single", "reference", "[]", "[]",
                "A", "[]", 3, json.dumps([tag], ensure_ascii=False), "test", 2026, "Guangdong",
            ),
        )
    connection.execute(
        "INSERT INTO reference_context_runs VALUES (?,?,?,?,?,NULL)",
        ("gen-1", "generate", "GONGKAO-STYLE-v1", target, '["R1"]'),
    )
    connection.execute(
        "INSERT INTO reference_context_runs VALUES (?,?,?,?,?,NULL)",
        ("eval-1", "evaluate", "GONGKAO-STYLE-v1", target, '["R2"]'),
    )
    connection.commit()
    connection.close()
    os.environ["EXAM_DB"] = str(db_path)

    qid = "quality-v3-Q001"
    item = question(qid, qo.CAT_YANYU, "", tag)
    manifest = {
        "batch_id": "quality-v3",
        "source": "test",
        "region": "Guangdong",
        "year": 2026,
        "kind": "ai-generated",
        "generation": {
            "style_marker": "GONGKAO-STYLE-v1",
            "batch_constraints": {
                "all_original": True,
                "question_count": 1,
                "tag_counts": {tag: 1},
                "no_images": True,
                "answer_max_per_letter": 1,
                "answer_min_letters": 1,
            },
            "generation_contexts": [
                {"context_id": "gen-1", "reference_ids": ["R1"], "question_ids": [qid]}
            ],
            "evaluation_contexts": [
                {"context_id": "eval-1", "reference_ids": ["R2"], "question_ids": [qid]}
            ],
        },
    }
    write_json(root / "manifest.json", manifest)
    write_json(root / "questions.json", [item])
    generation_gate.validate_batch_constraints(manifest, [item])
    generation_gate.validate_context_coverage(manifest, [qid])
    broken = json.loads(json.dumps(manifest))
    broken["generation"]["evaluation_contexts"][0]["reference_ids"] = ["R1"]
    try:
        generation_gate.validate_context_coverage(broken, [qid])
        raise AssertionError("reused generate/evaluate reference was accepted")
    except ValueError:
        pass

    evidence = {
        "version": 1,
        "kind": "examsystem-system-quality",
        "batch_id": "quality-v3",
        "model": "gemini-test-flash",
        "reviewed_at": "2026-08-31T00:00:00+00:00",
        "verdict": "PASS",
        "routes": {"A": 0, "B": 0, "C": 1, "D": 0},
        "questions_sha256": digest(root / "questions.json"),
        "manifest_sha256": digest(root / "manifest.json"),
        "results": [
            {
                "question_id": qid,
                "route": "C",
                "verdict": "PASS",
                "correctness": {"verdict": "PASS"},
                "quality": {"verdict": "PASS"},
            }
        ],
    }
    evidence_path = root / "evidence" / "system-quality.json"
    write_json(evidence_path, evidence)
    receipt = {
        "version": 3,
        "batch_id": "quality-v3",
        "issued_at": "2026-08-31T00:00:00+00:00",
        "manifest_sha256": digest(root / "manifest.json"),
        "questions_sha256": digest(root / "questions.json"),
        "artifacts": generation_gate.artifact_digests(root),
        "reference_contexts": generation_gate.reference_context_digests(root, manifest),
        "question_ids": [qid],
        "system_quality": {
            "path": "evidence/system-quality.json",
            "sha256": digest(evidence_path),
            "model": "gemini-test-flash",
        },
    }
    write_json(root / ".gate.json", receipt)
    assert generation_gate.verify(root)["ok"] is True

    item["stem"] = "tampered after signing"
    write_json(root / "questions.json", [item])
    try:
        generation_gate.verify(root)
        raise AssertionError("post-signing question tamper was accepted")
    except ValueError:
        pass


def test_verbal_local_quality_regressions() -> None:
    bad = {
        "external_id": "Y001",
        "category": "\u8a00\u8bed\u7406\u89e3",
        "stem": "\u8fd1\u5e74\u6765\uff0c\u884c\u4e1a\u4ece\u201c\u91ce\u86ee\u751f\u957f\u201d\u8d70\u5411\u201c\u7cbe\u8015\u7ec6\u4f5c\u201d\uff0c\u9700\u8981\u53cc\u5411\u53d1\u529b\u3002",
        "options": [
            {"key": "A", "text": "\u884c\u4e1a\u9700\u8981\u53cc\u5411\u53d1\u529b"},
            {"key": "B", "text": "\u6240\u6709\u95ee\u9898\u90fd\u5df2\u89e3\u51b3"},
            {"key": "C", "text": "\u5fc5\u987b\u4ec5\u51ed\u6d41\u91cf\u53d1\u5c55"},
            {"key": "D", "text": "\u5b8c\u5168\u4e0e\u6b64\u65e0\u5173"},
        ],
        "answer": "A",
        "analysis": "",
    }
    issues = qo.local_quality_issues(bad)
    assert "generated item has no analysis" in issues
    assert "all distractors rely on giveaway extreme words" in issues


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_routes_and_calculations(Path(temp) / "calc")
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_blind_conflict_and_image_requirements(Path(temp))
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_context_and_v3_tamper(Path(temp))
    test_verbal_local_quality_regressions()
    print("quality gate regression: ok")


if __name__ == "__main__":
    main()

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
import pytest

import generation_gate
import quality_orchestrator as qo


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


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
    eval_only = json.loads(json.dumps(manifest))
    eval_only["generation"].pop("generation_contexts", None)
    generation_gate.validate_context_coverage(eval_only, [qid])
    no_eval = json.loads(json.dumps(manifest))
    no_eval["generation"]["evaluation_contexts"] = []
    try:
        generation_gate.validate_context_coverage(no_eval, [qid])
        raise AssertionError("empty evaluate was accepted")
    except ValueError:
        pass
    contour_tag = "%s-%s-等高线" % (qo.CAT_PANDUAN, qo.SUB_SCIENCE)
    contour = question("Q-contour", qo.CAT_PANDUAN, qo.SUB_SCIENCE, contour_tag)
    mock = json.loads(json.dumps(manifest))
    mock["generation"]["evaluation_contexts"] = []
    mock["generation"].pop("generation_contexts", None)
    with patch.object(generation_gate, "question_needs_evaluate_holdout", return_value=False):
        generation_gate.validate_context_coverage(mock, ["Q-contour"], [contour])
    try:
        with patch.object(generation_gate, "question_needs_evaluate_holdout", return_value=True):
            generation_gate.validate_context_coverage(mock, ["Q-contour"], [contour])
        raise AssertionError("holdout-required empty evaluate was accepted")
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


def test_translation_echo_local_quality() -> None:
    echo = {
        "external_id": "F001",
        "category": "判断推理",
        "sub_category": "逻辑判断",
        "tags": ["判断推理-翻译推理-假言命题"],
        "stem": (
            "如果某批货物获得国际海关认证，则免于现场查验。"
            "现已知：某批进口货物申请了国际海关认证且免于现场查验。"
            "根据以上信息，可以推出的是："
        ),
        "options": [
            {"key": "A", "text": "该批货物走绿色通道"},
            {"key": "B", "text": "该批货物进入保税仓储"},
            {"key": "C", "text": "该批货物未接受现场查验"},
            {"key": "D", "text": "若未接受现场查验，则进入保税仓储"},
        ],
        "answer": "C",
        "analysis": "根据确定事实，C项必然为真。",
    }
    issues = qo.local_quality_issues(echo)
    assert any("restates" in item for item in issues), issues

    ok = {
        "external_id": "F002",
        "category": "判断推理",
        "sub_category": "逻辑判断",
        "tags": ["判断推理-翻译推理-逆否命题"],
        "stem": (
            "只有设立实验室才能立项。现已知：某项目未设立实验室。"
            "由此可以推出："
        ),
        "options": [
            {"key": "A", "text": "该项目已研发新产品"},
            {"key": "B", "text": "该项目未立项"},
            {"key": "C", "text": "该项目设立了实验室"},
            {"key": "D", "text": "该项目已经立项"},
        ],
        "answer": "B",
        "analysis": "立项→实验室，否后则否前。",
    }
    issues = qo.local_quality_issues(ok)
    assert not any("restates" in item for item in issues), issues


def test_notation_stem_mismatch_and_kepui_giveaway() -> None:
    mixed = {
        "external_id": "K003",
        "category": "科学推理",
        "sub_category": "科学推理",
        "tags": ["科学推理-压强与浮力-液体压强"],
        "stem": "甲、乙两容器盛有深度相同的液体。",
        "options": [
            {"key": "A", "text": "p_甲 < p_乙"},
            {"key": "B", "text": "p_甲 > p_乙"},
            {"key": "C", "text": "两者相等"},
            {"key": "D", "text": "无法判断"},
        ],
        "answer": "B",
        "analysis": "ρ_A > ρ_B，所以 G_A > G_B。",
    }
    issues = qo.local_quality_issues(mixed)
    assert "notation_stem_mismatch" in issues, issues

    giveaway = {
        "external_id": "K004",
        "category": "科学推理",
        "sub_category": "科学推理",
        "tags": ["科学推理-生物-人体调节"],
        "stem": "反射弧①–⑤如图。",
        "options": [
            {"key": "A", "text": "①是感受器"},
            {"key": "B", "text": "传导方向是⑤→①"},
            {"key": "C", "text": "可判断损伤部位一定是①"},
            {"key": "D", "text": "属于条件反射"},
        ],
        "answer": "A",
        "analysis": "②有神经节，①为感受器。",
    }
    issues = qo.local_quality_issues(giveaway)
    assert "giveaway extreme-word distractor" in issues, issues


def test_quality_rules_skip_feedback_archive() -> None:
    text = qo.quality_rules_text({}, [{"category": "科学推理"}])
    assert "六条评分项" in text
    assert "notation_stem_mismatch" in text
    assert "用户反馈沉淀" not in text
    assert "质量审查者 prompt 模板" not in text
    assert "如果无法读取，质量闸门不得判为通过" not in text


def test_verbal_single_extreme_is_not_giveaway() -> None:
    item = {
        "external_id": "Y002",
        "category": "言语理解与表达",
        "stem": "这段文字意在强调的是：",
        "options": [
            {"key": "A", "text": "行业需要双向发力"},
            {"key": "B", "text": "一定是政策推动的结果"},
            {"key": "C", "text": "技术迭代改变了生产结构"},
            {"key": "D", "text": "区域差异仍将长期存在"},
        ],
        "answer": "A",
        "analysis": "文段围绕双向发力展开。",
    }
    issues = qo.local_quality_issues(item)
    assert "giveaway extreme-word distractor" not in issues
    assert "all distractors rely on giveaway extreme words" not in issues


def test_mechanical_notation_skips_flash() -> None:
    item = {
        "external_id": "K-MECH",
        "category": "科学推理",
        "sub_category": "科学推理",
        "tags": ["科学推理-压强与浮力-液体压强"],
        "stem": "甲、乙两容器盛有深度相同的液体。",
        "options": [
            {"key": "A", "text": "p_甲 < p_乙"},
            {"key": "B", "text": "p_甲 > p_乙"},
            {"key": "C", "text": "两者相等"},
            {"key": "D", "text": "无法判断"},
        ],
        "answer": "B",
        "analysis": "ρ_A > ρ_B，所以 G_A > G_B。",
    }
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        root = Path(temp)
        with patch.object(qo, "call_flash", side_effect=RuntimeError("flash must not run")):
            style = qo.run_quality(root, {}, [item])
    assert style["K-MECH"]["verdict"] == "REJECT", style
    assert style["K-MECH"]["review"]["skipped"] == "mechanical"
    assert "notation_stem_mismatch" in style["K-MECH"]["issues"]


def test_syllabus_mock_holdout_lookup_does_not_crash() -> None:
    contour_tag = "%s-%s-等高线" % (qo.CAT_PANDUAN, qo.SUB_SCIENCE)
    contour = question("Q-contour", qo.CAT_PANDUAN, qo.SUB_SCIENCE, contour_tag)
    contour["stem_images"] = ["images/contour.png"]
    needed = generation_gate.question_needs_evaluate_holdout(contour)
    assert needed is False
    generation_gate.validate_context_coverage(
        {"generation": {"evaluation_contexts": []}},
        ["Q-contour"],
        [contour],
    )
    generation_gate.validate_context_coverage(
        {
            "generation": {
                "evaluation_contexts": [
                    {
                        "context_id": "",
                        "skipped": "no_holdout_syllabus_mock",
                        "question_ids": ["Q-contour"],
                        "reference_ids": [],
                    }
                ]
            }
        },
        ["Q-contour"],
        [contour],
    )


def test_syllabus_mock_reference_quality_passes() -> None:
    question = {
        "external_id": "Q-contour",
        "category": qo.CAT_PANDUAN,
        "sub_category": qo.SUB_SCIENCE,
        "stem": "contour",
        "tags": ["%s-%s-等高线" % (qo.CAT_PANDUAN, qo.SUB_SCIENCE)],
    }
    result = qo.run_reference_quality({"generation": {"evaluation_contexts": []}}, [question])
    assert result["verdict"] == "PASS", result
    assert result["results"][0]["review"]["skipped"] == "no_holdout_syllabus_mock"


def test_reference_quality_one_relevant_is_enough() -> None:
    question = {
        "external_id": "Q6",
        "category": qo.CAT_PANDUAN,
        "sub_category": qo.SUB_LOGIC,
        "stem": "strengthen",
        "tags": ["%s-%s-strengthen" % (qo.CAT_PANDUAN, qo.SUB_LOGIC)],
    }
    manifest = {
        "generation": {
            "evaluation_contexts": [
                {
                    "question_ids": ["Q6"],
                    "reference_ids": ["R-weak", "R-strong"],
                }
            ]
        }
    }
    flash = {
        "questions": [
            {
                "id": "Q6",
                "verdict": "REJECT",
                "references": [
                    {"id": "R-weak", "relevant": False, "reason": "weaken"},
                    {"id": "R-strong", "relevant": True, "reason": "strengthen"},
                ],
            }
        ]
    }
    fake_refs = {
        "Q6": [
            {"external_id": "R-weak"},
            {"external_id": "R-strong"},
        ]
    }
    with patch.object(qo, "evaluation_references", return_value=fake_refs), patch.object(
        qo, "call_flash", return_value=flash
    ):
        result = qo.run_reference_quality(manifest, [question])
    assert result["verdict"] == "PASS"
    assert result["results"][0]["verdict"] == "PASS"


def test_spatial_drill_skips_flash(root: Path) -> None:
    image = root / "images" / "q.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 200), "white").save(image)
    item = question(
        "Q-S",
        qo.CAT_PANDUAN,
        qo.SUB_GRAPH,
        f"{qo.CAT_PANDUAN}-{qo.SUB_GRAPH}-\u7a7a\u95f4\u7c7b",
        "B",
    )
    item["stem_images"] = ["images/q.png"]
    item["analysis"] = "computed"
    write_json(
        root / "manifest.json",
        {"generation": {"batch_constraints": {"spatial_drill": True, "answer_max_per_letter": 4}}},
    )
    write_json(
        root / "image-specs.json",
        {"questions": [{"question_id": "Q-S", "image_only_facts": ["net"], "must_derive": ["fold"]}]},
    )
    with patch.object(qo, "call_flash", side_effect=RuntimeError("flash must not run")):
        d = qo.run_route_d(root, [item])
        style = qo.run_quality(root, json.loads((root / "manifest.json").read_text()), [item])
        batch = qo.run_batch_quality(root, json.loads((root / "manifest.json").read_text()), [item])
    assert d["Q-S"]["verdict"] == "PASS", d
    assert style["Q-S"]["verdict"] == "PASS", style
    assert batch["verdict"] == "PASS", batch


def _quality_pass(qid: str, answer: str = "A") -> dict:
    wrong = [key for key in "ABCD" if key != answer]
    return {
        "questions": [
            {
                "id": qid,
                "verdict": "PASS",
                "score": 11,
                "zero_items": [],
                "hard_fail": [],
                "regression_fail": [],
                "module_match": True,
                "style_match": True,
                "facts_closed": True,
                "answer_unique": True,
                "distractor_paths": {key: f"wrong {key}" for key in wrong},
                "reference_ids": [],
            }
        ]
    }


def _program_kepui_item(root: Path, stem: str, svg_text: str) -> dict:
    image = root / "images" / "q.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1400, 700), "white").save(image)
    image.with_suffix(".svg").write_text(svg_text, encoding="utf-8")
    item = question("Q-P", "科学推理", "科学推理", "科学推理-地理-锋面天气", "A")
    item["stem"] = stem
    item["stem_images"] = ["images/q.png"]
    item["analysis"] = "computed"
    write_json(root / "manifest.json", {"generation": {"batch_constraints": {"program_figures": True}}})
    write_json(
        root / "image-specs.json",
        {"questions": [{"question_id": "Q-P", "image_only_facts": ["冷气团楔"], "must_derive": ["冷锋"]}]},
    )
    return item


def test_program_figures_requires_flash(root: Path) -> None:
    item = _program_kepui_item(
        root,
        "如图所示为某锋面天气系统剖面示意图。",
        '<svg width="1100" height="620"><text font-size="32">冷气团</text></svg>',
    )
    calls = [
        {"questions": [{"id": "Q-P", "answer": "A", "also_valid": [], "verdict": "PASS"}]},
        {"questions": [{"id": "Q-P", "verdict": "PASS", "issues": []}]},
        _quality_pass("Q-P"),
        {
            "verdict": "PASS",
            "type_distribution_ok": True,
            "difficulty_distribution_ok": True,
            "reference_alignment_ok": True,
            "duplicate_groups": [],
            "issues": [],
        },
    ]
    with patch.object(qo, "call_flash", side_effect=calls) as mocked:
        d = qo.run_route_d(root, [item])
        style = qo.run_quality(root, json.loads((root / "manifest.json").read_text()), [item])
        batch = qo.run_batch_quality(root, json.loads((root / "manifest.json").read_text()), [item])
    assert mocked.call_count >= 3, mocked.call_count
    assert d["Q-P"]["verdict"] == "PASS", d
    assert style["Q-P"]["verdict"] == "PASS", style
    assert batch["verdict"] == "PASS", batch


def test_kepui_never_skips_flash_even_if_spatial_flag(root: Path) -> None:
    item = _program_kepui_item(
        root,
        "如图所示为某锋面天气系统剖面示意图。",
        '<svg width="1100" height="620"><text font-size="32">冷气团</text></svg>',
    )
    write_json(
        root / "manifest.json",
        {
            "generation": {
                "batch_constraints": {
                    "program_figures": True,
                    "spatial_drill": True,
                    "kepui_layout": "5_kepui_distinct_subjects",
                }
            }
        },
    )
    with patch.object(qo, "call_flash", side_effect=RuntimeError("flash must run")):
        try:
            qo.run_route_d(root, [item])
            raise AssertionError("科学推理 skipped Flash via spatial_drill")
        except RuntimeError as exc:
            assert "flash must run" in str(exc)
        try:
            qo.run_quality(root, json.loads((root / "manifest.json").read_text()), [item])
            raise AssertionError("科学推理 quality skipped Flash")
        except RuntimeError as exc:
            assert "flash must run" in str(exc)
        try:
            qo.run_batch_quality(root, json.loads((root / "manifest.json").read_text()), [item])
            raise AssertionError("科学推理 batch skipped Flash")
        except RuntimeError as exc:
            assert "flash must run" in str(exc)


def test_program_figures_cannot_skip_flash(root: Path) -> None:
    item = _program_kepui_item(
        root,
        "如图所示为某锋面天气系统剖面示意图。",
        '<svg width="1100" height="620"><text font-size="32">冷气团</text></svg>',
    )
    with patch.object(qo, "call_flash", side_effect=RuntimeError("flash must run")):
        try:
            qo.run_route_d(root, [item])
            raise AssertionError("program_figures skipped Flash")
        except RuntimeError as exc:
            assert "flash must run" in str(exc)


def test_program_figures_rejects_front_on_contour_even_if_flash_passes(root: Path) -> None:
    item = _program_kepui_item(
        root,
        "如图所示为某锋面天气系统剖面示意图。",
        '<svg width="1100" height="620"><text font-size="24">等高线（单位：m，等高距 50m）</text></svg>',
    )
    calls = [
        {"questions": [{"id": "Q-P", "answer": "A", "also_valid": [], "verdict": "PASS"}]},
        {"questions": [{"id": "Q-P", "verdict": "PASS", "issues": []}]},
        _quality_pass("Q-P"),
    ]
    with patch.object(qo, "call_flash", side_effect=calls):
        d = qo.run_route_d(root, [item])
        style = qo.run_quality(root, json.loads((root / "manifest.json").read_text()), [item])
    assert d["Q-P"]["verdict"] == "REJECT", d
    assert any("锋面题配了等高线图" in issue for issue in d["Q-P"]["issues"]), d
    assert style["Q-P"]["verdict"] == "REJECT", style


def test_graphic_bank_skips_flash_style(root: Path) -> None:
    image = root / "images" / "q.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1400, 700), "white").save(image)
    item = question(
        "Q-G",
        qo.CAT_PANDUAN,
        qo.SUB_GRAPH,
        f"{qo.CAT_PANDUAN}-{qo.SUB_GRAPH}-\u5206\u7c7b",
        "A",
    )
    item["stem_images"] = ["images/q.png"]
    write_json(root / "manifest.json", {"generation": {"batch_constraints": {}}})
    with patch.object(qo, "call_flash", side_effect=RuntimeError("flash must not run")):
        style = qo.run_quality(root, json.loads((root / "manifest.json").read_text()), [item])
    assert style["Q-G"]["verdict"] == "PASS", style
    assert style["Q-G"]["review"]["skipped"] == "graphic_bank"


def test_easy_tier_nits_low_difficulty_and_holdout_mismatch() -> None:
    assert qo._batch_nit_issue("认知难度显著偏低，不符合广东省考", True)
    assert qo._batch_nit_issue("第5题过于简单幼态化", True)
    assert qo._batch_nit_issue("全卷难度标签均为'easy'，缺乏梯度", False)
    assert qo._batch_nit_issue("逻辑判断全部缺少难度评定", False)
    assert qo._batch_nit_issue("All 15 items have identical difficulty = 2", False)
    assert qo._reference_mismatch_issue(
        "evaluation reference is sentence completion, whereas item 14 is rearrangement; conversely inverted"
    )
    assert qo._batch_nit_issue("整卷难度系数全部机械标为2，难度分布完全单一无梯度", False)
    assert qo._batch_nit_issue({"issue_type": "material_missing", "description": "统计文字资料材料缺失"}, True)
    assert qo._reference_mismatch_issue("题目参考真题跨知识点错配严重")
    assert qo._reference_mismatch_issue("绑定的真题评估参考考查题型不一致")
    assert qo._reference_mismatch_issue("第01题与该真题考点完全不符")
    assert qo._reference_mismatch_issue("关联的参考真题为语句填空题，考点与题型不匹配")
    assert qo._batch_nit_issue("材料一与材料三机械镜像复制，成套题干模板复用", True)
    assert qo._batch_nit_issue("削弱/加强题目存在套路化模版与高频套路", True)
    assert qo._batch_nit_issue("第07题与第14题存在骨架复刻与套路换皮（Reskin）", True)
    assert qo._batch_nit_issue({"kind": "repeated_skeleton", "detail": "论证骨架复用"}, True)
    assert qo._batch_nit_issue({"kind": "difficulty_monotony", "detail": "全部机械标注为难度2"}, False)
    assert qo._batch_nit_issue("难度设置扁平化且梯度失真：全部机械赋值为2", False)


def test_run_batch_quality_drops_easy_nits(root: Path) -> None:
    write_json(root / "manifest.json", {"difficulty_tier": "easy", "generation": {"batch_constraints": {}}})
    write_json(root / "materials.json", [{"external_id": "M1", "content": "2024年社会物流总额"}])
    item = question("Q1", qo.CAT_ZILIAO, qo.CAT_ZILIAO, f"{qo.CAT_ZILIAO}-\u589e\u957f\u91cf")
    item["material_id"] = "M1"
    review = {
        "verdict": "REJECT",
        "type_distribution_ok": False,
        "difficulty_distribution_ok": False,
        "reference_alignment_ok": False,
        "duplicate_groups": [],
        "issues": [
            "真实认知难度过低：部分题目过于简单幼态化",
            "第01题与该真题考点完全不符",
            {"issue_type": "material_missing", "description": "统计文字资料材料缺失"},
        ],
    }
    with patch.object(qo, "call_flash", return_value=review):
        result = qo.run_batch_quality(
            root,
            json.loads((root / "manifest.json").read_text()),
            [item],
        )
    assert result["verdict"] == "PASS", result
    assert result["review"]["issues"] == []


def test_question_verdict_is_per_item() -> None:
    correct = {"verdict": "PASS"}
    style = {"verdict": "PASS"}
    # batch-level reference REJECT must not poison a passing item
    ref_item = {"question_id": "Q1", "verdict": "PASS"}
    assert (
        correct.get("verdict")
        == style.get("verdict")
        == ref_item.get("verdict")
        == "PASS"
    )


def main() -> None:
    test_syllabus_mock_holdout_lookup_does_not_crash()
    test_syllabus_mock_reference_quality_passes()
    test_reference_quality_one_relevant_is_enough()
    test_question_verdict_is_per_item()
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_routes_and_calculations(Path(temp) / "calc")
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_blind_conflict_and_image_requirements(Path(temp))
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_context_and_v3_tamper(Path(temp))
    test_easy_tier_nits_low_difficulty_and_holdout_mismatch()
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_run_batch_quality_drops_easy_nits(Path(temp))
    test_verbal_local_quality_regressions()
    test_translation_echo_local_quality()
    test_notation_stem_mismatch_and_kepui_giveaway()
    test_quality_rules_skip_feedback_archive()
    test_verbal_single_extreme_is_not_giveaway()
    test_mechanical_notation_skips_flash()
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_spatial_drill_skips_flash(Path(temp))
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_program_figures_requires_flash(Path(temp))
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_program_figures_cannot_skip_flash(Path(temp))
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_kepui_never_skips_flash_even_if_spatial_flag(Path(temp))
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_program_figures_rejects_front_on_contour_even_if_flash_passes(Path(temp))
    with tempfile.TemporaryDirectory(prefix="quality-gate-test-") as temp:
        test_graphic_bank_skips_flash_style(Path(temp))
    print("quality gate regression: ok")


if __name__ == "__main__":
    main()

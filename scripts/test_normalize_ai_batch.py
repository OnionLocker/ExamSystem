#!/usr/bin/env python3
"""Tests for mechanical AI-batch normalization."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generation_gate
import normalize_ai_batch as nab
from kaodian_taxonomy import is_abcd_plus_one, validate_ziliao_paper_answers


CAT_SHULIANG = "\u6570\u91cf\u5173\u7cfb"
CAT_PANDUAN = "\u5224\u65ad\u63a8\u7406"
CAT_YANYU = "\u8a00\u8bed\u7406\u89e3\u4e0e\u8868\u8fbe"
CAT_ZILIAO = "\u8d44\u6599\u5206\u6790"
SUB_LOGIC = "\u903b\u8f91\u5224\u65ad"
TAG_EQ = CAT_SHULIANG + "-\u6570\u5b66\u8fd0\u7b97-\u65b9\u7a0b\u95ee\u9898"
TAG_LOGIC = CAT_PANDUAN + "-" + SUB_LOGIC + "-\u7ffb\u8bd1\u63a8\u7406"
TAG_YANYU = CAT_YANYU + "-\u7247\u6bb5\u9605\u8bfb-\u4e3b\u65e8\u6982\u62ec"
TAG_ZILIAO = CAT_ZILIAO + "-ABRX\u7c7b-\u57fa\u671f\u91cf\u8ba1\u7b97\u4e0e\u6bd4\u8f83"


def item(qid: str, category: str, tag: str, answer: str = "B", **extra) -> dict:
    question = {
        "external_id": qid,
        "category": category,
        "sub_category": extra.pop("sub_category", ""),
        "question_type": "single",
        "stem": "stem",
        "options": [
            {"key": "A", "text": "opt-A"},
            {"key": "B", "text": "opt-B"},
            {"key": "C", "text": "opt-C"},
            {"key": "D", "text": "opt-D"},
        ],
        "answer": answer,
        "explanation": extra.pop("explanation", "\u6545\u9009" + answer),
        "tags": [tag],
    }
    question.update(extra)
    return question


class NormalizeBatchTest(unittest.TestCase):
    def test_letter_plan_is_balanced(self):
        letters = nab.planned_letters(CAT_SHULIANG, 15, "seed-15")
        self.assertEqual(len(letters), 15)
        counts = {letter: letters.count(letter) for letter in "ABCD"}
        self.assertEqual(sum(counts.values()), 15)
        self.assertLessEqual(max(counts.values()), 4)
        self.assertEqual(len([k for k, n in counts.items() if n]), 4)

    def test_ziliao_plan_is_paper_layout_and_even(self):
        groups = nab.planned_ziliao_groups(__import__("random").Random("z"))
        validate_ziliao_paper_answers(groups)
        self.assertEqual(sum(1 for group in groups if is_abcd_plus_one(group)), 3)
        flat = [key for group in groups for key in group]
        self.assertEqual(len(flat), 20)
        self.assertLessEqual(max(flat.count(letter) for letter in "ABCD"), 5)

    def test_all_b_is_reshuffled_with_calculations(self):
        questions = [item(f"Q{i:02d}", CAT_SHULIANG, TAG_EQ, "B") for i in range(1, 16)]
        for question in questions:
            question["explanation"] = "\u6545\u9009B\uff0cA\u9879\u9519\u8bef"
        manifest = {
            "batch_id": "reshuffle-test",
            "kind": "ai-generated",
            "generation": {
                "batch_constraints": {
                    "all_original": True,
                    "question_count": 15,
                    "answer_max_per_letter": 4,
                    "answer_min_letters": 4,
                }
            },
        }
        calculations = {
            f"Q{i:02d}": {
                "question_id": f"Q{i:02d}",
                "correct": "50",
                "options": {"A": "40", "B": "50", "C": "60", "D": "70"},
            }
            for i in range(1, 16)
        }
        self.assertFalse(nab.answer_distribution_ok(manifest, questions))
        rewritten = nab.redistribute_answers(questions, manifest, calculations)
        self.assertGreater(rewritten, 0)
        self.assertTrue(nab.answer_distribution_ok(manifest, questions))
        moved = [q for q in questions if q["answer"] != "B"]
        self.assertTrue(moved)
        sample = moved[0]
        self.assertIn("opt-B", [opt["text"] for opt in sample["options"]])
        self.assertEqual(
            next(opt["text"] for opt in sample["options"] if opt["key"] == sample["answer"]),
            "opt-B",
        )
        self.assertTrue(sample["explanation"].startswith("\u6545\u9009" + sample["answer"]))
        spec = calculations[sample["external_id"]]
        self.assertEqual(spec["options"][sample["answer"]], "50")
        generation_gate.validate_batch_constraints(manifest, questions)

    def test_already_valid_answers_are_left_alone(self):
        letters = list("ABCDABCDABCDABC")
        questions = [
            item(f"Q{i:02d}", CAT_SHULIANG, TAG_EQ, letter)
            for i, letter in enumerate(letters, start=1)
        ]
        manifest = {
            "batch_id": "keep",
            "generation": {
                "batch_constraints": nab.default_answer_constraints(15)
            },
        }
        before = [q["answer"] for q in questions]
        self.assertEqual(nab.redistribute_answers(questions, manifest, {}), 0)
        self.assertEqual([q["answer"] for q in questions], before)

    def test_graphic_image_letters_are_not_reshuffled(self):
        questions = [
            item(f"G{i:02d}", CAT_PANDUAN, TAG_LOGIC, "A", sub_category="图形推理", stem_images=["images/g.png"])
            for i in range(5)
        ]
        for q in questions:
            q["options"] = [{"key": k, "text": k} for k in "ABCD"]
        questions.extend(
            item(f"L{i:02d}", CAT_PANDUAN, TAG_LOGIC, "A") for i in range(15)
        )
        manifest = {
            "batch_id": "graphic-lock",
            "generation": {"batch_constraints": nab.default_answer_constraints(20)},
        }
        nab.redistribute_answers(questions, manifest, {})
        self.assertEqual([q["answer"] for q in questions[:5]], ["A"] * 5)
        self.assertEqual([opt["text"] for opt in questions[0]["options"]], list("ABCD"))

    def test_ziliao_all_b_becomes_paper_layout(self):
        questions = []
        for material in range(1, 5):
            for n in range(1, 6):
                q = item(f"M{material}-Q{n}", CAT_ZILIAO, TAG_ZILIAO, "B")
                q["material_id"] = f"mat-{material}"
                questions.append(q)
        manifest = {
            "batch_id": "ziliao-test",
            "generation": {"batch_constraints": nab.default_answer_constraints(20)},
        }
        nab.redistribute_answers(questions, manifest, {})
        self.assertTrue(nab.answer_distribution_ok(manifest, questions))
        groups = []
        for material in range(1, 5):
            groups.append(
                [q["answer"] for q in questions if q["material_id"] == f"mat-{material}"]
            )
        validate_ziliao_paper_answers(groups)

    def test_bookkeeping_fills_safe_fields_only(self):
        logic = item("L1", CAT_PANDUAN, TAG_LOGIC, "A")
        logic["sub_category"] = ""
        logic["analysis"] = ""
        logic["explanation"] = "why A"
        self.assertIn("sub_category", nab.fill_bookkeeping(logic))
        self.assertEqual(logic["sub_category"], SUB_LOGIC)
        self.assertEqual(logic["analysis"], "why A")

        verbal = item("Y1", CAT_YANYU, TAG_YANYU, "A")
        verbal["sub_category"] = ""
        nab.fill_bookkeeping(verbal)
        self.assertFalse(verbal.get("sub_category"))

        copied = item("C1", CAT_SHULIANG, TAG_EQ, "")
        copied.pop("answer")
        copied["correct_answer"] = "C"
        copied["tags"] = []
        copied["knowledge_point"] = TAG_EQ
        nab.fill_bookkeeping(copied)
        self.assertEqual(copied["answer"], "C")
        self.assertEqual(copied["tags"], [TAG_EQ])

    def test_normalize_batch_writes_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            os.environ["EXAM_DB"] = str(root / "missing.db")
            self.addCleanup(os.environ.pop, "EXAM_DB", None)
            questions = [item(f"Q{i:02d}", CAT_SHULIANG, TAG_EQ, "B") for i in range(1, 16)]
            manifest = {"batch_id": "file-test", "kind": "ai-generated", "generation": {}}
            (root / "questions.json").write_text(
                json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (root / "calculations.json").write_text(
                json.dumps(
                    {
                        "questions": [
                            {
                                "question_id": f"Q{i:02d}",
                                "correct": "50",
                                "options": {"A": "40", "B": "50", "C": "60", "D": "70"},
                            }
                            for i in range(1, 16)
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            result = nab.normalize_batch(root)
            self.assertTrue(result["changed"])
            saved = json.loads((root / "questions.json").read_text(encoding="utf-8"))
            saved_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(nab.answer_distribution_ok(saved_manifest, saved))
            generation_gate.validate_batch_constraints(saved_manifest, saved)

    def test_stamp_daily_source_uses_batch_slug(self):
        questions = [item("K01", CAT_PANDUAN, "科学推理-力学-杠杆滑轮", "A")]
        questions[0]["source"] = "广东省考行测-判断推理-20260902"
        manifest = {
            "batch_id": "daily-20260902-kepui-abc",
            "source": "广东省考行测-判断推理-20260902",
        }
        nab.stamp_daily_source(manifest, questions)
        self.assertEqual(manifest["source"], "广东省考行测-科学推理-20260902")
        self.assertEqual(questions[0]["source"], "广东省考行测-科学推理-20260902")

    def test_daily_source_is_stamped(self):
        questions = [item("Q01", CAT_SHULIANG, TAG_EQ, "A")]
        questions[0]["source"] = "random title"
        manifest = {
            "batch_id": "daily-20260901-shuliang-abc",
            "source": "random title",
            "kind": "ai-generated",
            "generation": {"batch_constraints": nab.default_answer_constraints(1)},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "questions.json").write_text(json.dumps(questions), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = nab.normalize_batch(root)
            self.assertTrue(result["source_stamped"])
            saved = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            saved_q = json.loads((root / "questions.json").read_text(encoding="utf-8"))
            expected = "广东省考行测-" + CAT_SHULIANG + "-20260901"
            self.assertEqual(saved["source"], expected)
            self.assertEqual(saved_q[0]["source"], expected)

    def test_payload_contains_plan(self):
        extras = nab.generation_payload_extras(CAT_SHULIANG, 15, "daily-x")
        self.assertEqual(len(extras["answer_plan"]), 15)
        self.assertEqual(extras["batch_constraints"]["question_count"], 15)
        extras_z = nab.generation_payload_extras(CAT_ZILIAO, 20, "daily-z")
        self.assertEqual(len(extras_z["ziliao_answer_groups"]), 4)
        validate_ziliao_paper_answers(extras_z["ziliao_answer_groups"])
        extras_p = nab.generation_payload_extras(CAT_PANDUAN, 20, "daily-p")
        self.assertEqual(len(extras_p["panduan_pack"]["slots"]), 20)
        self.assertEqual(extras_p["batch_constraints"]["panduan_layout"], "5_graphic_plus_15_logic")
        self.assertEqual([slot["section"] for slot in extras_p["panduan_pack"]["slots"][:5]], ["graphic"] * 5)
        self.assertEqual([slot["section"] for slot in extras_p["panduan_pack"]["slots"][5:]], ["logic"] * 15)
        self.assertNotIn("kepui_subjects", extras_p["batch_constraints"])
        extras_k = nab.generation_payload_extras("科学推理", 5, "daily-k")
        self.assertEqual(len(extras_k["kepui_pack"]["slots"]), 5)
        self.assertEqual(extras_k["batch_constraints"]["kepui_layout"], "5_kepui_distinct_subjects")
        self.assertEqual([slot["section"] for slot in extras_k["kepui_pack"]["slots"]], ["science"] * 5)
        self.assertEqual(extras["batch_constraints"]["shuliang_layout"], "5_sequence_plus_10_math")

    def test_daily_paper_order_is_restored(self):
        seq = item("Q-seq", CAT_SHULIANG, "数量关系-数字推理-递推数列", "A", sub_category="数字推理")
        math = item("Q-math", CAT_SHULIANG, TAG_EQ, "B", sub_category="数学运算")
        graphic = item("Q-g", CAT_PANDUAN, CAT_PANDUAN + "-图形推理-位置规律", "A", sub_category="图形推理")
        sci = item("Q-s", "科学推理", "科学推理-力学-受力平衡", "C", sub_category="科学推理")
        logic = item("Q-l", CAT_PANDUAN, TAG_LOGIC, "B", sub_category=SUB_LOGIC)
        self.assertEqual(
            [q["external_id"] for q in nab.sort_daily_questions([math, seq, math])],
            ["Q-seq", "Q-math", "Q-math"],
        )
        self.assertEqual(
            [q["external_id"] for q in nab.sort_daily_questions([logic, graphic])],
            ["Q-g", "Q-l"],
        )
        self.assertEqual(
            [q["external_id"] for q in nab.sort_daily_questions([sci])],
            ["Q-s"],
        )
        paper = [seq] * 5 + [math] * 10
        nab.validate_daily_paper_order("daily-20260902-shuliang-abc", paper)
        with self.assertRaises(ValueError):
            nab.validate_daily_paper_order("daily-20260902-shuliang-abc", [math] * 15)
        nab.validate_daily_paper_order("targeted-drill", [math] * 15)


    def test_kepui_category_is_rewritten(self):
        tags = [
            "科学推理-力学-受力平衡",
            "科学推理-压强与浮力-阿基米德原理",
            "科学推理-电学-串并联",
            "科学推理-生物-人体调节",
            "科学推理-地理-等高线",
        ]
        questions = [
            item(
                f"K{i:02d}",
                CAT_PANDUAN,
                tags[i],
                "ABCD"[i % 4] if i < 4 else "A",
                sub_category="科学推理",
                stem_images=[f"images/k{i}.png"],
            )
            for i in range(5)
        ]
        manifest = {
            "batch_id": "daily-20260902-kepui-abc",
            "kind": "ai-generated",
            "generation": {"batch_constraints": nab.default_answer_constraints(5)},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "questions.json").write_text(
                json.dumps(questions, ensure_ascii=False), encoding="utf-8"
            )
            (root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            result = nab.normalize_batch(root)
            self.assertTrue(result["changed"])
            saved = json.loads((root / "questions.json").read_text(encoding="utf-8"))
            saved_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual({q["category"] for q in saved}, {"科学推理"})
            self.assertEqual({q["sub_category"] for q in saved}, {"科学推理"})
            self.assertEqual(saved_manifest["source"], "广东省考行测-科学推理-20260902")
            self.assertEqual({q["source"] for q in saved}, {"广东省考行测-科学推理-20260902"})
            generation_gate.validate_paper_hard_rules(
                json.loads((root / "manifest.json").read_text(encoding="utf-8")),
                saved,
            )

    def test_focus_tag_skips_daily_layout_packs(self):
        extras_p = nab.generation_payload_extras(
            CAT_PANDUAN, 5, "hermes-fanyi", focus_tag="判断推理-逻辑判断-翻译推理"
        )
        self.assertEqual(extras_p["batch_constraints"]["focus_tag"], "判断推理-逻辑判断-翻译推理")
        self.assertEqual(extras_p["batch_constraints"]["question_count"], 5)
        self.assertNotIn("panduan_layout", extras_p["batch_constraints"])
        self.assertNotIn("panduan_pack", extras_p)
        extras_k = nab.generation_payload_extras(
            "科学推理", 2, "hermes-ganggan", focus_tag="科学推理-力学-杠杆滑轮"
        )
        self.assertEqual(extras_k["batch_constraints"]["focus_tag"], "科学推理-力学-杠杆滑轮")
        self.assertNotIn("kepui_layout", extras_k["batch_constraints"])
        self.assertNotIn("kepui_pack", extras_k)

    def test_kepui_payload_caps_letters(self):
        extras = nab.generation_payload_extras("科学推理", 5, "daily-k")
        self.assertEqual(extras["batch_constraints"]["answer_max_per_letter"], 2)
        self.assertGreaterEqual(extras["batch_constraints"]["answer_min_letters"], 3)
        self.assertEqual(len({row["answer"] for row in extras["answer_plan"]}), 4)

    def test_material_blank_lines_collapse_to_single_newline(self):
        materials = [{"content": "第一段。\n\n第二段。\n\n\n第三段。"}]
        self.assertEqual(nab.normalize_materials(materials), 1)
        self.assertEqual(materials[0]["content"], "第一段。\n第二段。\n第三段。")
        self.assertEqual(nab.normalize_materials(materials), 0)


if __name__ == "__main__":
    unittest.main()

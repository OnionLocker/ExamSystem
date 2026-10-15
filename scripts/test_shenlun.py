#!/usr/bin/env python3
"""申论：引文核对、要点表核对、分值配平、真题导入格式、采点算分。不调模型，只用临时库。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shenlun_grade  # noqa: E402
import shenlun_quiz  # noqa: E402
from shenlun_common import check_rubric, connect, contains, load_paper, save_paper, word_count  # noqa: E402

MATERIALS = [{"id": "M1", "title": "材料1", "paragraphs": [
    {"id": "M1-1", "text": "某镇建立“周末夜话”制度，镇干部每周到村里听取群众意见，当场能办的当场办。"},
    {"id": "M1-2", "text": "该镇还整合闲置农房发展民宿，村集体年收入从不足十万元增加到六十万元。"},
]}]


def question(points, expression=1, score=5):
    return {"no": 1, "qtype": "归纳概括", "prompt": "根据给定资料1，概括某镇的主要做法。（5分）不超过150字。",
            "requirements": {"score": score, "words_max": 150, "material_ids": ["M1"]},
            "rubric": {"kind": "points", "points": points, "expression_score": expression, "format_points": []},
            "reference_answer": "建立周末夜话制度听取民意；整合闲置农房发展民宿。"}


GOOD = [
    {"id": "P1", "text": "建立周末夜话制度，干部下村听取民意", "score": 2,
     "evidence": [{"para": "M1-1", "quote": "建立“周末夜话”制度"}]},
    {"id": "P2", "text": "整合闲置农房发展民宿，壮大集体经济", "score": 2,
     "evidence": [{"para": "M1-2", "quote": "整合闲置农房发展民宿"}]},
]


class TextTest(unittest.TestCase):
    def test_contains_ignores_spaces_and_punctuation(self):
        self.assertTrue(contains("一、建立周末夜话制度，听取意见。", "建立“周末夜话”制度"))
        self.assertFalse(contains("一、建立周末夜话制度", "建立周末议事制度"))
        self.assertFalse(contains("建立周末夜话制度", "制度"))  # 太短的引文不算

    def test_word_count_counts_punctuation_not_spaces(self):
        self.assertEqual(word_count("一、做法。\n 二、成效"), 9)


class RubricTest(unittest.TestCase):
    def test_good_rubric_passes(self):
        self.assertEqual(check_rubric(question(GOOD), MATERIALS), [])

    def test_fake_quote_and_bad_scores_are_caught(self):
        bad = [dict(GOOD[0], evidence=[{"para": "M1-1", "quote": "建立村民议事会制度"}]),
               dict(GOOD[1], score=3, text="整合闲置农房发展民宿壮大集体经济，并且推动乡村旅游、文化振兴和生态保护协同发展，形成区域品牌")]
        issues = "；".join(check_rubric(question(bad, expression=0), MATERIALS))
        self.assertIn("不是 M1-1 的原文", issues)
        self.assertIn("1 或 2 分", issues)
        self.assertIn("要点太长", issues)

    def test_out_of_scope_paragraph_is_caught(self):
        q = question(GOOD)
        q["requirements"]["material_ids"] = ["M2"]
        self.assertTrue(any("不在本题指定材料" in i for i in check_rubric(q, MATERIALS)))

    def test_expression_score_is_balanced_by_program(self):
        raw = [{"no": 1, "prompt": "设问" * 20, "rubric": {"kind": "points", "points": GOOD, "format_points": []},
                "reference_answer": "x"}]
        out = shenlun_quiz.normalize_questions(raw, [{"qtype": "归纳概括", "score": 5, "words_max": 150}], MATERIALS, None)
        self.assertEqual(out[0]["rubric"]["expression_score"], 1.0)


class ImportTest(unittest.TestCase):
    def test_paragraph_strings_become_numbered_materials(self):
        paper = shenlun_quiz.normalize_import({
            "title": "2025年广东省考申论（县级卷）",
            "materials": [{"paragraphs": ["第一段原文内容。", "  第二段原文内容。 "]}],
            "questions": [{"qtype": "归纳概括", "prompt": "概括做法。", "score": 10, "words_max": 200}]})
        self.assertEqual([p["id"] for p in paper["materials"][0]["paragraphs"]], ["M1-1", "M1-2"])
        self.assertEqual(paper["materials"][0]["paragraphs"][1]["text"], "第二段原文内容。")
        with self.assertRaises(ValueError):
            shenlun_quiz.normalize_import({"title": "x", "materials": [{"paragraphs": ["a"]}],
                                           "questions": [{"qtype": "申发论述", "prompt": "p", "score": 1}]})


class GradeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "exam.db"
        conn = connect(self.db)
        save_paper(conn, {"id": "t-paper", "title": "测试卷", "kind": "ai", "materials": MATERIALS,
                          "questions": [question(GOOD)]})
        self.answer = "一、建立周末夜话制度，镇干部每周下村听意见。二、加强领导，压实责任。"
        conn.execute("INSERT INTO shenlun_attempts (question_id, answer_text, status) VALUES ('t-paper-q1', ?, 'grading')",
                     (self.answer,))
        conn.commit()
        self.conn = conn

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def fake_passes(self, second_p1="hit", second_quote="建立周末夜话制度，镇干部每周下村听意见"):
        first = {"points": [{"id": "P1", "verdict": "hit", "answer_quote": "建立周末夜话制度，镇干部每周下村听意见"},
                            {"id": "P2", "verdict": "hit", "answer_quote": "整合闲置农房发展民宿"}],
                 "expression": {"level": "A"}, "comment": "ok"}
        second = {"points": [{"id": "P1", "verdict": second_p1, "answer_quote": second_quote},
                             {"id": "P2", "verdict": "miss", "answer_quote": ""}],
                  "expression": {"level": "B"}}
        return iter([first, second])

    def run_grade(self, passes):
        with mock.patch.object(shenlun_grade, "call", side_effect=lambda *a, **k: next(passes)):
            shenlun_grade.run_grade(self.conn, 1)
        row = self.conn.execute("SELECT * FROM shenlun_attempts WHERE id=1").fetchone()
        return row, json.loads(row["grading"])

    def test_invented_quote_does_not_score_and_lower_pass_wins(self):
        row, g = self.run_grade(self.fake_passes())
        p1, p2 = g["points"]
        self.assertEqual((p1["verdict"], p1["earned"], p1["disputed"]), ("hit", 2.0, False))
        # 第一遍声称命中 P2，但引的句子答案里没有 → 按未命中；两遍都算 0
        self.assertEqual((p2["verdict"], p2["earned"]), ("miss", 0.0))
        self.assertEqual(g["expression"]["earned"], 0.5)  # A 与 B 取低
        self.assertEqual(row["score"], 2.5)
        self.assertEqual(row["status"], "graded")

    def test_disagreement_is_flagged(self):
        _, g = self.run_grade(self.fake_passes(second_p1="partial"))
        self.assertTrue(g["points"][0]["disputed"])
        self.assertEqual(g["points"][0]["earned"], 1.0)
        self.assertTrue(any("判得不一样" in n for n in g["notes"]))

    def test_paper_round_trip(self):
        paper = load_paper(self.conn, "t-paper")
        self.assertEqual(paper["questions"][0]["rubric"]["points"][0]["id"], "P1")


if __name__ == "__main__":
    unittest.main()

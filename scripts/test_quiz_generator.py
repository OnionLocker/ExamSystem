#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

from quiz_generator import (
    align_answers,
    build_calculations,
    build_prompt,
    holdout_matches,
    infer_subcategory,
    module_of,
    reject_unsupported,
    stamp_questions,
)


class QuizGeneratorTest(unittest.TestCase):
    def test_module_and_sub(self):
        tag = "判断推理-逻辑判断-翻译推理"
        self.assertEqual(module_of(tag, ""), "判断推理")
        self.assertEqual(infer_subcategory(tag, "判断推理"), "逻辑判断")

    def test_reject_figures(self):
        with self.assertRaises(ValueError):
            reject_unsupported("科学推理", "科学推理-力学-杠杆滑轮")
        with self.assertRaises(ValueError):
            reject_unsupported("判断推理", "判断推理-图形推理-空间类")

    def test_focus_prompt(self):
        run = {
            "module": "判断推理",
            "focus_tag": "判断推理-逻辑判断-翻译推理",
            "planned_count": 2,
            "batch_id": "x",
            "plan_date": "2026-09-10",
        }
        extras = {"answer_plan": [{"index": 1, "answer": "A"}, {"index": 2, "answer": "B"}]}
        text = build_prompt(run, {}, extras)
        self.assertIn("判断推理-逻辑判断-翻译推理", text)
        self.assertIn("echo_given_fact", text)
        self.assertNotIn("5_graphic_plus_15_logic", text)

    def test_align_and_stamp(self):
        run = {
            "module": "判断推理",
            "focus_tag": "判断推理-逻辑判断-翻译推理",
            "planned_count": 1,
            "batch_id": "demo",
            "answer_plan": [{"index": 1, "answer": "C"}],
        }
        questions = stamp_questions(
            run,
            [
                {
                    "stem": "若P则Q。已知非Q。",
                    "options": [
                        {"key": "A", "text": "甲"},
                        {"key": "B", "text": "乙"},
                        {"key": "C", "text": "丙"},
                        {"key": "D", "text": "丁"},
                    ],
                    "answer": "A",
                    "analysis": "逆否。故选A。",
                }
            ],
            "src",
        )
        self.assertEqual(questions[0]["answer"], "C")
        self.assertEqual(questions[0]["external_id"], "demo_01")
        self.assertEqual(questions[0]["tags"], ["判断推理-逻辑判断-翻译推理"])
        self.assertIn("故选C", questions[0]["analysis"])

    def test_quantity_prompt_asks_calculations(self):
        run = {
            "module": "数量关系",
            "focus_tag": "数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）",
            "planned_count": 5,
            "batch_id": "x",
            "plan_date": "2026-09-10",
        }
        extras = {"answer_plan": [{"index": i, "answer": "ABCD"[(i - 1) % 4]} for i in range(1, 6)]}
        text = build_prompt(run, {}, extras)
        self.assertIn("calculations", text)
        self.assertIn("8*7*6/(3*2*1)", text)
        self.assertIn("禁止改成数列", text)

    def test_calculations_follow_aligned_keys(self):
        questions = [
            {
                "external_id": "demo_01",
                "answer": "A",
                "options": [
                    {"key": "A", "text": "56种"},
                    {"key": "B", "text": "48种"},
                    {"key": "C", "text": "36种"},
                    {"key": "D", "text": "24种"},
                ],
                "calculations": {
                    "correct": "8*7",
                    "options": {"A": "8*7", "B": "48", "C": "36", "D": "24"},
                    "tolerance": 0.01,
                },
            }
        ]
        align_answers(questions, ["C"])
        self.assertEqual(questions[0]["answer"], "C")
        calc = build_calculations(questions)
        row = calc["questions"][0]
        self.assertEqual(row["options"]["C"], "8*7")
        self.assertEqual(row["correct"], "8*7")
        self.assertNotIn("calculations", questions[0])

    def test_holdout_must_share_family(self):
        tag = "数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）"
        self.assertTrue(
            holdout_matches(
                tag,
                {"references": [{"tags": ["数量关系-逢考必有的排列组合与概率-基础原理与几何概型"], "stem": "分组"}]},
            )
        )
        self.assertFalse(
            holdout_matches(
                tag,
                {"references": [{"tags": ["数量关系-和差倍比与方程法-方程、比例与代入验证"], "stem": "容积"}]},
            )
        )


if __name__ == "__main__":
    unittest.main()

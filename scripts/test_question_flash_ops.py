#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
from pathlib import Path

from draw_contract import request_from_question, spec_from_question
from question_flash_ops import apply_decision, issue_brief, parse_decision, patch_one, preflight_draft


class ParseAndApplyTest(unittest.TestCase):
    def test_patch_options_and_contract(self):
        raw = """```json
{"action":"patch","stem":null,"options":[
  {"key":"A","text":"甲下沉"},
  {"key":"B","text":"乙上浮"},
  {"key":"C","text":"一样"},
  {"key":"D","text":"无法判断"}
],"analysis":"甲密度更大","figure_contract":{"kind":"tank","must_show":["甲","乙"]},"reason":"去掉一定是"}
```"""
        decision = parse_decision(raw)
        row = apply_decision(decision, {
            "stem": "如图甲、乙。",
            "answer": "A",
            "options": [{"key": "A", "text": "甲"}, {"key": "B", "text": "一定是乙"}, {"key": "C", "text": "丙"}, {"key": "D", "text": "丁"}],
        })
        self.assertEqual(row["options"][1]["text"], "乙上浮")
        self.assertEqual(row["figure_contract"]["kind"], "tank")
        self.assertEqual(row["figure_template"], "tank")
        self.assertNotIn("_ops_regen", row)

    def test_regen_marks_question(self):
        row = apply_decision({"action": "regen", "reason": "画不出"}, {"stem": "x"})
        self.assertTrue(row["_ops_regen"])


class PreflightTest(unittest.TestCase):
    def test_giveaway_is_patched_without_regen(self):
        draft = {"questions": [{
            "external_id": "q_01",
            "category": "科学推理",
            "tags": ["科学推理-物理-浮力"],
            "stem": "如图甲、乙。",
            "answer": "A",
            "analysis": "甲下沉",
            "options": [
                {"key": "A", "text": "甲下沉"},
                {"key": "B", "text": "一定是乙"},
                {"key": "C", "text": "丙"},
                {"key": "D", "text": "丁"},
            ],
        }]}
        def caller(_system, _payload):
            return {
                "action": "patch",
                "options": [
                    {"key": "A", "text": "甲下沉"},
                    {"key": "B", "text": "乙上浮"},
                    {"key": "C", "text": "丙"},
                    {"key": "D", "text": "丁"},
                ],
                "reason": "去掉一定是",
            }
        out = preflight_draft(draft, caller=caller)
        self.assertEqual(out["patched"], ["q_01"])
        self.assertEqual(out["need_gemini"], [])
        self.assertFalse(out["block_render"])
        self.assertEqual(draft["questions"][0]["options"][1]["text"], "乙上浮")

    def test_graphic_bank_is_left_alone(self):
        draft = {"questions": [{
            "external_id": "g_01",
            "exam_move": "立方体截面",
            "stem": "过 A、B、C 三点切开",
            "answer": "A",
            "options": [
                {"key": "A", "text": "x"},
                {"key": "B", "text": "一定是"},
                {"key": "C", "text": "y"},
                {"key": "D", "text": "z"},
            ],
        }]}
        called = []
        out = preflight_draft(draft, caller=lambda s, p: called.append(1) or {"action": "patch"})
        self.assertEqual(called, [])
        self.assertEqual(out["patched"], [])
        self.assertEqual(draft["questions"][0]["options"][1]["text"], "一定是")

    def test_issue_brief_keeps_verbatim(self):
        text = issue_brief("k_03: FIGURE_REGEN: 图上多了草\nk_04: giveaway extreme-word distractor")
        self.assertIn("图上多了草", text)
        self.assertIn("giveaway", text)


class ContractTest(unittest.TestCase):
    def test_request_reads_contract_not_placeholder(self):
        req = request_from_question(
            {
                "external_id": "k_01",
                "stem": "如图电路 R1 与 R2。",
                "figure_contract": {"kind": "circuit", "must_show": ["R1", "R2"], "must_not": ["木块"]},
            },
            {"image_facts": ["程序绘制的图形"]},
            {"kind": "front"},
            Path("/tmp/q.png"),
        )
        self.assertEqual(req["kind_hint"], "circuit")
        self.assertEqual(req["must_show"][:2], ["R1", "R2"])
        self.assertIn("木块", req["must_not"])

    def test_spec_keeps_gemini_facts(self):
        spec = spec_from_question(
            {"external_id": "k_01", "stem": "如图 R1", "figure_contract": {"must_show": ["R1"]}},
            {"image_facts": ["A1"]},
        )
        self.assertIn("R1", spec["image_facts"])
        self.assertIn("A1", spec["image_facts"])


if __name__ == "__main__":
    unittest.main()

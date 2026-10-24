#!/usr/bin/env python3
"""单篇/专项入口的计划与参数校验（不调模型）。"""
import contextlib
import io
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import ziliao_material_pipeline as pipe
from kaodian_taxonomy import is_abcd_plus_one
from ziliao_tracks import ZILIAO_DELTA, ZILIAO_SHARE

DB = Path(__file__).resolve().parents[1] / "data" / "exam.db"


class TargetedPlanTest(unittest.TestCase):
    def test_ten_questions_are_two_materials_all_on_tag(self):
        plans, keys = pipe.targeted_plans(ZILIAO_DELTA, 10, "mid", None, "", "t-seed", DB)
        self.assertEqual([p["id"] for p in plans], ["M01", "M02"])
        for plan, letters in zip(plans, keys):
            self.assertEqual(len(plan["slots"]), 5)
            self.assertEqual({s["tag"] for s in plan["slots"]}, {ZILIAO_DELTA})
            self.assertTrue(is_abcd_plus_one(letters))
            self.assertFalse(any("answer_key" in s for s in plan["slots"]))
            self.assertLessEqual(Counter(s.get("option_format") for s in plan["slots"])["interval"], 1)

    def test_format_and_brief_are_honoured(self):
        plans, _ = pipe.targeted_plans(ZILIAO_SHARE, 5, "easy", "饼图", "只练现期比重", "t2", DB)
        self.assertEqual(plans[0]["material_type"], "pie")
        self.assertTrue(all("用户要求：只练现期比重" in s["brief"] for s in plans[0]["slots"]))

    def test_one_paper_can_pin_one_variant(self):
        from kaodian_taxonomy import ZILIAO_QI
        plans, keys = pipe.targeted_plans(
            ZILIAO_QI, 6, "mid", None, "", "lookup-6", DB, one_paper=True, variant="直接定位读数")
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(plans[0]["slots"]), 6)
        self.assertEqual(plans[0]["material_type"], "text")
        self.assertTrue(all(s.get("kaofa_variant_name") == "直接定位读数" for s in plans[0]["slots"]))
        self.assertEqual(len(keys[0]), 6)
        self.assertEqual(set(keys[0]), set("ABCD"))
        self.assertLessEqual(max(Counter(keys[0]).values()), 2)

    def test_invalid_requests_are_refused(self):
        for tag, count in (("资料分析-不存在", 5), (ZILIAO_DELTA, 7), (ZILIAO_DELTA, 20)):
            with self.subTest(tag=tag, count=count), self.assertRaises(ValueError):
                pipe.targeted_plans(tag, count, "mid", None, "", "x", DB)


class CliTest(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["ziliao_material_pipeline.py", *argv]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = pipe.main()
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_full_paper_requests_point_to_paper_entry(self):
        code, _, err = self.run_main("--count", "20")
        self.assertNotEqual(code, 0)
        self.assertIn("ziliao_agent_paper.py", err)

    def test_plan_only_does_not_call_models(self):
        with patch.object(pipe.runner, "call", side_effect=AssertionError("不应调模型")):
            code, out, _ = self.run_main("--tag", ZILIAO_DELTA, "--count", "10", "--plan-only", "--batch-id", "cli_test")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["materials"]), 2)


if __name__ == "__main__":
    unittest.main()

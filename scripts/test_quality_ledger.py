#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
from pathlib import Path

import quality_ledger as ql


class QualityLedgerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rejects.jsonl"
        os.environ["QUALITY_LEDGER"] = str(self.path)

    def tearDown(self):
        os.environ.pop("QUALITY_LEDGER", None)
        self.temp.cleanup()

    def test_classify_figure_and_notation(self):
        self.assertEqual(ql.classify_figure_issue("题干有甲乙，图上没有"), "fig_missing_label")
        self.assertEqual(ql.classify_figure_issue("清单要求交点，图上折线不相交"), "fig_no_intersection")
        self.assertEqual(ql.classify_figure_issue("图上多了清单/题干没有的「木块」"), "fig_extra_object")
        self.assertEqual(ql.classify_figure_issue("锋面题配了等高线图"), "fig_kind_mismatch")
        self.assertEqual(ql.classify_figure_issue("图上写了 must_derive 的「冷锋」"), "fig_leak_answer")
        self.assertEqual(ql.classify_figure_issue("像素过低 1280x720"), "fig_low_res")
        events = ql.classify_error(
            "程序作图质检未过：daily-20260907-kepui-f3b9b0dd1c394c0b889a_03: 图上多了木块"
        )
        self.assertEqual(events[0]["class"], "fig_extra_object")
        self.assertEqual(events[0]["question_id"], "daily-20260907-kepui-f3b9b0dd1c394c0b889a_03")
        mixed = ql.classify_error("题干设定两容器为甲、乙，解析混用 ρ_A、ρ_B")
        self.assertEqual(mixed[0]["class"], "notation_stem_mismatch")

    def test_record_dedup_and_summary(self):
        first = ql.record_event(
            {
                "batch_id": "daily-20260907-kepui-aaa",
                "question_id": "daily-20260907-kepui-aaa_03",
                "class": "notation_stem_mismatch",
                "module": "科学推理",
                "detail": "ρ_A",
            }
        )
        second = ql.record_event(
            {
                "batch_id": "daily-20260907-kepui-aaa",
                "question_id": "daily-20260907-kepui-aaa_03",
                "class": "notation_stem_mismatch",
                "module": "科学推理",
                "detail": "ρ_B",
            }
        )
        self.assertEqual(first["count"], 1)
        self.assertEqual(second["count"], 2)
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        tallies = ql.summarize(days=30)
        self.assertEqual(tallies["科学推理"]["notation_stem_mismatch"], 2)

    def test_retry_prompt_uses_classes_not_raw_dump(self):
        ql.record_event(
            {
                "batch_id": "daily-20260907-kepui-aaa",
                "question_id": "daily-20260907-kepui-aaa_04",
                "class": "giveaway_extreme",
                "module": "科学推理",
            }
        )
        raw = "ExamSystem 系统质检失败：" + ("x" * 2000)
        block = ql.retry_prompt_block("科学推理", raw)
        self.assertIn("giveaway_extreme", block)
        self.assertNotIn("x" * 50, block)
        self.assertNotIn("系统质检失败", block)

    def test_promote_discipline(self):
        self.assertIn("审核噪声不升级", ql.promote_advice("flash_visual_missing"))
        self.assertIn("单次失败不升级", ql.promote_advice("notation_stem_mismatch"))
        ql.record_event(
            {
                "batch_id": "daily-20260907-kepui-aaa",
                "question_id": "q_01",
                "class": "notation_stem_mismatch",
                "module": "科学推理",
            }
        )
        ql.record_event(
            {
                "batch_id": "daily-20260907-kepui-aaa",
                "question_id": "q_01",
                "class": "notation_stem_mismatch",
                "module": "科学推理",
            }
        )
        advice = ql.promote_advice("notation_stem_mismatch")
        self.assertIn("该写检查器", advice)
        self.assertIn("notation_stem_issues", advice)

    def test_promote_flash_quality_stays_short_rule(self):
        ql.record_event(
            {
                "batch_id": "daily-20260907-kepui-aaa",
                "question_id": "q_02",
                "class": "flash_quality",
                "module": "科学推理",
            }
        )
        ql.record_event(
            {
                "batch_id": "daily-20260907-kepui-aaa",
                "question_id": "q_03",
                "class": "flash_quality",
                "module": "科学推理",
            }
        )
        advice = ql.promote_advice("flash_quality")
        self.assertIn("保持短规则", advice)
        self.assertNotIn("该写检查器", advice)

    def test_record_gate_failure_and_issue_wrapper(self):
        root = Path(self.temp.name) / "batch"
        root.mkdir()
        (root / "manifest.json").write_text(
            json.dumps({"batch_id": "daily-20260907-kepui-abc"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (root / "questions.json").write_text(
            json.dumps([{"category": "科学推理"}], ensure_ascii=False),
            encoding="utf-8",
        )
        recorded = ql.record_gate_failure(
            root,
            "程序作图质检未过：daily-20260907-kepui-abc_01: 题干有甲乙，图上没有",
        )
        self.assertEqual(recorded[0]["class"], "fig_missing_label")
        self.assertEqual(recorded[0]["module"], "科学推理")

        import generation_gate
        from unittest.mock import patch

        with patch.object(
            generation_gate,
            "_issue",
            side_effect=ValueError("C项一定是①"),
        ):
            try:
                generation_gate.issue(root)
            except ValueError:
                pass
            else:
                raise AssertionError("issue should re-raise")
        rows = ql._read_rows()
        self.assertTrue(any(row["class"] == "giveaway_extreme" for row in rows))

    def test_seed_is_idempotent(self):
        first = ql.seed_kepui_20260907()
        second = ql.seed_kepui_20260907()
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)
        classes = {row["class"] for row in ql._read_rows()}
        self.assertIn("fig_missing_label", classes)
        self.assertIn("notation_stem_mismatch", classes)
        self.assertIn("giveaway_extreme", classes)


if __name__ == "__main__":
    unittest.main()

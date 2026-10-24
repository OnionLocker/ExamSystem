#!/usr/bin/env python3
"""Regression checks for registered topics and configurable data-analysis generation."""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

import generation_gate
import quiz_generator
import quality_orchestrator
import ziliao_parallel_runner as ziliao
from kaodian_profile import coverage_report, ensure_schema, plan_blueprint, register_knowledge_point
from kaodian_taxonomy import canonicalize, registered_knowledge_points, validate_ai_primary_tag


class RegisteredWorkflow(unittest.TestCase):
    def test_registration_updates_wal_reader_coverage_and_next_batch_without_samples(self):
        tag = "数量关系-数学运算-最值问题-测试独立考法"
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, EXAM_DB=f"{tmp}/exam.db"):
            conn = sqlite3.connect(os.environ["EXAM_DB"])
            self.addCleanup(conn.close)
            conn.execute("PRAGMA journal_mode=WAL")
            ensure_schema(conn)
            with self.assertRaisesRegex(ValueError, "先 --register"):
                validate_ai_primary_tag(tag, "数量关系")
            with self.assertRaisesRegex(ValueError, "定义"):
                register_knowledge_point(conn, tag, "数量关系", "数学运算")
            register_knowledge_point(conn, tag, "数量关系", "数学运算", "定义版本甲：只练排序约束")
            conn.commit()
            self.assertEqual(validate_ai_primary_tag(tag, "数量关系"), tag)
            rows = [r for c in coverage_report(conn, "最值") for r in c["rows"]]
            self.assertTrue(any(r["tag"] == tag and "版本甲" in r["definition"] for r in rows))
            plan = plan_blueprint(conn, "测试独立考法", 3)
            self.assertIn(tag, [s["tag"] for s in plan["slots"]])
            run = {"module": "数量关系"}
            frozen = quiz_generator.run_canon_card(run, tag)
            register_knowledge_point(conn, tag, "数量关系", "数学运算", "定义版本乙：增加不同量约束")
            conn.commit()
            self.assertIn("版本乙", registered_knowledge_points()[tag]["definition"])
            self.assertEqual(quiz_generator.run_canon_card(run, tag), frozen)
            self.assertIn("版本乙", quiz_generator.run_canon_card({"module": "数量关系"}, tag))
            self.assertEqual(conn.execute("SELECT attempts FROM kaodian_profile WHERE kaodian=?", (tag,)).fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM kaodian_events").fetchone()[0], 0)

    def test_historical_registration_cannot_shadow_confirmed_alias(self):
        raw = "数量关系-排列组合-分组分配与消序"
        with patch("kaodian_taxonomy.static_alias", return_value="confirmed"), patch(
            "kaodian_taxonomy.registered_canonical_tags", return_value={raw}
        ):
            self.assertEqual(canonicalize(raw), "confirmed")

    def test_experimental_images_require_opt_in_and_cannot_issue(self):
        with self.assertRaises(ValueError):
            quiz_generator.reject_unsupported("科学推理", "科学推理-力学-杠杆滑轮", allow_images=True)
        quiz_generator.reject_unsupported("科学推理", "科学推理-力学-杠杆滑轮", allow_images=True, experimental=True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(generation_gate, "normalize_batch") as normalize:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps({"kind": "ai-generated", "generation": {"experimental_images": True}}))
            with self.assertRaisesRegex(ValueError, "实验图题"):
                generation_gate.issue(root)
            normalize.assert_not_called()

    def test_heavy_examiner_receives_single_slot_brief_and_frozen_definition(self):
        manifest = {"generation": {"kaofa_canon": {"tag": "frozen definition"},
                    "batch_constraints": {"targeted_drill": True, "slot_plan": [{"tag": "tag", "brief": "custom requirement"}]}}}
        review = {"verdict": "PASS", "type_distribution_ok": True, "difficulty_distribution_ok": True,
                  "reference_alignment_ok": True, "duplicate_groups": [], "issues": []}
        with patch.object(quality_orchestrator, "call_flash", return_value=review) as model, patch.object(
            quality_orchestrator, "evaluation_references", return_value={}
        ), patch.object(quality_orchestrator, "mechanical_answers_ok", return_value=True):
            result = quality_orchestrator.run_batch_quality(Path("."), manifest, [])
        payload = json.loads(model.call_args.args[1])
        self.assertEqual(payload["kaofa_canon"]["tag"], "frozen definition")
        self.assertEqual(payload["batch_constraints"]["slot_plan"][0]["brief"], "custom requirement")
        self.assertEqual(result["verdict"], "PASS")




if __name__ == "__main__":
    unittest.main()

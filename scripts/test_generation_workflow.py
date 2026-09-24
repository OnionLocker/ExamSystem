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


class ZiliaoWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "exam.db"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE questions (batch_id TEXT)")
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.argv = ["--db", str(self.db), "--output-dir", str(self.root / "output"),
                     "--tag", ziliao.TAGS[1], "--count", "2", "--materials", "1",
                     "--formats", "text", "--difficulty", "easy", "--batch-id", "test"]

    def test_cli_count_difficulty_format_and_unique_ids(self):
        args = ziliao.parse_args(self.argv)
        self.assertEqual((args.total, args.difficulty, args.formats), (2, "easy", ["text"]))
        self.assertEqual(args.slots[0]["tag"], ziliao.TAGS[1])
        self.assertNotEqual(ziliao.parse_args([]).batch_id, ziliao.parse_args([]).batch_id)
        for extra in (["--count", "0"], ["--count", "21"], ["--formats", "mixed"], ["--materials", "3"], ["--batch-id", "../bad"]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                ziliao.parse_args(self.argv + extra)

    def test_frozen_material_rejects_nonfinite_or_string_chart_values(self):
        figure = {"kind": "bars", "categories": ["a", "b", "c", "d"], "series": [{"values": [1, 2, 3, 4]}]}
        self.assertTrue(ziliao.valid_material({"material": {"figure": figure}}))
        for bad in ("4", float("nan"), float("inf"), True):
            figure["series"][0]["values"][-1] = bad
            self.assertFalse(ziliao.valid_material({"material": {"figure": figure}}))

    def run_pipeline(self, gate_code=0, no_import=False, bad_id=False):
        frame = {"difficulty": "easy", "materials": [{"id": "M01", "format": "text"}]}
        def model(prompt, max_tokens):
            if "命题总设计师" in prompt:
                return frame
            index = 1 if "设计第1题" in prompt else 2
            qid = f"test-M01-Q{index}"
            self.assertIn('"difficulty":2', prompt)
            return {"question": {"external_id": qid, "material_id": "test-M01", "tags": [ziliao.TAGS[1]], "difficulty": 5},
                    "calculation": {"question_id": qid}}
        material = {"external_id": "../bad" if bad_id else "test-M01", "content": "G省产值123.4亿元", "figure": {"kind": "none"}}
        def command(cmd, **kwargs):
            self.assertEqual(kwargs["env"]["EXAM_DB"], str(self.db))
            return subprocess.CompletedProcess(cmd, gate_code if "issue" in cmd else 0, "checked", "")
        with patch.object(ziliao, "call", side_effect=model), patch.object(ziliao, "material_call", return_value={"material": material}), patch.object(
            ziliao, "render_material"
        ) as render, patch.object(ziliao.subprocess, "run", side_effect=command) as commands, contextlib.redirect_stdout(io.StringIO()):
            if bad_id:
                with self.assertRaisesRegex(ValueError, "材料 ID"):
                    ziliao.main(self.argv)
                render.assert_not_called()
                commands.assert_not_called()
                return
            result = ziliao.main(self.argv + (["--no-import"] if no_import else []))
            self.assertEqual(result, gate_code)
            self.assertEqual(commands.call_count, 1 if no_import or gate_code else 2)
        manifest = json.loads(next((self.root / "output").glob("*/*/manifest.json")).read_text())
        constraints = manifest["generation"]["batch_constraints"]
        self.assertEqual(constraints["question_count"], 2)
        self.assertEqual(constraints["slot_plan"][0]["tag"], ziliao.TAGS[1])
        self.assertTrue(constraints["targeted_drill"])
        self.assertIn(ziliao.TAGS[1], manifest["generation"]["kaofa_canon"])

    def test_targeted_pipeline_calls_gate_before_import(self):
        self.run_pipeline()

    def test_failed_gate_prevents_import(self):
        self.run_pipeline(gate_code=1)

    def test_no_import_still_runs_gate(self):
        self.run_pipeline(no_import=True)

    def test_material_id_checked_before_render(self):
        self.run_pipeline(bad_id=True)

    def test_existing_batch_id_stops_before_generation(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO questions VALUES ('test')")
        with patch.object(ziliao, "call") as model, self.assertRaisesRegex(ValueError, "已入库"):
            ziliao.main(self.argv)
        model.assert_not_called()


if __name__ == "__main__":
    unittest.main()

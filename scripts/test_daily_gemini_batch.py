#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for direct Gemini daily drafts."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import daily_batch_scheduler
import daily_gemini_batch
from scheduler_common import ensure_run_schema


CAT_SHULIANG = "\u6570\u91cf\u5173\u7cfb"
SRC_SHULIANG = "\u5e7f\u4e1c\u7701\u8003\u884c\u6d4b-\u6570\u91cf\u5173\u7cfb-20260920"
TAG_SHULIANG = "\u6570\u91cf\u5173\u7cfb-\u6570\u5b57\u63a8\u7406-\u6570\u5b57\u63a8\u7406"
SUB_SEQ = "\u6570\u5b57\u63a8\u7406"


class ParseJsonTest(unittest.TestCase):
    def test_strips_fences_and_list(self):
        raw = '```json\n[{"stem": "x"}]\n```'
        self.assertEqual(daily_gemini_batch.parse_json(raw)["questions"][0]["stem"], "x")

    def test_extracts_object_from_prose(self):
        raw = 'here\n{"questions": [{"stem": "y"}]}\nok'
        self.assertEqual(daily_gemini_batch.parse_json(raw)["questions"][0]["stem"], "y")


class WriteBatchTest(unittest.TestCase):
    def test_writes_manifest_and_stamps_source(self):
        run = {
            "plan_date": "2026-09-20",
            "module": CAT_SHULIANG,
            "planned_count": 2,
            "batch_id": "daily-20260920-shuliang-abc",
        }
        draft = {
            "questions": [
                {
                    "stem": "1,2,3,?",
                    "options": {"A": "4", "B": "5", "C": "6", "D": "7"},
                    "answer": "A",
                    "analysis": "diff",
                    "tags": [TAG_SHULIANG],
                    "sub_category": SUB_SEQ,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            daily_gemini_batch.write_batch(run, batch_dir, draft)
            questions = json.loads((batch_dir / "questions.json").read_text(encoding="utf-8"))
            manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(questions[0]["external_id"], "daily-20260920-shuliang-abc_01")
            self.assertEqual(questions[0]["source"], SRC_SHULIANG)
            self.assertEqual(questions[0]["options"][0]["key"], "A")
            self.assertEqual(manifest["kind"], "ai-generated")
            self.assertEqual(manifest["difficulty_tier"], "hard")
            self.assertEqual(manifest["generation"]["evaluation_contexts"], [])


class RenderFigureTest(unittest.TestCase):
    def test_renders_table_and_strips_figure(self):
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            draft = {
                "questions": [],
                "materials": [
                    {
                        "content": "see figure",
                        "figure": {
                            "kind": "table",
                            "file": "images/m-01-table.png",
                            "title": "value",
                            "headers": ["y", "v"],
                            "rows": [["2024", "10"]],
                        },
                    }
                ],
            }
            daily_gemini_batch.render_assets(batch_dir, draft, deadline=10**12)
            dest = batch_dir / "images" / "m-01-table.png"
            self.assertTrue(dest.is_file())
            self.assertNotIn("figure", draft["materials"][0])
            self.assertEqual(draft["materials"][0]["images"], ["images/m-01-table.png"])


class SchedulerPromptTest(unittest.TestCase):
    def test_run_one_calls_gemini_not_hermes(self):
        run = {
            "plan_date": "2026-09-20",
            "module": CAT_SHULIANG,
            "planned_count": 15,
            "batch_id": "daily-x",
        }
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "exam.db"
            conn = sqlite3.connect(db)
            ensure_run_schema(conn)
            conn.execute(
                "INSERT INTO ai_daily_batch_runs(plan_date,module,batch_id,status,planned_count,source) "
                "VALUES (?,?,?,?,?,?)",
                ("2026-09-20", CAT_SHULIANG, "daily-x", "scheduled", 15, "daily-scheduler"),
            )
            conn.execute("CREATE TABLE questions (batch_id TEXT)")
            conn.commit()
            conn.close()
            with (
                mock.patch.object(daily_batch_scheduler, "generate_and_import") as gen,
                mock.patch.object(daily_batch_scheduler, "imported_count", return_value=15),
            ):
                out = daily_batch_scheduler.run_one(
                    run, {"compact": ""}, db, Path(temp) / "out", timeout=30
                )
            gen.assert_called_once()
            self.assertNotIn("hermes", str(gen.call_args).lower())
            self.assertEqual(out["status"], "imported")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for weekday calendar and daily schedulers."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import daily_batch_scheduler
import daily_plan_scheduler
from china_workday import is_workday, workday_reason
from scheduler_common import daily_source_for_batch, module_from_daily_batch, reserve_runs


SNAPSHOT = {
    "as_of": "2026-09-20T04:00:00+08:00",
    "summary": {"profiles": 0},
    "recommended_targets": [],
    "weaknesses": [],
    "needs_measurement": [],
    "open_mistake_families": [],
    "compact": "test snapshot",
}


class WorkdayCalendarTest(unittest.TestCase):
    def test_national_day_is_holiday(self):
        self.assertFalse(is_workday(dt.date(2026, 10, 1)))
        self.assertEqual(
            workday_reason(dt.date(2026, 10, 1))[1], "statutory_holiday"
        )

    def test_regular_weekend_is_skipped(self):
        self.assertFalse(is_workday(dt.date(2026, 8, 29)))
        self.assertEqual(workday_reason(dt.date(2026, 8, 29))[1], "weekend")

    def test_makeup_weekend_is_workday(self):
        self.assertTrue(is_workday(dt.date(2026, 9, 20)))
        self.assertEqual(
            workday_reason(dt.date(2026, 9, 20))[1], "makeup_workday"
        )


class SchedulerTest(unittest.TestCase):
    def test_run_reservation_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        first = reserve_runs(conn, dt.date(2026, 9, 20))
        second = reserve_runs(conn, dt.date(2026, 9, 20))
        self.assertEqual(len(first), 5)
        self.assertEqual(
            {row["module"]: row["batch_id"] for row in first},
            {row["module"]: row["batch_id"] for row in second},
        )
        self.assertEqual(
            {row["module"]: row["planned_count"] for row in first},
            {
                "言语理解与表达": 15,
                "判断推理": 20,
                "科学推理": 5,
                "数量关系": 15,
                "资料分析": 20,
            },
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM ai_daily_batch_runs").fetchone()[0],
            5,
        )
        conn.close()

    def test_batch_dry_run_never_calls_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(
                    daily_batch_scheduler, "load_snapshot", return_value=SNAPSHOT
                ),
                mock.patch.object(daily_batch_scheduler, "generate_and_import") as gen,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = daily_batch_scheduler.main(
                    [
                        "--date",
                        "2026-09-20",
                        "--db",
                        str(root / "exam.db"),
                        "--lock-file",
                        str(root / "batch.lock"),
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            gen.assert_not_called()
            conn = sqlite3.connect(root / "exam.db")
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("SELECT * FROM ai_daily_batch_runs").fetchall()
            conn.close()

    def test_plan_dry_run_never_calls_subprocess_or_reserves_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(
                    daily_plan_scheduler, "load_snapshot", return_value=SNAPSHOT
                ),
                mock.patch.object(daily_plan_scheduler.subprocess, "run") as run,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = daily_plan_scheduler.main(
                    [
                        "--date",
                        "2026-09-20",
                        "--db",
                        str(root / "exam.db"),
                        "--lock-file",
                        str(root / "plan.lock"),
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            run.assert_not_called()
            conn = sqlite3.connect(root / "exam.db")
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("SELECT * FROM ai_daily_batch_runs").fetchall()
            conn.close()

    def test_generation_prompt_is_readable_chinese(self):
        run = {
            "plan_date": "2026-09-20",
            "module": "数量关系",
            "planned_count": 15,
            "batch_id": "daily-x",
        }
        prompt = daily_batch_scheduler.generation_prompt(
            run, SNAPSHOT, Path("/tmp/batch")
        )
        self.assertIn("You are ExamSystem", prompt)
        self.assertIn("Output one JSON object only", prompt)
        self.assertNotIn("hermes-skills/quiz-pipeline/SKILL.md", prompt)
        self.assertNotIn("import-batch.mjs", prompt)
        self.assertNotIn("hermes chat", prompt.lower())
        self.assertIn("15", prompt)
        self.assertIn("answer_plan", prompt)
        self.assertIn("answer_max_per_letter", prompt)
        self.assertIn("reshuffle", prompt)
        self.assertIn("广东省考行测-数量关系-20260920", prompt)
        self.assertIn("must be exactly", prompt)
        self.assertIn("principles+profile", prompt)
        self.assertIn("evaluate holdout", prompt)
        self.assertIn("omit evaluation_contexts", prompt)
        self.assertIn("do not shuffle questions", prompt)
        self.assertIn("数字推理", prompt)
        self.assertIn("数学运算", prompt)
        self.assertNotIn("Data analysis must be exactly 4 materials", prompt)
        self.assertFalse(hasattr(daily_batch_scheduler, "DEFAULT_SKILLS"))

    def test_panduan_prompt_is_graphic5_logic15_without_kepui(self):
        run = {
            "plan_date": "2026-09-20",
            "module": "判断推理",
            "planned_count": 20,
            "batch_id": "daily-p",
        }
        prompt = daily_batch_scheduler.generation_prompt(run, SNAPSHOT, Path("/tmp/batch"))
        self.assertIn("panduan_pack", prompt)
        self.assertIn("图形推理", prompt)
        self.assertIn("逻辑判断", prompt)
        self.assertIn("Do NOT include 科学推理", prompt)
        self.assertNotIn("Questions 16-20: 科学推理", prompt)
        self.assertNotIn("16-20", prompt)

    def test_kepui_prompt_is_independent_five(self):
        run = {
            "plan_date": "2026-09-20",
            "module": "科学推理",
            "planned_count": 5,
            "batch_id": "daily-k",
        }
        prompt = daily_batch_scheduler.generation_prompt(run, SNAPSHOT, Path("/tmp/batch"))
        self.assertIn("kepui_pack", prompt)
        self.assertIn("科学推理", prompt)
        self.assertIn("生物", prompt)
        self.assertIn("地理", prompt)
        self.assertIn("等高线", prompt)
        self.assertIn("contour-map", prompt)
        self.assertIn("independent", prompt)
        self.assertIn("5-question", prompt)
        self.assertIn("NEVER write category=判断推理", prompt)
        self.assertIn("any letter at most 2 times", prompt)

    def test_wait_unlocked_can_be_disabled(self):
        daily_plan_scheduler.wait_unlocked(Path("/tmp/missing.lock"), 0)


class DailyNameTest(unittest.TestCase):
    def test_kepui_slug_is_science_not_judgment(self):
        batch = "daily-20260902-kepui-c021e6dac46a413a97f3"
        self.assertEqual(module_from_daily_batch(batch), "科学推理")
        self.assertEqual(
            daily_source_for_batch(batch, ""),
            "广东省考行测-科学推理-20260902",
        )


if __name__ == "__main__":
    unittest.main()

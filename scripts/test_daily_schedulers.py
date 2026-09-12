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
from scheduler_common import (
    DAILY_SLUG,
    MODULE_QUOTAS,
    daily_source_for_batch,
    module_from_batch_id,
    pause_retired_modules,
    reserve_runs,
)


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
        self.assertEqual(len(first), 3)
        self.assertEqual(
            {row["module"]: row["batch_id"] for row in first},
            {row["module"]: row["batch_id"] for row in second},
        )
        self.assertEqual(
            {row["module"]: row["planned_count"] for row in first},
            {
                "判断推理": 20,
                "数量关系": 15,
                "资料分析": 20,
            },
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM ai_daily_batch_runs").fetchone()[0],
            3,
        )
        self.assertNotIn("言语理解与表达", {row["module"] for row in first})
        self.assertNotIn("科学推理", {row["module"] for row in first})
        self.assertNotIn("图形题目", {row["module"] for row in first})
        self.assertNotIn("图形题目", {module for module, _slug, _count in MODULE_QUOTAS})
        self.assertEqual(DAILY_SLUG["tuxing"], "图形题目")
        conn.close()

    def test_scheduled_yanyu_is_paused_not_regenerated(self):
        conn = sqlite3.connect(":memory:")
        reserve_runs(conn, dt.date(2026, 9, 21))
        conn.execute(
            """
            INSERT INTO ai_daily_batch_runs(
              plan_date,module,batch_id,status,planned_count,source
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                "2026-09-21",
                "言语理解与表达",
                "daily-20260921-yanyu-old",
                "scheduled",
                15,
                "daily-scheduler",
            ),
        )
        conn.commit()
        self.assertEqual(pause_retired_modules(conn, dt.date(2026, 9, 21)), 1)
        row = conn.execute(
            "SELECT status, error FROM ai_daily_batch_runs WHERE module=?",
            ("言语理解与表达",),
        ).fetchone()
        self.assertEqual(row[0], "paused")
        self.assertIn("已停", row[1])
        conn.execute(
            """
            INSERT INTO ai_daily_batch_runs(
              plan_date,module,batch_id,status,planned_count,source
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                "2026-09-21",
                "科学推理",
                "daily-20260921-kepui-old",
                "scheduled",
                5,
                "daily-scheduler",
            ),
        )
        conn.commit()
        self.assertEqual(pause_retired_modules(conn, dt.date(2026, 9, 21)), 1)
        kepui = conn.execute(
            "SELECT status FROM ai_daily_batch_runs WHERE module=?",
            ("科学推理",),
        ).fetchone()
        self.assertEqual(kepui[0], "paused")
        conn.close()

    def test_tuxing_slug_names_without_generation_quota(self):
        batch_id = "daily-20260910-tuxing-abc123"
        self.assertEqual(module_from_batch_id(batch_id), "图形题目")
        self.assertEqual(
            daily_source_for_batch(batch_id, "判断推理"),
            "广东省考行测-图形题目-20260910",
        )
        self.assertEqual(
            daily_source_for_batch("daily-20260909-yanyu-zzzz", ""),
            "广东省考行测-言语理解与表达-20260909",
        )

    def test_batch_dry_run_never_calls_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(
                    daily_batch_scheduler, "load_snapshot", return_value=SNAPSHOT
                ),
                mock.patch.object(daily_batch_scheduler.subprocess, "run") as run,
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
            run.assert_not_called()
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
        self.assertIn("quiz-pipeline", prompt)
        self.assertIn("hermes-skills/quiz-pipeline/SKILL.md", prompt)
        self.assertIn("import-batch.mjs", prompt)
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
        self.assertIn("quiz-pipeline", daily_batch_scheduler.DEFAULT_SKILLS)

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

    def test_wait_unlocked_can_be_disabled(self):
        daily_plan_scheduler.wait_unlocked(Path("/tmp/missing.lock"), 0)


if __name__ == "__main__":
    unittest.main()

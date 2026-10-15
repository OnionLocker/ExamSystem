#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for weekday calendar and daily schedulers."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import daily_batch_scheduler
import daily_plan_scheduler
import daily_review_plan
from china_workday import is_workday, workday_reason
from kaodian_profile import ensure_schema
from scheduler_common import (
    DAILY_SLUG,
    MODULE_QUOTAS,
    PAUSED_DAILY_MODULES,
    REVIEW_QUOTAS,
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
    def test_daily_placeholder_reservation_is_stopped(self):
        conn = sqlite3.connect(":memory:")
        first = reserve_runs(conn, dt.date(2026, 9, 20))
        second = reserve_runs(conn, dt.date(2026, 9, 20))
        self.assertEqual(MODULE_QUOTAS, ())
        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM ai_daily_batch_runs").fetchone()[0],
            0,
        )
        self.assertNotIn("图形题目", {module for module, _slug, _count in MODULE_QUOTAS})
        self.assertEqual(DAILY_SLUG["tuxing"], "图形题目")
        # 只剩数量关系的每日复习卷；它不走占位，也不能被“停用模块”暂停
        self.assertEqual(REVIEW_QUOTAS, (("数量关系", "shuliang", 20),))
        self.assertNotIn("数量关系", PAUSED_DAILY_MODULES)
        conn.close()

    def test_leftover_scheduled_runs_are_paused_not_recreated(self):
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
                "判断推理",
                "daily-20260921-panduan-old",
                "scheduled",
                20,
                "daily-scheduler",
            ),
        )
        conn.commit()
        rows = reserve_runs(conn, dt.date(2026, 9, 21))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "paused")
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM ai_daily_batch_runs").fetchone()[0],
            1,
        )
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


REVIEW_DAY = dt.date(2026, 10, 16)
MATH = "数量关系-数学运算-"


def stub_leaves(module, tags):
    """测试不读知识点目录：每个考点一个子考法。"""
    table = {tag: [{"tag": f"{tag}-@a", "title": "A"}] for tag in tags}
    return table, {leaf["tag"]: leaf["tag"] for items in table.values() for leaf in items}


def seed_review_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    ensure_schema(conn)
    conn.executescript(
        """
        CREATE TABLE questions (id INTEGER PRIMARY KEY, batch_id TEXT, tags TEXT, category TEXT, sub_category TEXT);
        CREATE TABLE practice_answers (id INTEGER PRIMARY KEY, session_id INTEGER, question_id INTEGER,
          user_answer TEXT, is_correct INTEGER, time_spent_sec INTEGER, answered_at TEXT);
        """
    )
    names = ("工程问题", "行程问题", "几何问题", "概率问题", "最值问题", "容斥原理问题", "溶液问题", "年龄问题")
    for index, name in enumerate(names):
        for n in range(6):
            qid = conn.execute(
                "INSERT INTO questions(tags, category, sub_category) VALUES (?,?,?)",
                (json.dumps([f"{MATH}{name}-@a"], ensure_ascii=False), "数量关系", "数学运算"),
            ).lastrowid
            conn.execute(
                "INSERT INTO practice_answers(session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)"
                " VALUES (?,?,?,?,?,?)",
                (1, qid, "A", int(n % 3 != 0), 150, f"{REVIEW_DAY - dt.timedelta(days=3 + index)} 04:00:00"),
            )
    conn.commit()
    conn.close()


class FakeQuizLite:
    """替身 quiz_lite：按 blueprint 把题写进 questions，或者按要求失败、超时。"""

    def __init__(self, db: Path, fail: bool = False, timeout: bool = False):
        self.db, self.fail, self.timeout, self.calls = db, fail, timeout, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if self.timeout:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
        if self.fail:
            return subprocess.CompletedProcess(
                command, 1, json.dumps({"status": "error", "error": "5 轮后仍有 1 道不合格"}, ensure_ascii=False), ""
            )
        batch_id = command[command.index("--batch-id") + 1]
        slots = json.loads(command[command.index("--blueprint") + 1])["slots"]
        conn = sqlite3.connect(self.db)
        conn.executemany(
            "INSERT INTO questions(batch_id, tags, category, sub_category) VALUES (?,?,?,?)",
            [(batch_id, json.dumps([slot["tag"]], ensure_ascii=False), "数量关系", "数学运算") for slot in slots],
        )
        conn.commit()
        conn.close()
        return subprocess.CompletedProcess(command, 0, "进度\n" + json.dumps({"status": "success"}), "")


class ReviewSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "exam.db"
        seed_review_db(self.db)
        real = daily_review_plan.build_plan
        self.patch = mock.patch.object(
            daily_batch_scheduler, "build_plan",
            lambda conn, module, day: real(conn, module, day, leaves_loader=stub_leaves),
        )
        self.patch.start()
        self.env = mock.patch.dict(os.environ, {"EXAM_DB": str(self.db)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.patch.stop()
        self.temp.cleanup()

    def run_scheduler(self, fake, *extra, day=REVIEW_DAY):
        out = io.StringIO()
        with (
            mock.patch.object(daily_batch_scheduler.subprocess, "run", side_effect=fake),
            contextlib.redirect_stdout(out),
        ):
            code = daily_batch_scheduler.main(
                ["--date", str(day), "--db", str(self.db), "--lock-file", str(self.root / "batch.lock"),
                 "--output-root", str(self.root / "batches"), *extra]
            )
        return code, json.loads(out.getvalue())

    def rows(self, sql, *params):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def answer_one(self, batch_id):
        conn = sqlite3.connect(self.db)
        qid = conn.execute("SELECT id FROM questions WHERE batch_id=? LIMIT 1", (batch_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO practice_answers(session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)"
            " VALUES (9, ?, 'A', 1, 80, datetime('now'))",
            (qid,),
        )
        conn.commit()
        conn.close()

    def test_sunday_set_goes_through_quiz_lite(self):
        fake = FakeQuizLite(self.db)
        sunday = dt.date(2026, 10, 18)
        code, out = self.run_scheduler(fake, day=sunday)
        self.assertEqual(code, 0)
        run = out["runs"][0]
        self.assertEqual(run["status"], "imported")
        self.assertTrue(run["batch_id"].startswith("daily-20261018-shuliang-"))
        command = fake.calls[0]
        self.assertTrue(command[1].endswith("quiz_lite.py"))
        self.assertEqual(command[command.index("--module") + 1], "数量关系")
        self.assertEqual(command[command.index("--rounds") + 1], "5")
        slots = json.loads(command[command.index("--blueprint") + 1])["slots"]
        self.assertEqual(len(slots), 20)
        self.assertTrue(all(slot["tag"].startswith(MATH) for slot in slots))
        self.assertEqual(
            self.rows("SELECT status, source FROM ai_daily_batch_runs WHERE batch_id=?", run["batch_id"]),
            [("imported", "daily-review")],
        )
        stored = self.rows("SELECT plan_date, plan_json FROM daily_review_plans WHERE batch_id=?", run["batch_id"])
        self.assertEqual(stored[0][0], "2026-10-18")
        self.assertEqual(json.loads(stored[0][1])["slots"], slots)
        # 06:30 那次补跑：今天已经有了，什么都不做
        code, out = self.run_scheduler(fake, day=sunday)
        self.assertEqual((code, out["runs"][0]["status"]), (0, "skipped_imported"))
        self.assertEqual(len(fake.calls), 1)

    def test_untouched_previous_set_blocks_the_next_one(self):
        fake = FakeQuizLite(self.db)
        _code, out = self.run_scheduler(fake)
        first = out["runs"][0]["batch_id"]
        _code, out = self.run_scheduler(fake, day=REVIEW_DAY + dt.timedelta(days=1))
        self.assertEqual(out["runs"][0]["status"], "skipped_untouched")
        self.assertEqual(out["runs"][0]["batch_id"], first)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM ai_daily_batch_runs WHERE plan_date='2026-10-17'"), [(0,)])
        # 动过一题就照常出
        self.answer_one(first)
        _code, out = self.run_scheduler(fake, day=REVIEW_DAY + dt.timedelta(days=1))
        self.assertEqual(out["runs"][0]["status"], "imported")
        # 又一套没动；--force 照出
        _code, out = self.run_scheduler(fake, day=REVIEW_DAY + dt.timedelta(days=2))
        self.assertEqual(out["runs"][0]["status"], "skipped_untouched")
        _code, out = self.run_scheduler(fake, "--force", day=REVIEW_DAY + dt.timedelta(days=2))
        self.assertEqual(out["runs"][0]["status"], "imported")
        self.assertEqual(len(fake.calls), 3)

    def test_failure_is_recorded_and_retry_uses_a_new_batch_id(self):
        code, out = self.run_scheduler(FakeQuizLite(self.db, fail=True))
        self.assertEqual(code, 1)
        failed = out["runs"][0]
        self.assertEqual(failed["status"], "failed")
        self.assertIn("不合格", failed["error"])
        self.assertEqual(self.rows("SELECT status FROM ai_daily_batch_runs WHERE batch_id=?", failed["batch_id"]), [("failed",)])
        code, out = self.run_scheduler(FakeQuizLite(self.db))
        self.assertEqual(code, 0)
        retry = out["runs"][0]
        self.assertNotEqual(retry["batch_id"], failed["batch_id"])
        self.assertEqual(
            self.rows("SELECT batch_id, status FROM ai_daily_batch_runs WHERE plan_date=?", str(REVIEW_DAY)),
            [(retry["batch_id"], "imported")],
        )

    def test_timeout_marks_the_generation_job_failed(self):
        code, out = self.run_scheduler(FakeQuizLite(self.db, timeout=True))
        self.assertEqual(code, 1)
        run = out["runs"][0]
        self.assertIn("没完成", run["error"])
        self.assertEqual(self.rows("SELECT status FROM generation_jobs WHERE batch_id=?", run["batch_id"]), [("failed",)])

    def test_plan_item_row_is_left_alone(self):
        conn = sqlite3.connect(self.db)
        daily_batch_scheduler.ensure_run_schema(conn)
        conn.execute(
            "INSERT INTO ai_daily_batch_runs(plan_date,module,batch_id,status,planned_count,source) VALUES (?,?,?,?,?,?)",
            (str(REVIEW_DAY), "数量关系", "20261016_hermes_jishu_01", "imported", 10, "hermes"),
        )
        conn.commit()
        conn.close()
        fake = FakeQuizLite(self.db)
        _code, out = self.run_scheduler(fake)
        self.assertEqual(out["runs"][0]["status"], "imported")
        self.assertEqual(
            self.rows("SELECT batch_id, status FROM ai_daily_batch_runs WHERE plan_date=?", str(REVIEW_DAY)),
            [("20261016_hermes_jishu_01", "imported")],
        )
        # 认“今天出过没有”靠 daily_review_plans，不靠那一行
        _code, out = self.run_scheduler(fake)
        self.assertEqual(out["runs"][0]["status"], "skipped_imported")

    def test_deleted_set_is_not_regenerated(self):
        fake = FakeQuizLite(self.db)
        _code, out = self.run_scheduler(fake)
        batch_id = out["runs"][0]["batch_id"]
        conn = sqlite3.connect(self.db)
        conn.execute("DELETE FROM questions WHERE batch_id=?", (batch_id,))
        conn.execute("UPDATE ai_daily_batch_runs SET status='deleted' WHERE batch_id=?", (batch_id,))
        conn.commit()
        conn.close()
        _code, out = self.run_scheduler(fake)
        self.assertEqual(out["runs"][0]["status"], "skipped_deleted")
        self.assertEqual(len(fake.calls), 1)

    def test_dry_run_plans_without_writing(self):
        before = self.rows("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        code, out = self.run_scheduler(FakeQuizLite(self.db), "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(out["reviews"][0]["count"], 20)
        self.assertEqual(self.rows("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"), before)


if __name__ == "__main__":
    unittest.main()

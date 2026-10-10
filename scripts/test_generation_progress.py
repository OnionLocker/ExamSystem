#!/usr/bin/env python3
"""出题进度：同一批次覆盖更新，终态后不再被改回。"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

import generation_progress as progress


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "exam.db")
        self._old = os.environ.get("EXAM_DB")
        os.environ["EXAM_DB"] = self.db

    def tearDown(self):
        if self._old is None:
            os.environ.pop("EXAM_DB", None)
        else:
            os.environ["EXAM_DB"] = self._old

    def rows(self):
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM generation_jobs ORDER BY batch_id")]

    def test_updates_keep_the_passed_count_and_terminal_state_sticks(self):
        job = progress.Job("b1", module="数量关系", title="排列组合", planned=8)
        job.update(stage="命题", detail="第1轮 · 正在出第 1–3 题", passed=0, round_no=1, progress=0)
        job.update(stage="审核", detail="第1轮 · 已过审 3/8", passed=3, round_no=1, progress=31)
        job.finish(status="done", stage="已入库", detail="已入库 8 题", passed=8, progress=100)
        job.update(stage="命题", detail="不该写回来", passed=0, progress=1)
        row = self.rows()[0]
        self.assertEqual((row["passed_count"], row["status"], row["stage"], row["progress"]), (8, "done", "已入库", 100))
        self.assertEqual(row["title"], "排列组合")
        self.assertIsNotNone(row["finished_at"])
        self.assertEqual(row["planned_count"], 8)

    def test_failure_keeps_the_title_from_the_first_write(self):
        progress.report("b2", module="言语理解与表达", title="片段阅读", planned=4, stage="命题", detail="正在出第 1–2 题")
        progress.report("b2", status="failed", stage="失败", error="审核未过", detail="审核未过")
        row = self.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["title"], "片段阅读")
        self.assertEqual(row["module"], "言语理解与表达")
        self.assertEqual(row["error"], "审核未过")

    def test_write_errors_are_swallowed(self):
        os.environ["EXAM_DB"] = str(Path(self.tmp.name))
        progress.report("b3", stage="命题")
        self.assertFalse((Path(self.tmp.name) / "generation_jobs").exists())


if __name__ == "__main__":
    unittest.main()

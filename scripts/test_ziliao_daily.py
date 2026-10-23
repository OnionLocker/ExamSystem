#!/usr/bin/env python3
import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import daily_ziliao_scheduler as sched
import ziliao_performance as perf

TODAY = dt.date(2026, 10, 24)
SHARE = "资料分析-比重类-现期、基期与隔级比重"
CMP = "资料分析-比较类-双线法与增量比较"


def make_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE questions(id INTEGER PRIMARY KEY, external_id TEXT, category TEXT, tags TEXT,
                               batch_id TEXT, created_at TEXT);
        CREATE TABLE practice_answers(id INTEGER PRIMARY KEY, session_id TEXT, question_id INTEGER,
                                      user_answer TEXT, is_correct INTEGER, time_spent_sec INTEGER, answered_at TEXT);
    """)
    return conn


class PerformanceTest(unittest.TestCase):
    def test_boost_direction_and_shrinkage(self):
        self.assertGreater(perf.boost_of(10, 4), 1.3)
        self.assertLess(perf.boost_of(10, 10), 0.8)
        self.assertAlmostEqual(perf.boost_of(1, 0), 1.375, places=3)
        self.assertLessEqual(perf.boost_of(100, 0), perf.BOOST_MAX)

    def test_collect_maps_kind_variant_and_skips_judge_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            batch = "b1"
            (tmp / batch).mkdir()
            slots = [{"tag": SHARE, "kind": "share", "kaofa_variant": "multi-part-share"},
                     {"tag": CMP, "kind": "count"}, {}, {}, {"tag": CMP, "kind": "judge"}]
            (tmp / batch / "M01-plan.json").write_text(json.dumps({"id": "M01", "slots": slots}))
            conn = make_db(tmp / "exam.db")
            for i, (qno, tag) in enumerate([(1, SHARE), (2, CMP), (5, CMP)], 1):
                conn.execute("INSERT INTO questions VALUES (?,?,?,?,?,?)",
                             (i, f"{batch}-M01-Q{qno}", "资料分析", json.dumps([tag]), batch, "2026-10-20"))
            answers = [(1, "A", 0, 60, "2026-10-21"), (1, "B", 1, 60, "2026-10-22"),
                       (2, "C", 1, 50, "2026-10-21"), (3, "D", 0, 90, "2026-10-21")]
            conn.executemany("INSERT INTO practice_answers(question_id,user_answer,is_correct,time_spent_sec,answered_at)"
                             " VALUES (?,?,?,?,?)", answers)
            stats = perf.collect(conn, TODAY, paper_dir=tmp)
        self.assertEqual(stats["answered"], 3)
        self.assertEqual(stats["tag"][SHARE], {"n": 1, "correct": 0})
        self.assertEqual(stats["tag"][CMP], {"n": 1, "correct": 1})
        self.assertEqual(stats["kind"]["judge"], {"n": 1, "correct": 0})
        self.assertEqual(stats["variant"][f"{SHARE}|multi-part-share"], {"n": 1, "correct": 0})


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = make_db(Path(self.tmp.name, "exam.db"))
        sched.ensure_run_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def add_run(self, day, batch, status="imported", source="daily-ziliao", answered=False):
        self.conn.execute("INSERT INTO ai_daily_batch_runs(plan_date,module,batch_id,status,planned_count,source)"
                          " VALUES (?,?,?,?,20,?)", (day, "资料分析", batch, status, source))
        self.conn.execute("INSERT INTO questions(external_id,category,tags,batch_id) VALUES (?,?,?,?)",
                          (f"{batch}-M01-Q1", "资料分析", "[]", batch))
        if answered:
            qid = self.conn.execute("SELECT MAX(id) FROM questions").fetchone()[0]
            self.conn.execute("INSERT INTO practice_answers(question_id,user_answer,is_correct,answered_at)"
                              " VALUES (?,?,?,?)", (qid, "A", 1, "2026-10-23"))

    def test_skips_when_previous_untouched_but_ignores_legacy(self):
        self.add_run("2026-09-14", "daily-20260914-ziliao-old", source="hermes-scheduler")
        self.assertIsNone(sched.untouched_previous(self.conn, TODAY))
        self.add_run("2026-10-23", "daily-20261023-ziliao-x")
        self.assertEqual(sched.untouched_previous(self.conn, TODAY)["batch_id"], "daily-20261023-ziliao-x")

    def test_answered_previous_and_today_imported(self):
        self.add_run("2026-10-23", "daily-20261023-ziliao-x", answered=True)
        self.assertIsNone(sched.untouched_previous(self.conn, TODAY))
        self.assertIsNone(sched.todays_paper(self.conn, TODAY))
        self.add_run("2026-10-24", "daily-20261024-ziliao-y")
        self.assertEqual(sched.todays_paper(self.conn, TODAY)["status"], "skipped_imported")


if __name__ == "__main__":
    unittest.main()

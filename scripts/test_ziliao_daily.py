#!/usr/bin/env python3
import datetime as dt
import json
import sqlite3
import tempfile
import unittest
import unittest.mock
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


class JudgeRotationTest(unittest.TestCase):
    def test_new_gd_stems_classified_same_in_gate_and_tracks(self):
        from generation_gate import _judge_form
        from ziliao_tracks import GD_JUDGE_FORM_POOL, classify_judge_form
        expected = {"根据资料，下列说法不准确的是": "有误", "根据资料，下列说法最不准确的是": "有误",
                    "根据资料，下列说法最准确的是": "正确", "根据资料，以下判断正确的是": "正确"}
        for stem, form in expected.items():
            self.assertEqual(classify_judge_form(stem), form)
            self.assertEqual(_judge_form(stem), form)
        for spec in GD_JUDGE_FORM_POOL:
            self.assertEqual(classify_judge_form(spec["stem"]), spec["form"], spec["stem"])

    def test_mixes_distinct_and_recent_ones_rarer(self):
        import random
        from collections import Counter
        from ziliao_tracks import GD_JUDGE_MIXES, pick_judge_mixes
        recent = [{"estimate-compare", "multi-step"}]
        counts = Counter()
        for seed in range(400):
            picked = pick_judge_mixes(random.Random(seed), recent)
            self.assertEqual(len({m["id"] for m in picked}), 4)
            counts.update(m["id"] for m in picked)
        self.assertEqual(set(counts), {m["id"] for m in GD_JUDGE_MIXES})
        self.assertLess(counts["estimate-compare"], counts["truth-mix"])


class VariantReviewTest(unittest.TestCase):
    def test_variant_match_is_required_when_slot_has_variant(self):
        import quality_orchestrator as qo
        q = {"explanation": "A项符合。", "requested_slot": {"family": "share_add", "kaofa_variant_name": "多部分合计占比"}}
        good = dict(material_consistent=True, slot_match=True, actual_family="share_add", actual_difficulty=2,
                    difficulty_reason="一步", claim_checks=[{"index": 1, "valid": True, "reason": "核对"}])
        self.assertTrue(any("多部分合计占比" in i for i in qo.ziliao_review_issues(q, good)))
        self.assertTrue(qo.ziliao_review_issues(q, good | {"variant_match": {"ok": False, "reason": "退回现期比重"}}))
        self.assertEqual(qo.ziliao_review_issues(q, good | {"variant_match": {"ok": True, "reason": "四项合计"}}), [])
        judge = {"explanation": "A项符合。", "requested_slot": {"family": "share_add", "judge_mix_id": "hypothesis"}}
        self.assertTrue(qo.ziliao_review_issues(judge, good))
        plain = {"explanation": "A项符合。", "requested_slot": {"family": "share_add"}}
        self.assertEqual(qo.ziliao_review_issues(plain, good), [])


class QualityCacheTest(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        import quality_orchestrator as qo
        self.qo = qo
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "b"
        self.dir.mkdir()
        env = mock.patch.dict("os.environ", {"QUALITY_CACHE_DIR": str(Path(self.tmp.name) / "cache")})
        env.start()
        self.addCleanup(env.stop)
        self.verdicts = {}
        self.calls = []

        def fake_call(system, prompt, images=None):
            ids = [item["question"]["id"] for item in json.loads(prompt)["items"]]
            self.calls.append(ids)
            return {"questions": [{"id": qid, "verdict": self.verdicts.get(qid, "PASS")} for qid in ids]}

        def fake_judge(question, review, references):
            ok = bool(review) and review.get("verdict") == "PASS"
            return {"verdict": "PASS" if ok else "REJECT", "review": review, "issues": [] if ok else ["x"]}

        for target, value in (("call_flash", fake_call), ("judge_quality", fake_judge),
                              ("evaluation_references", lambda manifest: {})):
            patcher = mock.patch.object(qo, target, side_effect=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def question(self, material, no, stem="题干"):
        return {"external_id": f"b-{material}-Q{no}", "material_id": material, "category": "资料分析",
                "stem": stem, "options": [{"key": k, "text": k} for k in "ABCD"], "answer": "A",
                "explanation": "A项符合。"}

    def run_quality(self, questions):
        return self.qo.run_quality(self.dir, {"generation": {}}, questions)

    def test_unchanged_passed_material_is_not_reviewed_again(self):
        questions = [self.question("M01", 1), self.question("M02", 1)]
        self.verdicts["b-M02-Q1"] = "REJECT"
        self.run_quality(questions)
        self.assertEqual(sorted(self.calls), [["b-M01-Q1"], ["b-M02-Q1"]])
        self.calls.clear()
        self.verdicts.clear()
        result = self.run_quality(questions)
        self.assertEqual(self.calls, [["b-M02-Q1"]])
        self.assertTrue(all(item["verdict"] == "PASS" for item in result.values()))

    def test_passed_blind_solve_is_not_repeated(self):
        blind = []

        def fake_blind(system, prompt, images=None):
            items = json.loads(prompt)
            blind.append([item["id"] for item in items])
            return {"questions": [{"id": item["id"], "verdict": "PASS", "answer": "A", "also_valid": [],
                                   "steps": "算", "issues": [], "option_tests": {
                                       k: {"stands": k == "A", "reason": "r"} for k in "ABCD"}} for item in items]}

        (self.dir / "calculations.json").write_text(json.dumps({"questions": [
            {"question_id": "b-M01-Q1", "correct": "1", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}}]}))
        with unittest.mock.patch.object(self.qo, "call_flash", side_effect=fake_blind):
            first = self.qo.run_route_b(self.dir, [self.question("M01", 1)])
            second = self.qo.run_route_b(self.dir, [self.question("M01", 1)])
        self.assertEqual(first["b-M01-Q1"]["verdict"], "PASS")
        self.assertEqual(second["b-M01-Q1"]["verdict"], "PASS")
        self.assertEqual(blind, [["b-M01-Q1"]])

    def test_only_changed_question_is_reviewed_again(self):
        self.run_quality([self.question("M01", 1), self.question("M01", 2)])
        self.calls.clear()
        self.run_quality([self.question("M01", 1), self.question("M01", 2, stem="改过的题干")])
        self.assertEqual(self.calls, [["b-M01-Q2"]])


class LockedAnswerTest(unittest.TestCase):
    def paper(self, answers):
        return [{"external_id": f"b-M0{i // 5 + 1}-Q{i % 5 + 1}", "material_id": f"b-M0{i // 5 + 1}",
                 "category": "资料分析", "stem": "s", "answer": a, "explanation": f"故选{a}",
                 "options": [{"key": k, "text": k} for k in "ABCD"]} for i, a in enumerate(answers)]

    def test_redistribution_only_moves_unlocked_questions(self):
        import normalize_ai_batch as nab
        questions = self.paper("ABCDA" "ABCDB" "ABCDA" "BCCDD")
        manifest = {"batch_id": "b", "generation": {}}
        self.assertTrue(nab.answer_distribution_ok(manifest, questions))
        questions[0]["answer"] = "D"
        self.assertFalse(nab.answer_distribution_ok(manifest, questions))
        locked = {q["external_id"] for q in questions} - {"b-M01-Q1"}
        before = {q["external_id"]: q["answer"] for q in questions}
        nab.redistribute_answers(questions, manifest, {}, locked)
        self.assertTrue(nab.answer_distribution_ok(manifest, questions))
        moved = [qid for qid, a in before.items() if a != next(q["answer"] for q in questions if q["external_id"] == qid)]
        self.assertEqual(moved, ["b-M01-Q1"])


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

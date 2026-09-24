"""Run: python3 scripts/test_mastery_assessment.py (no learner data touched)."""

import datetime as dt
import json
import sqlite3

from mastery_assessment import assess, validate_review
from kaodian_profile import assess_event, ensure_schema, record, recompute_mastery
from kaodian_taxonomy import NUM_DATE

NOW = dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc)


def event(n, day, **changes):
    review = dict(independence="independent", process="correct", basis="draft", execution="smooth",
                  reason="Independent draft contains the correct equation.", template=f"model-{n}",
                  variant=True, mixed=True, timing_valid=True, target_seconds=60, target_basis="Agreed exam budget")
    review.update(changes.pop("review", {}))
    return dict(id=n, question_id=n, session_id=n, evidence_type="practice", is_correct=1,
                elapsed_ms=50000, answered_at=f"2026-09-{day:02} 00:00:00",
                assessment_json=json.dumps(review), **changes)


initial = [event(n, 10 if n < 4 else 11) for n in range(1, 6)]
assert assess(initial, NOW)["level"] == "mastered"
assert assess(initial, NOW)["fluency"] == "fluent"
stable = initial + [event(6, 18)]
assert assess(stable, NOW)["level"] == "stable"
assert assess(initial + [event(6, 17)], NOW)["level"] == "mastered"
assert assess(stable + [event(7, 19, review={"process": "incorrect"}),
                        event(8, 20, review={"process": "incorrect"})], NOW)["level"] == "developing"
assert assess([event(n, 10) for n in range(1, 12)], NOW)["level"] == "initial"
assert assess([event(n, 10, review={"template": "same"}) for n in range(1, 12)], NOW)["independent_samples"] == 1

repeats = [dict(event(n, 10 + n), question_id=1) for n in range(1, 7)]
assert assess(repeats, NOW)["independent_samples"] == 1
assert assess(repeats, NOW)["repeats_excluded"] == 5
assert assess([dict(event(1, 10), is_repeat=True)], NOW)["independent_samples"] == 0
assert assess([dict(event(1, 10), assessment_json=None)], NOW)["level"] == "unassessed"
assert assess([event(1, 10, review={"independence": "assisted"})], NOW)["level"] == "unassessed"
assert assess([event(1, 10, review={"process": "unknown", "basis": "unavailable"})], NOW)["level"] == "unassessed"
assert assess([dict(event(1, 10), is_correct=0)], NOW)["level"] == "initial", "calculation error is not a modeling failure"
assert assess([dict(e, elapsed_ms=120000) for e in initial], NOW)["fluency"] == "slow"
assert assess([dict(e, is_correct=0) for e in initial], NOW)["fluency"] == "unassessed"
assert assess([event(n, 10 + n, review={"timing_valid": False}) for n in range(1, 6)], NOW)["fluency"] == "unassessed"
old = assess(stable, NOW + dt.timedelta(days=40))
assert old["review_due"] and old["fluency"] == "unassessed"
assert assess([dict(e, prior_level="mastered") for e in initial], NOW)["calibration"] == {"samples": 5, "correct": 5}

history = [dict(e, assessment_json=None, objective_result=True) for e in initial]
inherited = assess(history, NOW)
assert inherited["level"] == "unassessed" and inherited["basis"] == "history"
assert inherited["label"] == "历史表现较好" and inherited["history"]["correct"] == 5
assert inherited["fluency"] == "unassessed", "raw time without a target cannot certify fluency"
assert assess([dict(e, is_correct=0) for e in history], NOW)["label"] == "历史薄弱"
assert assess(history + [dict(history[0], id=99, session_id=99)], NOW)["history"]["samples"] == 5
assert assess([dict(e, objective_result=True, assessment_json=json.dumps({**json.loads(e["assessment_json"]), "independence": "assisted"})) for e in initial], NOW)["history"]["samples"] == 0
assert assess([dict(e, assessment_json=None) for e in initial], NOW)["basis"] == "activity"
plateau = [dict(event(n, 10 if n <= 3 else 12), session_id=1 if n <= 3 else 2,
                is_correct=0, objective_result=True, assessment_json=None) for n in range(1, 7)]
assert assess(plateau, NOW)["history"]["plateau"]

for patch in ({"process": "correct", "basis": "unavailable"}, {"target_seconds": -1},
              {"target_seconds": float("nan")}, {"reason": ""}, {"variant": "false"},
              {"mastery": 100}, {"target_basis": ""}):
    try:
        validate_review({**json.loads(initial[0]["assessment_json"]), **patch})
    except ValueError:
        pass
    else:
        raise AssertionError(patch)

conn = sqlite3.connect(":memory:")
ensure_schema(conn)
conn.executescript("""
CREATE TABLE practice_sessions(id INTEGER PRIMARY KEY, profile_reviewed_at TEXT, assessment_baseline TEXT);
CREATE TABLE practice_answers(id INTEGER PRIMARY KEY,session_id INTEGER,question_id INTEGER,
 is_correct INTEGER,time_spent_sec INTEGER,answered_at TEXT,user_answer TEXT);
INSERT INTO practice_sessions VALUES(1,'sealed','{}'),(2,NULL,'{}');
INSERT INTO practice_answers VALUES(1,1,9,0,120,'2026-09-10 00:00:00','B'),(2,2,9,1,30,'2026-09-11 00:00:00','A');
""")
assert record(conn, NUM_DATE, "数量关系", "数学运算", True, 1, "practice", session_id=1, question_id=9)
review = json.loads(initial[0]["assessment_json"])
assert assess_event(conn, 1, 9, review)
assert not assess_event(conn, 1, 9, review), "same review must be idempotent"
saved = json.loads(conn.execute("SELECT assessment_json FROM kaodian_profile").fetchone()[0])
assert saved["evidence"][0]["correct"] is False, "real answer overrides old subjective correctness"
assert saved["evidence"][0]["elapsed_seconds"] == 120
assert saved["evidence"][0]["date"] == "2026-09-10", "use answer time, not review time"
assert record(conn, NUM_DATE, "数量关系", "数学运算", True, source="practice", session_id=2, question_id=9)
assert assess_event(conn, 2, 9, review)
assert conn.execute("SELECT COUNT(*) FROM kaodian_events").fetchone()[0] == 2
assert json.loads(conn.execute("SELECT assessment_json FROM kaodian_profile").fetchone()[0])["independent_samples"] == 1
assert assess_event(conn, 1, 9, {**review, "process": "incorrect"})
assert conn.execute("SELECT COUNT(*) FROM kaodian_assessment_history").fetchone()[0] == 3
conn.execute("UPDATE kaodian_profile SET mastery=99,mastery_source='manual'")
recompute_mastery(conn)
assert conn.execute("SELECT mastery FROM kaodian_profile").fetchone()[0] == 99
assert json.loads(conn.execute("SELECT assessment_json FROM kaodian_profile").fetchone()[0])["level"] != "stable"
conn.close()
print("mastery assessment: ok")

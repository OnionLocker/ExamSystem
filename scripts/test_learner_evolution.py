#!/usr/bin/env python3
"""画像归一→知识债→计划对账的最小闭环集成测试。"""

from __future__ import annotations

import json
import datetime as dt
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from daily_plan_state import reconcile, save_plan, today
from kaodian_taxonomy import NUM_DATE
from learner_snapshot import build_snapshot, recommend_targets, recommendation
from kaodian_profile import record, set_learning_state


ROOT = Path(__file__).resolve().parents[1]

def candidate(tag, module, history_status, attempts=5, plateau=False):
    return {"kaodian": tag, "family": tag, "module": module, "attempts": attempts,
            "family_days_since": 3, "assessment": {"level": "unassessed", "history": {
                "status": history_status, "recent_samples": 5, "plateau": plateau}}}

pool = [candidate(f"quantity-{i}", "数量关系", "weak", 200) for i in range(6)]
pool += [candidate("language", "言语理解与表达", "mixed"), candidate("data", "资料分析", "weak")]
pool += [candidate("legacy-unknown", "未分类", "weak")]
targets, _ = recommend_targets(pool)
assert len([r for r in targets if r["module"] == "数量关系"]) <= 2
assert {r["module"] for r in targets} == {"数量关系", "言语理解与表达", "资料分析"}
assert recommendation(candidate("stuck", "数量关系", "weak", plateau=True))["action"] == "change_method"
assert recommendation(candidate("strong", "判断推理", "strong"))["minutes"] == 10
assert recommendation(candidate("unknown", "判断推理", "limited"))["action"] == "diagnose"
assert not recommend_targets([{**pool[0], "family_days_since": 1}])[0]
assert not recommend_targets([candidate("legacy-only", "未分类", "limited")])[0]


with tempfile.TemporaryDirectory(prefix="learner-evolution-") as temp:
    db_path = Path(temp) / "exam.db"
    env = {**os.environ, "EXAM_DB": str(db_path)}
    init = subprocess.run(
        ["node", "--input-type=module", "-e", "await import('./server/db.js')"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert init.returncode == 0, init.stderr

    conn = sqlite3.connect(db_path)
    question_id = conn.execute("SELECT id FROM questions ORDER BY id LIMIT 1").fetchone()[0]
    conn.execute(
        """
        UPDATE questions
           SET category='数量关系', sub_category='数学运算', tags=?, batch_id='test-batch'
         WHERE id=?
        """,
        (json.dumps([NUM_DATE], ensure_ascii=False), question_id),
    )
    conn.execute("DELETE FROM kaodian_profile")
    conn.execute("DELETE FROM kaodian_events")
    conn.executemany(
        """
        INSERT INTO kaodian_profile(kaodian,module,subtype,attempts,correct,total_ms,last_seen,streak)
        VALUES (?,'数量关系','数学运算',1,0,1000,'2026-08-28',-1)
        """,
        [("日期推算",), ("平年闰年",)],
    )
    conn.executemany(
        """
        INSERT INTO kaodian_events(
          kaodian,question_id,is_correct,elapsed_ms,evidence_type,evidence_weight,answered_at
        ) VALUES (?,?,0,1000,'practice',1.0,'2026-08-28 10:00:00')
        """,
        [("日期推算", question_id), ("平年闰年", question_id)],
    )
    conn.commit()
    conn.close()

    normalized = subprocess.run(
        [
            "python3",
            "scripts/normalize_kaodian_profile.py",
            "--db",
            str(db_path),
            "--apply",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert normalized.returncode == 0, normalized.stderr

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT kaodian,attempts,correct FROM kaodian_profile"
    ).fetchone()
    assert row == (NUM_DATE, 1, 0), row
    conn.execute(
        "INSERT INTO mistakes(question_id,wrong_count,correct_streak,mastered) VALUES (?,1,0,0)",
        (question_id,),
    )
    conn.commit()
    conn.close()

    seeded = subprocess.run(
        [
            "python3",
            "scripts/seed_kaodian_debts.py",
            "--db",
            str(db_path),
            "--apply",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert seeded.returncode == 0, seeded.stderr

    conn = sqlite3.connect(db_path)
    snapshot = build_snapshot(conn)
    assert snapshot["summary"]["open_debt_families"] == 0, "旧错题不能自动变成知识债"
    assert snapshot["open_mistake_families"] == []
    assert snapshot["historical_mistakes"], "legacy mistakes must remain visible, separately from debt"
    set_learning_state(conn, NUM_DATE, "learned")
    record(conn, NUM_DATE, "数量关系", "数学运算", False)
    conn.commit()
    snapshot = build_snapshot(conn)
    assert snapshot["summary"]["open_debt_families"] == 1
    assert snapshot["open_mistake_families"][0]["last_wrong_at"]
    assert "距上次错" in snapshot["compact"]
    plan_date = today()
    save_plan(
        conn,
        plan_date,
        [{"id": "date", "module": "数量关系", "target": NUM_DATE, "batch_id": "test-batch", "count": 1}],
        source="test",
    )
    session_id = conn.execute(
        """
        INSERT INTO practice_sessions(category,total,correct,duration_sec,ended_at)
        VALUES ('test',1,1,30,datetime('now')) RETURNING id
        """
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO practice_answers(session_id,question_id,user_answer,is_correct,time_spent_sec)
        VALUES (?,?, 'A',1,30)
        """,
        (session_id, question_id),
    )
    conn.commit()
    plan = reconcile(conn, plan_date)
    assert plan["items"][0]["done"] == 1
    assert plan["items"][0]["status"] == "done"
    save_plan(conn, plan_date, [{"id": "manual-review", "module": "数量关系", "task_type": "manual",
                               "batch_id": "test-batch", "count": 1, "minutes": 15, "exit_criterion": "复现关键关系"}], merge=True)
    plan = reconcile(conn, plan_date)
    assert len(plan["items"]) == 2 and plan["items"][1]["done"] == 0, "practice must not auto-complete review"
    save_plan(conn, plan_date, [{"id": "date", "done": 0, "verdict": "needs followup", "followup_date": plan_date}], merge=True)
    snapshot = build_snapshot(conn)
    assert snapshot["plan_continuity"]["items"][0]["done"] == 1
    assert snapshot["plan_continuity"]["due_reviews"][0]["id"] == "date"
    assert snapshot["plan_continuity"]["items"][1]["exit_criterion"] == "复现关键关系"
    week_ago = str(dt.date.fromisoformat(plan_date) - dt.timedelta(days=7))
    save_plan(conn, week_ago, [{"id": "week-check", "module": "数量关系", "count": 1,
                               "followup_date": plan_date}])
    assert any(item["id"] == "week-check" for item in build_snapshot(conn)["plan_continuity"]["due_reviews"])
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()

print("learner evolution loop: ok")

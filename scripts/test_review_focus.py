#!/usr/bin/env python3
"""复盘结语用的考点画像：只读当前画像，按别名归并，标出知识债、停滞和本场是否已计入。"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kaodian_profile import ensure_schema
from learner_snapshot import TZ, render_focus

TAG = "数量关系-数学运算-数列问题-@arithmetic-median-sum"
FRESH = "数量关系-数学运算-数列问题-@sequence-general-recurrence"


def seed(conn: sqlite3.Connection) -> None:
    ensure_schema(conn)
    today = str(dt.datetime.now(TZ).date())
    assessment = {
        "label": "初步掌握", "fluency_label": "需提速", "review_due": True,
        "history": {"recent_samples": 5, "correct": 4, "median_seconds": 96.0, "plateau": True},
    }
    conn.execute(
        """INSERT INTO kaodian_profile(kaodian,module,subtype,attempts,correct,total_ms,last_seen,streak,assessment_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (TAG, "数量关系", "数学运算", 5, 4, 480000, today, 2, json.dumps(assessment, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO kaodian_aliases(alias,canonical,module) VALUES (?,?,?)",
        ("数量关系-数学运算-数列问题-等差数列中项求和", TAG, "数量关系"),
    )
    conn.execute(
        "INSERT INTO kaodian_events(kaodian,question_id,session_id,is_correct,evidence_type) VALUES (?,?,?,?,?)",
        ("数量关系-数学运算-数列问题-等差数列中项求和", 11, 7, 1, "practice"),
    )
    conn.execute("INSERT INTO kaodian_debts(kaodian,wrong_count,recovery_streak) VALUES (?,3,1)", (TAG,))
    conn.execute("INSERT INTO kaodian_learning(kaodian,status) VALUES (?, 'learned')", (TAG,))
    conn.commit()


conn = sqlite3.connect(":memory:")
seed(conn)

lines = render_focus(conn, ["数量关系-数学运算-数列问题-等差数列中项求和", TAG, FRESH], session_id=7).splitlines()
assert len(lines) == 2, lines  # 别名与规范名是同一个考点，只出一行
first = lines[0]
for part in (
    TAG, "掌握：初步掌握", "熟练度：需提速", "最近5道首次作答对4，答对题中位用时01:36", "连对2", "上次：今天",
    "知识债：累计错3次，连对1/2", "两轮新题未改善", "待复测", "已含本场记录",
):
    assert part in first, (part, first)
assert lines[1] == f"- {FRESH}｜无画像记录：本场是首次作答", lines[1]

# 别的场次不算本场；没有 session_id 就不判断
assert "已含本场记录" not in render_focus(conn, [TAG], session_id=8)
assert "已含本场记录" not in render_focus(conn, [TAG])

# 没有画像表的新库不报错
assert render_focus(sqlite3.connect(":memory:"), [TAG]) == ""

# 命令行以只读方式打开，不重算、不改库
with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "exam.db"
    disk = sqlite3.connect(db)
    seed(disk)
    before = disk.execute("SELECT assessment_json FROM kaodian_profile WHERE kaodian=?", (TAG,)).fetchone()[0]
    disk.close()
    out = subprocess.run(
        [sys.executable, str(HERE / "learner_snapshot.py"), "--db", str(db), "--focus", TAG, FRESH, "--session-id", "7"],
        capture_output=True, text=True, check=True, env={**os.environ, "EXAM_DB": str(db)},
    ).stdout
    assert "已含本场记录" in out and "无画像记录" in out, out
    disk = sqlite3.connect(db)
    after = disk.execute("SELECT assessment_json FROM kaodian_profile WHERE kaodian=?", (TAG,)).fetchone()[0]
    disk.close()
    assert after == before

print("review focus ok")

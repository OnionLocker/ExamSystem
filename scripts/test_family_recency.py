#!/usr/bin/env python3
"""空标签的排列组合专场，不能把同族特殊模型再推成主攻。"""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kaodian_profile import ensure_schema
from kaodian_taxonomy import NUM_GEOMETRY, NUM_PERM_SPECIAL, kaodian_family
from learner_snapshot import TZ, build_snapshot


assert kaodian_family(NUM_PERM_SPECIAL) == "数量关系-逢考必有的排列组合与概率"

conn = sqlite3.connect(":memory:")
ensure_schema(conn)
conn.executescript(
    """
    CREATE TABLE practice_sessions (
      id INTEGER PRIMARY KEY, category TEXT, total INT, correct INT,
      duration_sec INT, started_at TEXT, ended_at TEXT
    );
    CREATE TABLE practice_answers (
      id INTEGER PRIMARY KEY, session_id INT, question_id INT,
      user_answer TEXT, is_correct INT, time_spent_sec INT, answered_at TEXT
    );
    CREATE TABLE questions (
      id INTEGER PRIMARY KEY, tags TEXT, category TEXT, sub_category TEXT
    );
    CREATE TABLE mistakes (
      question_id INT, mastered INT DEFAULT 0, wrong_count INT, correct_streak INT
    );
    CREATE TABLE user_kv (k TEXT PRIMARY KEY, v TEXT);
    """
)
today = dt.datetime.now(TZ).date()
ago3 = str(today - dt.timedelta(days=3))
yesterday = f"{today - dt.timedelta(days=1)} 05:50:23"
conn.execute(
    """INSERT INTO kaodian_profile(
         kaodian,module,subtype,attempts,correct,total_ms,last_seen,streak,
         mastery,mastery_confidence,mastery_samples,mastery_source)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
    (NUM_PERM_SPECIAL, "数量关系", "逢考必有的排列组合与概率", 6, 2, 6000, ago3, -3, 40, 49, 6, "auto"),
)
conn.execute(
    """INSERT INTO kaodian_profile(
         kaodian,module,subtype,attempts,correct,total_ms,last_seen,streak,
         mastery,mastery_confidence,mastery_samples,mastery_source)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
    (NUM_GEOMETRY, "数量关系", "要抓住常考图形的几何问题", 10, 5, 8000, ago3, -1, 52, 65, 10, "auto"),
)
conn.execute("INSERT INTO questions(id, tags, category, sub_category) VALUES (1, '[]', '数量关系', '数学运算')")
conn.execute(
    """INSERT INTO practice_sessions(id, category, total, correct, duration_sec, ended_at)
       VALUES (1, '20260827_shuliang_plzh_06', 5, 4, 152, ?)""",
    (yesterday,),
)
conn.execute(
    """INSERT INTO practice_answers(session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)
       VALUES (1, 1, 'A', 1, 10, ?)""",
    (yesterday,),
)
conn.commit()

snapshot = build_snapshot(conn)
assert NUM_PERM_SPECIAL not in {row["kaodian"] for row in snapshot["recommended_targets"]}, snapshot["recommended_targets"]
blocked = next(row for row in snapshot["recently_practiced"] if row["kaodian"] == NUM_PERM_SPECIAL)
assert blocked["reason"] == "刚练过不宜主攻", blocked
assert blocked["family_days_since"] <= 1, blocked
geo = next(row for row in snapshot["recommended_targets"] if row["kaodian"] == NUM_GEOMETRY)
assert geo["reason"] == "高置信弱项", geo
assert "刚练过不宜主攻" in snapshot["compact"]
print("family recency: ok")

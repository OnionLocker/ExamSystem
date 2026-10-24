#!/usr/bin/env python3
"""每日复习卷选点：遗忘曲线、题量约束、子考法分配、出题顺序、只读。"""

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

import daily_review_plan as plan_mod
from daily_review_plan import (POLICIES, build_plan, exam_frequency, recall, save_plan, scope_points,
                               stability_of)
from kaodian_profile import ensure_schema

TODAY = dt.date(2026, 10, 16)
SCOPE = POLICIES["数量关系"]["scope"]
POINT = {title: tag for tag, title in scope_points(SCOPE)}


def leaves(module, tags):
    """测试不读知识点目录：每个考点两个子考法 a、b。"""
    table = {tag: [{"tag": f"{tag}-@a", "title": "子考法A"}, {"tag": f"{tag}-@b", "title": "子考法B"}] for tag in tags}
    return table, {leaf["tag"]: leaf["tag"] for items in table.values() for leaf in items}


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    conn.executescript("""
        CREATE TABLE questions (id INTEGER PRIMARY KEY, batch_id TEXT, tags TEXT, category TEXT, sub_category TEXT);
        CREATE TABLE practice_answers (id INTEGER PRIMARY KEY, session_id INTEGER, question_id INTEGER,
          user_answer TEXT, is_correct INTEGER, time_spent_sec INTEGER, answered_at TEXT);
        CREATE TABLE reference_questions (id INTEGER PRIMARY KEY, category TEXT, sub_category TEXT, tags TEXT, source TEXT);
    """)
    return conn


def answer(conn, tag, days_ago, correct, seconds=120, *, qid=None, blank=False, session=1):
    """在 TODAY 之前 days_ago 天答一道题（北京时间中午）；qid 相同表示重做旧题。"""
    if qid is None:
        qid = conn.execute("INSERT INTO questions(tags, category, sub_category) VALUES (?,?,?)",
                           (json.dumps([tag], ensure_ascii=False), "数量关系", "数学运算")).lastrowid
    when = f"{TODAY - dt.timedelta(days=days_ago)} 04:00:00"
    conn.execute("INSERT INTO practice_answers(session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)"
                 " VALUES (?,?,?,?,?,?)", (session, qid, None if blank else "A", int(correct), seconds, when))
    return qid


def practice(conn, title, days_ago, right, wrong, seconds=120, leaf="a"):
    tag = f"{POINT[title]}-@{leaf}"
    for _ in range(right):
        answer(conn, tag, days_ago, True, seconds)
    for _ in range(wrong):
        answer(conn, tag, days_ago, False, seconds)


# ── 遗忘曲线 ──────────────────────────────────────────────
assert abs(recall(3, 3) - 0.9) < 1e-9          # 隔稳定度那么多天，还记得 90%
assert recall(30, 3) < recall(10, 3) < recall(3, 3)
day = lambda n: TODAY - dt.timedelta(days=n)
good = lambda n, repeat=False: {"day": day(n), "correct": True, "repeat": repeat}
bad = lambda n: {"day": day(n), "correct": False, "repeat": False}
assert stability_of([good(9)] * 4)[0] == 2.5
spaced = stability_of([good(9)] * 4 + [good(2)] * 4)[0]
crammed = stability_of([good(9)] * 4 + [good(8)] * 4)[0]
assert spaced > crammed > 2.5, (spaced, crammed)          # 隔得越久还答对，涨得越多
assert stability_of([good(9)] * 4 + [bad(2)] * 4)[0] < 2.5  # 答崩就缩
redo = stability_of([good(9)] * 4 + [good(2, True)] * 4)[0]
assert 2.5 < redo < spaced                                  # 只重做旧题，效果减半
assert stability_of([])[0] is None

# ── 选点 ─────────────────────────────────────────────────
conn = make_db()
practice(conn, "工程问题", 20, 5, 5)                # 久没练、正确率一般
practice(conn, "概率问题", 18, 3, 7)                # 久没练、偏弱
practice(conn, "行程问题", 9, 8, 2)
practice(conn, "几何问题", 7, 9, 1, seconds=400)    # 慢
practice(conn, "容斥原理问题", 6, 8, 2)
practice(conn, "最值问题", 12, 7, 3)
practice(conn, "经济利润问题", 15, 6, 4)
practice(conn, "不定方程问题", 5, 8, 2)
practice(conn, "钟表问题", 4, 9, 1)
practice(conn, "数列问题", 1, 10, 0)                # 昨天刚练过
practice(conn, "年龄问题", 8, 4, 6)                 # 有知识债
practice(conn, "平均数问题", 3, 4, 6)               # 两轮新题没改善
practice(conn, "溶液问题", 10, 8, 2)
for _ in range(6):                                   # 只有几秒就翻过去的空题：不算练过
    answer(conn, f"{POINT['钟表问题']}-@b", 2, False, 2, blank=True)
for _ in range(4):
    answer(conn, f"{POINT['计数模型问题']}-@a", 3, False, 3, blank=True)
conn.execute("INSERT INTO kaodian_debts(kaodian, wrong_count, recovery_streak, mastered) VALUES (?,3,0,0)", (POINT["年龄问题"],))
conn.execute("INSERT INTO kaodian_learning(kaodian, status) VALUES (?, 'learned')", (POINT["年龄问题"],))
conn.execute("INSERT INTO kaodian_profile(kaodian, module, subtype, attempts, correct, assessment_json) VALUES (?,?,?,?,?,?)",
             (POINT["平均数问题"], "数量关系", "数学运算", 10, 4, json.dumps({"history": {"plateau": True}})))
conn.commit()

plan = build_plan(conn, "数量关系", TODAY, leaves_loader=leaves)
points = {p["title"]: p for p in plan["points"]}
assert plan["count"] == 20 == len(plan["slots"]) == sum(p["count"] for p in plan["points"]), plan["count"]
assert 6 <= len(plan["points"]) <= 10, len(plan["points"])
assert all(1 <= p["count"] <= 3 for p in plan["points"])
assert "计数模型问题" not in points and all(o["title"] != "计数模型问题" for o in plan["others"])  # 只有秒翻的空题
ranked = sorted(plan["points"] + plan["others"], key=lambda p: -p["priority"])
assert [p["title"] for p in plan["points"] if p.get("must")] == [p["title"] for p in ranked[:3]]
assert "工程问题" in points and "概率问题" in points
assert points.get("数列问题", {"count": 1})["count"] == 1    # 同族距上次 ≤1 天：最多 1 题
if "数列问题" in points:
    assert "昨天练过" in points["数列问题"]["reason"]
assert points.get("平均数问题", {"count": 2})["count"] <= 2  # 两轮没改善：最多 2 题
assert "知识债未清" in points["年龄问题"]["reason"] if "年龄问题" in points else True
assert "20 天没练" in points["工程问题"]["reason"] and "估计还记得" in points["工程问题"]["reason"]

# 子考法：只练过 a，第一题先给没练过的 b；两题以上 a、b 都覆盖
for point in plan["points"]:
    titles = [leaf["tag"].rsplit("-@", 1)[1] for leaf in point["leaves"]]
    assert sum(leaf["count"] for leaf in point["leaves"]) == point["count"]
    if point["count"] == 1:
        assert titles == ["b"], (point["title"], titles)
    else:
        assert set(titles) == {"a", "b"}, (point["title"], titles)

# 出题顺序打散：能避开时同一考点不连着出
order = [slot["tag"].rsplit("-@", 1)[0] for slot in plan["slots"]]
assert all(a != b for a, b in zip(order, order[1:])), order
assert all(slot["count"] == 1 and slot["difficulty"] in {"auto", "hard"} for slot in plan["slots"])

# 同一天同一份数据：结果完全一样；随机只在到期的点之间
again = build_plan(conn, "数量关系", TODAY, leaves_loader=leaves)
assert again["slots"] == plan["slots"]
top = ranked[0]["priority"]
due_points = [p for p in plan["points"] if p.get("must") or p["priority"] >= 0.5 * top]
for point in plan["points"]:
    # 不到期的点只在到期点按单点上限装不下整卷时补进来
    assert (point in due_points or len(plan["points"]) == 6
            or sum(p["cap"] for p in due_points) < plan["count"]), point["title"]

# 昨天刚练过的点哪怕又弱又有债、排进前三，也只放 1 题
conn3 = make_db()
for title, ago in (("钟表问题", 1), ("工程问题", 12), ("行程问题", 10), ("几何问题", 9), ("最值问题", 8),
                   ("容斥原理问题", 7), ("溶液问题", 6), ("年龄问题", 11)):
    practice(conn3, title, ago, 3, 7)
conn3.execute("INSERT INTO kaodian_debts(kaodian, wrong_count, recovery_streak, mastered) VALUES (?,5,0,0)", (POINT["钟表问题"],))
conn3.execute("INSERT INTO kaodian_learning(kaodian, status) VALUES (?, 'learned')", (POINT["钟表问题"],))
cooled = {p["title"]: p for p in build_plan(conn3, "数量关系", TODAY, leaves_loader=leaves)["points"]}
assert cooled["钟表问题"]["count"] == 1 and "昨天练过" in cooled["钟表问题"]["reason"], cooled["钟表问题"]
assert sum(p["count"] for p in cooled.values()) == 20

# 重做旧题也算练过（刷新“上次”），但只算一半的巩固
conn2 = make_db()
qid = answer(conn2, f"{POINT['工程问题']}-@a", 9, True)
for _ in range(3):
    answer(conn2, f"{POINT['工程问题']}-@a", 9, True)
answer(conn2, f"{POINT['工程问题']}-@a", 1, True, qid=qid, session=2)
state = build_plan(conn2, "数量关系", TODAY, leaves_loader=leaves)
eng = next(p for p in state["points"] + state["others"] if p["title"] == "工程问题")
assert eng["days_since"] == 1 and eng["recent"]["n"] == 4, eng

# 没有作答记录：不出卷，也不去读知识点目录
def boom(*_):
    raise AssertionError("没有作答记录时不该读目录")
empty = build_plan(make_db(), "数量关系", TODAY, leaves_loader=boom)
assert empty["slots"] == [] and empty["note"]
assert build_plan(None, "数量关系", TODAY, leaves_loader=boom)["slots"] == []

# ── 考频 ─────────────────────────────────────────────────
points_all = scope_points(SCOPE)
assert set(exam_frequency(make_db(), SCOPE, points_all, {}).values()) == {1.0}
freq_db = make_db()
for _ in range(4):
    freq_db.execute("INSERT INTO reference_questions(category, sub_category, tags, source) VALUES (?,?,?,?)",
                    ("数量关系", "数学运算", json.dumps([POINT["行程问题"]], ensure_ascii=False), "2024年广东省公务员录用考试"))
freq_db.execute("INSERT INTO reference_questions(category, sub_category, tags, source) VALUES (?,?,?,?)",
                ("数量关系", "数学运算", json.dumps([POINT["工程问题"]], ensure_ascii=False), "2024年浙江省公务员录用考试"))
freq = exam_frequency(freq_db, SCOPE, points_all, {})
assert freq[POINT["行程问题"]] == 1.3 and freq[POINT["年龄问题"]] == 0.7
assert 0.7 < freq[POINT["工程问题"]] < freq[POINT["行程问题"]]

# ── 存档与命令行只读 ──────────────────────────────────────
save_plan(conn, "daily-20261016-shuliang-x", plan)
stored = json.loads(conn.execute("SELECT plan_json FROM daily_review_plans WHERE batch_id=?",
                                 ("daily-20261016-shuliang-x",)).fetchone()[0])
assert stored["slots"] == plan["slots"] and stored["points"][0]["reason"]

# 快照告诉 Hermes：今天的复习卷已经有了，排计划时算进去
from learner_snapshot import daily_review_today, render_compact

for slot in plan["slots"]:
    conn.execute("INSERT INTO questions(batch_id, tags, category, sub_category) VALUES (?,?,?,?)",
                 ("daily-20261016-shuliang-x", json.dumps([slot["tag"]], ensure_ascii=False), "数量关系", "数学运算"))
first_qid = conn.execute("SELECT id FROM questions WHERE batch_id=? ORDER BY id LIMIT 1", ("daily-20261016-shuliang-x",)).fetchone()[0]
conn.execute("INSERT INTO practice_answers(session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)"
             " VALUES (77, ?, 'A', 1, 60, '2026-10-16 03:00:00')", (first_qid,))
today_sets = daily_review_today(conn, TODAY)
assert today_sets == [{"batch_id": "daily-20261016-shuliang-x", "module": "数量关系", "total": 20, "done": 1}], today_sets
assert daily_review_today(conn, TODAY - dt.timedelta(days=1)) == []
assert daily_review_today(sqlite3.connect(":memory:"), TODAY) == []
compact = render_compact({
    "as_of": "2026-10-16T08:00:00+08:00", "recent_sessions": [], "recommended_targets": [], "recently_practiced": [],
    "strengths": [], "open_mistake_families": [], "plan_continuity": {}, "daily_review": today_sets,
    "summary": {"completed_sessions": 0, "profiles": 0, "history_profiles": 0, "reliable_profiles": 0,
                "open_debt_families": 0, "open_mistakes": 0},
})
assert "今日定时复习卷：数量关系 已做1/20（batch_id=daily-20261016-shuliang-x" in compact, compact
assert "不再另排数量关系专项" in compact

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "exam.db"
    sqlite3.connect(db).close()
    before = db.read_bytes()
    out = subprocess.run([sys.executable, str(HERE / "daily_review_plan.py"), "--db", str(db), "--date", str(TODAY)],
                         capture_output=True, text=True, check=True, env={**os.environ, "EXAM_DB": str(db)}).stdout
    assert "无从复习" in out, out
    assert db.read_bytes() == before                     # 预览不建表、不写库

print("daily review plan ok")

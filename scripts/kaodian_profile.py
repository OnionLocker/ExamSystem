#!/usr/bin/env python3
"""考点画像表：随做题积累，沉淀每个考点的掌握度。

设计取舍（ponytail）：不建独立的"考点主数据表"。考点标签是字符串主键，
真题地图里已经有池子，这里只记录"你在这个标签上表现如何"。
"""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "exam.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS kaodian_profile (
    kaodian      TEXT PRIMARY KEY,          -- 考点标签，与 zhenti json 的 knowledge_points 同名
    module       TEXT NOT NULL,
    subtype      TEXT,
    attempts     INTEGER NOT NULL DEFAULT 0,
    correct      INTEGER NOT NULL DEFAULT 0,
    total_ms     INTEGER NOT NULL DEFAULT 0, -- 累计用时，算平均速度
    last_seen    TEXT,                       -- ISO 日期，控制"两周内不重复出"
    streak       INTEGER NOT NULL DEFAULT 0, -- 连续答对数，负数表示连续错
    note         TEXT,                       -- 复盘时人工/AI 写入的定性判断
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kp_module ON kaodian_profile(module);
CREATE INDEX IF NOT EXISTS idx_kp_lastseen ON kaodian_profile(last_seen);

-- 每次作答的流水，画像是它的聚合。保留流水才能回溯趋势（是一直弱还是最近变弱）
CREATE TABLE IF NOT EXISTS kaodian_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kaodian     TEXT NOT NULL,
    question_id INTEGER,
    is_correct  INTEGER NOT NULL,
    elapsed_ms  INTEGER,
    answered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ke_kaodian ON kaodian_events(kaodian, answered_at);
"""

RECORD = """
INSERT INTO kaodian_profile (kaodian, module, subtype, attempts, correct, total_ms, last_seen, streak)
VALUES (?, ?, ?, 1, ?, ?, date('now'), ?)
ON CONFLICT(kaodian) DO UPDATE SET
    attempts   = attempts + 1,
    correct    = correct + excluded.correct,
    total_ms   = total_ms + excluded.total_ms,
    last_seen  = date('now'),
    streak     = CASE WHEN excluded.correct = 1
                      THEN MAX(streak, 0) + 1
                      ELSE MIN(streak, 0) - 1 END,
    updated_at = datetime('now')
"""


def record(conn, kaodian, module, subtype, is_correct, elapsed_ms=0):
    """记一次作答。画像和流水一起更新。"""
    c = 1 if is_correct else 0
    conn.execute(RECORD, (kaodian, module, subtype, c, elapsed_ms, 1 if c else -1))
    conn.execute(
        "INSERT INTO kaodian_events (kaodian, is_correct, elapsed_ms) VALUES (?,?,?)",
        (kaodian, c, elapsed_ms),
    )


def weak_points(conn, limit=20, min_attempts=3):
    """薄弱考点：做过至少 min_attempts 次且正确率低的，按 (正确率, 连错) 排序。"""
    return conn.execute("""
        SELECT kaodian, module, subtype, attempts, correct,
               ROUND(correct * 100.0 / attempts, 1) AS acc,
               CASE WHEN attempts > 0 THEN total_ms / attempts / 1000 ELSE 0 END AS avg_sec,
               streak, last_seen
        FROM kaodian_profile
        WHERE attempts >= ?
        ORDER BY acc ASC, streak ASC, attempts DESC
        LIMIT ?
    """, (min_attempts, limit)).fetchall()


def _demo():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    for ok in (False, False, True):
        record(conn, "假言命题逆否", "判断推理", "逻辑判断-翻译推理", ok, 60000)
    for _ in range(4):
        record(conn, "两期比重差", "资料分析", "资料分析-比重", True, 45000)
    row = conn.execute(
        "SELECT attempts, correct, streak, total_ms FROM kaodian_profile WHERE kaodian='假言命题逆否'"
    ).fetchone()
    assert row == (3, 1, 1, 180000), row
    assert conn.execute("SELECT COUNT(*) FROM kaodian_events").fetchone()[0] == 7
    weak = weak_points(conn, min_attempts=3)
    assert weak[0][0] == "假言命题逆否", weak       # 33% 排在 100% 前面
    assert weak[0][5] == 33.3 and weak[0][6] == 60, weak
    # 连错要累加为负
    record(conn, "两期比重差", "资料分析", "资料分析-比重", False, 50000)
    record(conn, "两期比重差", "资料分析", "资料分析-比重", False, 50000)
    assert conn.execute("SELECT streak FROM kaodian_profile WHERE kaodian='两期比重差'").fetchone()[0] == -2
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        conn = sqlite3.connect(DB)
        conn.executescript(SCHEMA)
        conn.commit()
        print(f"schema applied -> {DB}")

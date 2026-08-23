#!/usr/bin/env python3
"""考点画像表：随做题积累，沉淀每个考点的掌握度。

设计取舍（ponytail）：不建独立的"考点主数据表"。考点标签是字符串主键，
真题地图里已经有池子，这里只记录"你在这个标签上表现如何"。遇到新考点时，
先用 register_knowledge_point() 预登记到同一张表，后续再由 record() 累积表现。
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
    mastery      INTEGER,                    -- 0~100，对话里按实际情况改
    mastery_note TEXT,
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


def register_knowledge_point(conn, kaodian, module, subtype, note=""):
    """登记词表里没有的新考点，不制造第二套主数据表。

    新点以 attempts=0 进入画像，后续第一次作答直接复用同一标签调用 record()。
    note 建议包含来源题号、定义和与相邻考点的区分，方便下次复盘确认是否合并。
    """
    conn.execute("""
        INSERT INTO kaodian_profile
          (kaodian, module, subtype, attempts, correct, total_ms, last_seen, streak, note)
        VALUES (?, ?, ?, 0, 0, 0, NULL, 0, ?)
        ON CONFLICT(kaodian) DO UPDATE SET
          module = excluded.module,
          subtype = excluded.subtype,
          note = CASE
                   WHEN excluded.note = '' THEN kaodian_profile.note
                   WHEN kaodian_profile.note IS NULL OR kaodian_profile.note = ''
                     THEN excluded.note
                   ELSE kaodian_profile.note || '；' || excluded.note
                 END,
          updated_at = datetime('now')
    """, (kaodian, module, subtype, note.strip()))


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


def ensure_schema(conn):
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(kaodian_profile)")}
    if "mastery" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery INTEGER")
    if "mastery_note" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery_note TEXT")


def score_of(row):
    """row: mapping or sequence with mastery/attempts/correct."""
    if row is None:
        return None
    if isinstance(row, dict):
        mastery, attempts, correct = row.get("mastery"), row.get("attempts") or 0, row.get("correct") or 0
    else:
        mastery, attempts, correct = row[0], row[1] or 0, row[2] or 0
    if mastery is not None:
        return int(mastery)
    if attempts > 0:
        return round(correct * 100.0 / attempts)
    return None


def set_mastery(conn, kaodian, score, note="", module="", subtype=""):
    """按实际情况写入掌握度。没有这个考点就建一行。"""
    ensure_schema(conn)
    score = max(0, min(100, int(score)))
    note = (note or "").strip()
    module = (module or "").strip()
    subtype = (subtype or "").strip()
    exists = conn.execute("SELECT 1 FROM kaodian_profile WHERE kaodian=?", (kaodian,)).fetchone()
    if exists:
        conn.execute(
            """
            UPDATE kaodian_profile
               SET mastery = ?,
                   mastery_note = CASE WHEN ? = '' THEN mastery_note ELSE ? END,
                   module = CASE WHEN ? = '' THEN module ELSE ? END,
                   subtype = CASE WHEN ? = '' THEN subtype ELSE ? END,
                   updated_at = datetime('now')
             WHERE kaodian = ?
            """,
            (score, note, note, module, module, subtype, subtype, kaodian),
        )
    else:
        inferred = module or (kaodian.split("-")[0] if "-" in kaodian else "未分类")
        conn.execute(
            """
            INSERT INTO kaodian_profile
              (kaodian, module, subtype, attempts, correct, total_ms, last_seen, streak, note, mastery, mastery_note)
            VALUES (?, ?, ?, 0, 0, 0, date('now'), 0, ?, ?, ?)
            """,
            (kaodian, inferred, subtype, note, score, note),
        )
    return score


def list_points(conn):
    ensure_schema(conn)
    return conn.execute(
        """
        SELECT kaodian, module, subtype, attempts, correct, streak,
               mastery, mastery_note, note, last_seen
          FROM kaodian_profile
         ORDER BY module, kaodian
        """
    ).fetchall()


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
    register_knowledge_point(
        conn,
        "政治理论-党史党建-党的组织路线",
        "政治理论",
        "党史党建",
        "来源：复盘新题；待确认与组织建设表述的边界",
    )
    pending = conn.execute(
        "SELECT attempts, note FROM kaodian_profile WHERE kaodian=?",
        ("政治理论-党史党建-党的组织路线",),
    ).fetchone()
    assert pending == (0, "来源：复盘新题；待确认与组织建设表述的边界"), pending
    set_mastery(conn, "假言命题逆否", 35, "刚讲完逆否，自己做还要停很久")
    assert conn.execute("SELECT mastery FROM kaodian_profile WHERE kaodian='假言命题逆否'").fetchone()[0] == 35
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    elif "--register" in sys.argv:
        args = sys.argv[sys.argv.index("--register") + 1:]
        if len(args) < 3:
            raise SystemExit("用法：--register <标签> <模块> <题型/一级> [备注]")
        tag, module, subtype, *note = args
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        register_knowledge_point(conn, tag, module, subtype, " ".join(note))
        conn.commit()
        print(f"registered -> {tag}")
    elif "--mastery" in sys.argv:
        args = sys.argv[sys.argv.index("--mastery") + 1:]
        if len(args) < 2:
            raise SystemExit("用法：--mastery <标签> <0-100> [一句依据] [模块] [一级]")
        tag, score, *rest = args
        note = rest[0] if rest else ""
        module = rest[1] if len(rest) > 1 else ""
        subtype = rest[2] if len(rest) > 2 else ""
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        set_mastery(conn, tag, score, note, module, subtype)
        conn.commit()
        print(f"mastery -> {tag} = {int(score)}")
    elif "--list" in sys.argv:
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        rows = list_points(conn)
        if not rows:
            print("(empty)")
        for kaodian, module, subtype, attempts, correct, streak, mastery, mastery_note, note, last_seen in rows:
            shown = mastery if mastery is not None else (
                round(correct * 100.0 / attempts) if attempts else "-"
            )
            print(f"{shown}\t{kaodian}\t{module}\t{subtype or ''}\t{correct}/{attempts}\t{mastery_note or note or ''}")
    else:
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        conn.commit()
        print(f"schema applied -> {DB}")

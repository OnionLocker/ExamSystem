#!/usr/bin/env python3
"""考点画像表：随做题积累，沉淀每个考点的掌握度。

设计取舍（ponytail）：不建独立的"考点主数据表"。考点标签是字符串主键，
真题地图里已经有池子，这里只记录"你在这个标签上表现如何"。熟练度由事件流水
按 Beta 先验、时间衰减和证据来源自动估计；遇到新考点时，先登记再记录事件。
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

from kaodian_taxonomy import (
    assert_registerable_tag,
    canonicalize,
    is_fenbi_primary,
    normalize_module,
    parse_fenbi_tag,
    static_alias,
)

DB = Path(os.environ.get("EXAM_DB") or Path(__file__).resolve().parent.parent / "data" / "exam.db")

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
    mastery      INTEGER,                    -- 统计估计值，不是裸正确率
    mastery_note TEXT,
    mastery_confidence INTEGER,
    mastery_samples REAL,
    mastery_source TEXT NOT NULL DEFAULT 'auto',
    mastery_updated_at TEXT,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kp_module ON kaodian_profile(module);
CREATE INDEX IF NOT EXISTS idx_kp_lastseen ON kaodian_profile(last_seen);

-- 每次作答的流水，画像是它的聚合。保留流水才能回溯趋势（是一直弱还是最近变弱）
CREATE TABLE IF NOT EXISTS kaodian_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kaodian     TEXT NOT NULL,
    question_id INTEGER,
    session_id  INTEGER,
    is_correct  INTEGER NOT NULL,
    elapsed_ms  INTEGER,
    evidence_type TEXT NOT NULL DEFAULT 'hermes',
    evidence_weight REAL NOT NULL DEFAULT 1.0,
    answered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ke_kaodian ON kaodian_events(kaodian, answered_at);

CREATE TABLE IF NOT EXISTS kaodian_aliases (
    alias       TEXT PRIMARY KEY,
    canonical   TEXT NOT NULL,
    module      TEXT NOT NULL,
    subtype     TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kaodian_alias_canonical
    ON kaodian_aliases(canonical);

CREATE TABLE IF NOT EXISTS kaodian_debts (
    kaodian          TEXT PRIMARY KEY,
    wrong_count      INTEGER NOT NULL DEFAULT 1,
    recovery_streak  INTEGER NOT NULL DEFAULT 0,
    last_wrong_at    TEXT,
    last_seen_at     TEXT,
    mastered         INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
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


SOURCE_WEIGHTS = {"practice": 1.0, "exam": 1.0, "hermes": 0.7, "manual": 0.4}
PRIOR_CORRECT = 2.0
PRIOR_WRONG = 2.0
HALF_LIFE_DAYS = 21.0
CONFIDENCE_SCALE = 8.0


def calculate_mastery(events, now=None):
    """用带时间衰减的 Beta 估计，返回分数、置信度和有效样本数。"""
    import datetime as dt

    now = now or dt.datetime.now(dt.timezone.utc)
    effective = 0.0
    weighted_correct = 0.0
    for event in events:
        source = event["evidence_type"] if event["evidence_type"] in SOURCE_WEIGHTS else "hermes"
        try:
            weight = min(1.5, max(0.1, float(event["evidence_weight"])))
        except (TypeError, ValueError):
            weight = 1.0
        raw = str(event["answered_at"] or "").replace(" ", "T")
        try:
            seen = dt.datetime.fromisoformat(raw).replace(tzinfo=dt.timezone.utc)
            age = max(0.0, (now - seen).total_seconds() / 86400.0)
        except ValueError:
            age = 0.0
        factor = SOURCE_WEIGHTS[source] * weight * (0.5 ** (age / HALF_LIFE_DAYS))
        effective += factor
        weighted_correct += factor * int(bool(event["is_correct"]))
    if effective <= 0:
        return None
    estimate = (PRIOR_CORRECT + weighted_correct) / (PRIOR_CORRECT + PRIOR_WRONG + effective)
    confidence = 1 - __import__("math").exp(-effective / CONFIDENCE_SCALE)
    return {
        "mastery": round(max(0.0, min(100.0, estimate * 100))),
        "mastery_confidence": round(max(0.0, min(100.0, confidence * 100))),
        "mastery_samples": round(effective, 2),
    }


def recompute_mastery(conn, kaodian=None):
    """按事件流水重算画像；手工估计不会覆盖自动值。"""
    ensure_schema(conn)
    profiles = conn.execute(
        "SELECT kaodian FROM kaodian_profile WHERE mastery_source != 'manual'"
        + (" AND kaodian=?" if kaodian else ""),
        ((kaodian,) if kaodian else ()),
    ).fetchall()
    for (tag,) in profiles:
        events = conn.execute(
            """SELECT MAX(e.is_correct), MIN(e.answered_at),
                      MAX(e.evidence_type), MAX(e.evidence_weight)
                 FROM kaodian_events e
                 LEFT JOIN kaodian_aliases a ON a.alias=e.kaodian
                WHERE COALESCE(a.canonical, e.kaodian)=?
                GROUP BY CASE
                  WHEN e.session_id IS NOT NULL
                    THEN 's:' || e.session_id || ':' || COALESCE(e.question_id, 0) || ':' || e.evidence_type
                  WHEN e.question_id IS NOT NULL
                    THEN 'q:' || e.question_id || ':' || e.answered_at || ':' || e.evidence_type
                  ELSE 'e:' || e.id
                END
                ORDER BY MIN(e.answered_at), MIN(e.id)""",
            (tag,),
        ).fetchall()
        score = calculate_mastery([
            {
                "is_correct": row[0],
                "answered_at": row[1],
                "evidence_type": row[2],
                "evidence_weight": row[3],
            }
            for row in events
        ])
        if score:
            conn.execute(
                """UPDATE kaodian_profile
                   SET mastery=?, mastery_confidence=?, mastery_samples=?,
                       mastery_source='auto', mastery_updated_at=datetime('now'),
                       updated_at=datetime('now') WHERE kaodian=?""",
                (score["mastery"], score["mastery_confidence"], score["mastery_samples"], tag),
            )


def wellformed_kaodian(kaodian: str) -> bool:
    """粉笔 `模块-一级-二级`，或挂在 L3 下的 L4。"""
    return is_fenbi_primary(kaodian)


def resolve_kaodian(conn, kaodian, module="", subtype="", verbatim=False):
    row = conn.execute(
        "SELECT canonical, module, subtype FROM kaodian_aliases WHERE alias=?",
        (kaodian,),
    ).fetchone()
    if row:
        stored = static_alias(row[0]) or row[0]
        parsed = parse_fenbi_tag(stored)
        return stored, row[1] or (parsed[0] if parsed else row[1]), row[2] or (parsed[1] if parsed else row[2])
    # 显式登记新考点时按原样收下：--register 本身就是「这是个独立新点」的声明，
    # 不能再让关键词兜底把它并进某个老考点（那样新点永远建不起来）。
    if verbatim and wellformed_kaodian(kaodian):
        canonical = kaodian
    else:
        canonical = canonicalize(kaodian, module, subtype)
    parsed = parse_fenbi_tag(canonical)
    normalized_module = normalize_module(module or (parsed[0] if parsed else canonical.split("-", 1)[0]))
    canonical_subtype = parsed[1] if parsed else (canonical.split("-")[1] if "-" in canonical else subtype)
    conn.execute(
        """INSERT INTO kaodian_aliases(alias, canonical, module, subtype)
           VALUES (?,?,?,?)
           ON CONFLICT(alias) DO NOTHING""",
        (kaodian, canonical, normalized_module, canonical_subtype),
    )
    return canonical, normalized_module, canonical_subtype


DEBT_CLEAR = 2


def practice_session_sealed(conn, session_id):
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(practice_sessions)")}
    except sqlite3.OperationalError:
        return False
    if "profile_reviewed_at" not in cols:
        return False
    row = conn.execute(
        "SELECT profile_reviewed_at FROM practice_sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    return bool(row and row[0])


def seal_practice(conn, session_id):
    ensure_schema(conn)
    try:
        cur = conn.execute(
            """UPDATE practice_sessions
                  SET profile_reviewed_at=datetime('now')
                WHERE id=? AND profile_reviewed_at IS NULL""",
            (session_id,),
        )
        return cur.rowcount > 0
    except sqlite3.OperationalError:
        return False


def apply_debt(conn, kaodian, is_correct):
    if is_correct:
        conn.execute(
            """UPDATE kaodian_debts
                  SET recovery_streak = recovery_streak + 1,
                      last_seen_at = datetime('now'),
                      mastered = CASE WHEN recovery_streak + 1 >= ? THEN 1 ELSE 0 END,
                      updated_at = datetime('now')
                WHERE kaodian = ? AND mastered = 0""",
            (DEBT_CLEAR, kaodian),
        )
        return
    conn.execute(
        """INSERT INTO kaodian_debts
             (kaodian, wrong_count, recovery_streak, last_wrong_at, last_seen_at, mastered)
           VALUES (?, 1, 0, datetime('now'), datetime('now'), 0)
           ON CONFLICT(kaodian) DO UPDATE SET
             wrong_count = wrong_count + 1,
             recovery_streak = 0,
             last_wrong_at = datetime('now'),
             last_seen_at = datetime('now'),
             mastered = 0,
             updated_at = datetime('now')""",
        (kaodian,),
    )


def rebuild_kaodian(conn, kaodian):
    rows = conn.execute(
        """SELECT e.is_correct, e.elapsed_ms, e.answered_at
             FROM kaodian_events e
             LEFT JOIN kaodian_aliases a ON a.alias = e.kaodian
            WHERE COALESCE(a.canonical, e.kaodian)=?
            ORDER BY e.answered_at, e.id""",
        (kaodian,),
    ).fetchall()
    attempts = len(rows)
    correct = sum(int(row[0]) for row in rows)
    total_ms = sum(int(row[1] or 0) for row in rows)
    streak = 0
    wrong_count = 0
    recovery = 0
    mastered = 0
    last_wrong = None
    last_seen_at = None
    for ok, _ms, when in rows:
        last_seen_at = when
        if int(ok):
            streak = streak + 1 if streak >= 0 else 1
            recovery += 1
            if recovery >= DEBT_CLEAR:
                mastered = 1
        else:
            streak = streak - 1 if streak <= 0 else -1
            wrong_count += 1
            recovery = 0
            mastered = 0
            last_wrong = when
    last_seen = str(last_seen_at)[:10] if last_seen_at else None
    conn.execute(
        """UPDATE kaodian_profile
              SET attempts=?, correct=?, total_ms=?, last_seen=?, streak=?,
                  updated_at=datetime('now')
            WHERE kaodian=?""",
        (attempts, correct, total_ms, last_seen, streak, kaodian),
    )
    if attempts == 0:
        conn.execute("DELETE FROM kaodian_debts WHERE kaodian=?", (kaodian,))
    else:
        conn.execute(
            """INSERT INTO kaodian_debts
                 (kaodian, wrong_count, recovery_streak, last_wrong_at, last_seen_at, mastered)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(kaodian) DO UPDATE SET
                 wrong_count=excluded.wrong_count,
                 recovery_streak=excluded.recovery_streak,
                 last_wrong_at=excluded.last_wrong_at,
                 last_seen_at=excluded.last_seen_at,
                 mastered=excluded.mastered,
                 updated_at=datetime('now')""",
            (kaodian, wrong_count, recovery, last_wrong, last_seen_at, mastered),
        )
    recompute_mastery(conn, kaodian)


def undo_practice_session(conn, session_id):
    ensure_schema(conn)
    tags = [row[0] for row in conn.execute(
        "SELECT DISTINCT kaodian FROM kaodian_events WHERE session_id=?",
        (session_id,),
    )]
    conn.execute("DELETE FROM kaodian_events WHERE session_id=?", (session_id,))
    try:
        conn.execute(
            "UPDATE practice_sessions SET profile_reviewed_at=NULL WHERE id=?",
            (session_id,),
        )
    except sqlite3.OperationalError:
        pass
    canonicals = set()
    for tag in tags:
        canonical, _module, _subtype = resolve_kaodian(conn, tag)
        canonicals.add(canonical)
    for kaodian in canonicals:
        rebuild_kaodian(conn, kaodian)
    return len(tags)


def record(conn, kaodian, module, subtype, is_correct, elapsed_ms=0, source="hermes", weight=1.0, session_id=None, question_id=None, practice_lock=False):
    """记录一次证据并按全部历史流水重算熟练度。

    录屏/真题复盘传入 session_id=exam_analyses.id、question_id=题号、source=exam，
    同一场同一题只落一条；重复复盘直接跳过，不增加样本。
    """
    ensure_schema(conn)
    if practice_lock and session_id is not None and practice_session_sealed(conn, session_id):
        return False
    if practice_lock and session_id is not None and question_id is not None:
        already = conn.execute(
            "SELECT 1 FROM kaodian_events WHERE session_id=? AND question_id=? LIMIT 1",
            (int(session_id), int(question_id)),
        ).fetchone()
        if already:
            return False
    kaodian, module, subtype = resolve_kaodian(conn, kaodian, module, subtype)
    c = 1 if is_correct else 0
    source = source if source in SOURCE_WEIGHTS else "hermes"
    if session_id is not None:

        cur = conn.execute(
            """INSERT OR IGNORE INTO kaodian_events
               (kaodian, question_id, session_id, is_correct, elapsed_ms, evidence_type, evidence_weight)
               VALUES (?,?,?,?,?,?,?)""",
            (kaodian, question_id, int(session_id), c, elapsed_ms, source, weight),
        )
        if cur.rowcount == 0:
            return False
    else:
        conn.execute(
            """INSERT INTO kaodian_events
               (kaodian, is_correct, elapsed_ms, evidence_type, evidence_weight)
               VALUES (?,?,?,?,?)""",
            (kaodian, c, elapsed_ms, source, weight),
        )
    conn.execute(RECORD, (kaodian, module, subtype, c, elapsed_ms, 1 if c else -1))
    apply_debt(conn, kaodian, c)
    recompute_mastery(conn, kaodian)
    return True


def register_knowledge_point(conn, kaodian, module, subtype, note=""):
    """登记词表里没有的新考点，不制造第二套主数据表。

    新点以 attempts=0 进入画像，后续第一次作答直接复用同一标签调用 record()。
    note 建议包含来源题号、定义和与相邻考点的区分，方便下次复盘确认是否合并。
    """
    ensure_schema(conn)
    kaodian = assert_registerable_tag(kaodian, module)
    kaodian, module, subtype = resolve_kaodian(conn, kaodian, module, subtype, verbatim=True)
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
    """薄弱考点：优先可信画像，再看掌握度、连错与耗时。"""
    return conn.execute("""
        SELECT kaodian, module, subtype, attempts, correct,
               ROUND(correct * 100.0 / attempts, 1) AS acc,
               CASE WHEN attempts > 0 THEN total_ms / attempts / 1000 ELSE 0 END AS avg_sec,
               streak, last_seen, mastery, mastery_confidence, mastery_samples
        FROM kaodian_profile
        WHERE attempts >= ?
        ORDER BY CASE WHEN COALESCE(mastery_confidence,0) >= 25 THEN 0 ELSE 1 END,
                 COALESCE(mastery, acc) ASC,
                 streak ASC,
                 attempts DESC
        LIMIT ?
    """, (min_attempts, limit)).fetchall()


def ensure_schema(conn):
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(kaodian_profile)")}
    if "mastery" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery INTEGER")
    if "mastery_note" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery_note TEXT")
    if "mastery_confidence" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery_confidence INTEGER")
    if "mastery_samples" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery_samples REAL")
    if "mastery_source" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery_source TEXT NOT NULL DEFAULT 'auto'")
    if "mastery_updated_at" not in cols:
        conn.execute("ALTER TABLE kaodian_profile ADD COLUMN mastery_updated_at TEXT")
    event_cols = {r[1] for r in conn.execute("PRAGMA table_info(kaodian_events)")}
    if "evidence_type" not in event_cols:
        conn.execute("ALTER TABLE kaodian_events ADD COLUMN evidence_type TEXT NOT NULL DEFAULT 'hermes'")
    if "evidence_weight" not in event_cols:
        conn.execute("ALTER TABLE kaodian_events ADD COLUMN evidence_weight REAL NOT NULL DEFAULT 1.0")
    if "session_id" not in event_cols:
        conn.execute("ALTER TABLE kaodian_events ADD COLUMN session_id INTEGER")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kaodian_aliases (
          alias TEXT PRIMARY KEY,
          canonical TEXT NOT NULL,
          module TEXT NOT NULL,
          subtype TEXT,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_ke_practice_evidence
        ON kaodian_events(kaodian, question_id, session_id, evidence_type)
        WHERE session_id IS NOT NULL
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_ke_exam_item
        ON kaodian_events(session_id, question_id, evidence_type)
        WHERE evidence_type = 'exam' AND session_id IS NOT NULL AND question_id IS NOT NULL
    """)

    try:
        ps_cols = {r[1] for r in conn.execute("PRAGMA table_info(practice_sessions)")}
        if ps_cols and "profile_reviewed_at" not in ps_cols:
            conn.execute("ALTER TABLE practice_sessions ADD COLUMN profile_reviewed_at TEXT")
    except sqlite3.OperationalError:
        pass


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
    kaodian, module, subtype = resolve_kaodian(conn, kaodian, module, subtype)
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
                   mastery_source = 'manual',
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
              (kaodian, module, subtype, attempts, correct, total_ms, last_seen, streak,
               note, mastery, mastery_note, mastery_source)
            VALUES (?, ?, ?, 0, 0, 0, date('now'), 0, ?, ?, ?, 'manual')
            """,
            (kaodian, inferred, subtype, note, score, note),
        )
    return score


def list_points(conn):
    ensure_schema(conn)
    return conn.execute(
        """
        SELECT kaodian, module, subtype, attempts, correct, streak,
               mastery, mastery_note, mastery_confidence, mastery_samples,
               mastery_source, note, last_seen
          FROM kaodian_profile
         ORDER BY module, kaodian
        """
    ).fetchall()


def _demo():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    import datetime as dt

    estimate = calculate_mastery(
        [{
            "is_correct": 1,
            "answered_at": "2026-08-24T00:00:00+00:00",
            "evidence_type": "hermes",
            "evidence_weight": 1,
        }],
        dt.datetime(2026, 8, 24, tzinfo=dt.timezone.utc),
    )
    assert estimate["mastery"] == 57 and estimate["mastery_confidence"] == 8, estimate
    translation = "判断推理-逻辑判断-翻译推理"
    for ok in (False, False, True):
        record(conn, "假言命题逆否", "判断推理", "逻辑判断-翻译推理", ok, 60000)
    for _ in range(4):
        record(conn, "两期比重差", "资料分析", "资料分析-比重", True, 45000)
    row = conn.execute(
        "SELECT attempts, correct, streak, total_ms FROM kaodian_profile WHERE kaodian=?",
        (translation,),
    ).fetchone()
    assert row == (3, 1, 1, 180000), row
    assert conn.execute("SELECT COUNT(*) FROM kaodian_events").fetchone()[0] == 7
    weak = {row[0]: row for row in weak_points(conn, min_attempts=3)}
    assert translation in weak and weak[translation][5] == 33.3, weak
    # 连错要累加为负
    record(conn, "两期比重差", "资料分析", "资料分析-比重", False, 50000)
    record(conn, "两期比重差", "资料分析", "资料分析-比重", False, 50000)
    share_diff = "资料分析-比重类-比重趋势、比重差与比值差"
    assert conn.execute("SELECT streak FROM kaodian_profile WHERE kaodian=?", (share_diff,)).fetchone()[0] == -2
    register_knowledge_point(
        conn,
        "政治理论-毛中特-党的基本知识-党的组织路线",
        "政治理论",
        "毛中特",
        "来源：复盘新题；待确认与组织建设表述的边界",
    )
    pending = conn.execute(
        "SELECT attempts, note FROM kaodian_profile WHERE kaodian=?",
        ("政治理论-毛中特-党的基本知识-党的组织路线",),
    ).fetchone()
    assert pending == (0, "来源：复盘新题；待确认与组织建设表述的边界"), pending
    set_mastery(conn, "假言命题逆否", 35, "刚讲完逆否，自己做还要停很久")
    assert conn.execute("SELECT mastery FROM kaodian_profile WHERE kaodian=?", (translation,)).fetchone()[0] == 35
    record(conn, "假言命题逆否", "判断推理", "逻辑判断-翻译推理", True, 60000)
    assert conn.execute("SELECT mastery, mastery_source FROM kaodian_profile WHERE kaodian=?", (translation,)).fetchone() == (35, "manual")
    exam_tag = translation
    assert record(conn, exam_tag, "判断推理", "逻辑判断", False, 90000, "exam", session_id=12, question_id=7) is True
    before = conn.execute("SELECT attempts, correct FROM kaodian_profile WHERE kaodian=?", (exam_tag,)).fetchone()
    assert record(conn, exam_tag, "判断推理", "逻辑判断", True, 1000, "exam", session_id=12, question_id=7) is False
    assert record(conn, "资料分析-增长率-一般增长率", "资料分析", "增长率", True, 1000, "exam", session_id=12, question_id=7) is False
    after = conn.execute("SELECT attempts, correct FROM kaodian_profile WHERE kaodian=?", (exam_tag,)).fetchone()
    assert after == before
    assert conn.execute(
        "SELECT COUNT(*) FROM kaodian_events WHERE session_id=12 AND evidence_type='exam'"
    ).fetchone()[0] == 1
    print("demo ok")



def coverage_report(conn, keyword=""):
    """按一级知识点汇总：这张卡有几种考法、建了几个标签、各自多少题多少练习。

    给 Hermes 回答「这个知识点下的题型覆盖全面了吗」。
    """
    from kaodian_taxonomy import canon_index, canonicalize

    stock, seen = {}, {}
    try:
        rows = conn.execute(
            "SELECT tags, COUNT(*) FROM questions WHERE tags IS NOT NULL GROUP BY tags"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []  # 题库表由导入器建；画像库单独存在时只报考点不报库存
    for tag, n in rows:
        try:
            first = json.loads(tag)[0]
        except (ValueError, IndexError, TypeError):
            continue
        stock[first] = stock.get(first, 0) + n
    for row in conn.execute(
        "SELECT kaodian, attempts, mastery, mastery_confidence FROM kaodian_profile"
    ):
        seen[row[0]] = row[1:]

    out = []
    for card in canon_index():
        # 图形推理/科学推理/资料分析走日练，专项出不了，列出来只是噪音
        if any("图形推理" in t for t in card["tags"]) or not card["tags"]:
            continue
        family = card["tags"][0].rsplit("-", 1)[0]
        if keyword and keyword not in family and keyword not in card["title"]:
            continue
        # canon 里写的可能是旧名，先归一到实际在用的标签，库存/练习才对得上
        usable = {canonicalize(t, card["module"]) for t in card["tags"]}
        rows = []
        for tag in sorted(usable):
            attempts, mastery, conf = seen.get(tag, (0, None, 0))
            rows.append({
                "tag": tag,
                "stock": stock.get(tag, 0),
                "attempts": attempts or 0,
                "mastery": mastery,
                "confidence": conf or 0,
            })
        # 一张卡只有一个标签时，卡内条目既可能是并列步骤也可能是可拆的考法，
        # 不替 Hermes 下结论，如实列出让它自己判断。
        untagged = [b["text"] for b in card["bullets"] if not b["tag"]] if len(rows) <= 1 else []
        out.append({
            "module": card["module"],
            "title": card["title"],
            "family": family,
            "methods": len(card["bullets"]),
            "rows": rows,
            "untagged": untagged,
        })
    return out


def print_coverage(conn, keyword=""):
    import signal

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    cards = coverage_report(conn, keyword)
    if not cards:
        print("(没有匹配的考点，换个关键词)")
        return
    for card in cards:
        n_tag, n_method = len(card["rows"]), card["methods"]
        mark = "已按考法拆分" if n_tag > 1 else ("单一考法" if n_method <= 1 else "尚未拆分")
        print(f"【{card['module']}】{card['title']}")
        print(f"    {n_tag} 标签 / 卡内 {n_method} 条 · {mark}")
        for row in card["rows"]:
            m = "-" if row["mastery"] is None else row["mastery"]
            print(
                f"      题{row['stock']:<4}练{row['attempts']:<4}掌握{m:<5}"
                f"{row['tag'].rsplit('-', 1)[-1]}"
            )
        if card["untagged"]:
            print("      卡内条目（并列步骤还是可拆考法，自行判断）：" + "｜".join(card["untagged"]))


def plan_blueprint(conn, keyword, count):
    """在匹配到的考点之间均衡分题，弱项优先，直接吐出 quiz_generator 能吃的蓝图。"""
    cards = coverage_report(conn, keyword)
    from kaodian_taxonomy import LEGACY_TAGS

    pool = [row for card in cards for row in card["rows"] if row["tag"] not in LEGACY_TAGS]
    if not pool:
        raise SystemExit(f"没有匹配 '{keyword}' 的考点；先 --coverage 看有哪些")
    pool.sort(key=lambda r: (r["mastery"] if r["mastery"] is not None else 50, r["stock"]))
    pool = pool[:count]
    base, extra = divmod(count, len(pool))
    slots = []
    for index, row in enumerate(pool):
        n = base + (1 if index < extra else 0)
        if n:
            slots.append({"tag": row["tag"], "count": n})
    return {"slots": slots}


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
    elif "--record" in sys.argv:
        args = sys.argv[sys.argv.index("--record") + 1:]
        exam_id = practice_id = item = None
        weight = 1.0
        cleaned = []
        i = 0
        while i < len(args):
            if args[i] == "--exam-id" and i + 1 < len(args):
                exam_id = int(args[i + 1]); i += 2
            elif args[i] == "--practice-id" and i + 1 < len(args):
                practice_id = int(args[i + 1]); i += 2
            elif args[i] == "--item" and i + 1 < len(args):
                item = int(args[i + 1]); i += 2
            elif args[i] == "--weight" and i + 1 < len(args):
                weight = float(args[i + 1]); i += 2
            else:
                cleaned.append(args[i]); i += 1
        if len(cleaned) < 4:
            raise SystemExit(
                "用法：--record <标签> <模块> <题型/一级> <0|1> [用时毫秒] [practice|exam|hermes|manual] "
                "[--weight 0.1-1.5] [--practice-id 练习场次 --item 题目id | --exam-id 场次id --item 题号]"
            )
        if exam_id is not None and practice_id is not None:
            raise SystemExit("--exam-id 和 --practice-id 不能一起用")
        tag, module, subtype, result, *rest = cleaned
        elapsed_ms = 0
        source = "hermes"
        for tok in rest:
            if tok in SOURCE_WEIGHTS:
                source = tok
            elif tok.isdigit():
                elapsed_ms = int(tok)
            else:
                try:
                    parsed = float(tok)
                except ValueError:
                    parsed = None
                if parsed is not None and 0.1 <= parsed <= 1.5:
                    weight = parsed
        session_id = practice_id if practice_id is not None else exam_id
        if session_id is not None and item is None:
            raise SystemExit("带场次写入必须同时给 --item")
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        if practice_id is not None and practice_session_sealed(conn, practice_id):
            print(f"already sealed -> practice {practice_id}")
        else:
            added = record(
                conn, tag, module, subtype,
                result in {"1", "true", "True", "对", "正确"},
                elapsed_ms, source, weight,
                session_id=session_id, question_id=item,
                practice_lock=practice_id is not None,
            )
            conn.commit()
            if not added:
                print(f"already recorded -> session {session_id} item {item}")
            else:
                stored, _, _ = resolve_kaodian(conn, tag, module, subtype)
                row = conn.execute(
                    "SELECT mastery, mastery_confidence, mastery_samples FROM kaodian_profile WHERE kaodian=?",
                    (stored,),
                ).fetchone()
                print(f"recorded -> {stored}: mastery={row[0]} confidence={row[1]} samples={row[2]}")
    elif "--seal-practice" in sys.argv:
        args = sys.argv[sys.argv.index("--seal-practice") + 1:]
        if not args:
            raise SystemExit("用法：--seal-practice <practice_sessions.id>")
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        changed = seal_practice(conn, int(args[0]))
        conn.commit()
        print(f"{'sealed' if changed else 'already sealed'} -> practice {args[0]}")
    elif "--undo-practice" in sys.argv:
        args = sys.argv[sys.argv.index("--undo-practice") + 1:]
        if not args:
            raise SystemExit("用法：--undo-practice <practice_sessions.id>")
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        n = undo_practice_session(conn, int(args[0]))
        conn.commit()
        print(f"undone practice {args[0]} -> {n} event tags")
    elif "--recompute" in sys.argv:
        args = sys.argv[sys.argv.index("--recompute") + 1:]
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        recompute_mastery(conn, args[0] if args else None)
        conn.commit()
        print(f"recomputed -> {args[0] if args else 'all'}")
    elif "--mastery" in sys.argv:
        args = sys.argv[sys.argv.index("--mastery") + 1:]
        if len(args) < 2:
            raise SystemExit("用法：--mastery <标签> <0-100> [一句依据] [模块] [一级]（仅人工覆盖，Hermes 不应使用）")
        tag, score, *rest = args
        note = rest[0] if rest else ""
        module = rest[1] if len(rest) > 1 else ""
        subtype = rest[2] if len(rest) > 2 else ""
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        set_mastery(conn, tag, score, note, module, subtype)
        conn.commit()
        print(f"mastery -> {tag} = {int(score)}")
    elif "--coverage" in sys.argv:
        args = [a for a in sys.argv[sys.argv.index("--coverage") + 1:] if not a.startswith("-")]
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        print_coverage(conn, args[0] if args else "")
    elif "--plan" in sys.argv:
        args = [a for a in sys.argv[sys.argv.index("--plan") + 1:] if not a.startswith("-")]
        if not args:
            raise SystemExit("用法：--plan <考点关键词> [--count N]")
        count = 5
        if "--count" in sys.argv:
            count = int(sys.argv[sys.argv.index("--count") + 1])
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        print(json.dumps(plan_blueprint(conn, args[0], count), ensure_ascii=False))
    elif "--list" in sys.argv:
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        rows = list_points(conn)
        if not rows:
            print("(empty)")
        for kaodian, module, subtype, attempts, correct, streak, mastery, mastery_note, confidence, samples, source, note, last_seen in rows:
            shown = mastery if mastery is not None else (
                round(correct * 100.0 / attempts) if attempts else "-"
            )
            print(f"{shown}\t{kaodian}\t{module}\t{subtype or ''}\t{correct}/{attempts}\t置信度={confidence or 0}%\t样本={samples or 0}\t来源={source or 'auto'}\t{mastery_note or note or ''}")
    else:
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        conn.commit()
        print(f"schema applied -> {DB}")

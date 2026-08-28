#!/usr/bin/env python3
"""考点画像表：随做题积累，沉淀每个考点的掌握度。

设计取舍（ponytail）：不建独立的"考点主数据表"。考点标签是字符串主键，
真题地图里已经有池子，这里只记录"你在这个标签上表现如何"。熟练度由事件流水
按 Beta 先验、时间衰减和证据来源自动估计；遇到新考点时，先登记再记录事件。
"""

import sqlite3
import sys
from pathlib import Path

from kaodian_taxonomy import canonicalize, normalize_module

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


SOURCE_WEIGHTS = {"practice": 1.0, "hermes": 0.7, "manual": 0.4}
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


def resolve_kaodian(conn, kaodian, module="", subtype=""):
    row = conn.execute(
        "SELECT canonical, module, subtype FROM kaodian_aliases WHERE alias=?",
        (kaodian,),
    ).fetchone()
    if row:
        return row[0], row[1], row[2]
    canonical = canonicalize(kaodian, module, subtype)
    normalized_module = normalize_module(module or canonical.split("-", 1)[0])
    canonical_subtype = canonical.split("-")[1] if "-" in canonical else subtype
    conn.execute(
        """INSERT INTO kaodian_aliases(alias, canonical, module, subtype)
           VALUES (?,?,?,?)
           ON CONFLICT(alias) DO NOTHING""",
        (kaodian, canonical, normalized_module, canonical_subtype),
    )
    return canonical, normalized_module, canonical_subtype


def record(conn, kaodian, module, subtype, is_correct, elapsed_ms=0, source="hermes", weight=1.0):
    """记录一次证据并按全部历史流水重算熟练度。"""
    ensure_schema(conn)
    kaodian, module, subtype = resolve_kaodian(conn, kaodian, module, subtype)
    c = 1 if is_correct else 0
    conn.execute(RECORD, (kaodian, module, subtype, c, elapsed_ms, 1 if c else -1))
    conn.execute(
        """INSERT INTO kaodian_events
           (kaodian, is_correct, elapsed_ms, evidence_type, evidence_weight)
           VALUES (?,?,?,?,?)""",
        (kaodian, c, elapsed_ms, source if source in SOURCE_WEIGHTS else "hermes", weight),
    )
    recompute_mastery(conn, kaodian)


def register_knowledge_point(conn, kaodian, module, subtype, note=""):
    """登记词表里没有的新考点，不制造第二套主数据表。

    新点以 attempts=0 进入画像，后续第一次作答直接复用同一标签调用 record()。
    note 建议包含来源题号、定义和与相邻考点的区分，方便下次复盘确认是否合并。
    """
    ensure_schema(conn)
    kaodian, module, subtype = resolve_kaodian(conn, kaodian, module, subtype)
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
    record(conn, "假言命题逆否", "判断推理", "逻辑判断-翻译推理", True, 60000)
    assert conn.execute("SELECT mastery, mastery_source FROM kaodian_profile WHERE kaodian='假言命题逆否'").fetchone() == (35, "manual")
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
    elif "--record" in sys.argv:
        args = sys.argv[sys.argv.index("--record") + 1:]
        if len(args) < 4:
            raise SystemExit("用法：--record <标签> <模块> <题型/一级> <0|1> [用时毫秒] [practice|hermes|manual]")
        tag, module, subtype, result, *rest = args
        source = rest[1] if len(rest) > 1 else "hermes"
        elapsed_ms = int(rest[0]) if rest and rest[0].isdigit() else 0
        conn = sqlite3.connect(DB)
        ensure_schema(conn)
        record(conn, tag, module, subtype, result in {"1", "true", "True", "对", "正确"}, elapsed_ms, source)
        conn.commit()
        row = conn.execute(
            "SELECT mastery, mastery_confidence, mastery_samples FROM kaodian_profile WHERE kaodian=?",
            (tag,),
        ).fetchone()
        print(f"recorded -> {tag}: mastery={row[0]} confidence={row[1]} samples={row[2]}")
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

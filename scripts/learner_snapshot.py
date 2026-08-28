#!/usr/bin/env python3
"""生成供 Hermes/每日计划使用的精确学员快照。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path

from kaodian_profile import recompute_mastery
from kaodian_taxonomy import canonicalize, kaodian_family, parse_tags


DB = Path(os.environ.get("EXAM_DB") or Path(__file__).resolve().parents[1] / "data" / "exam.db")
TZ = dt.timezone(dt.timedelta(hours=8))
FAMILY_MAIN_COOLDOWN_DAYS = 1
SESSION_FAMILY_HINTS = (
    ("plzh", "数量关系-逢考必有的排列组合与概率"),
    ("date_cycle", "数量关系-有规律的周期循环与要算准的日期星期"),
    ("date-cycle", "数量关系-有规律的周期循环与要算准的日期星期"),
)


def days_since(value: str | None, today: dt.date) -> int | None:
    try:
        return max(0, (today - dt.date.fromisoformat(str(value)[:10])).days)
    except (TypeError, ValueError):
        return None


def compact_profile(row: sqlite3.Row, today: dt.date, family_last: dict[str, str] | None = None) -> dict:
    family = kaodian_family(row["kaodian"])
    return {
        "kaodian": row["kaodian"],
        "module": row["module"],
        "family": family,
        "attempts": row["attempts"],
        "accuracy": round(row["correct"] * 100 / row["attempts"]) if row["attempts"] else None,
        "mastery": row["mastery"],
        "confidence": row["mastery_confidence"] or 0,
        "streak": row["streak"],
        "avg_sec": round(row["total_ms"] / row["attempts"] / 1000) if row["attempts"] else 0,
        "days_since": days_since(row["last_seen"], today),
        "family_days_since": days_since((family_last or {}).get(family), today),
    }


def _touch_family(store: dict[str, str], family: str, when: str | None) -> None:
    day = str(when or "")[:10]
    if not family or len(day) < 10:
        return
    prev = store.get(family)
    if prev is None or day > prev:
        store[family] = day


def family_from_session_category(category: str) -> str | None:
    text = (category or "").lower()
    for needle, family in SESSION_FAMILY_HINTS:
        if needle in text:
            return family
    return None


def collect_family_last_seen(conn: sqlite3.Connection, alias_map: dict[str, str]) -> dict[str, str]:
    store: dict[str, str] = {}
    for row in conn.execute(
        "SELECT kaodian, last_seen FROM kaodian_profile WHERE attempts > 0"
    ):
        _touch_family(store, kaodian_family(row["kaodian"]), row["last_seen"])
    for row in conn.execute("SELECT kaodian, answered_at FROM kaodian_events"):
        raw = row["kaodian"] or ""
        canonical = alias_map.get(raw) or canonicalize(raw)
        _touch_family(store, kaodian_family(canonical), row["answered_at"])
    try:
        for row in conn.execute(
            """
            SELECT s.category, s.ended_at, q.tags, q.category AS q_category, q.sub_category
              FROM practice_answers pa
              JOIN practice_sessions s ON s.id = pa.session_id
              LEFT JOIN questions q ON q.id = pa.question_id
             WHERE s.ended_at IS NOT NULL
            """
        ):
            when = row["ended_at"]
            tags = parse_tags(row["tags"])
            if tags:
                for tag in tags:
                    canonical = alias_map.get(tag) or canonicalize(
                        tag, row["q_category"] or "", row["sub_category"] or ""
                    )
                    _touch_family(store, kaodian_family(canonical), when)
            else:
                _touch_family(store, family_from_session_category(row["category"]) or "", when)
    except sqlite3.OperationalError:
        pass
    return store


def family_too_recent(row: dict) -> bool:
    gap = row.get("family_days_since")
    return gap is not None and gap <= FAMILY_MAIN_COOLDOWN_DAYS


def build_snapshot(conn: sqlite3.Connection) -> dict:
    conn.row_factory = sqlite3.Row
    recompute_mastery(conn)
    conn.commit()
    now = dt.datetime.now(TZ)
    today = now.date()
    alias_map = {
        row["alias"]: row["canonical"]
        for row in conn.execute("SELECT alias,canonical FROM kaodian_aliases")
    }
    family_last = collect_family_last_seen(conn, alias_map)

    profiles = [
        compact_profile(row, today, family_last)
        for row in conn.execute(
            """
            SELECT kaodian,module,subtype,attempts,correct,total_ms,last_seen,
                   streak,mastery,mastery_confidence,mastery_samples
              FROM kaodian_profile
             WHERE attempts > 0
            """
        )
    ]
    reliable = [row for row in profiles if row["confidence"] >= 40]
    weaknesses = sorted(
        (row for row in reliable if (row["mastery"] or 50) < 60 or row["streak"] <= -2),
        key=lambda row: (row["mastery"] or 50, row["streak"], -row["confidence"]),
    )
    strengths = sorted(
        (row for row in reliable if (row["mastery"] or 0) >= 70 and row["streak"] >= 2),
        key=lambda row: (-(row["mastery"] or 0), -row["confidence"]),
    )
    needs_measurement = sorted(
        (row for row in profiles if row["confidence"] < 40),
        key=lambda row: (-row["attempts"], row["mastery"] or 50),
    )
    overdue = sorted(
        (
            row for row in profiles
            if row["days_since"] is not None
            and row["days_since"] >= 14
            and row["confidence"] >= 25
        ),
        key=lambda row: (-row["days_since"], row["mastery"] or 50),
    )

    recent_sessions = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id,category,total,correct,duration_sec,ended_at
              FROM practice_sessions
             WHERE ended_at IS NOT NULL
             ORDER BY id DESC LIMIT 5
            """
        )
    ]
    for row in recent_sessions:
        row["accuracy"] = round(row["correct"] * 100 / row["total"]) if row["total"] else 0

    mistake_counts: Counter[str] = Counter()
    for row in conn.execute(
        """
        SELECT q.tags,q.category,q.sub_category
          FROM mistakes m
          JOIN questions q ON q.id=m.question_id
         WHERE m.mastered=0
        """
    ):
        try:
            tags = json.loads(row["tags"] or "[]")
        except json.JSONDecodeError:
            tags = []
        if not tags:
            continue
        raw = str(tags[0])
        canonical = alias_map.get(raw) or canonicalize(
            raw, row["category"] or "", row["sub_category"] or ""
        )
        mistake_counts[canonical] += 1
    debt_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT kaodian,wrong_count,recovery_streak,last_wrong_at,last_seen_at
              FROM kaodian_debts
             WHERE mastered=0
             ORDER BY wrong_count DESC,last_wrong_at DESC
            """
        )
    ]

    recent_digest = {}
    digest_row = conn.execute(
        "SELECT v FROM user_kv WHERE k='study_digest_v1'"
    ).fetchone()
    if digest_row:
        try:
            digest = json.loads(digest_row["v"])
            for offset in (0, 1):
                day = str(today - dt.timedelta(days=offset))
                if digest.get(day):
                    recent_digest[day] = digest[day]
        except (TypeError, json.JSONDecodeError):
            pass

    recommended: list[dict] = []
    recent_blocked: list[dict] = []
    seen_kaodian: set[str] = set()
    for reason, rows in (
        ("高置信弱项", weaknesses),
        ("到期回捞", overdue),
        ("低置信待测", needs_measurement),
    ):
        for row in rows:
            if row["kaodian"] in seen_kaodian:
                continue
            seen_kaodian.add(row["kaodian"])
            if family_too_recent(row):
                recent_blocked.append({**row, "reason": "刚练过不宜主攻"})
            elif len(recommended) < 5:
                recommended.append({**row, "reason": reason})

    snapshot = {
        "as_of": now.isoformat(timespec="seconds"),
        "summary": {
            "profiles": len(profiles),
            "reliable_profiles": len(reliable),
            "high_confidence_weaknesses": len(weaknesses),
            "open_mistakes": sum(mistake_counts.values()),
            "open_debt_families": len(debt_rows),
            "completed_sessions": conn.execute(
                "SELECT COUNT(*) FROM practice_sessions WHERE ended_at IS NOT NULL"
            ).fetchone()[0],
        },
        "recommended_targets": recommended[:5],
        "recently_practiced": recent_blocked[:5],
        "weaknesses": weaknesses[:8],
        "strengths": strengths[:5],
        "needs_measurement": needs_measurement[:5],
        "overdue": overdue[:5],
        "open_mistake_families": [
            {
                "kaodian": row["kaodian"],
                "count": row["wrong_count"],
                "recovery_streak": row["recovery_streak"],
            }
            for row in debt_rows[:8]
        ] if debt_rows else [
            {"kaodian": tag, "count": count, "recovery_streak": 0}
            for tag, count in mistake_counts.most_common(8)
        ],
        "recent_sessions": recent_sessions,
        "recent_digest": recent_digest,
    }
    snapshot["compact"] = render_compact(snapshot)
    return snapshot


def _compact_target_line(item: dict) -> str:
    recency = ""
    if item.get("days_since") is not None:
        recency = f" 本点{item['days_since']}天"
    if item.get("family_days_since") is not None:
        recency += f" 同族{item['family_days_since']}天"
    return (
        f"- {item['reason']}｜{item['kaodian']}｜掌握{item['mastery']} "
        f"置信{item['confidence']} 样本{item['attempts']} 连续{item['streak']}"
        f"{recency}"
    )


def render_compact(snapshot: dict) -> str:
    summary = snapshot["summary"]
    lines = [
        f"学员快照 {snapshot['as_of']}",
        (
            f"已完成{summary['completed_sessions']}场；规范画像{summary['profiles']}个，"
            f"其中可信{summary['reliable_profiles']}个；未清知识债"
            f"{summary['open_debt_families']}类/{summary['open_mistakes']}题。"
        ),
    ]
    if snapshot["recent_sessions"]:
        bits = [
            f"{row['category']} {row['correct']}/{row['total']} {row['ended_at']}"
            for row in snapshot["recent_sessions"][:3]
        ]
        lines.append("最近练习：" + "；".join(bits))
    if snapshot["recommended_targets"]:
        lines.append("下一步候选：")
        for item in snapshot["recommended_targets"][:5]:
            lines.append(_compact_target_line(item))
    blocked = snapshot.get("recently_practiced") or []
    if blocked:
        lines.append("刚练过不宜主攻：")
        for item in blocked[:5]:
            lines.append(_compact_target_line(item))
    if snapshot["recommended_targets"] or blocked:
        lines.append(
            "出题纪律：用户没点名时，同族距上次≤1天不当本批主攻"
            "（排列组合三个子点算同一族，日期与周期算同一族）；"
            "最多盲盒混入2道结构变式；禁止同场景换数字。"
            "优先选同族距上次≥2天的高置信弱项。"
        )
    if snapshot["strengths"]:
        lines.append(
            "已稳定：" + "；".join(item["kaodian"] for item in snapshot["strengths"][:3])
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    try:
        snapshot = build_snapshot(conn)
    finally:
        conn.close()
    print(snapshot["compact"] if args.compact else json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

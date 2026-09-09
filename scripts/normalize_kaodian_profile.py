#!/usr/bin/env python3
"""按 kaodian_aliases 将碎片化画像汇总到规范考点。

默认只预览；传 --apply 才写库。原始 kaodian_events 不改名，便于回溯。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from kaodian_profile import calculate_mastery
from kaodian_taxonomy import canonicalize, normalize_module, seed_aliases


DB = Path(__file__).resolve().parents[1] / "data" / "exam.db"


def rebuild(conn: sqlite3.Connection, apply: bool) -> dict:
    conn.row_factory = sqlite3.Row
    old_profiles = {
        row["kaodian"]: dict(row)
        for row in conn.execute("SELECT * FROM kaodian_profile")
    }
    if apply:
        conn.execute("BEGIN IMMEDIATE")
    aliases = seed_aliases(conn)
    events = [dict(row) for row in conn.execute(
        """
        SELECT id, kaodian, question_id, is_correct, elapsed_ms,
               evidence_type, evidence_weight, answered_at
          FROM kaodian_events
         ORDER BY answered_at, id
        """
    )]

    grouped: dict[str, list[dict]] = defaultdict(list)
    duplicate_events = 0
    seen = set()
    for event in events:
        old = old_profiles.get(event["kaodian"], {})
        module = old.get("module", "")
        if module == "未分类":
            module = ""
        alias_canonical = aliases.get(event["kaodian"])
        if alias_canonical and str(alias_canonical).startswith("未分类-"):
            alias_canonical = None
        canonical = alias_canonical or canonicalize(
            event["kaodian"],
            module,
            old.get("subtype", ""),
        )
        if event["question_id"] is not None:
            key = (
                canonical,
                event["question_id"],
                event["evidence_type"],
                event["answered_at"],
            )
            if key in seen:
                duplicate_events += 1
                continue
            seen.add(key)
        grouped[canonical].append(event)

    # 保留尚无事件但已经登记的考点。
    for alias, profile in old_profiles.items():
        canonical = aliases.get(alias) or canonicalize(
            alias, profile.get("module", ""), profile.get("subtype", "")
        )
        grouped.setdefault(canonical, [])
    grouped = {
        kaodian: events
        for kaodian, events in grouped.items()
        if events or not kaodian.startswith("未分类-")
    }

    rows = []
    for canonical, canonical_events in sorted(grouped.items()):
        source_profiles = [
            profile
            for alias, profile in old_profiles.items()
            if aliases.get(alias, alias) == canonical
        ]
        module = normalize_module(
            next((p.get("module") for p in source_profiles if p.get("module")), "")
            or canonical.split("-", 1)[0]
        )
        parts = canonical.split("-")
        subtype = parts[1] if len(parts) > 1 else next(
            (p.get("subtype") for p in source_profiles if p.get("subtype")), None
        )
        attempts = len(canonical_events)
        correct = sum(1 for event in canonical_events if event["is_correct"])
        total_ms = sum(int(event["elapsed_ms"] or 0) for event in canonical_events)
        last_seen = max(
            (str(event["answered_at"])[:10] for event in canonical_events),
            default=next((p.get("last_seen") for p in source_profiles if p.get("last_seen")), None),
        )
        streak = 0
        for event in canonical_events:
            if event["is_correct"]:
                streak = max(streak, 0) + 1
            else:
                streak = min(streak, 0) - 1

        notes = []
        for profile in source_profiles:
            for value in (profile.get("note"), profile.get("mastery_note")):
                value = str(value or "").strip()
                if value and value not in notes:
                    notes.append(value)
        note = "；".join(notes)[:4000] or None
        manual = next(
            (p for p in source_profiles if p.get("mastery_source") == "manual"),
            None,
        )
        score = calculate_mastery(canonical_events) if canonical_events else None
        rows.append({
            "kaodian": canonical,
            "module": module,
            "subtype": subtype,
            "attempts": attempts,
            "correct": correct,
            "total_ms": total_ms,
            "last_seen": last_seen,
            "streak": streak,
            "note": note,
            "mastery": manual.get("mastery") if manual else (score or {}).get("mastery"),
            "mastery_note": manual.get("mastery_note") if manual else None,
            "mastery_confidence": None if manual else (score or {}).get("mastery_confidence"),
            "mastery_samples": None if manual else (score or {}).get("mastery_samples"),
            "mastery_source": "manual" if manual else "auto",
        })

    before_attempts = sum(int(profile.get("attempts") or 0) for profile in old_profiles.values())
    summary = {
        "profiles_before": len(old_profiles),
        "profiles_after": len(rows),
        "attempts_before": before_attempts,
        "events_total": len(events),
        "events_after_alias_dedupe": sum(row["attempts"] for row in rows),
        "duplicate_events_collapsed": duplicate_events,
        "aliases": len(aliases),
        "applied": apply,
        "top_profiles": sorted(
            ({
                "kaodian": row["kaodian"],
                "attempts": row["attempts"],
                "correct": row["correct"],
                "mastery": row["mastery"],
                "confidence": row["mastery_confidence"],
            } for row in rows),
            key=lambda row: (-row["attempts"], row["kaodian"]),
        )[:20],
    }
    if not apply:
        conn.rollback()
        return summary

    insert = conn.execute
    try:
        conn.execute("DELETE FROM kaodian_profile")
        for row in rows:
            insert(
                """
                INSERT INTO kaodian_profile (
                  kaodian, module, subtype, attempts, correct, total_ms,
                  last_seen, streak, note, mastery, mastery_note,
                  mastery_confidence, mastery_samples, mastery_source,
                  mastery_updated_at, updated_at
                ) VALUES (
                  :kaodian, :module, :subtype, :attempts, :correct, :total_ms,
                  :last_seen, :streak, :note, :mastery, :mastery_note,
                  :mastery_confidence, :mastery_samples, :mastery_source,
                  datetime('now', '+8 hours'), datetime('now', '+8 hours')
                )
                """,
                row,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    try:
        print(json.dumps(rebuild(conn, args.apply), ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

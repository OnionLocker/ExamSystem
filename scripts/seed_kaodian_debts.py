#!/usr/bin/env python3
"""从题目级错题本一次性建立规范考点知识债。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from kaodian_taxonomy import canonicalize


DB = Path(__file__).resolve().parents[1] / "data" / "exam.db"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kaodian_debts (
          kaodian TEXT PRIMARY KEY,
          wrong_count INTEGER NOT NULL DEFAULT 1,
          recovery_streak INTEGER NOT NULL DEFAULT 0,
          last_wrong_at TEXT,
          last_seen_at TEXT,
          mastered INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours'))
        )
        """
    )
    existing = conn.execute("SELECT COUNT(*) FROM kaodian_debts").fetchone()[0]
    if existing and not args.force:
        raise SystemExit(f"kaodian_debts 已有 {existing} 条；拒绝覆盖，需显式 --force")
    aliases = {
        row["alias"]: row["canonical"]
        for row in conn.execute("SELECT alias,canonical FROM kaodian_aliases")
    }
    grouped = defaultdict(lambda: {"wrong_count": 0, "last_wrong_at": None})
    for row in conn.execute(
        """
        SELECT m.wrong_count,m.last_wrong_at,q.tags,q.category,q.sub_category
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
        canonical = aliases.get(raw) or canonicalize(
            raw, row["category"] or "", row["sub_category"] or ""
        )
        item = grouped[canonical]
        item["wrong_count"] += int(row["wrong_count"] or 1)
        if not item["last_wrong_at"] or str(row["last_wrong_at"]) > item["last_wrong_at"]:
            item["last_wrong_at"] = str(row["last_wrong_at"])
    summary = {
        "existing": existing,
        "families": len(grouped),
        "wrong_events": sum(item["wrong_count"] for item in grouped.values()),
        "applied": args.apply,
        "items": [
            {"kaodian": tag, **value}
            for tag, value in sorted(
                grouped.items(),
                key=lambda pair: (-pair[1]["wrong_count"], pair[0]),
            )
        ],
    }
    if args.apply:
        conn.execute("DELETE FROM kaodian_debts")
        conn.executemany(
            """
            INSERT INTO kaodian_debts(
              kaodian,wrong_count,recovery_streak,last_wrong_at,last_seen_at,mastered
            ) VALUES (?,?,0,?,?,0)
            """,
            [
                (tag, value["wrong_count"], value["last_wrong_at"], value["last_wrong_at"])
                for tag, value in grouped.items()
            ],
        )
        conn.commit()
    else:
        conn.rollback()
    conn.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

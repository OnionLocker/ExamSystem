#!/usr/bin/env python3
"""给 20260827 排列组合六场补三级标签，并按作答重写考点流水。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from kaodian_taxonomy import NUM_PERM_BASIC, NUM_PERM_REVERSE, NUM_PERM_SPECIAL
from normalize_kaodian_profile import rebuild


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "exam.db"
BATCH_PREFIX = "20260827_shuliang_plzh_"
SPECIAL_HINTS = (
    "隔板", "插空", "捆绑", "环形", "圆桌", "围坐", "错位",
    "分组", "分堆", "消序", "相同", "允许为0", "允许某些",
)
REVERSE_HINTS = ("正难则反", "反面容斥", "反面排除", "反面法")
GRID_HINTS = ("网格", "街区", "路径")


def classify(stem: str, analysis: str) -> str:
    text = f"{stem}\n{analysis}"
    if any(hint in text for hint in SPECIAL_HINTS):
        return NUM_PERM_SPECIAL
    if any(hint in text for hint in REVERSE_HINTS) and not any(hint in text for hint in GRID_HINTS):
        return NUM_PERM_REVERSE
    return NUM_PERM_BASIC


def load_batch_tags() -> dict[str, str]:
    mapping = {}
    for path in sorted((ROOT / "batches").glob(f"{BATCH_PREFIX}*/questions.json")):
        for question in json.loads(path.read_text(encoding="utf-8")):
            external_id = question.get("external_id")
            if not external_id:
                continue
            mapping[external_id] = classify(
                question.get("stem") or "",
                question.get("explanation") or question.get("analysis") or "",
            )
    return mapping


def apply(conn: sqlite3.Connection, mapping: dict[str, str]) -> dict:
    conn.row_factory = sqlite3.Row
    rows = list(
        conn.execute(
            "SELECT id, external_id, batch_id FROM questions WHERE batch_id LIKE ?",
            (f"{BATCH_PREFIX}%",),
        )
    )
    if len(rows) != 50:
        raise ValueError(f"期望 50 道排列组合题，实际 {len(rows)}")
    missing = [row["external_id"] for row in rows if row["external_id"] not in mapping]
    if missing:
        raise ValueError(f"草稿里找不到: {missing[:5]}")

    by_tag: dict[str, int] = {}
    ids = []
    for row in rows:
        tag = mapping[row["external_id"]]
        by_tag[tag] = by_tag.get(tag, 0) + 1
        ids.append(row["id"])
        conn.execute(
            "UPDATE questions SET tags=? WHERE id=?",
            (json.dumps([tag], ensure_ascii=False), row["id"]),
        )

    placeholders = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM kaodian_events WHERE question_id IN ({placeholders})", ids)
    inserted = 0
    for answer in conn.execute(
        f"""
        SELECT pa.session_id, pa.question_id, pa.is_correct, pa.time_spent_sec,
               pa.answered_at, s.ended_at, q.external_id
          FROM practice_answers pa
          JOIN questions q ON q.id = pa.question_id
          JOIN practice_sessions s ON s.id = pa.session_id
         WHERE pa.question_id IN ({placeholders})
           AND pa.user_answer IS NOT NULL
           AND pa.user_answer != ''
        """,
        ids,
    ):
        tag = mapping[answer["external_id"]]
        when = answer["answered_at"] or answer["ended_at"]
        conn.execute(
            """
            INSERT INTO kaodian_events(
              kaodian, question_id, session_id, is_correct, elapsed_ms,
              evidence_type, evidence_weight, answered_at
            ) VALUES (?, ?, ?, ?, ?, 'practice', 1.0, ?)
            """,
            (
                tag,
                answer["question_id"],
                answer["session_id"],
                int(answer["is_correct"] or 0),
                int(answer["time_spent_sec"] or 0) * 1000,
                when,
            ),
        )
        inserted += 1
    conn.commit()
    summary = rebuild(conn, apply=True)
    summary["tagged"] = by_tag
    summary["events_inserted"] = inserted
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    mapping = load_batch_tags()
    counts: dict[str, int] = {}
    for tag in mapping.values():
        counts[tag] = counts.get(tag, 0) + 1
    if not args.apply:
        print(json.dumps({"tagged": counts, "questions": len(mapping)}, ensure_ascii=False, indent=2))
        return 0
    conn = sqlite3.connect(args.db)
    try:
        print(json.dumps(apply(conn, mapping), ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

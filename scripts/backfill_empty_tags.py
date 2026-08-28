#!/usr/bin/env python3
"""给题库里 tags 为空的题补上规范主标签，并按作答重写考点流水。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from kaodian_taxonomy import (
    canonicalize,
    parse_tags,
    question_primary_tag,
    validate_ai_primary_tag,
)
from normalize_kaodian_profile import rebuild


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "exam.db"


def load_draft(batch_id: str, external_id: str) -> dict | None:
    path = ROOT / "batches" / (batch_id or "") / "questions.json"
    if not path.is_file():
        return None
    for question in json.loads(path.read_text(encoding="utf-8")):
        if question.get("external_id") == external_id:
            return question
    return None


def resolve_tag(row: sqlite3.Row) -> str:
    draft = load_draft(row["batch_id"], row["external_id"]) or {}
    raw = question_primary_tag(draft)
    if not raw:
        raw = (parse_tags(row["tags"]) or [""])[0]
    if not raw:
        raise ValueError(f"q{row['id']} {row['external_id']} 草稿也没有考点标签")
    try:
        return validate_ai_primary_tag(raw, row["category"] or "")
    except ValueError:
        return canonicalize(raw, row["category"] or "", row["sub_category"] or "")


def empty_tag_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = []
    for row in conn.execute(
        """
        SELECT id, external_id, batch_id, category, sub_category, tags
          FROM questions
         ORDER BY id
        """
    ):
        if not parse_tags(row["tags"]):
            rows.append(row)
    return rows


def apply(conn: sqlite3.Connection) -> dict:
    conn.row_factory = sqlite3.Row
    rows = empty_tag_rows(conn)
    mapping: dict[int, str] = {}
    by_tag: dict[str, int] = {}
    for row in rows:
        tag = resolve_tag(row)
        mapping[row["id"]] = tag
        by_tag[tag] = by_tag.get(tag, 0) + 1
        conn.execute(
            "UPDATE questions SET tags=? WHERE id=?",
            (json.dumps([tag], ensure_ascii=False), row["id"]),
        )
    ids = list(mapping)
    inserted = 0
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM kaodian_events WHERE question_id IN ({placeholders})", ids)
        for answer in conn.execute(
            f"""
            SELECT pa.session_id, pa.question_id, pa.is_correct, pa.time_spent_sec,
                   pa.answered_at, s.ended_at
              FROM practice_answers pa
              JOIN practice_sessions s ON s.id = pa.session_id
             WHERE pa.question_id IN ({placeholders})
               AND pa.user_answer IS NOT NULL
               AND pa.user_answer != ''
            """,
            ids,
        ):
            conn.execute(
                """
                INSERT INTO kaodian_events(
                  kaodian, question_id, session_id, is_correct, elapsed_ms,
                  evidence_type, evidence_weight, answered_at
                ) VALUES (?, ?, ?, ?, ?, 'practice', 1.0, ?)
                """,
                (
                    mapping[answer["question_id"]],
                    answer["question_id"],
                    answer["session_id"],
                    int(answer["is_correct"] or 0),
                    int(answer["time_spent_sec"] or 0) * 1000,
                    answer["answered_at"] or answer["ended_at"],
                ),
            )
            inserted += 1
        conn.commit()
        rebuild(conn, apply=True)
    return {"empty_before": len(rows), "tagged": by_tag, "events_inserted": inserted}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        if not args.apply:
            preview = []
            for row in empty_tag_rows(conn):
                preview.append({
                    "id": row["id"],
                    "external_id": row["external_id"],
                    "tag": resolve_tag(row),
                })
            print(json.dumps({"empty": len(preview), "items": preview}, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps(apply(conn), ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

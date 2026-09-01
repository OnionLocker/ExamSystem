#!/usr/bin/env python3
"""Daily study plan persistence and reconciliation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

from kaodian_taxonomy import canonicalize, normalize_module
from learner_snapshot import TZ, build_snapshot


DB = Path(
    os.environ.get("EXAM_DB")
    or Path(__file__).resolve().parents[1] / "data" / "exam.db"
)
MODULES = {
    "\u653f\u6cbb\u7406\u8bba",
    "\u5e38\u8bc6\u5224\u65ad",
    "\u8a00\u8bed\u7406\u89e3\u4e0e\u8868\u8fbe",
    "\u6570\u91cf\u5173\u7cfb",
    "\u5224\u65ad\u63a8\u7406",
    "\u79d1\u5b66\u63a8\u7406",
    "\u8d44\u6599\u5206\u6790",
    "\u7533\u8bba",
}
MAX_DAILY_COUNT = 120


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_plans (
          plan_date TEXT PRIMARY KEY,
          items TEXT NOT NULL,
          source TEXT NOT NULL DEFAULT 'hermes',
          snapshot_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_daily_batch_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          plan_date TEXT NOT NULL,
          module TEXT NOT NULL,
          batch_id TEXT,
          status TEXT NOT NULL DEFAULT 'scheduled',
          error TEXT,
          planned_count INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL DEFAULT 'hermes',
          generated_at TEXT,
          imported_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(plan_date, module)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_daily_batch_runs_batch "
        "ON ai_daily_batch_runs(batch_id)"
    )


def today() -> str:
    return str(dt.datetime.now(TZ).date())


def load_plan(conn: sqlite3.Connection, date: str) -> dict | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM daily_plans WHERE plan_date=?", (date,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["items"] = json.loads(result["items"])
    except (json.JSONDecodeError, TypeError):
        result["items"] = []
    return result


def _status(done: int, count: int) -> str:
    return "done" if done >= count else ("partial" if done else "pending")


def _key(item: dict, index: int) -> str:
    return str(
        item.get("batch_id")
        or item.get("id")
        or f"{item.get('module', '')}|{item.get('target', '')}|{index}"
    )


def normalize_items(items: list[dict]) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("items must be an array")
    normalized = []
    total = 0
    for index, raw in enumerate(items, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"items[{index}] must be an object")
        module = normalize_module(str(raw.get("module") or ""))
        if module not in MODULES:
            raise ValueError(f"items[{index}].module is invalid: {module}")

        groups = []
        for group_index, group_raw in enumerate(raw.get("groups") or [], 1):
            if not isinstance(group_raw, dict):
                raise ValueError(
                    f"items[{index}].groups[{group_index}] must be an object"
                )
            group_count = max(
                0, min(MAX_DAILY_COUNT, int(group_raw.get("count") or 0))
            )
            group_done = max(
                0, min(group_count, int(group_raw.get("done") or 0))
            )
            groups.append(
                {
                    **group_raw,
                    "id": str(
                        group_raw.get("id")
                        or group_raw.get("group_id")
                        or f"group-{group_index}"
                    ),
                    "count": group_count,
                    "done": group_done,
                    "status": _status(group_done, group_count),
                }
            )

        count = int(raw.get("count") or sum(g["count"] for g in groups))
        if count < 1 or count > MAX_DAILY_COUNT:
            raise ValueError(
                f"items[{index}].count must be 1..{MAX_DAILY_COUNT}"
            )
        total += count
        grouped_done = sum(group["done"] for group in groups)
        done = max(0, min(count, int(raw.get("done", grouped_done) or 0)))
        normalized.append(
            {
                **raw,
                "id": str(raw.get("id") or f"item-{index}"),
                "module": module,
                "target": str(raw.get("target") or "").strip() or None,
                "task_type": str(
                    raw.get("task_type")
                    or ("quant_groups" if groups else "ai_practice")
                ),
                "groups": groups,
                "count": count,
                "done": done,
                "status": _status(done, count),
                "batch_id": str(raw.get("batch_id") or "").strip() or None,
                "route": (
                    str(raw["route"]) if raw.get("route") is not None else None
                ),
                "reason": (
                    str(raw["reason"]) if raw.get("reason") is not None else None
                ),
            }
        )
    if total > MAX_DAILY_COUNT:
        raise ValueError(
            f"daily total cannot exceed {MAX_DAILY_COUNT}; got {total}"
        )
    return normalized


def preserve_progress(
    items: list[dict], previous: list[dict]
) -> list[dict]:
    old_by_key = {
        _key(item, index): item for index, item in enumerate(previous)
    }
    for index, item in enumerate(items):
        old = old_by_key.get(_key(item, index))
        if not old:
            continue
        item["done"] = min(
            item["count"], max(item["done"], int(old.get("done") or 0))
        )
        old_groups = {
            _key(group, group_index): group
            for group_index, group in enumerate(old.get("groups") or [])
        }
        for group_index, group in enumerate(item["groups"]):
            old_group = old_groups.get(_key(group, group_index))
            if not old_group:
                continue
            group["done"] = min(
                group["count"],
                max(group["done"], int(old_group.get("done") or 0)),
            )
            group["completed_question_ids"] = list(
                dict.fromkeys(
                    str(value)
                    for value in [
                        *(old_group.get("completed_question_ids") or []),
                        *(group.get("completed_question_ids") or []),
                    ]
                )
            )
            group["status"] = _status(group["done"], group["count"])
        item["status"] = _status(item["done"], item["count"])
    return items


def sync_runs(
    conn: sqlite3.Connection,
    date: str,
    items: list[dict],
    source: str,
) -> None:
    for item in items:
        batch_id = item.get("batch_id")
        if not batch_id:
            continue
        imported = (
            conn.execute(
                "SELECT COUNT(*) FROM questions WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
            > 0
        )
        status = (
            "completed"
            if item["done"] >= item["count"]
            else ("imported" if imported else "scheduled")
        )
        conn.execute(
            """
            INSERT INTO ai_daily_batch_runs(
              plan_date,module,batch_id,status,planned_count,source,
              generated_at,imported_at
            ) VALUES (
              ?,?,?,?,?,?,
              CASE WHEN ? THEN CURRENT_TIMESTAMP END,
              CASE WHEN ? THEN CURRENT_TIMESTAMP END
            )
            ON CONFLICT(plan_date,module) DO UPDATE SET
              batch_id=COALESCE(excluded.batch_id,ai_daily_batch_runs.batch_id),
              planned_count=excluded.planned_count,
              source=excluded.source,
              status=CASE
                WHEN ai_daily_batch_runs.status IN ('failed','deleted')
                 AND excluded.batch_id=ai_daily_batch_runs.batch_id
                THEN ai_daily_batch_runs.status
                ELSE excluded.status
              END,
              generated_at=COALESCE(
                ai_daily_batch_runs.generated_at,excluded.generated_at
              ),
              imported_at=COALESCE(
                ai_daily_batch_runs.imported_at,excluded.imported_at
              ),
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                date,
                item["module"],
                batch_id,
                status,
                item["count"],
                source,
                imported,
                imported,
            ),
        )


def save_plan(
    conn: sqlite3.Connection,
    date: str,
    items: list[dict],
    source: str = "hermes",
    snapshot_at: str | None = None,
) -> dict:
    ensure_schema(conn)
    normalized = normalize_items(items)
    previous = load_plan(conn, date)
    if previous:
        normalized = preserve_progress(normalized, previous["items"])
    conn.execute(
        """
        INSERT INTO daily_plans(plan_date,items,source,snapshot_at)
        VALUES (?,?,?,?)
        ON CONFLICT(plan_date) DO UPDATE SET
          items=excluded.items,
          source=excluded.source,
          snapshot_at=excluded.snapshot_at,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            date,
            json.dumps(normalized, ensure_ascii=False),
            source,
            snapshot_at,
        ),
    )
    sync_runs(conn, date, normalized, source)
    conn.commit()
    return load_plan(conn, date)


def reconcile(conn: sqlite3.Connection, date: str) -> dict | None:
    ensure_schema(conn)
    plan = load_plan(conn, date)
    if not plan:
        return None
    alias_map = {
        row[0]: row[1]
        for row in conn.execute("SELECT alias,canonical FROM kaodian_aliases")
    }
    actual = []
    for row in conn.execute(
        """
        SELECT q.category,q.sub_category,q.tags
          FROM practice_answers pa
          JOIN questions q ON q.id=pa.question_id
         WHERE pa.user_answer!=''
           AND date(pa.answered_at, '+8 hours')=?
        """,
        (date,),
    ):
        try:
            tags = json.loads(row[2] or "[]")
        except json.JSONDecodeError:
            tags = []
        raw_tag = str(tags[0]) if tags else ""
        actual.append(
            {
                "module": normalize_module(row[0] or ""),
                "target": alias_map.get(raw_tag)
                or canonicalize(raw_tag, row[0] or "", row[1] or ""),
            }
        )

    items = []
    for item in plan["items"]:
        if item.get("groups"):
            matched = 0
        elif item.get("batch_id"):
            matched = conn.execute(
                """
                SELECT COUNT(DISTINCT q.id)
                  FROM questions q
                  JOIN practice_answers pa ON pa.question_id=q.id
                 WHERE q.batch_id=? AND pa.user_answer!=''
                """,
                (item["batch_id"],),
            ).fetchone()[0]
        else:
            matched = sum(
                1
                for answer in actual
                if (
                    answer["target"] == item.get("target")
                    if item.get("target")
                    else answer["module"] == item["module"]
                )
            )
        done = min(
            item["count"], max(int(item.get("done") or 0), matched)
        )
        items.append(
            {
                **item,
                "done": done,
                "status": _status(done, item["count"]),
            }
        )
    return save_plan(
        conn,
        date,
        items,
        source=plan["source"],
        snapshot_at=plan.get("snapshot_at"),
    )


def context(conn: sqlite3.Connection, date: str) -> dict:
    ensure_schema(conn)
    snapshot = build_snapshot(conn)
    conn.commit()
    current = reconcile(conn, date)
    previous_date = str(
        dt.date.fromisoformat(date) - dt.timedelta(days=1)
    )
    return {
        "date": date,
        "learner_snapshot": snapshot,
        "today_plan": current,
        "previous_plan": reconcile(conn, previous_date),
    }


def compact_context(data: dict) -> str:
    lines = [data["learner_snapshot"]["compact"]]
    previous = data.get("previous_plan")
    if previous:
        lines.append("\u6628\u65e5\u8ba1\u5212\u5b8c\u6210\uff1a")
        lines.extend(
            f"- {item['module']} "
            f"{item['done']}/{item['count']} {item['status']}"
            for item in previous["items"]
        )
    current = data.get("today_plan")
    if current:
        lines.append("\u4eca\u65e5\u5df2\u6709\u8ba1\u5212\uff1a")
        lines.extend(
            f"- {item['module']} "
            f"{item['done']}/{item['count']} {item['status']}"
            for item in current["items"]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    sub = parser.add_subparsers(dest="command", required=True)
    context_parser = sub.add_parser("context")
    context_parser.add_argument("--date", default=today())
    context_parser.add_argument("--compact", action="store_true")
    save_parser = sub.add_parser("save")
    save_parser.add_argument("--date", default=today())
    save_parser.add_argument("--items-json", required=True)
    save_parser.add_argument("--source", default="hermes")
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--date", default=today())
    complete_parser = sub.add_parser("complete")
    complete_parser.add_argument("--date", default=today())
    complete_parser.add_argument("--item", required=True)
    complete_parser.add_argument("--done", type=int)
    reconcile_parser = sub.add_parser("reconcile")
    reconcile_parser.add_argument("--date", default=today())

    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    try:
        if args.command == "context":
            result = context(conn, args.date)
            print(
                compact_context(result)
                if args.compact
                else json.dumps(result, ensure_ascii=False, indent=2)
            )
        elif args.command == "save":
            snapshot = build_snapshot(conn)
            result = save_plan(
                conn,
                args.date,
                json.loads(args.items_json),
                source=args.source,
                snapshot_at=snapshot["as_of"],
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "status":
            print(
                json.dumps(
                    load_plan(conn, args.date),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "reconcile":
            print(
                json.dumps(
                    reconcile(conn, args.date),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            plan = load_plan(conn, args.date)
            if not plan:
                raise SystemExit(f"{args.date} has no plan")
            found = False
            for item in plan["items"]:
                if item["id"] == args.item:
                    item["done"] = (
                        item["count"] if args.done is None else args.done
                    )
                    found = True
            if not found:
                raise SystemExit(f"plan item not found: {args.item}")
            result = save_plan(
                conn,
                args.date,
                plan["items"],
                source=plan["source"],
                snapshot_at=plan.get("snapshot_at"),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

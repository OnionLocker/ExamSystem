#!/usr/bin/env python3
"""每日学习计划状态：保存、对账、完成与上下文输出。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

from kaodian_taxonomy import canonicalize, normalize_module
from learner_snapshot import TZ, build_snapshot


DB = Path(__file__).resolve().parents[1] / "data" / "exam.db"
MODULES = {
    "政治理论", "常识判断", "言语理解与表达", "数量关系",
    "判断推理", "科学推理", "资料分析", "申论",
}


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
    except json.JSONDecodeError:
        result["items"] = []
    return result


def normalize_items(items: list[dict]) -> list[dict]:
    normalized = []
    total = 0
    for index, raw in enumerate(items, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"items[{index}] 必须是对象")
        module = normalize_module(str(raw.get("module") or ""))
        if module not in MODULES:
            raise ValueError(f"items[{index}].module 不合法：{module}")
        count = int(raw.get("count") or 0)
        if count < 1 or count > 40:
            raise ValueError(f"items[{index}].count 必须是1~40")
        total += count
        target = str(raw.get("target") or "").strip() or None
        done = max(0, min(count, int(raw.get("done") or 0)))
        normalized.append({
            "id": str(raw.get("id") or f"item-{index}"),
            "module": module,
            "target": target,
            "count": count,
            "done": done,
            "status": "done" if done >= count else ("partial" if done else "pending"),
        })
    if total > 40:
        raise ValueError(f"每日总题量不能超过40，当前为{total}")
    return normalized


def save_plan(
    conn: sqlite3.Connection,
    date: str,
    items: list[dict],
    source: str = "hermes",
    snapshot_at: str | None = None,
) -> dict:
    ensure_schema(conn)
    items = normalize_items(items)
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
        (date, json.dumps(items, ensure_ascii=False), source, snapshot_at),
    )
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
        actual.append({
            "module": normalize_module(row[0] or ""),
            "target": alias_map.get(raw_tag) or canonicalize(raw_tag, row[0] or "", row[1] or ""),
        })

    items = []
    for item in plan["items"]:
        matched = sum(
            1 for answer in actual
            if (
                answer["target"] == item.get("target")
                if item.get("target")
                else answer["module"] == item["module"]
            )
        )
        done = min(item["count"], max(int(item.get("done") or 0), matched))
        items.append({
            **item,
            "done": done,
            "status": "done" if done >= item["count"] else ("partial" if done else "pending"),
        })
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
    previous_date = str(dt.date.fromisoformat(date) - dt.timedelta(days=1))
    previous = reconcile(conn, previous_date)
    return {
        "date": date,
        "learner_snapshot": snapshot,
        "today_plan": current,
        "previous_plan": previous,
    }


def compact_context(data: dict) -> str:
    lines = [data["learner_snapshot"]["compact"]]
    previous = data.get("previous_plan")
    if previous:
        lines.append("昨日计划完成：")
        for item in previous["items"]:
            lines.append(
                f"- {item['module']} {item['done']}/{item['count']} {item['status']}"
            )
    current = data.get("today_plan")
    if current:
        lines.append("今日已有计划：")
        for item in current["items"]:
            lines.append(
                f"- {item['module']} {item['done']}/{item['count']} {item['status']}"
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
            print(compact_context(result) if args.compact else json.dumps(result, ensure_ascii=False, indent=2))
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
            result = load_plan(conn, args.date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "reconcile":
            result = reconcile(conn, args.date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            plan = load_plan(conn, args.date)
            if not plan:
                raise SystemExit(f"{args.date} 没有计划")
            found = False
            for item in plan["items"]:
                if item["id"] == args.item:
                    item["done"] = item["count"] if args.done is None else args.done
                    found = True
            if not found:
                raise SystemExit(f"未找到计划项：{args.item}")
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

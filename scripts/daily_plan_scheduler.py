#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""04:20 weekday daily-plan scheduler."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
from pathlib import Path

from china_workday import CALENDAR, workday_reason
from scheduler_common import (
    AlreadyLocked,
    DB,
    EXIT_ERROR,
    EXIT_LOCKED,
    EXIT_OK,
    FileLock,
    ROOT,
    load_runs,
    load_snapshot,
    local_today,
    preview_runs,
    reserve_runs,
    wait_unlocked,
)


LOCK_FILE = Path("/tmp/examsystem-daily-plan.lock")
BATCH_LOCK = Path("/tmp/examsystem-daily-batches.lock")


def target_for(module: str, snapshot: dict) -> tuple[str | None, str]:
    candidates = (
        (snapshot.get("recommended_targets") or [])
        + (snapshot.get("weaknesses") or [])
        + (snapshot.get("needs_measurement") or [])
    )
    for item in candidates:
        if item.get("module") == module:
            return item.get("kaodian"), item.get("reason") or "\u753b\u50cf\u4f18\u5148\u9879"
    return None, "\u6bcf\u65e5\u56fa\u5b9a\u6a21\u5757\u914d\u989d"


def suggested_items(runs: list[dict], snapshot: dict) -> list[dict]:
    items = []
    for index, run in enumerate(runs, 1):
        target, reason = target_for(run["module"], snapshot)
        items.append(
            {
                "id": f"daily-ai-{index}",
                "task_type": "ai_batch",
                "module": run["module"],
                "target": target,
                "groups": [],
                "count": int(run["planned_count"]),
                "done": 0,
                "status": "pending",
                "batch_id": run["batch_id"],
                "batch_status": run["status"],
                "route": f"/ai-practice?batch_id={run['batch_id']}",
                "reason": reason,
            }
        )
    return items


def plan_prompt(
    day: dt.date, snapshot: dict, runs: list[dict], db_path: Path
) -> str:
    payload = {
        "date": str(day),
        "database": str(db_path),
        "snapshot_at": snapshot.get("as_of"),
        "learner_snapshot": {
            "summary": snapshot.get("summary"),
            "recommended_targets": snapshot.get("recommended_targets"),
            "weaknesses": snapshot.get("weaknesses"),
            "compact": snapshot.get("compact"),
        },
        "batch_runs": runs,
        "suggested_items": suggested_items(runs, snapshot),
        "numeric_task_policy": {
            "optional_items": "1~2",
            "total_questions": "10~30",
            "groups_per_item": "1~3",
            "task_type": "quant_groups",
            "route_source": "available CATEGORIES in src/practice/generators.js",
        },
    }
    return (
        "\u4f60\u662f ExamSystem 04:20 \u4eca\u65e5\u4efb\u52a1\u4fdd\u5b58\u5de5\u4f5c\u5668\u3002\n"
        "\u8bf7\u6839\u636e\u4ee5\u4e0b payload \u4fdd\u5b58\u5f53\u5929 daily_plans\uff1a\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "\u5fc5\u987b\u4fdd\u7559\u56db\u4e2a suggested_items \u7684\u56fa\u5b9a\u9898\u6570\u4e0e batch_id\uff1b"
        "\u5373\u4f7f batch_status \u5c1a\u672a imported\uff0c\u4e5f\u8981\u628a\u8be5\u5360\u4f4d batch \u7ed1\u5b9a\u5230\u8ba1\u5212\u3002"
        "\u53ea\u5141\u8bb8\u5fae\u8c03 target/reason\uff0c\u4e0d\u5f97\u751f\u6210\u9898\u76ee\u6216\u5bfc\u5165\u6279\u6b21\u3002\n"
        "\u4f7f\u7528\u73b0\u6709 scripts/daily_plan_state.py --db \u6307\u5b9a\u4e0a\u8ff0 database \u540e\u6267\u884c save\uff1b"
        "source \u4f7f\u7528 hermes-scheduler\u3002\n"
        "\u4fdd\u5b58\u540e\u8bfb\u53d6 status \u81ea\u68c0\uff1b\u6210\u529f\u53ea\u8fd4\u56de\u7b80\u77ed\u7ed3\u679c\uff0c\u5931\u8d25\u660e\u786e\u62a5\u9519\u3002\n"
        "\n"
        "You may add one or two profile-based quant_groups tasks (10-30 questions total,\n"
        "one to three groups per task). Each group must contain id, count, catId, subId,\n"
        'and route={"catId":"...","subId":"..."}. Use only available category/sub IDs\n'
        "from src/practice/generators.js. Do not add drills without profile evidence.\n"
        "The total daily count must remain at or below 120.\n"
    )


def load_saved_plan(conn: sqlite3.Connection, day: dt.date) -> dict | None:
    try:
        row = conn.execute(
            "SELECT items,source,snapshot_at FROM daily_plans WHERE plan_date=?",
            (str(day),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    return {
        "items": json.loads(row[0]),
        "source": row[1],
        "snapshot_at": row[2],
    }


def invoke_hermes(
    day: dt.date,
    snapshot: dict,
    runs: list[dict],
    db_path: Path,
    timeout: int,
) -> dict:
    hermes = os.environ.get("HERMES_BIN", "hermes")
    env = {**os.environ, "EXAM_DB": str(db_path)}
    result = subprocess.run(
        [
            hermes,
            "chat",
            "-Q",
            "--query-file",
            "-",
            "--in",
            str(ROOT),
            "--source",
            "tool",
            "--yolo",
            "--max-turns",
            "20",
            "--run-budget",
            str(timeout),
        ],
        input=plan_prompt(day, snapshot, runs, db_path),
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout + 30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Hermes failed").strip()
        raise RuntimeError(detail[-2000:])
    conn = sqlite3.connect(db_path)
    try:
        plan = load_saved_plan(conn, day)
    finally:
        conn.close()
    if not plan:
        raise RuntimeError("Hermes returned ok, but daily_plans has no row for today")
    expected = {row["batch_id"] for row in runs}
    actual = {
        item.get("batch_id")
        for item in plan.get("items") or []
        if isinstance(item, dict)
    }
    if not expected.issubset(actual):
        raise RuntimeError("today plan did not bind all four batch placeholders")
    return plan


def save_suggested_plan(
    day: dt.date,
    snapshot: dict,
    runs: list[dict],
    db_path: Path,
) -> dict:
    from daily_plan_state import save_plan

    conn = sqlite3.connect(db_path)
    try:
        return save_plan(
            conn,
            str(day),
            suggested_items(runs, snapshot),
            source="hermes-scheduler",
            snapshot_at=snapshot.get("as_of"),
        )
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=dt.date.fromisoformat, default=local_today())
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--calendar", type=Path, default=CALENDAR)
    parser.add_argument("--lock-file", type=Path, default=LOCK_FILE)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--wait-timeout", type=int, default=5400)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.timeout < 1:
            raise ValueError("--timeout must be a positive integer")
        allowed, reason = workday_reason(args.date, args.calendar.resolve())
        if not allowed:
            print(
                json.dumps(
                    {"ok": True, "skipped": True, "date": str(args.date), "reason": reason},
                    ensure_ascii=False,
                )
            )
            return EXIT_OK
        if not args.dry_run:
            wait_unlocked(BATCH_LOCK, args.wait_timeout)
        with FileLock(args.lock_file):
            conn = sqlite3.connect(args.db, timeout=30)
            try:
                snapshot = load_snapshot(conn)
                if args.dry_run:
                    existing = load_runs(conn, args.date, ensure_schema=False)
                    runs = existing if len(existing) == 4 else preview_runs(args.date)
                else:
                    runs = reserve_runs(conn, args.date)
            finally:
                conn.close()
            payload = {
                "date": str(args.date),
                "workday_reason": reason,
                "snapshot_at": snapshot.get("as_of"),
                "items": suggested_items(runs, snapshot),
            }
            if args.dry_run:
                print(
                    json.dumps(
                        {"ok": True, "dry_run": True, "suggested_plan": payload},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return EXIT_OK
            try:
                plan = invoke_hermes(args.date, snapshot, runs, args.db, args.timeout)
                fallback = False
                hermes_error = None
            except (RuntimeError, subprocess.SubprocessError) as exc:
                plan = save_suggested_plan(args.date, snapshot, runs, args.db)
                fallback = True
                hermes_error = str(exc)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "date": str(args.date),
                        "plan": plan,
                        "fallback": fallback,
                        "hermes_error": hermes_error,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return EXIT_OK
    except AlreadyLocked as exc:
        print(json.dumps({"ok": False, "error": "locked", "lock_file": str(exc)}))
        return EXIT_LOCKED
    except (
        OSError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

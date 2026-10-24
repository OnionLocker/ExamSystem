#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凌晨日练调度：每日复习卷（REVIEW_QUOTAS）按遗忘曲线选点（daily_review_plan），直接调 quiz_lite 出题入库。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from daily_review_plan import build_plan, ensure_schema as ensure_plan_schema, save_plan
from scheduler_common import (
    AlreadyLocked,
    DB,
    EXIT_ERROR,
    EXIT_LOCKED,
    EXIT_OK,
    FileLock,
    REVIEW_QUOTAS,
    ROOT,
    ensure_run_schema,
    local_today,
    new_batch_id,
    update_run,
)


LOCK_FILE = Path("/tmp/examsystem-daily-batches.lock")
OUTPUT_ROOT = ROOT / "data" / "daily-batches"
# Hermes 定时任务给脚本 3600 秒；20 题通常 15–25 分钟，留出选点和入库的余量。
REVIEW_TIMEOUT = 3000
# quiz_lite 只重出不合格的题；多给两轮，少因个别题整卷作废。
REVIEW_ROUNDS = 5
# 和 examsystem.service 用同一个 node：import-batch 的 better-sqlite3 认 Node 版本。
SERVICE_PATH = f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def imported_count(conn: sqlite3.Connection, batch_id: str) -> int:
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM questions WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
        )
    except sqlite3.OperationalError:
        return 0


def todays_review(conn: sqlite3.Connection, module: str, prefix: str, day: dt.date) -> dict | None:
    """今天这套复习卷已经入库就不再出；用户把它删了，也不再出。"""
    for (batch_id,) in conn.execute(
        "SELECT batch_id FROM daily_review_plans WHERE plan_date=? AND module=? ORDER BY created_at DESC",
        (str(day), module),
    ):
        if imported_count(conn, batch_id):
            return {"status": "skipped_imported", "batch_id": batch_id}
    row = conn.execute(
        "SELECT batch_id, status FROM ai_daily_batch_runs WHERE plan_date=? AND module=?",
        (str(day), module),
    ).fetchone()
    if row and row[1] == "deleted" and str(row[0] or "").startswith(prefix):
        return {"status": "skipped_deleted", "batch_id": row[0]}
    return None


def untouched_previous(conn: sqlite3.Connection, module: str, day: dt.date) -> dict | None:
    """上一套复习卷一题没做：今天不再出，免得堆在题库里（已删掉的不算）。"""
    for batch_id, plan_date in conn.execute(
        "SELECT batch_id, plan_date FROM daily_review_plans WHERE module=? AND plan_date<? "
        "ORDER BY plan_date DESC, created_at DESC",
        (module, str(day)),
    ):
        if not imported_count(conn, batch_id):
            continue
        try:
            done = conn.execute(
                "SELECT COUNT(*) FROM practice_answers pa JOIN questions q ON q.id = pa.question_id "
                "WHERE q.batch_id=?",
                (batch_id,),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            done = 0
        return None if done else {"batch_id": batch_id, "plan_date": plan_date}
    return None


def claim_run(conn: sqlite3.Connection, run: dict, prefix: str) -> bool:
    """练题页的「生成中 / 生成失败」卡片看 ai_daily_batch_runs。

    同一天同一模块只有一行；若已被今天学习计划里别的题组占着，就不去抢，题组照样入库。
    """
    row = conn.execute(
        "SELECT batch_id, status FROM ai_daily_batch_runs WHERE plan_date=? AND module=?",
        (run["plan_date"], run["module"]),
    ).fetchone()
    if row and not str(row[0] or "").startswith(prefix) and row[1] not in {"scheduled", "failed", "deleted", "paused"}:
        return False
    conn.execute(
        """
        INSERT INTO ai_daily_batch_runs(plan_date,module,batch_id,status,planned_count,source)
        VALUES (?,?,?,'running',?,'daily-review')
        ON CONFLICT(plan_date,module) DO UPDATE SET
          batch_id=excluded.batch_id, status='running', error=NULL,
          planned_count=excluded.planned_count, source=excluded.source,
          generated_at=NULL, imported_at=NULL, updated_at=CURRENT_TIMESTAMP
        """,
        (run["plan_date"], run["module"], run["batch_id"], run["planned_count"]),
    )
    return True


def last_json(text: str) -> dict:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def run_review(module: str, slug: str, count: int, args: argparse.Namespace) -> dict:
    """选点 → quiz_lite 出题入库。失败时 ai_daily_batch_runs 记 failed，下一次调度换新批次号重出。"""
    day = args.date
    prefix = f"daily-{day:%Y%m%d}-{slug}-"
    base = {"plan_date": str(day), "module": module, "planned_count": count}
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        ensure_run_schema(conn)
        ensure_plan_schema(conn)
        done = todays_review(conn, module, prefix, day)
        if done:
            return {**base, **done}
        stale = None if args.force else untouched_previous(conn, module, day)
        if stale:
            return {**base, "status": "skipped_untouched", "batch_id": stale["batch_id"],
                    "reason": f"{stale['plan_date']} 那套还一题没做，今天不再出"}
        plan = build_plan(conn, module, day)
        if not plan["slots"]:
            return {**base, "status": "skipped_empty", "reason": plan.get("note") or "没有可复习的考点"}
        run = {**base, "batch_id": new_batch_id(day, slug), "planned_count": len(plan["slots"])}
        owned = claim_run(conn, run, prefix)
        save_plan(conn, run["batch_id"], plan)
        conn.commit()
    finally:
        conn.close()

    command = [
        sys.executable, str(ROOT / "scripts" / "quiz_lite.py"),
        "--module", module,
        "--blueprint", json.dumps({"slots": plan["slots"]}, ensure_ascii=False),
        "--batch-id", run["batch_id"],
        "--rounds", str(args.rounds),
        "--output-dir", str(args.output_root),
        "--db", str(args.db),
    ]
    env = {**os.environ, "EXAM_DB": str(args.db), "PATH": f"{SERVICE_PATH}:{os.environ.get('PATH', '')}"}
    error = None
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
            timeout=args.review_timeout,
        )
        outcome = last_json(result.stdout)
        if result.returncode != 0 or outcome.get("status") != "success":
            error = str(outcome.get("error") or (result.stderr or result.stdout or "quiz_lite 出题失败").strip())
    except subprocess.TimeoutExpired:
        error = f"出题超过 {args.review_timeout} 秒没完成，已停止"
        from generation_progress import report

        report(run["batch_id"], status="failed", stage="失败", detail=error, error=error)
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        imported = imported_count(conn, run["batch_id"])
        if error is None and imported < run["planned_count"]:
            error = f"quiz_lite 返回成功，但只入库 {imported}/{run['planned_count']} 题"
        if owned:
            if error:
                update_run(conn, run["batch_id"], "failed", error=error[-2000:])
            else:
                update_run(conn, run["batch_id"], "imported", generated=True, imported=True)
    finally:
        conn.close()
    if error:
        return {**run, "status": "failed", "error": error[-2000:]}
    return {**run, "status": "imported", "imported_count": imported, "error": None,
            "points": [f"{point['title']}×{point['count']}" for point in plan["points"]]}


def dry_run(args: argparse.Namespace) -> dict:
    """只算不写：给出复习卷的选点结果。"""
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) if args.db.is_file() else None
    try:
        reviews = [build_plan(conn, module, args.date) for module, _slug, _count in REVIEW_QUOTAS]
    finally:
        if conn is not None:
            conn.close()
    return {"ok": True, "dry_run": True, "date": str(args.date), "reviews": reviews}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=dt.date.fromisoformat, default=local_today())
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--lock-file", type=Path, default=LOCK_FILE)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--rounds", type=positive_int, default=REVIEW_ROUNDS, help="复习卷 quiz_lite 补题轮数")
    parser.add_argument("--review-timeout", type=positive_int, default=REVIEW_TIMEOUT)
    parser.add_argument("--force", action="store_true", help="上一套没做也照出今天的复习卷")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.environ["EXAM_DB"] = str(args.db)
    try:
        with FileLock(args.lock_file):
            if args.dry_run:
                print(json.dumps(dry_run(args), ensure_ascii=False, indent=2))
                return EXIT_OK
            results = [run_review(module, slug, count, args) for module, slug, count in REVIEW_QUOTAS]
            failed = [row for row in results if row["status"] == "failed"]
            print(json.dumps({"ok": not failed, "date": str(args.date), "runs": results}, ensure_ascii=False, indent=2))
            return EXIT_ERROR if failed else EXIT_OK
    except AlreadyLocked as exc:
        print(json.dumps({"ok": False, "error": "locked", "lock_file": str(exc)}))
        return EXIT_LOCKED
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

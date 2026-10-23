#!/usr/bin/env python3
"""每日资料分析整套（4 篇 20 题）：排在数量复习卷之后，由 Hermes 定时任务调用。

不看遗忘曲线：题型按广东真题频率 × 近 3 套降权 × 近 60 天做题表现系数轮转，
每题再挑同题型、适配材料形态、近期少练且错得多的细分考法（ziliao_agent_paper 内置）。
当天已入库就不再出；前一天那套一题没做也不出，免得堆题；失败时下一次调度换新批次号重出。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from scheduler_common import (AlreadyLocked, DB, EXIT_ERROR, EXIT_LOCKED, EXIT_OK, FileLock, ROOT,
                              ensure_run_schema, local_today, new_batch_id, update_run)

MODULE = "资料分析"
SLUG = "ziliao"
LOCK_FILE = Path("/tmp/examsystem-daily-ziliao.lock")
OUTPUT_DIR = ROOT / "data" / "manual-ziliao-agent-paper"
# Hermes 定时脚本上限 5400 秒（~/.hermes/config.yaml cron.script_timeout_seconds）；整套通常 30–40 分钟。
PAPER_TIMEOUT = 5100
SERVICE_PATH = f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"


def imported_count(conn: sqlite3.Connection, batch_id: str) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM questions WHERE batch_id=?", (batch_id,)).fetchone()[0])


def prefix_of(day: dt.date) -> str:
    return f"daily-{day:%Y%m%d}-{SLUG}-"


def todays_paper(conn: sqlite3.Connection, day: dt.date) -> dict | None:
    for (batch_id,) in conn.execute("SELECT DISTINCT batch_id FROM questions WHERE batch_id LIKE ?",
                                    (prefix_of(day) + "%",)):
        return {"status": "skipped_imported", "batch_id": batch_id}
    row = conn.execute("SELECT batch_id, status FROM ai_daily_batch_runs WHERE plan_date=? AND module=?",
                       (str(day), MODULE)).fetchone()
    if row and row[1] == "deleted" and str(row[0] or "").startswith(prefix_of(day)):
        return {"status": "skipped_deleted", "batch_id": row[0]}
    return None


def untouched_previous(conn: sqlite3.Connection, day: dt.date) -> dict | None:
    """本调度器出的上一套一题没做：今天不再出（已删掉的、旧版日练不算）。"""
    row = conn.execute(
        """SELECT batch_id FROM ai_daily_batch_runs
            WHERE module=? AND source='daily-ziliao' AND status IN ('imported','completed') AND plan_date<?
            ORDER BY plan_date DESC LIMIT 1""",
        (MODULE, str(day))).fetchone()
    if not row or not row[0] or not imported_count(conn, row[0]):
        return None
    done = conn.execute(
        "SELECT COUNT(*) FROM practice_answers pa JOIN questions q ON q.id = pa.question_id WHERE q.batch_id=?",
        (row[0],)).fetchone()[0]
    return None if done else {"batch_id": row[0]}


def claim_run(conn: sqlite3.Connection, day: dt.date, batch_id: str) -> None:
    """练题页的「生成中 / 生成失败」卡片看 ai_daily_batch_runs。"""
    conn.execute(
        """INSERT INTO ai_daily_batch_runs(plan_date,module,batch_id,status,planned_count,source)
           VALUES (?,?,?,'running',20,'daily-ziliao')
           ON CONFLICT(plan_date,module) DO UPDATE SET
             batch_id=excluded.batch_id, status='running', error=NULL,
             planned_count=excluded.planned_count, source=excluded.source,
             generated_at=NULL, imported_at=NULL, updated_at=CURRENT_TIMESTAMP""",
        (str(day), MODULE, batch_id))


def last_json(text: str) -> dict:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def run(args: argparse.Namespace) -> dict:
    day = args.date
    base = {"plan_date": str(day), "module": MODULE, "planned_count": 20}
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        ensure_run_schema(conn)
        done = todays_paper(conn, day)
        if done:
            return {**base, **done}
        stale = None if args.force else untouched_previous(conn, day)
        if stale:
            return {**base, "status": "skipped_untouched", "batch_id": stale["batch_id"],
                    "reason": "上一套每日资料分析还一题没做，今天不再出"}
        batch_id = new_batch_id(day, SLUG)
        claim_run(conn, day, batch_id)
        conn.commit()
    finally:
        conn.close()

    command = [sys.executable, str(ROOT / "scripts" / "ziliao_agent_paper.py"),
               "--output-dir", str(args.output_dir), "--db", str(args.db),
               "--batch-id", batch_id, "--import"]
    env = {**os.environ, "EXAM_DB": str(args.db), "PATH": f"{SERVICE_PATH}:{os.environ.get('PATH', '')}"}
    error, summary = None, {}
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                                encoding="utf-8", timeout=args.timeout)
        summary = last_json(result.stdout)
        if result.returncode != 0 or not summary.get("passed"):
            error = str(summary.get("error") or (result.stderr or result.stdout or "整套出题失败").strip())
    except subprocess.TimeoutExpired:
        error = f"整套出题超过 {args.timeout} 秒没完成，已停止"
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        imported = imported_count(conn, batch_id)
        if error is None and imported < 20:
            error = f"整套返回通过，但只入库 {imported}/20 题"
        update_run(conn, batch_id, "failed" if error else "imported", error=(error or "")[-2000:] or None,
                   generated=(args.output_dir / batch_id / "questions.json").is_file(), imported=not error)
        conn.commit()
    finally:
        conn.close()
    adaptive = {}
    path = args.output_dir / batch_id / "adaptive.json"
    if path.is_file():
        adaptive = json.loads(path.read_text(encoding="utf-8"))
    if error:
        return {**base, "batch_id": batch_id, "status": "failed", "error": error[-2000:]}
    return {**base, "batch_id": batch_id, "status": "imported", "imported_count": imported,
            "weak_kinds": [k for k, v in (adaptive.get("kind_boost") or {}).items() if v > 1][:5]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=dt.date.fromisoformat, default=local_today())
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--lock-file", type=Path, default=LOCK_FILE)
    parser.add_argument("--timeout", type=int, default=PAPER_TIMEOUT)
    parser.add_argument("--force", action="store_true", help="上一套没做也照出今天的")
    parser.add_argument("--dry-run", action="store_true", help="只判断今天出不出、按什么权重，不出题")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.environ["EXAM_DB"] = str(args.db)
    try:
        with FileLock(args.lock_file):
            if args.dry_run:
                conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
                try:
                    decision = todays_paper(conn, args.date) or (None if args.force else untouched_previous(conn, args.date))
                finally:
                    conn.close()
                from ziliao_performance import adaptive_plan, summary
                print(json.dumps({"ok": True, "dry_run": True, "date": str(args.date),
                                  "skip": decision, "adaptive": summary(adaptive_plan(args.db))},
                                 ensure_ascii=False, indent=2))
                return EXIT_OK
            result = run(args)
            print(json.dumps({"ok": result["status"] != "failed", "date": str(args.date), "runs": [result]},
                             ensure_ascii=False, indent=2))
            return EXIT_ERROR if result["status"] == "failed" else EXIT_OK
    except AlreadyLocked as exc:
        print(json.dumps({"ok": False, "error": "locked", "lock_file": str(exc)}))
        return EXIT_LOCKED
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""04:00 weekday AI batch scheduler."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from china_workday import CALENDAR, workday_reason
from normalize_ai_batch import generation_payload_extras
from scheduler_common import (
    AlreadyLocked,
    DB,
    EXIT_ERROR,
    EXIT_LOCKED,
    EXIT_OK,
    FileLock,
    ROOT,
    daily_source_name,
    load_runs,
    load_snapshot,
    local_today,
    preview_runs,
    reserve_runs,
    update_run,
)


LOCK_FILE = Path("/tmp/examsystem-daily-batches.lock")
OUTPUT_ROOT = ROOT / "data" / "daily-batches"
DEFAULT_SKILLS = "quiz-pipeline,gd-gongkao-coach"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def snapshot_for_prompt(snapshot: dict) -> dict:
    return {
        "as_of": snapshot.get("as_of"),
        "summary": snapshot.get("summary"),
        "recommended_targets": snapshot.get("recommended_targets"),
        "weaknesses": snapshot.get("weaknesses"),
        "needs_measurement": snapshot.get("needs_measurement"),
        "open_mistake_families": snapshot.get("open_mistake_families"),
        "compact": snapshot.get("compact"),
    }


def generation_prompt(run: dict, snapshot: dict, batch_dir: Path, db_path: Path | None = None) -> str:
    source = daily_source_name(run["module"], run["plan_date"])
    payload = {
        "plan_date": run["plan_date"],
        "module": run["module"],
        "question_count": run["planned_count"],
        "batch_id": run["batch_id"],
        "batch_dir": str(batch_dir),
        "workdir": str(ROOT),
        "all_original": True,
        "source": source,
        "learner_snapshot": snapshot_for_prompt(snapshot),
        **generation_payload_extras(
            run["module"],
            int(run["planned_count"]),
            str(run["batch_id"]),
            db_path,
        ),
    }
    resume = ""
    if (batch_dir / "questions.json").is_file():
        resume = (
            "batch_dir already has an unpublished draft. Continue from these files, "
            "fix gate/quality issues, then import. Do not change batch_id or start a new batch.\n"
        )
    if run["module"] == "资料分析":
        ziliao_rule = (
            "Data analysis must be exactly 4 materials x 5 questions = 20. "
            "Use ziliao_pack slot tags and the assigned answer letters. Keep 4 materials in order, 5 questions each; do not shuffle."
        )
    elif run["module"] == "判断推理":
        ziliao_rule = (
            "This is a 20-question Guangdong 判断推理 paper. Follow panduan_pack slots in order. "
            "Questions 1-15: 图形推理 about 5 + 逻辑判断 covering 加强/削弱/分析推理/结构相似/原因解释; "
            "翻译推理 at most 2; never 定义判断 or 类比推理. "
            "Questions 16-20: 科学推理, one subject each from 力学、压强与浮力、电学、生物、地理 "
            "(physics 2-3 + biology 1 + geography 1). Do not dump five of one subject. "
            "category remains 判断推理; last five sub_category=科学推理, tags[0] like 科学推理-力学-受力平衡. "
            "For 翻译推理, the keyed option must not restate 已知 instance facts (synonyms included). "
            "Need a contrapositive, disjunctive syllogism, or a two-step chain. Neutral subject; "
            "verify-logic.py rejects echo_given_fact (R029). "
            "Follow panduan_pack slot.tag exactly. 等高线 means a contour-map figure item, "
            "difficulty 3 (slope/valley/flow/simple site), not 地球自转. "
            "A missing holdout does not skip that slot. If evaluate context fails, omit it and still import after correctness passes."
        )
    elif run["module"] == "数量关系":
        ziliao_rule = (
            "This is a 15-question Guangdong 数量关系 paper. "
            "Questions 1-5: 数字推理 (sub_category=数字推理). "
            "Questions 6-15: 数学运算. Write questions.json in this paper order; do not shuffle."
        )
    elif run["module"] == "言语理解与表达":
        ziliao_rule = (
            "This is a 15-question Guangdong 言语理解与表达 paper. "
            "Questions 1-5: 逻辑填空. Questions 6-15: 片段阅读 and 语句表达. "
            "Write questions.json in this paper order; do not shuffle."
        )
    else:
        ziliao_rule = (
            "Pick knowledge points from the learner snapshot, but do not change the question count."
        )
    return (
        "You are ExamSystem's unattended weekday batch generator for one module.\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"{resume}"
        f"Handle only module [{run['module']}]. Question count must be exactly {run['planned_count']}, "
        "all original, do not insert origin=zhenti items.\n"
        f"Use batch_id unchanged. Working directory must be {ROOT}; run every python3/node script there.\n"
        "First read hermes-skills/quiz-pipeline/SKILL.md and hermes-skills/gd-gongkao-coach/SKILL.md "
        "(or skill_view if Hermes is available), then follow the existing quiz-pipeline.\n"
        "Draft from internalized GONGKAO-STYLE principles+profile; do not call reference_style.py context --role generate per question. After writing, request one evaluate holdout per tag family (reference_style.py context --role evaluate --count 1). If evaluate context fails, omit evaluation_contexts for those tags and still import after correctness; do not rewrite the slot. generation_contexts may be omitted.\n"
        "Put the correct option on answer_plan[i].answer. Do not change computed values to chase a letter. "
        "generation_gate will reshuffle options if the draft ignores the plan. Keep Guangdong paper question order; do not shuffle questions.\n"
        f"{ziliao_rule}\n"
        f"manifest.source and every question.source must be exactly {source}. Do not invent another title.\n"
        f"Write the complete batch into batch_dir, run python3 scripts/generation_gate.py issue {batch_dir}, "
        f"then node scripts/import-batch.mjs {batch_dir}.\n"
        "Do not modify project code, database schema, or other module batches.\n"
        "If any step fails, report the error and do not pretend success. On success, return only the imported count.\n"
    )


def imported_count(conn: sqlite3.Connection, batch_id: str) -> int:
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM questions WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
        )
    except sqlite3.OperationalError:
        return 0


def run_one(
    run: dict,
    snapshot: dict,
    db_path: Path,
    output_root: Path,
    timeout: int,
    max_turns: int,
    skills: str,
) -> dict:
    batch_dir = output_root / run["plan_date"] / run["batch_id"]
    hermes = os.environ.get("HERMES_BIN", "hermes")
    command = [
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
        str(max_turns),
        "--run-budget",
        str(timeout),
    ]
    if skills:
        command.extend(["--skills", skills])
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        update_run(conn, run["batch_id"], "running")
        env = {**os.environ, "EXAM_DB": str(db_path)}
        result = subprocess.run(
            command,
            input=generation_prompt(run, snapshot, batch_dir, db_path),
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
        count = imported_count(conn, run["batch_id"])
        if count < int(run["planned_count"]):
            raise RuntimeError(
                f"Hermes returned ok, but imported only {count}/{run['planned_count']} questions"
            )
        update_run(
            conn,
            run["batch_id"],
            "imported",
            generated=True,
            imported=True,
        )
        return {**run, "status": "imported", "imported_count": count, "error": None}
    except Exception as exc:
        update_run(
            conn,
            run["batch_id"],
            "failed",
            error=str(exc)[-2000:],
            generated=(batch_dir / "manifest.json").is_file(),
        )
        return {**run, "status": "failed", "error": str(exc)}
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=dt.date.fromisoformat, default=local_today())
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--calendar", type=Path, default=CALENDAR)
    parser.add_argument("--lock-file", type=Path, default=LOCK_FILE)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--concurrency", type=positive_int, default=2)
    parser.add_argument("--timeout", type=positive_int, default=2400)
    parser.add_argument("--max-turns", type=positive_int, default=200)
    parser.add_argument("--skills", default=DEFAULT_SKILLS)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        allowed, reason = workday_reason(args.date, args.calendar.resolve())
        if not allowed:
            print(
                json.dumps(
                    {"ok": True, "skipped": True, "date": str(args.date), "reason": reason},
                    ensure_ascii=False,
                )
            )
            return EXIT_OK
        with FileLock(args.lock_file):
            conn = sqlite3.connect(args.db, timeout=30)
            try:
                snapshot = load_snapshot(conn)
                runs = preview_runs(args.date) if args.dry_run else reserve_runs(conn, args.date)
            finally:
                conn.close()
            if args.dry_run:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "dry_run": True,
                            "date": str(args.date),
                            "workday_reason": reason,
                            "quota_total": sum(row["planned_count"] for row in runs),
                            "runs": runs,
                            "snapshot": snapshot_for_prompt(snapshot),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return EXIT_OK

            terminal = {"imported", "completed", "deleted"}
            pending = [row for row in runs if row["status"] not in terminal]
            results = [
                {**row, "status": f"skipped_{row['status']}"}
                for row in runs
                if row["status"] in terminal
            ]
            if pending:
                with ThreadPoolExecutor(
                    max_workers=min(args.concurrency, len(pending))
                ) as pool:
                    futures = [
                        pool.submit(
                            run_one,
                            row,
                            snapshot,
                            args.db,
                            args.output_root,
                            args.timeout,
                            args.max_turns,
                            args.skills,
                        )
                        for row in pending
                    ]
                    results.extend(future.result() for future in as_completed(futures))
            failed = [row for row in results if row["status"] == "failed"]
            print(
                json.dumps(
                    {
                        "ok": not failed,
                        "date": str(args.date),
                        "runs": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return EXIT_ERROR if failed else EXIT_OK
    except AlreadyLocked as exc:
        print(json.dumps({"ok": False, "error": "locked", "lock_file": str(exc)}))
        return EXIT_LOCKED
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

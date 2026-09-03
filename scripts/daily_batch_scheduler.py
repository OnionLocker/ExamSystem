#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""04:00 weekday AI batch scheduler."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from china_workday import CALENDAR, workday_reason
from daily_gemini_batch import generate_and_import
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
    difficulty_tier,
    load_runs,
    load_snapshot,
    local_today,
    preview_runs,
    reserve_runs,
    update_run,
)


LOCK_FILE = Path("/tmp/examsystem-daily-batches.lock")
OUTPUT_ROOT = ROOT / "data" / "daily-batches"


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
    tier = difficulty_tier(run["plan_date"])
    payload = {
        "plan_date": run["plan_date"],
        "module": run["module"],
        "difficulty_tier": tier,
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
            "batch_dir already has an unpublished draft. Fix it in the JSON you output. "
            "Do not change batch_id or start a new batch.\n"
        )
    if run["module"] == "资料分析":
        ziliao_rule = (
            "Data analysis must be exactly 4 materials x 5 questions = 20. "
            "Use ziliao_pack slot tags and the assigned answer letters. Keep 4 materials in order, 5 questions each; do not shuffle."
        )
    elif run["module"] == "判断推理":
        ziliao_rule = (
            "This is a 20-question Guangdong 判断推理 paper. Follow panduan_pack slots in order. "
            "Questions 1-5: 图形推理 (five different families). "
            "Questions 6-20: 逻辑判断 covering 加强/削弱/分析推理/结构相似/原因解释/归因; "
            "翻译推理 at most 2; never 定义判断 or 类比推理. "
            "Do NOT include 科学推理 in this batch. Science is a separate 5-question daily module. "
            "category=判断推理; sub_category=图形推理 or 逻辑判断. "
            "For 翻译推理, the keyed option must not restate 已知 instance facts (synonyms included). "
            "Need a contrapositive, disjunctive syllogism, or a two-step chain. Neutral subject; "
            "verify-logic.py rejects echo_given_fact (R029). "
            "Follow panduan_pack slot.tag exactly. "
            "A missing holdout does not skip that slot. If evaluate context fails, omit it and still import after correctness passes."
        )
    elif run["module"] == "科学推理":
        ziliao_rule = (
            "This is a 5-question Guangdong 科学推理 paper (independent module, not part of 判断推理). "
            "Follow kepui_pack slots in order. Exactly 5 questions, five different subjects "
            "from 力学、压强与浮力、电学、生物、地理 (physics 2-3 + biology 1 + geography 1). "
            "category=科学推理; sub_category=科学推理; tags[0] like 科学推理-力学-受力平衡. "
            "NEVER write category=判断推理 on this batch (hard fail even if sub_category/tags say 科学推理). "
            "Put answers on answer_plan first: any letter at most 2 times, at least 3 distinct letters; never 5 of the same letter. "
            "Every question MUST have a figure (stem_images or option images). "
            "Junior-high Guangdong level only: 杠杆/浮力/串并联/海陆风/等高线/食物链光合; "
            "formulas limited to F=ma, G=mg, p=ρgh, I=U/R. "
            "Ban 理想气体/动量守恒/洛伦兹力 and other high-school/college content. "
            "Follow kepui_pack slot.tag exactly. 等高线 means a contour-map figure item, "
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
    tier_rule = (
        f"本批难度档：difficulty_tier={tier}（日练隔天轮换：公历偶数序数日=简单 easy、奇数=难 hard；"
        "同一广东卷结构/知识点/模块配比不变，只调节‘弯子多少’）。\n"
        + ("【简单档 easy】每题 1–2 步、设问直接、干扰项为常见错法；少跨段、少多约束——"
           "资料少综合判断与跨段、数量少表示转换、逻辑少多层论证、图形规律直观。\n"
           if tier == "easy" else
           "【难档 hard】同一知识点多绕一层：表示转换、多约束、半对/近义干扰；资料更多跨段与综合判断、"
           "数量多步组合、逻辑多层论证。仍在广东卷面内，不得改成国考篇幅、不得出类比/定义。\n")
        + "在 manifest 写入 difficulty_tier；可选给每题加 difficulty:\"easy\"/\"hard\" 软标注（非硬性 GATE）。\n"
    )
    return (
        "You are ExamSystem's daily question writer for one module. Output one JSON object only.\n"
        "No markdown fences, no commentary, no tool calls, no shell.\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"{resume}"
        f"Handle only module [{run['module']}]. Question count must be exactly {run['planned_count']}, "
        "all original, do not insert origin=zhenti items.\n"
        f"Use batch_id unchanged. Number questions {run['batch_id']}_01 .. _{run['planned_count']:02d}.\n"
        "Obey every 【GATE】 rule in module-hard-rules.md (脏数字≥40%、禁某省、Q5综合判断跨篇轮换、禁课纲词、"
        "加强/削弱项须对准结论、数字推理五规律不克隆、数学运算禁鸡兔/长方形周长面积/纯相遇口算)。\n"
        f"{tier_rule}"
        "Draft from internalized GONGKAO-STYLE principles+profile. Python attaches evaluate holdout after you write; omit evaluation_contexts. generation_contexts may be omitted.\n"
        "Put the correct option on answer_plan[i].answer. Do not change computed values to chase a letter. "
        "generation_gate will reshuffle options if the draft ignores the plan. Keep Guangdong paper question order; do not shuffle questions.\n"
        f"{ziliao_rule}\n"
        f"Every question.source must be exactly {source}. Do not invent another title.\n"
        "JSON schema:\n"
        '{"questions":[{"external_id":"..._01","category":"...","sub_category":"...","tags":["module-l1-l2"],'
        '"stem":"...","stem_images":[],"options":[{"key":"A","text":"..."}],"answer":"B","analysis":"..."}],'
        '"materials":[{"external_id":"...-M01","content":"...","images":[],'
        '"figure":{"kind":"table|bars|pie","file":"images/m-02-table.png","title":"","unit":"",'
        '"headers":[],"rows":[],"ylabel":"","categories":[],'
        '"series":[{"name":"","values":[]}],"slices":[{"name":"","value":0}]}}],'
        '"calculations":{"questions":[{"question_id":"...","correct":0,"options":{"A":0,"B":0,"C":0,"D":0},"tolerance":0.01}]},'
        '"image_specs":{"questions":[{"question_id":"...","image_facts":["visible objects only"],'
        '"image_only_facts":["facts only in the figure"],"must_derive":["never put these in the image prompt"]}]}}\n'
        "materials[].figure is optional. Python renders table/bars/pie; never draw data-analysis charts yourself.\n"
        "For graphic-reasoning and science-reasoning, fill image_specs and stem_images like images/q-01-stem.png. "
        "image_facts describe only what to draw; never include the answer or must_derive.\n"
        "Do not emit manifest.json; Python writes it.\n"
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
) -> dict:
    batch_dir = output_root / run["plan_date"] / run["batch_id"]
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        update_run(conn, run["batch_id"], "running")
        generate_and_import(
            run,
            batch_dir,
            db_path,
            timeout,
            generation_prompt(run, snapshot, batch_dir, db_path),
        )
        count = imported_count(conn, run["batch_id"])
        if count < int(run["planned_count"]):
            raise RuntimeError(
                f"Gemini draft imported only {count}/{run['planned_count']} questions"
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

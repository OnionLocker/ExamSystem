#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凌晨日练调度。

每日复习卷（REVIEW_QUOTAS）每天都出：daily_review_plan 按遗忘曲线选点，直接调 quiz_lite
出题入库，不开 Hermes 会话。成套日练（MODULE_QUOTAS，Hermes 会话出题）只在工作日跑，目前全停。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from china_workday import CALENDAR, workday_reason
from daily_review_plan import build_plan, ensure_schema as ensure_plan_schema, save_plan
from normalize_ai_batch import generation_payload_extras
from scheduler_common import (
    AlreadyLocked,
    DB,
    EXIT_ERROR,
    EXIT_LOCKED,
    EXIT_OK,
    FileLock,
    MODULE_QUOTAS,
    REVIEW_QUOTAS,
    ROOT,
    active_daily_runs,
    daily_source_name,
    difficulty_tier,
    ensure_run_schema,
    load_runs,
    load_snapshot,
    local_today,
    new_batch_id,
    preview_runs,
    reserve_runs,
    update_run,
)


LOCK_FILE = Path("/tmp/examsystem-daily-batches.lock")
OUTPUT_ROOT = ROOT / "data" / "daily-batches"
DEFAULT_SKILLS = "quiz-pipeline,gd-gongkao-coach"
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
            "batch_dir already has an unpublished draft. Continue from these files, "
            "fix gate/quality issues, then import. Do not change batch_id or start a new batch.\n"
        )
    if run["module"] == "资料分析":
        ziliao_rule = (
            "Data analysis must be exactly 4 materials x 5 questions = 20. "
            "Use ziliao_pack slot tags and the assigned answer letters. Keep 4 materials in order, 5 questions each; do not shuffle. "
            "Vary the Q1-Q4 sequence and information structure when practical; this is a quality preference, not an import blocker. Before writing questions, "
            "you may assign each material a different blueprint from: direct retrieval+comparison, two-period/base-period transformation, chart trend/average, "
            "mixed multi-paragraph synthesis, and record that blueprint in the material or manifest. Across the paper, avoid repeating the same unknown, "
            "formula, and distractor path, while allowing the model to use a suitable structure for the selected knowledge points. "
            "Do not make every material Q1=倍数,Q2=增长量,Q3=平均,Q4=比重. Each material must use at least 3 different paragraphs/data blocks. "
            "For each question, include the material text and any linked image in the quality-review payload; a question is not valid without its source material. "
            "If difficulty_tier=easy, write Guangdong provincial-exam style: shorter context, one or two operations, direct wording, ordinary traps. "
            "If difficulty_tier=hard, write national-exam style: denser statistics, more cross-paragraph or table-text joins, one extra transformation, "
            "mixed-growth/contribution/ratio comparisons, and half-right distractors; never turn it into an arithmetic puzzle. "
            "Vary final question forms across the four materials; do not repeat one fixed comprehensive-judgment sentence."
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
            "Every question MUST have a figure (stem_images or option images). "
            "Junior-high Guangdong level only: 杠杆/浮力/串并联/海陆风/等高线/食物链光合; "
            "formulas limited to F=ma, G=mg, p=ρgh, I=U/R. "
            "Ban 理想气体/动量守恒/洛伦兹力 and other high-school/college content. "
            "Follow kepui_pack slot.tag exactly. 等高线 means a contour-map figure item, "
            "difficulty 3 (slope/valley/flow/simple site), not 地球自转. "
            "A missing holdout does not skip that slot. If evaluate context fails, omit it and still import after correctness passes."
            " Gemini must return a structured figure spec for every item; use scripts/quiz_generator.py's renderer and image-specs.json, "
            "never omit the figure or replace an unworkable science point with a simpler one."
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
            "Write questions.json in this paper order; do not shuffle. "
            "CONSTRAINT (machine-checked, do not invent around it): "
            "generation_gate rejects 逻辑填空 polarity dumps "
            "(2+ 贬义第二空塞进「才能让/从而/得以」) and the "
            "「从来不是+一方面另一方面+只有才能」 stamp; "
            "each of 不仅更是 / 从来不是 / 在传统开篇 / 若只就会唯有 "
            "at most once per batch. Honor yanyu_avoid.do_not_reuse_molds "
            "and do not rewrite recent_openings. "
            "Two-blank options must be half-right (one blank fits, the other fails "
            "on 搭配/色彩/方向); not three extreme fakes + one obvious key. "
            "FREEDOM (Gemini, required): topic, field, entities, 说明/叙事/对话/实验记录, "
            "1 or 2 blanks, which words to test, sentence order. "
            "Do not default to 政策议论文+然而. Mix registers."
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
        "You are ExamSystem's unattended weekday batch generator for one module.\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"{resume}"
        f"Handle only module [{run['module']}]. Question count must be exactly {run['planned_count']}, "
        "all original, do not insert origin=zhenti items.\n"
        f"Use batch_id unchanged. Working directory must be {ROOT}; run every python3/node script there.\n"
        "First read hermes-skills/quiz-pipeline/SKILL.md, "
        "hermes-skills/quiz-pipeline/references/module-hard-rules.md, hermes-skills/quiz-pipeline/references/ziliao-paper-styles.md, "
        "and hermes-skills/gd-gongkao-coach/SKILL.md "
        "(or skill_view if Hermes is available), then follow the existing quiz-pipeline. "
        "Obey every 【GATE】 rule in module-hard-rules.md (脏数字≥40%、禁某省、Q5综合判断跨篇轮换、禁课纲词、"
        "加强/削弱项须对准结论、数字推理五规律不克隆、数学运算禁鸡兔/长方形周长面积/纯相遇口算)。\n"
        f"{tier_rule}"
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


def run_legacy(args: argparse.Namespace) -> list[dict]:
    """成套日练：每个模块开一个 Hermes 会话出题。"""
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        snapshot = load_snapshot(conn)
        runs = active_daily_runs(reserve_runs(conn, args.date))
    finally:
        conn.close()
    terminal = {"imported", "completed", "deleted"}
    pending = [row for row in runs if row["status"] not in terminal]
    results = [
        {**row, "status": f"skipped_{row['status']}"}
        for row in runs
        if row["status"] in terminal
    ]
    if pending:
        with ThreadPoolExecutor(max_workers=min(args.concurrency, len(pending))) as pool:
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
    return results


def dry_run(args: argparse.Namespace, legacy: bool, reason: str) -> dict:
    """只算不写：复习卷给出选点结果，成套日练给出配额预览。"""
    out = {"ok": True, "dry_run": True, "date": str(args.date), "workday_reason": reason, "reviews": [], "runs": []}
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) if args.db.is_file() else None
    try:
        out["reviews"] = [build_plan(conn, module, args.date) for module, _slug, _count in REVIEW_QUOTAS]
    finally:
        if conn is not None:
            conn.close()
    if legacy:
        conn = sqlite3.connect(args.db, timeout=30)
        try:
            out["snapshot"] = snapshot_for_prompt(load_snapshot(conn))
        finally:
            conn.close()
        out["runs"] = active_daily_runs(preview_runs(args.date))
        out["quota_total"] = sum(row["planned_count"] for row in out["runs"])
    return out


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
    parser.add_argument("--rounds", type=positive_int, default=REVIEW_ROUNDS, help="复习卷 quiz_lite 补题轮数")
    parser.add_argument("--review-timeout", type=positive_int, default=REVIEW_TIMEOUT)
    parser.add_argument("--force", action="store_true", help="上一套没做也照出今天的复习卷")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.environ["EXAM_DB"] = str(args.db)
    try:
        legacy, reason = False, "no_legacy_quota"
        if MODULE_QUOTAS:
            legacy, reason = workday_reason(args.date, args.calendar.resolve())
        if not legacy and not REVIEW_QUOTAS:
            print(
                json.dumps(
                    {"ok": True, "skipped": True, "date": str(args.date), "reason": reason},
                    ensure_ascii=False,
                )
            )
            return EXIT_OK
        with FileLock(args.lock_file):
            if args.dry_run:
                print(json.dumps(dry_run(args, legacy, reason), ensure_ascii=False, indent=2))
                return EXIT_OK
            results = [run_review(module, slug, count, args) for module, slug, count in REVIEW_QUOTAS]
            if legacy:
                results.extend(run_legacy(args))
            failed = [row for row in results if row["status"] == "failed"]
            print(
                json.dumps(
                    {
                        "ok": not failed,
                        "date": str(args.date),
                        "workday_reason": reason,
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

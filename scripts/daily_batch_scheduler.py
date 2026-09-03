#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""04:00 weekday AI batch scheduler."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from china_workday import CALENDAR, workday_reason
from daily_gemini_batch import generate_and_import
from normalize_ai_batch import generation_payload_extras
from rule_loader import load_hard_rules
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
            str(run.get("focus_tag") or ""),
        ),
    }
    resume = ""
    if (batch_dir / "questions.json").is_file():
        resume = (
            "batch_dir already has an unpublished draft. Fix it in the JSON you output. "
            "Do not change batch_id or start a new batch.\n"
        )
    n = int(run["planned_count"])
    focus = str(run.get("focus_tag") or "").strip()
    daily_panduan = run["module"] == "判断推理" and n == 20 and not focus
    if focus:
        ziliao_rule = (
            f"This is a targeted drill on [{focus}]. Output exactly {n} questions. "
            f"Every tags[0] must be exactly {focus} or a more specific tag that starts with it. "
            "Do not emit a mixed daily paper: no 图形5+逻辑15, no five-subject 科学推理 mix, "
            "no 4 materials unless the user asked for a full 资料 paper. All original.\n"
        )
        if "翻译" in focus:
            ziliao_rule += (
                "For 翻译推理, the keyed option must not restate 已知 instance facts. "
                "Need a contrapositive, disjunctive syllogism, or a two-step chain (R029).\n"
            )
        if run["module"] == "科学推理":
            ziliao_rule += (
                "category=科学推理. Every item needs a figure + image_specs. "
                "Junior-high only. Ban 理想气体/动量守恒/洛伦兹力.\n"
            )
    elif run["module"] == "资料分析":
        ziliao_rule = (
            "Data analysis must be exactly 4 materials x 5 questions = 20. "
            "Use ziliao_pack slot tags and the assigned answer letters. Keep 4 materials in order, 5 questions each; do not shuffle."
        )
    elif run["module"] == "判断推理":
        ziliao_rule = (
            "This is a 20-question Guangdong 判断推理 paper. Follow panduan_pack slots in order. "
            "Questions 1-5 图形推理 are already drawn by Python graphic_bank (deterministic figures). "
            f"Output ONLY 15 逻辑判断 items as questions[], numbered {run['batch_id']}_06 .. _20. "
            "Do not emit graphic stems, image_specs, or stem_images. "
            "Logic covers 加强/削弱/分析推理/结构相似/原因解释/归因; "
            "翻译推理 at most 2; never 定义判断 or 类比推理. "
            "Do NOT include 科学推理 in this batch. Science is a separate 5-question daily module. "
            "category=判断推理; sub_category=逻辑判断. "
            "For 翻译推理, the keyed option must not restate 已知 instance facts (synonyms included). "
            "Need a contrapositive, disjunctive syllogism, or a two-step chain. Neutral subject; "
            "verify-logic.py rejects echo_given_fact (R029). "
            "Follow panduan_pack slot.tag and slot.exam_move exactly. exam_move is the knowledge point; "
            "the item must be unsolvable without that cognitive move. "
            "Same tag may repeat only with a different exam_move. "
            "Reskin is a fail: do not reuse 另有他因 / 甲乙丙职业匹配 / 样本占比推因果 by swapping 景区电商实验组. "
            "秒杀/结构 slots MUST ask 下列哪项与题干逻辑结构或逻辑错误最为相似; never write 真假话 on that slot. "
            "解释 slots MUST ask 最能解释; never write 指出漏洞/反驳 unless exam_move is 比例与绝对量. "
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
            "Every question MUST have a figure object AND image_specs. Python draws figure; "
            "the gate checks the SVG against image_facts (labels, ticks, intersection). "
            "figure.kind one of lever, circuit, tank, motion, contour, front, food, pedigree, reflex. "
            "反射弧/神经 → kind=reflex with parts and ①–⑤. 食物网 → kind=food. Never put a food web on a reflex stem. "
            "s-t/v-t/相遇 → kind=motion with ylabel, xmax, ymax, xticks, yticks, series[{name,points}]. "
            "Points are data coordinates; include the intersection if the stem needs 相交. Axis ticks must show those numbers. "
            "容器/浮力 → kind=tank, shape=cylinder|rect. Two vessels: names=['甲','乙'] or vessels=[{name,object,state}]. "
            "objects only what the stem names (no extra 铁块). "
            "电路 → kind=circuit with left/right/meter/main_meter (R1/R2/A1/A or L1/L2/A/V). "
            "Stem labels (甲/乙/虚线/L1/L2/钩码/①–⑤) must appear in figure params and in the drawing. "
            "image_facts = visible objects, labels, ticks, intersection only. "
            "image_only_facts = facts only in the figure. "
            "must_derive = the answer (相遇/冷锋/感受器职责); never draw must_derive as a title. "
            "Junior-high Guangdong level only: 杠杆/浮力/串并联/海陆风/等高线/食物链光合/反射弧; "
            "formulas limited to F=ma, G=mg, p=ρgh, I=U/R. "
            "Ban 理想气体/动量守恒/洛伦兹力 and other high-school/college content. "
            "Follow kepui_pack slot.tag exactly. 等高线 means kind=contour (contour-map, plan-view). "
            "锋面天气 means kind=front (cold/warm front CROSS-SECTION with 冷气团/暖气团/雨区). "
            "Never write 冷锋/暖锋 on the figure. Never put a contour-map on a 锋面/剖面 stem. "
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
        f"本批难度档：difficulty_tier={tier}（日练隔天轮换；同一广东卷结构/知识点/模块配比不变，只调弯子）。\n"
        "锚点：近年广东省考行测真题的偏易/偏难题，不是小学题、不是热身题、不是国考篇幅。\n\n"
        + (
            "【简单档 easy】地板：每题必须先认考点/模型再算；计算题要有一次真正运算（增长量/基期/比重/工程/容斥等）；选项含常见错法。\n"
            "天花板：认出模型后 1–2 步算完；设问直接；少表示转换、少多约束叠加。\n"
            "禁出：小学课本题（纯平方/立方数列、各位数字递增、一步顺流、一步工程合作无变化）；"
            "纯读数成题（谁最大、全年除以4、出口减进口）；资料四篇问法同序/双胞胎。\n"
            "分模块：\n"
            "- 资料：每篇至少 3 题要计算；Q5 综合判断仍要有，但陈述多可直接核、少跨表跨段陷阱。禁止用「少综合判断」当成可以不出。\n"
            "- 数量：数推要有一次差/和/积/交错，禁止平方数列和位数递增；运算是「认模型 + 1–2 步 + 常见错法选项」，不是公式裸套。\n"
            "- 逻辑/言语/图形：保持现在这档卷面手感，不再往下减。\n"
            if tier == "easy"
            else
            "【难档 hard】同一知识点多绕一层：基期比重/隔年/混合+比较、工程+效率变化、表示转换、多约束、半对/近义干扰。\n"
            "资料更多跨段与综合判断（一题 3–4 句里至少 2 句要算）；数量多步组合；逻辑多层论证。\n"
            "仍在广东卷面内，不得改成国考篇幅，不得出类比/定义。\n"
        )
        + "在 manifest 写入 difficulty_tier；可选给每题加 difficulty:\"easy\"/\"hard\" 软标注（非硬性 GATE）。\n"
    )

    return (
        "You are ExamSystem's daily question writer for one module. Output one JSON object only.\n"
        "No markdown fences, no commentary, no tool calls, no shell.\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"{resume}"
        f"Handle only module [{run['module']}]. "
        + (
            "JSON question count must be exactly 15 (logic only; Python already has 5 graphic items). "
            if daily_panduan
            else f"Question count must be exactly {run['planned_count']}, "
        )
        + "all original, do not insert origin=zhenti items.\n"
        f"Use batch_id unchanged. Number questions {run['batch_id']}_01 .. _{run['planned_count']:02d}.\n\n"
        f"{load_hard_rules(run['module'])}\n"
        f"{tier_rule}"
        "参考题只学步骤和干扰项分类，禁止复用实体名、数字链、罕见术语或整组选项句式。"
        "排除固定设问后不得有连续8个汉字与参考题重合。\n"
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
    finally:
        conn.close()
    try:
        generate_and_import(
            run,
            batch_dir,
            db_path,
            timeout,
            generation_prompt(run, snapshot, batch_dir, db_path),
        )
        conn = sqlite3.connect(db_path, timeout=30)
        try:
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
        finally:
            conn.close()
        return {**run, "status": "imported", "imported_count": count, "error": None}
    except Exception as exc:
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            update_run(
                conn,
                run["batch_id"],
                "failed",
                error=str(exc)[-2000:],
                generated=(batch_dir / "manifest.json").is_file(),
            )
        finally:
            conn.close()
        return {**run, "status": "failed", "error": str(exc)}



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
        if not allowed and reason == "weekend" and os.environ.get("DAILY_ALLOW_WEEKEND") == "1":
            allowed, reason = True, "weekend_open"
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

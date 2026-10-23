#!/usr/bin/env python3
"""Four isolated Hermes/Gemini workers, full-paper gate, and optional checked import."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections import Counter

# 本脚本可能经 hermes root 的 runpy 启动，sys.path 不含本脚本目录；
# 先加入 scripts 目录，保证同级模块（ziliao_parallel_runner 等）可导入。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ziliao_parallel_runner as runner
from generation_gate import verify
from ziliao_agent_trial import default_hermes_root, write
from ziliao_tracks import (TIERS, MATERIAL_TYPES, apply_difficulty_overrides, gd_rotating_paper, judge_mix_id,
                           material_question_plan, parse_difficulty_blueprint)
from service_node import service_node
from kaofa_variants import assign_ziliao_variants, record_variants
from ziliao_performance import adaptive_plan, summary as performance_summary

ROOT = Path(__file__).resolve().parents[1]
# 后 28 个按 2020–2026 粤考与 2024–2026 国考、2025 浙苏川真题资料分析材料主题整理。
THEME_POOL = (
    "农业农村经济与主要农产品产量", "文化和旅游消费与接待游客", "港口货物与集装箱吞吐量", "研发投入与专利授权",
    "城镇新增就业与常住人口", "电力生产与能源消费", "数字经济核心产业与软件信息服务", "海洋生产总值与海洋产业",
    "快递业务量与邮政物流", "新能源汽车与充电设施", "医疗卫生机构与床位人员", "金融机构存贷款",
    "社会保险参保与基金收支", "农民工规模与月均收入", "企业用水量与重复用水", "科普活动与科普示范基地",
    "法律援助与公共法律服务", "博物馆与文物保护", "铁路旅客运输与周转量", "城镇化率与城市规模",
    "体育场地与全民健身", "可再生能源绿证核发", "期货市场成交情况", "发明专利产业化",
    "民航旅客与货邮运输", "公共图书馆与群众文化机构", "中医药服务与中医类医院", "技能人才培养与技工院校",
    "居民人均可支配收入与消费支出", "电信业务收入与移动用户", "电影票房与观影人次", "支付系统业务量",
    "机动车保有量与驾驶人", "专精特新中小企业", "林业资源与湿地保护", "节假日旅游接待",
    "基层群众自治组织与村居委会", "教育事业发展与在校生", "住房公积金缴存与提取", "跨境电商交易规模",
)
THEME_RECENT_BATCHES = 6
OLD_SKELETON = ("财政", "工业", "外贸", "进出口", "社会消费品零售")
REGIONS = ("广东省", "深圳市", "广州市", "佛山市", "东莞市", "珠海市", "惠州市", "中山市", "江门市", "湛江市", "汕头市")
def recent_rotation(output_dir, batches=3):
    """最近几套（新的在前）用过的题型与材料形态，供轮转降权。"""
    plans = sorted(output_dir.glob("*/M0[1-4]-plan.json"), key=lambda p: p.stat().st_mtime)
    dirs = []
    for plan in reversed(plans):
        if plan.parent not in dirs:
            dirs.append(plan.parent)
        if len(dirs) == batches:
            break
    kinds, types, mixes = [], [], []
    for d in dirs:
        loaded = [json.loads(p.read_text()) for p in sorted(d.glob("M0[1-4]-plan.json"))]
        kinds.append({s.get("kind") for p in loaded for s in p.get("slots") or [] if s.get("kind")})
        types.append({p.get("material_type") or {"chart": "years", "table": "table", "text": "text"}.get(p.get("format"))
                      for p in loaded})
        mixes.append({judge_mix_id(s) for p in loaded for s in p.get("slots") or [] if s.get("kind") == "judge"} - {None})
    return kinds, types, mixes


def recent_themes(output_dir, batches=THEME_RECENT_BATCHES):
    """Themes of the most recent earlier batches, so consecutive papers do not reuse them."""
    plans = sorted(output_dir.glob("*/M0[1-4]-plan.json"), key=lambda p: p.stat().st_mtime)
    latest = []
    for plan in reversed(plans):
        if plan.parent not in latest:
            latest.append(plan.parent)
        if len(latest) == batches:
            break
    return {json.loads(p.read_text()).get("theme_key") for d in latest for p in d.glob("M0[1-4]-plan.json")}


def pick_themes(output_dir, rng):
    used = recent_themes(output_dir)
    fresh = [t for t in THEME_POOL if t not in used]
    pool = fresh if len(fresh) >= 4 else list(THEME_POOL)
    return rng.sample(pool, 4)


def select_repair_materials(plans, batch_id, out, gate_text, quality):
    """回修只针对结构化失败的篇。总审原文里出现的题号不作为回修依据。"""
    targets = runner.failed_visual_material_ids(out) | runner.failed_data_material_ids(out)
    if not (out / "evidence" / "system-quality.json").is_file():
        targets.update(p["id"] for p in plans if f"{batch_id}-{p['id']}" in gate_text)
    for result in (quality or {}).get("results") or []:
        if any((result.get(k) or {}).get("verdict") != "PASS" for k in ("correctness", "quality")):
            parts = str(result.get("question_id") or "").rsplit("-", 2)
            if len(parts) == 3:
                targets.add(parts[-2])
    return targets or {p["id"] for p in plans}


def import_checked(out, db):
    question_count = verify(out)["question_count"]
    if type(question_count) is not int or question_count <= 0:
        raise ValueError("闸门返回的题数无效，不得入库")
    proc = subprocess.run([service_node(), str(ROOT / "scripts/import-batch.mjs"), str(out)],
                          cwd=ROOT, env={**os.environ, "EXAM_DB": str(db.resolve())},
                          capture_output=True, text=True, timeout=180)
    (out / "import-output.txt").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError("审核已通过，但入库失败：" + (proc.stdout + proc.stderr)[-2000:])
    return question_count


def sync_reviewed_version(out, work, mid, attempt):
    """Return the exact normalized version reviewed by the full-paper gate."""
    questions = [q for q in json.loads((out / "questions.json").read_text())
                 if q["material_id"] == f"{out.name}-{mid}"]
    ids = {q["external_id"] for q in questions}
    calculations = [c for c in json.loads((out / "calculations.json").read_text())["questions"]
                    if c["question_id"] in ids]
    if len(ids) != 5 or len(calculations) != 5 or {c["question_id"] for c in calculations} != ids:
        raise ValueError("整套回修版本缺题或验算，不得写入worker")
    snapshot = work / f"before-full-repair-{attempt}"
    snapshot.mkdir()
    for name in ("questions.json", "calculations.json", ".gate.json"):
        if (work / name).exists():
            shutil.copy2(work / name, snapshot / name)
    (work / ".gate.json").unlink(missing_ok=True)
    write(work / "questions.json", questions)
    write(work / "calculations.json", {"questions": calculations})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument("--hermes-root", type=Path, default=default_hermes_root())
    parser.add_argument("--resume", type=Path, help="恢复已有批次并重新执行整套闸门，失败自动回修")
    parser.add_argument("--import", dest="import_batch", action="store_true",
                        help="完整闸门通过后调用现有校验导入器；默认仅生成验收产物")
    parser.add_argument("--difficulty", choices=TIERS, help="整卷档位，默认mid；蓝图里的difficulty与之等价")
    parser.add_argument("--blueprint", help='只调难度：{"difficulty":"mid","slots":{"M02":"easy","M03-Q4":"hard"}}，'
                                            '槽位值也可写{"difficulty":"hard","note":"命题倾向"}；内联JSON或@路径')
    parser.add_argument("--plan-only", action="store_true", help="只打印整套槽位与难度，不调用模型")
    parser.add_argument("--batch-id", help="指定批次号（每日调度用 daily-YYYYMMDD-ziliao-…）；默认自动生成")
    parser.add_argument("--no-adaptive", action="store_true", help="不按做题表现调题型与细分考法权重")
    args = parser.parse_args()
    if args.batch_id and not re.fullmatch(r"[\w-]{1,160}", args.batch_id):
        parser.error("batch-id 只能包含字母、数字、汉字、下划线和连字符")
    try:
        blueprint_tier, overrides = parse_difficulty_blueprint(args.blueprint)
    except (ValueError, OSError) as exc:
        parser.error(f"蓝图无效：{exc}")
    if args.difficulty and blueprint_tier and args.difficulty != blueprint_tier:
        parser.error("--difficulty 与蓝图 difficulty 不一致")
    tier = args.difficulty or blueprint_tier or "mid"
    if args.resume and (args.difficulty or args.blueprint):
        parser.error("--resume 沿用原批次计划，不能再改难度")
    started = time.monotonic()
    today = dt.date.today()
    batch_id = args.batch_id or today.strftime("%Y%m%d") + "_hermes_agents_" + uuid.uuid4().hex[:8]
    out = args.resume.resolve() if args.resume else args.output_dir.resolve() / batch_id
    batch_id = out.name
    rng = random.Random(batch_id)
    adaptive = ({"kind_boost": {}, "variant_boost": {}} if args.no_adaptive
                else adaptive_plan(args.db.resolve(), today, args.output_dir.resolve()))
    recent_kinds, recent_types, recent_mixes = recent_rotation(args.output_dir.resolve())
    material_types, rotated = gd_rotating_paper(tier, rng, recent_kinds, recent_types, adaptive["kind_boost"],
                                                recent_mixes, adaptive.get("mix_boost"))
    slots = assign_ziliao_variants(apply_difficulty_overrides(rotated, overrides), seed=batch_id,
                                   boost=adaptive["variant_boost"])
    runner.validate_gd_quota(slots, count=20)
    if args.plan_only:
        print(json.dumps({"difficulty": tier, "overrides": overrides, "adaptive": performance_summary(adaptive),
                          "materials": material_types, "slots": [
            {"slot": f"M{i // 5 + 1:02}-Q{i % 5 + 1}", "kind": s.get("kind_label"),
             "variant": s.get("kaofa_variant_name") or (f"{s.get('judge_stem')}｜{s.get('judge_mix_id')}"
                                                        if s.get("judge_stem") else None),
             "option_format": s.get("option_format"),
             "difficulty": s["difficulty"], "difficulty_score": s["difficulty_score"],
             **({"note": s["difficulty_note"]} if s.get("difficulty_note") else {})}
            for i, s in enumerate(slots)]}, ensure_ascii=False, indent=2))
        return 0
    out.mkdir(parents=True, exist_ok=bool(args.resume))
    (out / "images").mkdir(exist_ok=bool(args.resume))
    themes = pick_themes(args.output_dir.resolve(), rng)
    regions = ["广东省"] + rng.sample(REGIONS[1:], 3)
    tier_focus = {"easy": "难度偏易", "mid": "难度偏易到中", "hard": "难度中到难"}[tier]
    plans = [{"id": f"M{i+1:02}", "track": "gd", "difficulty": tier,
              "format": MATERIAL_TYPES[mtype]["format"], "figure_kind": MATERIAL_TYPES[mtype]["figure_kind"],
              "material_type": mtype,
              "theme": f"{regions[i]}{themes[i]}", "theme_key": themes[i], "region": regions[i],
              "count": 5, "slots": slots[i*5:(i+1)*5],
              "focus": (f"真实统计公报信息组织，地名用真实广东地名；{tier_focus}；显示数从高精度底数独立舍入；"
                        "四篇主题互不相同，不写财政、工业、外贸、社零老骨架"),
              "question_plan": material_question_plan(mtype, slots[i*5:(i+1)*5]),
              "figure_shape": MATERIAL_TYPES[mtype]["figure_shape"],
              "chart_tasks": []} for i, mtype in enumerate(material_types)]
    if any(word in plan["theme"] for plan in plans for word in OLD_SKELETON):
        raise ValueError("主题落入财政/工业/外贸/社零老骨架")
    if args.resume:
        previous = json.loads((out / "paper-summary.json").read_text())
        shutil.copy2(out / "paper-summary.json", out / f"paper-summary-before-{len(previous['full_gate_rounds'])}.json")
        plans = [json.loads((out / f"M{i:02}-plan.json").read_text()) for i in range(1, 5)]
        slots = [s for p in plans for s in p["slots"]]
        rounds, worker_runs = previous["full_gate_rounds"], previous["worker_runs"]
        (out / ".gate.json").unlink(missing_ok=True)
        write(out / "paper-summary.json", {**previous, "passed": False, "status": "rechecking"})
    else:
        for plan in plans:
            write(out / f"{plan['id']}-plan.json", plan)
        write(out / "adaptive.json", performance_summary(adaptive))
        rounds, worker_runs = [], []
    print(f"batch_dir={out}", flush=True)
    from generation_progress import Job
    job = Job(batch_id, module="资料分析", title="资料分析整套", planned=20)

    def worker(plan, resume=False, feedback=None):
        mid = plan["id"]
        job.update(stage="回修" if resume else "出题",
                   detail=f"{mid} {'回修' if resume else '生成'}中", progress=20 if resume else 15)
        work = out / "workers" / mid / batch_id
        cmd = [sys.executable, str(ROOT / "scripts/ziliao_agent_trial.py"),
               "--output-dir", str(work.parent), "--batch-id", batch_id,
               "--db", str(args.db.resolve()), "--hermes-root", str(args.hermes_root),
               "--plan", str(out / f"{mid}-plan.json")]
        if resume:
            sync_reviewed_version(out, work, mid, len(rounds))
            write(out / f"{mid}-feedback.json", feedback)
            cmd += ["--resume", str(work), "--feedback", str(out / f"{mid}-feedback.json")]
        log = out / f"{mid}-{'resume-' + str(len(rounds)) if resume else 'initial'}.log"
        mark = time.monotonic()
        print(f"{mid} {'repair' if resume else 'generation'} started", flush=True)
        try:
            with log.open("w") as handle:
                proc = subprocess.run(["timeout", "--signal=TERM", "--kill-after=10s", "25m", *cmd],
                                      cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
            record = {"material": mid, "resume": resume, "seconds": round(time.monotonic()-mark, 2),
                      "returncode": proc.returncode, "log": str(log)}
            worker_runs.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            if proc.returncode:
                raise RuntimeError(f"{mid} 未自主完成，保留失败产物；见 {log}")
            verify(work)
            return work
        finally:
            write(out / "worker-runs.json", worker_runs)

    def assemble(paths):
        materials, questions, calculations, canon = [], [], [], {}
        manifest = None
        for path in paths:
            verify(path)
            materials += json.loads((path / "materials.json").read_text())
            questions += json.loads((path / "questions.json").read_text())
            calculations += json.loads((path / "calculations.json").read_text())["questions"]
            manifest = json.loads((path / "manifest.json").read_text())
            canon.update(manifest["generation"]["kaofa_canon"])
            for image in (path / "images").glob("*.png"):
                shutil.copy2(image, out / "images" / image.name)
        paper_tier = plans[0].get("difficulty") or "mid"
        manifest["source"] = runner.batch_source("gd", False, paper_tier, today.strftime("%Y%m%d"))
        manifest["difficulty_tier"] = paper_tier
        manifest["generation"]["kaofa_canon"] = canon
        constraints = manifest["generation"]["batch_constraints"]
        constraints.update(question_count=20, targeted_drill=False, slot_plan=slots, difficulty_tier=paper_tier,
                           tag_counts=dict(Counter(s["tag"] for s in slots)))
        constraints.pop("answer_max_per_letter", None)
        constraints.pop("answer_min_letters", None)
        for name, data in [("materials", materials), ("questions", questions),
                           ("calculations", {"questions": calculations}), ("manifest", manifest),
                           ("framework", {"track": "gd", "materials": plans})]:
            write(out / f"{name}.json", data)

    passed, error = False, None
    try:
        job.update(stage="准备出题", detail="4 篇", progress=2)
        if args.resume:
            paths = [out / "workers" / p["id"] / batch_id for p in plans]
        else:
            job.update(stage="出题", detail=f"{len(plans)} 篇并行生成", progress=15)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                paths = list(pool.map(worker, plans))
            job.update(stage="组装", detail=f"{len(plans)} 篇已出稿，准备整套质检", progress=55)
        for attempt in range(len(rounds) + 1, 4):
            assemble(paths)
            (out / ".gate.json").unlink(missing_ok=True)
            for name in ("system-quality.json", "ziliao-visual-quality.json"):
                (out / "evidence" / name).unlink(missing_ok=True)
            snapshot = out / "gate-attempts" / str(attempt)
            snapshot.mkdir(parents=True)
            for name in ("materials.json", "questions.json", "calculations.json", "manifest.json"):
                shutil.copy2(out / name, snapshot / name)
            shutil.copytree(out / "images", snapshot / "images")
            print(f"full-paper gate {attempt} started", flush=True)
            job.update(stage="闸门", detail=f"整套第 {attempt} 轮质检", progress=min(90, 68 + attempt * 6))
            mark = time.monotonic()
            proc = subprocess.run(["python3", "scripts/generation_gate.py", "issue", str(out)],
                                  cwd=ROOT, env={**os.environ, "EXAM_DB": str(args.db.resolve())},
                                  text=True, capture_output=True, timeout=1200)
            (snapshot / "output.txt").write_text(proc.stdout + proc.stderr)
            if (out / "evidence").exists():
                shutil.copytree(out / "evidence", snapshot / "evidence")
            rounds.append({"attempt": attempt, "seconds": round(time.monotonic()-mark, 2), "returncode": proc.returncode})
            if not proc.returncode:
                verify(out)
                passed = True
                break
            if attempt == 3:
                raise RuntimeError("整套审核三轮未通过，禁止自动放行")
            quality = out / "evidence/system-quality.json"
            data = json.loads(quality.read_text()) if quality.exists() else {}
            visual = out / "evidence/ziliao-visual-quality.json"
            figures = json.loads(visual.read_text()) if visual.exists() else {}
            targets = select_repair_materials(plans, batch_id, out, proc.stdout + proc.stderr, data)
            job.update(stage="回修", detail=f"回修 {len(targets)} 篇", progress=72)
            def repair(plan):
                feedback = {"gate_error": (proc.stdout + proc.stderr)[-4000:],
                            "batch_quality": data.get("batch_quality"),
                            "questions": [r for r in data.get("results", []) if f"-{plan['id']}-" in r["question_id"] and r.get("verdict") != "PASS"],
                            "visual": figures}
                worker(plan, resume=True, feedback=feedback)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                list(pool.map(repair, [p for p in plans if p["id"] in targets]))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    imported = 0
    if passed and args.import_batch:
        try:
            job.update(stage="入库", detail="正在写入题库", passed=20, progress=96)
            imported = import_checked(out, args.db)
            if imported:
                record_variants(batch_id, slots)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    if passed and error is None:
        job.finish(status="done", stage="已入库" if imported else "已通过",
                   detail=f"{'已入库' if imported else '质检通过'} 20 题", passed=20, progress=100)
    else:
        job.finish(status="failed", stage="失败", error=error or "未通过",
                   detail=(error or "未通过")[:160])
    summary = {"passed": passed, "batch_dir": str(out), "model": runner.MODEL,
               "seconds": round(time.monotonic()-started, 2) + (previous["seconds"] if args.resume else 0),
               "question_count": 20, "materials": 4,
               "worker_runs": worker_runs, "full_gate_rounds": rounds,
               "error": error, "imported": imported, "manual_content_edits": 0,
               "chart_match_supported": runner.CHART_MATCH_HOOK["implemented"]}
    write(out / "paper-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

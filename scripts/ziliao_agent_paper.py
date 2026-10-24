#!/usr/bin/env python3
"""资料分析整套：蓝图分配 → 4篇单篇流水线并发出题（各自篇内审核并签名）→ 整卷轻量闸门 → 带校验入库。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter

# 本脚本可能经 hermes root 的 runpy 启动，sys.path 不含本脚本目录；
# 先加入 scripts 目录，保证同级模块（ziliao_parallel_runner 等）可导入。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ziliao_parallel_runner as runner
from generation_gate import verify
from ziliao_agent_trial import write
from ziliao_tracks import TIERS, MATERIAL_TYPES, material_question_plan, parse_difficulty_blueprint
from service_node import service_node
from kaofa_variants import record_variants
from ziliao_blueprint import build_blueprint, format_blueprint, plan_slot, pick_themes as pick_blueprint_themes
from ziliao_assembly import assemble as assemble_paper, issue_assembly
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
OLD_SKELETON = ("财政", "工业", "外贸", "进出口", "社会消费品零售")
REGIONS = ("广东省", "深圳市", "广州市", "佛山市", "东莞市", "珠海市", "惠州市", "中山市", "江门市", "湛江市", "汕头市")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 4), default=4)
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
    blueprint = build_blueprint(seed=batch_id, tier=tier, overrides=overrides, adaptive=adaptive,
                                output_dir=args.output_dir.resolve(), db=args.db.resolve())
    material_types = blueprint["material_types"]
    themes = pick_blueprint_themes(THEME_POOL, set(blueprint["recent_themes"]), rng)
    blueprint["themes"] = themes
    slots = [plan_slot(s) for s in blueprint["slots"]]
    runner.validate_gd_quota(slots, count=20)
    if args.plan_only:
        print(format_blueprint(blueprint, themes), flush=True)
        print(json.dumps({"difficulty": tier, "overrides": overrides, "adaptive": performance_summary(adaptive),
                          "relaxed": blueprint["relaxed"], "rotation_papers": blueprint["rotation_papers"],
                          "slots": [{"slot": f"M{i // 5 + 1:02}-Q{i % 5 + 1}",
                                     **{k: s.get(k) for k in ("kind_label", "kaofa_variant_name", "option_format",
                                                              "answer_key", "kind_reason", "variant_reason",
                                                              "format_reason", "judge_stem", "judge_mix_id",
                                                              "difficulty", "difficulty_score")}}
                                    for i, s in enumerate(blueprint["slots"])]}, ensure_ascii=False, indent=2))
        return 0
    out.mkdir(parents=True, exist_ok=bool(args.resume))
    (out / "images").mkdir(exist_ok=bool(args.resume))
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
    keys = [s["answer_key"] for s in blueprint["slots"]]
    if args.resume:
        plans = [json.loads((out / f"M{i:02}-plan.json").read_text()) for i in range(1, 5)]
        slots = [s for p in plans for s in p["slots"]]
        keys = [s["answer_key"] for s in json.loads((out / "paper-blueprint.json").read_text())["slots"]]
        (out / ".gate.json").unlink(missing_ok=True)
    else:
        for plan in plans:
            write(out / f"{plan['id']}-plan.json", plan)
        write(out / "adaptive.json", performance_summary(adaptive))
        write(out / "paper-blueprint.json", blueprint)
        print(format_blueprint(blueprint, themes), flush=True)
    print(f"batch_dir={out}", flush=True)
    from generation_progress import Job
    job = Job(batch_id, module="资料分析", title="资料分析整套", planned=20)
    worker_runs: list[dict] = []

    def worker(plan, attempt=1):
        """单篇流水线（材料员→出题员→篇内审核）在子进程里跑完并签名；失败重跑一次。"""
        mid = plan["id"]
        index = int(mid[1:]) - 1
        work = out / "workers" / mid / batch_id
        if (work / ".gate.json").is_file():
            try:
                verify(work)
                return work
            except Exception:
                pass
        if work.exists():
            work.rename(work.with_name(f"{batch_id}.failed-{time.strftime('%H%M%S')}-{attempt}"))
        cmd = [sys.executable, str(ROOT / "scripts/ziliao_material_pipeline.py"),
               "--plan", str(out / f"{mid}-plan.json"), "--keys", "".join(keys[index * 5:index * 5 + 5]),
               "--out", str(work), "--db", str(args.db.resolve()),
               "--progress", str(out / "workers" / mid / "progress.json")]
        log = out / f"{mid}-pipeline-{attempt}.log"
        (out / "workers" / mid).mkdir(parents=True, exist_ok=True)
        print(f"{mid} pipeline started (attempt {attempt})", flush=True)
        with log.open("w") as handle:
            proc = subprocess.run(["timeout", "--signal=TERM", "--kill-after=10s", "20m", *cmd],
                                  cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        summary_path = work / "pipeline-summary.json"
        record = json.loads(summary_path.read_text()) if summary_path.is_file() else {"material": mid}
        record.update(attempt=attempt, returncode=proc.returncode, log=str(log))
        worker_runs.append(record)
        write(out / "worker-runs.json", worker_runs)
        if proc.returncode == 0:
            verify(work)
            return work
        if attempt < 2:
            return worker(plan, attempt + 1)
        raise RuntimeError(f"{mid} 单篇两次未通过：{record.get('error') or log}")

    def watch(stop: threading.Event) -> None:
        names = {"材料": "写材料", "材料审核": "材料审核", "出题": "出题", "篇内审核": "审核", "已通过": "完成", "失败": "失败"}
        while not stop.wait(5):
            parts, total = [], 0
            for plan in plans:
                path = out / "workers" / plan["id"] / "progress.json"
                state = json.loads(path.read_text()) if path.is_file() else {}
                parts.append(f"{plan['id']} {names.get(state.get('stage'), state.get('stage') or '排队')}")
                total += int(state.get("progress") or 0)
            job.update(stage="出题", detail="｜".join(parts), progress=min(90, total // 4))

    passed, error, imported = False, None, 0
    stop = threading.Event()
    try:
        job.update(stage="出题", detail=f"4 篇并行（并发 {args.workers}）", progress=5)
        threading.Thread(target=watch, args=(stop,), daemon=True).start()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            paths = list(pool.map(worker, plans))
        stop.set()
        job.update(stage="整卷闸门", detail="核对单篇签名、内容未改动与整卷规则", progress=92)
        source = runner.batch_source("gd", False, tier, today.strftime("%Y%m%d"))
        assemble_paper(out, paths, slots, source, tier)
        issue_assembly(out, paths)
        passed = True
        if args.import_batch:
            job.update(stage="入库", detail="正在写入题库", passed=20, progress=96)
            imported = import_checked(out, args.db)
            if imported:
                record_variants(batch_id, slots)
    except Exception as exc:
        stop.set()
        error = f"{type(exc).__name__}: {exc}"
    if passed and error is None:
        job.finish(status="done", stage="已入库" if imported else "已通过",
                   detail=f"{'已入库' if imported else '质检通过'} 20 题", passed=20, progress=100)
    else:
        job.finish(status="failed", stage="失败", error=error or "未通过", detail=(error or "未通过")[:160])
    requests = Counter()
    for run in worker_runs:
        requests.update(run.get("requests") or {})
    summary = {"passed": passed and error is None, "batch_dir": str(out), "model": runner.MODEL,
               "seconds": round(time.monotonic() - started, 2), "question_count": 20, "materials": 4,
               "workers": args.workers, "worker_runs": worker_runs, "requests": dict(requests),
               "error": error, "imported": imported, "pipeline": "ziliao_material_pipeline+assembly"}
    write(out / "paper-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

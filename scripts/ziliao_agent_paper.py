#!/usr/bin/env python3
"""Four isolated Hermes/Gemini workers, full-paper gate, and optional checked import."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from collections import Counter

import ziliao_parallel_runner as runner
from generation_gate import verify
from ziliao_agent_trial import write

ROOT = Path(__file__).resolve().parents[1]


def import_checked(out, db):
    question_count = verify(out)["question_count"]
    if type(question_count) is not int or question_count <= 0:
        raise ValueError("闸门返回的题数无效，不得入库")
    proc = subprocess.run(["node", str(ROOT / "scripts/import-batch.mjs"), str(out)],
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
    parser.add_argument("--hermes-root", type=Path, default=Path.home() / ".hermes/hermes-agent")
    parser.add_argument("--resume", type=Path, help="恢复已有批次并重新执行整套闸门，失败自动回修")
    parser.add_argument("--import", dest="import_batch", action="store_true",
                        help="完整闸门通过后调用现有校验导入器；默认仅生成验收产物")
    args = parser.parse_args()
    started = time.monotonic()
    today = dt.date.today()
    batch_id = today.strftime("%Y%m%d") + "_hermes_agents_" + uuid.uuid4().hex[:8]
    out = args.resume.resolve() if args.resume else args.output_dir.resolve() / batch_id
    batch_id = out.name
    out.mkdir(parents=True, exist_ok=bool(args.resume))
    (out / "images").mkdir(exist_ok=bool(args.resume))
    slots = runner.auto_slots(20, 4, "mid", "gd")
    themes = ["财政收支与民生支出", "工业分行业营业收入与利润额", "货物进出口与分地区结构", "社会消费品零售与城乡结构"]
    plans = [{"id": f"M{i+1:02}", "track": "gd", "difficulty": "mid", "format": kind,
              "theme": themes[i], "count": 5, "slots": slots[i*5:(i+1)*5],
              "focus": "真实公报信息组织；综合问法按槽位锁定；显示数从高精度底数独立舍入",
              "question_plan": ("增长率槽只问收入/利润额同比率，不问利润率的相对增长率。" if i == 1 else
                                "混合槽不得机械反推整数配比，若问混合总增速则正文不能直接给出总增速。" if i == 3 else ""),
              "chart_tasks": []} for i, kind in enumerate(runner.default_formats("gd", 4, False))]
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
        rounds, worker_runs = [], []
    print(f"batch_dir={out}", flush=True)

    def worker(plan, resume=False, feedback=None):
        mid = plan["id"]
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
        manifest["source"] = runner.batch_source("gd", False, "mid", today.strftime("%Y%m%d"))
        manifest["generation"]["kaofa_canon"] = canon
        constraints = manifest["generation"]["batch_constraints"]
        constraints.update(question_count=20, targeted_drill=False, slot_plan=slots,
                           tag_counts=dict(Counter(s["tag"] for s in slots)))
        constraints.pop("answer_max_per_letter", None)
        constraints.pop("answer_min_letters", None)
        for name, data in [("materials", materials), ("questions", questions),
                           ("calculations", {"questions": calculations}), ("manifest", manifest),
                           ("framework", {"track": "gd", "materials": plans})]:
            write(out / f"{name}.json", data)

    passed, error = False, None
    try:
        if args.resume:
            paths = [out / "workers" / p["id"] / batch_id for p in plans]
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                paths = list(pool.map(worker, plans))
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
            targets = runner.failed_visual_material_ids(out) | runner.failed_data_material_ids(out)
            # A local hard-gate failure can name a material before any model evidence exists.
            targets.update(p["id"] for p in plans if f"{batch_id}-{p['id']}" in proc.stdout + proc.stderr)
            for result in data.get("results", []):
                if any((result.get(k) or {}).get("verdict") != "PASS" for k in ("correctness", "quality")):
                    targets.add(result["question_id"].rsplit("-", 2)[-2])
            if not targets:
                targets = {p["id"] for p in plans}
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
            imported = import_checked(out, args.db)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    summary = {"passed": passed, "batch_dir": str(out), "model": runner.MODEL,
               "seconds": round(time.monotonic()-started, 2) + (previous["seconds"] if args.resume else 0),
               "question_count": 20, "materials": 4,
               "worker_runs": worker_runs, "full_gate_rounds": rounds,
               "error": error, "imported": imported, "manual_content_edits": 0,
               "chart_match_supported": False}
    write(out / "paper-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

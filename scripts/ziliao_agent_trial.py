#!/usr/bin/env python3
"""Single scoped Hermes/Gemini worker. Produces artifacts, never imports them."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter

import ziliao_parallel_runner as runner
from generation_gate import verify
from ziliao_checklist import VERSION, MATERIAL_RULES, QUESTION_RULES, rounding_issues, material_text_issues, paper_issues

ROOT = Path(__file__).resolve().parents[1]
FILES = ("materials.json", "questions.json", "calculations.json", "manifest.json", ".gate.json")


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Trial:
    def __init__(self, out, db, plan=None, resume=False):
        self.out, self.db = out, db
        self.started = time.monotonic()
        self.lock = threading.Lock()  # Hermes may dispatch sibling tool calls concurrently.
        self.calls = []
        self.material_reviews = self.gate_attempts = 0
        self.material = None
        self.questions, self.calculations = {}, {}
        slots = plan["slots"] if plan else runner.auto_slots(5, 1, "mid", "gd")
        run = {"module": "资料分析", "slots": slots}
        self.plan = {**(plan or {"id": "M01", "track": "gd", "difficulty": "mid", "format": "chart",
                     "theme": "统计公报常见题材，自选"}),
                     "count": 5, "slots": [
                         dict(s, definition=runner.run_canon_card(run, s["tag"])) for s in slots]}
        if not re.fullmatch(r"M0[1-4]", self.plan["id"]) or len(slots) != 5:
            raise ValueError("每个worker须有M01—M04编号及五个槽位")
        self.material_id = f"{out.name}-{self.plan['id']}"
        self.frame = {"track": "gd", "difficulty": "mid", "materials": [self.plan]}
        if resume:
            self.frame = json.loads((out / "framework.json").read_text())
            self.plan = self.frame["materials"][0]
            self.calls = json.loads((out / "tool-log.json").read_text())
            self.material_reviews = len(list(out.glob("material-review-*.json")))
            self.gate_attempts = len(list((out / "gate-attempts").glob("*")))
            self.material = (json.loads((out / "materials.json").read_text()) or [None])[0]
            self.questions = {q["external_id"]: q for q in json.loads((out / "questions.json").read_text())}
            self.calculations = {c["question_id"]: c for c in json.loads((out / "calculations.json").read_text())["questions"]}
            self.invalidate()
            return
        constraints = {"all_original": True, "question_count": 5, "difficulty_tier": "mid",
                       "answer_distribution": "unconstrained", "targeted_drill": True,
                       "slot_plan": slots, "track": "gd", "track_label": "粤考日练",
                       "chart_match": runner.CHART_MATCH_HOOK, "answer_max_per_letter": 5,
                       "answer_min_letters": 1, "tag_counts": dict(Counter(s["tag"] for s in slots))}
        today = dt.date.today()
        out.mkdir(parents=True, exist_ok=False)
        (out / "images").mkdir()
        write(out / "framework.json", self.frame)
        write(out / "manifest.json", {
            "batch_id": out.name, "source": runner.batch_source("gd", True, "mid", today.strftime("%Y%m%d"), slots),
            "region": "广东-模拟", "year": today.year, "created_at": today.isoformat(),
            "license": "仅用于学习与题库内部评测", "kind": "ai-generated", "difficulty_tier": "mid",
            "generation": {"style_marker": "GONGKAO-STYLE-v2-split", "model": runner.MODEL, "ziliao_checklist": VERSION,
                           "batch_constraints": constraints, "kaofa_canon": run["kaofa_canon"],
                           "evaluation_contexts": []}})

    def invalidate(self):
        (self.out / ".gate.json").unlink(missing_ok=True)
        for name in ("system-quality.json", "ziliao-visual-quality.json"):
            (self.out / "evidence" / name).unlink(missing_ok=True)

    def save(self):
        write(self.out / "materials.json", [self.material] if self.material else [])
        write(self.out / "questions.json", [self.questions[k] for k in sorted(self.questions)])
        write(self.out / "calculations.json", {"questions": [self.calculations[k] for k in sorted(self.calculations)]})

    def invoke(self, name, args):
        with self.lock:
            began = time.monotonic()
            index = len(self.calls) + 1
            write(self.out / f"tool-{index:02d}-input.json", {"tool": name, "arguments": args})
            print(f"tool {index}: {name} started", flush=True)
            try:
                result = getattr(self, name)(**args)
            except Exception as exc:
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            event = {"index": index, "tool": name, "seconds": round(time.monotonic() - began, 2), "result": result}
            self.calls.append(event)
            write(self.out / "tool-log.json", self.calls)
            print(f"tool {index}: {name} ok={result.get('ok')} seconds={event['seconds']}", flush=True)
            return json.dumps(result, ensure_ascii=False)

    def calculate(self, expressions):
        if not isinstance(expressions, list) or not 1 <= len(expressions) <= 32:
            raise ValueError("提供1—32个纯数字四则算式")
        return {"ok": True, "values": [{"expression": e, "value": runner.safe_eval(e)} for e in expressions]}

    def submit_material(self, material):
        if self.material_reviews >= 6:
            raise ValueError("材料审核预算已用完，停止并报告失败")
        # Accept only content and structured figure, never model-supplied paths/receipts.
        candidate = {"external_id": self.material_id, "content": material.get("content"),
                     "figure": material.get("figure"), "rounding_checks": material.get("rounding_checks")}
        kind = {"chart": "bars", "table": "table", "text": "none"}[self.plan["format"]]
        if not candidate["content"] or (candidate["figure"] or {}).get("kind") != kind or not runner.valid_material({"material": candidate}):
            raise ValueError(f"须非空正文和指定figure.kind={kind}")
        errors = (runner.material_realism_errors(candidate, track="gd", long_text=self.plan["format"] == "text")
                  + rounding_issues(candidate) + material_text_issues(candidate) + self.figure_shape_issues(candidate))
        if errors:
            return {"ok": False, "issues": [{"target": self.material_id, "rule": "material_checklist",
                    "message": e, "repair": "修复材料及台账后重新submit_material；禁止放宽容差"} for e in errors]}
        self.material_reviews += 1
        review = runner.review_ziliao_material(candidate, self.plan)
        write(self.out / f"material-review-{self.material_reviews}.json", review)
        if review.get("verdict") != "PASS":
            return {"ok": False, "material_review": review}
        # Replacing a material invalidates *all* dependent artifacts, even if rendering fails.
        self.invalidate()
        self.material = None
        self.questions, self.calculations = {}, {}
        self.save()
        if kind != "none":
            runner.render_material(candidate, self.out / "images")
        self.material = candidate
        self.save()
        return {"ok": True, "material": candidate, "questions_reset": True,
                "next": runner.paper_prompt(candidate, self.plan, self.out.name)}

    def figure_shape_issues(self, candidate):
        figure = candidate.get("figure") or {}
        shape = self.plan.get("figure_shape")
        if shape == "years":
            years = [c for c in figure.get("categories") or [] if re.fullmatch(r"20\d{2}年?", str(c).strip())]
            if len(years) < 5 or len(years) != len(figure.get("categories") or []):
                return ["本篇柱图须为连续5—6个年份的时间序列（categories为年份），供年均增长与增长量题使用"]
        if shape == "two_series" and len(figure.get("series") or []) < 2:
            return ["本篇柱图须为4—8个城市或类别的两年数值（两个同单位series），供比重、增长率与混合增长率题使用"]
        return []

    def put_questions(self, questions, calculations):
        if not self.material:
            raise ValueError("先提交并通过材料审核")
        if not isinstance(questions, list) or not 1 <= len(questions) <= 5 or not isinstance(calculations, list):
            raise ValueError("提交1—5道题及对应验算；可局部替换，其他题保留")
        qs, cs = copy.deepcopy(self.questions), copy.deepcopy(self.calculations)
        ids = [q.get("external_id") for q in questions]
        calc = {c.get("question_id"): c for c in calculations}
        allowed = {f"{self.material_id}-Q{i}" for i in range(1, 6)}
        if len(set(ids)) != len(ids) or not set(ids) <= allowed or set(calc) != set(ids) or len(calc) != len(calculations):
            raise ValueError("题号须为本篇Q1—Q5，且与验算一一对应")
        fields = {"external_id", "category", "question_type", "material_id", "stem", "options",
                  "answer", "explanation", "tags", "difficulty", "family"}
        for q in questions:
            qid = q["external_id"]
            if any(o.get("figure") or o.get("images") for o in q.get("options", [])):
                raise ValueError("选项图尚未实现，不能提供或静默丢弃选项图")
            qs[qid] = {k: v for k, v in q.items() if k in fields}
            qs[qid]["category"], qs[qid]["question_type"] = "资料分析", "single"
            cs[qid] = {k: v for k, v in calc[qid].items() if k in {"question_id", "correct", "options", "tolerance"}}
        errors = {}
        for qid, q in qs.items():
            slot = self.plan["slots"][int(qid[-1]) - 1]
            issues = runner.question_errors(q, cs[qid], self.material, self.plan, qid, slot,
                                            [s for k, s in qs.items() if k != qid])
            if q.get("family") != slot["family"]:
                issues.append("family 不符槽位")
            if issues:
                errors[qid] = issues
        if errors:
            return {"ok": False, "issues": [{"target": qid, "rule": "question_checklist",
                    "message": "；".join(messages), "repair": "只修改该题及对应验算，再put_questions"} for qid, messages in errors.items()], "saved": False}
        self.invalidate()
        self.questions, self.calculations = qs, cs
        self.save()
        return {"ok": True, "saved": ids, "total_questions": len(qs)}

    def review(self):
        if len(self.questions) != 5:
            raise ValueError("先保存完整五题")
        if self.gate_attempts >= 6:
            raise ValueError("整篇审核预算已用完，停止并报告失败")
        local = paper_issues([self.material], [self.questions[k] for k in sorted(self.questions)], self.plan["slots"])
        if local:
            return {"ok": False, "issues": [{"rule": "paper_checklist", "message": m,
                    "repair": "按提示局部put_questions；不消耗整篇审核次数"} for m in local]}
        self.gate_attempts += 1
        self.invalidate()
        snapshot = self.out / "gate-attempts" / str(self.gate_attempts)
        snapshot.mkdir(parents=True)
        for name in FILES:
            if (self.out / name).exists():
                shutil.copy2(self.out / name, snapshot / name)
        shutil.copytree(self.out / "images", snapshot / "images")
        try:
            proc = subprocess.run(["python3", "scripts/generation_gate.py", "issue", str(self.out)],
                                  cwd=ROOT, env={**os.environ, "EXAM_DB": str(self.db)},
                                  capture_output=True, text=True, timeout=1200)
            (snapshot / "gate-output.txt").write_text(proc.stdout + proc.stderr)
        finally:
            if (self.out / "evidence").exists():
                shutil.copytree(self.out / "evidence", snapshot / "evidence")
            # The gate normalizes data and stamps reviewed difficulty; keep its current state.
            self.questions = {q["external_id"]: q for q in json.loads((self.out / "questions.json").read_text())}
            self.calculations = {c["question_id"]: c for c in json.loads((self.out / "calculations.json").read_text())["questions"]}
            self.material = json.loads((self.out / "materials.json").read_text())[0]
        if proc.returncode == 0:
            verify(self.out)
            return {"ok": True, "verdict": "PASS", "next": "完成；直接报告，不要再修改产物"}
        evidence = {}
        for name in ("system-quality.json", "ziliao-visual-quality.json"):
            path = self.out / "evidence" / name
            if path.exists():
                data = json.loads(path.read_text())
                if "results" in data:
                    data["results"] = [r for r in data["results"] if r.get("verdict") != "PASS"]
                evidence[name] = data
        return {"ok": False, "gate_error": (proc.stdout + proc.stderr)[-5000:], "evidence": evidence,
                "repair": "按证据题号局部put_questions；材料错误才submit_material并重出五题；审核格式错可原样重审"}

    def read_state(self):
        return {"ok": True, "material": self.material, "questions": list(self.questions.values()),
                "calculations": list(self.calculations.values()), "gate_attempts": self.gate_attempts,
                "material_reviews": self.material_reviews}


def make_agent(trial, hermes_root):
    sys.path.insert(0, str(hermes_root))
    from run_agent import AIAgent
    from tools.registry import registry
    specs = {
        "calculate": ("计算纯数字四则算式，禁止变量或函数。", {"expressions": {"type": "array", "items": {"type": "string"}}}),
        "submit_material": ("提交正文、指定图表和rounding_checks；独立审材渲染；通过后清空旧题。", {"material": {"type": "object"}}),
        "put_questions": ("保存或局部修复1—5道题和验算；本地验证失败不覆盖。结构见材料通过后的next。", {
            "questions": {"type": "array", "items": {"type": "object"}},
            "calculations": {"type": "array", "items": {"type": "object"}}}),
        "review": ("整篇提交现有独立盲解、质量、图表闸门；返回可修复问题。", {}),
        "read_state": ("读取本篇当前保存的材料、五题和验算。", {}),
    }
    for name, (description, props) in specs.items():
        registry.register(name=name, toolset="examsystem_trial", schema={"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}},
            handler=lambda args, _name=name, **kw: trial.invoke(_name, args))
    agent = AIAgent(model=runner.MODEL, base_url=runner.BASE, api_key=os.environ["CLIPROXY_API_KEY"],
                    provider="custom", api_mode="chat_completions", enabled_toolsets=["examsystem_trial"],
                    max_iterations=40, max_tokens=16000, tool_delay=0, quiet_mode=True,
                    skip_context_files=True, skip_memory=True, load_soul_identity=False,
                    save_trajectories=False, fallback_model=[], session_id=trial.out.name,
                    request_overrides={"temperature": 0.4, "parallel_tool_calls": False})
    if agent.valid_tool_names != set(specs):
        raise RuntimeError(f"工具隔离失败: {agent.valid_tool_names}")
    return agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--hermes-root", type=Path, default=Path.home() / ".hermes/hermes-agent")
    parser.add_argument("--plan", type=Path, help="冻结的单篇计划，由整套调度器传入")
    parser.add_argument("--batch-id")
    parser.add_argument("--resume", type=Path, help="续跑本篇，保留工具轨迹与对话")
    parser.add_argument("--feedback", type=Path, help="整套闸门反馈，不能更改配额或放宽审核")
    args = parser.parse_args()
    if "gemini" not in runner.MODEL.lower():
        parser.error("本试验只允许 Gemini 模型")
    batch_id = args.batch_id or dt.date.today().strftime("%Y%m%d") + "_gemini_agent_" + uuid.uuid4().hex[:8]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", batch_id):
        parser.error("batch-id只能含字母、数字、下划线和横线")
    out = args.resume.resolve() if args.resume else args.output_dir.resolve() / batch_id
    plan = json.loads(args.plan.read_text()) if args.plan else None
    trial = Trial(out, args.db.resolve(), plan, resume=bool(args.resume))
    result, passed, error = {}, False, None
    print(f"batch_dir={out}", flush=True)
    try:
        agent = make_agent(trial, args.hermes_root)
        prompt = ("你是Hermes里的独立资料分析出题子Agent。自主设计一篇材料和5题，调用工具计算、自检、修复。"
                  "只能处理本篇，不入库。必须调用review且获得PASS后才能报告完成。不要只在最终回复中输出题目。"
                  "独立审材和整篇审核各最多6次。根据反馈局部修复，不能改槽位、改闸门或编造通过。"
                  "先规划五题所需数据再submit_material；材料通过后以工具返回的next命题，put_questions后review。"
                  "纯审核响应格式错误可原样再review；有实质错误先修复再送审。每次工具失败都说明原因并自行纠错。\n"
                  + runner.framework_prompt("mid", [trial.plan["format"]], trial.plan["slots"], "gd")
                  + "\n以上框架只供你内部规划，无需单独输出JSON。\n"
                  + runner.material_prompt(trial.frame, trial.plan, out.name) + "\n" + MATERIAL_RULES + "\n" + QUESTION_RULES)
        history = None
        if args.resume:
            previous = json.loads((out / "agent-result.json").read_text())
            history = previous["messages"]
            shutil.copy2(out / "agent-result.json", out / f"agent-result-before-{len(trial.calls)}.json")
            prompt = ("整套合并审核未通过。沿用本篇材料和五题，按下列反馈自主修复，重新review通过后完成。"
                      "先read_state：程序已同步整套闸门实际审过的题面/选项/验算，可能与旧对话选项顺序不同。"
                      "只处理本篇，忽略其他篇的题号；不能改变配额。反馈：\n" + args.feedback.read_text())
        write(out / ("resume-prompt.json" if args.resume else "prompt.json"), {"prompt": prompt, "model": runner.MODEL})
        result = agent.run_conversation(prompt, conversation_history=history)
        write(out / "agent-result.json", result)
        verify(out)
        passed = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        summary = {"passed": passed, "batch_dir": str(out), "model": runner.MODEL,
                   "seconds": round(time.monotonic() - trial.started, 2), "material_reviews": trial.material_reviews,
                   "gate_attempts": trial.gate_attempts, "tool_calls": len(trial.calls),
                   "rejected_tool_calls": sum(c["result"].get("ok") is False for c in trial.calls),
                   "agent_api_calls": result.get("api_calls"), "agent_total_tokens": result.get("total_tokens"),
                   "error": error, "imported": 0, "manual_content_edits": 0}
        write(out / "trial-summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

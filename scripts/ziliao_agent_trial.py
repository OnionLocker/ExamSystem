#!/usr/bin/env python3
"""资料分析单篇产物与本地校验：材料/题目的文件管理、程序化检查与篇内完整闸门（generation_gate issue）。

由 ziliao_material_pipeline 的各角色调用；不调模型写题，不入库。
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ziliao_parallel_runner as runner
from generation_gate import verify
from ziliao_checklist import VERSION, rounding_issues, material_text_issues, paper_issues

ROOT = Path(__file__).resolve().parents[1]
FILES = ("materials.json", "questions.json", "calculations.json", "manifest.json", ".gate.json")
PAPER_MAX = 10


def question_number(qid: str) -> int:
    match = re.search(r"-Q(\d+)$", str(qid or ""))
    if not match:
        raise ValueError(f"题号无法解析：{qid}")
    return int(match.group(1))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Trial:
    def __init__(self, out, db, plan):
        self.out, self.db = out, db
        self.started = time.monotonic()
        self.material_reviews = self.gate_attempts = 0
        self.material = None
        self.questions, self.calculations = {}, {}
        slots = plan["slots"]
        run = {"module": "资料分析", "slots": slots}
        n = len(slots)
        self.plan = {**plan,
                     "count": n, "slots": [
                         dict(s, definition=runner.run_canon_card(run, s["tag"])) for s in slots]}
        if not re.fullmatch(r"M0[1-4]", self.plan["id"]) or not 1 <= n <= PAPER_MAX:
            raise ValueError(f"每个worker须有M01—M04编号及1—{PAPER_MAX}个槽位")
        self.material_id = f"{out.name}-{self.plan['id']}"
        self.tier = str(self.plan.get("difficulty") or "mid")
        self.frame = {"track": "gd", "difficulty": self.tier, "materials": [self.plan]}
        # 5题整篇沿用原来的字母上限，避免把已有单篇收紧。超过5题的专项按均匀分布收口。
        max_per = 5 if n <= 5 else max(2, -(-n // 4))
        constraints = {"all_original": True, "question_count": n, "difficulty_tier": self.tier,
                       "answer_distribution": "unconstrained", "targeted_drill": True,
                       "slot_plan": slots, "track": "gd", "track_label": "粤考日练",
                       "chart_match": runner.CHART_MATCH_HOOK, "answer_max_per_letter": max_per,
                       "answer_min_letters": 1 if n <= 5 else min(4, n),
                       "tag_counts": dict(Counter(s["tag"] for s in slots))}
        today = dt.date.today()
        out.mkdir(parents=True, exist_ok=False)
        (out / "images").mkdir()
        write(out / "framework.json", self.frame)
        write(out / "manifest.json", {
            "batch_id": out.name, "source": runner.batch_source("gd", True, self.tier, today.strftime("%Y%m%d"), slots),
            "region": "广东-模拟", "year": today.year, "created_at": today.isoformat(),
            "license": "仅用于学习与题库内部评测", "kind": "ai-generated", "difficulty_tier": self.tier,
            "generation": {"style_marker": "GONGKAO-STYLE-v2-split", "model": runner.MODEL, "ziliao_checklist": VERSION,
                           "batch_constraints": constraints, "kaofa_canon": run["kaofa_canon"],
                           "evaluation_contexts": []}})

    def invalidate(self):
        (self.out / ".gate.json").unlink(missing_ok=True)
        for name in ("system-quality.json", "ziliao-visual-quality.json"):
            (self.out / "evidence" / name).unlink(missing_ok=True)

    def save(self):
        write(self.out / "materials.json", [self.material] if self.material else [])
        order = sorted(self.questions, key=question_number)
        write(self.out / "questions.json", [self.questions[k] for k in order])
        write(self.out / "calculations.json", {"questions": [self.calculations[k] for k in order if k in self.calculations]})

    def submit_material(self, material):
        if self.material_reviews >= 6:
            raise ValueError("材料审核预算已用完，停止并报告失败")
        # Accept only content and structured figure, never model-supplied paths/receipts.
        candidate = {"external_id": self.material_id, "content": material.get("content"),
                     "figure": material.get("figure"), "rounding_checks": material.get("rounding_checks")}
        kind = runner.figure_kind(self.plan)
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
        return {"ok": True, "material": candidate, "questions_reset": True}

    def figure_shape_issues(self, candidate):
        figure = candidate.get("figure") or {}
        shape = self.plan.get("figure_shape")
        if shape == "years":
            years = [c for c in figure.get("categories") or [] if re.fullmatch(r"20\d{2}年?", str(c).strip())]
            if len(years) < 5 or len(years) != len(figure.get("categories") or []):
                return ["本篇柱图须为连续5—6个年份的时间序列（categories为年份），供年均增长与增长量题使用"]
        if shape == "two_series" and len(figure.get("series") or []) < 2:
            return ["本篇柱图须为4—8个城市或类别的两年数值（两个同单位series），供比重、增长率与混合增长率题使用"]
        if shape == "monthly":
            first = [str(row[0]) for row in figure.get("rows") or [] if row]
            if sum("月" in cell or "季度" in cell for cell in first) < 5:
                return ["本篇表格首列须为月份、季度或“1—N月”累计期（至少5行），供累计与当期、月均题使用"]
        if shape == "pie" and len(figure.get("series") or []) != 1:
            return ["本篇饼图只能有一个series，categories为3—6个组成部分"]
        return []

    def put_questions(self, questions, calculations):
        if not self.material:
            raise ValueError("先提交并通过材料审核")
        n = len(self.plan["slots"])
        if not isinstance(questions, list) or not 1 <= len(questions) <= n or not isinstance(calculations, list):
            raise ValueError(f"提交1—{n}道题及对应验算；可局部替换，其他题保留")
        qs, cs = copy.deepcopy(self.questions), copy.deepcopy(self.calculations)
        ids = [q.get("external_id") for q in questions]
        calc = {c.get("question_id"): c for c in calculations}
        allowed = {f"{self.material_id}-Q{i}" for i in range(1, n + 1)}
        if len(set(ids)) != len(ids) or not set(ids) <= allowed or set(calc) != set(ids) or len(calc) != len(calculations):
            raise ValueError(f"题号须为本篇Q1—Q{n}，且与验算一一对应")
        fields = {"external_id", "category", "question_type", "material_id", "stem", "options",
                  "answer", "explanation", "tags", "difficulty", "family"}
        for q in questions:
            qid = q["external_id"]
            slot = self.plan["slots"][question_number(qid) - 1]
            if slot.get("kind") == "chart_match":
                q = self.render_option_figures(q)
            elif any(o.get("figure") or o.get("images") for o in q.get("options", [])):
                raise ValueError("只有图表匹配槽位能用选项图；本题去掉options[].figure")
            qs[qid] = {k: v for k, v in q.items() if k in fields}
            qs[qid]["category"], qs[qid]["question_type"] = "资料分析", "single"
            cs[qid] = {k: v for k, v in calc[qid].items()
                       if k in {"question_id", "correct", "options", "tolerance", "ranges", "target"}}
        errors = {}
        for qid, q in qs.items():
            slot = self.plan["slots"][question_number(qid) - 1]
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
        result = {"ok": True, "saved": ids, "total_questions": len(qs)}
        return result

    def render_option_figures(self, question):
        question = copy.deepcopy(question)
        options = question.get("options") or []
        if len(options) != 4 or not all(isinstance(o.get("figure"), dict) for o in options):
            raise ValueError("图表匹配题四个选项都须给figure（kind/categories/values），text写空字符串")
        for option in options:
            name = f"{question['external_id']}-{option.get('key')}.png"
            runner.render_option_figure(option["figure"], self.out / "images" / name)
            option["images"] = [f"images/{name}"]
            option["text"] = str(option.get("text") or "")
        return question

    def review(self):
        if len(self.questions) != len(self.plan["slots"]):
            raise ValueError(f"先保存完整{len(self.plan['slots'])}题")
        if self.gate_attempts >= 6:
            raise ValueError("整篇审核预算已用完，停止并报告失败")
        local = paper_issues([self.material], [self.questions[k] for k in sorted(self.questions, key=question_number)], self.plan["slots"])
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

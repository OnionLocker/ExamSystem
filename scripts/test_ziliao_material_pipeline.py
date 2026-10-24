#!/usr/bin/env python3
"""离线回放：用写好的模型回复把单篇流水线完整跑一遍，不发任何真实请求。

ziliao_agent_trial 导入时会切换到 Hermes 解释器，所以这是脚本式测试：python3 test_ziliao_material_pipeline.py
"""
import json
import re
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import ziliao_material_pipeline as pipe
from ziliao_checklist import paper_issues
from ziliao_tracks import KIND_FAMILY, ZILIAO_CMP, ZILIAO_RATE, ZILIAO_SHARE

FOUR = "(318.7+426.3+251.9+187.4)"
MATERIAL = {
    "content": ("2024年，广州市文化旅游消费持续回暖。越秀、天河、海珠、番禺四个重点区文旅消费额合计{{G1}}亿元，"
                "其中越秀区318.7亿元，天河区426.3亿元，海珠区251.9亿元，番禺区187.4亿元。"
                "全市全年接待游客2.36亿人次，同比增长8.7%；旅游总收入同比增长9.4%。"),
    "figure": {"kind": "table", "title": "2024年广州市部分区文旅消费情况", "unit": "亿元、%、万人次",
               "headers": ["区域", "2024年消费额（亿元）", "2023年消费额（亿元）", "同比增速（%）", "接待游客（万人次）"],
               "rows": [["越秀", "318.7", "289.4", "10.1", "4127.6"], ["天河", "426.3", "381.2", "11.8", "5263.9"],
                        ["海珠", "251.9", "236.8", "6.4", "3318.2"], ["番禺", "187.4", "165.3", "13.4", "2786.5"],
                        ["白云", "213.6", "202.9", "5.3", "2954.1"], ["荔湾", "142.8", "131.6", "8.5", "1873.4"]],
               "categories": [], "series": []},
    "groups": [{"id": "G1", "label": "2024年四个重点区文旅消费额合计", "unit": "亿元", "places": 1,
                "parts": [{"label": l, "shown": v} for l, v in
                          (("越秀", "318.7"), ("天河", "426.3"), ("海珠", "251.9"), ("番禺", "187.4"))]}],
}

Q1_INTEGER = {"stem": "2024年，天河区文旅消费额约占四个重点区合计的（ ）", "analysis": "天河区426.3亿元。",
              "unit": "%", "decimals": 1, "correct_expr": f"426.3/{FOUR}*100",
              "distractors": [{"expr": f"318.7/{FOUR}*100", "why": "分子取相邻主体越秀区"},
                              {"expr": f"251.9/{FOUR}*100", "why": "分子取海珠区"},
                              {"expr": "426.3/(318.7+251.9+187.4)*100", "why": "分母漏加本区"}]}
Q1_FIXED = {"stem": "2024年，越秀区文旅消费额约占四个重点区合计的比重为（ ）",
            "analysis": "越秀区318.7亿元，四区合计318.7+426.3+251.9+187.4=1184.30亿元，比重=318.7÷1184.3×100≈26.91%。",
            "unit": "%", "decimals": 1, "correct_expr": f"318.7/{FOUR}*100",
            "distractors": [{"expr": f"251.9/{FOUR}*100", "why": "分子取相邻主体海珠区"},
                            {"expr": f"187.4/{FOUR}*100", "why": "分子取番禺区"},
                            {"expr": "318.7/(426.3+251.9+187.4)*100", "why": "分母漏加本区"}]}
Q2 = {"stem": "2024年，天河区文旅消费额同比增长约（ ）",
      "analysis": "2024年426.3亿元，2023年381.2亿元，增长率=(426.3−381.2)÷381.2×100≈11.83%。",
      "unit": "%", "decimals": 1, "value_expr": "(426.3-381.2)/381.2*100",
      "distractors": [{"expr": "(426.3-381.2)/426.3*100", "why": "用现期作分母"}]}
Q3 = {"stem": "表中6个区，2024年文旅消费额同比增速超过10%的有几个（ ）",
      "analysis": "越秀10.1%、天河11.8%、番禺13.4%超过10%；海珠6.4%、白云5.3%、荔湾8.5%未超过。",
      "value_expr": "3", "unit": "个"}
Q4 = {"stem": "2024年，越秀、海珠、白云三区文旅消费额同比增量从高到低排序正确的是（ ）",
      "options": [{"text": "越秀＞海珠＞白云"}, {"text": "海珠＞越秀＞白云"},
                  {"text": "越秀＞白云＞海珠"}, {"text": "白云＞海珠＞越秀"}], "correct": 0,
      "analysis": "越秀318.7−289.4=29.30，海珠251.9−236.8=15.10，白云213.6−202.9=10.70，[1]排序正确，[2][3][4]顺序错误。"}
Q5 = {"stem": "根据资料，以下说法可以判断属实的是（ ）", "correct": 2,
      "options": [{"text": "2024年番禺区文旅消费额超过200亿元"}, {"text": "2023年荔湾区文旅消费额高于140亿元"},
                  {"text": "2024年天河区接待游客比越秀区多1000万人次以上"}, {"text": "2024年海珠区增速高于全市旅游收入增速"}],
      "analysis": "[1]番禺187.4亿元，200−187.4=12.60，不超过200；[2]荔湾131.6亿元，140−131.6=8.40，不高于140；"
                  "[3]5263.9−4127.6=1136.30万人次，超过1000，属实；[4]9.4−6.4=3.00个百分点，海珠低于全市，不成立。"}
DRAFTS = {1: Q1_INTEGER, 2: Q2, 3: Q3, 4: Q4, 5: Q5}


def slot(kind, tag, label, variant, fmt="exact", score=2, **extra):
    return {"kind": kind, "family": KIND_FAMILY.get(kind, kind), "tag": tag, "kind_label": label,
            "kaofa_variant_name": variant, "option_format": fmt, "difficulty": "mid", "difficulty_score": score,
            "brief": f"{label}；本题考法变式：{variant}。", **extra}


PLAN = {"id": "M02", "track": "gd", "difficulty": "mid", "format": "table", "figure_kind": "table",
        "material_type": "table", "theme": "广州市文化和旅游消费", "theme_key": "文化和旅游消费", "region": "广州市",
        "count": 5, "figure_shape": None, "chart_tasks": [], "question_plan": "表格给各区两年消费额与增速。",
        "slots": [slot("share", ZILIAO_SHARE, "比重", "现期比重直接求", score=1),
                  slot("growth_rate", ZILIAO_RATE, "增长率", "两期数值求增长率", "interval"),
                  slot("count", ZILIAO_CMP, "计数", "增速超阈值的个数", score=3),
                  slot("sort", ZILIAO_CMP, "排序", "增长量排序"),
                  {"kind": "judge", "family": "judge", "tag": ZILIAO_CMP, "kind_label": "综合分析", "option_format": None,
                   "difficulty": "mid", "difficulty_score": 4, "judge_form": "属实",
                   "judge_stem": "根据资料，以下说法可以判断属实的是", "judge_mix": "估算比较：四句以数据核算为主。",
                   "brief": "综合分析。"}]}
KEYS = ["C", "A", "B", "D", "C"]


def fake_call(prompt, max_tokens=12000, role=None):
    if "你是资料分析材料员" in prompt:
        return json.loads(json.dumps(MATERIAL))
    index = int(re.search(r"只出本篇第(\d)题", prompt)[1])
    if "上一版（未通过）" in prompt:
        return dict(Q1_FIXED) if index == 1 else dict(DRAFTS[index], stem=DRAFTS[index]["stem"].replace("约", "大约"))
    return json.loads(json.dumps(DRAFTS[index]))


def fake_review(self):
    local = paper_issues([self.material], [self.questions[k] for k in sorted(self.questions)], self.plan["slots"])
    if local:
        return {"ok": False, "issues": [{"rule": "paper_checklist", "message": m} for m in local]}
    self.gate_attempts += 1
    if self.gate_attempts == 1 and getattr(fake_review, "reject_first", True):
        return {"ok": False, "gate_error": "generation gate failed", "evidence": {"system-quality.json": {
            "results": [{"question_id": f"{self.material_id}-Q{i}", "verdict": "REJECT",
                         "correctness": {"verdict": "PASS", "issues": []}, "quality": {"verdict": "PASS", "issues": []}}
                        for i in range(1, 6)],
            "batch_quality": {"verdict": "REJECT", "review": {"issues": [
                {"question_id": f"{self.material_id}-Q2", "description": "第2题表述可更贴近真题"}]}}}}}
    (self.out / ".gate.json").write_text(json.dumps({"fake": True}))
    return {"ok": True, "verdict": "PASS"}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "20261024_ziliao_single_offline" 
        with patch.object(pipe.runner, "call", side_effect=fake_call), \
             patch("ziliao_agent_trial.runner.review_ziliao_material", return_value={"verdict": "PASS"}), \
             patch("ziliao_agent_trial.runner.render_material"), \
             patch.object(pipe.Trial, "review", fake_review), \
             patch.object(pipe, "precheck_images"), \
             patch.object(pipe, "Job"):
            summary = pipe.run_pipeline(PLAN, KEYS, out, Path(tmp) / "exam.db")
        assert summary["passed"], summary["error"]
        questions = json.loads((out / "questions.json").read_text())
        assert len(questions) == 5
        manifest = (out / "manifest.json").read_text()
        assert "answer_key" not in manifest, "答案字母泄露进批次清单"
        print("PASS: 5题全部保存，批次清单不含答案字母")

        calls = sorted(p.name for p in (out / "calls").glob("*.json"))
        roles = [re.sub(r"^\d+-", "", n)[:-5] for n in calls]
        assert roles.count("material") == 1 and roles.count("questions") == 5, roles
        repairs = [json.loads((out / "calls" / n).read_text()) for n in calls if "question_repair" in n]
        repaired = sorted(int(re.search(r"只出本篇第(\d)题", r["prompt"])[1]) for r in repairs)
        assert repaired == [1, 2], repaired
        print("PASS: 材料1次、出题5次并行；本地校验只回修Q1（整数百分比），审核只回修点名的Q2")

        prompt = json.loads((out / "calls" / next(n for n in calls if "questions" in n)).read_text())["prompt"]
        for banned in ("calculation写ranges", "options[].figure", "解析逐项写出“X项", "价格口径"):
            assert banned not in prompt, banned
        assert len(prompt) < 4000, len(prompt)
        print(f"PASS: 出题提示词无旧格式矛盾，单题约{len(prompt)}字")

        by_id = {q["external_id"][-2:]: q for q in questions}
        assert by_id["Q1"]["answer"] == "C" and [o["text"] for o in by_id["Q1"]["options"]] == sorted(
            [o["text"] for o in by_id["Q1"]["options"]], key=lambda t: float(t.rstrip("%")))
        assert by_id["Q2"]["options"][0]["text"].startswith("不到") and by_id["Q2"]["options"][3]["text"].startswith("超过")
        assert by_id["Q3"]["answer"] == "B" and by_id["Q5"]["answer"] == "C"
        assert Counter(q["answer"] for q in questions) == Counter(KEYS), [q["answer"] for q in questions]
        assert "^" not in json.dumps(questions, ensure_ascii=False)
        print("PASS: 数值选项升序、区间选项从小到大；区间为隔开错法换了位置，其余题自动补齐，答案组合与蓝图一致")
        stages = [r["stage"] + ":" + r["target"] for r in summary["rejections"]]
        assert stages == ["question_check:Q1", "gate:Q2"], stages
        print("PASS: 退回记录准确：", stages)


def offline_patches():
    return (patch.object(pipe.runner, "call", side_effect=fake_call),
            patch("ziliao_agent_trial.runner.review_ziliao_material", return_value={"verdict": "PASS"}),
            patch("ziliao_agent_trial.runner.render_material"),
            patch.object(pipe.Trial, "review", fake_review),
            patch.object(pipe, "precheck_images"),
            patch.object(pipe, "Job"))


def hedging():
    import time
    calls = []

    def slow_then_fast(prompt, max_tokens=12000, role=None):
        calls.append(role)
        if len(calls) == 1:
            time.sleep(1.5)
        return {"ok": role}

    with patch.object(pipe.runner, "call", side_effect=slow_then_fast), \
         patch.dict(pipe.HEDGE_AFTER, {"material": 0.3}):
        pipe.HEDGES.clear()
        result = pipe.ask("material", "x")
    assert result == {"ok": "material_hedge"} and pipe.HEDGES == ["material"], (result, pipe.HEDGES)
    print("PASS: 材料请求超时自动补发，用先返回的结果")


def assembly():
    import random
    from contextlib import ExitStack
    from ziliao_assembly import assemble, issue_assembly, verify_assembly
    from normalize_ai_batch import planned_ziliao_groups
    groups = planned_ziliao_groups(random.Random(3))
    fake_review.reject_first = False
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "20261024_ziliao_offline_paper"
        paths, slots = [], []
        with ExitStack() as stack:
            for item in offline_patches():
                stack.enter_context(item)
            for m in range(4):
                plan = json.loads(json.dumps(PLAN)) | {"id": f"M0{m + 1}"}
                work = out / "workers" / plan["id"] / out.name
                summary = pipe.run_pipeline(plan, groups[m], work, Path(tmp) / "exam.db")
                assert summary["passed"], summary["error"]
                answers = [s["answer"] for s in summary["slots"]]
                assert Counter(answers) == Counter(groups[m]), (answers, groups[m])
                paths.append(work)
                slots += plan["slots"]
        stub = lambda work: {"ok": True}
        with patch("ziliao_tracks.validate_gd_quota"):
            assemble(out, paths, slots, "粤考日练-资料分析-mid-20261024", "mid")
            receipt = issue_assembly(out, paths, stub)
            assert verify_assembly(out, receipt, stub)["question_count"] == 20
            print("PASS: 4篇离线跑通、每篇答案组合与蓝图一致，整卷组装签发与复核通过")
            questions = json.loads((out / "questions.json").read_text())
            questions[7]["explanation"] += "（改）"
            (out / "questions.json").write_text(json.dumps(questions, ensure_ascii=False))
            try:
                verify_assembly(out, receipt, stub)
                raise AssertionError("改动后的整卷不应通过复核")
            except ValueError as exc:
                assert "questions" in str(exc) or "改动" in str(exc), exc
            print("PASS: 整卷签发后改动题目会被复核拦下")
    fake_review.reject_first = True


if __name__ == "__main__":
    main()
    hedging()
    assembly()

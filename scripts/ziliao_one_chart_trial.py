#!/usr/bin/env python3
"""Minimal two-stage Gemini trial: freeze chart data, render it, then write 5 questions."""
from __future__ import annotations
import json, os, subprocess, time, urllib.request
from pathlib import Path
from ziliao_parallel_runner import call

ROOT = Path(__file__).resolve().parents[1]
BATCH = "20260920_hermes_ziliao_chart_trial_01"
OUT = ROOT / "data" / "chart-trial" / "2026-09-20" / BATCH


def main() -> int:
    started = time.monotonic(); OUT.mkdir(parents=True, exist_ok=True); (OUT / "images").mkdir(exist_ok=True)
    frame = call("""只生成一份广东省考资料分析图表材料的数据底稿，不出题。输出JSON：
{"theme":"...","content":"完整材料正文，正文中的所有图表数字都必须出现","figure":{"kind":"bars","title":"不超过16个汉字","unit":"亿元","categories":["标签1","标签2","标签3","标签4"],"series":[{"name":"业务收入","values":[100,200,300,400]}]}}
要求：使用G省/H省或全国；柱状图只有一个系列；分类标签每个不超过6个汉字；正文、图表数字和单位必须完全一致；数据足够支持5道资料分析题。只输出JSON。""", 5000)
    fig = frame["figure"]; assert fig["kind"] == "bars" and len(fig["categories"]) == len(fig["series"][0]["values"])
    image = OUT / "images" / "material-bars.png"
    cmd = ["python3", "scripts/render_ziliao_figure.py", "bars", "--title", fig["title"], "--ylabel", fig["unit"],
           "--categories", ",".join(fig["categories"]), "--series", f"{fig['series'][0]['name']}:{','.join(map(str, fig['series'][0]['values']))}", "--out", str(image)]
    subprocess.run(cmd, cwd=ROOT, check=True)
    qprompt = f"""只根据以下已经冻结的资料正文和图表数据出5道原创广东省考资料分析题，不得修改材料、图表数字、单位或分类。options必须是带key/text的A-D对象数组：
材料：{frame['content']}
图表数据：{json.dumps(fig, ensure_ascii=False)}
第5题必须是综合判断题，且答案唯一。输出严格JSON，字段为 material、questions、calculations；questions 每题含 external_id、category、question_type、material_id、stem、options(A-D)、answer、explanation、tags、difficulty；tags 必须严格从完整白名单复制：资料分析-基础知识-统计术语与常考概念；资料分析-ABRX类-基期量计算与比较；资料分析-ABRX类-增长量计算与现期推算；资料分析-ABRX类-增长率计算模型；资料分析-比重类-现期、基期与隔级比重；资料分析-比重类-比重趋势、比重差与比值差；资料分析-平均类-一般平均值与年均增速/增量；资料分析-比较类-双线法与增量比较；资料分析-盐水类-十字交叉法与混合增长率；资料分析-特殊考点-拉动增长、贡献率与容斥。不得自创标签。calculations 每题含 question_id、correct（只允许数字和四则运算括号）、options(A-D数值)、tolerance。解析最后结论必须与answer一致，禁止草稿记录。"""
    result = call(qprompt, 12000)
    material_id = BATCH + "-M01"
    material = {"external_id": material_id, "content": frame["content"], "images": ["images/material-bars.png"]}
    questions = result["questions"]
    for i, q in enumerate(questions, 1):
        q["external_id"] = f"{BATCH}-Q{i}"; q["material_id"] = material_id
    manifest = {"batch_id": BATCH, "source": "广东省考行测-资料分析-20260920", "region": "广东-模拟", "year": 2026,
                "license": "仅用于学习与题库内部评测", "created_at": "2026-09-20", "kind": "ai-generated",
                "difficulty_tier": "hard", "generation": {"style_marker": "GONGKAO-STYLE-v1",
                "batch_constraints": {"all_original": True, "question_count": 5, "answer_min_letters": 2}, "evaluation_contexts": []}}
    for name, data in [("manifest.json", manifest), ("materials.json", [material]), ("questions.json", questions),
                       ("calculations.json", {"questions": result["calculations"]}), ("frozen-data.json", frame)]:
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    gate = subprocess.run(["python3", "scripts/generation_gate.py", "issue", str(OUT)], cwd=ROOT, text=True, capture_output=True)
    timing = {"total_seconds": round(time.monotonic() - started, 2), "gate_returncode": gate.returncode}
    (OUT / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2))
    print(gate.stdout or gate.stderr)
    if gate.returncode: return gate.returncode
    imp = subprocess.run(["node", "scripts/import-batch.mjs", str(OUT)], cwd=ROOT, text=True, capture_output=True)
    print(imp.stdout or imp.stderr); return imp.returncode

if __name__ == "__main__":
    raise SystemExit(main())

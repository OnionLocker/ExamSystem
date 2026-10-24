#!/usr/bin/env python3
"""Gemini data-analysis paper: framework -> materials -> independent questions."""
from __future__ import annotations

import argparse, concurrent.futures, datetime as dt, json, math, os, re, shutil, sqlite3, subprocess, time, urllib.request, uuid
from pathlib import Path
from collections import Counter
from quiz_generator import resolve_slots, run_canon_card
from kaodian_taxonomy import validate_ai_primary_tag
from scheduler_common import DB
from service_node import service_node
from kaofa_variants import assign_ziliao_variants, record_variants
import model_router
from quality_orchestrator import equivalent, safe_eval, review_ziliao_material
from ziliao_tracks import (
    TRACK_GD,
    apply_slot_difficulty,
    assert_source_label,
    batch_source,
    default_formats,
    material_realism_errors,
    render_option_figures,
    resolve_gemini_model,
    resolve_track_slots,
    skip_calculation,
    track_framework_rules,
    track_material_rules,
    track_question_rules,
    validate_comparison_explanations,
    validate_difficulty_gradient,
    validate_gd_quota,
    explanation_missing_years,
    classify_judge_form,
    chart_match_issues,
    range_calculation_issues,
    uses_ranges,
    KIND_CHART_MATCH,
    CHART_MATCH_HOOK,
    ZILIAO_INFERENCE_RULES,
    ZILIAO_FIGURE_RULES,
    GD_DESIGN_RULES,
    GD_PAPER_RULES,
)
from ziliao_checklist import (VERSION as CHECKLIST_VERSION, MATERIAL_RULES, material_text_issues,
                              question_style_issues, rounding_issues)

ROOT = Path(__file__).resolve().parents[1]
MODEL = resolve_gemini_model()
BASE = model_router.resolve_base_url()
GATE_ATTEMPTS = 3
TAGS = [
    "资料分析-基础知识-统计术语与常考概念", "资料分析-ABRX类-基期量计算与比较",
    "资料分析-ABRX类-增长量计算与现期推算", "资料分析-ABRX类-增长率计算模型",
    "资料分析-比重类-现期、基期与隔级比重", "资料分析-比重类-比重趋势、比重差与比值差",
    "资料分析-平均类-一般平均值与年均增速/增量", "资料分析-比较类-双线法与增量比较",
    "资料分析-盐水类-十字交叉法与混合增长率", "资料分析-特殊考点-拉动增长、贡献率与容斥",
]
BALANCED_TAGS = TAGS[:]
CALCULATION_RULE = """calculation.correct和options中的值必须是JSON数字或仅含数字及+-*/括号的算式字符串。
禁止Python函数、变量、if、列表推导、count、index或中文；不要把题面选项字母写成算式。
比较/排序/计数题直接填写独立算出的年份、排名或个数（例如2021或2），在解析中枚举全部比较点，
系统另有不看验算清单的盲解核验。数值题选项用与正确值相同单位；不能为匹配答案随意增大容差。
区间式、升降+程度式选项不写options，改写ranges（A—D各一个[下界,上界]，左闭右开，null为无界）；
图表匹配题写correct=1、options正确项1错项0，另加target（正确图各点算式数组）。"""

def key() -> str:
    try:
        return model_router.resolve_api_key()
    except RuntimeError:
        pass
    if os.environ.get("CLIPROXY_API_KEY"):
        return os.environ["CLIPROXY_API_KEY"]
    for line in (Path.home() / ".hermes" / ".env").read_text().splitlines():
        if line.startswith("CLIPROXY_API_KEY="): return line.split("=", 1)[1].strip()
    raise RuntimeError("模型 API key not found（检查 ~/.hermes/.env）")

def call(prompt: str, max_tokens: int = 12000, role: str | None = None) -> dict:
    last = None
    for attempt in range(2):
        body = json.dumps({"model": MODEL, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "temperature": 0.55 if attempt == 0 else 0.2,
            "messages": [{"role": "user", "content": prompt + ("\n只输出完整可解析JSON对象，不要Markdown或解释。" if attempt else "")}]}
        ).encode()
        req = urllib.request.Request(BASE + "/chat/completions", body, headers={"Content-Type":"application/json", "Authorization":"Bearer "+key()})
        model_router.log_call(role or "writer")
        with urllib.request.urlopen(req, timeout=900) as res: text = json.loads(res.read())["choices"][0]["message"]["content"]
        try: return json.loads(text[text.find("{"):text.rfind("}")+1])
        except json.JSONDecodeError as exc: last = exc
    raise last






def figure_kind(item: dict) -> str:
    return str(item.get("figure_kind") or {"chart": "bars", "table": "table", "text": "none"}.get(str(item.get("format")), "none"))




def render_material(material: dict, image_dir: Path) -> None:
    figure = material.pop("figure", None) or {}; kind = str(figure.get("kind") or "none")
    if kind == "none": return
    mid = material["external_id"].rsplit("-", 1)[-1].lower(); path = image_dir / f"{mid}-{kind}.png"
    if kind == "table":
        cmd = ["python3","scripts/render_ziliao_figure.py","table","--title",str(figure.get("title") or ""),"--unit",str(figure.get("unit") or ""),"--headers",",".join(map(str,figure.get("headers") or [])),"--rows"]
        cmd += [",".join(map(str,row)) for row in (figure.get("rows") or [])]
    elif kind in ("bars", "line"):
        cmd = ["python3","scripts/render_ziliao_figure.py",kind,"--title",str(figure.get("title") or ""),"--ylabel",str(figure.get("unit") or ""),"--categories",",".join(map(str,figure.get("categories") or [])),"--series"]
        cmd += [f"{series.get('name','系列')}:{','.join(map(str,series.get('values') or []))}" for series in (figure.get("series") or [])]
    elif kind == "pie":
        values = ((figure.get("series") or [{}])[0].get("values") or [])
        cmd = ["python3","scripts/render_ziliao_figure.py","pie","--title",str(figure.get("title") or ""),"--unit",str(figure.get("unit") or ""),"--slices"]
        cmd += [f"{name},{value}" for name, value in zip(figure.get("categories") or [], values)]
    else: raise ValueError(f"unsupported figure kind: {kind}")
    subprocess.run(cmd + ["--out",str(path)], cwd=ROOT, check=True); material["images"] = [f"images/{path.name}"]; material["figure"] = figure

def valid_material(result: dict) -> bool:
    material = result.get("material") or {}
    figure = material.get("figure") or {}
    kind = str(figure.get("kind") or "none")
    if kind == "none": return bool(material.get("content"))
    if kind == "table":
        rows = figure.get("rows") or []
        return len(figure.get("headers") or []) >= 4 and len(rows) >= 6 and all(len(row) == len(figure["headers"]) for row in rows)
    if kind in ("bars", "line", "pie"):
        categories = figure.get("categories") or []
        series = figure.get("series") or []
        size_ok = {"bars": 4 <= len(categories) <= 8 and 1 <= len(series) <= 8,
                   "line": 5 <= len(categories) <= 8 and 1 <= len(series) <= 3,
                   "pie": 3 <= len(categories) <= 6 and len(series) == 1}[kind]
        return (size_ok and bool(categories)
                and all(len(item.get("values") or []) == len(categories)
                        and all(type(value) in (int, float) and math.isfinite(value) for value in item["values"])
                        and (kind != "pie" or all(value > 0 for value in item["values"]))
                        for item in series))
    return False


def render_option_figure(figure: dict, path: Path) -> None:
    """图表匹配的选项图：不标数值，按真题惯例只凭形状判断。"""
    kind = str(figure.get("kind") or "")
    categories = [str(c) for c in figure.get("categories") or []]
    values = [float(v) for v in figure.get("values") or []]
    if kind == "pie":
        cmd = ["python3", "scripts/render_ziliao_figure.py", "pie", "--no-values", "--slices",
               *[f"{name},{value}" for name, value in zip(categories, values)]]
    elif kind in ("line", "bars"):
        cmd = ["python3", "scripts/render_ziliao_figure.py", kind, "--no-values", "--compact",
               "--categories", ",".join(categories), "--series", "数值:" + ",".join(f"{v:g}" for v in values)]
    else:
        raise ValueError(f"unsupported option figure kind: {kind}")
    subprocess.run(cmd + ["--out", str(path)], cwd=ROOT, check=True)



def question_errors(question: dict, calculation: dict, material: dict, plan: dict,
                    expected_id: str, slot: dict, sibling_questions: list[dict]) -> list[str]:
    errors = []
    if question.get("external_id") != expected_id:
        errors.append(f"题号必须为 {expected_id}")
    if question.get("material_id") != material.get("external_id"):
        errors.append("material_id 必须指向冻结材料")
    try:
        validate_ai_primary_tag((question.get("tags") or [""])[0], "资料分析")
    except (ValueError, IndexError):
        errors.append("tags[0] 必须是有效的资料分析主标签")
    if slot.get("tag") and (question.get("tags") or [""])[0] != slot["tag"]:
        errors.append(f"必须命中指定知识点 {slot['tag']}")
    options = question.get("options") or []
    if len(options) != 4 or {str(o.get("key")) for o in options} != {"A", "B", "C", "D"}:
        errors.append("必须恰有A-D四个选项")
    elif len({str(o.get("text") or "") or json.dumps(o.get("figure") or {}, sort_keys=True) for o in options}) != 4:
        errors.append("四个选项必须存在且互不重复")
    if str(question.get("answer") or "") not in {"A", "B", "C", "D"}:
        errors.append("answer必须是A-D之一")
    signature = re.sub(r"\d+(?:\.\d+)?", "<n>", str(question.get("stem") or ""))
    for sibling in sibling_questions:
        other = re.sub(r"\d+(?:\.\d+)?", "<n>", str(sibling.get("stem") or ""))
        if signature and signature == other:
            errors.append("题干结构与本篇其他题重复")
            break
    if slot.get("kind") == KIND_CHART_MATCH:
        errors.extend(chart_match_issues(question, calculation))
    elif uses_ranges(slot):
        try:
            target = float(safe_eval(calculation.get("correct")))
            errors.extend(range_calculation_issues(target, calculation.get("ranges"), str(question.get("answer") or ""),
                                                   {str(o.get("key")) for o in options}))
        except Exception as exc:
            errors.append(f"计算式不可复算：{exc}")
    elif not skip_calculation(slot):
        try:
            target = safe_eval(calculation.get("correct"))
            values = {str(k): safe_eval(v) for k, v in (calculation.get("options") or {}).items()}
            matches = [k for k, value in values.items() if equivalent(value, target, float(calculation.get("tolerance", 0.001)))]
            if matches != [str(question.get("answer") or "")]:
                errors.append(f"计算验算匹配 {matches}，但答案是 {question.get('answer')}")
        except Exception as exc:
            errors.append(f"计算式不可复算：{exc}")
    missing = explanation_missing_years({**question, "family": slot.get("family"), "brief": slot.get("brief")})
    if missing:
        errors.append(f"比较类解析漏年：{','.join(missing)}")
    expected_stem = str(slot.get("judge_stem") or "")
    expected_form = str(slot.get("judge_form") or "")
    stem = str(question.get("stem") or "")
    if expected_stem and expected_stem not in stem:
        errors.append(f"综合判断题干必须包含「{expected_stem}」")
    if expected_form and classify_judge_form(stem) != expected_form:
        errors.append(f"综合判断形式须为{expected_form}，实际{classify_judge_form(stem) or '未识别'}")
    errors.extend(question_style_issues({**question, "family": question.get("family") or slot.get("family")}, calculation, slot))
    return errors


















_active_job = None

def main(argv=None) -> int:
    raise SystemExit("老的资料分析并行流水线已下线：单篇/指定考点专项用 scripts/ziliao_material_pipeline.py，"
                     "20题整套用 scripts/ziliao_agent_paper.py。")


if __name__ == "__main__": raise SystemExit(main())

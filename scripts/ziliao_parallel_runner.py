#!/usr/bin/env python3
"""Gemini data-analysis paper: framework -> materials -> independent questions."""
from __future__ import annotations

import argparse, concurrent.futures, datetime as dt, json, math, os, re, shutil, sqlite3, subprocess, time, urllib.request, uuid
from pathlib import Path
from collections import Counter
from quiz_generator import resolve_slots, run_canon_card
from kaodian_taxonomy import validate_ai_primary_tag
from scheduler_common import DB
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
    CHART_MATCH_HOOK,
    ZILIAO_INFERENCE_RULES,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL = resolve_gemini_model()
BASE = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
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
系统另有不看验算清单的盲解核验。数值题选项用与正确值相同单位；不能为匹配答案随意增大容差。"""

def key() -> str:
    if os.environ.get("CLIPROXY_API_KEY"):
        return os.environ["CLIPROXY_API_KEY"]
    for line in (Path.home() / ".hermes" / ".env").read_text().splitlines():
        if line.startswith("CLIPROXY_API_KEY="): return line.split("=", 1)[1].strip()
    raise RuntimeError("CLIPROXY_API_KEY not found")

def call(prompt: str, max_tokens: int = 12000) -> dict:
    last = None
    for attempt in range(2):
        body = json.dumps({"model": MODEL, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "temperature": 0.55 if attempt == 0 else 0.2,
            "messages": [{"role": "user", "content": prompt + ("\n只输出完整可解析JSON对象，不要Markdown或解释。" if attempt else "")}]}
        ).encode()
        req = urllib.request.Request(BASE + "/chat/completions", body, headers={"Content-Type":"application/json", "Authorization":"Bearer "+key()})
        with urllib.request.urlopen(req, timeout=900) as res: text = json.loads(res.read())["choices"][0]["message"]["content"]
        try: return json.loads(text[text.find("{"):text.rfind("}")+1])
        except json.JSONDecodeError as exc: last = exc
    raise last

def framework_prompt(difficulty="mid", formats=None, slots=None, track=TRACK_GD) -> str:
    formats = formats or default_formats(track, 4, False)
    return f"""你是公考资料分析命题总设计师。设计{len(formats)}篇材料的命题框架，不写题目。
产品轨：{"粤考日练（轨A）" if track == TRACK_GD else "经典计算加练（轨B）"}。{track_framework_rules(track)}
输出JSON：{{"difficulty":"{difficulty}","materials":[{{"id":"M01","theme":"...","format":"text/table/chart","focus":"...","question_plan":"...","chart_tasks":[]}}]}}
材料编号严格依次M01、M02等；形态按此顺序：{json.dumps(formats)}。chart只用bars，table只用table，text只用none；禁止mixed。柱图4—8分类，表格至少6行4列。
各篇主题和信息组织应不同。图表必须承担找数、筛选、求和、趋势或表文结合任务，不能只是装饰。
题目槽位：{json.dumps(slots or [], ensure_ascii=False)}。材料须提供槽位考法所需数据与口径；不得更换考法，不得把细节/综合槽改成混合或拉动。
按槽位 difficulty_score 拉开梯度（1秒杀找数 / 2一步 / 3两步 / 4四陈述综合），禁止规划成全员3。比较类须预留可枚举的完整年份点。"""

def material_prompt(frame: dict, item: dict, batch_id: str) -> str:
    track = frame.get("track") or TRACK_GD
    return f"""你是独立的资料分析材料设计模型，只负责{item['id']}，不出题。
产品轨：{"粤考日练" if track == TRACK_GD else "经典计算加练"}。{track_material_rules(track, item)}
本批难度 {frame.get('difficulty', 'mid')}。方向与已确认考点：{json.dumps(item, ensure_ascii=False)}。生成一篇数据足够、篇幅适当的原创统计材料。
{ZILIAO_INFERENCE_RULES}
材料自洽，所有题目所需数字必须来自正文或结构化图表。使用G省、H省或全国，不用“某省”。
先确定独立的底层数，再计算总量、合计、占比和总增速，禁止独立随机编造互相约束的统计数。
分项穷尽时，现期之和、各自反推的基期之和都必须与总量一致；部分列示须说明范围。
不要添加不必要的总增速；已给总增速必须与分项加权关系一致。图表长分类名用清楚简称，并在正文释义。
    format为chart时只能返回bars figure，format为table时只能返回table figure，format为text时kind必须为none，绝不返回mixed。bars的categories为4-10个且每个series.values等长非空数字数组；table至少6行、至少4列。图表数字、标题、单位、分类完整；不要双轴。图表要保留足够无关项，让题目能考察定位、筛选和排除，而不是只读一个数字。
严格输出JSON：{{"material":{{"external_id":"{batch_id}-{item['id']}","content":"...","figure":{{"kind":"none或table或bars","title":"...","unit":"...","headers":[],"rows":[],"categories":[],"series":[]}}}}}}。"""

def question_prompt(material: dict, plan: dict, index: int, batch_id: str, slot=None) -> str:
    slot = slot or {}
    track = plan.get("track") or TRACK_GD
    q5 = index == 5 and (slot.get("family") == "judge" or (track == TRACK_GD and not slot.get("tag")))
    level = slot.get("difficulty_score") or {"easy": 2, "mid": 3, "hard": 4}[slot.get("difficulty") or plan.get("difficulty", "mid")]
    form = slot.get("judge_stem") or {
        "M01": "根据资料，以下说法可以判断属实的是",
        "M02": "不能从上述资料中推出的是",
        "M03": "根据资料，下列说法正确的有",
        "M04": "能够从上述资料中推出的是",
    }.get(str(plan.get("id")), "根据资料，以下说法可以判断属实的是")
    tasks = plan.get("chart_tasks") or []
    task = tasks[(index - 1) % len(tasks)] if tasks else "根据材料完成不同于其他题的信息定位或计算"
    calc_rule = '计算清单可写 correct=1、正确项1、错项0' if skip_calculation(slot) else '计算选项必须唯一匹配answer，correct只含数字和+-*/括号'
    return f"""你是独立命题模型，只根据下面冻结材料设计第{index}题，不修改材料、数字、图表或口径。
产品轨：{"粤考日练" if track == TRACK_GD else "经典计算加练"}。{track_question_rules(track, slot, index)}
{ZILIAO_INFERENCE_RULES}
本题难度分 {level}（1秒杀找数 / 2一步 / 3两步 / 4四陈述综合）。材料方向：{json.dumps(plan, ensure_ascii=False)}
指定槽位（family、主标签、brief 必须遵守）：{json.dumps(slot, ensure_ascii=False)}。
材料：{material['content']}
图表数据：{json.dumps(material.get('figure') or {}, ensure_ascii=False)}
本题指定考法：{task}。如果材料带图，本题必须真正使用图表中的数据；图表题不得只复述正文中已直接给出的同一句数字。
第{index}题必须{'是综合正误题，题干必须以“'+form+'”开头，不得改成「下列说法正确/有误的是」，四选项各一句陈述' if q5 or slot.get('family')=='judge' else '围绕材料真实数据设计单选题'}。
解析写清取数与算式；比较类必须枚举题干年份范围内每一年。不要用「最后明确选择X项」套话收尾。
{CALCULATION_RULE}
严格输出JSON：{{"question":{{"external_id":"{batch_id}-{material['external_id'].rsplit('-',1)[-1]}-Q{index}","category":"资料分析","question_type":"single","material_id":"{material['external_id']}","stem":"...","options":[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}],"answer":"A","explanation":"...","tags":["白名单标签"],"difficulty":{level},"family":"{slot.get('family') or ''}"}},"calculation":{{"question_id":"...","correct":"算式或1","options":{{"A":0,"B":0,"C":0,"D":0}},"tolerance":0.001}}}}
tags只能从以下白名单选：{json.dumps(TAGS, ensure_ascii=False)}。{calc_rule}；解析、答案、计算清单一致；保留Gemini原始A-D顺序，不要改排。"""

def paper_prompt(material: dict, plan: dict, batch_id: str) -> str:
    slots = plan.get("slots") or []
    track = plan.get("track") or TRACK_GD
    slot_rules = "\n".join(
        f"Q{index} family={slot.get('family')} score={slot.get('difficulty_score')}：{track_question_rules(track, slot, index)}"
        for index, slot in enumerate(slots, 1)
    )
    judge = next((slot for slot in reversed(slots) if slot.get("family") == "judge"), {})
    judge_stem = str(judge.get("judge_stem") or "")
    mix_rule = (
        "严格按槽位 family 出题：细节定位/排除、现期比重或简单加减、增长率/增长量、基期或两期比重、平均/比较、综合正误。"
        + (f"第5题题干必须以「{judge_stem}」开头，禁止改成「下列说法正确的是」或「下列说法有误的是」。" if judge_stem else "第5题必须是综合正误，并使用槽位指定问法。")
        + "四陈述埋时间偷换、累计vs当年、未给出不能比、范围扩大。"
        "不要把本篇改成教材 10 类套餐，混合或拉动仅当槽位 family=mix_pull 时才出。"
        if track == TRACK_GD else
        "可按经典计算技法覆盖本篇槽位，允许混合/拉动/比重差；第5题可以是综合判断或承重计算。"
    )
    return f"""你是独立的资料分析篇命题 Agent，只负责 {plan.get('id')} 这一篇和它的5道题。
产品轨：{"粤考日练" if track == TRACK_GD else "经典计算加练"}。{mix_rule}
{ZILIAO_INFERENCE_RULES}
你看不到其他材料，也不得生成其他篇。材料和图表已经冻结，不能修改任何数字、单位、分类、口径或正文。
材料：{material['content']}
图表数据：{json.dumps(material.get('figure') or {}, ensure_ascii=False)}
本篇五题槽位：{json.dumps(slots, ensure_ascii=False)}
{slot_rules}
先输出 blueprint，列出每题考点、数据引用、计算链和错误路径，再输出 questions、calculations。
五题各自主要考一个槽位，不得重复同一未知量或直接泄露另一题答案。细节/综合题计算清单可写 correct=1。
{CALCULATION_RULE}
每个选项都要有可解释的错误路径。图表篇必须真正使用图表数据。比较类解析必须枚举题干年份范围内全部点。
槽位difficulty_score仅作设计参考；difficulty须按实际定位/计算/判断步骤评定，后续由独立考官复核。不要用「最后明确选择X项」套话。
严格输出JSON：{{"blueprint":[{{"index":1,"tag":"白名单标签","family":"detail","skill":"...","calculation_plan":"...","trap":"..."}}],"questions":[{{"external_id":"{batch_id}-{plan.get('id')}-Q1","category":"资料分析","question_type":"single","material_id":"{material['external_id']}","stem":"...","options":[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}],"answer":"A","explanation":"...","tags":["白名单标签"],"difficulty":1,"family":"detail"}}],"calculations":[{{"question_id":"{batch_id}-{plan.get('id')}-Q1","correct":"算式或1","options":{{"A":1,"B":0,"C":0,"D":0}},"tolerance":0.001}}]}}
questions和calculations必须各恰好5个，external_id按Q1-Q5连续。tags只能从以下白名单选择：{json.dumps(TAGS, ensure_ascii=False)}。不要输出Markdown。"""

def question_repair_prompt(material: dict, plan: dict, question: dict, calculation: dict, error: str, siblings: list[dict] | None = None) -> str:
    raw_id = str(question.get("external_id") or "")
    index = raw_id.rsplit("-Q", 1)[-1]
    slots = plan.get("slots") or []
    slot = slots[int(index) - 1] if index.isdigit() and 0 < int(index) <= len(slots) else {}
    return f"""只修复冻结材料中的第{index}题。不要改材料、不要改其他题、不要改变题号。
材料：{material['content']}
图表数据：{json.dumps(material.get('figure') or {}, ensure_ascii=False)}
本题槽位：{json.dumps(slot, ensure_ascii=False)}
本篇其他题（不可修改，避免重复求同一结果或泄露答案）：{json.dumps(siblings or [], ensure_ascii=False)}
原题：{json.dumps(question, ensure_ascii=False)}
原验算：{json.dumps(calculation, ensure_ascii=False)}
校验失败：{error}
{CALCULATION_RULE}
{ZILIAO_INFERENCE_RULES}
如果只错解析或难度，保留题干、选项、答案，仅修正错误解析或评级；材料缺数据时重设本题，不得编造材料。
解析所有等式、比例方向、排除项字母均须与最终选项一致；不要添加无必要的第二种解法。
重新设计时必须唯一答案、真正命中槽位。只输出{{"question":{{...}},"calculation":{{...}}}}。"""

def render_material(material: dict, image_dir: Path) -> None:
    figure = material.pop("figure", None) or {}; kind = str(figure.get("kind") or "none")
    if kind == "none": return
    mid = material["external_id"].rsplit("-", 1)[-1].lower(); path = image_dir / f"{mid}-{kind}.png"
    if kind == "table":
        cmd = ["python3","scripts/render_ziliao_figure.py","table","--title",str(figure.get("title") or ""),"--unit",str(figure.get("unit") or ""),"--headers",",".join(map(str,figure.get("headers") or [])),"--rows"]
        cmd += [",".join(map(str,row)) for row in (figure.get("rows") or [])]
    elif kind == "bars":
        cmd = ["python3","scripts/render_ziliao_figure.py","bars","--title",str(figure.get("title") or ""),"--ylabel",str(figure.get("unit") or ""),"--categories",",".join(map(str,figure.get("categories") or [])),"--series"]
        cmd += [f"{series.get('name','系列')}:{','.join(map(str,series.get('values') or []))}" for series in (figure.get("series") or [])]
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
    if kind == "bars":
        categories = figure.get("categories") or []
        series = figure.get("series") or []
        return (4 <= len(categories) <= 8 and 1 <= len(series) <= 8 and bool(categories)
                and all(len(item.get("values") or []) == len(categories)
                        and all(type(value) in (int, float) and math.isfinite(value) for value in item["values"])
                        for item in series))
    return False

def material_passes_realism(result: dict, item: dict, track: str = TRACK_GD) -> bool:
    material = result.get("material") or {}
    long_text = track == TRACK_GD and str(item.get("id") or "") == "M01" and str(item.get("format") or "") == "text"
    return not material_realism_errors(material, track=track, long_text=long_text)

def auto_slots(count: int, materials: int, difficulty: str, track: str = TRACK_GD) -> list[dict]:
    """Default slots: 轨A 粤向配额，轨B 经典 10 类轮转。"""
    return resolve_track_slots(track, count, materials, difficulty)

def valid_paper(result: dict, material: dict, plan: dict, batch_id: str) -> bool:
    questions = result.get("questions") or []
    calculations = result.get("calculations") or []
    if len(questions) != plan.get("count") or len(calculations) != plan.get("count"):
        return False
    return all(isinstance(question, dict) for question in questions)

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
    elif len({str(o.get("text") or "") for o in options}) != 4:
        errors.append("四个选项必须存在且互不重复")
    if str(question.get("answer") or "") not in {"A", "B", "C", "D"}:
        errors.append("answer必须是A-D之一")
    signature = re.sub(r"\d+(?:\.\d+)?", "<n>", str(question.get("stem") or ""))
    for sibling in sibling_questions:
        other = re.sub(r"\d+(?:\.\d+)?", "<n>", str(sibling.get("stem") or ""))
        if signature and signature == other:
            errors.append("题干结构与本篇其他题重复")
            break
    if not skip_calculation(slot):
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
    return errors

def paper_call(material: dict, plan: dict, batch_id: str) -> dict:
    prompt = paper_prompt(material, plan, batch_id)
    for attempt in range(3):
        result = call(prompt + (f"\n这是第{attempt + 1}次修复：输出必须恰好{plan.get('count')}道题。" if attempt else ""), 12000)
        if valid_paper(result, material, plan, batch_id):
            return result
    raise ValueError(f"篇级题目生成失败：{plan.get('id')}")

def generate_paper_questions(material: dict, plan: dict, batch_id: str) -> tuple[list[dict], list[dict]]:
    result = paper_call(material, plan, batch_id)
    questions = list(result["questions"])
    calculations = list(result["calculations"])
    calc_by_id = {str(c.get("question_id")): c for c in calculations if isinstance(c, dict)}
    for index, question in enumerate(questions, 1):
        qid = f"{batch_id}-{plan['id']}-Q{index}"
        calculation = calc_by_id.get(qid, {})
        slots = plan.get("slots") or []
        slot = slots[index - 1] if index <= len(slots) else {}
        siblings = questions[:index - 1] + questions[index:]
        errors = question_errors(question, calculation, material, plan, qid, slot, siblings)
        for attempt in range(2):
            if not errors:
                break
            repaired = call(question_repair_prompt(material, plan, question, calculation, "；".join(errors), siblings), 6000)
            question = repaired.get("question") or question
            calculation = repaired.get("calculation") or calculation
            questions[index - 1] = question
            calc_by_id[qid] = calculation
            errors = question_errors(question, calculation, material, plan, qid, slot, siblings)
        if errors:
            raise ValueError(f"{qid} 题级修复失败：{'；'.join(errors)}；验算={json.dumps(calculation, ensure_ascii=False)}")
    return questions, [calc_by_id[f"{batch_id}-{plan['id']}-Q{i}"] for i in range(1, len(questions) + 1)]


def generate_material_questions(material: dict, plan: dict, batch_id: str) -> tuple[list[dict], list[dict]]:
    if plan.get("count") == 5:
        return generate_paper_questions(material, plan, batch_id)
    jobs = [(material, plan, index) for index in range(1, plan["count"] + 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        results = list(pool.map(
            lambda job: call(
                question_prompt(job[0], job[1], job[2], batch_id,
                                job[1]["slots"][job[2] - 1] if job[1].get("slots") else None),
                6000,
            ),
            jobs,
        ))
    return [result["question"] for result in results], [result["calculation"] for result in results]


def failed_visual_material_ids(batch_dir: Path) -> set[str]:
    evidence_path = batch_dir / "evidence" / "ziliao-visual-quality.json"
    if not evidence_path.is_file():
        return set()
    try:
        evidence = json.loads(evidence_path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    result = set()
    for item in evidence.get("images") or []:
        if str(item.get("verdict") or "").upper() == "PASS":
            continue
        stem = Path(str(item.get("path") or "")).stem
        material_id = stem.rsplit("-", 1)[0].upper()
        if re.fullmatch(r"M\d{2}", material_id):
            result.add(material_id)
    return result


def retry_visual_materials(batch_dir: Path, frame: dict, plans: list[dict],
                           target_ids: set[str], batch_id: str) -> bool:
    if not target_ids:
        return False
    materials_path = batch_dir / "materials.json"
    questions_path = batch_dir / "questions.json"
    calculations_path = batch_dir / "calculations.json"
    materials = json.loads(materials_path.read_text())
    questions = json.loads(questions_path.read_text())
    raw_calculations = json.loads(calculations_path.read_text())
    calculations = raw_calculations.get("questions") if isinstance(raw_calculations, dict) else raw_calculations
    calculations = calculations if isinstance(calculations, list) else []
    material_by_id = {str(item.get("external_id")): item for item in materials}
    plan_by_id = {str(plan.get("id")): plan for plan in plans}
    question_by_id = {str(item.get("external_id")): item for item in questions}
    calculation_by_id = {str(item.get("question_id")): item for item in calculations}
    image_dir = batch_dir / "images"
    changed = False
    for short_id in sorted(target_ids):
        plan = plan_by_id.get(short_id)
        if not plan:
            continue
        new_result = material_call(frame, plan, batch_id, batch_dir)
        new_material = new_result["material"]
        render_material(new_material, image_dir)
        old_material = next((item for item in materials if str(item.get("external_id", "")).endswith(f"-{short_id}")), None)
        if old_material is None:
            continue
        material_index = materials.index(old_material)
        materials[material_index] = new_material
        new_questions, new_calculations = generate_material_questions(new_material, plan, batch_id)
        for index, question in enumerate(new_questions, 1):
            slot = (plan.get("slots") or [])[index - 1] if index <= len(plan.get("slots") or []) else {}
            question["category"] = "资料分析"
            apply_slot_difficulty(question, slot, slot.get("difficulty") or plan.get("difficulty") or "mid")
            question_by_id[str(question.get("external_id"))] = question
        for calculation in new_calculations:
            calculation_by_id[str(calculation.get("question_id"))] = calculation
        changed = True
    if not changed:
        return False
    for index, question in enumerate(questions):
        replacement = question_by_id.get(str(question.get("external_id")))
        if replacement is not None:
            questions[index] = replacement
    materials_path.write_text(json.dumps(materials, ensure_ascii=False, indent=2))
    questions_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2))
    calculations_path.write_text(json.dumps({"questions": list(calculation_by_id.values())}, ensure_ascii=False, indent=2))
    return True

def gate_repair_targets(batch_dir: Path) -> dict[str, str]:
    evidence_path = batch_dir / "evidence" / "system-quality.json"
    if not evidence_path.is_file():
        return {}
    try:
        evidence = json.loads(evidence_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    targets = {}
    for item in evidence.get("results") or []:
        if str(item.get("verdict") or "").upper() == "PASS":
            continue
        if all((item.get(key) or {}).get("verdict") == "PASS" for key in ("correctness", "quality")):
            continue
        qid = str(item.get("question_id") or "")
        if not qid:
            continue
        issues = []
        for key in ("correctness", "quality"):
            section = item.get(key) or {}
            issues.extend(str(value) for value in section.get("issues") or [])
            review = section.get("review") or {}
            issues.extend(str(value) for value in review.get("issues") or [])
        targets[qid] = "；".join(issues) or "质量门拒绝该题"
    batch = evidence.get("batch_quality", {}).get("review", {})
    for group in batch.get("duplicate_groups") or []:
        for qid in list(group)[1:]:
            targets.setdefault(str(qid), "与同篇其他题重复或泄题")
    return targets

def repair_gate_questions(batch_dir: Path, materials: list[dict], plans: list[dict],
                          questions: list[dict], calculations: list[dict], batch_id: str) -> bool:
    targets = gate_repair_targets(batch_dir)
    if not targets:
        return False
    material_by_id = {str(material.get("external_id")): material for material in materials}
    plan_by_id = {str(plan.get("id")): plan for plan in plans}
    calc_by_id = {str(item.get("question_id")): item for item in calculations}
    changed = False
    for qid, error in targets.items():
        question = next((item for item in questions if str(item.get("external_id")) == qid), None)
        if not question:
            continue
        material = material_by_id.get(str(question.get("material_id")))
        plan_id = str(question.get("material_id") or "").rsplit("-", 1)[-1]
        plan = plan_by_id.get(plan_id)
        calculation = calc_by_id.get(qid, {})
        if not material or not plan:
            continue
        position = questions.index(question)
        candidate_question, candidate_calculation = question, calculation
        for attempt in range(2):
            repaired = call(question_repair_prompt(
                material, plan, candidate_question, candidate_calculation,
                error + ("；上一次回炉仍未通过本地计算校验，请重新核对答案字母与 options 数值" if attempt else ""),
                [q for q in questions if q.get("material_id") == material["external_id"] and q is not question],
            ), 6000)
            next_question = repaired.get("question")
            next_calculation = repaired.get("calculation")
            if not isinstance(next_question, dict) or not isinstance(next_calculation, dict):
                continue
            next_question["external_id"] = qid
            next_question["material_id"] = material["external_id"]
            next_calculation["question_id"] = qid
            slot = (plan.get("slots") or [])[int(qid.rsplit("-Q", 1)[-1]) - 1]
            apply_slot_difficulty(next_question, slot, plan.get("difficulty") or "mid")
            errors = question_errors(
                next_question, next_calculation, material, plan, qid, slot,
                questions[:position] + questions[position + 1:],
            )
            if not errors:
                candidate_question, candidate_calculation = next_question, next_calculation
                break
            candidate_question, candidate_calculation = next_question, next_calculation
        else:
            continue
        questions[position] = candidate_question
        candidate_question["analysis"] = candidate_question.get("explanation") or ""
        calc_by_id[qid] = candidate_calculation
        changed = True
    if changed:
        (batch_dir / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2))
        (batch_dir / "calculations.json").write_text(json.dumps({"questions": list(calc_by_id.values())}, ensure_ascii=False, indent=2))
    return changed

def failed_data_material_ids(batch_dir: Path) -> set[str]:
    path = batch_dir / "evidence" / "system-quality.json"
    if not path.is_file():
        return set()
    return {
        item["question_id"].rsplit("-", 2)[-2]
        for item in json.loads(path.read_text()).get("results") or []
        if ((item.get("quality") or {}).get("review") or {}).get("material_consistent") is False
    }


def material_call(frame: dict, item: dict, batch_id: str, batch_dir: Path | None = None) -> dict:
    prompt = material_prompt(frame, item, batch_id)
    track = frame.get("track") or TRACK_GD
    required_kind = {"chart": "bars", "table": "table", "text": "none"}[str(item.get("format") or "text")]
    repair = f"\n这是第{{attempt}}次修复。format={item.get('format')}，figure.kind必须严格等于 {required_kind}。只输出完整JSON；不要把图表改成文字，不要输出mixed。数字禁止整万配整十人均，图序列禁止等差或等差增量。"
    feedback = ""
    attempts = []
    for attempt in range(5):
        result = call(prompt + (repair.format(attempt=attempt + 1) + feedback if attempt else ""), 9000)
        result["track"] = track
        if valid_material(result):
            kind = str((result["material"].get("figure") or {}).get("kind") or "none")
            if ((item.get("format") == "chart" and kind == "bars")
                    or (item.get("format") == "table" and kind == "table")
                    or (item.get("format") == "text" and kind == "none")):
                if material_passes_realism(result, item, track):
                    review = review_ziliao_material(result["material"])
                    attempts.append({"material": result["material"], "review": review})
                    if batch_dir is not None:
                        evidence = batch_dir / "evidence"
                        evidence.mkdir(exist_ok=True)
                        (evidence / f"{item['id'].lower()}-material.json").write_text(json.dumps(
                            {"model": MODEL, "attempts": attempts}, ensure_ascii=False, indent=2))
                    if review.get("verdict") == "PASS" and review.get("issues") == []:
                        return result
                    feedback = "\n独立材料核查未通过：" + json.dumps(review, ensure_ascii=False)
    raise ValueError(f"invalid frozen material data: {item.get('id')} {feedback}")

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="资料分析：冻结材料、程序渲染、独立出题、现有质检入库")
    parser.add_argument("--tag")
    parser.add_argument("--blueprint")
    parser.add_argument("--count", type=int)
    parser.add_argument("--materials", type=int)
    parser.add_argument("--formats", help="按篇指定 text,table,chart；chart 为确定性柱图")
    parser.add_argument("--track", choices=["gd", "classic"], default="gd",
                        help="gd=粤考日练（默认日练/广东省考）；classic=经典计算加练")
    parser.add_argument("--difficulty", choices=["easy", "mid", "hard"], default="mid")
    parser.add_argument("--batch-id")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "parallel-ziliao")
    parser.add_argument("--no-import", action="store_true")
    parser.add_argument("--plan-only", action="store_true", help="只输出轨/配额/标签/模型，不调用 Gemini")
    args = parser.parse_args(argv)
    os.environ["EXAM_DB"] = str(args.db)
    args.module = "资料分析"
    if args.tag and args.count is None:
        args.count = 5
    _, slots = resolve_slots(args) if args.tag or args.blueprint else (args.module, [])
    count = sum(s["count"] for s in slots) if slots else (args.count if args.count is not None else 20)
    n = args.materials if args.materials is not None else math.ceil(count / 5)
    if not 1 <= count <= 20 or not 1 <= n <= 4 or not n <= count <= n * 5:
        parser.error("题量须1–20，每篇1–5题，材料须1–4篇")
    targeted = bool(slots) or count != 20
    formats = args.formats.split(',') if args.formats else default_formats(args.track, n, targeted)
    if len(formats) != n or any(f not in {"text", "table", "chart"} for f in formats):
        parser.error("--formats 须与材料篇数一致，仅允许 text/table/chart")
    args.batch_id = args.batch_id or f"{dt.date.today():%Y%m%d}_hermes_ziliao_{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[\w-]{1,160}", args.batch_id):
        parser.error("batch-id 只能包含字母、数字、汉字、下划线和连字符")
    if not slots:
        slots = auto_slots(count, n, args.difficulty, args.track)
    if args.track == TRACK_GD and count == 20 and n == 4 and not targeted:
        validate_gd_quota(slots, count=count)
    args.total, args.slots, args.formats, args.targeted = count, slots, formats, targeted
    return args


def validate_frame(frame, args):
    items = frame.get("materials") or []
    if frame.get("difficulty") != args.difficulty or len(items) != len(args.formats):
        raise ValueError("材料框架数量或难度不匹配")
    if [item.get("id") for item in items] != [f"M{i+1:02d}" for i in range(len(items))]:
        raise ValueError("材料编号必须唯一且依次为 M01、M02 等")
    if [item.get("format") for item in items] != args.formats:
        raise ValueError("材料形态不符合请求")


def main(argv=None) -> int:
    args = parse_args(argv)
    os.environ["EXAM_DB"] = str(args.db)
    started = time.monotonic(); today = dt.date.today().isoformat(); batch_id = args.batch_id
    compact = today.replace("-", "")
    source = batch_source(args.track, args.targeted, args.difficulty, compact, args.slots)
    assert_source_label(args.track, source)
    if args.plan_only:
        plan = {
            "track": args.track,
            "track_label": "粤考日练" if args.track == TRACK_GD else "经典计算加练",
            "source": source,
            "model": MODEL,
            "count": args.total,
            "materials": len(args.formats),
            "formats": args.formats,
            "targeted_drill": args.targeted,
            "slots": args.slots,
            "chart_match": CHART_MATCH_HOOK,
            "gemini": "CLIPROXY_API_KEY + CLIPROXY_BASE_URL（只读环境变量，勿写入仓库）",
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        if conn.execute("SELECT 1 FROM questions WHERE batch_id=? LIMIT 1", (batch_id,)).fetchone():
            raise ValueError("batch-id 已入库，请换编号")
    finally:
        conn.close()
    out = args.output_dir/today/batch_id; out.mkdir(parents=True, exist_ok=False); marks = {"started_at":dt.datetime.now(dt.timezone.utc).isoformat()}
    run = {"module": "资料分析", "slots": args.slots}
    per_item = [dict(slot, definition=run_canon_card(run, slot["tag"])) for slot in args.slots for _ in range(slot["count"])]
    t=time.monotonic(); frame=call(framework_prompt(args.difficulty,args.formats,per_item,args.track),5000); marks["framework_seconds"]=round(time.monotonic()-t,2)
    validate_frame(frame,args)
    frame["track"] = args.track
    cursor = 0
    for i, item in enumerate(frame["materials"]):
        item["difficulty"] = args.difficulty
        item["track"] = args.track
        item["count"] = args.total // len(args.formats) + (i < args.total % len(args.formats))
        item["slots"] = per_item[cursor:cursor + item["count"]]
        cursor += item["count"]
    (out/"framework.json").write_text(json.dumps(frame, ensure_ascii=False, indent=2))
    t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: material_results=list(pool.map(lambda item:material_call(frame,item,batch_id,out),frame["materials"]))
    marks["materials_seconds_wall"]=round(time.monotonic()-t,2); materials=[r["material"] for r in material_results]; image_dir=out/"images"; image_dir.mkdir(exist_ok=True)
    for material, plan in zip(materials,frame["materials"]):
        if material.get("external_id") != f"{batch_id}-{plan['id']}":
            raise ValueError("材料 ID 与冻结框架不一致")
        render_material(material,image_dir)
    jobs=[(material,plan,index) for material,plan in zip(materials,frame["materials"]) for index in range(1,plan["count"]+1)]; t=time.monotonic()
    # Each material owns its own question context; retries use the same boundary.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(materials)) as pool:
        packed = list(pool.map(lambda pair: generate_material_questions(pair[0], pair[1], batch_id), zip(materials, frame["materials"])))
    questions = [question for pair in packed for question in pair[0]]
    calculations = [calculation for pair in packed for calculation in pair[1]]
    marks["questions_seconds_wall"] = round(time.monotonic() - t, 2)
    for position, (question, calculation, job) in enumerate(zip(questions, calculations, jobs)):
        material, plan, index = job
        qid = f"{batch_id}-{plan['id']}-Q{index}"
        if question.get("external_id") != qid or question.get("material_id") != material["external_id"] or calculation.get("question_id") != qid:
            raise ValueError("题目、验算与冻结材料关联不一致")
        tag = validate_ai_primary_tag((question.get("tags") or [""])[0], "资料分析")
        if per_item and tag != per_item[position]["tag"]:
            raise ValueError(f"{qid} 未命中指定考点")
        question["category"] = "资料分析"
        apply_slot_difficulty(question, per_item[position] if per_item else {}, args.difficulty)
        render_option_figures(question, image_dir)
    if args.track == TRACK_GD and not args.targeted:
        validate_difficulty_gradient(questions, track=TRACK_GD)
        validate_comparison_explanations(questions)
    constraints = {"all_original":True,"question_count":args.total,"difficulty_tier":args.difficulty,
                   "answer_distribution":"unconstrained","targeted_drill":args.targeted,
                   "slot_plan":args.slots,"track":args.track,
                   "track_label": "粤考日练" if args.track == TRACK_GD else "经典计算加练",
                   "chart_match": CHART_MATCH_HOOK}
    if args.targeted:
        constraints.update(answer_max_per_letter=args.total, answer_min_letters=1)
    if per_item: constraints["tag_counts"] = dict(Counter(s["tag"] for s in per_item))
    manifest={"batch_id":batch_id,"source":source,"region":"广东-模拟" if args.track == TRACK_GD else "经典计算-模拟","year":int(today[:4]),"license":"仅用于学习与题库内部评测","created_at":today,"kind":"ai-generated","difficulty_tier":args.difficulty,"generation":{"style_marker":"GONGKAO-STYLE-v2-split","model":MODEL,"batch_constraints":constraints,"kaofa_canon":run.get("kaofa_canon",{}),"evaluation_contexts":[]}}
    for name,data in [("framework.json",frame),("manifest.json",manifest),("materials.json",materials),("questions.json",questions),("calculations.json",{"questions":calculations})]: (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    env = {**os.environ, "EXAM_DB": str(args.db)}
    marks["question_count"] = len(questions)
    t = time.monotonic()
    gate = None
    retry_log = []
    for gate_attempt in range(1, GATE_ATTEMPTS + 1):
        # Retain each input/review so later repairs do not erase the failure evidence.
        snapshot = out / "gate-attempts" / str(gate_attempt)
        snapshot.mkdir(parents=True)
        for name in ("materials.json", "questions.json", "calculations.json", "manifest.json"):
            shutil.copy2(out / name, snapshot / name)
        for name in ("system-quality.json", "ziliao-visual-quality.json"):
            (out / "evidence" / name).unlink(missing_ok=True)
        gate = subprocess.run(["python3", "scripts/generation_gate.py", "issue", str(out)], cwd=ROOT, env=env, text=True, capture_output=True)
        for name in ("materials.json", "questions.json", "calculations.json", "manifest.json"):
            shutil.copy2(out / name, snapshot / name)
        shutil.copytree(out / "evidence", snapshot / "evidence", dirs_exist_ok=True)
        if gate.returncode == 0:
            break
        # The gate normalizes files before checking them; always use its latest files.
        materials = json.loads((out / "materials.json").read_text())
        questions = json.loads((out / "questions.json").read_text())
        calculation_payload = json.loads((out / "calculations.json").read_text())
        calculations = calculation_payload.get("questions", calculation_payload) if isinstance(calculation_payload, dict) else calculation_payload
        visual_ids = failed_visual_material_ids(out) | failed_data_material_ids(out)
        if visual_ids and gate_attempt < GATE_ATTEMPTS:
            retry_log.append({"attempt": gate_attempt, "kind": "material", "materials": sorted(visual_ids)})
            if retry_visual_materials(out, frame, frame["materials"], visual_ids, batch_id):
                continue
        if gate_attempt < GATE_ATTEMPTS:
            repaired = repair_gate_questions(out, materials, frame["materials"], questions, calculations, batch_id)
            if repaired:
                retry_log.append({"attempt": gate_attempt, "kind": "question-repair"})
                continue
        break
    marks["gate_seconds"] = round(time.monotonic() - t, 2)
    marks["gate_attempts"] = gate_attempt
    marks["gate_retries"] = retry_log
    if gate.returncode:
        marks["gate_error"]=(gate.stdout or gate.stderr)[-6000:]; marks["total_seconds"]=round(time.monotonic()-started,2); (out/"timing.json").write_text(json.dumps(marks,ensure_ascii=False,indent=2)); print(gate.stdout or gate.stderr); return gate.returncode
    if args.no_import:
        marks["total_seconds"] = round(time.monotonic() - started, 2)
        (out / "timing.json").write_text(json.dumps(marks, ensure_ascii=False, indent=2))
        print(json.dumps({"status":"success","batch_id":batch_id,"imported":0,"batch_dir":str(out),"message":"质检通过，未入库"},ensure_ascii=False))
        return 0
    t=time.monotonic(); imp=subprocess.run(["node","scripts/import-batch.mjs",str(out)],cwd=ROOT,env=env,text=True,capture_output=True); marks["import_seconds"]=round(time.monotonic()-t,2); marks["total_seconds"]=round(time.monotonic()-started,2); marks["import_output"]=imp.stdout[-3000:]; (out/"timing.json").write_text(json.dumps(marks,ensure_ascii=False,indent=2))
    print(json.dumps({"status":"success" if imp.returncode == 0 else "error","batch_id":batch_id,"batch_dir":str(out),"message":imp.stdout or imp.stderr},ensure_ascii=False))
    return imp.returncode

if __name__ == "__main__": raise SystemExit(main())

#!/usr/bin/env python3
"""Gemini data-analysis paper: framework -> materials -> independent questions."""
from __future__ import annotations

import concurrent.futures, datetime as dt, json, os, subprocess, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("DAILY_GEMINI_MODEL", "gemini-3.8-flash-high")
BASE = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
TAGS = [
    "资料分析-基础知识-统计术语与常考概念", "资料分析-ABRX类-基期量计算与比较",
    "资料分析-ABRX类-增长量计算与现期推算", "资料分析-ABRX类-增长率计算模型",
    "资料分析-比重类-现期、基期与隔级比重", "资料分析-比重类-比重趋势、比重差与比值差",
    "资料分析-平均类-一般平均值与年均增速/增量", "资料分析-比较类-双线法与增量比较",
    "资料分析-盐水类-十字交叉法与混合增长率", "资料分析-特殊考点-拉动增长、贡献率与容斥",
]

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
            "temperature": 0.55 if attempt == 0 else 0.2,
            "messages": [{"role": "user", "content": prompt + ("\n只输出完整可解析JSON对象，不要Markdown或解释。" if attempt else "")}]}
        ).encode()
        req = urllib.request.Request(BASE + "/chat/completions", body, headers={"Content-Type":"application/json", "Authorization":"Bearer "+key()})
        with urllib.request.urlopen(req, timeout=900) as res: text = json.loads(res.read())["choices"][0]["message"]["content"]
        try: return json.loads(text[text.find("{"):text.rfind("}")+1])
        except json.JSONDecodeError as exc: last = exc
    raise last

def framework_prompt() -> str:
    return """你是公考资料分析命题总设计师。只设计一套20题的命题框架，不写材料和题目。
输出JSON：{"difficulty":"hard","materials":[{"id":"M01","theme":"...","format":"text/table/chart","focus":"...","question_plan":"..."},...]}
硬性要求：四篇中恰好一篇format=chart且只能返回kind=bars，恰好一篇format=table且只能返回kind=table，另外两篇format=text；不得使用mixed。带图材料位置随机，chart至少4个分类，table至少6行4列。
必须四篇主题和信息组织明显不同；恰好两篇为table/chart，另外两篇为text，带图材料的位置随机。带图材料必须承担找数、筛选、求和、趋势或表文结合任务，不能只是装饰。每篇question_plan必须包含chart_tasks数组，从filtered_sum、multi_value_lookup、trend_compare、text_chart_join、share_change、direct_read中选择并说明题目如何使用。hard题方向允许隐含中间量、现期/基期转换、跨段或表文组合、接近选项和真实粗心陷阱。不要安排固定Q1-Q5顺序。"""

def material_prompt(frame: dict, item: dict, batch_id: str) -> str:
    return f"""你是独立的广东省考资料分析材料设计模型，只负责{item['id']}，不出题。
本批难度 hard。方向：{json.dumps(item, ensure_ascii=False)}。生成一篇约420-650字、4段左右的原创统计材料。
材料自洽，所有题目所需数字必须来自正文或结构化图表。使用G省、H省或全国，不用“某省”。
    format为chart时只能返回bars figure，format为table时只能返回table figure，format为text时kind必须为none，绝不返回mixed。bars的categories为4-10个且每个series.values等长非空数字数组；table至少6行、至少4列。图表数字、标题、单位、分类完整；不要双轴。图表要保留足够无关项，让题目能考察定位、筛选和排除，而不是只读一个数字。
严格输出JSON：{{"material":{{"external_id":"{batch_id}-{item['id']}","content":"...","figure":{{"kind":"none或table或bars","title":"...","unit":"...","headers":[],"rows":[],"categories":[],"series":[]}}}}}}。"""

def question_prompt(material: dict, plan: dict, index: int, batch_id: str) -> str:
    q5 = index == 5
    form = {"M01": "根据资料，以下说法可以判断属实的是", "M02": "不能从上述资料中推出的是", "M03": "下列说法正确的有", "M04": "能够从上述资料中推出的是"}.get(str(plan.get("id")), "能够从上述资料中推出的是")
    tasks = plan.get("chart_tasks") or []
    task = tasks[(index - 1) % len(tasks)] if tasks else "根据材料完成不同于其他题的信息定位或计算"
    return f"""你是独立命题模型，只根据下面冻结材料设计第{index}题，不修改材料、数字、图表或口径。
本批难度hard。材料方向：{json.dumps(plan, ensure_ascii=False)}
材料：{material['content']}
图表数据：{json.dumps(material.get('figure') or {}, ensure_ascii=False)}
本题指定考法：{task}。如果材料带图，本题必须真正使用图表中的数据；图表题不得只复述正文中已直接给出的同一句数字。
第{index}题必须{'是综合判断题，题干必须以“'+form+'”开头' if q5 else '围绕材料真实数据设计单选题'}。
hard题至少满足两个难度维度：先求隐含中间量再计算、跨段/表文组合、单位或口径转换、接近选项、半对判断；至少一个错误选项对应直接使用现成数据或只完成第一步的真实粗心路径。对于增速、比重变化、比重差题，优先设置两个“上升/增加”和两个“下降/减少”方向的选项，正负方向和数值都要接近；必须覆盖把“比重上升”误当“比重下降”、把百分比当百分点、把现期直接代入基期等真实错误。对于filtered_sum/multi_value_lookup，至少筛选6个数据项相加，并安排足够无关项，难点放在找数、排除和数字处理。不要用无意义长小数。
严格输出JSON：{{"question":{{"external_id":"{batch_id}-{material['external_id'].rsplit('-',1)[-1]}-Q{index}","category":"资料分析","question_type":"single","material_id":"{material['external_id']}","stem":"...","options":[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}],"answer":"A","explanation":"...最后明确选择X项","tags":["白名单标签"],"difficulty":4}},"calculation":{{"question_id":"...","correct":"只含数字和+-*/括号的算式","options":{{"A":0,"B":0,"C":0,"D":0}},"tolerance":0.001}}}}
tags只能从以下白名单选：{json.dumps(TAGS, ensure_ascii=False)}。计算选项必须唯一匹配answer；解析、答案、计算清单一致；保留Gemini原始A-D顺序，不要改排。"""

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
                and all(len(item.get("values") or []) == len(categories) for item in series))
    return False

def material_call(frame: dict, item: dict, batch_id: str) -> dict:
    prompt = material_prompt(frame, item, batch_id)
    required_kind = {"chart": "bars", "table": "table", "text": "none"}[str(item.get("format") or "text")]
    repair = f"\n这是第{{attempt}}次修复。format={item.get('format')}，figure.kind必须严格等于 {required_kind}。只输出完整JSON；不要把图表改成文字，不要输出mixed。"
    for attempt in range(5):
        result = call(prompt + (repair.format(attempt=attempt + 1) if attempt else ""), 9000)
        if valid_material(result):
            kind = str((result["material"].get("figure") or {}).get("kind") or "none")
            if ((item.get("format") == "chart" and kind == "bars")
                    or (item.get("format") == "table" and kind == "table")
                    or (item.get("format") == "text" and kind == "none")):
                return result
    raise ValueError(f"invalid frozen material data: {item.get('id')}")

def main() -> int:
    started = time.monotonic(); today = dt.date.today().isoformat(); batch_id = dt.date.today().strftime("%Y%m%d")+"_hermes_ziliao_hard_split_07"
    out = ROOT/"data"/"parallel-ziliao"/today/batch_id; out.mkdir(parents=True, exist_ok=True); marks = {"started_at":dt.datetime.now(dt.timezone.utc).isoformat()}
    t=time.monotonic(); frame=call(framework_prompt(),5000); marks["framework_seconds"]=round(time.monotonic()-t,2)
    if frame.get("difficulty")!="hard" or len(frame.get("materials",[]))!=4: raise ValueError("invalid framework")
    (out/"framework.json").write_text(json.dumps(frame, ensure_ascii=False, indent=2))
    t=time.monotonic()
    formats = [str(item.get("format") or "text") for item in frame["materials"]]
    if formats.count("chart") != 1 or formats.count("table") != 1:
        raise ValueError("framework must assign exactly one chart and one table material")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: material_results=list(pool.map(lambda item:material_call(frame,item,batch_id),frame["materials"]))
    marks["materials_seconds_wall"]=round(time.monotonic()-t,2); materials=[r["material"] for r in material_results]; image_dir=out/"images"; image_dir.mkdir(exist_ok=True)
    for material in materials: render_material(material,image_dir)
    jobs=[(material,plan,index) for material,plan in zip(materials,frame["materials"]) for index in range(1,6)]; t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(lambda job:call(question_prompt(job[0],job[1],job[2],batch_id),6000),jobs))
    marks["questions_seconds_wall"]=round(time.monotonic()-t,2); questions=[r["question"] for r in results]; calculations=[r["calculation"] for r in results]
    manifest={"batch_id":batch_id,"source":"广东省考行测-资料分析-"+today.replace("-",""),"region":"广东-模拟","year":int(today[:4]),"license":"仅用于学习与题库内部评测","created_at":today,"kind":"ai-generated","difficulty_tier":"hard","generation":{"style_marker":"GONGKAO-STYLE-v2-split","batch_constraints":{"all_original":True,"question_count":20,"difficulty_tier":"hard","answer_distribution":"unconstrained"},"evaluation_contexts":[]}}
    for name,data in [("framework.json",frame),("manifest.json",manifest),("materials.json",materials),("questions.json",questions),("calculations.json",{"questions":calculations})]: (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    marks["question_count"]=len(questions); t=time.monotonic(); gate=subprocess.run(["python3","scripts/generation_gate.py","issue",str(out)],cwd=ROOT,text=True,capture_output=True); marks["gate_seconds"]=round(time.monotonic()-t,2)
    if gate.returncode:
        marks["gate_error"]=(gate.stdout or gate.stderr)[-6000:]; marks["total_seconds"]=round(time.monotonic()-started,2); (out/"timing.json").write_text(json.dumps(marks,ensure_ascii=False,indent=2)); print(gate.stdout or gate.stderr); return gate.returncode
    t=time.monotonic(); imp=subprocess.run(["node","scripts/import-batch.mjs",str(out)],cwd=ROOT,text=True,capture_output=True); marks["import_seconds"]=round(time.monotonic()-t,2); marks["total_seconds"]=round(time.monotonic()-started,2); marks["import_output"]=imp.stdout[-3000:]; (out/"timing.json").write_text(json.dumps(marks,ensure_ascii=False,indent=2)); print(imp.stdout or imp.stderr); return imp.returncode

if __name__ == "__main__": raise SystemExit(main())

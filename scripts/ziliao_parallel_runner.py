#!/usr/bin/env python3
"""Gemini data-analysis paper: framework -> materials -> independent questions."""
from __future__ import annotations

import argparse, concurrent.futures, datetime as dt, json, math, os, re, sqlite3, subprocess, time, urllib.request, uuid
from pathlib import Path
from collections import Counter
from quiz_generator import resolve_slots, run_canon_card
from kaodian_taxonomy import validate_ai_primary_tag
from scheduler_common import DB

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

def framework_prompt(difficulty="mid", formats=None, slots=None) -> str:
    formats = formats or ["chart", "table", "text", "text"]
    return f"""你是公考资料分析命题总设计师。设计{len(formats)}篇材料的命题框架，不写题目。
输出JSON：{{"difficulty":"{difficulty}","materials":[{{"id":"M01","theme":"...","format":"text/table/chart","focus":"...","question_plan":"...","chart_tasks":[]}}]}}
材料编号严格依次M01、M02等；形态按此顺序：{json.dumps(formats)}。chart只用bars，table只用table，text只用none；禁止mixed。柱图4—8分类，表格至少6行4列。
各篇主题和信息组织应不同。图表必须承担找数、筛选、求和、趋势或表文结合任务，不能只是装饰。
题目槽位：{json.dumps(slots or [], ensure_ascii=False)}。材料须提供槽位考法所需数据与口径；不得更换考法。
难度easy为直接定位或一步计算，mid多一层转化，hard增加同一考点内的约束或表文组合，不靠无意义长小数。不要默认把所有题出成hard。"""

def material_prompt(frame: dict, item: dict, batch_id: str) -> str:
    return f"""你是独立的广东省考资料分析材料设计模型，只负责{item['id']}，不出题。
本批难度 {frame.get('difficulty', 'mid')}。方向与已确认考点：{json.dumps(item, ensure_ascii=False)}。生成一篇数据足够、篇幅适当的原创统计材料。
材料自洽，所有题目所需数字必须来自正文或结构化图表。使用G省、H省或全国，不用“某省”。
    format为chart时只能返回bars figure，format为table时只能返回table figure，format为text时kind必须为none，绝不返回mixed。bars的categories为4-10个且每个series.values等长非空数字数组；table至少6行、至少4列。图表数字、标题、单位、分类完整；不要双轴。图表要保留足够无关项，让题目能考察定位、筛选和排除，而不是只读一个数字。
严格输出JSON：{{"material":{{"external_id":"{batch_id}-{item['id']}","content":"...","figure":{{"kind":"none或table或bars","title":"...","unit":"...","headers":[],"rows":[],"categories":[],"series":[]}}}}}}。"""

def question_prompt(material: dict, plan: dict, index: int, batch_id: str, slot=None) -> str:
    q5 = index == 5 and not slot
    level = {"easy": 2, "mid": 3, "hard": 4}[(slot or {}).get("difficulty") or plan.get("difficulty", "mid")]
    form = {"M01": "根据资料，以下说法可以判断属实的是", "M02": "不能从上述资料中推出的是", "M03": "下列说法正确的有", "M04": "能够从上述资料中推出的是"}.get(str(plan.get("id")), "能够从上述资料中推出的是")
    tasks = plan.get("chart_tasks") or []
    task = tasks[(index - 1) % len(tasks)] if tasks else "根据材料完成不同于其他题的信息定位或计算"
    return f"""你是独立命题模型，只根据下面冻结材料设计第{index}题，不修改材料、数字、图表或口径。
本题难度{(slot or {}).get('difficulty') or plan.get('difficulty', 'mid')}。材料方向：{json.dumps(plan, ensure_ascii=False)}
指定槽位（主标签、定义、额外要求必须遵守）：{json.dumps(slot or {}, ensure_ascii=False)}。
材料：{material['content']}
图表数据：{json.dumps(material.get('figure') or {}, ensure_ascii=False)}
本题指定考法：{task}。如果材料带图，本题必须真正使用图表中的数据；图表题不得只复述正文中已直接给出的同一句数字。
第{index}题必须{'是综合判断题，题干必须以“'+form+'”开头' if q5 else '围绕材料真实数据设计单选题'}。
easy只需直接定位或一步计算；mid多一层转化；hard允许隐含中间量、跨段/表文组合、单位或口径转换、接近选项。错误选项对应真实粗心路径。比重上升下降、百分比与百分点、现期与基期等必须区分。不要用无意义长小数。
严格输出JSON：{{"question":{{"external_id":"{batch_id}-{material['external_id'].rsplit('-',1)[-1]}-Q{index}","category":"资料分析","question_type":"single","material_id":"{material['external_id']}","stem":"...","options":[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}],"answer":"A","explanation":"...最后明确选择X项","tags":["白名单标签"],"difficulty":{level}}},"calculation":{{"question_id":"...","correct":"只含数字和+-*/括号的算式","options":{{"A":0,"B":0,"C":0,"D":0}},"tolerance":0.001}}}}
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
                and all(len(item.get("values") or []) == len(categories)
                        and all(type(value) in (int, float) and math.isfinite(value) for value in item["values"])
                        for item in series))
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

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="资料分析：冻结材料、程序渲染、独立出题、现有质检入库")
    parser.add_argument("--tag")
    parser.add_argument("--blueprint")
    parser.add_argument("--count", type=int)
    parser.add_argument("--materials", type=int)
    parser.add_argument("--formats", help="按篇指定 text,table,chart；chart 为确定性柱图")
    parser.add_argument("--difficulty", choices=["easy", "mid", "hard"], default="mid")
    parser.add_argument("--batch-id")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "parallel-ziliao")
    parser.add_argument("--no-import", action="store_true")
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
    formats = args.formats.split(',') if args.formats else ["chart", "table", "text", "text"][:n]
    if len(formats) != n or any(f not in {"text", "table", "chart"} for f in formats):
        parser.error("--formats 须与材料篇数一致，仅允许 text/table/chart")
    args.batch_id = args.batch_id or f"{dt.date.today():%Y%m%d}_hermes_ziliao_{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[\w-]{1,160}", args.batch_id):
        parser.error("batch-id 只能包含字母、数字、汉字、下划线和连字符")
    args.total, args.slots, args.formats = count, slots, formats
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
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        if conn.execute("SELECT 1 FROM questions WHERE batch_id=? LIMIT 1", (batch_id,)).fetchone():
            raise ValueError("batch-id 已入库，请换编号")
    finally:
        conn.close()
    out = args.output_dir/today/batch_id; out.mkdir(parents=True, exist_ok=False); marks = {"started_at":dt.datetime.now(dt.timezone.utc).isoformat()}
    run = {"module": "资料分析", "slots": args.slots}
    per_item = [dict(slot, definition=run_canon_card(run, slot["tag"])) for slot in args.slots for _ in range(slot["count"])]
    t=time.monotonic(); frame=call(framework_prompt(args.difficulty,args.formats,per_item),5000); marks["framework_seconds"]=round(time.monotonic()-t,2)
    validate_frame(frame,args)
    cursor = 0
    for i, item in enumerate(frame["materials"]):
        item["difficulty"] = args.difficulty
        item["count"] = args.total // len(args.formats) + (i < args.total % len(args.formats))
        item["slots"] = per_item[cursor:cursor + item["count"]]
        cursor += item["count"]
    (out/"framework.json").write_text(json.dumps(frame, ensure_ascii=False, indent=2))
    t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: material_results=list(pool.map(lambda item:material_call(frame,item,batch_id),frame["materials"]))
    marks["materials_seconds_wall"]=round(time.monotonic()-t,2); materials=[r["material"] for r in material_results]; image_dir=out/"images"; image_dir.mkdir(exist_ok=True)
    for material, plan in zip(materials,frame["materials"]):
        if material.get("external_id") != f"{batch_id}-{plan['id']}":
            raise ValueError("材料 ID 与冻结框架不一致")
        render_material(material,image_dir)
    jobs=[(material,plan,index) for material,plan in zip(materials,frame["materials"]) for index in range(1,plan["count"]+1)]; t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(lambda job:call(question_prompt(job[0],job[1],job[2],batch_id,job[1]["slots"][job[2]-1] if job[1]["slots"] else None),6000),jobs))
    marks["questions_seconds_wall"]=round(time.monotonic()-t,2); questions=[r["question"] for r in results]; calculations=[r["calculation"] for r in results]
    for position, (question, calculation, job) in enumerate(zip(questions, calculations, jobs)):
        material, plan, index = job
        qid = f"{batch_id}-{plan['id']}-Q{index}"
        if question.get("external_id") != qid or question.get("material_id") != material["external_id"] or calculation.get("question_id") != qid:
            raise ValueError("题目、验算与冻结材料关联不一致")
        tag = validate_ai_primary_tag((question.get("tags") or [""])[0], "资料分析")
        if per_item and tag != per_item[position]["tag"]:
            raise ValueError(f"{qid} 未命中指定考点")
        question["category"] = "资料分析"
        question["difficulty"] = {"easy":2,"mid":3,"hard":4}[(per_item[position].get("difficulty") if per_item else None) or args.difficulty]
    constraints = {"all_original":True,"question_count":args.total,"difficulty_tier":args.difficulty,
                   "answer_distribution":"unconstrained","targeted_drill":bool(args.slots) or args.total != 20,
                   "slot_plan":args.slots}
    if per_item: constraints["tag_counts"] = dict(Counter(s["tag"] for s in per_item))
    topic = args.slots[0]["tag"].split('-',1)[1] if args.slots else "综合训练"
    manifest={"batch_id":batch_id,"source":f"广东省考行测-资料分析-{topic}-{args.difficulty}-{today.replace('-','')}","region":"广东-模拟","year":int(today[:4]),"license":"仅用于学习与题库内部评测","created_at":today,"kind":"ai-generated","difficulty_tier":args.difficulty,"generation":{"style_marker":"GONGKAO-STYLE-v2-split","batch_constraints":constraints,"kaofa_canon":run.get("kaofa_canon",{}),"evaluation_contexts":[]}}
    for name,data in [("framework.json",frame),("manifest.json",manifest),("materials.json",materials),("questions.json",questions),("calculations.json",{"questions":calculations})]: (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    env = {**os.environ, "EXAM_DB": str(args.db)}
    marks["question_count"]=len(questions); t=time.monotonic(); gate=subprocess.run(["python3","scripts/generation_gate.py","issue",str(out)],cwd=ROOT,env=env,text=True,capture_output=True); marks["gate_seconds"]=round(time.monotonic()-t,2)
    if gate.returncode:
        marks["gate_error"]=(gate.stdout or gate.stderr)[-6000:]; marks["total_seconds"]=round(time.monotonic()-started,2); (out/"timing.json").write_text(json.dumps(marks,ensure_ascii=False,indent=2)); print(gate.stdout or gate.stderr); return gate.returncode
    if args.no_import:
        print(json.dumps({"status":"success","batch_id":batch_id,"imported":0,"batch_dir":str(out),"message":"质检通过，未入库"},ensure_ascii=False))
        return 0
    t=time.monotonic(); imp=subprocess.run(["node","scripts/import-batch.mjs",str(out)],cwd=ROOT,env=env,text=True,capture_output=True); marks["import_seconds"]=round(time.monotonic()-t,2); marks["total_seconds"]=round(time.monotonic()-started,2); marks["import_output"]=imp.stdout[-3000:]; (out/"timing.json").write_text(json.dumps(marks,ensure_ascii=False,indent=2))
    print(json.dumps({"status":"success" if imp.returncode == 0 else "error","batch_id":batch_id,"batch_dir":str(out),"message":imp.stdout or imp.stderr},ensure_ascii=False))
    return imp.returncode

if __name__ == "__main__": raise SystemExit(main())

#!/usr/bin/env python3
"""申论（广东省考）出题与真题导入。Hermes 只调这个脚本，不在会话里写题。

  generate   AI 出整卷或题型特训：命题蓝图 → 按蓝图虚构材料（并行、程序核字数）→ 命题人出设问和要点表 → 审核官复核 → 入库
             材料、设问形式照 hermes-skills/quiz-pipeline/references/shenlun-style.md（由 2023–2026 真题统计归纳）
  import     导入真题卷 JSON；没有要点表的由命题人补建并复核
  ingest     处理收件箱：data/shenlun-inbox/sources/*.json 抓原文登记，papers/*.json 导入
  add-source 登记一篇申论材料原文
  sources    列出已登记材料

用法：
  python3 scripts/shenlun_quiz.py generate --batch-id 20261015_hermes_申论_01 --paper 县镇卷 --theme 百千万工程
  python3 scripts/shenlun_quiz.py generate --batch-id 20261015_hermes_申论_02 --types 归纳概括,归纳概括
  python3 scripts/shenlun_quiz.py import @data/shenlun-inbox/papers/gd-2025-xianzhen.json

评分与复盘在 shenlun_grade.py（Hermes「申论复盘」调用）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import policy_sources  # noqa: E402
from scheduler_common import local_today  # noqa: E402
from shenlun_common import (BATCH_DIR, DRILL_DEFAULTS, INBOX_DIR, LAYOUTS, LEVEL, PAPER_TYPES, QTYPES, ROOT,  # noqa: E402
                            STYLE_GUIDE, TIME_LIMIT_MIN, call, check_rubric, repair_evidence, connect, dumps, materials_text, save_paper,
                            word_count)

SOURCE_DIR = ROOT / "data" / "shenlun-sources"
# 申论材料多是新闻报道、评论和调研，比政治题的权威白名单宽一些；抓取与核验办法相同
MEDIA = ("southcn.com", "nfnews.com", "ycwb.com", "gmw.cn", "cctv.com", "cnr.cn", "chinanews.com.cn", "ce.cn",
         "chinadaily.com.cn", "gd.gov.cn", "dutenews.com", "sznews.com", "gzdaily.cn")
WORKERS = 3
# 不指定主题时随机抽一个；前几项是 2024–2026 真题主题，后面是县镇卷常见方向
THEME_POOL = (
    "百千万工程与县域富民产业", "绿美广东生态建设", "古树名木保护", "绿色工厂与绿色低碳发展", "产业科技创新与新质生产力",
    "做好“土特产”文章", "农村人居环境长效管护", "基层治理与为基层减负", "传统村落保护与文旅融合", "防灾减灾与基层应急管理",
    "“一老一小”民生服务", "数字乡村与政务服务", "农业科技与种业振兴", "青年返乡创业与乡村人才", "海洋经济与渔业转型",
)


def style_guide() -> str:
    return STYLE_GUIDE.read_text(encoding="utf-8") if STYLE_GUIDE.exists() else ""


RUBRIC_RULES = """要点表（rubric）规则——它是阅卷采点给分的唯一依据：
- 小题 rubric = {"kind":"points","points":[...],"expression_score":N,"format_points":[...]}。
- 每个 point = {"id":"P1","text":"规范表述的得分点","score":1或2（30 分题可到 3）,"side":"问题或对策（只有提出对策题填）","evidence":[{"para":"M2-3","quote":"逐字摘自该段的8到40字原文"}]}。
  像阅卷细则那样细：一个要点只含一个可独立判分的意思，text 不超过 30 字，score 一般 1 或 2，30 分的对策题可以给 3；
  不要把几件事用分号塞进一个要点。不重复、不交叉；只收设问真正问到的内容；evidence 必须引用本题指定材料的原文，quote 一字不改。
- 归纳概括 20 分题一般 9 到 12 个要点；提出对策 30 分题问题侧 5 到 7 个要点（每个 2 分左右）、对策侧 5 到 8 个要点（每个 2 到 3 分），每条对策要对得上材料里的某个问题；要点分合计至少比满分少 1、多则少 3。
- 对策可以由材料里的问题反推，不必是材料现成的措施；但不能是与材料无关的空话。对策侧要点的 evidence 引它所针对的那句问题原文（或材料里可借鉴的做法原文），quote 一字不改。
- expression_score：表述与条理分，一般 1 到 2 分（程序会按满分自动配平，不必自己凑总分）。
- format_points 只用于贯彻执行（如发言提纲的标题、导语、按主体分块、结尾），合计 2 到 3 分；提出对策题的文种壳（汇报、调研报告部分内容）不设格式分，给空数组。
- 要点分 + format_points 分要比本题分值少 1 到 2 分，余下作表述分。
- 文章写作 rubric = {"kind":"essay","theme":"立意：总论点应指向……","must_cover":[{"id":"T1","text":"分论点方向","evidence":[...]}],
  "off_topic":"判为偏题的情形"}；must_cover 给 3 到 4 个由材料能推出的论证方向。
- reference_answer：归纳概括写 4 到 5 条，每条「4 到 8 字自拟总括 + 用材料关键词压成的一句」，不写总起和结尾；
  提出对策分「问题」「对策建议」两块，问题与对策大体一一对应；两者都必须逐条覆盖全部要点，不超过字数上限。
  文章写作写提纲（标题、总论点、分论点句、每段用哪份材料的哪个事实），不写全文。"""

PLANNER = """你是广东省考申论命题组组长。按下面的「风格档案」，为一套申论题设计材料与设问蓝图。材料全部虚构，但形式要和真题一样。
虚构规则：宏观背景可以用广东和国家的真实政策、工程名称（如「百千万工程」「绿美广东」）；具体案例的县、镇、村、企业、人物一律用化名
（A县、G市、X镇、榕泉村、小王、吕主任）；不要把编造的数据安到真实地名上。

风格档案：
{style}

本次要出：{task}
只输出 JSON：
{{"theme":"整卷主题一句话","essay_topic":"作文围绕的主题句（没有作文就空字符串）",
"materials":[{{"no":1,"role":"背景/第1题/第2题/作文/特训","genre":"报道/案例/访谈/讲话/调研/座谈会发言/评论/政策文件","structure":"总-分/总-分-总/按时间/一人一段发言…",
"chars":目标字数,"outline":["这份材料必须写到的具体内容：一项做法、一个问题、一句群众或干部原话、一个数据……，6 到 12 条"],"names":"用到的化名"}}],
"questions":[{{"no":1,"qtype":"归纳概括","material":这道题限定的材料编号（文章写作写 0 表示全部）,"identity":"作答身份（没有就空）","shell":"文种壳（没有就空）","focus":"这道题问什么"}}]}}"""

MATERIAL_WRITER = """你是申论「给定资料」撰稿人。按蓝图写出其中一份材料，像真实的新闻报道、调研记录、座谈发言或讲话那样写。
- 内容虚构；具体案例的地名、单位、人名用蓝图里的化名，不要用真实县镇名。
- 必须写到蓝图 outline 里的每一条，一段讲一件事；多用干部、群众、专家的原话（加引号），多用具体数字和细节。
- 只写事实、做法、现象和人物的话，不要替考生归纳：不要出现「一是……二是……」式的答案总结，也不要写「存在的问题有」「对策是」这类提示句。
- 字数约 {chars} 字（不含空白），上下浮动不超过一成。
参考真题材料的语言风格（风格档案第七节有真题原文样本）：
{samples}
只输出 JSON：{{"paragraphs":["第一段","第二段", "..."]}}"""

def writer_prompt() -> str:
    # 要点表规则里有 JSON 花括号，不能走 str.format
    return ("你是广东省考申论命题人。设问句式、要求措辞、身份和文种壳都要照下面「风格档案」里的真题写法，不要自创花样。\n"
            "风格档案：\n" + style_guide() + "\n\n" + RUBRIC_RULES + "\n"
            '只输出 JSON：{"questions":[{"no":1,"qtype":"归纳概括","prompt":"完整设问（含分值、要求、字数，照真题格式换行）",'
            '"material_ids":["M2"],"score":20,"words_min":null,"words_max":200,"rubric":{...},"reference_answer":"..."}]}')


REVIEWER = """你是广东省考申论阅卷组长，独立复核命题人交来的题目和要点表。逐题检查：
1. 设问是否清楚、只指向指定材料；设问句式、要求措辞、身份与文种壳是否和风格档案里的真题写法一致。
2. 每个要点是否真是设问所问，引文是否真的支持该要点；要点有无重复、交叉、过细凑分。
3. 指定材料里有没有明显应得分却漏掉的要点（列入 missing_points）。漏掉重要要点必须 REJECT。
4. 分值分配是否合理；要点是否细到一个意思一分到两分（几件事塞进一个要点必须 REJECT）。
   参考答案是否逐条覆盖全部要点（逐个要点核对，漏一个就 REJECT）、没有材料外的编造、没超字数。
5. 材料是否撑得起这道题：归纳题材料里要有足够多可拆分的做法或表现；对策题材料里要有具体问题，不能是现成的对策清单。
6. 文章写作：立意能否由材料推出、must_cover 方向是否合理、偏题标准是否清楚。
风格档案（节选看设问写法即可）：
{style}
只输出 JSON：{{"questions":[{{"no":1,"verdict":"PASS","issues":[],"missing_points":[]}}]}}；有任何实质问题就 REJECT 并写明。"""


def _samples() -> str:
    text = style_guide()
    return text[text.find("## 七"):] if "## 七" in text else ""


def _task_text(paper_type: str, layout: list[dict], drill: bool, theme: list[str]) -> str:
    lines = []
    if drill:
        lines.append(f"题型特训（{paper_type}风格），只出这几道题：" + "、".join(s["qtype"] for s in layout) + "。")
        lines.append("每道小题配一份专用材料：归纳概括 600 到 1200 字（两到四段即可）；提出对策 1000 到 1500 字，要写清具体问题；"
                     "综合分析 800 到 1200 字；贯彻执行 1000 到 1500 字。文章写作单独特训时配 4 份材料、每份 700 到 900 字。"
                     "不要背景材料。")
    else:
        lines.append(f"一整套{paper_type}：8 份材料、3 道题（归纳概括 20 分、提出对策 30 分、文章写作 50 分）。")
        lines.append("材料 1 写宏观背景或理论，不单独命题；第 1 题限定一份 1200 到 2000 字、有 8 到 12 个可拆分做法或表现的案例材料（编号在 2 到 5 之间）；"
                     "第 2 题限定另一份 1200 到 2000 字、同时有问题和办法的材料"
                     + ("（县镇卷：调研组走访，多用群众和干部原话）" if paper_type == "县镇卷" else "（省市卷：座谈会上一人一段的发言）")
                     + "；其余材料每份 800 到 1100 字，供作文使用。8 份总字数 7800 到 9000。")
    lines.append("各题配分与字数：" + json.dumps(layout, ensure_ascii=False))
    if theme:
        lines.append(f"指定主题：{'、'.join(theme)}。整卷材料都围绕这个主题。")
    return "\n".join(lines)


def plan_paper(paper_type: str, layout: list[dict], drill: bool, theme: list[str], audit: Path) -> dict:
    plan = call(PLANNER.format(style=style_guide(), task=_task_text(paper_type, layout, drill, theme)), "请给出蓝图。",
                temperature=0.7, audit=audit)
    mats = plan.get("materials") or []
    qs = plan.get("questions") or []
    issues = []
    if not drill and len(mats) != 8:
        issues.append(f"整卷要 8 份材料，蓝图给了 {len(mats)} 份")
    if len(qs) != len(layout):
        issues.append(f"题目数 {len(qs)} 与要求 {len(layout)} 不符")
    nos = {int(m.get("no") or 0) for m in mats}
    for q in qs:
        if q.get("qtype") != "文章写作" and int(q.get("material") or 0) not in nos:
            issues.append(f"第{q.get('no')}题限定的材料 {q.get('material')} 不存在")
    if issues:
        raise RuntimeError("命题蓝图不合格：" + "；".join(issues))
    for m in mats:
        m["chars"] = max(400, min(2200, int(m.get("chars") or 900)))
    return plan


def write_material(item: dict, plan: dict, audit: Path) -> dict:
    brief = json.dumps({"整卷主题": plan.get("theme"), "本份材料蓝图": item}, ensure_ascii=False)
    target = int(item["chars"])
    # 长材料字数波动大：前两稿按 0.75–1.3 倍要求，第三稿放宽到 0.6–1.6 倍，字数略偏不影响训练
    for low, high in ((0.75, 1.3), (0.75, 1.3), (0.6, 1.6)):
        out = call(MATERIAL_WRITER.format(chars=target, samples=_samples()), brief, temperature=0.8, audit=audit)
        paras = [re.sub(r"\s+", " ", str(x)).strip() for x in out.get("paragraphs") or [] if str(x).strip()]
        chars = sum(word_count(x) for x in paras)
        if paras and low * target <= chars <= high * target:
            return {"no": int(item["no"]), "paragraphs": paras}
        brief += f"\n上一稿 {chars} 字，要求约 {target} 字，请按字数重写。"
    raise RuntimeError(f"材料{item['no']}字数三次都不合要求（要求约 {target} 字，实际 {chars} 字）")


def build_materials(plan: dict, audit: Path) -> list[dict]:
    items = sorted(plan["materials"], key=lambda m: int(m.get("no") or 0))
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        written = list(pool.map(lambda m: write_material(m, plan, audit), items))
    materials = []
    for k, w in enumerate(written, 1):
        materials.append({"id": f"M{k}", "title": f"材料{k}",
                          "paragraphs": [{"id": f"M{k}-{j}", "text": t} for j, t in enumerate(w["paragraphs"], 1)]})
    return materials


def plan_hint(plan: dict) -> str:
    rows = []
    for q in plan.get("questions") or []:
        scope = "全部材料" if q.get("qtype") == "文章写作" else f"材料{q.get('material')}（M{q.get('material')}）"
        rows.append(f"第{q.get('no')}题 {q.get('qtype')}：限定{scope}；身份：{q.get('identity') or '无'}；"
                    f"文种壳：{q.get('shell') or '无'}；问：{q.get('focus')}")
    topic = f"\n作文主题句：{plan.get('essay_topic')}" if plan.get("essay_topic") else ""
    return "\n\n命题蓝图（照此出题，限定材料不要改）：\n" + "\n".join(rows) + topic


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 材料库
def add_source(spec: dict) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,79}", spec.get("id", "")):
        raise ValueError("材料 id 须为 2–80 位小写字母、数字、下划线或连字符")
    for key in ("title", "url", "published_at"):
        if not spec.get(key):
            raise ValueError(f"材料缺 {key}")
    dt.date.fromisoformat(spec["published_at"])
    saved = policy_sources.TRUSTED
    policy_sources.TRUSTED = tuple(dict.fromkeys(saved + MEDIA))
    try:
        page, url = policy_sources.fetch(spec["url"])
    finally:
        policy_sources.TRUSTED = saved
    paragraphs = list(dict.fromkeys(p for p in page.parts if len(p) >= 20))
    if spec.get("focus"):
        paragraphs = [p for p in paragraphs if any(word in p for word in spec["focus"])]
    if sum(map(len, paragraphs)) < 200:
        raise ValueError("原文提取不足 200 字，可能是空页、拦截页或需要登录：" + spec["url"])
    record = {**spec, "url": url, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "sha256": _sha("\n".join(paragraphs)),
              "paragraphs": [{"id": f"p{i + 1}", "text": p} for i, p in enumerate(paragraphs)]}
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    (SOURCE_DIR / f"{spec['id']}.json").write_text(dumps(record), encoding="utf-8")
    return record


def all_sources() -> dict[str, dict]:
    """申论材料库 + 已登记的政策原文（政策文件也是申论材料的常见来源）。"""
    out = {}
    pdir = policy_sources.directory()
    for ident, spec in policy_sources.registry().items():
        path = pdir / f"{ident}.json"
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            out[ident] = {"id": ident, "title": rec.get("title") or spec.get("title"), "url": rec.get("url"),
                          "published_at": rec.get("published_at"), "origin": "policy",
                          "paragraphs": [p["text"] for p in rec.get("paragraphs") or []]}
    for path in sorted(SOURCE_DIR.glob("*.json")) if SOURCE_DIR.exists() else []:
        rec = json.loads(path.read_text(encoding="utf-8"))
        out[rec["id"]] = {"id": rec["id"], "title": rec["title"], "url": rec["url"], "published_at": rec["published_at"],
                          "origin": "shenlun", "paragraphs": [p["text"] for p in rec["paragraphs"]],
                          "tags": rec.get("tags") or []}
    return out


def _layout_text(layout: list[dict], fixed: list[dict] | None) -> str:
    if fixed:
        return "题目已定（真题），不得改动设问，只补 rubric 和 reference_answer：\n" + dumps(fixed)
    return "本卷题型与配分：\n" + dumps([{**slot, "no": i + 1} for i, slot in enumerate(layout)])


def normalize_questions(raw: list[dict], layout: list[dict], materials: list[dict], fixed: list[dict] | None) -> list[dict]:
    out = []
    ids = {m["id"] for m in materials}
    for i, slot in enumerate(fixed or layout):
        q = next((x for x in raw if int(x.get("no") or 0) == i + 1), None)
        if q is None:
            raise RuntimeError(f"命题人漏了第 {i + 1} 题")
        base = fixed[i] if fixed else q
        material_ids = [m for m in (base.get("material_ids") or q.get("material_ids") or []) if m in ids] or sorted(ids)
        rubric = q.get("rubric") or {}
        if rubric.get("kind") == "points":
            # 配平交给程序：表述分 = 满分 − 要点分 − 格式分，落在 0–3 分就采用；超出说明要点配错了，交给核对退回
            full = float(base.get("score") or slot.get("score"))
            used = sum(float(p.get("score") or 0) for p in (rubric.get("points") or []) + (rubric.get("format_points") or []))
            if 0 <= full - used <= 3:
                rubric["expression_score"] = full - used
        out.append({
            "no": i + 1,
            "qtype": base.get("qtype") or slot["qtype"],
            "prompt": str(base.get("prompt") or "").strip(),
            "requirements": {"score": float(base.get("score") or slot.get("score")),
                             "words_min": base.get("words_min", slot.get("words_min")),
                             "words_max": base.get("words_max", slot.get("words_max")),
                             "material_ids": material_ids},
            "rubric": rubric,
            "reference_answer": str(q.get("reference_answer") or "").strip(),
        })
    return out


def program_issues(q: dict, materials: list[dict]) -> list[str]:
    repair_evidence(q, materials)
    issues = check_rubric(q, materials)
    if q["qtype"] not in QTYPES:
        issues.append(f"第{q['no']}题：题型 {q['qtype']} 不在县级卷五类里")
    if len(q["prompt"]) < 20:
        issues.append(f"第{q['no']}题：设问太短")
    limit = q["requirements"].get("words_max")
    if q["qtype"] != "文章写作" and limit and word_count(q["reference_answer"]) > int(limit) * 1.05:
        issues.append(f"第{q['no']}题：参考答案 {word_count(q['reference_answer'])} 字，超过 {limit} 字")
    if not q["reference_answer"]:
        issues.append(f"第{q['no']}题：缺参考答案")
    return issues


def write_and_review(materials: list[dict], layout: list[dict], audit: Path, *, fixed: list[dict] | None = None,
                     hints: str = "", rounds: int = 2) -> tuple[list[dict], list[dict]]:
    context = "给定资料：\n" + materials_text(materials)
    writer = writer_prompt()
    raw = call(writer, context + "\n\n" + _layout_text(layout, fixed) + hints, temperature=0.5, audit=audit,
               max_tokens=24000)
    questions = normalize_questions(raw.get("questions") or [], layout, materials, fixed)
    history = []
    for round_no in range(1, rounds + 2):
        prog = {q["no"]: program_issues(q, materials) for q in questions}
        review = call(REVIEWER.format(style=style_guide()), context + "\n\n题目与要点表：\n" + dumps(questions), temperature=0.1,
                      audit=audit)
        verdicts = {int(v.get("no") or 0): v for v in review.get("questions") or []}
        bad = []
        for q in questions:
            v = verdicts.get(q["no"]) or {"verdict": "REJECT", "issues": ["审核官漏审本题"]}
            issues = prog[q["no"]] + ([] if v.get("verdict") == "PASS" else list(v.get("issues") or []))
            issues += [f"漏掉要点：{m}" for m in v.get("missing_points") or []] if v.get("verdict") != "PASS" else []
            if issues:
                bad.append((q["no"], issues))
        history.append({"round": round_no, "rejected": [{"no": n, "issues": i} for n, i in bad]})
        if not bad:
            return questions, history
        if round_no > rounds:
            break
        redo = {n for n, _ in bad}
        feedback = "\n".join(f"第{n}题需重写：" + "；".join(i) for n, i in bad)
        keep = [q for q in questions if q["no"] not in redo]
        prompt = (context + "\n\n" + _layout_text(layout, fixed) + hints
                  + "\n\n以下题目已通过，原样保留，不要输出：" + ",".join(str(q["no"]) for q in keep)
                  + "\n只重写这些题号：" + ",".join(map(str, sorted(redo))) + "\n审核意见：\n" + feedback)
        raw = call(writer, prompt, temperature=0.5, audit=audit, max_tokens=24000)
        fresh = {int(x.get("no") or 0): x for x in raw.get("questions") or []}
        merged = []
        for q in questions:
            if q["no"] in redo:
                if q["no"] not in fresh:
                    raise RuntimeError(f"重写时命题人漏了第 {q['no']} 题")
                slot_fixed = [fixed[q["no"] - 1]] if fixed else None
                slot = (fixed or layout)[q["no"] - 1]
                new = normalize_questions([{**fresh[q["no"]], "no": 1}], [slot], materials, slot_fixed)[0]
                new["no"] = q["no"]
                merged.append(new)
            else:
                merged.append(q)
        questions = merged
    left = "；".join(f"第{n}题：" + "、".join(i[:3]) for n, i in bad)
    raise RuntimeError(f"{rounds + 1} 轮后仍有题目不合格：{left}")


# ---------------------------------------------------------------- 子命令
def parse_layout(types: str | None, paper_type: str = LEVEL) -> list[dict]:
    if paper_type not in PAPER_TYPES:
        raise ValueError(f"卷种只能是：{'、'.join(PAPER_TYPES)}")
    if not types:
        return [dict(s) for s in LAYOUTS[paper_type]]
    out = []
    for name in [t.strip() for t in types.replace("，", ",").split(",") if t.strip()]:
        if name not in DRILL_DEFAULTS:
            raise ValueError(f"题型只能是：{'、'.join(QTYPES)}")
        slot = dict(DRILL_DEFAULTS[name])
        if name == "文章写作":
            slot.update({k: v for k, v in LAYOUTS[paper_type][-1].items() if k.startswith("words")})
        out.append(slot)
    if len(out) > 3:
        raise ValueError("题型特训一次最多 3 道题")
    return out


def batch_dir(batch_id: str) -> Path:
    path = BATCH_DIR / local_today().isoformat() / batch_id
    if path.exists() and any(path.iterdir()):
        raise ValueError("批次目录已有产物，请换一个 batch_id")
    path.mkdir(parents=True, exist_ok=True)
    return path


def cmd_generate(args) -> dict:
    if not re.fullmatch(r"[\w\-]{4,80}", args.batch_id):
        raise ValueError("batch_id 只能含字母、数字、下划线、连字符和汉字")
    conn = connect(args.db)
    if conn.execute("SELECT 1 FROM shenlun_papers WHERE id=?", (args.batch_id,)).fetchone():
        raise ValueError("这个 batch_id 已入库，换一个序号")
    paper_type = args.paper or LEVEL
    layout = parse_layout(args.types, paper_type)
    drill = bool(args.types)
    theme = [w.strip() for w in (args.theme or "").replace("，", ",").split(",") if w.strip()]
    if not theme:
        theme = [random.choice(THEME_POOL)]
    out_dir = batch_dir(args.batch_id)
    audit = out_dir / "audit"
    started = time.monotonic()
    plan = plan_paper(paper_type, layout, drill, theme, audit)
    (out_dir / "plan.json").write_text(dumps(plan), encoding="utf-8")
    materials = build_materials(plan, audit)
    # 限定材料以蓝图为准：命题人只管写设问和要点
    scope = {int(q.get("no") or 0): q for q in plan["questions"]}
    for i, slot in enumerate(layout, 1):
        q = scope.get(i) or {}
        if slot["qtype"] != "文章写作" and q.get("material"):
            slot["material_ids"] = [f"M{int(q['material'])}"]
    questions, history = write_and_review(materials, layout, audit, rounds=args.rounds, hints=plan_hint(plan))
    topic = str(plan.get("theme") or "").strip()
    kinds = "、".join(q["qtype"] for q in questions)
    day = f"{local_today():%Y%m%d}"
    paper = {
        "id": args.batch_id, "kind": "ai", "level": paper_type, "region": "广东", "year": local_today().year,
        "title": (f"广东省考申论（{paper_type}）特训-{kinds}-{topic}-{day}" if drill
                  else f"广东省考申论（{paper_type}）模拟-{topic}-{day}"),
        "time_limit_min": None if drill else TIME_LIMIT_MIN,
        "source_note": f"材料为虚构，按 2024–2026 年广东省考申论{paper_type}真题的材料形式与设问方式命制。",
        "materials": materials, "questions": questions,
        "meta": {"pipeline": "shenlun_quiz", "model": MODEL, "paper_type": paper_type, "drill": drill,
                 "theme": theme, "plan": plan, "review_rounds": history,
                 "seconds": round(time.monotonic() - started, 1)},
    }
    (out_dir / "paper.json").write_text(dumps(paper), encoding="utf-8")
    if not args.no_import:
        save_paper(conn, paper)
    return {"status": "success", "paper_id": paper["id"], "title": paper["title"], "questions": len(questions),
            "materials": len(materials), "material_chars": sum(word_count(p["text"]) for m in materials for p in m["paragraphs"]),
            "imported": not args.no_import, "batch_dir": str(out_dir), "seconds": paper["meta"]["seconds"],
            "message": f"已{'入库' if not args.no_import else '生成'}申论 {len(questions)} 题：{paper['title']}"}


def normalize_import(data: dict) -> dict:
    """真题卷 JSON → 内部结构。materials 的 paragraphs 可以是字符串数组。"""
    for key in ("title", "materials", "questions"):
        if not data.get(key):
            raise ValueError(f"试卷缺 {key}")
    materials = []
    for i, m in enumerate(data["materials"], 1):
        paras = [p if isinstance(p, str) else p.get("text", "") for p in m.get("paragraphs") or []]
        paras = [re.sub(r"\s+", " ", p).strip() for p in paras if p and p.strip()]
        if not paras:
            raise ValueError(f"材料{i} 没有正文")
        materials.append({"id": f"M{i}", "title": m.get("title") or f"材料{i}",
                          "paragraphs": [{"id": f"M{i}-{j}", "text": t} for j, t in enumerate(paras, 1)]})
    questions = []
    for i, q in enumerate(data["questions"], 1):
        if q.get("qtype") not in QTYPES:
            raise ValueError(f"第{i}题 qtype 须为：{'、'.join(QTYPES)}")
        if not q.get("prompt") or not q.get("score"):
            raise ValueError(f"第{i}题缺 prompt 或 score")
        questions.append({"no": i, "qtype": q["qtype"], "prompt": q["prompt"].strip(), "score": float(q["score"]),
                          "words_min": q.get("words_min"), "words_max": q.get("words_max"),
                          "material_ids": q.get("material_ids") or [], "rubric": q.get("rubric"),
                          "reference_answer": q.get("reference_answer"),
                          "reference_answers": q.get("reference_answers") or []})
    slug = data.get("id") or "zhenti-" + _sha(data["title"])[:10]
    if not re.fullmatch(r"[\w\-]{4,80}", slug):
        raise ValueError("试卷 id 只能含字母、数字、下划线、连字符和汉字")
    return {"id": slug, "title": data["title"], "kind": data.get("kind") or "zhenti", "level": data.get("level") or LEVEL,
            "region": data.get("region") or "广东", "year": data.get("year"),
            "time_limit_min": data.get("time_limit_min") or TIME_LIMIT_MIN,
            "source_note": data.get("source_note") or "", "materials": materials, "questions": questions}


def cmd_import(spec: str, db=None, rounds: int = 2) -> dict:
    text = Path(spec[1:]).read_text(encoding="utf-8") if spec.startswith("@") else spec
    paper = normalize_import(json.loads(text))
    out_dir = BATCH_DIR / local_today().isoformat() / paper["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    audit = out_dir / "audit"
    have = [q for q in paper["questions"] if q.get("rubric")]
    final = []
    for q in paper["questions"]:  # 卷面给了 rubric 的直接用程序核对
        if q.get("rubric"):
            final.append({"no": q["no"], "qtype": q["qtype"], "prompt": q["prompt"],
                          "requirements": {"score": q["score"], "words_min": q["words_min"], "words_max": q["words_max"],
                                           "material_ids": q["material_ids"] or [m["id"] for m in paper["materials"]]},
                          "rubric": q["rubric"], "reference_answer": q.get("reference_answer") or ""})
    issues = [i for q in final for i in check_rubric(q, paper["materials"])]
    if issues:
        raise ValueError("给定要点表核对不过：" + "；".join(issues[:6]))
    todo = [q for q in paper["questions"] if not q.get("rubric")]
    history = []
    if todo:
        refs = [f"第{q['no']}题机构参考答案（{a.get('source', '未注明')}）：{a.get('text', '')}"
                for q in todo for a in q.get("reference_answers") or []]
        hints = ("\n\n以下是培训机构的参考答案，只作提示：几家都提到、且材料里有原文依据的才进要点表；"
                 "与材料不符的不要收。\n" + "\n".join(refs)) if refs else ""
        fixed = [{k: q[k] for k in ("no", "qtype", "prompt", "score", "words_min", "words_max", "material_ids")}
                 for q in todo]
        # 只补没给 rubric 的题，题号按原卷
        built, history = write_and_review(paper["materials"], [], audit, fixed=[{**f, "no": i + 1}
                                                                                  for i, f in enumerate(fixed)],
                                          hints=hints, rounds=rounds)
        for f, b in zip(fixed, built):
            b["no"] = f["no"]
        final += built
    final.sort(key=lambda q: q["no"])
    paper["questions"] = final
    paper["meta"] = {"pipeline": "shenlun_import", "rubric_given": len(have), "rubric_built": len(todo),
                     "review_rounds": history}
    (out_dir / "paper.json").write_text(dumps(paper), encoding="utf-8")
    save_paper(connect(db), paper)
    return {"status": "success", "paper_id": paper["id"], "title": paper["title"], "questions": len(final),
            "rubric_built": len(todo), "message": f"已导入：{paper['title']}（补建要点表 {len(todo)} 题）"}


def cmd_ingest(db=None) -> dict:
    done = {"sources": [], "papers": [], "errors": []}
    for kind in ("sources", "papers"):
        folder = INBOX_DIR / kind
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            target = INBOX_DIR / "done" / kind
            try:
                if kind == "sources":
                    rec = add_source(json.loads(path.read_text(encoding="utf-8")))
                    done["sources"].append(rec["id"])
                else:
                    done["papers"].append(cmd_import("@" + str(path), db)["paper_id"])
            except Exception as exc:  # noqa: BLE001
                done["errors"].append({"file": path.name, "error": str(exc)[:400]})
                target = INBOX_DIR / "failed" / kind
            target.mkdir(parents=True, exist_ok=True)
            path.rename(target / path.name)
    return {"status": "success" if not done["errors"] else "partial", **done}




def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="申论出题、导入与材料登记")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--batch-id", required=True)
    g.add_argument("--paper", choices=PAPER_TYPES, default=LEVEL, help="卷种，默认县镇卷")
    g.add_argument("--theme", help="主题，逗号分隔；不给就从近年真题常见主题里随机抽一个")
    g.add_argument("--types", help="题型特训：只出这些题型（可重复，最多 3 道），逗号分隔；不给则出整卷 3 题")
    g.add_argument("--rounds", type=int, default=2)
    g.add_argument("--no-import", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("spec", help="试卷 JSON，内联或 @路径")
    sub.add_parser("ingest")
    a = sub.add_parser("add-source")
    a.add_argument("spec", help='{"id","title","url","published_at","publisher?","tags?","focus?"}，内联或 @路径')
    sub.add_parser("sources")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = cmd_generate(args)
        elif args.command == "import":
            result = cmd_import(args.spec, args.db)
        elif args.command == "ingest":
            result = cmd_ingest(args.db)
        elif args.command == "add-source":
            text = Path(args.spec[1:]).read_text(encoding="utf-8") if args.spec.startswith("@") else args.spec
            rec = add_source(json.loads(text))
            result = {"status": "success", "id": rec["id"], "title": rec["title"], "paragraphs": len(rec["paragraphs"])}
        elif args.command == "sources":
            result = {"sources": [{"id": s["id"], "title": s["title"], "published_at": s.get("published_at"),
                                   "origin": s["origin"], "chars": sum(map(len, s["paragraphs"]))}
                                  for s in all_sources().values()]}
        else:
            raise ValueError(f"未知命令：{args.command}")
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)[:2000], "message": f"失败：{str(exc)[:600]}"},
                         ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

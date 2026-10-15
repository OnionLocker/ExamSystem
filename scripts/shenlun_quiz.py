#!/usr/bin/env python3
"""申论（广东县级卷）出题、导入与材料登记。Hermes 只调这个脚本，不在会话里写题。

  generate   AI 出整卷或单题：材料逐字摘自已登记原文 → 命题人出题和要点表 → 审核官复核 → 入库
  import     导入真题卷 JSON（grokbot 收集或手工整理）；没有要点表的由命题人补建并复核
  ingest     处理 grokbot 收件箱：data/shenlun-inbox/sources/*.json 抓原文登记，papers/*.json 导入
  add-source 登记一篇申论材料原文（新闻报道、评论、调研、政策文件）
  sources    列出可用材料
  report     打印某次作答的批改报告（Markdown），Hermes 讲评用

用法：
  python3 scripts/shenlun_quiz.py generate --batch-id 20261015_hermes_申论_01 --theme 百千万工程,乡村振兴
  python3 scripts/shenlun_quiz.py generate --batch-id 20261015_hermes_申论_02 --types 归纳概括 --sources src-a,src-b
  python3 scripts/shenlun_quiz.py import @data/shenlun-inbox/papers/gd-2025-xianji.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import policy_sources  # noqa: E402
from scheduler_common import local_today  # noqa: E402
from shenlun_common import (BATCH_DIR, DEFAULT_LAYOUT, INBOX_DIR, LEVEL, QTYPES, ROOT, TIME_LIMIT_MIN,  # noqa: E402
                            call, check_rubric, connect, contains, dumps, load_paper, materials_text, save_paper,
                            word_count)

SOURCE_DIR = ROOT / "data" / "shenlun-sources"
# 申论材料多是新闻报道、评论和调研，比政治题的权威白名单宽一些；抓取与核验办法相同
MEDIA = ("southcn.com", "nfnews.com", "ycwb.com", "gmw.cn", "cctv.com", "cnr.cn", "chinanews.com.cn", "ce.cn",
         "chinadaily.com.cn", "gd.gov.cn", "dutenews.com", "sznews.com", "gzdaily.cn")
POOL_CHARS = 45000

STYLE = """广东省考申论县级卷的特点：材料多是基层治理、乡村振兴（“百县千镇万村高质量发展工程”）、民生服务、产业发展、生态（绿美广东）、
基层干部作风等主题的案例、报道、访谈和调研，给定资料按「材料1」「材料2」编号。设问紧扣指定材料，要求写明作答范围、分值、字数。
设问示例：
- 根据“给定资料1”，概括X镇在推进……中采取的主要做法。（10分）要求：全面、准确、有条理。不超过200字。
- 根据“给定资料2”，谈谈你对“……”这句话的理解。（15分）要求：观点明确，分析透彻，不超过300字。
- 根据“给定资料3”，针对……存在的问题，提出解决对策。（15分）要求：对策具体可行，有针对性，不超过300字。
- 假如你是X县……的工作人员，请根据“给定资料4”，写一份……的倡议书（宣传稿/讲话提纲/工作简报/情况报告）。（20分）
  要求：格式规范，内容具体，语言得体，不超过500字。
- 参考“给定资料”，围绕“……”，自选角度，自拟题目，写一篇议论文。（40分）要求：观点明确，联系实际，论述深刻，
  结构完整，语言流畅，字数1000～1200字。"""

RUBRIC_RULES = """要点表（rubric）规则——它是阅卷采点给分的唯一依据：
- 小题 rubric = {"kind":"points","points":[...],"expression_score":N,"format_points":[...]}。
- 每个 point = {"id":"P1","text":"规范表述的得分点","score":1或2,"evidence":[{"para":"M1-3","quote":"逐字摘自该段的8到40字原文"}]}。
  像阅卷细则那样细：一个要点只含一个可独立判分的意思，text 不超过 30 字，score 只能是 1 或 2；
  不要把几件事用分号塞进一个要点。不重复、不交叉；只收设问真正问到的内容；evidence 必须引用本题指定材料的原文，quote 一字不改。
- 对策题的要点要能从材料里的问题、原因或经验推出来；如果指定材料只是一张现成的措施清单，换一份讲问题或案例的材料来出对策题。
- expression_score：表述与条理分，一般 1 到 2 分（程序会按满分自动配平，不必自己凑总分）。
- format_points 只用于贯彻执行：标题、称谓、落款、文种要素等，每项 {"id":"F1","text":"...","score":1}，合计 2 到 3 分；其他题给空数组。
- 要点分 + format_points 分要比本题分值少 1 到 2 分，余下作表述分。
- 文章写作 rubric = {"kind":"essay","theme":"立意：总论点应指向……","must_cover":[{"id":"T1","text":"分论点方向","evidence":[...]}],
  "off_topic":"判为偏题的情形"}；must_cover 给 3 到 4 个由材料能推出的论证方向。
- reference_answer：小题写按要点组织的参考答案，必须逐条覆盖全部要点，不超过字数上限；文章写作写提纲（标题、总论点、三个分论点及对应材料论据），不写全文。"""


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


def build_pool(sources: dict[str, dict], ids: list[str] | None, theme: list[str]) -> tuple[list[dict], str]:
    """把候选原文编号成 S1-p3 这样的段落池；有主题词时只取命中段落及其前后各一段。"""
    chosen = [sources[i] for i in ids] if ids else sorted(sources.values(), key=lambda s: s.get("published_at") or "",
                                                          reverse=True)
    if ids and len(chosen) != len(ids):
        raise ValueError("有未登记的材料 id")
    pool, lines, used = [], [], 0
    for k, src in enumerate(chosen, 1):
        paras = src["paragraphs"]
        keep = range(len(paras))
        if theme:
            hits = {i for i, p in enumerate(paras) if any(w in p for w in theme)}
            keep = sorted({j for i in hits for j in (i - 1, i, i + 1) if 0 <= j < len(paras)})
        if not keep:
            continue
        lines.append(f"\n=== S{k}：{src['title']}（{src.get('published_at') or ''}）")
        for i in keep:
            ref = f"S{k}-p{i + 1}"
            if used + len(paras[i]) > POOL_CHARS:
                break
            pool.append({"ref": ref, "text": paras[i], "source": {"id": src["id"], "title": src["title"],
                                                                   "url": src.get("url")}})
            lines.append(f"[{ref}] {paras[i]}")
            used += len(paras[i])
        if used >= POOL_CHARS:
            break
    if used < 2500:
        raise ValueError(f"可用材料只有 {used} 字，不够组卷；先用 add-source 登记更多原文，或换主题词")
    return pool, "\n".join(lines)


# ---------------------------------------------------------------- 命题
COMPOSER = """你是广东省考申论（县级卷）命题组的材料编辑。只能从给定原文段落里逐字摘录组成「给定资料」，不得改写、拼接或补写任何字。
""" + STYLE + """
任务：从段落池选材，组成 {n_materials} 份给定资料，总字数 {chars} 字左右。
- 每份资料围绕一个侧面（案例做法、存在问题、群众反映、成效经验、观点评论），能支撑后面的设问；资料之间不重复。
- excerpt 写该段原文中连续的一段（可以是整段，也可以截去首尾），必须一字不差；ref 写段落编号。
- 不要选纯口号、目录、页眉页脚类段落。
只输出 JSON：{{"theme":"整卷主题","materials":[{{"title":"材料1","focus":"这份资料讲什么","excerpts":[{{"ref":"S1-p3","excerpt":"……"}}]}}]}}"""

WRITER = """你是广东省考申论（县级卷）命题人。""" + STYLE + """
""" + RUBRIC_RULES + """
只输出 JSON：{"questions":[{"no":1,"qtype":"归纳概括","prompt":"完整设问（含分值、要求、字数）","material_ids":["M1"],
"score":10,"words_min":null,"words_max":200,"rubric":{...},"reference_answer":"..."}]}"""

REVIEWER = """你是广东省考申论阅卷组长，独立复核命题人交来的题目和要点表。逐题检查：
1. 设问是否清楚、只指向指定材料、像广东县级卷真题；题型与要求一致（贯彻执行须写明身份、文种与格式要求）。
2. 每个要点是否真是设问所问，引文是否真的支持该要点；要点有无重复、交叉、过细凑分。
3. 指定材料里有没有明显应得分却漏掉的要点（列入 missing_points）。漏掉重要要点必须 REJECT。
4. 分值分配是否合理；要点是否细到一个意思一分到两分（几件事塞进一个要点必须 REJECT）。
   参考答案是否逐条覆盖全部要点（逐个要点核对，漏一个就 REJECT）、没有材料外的编造、没超字数。
5. 材料是否适合这道设问：对策题的材料若本身就是现成措施清单、照抄即可作答，必须 REJECT。
6. 文章写作：立意能否由材料推出、must_cover 方向是否合理、偏题标准是否清楚。
只输出 JSON：{"questions":[{"no":1,"verdict":"PASS","issues":[],"missing_points":[]}]}；有任何实质问题就 REJECT 并写明。"""


def compose_materials(pool: list[dict], pool_text: str, layout: list[dict], audit: Path) -> tuple[str, list[dict]]:
    n = 5 if len(layout) >= 4 else max(1, len(layout) + 1)
    chars = "5000 到 7000" if len(layout) >= 4 else "1500 到 3000"
    result = call(COMPOSER.format(n_materials=n, chars=chars), "段落池：\n" + pool_text, temperature=0.4, audit=audit)
    by_ref = {p["ref"]: p for p in pool}
    materials, dropped = [], []
    for m_index, item in enumerate(result.get("materials") or [], 1):
        paragraphs = []
        for ex in item.get("excerpts") or []:
            para = by_ref.get(str(ex.get("ref")))
            text = re.sub(r"\s+", " ", str(ex.get("excerpt") or "")).strip()
            if para is None or len(text) < 20 or text not in para["text"]:
                dropped.append(str(ex.get("ref")))
                continue
            paragraphs.append({"id": f"M{m_index}-{len(paragraphs) + 1}", "text": text, "source": para["source"]})
        if paragraphs:
            materials.append({"id": f"M{m_index}", "title": f"材料{m_index}", "paragraphs": paragraphs})
    for k, m in enumerate(materials, 1):  # 有材料整份被丢掉时重新连续编号
        if m["id"] != f"M{k}":
            m["id"], m["title"] = f"M{k}", f"材料{k}"
            for j, p in enumerate(m["paragraphs"], 1):
                p["id"] = f"M{k}-{j}"
    total = sum(len(p["text"]) for m in materials for p in m["paragraphs"])
    if dropped and len(dropped) > 3:
        raise RuntimeError(f"材料编辑有 {len(dropped)} 处摘录不是原文（{dropped[:5]}），本次停止")
    if not materials or total < (3000 if len(layout) >= 4 else 800):
        raise RuntimeError(f"组出的材料只有 {total} 字，不够出题")
    return str(result.get("theme") or ""), materials


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
    raw = call(WRITER, context + "\n\n" + _layout_text(layout, fixed) + hints, temperature=0.5, audit=audit,
               max_tokens=24000)
    questions = normalize_questions(raw.get("questions") or [], layout, materials, fixed)
    history = []
    for round_no in range(1, rounds + 2):
        prog = {q["no"]: program_issues(q, materials) for q in questions}
        review = call(REVIEWER, context + "\n\n题目与要点表：\n" + dumps(questions), temperature=0.1, audit=audit)
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
        raw = call(WRITER, prompt, temperature=0.5, audit=audit, max_tokens=24000)
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
def parse_layout(types: str | None) -> list[dict]:
    if not types:
        return [dict(s) for s in DEFAULT_LAYOUT]
    by_type = {s["qtype"]: s for s in DEFAULT_LAYOUT}
    out = []
    for name in [t.strip() for t in types.split(",") if t.strip()]:
        if name not in by_type:
            raise ValueError(f"题型只能是：{'、'.join(QTYPES)}")
        out.append(dict(by_type[name]))
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
    layout = parse_layout(args.types)
    theme = [w.strip() for w in (args.theme or "").replace("，", ",").split(",") if w.strip()]
    ids = [s.strip() for s in (args.sources or "").split(",") if s.strip()] or None
    out_dir = batch_dir(args.batch_id)
    audit = out_dir / "audit"
    started = time.monotonic()
    pool, pool_text = build_pool(all_sources(), ids, theme)
    topic, materials = compose_materials(pool, pool_text, layout, audit)
    questions, history = write_and_review(materials, layout, audit, rounds=args.rounds,
                                          hints=f"\n整卷主题：{topic}" if topic else "")
    full = len(layout) == len(DEFAULT_LAYOUT)
    kinds = "、".join(q["qtype"] for q in questions)
    paper = {
        "id": args.batch_id, "kind": "ai", "level": LEVEL, "region": "广东", "year": local_today().year,
        "title": (f"广东省考申论（县级卷）模拟-{topic}-{local_today():%Y%m%d}" if full
                  else f"广东省考申论（县级卷）{kinds}-{topic}-{local_today():%Y%m%d}"),
        "time_limit_min": TIME_LIMIT_MIN if full else None,
        "source_note": "材料逐字摘自：" + "；".join(sorted({p["source"]["title"] for m in materials
                                                    for p in m["paragraphs"]})),
        "materials": materials, "questions": questions,
        "meta": {"pipeline": "shenlun_quiz", "model": "gemini-3.8-flash-high", "theme": theme,
                 "review_rounds": history, "seconds": round(time.monotonic() - started, 1)},
    }
    (out_dir / "paper.json").write_text(dumps(paper), encoding="utf-8")
    if not args.no_import:
        save_paper(conn, paper)
    return {"status": "success", "paper_id": paper["id"], "title": paper["title"], "questions": len(questions),
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


def report(attempt_id: int, db=None) -> str:
    conn = connect(db)
    row = conn.execute("SELECT * FROM shenlun_attempts WHERE id=?", (attempt_id,)).fetchone()
    if row is None:
        raise ValueError("没有这次作答")
    q = conn.execute("SELECT * FROM shenlun_questions WHERE id=?", (row["question_id"],)).fetchone()
    paper = load_paper(conn, q["paper_id"])
    question = next(x for x in paper["questions"] if x["id"] == q["id"])
    grading = json.loads(row["grading"] or "{}")
    lines = [f"# 申论批改报告：{paper['title']} 第{question['no']}题（{question['qtype']}）", "",
             f"- 作答 ID：{attempt_id}；得分 {row['score']}/{row['max_score']}；字数 {row['word_count']}"
             f"（上限 {question['requirements'].get('words_max')}）；用时 {row['time_spent_sec'] or '未记'} 秒", "",
             "## 设问", question["prompt"], "", "## 考生作答（阅卷人从照片转写或直接输入）", row["answer_text"] or "", ""]
    if grading.get("kind") == "points":
        lines += ["## 采点结果", "| 要点 | 分值 | 得分 | 判定 | 考生原句 | 材料依据 |", "|---|---|---|---|---|---|"]
        for p in grading["points"]:
            ev = "；".join(f"{e['para']}「{e['quote']}」" for e in p.get("evidence") or [])
            lines.append(f"| {p['id']} {p['text']} | {p['score']:g} | {p['earned']:g} | {p['verdict_text']}"
                         f"{'（两遍有分歧）' if p.get('disputed') else ''} | {p.get('answer_quote') or '—'} | {ev} |")
        for key in ("format", "expression"):
            if grading.get(key):
                lines.append(f"\n{grading[key]['label']}：{grading[key]['earned']:g}/{grading[key]['score']:g}"
                             f"——{grading[key].get('reason', '')}")
    elif grading.get("kind") == "essay":
        lines += [f"## 作文档次：{grading['level']}（{grading['earned']:g}/{grading['score']:g}）", ""]
        for d in grading["dimensions"]:
            lines.append(f"- {d['name']}：{d['level']}——{d.get('reason', '')}")
    if grading.get("notes"):
        lines += ["", "## 其他", *[f"- {n}" for n in grading["notes"]]]
    if question.get("reference_answer"):
        lines += ["", "## 参考答案", question["reference_answer"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="申论出题、导入与材料登记")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--batch-id", required=True)
    g.add_argument("--theme", help="主题词，逗号分隔，用来从原文里挑段落")
    g.add_argument("--sources", help="指定材料 id，逗号分隔；不给则按发布日期取最新的")
    g.add_argument("--types", help="只出这些题型，逗号分隔；不给则出整卷 5 题")
    g.add_argument("--rounds", type=int, default=2)
    g.add_argument("--no-import", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("spec", help="试卷 JSON，内联或 @路径")
    sub.add_parser("ingest")
    a = sub.add_parser("add-source")
    a.add_argument("spec", help='{"id","title","url","published_at","publisher?","tags?","focus?"}，内联或 @路径')
    sub.add_parser("sources")
    r = sub.add_parser("report")
    r.add_argument("--attempt", type=int, required=True)
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
            print(report(args.attempt, args.db))
            return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)[:2000], "message": f"失败：{str(exc)[:600]}"},
                         ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

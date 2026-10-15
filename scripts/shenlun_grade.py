#!/usr/bin/env python3
"""申论交卷评分：Hermes「申论复盘」先调这里打分，再按报告点评。照片直接交给模型（多模态），不单独做识别。

  grade --submission ID   给一次交卷里的每道题评分，写评分报告，返回报告路径
  seal  --submission ID --comment 点评文件   Hermes 点评写完后封存，网页上显示「已复盘」
  grade --attempt ID      只重评一道题（调试用）

评判标准在 hermes-skills/gd-gongkao-coach/references/shenlun-review-standard.md，由用户维护：
「通用」和对应题型章节原文交给阅卷模型，「评分参数」控制部分命中、表述分、作文档次的折算。

小题按要点表采点，两遍独立批改：每遍先把照片里的答案逐字转写进 transcript，再采点；
answer_quote 由程序到这一遍的 transcript 里核对，对不上的按未命中计。分数由程序相加，
两遍判定不一致的要点按「评分参数」取低（或高）并标出「有分歧」。作文按立意、结构、论证、语言评档。
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shenlun_common import (ESSAY_DIMENSIONS, REVIEW_DIR, ROOT, UPLOAD_DIR, call, connect, contains,  # noqa: E402
                            image_part, load_paper, load_standard, materials_text, standard_for, word_count)

READ_RULES = """考生答案在照片里（按顺序拍的答题卡）。先在 transcript 里逐字转写答案：保留错别字和病句，不纠正、不润色、不补写；
看不清的字写 □；划掉的字、题号、格子线、答题卡印刷文字不转写。之后的判定只依据你转写出来的内容。"""

POINT_SYSTEM = """你是广东省考申论阅卷人，严格按要点表采点给分，不凭整体印象打分。
{read}
评判标准（用户维护，必须遵守）：
{standard}
对每个要点判定 verdict：hit（答出了这个意思）/ partial（只答到一部分或表述含糊）/ miss（没答到或只有空话套话）。
answer_quote：命中或部分命中时，逐字摘录考生答案里对应的那句（8 到 60 字，一字不改）；miss 写空字符串。
expression：条理与语言，level 取 A / B / C。
format（只在给了格式要点时判）：每项 hit 或 miss。
只输出 JSON：{{"transcript":"考生答案全文","points":[{{"id":"P1","verdict":"hit","answer_quote":"...","reason":"..."}}],
"format":[{{"id":"F1","verdict":"hit","reason":"..."}}],"expression":{{"level":"A","reason":"..."}},"comment":"一句话总评"}}"""

ESSAY_SYSTEM = """你是广东省考申论大作文阅卷人。
{read}
评判标准（用户维护，必须遵守）：
{standard}
按四个维度分别评档：立意、结构、论证、语言，每个维度给 一类 / 二类 / 三类 / 四类 之一，
reason 写依据，quote 逐字摘录作文里最能说明问题的一句（8 到 60 字）。
must_cover_hit：列出作文实际论述到的论证方向编号。off_topic：是否偏题。
只输出 JSON：{{"transcript":"作文全文","dimensions":[{{"name":"立意","level":"二类","reason":"...","quote":"..."}}],
"off_topic":false,"must_cover_hit":["T1"],"comment":"一句话总评"}}"""

TYPED = "考生答案是直接输入的文字，transcript 原样抄写下面「考生答案」即可。"
LEVEL_NAMES = ("一类", "二类", "三类", "四类")
VERDICT_TEXT = {"hit": "命中", "partial": "部分命中", "miss": "未命中"}
WORKERS = 3


def _set(conn, table: str, row_id: int, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn:
        conn.execute(f"UPDATE {table} SET {cols}, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*fields.values(), row_id))


class Answer:
    """考生答案：照片（交给模型转写）或直接输入的文字。"""

    def __init__(self, images: list[str], text: str):
        self.images, self.text = images, (text or "").strip()
        if not images and len(self.text) < 20:
            raise ValueError("没有照片，答案文字也太少")

    @property
    def read_rules(self) -> str:
        return READ_RULES if self.images else TYPED

    def parts(self, prefix: str) -> list:
        if not self.images:
            return [{"type": "text", "text": prefix + f"\n\n考生答案：\n{self.text}"}]
        parts = [{"type": "text", "text": prefix + f"\n\n考生答案照片共 {len(self.images)} 张："}]
        for k, rel in enumerate(self.images, 1):
            parts += [{"type": "text", "text": f"第 {k} 张"}, image_part(UPLOAD_DIR / rel)]
        return parts

    def transcript(self, res: dict) -> str:
        if not self.images:
            return self.text
        text = str(res.get("transcript") or "").strip()
        if len(text) < 20:
            raise RuntimeError("阅卷人没从照片里读出答案，请检查照片是否清晰、是否拍到答题区")
        return text


def _pick(values: list[float], params: dict) -> float:
    return max(values) if params.get("dispute_policy") == "higher" else min(values)


# ---------------------------------------------------------------- 小题采点
def _verify(verdict: str, quote: str, transcript: str) -> tuple[str, str]:
    if verdict not in ("hit", "partial"):
        return "miss", ""
    if not contains(transcript, quote):
        return "miss", "阅卷人引的句子在答案里找不到，按未命中计"
    return verdict, ""


def grade_points(question: dict, paper: dict, answer: Answer, audit: Path, params: dict) -> dict:
    rubric = question["rubric"]
    points = rubric["points"]
    system = POINT_SYSTEM.format(read=answer.read_rules, standard=standard_for(question["qtype"]))

    def one_pass(order: list[dict], temperature: float) -> dict:
        prefix = (materials_text(paper["materials"], question["requirements"].get("material_ids"))
                  + f"\n\n设问：{question['prompt']}\n\n要点表：\n"
                  + json.dumps([{k: p[k] for k in ("id", "text", "score")} for p in order], ensure_ascii=False)
                  + ("\n\n格式要点：\n" + json.dumps(rubric.get("format_points"), ensure_ascii=False)
                     if rubric.get("format_points") else ""))
        return call(system, answer.parts(prefix), temperature=temperature, audit=audit)

    # 第二遍倒序给要点，减少排在前面的要点占便宜
    passes = [one_pass(points, 0.0), one_pass(list(reversed(points)), 0.3)]
    texts = [answer.transcript(res) for res in passes]
    ratio = float(params.get("partial_ratio", 0.5))
    out_points = []
    for p in points:
        judged = []
        for res, text in zip(passes, texts):
            hit = next((x for x in res.get("points") or [] if x.get("id") == p["id"]), {})
            verdict, note = _verify(str(hit.get("verdict") or "miss"), str(hit.get("answer_quote") or ""), text)
            earned = {"hit": 1.0, "partial": ratio, "miss": 0.0}[verdict] * float(p["score"])
            judged.append({"verdict": verdict, "earned": round(earned * 2) / 2, "quote": hit.get("answer_quote") or "",
                           "reason": hit.get("reason") or "", "note": note})
        target = _pick([j["earned"] for j in judged], params)
        chosen = next(j for j in judged if j["earned"] == target)
        out_points.append({"id": p["id"], "text": p["text"], "score": float(p["score"]), "earned": chosen["earned"],
                           "verdict": chosen["verdict"], "verdict_text": VERDICT_TEXT[chosen["verdict"]],
                           "answer_quote": chosen["quote"] if chosen["verdict"] != "miss" else "",
                           "reason": chosen["reason"], "note": chosen["note"],
                           "disputed": len({j["verdict"] for j in judged}) > 1,
                           "passes": [{"verdict": j["verdict"], "reason": j["reason"]} for j in judged],
                           "evidence": p.get("evidence") or []})
    result = {"kind": "points", "points": out_points, "transcript": texts[0], "notes": []}
    fmt = rubric.get("format_points") or []
    if fmt:
        got = []
        for f in fmt:
            vs = [next((x for x in res.get("format") or [] if x.get("id") == f["id"]), {}) for res in passes]
            got.append(_pick([float(f["score"]) if v.get("verdict") == "hit" else 0.0 for v in vs], params))
        missed = [f["text"] for f, g in zip(fmt, got) if not g]
        result["format"] = {"label": "格式分", "score": sum(float(f["score"]) for f in fmt), "earned": sum(got),
                            "reason": "缺：" + "、".join(missed) if missed else "格式要素齐全"}
    expr = float(rubric.get("expression_score") or 0)
    if expr:
        table = params.get("expression_levels") or {"A": 1.0, "B": 0.5, "C": 0.0}
        values = [float(table.get(str((res.get("expression") or {}).get("level") or "C").upper()[:1], 0.0)) * expr
                  for res in passes]
        result["expression"] = {"label": "表述分", "score": expr, "earned": round(_pick(values, params) * 2) / 2,
                                "reason": (passes[0].get("expression") or {}).get("reason", "")}
    result["earned"] = (sum(p["earned"] for p in out_points)
                        + sum((result.get(k) or {}).get("earned", 0) for k in ("format", "expression")))
    result["comment"] = passes[0].get("comment") or ""
    disputed = [p["id"] for p in out_points if p["disputed"]]
    if disputed:
        result["notes"].append(f"两遍批改对 {'、'.join(disputed)} 判得不一样，已按{'高' if params.get('dispute_policy') == 'higher' else '低'}的计分")
    return result


# ---------------------------------------------------------------- 大作文
def grade_essay(question: dict, paper: dict, answer: Answer, audit: Path, params: dict) -> dict:
    rubric = question["rubric"]
    prefix = (materials_text(paper["materials"], with_ids=False) + f"\n\n题目：{question['prompt']}\n\n命题立意："
              + str(rubric.get("theme")) + "\n论证方向：" + json.dumps(rubric.get("must_cover") or [], ensure_ascii=False)
              + "\n偏题标准：" + str(rubric.get("off_topic") or ""))
    system = ESSAY_SYSTEM.format(read=answer.read_rules, standard=standard_for(question["qtype"]))
    passes = [call(system, answer.parts(prefix), temperature=0.0, audit=audit),
              call(system, answer.parts(prefix), temperature=0.3, audit=audit)]
    texts = [answer.transcript(res) for res in passes]
    lower = params.get("dispute_policy") != "higher"
    dims, notes = [], []
    for name in ESSAY_DIMENSIONS:
        judged = []
        for res, text in zip(passes, texts):
            d = next((x for x in res.get("dimensions") or [] if x.get("name") == name), {})
            level = str(d.get("level") or "四类")[:2]
            level = level if level in LEVEL_NAMES else "四类"
            quote = str(d.get("quote") or "")
            judged.append({"level": level, "reason": d.get("reason") or "", "quote": quote if contains(text, quote) else ""})
        pick = max if lower else min
        chosen = pick(judged, key=lambda j: LEVEL_NAMES.index(j["level"]))
        dims.append({"name": name, **chosen, "disputed": len({j["level"] for j in judged}) > 1})
    levels = params.get("essay_levels") or []
    ranks = [LEVEL_NAMES.index(d["level"]) for d in dims]
    overall = min(len(levels) - 1, max(ranks[0], round(sum(ranks) / len(ranks))))  # 立意定上限
    if any(res.get("off_topic") for res in passes):
        names = [lv["name"] for lv in levels]
        target = params.get("essay_off_topic_level") or names[-1]
        overall = names.index(target) if target in names else len(levels) - 1
        notes.append(f"阅卷人判定偏题，按{levels[overall]['name']}计")
    band = levels[overall]
    full = float(question["requirements"]["score"])
    words = word_count(texts[0])
    wmin = question["requirements"].get("words_min")
    if wmin and words < int(wmin):
        notes.append(f"全文约 {words} 字，少于 {wmin} 字的要求，考场上会扣分"
                     + ("（本次未扣）" if params.get("overflow_note_only", True) else ""))
    disputed = [d["name"] for d in dims if d["disputed"]]
    if disputed:
        notes.append(f"两遍批改对 {'、'.join(disputed)} 评得不一样，已按{'低' if lower else '高'}的计")
    hits = sorted(set(passes[0].get("must_cover_hit") or []) & set(passes[1].get("must_cover_hit") or []))
    return {"kind": "essay", "level": band["name"], "score": full,
            "earned": float(round(full * (float(band["min"]) + float(band["max"])) / 2)),
            "dimensions": dims, "must_cover_hit": hits, "transcript": texts[0],
            "comment": passes[0].get("comment") or "", "notes": notes}


def grade_attempt(conn, attempt_id: int, params: dict) -> dict:
    row = conn.execute("SELECT * FROM shenlun_attempts WHERE id=?", (attempt_id,)).fetchone()
    if row is None:
        raise ValueError(f"没有这次作答：{attempt_id}")
    q = conn.execute("SELECT paper_id FROM shenlun_questions WHERE id=?", (row["question_id"],)).fetchone()
    paper = load_paper(conn, q["paper_id"])
    question = next(x for x in paper["questions"] if x["id"] == row["question_id"])
    answer = Answer(json.loads(row["images"] or "[]"), row["answer_text"] or "")
    audit = UPLOAD_DIR / str(attempt_id) / "audit"
    grader = grade_essay if question["rubric"].get("kind") == "essay" else grade_points
    result = grader(question, paper, answer, audit, params)
    words = word_count(result["transcript"])
    wmax = question["requirements"].get("words_max")
    if wmax and question["qtype"] != "文章写作" and words > int(wmax):
        result["notes"].append(f"答案约 {words} 字，超出 {wmax} 字的限制；考场上超出部分可能不计分"
                               + ("（本次未扣）" if params.get("overflow_note_only", True) else ""))
    full = float(question["requirements"]["score"])
    return {"attempt_id": attempt_id, "question": question, "grading": result, "score": result["earned"],
            "max_score": full, "word_count": words, "transcript": result["transcript"]}


# ---------------------------------------------------------------- 报告
def _report(paper: dict, submission: dict, graded: list[dict], failed: list[tuple[dict, str]]) -> str:
    total = sum(g["score"] for g in graded)
    full = sum(g["max_score"] for g in graded)
    lines = [f"# 申论评分报告：{paper['title']}", "",
             f"- 交卷 ID：{submission['id']}；交卷时间 {submission['created_at']}；整套用时 "
             f"{round((submission['time_spent_sec'] or 0) / 60)} 分钟",
             f"- 本次交了 {len(graded) + len(failed)} 题，评出 {len(graded)} 题：合计 {total:g}/{full:g} 分", "",
             "| 题号 | 题型 | 得分 | 字数 |", "|---|---|---|---|"]
    for g in graded:
        q = g["question"]
        limit = q["requirements"].get("words_max")
        lines.append(f"| 第{q['no']}题 | {q['qtype']} | {g['score']:g}/{g['max_score']:g} | {g['word_count']}"
                     f"{f'（上限 {limit}）' if limit else ''} |")
    for q, err in failed:
        lines.append(f"| 第{q['no']}题 | {q['qtype']} | 评分失败：{err[:60]} | — |")
    for g in graded:
        q, r = g["question"], g["grading"]
        lines += ["", f"## 第{q['no']}题 · {q['qtype']}（{g['score']:g}/{g['max_score']:g}）", "", f"**设问**：{q['prompt']}", "",
                  "**考生答案（阅卷人从照片转写）**：", "", g["transcript"], ""]
        if r["kind"] == "points":
            lines += ["| 要点 | 分值 | 得分 | 判定 | 考生原句 | 材料依据 |", "|---|---|---|---|---|---|"]
            for p in r["points"]:
                ev = "；".join(f"{e['para']}「{e['quote']}」" for e in p.get("evidence") or [])
                lines.append(f"| {p['id']} {p['text']} | {p['score']:g} | {p['earned']:g} | {p['verdict_text']}"
                             f"{'（两遍有分歧）' if p['disputed'] else ''} | {p.get('answer_quote') or '—'} | {ev} |")
            for key in ("format", "expression"):
                if r.get(key):
                    lines.append(f"\n{r[key]['label']}：{r[key]['earned']:g}/{r[key]['score']:g}——{r[key].get('reason', '')}")
        else:
            lines.append(f"**档次**：{r['level']}")
            for d in r["dimensions"]:
                lines.append(f"- {d['name']}：{d['level']}{'（两遍有分歧）' if d['disputed'] else ''}——{d['reason']}"
                             + (f"（原文：「{d['quote']}」）" if d.get("quote") else ""))
        if r.get("comment"):
            lines.append(f"\n阅卷人一句话：{r['comment']}")
        for n in r.get("notes") or []:
            lines.append(f"- 提醒：{n}")
        if q.get("reference_answer"):
            lines += ["", "**参考答案**：", "", q["reference_answer"]]
    return "\n".join(lines) + "\n"


def grade_submission(conn, submission_id: int) -> dict:
    sub = conn.execute("SELECT * FROM shenlun_submissions WHERE id=?", (submission_id,)).fetchone()
    if sub is None:
        raise ValueError(f"没有这次交卷：{submission_id}")
    sub = dict(sub)
    paper = load_paper(conn, sub["paper_id"])
    attempts = [dict(r) for r in conn.execute(
        "SELECT a.* FROM shenlun_attempts a JOIN shenlun_questions q ON q.id=a.question_id"
        " WHERE a.submission_id=? ORDER BY q.no", (submission_id,))]
    if not attempts:
        raise ValueError("这次交卷里没有作答")
    _, params = load_standard()
    _set(conn, "shenlun_submissions", submission_id, status="grading", error=None)
    for a in attempts:
        _set(conn, "shenlun_attempts", a["id"], status="grading", error=None)
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]

    def work(attempt: dict):
        local = connect(db_path)  # sqlite 连接不跨线程
        try:
            return grade_attempt(local, attempt["id"], params), None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(work, attempts))
    questions = {q["id"]: q for q in paper["questions"]}
    graded, failed = [], []
    for a, (res, err) in zip(attempts, outcomes):
        if res is None:
            failed.append((questions[a["question_id"]], err))
            _set(conn, "shenlun_attempts", a["id"], status="failed", error=err[:1000])
            continue
        graded.append(res)
        _set(conn, "shenlun_attempts", a["id"], grading=json.dumps(res["grading"], ensure_ascii=False),
             score=res["score"], max_score=res["max_score"], answer_text=res["transcript"],
             word_count=res["word_count"], status="graded", error=None)
    if not graded:
        msg = "；".join(f"第{q['no']}题：{e[:120]}" for q, e in failed)
        _set(conn, "shenlun_submissions", submission_id, status="failed", error=msg[:1000])
        raise RuntimeError("所有题都没评出来：" + msg)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    report = REVIEW_DIR / f"submission-{submission_id}.md"
    report.write_text(_report(paper, sub, graded, failed), encoding="utf-8")
    score = sum(g["score"] for g in graded)
    full = sum(g["max_score"] for g in graded)
    _set(conn, "shenlun_submissions", submission_id, status="graded", score=score, max_score=full,
         report_path=str(report.relative_to(ROOT)),
         error=("；".join(f"第{q['no']}题评分失败：{e[:120]}" for q, e in failed) or None))
    return {"submission_id": submission_id, "score": score, "max_score": full, "graded": len(graded),
            "failed": [{"no": q["no"], "error": e[:300]} for q, e in failed], "report_path": str(report)}


def seal(conn, submission_id: int, comment: str) -> dict:
    sub = conn.execute("SELECT status FROM shenlun_submissions WHERE id=?", (submission_id,)).fetchone()
    if sub is None:
        raise ValueError(f"没有这次交卷：{submission_id}")
    if sub["status"] not in ("graded", "reviewed"):
        raise ValueError("还没评分，先运行 grade --submission")
    path = Path(comment).expanduser().resolve()
    if not path.is_file() or path.stat().st_size < 50:
        raise ValueError(f"点评文件不存在或太短：{path}")
    try:
        rel = str(path.relative_to(ROOT))
    except ValueError:
        rel = str(path)
    _set(conn, "shenlun_submissions", submission_id, status="reviewed", comment_path=rel)
    return {"submission_id": submission_id, "comment_path": rel}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="申论交卷评分（照片直接交给模型）")
    parser.add_argument("command", choices=["grade", "seal"])
    parser.add_argument("--submission", type=int)
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--comment", help="seal 用：Hermes 点评文件路径")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        if args.command == "seal":
            if not args.submission or not args.comment:
                raise ValueError("seal 需要 --submission 和 --comment")
            out = seal(conn, args.submission, args.comment)
        elif args.submission:
            out = grade_submission(conn, args.submission)
        elif args.attempt:
            _, params = load_standard()
            res = grade_attempt(conn, args.attempt, params)
            _set(conn, "shenlun_attempts", args.attempt, grading=json.dumps(res["grading"], ensure_ascii=False),
                 score=res["score"], max_score=res["max_score"], answer_text=res["transcript"],
                 word_count=res["word_count"], status="graded", error=None)
            out = {"attempt_id": args.attempt, "score": res["score"], "max_score": res["max_score"]}
        else:
            raise ValueError("需要 --submission 或 --attempt")
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)[:1000], "message": f"失败：{str(exc)[:600]}"},
                         ensure_ascii=False))
        return 1
    print(json.dumps({"status": "success", **out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

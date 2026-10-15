#!/usr/bin/env python3
"""申论作答批改：照片直接交给模型（多模态），不单独做识别。网页上传后由服务端在后台调用，也可手动跑。

  grade --attempt ID

小题按要点表采点，两遍独立批改：每遍先把照片里的答案逐字转写进 transcript，再采点；
answer_quote 由程序到这一遍的 transcript 里核对，对不上的按未命中计。分数由程序相加，
两遍判定不一致的要点取低分并标出「有分歧」。作文按立意、结构、论证、语言四个维度评档次。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shenlun_common import (ESSAY_DIMENSIONS, ESSAY_LEVELS, UPLOAD_DIR, call, connect, contains,  # noqa: E402
                            image_part, load_paper, materials_text, word_count)

READ_RULES = """考生答案在照片里（按顺序拍的答题卡）。先在 transcript 里逐字转写答案：保留错别字和病句，不纠正、不润色、不补写；
看不清的字写 □；划掉的字、题号、格子线、答题卡印刷文字不转写。之后的判定只依据你转写出来的内容。"""

POINT_SYSTEM = """你是广东省考申论阅卷人，严格按要点表采点给分，不凭整体印象打分。
{read}
对每个要点判定 verdict：
- hit：考生答出了这个意思（同义表述、换个说法都算），表述基本完整；
- partial：只答到一部分、或表述含糊到阅卷人要猜；
- miss：没答到，或只有与材料无关的空话套话。
answer_quote：命中或部分命中时，逐字摘录考生答案里对应的那句（8 到 60 字，一字不改）；miss 写空字符串。
一句话只能支撑它真正表达的要点，不能一句话兼得多个不同要点。
expression：条理与语言，level 取 A（分条清楚、语言规范）/B（基本清楚）/C（混乱或口语化严重）。
format（只在给了格式要点时判）：每项 hit 或 miss。
只输出 JSON：{{"transcript":"考生答案全文","points":[{{"id":"P1","verdict":"hit","answer_quote":"...","reason":"..."}}],
"format":[{{"id":"F1","verdict":"hit","reason":"..."}}],"expression":{{"level":"A","reason":"..."}},"comment":"一句话总评"}}"""

ESSAY_SYSTEM = """你是广东省考申论大作文阅卷人。
{read}
按四个维度分别评档：立意、结构、论证、语言，每个维度给 一类 / 二类 / 三类 / 四类 之一：
- 立意：是否扣住题目要求和材料主旨（偏离主题最高三类，完全偏题四类）；
- 结构：标题、开头、分论点、结尾是否完整清晰；
- 论证：分论点是否有材料或实例支撑、分析是否深入，有没有只罗列口号；
- 语言：是否规范流畅、符合机关文风。
每个维度 reason 写依据，quote 逐字摘录作文里最能说明问题的一句（8 到 60 字）。
must_cover_hit：列出作文实际论述到的论证方向编号。
只输出 JSON：{{"transcript":"作文全文","dimensions":[{{"name":"立意","level":"二类","reason":"...","quote":"..."}}],
"off_topic":false,"must_cover_hit":["T1"],"comment":"一句话总评"}}"""

TYPED = "考生答案是直接输入的文字，transcript 原样抄写下面「考生答案」即可。"
LEVEL_NAMES = ("一类", "二类", "三类", "四类")
VERDICT_TEXT = {"hit": "命中", "partial": "部分命中", "miss": "未命中"}


def _attempt(conn, attempt_id: int):
    row = conn.execute("SELECT * FROM shenlun_attempts WHERE id=?", (attempt_id,)).fetchone()
    if row is None:
        raise ValueError(f"没有这次作答：{attempt_id}")
    q = conn.execute("SELECT paper_id FROM shenlun_questions WHERE id=?", (row["question_id"],)).fetchone()
    paper = load_paper(conn, q["paper_id"])
    question = next(x for x in paper["questions"] if x["id"] == row["question_id"])
    return row, paper, question


def _set(conn, attempt_id: int, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn:
        conn.execute(f"UPDATE shenlun_attempts SET {cols}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (*fields.values(), attempt_id))


class Answer:
    """考生答案：照片（交给模型转写）或直接输入的文字。"""

    def __init__(self, images: list[str], text: str):
        self.images, self.text = images, text.strip()
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


# ---------------------------------------------------------------- 小题采点
def _verify(verdict: str, quote: str, transcript: str) -> tuple[str, str]:
    if verdict not in ("hit", "partial"):
        return "miss", ""
    if not contains(transcript, quote):
        return "miss", "阅卷人引的句子在答案里找不到，按未命中计"
    return verdict, ""


def grade_points(question: dict, paper: dict, answer: Answer, audit: Path) -> dict:
    rubric = question["rubric"]
    points = rubric["points"]

    def one_pass(order: list[dict], temperature: float) -> dict:
        prefix = (materials_text(paper["materials"], question["requirements"].get("material_ids"))
                  + f"\n\n设问：{question['prompt']}\n\n要点表：\n"
                  + json.dumps([{k: p[k] for k in ("id", "text", "score")} for p in order], ensure_ascii=False)
                  + ("\n\n格式要点：\n" + json.dumps(rubric.get("format_points"), ensure_ascii=False)
                     if rubric.get("format_points") else ""))
        return call(POINT_SYSTEM.format(read=answer.read_rules), answer.parts(prefix), temperature=temperature,
                    audit=audit)

    # 第二遍倒序给要点，减少排在前面的要点占便宜
    passes = [one_pass(points, 0.0), one_pass(list(reversed(points)), 0.3)]
    texts = [answer.transcript(res) for res in passes]
    out_points = []
    for p in points:
        judged = []
        for res, text in zip(passes, texts):
            hit = next((x for x in res.get("points") or [] if x.get("id") == p["id"]), {})
            verdict, note = _verify(str(hit.get("verdict") or "miss"), str(hit.get("answer_quote") or ""), text)
            earned = float(p["score"]) if verdict == "hit" else (round(float(p["score"])) / 2 if verdict == "partial" else 0.0)
            judged.append({"verdict": verdict, "earned": earned, "quote": hit.get("answer_quote") or "",
                           "reason": hit.get("reason") or "", "note": note})
        low = min(judged, key=lambda j: j["earned"])
        out_points.append({"id": p["id"], "text": p["text"], "score": float(p["score"]), "earned": low["earned"],
                           "verdict": low["verdict"], "verdict_text": VERDICT_TEXT[low["verdict"]],
                           "answer_quote": low["quote"] if low["verdict"] != "miss" else "",
                           "reason": low["reason"], "note": low["note"],
                           "disputed": len({j["verdict"] for j in judged}) > 1,
                           "passes": [{"verdict": j["verdict"], "reason": j["reason"]} for j in judged],
                           "evidence": p.get("evidence") or []})
    result = {"kind": "points", "points": out_points, "transcript": texts[0], "notes": []}
    fmt = rubric.get("format_points") or []
    if fmt:
        got = []
        for f in fmt:
            vs = [next((x for x in res.get("format") or [] if x.get("id") == f["id"]), {}) for res in passes]
            got.append(float(f["score"]) if all(v.get("verdict") == "hit" for v in vs) else 0.0)
        missed = [f["text"] for f, g in zip(fmt, got) if not g]
        result["format"] = {"label": "格式分", "score": sum(float(f["score"]) for f in fmt), "earned": sum(got),
                            "reason": "缺：" + "、".join(missed) if missed else "格式要素齐全"}
    expr = float(rubric.get("expression_score") or 0)
    if expr:
        levels = [str((res.get("expression") or {}).get("level") or "C").upper()[:1] for res in passes]
        worst = max(levels, key="ABC".index) if all(lv in "ABC" for lv in levels) else "C"
        result["expression"] = {"label": "表述分", "score": expr, "earned": {"A": expr, "B": expr / 2, "C": 0.0}[worst],
                                "reason": (passes[0].get("expression") or {}).get("reason", "")}
    result["earned"] = (sum(p["earned"] for p in out_points)
                        + sum((result.get(k) or {}).get("earned", 0) for k in ("format", "expression")))
    result["comment"] = passes[0].get("comment") or ""
    disputed = [p["id"] for p in out_points if p["disputed"]]
    if disputed:
        result["notes"].append(f"两遍批改对 {'、'.join(disputed)} 判得不一样，已按低的计分，可以对照材料自己看一下")
    return result


# ---------------------------------------------------------------- 大作文
def grade_essay(question: dict, paper: dict, answer: Answer, audit: Path) -> dict:
    rubric = question["rubric"]
    prefix = (materials_text(paper["materials"], with_ids=False) + f"\n\n题目：{question['prompt']}\n\n命题立意："
              + str(rubric.get("theme")) + "\n论证方向：" + json.dumps(rubric.get("must_cover") or [], ensure_ascii=False)
              + "\n偏题标准：" + str(rubric.get("off_topic") or ""))
    system = ESSAY_SYSTEM.format(read=answer.read_rules)
    passes = [call(system, answer.parts(prefix), temperature=0.0, audit=audit),
              call(system, answer.parts(prefix), temperature=0.3, audit=audit)]
    texts = [answer.transcript(res) for res in passes]
    dims, notes = [], []
    for name in ESSAY_DIMENSIONS:
        judged = []
        for res, text in zip(passes, texts):
            d = next((x for x in res.get("dimensions") or [] if x.get("name") == name), {})
            level = str(d.get("level") or "四类")[:2]
            level = level if level in LEVEL_NAMES else "四类"
            quote = str(d.get("quote") or "")
            judged.append({"level": level, "reason": d.get("reason") or "", "quote": quote if contains(text, quote) else ""})
        low = max(judged, key=lambda j: LEVEL_NAMES.index(j["level"]))
        dims.append({"name": name, **low, "disputed": len({j["level"] for j in judged}) > 1})
    ranks = [LEVEL_NAMES.index(d["level"]) for d in dims]
    overall = max(ranks[0], round(sum(ranks) / len(ranks)))  # 立意定上限
    if any(res.get("off_topic") for res in passes):
        overall = 3
        notes.append("阅卷人判定偏题，按四类文计")
    name, lo, hi = ESSAY_LEVELS[overall]
    full = float(question["requirements"]["score"])
    words = word_count(texts[0])
    wmin = question["requirements"].get("words_min")
    if wmin and words < int(wmin):
        notes.append(f"全文约 {words} 字，少于 {wmin} 字的要求，考场上会扣分（本次未扣）")
    disputed = [d["name"] for d in dims if d["disputed"]]
    if disputed:
        notes.append(f"两遍批改对 {'、'.join(disputed)} 评得不一样，已按低的计")
    hits = sorted(set(passes[0].get("must_cover_hit") or []) & set(passes[1].get("must_cover_hit") or []))
    return {"kind": "essay", "level": name, "score": full, "earned": float(round(full * (lo + hi) / 2)),
            "dimensions": dims, "must_cover_hit": hits, "transcript": texts[0],
            "comment": passes[0].get("comment") or "", "notes": notes}


def run_grade(conn, attempt_id: int) -> dict:
    row, paper, question = _attempt(conn, attempt_id)
    answer = Answer(json.loads(row["images"] or "[]"), row["answer_text"] or "")
    audit = UPLOAD_DIR / str(attempt_id) / "audit"
    if question["rubric"].get("kind") == "essay":
        result = grade_essay(question, paper, answer, audit)
    else:
        result = grade_points(question, paper, answer, audit)
    words = word_count(result["transcript"])
    wmax = question["requirements"].get("words_max")
    if wmax and question["qtype"] != "文章写作" and words > int(wmax):
        result["notes"].append(f"答案约 {words} 字，超出 {wmax} 字的限制；考场上超出部分可能不计分（本次未扣）")
    full = float(question["requirements"]["score"])
    _set(conn, attempt_id, grading=json.dumps(result, ensure_ascii=False), score=result["earned"], max_score=full,
         answer_text=result["transcript"], word_count=words, status="graded", error=None)
    return {"score": result["earned"], "max_score": full}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="申论作答批改（照片直接交给模型）")
    parser.add_argument("command", choices=["grade"])
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        _set(conn, args.attempt, status="grading", error=None)
        out = run_grade(conn, args.attempt)
    except Exception as exc:  # noqa: BLE001
        _set(conn, args.attempt, status="failed", error=str(exc)[:1000])
        print(json.dumps({"status": "error", "error": str(exc)[:1000]}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "success", **out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

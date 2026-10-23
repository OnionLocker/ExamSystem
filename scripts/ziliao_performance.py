#!/usr/bin/env python3
"""资料分析做题表现 → 整套出题的题型/细分考法系数。

只看近 N 天的首次作答（重做旧题、几秒就翻过的空题不算），不用遗忘曲线。
AI 整套题能从批次目录的 M0x-plan.json 反查到题型（kind）与细分考法；其他资料分析题只计入考点。
正确率先向 75% 收缩再换算系数：错得多的 >1，稳定全对的 <1，样本少时接近 1。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "exam.db"
PAPER_DIR = ROOT / "data" / "manual-ziliao-agent-paper"
WINDOW_DAYS = 60
PRIOR_ACC, PRIOR_N = 0.75, 4
TARGET_ACC, SLOPE = 0.75, 2.5
BOOST_MIN, BOOST_MAX = 0.6, 2.0
MIN_KIND_N, MIN_VARIANT_N = 3, 2
SKIP_SECONDS = 5
SLOT_RE = re.compile(r"-(M0[1-4])-Q([1-5])$")


def boost_of(n: int, correct: int) -> float:
    acc = (correct + PRIOR_ACC * PRIOR_N) / (n + PRIOR_N)
    return round(min(BOOST_MAX, max(BOOST_MIN, 1 + SLOPE * (TARGET_ACC - acc))), 3)


def _plan_slots(batch_id: str, cache: dict, paper_dir: Path) -> dict:
    if batch_id not in cache:
        slots = {}
        for plan in sorted((paper_dir / batch_id).glob("M0[1-4]-plan.json")):
            try:
                data = json.loads(plan.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for index, slot in enumerate(data.get("slots") or [], 1):
                slots[(data.get("id") or plan.stem[:3], index)] = slot
        cache[batch_id] = slots
    return cache[batch_id]


def collect(conn: sqlite3.Connection, today: dt.date | None = None, days: int = WINDOW_DAYS,
            paper_dir: Path = PAPER_DIR) -> dict:
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=days)).isoformat()
    from ziliao_tracks import judge_mix_id
    stats = {"tag": defaultdict(lambda: [0, 0]), "kind": defaultdict(lambda: [0, 0]),
             "variant": defaultdict(lambda: [0, 0]), "judge_mix": defaultdict(lambda: [0, 0])}
    seen, cache, answered = set(), {}, 0
    rows = conn.execute(
        """SELECT pa.question_id, pa.user_answer, pa.is_correct, pa.time_spent_sec, pa.answered_at,
                  q.tags, q.external_id, q.batch_id
             FROM practice_answers pa JOIN questions q ON q.id = pa.question_id
            WHERE q.category = '资料分析'
            ORDER BY pa.answered_at, pa.id""")
    for qid, answer, correct, seconds, when, raw_tags, external_id, batch_id in rows:
        first = qid not in seen
        seen.add(qid)
        if not first or str(when or "")[:10] < since:
            continue
        if not str(answer or "").strip() and (seconds or 0) < SKIP_SECONDS:
            continue
        ok = 1 if correct else 0
        answered += 1
        try:
            tag = (json.loads(raw_tags or "[]") or [""])[0]
        except (TypeError, ValueError):
            tag = ""
        matched = SLOT_RE.search(str(external_id or ""))
        slot = (_plan_slots(batch_id, cache, paper_dir).get((matched[1], int(matched[2])))
                if matched and batch_id else None)
        # 综合分析每套固定 4 题、不参与轮转，计入考点会把同标签的计数/排序误判成弱项
        if tag and not (slot and slot.get("kind") == "judge"):
            stats["tag"][tag][0] += 1
            stats["tag"][tag][1] += ok
        if slot:
            mix = judge_mix_id(slot) if slot.get("kind") == "judge" else None
            if mix:
                stats["judge_mix"][mix][0] += 1
                stats["judge_mix"][mix][1] += ok
            if slot.get("kind"):
                stats["kind"][slot["kind"]][0] += 1
                stats["kind"][slot["kind"]][1] += ok
                if slot.get("kaofa_variant"):
                    key = f"{slot.get('tag')}|{slot['kaofa_variant']}"
                    stats["variant"][key][0] += 1
                    stats["variant"][key][1] += ok
    return {"window_days": days, "answered": answered,
            **{name: {k: {"n": v[0], "correct": v[1]} for k, v in table.items()} for name, table in stats.items()}}


def mix_boosts(stats: dict) -> dict:
    """综合分析考查组合系数：各组合样本够用各自正确率，否则用综合分析整体正确率。"""
    from ziliao_tracks import GD_JUDGE_MIXES
    judge = stats["kind"].get("judge")
    result = {}
    for mix in GD_JUDGE_MIXES:
        own = stats.get("judge_mix", {}).get(mix["id"])
        base = own if own and own["n"] >= MIN_VARIANT_N else judge
        if base and base["n"]:
            result[mix["id"]] = boost_of(base["n"], base["correct"])
    return result


def boosts(stats: dict) -> tuple[dict, dict]:
    """题型系数：题型样本够用题型正确率，否则退回所属考点正确率。细分考法系数：样本够才调。"""
    from ziliao_tracks import KIND_SPECS, KIND_TAGS
    kind_boost = {}
    for kind in KIND_SPECS:
        own = stats["kind"].get(kind)
        base = own if own and own["n"] >= MIN_KIND_N else stats["tag"].get(KIND_TAGS.get(kind, ""))
        if base and base["n"]:
            kind_boost[kind] = boost_of(base["n"], base["correct"])
    variant_boost = {}
    for key, row in stats["variant"].items():
        if row["n"] >= MIN_VARIANT_N:
            tag, vid = key.split("|", 1)
            variant_boost[(tag, vid)] = boost_of(row["n"], row["correct"])
    return kind_boost, variant_boost


def adaptive_plan(db: Path = DB, today: dt.date | None = None, paper_dir: Path = PAPER_DIR) -> dict:
    if not Path(db).is_file():
        return {"stats": None, "kind_boost": {}, "variant_boost": {}, "mix_boost": {}}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    try:
        stats = collect(conn, today, paper_dir=paper_dir)
    finally:
        conn.close()
    kind_boost, variant_boost = boosts(stats)
    return {"stats": stats, "kind_boost": kind_boost, "variant_boost": variant_boost, "mix_boost": mix_boosts(stats)}


def summary(plan: dict) -> dict:
    from ziliao_tracks import KIND_LABELS
    stats = plan.get("stats") or {}
    kinds = sorted(plan.get("kind_boost", {}).items(), key=lambda kv: -kv[1])
    return {
        "answered": stats.get("answered", 0),
        "window_days": stats.get("window_days"),
        "kind_boost": {KIND_LABELS.get(k, k): v for k, v in kinds},
        "weak_variants": sorted(([f"{t.split('-')[-1]}·{v}", b] for (t, v), b in plan.get("variant_boost", {}).items()
                                 if b > 1), key=lambda x: -x[1])[:8],
        "judge": (stats.get("kind") or {}).get("judge"),
        "judge_mix": stats.get("judge_mix"),
        "judge_mix_boost": plan.get("mix_boost"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB)
    args = parser.parse_args()
    result = adaptive_plan(args.db)
    print(json.dumps({"summary": summary(result), "kind_stats": (result["stats"] or {}).get("kind"),
                      "tag_stats": (result["stats"] or {}).get("tag")}, ensure_ascii=False, indent=2))

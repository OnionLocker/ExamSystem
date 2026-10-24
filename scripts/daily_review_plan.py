#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日复习卷选点：按遗忘曲线、薄弱、用时和知识债给考点打分，配出当天的题。

只读作答记录（练题作答 + 录屏复盘的 exam 证据），不写画像。选中的考点、题量和
原因存进 daily_review_plans，练题页「考点预热」按 batch_id 读它。

预览明天会选哪些点（只读）：
  python3 scripts/daily_review_plan.py --module 数量关系 --date 2026-10-16
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from fenbi_taxonomy import fenbi_l3_of, fenbi_modules
from kaodian_profile import blank_weight
from kaodian_taxonomy import canonicalize, parse_tags
from scheduler_common import DB, TZ, local_today

# 每个模块一份口径：count 整卷题量；points 一天覆盖几个三级考点；per_point 单点题量上下限；
# target_seconds 考场单题预算，只用来算“慢”；must 优先分前几名必进。
POLICIES = {
    "数量关系": {
        "scope": "数量关系-数学运算",
        "count": 20,
        "points": (6, 10),
        "per_point": (1, 3),
        "target_seconds": 90,
        "must": 3,
    },
}

WEIGHTS = {"forget": 0.45, "weak": 0.25, "slow": 0.15, "debt": 0.15}
# 遗忘曲线用 FSRS 的幂函数形式：隔 S（稳定度，天）天时还记得 90%，之后衰减越来越慢。
# 解题方法不像单词那样几天就忘光，指数曲线会把一周没练算成“几乎全忘”。
FACTOR, DECAY = 19 / 81, -0.5
FIRST_STABILITY = (2.5, 1.0, 0.4)   # 第一次练完：正确率 ≥80% / 50–80% / <50%
STABILITY_RANGE = (0.4, 180.0)
RECENT = 15                 # 薄弱、用时只看最近这么多道首次作答
COOLDOWN_DAYS = 1           # 同族距上次 ≤1 天不当主攻：本卷最多 1 题
PLATEAU_CAP = 2             # 两轮新题没改善先换教法：本卷最多 2 题
FREQ_RANGE = (0.7, 1.3)

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_review_plans (
  batch_id   TEXT PRIMARY KEY,
  plan_date  TEXT NOT NULL,
  module     TEXT NOT NULL,
  plan_json  TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_daily_review_plans_day ON daily_review_plans(plan_date, module);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def save_plan(conn: sqlite3.Connection, batch_id: str, plan: dict) -> None:
    ensure_schema(conn)
    conn.execute(
        "INSERT OR REPLACE INTO daily_review_plans(batch_id, plan_date, module, plan_json) VALUES (?,?,?,?)",
        (batch_id, plan["plan_date"], plan["module"], json.dumps(plan, ensure_ascii=False)),
    )


def _tables(conn: sqlite3.Connection | None) -> set[str]:
    if conn is None:
        return set()
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _day(raw) -> dt.date | None:
    """库里的时间是 UTC 文本，按北京时间归到哪一天。"""
    try:
        value = dt.datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00").replace(" ", "T"))
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(TZ).date()


def _mmss(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def scope_points(scope: str) -> list[tuple[str, str]]:
    """scope（模块-一级）下的三级考点：(标签, 名称)，顺序同粉笔树。"""
    module, _, group_name = scope.partition("-")
    for mod in fenbi_modules():
        if mod["name"] != module:
            continue
        for group in mod.get("children") or []:
            if group["name"] == group_name:
                return [(f"{scope}-{leaf['name']}", leaf["name"]) for leaf in group.get("children") or []]
    return []


def alias_map(conn: sqlite3.Connection | None) -> dict[str, str]:
    if "kaodian_aliases" not in _tables(conn):
        return {}
    return {alias: canonical for alias, canonical in conn.execute("SELECT alias, canonical FROM kaodian_aliases")}


def load_attempts(conn, scope: str, aliases: dict[str, str]) -> dict[str, list[dict]]:
    """scope 内每个三级考点的作答，按时间排好。

    重做旧题（同一道题以前做过）标 repeat；几秒就翻过去的空题不算作答，久看后交白卷算错。
    """
    tables = _tables(conn)
    placed: dict[tuple, tuple | None] = {}

    def place(raw: str, category: str = "", sub: str = ""):
        key = (raw, category, sub)
        if key not in placed:
            tag = canonicalize(raw, category, sub, aliases=aliases)
            l3 = fenbi_l3_of(tag)
            placed[key] = (l3, tag) if l3.startswith(scope + "-") else None
        return placed[key]

    by_point: dict[str, list[dict]] = defaultdict(list)
    if {"practice_answers", "questions"} <= tables:
        seen: set[int] = set()
        for qid, answer, correct, seconds, when, raw_tags, category, sub in conn.execute(
            """SELECT pa.question_id, pa.user_answer, pa.is_correct, pa.time_spent_sec, pa.answered_at,
                      q.tags, q.category, q.sub_category
                 FROM practice_answers pa JOIN questions q ON q.id = pa.question_id
                ORDER BY pa.answered_at, pa.id"""
        ):
            repeat = qid in seen
            seen.add(qid)
            tags = parse_tags(raw_tags)
            spot = place(tags[0], category or "", sub or "") if tags else None
            day = _day(when)
            if not spot or day is None:
                continue
            seconds = int(seconds or 0)
            if not answer and blank_weight(seconds) == 0:
                continue
            by_point[spot[0]].append({"day": day, "correct": bool(answer) and bool(correct), "seconds": seconds,
                                      "repeat": repeat, "tag": spot[1], "raw": tags[0], "leaf": None})
    if "kaodian_events" in tables:
        for kaodian, correct, elapsed, when in conn.execute(
            "SELECT kaodian, is_correct, elapsed_ms, answered_at FROM kaodian_events "
            "WHERE evidence_type='exam' ORDER BY answered_at, id"
        ):
            spot = place(kaodian or "")
            day = _day(when)
            if spot and day is not None:
                by_point[spot[0]].append({"day": day, "correct": bool(correct), "seconds": int(elapsed or 0) // 1000,
                                          "repeat": False, "tag": spot[1], "raw": kaodian, "leaf": None})
    for items in by_point.values():
        items.sort(key=lambda a: a["day"])
    return by_point


def load_flags(conn, scope: str, aliases: dict[str, str]) -> tuple[set[str], set[str]]:
    """未清的知识债（已确认学过之后的错）、两轮新题没改善：都按三级考点汇总。"""
    tables = _tables(conn)
    debts: set[str] = set()
    plateaus: set[str] = set()

    def l3_of(tag: str) -> str:
        l3 = fenbi_l3_of(canonicalize(tag or "", aliases=aliases))
        return l3 if l3.startswith(scope + "-") else ""

    if {"kaodian_debts", "kaodian_learning"} <= tables:
        for (tag,) in conn.execute(
            "SELECT d.kaodian FROM kaodian_debts d JOIN kaodian_learning l "
            "ON l.kaodian=d.kaodian AND l.status='learned' WHERE d.mastered=0"
        ):
            if l3 := l3_of(tag):
                debts.add(l3)
    if "kaodian_profile" in tables and "assessment_json" in {r[1] for r in conn.execute("PRAGMA table_info(kaodian_profile)")}:
        for tag, raw in conn.execute("SELECT kaodian, assessment_json FROM kaodian_profile WHERE assessment_json IS NOT NULL"):
            try:
                history = (json.loads(raw) or {}).get("history") or {}
            except (TypeError, ValueError):
                continue
            if history.get("plateau") and (l3 := l3_of(tag)):
                plateaus.add(l3)
    return debts, plateaus


def exam_frequency(conn, scope: str, points: list[tuple[str, str]], aliases: dict[str, str]) -> dict[str, float]:
    """考频系数：题库里的广东省考真题每道记 1，其他省份记 0.5，各加 1 平滑后线性折到 0.7–1.3。"""
    weight = {tag: 1.0 for tag, _ in points}
    module, _, group = scope.partition("-")
    if "reference_questions" in _tables(conn):
        for raw_tags, source in conn.execute("SELECT tags, source FROM reference_questions WHERE category=?", (module,)):
            tags = parse_tags(raw_tags) or ([str(raw_tags).strip()] if raw_tags and not str(raw_tags).startswith("[") else [])
            if not tags:
                continue
            l3 = fenbi_l3_of(canonicalize(tags[0], module, group, aliases=aliases))
            if l3 in weight:
                weight[l3] += 1.0 if "广东" in str(source or "") else 0.5
    low, high = min(weight.values(), default=1.0), max(weight.values(), default=1.0)
    if high == low:
        return {tag: 1.0 for tag in weight}
    span = FREQ_RANGE[1] - FREQ_RANGE[0]
    return {tag: round(FREQ_RANGE[0] + span * (value - low) / (high - low), 2) for tag, value in weight.items()}


def recall(gap: float, stability: float) -> float:
    """隔 gap 天的估计保持率。"""
    return (1 + FACTOR * gap / stability) ** DECAY


def stability_of(attempts: list[dict]) -> tuple[float | None, dt.date | None]:
    """按天回放复习记录（FSRS 的简化版），返回当前稳定度（天）和最后一次练的日期。

    第一次练完按正确率取 2.5 / 1 / 0.4 天；之后答得好（≥80%）乘 1.5–4.5，当时忘得越多
    还答对，涨得越多；答得一般（50–80%）乘 1.1–2.1；答崩（<50%）乘 0.4。
    当天只有重做旧题时，涨跌都减半。
    """
    days: dict[dt.date, dict[str, list[bool]]] = defaultdict(lambda: {"first": [], "repeat": []})
    for item in attempts:
        days[item["day"]]["repeat" if item["repeat"] else "first"].append(item["correct"])
    stability, last = None, None
    for day in sorted(days):
        first, repeat = days[day]["first"], days[day]["repeat"]
        marks = first or repeat
        accuracy = sum(marks) / len(marks)
        tier = 0 if accuracy >= 0.8 else 1 if accuracy >= 0.5 else 2
        if stability is None:
            stability = FIRST_STABILITY[tier]
        else:
            forgotten = 1 - recall((day - last).days, stability)
            gain = (1.5 + 3 * forgotten, 1.1 + forgotten, 0.4)[tier]
            if not first:
                gain = 1 + (gain - 1) / 2
            stability = min(STABILITY_RANGE[1], max(STABILITY_RANGE[0], stability * gain))
        last = day
    return stability, last


def retention_of(attempts: list[dict], today: dt.date) -> tuple[float, int | None, float | None]:
    """估计保持率、距上次天数、稳定度；没练过保持率记 0。"""
    stability, last = stability_of(attempts)
    if stability is None:
        return 0.0, None, None
    gap = max(0, (today - last).days)
    return recall(gap, stability), gap, stability


def recent_record(attempts: list[dict]) -> tuple[int, int, float, float | None]:
    """最近首次作答：题数、对数、平滑正确率（先验 75%）、答对题的中位用时。"""
    firsts = [item for item in attempts if not item["repeat"]][-RECENT:]
    correct = sum(item["correct"] for item in firsts)
    times = [item["seconds"] for item in firsts if item["correct"] and item["seconds"] > 0]
    median = statistics.median(times) if len(times) >= 2 else None
    return len(firsts), correct, (correct + 1.5) / (len(firsts) + 2), median


def point_state(tag: str, title: str, attempts: list[dict], today: dt.date, policy: dict,
                freq: float, debt: bool, plateau: bool) -> dict:
    retention, gap, stability = retention_of(attempts, today)
    n, correct, accuracy, median = recent_record(attempts)
    target = policy["target_seconds"]
    parts = {
        "forget": 1 - retention,
        "weak": _clamp((0.9 - accuracy) / 0.5),
        "slow": _clamp(math.log2(median / target) / 2) if median else 0.3,
        "debt": 1.0 if debt else 0.0,
    }
    priority = freq * sum(WEIGHTS[key] * value for key, value in parts.items())
    if gap is not None and gap <= COOLDOWN_DAYS:
        cap = 1
    elif plateau:
        cap = PLATEAU_CAP
    else:
        cap = policy["per_point"][1]
    return {
        "tag": tag, "title": title, "priority": round(priority, 4), "freq": freq,
        "retention": round(retention, 3), "stability": round(stability, 1) if stability else None, "days_since": gap,
        "recent": {"n": n, "correct": correct}, "accuracy": round(accuracy, 3),
        "median_seconds": round(median) if median else None, "debt": debt, "plateau": plateau,
        "parts": {key: round(value, 3) for key, value in parts.items()}, "cap": cap,
    }


def weighted_order(states: list[dict], rng: random.Random) -> list[dict]:
    """按优先分平方加权的随机排序（Efraimidis–Spirakis：key = u^(1/w) 从大到小）。"""
    return sorted(states, key=lambda s: -(rng.random() ** (1 / max(s["priority"] ** 2, 1e-9))))


def choose(states: list[dict], policy: dict, rng: random.Random) -> list[dict]:
    """优先分前 must 名必进；其余先在“到期”的点（不低于榜首一半）里加权随机，不够再从剩下的补。

    随机只在该复习的点之间发生：每天组合不同，但不会抽中刚练过、明显不急的点。
    """
    ranked = sorted(states, key=lambda s: (-s["priority"], s["tag"]))
    must = ranked[: policy["must"]]
    top = ranked[0]["priority"] if ranked else 0
    due = [s for s in ranked[policy["must"]:] if s["priority"] >= 0.5 * top]
    rest = [s for s in ranked[policy["must"]:] if s["priority"] < 0.5 * top]
    queue = must + weighted_order(due, rng) + weighted_order(rest, rng)
    low, high = policy["points"]
    chosen = queue[: min(len(queue), max(low, min(high, len(must) + len(due))))]
    while sum(s["cap"] for s in chosen) < policy["count"] and len(chosen) < len(queue):
        chosen.append(queue[len(chosen)])
    for state in chosen:
        state["must"] = state in must
    return chosen


def allocate(chosen: list[dict], total: int, rng: random.Random) -> dict[str, int]:
    """每点先 1 题，余下按优先分做圣拉古分配（P/(2n+1) 最大者得下一题），不超过各点上限。"""
    counts = {s["tag"]: 1 for s in chosen}
    tie = {s["tag"]: rng.random() for s in chosen}
    left = total - len(chosen)
    while left > 0:
        open_points = [s for s in chosen if counts[s["tag"]] < s["cap"]]
        if not open_points:
            break
        best = max(open_points, key=lambda s: (s["priority"] / (2 * counts[s["tag"]] + 1), tie[s["tag"]]))
        counts[best["tag"]] += 1
        left -= 1
    return counts


def spread(attempts: list[dict], leaves: list[dict], count: int, today: dt.date, rng: random.Random) -> list[dict]:
    """一个考点的题分到子考法：忘得多、做得差、没练过的先上，同一子考法尽量不重复。"""
    scored = []
    for leaf in leaves:
        items = [a for a in attempts if a["leaf"] == leaf["tag"]]
        retention, _gap, _stability = retention_of(items, today)
        _n, _c, accuracy, _median = recent_record(items)
        score = 0.6 * (1 - retention) + 0.4 * _clamp((0.9 - accuracy) / 0.5) + 0.05 * rng.random()
        scored.append({"tag": leaf["tag"], "title": leaf["title"], "score": score, "count": 0})
    for _ in range(count):
        best = max(scored, key=lambda leaf: leaf["score"] / (2 * leaf["count"] + 1))
        best["count"] += 1
    return [{"tag": leaf["tag"], "title": leaf["title"], "count": leaf["count"]} for leaf in scored if leaf["count"]]


def interleave(items: list[dict], rng: random.Random) -> list[dict]:
    """题目顺序打散：同一考点尽量不连着出，考场第一步就是认出这是什么题。"""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        buckets[item["point"]].append(item)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    ordered, previous = [], None
    while any(buckets.values()):
        live = sorted(tag for tag, bucket in buckets.items() if bucket)
        candidates = [tag for tag in live if tag != previous] or live
        most = max(len(buckets[tag]) for tag in candidates)
        pick = rng.choice([tag for tag in candidates if len(buckets[tag]) == most])
        ordered.append(buckets[pick].pop())
        previous = pick
    return ordered


def reason_of(state: dict, policy: dict) -> str:
    gap = state["days_since"]
    if gap is None:
        head = "还没有作答记录"
    elif gap == 0:
        head = "今天练过，只放 1 题"
    elif gap == 1:
        head = "昨天练过，只放 1 题"
    else:
        head = f"{gap} 天没练，估计还记得 {round(state['retention'] * 100)}%"
    extra = []
    if state["debt"]:
        extra.append("知识债未清")
    if state["plateau"]:
        extra.append("两轮新题没改善，先少量")
    n, correct = state["recent"]["n"], state["recent"]["correct"]
    if n and correct / n < 0.75:
        extra.append(f"最近 {n} 题对 {correct}")
    elif state["median_seconds"] and state["median_seconds"] >= policy["target_seconds"] * 1.5:
        extra.append(f"答对中位 {_mmss(state['median_seconds'])}")
    return "；".join([head, *extra[:2]])


def content_leaves(module: str, tags: list[str]) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """知识点页当前的末级子考法（和出题用同一份目录）；以及旧标签/别名 → 子考法。"""
    from quiz_scope import catalog, scope_slots

    nodes = catalog()
    leaves: dict[str, list[dict]] = {}
    leaf_of: dict[str, str] = {}
    for tag in tags:
        try:
            slots = scope_slots(tag, 1, module, nodes=nodes, all_leaves=True)
        except ValueError:
            slots = []
        leaves[tag] = [{"tag": s["tag"], "title": s.get("display_title") or s["tag"].rsplit("-", 1)[-1]} for s in slots]
        for slot in slots:
            leaf_of[slot["tag"]] = slot["tag"]
            for alias in (nodes.get(slot["tag"]) or {}).get("aliases") or []:
                leaf_of.setdefault(alias, slot["tag"])
    return leaves, leaf_of


def build_plan(conn, module: str, today: dt.date, *, leaves_loader=content_leaves, seed: str | None = None) -> dict:
    """算出当天的复习卷：选哪些考点、各几题、分到哪些子考法、什么难度、什么顺序。只读。"""
    policy = POLICIES[module]
    scope = policy["scope"]
    plan = {"version": 1, "module": module, "plan_date": str(today), "scope": scope, "count": 0,
            "params": {"target_seconds": policy["target_seconds"], "weights": WEIGHTS,
                       "first_stability": FIRST_STABILITY, "cooldown_days": COOLDOWN_DAYS},
            "points": [], "others": [], "slots": []}
    points = scope_points(scope)
    aliases = alias_map(conn)
    attempts = load_attempts(conn, scope, aliases) if conn is not None else {}
    eligible = [(tag, title) for tag, title in points if any(not a["repeat"] for a in attempts.get(tag, []))]
    if not eligible:
        plan["note"] = "还没有练过的考点，无从复习"
        return plan
    leaves, leaf_of = leaves_loader(module, [tag for tag, _ in eligible])
    for items in attempts.values():
        for item in items:
            item["leaf"] = leaf_of.get(item["tag"]) or leaf_of.get(item["raw"])
    freq = exam_frequency(conn, scope, points, aliases)
    debts, plateaus = load_flags(conn, scope, aliases)
    states = [point_state(tag, title, attempts[tag], today, policy, freq.get(tag, 1.0), tag in debts, tag in plateaus)
              for tag, title in eligible]
    rng = random.Random(seed or f"{today}:{module}")
    chosen = choose(states, policy, rng)
    counts = allocate(chosen, policy["count"], rng)
    items = []
    for state in chosen:
        state["count"] = counts[state["tag"]]
        state["difficulty"] = ("hard" if state["retention"] >= 0.6 and state["accuracy"] >= 0.85
                               and state["recent"]["n"] >= 5 else "auto")
        state["leaves"] = spread(attempts[state["tag"]], leaves.get(state["tag"]) or [{"tag": state["tag"], "title": state["title"]}],
                                 state["count"], today, rng)
        state["reason"] = reason_of(state, policy)
        for leaf in state["leaves"]:
            items.extend({"point": state["tag"], "tag": leaf["tag"], "difficulty": state["difficulty"]}
                         for _ in range(leaf["count"]))
    picked = {s["tag"] for s in chosen}
    plan["points"] = chosen
    plan["others"] = [{"tag": s["tag"], "title": s["title"], "priority": s["priority"], "reason": reason_of(s, policy)}
                      for s in sorted(states, key=lambda s: -s["priority"]) if s["tag"] not in picked]
    plan["slots"] = [{"tag": item["tag"], "count": 1, "difficulty": item["difficulty"]} for item in interleave(items, rng)]
    plan["count"] = len(plan["slots"])
    return plan


def render(plan: dict) -> str:
    if not plan["points"]:
        return f"{plan['module']} {plan['plan_date']}：{plan.get('note') or '没有可复习的考点'}"
    lines = [f"{plan['module']} {plan['plan_date']} 每日复习卷 {plan['count']} 题（{len(plan['points'])} 个考点）"]
    for index, point in enumerate(plan["points"], 1):
        flag = "［必选］" if point.get("must") else ""
        lines.append(f"{index:>2}. {point['title']} {point['count']} 题 {point['difficulty']}{flag}"
                     f"｜优先 {point['priority']:.2f}（考频 {point['freq']:.2f}）｜{point['reason']}")
        lines.append("    " + "、".join(f"{leaf['title']}×{leaf['count']}" for leaf in point["leaves"]))
    if plan["others"]:
        lines.append("没选上的（按优先分）：")
        lines.extend(f"  - {item['title']} {item['priority']:.2f}｜{item['reason']}" for item in plan["others"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="预览每日复习卷的选点（只读，不出题）")
    parser.add_argument("--module", default="数量关系", choices=sorted(POLICIES))
    parser.add_argument("--date", type=dt.date.fromisoformat, default=local_today())
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    os.environ["EXAM_DB"] = str(args.db)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) if args.db.is_file() else None
    try:
        plan = build_plan(conn, args.module, args.date)
    finally:
        if conn is not None:
            conn.close()
    print(json.dumps(plan, ensure_ascii=False, indent=2) if args.json else render(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

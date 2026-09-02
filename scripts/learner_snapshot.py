#!/usr/bin/env python3
"""生成供 Hermes/每日计划使用的精确学员快照。"""

from __future__ import annotations

import argparse
import random
import datetime as dt
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path

from kaodian_profile import recompute_mastery
from kaodian_taxonomy import (
    ZILIAO_ALT_PACK,
    ZILIAO_DEFAULT_PACK,
    ZILIAO_FINALE_TAGS,
    ZILIAO_FORMS,
    ZILIAO_LIGHT_TAGS,
    ZILIAO_QUESTION_TAGS,
    assign_ziliao_answers,
    canonicalize,
    kaodian_family,
    normalize_module,
    parse_tags,
)

from panduan_pack import (
    compact_kepui_pack,
    compact_panduan_pack,
    render_kepui_pack,
    render_panduan_pack,
    select_kepui_paper,
    select_panduan_paper,
)

ZILIAO_FOREIGN_MODULES = {
    "数量关系",
    "判断推理",
    "言语理解与表达",
    "政治理论",
    "常识判断",
    "科学推理",
}


DB = Path(os.environ.get("EXAM_DB") or Path(__file__).resolve().parents[1] / "data" / "exam.db")
TZ = dt.timezone(dt.timedelta(hours=8))
FAMILY_MAIN_COOLDOWN_DAYS = 1
SESSION_FAMILY_HINTS = (
    ("plzh", "数量关系-逢考必有的排列组合与概率"),
    ("date_cycle", "数量关系-有规律的周期循环与要算准的日期星期"),
    ("date-cycle", "数量关系-有规律的周期循环与要算准的日期星期"),
)


def days_since(value: str | None, today: dt.date) -> int | None:
    try:
        return max(0, (today - dt.date.fromisoformat(str(value)[:10])).days)
    except (TypeError, ValueError):
        return None


def compact_profile(row: sqlite3.Row, today: dt.date, family_last: dict[str, str] | None = None) -> dict:
    family = kaodian_family(row["kaodian"])
    return {
        "kaodian": row["kaodian"],
        "module": row["module"],
        "family": family,
        "attempts": row["attempts"],
        "accuracy": round(row["correct"] * 100 / row["attempts"]) if row["attempts"] else None,
        "mastery": row["mastery"],
        "confidence": row["mastery_confidence"] or 0,
        "streak": row["streak"],
        "avg_sec": round(row["total_ms"] / row["attempts"] / 1000) if row["attempts"] else 0,
        "days_since": days_since(row["last_seen"], today),
        "family_days_since": days_since((family_last or {}).get(family), today),
    }


def _touch_family(store: dict[str, str], family: str, when: str | None) -> None:
    day = str(when or "")[:10]
    if not family or len(day) < 10:
        return
    prev = store.get(family)
    if prev is None or day > prev:
        store[family] = day


def family_from_session_category(category: str) -> str | None:
    text = (category or "").lower()
    for needle, family in SESSION_FAMILY_HINTS:
        if needle in text:
            return family
    return None


def collect_family_last_seen(conn: sqlite3.Connection, alias_map: dict[str, str]) -> dict[str, str]:
    store: dict[str, str] = {}
    for row in conn.execute(
        "SELECT kaodian, last_seen FROM kaodian_profile WHERE attempts > 0"
    ):
        _touch_family(store, kaodian_family(row["kaodian"]), row["last_seen"])
    for row in conn.execute("SELECT kaodian, answered_at FROM kaodian_events"):
        raw = row["kaodian"] or ""
        canonical = alias_map.get(raw) or canonicalize(raw)
        _touch_family(store, kaodian_family(canonical), row["answered_at"])
    try:
        for row in conn.execute(
            """
            SELECT s.category, s.ended_at, q.tags, q.category AS q_category, q.sub_category
              FROM practice_answers pa
              JOIN practice_sessions s ON s.id = pa.session_id
              LEFT JOIN questions q ON q.id = pa.question_id
             WHERE s.ended_at IS NOT NULL
            """
        ):
            when = row["ended_at"]
            tags = parse_tags(row["tags"])
            if tags:
                for tag in tags:
                    canonical = alias_map.get(tag) or canonicalize(
                        tag, row["q_category"] or "", row["sub_category"] or ""
                    )
                    _touch_family(store, kaodian_family(canonical), when)
            else:
                _touch_family(store, family_from_session_category(row["category"]) or "", when)
    except sqlite3.OperationalError:
        pass
    return store


def family_too_recent(row: dict) -> bool:
    gap = row.get("family_days_since")
    return gap is not None and gap <= FAMILY_MAIN_COOLDOWN_DAYS


def build_snapshot(conn: sqlite3.Connection) -> dict:
    conn.row_factory = sqlite3.Row
    recompute_mastery(conn)
    conn.commit()
    now = dt.datetime.now(TZ)
    today = now.date()
    alias_map = {
        row["alias"]: row["canonical"]
        for row in conn.execute("SELECT alias,canonical FROM kaodian_aliases")
    }
    family_last = collect_family_last_seen(conn, alias_map)

    profiles = [
        compact_profile(row, today, family_last)
        for row in conn.execute(
            """
            SELECT kaodian,module,subtype,attempts,correct,total_ms,last_seen,
                   streak,mastery,mastery_confidence,mastery_samples
              FROM kaodian_profile
             WHERE attempts > 0
            """
        )
    ]
    reliable = [row for row in profiles if row["confidence"] >= 40]
    weaknesses = sorted(
        (row for row in reliable if (row["mastery"] or 50) < 60 or row["streak"] <= -2),
        key=lambda row: (row["mastery"] or 50, row["streak"], -row["confidence"]),
    )
    strengths = sorted(
        (row for row in reliable if (row["mastery"] or 0) >= 70 and row["streak"] >= 2),
        key=lambda row: (-(row["mastery"] or 0), -row["confidence"]),
    )
    needs_measurement = sorted(
        (row for row in profiles if row["confidence"] < 40),
        key=lambda row: (-row["attempts"], row["mastery"] or 50),
    )
    overdue = sorted(
        (
            row for row in profiles
            if row["days_since"] is not None
            and row["days_since"] >= 14
            and row["confidence"] >= 25
        ),
        key=lambda row: (-row["days_since"], row["mastery"] or 50),
    )

    recent_sessions = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id,category,total,correct,duration_sec,ended_at
              FROM practice_sessions
             WHERE ended_at IS NOT NULL
             ORDER BY id DESC LIMIT 5
            """
        )
    ]
    for row in recent_sessions:
        row["accuracy"] = round(row["correct"] * 100 / row["total"]) if row["total"] else 0

    mistake_counts: Counter[str] = Counter()
    for row in conn.execute(
        """
        SELECT q.tags,q.category,q.sub_category
          FROM mistakes m
          JOIN questions q ON q.id=m.question_id
         WHERE m.mastered=0
        """
    ):
        try:
            tags = json.loads(row["tags"] or "[]")
        except json.JSONDecodeError:
            tags = []
        if not tags:
            continue
        raw = str(tags[0])
        canonical = alias_map.get(raw) or canonicalize(
            raw, row["category"] or "", row["sub_category"] or ""
        )
        mistake_counts[canonical] += 1
    debt_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT kaodian,wrong_count,recovery_streak,last_wrong_at,last_seen_at
              FROM kaodian_debts
             WHERE mastered=0
             ORDER BY wrong_count DESC,last_wrong_at DESC
            """
        )
    ]

    recent_digest = {}
    digest_row = conn.execute(
        "SELECT v FROM user_kv WHERE k='study_digest_v1'"
    ).fetchone()
    if digest_row:
        try:
            digest = json.loads(digest_row["v"])
            for offset in (0, 1):
                day = str(today - dt.timedelta(days=offset))
                if digest.get(day):
                    recent_digest[day] = digest[day]
        except (TypeError, json.JSONDecodeError):
            pass

    recommended: list[dict] = []
    recent_blocked: list[dict] = []
    seen_kaodian: set[str] = set()
    for reason, rows in (
        ("高置信弱项", weaknesses),
        ("到期回捞", overdue),
        ("低置信待测", needs_measurement),
    ):
        for row in rows:
            if row["kaodian"] in seen_kaodian:
                continue
            seen_kaodian.add(row["kaodian"])
            if family_too_recent(row):
                recent_blocked.append({**row, "reason": "刚练过不宜主攻"})
            elif len(recommended) < 5:
                recommended.append({**row, "reason": reason})

    snapshot = {
        "as_of": now.isoformat(timespec="seconds"),
        "summary": {
            "profiles": len(profiles),
            "reliable_profiles": len(reliable),
            "high_confidence_weaknesses": len(weaknesses),
            "open_mistakes": sum(mistake_counts.values()),
            "open_debt_families": len(debt_rows),
            "completed_sessions": conn.execute(
                "SELECT COUNT(*) FROM practice_sessions WHERE ended_at IS NOT NULL"
            ).fetchone()[0],
        },
        "recommended_targets": recommended[:5],
        "recently_practiced": recent_blocked[:5],
        "weaknesses": weaknesses[:8],
        "strengths": strengths[:5],
        "needs_measurement": needs_measurement[:5],
        "overdue": overdue[:5],
        "open_mistake_families": [
            {
                "kaodian": row["kaodian"],
                "count": row["wrong_count"],
                "recovery_streak": row["recovery_streak"],
            }
            for row in debt_rows[:8]
        ] if debt_rows else [
            {"kaodian": tag, "count": count, "recovery_streak": 0}
            for tag, count in mistake_counts.most_common(8)
        ],
        "recent_sessions": recent_sessions,
        "recent_digest": recent_digest,
    }
    snapshot["compact"] = render_compact(snapshot)
    return snapshot


def _compact_target_line(item: dict) -> str:
    recency = ""
    if item.get("days_since") is not None:
        recency = f" 本点{item['days_since']}天"
    if item.get("family_days_since") is not None:
        recency += f" 同族{item['family_days_since']}天"
    return (
        f"- {item['reason']}｜{item['kaodian']}｜掌握{item['mastery']} "
        f"置信{item['confidence']} 样本{item['attempts']} 连续{item['streak']}"
        f"{recency}"
    )


def _ziliao_rank(tag: str, by_tag: dict, mistakes: dict) -> tuple:
    row = by_tag.get(tag) or {}
    mastery = row["mastery"] if row.get("mastery") is not None else 50
    conf = row.get("confidence") or 0
    streak = row.get("streak") or 0
    debt = mistakes.get(tag, 0)
    if ((mastery < 60 or streak <= -2) and conf >= 40) or debt:
        return (0, mastery, -conf, -debt)
    if row and conf < 40:
        return (1, mastery, -conf, -debt)
    if row:
        return (2, mastery, -conf, -debt)
    return (3, 50, 0, 0)


def _ziliao_recent(tag: str, by_tag: dict) -> bool:
    days = (by_tag.get(tag) or {}).get("days_since")
    return days is not None and days <= 1


def _slot_row(tag: str, reason: str, by_tag: dict) -> dict:
    row = by_tag.get(tag) or {}
    return {
        "tag": tag,
        "reason": reason,
        "mastery": row.get("mastery"),
        "confidence": row.get("confidence"),
        "attempts": row.get("attempts"),
        "days_since": row.get("days_since"),
    }


def select_ziliao_slots(
    by_tag: dict,
    mistakes: dict | None = None,
    avoid: set | None = None,
    used: list[str] | None = None,
    recent: set | None = None,
) -> list[dict]:
    """按画像组 1 篇材料的 5 个知识库主标签。"""
    mistakes = mistakes or {}
    used_counts = Counter(used or avoid or ())
    recent = set(recent or ())
    if not by_tag and not mistakes:
        default_hits = sum(used_counts[tag] for tag in ZILIAO_DEFAULT_PACK)
        alt_hits = sum(used_counts[tag] for tag in ZILIAO_ALT_PACK)
        skeleton = ZILIAO_ALT_PACK if default_hits > alt_hits else ZILIAO_DEFAULT_PACK
        return [_slot_row(tag, "默认骨架", by_tag) for tag in skeleton]

    picked: list[str] = []
    reasons: list[str] = []

    def usage_key(tag: str) -> tuple:
        return (used_counts[tag], tag in recent)

    def take(candidates, reason: str, allow_recent: bool = False) -> bool:
        for tag in candidates:
            if tag in picked or tag not in ZILIAO_QUESTION_TAGS:
                continue
            if not allow_recent and _ziliao_recent(tag, by_tag):
                continue
            picked.append(tag)
            reasons.append(reason)
            return True
        return False

    def take_lenient(candidates, reason: str) -> bool:
        return take(candidates, reason) or take(candidates, reason, allow_recent=True)

    light = sorted(
        ZILIAO_LIGHT_TAGS,
        key=lambda tag: (*usage_key(tag), _ziliao_recent(tag, by_tag), _ziliao_rank(tag, by_tag, mistakes)),
    )
    take_lenient(light, "槽1较轻")

    weak_order = sorted(
        ZILIAO_QUESTION_TAGS,
        key=lambda tag: (*usage_key(tag), _ziliao_rank(tag, by_tag, mistakes)),
    )
    for _ in range(3):
        take_lenient(weak_order, "画像弱项")

    finale = sorted(
        (*ZILIAO_FINALE_TAGS, *(tag for tag in weak_order if tag not in ZILIAO_FINALE_TAGS)),
        key=lambda tag: (*usage_key(tag), 0 if tag in ZILIAO_FINALE_TAGS else 1, _ziliao_rank(tag, by_tag, mistakes)),
    )
    take_lenient(finale, "槽5收束")

    for tag in (*ZILIAO_DEFAULT_PACK, *ZILIAO_ALT_PACK, *ZILIAO_QUESTION_TAGS):
        if len(picked) >= 5:
            break
        if tag not in picked:
            picked.append(tag)
            reasons.append("补齐骨架")

    return [_slot_row(tag, reason, by_tag) for tag, reason in zip(picked[:5], reasons[:5])]


def select_ziliao_paper(
    by_tag: dict,
    mistakes: dict | None = None,
    rng=None,
) -> list[dict]:
    """广东日常 4 篇 × 5 题。形态均衡；考点按画像，跨篇尽量不重复。"""
    used: list[str] = []
    recent: set[str] = set()
    materials = []
    empty = not by_tag and not mistakes
    for index, (form, label) in enumerate(ZILIAO_FORMS):
        if empty:
            pack = ZILIAO_DEFAULT_PACK if index % 2 == 0 else ZILIAO_ALT_PACK
            slots = [_slot_row(tag, "默认骨架", by_tag) for tag in pack]
        else:
            slots = select_ziliao_slots(by_tag, mistakes, used=used, recent=recent)
        recent = {slot["tag"] for slot in slots}
        used.extend(slot["tag"] for slot in slots)
        materials.append({"form": form, "form_label": label, "slots": slots})
    for material, plan in zip(materials, assign_ziliao_answers(len(materials), rng=rng)):
        material["answer_kind"] = plan["kind"]
        material["answer_label"] = plan["label"]
        material["answers"] = plan["answers"]
        for slot, key in zip(material["slots"], plan["answers"]):
            slot["answer"] = key
    return materials


def collect_ziliao_state(conn: sqlite3.Connection) -> tuple[dict, dict]:
    conn.row_factory = sqlite3.Row
    today = dt.datetime.now(TZ).date()
    alias_map = {
        row["alias"]: row["canonical"]
        for row in conn.execute("SELECT alias,canonical FROM kaodian_aliases")
    }
    by_tag: dict[str, dict] = {}
    for row in conn.execute(
        """
        SELECT kaodian,module,subtype,attempts,correct,total_ms,last_seen,
               streak,mastery,mastery_confidence,mastery_samples
          FROM kaodian_profile
        """
    ):
        raw = row["kaodian"] or ""
        module = row["module"] or ""
        head = normalize_module(module or raw.split("-")[0])
        if head in ZILIAO_FOREIGN_MODULES:
            continue
        tag = canonicalize(raw, module)
        if tag not in ZILIAO_QUESTION_TAGS:
            alias = alias_map.get(raw)
            tag = canonicalize(alias or raw.split("-")[-1], "资料分析")
        if tag not in ZILIAO_QUESTION_TAGS:
            continue
        compact = compact_profile(row, today)
        compact["kaodian"] = tag
        prev = by_tag.get(tag)
        if prev is None:
            by_tag[tag] = compact
            continue
        prev_n = prev.get("attempts") or 0
        cur_n = compact.get("attempts") or 0
        if cur_n and not prev_n:
            by_tag[tag] = compact
        elif cur_n and prev_n and (compact.get("mastery") or 50) < (prev.get("mastery") or 50):
            by_tag[tag] = compact

    mistakes: dict[str, int] = Counter()
    for row in conn.execute("SELECT kaodian, wrong_count FROM kaodian_debts WHERE mastered=0"):
        tag = canonicalize(alias_map.get(row["kaodian"]) or row["kaodian"] or "", "资料分析")
        if tag in ZILIAO_QUESTION_TAGS:
            mistakes[tag] += int(row["wrong_count"] or 0)
    for row in conn.execute(
        """
        SELECT q.tags, q.category, q.sub_category
          FROM mistakes m
          JOIN questions q ON q.id=m.question_id
         WHERE m.mastered=0
        """
    ):
        tags = parse_tags(row["tags"])
        if not tags:
            continue
        tag = canonicalize(alias_map.get(tags[0]) or tags[0], row["category"] or "资料分析")
        if tag in ZILIAO_QUESTION_TAGS:
            mistakes[tag] += 1
    return by_tag, dict(mistakes)


def collect_panduan_state(conn: sqlite3.Connection) -> tuple[dict, dict]:
    conn.row_factory = sqlite3.Row
    today = dt.datetime.now(TZ).date()
    by_tag: dict[str, dict] = {}
    for row in conn.execute(
        """
        SELECT kaodian,module,subtype,attempts,correct,total_ms,last_seen,
               streak,mastery,mastery_confidence,mastery_samples
          FROM kaodian_profile
        """
    ):
        tag = row["kaodian"] or ""
        module = row["module"] or ""
        blob = f"{module} {tag}"
        if not any(token in blob for token in ("判断推理", "图形推理", "逻辑判断")):
            continue
        if "科学推理" in blob:
            continue
        compact = compact_profile(row, today)
        compact["kaodian"] = tag
        prev = by_tag.get(tag)
        if prev is None or (compact.get("attempts") or 0) > (prev.get("attempts") or 0):
            by_tag[tag] = compact
    mistakes: dict[str, int] = Counter()
    for row in conn.execute("SELECT kaodian, wrong_count FROM kaodian_debts WHERE mastered=0"):
        tag = row["kaodian"] or ""
        if tag:
            mistakes[tag] += int(row["wrong_count"] or 0)
    return by_tag, dict(mistakes)


def collect_kepui_state(conn: sqlite3.Connection) -> tuple[dict, dict]:
    conn.row_factory = sqlite3.Row
    today = dt.datetime.now(TZ).date()
    by_tag: dict[str, dict] = {}
    for row in conn.execute(
        """
        SELECT kaodian,module,subtype,attempts,correct,total_ms,last_seen,
               streak,mastery,mastery_confidence,mastery_samples
          FROM kaodian_profile
        """
    ):
        tag = row["kaodian"] or ""
        module = row["module"] or ""
        blob = f"{module} {tag}"
        if "科学推理" not in blob:
            continue
        compact = compact_profile(row, today)
        compact["kaodian"] = tag
        prev = by_tag.get(tag)
        if prev is None or (compact.get("attempts") or 0) > (prev.get("attempts") or 0):
            by_tag[tag] = compact
    mistakes: dict[str, int] = Counter()
    for row in conn.execute("SELECT kaodian, wrong_count FROM kaodian_debts WHERE mastered=0"):
        tag = row["kaodian"] or ""
        if tag and "科学推理" in tag:
            mistakes[tag] += int(row["wrong_count"] or 0)
    return by_tag, dict(mistakes)


def build_panduan_pack(conn: sqlite3.Connection, letters: list[str] | None = None, seed: str = "") -> dict:
    by_tag, mistakes = collect_panduan_state(conn)
    practiced = {tag: row for tag, row in by_tag.items() if (row.get("attempts") or 0) > 0}
    rng = random.Random(seed or "panduan")
    slots = select_panduan_paper(practiced, mistakes, letters=letters, rng=rng)
    return {
        "empty_profile": not practiced and not mistakes,
        "paper_style": "gd",
        "slots": slots,
    }


def build_kepui_pack(conn: sqlite3.Connection, letters: list[str] | None = None, seed: str = "") -> dict:
    by_tag, mistakes = collect_kepui_state(conn)
    practiced = {tag: row for tag, row in by_tag.items() if (row.get("attempts") or 0) > 0}
    rng = random.Random(seed or "kepui")
    slots = select_kepui_paper(practiced, mistakes, letters=letters, rng=rng)
    return {
        "empty_profile": not practiced and not mistakes,
        "paper_style": "gd",
        "slots": slots,
    }


def build_ziliao_pack(conn: sqlite3.Connection) -> dict:
    by_tag, mistakes = collect_ziliao_state(conn)
    practiced = {
        tag: row for tag, row in by_tag.items()
        if (row.get("attempts") or 0) > 0
    }
    materials = select_ziliao_paper(practiced, mistakes)
    return {
        "empty_profile": not practiced and not mistakes,
        "paper_style": "gd",
        "materials": materials,
        "slots": [slot for material in materials for slot in material["slots"]],
    }


def render_ziliao_pack(pack: dict) -> str:
    lines = [
        "资料分析20题包（广东日常 4篇×5题；用户未点名三级，按画像组合；未点名拔高）"
    ]
    question_no = 0
    for index, material in enumerate(pack.get("materials") or [], start=1):
        answers = "".join(material.get("answers") or [])
        kind = material.get("answer_label") or ""
        lines.append(f"第{index}篇｜{material['form']}｜{material['form_label']}｜答案{answers}（{kind}）")
        for slot in material.get("slots") or []:
            question_no += 1
            extra = ""
            if slot.get("mastery") is not None:
                extra = f"｜掌握{slot['mastery']} 置信{slot.get('confidence') or 0}"
                if slot.get("days_since") is not None:
                    extra += f" {slot['days_since']}天前"
            answer = slot.get("answer") or ""
            lines.append(f"  {question_no}. {slot['tag']} ｜{slot['reason']}｜答{answer}{extra}")
    lines.append(
        "纪律：paper_style=gd，除非用户显式点名国考/深圳/拔高；"
        "tags[0] 必须是上列知识库主标签（07-ziliao.md）；"
        "禁止资料分析-综合分析-综合判断；"
        "每篇末题可出综合判断句，标签打在正确项最重的那张卡；"
        "速算/每题四步只写解析，不单独占槽；"
        "先算定值，再把正确项排到指定字母，不要算完再改数字去凑答案；"
        "4篇须恰好3篇为ABCD各一+1随机，1篇故意打散。"
    )
    return "\n".join(lines)


def render_compact(snapshot: dict) -> str:
    summary = snapshot["summary"]
    lines = [
        f"学员快照 {snapshot['as_of']}",
        (
            f"已完成{summary['completed_sessions']}场；规范画像{summary['profiles']}个，"
            f"其中可信{summary['reliable_profiles']}个；未清知识债"
            f"{summary['open_debt_families']}类/{summary['open_mistakes']}题。"
        ),
    ]
    if snapshot["recent_sessions"]:
        bits = [
            f"{row['category']} {row['correct']}/{row['total']} {row['ended_at']}"
            for row in snapshot["recent_sessions"][:3]
        ]
        lines.append("最近练习：" + "；".join(bits))
    if snapshot["recommended_targets"]:
        lines.append("下一步候选：")
        for item in snapshot["recommended_targets"][:5]:
            lines.append(_compact_target_line(item))
    blocked = snapshot.get("recently_practiced") or []
    if blocked:
        lines.append("刚练过不宜主攻：")
        for item in blocked[:5]:
            lines.append(_compact_target_line(item))
    if snapshot["recommended_targets"] or blocked:
        lines.append(
            "出题纪律：用户没点名时，同族距上次≤1天不当本批主攻"
            "（排列组合三个子点算同一族，日期与周期算同一族）；"
            "最多盲盒混入2道结构变式；禁止同场景换数字。"
            "优先选同族距上次≥2天的高置信弱项。"
        )
    if snapshot["strengths"]:
        lines.append(
            "已稳定：" + "；".join(item["kaodian"] for item in snapshot["strengths"][:3])
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--ziliao-pack", action="store_true")
    parser.add_argument("--panduan-pack", action="store_true")
    parser.add_argument("--kepui-pack", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    try:
        snapshot = build_snapshot(conn)
        pack = build_ziliao_pack(conn) if args.ziliao_pack else None
        panduan = build_panduan_pack(conn) if args.panduan_pack else None
        kepui = build_kepui_pack(conn) if args.kepui_pack else None
    finally:
        conn.close()
    if args.kepui_pack:
        if args.compact:
            print(snapshot["compact"])
            print()
        print(render_kepui_pack(compact_kepui_pack(kepui or {"slots": []})))
        return 0
    if args.panduan_pack:
        if args.compact:
            print(snapshot["compact"])
            print()
        print(render_panduan_pack(compact_panduan_pack(panduan or {"slots": []})))
        return 0
    if args.ziliao_pack:
        if args.compact:
            print(snapshot["compact"])
            print()
        print(render_ziliao_pack(pack or {"slots": []}))
        return 0
    print(snapshot["compact"] if args.compact else json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

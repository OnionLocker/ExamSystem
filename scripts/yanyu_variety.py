#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""言语逻辑填空：句法模具与极性送分的机械指纹。

只拦能数清的东西。主题、领域、具体用词交给模型。
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

CAT_YANYU = "言语理解与表达"

# 申论套句。同批逻辑填空每种最多 1 道。
MOLDS: list[tuple[str, re.Pattern[str]]] = [
    ("不仅更是", re.compile(r"不仅.{0,16}更是")),
    ("从来不是", re.compile(r"从来不是")),
    ("一方面另一方面", re.compile(r"一方面[\s\S]{0,80}另一方面")),
    ("若只就会唯有", re.compile(r"若只[\s\S]{0,30}就会[\s\S]{0,40}唯有")),
    ("在传统开篇", re.compile(r"^在传统")),
]

COMBO = ("从来不是", "一方面另一方面", "只有才能")
COMBO_ONLY = re.compile(r"只有[\s\S]{0,40}才能")

POS_FRAME = re.compile(r"才能[让使着]|从而|得以")
NEG_DUMP = (
    "格格不入", "水火不容", "固步自封", "昙花一现", "南辕北辙", "背道而驰",
    "缘木求鱼", "本末倒置", "空中楼阁", "纸上谈兵", "无济于事", "于事无补",
    "适得其反", "事与愿违", "分道扬镳", "同床异梦", "貌合神离", "一败涂地",
    "销声匿迹", "日薄西山", "束手无策", "一筹莫展", "进退维谷", "难以为继",
    "无以为继", "名存实亡", "形同虚设", "徒劳无功", "雪上加霜", "饮鸩止渴",
    "竭泽而渔",
)

BLANK = re.compile(r"[_＿]{4,}|…{2,}")


def stem_of(question: dict) -> str:
    return str(question.get("stem") or question.get("content") or "")


def is_fill(question: dict) -> bool:
    blob = f"{question.get('sub_category') or ''} {' '.join(question.get('tags') or [])}"
    if "逻辑填空" in blob:
        return True
    return bool(BLANK.search(stem_of(question)))


def molds_of(text: str) -> list[str]:
    hits = [name for name, cre in MOLDS if cre.search(text)]
    if COMBO_ONLY.search(text):
        hits.append("只有才能")
    return hits


def option_words(text: str) -> list[str]:
    return [part for part in str(text or "").split() if part]


def two_blank_slots(question: dict) -> list[list[str]] | None:
    rows = []
    for option in question.get("options") or []:
        words = option_words(option.get("text") if isinstance(option, dict) else option)
        if len(words) != 2:
            return None
        rows.append(words)
    return rows if len(rows) == 4 else None


def polarity_dump(question: dict) -> str | None:
    slots = two_blank_slots(question)
    if not slots or not POS_FRAME.search(stem_of(question)):
        return None
    seconds = [row[-1] for row in slots]
    dumped = [word for word in seconds if any(neg in word for neg in NEG_DUMP)]
    if len(dumped) >= 2:
        return "、".join(dumped)
    return None


def validate_yanyu_fills(questions: list[dict]) -> None:
    fills = [
        item for item in questions
        if isinstance(item, dict)
        and str(item.get("category") or "") == CAT_YANYU
        and is_fill(item)
    ]
    mold_counts: Counter[str] = Counter()
    for item in fills:
        qid = item.get("external_id")
        dumped = polarity_dump(item)
        if dumped:
            raise ValueError(
                f"逻辑填空干扰项极性送分（才能/从而空塞了 {dumped}）：{qid}"
            )
        hits = molds_of(stem_of(item))
        if set(COMBO) <= set(hits):
            raise ValueError(
                f"逻辑填空禁止「从来不是 + 一方面另一方面 + 只有才能」三件套：{qid}"
            )
        for name in hits:
            if name != "只有才能":
                mold_counts[name] += 1
    over = [f"{name}×{count}" for name, count in mold_counts.items() if count > 1]
    if over:
        raise ValueError(
            "同批逻辑填空句法模具重复（"
            + "，".join(over)
            + "），每种申论套句最多 1 道"
        )


def recent_yanyu_avoid(db_path: Path | None, days: int = 14) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "recent_molds": {},
        "do_not_reuse_molds": [],
        "recent_openings": [],
    }
    if db_path is None or not Path(db_path).is_file():
        return empty
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                """
                SELECT content FROM questions
                WHERE category = ?
                  AND batch_id LIKE 'daily-%'
                  AND created_at >= date('now', ?)
                ORDER BY created_at DESC
                """,
                (CAT_YANYU, f"-{int(days)} days"),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return empty
    counts: Counter[str] = Counter()
    openings: list[str] = []
    for (content,) in rows:
        text = str(content or "")
        if not BLANK.search(text):
            continue
        for name in molds_of(text):
            if name != "只有才能":
                counts[name] += 1
        head = re.sub(r"\s+", "", text)[:22]
        if head and head not in openings and not head.startswith("将下列句子"):
            openings.append(head)
        if len(openings) >= 16:
            break
    return {
        "recent_molds": dict(counts),
        "do_not_reuse_molds": [name for name, count in counts.items() if count >= 2],
        "recent_openings": openings,
    }

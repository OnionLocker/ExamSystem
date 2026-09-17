#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把口语转写收成专项出题参数。供语音入口使用，不代替用户点名。"""

from __future__ import annotations

import re
from datetime import date

from kaodian_taxonomy import (
    NUM_AVERAGE,
    NUM_CYCLE,
    NUM_DATE,
    NUM_ENGINEERING,
    NUM_EQUATION,
    NUM_EXTREME,
    NUM_GEOMETRY,
    NUM_INCLUSION,
    NUM_PERM,
    NUM_PROB,
    NUM_PROFIT,
    NUM_SEQUENCE,
    NUM_SEQUENCE_RECUR,
    NUM_SEQUENCE_SPLIT,
    NUM_TRAVEL,
    TRANSLATION,
    YANYU_MAIN,
    lookup_fenbi_short,
    parse_fenbi_tag,
)
from scheduler_common import local_today


CN_NUM = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

# 先写更细的叶子，再写家族词。粉笔短名由 lookup_fenbi_short 兜底。
TAG_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("平均数问题", "平均数"), NUM_AVERAGE),
    (("工程问题", "工程", "效率合作"), NUM_ENGINEERING),
    (("片段阅读", "中心理解"), YANYU_MAIN),
    (("古典概型", "同组概率", "几何概型", "概率问题"), NUM_PROB),
    (("特殊模型", "八大情形", "经典模型", "捆绑", "插空", "隔板", "排列组合"), NUM_PERM),
    (("反面容斥", "正难则反", "反面剥离"), NUM_PERM),
    (("翻译推理", "逆否", "德摩根", "否后否前"), TRANSLATION),
    (("和定最值", "和定", "最值构造", "抽屉", "最不利"), NUM_EXTREME),
    (("日期", "星期"), NUM_DATE),
    (("周期", "排班"), NUM_CYCLE),
    (("行程", "相遇", "追及"), NUM_TRAVEL),
    (("利润", "分段计费"), NUM_PROFIT),
    (("容斥", "集合计数"), NUM_INCLUSION),
    (("方程", "和差倍比", "比例代入"), NUM_EQUATION),
    (("平面几何", "周长面积"), NUM_GEOMETRY),
    (("机械划分", "机械拆分"), NUM_SEQUENCE_SPLIT),
    (("递推数列", "多级递推"), NUM_SEQUENCE_RECUR),
    (("数字推理", "数推"), NUM_SEQUENCE),
)

QUIZ_HINT = re.compile(
    r"出题|刷题|专项|考考我|测测我|给我出|帮我出|来几|练练|"
    r"[出来]\s*(?:\d+|[一二两三四五六七八九十])\s*[道题个]|"
    r"生成.{0,6}练习"
)
COUNT_HINT = re.compile(r"(?:出|来|给我出|帮我出)?\s*(\d+|[一二两三四五六七八九十])\s*[道题个]")
UNSUPPORTED_HINT = re.compile(r"图形推理|科学推理|资料分析|空间类")
FIGURE_HINT = re.compile(r"图形推理|科学推理|空间类")

SLUGS = {
    NUM_PERM: "排列组合",
    NUM_PROB: "概率",
    TRANSLATION: "翻译推理",
    NUM_EXTREME: "最值",
    NUM_AVERAGE: "平均数",
    NUM_DATE: "日期星期",
    NUM_CYCLE: "周期排班",
    NUM_TRAVEL: "行程",
    NUM_ENGINEERING: "工程",
    NUM_PROFIT: "利润",
    NUM_INCLUSION: "容斥",
    NUM_EQUATION: "方程比例",
    NUM_GEOMETRY: "平面几何",
    NUM_SEQUENCE: "数字推理",
    NUM_SEQUENCE_RECUR: "递推数列",
    NUM_SEQUENCE_SPLIT: "机械划分",
    YANYU_MAIN: "片段阅读",
}


def _parse_count_token(token: str) -> int | None:
    if token.isdigit():
        value = int(token)
        return value if 1 <= value <= 15 else None
    return CN_NUM.get(token)


def extract_count(text: str, default: int = 5) -> int:
    match = COUNT_HINT.search(text or "")
    if not match:
        return default
    parsed = _parse_count_token(match.group(1))
    return parsed if parsed else default


def resolve_tag(text: str) -> str:
    blob = text or ""
    short = lookup_fenbi_short(blob)
    if short:
        return short
    for needles, tag in TAG_ALIASES:
        if any(needle in blob for needle in needles):
            return tag
    return ""


def wants_quiz(text: str) -> bool:
    blob = text or ""
    if UNSUPPORTED_HINT.search(blob) and QUIZ_HINT.search(blob):
        return True
    if QUIZ_HINT.search(blob):
        return True
    return bool(resolve_tag(blob) and re.search(r"练|刷|出|来|专项|测|考", blob))


def module_of_tag(tag: str) -> str:
    parsed = parse_fenbi_tag(tag)
    if parsed:
        return parsed[0]
    return (tag or "").split("-", 1)[0]


def slug_of(tag: str) -> str:
    if tag in SLUGS:
        return SLUGS[tag]
    parsed = parse_fenbi_tag(tag)
    if parsed:
        return parsed[3] or parsed[2]
    return "专项"


def suggest_batch_id(tag: str, today: date | None = None, taken: set[str] | None = None) -> str:
    day = (today or local_today()).strftime("%Y%m%d")
    prefix = f"{day}_hermes_{slug_of(tag)}_"
    used = taken or set()
    index = 1
    while f"{prefix}{index:02d}" in used:
        index += 1
    return f"{prefix}{index:02d}"


def parse_spoken_intent(text: str, *, taken_batch_ids: set[str] | None = None) -> dict:
    blob = str(text or "").strip()
    tag = resolve_tag(blob)
    quiz = wants_quiz(blob)
    unsupported = bool(UNSUPPORTED_HINT.search(blob) or (tag and FIGURE_HINT.search(tag)))
    count = extract_count(blob, 5 if quiz or tag else 0)
    module = module_of_tag(tag)
    return {
        "text": blob,
        "wants_quiz": quiz and not unsupported,
        "unsupported": unsupported and quiz,
        "module": module,
        "tag": tag,
        "count": count if quiz or tag else 0,
        "batch_id": suggest_batch_id(tag, taken=taken_batch_ids) if (quiz or tag) and tag and not unsupported else "",
    }

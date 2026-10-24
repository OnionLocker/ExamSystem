#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""言语重复线索；只硬拦相同题干，句式和选项极性由语境审核判断。"""

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


def duplicate_fill_ids(questions: list[dict]) -> list[str]:
    """后出现的重复题干。只返回重复的那几题，先出现的保留。"""
    fills = [
        item for item in questions
        if isinstance(item, dict)
        and str(item.get("category") or "") == CAT_YANYU
        and is_fill(item)
    ]
    seen: set[str] = set()
    bad: list[str] = []
    for item in fills:
        stem = re.sub(r"\s+", "", stem_of(item))
        if stem in seen:
            bad.append(str(item.get("external_id") or ""))
        else:
            seen.add(stem)
    return bad


def validate_yanyu_fills(questions: list[dict]) -> None:
    bad = duplicate_fill_ids(questions)
    if bad:
        raise ValueError(f"同批逻辑填空题干重复：{bad[0]}")


def recent_yanyu_avoid(db_path: Path | None, days: int = 14) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "recent_molds": {},
        "do_not_reuse_molds": [],
        "recent_openings": [],
        "recent_topics": [],
        "recent_families": [],
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
    topics: list[str] = []
    families: list[str] = []
    family_counts: Counter[str] = Counter()
    for (content,) in rows:
        text = str(content or "")
        if not text:
            continue
        for name in molds_of(text):
            if name != "只有才能":
                counts[name] += 1
        head = re.sub(r"\s+", "", text)[:22]
        if head and head not in openings and not head.startswith("将下列句子"):
            openings.append(head)
        topic = topic_of(text)
        if topic and topic not in topics:
            topics.append(topic)
        family = family_of(text)
        if family:
            family_counts[family] += 1
            if family not in families:
                families.append(family)
        if len(openings) >= 16 and len(topics) >= 16 and len(families) >= 16:
            break
    return {
        "recent_molds": dict(counts),
        "do_not_reuse_molds": [name for name, count in counts.items() if count >= 2],
        "recent_openings": openings,
        "recent_topics": topics,
        "recent_families": families,
        "family_counts": dict(family_counts),
    }


# 主题避让：提取题干代表性短语作为主题指纹。优先提取“XX的YY/XX与YY”式
# 名词短语；没有明显短语时退回题干开头。提取结果只用于提醒模型避开重复主题，
# 不是禁用词表。
_TOPIC_RE = [
    re.compile(r"[\u4e00-\u9fa5]{2,8}(?:文化|生态|产业|经济|治理|服务|技术|工程|建设|模式|机制|系统|体系|设施|市场|人才|科技|金融|环境|乡村|城市|政务|阅读|教育|健康|交通|能源|制造|消费|创新|改革|发展|保护|修复|传承|利用|监测|监管|平台|数据|网络|电池|风电|光伏|材料|育种|种植|养殖)"),
    re.compile(r"(?:[\u4e00-\u9fa5]{2,6}){1,3}(?:现象|问题|短板|挑战|瓶颈|机遇|趋势|路径|方向|对策|举措)"),
]


def topic_of(text: str) -> str | None:
    """从题干提取一个代表性主题指纹。

    优先级：
    1. 跳过时间/背景状语（近年来/长期以来/随着…/当前/目前…）后的主语名词短语；
    2. 匹配“XX的YY”式名词短语；
    3. 退回题干开头 10 字。
    提取结果只用于提醒模型避开重复主题，不是禁用词表。
    """
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 8:
        return compact
    # 1) 跳过开头时间/背景状语，取真正主语
    body = re.sub(
        r"^(?:近年来|长期以来|当前|目前|如今|眼下|随着|在|从|对于|就|针对|围绕|伴随|进入|步入)[^，。；]{0,18}[，,]",
        "", compact,
    )
    m = re.match(r"[\u4e00-\u9fa5]{2,12}(?:的[\u4e00-\u9fa5]{2,10})?", body)
    if m:
        cand = m.group(0)
        if len(cand) >= 3 and cand not in ("随着进一步", "在推进"):
            return cand
    # 2) 匹配名词短语
    for cre in _TOPIC_RE:
        m = cre.search(compact)
        if m:
            return m.group(0)
    # 3) 退回开头 10 字
    return compact[:10]


# 主题族：把措辞不同但语义同族的高频公考题材归并到同一族，避免"换皮不换主题"。
# 每个族配若干关键词，命中任一即归入该族。归并只用于提醒与撞车判断，不限制题材本身。
# 关键词只用领域专属词；平台/环境/市场/制度/监管/研究/技术等通用行政词不参与族匹配，
# 否则"营商环境""政务平台"这类常见表述会把题误归到不相关的高频族。
TOPIC_FAMILIES: list[tuple[str, tuple[str, ...]]] = [
    ("城市更新与历史保护", ("城市更新", "历史街区", "历史地段", "老街", "老城区", "旧城", "大拆大建",
                         "拆旧建新", "微改造", "针灸式", "修旧如旧", "传统村落", "古村", "古民居",
                         "老建筑", "风貌保护", "活化利用", "空心化", "整体保留", "原样保留")),
    ("乡村振兴与农业发展", ("乡村振兴", "农村", "农业", "农户", "村集体", "粮食", "耕地", "种子",
                          "育种", "农技", "种植", "养殖", "农民增收", "县域", "高标准农田")),
    ("科技创新与数字经济", ("人工智能", "AI", "算法", "大模型", "算力", "芯片", "软件", "信息化",
                          "智能制造", "工业互联网", "数字孪生", "数据要素", "数字化转型")),
    ("医疗健康与公共卫生", ("医疗", "医院", "医生", "患者", "疾病", "疫苗", "药物", "药品", "医药",
                          "医保", "公共卫生", "养老", "老龄化", "康复", "护理", "诊疗")),
    ("生态环保与双碳", ("生态", "环保", "污染", "碳", "湿地", "森林", "水资源", "垃圾分类",
                       "生态修复", "环境修复", "减排", "气候", "生物多样性", "江河湖泊")),
    ("教育文化", ("教育", "学校", "学生", "教师", "课堂", "校园", "非遗", "文化传承",
                  "传统文化", "阅读", "方言", "文物", "博物馆", "古籍", "文化自信")),
    ("经济金融与消费", ("金融", "银行", "消费", "物价", "贸易", "投资", "产业升级", "中小企业",
                      "融资", "股市", "汇率")),
    ("基层治理与公共服务", ("社区", "街道", "网格", "政务", "物业", "志愿者", "便民",
                          "居委会", "业委会", "一网通办")),
    ("交通能源与基础设施", ("交通", "地铁", "高铁", "出行", "道路", "能源", "电力", "风电", "光伏",
                          "充电", "物流", "港口", "基础设施", "轨道交通", "停车")),
    ("法治与制度", ("法治", "法律", "法规", "立法", "执法", "司法", "法院", "检察院",
                   "条例", "违法", "行政处罚")),
    ("科技与科研", ("科研", "实验室", "科学家", "论文", "专利", "航天", "海洋",
                   "学科", "基础研究", "科研院所")),
]


def family_of(text: str) -> str | None:
    """返回题干命中的主题族；未命中任何族返回 None。"""
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return None
    for family, keywords in TOPIC_FAMILIES:
        if any(kw in compact for kw in keywords):
            return family
    return None


def topic_conflict(text: str, avoid: dict[str, Any]) -> str | None:
    """判断新题干与近期避让名单是否主题撞车。

    规则（只用于提醒与闸门硬拦，不限制题材本身）：
    1. 命中了避让名单里的主题族（recent_families）→ 撞车；
    2. 指纹与近期主题（recent_topics）存在包含关系（双向）→ 撞车。
    返回撞车原因；不撞车返回 None。
    """
    if not isinstance(avoid, dict):
        return None
    families = avoid.get("recent_families") or []
    family_counts = avoid.get("family_counts") or {}
    topics = avoid.get("recent_topics") or []
    if not families and not topics:
        return None
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return None
    fam = family_of(compact)
    if fam and int(family_counts.get(fam, 0)) >= 3:
        return f"主题族「{fam}」近 14 天已重复出现 {family_counts[fam]} 次，本次需换主题"
    for recent in topics:
        if not recent:
            continue
        if recent in compact or compact in recent:
            return f"与近期主题「{recent}」高度相似（recent_topics），本次需换主题"
    return None

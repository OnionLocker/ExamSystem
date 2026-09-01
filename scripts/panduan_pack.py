#!/usr/bin/env python3
"""广东判断推理 20 题套：前 15 图形+逻辑，后 5 科学推理。"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any

from kaodian_taxonomy import question_primary_tag


CAT_PANDUAN = "判断推理"
SUB_GRAPHIC = "图形推理"
SUB_LOGIC = "逻辑判断"
SUB_SCIENCE = "科学推理"

GRAPHIC_TAGS = (
    "判断推理-图形推理-位置规律",
    "判断推理-图形推理-样式规律",
    "判断推理-图形推理-属性规律",
    "判断推理-图形推理-数量规律",
    "判断推理-图形推理-空间类",
)
GRAPHIC_ALT = "判断推理-图形推理-特殊规律"

LOGIC_TAGS = (
    "判断推理-逻辑判断-逻辑论证-支持与前提假设",
    "判断推理-逻辑判断-逻辑论证-一般质疑",
    "判断推理-逻辑判断-分析类-日常分析推理",
    "判断推理-逻辑判断-秒杀模型与速解技巧",
    "判断推理-逻辑判断-比例类论证与解释说明",
    "判断推理-逻辑判断-翻译推理",
    "判断推理-逻辑判断-逻辑论证-归因论证",
)
LOGIC_DEFAULT = (
    LOGIC_TAGS[0],
    LOGIC_TAGS[1],
    LOGIC_TAGS[2],
    LOGIC_TAGS[3],
    LOGIC_TAGS[4],
    LOGIC_TAGS[5],
    LOGIC_TAGS[0],
    LOGIC_TAGS[1],
    LOGIC_TAGS[2],
    LOGIC_TAGS[6],
)
TRANSLATION_TAG = LOGIC_TAGS[5]

KEPUI_BUCKETS = {
    "力学": (
        "科学推理-力学-受力平衡",
        "科学推理-力学-杠杆滑轮",
        "科学推理-力学-摩擦与惯性",
        "科学推理-力学-运动图像",
        "科学推理-力学-平抛运动",
    ),
    "压强浮力": (
        "科学推理-压强与浮力-阿基米德原理",
        "科学推理-压强与浮力-液体压强",
        "科学推理-压强与浮力-固体压强",
        "科学推理-压强与浮力-容器底部受力",
    ),
    "电学": (
        "科学推理-电学-串并联",
        "科学推理-电学-电路故障",
        "科学推理-电学-欧姆定律",
        "科学推理-电学-电功率",
    ),
    "生物": (
        "科学推理-生物-人体调节",
        "科学推理-生物-遗传",
        "科学推理-生物-食物网",
        "科学推理-生物-生态系统与能量",
    ),
    "地理": (
        "科学推理-地理-地球自转",
        "科学推理-地理-板块",
        "科学推理-地理-气候",
        "科学推理-地理-等高线",
        "科学推理-地理-锋面天气",
        "科学推理-地理-海陆风",
        "科学推理-地理-区域地理",
    ),
    "化学": (
        "科学推理-化学-酸碱与 pH",
        "科学推理-化学-质量守恒",
        "科学推理-化学-反应类型",
    ),
}
DEFAULT_KEPUI_BUCKETS = ("力学", "压强浮力", "电学", "生物", "地理")
PHYSICS_BUCKETS = {"力学", "压强浮力", "电学", "热学与光学"}
LAYOUT_NAME = "15_graphic_logic_plus_5_kepui"

# 广东科推地理：库里可能没有同家族 holdout，仍按考频给槽，抽检按学科相关即可。
KEPUI_TAG_WEIGHT = {
    "科学推理-地理-等高线": 4,
    "科学推理-地理-锋面天气": 3,
    "科学推理-地理-海陆风": 2,
    "科学推理-地理-地球自转": 2,
    "科学推理-地理-气候": 2,
    "科学推理-地理-板块": 1,
    "科学推理-地理-区域地理": 1,
}
KEPUI_TAG_DIFFICULTY = {
    "科学推理-地理-等高线": 3,
    "科学推理-地理-锋面天气": 3,
    "科学推理-地理-海陆风": 3,
    "科学推理-地理-地球自转": 3,
    "科学推理-地理-气候": 2,
    "科学推理-地理-板块": 2,
    "科学推理-地理-区域地理": 2,
}


def _blob(question: dict) -> str:
    tags = question.get("tags") or []
    parts = [
        str(question.get("category") or ""),
        str(question.get("sub_category") or ""),
        question_primary_tag(question),
        " ".join(str(tag) for tag in tags),
    ]
    return " ".join(parts)


def question_kind(question: dict) -> str:
    text = _blob(question)
    if "定义判断" in text or "类比推理" in text:
        return "banned"
    if "科学推理" in text:
        return "science"
    if "图形推理" in text:
        return "graphic"
    if "逻辑判断" in text or "翻译推理" in text:
        return "logic"
    return "other"


def is_translation(question: dict) -> bool:
    return "翻译推理" in _blob(question)


def kepui_bucket(text: str) -> str:
    if any(token in text for token in ("压强", "浮力")):
        return "压强浮力"
    if any(token in text for token in ("电学", "电路", "串并联", "欧姆")):
        return "电学"
    if any(token in text for token in ("光学", "热学", "透镜", "折射")):
        return "热学与光学"
    if any(token in text for token in ("化学", "酸碱", "pH", "酸碱")):
        return "化学"
    if any(token in text for token in ("生物", "遗传", "光合", "食物网", "人体调节")):
        return "生物"
    if any(token in text for token in ("地理", "等高", "锋面", "海陆风", "自转", "板块", "昼夜", "气候")):
        return "地理"
    if any(token in text for token in ("力学", "杠杆", "惯性", "受力", "平抛")):
        return "力学"
    return ""


def is_panduan_paper(questions: list[dict]) -> bool:
    items = [item for item in questions if isinstance(item, dict)]
    if len(items) != 20:
        return False
    return all(str(item.get("category") or "") == CAT_PANDUAN for item in items)


def logic_family(tag: str) -> str:
    if "翻译" in tag:
        return "翻译推理"
    if "质疑" in tag or "削弱" in tag:
        return "削弱"
    if "支持" in tag or "前提" in tag or "加强" in tag:
        return "加强前提"
    if "分析" in tag:
        return "分析推理"
    if "秒杀" in tag or "结构" in tag:
        return "结构相似"
    if "解释" in tag:
        return "原因解释"
    if "归因" in tag:
        return "归因"
    parts = [part for part in tag.split("-") if part]
    return parts[-1] if parts else tag


def validate_panduan_paper(questions: list[dict]) -> None:
    if not is_panduan_paper(questions):
        return
    kinds = [question_kind(item) for item in questions]
    if "banned" in kinds:
        raise ValueError("判断推理套不得出现定义判断或类比推理")
    head, tail = kinds[:15], kinds[15:]
    if any(kind == "science" for kind in head):
        raise ValueError("判断推理 20 题套前 15 题必须是图形推理或逻辑判断，不能放科学推理")
    if any(kind != "science" for kind in tail):
        raise ValueError("判断推理 20 题套最后 5 题必须是科学推理")
    if head.count("graphic") < 4:
        raise ValueError("前 15 题至少 4 道图形推理，对齐广东卷图形 5 题")
    if head.count("logic") < 8:
        raise ValueError("前 15 题须覆盖逻辑判断多个知识点，不能只出图形")
    if sum(1 for item in questions[:15] if is_translation(item)) > 2:
        raise ValueError("翻译推理每年只考 1–2 题，20 题套最多 2 道")
    families = {logic_family(question_primary_tag(item)) for item, kind in zip(questions[:15], head) if kind == "logic"}
    if len(families) < 4:
        raise ValueError("前 15 题逻辑判断须覆盖加强/削弱/分析/解释/结构相似等，不得单题型堆满")
    buckets = [kepui_bucket(_blob(item)) for item in questions[15:]]
    if any(not bucket for bucket in buckets):
        raise ValueError("科学推理必须落到力学/压强浮力/电学/生物/地理等学科分支")
    if len(set(buckets)) < 5:
        raise ValueError("最后 5 题科学推理不得重复同一学科")
    if "生物" not in buckets or "地理" not in buckets:
        raise ValueError("科学推理 5 题须含生物和地理各 1 题")
    if sum(1 for bucket in buckets if bucket in PHYSICS_BUCKETS) < 2:
        raise ValueError("科学推理 5 题物理至少 2 题（力学/压强浮力/电学），对齐近年真题")


def _rank(tag: str, by_tag: dict, mistakes: dict) -> tuple:
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


def _profile_for(pool_tag: str, by_tag: dict) -> dict:
    if pool_tag in by_tag:
        return by_tag[pool_tag]
    parts = [part for part in pool_tag.split("-") if part]
    for n in range(len(parts) - 1, 0, -1):
        parent = "-".join(parts[:n])
        if parent in by_tag:
            return by_tag[parent]
    return {}


def _effective_state(pool: tuple[str, ...] | list[str], by_tag: dict, mistakes: dict) -> tuple[dict, dict]:
    mapped_tag: dict[str, dict] = {}
    mapped_debt: dict[str, int] = {}
    for tag in pool:
        row = _profile_for(pool_tag=tag, by_tag=by_tag)
        if row:
            mapped_tag[tag] = row
        mapped_debt[tag] = sum(
            count
            for key, count in mistakes.items()
            if key == tag or key.startswith("-".join(tag.split("-")[:2]))
        )
    return mapped_tag, mapped_debt


def tag_difficulty(tag: str) -> int:
    return int(KEPUI_TAG_DIFFICULTY.get(tag) or 3)


def _pick_kepui_tag(pool: tuple[str, ...] | list[str], by_tag: dict, mistakes: dict, rng: random.Random) -> str:
    k_state, k_debt = _effective_state(pool, by_tag, mistakes)
    ordered = sorted(pool, key=lambda tag: _rank(tag, k_state, k_debt))
    if _rank(ordered[0], k_state, k_debt)[0] == 0:
        return ordered[0]
    weights = [KEPUI_TAG_WEIGHT.get(tag, 1) for tag in pool]
    return rng.choices(list(pool), weights=weights, k=1)[0]


def _slot(tag: str, section: str, reason: str) -> dict:
    row = {"tag": tag, "section": section, "reason": reason}
    if tag in KEPUI_TAG_DIFFICULTY:
        row["difficulty"] = tag_difficulty(tag)
    return row


def select_panduan_paper(
    by_tag: dict | None = None,
    mistakes: dict | None = None,
    letters: list[str] | None = None,
    rng: random.Random | None = None,
) -> list[dict]:
    by_tag = by_tag or {}
    mistakes = mistakes or {}
    rng = rng or random.Random(0)
    graphic_pool = (*GRAPHIC_TAGS, GRAPHIC_ALT)
    g_state, g_debt = _effective_state(graphic_pool, by_tag, mistakes)
    graphic_order = sorted(graphic_pool, key=lambda tag: _rank(tag, g_state, g_debt))
    graphic = []
    for tag in graphic_order:
        if tag not in graphic:
            graphic.append(tag)
        if len(graphic) == 5:
            break
    l_state, l_debt = _effective_state(LOGIC_TAGS, by_tag, mistakes)
    translation_weak = _rank(TRANSLATION_TAG, l_state, l_debt)[0] == 0
    translation_quota = 2 if translation_weak else 1
    logic: list[str] = []
    used = Counter()

    def take_logic(tag: str) -> bool:
        if tag == TRANSLATION_TAG and used[TRANSLATION_TAG] >= translation_quota:
            return False
        if used[tag] >= 2:
            return False
        logic.append(tag)
        used[tag] += 1
        return True

    for tag in LOGIC_DEFAULT:
        if len(logic) >= 10:
            break
        take_logic(tag)
    weak_logic = sorted(LOGIC_TAGS, key=lambda tag: _rank(tag, l_state, l_debt))
    for tag in weak_logic:
        if len(logic) >= 10:
            break
        take_logic(tag)
    while len(logic) < 10:
        for tag in LOGIC_DEFAULT:
            if take_logic(tag) and len(logic) >= 10:
                break

    buckets = list(DEFAULT_KEPUI_BUCKETS)
    if (rng.randrange(3) == 0) and not translation_weak:
        buckets[1] = "化学"
    kepui: list[str] = []
    for bucket in buckets:
        kepui.append(_pick_kepui_tag(KEPUI_BUCKETS[bucket], by_tag, mistakes, rng))
    rng.shuffle(kepui)

    slots = (
        [_slot(tag, "graphic", "图形推理") for tag in graphic]
        + [_slot(tag, "logic", "逻辑判断") for tag in logic]
        + [_slot(tag, "science", "科学推理") for tag in kepui]
    )
    if letters:
        for slot, letter in zip(slots, letters):
            slot["answer"] = letter
    return slots


def compact_panduan_pack(pack: dict) -> dict:
    return {
        "paper_style": pack.get("paper_style") or "gd",
        "layout": LAYOUT_NAME,
        "slots": [
            {
                key: value
                for key, value in {
                    "index": index + 1,
                    "section": slot.get("section"),
                    "tag": slot.get("tag"),
                    "reason": slot.get("reason"),
                    "answer": slot.get("answer"),
                    "difficulty": slot.get("difficulty"),
                }.items()
                if value is not None
            }
            for index, slot in enumerate(pack.get("slots") or [])
        ],
    }


def render_panduan_pack(pack: dict) -> str:
    lines = [
        "判断推理20题套（广东日常：前15图形+逻辑各知识点，后5科学推理）",
        "图形约5、逻辑约10（论证类为主，翻译最多2题，不出定义/类比）；",
        "科学推理按近年真题：力学、压强浮力、电学、生物、地理均衡，物理2–3+生物1+地理1。",
    ]
    for slot in pack.get("slots") or []:
        answer = slot.get("answer") or ""
        extra = f" 答{answer}" if answer else ""
        diff = slot.get("difficulty")
        extra += f" 难度{diff}" if diff else ""
        lines.append(f"{slot.get('index') or ''} {slot.get('section')} {slot.get('tag')}{extra}")
    return "\n".join(lines)

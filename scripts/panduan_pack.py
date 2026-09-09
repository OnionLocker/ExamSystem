#!/usr/bin/env python3
"""广东判断推理 20 题套（纯逻辑 20）与独立科学推理 5 题套。"""

from __future__ import annotations

import random
from collections import Counter
from kaodian_taxonomy import question_primary_tag


CAT_PANDUAN = "判断推理"
CAT_KEPUI = "科学推理"
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
# 20 道逻辑：论证类为主，翻译最多 2 槽（弱项时再加 1）；每标签最多 3 次（7 标签×3=21 > 20）
LOGIC_DEFAULT = (
    LOGIC_TAGS[0],
    LOGIC_TAGS[1],
    LOGIC_TAGS[2],
    LOGIC_TAGS[3],
    LOGIC_TAGS[4],
    LOGIC_TAGS[5],
    LOGIC_TAGS[6],
    LOGIC_TAGS[0],
    LOGIC_TAGS[1],
    LOGIC_TAGS[2],
    LOGIC_TAGS[3],
    LOGIC_TAGS[4],
    LOGIC_TAGS[5],
    LOGIC_TAGS[6],
    LOGIC_TAGS[0],
    LOGIC_TAGS[1],
    LOGIC_TAGS[2],
    LOGIC_TAGS[3],
    LOGIC_TAGS[4],
    LOGIC_TAGS[5],
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
LAYOUT_NAME = "20_logic_no_graphic"
KEPUI_LAYOUT_NAME = "5_kepui_distinct_subjects"

# 各地理点同等抽，不因为锋面/等高线更好画就加重。
KEPUI_TAG_WEIGHT = {}
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


def is_science_question(question: dict) -> bool:
    return question_kind(question) == "science"


def is_panduan_paper(questions: list[dict]) -> bool:
    items = [item for item in questions if isinstance(item, dict)]
    if len(items) != 20:
        return False
    return all(str(item.get("category") or "") == CAT_PANDUAN for item in items)


def is_kepui_paper(questions: list[dict]) -> bool:
    items = [item for item in questions if isinstance(item, dict)]
    if len(items) != 5:
        return False
    return all(is_science_question(item) for item in items)


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


def validate_kepui_slots(questions: list[dict], *, require_images: bool = False) -> None:
    if len(questions) != 5:
        raise ValueError(f"科学推理须为独立 5 题，当前 {len(questions)} 题")
    if any(str(item.get("category") or "") != CAT_KEPUI for item in questions):
        raise ValueError("科学推理独立卷每题 category 必须是科学推理，禁止写成判断推理")
    if any(question_kind(item) != "science" for item in questions):
        raise ValueError("科学推理 5 题每题须标明科学推理（category 或 sub_category）")
    buckets = [kepui_bucket(_blob(item)) for item in questions]
    if any(not bucket for bucket in buckets):
        raise ValueError("科学推理必须落到力学/压强浮力/电学/生物/地理等学科分支")
    if len(set(buckets)) < 5:
        raise ValueError("科学推理 5 题不得重复同一学科")
    if "生物" not in buckets or "地理" not in buckets:
        raise ValueError("科学推理 5 题须含生物和地理各 1 题")
    if "压强浮力" not in buckets:
        raise ValueError("科学推理 5 题须含压强浮力 1 题")
    if sum(1 for bucket in buckets if bucket in PHYSICS_BUCKETS) < 2:
        raise ValueError("科学推理 5 题物理至少 2 题（力学/压强浮力/电学），对齐近年真题")
    if require_images:
        for item in questions:
            if not (item.get("stem_images") or any(opt.get("images") for opt in item.get("options") or [])):
                raise ValueError(f"科学推理每题必带图：{item.get('external_id')}")


def validate_kepui_paper(questions: list[dict], *, require_images: bool = False) -> None:
    items = [item for item in questions if isinstance(item, dict)]
    if not is_kepui_paper(items) and not (len(items) == 5 and all(is_science_question(item) for item in items)):
        return
    validate_kepui_slots(items, require_images=require_images)


def validate_panduan_paper(questions: list[dict]) -> None:
    if not is_panduan_paper(questions):
        return
    kinds = [question_kind(item) for item in questions]
    if "banned" in kinds:
        raise ValueError("判断推理套不得出现定义判断或类比推理")
    if any(kind == "science" for kind in kinds):
        raise ValueError("判断推理 20 题不得含科学推理；科学推理是独立模块，日练不再出科推")
    if kinds.count("graphic") != 0 or kinds.count("logic") != 20:
        raise ValueError(
            f"广东判断 20 题须纯逻辑 20（不再出图），当前 "
            f"graphic {kinds.count('graphic')}/logic {kinds.count('logic')}"
        )
    if sum(1 for item in questions if is_translation(item)) > 2:
        raise ValueError("翻译推理每年只考 1–2 题，20 题套最多 2 道")
    families = {
        logic_family(question_primary_tag(item))
        for item, kind in zip(questions, kinds)
        if kind == "logic"
    }
    if len(families) < 4:
        raise ValueError("逻辑判断须覆盖加强/削弱/分析/解释/结构相似等，不得单题型堆满")
    validate_panduan_kaodian(questions)


def validate_panduan_kaodian(questions: list[dict]) -> None:
    """标签说的考法必须出现在设问里；同卷不得用同一论证骨架换皮。短题干视为单测夹具，跳过。"""
    logic = [
        item for item in questions
        if isinstance(item, dict) and question_kind(item) == "logic"
    ]
    real = [item for item in logic if len(str(item.get("stem") or "")) >= 40]
    if len(real) < 10:
        return
    ask = {
        "结构相似": ("相似", "结构", "逻辑错误"),
        "原因解释": ("解释",),
        "翻译推理": ("推出", "推知", "得出", "可知", "正确的是", "无法推出", "不能推出", "一定为真", "可能为真"),
        "削弱": ("削弱", "质疑", "反驳", "漏洞", "切断", "推理链", "不能支持"),
        "加强前提": ("支持", "加强", "前提", "假设"),
        "归因": ("原因", "归因", "主要", "质疑"),
    }
    for item in real:
        family = logic_family(question_primary_tag(item))
        hints = ask.get(family)
        if not hints:
            continue
        stem = str(item.get("stem") or "")
        if not any(token in stem for token in hints):
            raise ValueError(
                f"考点与设问不符：{item.get('external_id')} 标签是{family}，"
                "题干设问却不像在考该知识点（换皮不算变式）"
            )
    analysis = [item for item in real if logic_family(question_primary_tag(item)) == "分析推理"]
    matching = 0
    for item in analysis:
        stem = str(item.get("stem") or "")
        if "甲" in stem and "乙" in stem and any(token in stem for token in ("分别", "各不相同", "对应")):
            matching += 1
    if matching >= 3:
        raise ValueError("分析推理不得三道都是甲乙丙对象匹配；换排序或分组")
    weaken = [
        item for item in real
        if logic_family(question_primary_tag(item)) in {"削弱", "归因"}
    ]
    bili = 0
    for item in weaken:
        stem = str(item.get("stem") or "")
        if ("占比" in stem or "高达" in stem) and any(
            token in stem for token in ("危险因素", "更容易", "主要原因")
        ):
            bili += 1
    if bili >= 2:
        raise ValueError("削弱/归因不得两道都用「样本占比推因果」同一骨架")


def _rank(tag: str, by_tag: dict, mistakes: dict) -> tuple:
    row = by_tag.get(tag) or {}
    signal = row.get('practice_signal') or {}
    gap = signal.get('family_days_since')
    if gap is not None and gap <= 1:
        return (4, 50, 0, 0)
    mastery = row["mastery"] if row.get("mastery") is not None else 50
    conf = row.get("confidence") or 0
    streak = row.get("streak") or 0
    debt = mistakes.get(tag, 0)
    if ((mastery < 60 or streak <= -2) and conf >= 40) or debt:
        return (0, mastery, -conf, -debt)
    if signal.get('slow'):
        return (1, 0, -conf, -debt)
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


def _pick_kepui_tag(
    pool: tuple[str, ...] | list[str],
    by_tag: dict,
    mistakes: dict,
    rng: random.Random,
    recent: set[str] | None = None,
) -> str:
    recent = set(recent or ())
    k_state, k_debt = _effective_state(pool, by_tag, mistakes)
    ordered = sorted(pool, key=lambda tag: _rank(tag, k_state, k_debt))
    if _rank(ordered[0], k_state, k_debt)[0] == 0 and ordered[0] not in recent:
        return ordered[0]
    weights = []
    for tag in pool:
        weight = KEPUI_TAG_WEIGHT.get(tag, 1)
        rank = _rank(tag, k_state, k_debt)[0]
        if tag in recent or rank == 4:
            weight *= 0.15
        elif (k_state.get(tag) or {}).get("practice_signal", {}).get("slow"):
            weight *= 2
        weights.append(weight)
    return rng.choices(list(pool), weights=weights, k=1)[0]


# 同一粗标签下必须换认知动作，禁止换景区/电商接着考同一个「另有他因」
GRAPHIC_EXAM_MOVES = {
    "数量规律": ("封闭面递增",),
    "位置规律": ("箭头平移旋转",),
    "样式规律": ("去同存异",),
    "属性规律": ("对称性分类",),
    "特殊规律": ("开闭性分类",),
    "空间类": ("六面体展开还原", "立方体截面", "小方块三视图"),
}

LOGIC_EXAM_MOVES = {
    "加强前提": (
        "搭桥：补上论据与结论之间缺失的联系",
        "必要条件：找出结论成立不可少的前提",
        "对比实验：无因则无果或控制变量",
    ),
    "削弱": (
        "另有他因",
        "切断论据与结论的推理链",
        "样本缺陷或实验前测不等",
    ),
    "分析推理": (
        "对象与属性一一匹配",
        "名次或时间先后排序",
        "分组或条件组合（不要再写成第三人称职业匹配）",
    ),
    "结构相似": (
        "推理形式平行（假言/联言结构）",
        "逻辑谬误平行（偷换概念或否定前件）",
    ),
    "原因解释": (
        "解释矛盾或反常现象",
        "解释比例与绝对量不一致",
    ),
    "翻译推理": ("逆否或选言连锁，正确项不得复述已知事实",),
    "归因": ("针对「A是主因」提出更强的替代原因或因果倒置",),
}


def _slot(tag: str, section: str, reason: str, exam_move: str | None = None) -> dict:
    row = {"tag": tag, "section": section, "reason": reason}
    if exam_move:
        row["exam_move"] = exam_move
    if tag in KEPUI_TAG_DIFFICULTY:
        row["difficulty"] = tag_difficulty(tag)
    return row


def _exam_move_for(
    tag: str, section: str, used: Counter, rng: random.Random | None = None
) -> str:
    rng = rng or random.Random(0)
    if section == "graphic":
        family = tag.rsplit("-", 1)[-1]
        moves = GRAPHIC_EXAM_MOVES.get(family) or (family,)
        unused = [move for move in moves if not used[move]]
        move = rng.choice(unused or list(moves))
        used[move] += 1
        return move
    family = logic_family(tag)
    moves = LOGIC_EXAM_MOVES.get(family) or (family,)
    move = moves[used[family] % len(moves)]
    used[family] += 1
    return move


def _select_graphic(by_tag: dict, mistakes: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random(0)
    graphic_pool = list((*GRAPHIC_TAGS, GRAPHIC_ALT))
    g_state, g_debt = _effective_state(graphic_pool, by_tag, mistakes)
    graphic_order = sorted(graphic_pool, key=lambda tag: _rank(tag, g_state, g_debt))
    # 同分时打乱，避免永远丢掉空间类或特殊规律
    groups: list[list[str]] = []
    for tag in graphic_order:
        if not groups or _rank(tag, g_state, g_debt) != _rank(groups[-1][0], g_state, g_debt):
            groups.append([tag])
        else:
            groups[-1].append(tag)
    ordered: list[str] = []
    for group in groups:
        rng.shuffle(group)
        ordered.extend(group)
    graphic: list[str] = []
    for tag in ordered:
        if tag not in graphic:
            graphic.append(tag)
        if len(graphic) == 5:
            break
    return graphic


def _select_logic(by_tag: dict, mistakes: dict) -> list[str]:
    l_state, l_debt = _effective_state(LOGIC_TAGS, by_tag, mistakes)
    translation_weak = _rank(TRANSLATION_TAG, l_state, l_debt)[0] == 0
    translation_quota = 2 if translation_weak else 1
    logic: list[str] = []
    used = Counter()

    def take_logic(tag: str) -> bool:
        if tag == TRANSLATION_TAG and used[TRANSLATION_TAG] >= translation_quota:
            return False
        cap = 3 if tag == TRANSLATION_TAG else 4
        if used[tag] >= cap:
            return False
        logic.append(tag)
        used[tag] += 1
        return True

    for tag in LOGIC_DEFAULT:
        if len(logic) >= 20:
            break
        take_logic(tag)
    weak_logic = sorted(LOGIC_TAGS, key=lambda tag: _rank(tag, l_state, l_debt))
    for tag in weak_logic:
        if len(logic) >= 20:
            break
        take_logic(tag)
    while len(logic) < 20:
        progressed = False
        for tag in LOGIC_DEFAULT:
            if take_logic(tag):
                progressed = True
            if len(logic) >= 20:
                break
        if not progressed:
            break
    if len(logic) != 20:
        raise ValueError("无法凑满逻辑判断 20 题槽")
    return logic


def _select_kepui_tags(
    by_tag: dict, mistakes: dict, rng: random.Random, recent: set[str] | None = None
) -> list[str]:
    buckets = list(DEFAULT_KEPUI_BUCKETS)
    kepui = [
        _pick_kepui_tag(KEPUI_BUCKETS[bucket], by_tag, mistakes, rng, recent) for bucket in buckets
    ]
    rng.shuffle(kepui)
    return kepui


def select_panduan_paper(
    by_tag: dict | None = None,
    mistakes: dict | None = None,
    letters: list[str] | None = None,
    rng: random.Random | None = None,
) -> list[dict]:
    by_tag = by_tag or {}
    mistakes = mistakes or {}
    rng = rng or random.Random(0)
    logic = _select_logic(by_tag, mistakes)
    used_moves: Counter = Counter()
    slots = [_slot(tag, "logic", "逻辑判断", _exam_move_for(tag, "logic", used_moves, rng)) for tag in logic]
    if letters:
        for slot, letter in zip(slots, letters):
            slot["answer"] = letter
    return slots


def select_kepui_paper(
    by_tag: dict | None = None,
    mistakes: dict | None = None,
    letters: list[str] | None = None,
    rng: random.Random | None = None,
    recent: set[str] | None = None,
) -> list[dict]:
    by_tag = by_tag or {}
    mistakes = mistakes or {}
    rng = rng or random.Random(0)
    kepui = _select_kepui_tags(by_tag, mistakes, rng, recent)
    slots = [_slot(tag, "science", "科学推理") for tag in kepui]
    if letters:
        for slot, letter in zip(slots, letters):
            slot["answer"] = letter
    return slots


def _compact_slots(pack: dict, layout: str) -> dict:
    return {
        "paper_style": pack.get("paper_style") or "gd",
        "layout": layout,
        "slots": [
            {
                key: value
                for key, value in {
                    "index": index + 1,
                    "section": slot.get("section"),
                    "tag": slot.get("tag"),
                    "exam_move": slot.get("exam_move"),
                    "reason": slot.get("reason"),
                    "answer": slot.get("answer"),
                    "difficulty": slot.get("difficulty"),
                }.items()
                if value is not None
            }
            for index, slot in enumerate(pack.get("slots") or [])
        ],
    }


def compact_panduan_pack(pack: dict) -> dict:
    return _compact_slots(pack, LAYOUT_NAME)


def compact_kepui_pack(pack: dict) -> dict:
    return _compact_slots(pack, KEPUI_LAYOUT_NAME)


SHULIANG_SEQ_POOL = (
    "数量关系-数字推理-递推数列",
    "数量关系-数字推理-机械划分",
    "数量关系-数字推理-多重数列",
    "数量关系-数字推理-多级数列",
    "数量关系-数字推理-幂次数列",
    "数量关系-数字推理-分数数列",
    "数量关系-数字推理-图形数阵",
    "数量关系-数字推理-作和作积数列",
    "数量关系-数字推理-作商数列",
    "数量关系-数字推理-小数与差分数列",
    "数量关系-数字推理-数位特征数列",
    "数量关系-数字推理-幂次变式数列",
)
SHULIANG_MATH_POOL = (
    "数量关系-有规律的周期循环与要算准的日期星期-日期推算与余数",
    "数量关系-有规律的周期循环与要算准的日期星期-周期排班与公倍数",
    "数量关系-逢考必有的排列组合与概率-基础原理与几何概型",
    "数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）",
    "数量关系-逢考必有的排列组合与概率-反面容斥与逆向思维",
    "数量关系-既烧脑又能套公式的最值问题-和定最值与构造",
    "数量关系-要抓住常考图形的几何问题-平面图形周长与面积",
    "数量关系-能“七十二变”的行程问题-基础行程、平均速度与相对运动",
    "数量关系-容易找到等式关系的利润问题-利润与分段计费",
    "数量关系-熟练掌握可“轻松拿下”的工程问题-工程效率与分段合作",
    "数量关系-和差倍比与方程法-方程、比例与代入验证",
    "数量关系-容斥问题-集合计数与逆向排除",
    "数量关系-数量基础之数论及数的特性-数的特性（倍数、整除与同余）",
    "数量关系-“溶质不变”的浓度问题与便捷的十字相乘法-03“溶质不变”的浓度问题与便捷的十字相乘法",
    "数量关系-古老的“牛吃草”与不变的容斥问题-04古老的“牛吃草”与不变的容斥问题",
    "数量关系-小学奥数之特殊情景应用题-鸡兔同笼、盈亏、年龄与方阵",
    "数量关系-能“七十二变”的行程问题-流水行船、扶梯、过桥与队伍",
)
YANYU_FILL_POOL = (
    "言语理解与表达-逻辑填空-词语辨析",
    "言语理解与表达-逻辑填空-逻辑对应",
    "言语理解与表达-逻辑填空-成语实词混搭",
)
YANYU_READ_POOL = (
    "言语理解与表达-片段阅读-主旨概括",
    "言语理解与表达-片段阅读-细节判断",
    "言语理解与表达-片段阅读-意图判断",
    "言语理解与表达-片段阅读-标题添加",
    "言语理解与表达-片段阅读-词句理解",
)
YANYU_SENT_POOL = (
    "言语理解与表达-语句表达-语句排序",
    "言语理解与表达-语句表达-语句填空",
    "言语理解与表达-语句表达-下文推断",
)


def _pick_rotate(pool: tuple[str, ...] | list[str], n: int, rng: random.Random, recent: set[str]) -> list[str]:
    pool = list(pool)
    if not pool or n <= 0:
        return []
    fresh = [tag for tag in pool if tag not in recent]
    stale = [tag for tag in pool if tag in recent]
    rng.shuffle(fresh)
    rng.shuffle(stale)
    ordered = fresh + stale
    picked: list[str] = []
    while len(picked) < n:
        picked.extend(ordered[: n - len(picked)])
        if not ordered:
            break
        rng.shuffle(ordered)
    return picked[:n]


def select_shuliang_paper(
    letters: list[str] | None = None,
    rng: random.Random | None = None,
    recent: set[str] | None = None,
) -> list[dict]:
    rng = rng or random.Random(0)
    recent = set(recent or ())
    tags = _pick_rotate(SHULIANG_SEQ_POOL, 5, rng, recent) + _pick_rotate(
        SHULIANG_MATH_POOL, 10, rng, recent
    )
    slots = [_slot(tag, "sequence" if index < 5 else "math", "数字推理" if index < 5 else "数学运算")
             for index, tag in enumerate(tags)]
    if letters:
        for slot, letter in zip(slots, letters):
            slot["answer"] = letter
    return slots


def select_yanyu_paper(
    letters: list[str] | None = None,
    rng: random.Random | None = None,
    recent: set[str] | None = None,
) -> list[dict]:
    rng = rng or random.Random(0)
    recent = set(recent or ())
    tags = (
        _pick_rotate(YANYU_FILL_POOL, 5, rng, recent)
        + _pick_rotate(YANYU_READ_POOL, 7, rng, recent)
        + _pick_rotate(YANYU_SENT_POOL, 3, rng, recent)
    )
    slots = []
    for index, tag in enumerate(tags):
        section = "fill" if index < 5 else "read" if index < 12 else "sentence"
        slots.append(_slot(tag, section, "逻辑填空" if index < 5 else "片段阅读" if index < 12 else "语句表达"))
    if letters:
        for slot, letter in zip(slots, letters):
            slot["answer"] = letter
    return slots


def compact_shuliang_pack(pack: dict) -> dict:
    return _compact_slots(pack, "5_sequence_plus_10_math")


def compact_yanyu_pack(pack: dict) -> dict:
    return _compact_slots(pack, "5_fill_plus_10_read")


def render_panduan_pack(pack: dict) -> str:
    lines = [
        "判断推理20题套（纯逻辑判断 20，不再出图）",
        "不出定义判断/类比推理/图形推理；翻译推理最多 2 题。科学推理是独立模块，不写入本套。",
    ]
    for slot in pack.get("slots") or []:
        answer = slot.get("answer") or ""
        extra = f" 答{answer}" if answer else ""
        diff = slot.get("difficulty")
        extra += f" 难度{diff}" if diff else ""
        move = slot.get("exam_move") or ""
        extra += f" 考{move}" if move else ""
        lines.append(f"{slot.get('index') or ''} {slot.get('section')} {slot.get('tag')}{extra}")
    return "\n".join(lines)


def render_kepui_pack(pack: dict) -> str:
    lines = [
        "科学推理5题套（广东独立模块：五科互不相同，每题带图，初中档）",
        "近年均衡：力学、压强浮力、电学、生物、地理（物理 2–3 + 生物 1 + 地理 1）；禁理想气体/动量守恒等超纲。",
    ]
    for slot in pack.get("slots") or []:
        answer = slot.get("answer") or ""
        extra = f" 答{answer}" if answer else ""
        diff = slot.get("difficulty")
        extra += f" 难度{diff}" if diff else ""
        lines.append(f"{slot.get('index') or ''} {slot.get('section')} {slot.get('tag')}{extra}")
    return "\n".join(lines)

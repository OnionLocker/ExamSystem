#!/usr/bin/env python3
"""考点短标签/旧标签到稳定三级标签的归一规则。"""

from __future__ import annotations

import json
import os
import random
import sqlite3
from collections import Counter
from pathlib import Path


TRANSLATION = "判断推理-逻辑判断-翻译推理"
NUM_DATE = "数量关系-有规律的周期循环与要算准的日期星期-日期推算与余数"
NUM_CYCLE = "数量关系-有规律的周期循环与要算准的日期星期-周期排班与公倍数"
NUM_PERM_BASIC = "数量关系-逢考必有的排列组合与概率-基础原理与几何概型"
NUM_PERM_SPECIAL = "数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）"
NUM_PERM_REVERSE = "数量关系-逢考必有的排列组合与概率-反面容斥与逆向思维"
NUM_EXTREME = "数量关系-既烧脑又能套公式的最值问题-和定最值与构造"
NUM_GEOMETRY = "数量关系-要抓住常考图形的几何问题-平面图形周长与面积"
NUM_TRAVEL = "数量关系-能“七十二变”的行程问题-基础行程、平均速度与相对运动"
NUM_PROFIT = "数量关系-容易找到等式关系的利润问题-利润与分段计费"
NUM_ENGINEERING = "数量关系-熟练掌握可“轻松拿下”的工程问题-工程效率与分段合作"
NUM_EQUATION = "数量关系-和差倍比与方程法-方程、比例与代入验证"
NUM_INCLUSION = "数量关系-容斥问题-集合计数与逆向排除"
NUM_SEQUENCE = "数量关系-数字推理-数字推理"
NUM_SEQUENCE_RECUR = "数量关系-数字推理-递推数列"
NUM_SEQUENCE_SPLIT = "数量关系-数字推理-机械划分"
KNOWN_QUANTITY_TAGS = {
    NUM_DATE,
    NUM_CYCLE,
    NUM_PERM_BASIC,
    NUM_PERM_SPECIAL,
    NUM_PERM_REVERSE,
    NUM_EXTREME,
    NUM_GEOMETRY,
    NUM_TRAVEL,
    NUM_PROFIT,
    NUM_ENGINEERING,
    NUM_EQUATION,
    NUM_INCLUSION,
    NUM_SEQUENCE,
    NUM_SEQUENCE_RECUR,
    NUM_SEQUENCE_SPLIT,
}
COARSE_PRIMARY_TAGS = {
    "数量关系-数学运算-排列组合",
    "数量关系-数学运算-排列组合与概率",
    "排列组合",
}

# 与 solver-canon/07-ziliao.md、知识页卡片逐字一致。
ZILIAO_QI = "资料分析-基础知识-统计术语与常考概念"
ZILIAO_ADD = "资料分析-速算技巧-加法与减法"
ZILIAO_MUL = "资料分析-速算技巧-乘除截位与分数比较"
ZILIAO_415 = "资料分析-速算技巧-415份数法与假设分配法"
ZILIAO_BASE = "资料分析-ABRX类-基期量计算与比较"
ZILIAO_RATE = "资料分析-ABRX类-增长率计算模型"
ZILIAO_DELTA = "资料分析-ABRX类-增长量计算与现期推算"
ZILIAO_SHARE = "资料分析-比重类-现期、基期与隔级比重"
ZILIAO_SHARE_DIFF = "资料分析-比重类-比重趋势、比重差与比值差"
ZILIAO_MIX = "资料分析-盐水类-十字交叉法与混合增长率"
ZILIAO_CMP = "资料分析-比较类-双线法与增量比较"
ZILIAO_AVG = "资料分析-平均类-一般平均值与年均增速/增量"
ZILIAO_SPEC = "资料分析-特殊考点-拉动增长、贡献率与容斥"
ZILIAO_STEPS = "资料分析-每题四步-每题四步"
KNOWN_ZILIAO_TAGS = {
    ZILIAO_QI,
    ZILIAO_ADD,
    ZILIAO_MUL,
    ZILIAO_415,
    ZILIAO_BASE,
    ZILIAO_RATE,
    ZILIAO_DELTA,
    ZILIAO_SHARE,
    ZILIAO_SHARE_DIFF,
    ZILIAO_MIX,
    ZILIAO_CMP,
    ZILIAO_AVG,
    ZILIAO_SPEC,
    ZILIAO_STEPS,
}
ZILIAO_METHOD_TAGS = {ZILIAO_ADD, ZILIAO_MUL, ZILIAO_415, ZILIAO_STEPS}
ZILIAO_QUESTION_TAGS = (
    ZILIAO_QI,
    ZILIAO_BASE,
    ZILIAO_RATE,
    ZILIAO_DELTA,
    ZILIAO_SHARE,
    ZILIAO_SHARE_DIFF,
    ZILIAO_MIX,
    ZILIAO_CMP,
    ZILIAO_AVG,
    ZILIAO_SPEC,
)
ZILIAO_LIGHT_TAGS = (ZILIAO_QI, ZILIAO_BASE)
ZILIAO_FINALE_TAGS = (ZILIAO_SPEC, ZILIAO_SHARE_DIFF, ZILIAO_CMP)
ZILIAO_DEFAULT_PACK = (ZILIAO_BASE, ZILIAO_RATE, ZILIAO_DELTA, ZILIAO_SHARE, ZILIAO_AVG)
ZILIAO_ALT_PACK = (ZILIAO_QI, ZILIAO_SHARE_DIFF, ZILIAO_MIX, ZILIAO_CMP, ZILIAO_SPEC)
ZILIAO_FORMS = (
    ("text", "纯文字，无表无图"),
    ("table", "文字+窄表"),
    ("chart", "文字+柱或饼"),
    ("mixed", "文字+表或图，且至少1题选项是饼/柱图"),
)
ZILIAO_ANSWER_LETTERS = ("A", "B", "C", "D")
ZILIAO_ANSWER_COVER_RATE = 0.8


def is_abcd_plus_one(answers: list[str] | tuple[str, ...]) -> bool:
    """5 题恰好覆盖 A/B/C/D，并有一个字母重复一次。"""
    keys = [str(item).strip().upper() for item in answers]
    if len(keys) != 5 or any(key not in ZILIAO_ANSWER_LETTERS for key in keys):
        return False
    counts = Counter(keys)
    return set(counts) == set(ZILIAO_ANSWER_LETTERS) and sorted(counts.values()) == [1, 1, 1, 2]


def _abcd_plus_one(rng: random.Random) -> list[str]:
    keys = list(ZILIAO_ANSWER_LETTERS) + [rng.choice(ZILIAO_ANSWER_LETTERS)]
    rng.shuffle(keys)
    return keys


def _scattered_answers(rng: random.Random) -> list[str]:
    for _ in range(32):
        keys = [rng.choice(ZILIAO_ANSWER_LETTERS) for _ in range(5)]
        if not is_abcd_plus_one(keys):
            return keys
    return ["A", "A", "B", "B", "C"]


def assign_ziliao_answers(n_materials: int = 4, rng: random.Random | None = None) -> list[dict]:
    """4 篇里约 80%（3 篇）走考场常见分布：ABCD 各一 + 1 个重复；1 篇故意打散。"""
    rng = rng or random.Random()
    n_cover = max(0, min(n_materials, round(n_materials * ZILIAO_ANSWER_COVER_RATE)))
    cover_at = set(rng.sample(range(n_materials), n_cover)) if n_cover else set()
    plans = []
    for index in range(n_materials):
        if index in cover_at:
            keys = _abcd_plus_one(rng)
            kind = "abcd_plus_one"
            label = "ABCD各一+随机"
        else:
            keys = _scattered_answers(rng)
            kind = "scattered"
            label = "打散，不齐ABCD"
        plans.append({"kind": kind, "label": label, "answers": keys})
    return plans


def validate_ziliao_paper_answers(groups: list[list[str]]) -> None:
    """广东日常 4 篇须恰好 3 篇为 ABCD 各一 + 1 随机。"""
    if len(groups) != 4 or any(len(group) != 5 for group in groups):
        raise ValueError("资料分析日常批须 4 篇 × 5 题，才能检查答案分布")
    cover = sum(1 for group in groups if is_abcd_plus_one(group))
    if cover != 3:
        raise ValueError(f"4 篇须恰好 3 篇为 ABCD 各一+1 随机，当前 {cover} 篇")
ZILIAO_BANNED_PRIMARY = {"资料分析-综合分析-综合判断"}
ZILIAO_TAG_ALIASES = {
    "资料分析-简单计算与查找-直接查找": ZILIAO_QI,
    "资料分析-简单查找-直接查找": ZILIAO_QI,
    "资料分析-倍数-倍数计算": ZILIAO_QI,
    "资料分析-基期量-基期量计算": ZILIAO_BASE,
    "资料分析-增长率-同比增长率": ZILIAO_RATE,
    "资料分析-增长率-增长率计算": ZILIAO_RATE,
    "资料分析-增长量-增长量计算与比较": ZILIAO_DELTA,
    "资料分析-比重-比重计算与比较": ZILIAO_SHARE,
    "资料分析-比重-两期比重差": ZILIAO_SHARE_DIFF,
    "资料分析-增长率-年均增长率": ZILIAO_AVG,
    "资料分析-平均数-现期平均数": ZILIAO_AVG,
    "资料分析-平均类-年均增长率": ZILIAO_AVG,
    "资料分析-特殊考点-贡献率": ZILIAO_SPEC,
    "资料分析-综合分析-综合判断": ZILIAO_CMP,
}


def kaodian_family(kaodian: str) -> str:
    """三级标签的前两级：特殊模型与基础原理同属排列组合族。"""
    parts = [part for part in str(kaodian or "").split("-") if part]
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return str(kaodian or "")


def normalize_module(module: str) -> str:
    value = (module or "").strip()
    return {
        "言语理解": "言语理解与表达",
        "言语": "言语理解与表达",
        "数量": "数量关系",
        "判断": "判断推理",
        "资料": "资料分析",
    }.get(value, value or "未分类")


def _has_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def canonicalize(tag: str, module: str = "", subtype: str = "") -> str:
    raw = (tag or "").strip()
    mod = normalize_module(module)
    if (not module or mod == "未分类") and "-" in raw:
        inferred = normalize_module(raw.split("-", 1)[0])
        if inferred != "未分类":
            mod = inferred
    sub = (subtype or "").strip()
    if not raw:
        return f"{mod}-{sub or '未细分'}-未标注"
    if _has_any(raw, "翻译推理", "德摩根", "否后否前", "否定肯定", "只有才", "除非", "必要条件", "逆否"):
        return TRANSLATION

    if mod == "判断推理" and (sub == "逻辑判断" or not sub):
        return TRANSLATION

    if mod == "数量关系":
        if raw in KNOWN_QUANTITY_TAGS:
            return raw
        if sub == "数字推理" or "数字推理" in raw or _has_any(
            raw, "倍数递推", "多级递推积", "机械拆分", "递推数列", "广东数推"
        ):
            if _has_any(raw, "递推", "多级递推积", "倍数递推"):
                return NUM_SEQUENCE_RECUR
            if _has_any(raw, "机械拆分", "机械划分"):
                return NUM_SEQUENCE_SPLIT
            if raw.startswith("数量关系-") and raw.count("-") >= 2:
                return raw
            return NUM_SEQUENCE

        if _has_any(raw, "日期", "星期", "闰年", "跨月", "大月", "闭区间"):
            return NUM_DATE
        if _has_any(raw, "周期", "排班", "公倍数", "轮流作业"):
            return NUM_CYCLE
        if _has_any(raw, "反面容斥", "正难则反", "反面剥离", "反面法"):
            return NUM_PERM_REVERSE
        if _has_any(raw, "插空", "优限", "特殊位置", "位置限制", "隔板"):
            return NUM_PERM_SPECIAL
        if _has_any(raw, "排列", "组合数"):
            return NUM_PERM_BASIC
        if _has_any(raw, "极值", "最值", "统筹"):
            return NUM_EXTREME
        if _has_any(raw, "几何", "矩形", "勾股", "组合图形", "平面割补"):
            return NUM_GEOMETRY
        if _has_any(raw, "行程", "相遇", "单人模型"):
            return NUM_TRAVEL
        if _has_any(raw, "利润", "计费", "促销"):
            return NUM_PROFIT
        if "工程" in raw:
            return NUM_ENGINEERING
        if _has_any(raw, "方程", "特值", "代入验证", "和差倍比"):
            return NUM_EQUATION
        if "容斥" in raw:
            return NUM_INCLUSION
        if raw.startswith("数量关系-") and raw.count("-") >= 2:
            return raw
        return f"数量关系-{sub or '数学运算'}-{raw}"

    if mod == "言语理解与表达":
        if raw.startswith("言语理解与表达-") and raw.count("-") >= 2:
            return raw
        if raw.startswith("片段阅读"):
            if "标题" in raw:
                return "言语理解与表达-片段阅读-标题添加"
            if _has_any(raw, "细节", "未提及", "态度观点"):
                return "言语理解与表达-片段阅读-细节判断"
            return "言语理解与表达-片段阅读-主旨概括"
        if raw.startswith("语句表达"):
            if "排序" in raw:
                return "言语理解与表达-语句表达-语句排序"
            return "言语理解与表达-语句表达-语句填空"
        if raw.startswith("选词填空"):
            return "言语理解与表达-逻辑填空-逻辑填空"
        return f"言语理解与表达-{sub or '未细分'}-{raw}"

    if mod == "资料分析":
        return _canonicalize_ziliao(raw, sub)

    if raw.startswith(f"{mod}-") and raw.count("-") >= 2:
        return raw
    return f"{mod}-{sub or '未细分'}-{raw}"


def _ziliao_from_keywords(raw: str) -> str:
    if _has_any(raw, "每题四步"):
        return ZILIAO_STEPS
    if _has_any(raw, "415", "假设分配"):
        return ZILIAO_415
    if _has_any(raw, "截位", "分数比较"):
        return ZILIAO_MUL
    if _has_any(raw, "削峰填谷", "尾数法", "加法与减法"):
        return ZILIAO_ADD
    if _has_any(raw, "混合增长", "十字交叉", "盐水"):
        return ZILIAO_MIX
    if _has_any(raw, "拉动", "贡献率", "容斥"):
        return ZILIAO_SPEC
    if _has_any(raw, "两期比重", "比重差", "比重趋势", "比值差"):
        return ZILIAO_SHARE_DIFF
    if _has_any(raw, "隔级比重", "基期比重", "现期比重"):
        return ZILIAO_SHARE
    if _has_any(raw, "比重", "占比", "资产负债率", "饼图"):
        return ZILIAO_SHARE
    if "年均" in raw:
        return ZILIAO_AVG
    if _has_any(raw, "平均数", "平均值"):
        return ZILIAO_AVG
    if _has_any(raw, "增长量", "环比增量"):
        return ZILIAO_DELTA
    if _has_any(raw, "增长率", "同比增速"):
        return ZILIAO_RATE
    if _has_any(raw, "基期量", "基期"):
        return ZILIAO_BASE
    if _has_any(raw, "双线", "增量比较"):
        return ZILIAO_CMP
    if _has_any(raw, "倍数", "直接读数", "简单查找", "读数排序", "术语"):
        return ZILIAO_QI
    if _has_any(raw, "综合判断", "综合分析"):
        return ZILIAO_CMP
    return ""


def _canonicalize_ziliao(raw: str, subtype: str = "") -> str:
    if raw in KNOWN_ZILIAO_TAGS:
        return raw
    if raw in ZILIAO_TAG_ALIASES:
        return ZILIAO_TAG_ALIASES[raw]
    mapped = _ziliao_from_keywords(raw)
    if mapped:
        return mapped
    if raw.startswith("资料分析-") and raw.count("-") >= 2:
        return raw
    return f"资料分析-{subtype or '未细分'}-{raw}"


def seed_aliases(conn: sqlite3.Connection) -> dict[str, str]:
    """把当前事件/画像中的全部标签登记成 alias，返回 alias→canonical。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kaodian_aliases (
          alias TEXT PRIMARY KEY,
          canonical TEXT NOT NULL,
          module TEXT NOT NULL,
          subtype TEXT,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    rows = conn.execute(
        """
        SELECT p.kaodian AS alias, p.module, p.subtype
          FROM kaodian_profile p
        UNION
        SELECT e.kaodian AS alias,
               COALESCE(p.module, q.category, '未分类') AS module,
               COALESCE(p.subtype, q.sub_category) AS subtype
          FROM kaodian_events e
          LEFT JOIN kaodian_profile p ON p.kaodian = e.kaodian
          LEFT JOIN questions q ON q.id = e.question_id
        """
    ).fetchall()
    mappings: dict[str, str] = {}
    for alias, module, subtype in rows:
        canonical = canonicalize(alias, module or "", subtype or "")
        normalized_module = normalize_module(module or canonical.split("-", 1)[0])
        canonical_subtype = canonical.split("-")[1] if "-" in canonical else (subtype or "")
        conn.execute(
            """
            INSERT INTO kaodian_aliases(alias, canonical, module, subtype, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(alias) DO UPDATE SET
              canonical = excluded.canonical,
              module = excluded.module,
              subtype = excluded.subtype,
              updated_at = datetime('now')
            """,
            (alias, canonical, normalized_module, canonical_subtype),
        )
        mappings[alias] = canonical
    return mappings


def parse_tags(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(tag).strip() for tag in value if str(tag).strip()] if isinstance(value, list) else []


def question_primary_tag(question: dict) -> str:
    tags = question.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if str(tag).strip():
                return str(tag).strip()
    knowledge = question.get("knowledge_point")
    if isinstance(knowledge, str) and knowledge.strip():
        return knowledge.strip()
    points = question.get("knowledge_points")
    if isinstance(points, list):
        for tag in points:
            if str(tag).strip():
                return str(tag).strip()
    return ""


def registered_canonical_tags() -> set[str]:
    """已 --register 进画像的三级标签，允许作为新补录考点出题。"""
    path = Path(os.environ.get("EXAM_DB") or Path(__file__).resolve().parents[1] / "data" / "exam.db")
    if not path.is_file():
        return set()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute("SELECT kaodian FROM kaodian_profile").fetchall()
        conn.close()
    except sqlite3.Error:
        return set()
    return {
        str(row[0])
        for row in rows
        if row[0] and str(row[0]).count("-") >= 2 and not str(row[0]).startswith("未分类")
    }


def validate_ai_primary_tag(raw: str, category: str = "") -> str:
    """AI 练题主标签必须能落到知识卡片或已登记的新补录考点。"""
    tag = (raw or "").strip()
    if not tag:
        raise ValueError("缺规范考点标签 tags[0]（也可用 knowledge_point）")
    if tag in COARSE_PRIMARY_TAGS:
        raise ValueError(
            f"标签过粗: {tag}。排列组合必须写成 "
            f"{NUM_PERM_BASIC} / {NUM_PERM_SPECIAL} / {NUM_PERM_REVERSE} 之一"
        )
    if tag.count("-") < 2:
        raise ValueError(f"标签必须是 模块-一级-二级，收到: {tag}")
    canonical = canonicalize(tag, category)
    module = (category or tag.split("-", 1)[0]).strip()
    if tag in ZILIAO_BANNED_PRIMARY or tag.endswith("-综合判断"):
        raise ValueError(
            "不要写资料分析-综合分析-综合判断。"
            "末题可以出综合判断句，tags[0] 打在正确项最重的那张知识库主标签上。"
        )
    if module == "数量关系" and canonical not in KNOWN_QUANTITY_TAGS and canonical not in registered_canonical_tags():
        raise ValueError(
            f"数量关系标签无法归一到知识卡片或已登记考点: {tag} → {canonical}。"
            "新考点先 kaodian_profile.py --register 再出题。"
        )
    if module == "资料分析" or canonical.startswith("资料分析-"):
        if tag in ZILIAO_METHOD_TAGS or canonical in ZILIAO_METHOD_TAGS:
            raise ValueError(
                "速算技巧 / 每题四步是方法卡，不能当 tags[0]。"
                "改用 ABRX / 比重 / 平均 / 比较 / 盐水 / 贡献率等出题槽。"
            )
        if tag not in KNOWN_ZILIAO_TAGS:
            hint = f"应写成 {canonical}" if canonical in KNOWN_ZILIAO_TAGS else "词表见 solver-canon/07-ziliao.md"
            raise ValueError(f"资料分析 tags[0] 必须是知识库主标签，收到: {tag}。{hint}")
        return tag
    return canonical


# ─────────────────────────────────────────────
# 数量关系卷面结构校验（广东日常 15 = 数字推理 5 + 数学运算 10）
# ─────────────────────────────────────────────
def _is_shuliang(question: dict) -> bool:
    return str(question.get("category") or "") == "数量关系"


def _is_shuzi_tuili(question: dict) -> bool:
    blob = f"{question.get('sub_category') or ''} {question_primary_tag(question)}"
    return "数字推理" in blob


def is_shuliang_paper(questions: list[dict]) -> bool:
    """判定是否为一份数量关系卷：≥10 题且数量关系占多数。"""
    items = [q for q in questions if isinstance(q, dict)]
    shuliang = [q for q in items if _is_shuliang(q)]
    return len(shuliang) >= 10 and len(shuliang) * 2 >= len(items)


def validate_shuliang_paper(questions: list[dict]) -> None:
    """广东数量卷硬规则：不得 0 数字推理；满 15 题须为数字推理 5 + 数学运算 10。"""
    if not is_shuliang_paper(questions):
        return
    shuliang = [q for q in questions if _is_shuliang(q)]
    seq = sum(1 for q in shuliang if _is_shuzi_tuili(q))
    if seq == 0:
        raise ValueError("数量关系卷不得 0 数字推理：广东通用卷数量必含数字推理，弱项倾斜也不能整卷缺失")
    if len(shuliang) == 15 and seq != 5:
        raise ValueError(f"广东数量 15 题须为数字推理 5 + 数学运算 10，当前数字推理 {seq} 题")


# ─────────────────────────────────────────────
# 资料分析：四篇考点骨架不得同构（禁“四篇同一五连招”）
# ─────────────────────────────────────────────
def validate_ziliao_variety(questions: list[dict]) -> None:
    materials: dict[str, list[str]] = {}
    for question in questions:
        if str(question.get("category") or "") != "资料分析":
            continue
        material_id = str(question.get("material_id") or "")
        if not material_id:
            continue
        materials.setdefault(material_id, []).append(question_primary_tag(question))
    if len(materials) >= 4:
        skeletons = {tuple(tags) for tags in materials.values()}
        if len(skeletons) == 1:
            raise ValueError(
                "资料分析四篇不得复制同一套五连招：Q1–Q4 考点须跨篇错开，"
                "不能四篇按同一顺序同一家族出题"
            )

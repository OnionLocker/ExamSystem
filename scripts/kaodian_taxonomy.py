#!/usr/bin/env python3
"""考点短标签/旧标签到稳定三级标签的归一规则。"""

from __future__ import annotations

import json
import os
import random
import re
import sqlite3
from collections import Counter
from pathlib import Path


from fenbi_taxonomy import (
    LEGACY_TO_FENBI,
    fenbi_l3_by_module,
    fenbi_l3_of,
    fenbi_l3_tags,
    is_fenbi_l3,
    is_fenbi_l4,
    is_fenbi_primary,
    kaodian_family,
    lookup_fenbi_short,
    parse_fenbi_tag,
    static_alias,
    tags_for_canon_lookup,
)

# 粉笔 L3 主标签（新一代出题只发这些，或挂在它们下面的 L4）。
TRANSLATION = "判断推理-逻辑判断-翻译推理"
PD_SUPPORT = "判断推理-逻辑判断-加强题型"
PD_WEAKEN = "判断推理-逻辑判断-削弱题型"
PD_CAUSE = "判断推理-逻辑判断-原因解释"
PD_RATIO = "判断推理-逻辑判断-原因解释"
PD_DAILY = "判断推理-逻辑判断-日常结论"
PD_TRUEFALSE = "判断推理-逻辑判断-真假推理"
PD_QUICK = "判断推理-逻辑判断-论证结构"
PD_ARRANGE = "判断推理-逻辑判断-组合排列-单题"
PD_DEFECT = "判断推理-逻辑判断-论证缺陷"
KNOWN_PANDUAN_TAGS = set(fenbi_l3_by_module().get("判断推理", ()))
NUM_DATE = "数量关系-数学运算-星期日期问题"
NUM_CYCLE = "数量关系-数学运算-周期问题"
NUM_PERM = "数量关系-数学运算-排列组合问题"
NUM_PERM_BASIC = NUM_PERM
NUM_PERM_SPECIAL = NUM_PERM
NUM_PERM_REVERSE = NUM_PERM
NUM_PERM_POSITION = NUM_PERM
NUM_PERM_GROUPING = NUM_PERM
NUM_PERM_MISC = NUM_PERM
NUM_PERM_DERANGE = NUM_PERM
NUM_PROB = "数量关系-数学运算-概率问题"
NUM_PROB_CLASSIC = NUM_PROB
NUM_PROB_INDEPENDENT = NUM_PROB
NUM_EXTREME = "数量关系-数学运算-最值问题"
NUM_EXTREME_DRAWER = NUM_EXTREME
NUM_EXTREME_REVERSE = NUM_EXTREME
NUM_EXTREME_QUAD = "数量关系-数学运算-函数最值问题"
NUM_GEOMETRY = "数量关系-数学运算-几何问题"
NUM_TRAVEL = "数量关系-数学运算-行程问题"
NUM_TRAVEL_MEDIUM = NUM_TRAVEL
NUM_TRAVEL_LENGTH = NUM_TRAVEL
NUM_TRAVEL_MULTI = NUM_TRAVEL
NUM_PROFIT = "数量关系-数学运算-经济利润问题"
NUM_ENGINEERING = "数量关系-数学运算-工程问题"
NUM_EQUATION = "数量关系-数学运算-和差倍比问题"
NUM_INCLUSION = "数量关系-数学运算-容斥原理问题"
NUM_CATTLE = "数量关系-数学运算-牛吃草问题"
NUM_AVERAGE = "数量关系-数学运算-平均数问题"
NUM_SEQUENCE_RECUR = "数量关系-数字推理-递推数列"
NUM_SEQUENCE_SPLIT = "数量关系-数字推理-机械划分"
NUM_SEQUENCE = "数量关系-数字推理-数字推理-其他"
KNOWN_QUANTITY_TAGS = set(fenbi_l3_by_module().get("数量关系", ()))
KNOWN_YANYU_TAGS = set(fenbi_l3_by_module().get("言语理解与表达", ()))
KNOWN_ZHENGZHI_TAGS = set(fenbi_l3_by_module().get("政治理论", ()))
KNOWN_CHANGSHI_TAGS = set(fenbi_l3_by_module().get("常识判断", ()))
SCIENCE_TAG_RE = re.compile(
    r"^科学推理-(?:力学|压强与浮力|电学|热学与光学|化学|生物|地理)-[^-].+$"
)
YANYU_MAIN = "言语理解与表达-片段阅读-中心理解题"
YANYU_DETAIL = "言语理解与表达-片段阅读-细节判断题"
YANYU_TITLE = "言语理解与表达-片段阅读-标题填入题"
YANYU_ORDER = "言语理解与表达-语句表达-语句排序题"
YANYU_FILL = "言语理解与表达-语句表达-语句填空题"
YANYU_LOGIC = "言语理解与表达-逻辑填空-混搭填空"
# 旧合并标签：历史题继续留着，但不再往上面出新题。
LEGACY_TAGS = set(LEGACY_TO_FENBI)

COARSE_PRIMARY_TAGS = {
    "数量关系-数学运算-排列组合",
    "数量关系-数学运算-排列组合与概率",
    "数量关系-数学运算",
    "数量关系-数字推理",
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


CANON_DIR = Path(__file__).resolve().parents[1] / "hermes-skills" / "gd-gongkao-coach" / "references" / "solver-canon"
CANON_FILES = {
    "判断推理": "05-panduan.md",
    "数量关系": "04-shuliang.md",
    "言语理解与表达": "03-yanyu.md",
}
_SECTION = re.compile(r"^\*\*([^*：\n]+?)(?:（[^）\n]*）)?：\*\*", re.M)
_TAG_IN_TEXT = re.compile(r"`([^`]*-[^`]*-[^`]*)`")


def canon_index(module: str = "") -> list[dict]:
    """把 solver-canon 读成 [{module,title,一级,bullets:[{text,tag}],tags:[...]}]。

    bullets 是卡片「考场步骤」里的顶层条目，即这张卡覆盖的考法；
    tag 为空表示这条考法还没有自己的二级标签（和同卡其它考法共用一个）。
    """
    cards = []
    for mod, name in CANON_FILES.items():
        if module and mod != module:
            continue
        path = CANON_DIR / name
        if not path.is_file():
            continue
        for chunk in path.read_text(encoding="utf-8").split("\n### ")[1:]:
            title = chunk.split("\n", 1)[0].strip()
            marks = [(m.group(1), m.start(), m.end()) for m in _SECTION.finditer(chunk)]
            sections = {
                n: chunk[e : (marks[i + 1][1] if i + 1 < len(marks) else len(chunk))].strip()
                for i, (n, _s, e) in enumerate(marks)
            }
            bullets = []
            for line in sections.get("考场步骤", "").split("\n"):
                if not line.startswith("- "):
                    continue
                found = _TAG_IN_TEXT.findall(line)
                head = re.split(r"[：:（(]", line[2:].strip("*· "), 1)[0].strip("*· ")
                bullets.append({"text": head[:28], "tag": found[0] if found else ""})
            tags = [t for t in _TAG_IN_TEXT.findall(chunk)]
            cards.append({
                "module": mod,
                "title": title,
                "bullets": bullets,
                "tags": sorted({t for t in tags}),
            })
    return cards


def normalize_module(module: str) -> str:
    value = (module or "").strip()
    return {
        "言语理解": "言语理解与表达",
        "言语": "言语理解与表达",
        "数量": "数量关系",
        "判断": "判断推理",
        "资料": "资料分析",
        "政治": "政治理论",
        "常识": "常识判断",
    }.get(value, value or "未分类")


def _has_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def canonicalize(tag: str, module: str = "", subtype: str = "") -> str:
    raw = (tag or "").strip()
    # 科学推理在题库里是独立模块；粉笔树的历史别名把它挂在判断推理下，
    # 出题入口不能沿用那个展示归类，否则会走错 20 题判断卷规则。
    if raw.startswith("科学推理-") and normalize_module(module) in {"", "科学推理"}:
        return raw
    # Hermes 显式 --register 过的标签是权威的，不能再被下面的关键词兜底改写。
    # 资料分析例外：它是封闭词表，旧标签必须继续被归一到白名单上。
    if (
        raw.count("-") >= 2
        and not raw.startswith("资料分析-")
        and normalize_module(module) != "资料分析"
        and raw in registered_canonical_tags()
    ):
        return raw
    mapped = static_alias(raw)
    if mapped:
        return mapped
    if is_fenbi_primary(raw):
        return raw
    short = lookup_fenbi_short(raw)
    if short:
        return short
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

    if mod == "判断推理":
        if raw in KNOWN_PANDUAN_TAGS or is_fenbi_primary(raw):
            return raw
        if _has_any(raw, "归因", "因果倒置", "他因", "原因解释"):
            return PD_CAUSE
        if _has_any(raw, "削弱", "质疑", "反驳"):
            return PD_WEAKEN
        if _has_any(raw, "加强", "支持", "前提", "假设"):
            return PD_SUPPORT
        if _has_any(raw, "论证缺陷"):
            return PD_DEFECT
        if _has_any(raw, "比例", "解释说明", "解释型", "原因解释"):
            return PD_RATIO
        if _has_any(raw, "真假", "矛盾关系", "反对关系", "范畴"):
            return PD_TRUEFALSE
        if _has_any(raw, "组合排列", "排列匹配", "对应关系"):
            return PD_ARRANGE
        if _has_any(raw, "日常", "分析推理"):
            return PD_DAILY
        if _has_any(raw, "秒杀", "速解", "论证结构"):
            return PD_QUICK
        if raw.startswith("判断推理-") and is_fenbi_primary(raw):
            return raw
        if sub == "逻辑判断" or not sub:
            return TRANSLATION

    if mod == "数量关系":
        if raw in KNOWN_QUANTITY_TAGS or is_fenbi_primary(raw):
            return raw
        if "牛吃草" in raw:
            return NUM_CATTLE
        if _has_any(raw, "流水行船", "顺水", "逆水", "扶梯", "漂流", "过桥", "车长", "队伍行进",
                    "多次相遇", "环形追及", "环形相遇", "行程", "相遇", "单人模型", "平均速度", "追及"):
            return NUM_TRAVEL
        if sub == "数字推理" or "数字推理" in raw or _has_any(
            raw, "倍数递推", "多级递推积", "机械拆分", "递推数列", "广东数推",
            "基础数列", "多级数列", "幂次数列", "分数数列", "作商", "作和作积",
        ):
            if _has_any(raw, "递推", "多级递推积", "倍数递推"):
                return NUM_SEQUENCE_RECUR
            if _has_any(raw, "机械拆分", "机械划分"):
                return NUM_SEQUENCE_SPLIT
            hit = lookup_fenbi_short(raw)
            if hit:
                return hit
            return NUM_SEQUENCE

        if _has_any(raw, "日期", "星期", "闰年", "跨月", "大月", "闭区间"):
            return NUM_DATE
        if _has_any(raw, "周期", "排班", "公倍数", "轮流作业"):
            return NUM_CYCLE
        if _has_any(raw, "古典概型", "同组概率", "抽签", "伯努利", "赛制", "独立重复", "几何概型"):
            return NUM_PROB
        if _has_any(raw, "反面容斥", "正难则反", "反面剥离", "反面法", "捆绑", "插空", "优限",
                    "相邻限制", "不相邻", "特殊位置", "位置限制", "涂色", "染色", "插板", "隔板",
                    "分堆", "分组分配", "定序", "消序", "错位", "圆桌", "环形排列", "网格路径",
                    "最短路径", "排列", "组合数"):
            return NUM_PERM
        if _has_any(raw, "二次函数", "乘积极值", "均值定理", "和定差小", "函数最值"):
            return NUM_EXTREME_QUAD
        if _has_any(raw, "抽屉", "最不利", "反向构造", "多集合最值", "反向相加", "总数倒扣",
                    "极值", "最值"):
            return NUM_EXTREME
        if "统筹" in raw:
            return "数量关系-数学运算-统筹规划问题"
        if _has_any(raw, "几何", "矩形", "勾股", "组合图形", "平面割补"):
            return NUM_GEOMETRY
        if _has_any(raw, "利润", "计费", "促销"):
            return NUM_PROFIT
        if "工程" in raw:
            return NUM_ENGINEERING
        if _has_any(raw, "不定方程"):
            return "数量关系-数学运算-不定方程问题"
        if _has_any(raw, "方程", "特值", "代入验证", "和差倍比"):
            return NUM_EQUATION
        if "容斥" in raw:
            return NUM_INCLUSION
        if _has_any(raw, "平均数", "平均值"):
            return NUM_AVERAGE
        if _has_any(raw, "溶液", "浓度"):
            return "数量关系-数学运算-溶液问题"
        if is_fenbi_primary(raw):
            return raw
        return f"数量关系-{sub or '数学运算'}-{raw}"

    if mod == "言语理解与表达":
        if raw.startswith("言语理解-"):
            raw = "言语理解与表达-" + raw.split("-", 1)[1]
        mapped = static_alias(raw)
        if mapped:
            return mapped
        if is_fenbi_primary(raw):
            return raw
        short = lookup_fenbi_short(raw)
        if short:
            return short
        if "片段阅读" in raw or sub == "片段阅读":
            if "标题" in raw:
                return YANYU_TITLE
            if _has_any(raw, "细节", "未提及", "态度观点"):
                return YANYU_DETAIL
            return YANYU_MAIN
        if "语句表达" in raw or sub == "语句表达":
            if "排序" in raw:
                return YANYU_ORDER
            if "接语" in raw:
                return "言语理解与表达-语句表达-接语选择题"
            return YANYU_FILL
        if _has_any(raw, "选词填空", "逻辑填空"):
            if "成语" in raw:
                return "言语理解与表达-逻辑填空-成语填空"
            if "实词" in raw:
                return "言语理解与表达-逻辑填空-实词填空"
            return YANYU_LOGIC
        return f"言语理解与表达-{sub or '未细分'}-{raw}"

    if mod in {"政治理论", "常识判断"}:
        if is_fenbi_primary(raw):
            return raw
        short = lookup_fenbi_short(raw)
        if short:
            return short
        if raw.startswith(f"{mod}-") and raw.count("-") >= 2:
            return raw
        return f"{mod}-{sub or '未细分'}-{raw}"

    if mod == "资料分析":
        return _canonicalize_ziliao(raw, sub)

    if is_fenbi_primary(raw):
        return raw
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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _upsert_alias(conn: sqlite3.Connection, alias: str, canonical: str, module: str = "", subtype: str = "") -> None:
    parsed = parse_fenbi_tag(canonical)
    normalized_module = normalize_module(module or (parsed[0] if parsed else canonical.split("-", 1)[0]))
    canonical_subtype = parsed[1] if parsed else (canonical.split("-")[1] if "-" in canonical else subtype)
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


def seed_aliases(conn: sqlite3.Connection) -> dict[str, str]:
    """把旧 KNOWN_* 长标签和当前事件/画像登记成 alias，返回 alias→canonical。"""
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
    mappings: dict[str, str] = {}
    for alias, canonical in LEGACY_TO_FENBI.items():
        _upsert_alias(conn, alias, canonical)
        mappings[alias] = canonical
    for tag in fenbi_l3_tags():
        _upsert_alias(conn, tag, tag)
        mappings[tag] = tag
    rows = []
    if _table_exists(conn, "kaodian_profile"):
        rows.extend(conn.execute("SELECT kaodian, module, subtype FROM kaodian_profile").fetchall())
    if _table_exists(conn, "kaodian_events"):
        if _table_exists(conn, "questions"):
            rows.extend(conn.execute(
                """
                SELECT e.kaodian,
                       COALESCE(p.module, q.category, '未分类'),
                       COALESCE(p.subtype, q.sub_category)
                  FROM kaodian_events e
                  LEFT JOIN kaodian_profile p ON p.kaodian = e.kaodian
                  LEFT JOIN questions q ON q.id = e.question_id
                """
            ).fetchall())
        else:
            rows.extend(conn.execute(
                """
                SELECT e.kaodian, COALESCE(p.module, '未分类'), p.subtype
                  FROM kaodian_events e
                  LEFT JOIN kaodian_profile p ON p.kaodian = e.kaodian
                """
            ).fetchall())
    for alias, module, subtype in rows:
        canonical = canonicalize(alias, module or "", subtype or "")
        _upsert_alias(conn, alias, canonical, module or "", subtype or "")
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


_REGISTERED_CACHE: dict[str, tuple[float, set[str]]] = {}


def registered_canonical_tags() -> set[str]:
    """已 --register 进画像的三级标签，允许作为新补录考点出题。

    canonicalize 每次都要问，所以按库文件 mtime 缓存；新登记会立刻失效重读。
    """
    path = Path(os.environ.get("EXAM_DB") or Path(__file__).resolve().parents[1] / "data" / "exam.db")
    if not path.is_file():
        return set()
    key = str(path)
    stamp = path.stat().st_mtime
    hit = _REGISTERED_CACHE.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute("SELECT kaodian FROM kaodian_profile").fetchall()
        conn.close()
    except sqlite3.Error:
        return set()
    found = {
        str(row[0])
        for row in rows
        if row[0] and str(row[0]).count("-") >= 2 and not str(row[0]).startswith("未分类")
    }
    _REGISTERED_CACHE[key] = (stamp, found)
    return found


def assert_registerable_tag(kaodian: str, module: str = "") -> str:
    """新叶子必须挂在已有粉笔 L3 下：模块-一级-二级-子题型。"""
    raw = (kaodian or "").strip()
    if not raw:
        raise ValueError("缺考点标签")
    if raw.startswith("资料分析-") or normalize_module(module) == "资料分析":
        raise ValueError("资料分析是封闭词表，不能 --register 扩")
    if is_fenbi_primary(raw):
        return raw
    raise ValueError(
        "新叶子必须挂在粉笔 L3 下，写成 模块-一级-二级-子题型，"
        f"例如 {NUM_AVERAGE}-加权平均数。收到: {raw}"
    )


def validate_ai_primary_tag(raw: str, category: str = "") -> str:
    """AI 练题主标签必须落到粉笔 L3、其下 L4，或已登记的新补录考点。"""
    tag = (raw or "").strip()
    if not tag:
        raise ValueError("缺规范考点标签 tags[0]（也可用 knowledge_point）")
    # 科学推理是独立模块；带完整前缀的标签不能因调用方省略 category
    # （例如 CLI 未传 --module 或旧题库行缺 category）而落入粉笔旧树。
    if normalize_module(category) == "科学推理" or tag.startswith("科学推理-"):
        if not SCIENCE_TAG_RE.fullmatch(tag):
            raise ValueError(
                "科学推理标签必须写成 科学推理-学科-具体考点，"
                f"收到: {tag}"
            )
        return tag
    if tag in COARSE_PRIMARY_TAGS:
        raise ValueError(
            f"标签过粗: {tag}。数量请写成粉笔三级，如 {NUM_PERM} / {NUM_AVERAGE}"
        )
    parsed = parse_fenbi_tag(tag)
    if not parsed and tag.count("-") < 2 and not lookup_fenbi_short(tag):
        raise ValueError(f"标签必须是 模块-一级-二级，收到: {tag}")
    canonical = canonicalize(tag, category)
    parsed_canon = parse_fenbi_tag(canonical)
    module = (category or (parsed_canon[0] if parsed_canon else tag.split("-", 1)[0])).strip()
    if tag in ZILIAO_BANNED_PRIMARY or tag.endswith("-综合判断"):
        raise ValueError(
            "不要写资料分析-综合分析-综合判断。"
            "末题可以出综合判断句，tags[0] 打在正确项最重的那张知识库主标签上。"
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
    if is_fenbi_primary(canonical) or canonical in registered_canonical_tags():
        return canonical
    raise ValueError(
        f"标签无法归一到粉笔树或已登记考点: {tag} → {canonical}。"
        f"新叶子先 kaodian_profile.py --register '{fenbi_l3_of(canonical) or '模块-一级-二级'}-子题型'"
    )


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


def validate_ziliao_variety(questions: list[dict]) -> None:
    """Keep as a compatibility hook; variation is a generation preference."""
    return None

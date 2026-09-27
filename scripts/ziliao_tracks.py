#!/usr/bin/env python3
"""资料分析双轨：粤考日练（轨 A）与经典计算加练（轨 B）。"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from pathlib import Path

from kaodian_taxonomy import (
    ZILIAO_AVG,
    ZILIAO_BASE,
    ZILIAO_CMP,
    ZILIAO_DELTA,
    ZILIAO_MIX,
    ZILIAO_QI,
    ZILIAO_RATE,
    ZILIAO_SHARE,
    ZILIAO_SHARE_DIFF,
    ZILIAO_SPEC,
)

TRACK_GD = "gd"
TRACK_CLASSIC = "classic"
TRACKS = (TRACK_GD, TRACK_CLASSIC)

FAMILY_DETAIL = "detail"
FAMILY_JUDGE = "judge"
FAMILY_SHARE_ADD = "share_add"
FAMILY_GROWTH = "growth"
FAMILY_BASE_SHARE = "base_share"
FAMILY_AVG_CMP = "avg_cmp"
FAMILY_MIX_PULL = "mix_pull"

# 轨 A 20 题配额（可微调，精神不变）
GD_QUOTA = {
    FAMILY_DETAIL: (3, 4),
    FAMILY_JUDGE: (4, 4),
    FAMILY_SHARE_ADD: (3, 4),
    FAMILY_GROWTH: (3, 3),
    FAMILY_BASE_SHARE: (2, 2),
    FAMILY_AVG_CMP: (2, 2),
    FAMILY_MIX_PULL: (0, 2),
}

# 闸门认的四种综合判断（generation_gate._judge_form）。四篇 Q5 各用一种，禁止全写成「正确/有误」。
GD_JUDGE_FORMS = (
    {"material": "M01", "form": "属实", "stem": "根据资料，以下说法可以判断属实的是"},
    {"material": "M02", "form": "无法推出", "stem": "不能从上述资料中推出的是"},
    {"material": "M03", "form": "计数", "stem": "根据资料，下列说法正确的有"},
    {"material": "M04", "form": "能推出", "stem": "能够从上述资料中推出的是"},
)

# 秒杀找数 / 一步 / 两步 / 四陈述综合
FAMILY_DIFFICULTY = {
    FAMILY_DETAIL: 1,
    FAMILY_SHARE_ADD: 2,
    FAMILY_GROWTH: 3,
    FAMILY_BASE_SHARE: 3,
    FAMILY_AVG_CMP: 3,
    FAMILY_MIX_PULL: 4,
    FAMILY_JUDGE: 4,
}

CLASSIC_TAGS = [
    ZILIAO_QI, ZILIAO_BASE, ZILIAO_DELTA, ZILIAO_RATE, ZILIAO_SHARE,
    ZILIAO_SHARE_DIFF, ZILIAO_AVG, ZILIAO_CMP, ZILIAO_MIX, ZILIAO_SPEC,
]

GD_FORMATS_4 = ["text", "table", "chart", "chart"]
CLASSIC_FORMATS_4 = ["chart", "table", "text", "chart"]

# 图表匹配：本轮只留挂点，不强制、不假实现选项图配额
CHART_MATCH_HOOK = {
    "implemented": False,
    "family": "chart_match",
    "reason": (
        "粤考常见「下列哪幅图反映……」需为 A–D 各渲一张饼/柱/折线并挂 options[].images。"
        "当前 runner 只渲染材料图；render_option_figures() 已预留："
        "若题目自带 options[].figure 则程序出图，但轨 A 配额不强制本槽，避免假实现。"
    ),
}

_YEAR = re.compile(r"20\d{2}")
_CMP_HINT = re.compile(r"最快|最多|最少|最高|最低|超过|高于|低于|排序|同比增速最快")


def resolve_gemini_model() -> str:
    return (
        os.environ.get("ZILIAO_GEMINI_MODEL")
        or os.environ.get("DAILY_GEMINI_MODEL")
        or os.environ.get("QUIZ_LITE_MODEL")
        or "gemini-3.8-flash-high"
    )


def has_gemini_credentials() -> bool:
    if os.environ.get("CLIPROXY_API_KEY", "").strip():
        return True
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.is_file():
        return False
    for line in env_path.read_text().splitlines():
        if line.startswith("CLIPROXY_API_KEY=") and line.split("=", 1)[1].strip():
            return True
    return False


def _slot(family: str, tag: str, brief: str, paper_tier: str = "mid") -> dict:
    return {
        "tag": tag,
        "count": 1,
        "family": family,
        "brief": brief,
        "difficulty": paper_tier,
        "difficulty_score": difficulty_score(family, paper_tier),
    }


def difficulty_score(family: str, paper_tier: str = "mid") -> int:
    base = FAMILY_DIFFICULTY.get(family, 3)
    if paper_tier == "hard":
        return min(5, base + (0 if family == FAMILY_DETAIL else 1 if family in {FAMILY_MIX_PULL, FAMILY_JUDGE} else 0))
    if paper_tier == "easy" and family not in {FAMILY_DETAIL, FAMILY_JUDGE}:
        return max(1, base - 1)
    return base


def classify_judge_form(stem: str) -> str:
    """与 generation_gate._judge_form 同一分类，供配额和题级回炉使用。"""
    text = str(stem or "")
    if "正确的有" in text:
        return "计数"
    if ("不能" in text or "无法" in text) and "推" in text:
        return "无法推出"
    if "属实" in text:
        return "属实"
    if "能够" in text and "推" in text:
        return "能推出"
    if "有误" in text or "不正确" in text or "错误的是" in text:
        return "有误"
    if "正确的是" in text:
        return "正确"
    return ""


def judge_slot_fields(material_index: int) -> dict:
    spec = GD_JUDGE_FORMS[material_index % len(GD_JUDGE_FORMS)]
    return {
        "judge_form": spec["form"],
        "judge_stem": spec["stem"],
        "brief": (
            f"综合正误。题干必须以「{spec['stem']}」开头（形式={spec['form']}）。"
            "禁止改成「下列说法正确的是」或「下列说法有误的是」。"
            "四陈述埋时间偷换、累计vs当年、未给出不能比、范围扩大。"
        ),
    }


def gd_slots_20(paper_tier: str = "mid") -> list[dict]:
    """4×5 粤考日练槽位：M01 长文 3 细节/综合 + 2 轻量计算；每篇 Q5 综合正误且问法跨篇轮换。"""
    s = lambda family, tag, brief: _slot(family, tag, brief, paper_tier)
    slots = [
        # M01 长文字
        s(FAMILY_DETAIL, ZILIAO_QI, "文字细节定位：主题/分类/口径，直接找数，勿大计算"),
        s(FAMILY_DETAIL, ZILIAO_QI, "细节排除：未提及/不包括；利用材料里用不到的干扰指标"),
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, "现期比重或简单加减，一步可算，可用成数/区间"),
        s(FAMILY_GROWTH, ZILIAO_DELTA, "增长量或简单增长率，一步到两步"),
        s(FAMILY_JUDGE, ZILIAO_CMP, ""),
        # M02 表
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, "现期比重或表内简单加减"),
        s(FAMILY_GROWTH, ZILIAO_RATE, "同比增长率计算或区间判断"),
        s(FAMILY_BASE_SHARE, ZILIAO_BASE, "基期量，或由现期与增速反推"),
        s(FAMILY_AVG_CMP, ZILIAO_AVG, "平均数或年均增量；比较则枚举范围内全部点"),
        s(FAMILY_JUDGE, ZILIAO_CMP, ""),
        # M03 图
        s(FAMILY_SHARE_ADD, ZILIAO_QI, "简单加减或现期量查找，真正读图"),
        s(FAMILY_GROWTH, ZILIAO_DELTA, "增长量，读图序列"),
        s(FAMILY_BASE_SHARE, ZILIAO_SHARE_DIFF, "基期比重或两期比重差"),
        s(FAMILY_AVG_CMP, ZILIAO_CMP, "比较类：枚举题干年份范围内全部点，禁止漏年"),
        s(FAMILY_JUDGE, ZILIAO_CMP, ""),
        # M04 图：补足细节 + 至多 1 道混合/拉动
        s(FAMILY_DETAIL, ZILIAO_QI, "读图细节定位或排除"),
        s(FAMILY_DETAIL, ZILIAO_QI, "细节排除或口径辨析，可含未给出不能比"),
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, "现期比重，一步"),
        s(FAMILY_MIX_PULL, ZILIAO_MIX, "混合增速或拉动/贡献率，整套至多 1–2 道，不要再叠第二道"),
        s(FAMILY_JUDGE, ZILIAO_CMP, ""),
    ]
    for material_index, slot_index in enumerate((4, 9, 14, 19)):
        slots[slot_index].update(judge_slot_fields(material_index))
    return slots


def gd_slots_5(paper_tier: str = "mid") -> list[dict]:
    s = lambda family, tag, brief: _slot(family, tag, brief, paper_tier)
    slots = [
        s(FAMILY_DETAIL, ZILIAO_QI, "文字或图表细节定位/排除"),
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, "现期比重或简单加减"),
        s(FAMILY_GROWTH, ZILIAO_RATE, "增长率或增长量"),
        s(FAMILY_AVG_CMP, ZILIAO_CMP, "比较或平均；比较须枚举范围内全部点"),
        s(FAMILY_JUDGE, ZILIAO_CMP, ""),
    ]
    slots[-1].update(judge_slot_fields(0))
    return slots


def classic_slots(count: int, materials: int, paper_tier: str = "mid") -> list[dict]:
    """教材 10 类轮转（每类在 20 题整套上各 2 道）。"""
    result = []
    group_size = max(1, math.ceil(count / max(1, materials)))
    for index in range(count):
        group = index // group_size
        tag = CLASSIC_TAGS[(group * 5 + index % 5) % len(CLASSIC_TAGS)]
        result.append({
            "tag": tag,
            "count": 1,
            "family": "classic",
            "brief": "经典计算技法，可出混合/拉动/比重差",
            "difficulty": paper_tier,
            "difficulty_score": {"easy": 2, "mid": 3, "hard": 4}[paper_tier],
        })
    return result


def default_formats(track: str, n: int, targeted: bool) -> list[str]:
    if targeted:
        return ["chart", "table", "text", "chart"][:n]
    if track == TRACK_GD and n == 4:
        return list(GD_FORMATS_4)
    if n == 4:
        return list(CLASSIC_FORMATS_4)
    return ["chart", "table", "text", "chart"][:n]


def resolve_track_slots(track: str, count: int, materials: int, paper_tier: str,
                        targeted_slots: list[dict] | None = None) -> list[dict]:
    if targeted_slots:
        return [dict(slot) for slot in targeted_slots]
    if track == TRACK_GD and count == 20 and materials == 4:
        return gd_slots_20(paper_tier)
    if track == TRACK_GD and count == 5 and materials == 1:
        return gd_slots_5(paper_tier)
    if track == TRACK_GD:
        # 非整套：按篇尽量保留 Q5 综合，其余向粤向家族轮转
        base = gd_slots_20(paper_tier)
        picked = []
        for index in range(count):
            material = index // max(1, -(-count // materials))
            pos = index % 5
            if pos == 4 or (count >= materials * 5 and (index + 1) % 5 == 0):
                picked.append(dict(base[4]))
            else:
                picked.append(dict(base[index % 15]))
        return picked[:count]
    return classic_slots(count, materials, paper_tier)


def family_counts(slots: list[dict]) -> dict[str, int]:
    return dict(Counter(str(slot.get("family") or "") for slot in slots))


def validate_gd_quota(slots: list[dict], *, count: int | None = None) -> None:
    count = count if count is not None else len(slots)
    if count != 20:
        return
    counts = family_counts(slots)
    for family, (lo, hi) in GD_QUOTA.items():
        got = counts.get(family, 0)
        if not lo <= got <= hi:
            raise ValueError(f"轨A配额不符：{family} 应为 {lo}–{hi}，实际 {got}")
    if counts.get(FAMILY_MIX_PULL, 0) > 2:
        raise ValueError("轨A混合或拉动至多 1–2 道")
    long_text = slots[:5]
    light = {FAMILY_SHARE_ADD, FAMILY_GROWTH, FAMILY_BASE_SHARE, FAMILY_AVG_CMP}
    detail_judge = sum(1 for slot in long_text if slot.get("family") in {FAMILY_DETAIL, FAMILY_JUDGE})
    calc = sum(1 for slot in long_text if slot.get("family") in light)
    if detail_judge < 3 or calc < 2:
        raise ValueError("轨A至少1篇长文字：3 综合/细节 + 2 轻量计算（默认 M01）")
    if sum(1 for slot in slots[4::5] if slot.get("family") == FAMILY_JUDGE) < 4:
        raise ValueError("轨A每篇第5题须为综合正误")
    forms = [classify_judge_form(slot.get("judge_stem") or "") for slot in slots[4::5]]
    if len({form for form in forms if form}) < 2:
        raise ValueError("轨A四道综合正误须跨篇至少 2 种问法（属实 / 无法推出 / 能推出几个 / 能推出）")


def batch_source(track: str, targeted: bool, difficulty: str, compact_date: str,
                 slots: list[dict] | None = None) -> str:
    if track == TRACK_CLASSIC:
        topic = "专项" if targeted and slots else "计算技法"
        if targeted and slots:
            topic = str(slots[0].get("tag") or "专项").split("-", 1)[-1]
        return f"经典计算加练-资料分析-{topic}-{difficulty}-{compact_date}"
    topic = "粤考日练"
    if targeted and slots:
        topic = str(slots[0].get("tag") or "粤考日练").split("-", 1)[-1]
        return f"粤考日练-资料分析-{topic}-{difficulty}-{compact_date}"
    return f"粤考日练-资料分析-{difficulty}-{compact_date}"


def assert_source_label(track: str, source: str) -> None:
    text = str(source or "")
    if track == TRACK_CLASSIC:
        if "广东省考" in text or ("综合训练" in text and "经典计算加练" not in text):
            raise ValueError("轨B不得标成广东省考综合训练，应使用「经典计算加练-资料分析-…」")
        if not text.startswith("经典计算加练-"):
            raise ValueError("轨B source 必须以「经典计算加练-」开头")
        return
    if track == TRACK_GD:
        if "综合训练" in text:
            raise ValueError("轨A不要再写「综合训练」；默认日练用「粤考日练」")
        if not text.startswith("粤考日练-"):
            raise ValueError("轨A source 必须以「粤考日练-」开头")


def default_formats_label(track: str) -> str:
    return "粤考日练" if track == TRACK_GD else "经典计算加练"


def is_arithmetic_series(values: list[float], *, tol: float = 1e-6) -> bool:
    nums = [float(v) for v in values]
    if len(nums) < 3:
        return False
    first = [nums[i + 1] - nums[i] for i in range(len(nums) - 1)]
    if abs(first[0]) > 0 and all(abs(d - first[0]) <= tol for d in first):
        return True
    if len(nums) >= 4:
        second = [first[i + 1] - first[i] for i in range(len(first) - 1)]
        if abs(second[0]) > 0 and all(abs(d - second[0]) <= tol for d in second):
            return True
    return False


def figure_series_values(figure: dict) -> list[list[float]]:
    series = []
    for item in (figure or {}).get("series") or []:
        values = item.get("values") or []
        if values:
            try:
                series.append([float(v) for v in values])
            except (TypeError, ValueError):
                continue
    rows = (figure or {}).get("rows") or []
    if rows and all(isinstance(row, (list, tuple)) for row in rows):
        width = max((len(row) for row in rows), default=0)
        for col in range(1, width):
            nums = []
            for row in rows:
                if col >= len(row):
                    nums = []
                    break
                try:
                    nums.append(float(str(row[col]).replace(",", "").replace("%", "")))
                except (TypeError, ValueError):
                    nums = []
                    break
            if len(nums) >= 3:
                series.append(nums)
    return series


def material_realism_errors(material: dict, *, track: str = TRACK_GD, long_text: bool = False) -> list[str]:
    errors = []
    content = str((material or {}).get("content") or "")
    figure = (material or {}).get("figure") or {}
    for values in figure_series_values(figure):
        if is_arithmetic_series(values):
            errors.append("图/表序列一阶或二阶差分公差恒定（等差增量），须重生")
            break
    if _round_total_and_per_capita(content, figure):
        errors.append("禁止总计整万/整千且人均整十的凑数（如 10000 亿 / 400 万人 = 25 万）")
    if _too_round_base_period(content):
        errors.append("基期反推过于整齐（现期/(1+r) 恰为整百或整千），须打散数字")
    if track == TRACK_GD and long_text:
        if len(content) < 350:
            errors.append("轨A长文材须至少 350 字（仿粤考文字综合篇）")
        if not _has_decoy_numbers(content):
            errors.append("长文材须注入用不到的干扰指标或冗余句（至少 6 个独立统计数字）")
    return errors


def _round_total_and_per_capita(content: str, figure: dict) -> bool:
    blob = content + " " + json_safe(figure)
    totals = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:亿|万)", blob)]
    heads = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*万?\s*人", blob)]
    for total in totals:
        if total < 1000 or abs(total / 1000 - round(total / 1000)) > 1e-9:
            continue
        for head in heads:
            if head <= 0:
                continue
            per = total / head
            if abs(per - round(per)) < 1e-6 and round(per) % 5 == 0:
                return True
    return False


def _too_round_base_period(content: str) -> bool:
    pairs = re.findall(
        r"(\d+(?:\.\d+)?)\s*亿[^。\n]{0,16}同比(?:增长)?(\d+(?:\.\d+)?)%",
        content,
    )
    for raw_b, raw_r in pairs:
        try:
            current, rate = float(raw_b), float(raw_r) / 100
        except ValueError:
            continue
        if rate <= 0:
            continue
        base = current / (1 + rate)
        if abs(base - round(base)) < 1e-6 and round(base) % 100 == 0 and current >= 100:
            return True
    return False


def _has_decoy_numbers(content: str) -> bool:
    nums = [n for n in re.findall(r"\d+(?:\.\d+)?", content) if not re.fullmatch(r"(?:19|20)\d{2}", n)]
    return len(set(nums)) >= 6


def json_safe(value) -> str:
    if isinstance(value, dict):
        return " ".join(json_safe(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(json_safe(v) for v in value)
    return str(value or "")


def validate_difficulty_gradient(questions: list[dict], *, track: str) -> None:
    if track != TRACK_GD or len(questions) < 8:
        return
    scores = []
    for question in questions:
        try:
            scores.append(int(question.get("difficulty")))
        except (TypeError, ValueError):
            raise ValueError("轨A每题须有 1–5 的 difficulty，禁止缺省后全员 3")
    if len(set(scores)) < 3:
        raise ValueError("轨A禁止全员同一难度；须覆盖秒杀找数/一步/两步/综合等梯度")
    if scores and all(score == 3 for score in scores):
        raise ValueError("轨A禁止全员 difficulty=3")


def year_range_from_stem(stem: str) -> list[str]:
    years = _YEAR.findall(stem or "")
    if len(years) >= 2:
        start, end = int(years[0]), int(years[-1])
        if 1990 <= start <= end <= 2040 and end - start <= 12:
            return [str(year) for year in range(start, end + 1)]
    return years


def is_comparison_question(question: dict) -> bool:
    blob = f"{question.get('stem') or ''} {' '.join(question.get('tags') or [])} {question.get('brief') or ''}"
    family = str(question.get("family") or "")
    return bool(_CMP_HINT.search(blob)) or family == FAMILY_AVG_CMP and "比较" in blob


def explanation_missing_years(question: dict) -> list[str]:
    years = year_range_from_stem(str(question.get("stem") or ""))
    if len(years) < 3 or not is_comparison_question(question):
        return []
    text = str(question.get("explanation") or "")
    return [year for year in years if year not in text]


def validate_comparison_explanations(questions: list[dict]) -> None:
    for question in questions:
        missing = explanation_missing_years(question)
        if missing:
            raise ValueError(
                f"比较类解析必须枚举题干年份范围内全部点，缺少 {','.join(missing)}："
                f"{question.get('external_id')}"
            )


def infer_family_from_question(question: dict) -> str:
    if question.get("family"):
        return str(question["family"])
    stem = str(question.get("stem") or "")
    tag = " ".join(str(t) for t in (question.get("tags") or []))
    if re.search(r"说法(?:正确|有误|不正确)|可以判断属实|不能从|无法从|能够从|正确的有", stem):
        return FAMILY_JUDGE
    if re.search(r"未提及|不包括|不属于|分为几|主题是", stem):
        return FAMILY_DETAIL
    if "混合" in tag or "拉动" in tag or "贡献率" in tag:
        return FAMILY_MIX_PULL
    if "基期" in tag or "比重差" in tag:
        return FAMILY_BASE_SHARE
    if "平均" in tag or "比较" in tag:
        return FAMILY_AVG_CMP
    if "增长量" in tag or "增长率" in tag:
        return FAMILY_GROWTH
    if "比重" in tag or "加减" in stem or "多少亿元" in stem:
        return FAMILY_SHARE_ADD
    return ""


def validate_gd_question_mix(questions: list[dict]) -> None:
    if len(questions) != 20:
        return
    families = [infer_family_from_question(q) for q in questions]
    counts = Counter(families)
    detail = counts.get(FAMILY_DETAIL, 0)
    judge = counts.get(FAMILY_JUDGE, 0)
    mix = counts.get(FAMILY_MIX_PULL, 0)
    if detail < 3:
        raise ValueError(f"轨A须含细节定位/排除 3–4 道，当前 {detail}")
    if judge < 4:
        raise ValueError(f"轨A须含综合正误 4 道（每篇第5题），当前 {judge}")
    if mix > 2:
        raise ValueError(f"轨A混合或拉动至多 1–2 道，当前 {mix}")


def apply_slot_difficulty(question: dict, slot: dict, paper_tier: str = "mid") -> None:
    family = str(slot.get("family") or "")
    if family and family != "classic":
        question["difficulty"] = int(slot.get("difficulty_score") or difficulty_score(family, paper_tier))
        question["family"] = family
        return
    question["difficulty"] = {"easy": 2, "mid": 3, "hard": 4}[slot.get("difficulty") or paper_tier]


def skip_calculation(slot: dict) -> bool:
    return str(slot.get("family") or "") in {FAMILY_DETAIL, FAMILY_JUDGE}


def track_framework_rules(track: str) -> str:
    if track != TRACK_GD:
        return (
            "本批是「经典计算加练」：可覆盖现期/基期/增长量/增长率/比重/比重差/平均/比较/混合/拉动。"
            "不要写成广东省考综合训练。数字避免整万配整十人均，图序列禁止等差增量。"
        )
    return (
        "本批是「粤考日练」轨A，对照近年粤考卷面：文字细节定位/排除、轻量计算、每篇末题综合正误。"
        "禁止按教材 10 类×2 硬凑混合/拉动。默认 4 篇形态 text/table/chart/chart；"
        "M01 必须是长文字（350–700字），含 1–2 个本题用不到的干扰指标或冗余句。"
        "图序列禁止等差或等差增量；禁止总计整万+人均整十。"
        "难度按秒杀找数/一步/两步/四陈述综合拉开，禁止全员 difficulty=3。"
        "四篇 Q5 综合正误的题干已写在槽位 judge_stem：属实、不能推出、正确的有、能够推出，禁止四篇都写成「下列说法正确/有误的是」。"
    )


def track_material_rules(track: str, item: dict) -> str:
    extra = (
        "数字不要教材腔：避免 7800/5200/10000/400 这种整十整万；"
        "现期÷(1+r) 不要刚好等于 2000/1000/500；"
        "柱图/时间序列的一阶差分不得恒定，二阶差分也不得恒定（如增量 40、50、60、70）。"
    )
    if track == TRACK_GD and str(item.get("id") or "") == "M01":
        return extra + (
            "M01 写成统计公报式长文：先总述再「其中/分区域看」，3–5 段、350–700 字；"
            "至少注入两个本题不必用到的干扰指标（如同期另一行业、计划完成率、注里的口径说明）。"
        )
    if track == TRACK_GD:
        return extra + "正文保留足够冗余句和未入题指标，供细节排除命题。"
    return extra


def track_question_rules(track: str, slot: dict, index: int) -> str:
    family = str(slot.get("family") or "")
    if track == TRACK_GD and family == FAMILY_JUDGE:
        stem = str(slot.get("judge_stem") or "")
        form = str(slot.get("judge_form") or "")
        locked = (
            f"题干必须以「{stem}」开头，形式码={form}。"
            "不得改成「下列说法正确的是」「下列说法有误的是」或其他篇的问法。"
            if stem else
            "题干须使用槽位指定的综合判断句，不得四篇同一句。"
        )
        return (
            "本题必须是综合正误。" + locked +
            "四个选项各一句陈述，分别埋时间偷换、累计vs当年、未给出不能比、范围扩大中的至少两类。"
            "不要出混合增速或拉动专名题。计算清单可写正确项=1、错项=0。"
        )
    if family == FAMILY_DETAIL:
        return (
            "本题是细节定位或排除：主题/分为几类/未提及/不包括。错误项来自张冠李戴或材料未给出。"
            "不要编造需要两步公式的计算。计算清单可写正确项=1、错项=0。"
        )
    if family == FAMILY_AVG_CMP or "比较" in str(slot.get("brief") or ""):
        return "比较类解析必须列出题干年份范围内每一年的计算过程，禁止漏年。"
    if track == TRACK_GD and family == FAMILY_MIX_PULL:
        return "整套至多 1–2 道混合或拉动，本题若出则保持一道，解析保留干扰项对应的误用公式。"
    return "错误选项对应真实粗心路径：基期现期倒置、百分点混淆、取错行列。"


def render_option_figures(question: dict, image_dir: Path, renderer=None) -> bool:
    """挂点：仅当选项自带 figure 规格时渲染。不编造匹配题。"""
    rendered = False
    options = question.get("options") or []
    for option in options:
        figure = option.get("figure") if isinstance(option, dict) else None
        if not isinstance(figure, dict) or not figure.get("kind"):
            continue
        if renderer is None:
            continue
        name = f"{question.get('external_id', 'q')}-{option.get('key', 'X')}-{figure.get('kind')}.png"
        path = image_dir / name
        renderer(figure, path)
        option.setdefault("images", []).append(f"images/{path.name}")
        rendered = True
    return rendered

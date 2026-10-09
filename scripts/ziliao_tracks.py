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

ZILIAO_INFERENCE_RULES = """推断边界：范围扩大不自动等于错误。对人数、营收、产量等可加的非负量，
部分已超过某阈值，则包含该部分的整体也超过该阈值；整体未超过阈值，则部分也未超过。
须区分精确数值无法确定与上下界仍可推出，不能仅以“全部/规上/部分”字样否定选项。
把“超过/不足/至少/至多”保留为不等式，不能当成等式：“超过6.7万”没有7.6万的上界。
指标不同也不自动意味着无法比较：同口径下总产出=增加值+中间投入，中间投入非负，
已知增加值超过阈值时总产出也超过；不得把增加值较大的行业产出必较低误判成陷阱。
逐项尝试构造反例，检验是否存在第二个符合设问的选项；不同主体的增速和绝对量不能拼接反推。
价格口径：现价金额B与“不变价格/可比价格计算”的实际增速r不能直接用B/(1+r)反推现价基期，
也不能用B*r/(1+r)算现价增长量或据此算两期名义比重；缺价格指数时这些计算不成立。
仅比较同口径实际增速本身仍可行。不得在审核时忽略材料附注的价格口径。
平均数、增长率、比重不具有上述包含关系；利润等可能为负的量也不可直接套用。
“累计”本身不表示跨年；“2023年累计”通常就是2023年内累计。只有明确写出跨年起点，
如“自2020年启动以来至2023年底累计”，才能与2023年当年区分。口径歧义不得当作陷阱。
所有判定必须基于资料的具体数值和逻辑，不能凭“范围扩大/累计vs当年”模板猜命题意图。"""

ZILIAO_FIGURE_RULES = """渲染能力：bars只画同单位series.values柱形及其数值，只有一个纵轴；
不支持柱顶另标增速、折线、双轴或混合单位。若题目需要增长率，写在正文，明确为正文给出，
图标题仅描述实际柱形指标，禁止宣称图中有未编码的百分比或标注。本规则优先于框架中的图形建议。"""

GD_DESIGN_RULES = """粤考轨A命题与验收（难度偏易到中，宁要质不要量）：
每题按槽位kind考对应题型，不得换考法；同一篇五题求的未知量和公式互不相同。
细节槽只做直接定位或读数，实际难度1–2；不得设计人为口径陷阱，不得复读材料中的范围说明当正确项。
比较/平均题若需逐个求比值，题干明确限定最多4个候选主体；选项只有4个不等于题干已限定。
已知本期量A及本期增速r、求本期增长量时，须有误用A*r的干扰项；预测下一期增加量时A*r是正确算法。
两期比重差须有直接相减两增速a-b的干扰项（明确以百分点表述）；错误路径不能碰巧也等于正确答案。
每个干扰项都对应一条可复现的错误算法（如基期现期倒置、漏乘(1+r)、增速直接相加、取错年份或行列），
解析逐项写出“X项：错误算式=结果”；禁止用“计算失误”“估算误差”“粗心”等空话解释干扰项。
选项间距合理：数值选项两两相对差距至少3%，不得出现需精算才能区分的近选项（如15.3%与15.5%）。
正确值避免恰好整数百分比或整数倍；所有判断只依据材料数据，不依赖材料外常识或政策知识。
分子分母口径一致（同年份、同范围、同单位）；材料内部自洽，子项不超过母项，比重合计合理。
综合题四陈述以数据核算为主（估算比较、多步计算、真假混合），每句都要写出核算过程；
“百分点与百分比混淆”“累计当当年”“缺数据无法比较”这类文字陷阱每篇至多一句，全卷合计至多两句。
若有图表，本篇至少两个只在图表出现的数据进入题目计算，并在解析算式中写出；多年序列用于年均或增长量计算。
禁止规划尚未支持的chart_match或四幅选项图。"""

from ziliao_checklist import QUESTION_RULES
GD_DESIGN_RULES += "\n" + QUESTION_RULES

GD_PAPER_RULES = """轨A整套要求（targeted_drill为true时只按指定槽位）：
整套覆盖间隔增长率、年均增长、倍数、比重变化、平均数、基期量、增长量、增长率、比重、混合增长率、百分点与综合分析；
同一题型至多3题，细节查找/纯读数全卷至多2题；综合问法按槽位跨篇轮换，四道综合题的考查组合互不相同。
四篇主题互不相同，使用广东省及其地市真实地名，不用G省、S市、某省等占位。
每篇图表至少两个取数点仅在图表出现并进入计算。分项展示值之和与合计保留真实舍入差，不写四舍五入附注。"""

FAMILY_DETAIL = "detail"
FAMILY_JUDGE = "judge"
FAMILY_SHARE_ADD = "share_add"
FAMILY_GROWTH = "growth"
FAMILY_BASE_SHARE = "base_share"
FAMILY_AVG_CMP = "avg_cmp"
FAMILY_MIX_PULL = "mix_pull"

# 轨 A 20 题配额：family 是审核员可判别的大类，kind 是用户要求覆盖的具体题型。
GD_QUOTA = {
    FAMILY_DETAIL: (1, 2),
    FAMILY_JUDGE: (4, 4),
    FAMILY_SHARE_ADD: (2, 4),
    FAMILY_GROWTH: (4, 6),
    FAMILY_BASE_SHARE: (2, 3),
    FAMILY_AVG_CMP: (2, 3),
    FAMILY_MIX_PULL: (1, 2),
}

KIND_DETAIL = "detail_lookup"
KIND_BASE = "base_value"
KIND_DELTA = "growth_amount"
KIND_RATE = "growth_rate"
KIND_POINT = "percentage_point"
KIND_SHARE = "share"
KIND_SHARE_CHANGE = "share_change"
KIND_MULTIPLE = "multiple"
KIND_AVERAGE = "average"
KIND_ANNUAL = "annual_growth"
KIND_INTERVAL = "interval_growth"
KIND_MIX = "mixed_growth"
KIND_JUDGE = "judge"
KIND_LABELS = {
    KIND_DETAIL: "细节查找/读数", KIND_BASE: "基期量", KIND_DELTA: "增长量", KIND_RATE: "增长率",
    KIND_POINT: "百分点", KIND_SHARE: "比重", KIND_SHARE_CHANGE: "比重变化", KIND_MULTIPLE: "倍数",
    KIND_AVERAGE: "平均数/平均数增长", KIND_ANNUAL: "年均增长", KIND_INTERVAL: "间隔增长率",
    KIND_MIX: "混合增长率", KIND_JUDGE: "综合分析",
}
KIND_FAMILY = {
    KIND_DETAIL: FAMILY_DETAIL, KIND_BASE: FAMILY_BASE_SHARE, KIND_DELTA: FAMILY_GROWTH,
    KIND_RATE: FAMILY_GROWTH, KIND_POINT: FAMILY_GROWTH, KIND_SHARE: FAMILY_SHARE_ADD,
    KIND_SHARE_CHANGE: FAMILY_BASE_SHARE, KIND_MULTIPLE: FAMILY_SHARE_ADD, KIND_AVERAGE: FAMILY_AVG_CMP,
    KIND_ANNUAL: FAMILY_AVG_CMP, KIND_INTERVAL: FAMILY_GROWTH, KIND_MIX: FAMILY_MIX_PULL, KIND_JUDGE: FAMILY_JUDGE,
}
REQUIRED_KINDS = tuple(KIND_LABELS)
KIND_MAX = 3
DETAIL_MAX = 2

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


def _slot(family: str, tag: str, brief: str, paper_tier: str = "mid", kind: str | None = None) -> dict:
    slot = {
        "tag": tag,
        "count": 1,
        "family": family,
        "brief": brief,
        "difficulty": paper_tier,
        "difficulty_score": difficulty_score(family, paper_tier),
    }
    if kind:
        slot["kind"] = kind
        slot["kind_label"] = KIND_LABELS[kind]
    return slot


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


GD_JUDGE_MIXES = (
    "估算比较：四句中至少两句需估算比较大小或排序（如两项增长量、两个比重孰高），其余为直接计算；不考口径陷阱。",
    "多步计算：至少两句需两步及以上计算（如先反推基期再求比重、先求平均数再比较）；不能推出的那句须由计算得出，不能是“材料未提及”。",
    "正误混合：四句都依据图表与正文数据核算，正确的有2–3句，覆盖趋势判断、增长量或年均比较；不得用“缺数据无法比较”。",
    "估算+多步混合：四句分别涉及比重比较、增速比较、增长量估算、倍数或平均数；至多一句百分点与百分比辨析。",
)


def judge_slot_fields(material_index: int) -> dict:
    spec = GD_JUDGE_FORMS[material_index % len(GD_JUDGE_FORMS)]
    mix = GD_JUDGE_MIXES[material_index % len(GD_JUDGE_MIXES)]
    return {
        "judge_form": spec["form"],
        "judge_stem": spec["stem"],
        "judge_mix": mix,
        "brief": (
            f"综合分析。题干必须以「{spec['stem']}」开头（形式={spec['form']}）。"
            "禁止改成「下列说法正确的是」或「下列说法有误的是」。"
            f"本篇组合——{mix}每句解析写出核算算式；错误项必须确实不成立。"
        ),
    }


def gd_slots_20(paper_tier: str = "mid") -> list[dict]:
    """4×5 粤考槽位：覆盖12类计算/定位题型+4道综合，同类≤3、细节≤2；每篇Q5综合且问法与组合跨篇轮换。"""
    s = lambda family, tag, kind, brief: _slot(family, tag, brief, paper_tier, kind)
    slots = [
        # M01 长文字
        s(FAMILY_DETAIL, ZILIAO_QI, KIND_DETAIL, "文字定位：直接找出某个具体数值或分类归属，一步可得，不做计算，不设人为口径陷阱"),
        s(FAMILY_BASE_SHARE, ZILIAO_BASE, KIND_BASE, "基期量：由现期量和同比增速反推上年值；干扰项写出现期×(1-r)、现期×(1+r)等错误算式"),
        s(FAMILY_GROWTH, ZILIAO_DELTA, KIND_DELTA, "增长量：已知现期与增速求增长量A×r/(1+r)；干扰项含误用A×r"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_POINT, "百分点：两项增速或比率之差、或某增速比上年提高/回落多少个百分点；选项用“个百分点”，干扰项含相除得到的百分比"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
        # M02 表格
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, KIND_SHARE, "现期比重：表中某分项占合计比重；正确值不是整数百分比"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_RATE, "增长率：由表中两年数值计算同比增长率，或在至多4项中比较增长率"),
        s(FAMILY_AVG_CMP, ZILIAO_AVG, KIND_AVERAGE, "平均数或平均数增长率：如户均、人均、单位产出及其同比增速(a-b)/(1+b)"),
        s(FAMILY_SHARE_ADD, ZILIAO_QI, KIND_MULTIPLE, "倍数：现期倍数或基期倍数（A是B的多少倍），基期倍数须各自反推；正确值不是整数倍"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
        # M03 多年柱图
        s(FAMILY_AVG_CMP, ZILIAO_AVG, KIND_ANNUAL, "年均增长：用图中首末年份数据求年均增长量或年均增长率，年份差n须正确；题干含“年均”"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_INTERVAL, "间隔增长率：正文给某指标连续两年同比增速r1、r2，求现期比两年前增长百分之几R=r1+r2+r1×r2；解析写明“间隔增长率”，干扰项含r1+r2"),
        s(FAMILY_GROWTH, ZILIAO_DELTA, KIND_DELTA, "增长量：读图中相邻年份数值相减，或求增长量最多的年份（枚举范围内全部年份）"),
        s(FAMILY_BASE_SHARE, ZILIAO_SHARE_DIFF, KIND_SHARE_CHANGE, "比重变化：某部分占整体比重比上年上升/下降多少个百分点或判断升降，用a/b×(r1-r2)/(1+r1)；干扰项含直接相减两增速"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
        # M04 双系列柱图
        s(FAMILY_DETAIL, ZILIAO_QI, KIND_DETAIL, "读图定位：直接从图中读出某类别数值或排第一的类别，一步可得"),
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, KIND_SHARE, "比重：某城市或类别占合计比重，合计由正文给出或图中求和；正确值不是整数百分比"),
        s(FAMILY_MIX_PULL, ZILIAO_MIX, KIND_MIX, "混合增长率：两部分合计的增长率，介于两部分增速之间且偏向基数大的一方；干扰项含两增速简单平均"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_RATE, "增长率：由图中两年数值求某类别增长率，或在至多4个类别中比较增长率"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
    ]
    for material_index, slot_index in enumerate((4, 9, 14, 19)):
        slots[slot_index].update(judge_slot_fields(material_index))
    return slots


def validate_gd_kinds(slots: list[dict]) -> None:
    kinds = Counter(str(slot.get("kind") or "") for slot in slots)
    missing = [KIND_LABELS[k] for k in REQUIRED_KINDS if not kinds.get(k)]
    if missing:
        raise ValueError(f"轨A整套缺少题型：{'、'.join(missing)}")
    over = [f"{KIND_LABELS.get(k, k)}{n}题" for k, n in kinds.items() if k != KIND_JUDGE and n > KIND_MAX]
    if over:
        raise ValueError(f"轨A同一题型至多{KIND_MAX}题：{'、'.join(over)}")
    if kinds.get(KIND_DETAIL, 0) > DETAIL_MAX:
        raise ValueError(f"轨A细节查找/读数至多{DETAIL_MAX}题")
    if kinds.get(KIND_JUDGE, 0) != 4:
        raise ValueError("轨A须有4道综合分析")
    for slot in slots:
        if slot.get("kind") and KIND_FAMILY.get(slot["kind"]) != slot.get("family"):
            raise ValueError(f"槽位kind与family不一致：{slot.get('kind')}")


def gd_slots_5(paper_tier: str = "mid") -> list[dict]:
    s = lambda family, tag, kind, brief: _slot(family, tag, brief, paper_tier, kind)
    slots = [
        s(FAMILY_DETAIL, ZILIAO_QI, KIND_DETAIL, "文字或图表直接定位/读数"),
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, KIND_SHARE, "现期比重；正确值不是整数百分比"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_RATE, "增长率"),
        s(FAMILY_AVG_CMP, ZILIAO_AVG, KIND_AVERAGE, "平均数或平均数增长率"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
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
    validate_gd_kinds(slots)
    if len({slot.get("judge_mix") for slot in slots[4::5]}) < 4:
        raise ValueError("轨A四道综合分析须使用互不相同的考查组合")
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
        if (track == TRACK_GD and figure.get("kind") == "bars" and "元" in str(figure.get("unit") or "")
                and len(values) >= 4 and all(v > 0 and abs(v / 10 - round(v / 10)) < 1e-8 for v in values)):
            errors.append("金额柱图整列都是整十数，须保留自然数据精度，不要整列粗取整")
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
    if detail > DETAIL_MAX:
        raise ValueError(f"轨A细节查找/读数至多 {DETAIL_MAX} 道，当前 {detail}")
    if judge < 4:
        raise ValueError(f"轨A须含综合正误 4 道（每篇第5题），当前 {judge}")
    if mix > 2:
        raise ValueError(f"轨A混合或拉动至多 1–2 道，当前 {mix}")


def apply_slot_difficulty(question: dict, slot: dict, paper_tier: str = "mid") -> None:
    family = str(slot.get("family") or "")
    if family and family != "classic":
        question.setdefault("difficulty", int(slot.get("difficulty_score") or difficulty_score(family, paper_tier)))
        question["family"] = family
        return
    question.setdefault("difficulty", {"easy": 2, "mid": 3, "hard": 4}[slot.get("difficulty") or paper_tier])


def skip_calculation(slot: dict) -> bool:
    return str(slot.get("family") or "") in {FAMILY_DETAIL, FAMILY_JUDGE}


def track_framework_rules(track: str) -> str:
    if track != TRACK_GD:
        return (
            "本批是「经典计算加练」：可覆盖现期/基期/增长量/增长率/比重/比重差/平均/比较/混合/拉动。"
            "不要写成广东省考综合训练。数字避免整万配整十人均，图序列禁止等差增量。"
        )
    return (
        "本批是「粤考日练」轨A，对照近年粤考卷面：以计算题为主、少量直接定位、每篇末题综合分析，难度偏易到中。"
        "默认 4 篇形态 text/table/chart/chart；M01 为长文字（350–750字）。"
        "图序列禁止等差或等差增量；禁止总计整万+人均整十。"
        "难度按秒杀找数/一步/两步/四陈述综合拉开，禁止全员 difficulty=3。"
        "四篇 Q5 综合分析的题干已写在槽位 judge_stem：属实、不能推出、正确的有、能够推出，组合见 judge_mix，禁止四篇都写成「下列说法正确/有误的是」。"
        "各篇question_plan按五个槽位kind预留所需数据；有图表则至少两个只在图表出现的取数点进入计算。"
        "禁止九主体全表人均排序，禁止chart_match。主题按计划给定，四篇互不相同；地名用广东省及其地市真实名称。"
    )


def track_material_rules(track: str, item: dict) -> str:
    extra = (
        "数字不要教材腔：避免 7800/5200/10000/400 这种整十整万；"
        "现期÷(1+r) 不要刚好等于 2000/1000/500；"
        "柱图/时间序列的一阶差分不得恒定，二阶差分也不得恒定（如增量 40、50、60、70）。"
    )
    if track == TRACK_GD:
        extra += (
            "按同一底层数计算分项、总量及比率，再分别四舍五入；至少一组穷尽分项的展示值之和与合计存在真实舍入差，不要正好相等。"
            "容差随小数位和分项数量确定，不能统一放宽0.1–0.3。不要把现价口径或四舍五入分项差异写成附注。"
            "百分比避免整十整五扎堆，至少三分之二带一位小数；比值类结果不要恰好是整数百分比。"
            "时间序列也避免近似恒定差分及连续三年接近翻倍的模板，不给每年增长一个固定步长。"
            "图表金额按合适单位保留小数精度，避免整列粗取整；企业家数等离散计数仍用整数。"
            "材料内部自洽：子行业不超过母行业，地区之和不超过全省，比重合计不超过100%，同一数字前后一致；"
            "分子分母同年份同范围同单位。不依赖材料外常识。"
            "地名使用计划给定的广东省或地市真实名称，禁止G省、S市、某省、甲市等占位。"
            "禁止“本次统计范围严格限定为”“仅限于”这类人为设置的口径句和命题提示；按统计公报自然行文。"
            "图表保留至少两个不在正文复述、且会进入计算的取数点。"
        )
    if track == TRACK_GD and str(item.get("id") or "") == "M01":
        return extra + "M01 写成统计公报式长文：先总述再「其中/分领域看」，3–5 段、350–750 字，数据密度适中。"
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
        mix = str(slot.get("judge_mix") or "四句以数据核算为主，至多一句文字陷阱。")
        return (
            "本题必须是综合分析。" + locked + "考查组合：" + mix +
            "计数题把陈述放题干。每句解析写出取数与算式。计算清单可写正确项=1、错项=0。"
        )
    kind = str(slot.get("kind") or "")
    head = f"本题题型={slot.get('kind_label') or kind}，按此考法出题。" if kind else ""
    if family == FAMILY_DETAIL:
        return head + (
            "本题是直接定位或读数：找出具体数值、类别或排名第一项，一步可得。错误项来自相邻数据或张冠李戴。"
            "不得计算人均、增长量、比重，不设人为口径陷阱，也不得偷换成四陈述综合判断。计算清单可写正确项=1、错项=0。"
        )
    tail = "每个干扰项写出对应错误算式及结果；选项两两相对差距至少3%；正确值不是整数百分比或整数倍。"
    if family == FAMILY_AVG_CMP or "比较" in str(slot.get("brief") or ""):
        return head + "比较类解析必须覆盖题干完整范围；需逐项求比值时题干明确限定至多4个主体。" + tail
    if track == TRACK_GD and family == FAMILY_MIX_PULL:
        return head + "混合增长率按两部分基期量加权，解析保留干扰项对应的误用公式（如简单平均）。" + tail
    return head + "错误选项对应真实错误路径：基期现期倒置、漏乘(1+r)、增速直接相加减、取错年份或行列。" + tail


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

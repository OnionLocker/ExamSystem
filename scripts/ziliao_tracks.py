#!/usr/bin/env python3
"""资料分析双轨：粤考日练（轨 A）与经典计算加练（轨 B）。"""
from __future__ import annotations

import json
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
line只画同单位series.values折线及各点数值（1—3条），只有一个纵轴；pie只画一个series的各部分数值及占比。
不支持柱顶另标增速、柱线混合、双轴或混合单位。若题目需要增长率，写在正文，明确为正文给出，
图标题仅描述实际图形指标，禁止宣称图中有未编码的百分比或标注。本规则优先于框架中的图形建议。"""

GD_DESIGN_RULES = """粤考轨A命题与验收（难度偏易到中，宁要质不要量）：
每题按槽位kind考对应题型，不得换考法；同一篇五题求的未知量和公式互不相同。
细节槽只做直接定位或读数，实际难度1–2；不得设计人为口径陷阱，不得复读材料中的范围说明当正确项。
比较/平均题若需逐个求比值，题干明确限定最多4个候选主体；选项只有4个不等于题干已限定。
已知本期量A及本期增速r、求本期增长量时，须有误用A*r的干扰项；预测下一期增加量时A*r是正确算法。
数值型两期比重差须有直接相减两增速a-b的干扰项（明确以百分点表述）；定性升降判定题选项为主体名，不受此限；错误路径不能碰巧也等于正确答案。
每个干扰项都对应一条可复现的错误算法（如基期现期倒置、漏乘(1+r)、增速直接相加、取错年份或行列），
解析逐项写出“X项：错误算式=结果”；禁止用“计算失误”“估算误差”“粗心”等空话解释干扰项。
选项间距合理：数值选项两两相对差距至少3%，不得出现需精算才能区分的近选项（如15.3%与15.5%）。
正确值避免恰好整数百分比或整数倍；所有判断只依据材料数据，不依赖材料外常识或政策知识。
分子分母口径一致（同年份、同范围、同单位）；材料内部自洽，子项不超过母项，比重合计合理。
综合题四陈述以数据核算为主（估算比较、多步计算、真假混合），每句都要写出核算过程；
“百分点与百分比混淆”“累计当当年”“缺数据无法比较”这类文字陷阱每篇至多一句，全卷合计至多两句。
若有图表，本篇至少两个只在图表出现的数据进入题目计算，并在解析算式中写出；多年序列用于年均或增长量计算。
只有槽位kind=chart_match的题才能用选项图（options[].figure），其他题不得出选项图。"""

from ziliao_checklist import QUESTION_RULES
import model_router
GD_DESIGN_RULES += "\n" + QUESTION_RULES

GD_PAPER_RULES = """轨A整套要求（targeted_drill为true时只按指定槽位）：
每题按槽位kind与option_format出题，题型由系统按广东真题频率轮转分配，不得自行换题型或换选项格式；
同一题型至多3题，细节查找/读数/文字理解/读图排序全卷至多1题；综合问法按槽位跨篇轮换，四道综合题的考查组合互不相同。
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
    FAMILY_DETAIL: (0, 1),
    FAMILY_JUDGE: (4, 4),
    FAMILY_SHARE_ADD: (1, 5),
    FAMILY_GROWTH: (3, 8),
    FAMILY_BASE_SHARE: (0, 4),
    FAMILY_AVG_CMP: (2, 6),
    FAMILY_MIX_PULL: (0, 2),
    "chart_match": (0, 1),
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
KIND_AVG_DIFF = "average_diff"
KIND_COUNT = "count"
KIND_SORT = "sort"
KIND_PROJECTION = "projection"
KIND_DELTA_SHARE = "delta_share"
KIND_DIFF_GROWTH = "diff_growth"
KIND_CUMULATIVE = "cumulative"
KIND_TEXT_READING = "text_reading"
KIND_CHART_MATCH = "chart_match"
FAMILY_CHART = "chart_match"
KIND_LABELS = {
    KIND_DETAIL: "细节查找/读数", KIND_BASE: "基期量", KIND_DELTA: "增长量", KIND_RATE: "增长率",
    KIND_POINT: "百分点", KIND_SHARE: "比重", KIND_SHARE_CHANGE: "比重变化", KIND_MULTIPLE: "倍数",
    KIND_AVERAGE: "平均数/平均数增长", KIND_ANNUAL: "年均增长", KIND_INTERVAL: "间隔增长率",
    KIND_MIX: "混合增长率", KIND_JUDGE: "综合分析",
    KIND_AVG_DIFF: "平均数差值/比较", KIND_COUNT: "计数", KIND_SORT: "排序",
    KIND_PROJECTION: "假设推算", KIND_DELTA_SHARE: "增量占比/贡献率", KIND_DIFF_GROWTH: "差值增长率",
    KIND_CUMULATIVE: "累计与当期/月均", KIND_TEXT_READING: "文字理解", KIND_CHART_MATCH: "图表匹配",
}
KIND_FAMILY = {
    KIND_DETAIL: FAMILY_DETAIL, KIND_BASE: FAMILY_BASE_SHARE, KIND_DELTA: FAMILY_GROWTH,
    KIND_RATE: FAMILY_GROWTH, KIND_POINT: FAMILY_GROWTH, KIND_SHARE: FAMILY_SHARE_ADD,
    KIND_SHARE_CHANGE: FAMILY_BASE_SHARE, KIND_MULTIPLE: FAMILY_SHARE_ADD, KIND_AVERAGE: FAMILY_AVG_CMP,
    KIND_ANNUAL: FAMILY_AVG_CMP, KIND_INTERVAL: FAMILY_GROWTH, KIND_MIX: FAMILY_MIX_PULL, KIND_JUDGE: FAMILY_JUDGE,
    KIND_AVG_DIFF: FAMILY_AVG_CMP, KIND_COUNT: FAMILY_AVG_CMP, KIND_SORT: FAMILY_AVG_CMP,
    KIND_PROJECTION: FAMILY_GROWTH, KIND_DELTA_SHARE: FAMILY_MIX_PULL, KIND_DIFF_GROWTH: FAMILY_GROWTH,
    KIND_CUMULATIVE: FAMILY_GROWTH, KIND_TEXT_READING: FAMILY_DETAIL, KIND_CHART_MATCH: FAMILY_CHART,
}
LEGACY_KINDS = (KIND_DETAIL, KIND_BASE, KIND_DELTA, KIND_RATE, KIND_POINT, KIND_SHARE, KIND_SHARE_CHANGE,
                KIND_MULTIPLE, KIND_AVERAGE, KIND_ANNUAL, KIND_INTERVAL, KIND_MIX, KIND_JUDGE)
REQUIRED_KINDS = LEGACY_KINDS
KIND_MAX = 3
DETAIL_MAX = 1

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
    FAMILY_CHART: 3,
}

TIERS = ("easy", "mid", "hard")

# 档位只改变取数层数、步骤和选项间距，不改变题型配额与综合问法。
DIFFICULTY_GUIDE = {
    "easy": "易档：所需数据集中在一句或一行，一步计算；选项首位或量级即可区分（两两相对差约8%以上）；不跨段取数。",
    "mid": "中档：一到两步；可有一次跨句或表文结合取数；选项两两相对差≥3%，截位估算即可区分。",
    "hard": "难档：两到三步，如先由总量减已列分项、跨段或表文结合取数、先反推基期再计算；"
            "可有两个选项首位相同、需算到第二位，但相对差仍≥3%且答案唯一；不得靠口径陷阱制造难度。",
}
JUDGE_DIFFICULTY_GUIDE = {
    "easy": "易档综合：至少一句直接读数或一眼定性即可判断，其余为一步计算。",
    "mid": "中档综合：一句可直接读数或定性秒判，两句一步估算比较，一句两步计算。",
    "hard": "难档综合：四句都需计算，至少两句需两步以上（如先反推基期再比较比重）。",
}

# 干扰项优先取考生真实会犯的错；凭空公式由 ziliao_checklist.CONTRIVED 拦截。
TYPICAL_ERRORS = {
    KIND_BASE: "现期×(1−r)（近似公式误用）、现期×(1+r)（方向反）、直接取现期值、误用相邻主体或上年的增速",
    KIND_DELTA: "现期×r（漏除1+r）、取相邻主体或相邻年份数据、相邻年份相减取反",
    KIND_RATE: "（现期−基期）÷现期（分母用错）、取错年份或行列、增长量÷现期",
    KIND_POINT: "把百分点差写成“高X%”、取其中一项的上年增速或增速变动值、两增速相加",
    KIND_SHARE: "分母取上级总量或其他口径合计、分子取相邻主体、整体用上年（基期）数据",
    KIND_SHARE_CHANGE: "两增速直接相减当作百分点、升降方向判反、漏乘现期比重或漏除(1+部分增速)；定性题错项为比重实际下降（或上升）的主体",
    KIND_MULTIPLE: "分子分母颠倒、用现期倍数代替基期倍数、取错主体",
    KIND_AVERAGE: "分子分母颠倒、总量除以其他主体的数量；平均数增长率误用a−b或(a−b)/(1+a)",
    KIND_ANNUAL: "年份差n多算或少算一年、总增长率直接÷n、起点年取错",
    KIND_INTERVAL: "r1+r2漏加交叉项r1×r2、只用其中一年增速、取错年份的增速",
    KIND_MIX: "两增速简单平均、权重颠倒（用另一部分的量加权）、两增速相加",
    KIND_AVG_DIFF: "两期平均数直接用总量增速代替、分子分母颠倒、用现期总量除以基期数量、方向判反",
    KIND_PROJECTION: "把增量当增速逐年复利、年份少算或多算一年、用基期年起算",
    KIND_DELTA_SHARE: "用现期比重代替增量比重、分母用整体现期量、分子用部分现期量",
    KIND_DIFF_GROWTH: "直接用两项增速相减当差值增速、用现期差额除以现期差额、方向判反",
    KIND_CUMULATIVE: "把累计值当当月值、用累计增速当当月增速、月数少算一个月",
}

CLASSIC_TAGS = [
    ZILIAO_QI, ZILIAO_BASE, ZILIAO_DELTA, ZILIAO_RATE, ZILIAO_SHARE,
    ZILIAO_SHARE_DIFF, ZILIAO_AVG, ZILIAO_CMP, ZILIAO_MIX, ZILIAO_SPEC,
]

GD_FORMATS_4 = ["text", "table", "chart", "chart"]
CLASSIC_FORMATS_4 = ["chart", "table", "text", "chart"]

# 图表匹配：本轮只留挂点，不强制、不假实现选项图配额
CHART_MATCH_HOOK = {
    "implemented": True,
    "family": "chart_match",
    "reason": (
        "粤考常见「下列哪幅图反映……」：槽位 kind=chart_match 时，题目为 A–D 各给 options[].figure（饼图或折线），"
        "worker 用 render_option_figures() 程序出图并挂 options[].images；正确图按 calculation.target 复算，"
        "干扰图须凭形状可区分。整套按 CHART_MATCH_RATE 概率安排至多 1 道。"
    ),
}

_YEAR = re.compile(r"20\d{2}")
_CMP_HINT = re.compile(r"最快|最多|最少|最高|最低|超过|高于|低于|排序|同比增速最快")


def resolve_gemini_model() -> str:
    # 跟随模型路由；保留旧的按用途环境变量覆盖（显式设置时优先）
    return model_router.resolve_model("ziliao")


def has_gemini_credentials() -> bool:
    try:
        model_router.resolve_api_key()
        return True
    except RuntimeError:
        return False


def _slot(family: str, tag: str, brief: str, paper_tier: str = "mid", kind: str | None = None,
          quick: bool = False) -> dict:
    slot = {
        "tag": tag,
        "count": 1,
        "family": family,
        "brief": brief,
        "difficulty": paper_tier,
        "difficulty_score": difficulty_score(family, paper_tier, quick),
    }
    if kind:
        slot["kind"] = kind
        slot["kind_label"] = KIND_LABELS[kind]
    if quick:
        slot["quick"] = True
    return slot


def difficulty_score(family: str, paper_tier: str = "mid", quick: bool = False) -> int:
    base = 2 if quick else FAMILY_DIFFICULTY.get(family, 3)
    if paper_tier == "hard":
        return min(5, base + (0 if family == FAMILY_DETAIL or quick else 1))
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
    if "有误" in text or "不正确" in text or "错误的是" in text or "不准确" in text:
        return "有误"
    if "正确的是" in text or "准确的是" in text:
        return "正确"
    return ""


# 综合分析四句的考查组合：前 4 种为原有组合，其余按粤考/国考真题综合题选项归纳。
# 每套抽 4 种互不相同的组合，按 weight × 近 3 套降权 × 学员表现系数抽取。
GD_JUDGE_MIXES = (
    {"id": "estimate-compare", "weight": 4,
     "text": "估算比较：四句中至少两句需估算比较大小或排序（如两项增长量、两个比重孰高），其余为直接计算；不考口径陷阱。"},
    {"id": "multi-step", "weight": 4,
     "text": "多步计算：至少两句需两步及以上计算（如先反推基期再求比重、先求平均数再比较）；不能推出的那句须由计算得出，不能是“材料未提及”。"},
    {"id": "truth-mix", "weight": 3,
     "text": "正误混合：四句都依据图表与正文数据核算，正确的有2–3句，覆盖趋势判断、增长量或年均比较；不得用“缺数据无法比较”。"},
    {"id": "estimate-multi-mix", "weight": 3,
     "text": "估算+多步混合：四句分别涉及比重比较、增速比较、增长量估算、倍数或平均数；至多一句百分点与百分比辨析。"},
    {"id": "implicit-total", "weight": 3,
     "text": "隐含量反推：至少两句需由比重、人均或增速反推材料未直接给出的总量或人数（如由人均与总额推人口），再与阈值比较。"},
    {"id": "universal-trend", "weight": 3,
     "text": "全称与趋势核查：至少两句含“均/逐年/始终/无论……都/变化趋势一致”，须逐项逐年核查，错误句恰有一个反例。"},
    {"id": "hypothesis", "weight": 2,
     "text": "假设推算：一句以“如果/若……保持不变（或各期相等），则……”给出假设再判断，假设须能由材料数据完整推算；其余三句常规核算。"},
    {"id": "text-data-mix", "weight": 2,
     "text": "文字数据混合：一句依据正文文字表述（举措、排名、特点）判断，错误须与原文有明确出入；其余三句为数据核算。"},
    {"id": "cumulative-annual", "weight": 2,
     "text": "累计与年均：四句中至少两句涉及多年累计值、年均增量或年均增速、首次超过某值的年份，年份差须写对。"},
    {"id": "bound-inference", "weight": 2,
     "text": "边界推断：一句用“可能/不可能/至少/至多”表述，需用不等式判断上下界是否成立；其余三句常规核算。"},
    {"id": "contribution", "weight": 2,
     "text": "贡献与拉动：一句判断整体增长主要由哪部分贡献或某部分拉动多少个百分点，其余三句涉及比重、增速或平均数。"},
)
JUDGE_MIX_TEXT = {mix["id"]: mix["text"] for mix in GD_JUDGE_MIXES}
_JUDGE_MIX_BY_TEXT = {mix["text"]: mix["id"] for mix in GD_JUDGE_MIXES}


def judge_mix_id(slot: dict) -> str | None:
    """旧批次只存了组合原文，按原文反查 id。"""
    return slot.get("judge_mix_id") or _JUDGE_MIX_BY_TEXT.get(str(slot.get("judge_mix") or ""))


def judge_slot_fields(material_index: int) -> dict:
    spec = GD_JUDGE_FORMS[material_index % len(GD_JUDGE_FORMS)]
    mix = GD_JUDGE_MIXES[material_index % len(GD_JUDGE_MIXES)]["text"]
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
    """4×5 粤考槽位：覆盖12类计算/定位题型+4道综合，同类≤3、细节≤1；每篇Q5综合且问法与组合跨篇轮换。
    M02-Q3 固定平均数增长率，M04-Q4 为两期比重升降定性秒判。"""
    s = lambda family, tag, kind, brief, quick=False: _slot(family, tag, brief, paper_tier, kind, quick)
    slots = [
        # M01 长文字
        s(FAMILY_DETAIL, ZILIAO_QI, KIND_DETAIL, "文字定位：直接找出某个具体数值或分类归属，一步可得，不做计算，不设人为口径陷阱"),
        s(FAMILY_BASE_SHARE, ZILIAO_BASE, KIND_BASE, "基期量：由现期量和同比增速反推上年值；干扰项写出现期×(1-r)、现期×(1+r)等错误算式"),
        s(FAMILY_GROWTH, ZILIAO_DELTA, KIND_DELTA, "增长量：已知现期与增速求增长量A×r/(1+r)；干扰项含误用A×r"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_POINT, "百分点：两项增速或比率之差、或某增速比上年提高/回落多少个百分点；选项用“个百分点”。干扰项不得等于两增速的相对比值（如7.4%/5.0%-1=48%或1.48倍），否则按相对比较也成立；混淆单位的干扰项写成“高X%”且X等于百分点差"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
        # M02 表格
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, KIND_SHARE, "现期比重：表中某分项占合计比重；正确值不是整数百分比"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_RATE, "增长率：由表中两年数值计算同比增长率，或在至多4项中比较增长率"),
        s(FAMILY_AVG_CMP, ZILIAO_AVG, KIND_AVERAGE, "平均数增长率：表中某分项的户均、人均或单位产出比上年增长百分之几，用(a-b)/(1+b)，a为总量增速、b为数量增速；题干含“平均”“户均”“人均”等；干扰项含a-b直接相减、(a-b)/(1+a)"),
        s(FAMILY_SHARE_ADD, ZILIAO_QI, KIND_MULTIPLE, "倍数：现期倍数或基期倍数（A是B的多少倍），基期倍数须各自反推；正确值不是整数倍"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
        # M03 多年柱图
        s(FAMILY_AVG_CMP, ZILIAO_AVG, KIND_ANNUAL, "年均增长：用图中首末年份数据求年均增长量或年均增长率，年份差n须正确；题干含“年均”"),
        s(FAMILY_GROWTH, ZILIAO_RATE, KIND_INTERVAL, "间隔增长率：正文给某指标连续两年同比增速r1、r2，求现期比两年前增长百分之几R=r1+r2+r1×r2；解析写明“间隔增长率”，干扰项含r1+r2"),
        s(FAMILY_GROWTH, ZILIAO_DELTA, KIND_DELTA, "增长量：读图中相邻年份数值相减，或求增长量最多的年份（枚举范围内全部年份）"),
        s(FAMILY_BASE_SHARE, ZILIAO_SHARE_DIFF, KIND_SHARE_CHANGE, "比重变化：某部分占整体比重比上年上升/下降多少个百分点或判断升降，用a/b×(r1-r2)/(1+r1)；干扰项含直接相减两增速"),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
        # M04 双系列柱图
        s(FAMILY_AVG_CMP, ZILIAO_AVG, KIND_AVERAGE, "平均数：用图中某类别数值与正文给出的对应数量求平均数（如每个机构、每名人员对应量），或比较两类别平均数；不出读图排序题，正确值不是整数"),
        s(FAMILY_SHARE_ADD, ZILIAO_SHARE, KIND_SHARE, "比重：某城市或类别占合计比重，合计由正文给出或图中求和；正确值不是整数百分比"),
        s(FAMILY_MIX_PULL, ZILIAO_MIX, KIND_MIX, "混合增长率：两部分合计的增长率，介于两部分增速之间且偏向基数大的一方；干扰项含两增速简单平均"),
        s(FAMILY_BASE_SHARE, ZILIAO_SHARE_DIFF, KIND_SHARE_CHANGE,
          "两期比重升降定性判定：题干如“下列类别中，占合计比重比上年上升的是”，四个选项为图中类别名；"
          "只需比较各类别增速与合计增速的大小，不必算出比重；恰有一个类别比重上升（或下降）。"
          "解析逐项写“X项：部分增速−合计增速=a%−b%=…个百分点”并判方向；计算清单correct=1，正确项1、错项0",
          quick=True),
        s(FAMILY_JUDGE, ZILIAO_CMP, KIND_JUDGE, ""),
    ]
    for material_index, slot_index in enumerate((4, 9, 14, 19)):
        slots[slot_index].update(judge_slot_fields(material_index))
    return slots


# ---------------------------------------------------------------------------
# 题型池轮转：每套按广东真题频率加权抽题型，最近几套用过的降权；材料形态也轮换。
# weight 取自 2020–2026 广东省考资料分析逐题统计（综合分析单列，每篇末题固定）。

MATERIAL_TYPES = {
    "text": {"format": "text", "figure_kind": "none", "figure_shape": None, "weight": 0,
             "plan": "长文字统计公报式材料（3–5段，350–750字）：给出总量与多个分项的现期值和同比增速，"
                     "部分主体只给增速或只给绝对量，至少一个分项需由总量减其他分项得到；可含一段政策举措或原因表述。"},
    "table": {"format": "table", "figure_kind": "table", "figure_shape": None, "weight": 3,
              "plan": "表格至少6行×4列：各分项现期值、上年值或同比增速，以及第二指标（如企业数、人数、面积）及其上年值或增速；"
                      "含合计行，分项展示值之和与合计保留真实舍入差。"},
    "monthly": {"format": "table", "figure_kind": "table", "figure_shape": "monthly", "weight": 1.5,
                "plan": "月度或季度表格：首列为月份或“1—N月”累计期（至少6行），列出当月值、累计值或累计同比增速；"
                        "正文另给全年总量或上年同期数据，供累计反推当月、月均、季度汇总与同比判断。"},
    "years": {"format": "chart", "figure_kind": "bars", "figure_shape": "years", "weight": 2.5,
              "plan": "柱图为连续5–6年同一指标的时间序列（categories为年份），供年均增长、增长量、增速趋势；"
                      "正文另给某细分指标连续两年同比增速，以及该细分指标与总量的现期值和增速。"},
    "two_series": {"format": "chart", "figure_kind": "bars", "figure_shape": "two_series", "weight": 2,
                   "plan": "柱图为4–8个广东地市或类别的两年数值（两个同单位series），各类别增速与合计增速有高有低；"
                           "正文另给部分类别的对应数量（如机构数、人数、企业数），以及两部分各自的现期值和增速。"},
    "pie": {"format": "chart", "figure_kind": "pie", "figure_shape": "pie", "weight": 1.5,
            "plan": "饼图为某总量的3–6个组成部分（categories为部分名称，series只有一个、values为各部分绝对量），图中显示各部分数值与占比；"
                    "正文给总量及各部分或总量的同比增速等相关指标，供比重、比重变化、基期、增长量计算。"},
    "line": {"format": "chart", "figure_kind": "line", "figure_shape": "years", "weight": 1.5,
             "plan": "折线图为连续5–8期（年份）同一指标的数值序列（1–2条同单位折线），各点标注数值；"
                     "正文另给相关总量或增速，供增长量、增长率、年均与走势判断。"},
}
TABLE_TYPES = ("table", "monthly")
CHART_TYPES = ("years", "two_series", "pie", "line")
CHART_MATCH_PIE_TYPES = ("pie", "table", "two_series", "text")
CHART_MATCH_TREND_TYPES = ("years", "line", "monthly")

OPTION_FORMAT_WEIGHTS = {"exact": 0.55, "interval": 0.25, "direction": 0.2}

KIND_SPECS = {
    KIND_SHARE: {"weight": 10, "types": ("text", "table", "two_series", "pie", "monthly"), "formats": ("exact", "interval"),
                 "brief": "比重：某部分占整体的比重（现期比重、多部分合计占比或隔级比重）；正确值不是整数百分比",
                 "need": "部分与整体的同口径现期值"},
    KIND_SHARE_CHANGE: {"weight": 5, "types": ("text", "table", "two_series", "pie"), "formats": ("exact", "direction"),
                        "brief": "两期比重：某部分占整体的比重比上年上升/下降多少个百分点，用a/b×(r1-r2)/(1+r1)；干扰项含直接相减两增速",
                        "need": "部分与整体的现期值及各自同比增速"},
    KIND_AVERAGE: {"weight": 6, "types": ("table", "two_series", "text", "monthly", "pie"), "formats": ("exact", "interval"),
                   "brief": "平均数或平均数增长率：人均、户均、每个X对应量，或平均数比上年增长百分之几（(a-b)/(1+b)）；正确值不是整数",
                   "need": "总量与对应数量（人数、企业数等）及其增速"},
    KIND_AVG_DIFF: {"weight": 3, "types": ("table", "two_series", "text"), "formats": ("exact", "direction"),
                    "brief": "平均数差值或比较：平均每X比上年（或比另一主体）多/少多少，先分别求两个平均数再作差；不能用总量增速代替",
                    "need": "两期（或两主体）的总量与数量"},
    KIND_ANNUAL: {"weight": 4, "types": ("years", "line", "table"), "formats": ("exact", "interval"),
                  "brief": "年均增长：用首末年份数据求年均增长量或年均增长率，年份差n须正确；题干含“年均”",
                  "need": "连续多年同一指标的数值"},
    KIND_RATE: {"weight": 6, "types": ("text", "table", "years", "two_series", "monthly", "line"), "formats": ("exact", "interval"),
                "brief": "增长率：由两期数值求同比增长率，或在至多4项中比较增长率",
                "need": "同一指标两期数值，或增量与基期"},
    KIND_DELTA: {"weight": 4, "types": ("text", "table", "years", "two_series", "line", "monthly", "pie"),
                 "formats": ("exact", "interval", "direction"),
                 "brief": "增长量：已知现期与增速求增长量A×r/(1+r)（干扰项含误用A×r），或由两期数值相减、求增长量最多的年份",
                 "need": "现期值与同比增速，或两期数值"},
    KIND_BASE: {"weight": 2, "types": ("text", "table", "pie", "monthly"), "formats": ("exact", "interval"),
                "brief": "基期量：由现期量和同比增速反推上年值；干扰项含现期×(1-r)、现期×(1+r)",
                "need": "现期值与同比增速"},
    KIND_MULTIPLE: {"weight": 3, "types": ("text", "table", "years", "two_series", "pie"), "formats": ("exact", "interval"),
                    "brief": "倍数或比例：A是B的多少倍（现期或基期倍数，基期倍数须各自反推），或两量之比最接近哪个比例；正确值不是整数倍",
                    "need": "两个可比主体的数值（基期倍数还需各自增速）"},
    KIND_POINT: {"weight": 2, "types": ("text", "table"), "formats": ("exact", "direction"),
                 "brief": "百分点：两项增速或比率之差、或某增速比上年提高/回落多少个百分点；选项用“个百分点”",
                 "need": "两项增速或比率，或同一增速的两期值"},
    KIND_INTERVAL: {"weight": 1, "types": ("text", "years", "line"), "formats": ("exact",),
                    "brief": "间隔增长率：某指标连续两年同比增速r1、r2，求比两年前增长百分之几R=r1+r2+r1×r2；解析写明“间隔增长率”",
                    "need": "某指标连续两年同比增速"},
    KIND_MIX: {"weight": 0.8, "types": ("text", "two_series", "pie", "table"), "formats": ("exact", "interval"),
               "brief": "混合增长率：两部分合计的增长率，介于两部分增速之间且偏向基期量大的一方；干扰项含两增速简单平均",
               "need": "两部分各自现期值和增速"},
    KIND_COUNT: {"weight": 3, "types": ("table", "years", "two_series", "monthly", "line"), "formats": ("exact",),
                 "brief": "计数：在材料所列主体或年份中，满足某条件（如增速超过X%、比重超过X%、同比增长、高于平均水平）的有几个；选项为个数",
                 "need": "至少5个可逐一判断的主体或时期"},
    KIND_SORT: {"weight": 3, "types": ("table", "two_series", "text", "monthly"), "formats": ("exact",),
                "brief": "排序：把3—4个主体按增速、增长量、平均数或比重从高到低排列；四个选项为四种不同排列",
                "need": "3—4个主体的两期数值，或现期值与增速"},
    KIND_PROJECTION: {"weight": 1.5, "types": ("years", "line", "text", "monthly"), "formats": ("exact", "interval"),
                      "brief": "假设推算：如保持某年增量（或增速）不变，哪一年首次超过X；或若后续月份保持前几月平均水平，全年将比上年增长多少",
                      "need": "连续多期数值及可延续的增量或增速"},
    KIND_DELTA_SHARE: {"weight": 1.2, "types": ("text", "table", "two_series"), "formats": ("exact", "interval"),
                       "brief": "增量占比/贡献率：部分增量占整体增量的比重（增长贡献率），或部分拉动整体增长多少个百分点",
                       "need": "部分与整体的现期值及增速（或两期值）"},
    KIND_DIFF_GROWTH: {"weight": 1.2, "types": ("text", "table"), "formats": ("exact", "direction", "interval"),
                       "brief": "差值的增长率：顺差、收支盈余、净增额等差值指标比上年增长百分之几；先分别求两期差值再求增速",
                       "need": "构成差值的两个指标（如出口与进口）的两期值，或现期值与增速"},
    KIND_CUMULATIVE: {"weight": 1.5, "types": ("monthly",), "formats": ("exact", "interval"),
                      "brief": "累计与当期：由1—N月累计与1—(N−1)月累计求当月（季）值或其增速，或求月均、日均；月数须正确",
                      "need": "1—N月累计与前期累计，或累计值与月数"},
    KIND_DETAIL: {"weight": 1.2, "types": ("text", "table", "years", "two_series"), "formats": ("exact",),
                  "brief": "直接定位或读数：找出具体数值、类别或排名第一项，一步可得，不做计算",
                  "need": ""},
    KIND_TEXT_READING: {"weight": 1.5, "types": ("text",), "formats": ("exact",),
                        "brief": "文字理解：依据材料文字判断“资料未提及的是”“原因不包括”“主题是”或某说法是否符合原文，不做计算；错误项与原文有明确出入",
                        "need": "成段的政策举措、原因或主题表述（不只是数字）"},
}

KIND_TAGS = {
    KIND_SHARE: ZILIAO_SHARE, KIND_SHARE_CHANGE: ZILIAO_SHARE_DIFF, KIND_AVERAGE: ZILIAO_AVG,
    KIND_AVG_DIFF: ZILIAO_AVG, KIND_ANNUAL: ZILIAO_AVG, KIND_RATE: ZILIAO_RATE, KIND_POINT: ZILIAO_RATE,
    KIND_INTERVAL: ZILIAO_RATE, KIND_DIFF_GROWTH: ZILIAO_RATE, KIND_DELTA: ZILIAO_DELTA,
    KIND_PROJECTION: ZILIAO_DELTA, KIND_BASE: ZILIAO_BASE, KIND_CUMULATIVE: ZILIAO_BASE,
    KIND_MULTIPLE: ZILIAO_QI, KIND_DETAIL: ZILIAO_QI, KIND_TEXT_READING: ZILIAO_QI, KIND_MIX: ZILIAO_MIX,
    KIND_DELTA_SHARE: ZILIAO_SPEC, KIND_COUNT: ZILIAO_CMP, KIND_SORT: ZILIAO_CMP,
}

GD_JUDGE_FORM_POOL = GD_JUDGE_FORMS + (
    {"form": "有误", "stem": "根据资料，下列说法有误的是"},
    {"form": "有误", "stem": "根据资料，以下说法不正确的是"},
    {"form": "有误", "stem": "根据资料，下列说法不准确的是"},
    {"form": "有误", "stem": "根据资料，下列说法最不准确的是"},
    {"form": "正确", "stem": "根据资料，以下说法正确的是"},
    {"form": "正确", "stem": "根据资料，下列说法最准确的是"},
    {"form": "正确", "stem": "根据资料，以下判断正确的是"},
)

CORE_GROUPS = (
    ("比重类", {KIND_SHARE, KIND_SHARE_CHANGE, KIND_DELTA_SHARE}, 2),
    ("平均类", {KIND_AVERAGE, KIND_AVG_DIFF, KIND_ANNUAL}, 2),
    ("增长类", {KIND_RATE, KIND_DELTA, KIND_BASE, KIND_POINT, KIND_INTERVAL, KIND_DIFF_GROWTH,
              KIND_PROJECTION, KIND_CUMULATIVE}, 4),
)
NON_EXACT_MIN = 2
CHART_MATCH_RATE = 0.75


def chart_match_brief(material_type: str) -> tuple[str, str]:
    if material_type in CHART_MATCH_TREND_TYPES:
        return ZILIAO_RATE, ("图表匹配：题干问“下列选项中最能准确反映……连续4—5期同比增速（或同比增量）变化趋势的是”，"
                             "四个选项各为一幅折线图（figure.kind=line，categories为期次，values为该指标各期数值），图中不标数值；"
                             "正确图与材料算出的序列一致，三个干扰图各对应一种真实错误（如把增量当增速、用现期值代替增速、相邻期顺序颠倒），"
                             "且仅凭各点升降走势或高低次序即可与正确图区分")
    return ZILIAO_SHARE, ("图表匹配：题干问“下列饼图中最能准确反映……各组成部分占比关系的是”，并写明各部分名称；"
                          "四个选项各为一幅饼图（figure.kind=pie，categories为3—5个部分名称，values为各部分占比或数值），图中不标数值；"
                          "正确图与材料算出的占比一致，三个干扰图各对应一种真实错误（如用上年数据、两个部分对调、遗漏“其他”项），"
                          "且仅凭各块相对大小即可与正确图区分（至少一块占比相差5个百分点以上或大小次序不同）")


def _recency_factor(kind: str, recent: list) -> float:
    factor = 1.0
    for kinds, penalty in zip(recent or [], (0.4, 0.65, 0.85)):
        if kind in kinds:
            factor *= penalty
    return factor


def _weighted_pick(rng, items: list, weights: list):
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    point = rng.random() * total
    for item, weight in zip(items, weights):
        point -= weight
        if point <= 0:
            return item
    return items[-1]


def pick_material_types(rng, recent_types: list | None = None) -> list[str]:
    recent_types = recent_types or []
    for _ in range(200):
        chosen = ["text"]
        pool = [t for t in MATERIAL_TYPES if t != "text"]
        while len(chosen) < 4:
            options = [t for t in pool if t not in chosen]
            weights = [MATERIAL_TYPES[t]["weight"] * _recency_factor(t, recent_types) for t in options]
            chosen.append(_weighted_pick(rng, options, weights))
        if any(t in TABLE_TYPES for t in chosen) and any(t in CHART_TYPES for t in chosen):
            rest = chosen[1:]
            tables = [t for t in rest if t in TABLE_TYPES]
            charts = [t for t in rest if t in CHART_TYPES]
            rng.shuffle(charts)
            return ["text", *tables, *charts]
    return ["text", "table", "years", "two_series"]


def kind_cap(kind: str) -> int:
    weight = KIND_SPECS.get(kind, {}).get("weight", 0)
    return 1 if weight < 2 else 2 if weight < 5 else KIND_MAX


def _option_format(rng, kind: str) -> str:
    formats = KIND_SPECS.get(kind, {}).get("formats") or ("exact",)
    return _weighted_pick(rng, list(formats), [OPTION_FORMAT_WEIGHTS[f] for f in formats])


def _core_ok(kinds: list[str]) -> bool:
    counts = Counter(kinds)
    return all(sum(counts[k] for k in group) >= need for _, group, need in CORE_GROUPS)


def rotating_slot(kind: str, material_type: str, paper_tier: str, option_format: str, rng) -> dict:
    if kind == KIND_CHART_MATCH:
        tag, brief = chart_match_brief(material_type)
        slot = _slot(FAMILY_CHART, tag, brief, paper_tier, kind)
        slot["chart_variant"] = "trend" if material_type in CHART_MATCH_TREND_TYPES else "pie"
    else:
        spec = KIND_SPECS[kind]
        quick = kind == KIND_SHARE_CHANGE and material_type in ("two_series", "table") and rng.random() < 0.4
        brief = spec["brief"]
        if quick:
            brief = ("两期比重升降定性判定：题干如“下列类别中，占合计比重比上年上升的是”，四个选项为类别名；"
                     "只需比较各类别增速与合计增速，恰有一个类别比重上升（或下降）；计算清单correct=1、正确项1、错项0")
        slot = _slot(KIND_FAMILY[kind], KIND_TAGS[kind], brief, paper_tier, kind, quick)
        if quick:
            option_format = "exact"
    slot["option_format"] = option_format
    slot["material_type"] = material_type
    slot["rotation"] = True
    return slot


def pick_judge_mixes(rng, recent_mixes: list | None = None, mix_boost: dict | None = None, count: int = 4) -> list[dict]:
    """不放回抽 count 种综合分析考查组合：weight × 近 3 套降权 × 学员表现系数。"""
    mix_boost = mix_boost or {}
    pool, chosen = list(GD_JUDGE_MIXES), []
    while len(chosen) < count and pool:
        weights = [m["weight"] * _recency_factor(m["id"], recent_mixes or []) * mix_boost.get(m["id"], 1.0) for m in pool]
        mix = _weighted_pick(rng, pool, weights)
        chosen.append(mix)
        pool.remove(mix)
    return chosen


def gd_rotating_paper(paper_tier: str = "mid", rng=None, recent_kinds: list | None = None,
                      recent_types: list | None = None, kind_boost: dict | None = None,
                      recent_mixes: list | None = None, mix_boost: dict | None = None) -> tuple[list[str], list[dict]]:
    """返回（四篇材料形态，20 个槽位）。题型与综合分析组合按真题权重×近期降权×学员表现系数抽取，满足核心覆盖与配额。"""
    import random
    rng = rng or random.Random()
    recent_kinds = recent_kinds or []
    kind_boost = kind_boost or {}
    for _ in range(500):
        types = pick_material_types(rng, recent_types)
        want_chart = rng.random() < CHART_MATCH_RATE
        chart_host = None
        if want_chart:
            hosts = [i for i, t in enumerate(types) if i > 0 and (t in CHART_MATCH_PIE_TYPES or t in CHART_MATCH_TREND_TYPES)]
            chart_host = rng.choice(hosts) if hosts else None
        counts, picked, detail_used, mix_used = Counter(), [], False, 0
        for index, material_type in enumerate(types):
            chosen = [KIND_CHART_MATCH] if index == chart_host else []
            while len(chosen) < 4:
                pool = []
                for kind, spec in KIND_SPECS.items():
                    if material_type not in spec["types"] or kind in chosen or counts[kind] >= kind_cap(kind):
                        continue
                    if KIND_FAMILY[kind] == FAMILY_DETAIL and (detail_used or any(KIND_FAMILY[c] == FAMILY_DETAIL for c in chosen)):
                        continue
                    if KIND_FAMILY[kind] == FAMILY_MIX_PULL and mix_used >= 1:
                        continue
                    pool.append(kind)
                if not pool:
                    break
                kind = _weighted_pick(rng, pool, [KIND_SPECS[k]["weight"] * _recency_factor(k, recent_kinds)
                                                  * kind_boost.get(k, 1.0) for k in pool])
                chosen.append(kind)
                counts[kind] += 1
                detail_used = detail_used or KIND_FAMILY[kind] == FAMILY_DETAIL
                mix_used += KIND_FAMILY[kind] == FAMILY_MIX_PULL
            if len(chosen) < 4:
                break
            rank = lambda k: (0 if KIND_FAMILY[k] == FAMILY_DETAIL else 2 if k == KIND_CHART_MATCH else 1,
                              FAMILY_DIFFICULTY.get(KIND_FAMILY[k], 3))
            picked.append((material_type, sorted(chosen, key=rank)))
        if len(picked) != 4:
            continue
        kinds = [k for _, ks in picked for k in ks]
        if not _core_ok(kinds):
            continue
        slots = []
        for material_type, ks in picked:
            for kind in ks:
                slots.append(rotating_slot(kind, material_type, paper_tier, _option_format(rng, kind), rng))
            slots.append(_slot(FAMILY_JUDGE, ZILIAO_CMP, "", paper_tier, KIND_JUDGE))
        non_exact = [s for s in slots if s.get("option_format") not in (None, "exact")]
        if len(non_exact) < NON_EXACT_MIN:
            candidates = [s for s in slots if s.get("kind") in KIND_SPECS and not s.get("quick")
                          and len(KIND_SPECS[s["kind"]]["formats"]) > 1 and s.get("option_format") == "exact"]
            rng.shuffle(candidates)
            for slot in candidates[:NON_EXACT_MIN - len(non_exact)]:
                slot["option_format"] = next(f for f in KIND_SPECS[slot["kind"]]["formats"] if f != "exact")
        forms = rng.sample(list(GD_JUDGE_FORM_POOL), len(GD_JUDGE_FORM_POOL))
        unique_forms, seen = [], set()
        for spec in forms:
            if spec["form"] not in seen:
                unique_forms.append(spec)
                seen.add(spec["form"])
        mixes = pick_judge_mixes(rng, recent_mixes, mix_boost)
        for material_index in range(4):
            spec, mix_spec = unique_forms[material_index], mixes[material_index]
            mix = mix_spec["text"]
            slots[material_index * 5 + 4].update({
                "judge_form": spec["form"], "judge_stem": spec["stem"], "judge_mix": mix,
                "judge_mix_id": mix_spec["id"],
                "brief": (f"综合分析。题干必须以「{spec['stem']}」开头（形式={spec['form']}）。"
                          "禁止改成其他问法。" f"本篇组合——{mix}每句解析写出核算算式；错误项必须确实不成立。"),
            })
        try:
            validate_gd_quota(slots, count=20)
        except ValueError:
            continue
        return types, slots
    raise RuntimeError("题型轮转无法在约束内组卷")


def slot_label(slot: dict) -> str:
    label = str(slot.get("kind_label") or slot.get("kind") or "")
    return f"{label}（{slot['kaofa_variant_name']}）" if slot.get("kaofa_variant_name") else label


def material_question_plan(material_type: str, slots: list[dict]) -> str:
    needs = []
    for index, slot in enumerate(slots, 1):
        kind = slot.get("kind")
        if kind == KIND_CHART_MATCH:
            need = ("可算出各组成部分占比的总量与分项" if slot.get("chart_variant") == "pie"
                    else "连续5期以上可求同比增速或增量的数值")
        else:
            need = slot.get("kaofa_need") or KIND_SPECS.get(kind, {}).get("need") or ""
        if need:
            needs.append(f"Q{index}{slot_label(slot)}需{need}")
    return (MATERIAL_TYPES[material_type]["plan"]
            + "五题题型依次为：" + "、".join(slot_label(s) for s in slots) + "。"
            + ("各题所需数据：" + "；".join(needs) + "。" if needs else ""))


_DIFFICULTY_KEY = re.compile(r"M0([1-4])(?:-Q([1-5]))?")


def parse_difficulty_blueprint(raw) -> tuple[str | None, dict[str, dict]]:
    """Hermes 蓝图：{"difficulty":"mid","slots":{"M02":"easy","M03-Q4":{"difficulty":"hard","note":"..."}}}。
    只允许调整难度与命题倾向说明；题型、配额、综合问法不开放。"""
    if raw in (None, ""):
        return None, {}
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        data = json.loads(Path(text[1:]).read_text() if text.startswith("@") else text)
    if not isinstance(data, dict) or set(data) - {"difficulty", "slots"}:
        raise ValueError("资料整套蓝图只接受 difficulty 与 slots 两个字段")
    tier = data.get("difficulty")
    if tier is not None and tier not in TIERS:
        raise ValueError(f"整卷 difficulty 须为 {'/'.join(TIERS)}")
    overrides = {}
    for key, value in (data.get("slots") or {}).items():
        if not _DIFFICULTY_KEY.fullmatch(str(key)):
            raise ValueError(f"蓝图槽位键须为 M01–M04 或 M01-Q1–M04-Q5：{key}")
        spec = {"difficulty": value} if isinstance(value, str) else value
        if not isinstance(spec, dict) or set(spec) - {"difficulty", "note"} or spec.get("difficulty") not in TIERS:
            raise ValueError(f"{key} 须写 easy/mid/hard，或 {{\"difficulty\":...,\"note\":...}}")
        note = spec.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 120):
            raise ValueError(f"{key} 的 note 须为 120 字以内的文字")
        overrides[str(key)] = spec
    return tier, overrides


def apply_difficulty_overrides(slots: list[dict], overrides: dict[str, dict]) -> list[dict]:
    """先按篇再按题覆盖档位，并同步 difficulty_score。"""
    result = [dict(slot) for slot in slots]
    ordered = sorted(overrides.items(), key=lambda kv: "-Q" in kv[0])
    for key, spec in ordered:
        matched = _DIFFICULTY_KEY.fullmatch(key)
        material, question = int(matched[1]) - 1, matched[2]
        positions = [material * 5 + int(question) - 1] if question else range(material * 5, material * 5 + 5)
        for position in positions:
            if position >= len(result):
                raise ValueError(f"蓝图槽位 {key} 超出本套题量")
            slot = result[position]
            tier = spec["difficulty"]
            slot["difficulty"] = tier
            slot["difficulty_score"] = difficulty_score(str(slot.get("family") or ""), tier, bool(slot.get("quick")))
            if spec.get("note"):
                slot["difficulty_note"] = spec["note"]
    return result


def validate_gd_kinds(slots: list[dict]) -> None:
    kinds = Counter(str(slot.get("kind") or "") for slot in slots)
    unknown = [k for k in kinds if k and k not in KIND_LABELS]
    if unknown:
        raise ValueError(f"轨A出现未定义题型：{'、'.join(unknown)}")
    for name, group, need in CORE_GROUPS:
        if sum(kinds.get(k, 0) for k in group) < need:
            raise ValueError(f"轨A整套{name}题型至少{need}题")
    over = [f"{KIND_LABELS.get(k, k)}{n}题" for k, n in kinds.items() if k != KIND_JUDGE and n > KIND_MAX]
    if over:
        raise ValueError(f"轨A同一题型至多{KIND_MAX}题：{'、'.join(over)}")
    if sum(n for k, n in kinds.items() if KIND_FAMILY.get(k) == FAMILY_DETAIL) > DETAIL_MAX:
        raise ValueError(f"轨A细节查找/读数/文字理解至多{DETAIL_MAX}题")
    if kinds.get(KIND_CHART_MATCH, 0) > 1:
        raise ValueError("轨A图表匹配至多1题")
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
    return (str(slot.get("family") or "") in {FAMILY_DETAIL, FAMILY_JUDGE, FAMILY_CHART}
            or str(slot.get("kind") or "") == KIND_SORT)


def uses_ranges(slot: dict) -> bool:
    return str(slot.get("option_format") or "exact") in {"interval", "direction"}


OPTION_FORMAT_RULES = {
    "interval": ("选项采用区间式：四个区间互不重叠、首尾相接（如“不到5%”“在5%到10%之间”“在10%到15%之间”“超过15%”），"
                 "正确值落在且仅落在一个区间内，与最近区间端点的相对距离≥3%。calculation写correct（算式）和ranges，"
                 "如{\"A\":[null,5],\"B\":[5,10],\"C\":[10,15],\"D\":[15,null]}（左闭右开，null表示无界，单位与选项一致，百分数写百分数值），不写options。"
                 "解析写出算得的数值并说明落在哪个区间。"),
    "direction": ("选项采用“升降+程度”式：四个选项为“上升（增加/高）了不到X”“上升了X以上”“下降（减少/低）了不到X”“下降了X以上”，"
                  "X为同一阈值，正确值与X的相对差≥5%。calculation写correct（下降为负数）和ranges，"
                  "如{\"A\":[0,X],\"B\":[X,null],\"C\":[-X,0],\"D\":[null,-X]}，不写options。解析写出算得的数值和方向。"),
}

KIND_QUESTION_RULES = {
    KIND_COUNT: ("计数题：选项为个数（如1、2、3、4），解析逐一列出每个主体或时期的判断算式和结论，再汇总个数；"
                 "calculation.correct直接写正确个数，options写各选项个数。"),
    KIND_SORT: ("排序题：选项为四种不同排列（用主体名或①②③④），解析逐项算出排序依据的数值；"
                "calculation写correct=1、options正确项1错项0。"),
    KIND_AVG_DIFF: "平均数差值题：先分别求两期（或两主体）平均数再作差或比较，解析写出两个平均数的算式。",
    KIND_PROJECTION: "假设推算题：题干写明假设条件（如“如保持2024年同比增量不变”），解析逐年（或逐月）推算到结论；年份类答案calculation.correct写年份。",
    KIND_DELTA_SHARE: "增量占比题：分子为部分增量、分母为整体增量（贡献率），或拉动增长=部分增量/整体基期；解析分别写出增量算式。",
    KIND_DIFF_GROWTH: "差值增长率题：先分别求现期与基期的差值（如顺差=出口−进口），再求差值的增长率；解析写出两期差值。",
    KIND_CUMULATIVE: "累计与当期题：当月值=1—N月累计−1—(N−1)月累计，月均=累计÷月数；解析写明月数。",
    KIND_CHART_MATCH: ("图表匹配题：四个选项都是图，options[i].text写空字符串，options[i].figure写该图数据"
                       "（饼图{\"kind\":\"pie\",\"categories\":[...],\"values\":[...]}，折线{\"kind\":\"line\",\"categories\":[...],\"values\":[...]}），"
                       "四幅图categories相同、数据互不相同。calculation写correct=1、options正确项1错项0，并加target数组："
                       "按categories顺序给出正确图每个点的算式（饼图写各部分数值或占比算式，折线写各期增速或增量算式）。"
                       "解析先写出各点算式，再逐项说明A—D图与正确值哪里不符。"),
}


def option_format_rules(slot: dict) -> str:
    return OPTION_FORMAT_RULES.get(str(slot.get("option_format") or "exact"), "")


def _bound(value):
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "null", "none"}):
        return None
    return float(value)


def range_matches(target: float, ranges: dict) -> list[str]:
    hits = []
    for key, bounds in (ranges or {}).items():
        lo, hi = (_bound(bounds[0]), _bound(bounds[1])) if isinstance(bounds, (list, tuple)) and len(bounds) == 2 else (None, None)
        if lo is None and hi is None:
            continue
        if (lo is None or target >= lo) and (hi is None or target < hi):
            hits.append(str(key))
    return hits


def range_calculation_issues(target: float, ranges: dict, answer: str, keys: set[str]) -> list[str]:
    issues = []
    if not isinstance(ranges, dict) or set(map(str, ranges)) != keys:
        return ["区间/升降选项须在calculation.ranges里给出A—D四个区间"]
    hits = range_matches(target, ranges)
    if hits != [answer]:
        issues.append(f"算得{target:.6g}落在区间{hits}，但答案是{answer}")
    edges = [b for bounds in ranges.values() for b in map(_bound, bounds) if b not in (None, 0)]
    near = [e for e in edges if abs(target - e) / abs(e) < 0.02]
    if near:
        issues.append(f"正确值{target:.6g}距区间端点{near[0]:g}过近（相对差<2%），需精算才能判断；调整阈值或数据")
    return issues


def _shape_signature(kind: str, values: list[float]) -> tuple:
    if kind == "pie":
        total = sum(values) or 1
        shares = [v / total * 100 for v in values]
        return ("pie", tuple(sorted(range(len(shares)), key=lambda i: -shares[i])), tuple(shares))
    steps = tuple((b > a) - (b < a) for a, b in zip(values, values[1:]))
    return ("trend", steps, tuple(sorted(range(len(values)), key=lambda i: -values[i])))


def chart_match_issues(question: dict, calculation: dict) -> list[str]:
    """图表匹配：正确图须与 target 算式一致，干扰图须仅凭形状可区分。"""
    from quality_orchestrator import safe_eval
    options = question.get("options") or []
    figures = {str(o.get("key")): o.get("figure") for o in options}
    if len(figures) != 4 or not all(isinstance(f, dict) and f.get("kind") in {"pie", "line", "bars"} for f in figures.values()):
        return ["图表匹配题四个选项都须带figure（kind为pie/line/bars）"]
    kinds = {f["kind"] for f in figures.values()}
    cats = {tuple(map(str, f.get("categories") or [])) for f in figures.values()}
    if len(kinds) != 1 or len(cats) != 1 or not next(iter(cats)):
        return ["四幅选项图须同一图形种类、相同categories"]
    kind, categories = kinds.pop(), list(cats.pop())
    try:
        series = {k: [float(v) for v in f.get("values") or []] for k, f in figures.items()}
        target = [float(safe_eval(e)) for e in calculation.get("target") or []]
    except Exception as exc:
        return [f"图表匹配数据或target不可复算：{exc}"]
    if len(target) != len(categories) or any(len(v) != len(categories) for v in series.values()):
        return ["target与各选项图values须与categories等长"]
    issues = []
    answer = str(question.get("answer") or "")
    if kind == "pie" and len(categories) < 3:
        issues.append("饼图至少3个部分")
    if kind != "pie" and len(categories) < 4:
        issues.append("走势图至少4个期次")
    correct = series.get(answer) or []
    if kind == "pie":
        total_c, total_t = sum(correct) or 1, sum(target) or 1
        off = max(abs(c / total_c - t / total_t) * 100 for c, t in zip(correct, target))
        if off > 1.5:
            issues.append(f"正确选项饼图占比与target相差{off:.1f}个百分点")
    else:
        scale = max(abs(t) for t in target) or 1
        off = max(abs(c - t) for c, t in zip(correct, target)) / scale
        if off > 0.03:
            issues.append(f"正确选项走势图数值与target相差{off:.0%}")
    sig = _shape_signature(kind, correct)
    for key, values in series.items():
        if key == answer:
            continue
        other = _shape_signature(kind, values)
        if kind == "pie":
            diff = max(abs(a - b) for a, b in zip(sig[2], other[2]))
            if sig[1] == other[1] and diff < 5:
                issues.append(f"{key}项饼图与正确图各块大小次序相同且最大差<5个百分点，凭图形无法区分")
        elif sig[1] == other[1] and sig[2] == other[2]:
            issues.append(f"{key}项走势图与正确图升降走势和高低次序都相同，凭图形无法区分")
    return issues


def track_framework_rules(track: str) -> str:
    if track != TRACK_GD:
        return (
            "本批是「经典计算加练」：可覆盖现期/基期/增长量/增长率/比重/比重差/平均/比较/混合/拉动。"
            "不要写成广东省考综合训练。数字避免整万配整十人均，图序列禁止等差增量。"
        )
    return (
        "本批是「粤考日练」轨A，对照近年粤考卷面：以计算题为主、少量直接定位、每篇末题综合分析，难度偏易到中。"
        "4 篇形态按计划（M01 为长文字350–750字，其余为表格、月度表、柱图、饼图或折线图）。"
        "图序列禁止等差或等差增量；禁止总计整万+人均整十。"
        "难度按秒杀找数/一步/两步/四陈述综合拉开，禁止全员 difficulty=3。"
        "四篇 Q5 综合分析的题干已写在槽位 judge_stem（四篇问法互不相同），四句考查组合见 judge_mix，禁止四篇都写成「下列说法正确/有误的是」。"
        "各篇question_plan按五个槽位kind预留所需数据；有图表则至少两个只在图表出现的取数点进入计算。"
        "禁止九主体全表人均排序；图表匹配只在槽位kind=chart_match时出。主题按计划给定，四篇互不相同；地名用广东省及其地市真实名称。"
    )


GD_DISCLOSURE_RULES = (
    "信息披露按真实统计公报习惯，不做逐项齐全的报表：不必每个主体都同时给现期值和增速，"
    "至少一个主体只给现期值或只给增速；至少一处题目所需的数要由总量减去已列分项、或由两句数据合成才能得到，"
    "给考生留出定位和筛选成本；可穿插一到两句同领域但本篇题目用不到的指标（如投资额、项目数）。"
    "上述取舍不得让任何槽位缺数据，题目所需的每个数仍须能由材料唯一确定。"
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
            + GD_DISCLOSURE_RULES
        )
    if track == TRACK_GD and str(item.get("id") or "") == "M01":
        return extra + ("M01 写成统计公报式长文：先总述再「其中/分领域看」，3–5 段、350–750 字，数据密度适中；"
                        "段内可混写两三类指标，不写成一段一个维度的报表式排布。")
    return extra


def slot_difficulty_rules(track: str, slot: dict) -> str:
    if track != TRACK_GD:
        return ""
    tier = str(slot.get("difficulty") or "mid")
    if tier not in TIERS:
        return ""
    family = str(slot.get("family") or "")
    if family == FAMILY_DETAIL:
        text = "本题为直接定位，档位只影响定位距离（难档可跨段），不增加计算。"
    elif slot.get("quick"):
        text = ("本题为定性/估算秒判题，15–40秒可完成，不需精确计算。"
                + ("难档：候选主体增速与合计增速差距可小到1个百分点以内，需细看。" if tier == "hard" else ""))
    elif family == FAMILY_JUDGE:
        text = JUDGE_DIFFICULTY_GUIDE[tier]
    else:
        text = DIFFICULTY_GUIDE[tier]
    note = str(slot.get("difficulty_note") or "")
    return text + (f"命题倾向（不得因此改变题型）：{note}" if note else "")


def typical_error_rules(slot: dict) -> str:
    errors = TYPICAL_ERRORS.get(str(slot.get("kind") or ""))
    if not errors:
        return ""
    return (f"干扰项优先取本题型考生常见错法（至少两项来自此列）：{errors}；其余可用看错主体、年份或单位。"
            "禁止为凑选项构造考生不会犯的公式，如除以(1+2r)、(r1+r2)×(1+r2)、把无关数翻倍或乘无关系数。")


def track_question_rules(track: str, slot: dict, index: int) -> str:
    rules = _track_question_rules(track, slot, index)
    extra = slot_difficulty_rules(track, slot) + (typical_error_rules(slot) if track == TRACK_GD else "")
    return rules + KIND_QUESTION_RULES.get(str(slot.get("kind") or ""), "") + option_format_rules(slot) + extra


def _track_question_rules(track: str, slot: dict, index: int) -> str:
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
    if slot.get("kaofa_variant_name"):
        head += f"细分考法={slot['kaofa_variant_name']}，按槽位brief中的考法变式命题。"
    if kind == KIND_TEXT_READING:
        return head + (
            "本题是文字理解：依据材料原文判断“资料未提及”“原因不包括”“主题是”或说法是否符合原文，不做计算。"
            "三个错误项各与原文有明确出入（偷换主体、无中生有、因果倒置），解析逐项引用原文。计算清单可写正确项=1、错项=0。"
        )
    if family == FAMILY_DETAIL:
        return head + (
            "本题是直接定位或读数：找出具体数值、类别或排名第一项，一步可得。错误项来自相邻数据或张冠李戴。"
            "不得计算人均、增长量、比重，不设人为口径陷阱，也不得偷换成四陈述综合判断。计算清单可写正确项=1、错项=0。"
        )
    if family == FAMILY_CHART or kind in (KIND_COUNT, KIND_SORT):
        return head + "解析逐项写出判断依据的算式；比较类覆盖题干完整范围。"
    if uses_ranges(slot):
        return head + "错误区间应对应考生常见错算落入的区间；正确值不是整数百分比或整数倍。"
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

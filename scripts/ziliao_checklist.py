"""Auditable arithmetic and style checks for the scoped Gemini workers."""
import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP

VERSION = "gd-agent-v2"
GD_PLACES = ("广东", "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆", "江门", "茂名", "惠州",
             "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮", "珠三角", "粤东",
             "粤西", "粤北", "大湾区", "横琴", "前海", "南沙")
PLACEHOLDER = re.compile(r"(?<![A-Za-z])[A-Z]\s*[省市县区]|某(?:省|市|县|区|地区)|[甲乙丙丁][省市县]")
ARTIFICIAL = re.compile(r"严格限定|统计范围(?:仅|只)?(?:限定|限于)|本次统计范围|仅限于本|用于(?:命题|干扰|凑)|作为干扰")
VAGUE = re.compile(r"计算失误|计算错误|估算误差|估算偏差|计算偏差|粗心|口算失误|误差所致")
ARITH = re.compile(r"\d(?:\.\d+)?\s*[%％]?\s*\)?\s*[×÷*/+＋\-−－]\s*\(?\s*\d")
MATERIAL_RULES = """材料验收清单：
先生成多一至两位小数的原创底层金额，按同一底数推导总计，再把各数分别四舍五入到公报显示精度。
不要求每组都有缺口，但本篇至少保留一组有真实舍入缺口的穷尽分项，不能直接给合计加0.1造假。
地名用广东省及其地市真实名称；禁止G省、S市、某省等占位，禁止“本次统计范围严格限定为”等人造口径句。
不穷尽的部分列举不得当作舍入缺口。面向考生的材料不要写现价口径或四舍五入分项差异的附注。
material额外携带rounding_checks数组（仅供验收，不给考生看），每组格式：
{"label":"2024年某指标合计","unit":"亿元","places":1,
 "parts":[{"label":"甲","raw":"114.36","shown":"114.4"},{"label":"乙","raw":"86.16","shown":"86.2"}],
 "total":{"label":"合计","raw":"200.52","shown":"200.5"}}
示例数字不得照抄；raw总计必须精确等于raw分项和，每个shown必须等于自身raw四舍五入结果。
所有shown及其指标须出现在正文或结构化图表；年份、地区、单位、范围须一致。不得为凑台账新添无关组。
正文与图表内的全部总分关系都要核对，台账不能代替统计口径审查。
审查增长率反推时也须尊重显示精度，不能通过更改答案或放宽容差掩盖不自洽。"""

QUESTION_RULES = """新增轨A质量清单：
问比重、占比、利润率等比率的两期变化，使用“上升/下降多少个百分点”，不问这些比率本身相对增长百分之几。
growth槽可问营业收入/利润额等绝对指标的同比增长率，不可为了百分点问法偷换槽位/主标签。
混合槽如问两部分的倍数关系，正确结果不得精确或按选项精度近似落成整数倍（例如5.0倍）；
不能微调标答，须依据合理底层数据更换取数对象或重设材料。优先自然混合加权增速，避免反推整数配比。
四个选项的错误路径须可实际复现；禁止审核用“计算失误/取数错误”等泛话替缺乏依据的干扰项辩护。
计算题解析须逐个写“X项：错误算式=结果”，程序会检查每个错误选项字母后紧跟算式；解析出现“计算失误/估算误差/粗心”即退回。
数值选项两两相对差距须≥3%；比重、增长率、平均数类正确值不得是整数百分比，倍数类正确值不得是整数倍。
图表篇至少两个只在图表出现的数据须写进本篇解析算式；年均增长题须用图中至少两个年份数据。
综合分析每题解析至少两处写出算式；百分点/累计/缺数据三类文字陷阱每篇至多一句、全卷至多两篇使用。
解析中明确列出的纯数字算式须与写出的结果在展示精度内一致。按舍入后的增速反推基期，
结果可能与图表直接给的上年数略有不同；不得把图表旧数伪写成反推算式的计算结果。
本轮未实现四图选一：禁止chart_match及A—D选项图，不能把普通读图宣称为图表匹配已解决。"""


def rounding_issues(material):
    errors, gaps = [], []
    groups = material.get("rounding_checks")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 12:
        return ["缺少1—12组可复算rounding_checks；至少一组须有真实舍入缺口"]
    visible = str(material.get("content") or "") + json.dumps(material.get("figure") or {}, ensure_ascii=False)
    numbers = {Decimal(s) for s in re.findall(r"-?\d+(?:\.\d+)?", visible)}
    for group in groups:
        try:
            places = group["places"]
            if type(places) is not int or not 0 <= places <= 3:
                raise ValueError("places须为0—3")
            if not group.get("label") or not group.get("unit"):
                raise ValueError("须标明具体指标/年份和单位")
            parts, total = group["parts"], group["total"]
            if not isinstance(parts, list) or not 2 <= len(parts) <= 24:
                raise ValueError("穷尽分项须为2—24项")
            quantum = Decimal(1).scaleb(-places)
            for item in [*parts, total]:
                raw, shown = Decimal(str(item["raw"])), Decimal(str(item["shown"]))
                if not item.get("label") or not raw.is_finite() or not shown.is_finite():
                    raise ValueError("分项标签/有限数值缺失")
                if raw.quantize(quantum, rounding=ROUND_HALF_UP) != shown:
                    raise ValueError(f"{item['label']}显示值不等于底数按精度舍入")
                if shown not in numbers:
                    raise ValueError(f"{item['label']}显示值不在正文或图表中")
            if sum(Decimal(str(p["raw"])) for p in parts) != Decimal(str(total["raw"])):
                raise ValueError("底层分项之和不等于底层总计，禁止人为改合计")
            gaps.append(sum(Decimal(str(p["shown"])) for p in parts) - Decimal(str(total["shown"])))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            errors.append(f"舍入台账无效：{exc}")
    if not any(gaps):
        errors.append("全部展示分项恰好等于合计；本篇须从高精度底数独立舍入保留一组真实缺口")
    if re.search(r"按现价|现价名义|现价计算|现行价格|四舍五入|分项之和与总计略有差异", str(material.get("content") or "")):
        errors.append("不要在材料中写现价口径或四舍五入分项差异的附注")
    return errors


def explanation_math_issues(text):
    """Check explicit literal arithmetic only; symbolic/estimate reasoning stays with reviewers."""
    from quality_orchestrator import safe_eval
    text = text.replace("\\n", "\n")
    pattern = r"(?:≈|=|＝)\s*(-?\d+(?:\.\d+)?)(%|％|个百分点)?"
    issues = []
    for match in re.finditer(pattern, text):
        # The RHS must be a complete number, not the start of another expression in a chain.
        if re.match(r"\s*[+＋*/×÷−－-]", text[match.end():]):
            continue
        left = re.search(r"[\d.\s()＋+*/×÷−－%％-]+$", text[:match.start()])
        if not left:
            continue
        expression = left[0].strip()
        shown, unit = match.groups()
        if not re.search(r"[+＋*/×÷]|(?<=\d)\s*[-−－]", expression):
            continue
        expression = expression.translate(str.maketrans("×÷−－＋", "*/--+"))
        expression = re.sub(r"(\d+(?:\.\d+)?)\s*[%％]", r"(\1/100)", expression)
        try:
            value = float(safe_eval(expression)) * (100 if unit else 1)
            digits = len(shown.split(".")[1]) if "." in shown else 0
            tolerance = 0.5 * 10 ** -digits + 1e-8
            if math.isfinite(value) and abs(value - float(shown)) > tolerance:
                issues.append(f"解析算式不符展示精度：{left[0].strip()}{match[0]}；复算为{value:.8g}，须修正结果或明确改写估算过程")
        except (ValueError, SyntaxError, TypeError, ArithmeticError):
            continue  # Incomplete or symbolic fragments are not a mechanical proof.
    return issues


def material_text_issues(material):
    content = str(material.get("content") or "")
    visible = content + json.dumps(material.get("figure") or {}, ensure_ascii=False)
    errors = []
    if PLACEHOLDER.search(visible):
        errors.append(f"材料使用占位地名「{PLACEHOLDER.search(visible)[0]}」；改用广东省或地市真实名称")
    if not any(place in visible for place in GD_PLACES):
        errors.append("材料须使用广东省或其地市真实地名（如广东省、深圳、广州、佛山、东莞）")
    if ARTIFICIAL.search(content):
        errors.append(f"材料含人造口径句或命题提示「{ARTIFICIAL.search(content)[0]}」；按统计公报自然行文")
    percents = re.findall(r"(\d+(?:\.\d+)?)\s*[%％]", visible)
    integers = [p for p in percents if "." not in p]
    if len(percents) >= 4 and len(integers) * 3 > len(percents):
        errors.append(f"材料百分比过整：{len(integers)}/{len(percents)}个为整数百分比，至少三分之二应带小数")
    return errors


def _option_values(question):
    values = {}
    for option in question.get("options") or []:
        text = re.sub(r"(?:19|20)\d{2}\s*年", "", str(option.get("text") or ""))
        numbers = re.findall(r"\d+(?:\.\d+)?", text)
        if len(numbers) != 1:
            return {}
        value = float(numbers[0])
        values[str(option.get("key"))] = -value if re.search(r"下降|降低|减少|回落|负", text) else value
    return values


def _decimals(text):
    found = set()
    for token in re.findall(r"\d+(?:\.\d+)?", str(text)):
        try:
            found.add(Decimal(token).normalize())
        except ArithmeticError:
            continue
    return found


def _figure_values(figure):
    figure = figure or {}
    values = [v for series in figure.get("series") or [] for v in series.get("values") or []]
    values += [cell for row in figure.get("rows") or [] for cell in row[1:]]
    return _decimals(" ".join(str(v).replace(",", "") for v in values))


KIND_STEM_RULES = {
    "annual_growth": (r"年均", "年均增长题干须含“年均”"),
    "multiple": (r"倍", "倍数题须问“多少倍”"),
    "average": (r"平均|人均|户均|均价|每(?:个|家|人|户|件|吨|亩|台|辆|艘|项)|单位", "平均数题须问平均数、人均/户均等或其增速"),
    "share": (r"比重|占|份额", "比重题须问占比或比重"),
    "share_change": (r"比重|占比|份额", "比重变化题须问比重的两期变化"),
    "percentage_point": (r"百分点", "百分点题须在题干或选项使用“个百分点”"),
}


def question_style_issues(question, calculation=None, slot=None):
    issues = []
    slot = slot or {}
    stem = str(question.get("stem") or "")
    explanation = str(question.get("explanation") or "")
    family = question.get("family") or slot.get("family")
    kind = str(slot.get("kind") or "")
    if VAGUE.search(explanation):
        issues.append(f"解析用「{VAGUE.search(explanation)[0]}」搪塞干扰项；写出该选项对应的错误算式")
    if kind in KIND_STEM_RULES:
        pattern, message = KIND_STEM_RULES[kind]
        blob = stem + (" ".join(str(o.get("text")) for o in question.get("options") or []) if kind == "percentage_point" else "")
        if not re.search(pattern, blob):
            issues.append(message)
    if kind == "share_change" and not re.search(r"百分点|上升|下降|提高|降低|变化|升降", stem + json.dumps(question.get("options"), ensure_ascii=False)):
        issues.append("比重变化题须问比重上升/下降或变化多少个百分点")
    if kind == "interval_growth" and not re.search(r"间隔|隔年", explanation):
        issues.append("间隔增长率题解析须写明间隔增长率公式R=r1+r2+r1×r2")
    if family not in {"detail", "judge", None, ""}:
        keys = [str(o.get("key")) for o in question.get("options") or []]
        missing = []
        for key in keys:
            if key == question.get("answer"):
                continue
            spots = [m.end() for m in re.finditer(rf"(?<![A-Za-z]){key}\s*(?:项|选项|[：:、])|选项\s*{key}(?![A-Za-z])", explanation)]
            if not any(ARITH.search(explanation[pos:pos + 120]) for pos in spots):
                missing.append(key)
        if missing:
            issues.append(f"解析未写出干扰项{'、'.join(missing)}的错误算式（格式如“{missing[0]}项：错误算式=结果”）")
        values = _option_values(question)
        if len(values) == 4:
            ordered = sorted(values.items(), key=lambda kv: kv[1])
            for (k1, v1), (k2, v2) in zip(ordered, ordered[1:]):
                scale = max(abs(v1), abs(v2))
                if scale and abs(v2 - v1) / scale < 0.03:
                    issues.append(f"选项{k1}与{k2}过近（{v1:g}与{v2:g}，相对差<3%），需精算才能区分；拉开选项间距")
                    break
        answer = next((str(o.get("text")) for o in question.get("options", []) if o.get("key") == question.get("answer")), "")
        if kind in {"share", "growth_rate", "average", "interval_growth", "mixed_growth", "annual_growth"} and "百分点" not in answer:
            matched = re.search(r"(\d+(?:\.\d+)?)\s*[%％]", answer)
            if matched and float(matched[1]) == round(float(matched[1])):
                issues.append("正确值恰为整数百分比，数字不自然；调整底层数据")
        if kind == "multiple":
            matched = re.search(r"(\d+(?:\.\d+)?)\s*倍", answer)
            if matched and float(matched[1]) == round(float(matched[1])):
                issues.append("倍数题正确值为整数倍，数字不自然；调整底层数据")
    issues.extend(_legacy_style_issues(question))
    return issues


TRAP_PATTERNS = {
    "百分点与百分比": lambda t: "百分比" in t and "百分点" in t,
    "累计当当年": lambda t: "累计" in t,
    "缺数据无法比较": lambda t: bool(re.search(r"(?:无法|不能)(?:比较|判断|得出|确定|计算|求出)|未(?:给出|提及|提供)|缺少|缺乏|没有给出", t)),
}


def paper_issues(materials, questions, slots=None):
    """Cross-question checks that need the whole material (or paper)."""
    slots = slots or []
    slot_by_id = {}
    for index, question in enumerate(questions):
        matched = re.search(r"-M(\d{2})-Q(\d)$", str(question.get("external_id") or ""))
        position = (int(matched[1]) - 1) * 5 + int(matched[2]) - 1 if matched and len(slots) == 20 else index
        if position < len(slots):
            slot_by_id[question.get("external_id")] = slots[position]
    errors = []
    trap_papers = []
    for material in materials:
        mid = material.get("external_id")
        own = [q for q in questions if q.get("material_id") == mid]
        figure = material.get("figure") or {}
        figure_only = {v for v in _figure_values(figure) - _decimals(material.get("content") or "")
                       if v >= 10 or v != v.to_integral_value()}
        if figure.get("kind") in {"bars", "table"} and own:
            used = set()
            for question in own:
                if (question.get("family") or slot_by_id.get(question.get("external_id"), {}).get("family")) != "detail":
                    used |= figure_only & _decimals(question.get("explanation") or "")
            if len(used) < 2:
                errors.append(f"{mid}: 图表独有数据只有{len(used)}个写进解析算式；至少两个图表数据须进入题目计算")
        for question in own:
            slot = slot_by_id.get(question.get("external_id"), {})
            if slot.get("kind") == "annual_growth" and figure.get("kind") == "bars":
                if len(_figure_values(figure) & _decimals(question.get("explanation") or "")) < 2:
                    errors.append(f"{question.get('external_id')}: 年均增长须用图中多年序列的至少两个数据")
            if (question.get("family") or slot.get("family")) == "judge":
                explanation = str(question.get("explanation") or "")
                if len(ARITH.findall(explanation)) < 2:
                    errors.append(f"{question.get('external_id')}: 综合分析解析至少两处写出核算算式，不能只靠文字陷阱")
                hits = [name for name, test in TRAP_PATTERNS.items() if test(explanation)]
                if len(hits) > 1:
                    errors.append(f"{question.get('external_id')}: 综合分析同时依赖{'、'.join(hits)}文字陷阱；每篇至多一类")
                if hits:
                    trap_papers.append(mid)
    if len(set(trap_papers)) > 2:
        errors.append(f"{'、'.join(sorted(set(trap_papers)))}: 综合分析有{len(set(trap_papers))}篇依赖百分点/累计/缺数据文字陷阱，全卷至多两篇")
    return errors


def _legacy_style_issues(question):
    issues = []
    stem = str(question.get("stem") or "")
    if question.get("family") != "judge" and re.search(
        r"(?:利润率|比重|占比)(?:与|相?比|较|同比|相对|比上年|提高|增长|下降|降低|上升)", stem
    ) and "百分点" not in stem and not any("百分点" in str(o.get("text")) for o in question.get("options", [])):
        issues.append("比率两期变化须问百分点；growth槽请改问收入/利润额的增速，不能改成比率的比值增长率")
    answer = next((str(o.get("text")) for o in question.get("options", []) if o.get("key") == question.get("answer")), "")
    if question.get("family") == "mix_pull" and "倍" in answer:
        matched = re.search(r"(\d+(?:\.\d+)?)\s*倍", answer)
        if matched and math.isclose(float(matched[1]), round(float(matched[1])), abs_tol=1e-9):
            issues.append("混合倍数的正确选项为整数倍；重新设计取数/底层数据，不得直接微调答案")
    if question.get("family") == "chart_match" or any(
        o.get("figure") or o.get("images") for o in question.get("options", [])
    ):
        issues.append("四图选一尚未实现，本轮禁止chart_match/选项图")
    issues.extend(explanation_math_issues(str(question.get("explanation") or "")))
    return issues

"""Auditable arithmetic and style checks for the scoped Gemini workers."""
import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP

VERSION = "gd-agent-v1"
MATERIAL_RULES = """材料验收清单：
先生成多一至两位小数的原创底层金额，按同一底数推导总计，再把各数分别四舍五入到公报显示精度。
不要求每组都有缺口，但本篇至少保留一组有真实舍入缺口的穷尽分项，不能直接给合计加0.1造假。
若所有展示分项都严丝合缝，不能套写“分项之和与总计略有差异”。不穷尽的部分列举不得当作舍入缺口。
material额外携带rounding_checks数组（仅供验收，不给考生看），每组格式：
{"label":"2024年某指标合计","unit":"亿元","places":1,
 "parts":[{"label":"甲","raw":"114.36","shown":"114.4"},{"label":"乙","raw":"86.16","shown":"86.2"}],
 "total":{"label":"合计","raw":"200.52","shown":"200.5"}}
示例数字不得照抄；raw总计必须精确等于raw分项和，每个shown必须等于自身raw四舍五入结果。
所有shown及其指标须出现在正文或结构化图表；年份、地区、单位、范围须一致。不得为凑台账新添无关组。
正文与图表内的全部总分关系都要核对，台账不能代替统计口径审查；有实际缺口时才写舍入注。
审查增长率反推时也须尊重显示精度，不能通过更改答案或放宽容差掩盖不自洽。"""

QUESTION_RULES = """新增轨A质量清单：
问比重、占比、利润率等比率的两期变化，使用“上升/下降多少个百分点”，不问这些比率本身相对增长百分之几。
growth槽可问营业收入/利润额等绝对指标的同比增长率，不可为了百分点问法偷换槽位/主标签。
混合槽如问两部分的倍数关系，正确结果不得精确或按选项精度近似落成整数倍（例如5.0倍）；
不能微调标答，须依据合理底层数据更换取数对象或重设材料。优先自然混合加权增速，避免反推整数配比。
四个选项的错误路径须可实际复现；禁止审核用“计算失误/取数错误”等泛话替缺乏依据的干扰项辩护。
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
    if any(gaps) and "四舍五入" not in str(material.get("content") or ""):
        errors.append("存在真实舍入差异但正文/注释缺少四舍五入说明")
    return errors


def question_style_issues(question, calculation=None):
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
    return issues

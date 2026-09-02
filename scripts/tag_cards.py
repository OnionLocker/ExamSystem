#!/usr/bin/env python3
"""Knowledge point cards - structured extraction from solver-canon/*.md"""

from typing import TypedDict, Optional

class TagCard(TypedDict):
    """Structured knowledge point card."""
    tag: str
    module: str
    primary: str
    secondary: str
    triggers: list[str]
    method: str
    traps: list[str]
    formula: Optional[str]
    next_action_template: str


# 资料分析核心卡片
ZILIAO_CARDS = {
    "资料分析-ABRX类-基期量计算与现期推算": TagCard(
        tag="资料分析-ABRX类-基期量计算与现期推算",
        module="资料分析",
        primary="ABRX类",
        secondary="基期量计算与现期推算",
        triggers=["2022年", "基期", "上年同期", "比上年增长"],
        method="基期量 = 现期量 / (1 + 增长率)。现期量必须与增长率配对同一指标，单位一致。",
        traps=["基现期颠倒", "增长率与现期量指标不配对", "单位不统一"],
        formula="A / (1 + r)",
        next_action_template="触发：「2022年」「上年同期」 → 优先：找配对的现期量和增长率，公式 A/(1+r)"
    ),
    "资料分析-ABRX类-增长量计算与现期推算": TagCard(
        tag="资料分析-ABRX类-增长量计算与现期推算",
        module="资料分析",
        primary="ABRX类",
        secondary="增长量计算与现期推算",
        triggers=["增长了", "比上年增加", "增长量"],
        method="增长量 = 现期量 × r / (1+r)，或直接 现期量 - 基期量。",
        traps=["增长量当增长率", "只算分子忘记分母", "单位错"],
        formula="A × r / (1 + r)",
        next_action_template="触发：「增长了多少」 → 优先：现期×r/(1+r)，或现期-基期"
    ),
    "资料分析-比值类-比重计算与比较": TagCard(
        tag="资料分析-比值类-比重计算与比较",
        module="资料分析",
        primary="比值类",
        secondary="比重计算与比较",
        triggers=["占比", "比重", "占", "份额"],
        method="比重 = 部分 / 整体。部分和整体必须同期同单位。",
        traps=["部分整体颠倒", "跨年跨指标", "单位不统一"],
        formula="部分 / 整体",
        next_action_template="触发：「占比」「比重」 → 优先：找配对的部分和整体，同期同单位"
    ),
    "资料分析-综合分析-综合判断": TagCard(
        tag="资料分析-综合分析-综合判断",
        module="资料分析",
        primary="综合分析",
        secondary="综合判断",
        triggers=["以下说法", "可以判断", "属实", "能推出"],
        method="逐项验证，排除错误项。注意「无法推出」不等于「错误」。",
        traps=["材料未提及当成错误", "估算误差过大", "时间范围偷换"],
        formula=None,
        next_action_template="触发：「综合判断」 → 优先：逐项验证，排除明确错误项"
    )
}

# 翻译推理核心卡片
FANYI_CARDS = {
    "判断推理-逻辑判断-翻译推理-假言直言综合推理": TagCard(
        tag="判断推理-逻辑判断-翻译推理-假言直言综合推理",
        module="判断推理",
        primary="逻辑判断",
        secondary="翻译推理",
        triggers=["只有...才", "除非", "如果...那么", "或者"],
        method="①写翻译 → ②写逆否 → ③排除「肯后」和「否前」 → ④剩下的就是答案。「才」是箭头尾巴(B→A)，「否则」是反着推(¬前→后)。",
        traps=["肯后推前件", "否前推后件", "忘记写逆否", "主语偷换"],
        formula="A→B 的逆否是 ¬B→¬A",
        next_action_template="触发：「只有才」「除非」「如果那么」 → 优先：写翻译立刻写逆否，排除肯后否前"
    )
}

# 数量关系核心卡片
SHULIANG_CARDS = {
    "数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）": TagCard(
        tag="数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）",
        module="数量关系",
        primary="排列组合",
        secondary="特殊模型",
        triggers=["分组", "分配", "均等", "相同人数"],
        method="均等分组消序铁律：完全均等分堆必须除以组数阶乘(m!)。带具体地点直接按地点挑人分步相乘，严禁画蛇添足写除法。",
        traps=["均等分组忘记除阶乘", "部分均等只除部分阶乘", "有地点时多除了"],
        formula="均等分m组 = C(n,k)×C(n-k,k)×... / m!",
        next_action_template="触发：「均分」「相同人数」 → 优先：选人后除以组数阶乘；有地点直接分步乘"
    ),
    "数量关系-有规律的周期循环与要算准的日期星期-日期推算与余数": TagCard(
        tag="数量关系-有规律的周期循环与要算准的日期星期-日期推算与余数",
        module="数量关系",
        primary="周期循环",
        secondary="日期推算",
        triggers=["星期", "周几", "多少天后", "间隔"],
        method="单月余数即时对冲法：草稿纸只写各月模7余数(大月+3/小月+2/平2月0/闰2月+1)，逢7划掉。接近7的数字记负余数(如20≡-1)。",
        traps=["加总三位数做长除法", "忘记闰年2月+1", "端点±1"],
        formula="(总天数 mod 7)",
        next_action_template="触发：「星期几」「多少天后」 → 优先：写月余数逢7划掉，不加总"
    )
}

# 言语理解核心卡片
YANYU_CARDS = {
    "言语理解与表达-逻辑填空-词语辨析": TagCard(
        tag="言语理解与表达-逻辑填空-词语辨析",
        module="言语理解与表达",
        primary="逻辑填空",
        secondary="词语辨析",
        triggers=["填入画横线", "依次填入", "最恰当"],
        method="优先锁定第二空：搭配固定/排除明显不当，缩小范围后再看第一空。不追求完美，只选最恰当。",
        traps=["三个极端假词+一个明显真", "只看第一空", "过度赏析"],
        formula=None,
        next_action_template="触发：「依次填入」 → 优先：先锁第二空搭配，再看第一空"
    )
}

# 合并所有卡片
ALL_TAG_CARDS = {
    **ZILIAO_CARDS,
    **FANYI_CARDS,
    **SHULIANG_CARDS,
    **YANYU_CARDS
}


def get_tag_card(tag: str) -> Optional[TagCard]:
    """Get tag card by exact tag match."""
    return ALL_TAG_CARDS.get(tag)


def search_tag_cards(keyword: str) -> list[TagCard]:
    """Search tag cards by keyword."""
    results = []
    for card in ALL_TAG_CARDS.values():
        if keyword in card['tag'] or keyword in card['method']:
            results.append(card)
    return results


def format_card_for_generation(card: TagCard) -> str:
    """Format card for question generation prompt."""
    lines = [
        f"考点：{card['tag']}",
        f"必须考查：{card['method']}"
    ]
    if card['traps']:
        lines.append(f"常见陷阱：{' / '.join(card['traps'])}")
    return "\n".join(lines)


def format_card_for_review(card: TagCard, is_correct: bool, has_draft: bool) -> str:
    """Format card for review generation."""
    result = []

    # 标准解析
    result.append(f"#### 标准解析\n{card['method']}")
    if card['formula']:
        result.append(f"\n关键公式：${card['formula']}$")

    # 考场解法
    method_short = card['method'].split('。')[0]
    result.append(f"\n#### 考场解法\n{method_short}")

    # 下次动作
    result.append(f"\n#### 下次动作\n{card['next_action_template']}")

    return "\n".join(result)


if __name__ == "__main__":
    # Test
    card = get_tag_card("资料分析-ABRX类-基期量计算与现期推算")
    if card:
        print(format_card_for_generation(card))
        print("\n---\n")
        print(format_card_for_review(card, True, False))

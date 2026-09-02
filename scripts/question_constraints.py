#!/usr/bin/env python3
"""Structured constraints for question generation - replaces verbose prompt rules."""

from typing import TypedDict, Literal

# Forbidden phrases that would expose internal structure
FORBIDDEN_PHRASES = [
    "本题考察", "秒杀模型", "哈利波特", "黑魔法", "黑暗王子",
    "混血王子", "实战技巧", "课纲词", "某省"
]

# Guangdong-specific hard rules (violating these = rejection at gate)
GD_MODULE_LAYOUTS = {
    "数量关系": {"数字推理": 5, "数学运算": 10},
    "判断推理": {"图形推理": 5, "逻辑判断": 15},
    "资料分析": {"材料数": 4, "每材料题数": 5},
    "科学推理": {"total": 5, "subjects": 5, "images_required": True},
}

# Question type constraints
QUESTION_PATTERNS = {
    "资料分析-综合判断-广东": "根据资料，以下说法可以判断属实的是（    ）",
    "资料分析-综合判断-国考": "能够从上述资料中推出的是（    ）",
    "逻辑判断-加强": "以下选项如果为真，最能支持上述论证的是（    ）",
    "逻辑判断-削弱": "以下选项如果为真，最能削弱上述论证的是（    ）",
    "翻译推理": "根据以上陈述，可以得出的是（    ）",
}

# Stem length targets (from reference-style-profile.md)
STEM_LENGTH_TARGETS = {
    "资料分析-广东": (420, 650),
    "资料分析-国考": (600, 900),
    "逻辑判断-广东": (89, 136),
    "逻辑判断-国考": (100, 160),
    "科学推理-广东": (36, 82),
    "言语理解-逻辑填空": (40, 80),
    "言语理解-片段阅读": (80, 150),
}

# Distractor types for each question family
DISTRACTOR_PATTERNS = {
    "资料分析": [
        "取错分子",
        "取错分母",
        "算式正确但单位错",
        "基现期颠倒",
        "多算或少算一期",
        "增长量当增长率",
        "比重计算跨年跨指标"
    ],
    "翻译推理": [
        "肯后推前件（逻辑谬误）",
        "否前推后件（逻辑谬误）",
        "主语偷换",
        "结论写进主语"
    ],
    "逻辑填空": [
        "近义词但搭配不当",
        "感情色彩不符",
        "程度过重或过轻"
    ],
    "加强削弱": [
        "跑题项（未作用于结论）",
        "无关人物或情境",
        "强度不足"
    ]
}

# Answer distribution constraints
def answer_balance_constraints(n: int, module: str = "") -> dict:
    """Generate answer distribution rules."""
    import math
    base_max = math.ceil(n * 0.4)
    min_letters = min(3, n) if n >= 3 else 1

    result = {
        "answer_max_per_letter": base_max,
        "answer_min_letters": min_letters
    }

    # 资料分析特殊规则：4篇中3篇ABCD各一+1，1篇打散
    if module == "资料分析" and n == 20:
        result["ziliao_special"] = "3篇ABCD各一次+1随机，1篇打散"

    return result


class QuestionConstraint(TypedDict):
    """Structured constraint for one question or batch."""
    tag: str
    module: str
    sub_category: str
    stem_length_range: tuple[int, int]
    question_pattern: str
    distractor_types: list[str]
    forbidden_phrases: list[str]
    requires_image: bool
    answer_constraints: dict


def build_constraint(
    tag: str,
    module: str,
    paper_style: Literal["gd", "gk", "sz"] = "gd",
    requires_image: bool = False
) -> QuestionConstraint:
    """Build structured constraint from tag."""

    # Extract sub_category
    parts = tag.split("-")
    sub_category = parts[1] if len(parts) >= 2 else ""

    # Determine stem length
    if module == "资料分析":
        key = f"{module}-{paper_style}"
    elif module == "判断推理" and "逻辑判断" in tag:
        key = f"逻辑判断-{paper_style}"
    elif module == "科学推理" or "科学推理" in tag:
        key = f"{module}-{paper_style}"
    else:
        key = f"{module}-{sub_category}" if sub_category else module

    stem_range = STEM_LENGTH_TARGETS.get(key, (60, 120))

    # Question pattern
    pattern_key = f"{sub_category}-{paper_style}" if paper_style != "gd" else sub_category
    if pattern_key not in QUESTION_PATTERNS:
        pattern_key = sub_category
    question_pattern = QUESTION_PATTERNS.get(pattern_key, "")

    # Distractor types
    distractor_family = module
    if "翻译推理" in tag:
        distractor_family = "翻译推理"
    elif "加强" in tag or "削弱" in tag:
        distractor_family = "加强削弱"
    elif "逻辑填空" in tag:
        distractor_family = "逻辑填空"

    distractors = DISTRACTOR_PATTERNS.get(distractor_family, [])

    return QuestionConstraint(
        tag=tag,
        module=module,
        sub_category=sub_category,
        stem_length_range=stem_range,
        question_pattern=question_pattern,
        distractor_types=distractors,
        forbidden_phrases=FORBIDDEN_PHRASES,
        requires_image=requires_image,
        answer_constraints=answer_balance_constraints(1, module)
    )


def format_constraint_prompt(constraint: QuestionConstraint) -> str:
    """Convert constraint to compact prompt text."""
    lines = [
        f"考点：{constraint['tag']}",
        f"题干长度：{constraint['stem_length_range'][0]}-{constraint['stem_length_range'][1]}字"
    ]

    if constraint['question_pattern']:
        lines.append(f"设问句式：{constraint['question_pattern']}")

    if constraint['distractor_types']:
        lines.append(f"三个错误项分别来自：{' / '.join(constraint['distractor_types'][:3])}")

    if constraint['forbidden_phrases']:
        lines.append(f"禁止出现：{' '.join(constraint['forbidden_phrases'][:5])}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test
    c = build_constraint("资料分析-ABRX类-基期量计算与现期推算", "资料分析", "gd")
    print(format_constraint_prompt(c))

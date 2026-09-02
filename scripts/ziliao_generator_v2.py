#!/usr/bin/env python3
"""Optimized 资料分析 generator with structured constraints."""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.question_constraints import build_constraint, format_constraint_prompt
from scripts.tag_cards import get_tag_card, format_card_for_generation


def build_ziliao_batch_prompt(pack: dict, style_marker: str = "GONGKAO-STYLE-v1") -> str:
    """Build optimized prompt for 资料分析 batch generation.

    Args:
        pack: Output from learner_snapshot.py --ziliao-pack
        style_marker: Style version marker

    Returns:
        Compact prompt (target <1000 tokens vs current ~2000 lines)
    """

    paper_style = pack.get("paper_style", "gd")
    materials = pack.get("materials", [])

    # Core constraints (replaces 569-line quiz-pipeline)
    core_rules = f"""# 资料分析出题约束 ({style_marker})

## 硬性规则（违反直接拒绝）
- 4篇材料 × 5题 = 20题
- 四篇形态必须不同：纯文字 / 文字+表 / 文字+图 / 混合(至少1题选项是图)
- 答案分布：3篇ABCD各一次+1随机，1篇打散
- 题干长度：420-650字（广东风格）
- 禁用词：某省、本题考察、秒杀模型
- 脏数字≥40%（非整百整千）
- Q5必须综合判断且形式跨篇轮换

## 广东设问固定句式
- 综合判断："根据资料，以下说法可以判断属实的是（    ）"
- 其他题型："2023年XX为（    ）" 或 "2023年XX比2022年增长（    ）"

## 三个错误项规则
每题错误项必须来自三种不同且可复算的错因：
- 取错分子/分母
- 算式正确但单位错
- 基现期颠倒
- 多算或少算一期
- 增长量当增长率
- 比重计算跨年跨指标

禁止：随机邻近值、两个错项同属"取错分子"。
"""

    # Material-level instructions
    material_prompts = []
    for i, mat in enumerate(materials, 1):
        form = mat.get("form", "text")
        form_label = mat.get("form_label", "纯文字")
        answers = mat.get("answers", [])
        slots = mat.get("slots", [])

        mat_prompt = f"""
## 材料{i}（{form_label}）
形态：{form}
答案序列：{' '.join(answers)}（先算定值，再把正确项排到指定字母）

题目配置："""

        for j, slot in enumerate(slots, 1):
            tag = slot.get("tag", "")
            answer = slot.get("answer", "")
            reason = slot.get("reason", "")

            # Get tag card if available
            card = get_tag_card(tag)
            if card:
                card_info = format_card_for_generation(card)
            else:
                card_info = f"考点：{tag}"

            mat_prompt += f"""
Q{j} (答案{answer}):
{card_info}
{reason}
"""

        material_prompts.append(mat_prompt)

    # Combine all parts
    full_prompt = core_rules + "\n" + "\n".join(material_prompts) + """

## 输出要求
1. 先编写4篇材料的完整数据（年份×指标），保证数值自洽
2. 按上述配置逐题生成，题干用材料数据，选项按指定答案排列
3. 每题附 calculations.json 格式的验算表达式
4. 材料用文字描述，表/图稍后用render_ziliao_figure.py渲染

场景、项目、数字你自己编，但结构必须符合上述约束。
"""

    return full_prompt


def estimate_prompt_tokens(text: str) -> int:
    """Rough token estimate (Chinese ~1.5 chars per token)."""
    return len(text) // 1.5


def main():
    """Test the optimized prompt generator."""

    # Simulate pack from learner_snapshot.py --ziliao-pack
    test_pack = {
        "paper_style": "gd",
        "materials": [
            {
                "form": "text",
                "form_label": "纯文字",
                "answers": ["A", "B", "C", "D", "A"],
                "slots": [
                    {
                        "tag": "资料分析-ABRX类-基期量计算与现期推算",
                        "answer": "A",
                        "reason": "槽位1较轻，基础计算"
                    },
                    {
                        "tag": "资料分析-ABRX类-增长量计算与现期推算",
                        "answer": "B",
                        "reason": "槽位2中等难度"
                    },
                    {
                        "tag": "资料分析-比值类-比重计算与比较",
                        "answer": "C",
                        "reason": "槽位3-4跟画像弱项"
                    },
                    {
                        "tag": "资料分析-比值类-比重计算与比较",
                        "answer": "D",
                        "reason": "槽位3-4跟画像弱项"
                    },
                    {
                        "tag": "资料分析-综合分析-综合判断",
                        "answer": "A",
                        "reason": "槽位5收束，综合判断"
                    }
                ]
            },
            # ... 3 more materials
        ]
    }

    print("=== 生成优化后的 prompt ===\n")
    start = time.time()

    prompt = build_ziliao_batch_prompt(test_pack)

    elapsed = time.time() - start
    tokens = estimate_prompt_tokens(prompt)

    print(prompt)
    print(f"\n=== 统计 ===")
    print(f"生成耗时: {elapsed*1000:.1f}ms")
    print(f"Prompt 长度: {len(prompt)} 字符")
    print(f"估算 tokens: {tokens:.0f}")
    print(f"\n对比旧版:")
    print(f"- 旧版需要读取: quiz-pipeline/SKILL.md (569行) + references/*.md (2000+行)")
    print(f"- 旧版 prompt 长度: ~8000+ tokens")
    print(f"- 新版 prompt 长度: ~{tokens:.0f} tokens")
    print(f"- Token 节省: ~{(1 - tokens/8000)*100:.0f}%")


if __name__ == "__main__":
    main()

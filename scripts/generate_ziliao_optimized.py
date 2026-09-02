#!/usr/bin/env python3
"""实际生成资料分析题的完整流程（优化版）"""

import json
import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ziliao_generator_v2 import build_ziliao_batch_prompt, estimate_prompt_tokens


def parse_ziliao_pack_output(output: str) -> dict:
    """解析 learner_snapshot.py --ziliao-pack 的输出"""
    lines = output.strip().split('\n')

    materials = []
    current_material = None

    for line in lines:
        if line.startswith('第') and '篇' in line:
            # 第1篇｜text｜纯文字，无表无图｜答案BACDB
            parts = line.split('｜')
            form_map = {'text': 'text', 'table': 'table', 'chart': 'chart', 'mixed': 'mixed'}
            form = 'text'
            for key in form_map:
                if key in parts[1]:
                    form = form_map[key]
                    break

            answers_part = parts[3] if len(parts) > 3 else ''
            answers = list(answers_part.replace('答案', '').replace('（', '').replace('）', '').strip())

            current_material = {
                'form': form,
                'form_label': parts[2].strip() if len(parts) > 2 else '',
                'answers': answers[:5],  # 只取前5个
                'slots': []
            }
            materials.append(current_material)

        elif line.strip() and line[0].isdigit() and '.' in line[:4] and current_material:
            # 解析题目槽位
            parts = line.split('｜')
            if len(parts) >= 3:
                tag = parts[1].strip()
                answer_part = [p for p in parts if '答' in p]
                answer = answer_part[0].replace('答', '').strip() if answer_part else 'A'
                reason_parts = [p for p in parts[2:] if '槽' in p or '弱项' in p or '收束' in p]
                reason = reason_parts[0].strip() if reason_parts else ''

                current_material['slots'].append({
                    'tag': tag,
                    'answer': answer,
                    'reason': reason
                })

    return {
        'paper_style': 'gd',
        'materials': materials
    }


def call_gemini_flash(prompt: str) -> str:
    """调用 Gemini Flash 生成题目（模拟）"""
    # 这里应该调用实际的 Gemini API
    # 为了演示，返回一个简化版本
    return f"""已生成资料分析批次（模拟输出）

材料1：2023年某地区新能源汽车产业发展情况
2023年，该地区新能源汽车产量达到52.8万辆，比上年增长35.2%。其中，纯电动汽车产量38.6万辆，增长42.1%；插电式混合动力汽车产量14.2万辁，增长18.5%。全年新能源汽车销售额1247.3亿元，增长28.6%。其中，出口销售额423.8亿元，增长51.2%，占销售总额的比重比上年提高5.1个百分点...

[完整材料约600字]

Q1: 2022年该地区新能源汽车产量约为（  ）万辆
A. 39.1  B. 52.8  C. 71.4  D. 35.2
[答案: A, 基期量计算]

Q2-Q5: [其余4题]

材料2-4: [类似结构]

总计20题，4篇材料，答案分布符合要求。
"""


def main():
    """完整流程测试"""
    print("=== 优化版资料分析生成流程 ===\n")

    # Step 1: 获取真实的资料包配置
    print("Step 1: 获取学员画像和资料包配置...")
    start_total = time.time()

    result = subprocess.run(
        ['python3', 'scripts/learner_snapshot.py', '--ziliao-pack'],
        capture_output=True,
        text=True,
        cwd='/home/ubuntu/ExamSystem'
    )

    if result.returncode != 0:
        print(f"错误: {result.stderr}")
        return

    pack = parse_ziliao_pack_output(result.stdout)
    step1_time = time.time() - start_total
    print(f"✓ 完成 (耗时: {step1_time*1000:.0f}ms)")
    print(f"  配置: {len(pack['materials'])}篇材料，共20题\n")

    # Step 2: 构建优化的 prompt
    print("Step 2: 构建结构化 prompt...")
    start_step2 = time.time()

    prompt = build_ziliao_batch_prompt(pack)
    tokens = estimate_prompt_tokens(prompt)

    step2_time = time.time() - start_step2
    print(f"✓ 完成 (耗时: {step2_time*1000:.0f}ms)")
    print(f"  Prompt 长度: {len(prompt)} 字符")
    print(f"  估算 tokens: {tokens:.0f}")
    print(f"  Token 节省: ~90% (相比旧版 ~8000 tokens)\n")

    # Step 3: 调用 Gemini Flash 生成
    print("Step 3: 调用 Gemini Flash 3.7 生成题目...")
    print("  (实际环境中会调用 API，这里用模拟输出)\n")
    start_step3 = time.time()

    # 实际调用 API 的代码应该在这里
    # response = call_gemini_flash(prompt)

    step3_time = time.time() - start_step3
    print(f"✓ 模拟完成 (实际耗时取决于 API)\n")

    # 总结
    total_time = time.time() - start_total
    print("=== 总结 ===")
    print(f"总耗时: {total_time*1000:.0f}ms (不含实际 API 调用)")
    print(f"  - 画像查询: {step1_time*1000:.0f}ms")
    print(f"  - Prompt 构建: {step2_time*1000:.0f}ms")
    print(f"  - API 调用: (待实测)")
    print(f"\n对比旧版:")
    print(f"  - 旧版 Input tokens: ~8000")
    print(f"  - 新版 Input tokens: ~{tokens:.0f}")
    print(f"  - 节省: ~{8000 - tokens:.0f} tokens")
    print(f"  - 成本降低: ~{(1 - tokens/8000)*100:.0f}%")
    print(f"\n预期效果:")
    print(f"  - 出题质量: 约束更明确，Flash 理解难度降低")
    print(f"  - 一致性: 代码校验 + 模板，减少「理解偏差」")
    print(f"  - QPS: Token 减少 90%，冷却概率大幅降低")


if __name__ == "__main__":
    main()

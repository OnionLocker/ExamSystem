#!/usr/bin/env python3
"""简化版实测：用正确的模型名测试"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.generate_ziliao_optimized import parse_ziliao_pack_output
from scripts.ziliao_generator_v2 import build_ziliao_batch_prompt, estimate_prompt_tokens

# 获取资料包配置
result = subprocess.run(
    ['python3', 'scripts/learner_snapshot.py', '--ziliao-pack'],
    capture_output=True, text=True, cwd='/home/ubuntu/ExamSystem'
)
pack = parse_ziliao_pack_output(result.stdout)

# 构建简化测试 prompt（只第1篇5题）
test_prompt = f"""你是广东省考资料分析出题专家。

## 硬性规则
- 广东省考风格，题干420-600字
- 答案序列：{' '.join(pack['materials'][0]['answers'])}
- 禁用词：某省、本题考察
- 设问句式："2023年XX为（  ）"

## 任务
生成1篇纯文字材料（约500字）+ 5道完整题目

材料背景：2023年某地区新能源产业发展数据（自己编数字，保证自洽）

5题配置："""

for i, slot in enumerate(pack['materials'][0]['slots'], 1):
    test_prompt += f"\nQ{i}(答案{slot['answer']}): {slot['tag']}"

test_prompt += """

输出格式：
【材料】
[材料正文]

【题目】
1. [题干]
A. [选项]
B. [选项]
C. [选项]
D. [选项]
答案：X

[2-5题同样格式]
"""

# 保存到文件供 Hermes 使用
prompt_file = Path("/tmp/ziliao_test_prompt.txt")
prompt_file.write_text(test_prompt, encoding='utf-8')

print("=== 优化版 Prompt 已生成 ===\n")
print(f"文件位置: {prompt_file}")
print(f"Prompt 长度: {len(test_prompt)} 字符")
print(f"估算 tokens: {estimate_prompt_tokens(test_prompt):.0f}")
print(f"\n对比旧版:")
print(f"- 旧版: ~8000 tokens (需要读 quiz-pipeline 569行 + references 2000行)")
print(f"- 新版: ~{estimate_prompt_tokens(test_prompt):.0f} tokens")
print(f"- 节省: ~{(1 - estimate_prompt_tokens(test_prompt)/8000)*100:.0f}%")
print(f"\n请在 Hermes 中执行以下命令测试生成：")
print(f"\n```")
print(f"用 gemini-3.7-flash-high 按照 {prompt_file} 的要求生成资料分析题")
print(f"```")
print(f"\n或者直接复制这个 prompt：")
print(f"\n---")
print(test_prompt)
print(f"---")

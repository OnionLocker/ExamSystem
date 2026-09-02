#!/usr/bin/env python3
"""实际调用 Gemini Flash 测试资料分析生成（优化版 vs 原版对比）"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_ziliao_optimized import parse_ziliao_pack_output
from scripts.ziliao_generator_v2 import build_ziliao_batch_prompt, estimate_prompt_tokens
import subprocess


def get_cliproxy_key() -> str:
    """获取 CLIPROXY API key"""
    key = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if key:
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def call_gemini_flash(prompt: str, model: str = "gemini-3.7-flash") -> tuple[str, dict]:
    """调用 Gemini Flash 生成题目"""
    base_url = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
    api_key = get_cliproxy_key()

    if not api_key:
        raise ValueError("CLIPROXY_API_KEY not found")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是广东省考资料分析题的专业出题人。严格按照给定约束生成题目。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 8000
    }

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    start = time.time()
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    elapsed = time.time() - start

    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

    usage = result.get("usage", {})
    stats = {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "elapsed_seconds": elapsed
    }

    return content, stats


def main():
    print("=== 实际测试：优化版资料分析生成 ===\n")

    # Step 1: 获取资料包配置
    print("Step 1: 获取学员画像配置...")
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
    print(f"✓ 已配置 {len(pack['materials'])} 篇材料\n")

    # Step 2: 构建优化 prompt
    print("Step 2: 构建优化版 prompt...")
    optimized_prompt = build_ziliao_batch_prompt(pack)
    optimized_tokens = estimate_prompt_tokens(optimized_prompt)

    print(f"✓ Prompt 构建完成")
    print(f"  长度: {len(optimized_prompt)} 字符")
    print(f"  估算 tokens: {optimized_tokens:.0f}\n")

    # Step 3: 调用 API 生成（只生成第一篇材料作为测试）
    print("Step 3: 调用 Gemini Flash 3.7 生成...")
    print("  (为节省成本，只生成第1篇材料5题作为测试)\n")

    # 简化版 prompt - 只生成第1篇
    test_prompt = f"""# 资料分析出题测试

## 硬性规则
- 广东省考风格
- 题干长度：420-650字
- 答案序列：{' '.join(pack['materials'][0]['answers'])}
- 禁用词：某省、本题考察

## 材料1要求
形态：纯文字（4段，约500字）
场景：2023年某地区产业发展数据（自己编数字，保证自洽）

题目配置：
"""

    for i, slot in enumerate(pack['materials'][0]['slots'], 1):
        test_prompt += f"\nQ{i}（答案{slot['answer']}）: {slot['tag']}\n"

    test_prompt += "\n只输出：材料正文 + 5道完整题目（题干+4个选项，标注正确答案）"

    try:
        print(f"  发送请求... (输入约 {estimate_prompt_tokens(test_prompt):.0f} tokens)")
        start_total = time.time()

        content, stats = call_gemini_flash(test_prompt)

        total_time = time.time() - start_total

        print(f"✓ 生成完成\n")

        # 输出统计
        print("=== 生成结果 ===")
        print(f"\n{content[:500]}...\n")  # 只显示前500字符

        print("\n=== 性能统计 ===")
        print(f"API 耗时: {stats['elapsed_seconds']:.2f}s")
        print(f"Input tokens: {stats['input_tokens']}")
        print(f"Output tokens: {stats['output_tokens']}")
        print(f"Total tokens: {stats['total_tokens']}")

        print("\n=== 对比分析 ===")
        old_input = 8000  # 旧版估算
        print(f"旧版预计 input: ~{old_input} tokens")
        print(f"新版实际 input: {stats['input_tokens']} tokens")
        print(f"Token 节省: {old_input - stats['input_tokens']} ({(1 - stats['input_tokens']/old_input)*100:.0f}%)")

        # 估算成本（Gemini Flash 3.7 价格）
        # Input: $0.075 / 1M tokens, Output: $0.30 / 1M tokens
        old_cost = (old_input * 0.075 + stats['output_tokens'] * 0.30) / 1_000_000
        new_cost = (stats['input_tokens'] * 0.075 + stats['output_tokens'] * 0.30) / 1_000_000

        print(f"\n=== 成本对比（单次生成1篇材料5题）===")
        print(f"旧版成本: ${old_cost*1000:.4f} (千次)")
        print(f"新版成本: ${new_cost*1000:.4f} (千次)")
        print(f"节省: ${(old_cost-new_cost)*1000:.4f} (千次)")

        print(f"\n按每天生成5批次（100题）计算：")
        print(f"  旧版月成本: ${old_cost*5*30:.2f}")
        print(f"  新版月成本: ${new_cost*5*30:.2f}")
        print(f"  月节省: ${(old_cost-new_cost)*5*30:.2f}")

    except Exception as e:
        print(f"✗ 生成失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

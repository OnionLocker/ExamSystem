#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一出题工具 - 服务 Hermes 即时出题和定时批次生成

用途：
1. Hermes 即时出题：quiz_generator.py --tag "判断推理-逻辑判断-翻译推理" --count 5
2. 定时批次生成：被 daily_batch_scheduler.py 调用（复用相同逻辑）

优势：
- Hermes 不再加载 1584 行提示词到 session
- 出题逻辑统一，质量标准一致
- 外部进程，可显示进度，Hermes 不阻塞
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 复用 daily_batch_scheduler 和 daily_gemini_batch 的逻辑
from daily_batch_scheduler import generation_prompt
from daily_gemini_batch import generate_and_import
from scheduler_common import (
    DB,
    ROOT,
    daily_source_name,
    difficulty_tier,
    load_snapshot,
    local_today,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="统一出题工具 - 服务 Hermes 即时出题和定时批次",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # Hermes 即时出 5 道翻译推理
  python3 quiz_generator.py \\
    --module 判断推理 \\
    --tag "判断推理-逻辑判断-翻译推理" \\
    --count 5 \\
    --batch-id "20260903_hermes_翻译推理_01"

  # 出 10 道资料分析（4材料×5题，其实是20题）
  python3 quiz_generator.py \\
    --module 资料分析 \\
    --count 20 \\
    --batch-id "20260903_hermes_资料_01"
"""
    )
    parser.add_argument("--module", required=True, help="模块名：判断推理/资料分析/数量关系/言语理解与表达/科学推理")
    parser.add_argument("--tag", help="三级考点标签（可选）：如 判断推理-逻辑判断-翻译推理")
    parser.add_argument("--count", type=int, required=True, help="题目数量")
    parser.add_argument("--batch-id", required=True, help="批次 ID，如 20260903_hermes_翻译推理_01")
    parser.add_argument("--difficulty", choices=["easy", "hard"], help="难度档（可选，默认根据日期自动推断）")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "hermes-batches", help="输出目录")
    parser.add_argument("--timeout", type=int, default=2400, help="超时秒数（默认 2400s = 40min）")
    parser.add_argument("--db", type=Path, default=DB, help="数据库路径")
    parser.add_argument("--interactive", action="store_true", help="交互模式：输出简洁 JSON 供 Hermes 解析")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 准备运行参数（模拟 daily_batch_scheduler 的 run 字典）
    today = local_today()
    run = {
        "module": args.module,
        "plan_date": today.isoformat(),
        "batch_id": args.batch_id,
        "planned_count": args.count,
    }

    # 加载学员画像快照
    snapshot = load_snapshot(args.db)

    # 生成批次目录
    batch_dir = args.output_dir / today.isoformat() / args.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    # 构建 prompt（复用 daily_batch_scheduler 的逻辑）
    prompt = generation_prompt(run, snapshot, batch_dir, args.db)

    # 如果指定了 tag，追加到 prompt（Hermes 场景：用户点名某个考点）
    if args.tag:
        prompt += f"\n\n# 用户指定考点\n本批必须聚焦以下考点：{args.tag}\n"
        prompt += "可以在该考点下选择不同子类型，但不得跨一级或二级。\n"

    # 如果指定了难度，覆盖自动推断
    if args.difficulty:
        prompt += f"\n\n# 用户指定难度档\n本批难度档强制为：{args.difficulty}\n"

    if not args.interactive:
        print(f"=== 开始生成 {args.module} {args.count} 题 ===")
        print(f"批次 ID: {args.batch_id}")
        print(f"输出目录: {batch_dir}")
        print(f"考点: {args.tag or '自动选择'}")
        print(f"难度: {args.difficulty or difficulty_tier(run['plan_date'])}")
        print()

    try:
        # 调用统一的生成 + 验证 + 导入流程
        generate_and_import(
            run=run,
            batch_dir=batch_dir,
            db_path=args.db,
            timeout=args.timeout,
            prompt=prompt,
        )

        # 成功：输出结果
        result = {
            "status": "success",
            "batch_id": args.batch_id,
            "imported": args.count,
            "batch_dir": str(batch_dir),
            "message": f"已入库 {args.count} 题，批次 {args.batch_id}"
        }

        if args.interactive:
            # Hermes 交互模式：只输出 JSON
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"\n✅ 出题完成！")
            print(f"   入库: {args.count} 题")
            print(f"   批次: {args.batch_id}")
            print(f"   目录: {batch_dir}")
            print(f"\n用户可在 ExamSystem 「AI 练题」查看。")

        return 0

    except Exception as exc:
        result = {
            "status": "error",
            "batch_id": args.batch_id,
            "error": str(exc)[:2000],
            "message": f"出题失败：{str(exc)[:500]}"
        }

        if args.interactive:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"\n❌ 出题失败：{exc}", file=sys.stderr)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())

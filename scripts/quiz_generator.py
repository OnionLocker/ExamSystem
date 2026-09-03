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
import sqlite3
import sys
from pathlib import Path

# 复用 daily_batch_scheduler 和 daily_gemini_batch 的逻辑
from daily_batch_scheduler import generation_prompt
from daily_gemini_batch import generate_and_import
from normalize_ai_batch import generation_payload_extras
from rule_loader import load_hard_rules
from scheduler_common import (
    DB,
    ROOT,
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
    parser.add_argument(
        "--figure-control",
        action="store_true",
        help="Gemini 只出 figure spec，Python 画黑白线稿（10 题：5 空间 + 5 科推）",
    )
    return parser.parse_args()


FIGURE_KINDS = (
    "cube_net, cube_iso, voxels, views, section, section_abc, tetra, "
    "lever, pulley, circuit, tank, motion, contour, front, food, pedigree, "
    "lens, vessels, buoy, force, spring, gears, mirror, st"
)


def figure_control_prompt(run: dict, _snapshot: dict, db_path) -> str:
    extras = generation_payload_extras("判断推理", int(run["planned_count"]), str(run["batch_id"]), db_path)
    source = run["source"]
    payload = {
        "plan_date": run["plan_date"],
        "module": "空间科学推理",
        "question_count": run["planned_count"],
        "batch_id": run["batch_id"],
        "source": source,
        "all_original": True,
        "figure_kinds": FIGURE_KINDS,
        **extras,
    }
    return (
        "You are ExamSystem's writer for a 10-item Guangdong illustrated drill. "
        "Output one JSON object only. No markdown fences, no commentary.\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Exactly 10 questions, numbered "
        f"{run['batch_id']}_01 .. _10. Follow answer_plan letters.\n"
        "Q1-Q5: category=判断推理, sub_category=图形推理, tags[0]=判断推理-图形推理-空间类. "
        "Kinds: cube_net, cube_iso, voxels, views, section (use each at least once).\n"
        "Q6-Q10: category=科学推理, sub_category=科学推理. Five different subjects: "
        "力学, 压强与浮力, 电学, 生物, 地理. tags like 科学推理-力学-杠杆滑轮. "
        "Junior-high only (杠杆/浮力/串并联/等高线/食物网). No 理想气体/动量守恒/洛伦兹力.\n"
        "EVERY question must include figure (stem). Picture options also need figure. "
        "Python renders figure. You MUST emit image_specs: image_facts list every visible "
        "label/tick/intersection; must_derive is the answer and must not appear as a title.\n"
        "Figure must match the stem and be solvable from the drawing. "
        "Any 甲/乙/虚线/左视图/主视图/俯视图/L1/L2/钩码 mentioned in the stem MUST appear as labels in figure. "
        "Cube fold/rotate items: stem figure MUST be cube_net (all 6 faces). Options may be cube_iso. "
        "Do not ask a rotation question from only 3 visible faces. "
        "views: left/front/top cells must follow the intended solid, titles will be drawn large. "
        "food: pass nodes/edges using the exact organism names in the stem. "
        "contour: Python always draws dashed 甲/乙; stem must use those labels. "
        "front: cold/warm CROSS-SECTION with 冷气团/暖气团; never use contour for 锋面. "
        "lever: pass left_slot and left_n to match the stem.\n"
        "figure schema: {\"kind\":\"cube_iso\",\"file\":\"images/q-01-stem.png\","
        "\"marks\":{\"top\":\"pent\",\"south\":\"circle\",\"east\":\"x\"}} "
        "or {\"kind\":\"voxels\",\"file\":\"images/q-03-stem.png\","
        "\"voxels\":[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]} "
        "or {\"kind\":\"cube_net\",\"file\":\"images/q-01-stem.png\","
        "\"faces\":{\"pent\":[1,0],\"circle\":[0,1],\"plus\":[1,1],\"dia\":[2,1],\"x\":[3,1],\"sq\":[1,2]}} "
        "or {\"kind\":\"views\",\"file\":\"images/q-04-stem.png\","
        "\"left\":[[0,0],[0,1]],\"front\":[[0,0],[1,0]],\"top\":[[0,0],[1,0]]} "
        "or {\"kind\":\"section\",\"file\":\"images/q-05-stem.png\","
        "\"voxels\":[[0,0,0],[1,0,0],[0,1,0]],\"z\":0.5} "
        "or {\"kind\":\"lever|circuit|tank|contour|front|food|pedigree|motion|reflex\",\"file\":\"images/q-06-stem.png\"}. "
        "motion needs series/xticks; tank needs shape+objects; reflex needs parts ①–⑤. "
        "marks tokens: circle, plus, x, sq, pent, dia.\n"
        "Stem must depend on the figure (如图…). Options A-D. "
        f"Every question.source must be exactly {source}.\n"
        f"{load_hard_rules('判断推理')}\n"
        f"{load_hard_rules('科学推理')}\n"
        "JSON: {\"questions\":[{\"external_id\":\"..._01\",\"category\":\"...\","
        "\"sub_category\":\"...\",\"tags\":[\"...\"],\"stem\":\"...\","
        "\"figure\":{\"kind\":\"voxels\",\"file\":\"images/q-01-stem.png\",\"voxels\":[[0,0,0]]},"
        "\"options\":[{\"key\":\"A\",\"text\":\"...\"}],\"answer\":\"B\",\"analysis\":\"...\"}]}\n"
        "Do not emit manifest.json.\n"
    )


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
    if args.tag and not args.figure_control:
        run["focus_tag"] = args.tag
    if args.figure_control:
        run["figure_control"] = True
        run["module"] = "判断推理"
        run["planned_count"] = 10
        run["source"] = f"广东省考行测-空间科学推理-{today.strftime('%Y%m%d')}"
        args.count = 10

    # 加载学员画像快照
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        snapshot = load_snapshot(conn)
    finally:
        conn.close()

    # 生成批次目录
    batch_dir = args.output_dir / today.isoformat() / args.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    if args.figure_control:
        prompt = figure_control_prompt(run, snapshot, args.db)
    else:
        prompt = generation_prompt(run, snapshot, batch_dir, args.db)

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

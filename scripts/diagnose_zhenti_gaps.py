#!/usr/bin/env python3
"""诊断真题JSON数据缺失情况"""

import json
import os
from pathlib import Path
from collections import defaultdict, Counter

def diagnose():
    zhenti_dir = Path("data/zhenti")
    json_files = list(zhenti_dir.glob("*.json"))

    stats = {
        "total_files": len(json_files),
        "total_questions": 0,
        "missing_answer": 0,
        "missing_explanation": 0,
        "has_figure_but_missing": 0,
        "missing_material_ref": 0,
        "by_module": defaultdict(lambda: {"total": 0, "no_answer": 0, "no_explanation": 0}),
        "files_with_issues": []
    }

    for json_file in sorted(json_files):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        file_issues = {
            "file": json_file.name,
            "total": len(data.get("questions", [])),
            "no_answer": 0,
            "no_explanation": 0,
            "no_figure": 0
        }

        for q in data.get("questions", []):
            # 跳过 orphan（number 为 null 的碎片）
            if not isinstance(q.get("number"), int):
                continue

            stats["total_questions"] += 1
            module = q.get("module", "未知")

            stats["by_module"][module]["total"] += 1

            # 检查答案
            answer = q.get("correct_answer") or q.get("answer")
            if not answer or answer == "":
                stats["missing_answer"] += 1
                stats["by_module"][module]["no_answer"] += 1
                file_issues["no_answer"] += 1

            # 检查解析
            if not q.get("explanation"):
                stats["missing_explanation"] += 1
                stats["by_module"][module]["no_explanation"] += 1
                file_issues["no_explanation"] += 1

            # 检查图片
            if q.get("has_figure") and not q.get("figure_note"):
                stats["has_figure_but_missing"] += 1
                file_issues["no_figure"] += 1

        if file_issues["no_answer"] > 0 or file_issues["no_explanation"] > 0:
            stats["files_with_issues"].append(file_issues)

    # 输出报告
    print("# 真题数据缺失诊断报告")
    print(f"\n**诊断时间**: {Path.cwd()}")
    print(f"\n## 总体统计\n")
    print(f"- JSON 文件数: {stats['total_files']}")
    print(f"- 总题量: {stats['total_questions']}")
    print(f"- **缺答案**: {stats['missing_answer']} ({stats['missing_answer']/stats['total_questions']*100:.1f}%)")
    print(f"- **缺解析**: {stats['missing_explanation']} ({stats['missing_explanation']/stats['total_questions']*100:.1f}%)")
    print(f"- 标记有图但未提取: {stats['has_figure_but_missing']}")

    print(f"\n## 按模块分布\n")
    print("| 模块 | 总题数 | 缺答案 | 缺解析 |")
    print("|-----|--------|--------|--------|")
    for module in sorted(stats["by_module"].keys()):
        m = stats["by_module"][module]
        print(f"| {module} | {m['total']} | {m['no_answer']} | {m['no_explanation']} |")

    print(f"\n## 问题文件清单\n")
    for f in stats["files_with_issues"]:
        print(f"### {f['file']}")
        print(f"- 总题数: {f['total']}")
        if f['no_answer'] > 0:
            print(f"- **缺答案**: {f['no_answer']} ⚠️")
        if f['no_explanation'] > 0:
            print(f"- 缺解析: {f['no_explanation']}")
        if f['no_figure'] > 0:
            print(f"- 缺图片: {f['no_figure']}")
        print()

    print("\n## 下一步行动\n")
    if stats['missing_answer'] > 0:
        print(f"1. **P0 - 补全答案 ({stats['missing_answer']} 题)**:")
        print("   ```bash")
        print("   python3 scripts/merge_answers.py --dry-run")
        print("   python3 scripts/merge_answers.py")
        print("   ```\n")

    if stats['missing_explanation'] > stats['total_questions'] * 0.2:
        print(f"2. **P0 - 批量生成解析 ({stats['missing_explanation']} 题)**:")
        print("   - 需要创建 `scripts/batch_generate_explanations.py`")
        print("   - 或手动用 Claude/Workbuddy 批量补充\n")

    if stats['has_figure_but_missing'] > 0:
        print(f"3. **P1 - 补全图片 ({stats['has_figure_but_missing']} 题)**:")
        print("   - 需要创建 `scripts/extract_figures.py`\n")

if __name__ == "__main__":
    diagnose()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则加载器 - 从 rules/ 目录加载分层的出题规则

用途：
1. 替代硬编码的 1584 行提示词
2. 按模块和阶段加载精简规则
3. 支持规则版本管理和追溯
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).parent.parent / "rules"


def load_yaml(path: Path) -> dict[str, Any]:
    """加载 YAML 文件"""
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_hard_rules(module: str | None = None) -> str:
    """
    加载硬性约束规则

    Args:
        module: 模块名（判断推理/资料分析/数量关系/言语理解与表达/科学推理）
                None = 加载全部

    Returns:
        格式化的规则文本
    """
    guangdong = load_yaml(RULES_DIR / "hard_rules" / "guangdong_paper.yaml")

    if not guangdong:
        return "# 硬性规则文件缺失，请检查 rules/hard_rules/guangdong_paper.yaml"

    lines = ["# 广东 2024-2026 通用卷硬规则（标【GATE】者已写入 generation_gate.py）\n"]

    # 如果指定了模块，只返回该模块的规则
    if module:
        module_rules = guangdong.get(module, {})
        if not module_rules:
            # 尝试映射
            module_map = {
                "判断推理": "判断推理",
                "资料分析": "资料分析",
                "数量关系": "数量关系",
                "言语理解与表达": "言语理解与表达",
                "科学推理": "科学推理",
            }
            mapped = module_map.get(module)
            if mapped:
                module_rules = guangdong.get(mapped, {})

        if module_rules:
            lines.append(f"## {module}")
            lines.append(_format_rules(module_rules))
    else:
        # 返回全部规则
        for key, rules in guangdong.items():
            if key in ["资料分析", "数量关系", "判断推理", "科学推理", "言语理解与表达", "通用规则"]:
                lines.append(f"## {key}")
                lines.append(_format_rules(rules))
                lines.append("")

    return "\n".join(lines)


def load_quality_checks() -> str:
    """加载质量检查规则（前20条高频）"""
    checks = load_yaml(RULES_DIR / "quality" / "common_checks.yaml")

    if not checks:
        return "# 质量检查规则文件缺失"

    lines = ["# 质量检查规则（生成阶段自查清单）\n"]

    # 生成阶段规则
    gen_rules = checks.get("生成阶段规则", {})
    if gen_rules:
        lines.append("## 生成阶段自查")
        for rule_id, rule in gen_rules.items():
            lines.append(f"### {rule_id}")
            lines.append(f"- 规则: {rule.get('规则', '')}")
            if "必须打回" in rule:
                lines.append(f"- 必须打回: {rule['必须打回']}")
            if "可以通过" in rule:
                lines.append(f"- 可以通过: {rule['可以通过']}")
            lines.append("")

    # 自查清单
    checklist = checks.get("自查清单_生成后立即执行", [])
    if checklist:
        lines.append("## 自查清单（生成后立即执行）")
        for item in checklist:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def load_principles() -> str:
    """加载命题原则（从 reference-style-principles 提炼）"""
    principles = load_yaml(RULES_DIR / "meta" / "gongkao_principles.yaml")

    if not principles:
        return "# 命题原则文件缺失"

    lines = ["# 公考出题命题原则（内化版本: GONGKAO-STYLE-v1）\n"]

    # 全题型共同约束
    common = principles.get("全题型共同约束", {})
    if common:
        lines.append("## 全题型共同约束")
        for key, value in common.items():
            lines.append(f"### {key}")
            if isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, list):
                        lines.append(f"- {k}:")
                        for item in v:
                            lines.append(f"  - {item}")
                    else:
                        lines.append(f"- {k}: {v}")
            elif isinstance(value, list):
                for item in value:
                    lines.append(f"- {item}")
            lines.append("")

    # 各模块原则
    for module in ["判断推理", "资料分析", "数量关系", "言语理解与表达", "科学推理"]:
        module_prin = principles.get(module, {})
        if module_prin:
            lines.append(f"## {module}")
            lines.append(_format_rules(module_prin))
            lines.append("")

    return "\n".join(lines)


def _format_rules(rules: dict[str, Any], indent: int = 0) -> str:
    """递归格式化规则字典"""
    lines = []
    prefix = "  " * indent

    for key, value in rules.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}### {key}")
            lines.append(_format_rules(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}### {key}")
            for item in value:
                lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}- {key}: {value}")

    return "\n".join(lines)


def build_generation_prompt_rules(module: str) -> str:
    """
    构建生成阶段的完整规则集

    Args:
        module: 模块名

    Returns:
        精简的规则文本（<5000 tokens）
    """
    lines = []

    # 1. 命题原则（核心，必读）
    lines.append("# 一、命题原则（GONGKAO-STYLE-v1）")
    lines.append(load_principles())
    lines.append("")

    # 2. 硬性规则（该模块）
    lines.append("# 二、硬性约束（标【GATE】者已机械校验）")
    lines.append(load_hard_rules(module))
    lines.append("")

    # 3. 质量检查规则（前20条）
    lines.append("# 三、质量自查清单")
    lines.append(load_quality_checks())
    lines.append("")

    return "\n".join(lines)


def main():
    """测试规则加载"""
    print("=== 测试硬性规则加载 ===")
    print(load_hard_rules("判断推理")[:500])
    print("\n=== 测试质量检查加载 ===")
    print(load_quality_checks()[:500])
    print("\n=== 测试命题原则加载 ===")
    print(load_principles()[:500])
    print("\n=== 测试完整生成规则 ===")
    full = build_generation_prompt_rules("判断推理")
    print(f"完整规则长度: {len(full)} 字符")
    print(full[:800])


if __name__ == "__main__":
    main()

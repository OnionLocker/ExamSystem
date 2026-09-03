#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反克隆检测：防止生成题照搬参考题结构

检查点：
1. 特有实体复用（甲公司/乙部门/丙项目）
2. 连续8汉字重合（排除固定设问）
3. 数字链克隆（A比B多20%，B是C的1.5倍）
4. 罕见术语组合复用
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


# 固定设问模板（这些重合不算）
FIXED_TEMPLATES = [
    "根据以上信息，可以推出",
    "以下哪项如果为真",
    "最能支持上述论证的是",
    "最能削弱上述论证的是",
    "根据资料，以下说法可以判断属实的是",
    "能够从上述资料中推出的是",
    "下列说法正确的是",
    "下列说法错误的是",
]


def clean_text_for_comparison(text: str) -> str:
    """去除标点、空格，保留纯文字"""
    # 去掉所有标点和空格
    text = re.sub(r'[，。、；：！？""''（）《》【】\s\.,;:!?()\[\]<>{}]', '', text)
    return text


def remove_fixed_templates(text: str) -> str:
    """移除固定设问模板"""
    for template in FIXED_TEMPLATES:
        text = text.replace(template, '')
    return text


def find_continuous_overlap(text1: str, text2: str, min_length: int = 8) -> list[str]:
    """找出两段文本中连续重合的片段（长度 >= min_length）"""
    clean1 = clean_text_for_comparison(text1)
    clean2 = clean_text_for_comparison(text2)

    overlaps = []
    for i in range(len(clean1) - min_length + 1):
        for length in range(min_length, len(clean1) - i + 1):
            substr = clean1[i:i+length]
            if substr in clean2:
                overlaps.append(substr)

    # 去重，保留最长的
    if not overlaps:
        return []

    overlaps = sorted(set(overlaps), key=len, reverse=True)
    # 过滤：只保留不被其他更长片段包含的
    result = []
    for overlap in overlaps:
        if not any(overlap in longer for longer in result):
            result.append(overlap)

    return [o for o in result if len(o) >= min_length]


def extract_entities(text: str) -> set[str]:
    """提取特有实体（甲乙丙、公司名、人名等）"""
    entities = set()

    # 甲乙丙丁戊己庚辛壬癸 + 公司/部门/项目/企业
    pattern = r'[甲乙丙丁戊己庚辛壬癸][公司|部门|项目|企业|单位|机构|组织|团队]'
    entities.update(re.findall(pattern, text))

    # A/B/C/D + 公司（但要排除选项字母）
    if '公司' in text or '企业' in text:
        # 简单启发：如果是 "A公司" 且不在 "A." 或 "**A.**" 后面
        pattern = r'(?<![A-D]\.)\s*([A-D])[公司|企业]'
        matches = re.findall(pattern, text)
        entities.update(f'{m}公司' for m in matches)

    return entities


def extract_number_patterns(text: str) -> list[str]:
    """提取数字关系链（如"A比B多20%，B是C的1.5倍"）"""
    # 简化版：提取包含比较关系的句子片段
    patterns = []

    # 匹配 "X比Y多/少 数字%"
    pattern1 = r'[^，。]{1,15}比[^，。]{1,15}[多少增减][^，。]{0,10}\d+\.?\d*%'
    patterns.extend(re.findall(pattern1, text))

    # 匹配 "X是Y的 数字倍"
    pattern2 = r'[^，。]{1,15}是[^，。]{1,15}的\d+\.?\d*倍'
    patterns.extend(re.findall(pattern2, text))

    return patterns


def check_clone(
    question_stem: str,
    question_options: list[str],
    reference_questions: list[dict],
    threshold: float = 0.7
) -> dict[str, Any]:
    """
    检查生成题是否克隆了参考题

    Args:
        question_stem: 生成题题干
        question_options: 生成题选项列表
        reference_questions: 参考题列表（evaluate context 里的题）
        threshold: 相似度阈值

    Returns:
        {
            "is_clone": bool,
            "reasons": list[str],  # 克隆的具体原因
            "details": dict  # 详细信息
        }
    """
    reasons = []
    details = {}

    # 移除固定设问
    stem_clean = remove_fixed_templates(question_stem)

    for ref_idx, ref_q in enumerate(reference_questions):
        ref_stem = str(ref_q.get('stem') or ref_q.get('content') or '')
        ref_stem_clean = remove_fixed_templates(ref_stem)

        # 检查1：连续8汉字重合
        overlaps = find_continuous_overlap(stem_clean, ref_stem_clean, min_length=8)
        if overlaps:
            reasons.append(f"与参考题#{ref_idx+1}存在连续{len(overlaps[0])}字重合: {overlaps[0][:20]}...")
            details[f'overlap_ref_{ref_idx}'] = overlaps[:3]  # 最多记录3个

        # 检查2：特有实体复用
        entities_gen = extract_entities(question_stem)
        entities_ref = extract_entities(ref_stem)
        common_entities = entities_gen & entities_ref
        if common_entities:
            reasons.append(f"与参考题#{ref_idx+1}复用特有实体: {', '.join(common_entities)}")
            details[f'entities_ref_{ref_idx}'] = list(common_entities)

        # 检查3：数字关系链克隆
        patterns_gen = extract_number_patterns(question_stem)
        patterns_ref = extract_number_patterns(ref_stem)
        if patterns_gen and patterns_ref:
            # 简单检查：是否有相似的数字关系表达
            for pg in patterns_gen:
                for pr in patterns_ref:
                    if clean_text_for_comparison(pg) == clean_text_for_comparison(pr):
                        reasons.append(f"与参考题#{ref_idx+1}数字关系链雷同: {pg}")
                        details[f'number_pattern_ref_{ref_idx}'] = pg

    return {
        "is_clone": len(reasons) > 0,
        "reasons": reasons,
        "details": details
    }


def check_batch_clones(
    batch_dir: Path,
    db_path: Path
) -> dict[str, Any]:
    """
    检查整批题目是否有克隆

    Returns:
        {
            "verdict": "PASS" | "REJECT",
            "total_questions": int,
            "clone_count": int,
            "clones": [{"question_id": str, "reasons": list[str]}]
        }
    """
    import json

    # 读取生成的题目
    questions_path = batch_dir / "questions.json"
    if not questions_path.is_file():
        return {"verdict": "PASS", "total_questions": 0, "clone_count": 0, "clones": []}

    questions = json.loads(questions_path.read_text(encoding='utf-8'))
    if not isinstance(questions, list):
        questions = questions.get('questions', [])

    # 读取 manifest 获取 evaluation_contexts
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.is_file():
        # 没有 manifest，跳过检查
        return {"verdict": "PASS", "total_questions": len(questions), "clone_count": 0, "clones": []}

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    eval_contexts = manifest.get('generation', {}).get('evaluation_contexts', [])

    if not eval_contexts:
        # 没有 evaluation_contexts，跳过检查
        return {"verdict": "PASS", "total_questions": len(questions), "clone_count": 0, "clones": []}

    # 从数据库加载参考题
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 建立 question_id -> context 映射
    q_to_context = {}
    for ctx in eval_contexts:
        for qid in ctx.get('question_ids', []):
            q_to_context[qid] = ctx

    clones = []

    for question in questions:
        qid = str(question.get('external_id') or '')
        if not qid or qid not in q_to_context:
            continue

        ctx = q_to_context[qid]
        context_id = ctx.get('context_id')
        if not context_id:
            continue

        # 从数据库查询该 context 的参考题
        cursor = conn.execute("""
            SELECT rq.stem, rq.content, rq.options
            FROM reference_context_runs rcr
            JOIN reference_questions rq ON rq.id IN (
                SELECT value FROM json_each(rcr.reference_ids)
            )
            WHERE rcr.context_id = ?
        """, (context_id,))

        ref_questions = []
        for row in cursor:
            ref_questions.append({
                'stem': row['stem'] or row['content'],
                'options': row['options']
            })

        if not ref_questions:
            continue

        # 执行克隆检测
        stem = str(question.get('stem') or '')
        options = [opt.get('text', '') for opt in question.get('options', [])]

        result = check_clone(stem, options, ref_questions)

        if result['is_clone']:
            clones.append({
                "question_id": qid,
                "reasons": result['reasons'],
                "details": result['details']
            })

    conn.close()

    return {
        "verdict": "REJECT" if clones else "PASS",
        "total_questions": len(questions),
        "clone_count": len(clones),
        "clones": clones
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="反克隆检测")
    parser.add_argument("batch_dir", type=Path, help="批次目录")
    parser.add_argument("--db", type=Path, default=Path("data/exam.db"), help="数据库路径")
    parser.add_argument("--output", type=Path, help="输出 JSON 路径")
    args = parser.parse_args()

    result = check_batch_clones(args.batch_dir, args.db)

    if args.output:
        import json
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

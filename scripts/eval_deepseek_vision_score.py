#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终评分：用修复后的多选感知答案串给 DeepSeek 作答结果对拍。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_deepseek_vision_2026 import extract_answer_key, APDF

OUT = Path("/tmp/ds_vision_eval")


def main() -> int:
    key = extract_answer_key(APDF)
    total = len(key)
    answers = json.loads((OUT / "answers.json").read_text(encoding="utf-8"))
    answers = {int(k): v for k, v in answers.items()}

    missing = [n for n in range(1, total + 1) if n not in answers]
    correct = 0
    wrong = []
    for n in range(1, total + 1):
        a = answers.get(n)
        if a is None:
            continue
        k = key[n - 1]
        ok = (a == k) or (set(a) == set(k) and len(a) == len(k))
        if ok:
            correct += 1
        else:
            wrong.append((n, a, k))

    print("=" * 64)
    print("2026 广东行测 · DeepSeek 原生视觉作答 · 最终评分")
    print(f"总题数 {total} · 已答 {len(answers)} · 缺答 {len(missing)}")
    print(f"正确 {correct} · 得分率(缺答按错) {correct/total*100:.1f}%")
    if missing:
        print(f"缺答题号: {missing}")
    if wrong:
        print("错题 (题号, 模型, 标准):")
        for n, a, k in wrong:
            print(f"  {n}: {a} ≠ {k}")
    print("=" * 64)

    # 也存评分结果
    (OUT / "score.json").write_text(
        json.dumps({
            "total": total, "answered": len(answers), "missing": missing,
            "correct": correct, "pct": round(correct / total * 100, 1),
            "wrong": [{"q": n, "model": a, "key": k} for n, a, k in wrong],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

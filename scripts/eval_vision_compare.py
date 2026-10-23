#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek vs Gemini 并排评分：同一套 2026 广东行测真题、同一份标准答案、同图原生视觉。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_deepseek_vision_2026 import extract_answer_key, APDF

DS = Path("/tmp/ds_vision_eval")
GM = Path("/tmp/gemini_vision_eval")


def score(answers: dict[int, str], key: list[str]):
    total = len(key)
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
    return {
        "total": total, "answered": len(answers), "missing": missing,
        "correct": correct, "pct": round(correct / total * 100, 1),
        "answered_pct": round(correct / (len(answers) or 1) * 100, 1),
        "wrong": wrong,
    }


def main() -> int:
    key = extract_answer_key(APDF)
    ds = {int(k): v for k, v in json.loads((DS / "answers.json").read_text(encoding="utf-8")).items()}
    gm = {int(k): v for k, v in json.loads((GM / "answers.json").read_text(encoding="utf-8")).items()}

    r_ds = score(ds, key)
    r_gm = score(gm, key)

    print("=" * 70)
    print("2026 广东行测 · DeepSeek vs Gemini 原生视觉 · 并排评分")
    print("=" * 70)
    print(f"{'指标':<16}{'DeepSeek':<12}{'Gemini 3.8':<12}")
    print("-" * 70)
    print(f"{'总题数':<16}{r_ds['total']:<12}{r_gm['total']:<12}")
    print(f"{'已作答':<16}{r_ds['answered']:<12}{r_gm['answered']:<12}")
    print(f"{'缺答':<16}{len(r_ds['missing']):<12}{len(r_gm['missing']):<12}")
    print(f"{'正确':<16}{r_ds['correct']:<12}{r_gm['correct']:<12}")
    print(f"{'得分率(缺答按错)':<14}{r_ds['pct']:<12}{r_gm['pct']:<12}")
    print(f"{'已答正确率':<16}{r_ds['answered_pct']:<12}{r_gm['answered_pct']:<12}")

    if r_ds["missing"] or r_gm["missing"]:
        print("-" * 70)
        print(f"DeepSeek 缺答: {r_ds['missing']}")
        print(f"Gemini   缺答: {r_gm['missing']}")

    # 逐题对比表
    print("-" * 70)
    print("逐题对比（D=DeepSeek, G=Gemini, ·=对, ✗=错, 空=未答）")
    print(f"{'题':>4} {'标准':>6} {'DeepSeek':>9} {'Gemini':>8}")
    print("-" * 70)
    for n in range(1, r_ds["total"] + 1):
        k = key[n - 1]
        a_ds = ds.get(n, "-")
        a_gm = gm.get(n, "-")
        mark_ds = "·" if a_ds != "-" and ((a_ds == k) or (set(a_ds) == set(k) and len(a_ds) == len(k))) else ("✗" if a_ds != "-" else "空")
        mark_gm = "·" if a_gm != "-" and ((a_gm == k) or (set(a_gm) == set(k) and len(a_gm) == len(k))) else ("✗" if a_gm != "-" else "空")
        diff = "" if mark_ds == mark_gm else ("  ← 差异" if (mark_ds != "·" or mark_gm != "·") else "")
        print(f"{n:>4} {k:>6} {a_ds:>7}{mark_ds:>2} {a_gm:>6}{mark_gm:>2}{diff}")

    # 差异统计
    both_correct = sum(1 for n in range(1, 91) if
                       (ds.get(n, "-") != "-" and ((ds.get(n) == key[n-1]) or (set(ds.get(n)) == set(key[n-1]) and len(ds.get(n)) == len(key[n-1]))))
                       and (gm.get(n, "-") != "-" and ((gm.get(n) == key[n-1]) or (set(gm.get(n)) == set(key[n-1]) and len(gm.get(n)) == len(key[n-1])))))
    print("-" * 70)
    print(f"两模型都答对的题数: {both_correct}/90")
    print("=" * 70)

    # 存结果
    (Path("/tmp/ds_vision_eval") / "compare.json").write_text(
        json.dumps({
            "deepseek": {k: r_ds[k] for k in ("answered", "missing", "correct", "pct", "answered_pct")},
            "gemini": {k: r_gm[k] for k in ("answered", "missing", "correct", "pct", "answered_pct")},
            "wrong_ds": r_ds["wrong"], "wrong_gm": r_gm["wrong"],
            "both_correct": both_correct,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

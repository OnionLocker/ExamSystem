#!/usr/bin/env python3
"""从答案版真题 PDF 抽正确答案，合并进 data/zhenti/*.json。

答案版 PDF 的文字层**块顺序**是乱的（fitz 按内部对象序返回），但**坐标**是对的。
按 (页, y) 排序后，「正确答案：X」块的出现顺序 == 题号顺序，第 k 个就是第 k 题。
不靠题号块定位——很多页的题号块根本不存在，那样只有 60% 覆盖。

用法: python3 scripts/merge_answers.py [--check]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
ANS_DIRS = [ROOT / "data" / "uploads" / "真题" / "省考答案",
            ROOT / "data" / "uploads" / "真题" / "国考答案"]
ZHENTI = ROOT / "data" / "zhenti"

RE_ANS = re.compile(r"正确答案[：:]\s*([A-D](?:\s+[A-D])*)")


def extract(pdf: Path) -> list[str]:
    """→ 按题序排列的答案列表，第 k 项对应第 k+1 题。'D' 或 'BD'（多选）。"""
    doc = fitz.open(pdf)
    items = []
    try:
        for pno in range(len(doc)):
            for b in doc[pno].get_text("blocks"):
                if b[1] > 780:  # 页脚
                    continue
                m = RE_ANS.search(b[4])
                if m:
                    items.append((pno, b[1], m.group(1).replace(" ", "")))
    finally:
        doc.close()
    items.sort(key=lambda t: (t[0], t[1]))
    return [a for _, _, a in items]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告，不写回")
    args = ap.parse_args()

    # 同一份卷子可能有 "(1)" 重复上传，取答案多的
    best: dict[str, tuple[Path, list[str]]] = {}
    for d in ANS_DIRS:
        for pdf in sorted(d.glob("*.pdf")):
            stem = re.sub(r"\(\d+\)$", "", pdf.stem).strip()
            ans = extract(pdf)
            if stem not in best or len(ans) > len(best[stem][1]):
                best[stem] = (pdf, ans)

    total = 0
    for stem, (pdf, ans) in sorted(best.items()):
        tgt = ZHENTI / f"{stem}.json"
        if not tgt.exists():
            print(f"[无对应题库] {stem}  (抽到 {len(ans)} 个答案)")
            continue
        data = json.loads(tgt.read_text(encoding="utf-8"))
        # 解析阶段的 orphan（number 为 null 的碎片）会撑大题数，剔掉再对齐。
        # 答案数是标准题量的权威值：粉笔答案页每题一块，不会多也不会少。
        orphans = [q for q in data["questions"] if not isinstance(q.get("number"), int)]
        qs = [q for q in data["questions"] if isinstance(q.get("number"), int)]
        qs.sort(key=lambda q: q["number"])
        numbers = [q["number"] for q in qs]
        aligned = numbers == list(range(1, len(qs) + 1)) and len(ans) == len(qs)
        if not aligned:
            print(f"[跳过·对不齐] {stem[:44]:44s} 题{len(qs)} 答案{len(ans)} "
                  f"连续={numbers == list(range(1, len(qs)+1))} orphan{len(orphans)}")
            continue
        for q, a in zip(qs, ans):
            q["correct_answer"] = a
        multi = sum(1 for a in ans if len(a) > 1)
        data["questions"] = qs + orphans
        data["question_count"] = len(qs)
        data["answer_source"] = str(pdf.relative_to(ROOT))
        data["answer_coverage"] = f"{len(ans)}/{len(qs)}"
        if not args.check:
            tgt.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{'[check]' if args.check else '[merge]'} {stem[:44]:44s} "
              f"{len(ans)}/{len(qs)} 全覆盖  多选{multi}  剔除orphan{len(orphans)}")
        total += len(ans)

    print(f"\n共合并 {total} 个答案")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

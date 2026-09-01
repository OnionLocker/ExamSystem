#!/usr/bin/env python3
"""把 data/zhenti/*.json 聚合成考点体系报告，写进 hermes 的 skill references。

年份越新权重越高（省考 2026=8, 2025=6, 2024=5, 2023=3, 2022=2, 2021=1, 2020=1；
国考统一 ×0.35，只作参考）。加权后的题型频次决定"倾向于怎么考"。
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

from hermes_skills import coach_references

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "zhenti"
OUT = coach_references() / "zhenti-kaodian-map.md"

YEAR_W = {2026: 8, 2025: 6, 2024: 5, 2023: 3, 2022: 2, 2021: 1, 2020: 1}
GUOKAO_FACTOR = 0.35
MODULE_ORDER = ["政治理论", "常识判断", "言语理解与表达", "数量关系",
                "判断推理", "科学推理", "资料分析"]


def load():
    papers = []
    for f in sorted(SRC.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d["weight"] = YEAR_W.get(d["year"], 1) * (GUOKAO_FACTOR if d["exam"] == "国考" else 1.0)
        # 政治理论是 2025 年度才独立的模块。老卷里的政治题属于常识，
        # 标注模型会按现代分类把它们拆出去，这里归位，否则逐年题量表读不出真实断点。
        if d["year"] <= 2024:
            for q in d["questions"]:
                if q.get("module") == "政治理论":
                    q["module"] = "常识判断"
        papers.append(d)
    return papers


def main() -> int:
    papers = load()
    sheng = [p for p in papers if p["exam"] == "省考"]
    guo = [p for p in papers if p["exam"] == "国考"]

    L = []
    W = L.append
    W("---")
    W("title: 广东省考真题考点地图（由真题 PDF 结构化聚合生成）")
    W("generated_from: data/zhenti/*.json  via scripts/parse_zhenti.py + scripts/build_kaodian_map.py")
    W(f"papers_省考: {len(sheng)}  papers_国考: {len(guo)}")
    W("weighting: 省考年份权重 2026=8 2025=6 2024=5 2023=3 2022=2 2021=1 2020=1；国考整体 ×0.35 仅作参考")
    W("caveat: 这批真题 PDF 为粉笔网友回忆版且**不含答案与解析**。本文件只反映「考什么、怎么问、题型配比」，不含正确项与陷阱设置。")
    W("---")
    W("")
    W("# 广东省考真题考点地图")
    W("")
    W("> 用途：hermes 出题时对照本文件挑考点与题型配比，让模拟题贴近真实考察方式。")
    W("> 权重高的题型 = 近年高频 = 优先出。")
    W("")

    # 逐年模块题量
    W("## 1. 逐年模块题量（真题实测，非机构估算）")
    W("")
    W("| 试卷 | 总题 | " + " | ".join(MODULE_ORDER) + " |")
    W("|---|---|" + "---|" * len(MODULE_ORDER))
    for p in sorted(sheng, key=lambda x: (-x["year"], x["paper"])):
        c = collections.Counter(q["module"] for q in p["questions"])
        row = " | ".join(str(c.get(m, 0)) for m in MODULE_ORDER)
        W(f"| {p['year']} {p['paper']} | {p['question_count']} | {row} |")
    W("")
    W("国考（参考用，配比与广东不同，勿照搬题量）：")
    W("")
    W("| 试卷 | 总题 | " + " | ".join(MODULE_ORDER) + " |")
    W("|---|---|" + "---|" * len(MODULE_ORDER))
    for p in sorted(guo, key=lambda x: (-x["year"], x["paper"])):
        c = collections.Counter(q["module"] for q in p["questions"])
        W(f"| {p['year']} {p['paper']} | {p['question_count']} | " +
          " | ".join(str(c.get(m, 0)) for m in MODULE_ORDER) + " |")
    W("")

    # 加权题型频次
    W("## 2. 题型加权频次（出题优先级）")
    W("")
    W("`权重分` = Σ(该题型题数 × 试卷权重)。分数高 = 近年考得多 = hermes 出题该多出。")
    W("")
    for mod in MODULE_ORDER:
        sub_w: dict[str, float] = collections.defaultdict(float)
        sub_n: dict[str, int] = collections.defaultdict(int)
        sub_recent: dict[str, set] = collections.defaultdict(set)
        for p in papers:
            for q in p["questions"]:
                if q.get("module") != mod:
                    continue
                s = q.get("subtype") or "未标注"
                sub_w[s] += p["weight"]
                sub_n[s] += 1
                if p["exam"] == "省考":
                    sub_recent[s].add(p["year"])
        if not sub_w:
            continue
        W(f"### {mod}")
        W("")
        W("| 题型 | 权重分 | 真题总数 | 省考出现年份 |")
        W("|---|---|---|---|")
        for s, w in sorted(sub_w.items(), key=lambda kv: -kv[1]):
            years = ",".join(str(y) for y in sorted(sub_recent[s], reverse=True)) or "仅国考"
            W(f"| {s} | {w:.1f} | {sub_n[s]} | {years} |")
        W("")

    # 考点标签
    W("## 3. 高频考点标签")
    W("")
    W("从真题逐题抽取的 knowledge_points，按加权频次排序。这是出题时的**选点池**。")
    W("")
    for mod in MODULE_ORDER:
        kp_w: dict[str, float] = collections.defaultdict(float)
        for p in papers:
            for q in p["questions"]:
                if q.get("module") != mod:
                    continue
                for kp in q.get("knowledge_points") or []:
                    kp_w[str(kp).strip()] += p["weight"]
        if not kp_w:
            continue
        top = sorted(kp_w.items(), key=lambda kv: -kv[1])[:40]
        W(f"### {mod}")
        W("")
        for kp, w in top:
            W(f"- {kp} `{w:.1f}`")
        W("")

    # 带图题统计
    W("## 4. 带图题分布（出题时需预留图位）")
    W("")
    W("| 模块 | 带图题数 | 占该模块比例 |")
    W("|---|---|---|")
    for mod in MODULE_ORDER:
        qs = [q for p in sheng for q in p["questions"] if q.get("module") == mod]
        if not qs:
            continue
        fig = sum(1 for q in qs if q.get("has_figure"))
        W(f"| {mod} | {fig} | {fig/len(qs)*100:.0f}% |")
    W("")
    W("带图题目前**不出**，出题时跳过或改造成纯文字变体。图形推理与科学推理的电路/受力图是主要带图区。")
    W("")

    W("## 5. 出题参照规则（hermes 直接照做）")
    W("")
    W("1. 模块配比按 §1 最近一年（2026 省考）：政治10 / 常识5 / 言语15 / 数量15 / 判断20 / 科推5 / 资料20。")
    W("2. 题型比例按 §2 权重分分配，不要平均分配。")
    W("3. 考点从 §3 的池子里选，优先权重高的。同一考点两周内不重复出。")
    W("4. 命题口吻、设问句式照抄真题：如逻辑判断固定用「以下选项如果为真，最能……的是（    ）。」")
    W("5. 带图题型（§4）暂不出，或改造成纯文字描述版。")
    W("6. 出题后必须走既有的双重校验闸门（见 quiz-pipeline skill），验证通过才入库。")
    W("")
    W("原始结构化真题在项目的 `data/zhenti/*.json`，需要看具体某题的真实问法时直接查那里。")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"written -> {OUT}")
    print(f"省考 {len(sheng)} 份 / 国考 {len(guo)} 份 / 总题 {sum(p['question_count'] for p in papers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

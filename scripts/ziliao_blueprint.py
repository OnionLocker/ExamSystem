#!/usr/bin/env python3
"""资料分析整卷蓝图调度器：不调模型，按规则一次锁定 4 篇材料形态、题材与 20 个槽位。

题型沿用 ziliao_tracks.gd_rotating_paper 的真题权重与材料形态约束，本模块在其上统一做整卷约束：
- 问法（题型 + 细分考法 + 选项格式）同一套不重复；
- 区间、方向等非精确选项按配额分配，并分散到不同材料；
- 高频经典题型与典型考法保底，防止近期降权把它们压没；
- 轮转只参考已入库的卷子，失败未入库的不算；
- 预分配 20 题答案字母；每个槽位写明分配理由。
排不出来时按固定顺序放宽，放宽项写进蓝图。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kaofa_variants as kv
from normalize_ai_batch import planned_ziliao_groups
from ziliao_tracks import (KIND_BASE, KIND_DELTA, KIND_LABELS, KIND_RATE, KIND_SHARE, KIND_SPECS,
                           _recency_factor, _weighted_pick, apply_difficulty_overrides, gd_rotating_paper,
                           validate_gd_quota)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "exam.db"
PAPER_DIR = ROOT / "data" / "manual-ziliao-agent-paper"

ROTATION_PAPERS = 3
THEME_PAPERS = 6
# 按 2024–2026 广东省考：区间式每套 1–2 道，升降+幅度 0–1 道，同篇至多 1 道。
INTERVAL_COUNTS = {1: 0.3, 2: 0.7}
DIRECTION_COUNTS = {0: 0.6, 1: 0.4}
FORM_CAP = 2
FORM_LABELS = {"interval": "区间式", "direction": "升降式", "order": "排序", "count": "个数", "entity": "选主体"}
CLASSIC_KINDS = (KIND_SHARE, KIND_RATE, KIND_DELTA, KIND_BASE)
TYPICAL_FLOOR = 4
ATTEMPTS_PER_LEVEL = 120
# 答案是“选出某个主体/年份/个数/排列”的考法，配区间或升降选项会别扭，只出精确选项。
ENTITY_ANSWER = re.compile(r"最多|最大|最高|最低|最少|最快|最慢|排序|的个数|有几个|几项|哪|谁|升降判断|上升还是下降|主体或年份|是否|首次")

# 放宽顺序：先放宽非精确分散，再放宽典型保底，最后放宽经典题型保底；
# 问法不重复、同一选项形式至多 FORM_CAP 道始终不放宽。
LEVELS = (
    {"per_material": 1, "typical": TYPICAL_FLOOR, "classic": CLASSIC_KINDS},
    {"per_material": 2, "typical": TYPICAL_FLOOR, "classic": CLASSIC_KINDS},
    {"per_material": 2, "typical": 2, "classic": CLASSIC_KINDS},
    {"per_material": 2, "typical": 2, "classic": (KIND_SHARE, KIND_RATE, KIND_DELTA)},
)
RELAX_NOTES = ("", "非精确选项允许同篇 2 道", "典型考法保底降为 2 道", "经典题型保底不含基期量")


BLUEPRINT_ONLY = ("kind_reason", "variant_reason", "format_reason", "kaofa_variant_typical", "answer_key")


def plan_slot(slot: dict) -> dict:
    """写进计划文件（会进出题提示词）的槽位：去掉只供展示与校验的字段。"""
    return {k: v for k, v in slot.items() if k not in BLUEPRINT_ONLY}


def pick_themes(theme_pool, recent_themes: set, rng: random.Random) -> list[str]:
    fresh = [t for t in theme_pool if t not in recent_themes]
    return rng.sample(fresh if len(fresh) >= 4 else list(theme_pool), 4)


def plan_dirs(output_dir: Path) -> list[Path]:
    """有计划文件的批次目录，新的在前。"""
    plans = sorted(output_dir.glob("*/M0[1-4]-plan.json"), key=lambda p: p.stat().st_mtime)
    dirs: list[Path] = []
    for plan in reversed(plans):
        if plan.parent not in dirs:
            dirs.append(plan.parent)
    return dirs


def imported_dirs(output_dir: Path, db: Path, limit: int) -> list[Path]:
    """已入库（学员能做到）的卷子，新的在前。"""
    dirs = plan_dirs(output_dir)
    if not dirs or not Path(db).is_file():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    try:
        names = [d.name for d in dirs]
        found = {row[0] for row in conn.execute(
            f"SELECT DISTINCT batch_id FROM questions WHERE batch_id IN ({','.join('?' * len(names))})", names)}
    finally:
        conn.close()
    return [d for d in dirs if d.name in found][:limit]


def recent_rotation(dirs: list[Path]) -> tuple[list[set], list[set], list[set], set]:
    from ziliao_tracks import judge_mix_id
    kinds, types, mixes, themes = [], [], [], set()
    for index, d in enumerate(dirs):
        loaded = [json.loads(p.read_text()) for p in sorted(d.glob("M0[1-4]-plan.json"))]
        themes.update(p.get("theme_key") for p in loaded if p.get("theme_key"))
        if index >= ROTATION_PAPERS:
            continue
        kinds.append({s.get("kind") for p in loaded for s in p.get("slots") or [] if s.get("kind")})
        types.append({p.get("material_type") or {"chart": "years", "table": "table", "text": "text"}.get(p.get("format"))
                      for p in loaded})
        mixes.append({judge_mix_id(s) for p in loaded for s in p.get("slots") or [] if s.get("kind") == "judge"} - {None})
    return kinds, types, mixes, themes


def wording(slot: dict) -> tuple:
    if slot.get("kind") == "judge":
        return ("judge", slot.get("judge_stem"))
    return (slot.get("kind"), slot.get("kaofa_variant") or slot.get("brief"), slot.get("option_format") or "exact")


def entity_answer(slot: dict) -> bool:
    brief = str(slot.get("brief") or "")
    ask = re.split(r"真题设问参考|必须按此变式", brief.split("本题考法变式：", 1)[1])[0] if "本题考法变式：" in brief else ""
    return bool(ENTITY_ANSWER.search(str(slot.get("kaofa_variant_name") or "") + ask))


def non_exact_ok(slot: dict) -> bool:
    spec = KIND_SPECS.get(str(slot.get("kind")))
    return bool(spec and len(spec["formats"]) > 1 and not slot.get("quick") and not entity_answer(slot))


def answer_form(slot: dict) -> str | None:
    """选项的表现形式；None 为普通数值选项（不限量），综合分析、图表匹配、文字理解另计。"""
    kind, name = slot.get("kind"), str(slot.get("kaofa_variant_name") or "")
    if kind in ("judge", "chart_match", "text_reading"):
        return None
    if slot.get("option_format") in ("interval", "direction"):
        return slot["option_format"]
    if kind == "sort" or "排序" in name:
        return "order"
    if kind == "count" or re.search(r"的个数|有几个|几项", name):
        return "count"
    if slot.get("quick") or entity_answer(slot):
        return "entity"
    return None


def assign_formats(slots: list[dict], rng: random.Random, per_material: int) -> None:
    for slot in slots:
        if slot.get("kind") in KIND_SPECS:
            slot["option_format"] = "exact"
            slot["format_reason"] = "精确值"
    taken = Counter()
    plan = [("direction", _weighted_pick(rng, list(DIRECTION_COUNTS), list(DIRECTION_COUNTS.values()))),
            ("interval", _weighted_pick(rng, list(INTERVAL_COUNTS), list(INTERVAL_COUNTS.values())))]
    for fmt, want in plan:
        for _ in range(want):
            pool = [i for i, s in enumerate(slots) if s.get("option_format") == "exact" and non_exact_ok(s)
                    and fmt in KIND_SPECS[s["kind"]]["formats"] and taken[i // 5] < per_material]
            if not pool:
                break
            index = rng.choice(pool)
            slots[index]["option_format"] = fmt
            taken[index // 5] += 1
    total = sum(taken.values())
    for slot in slots:
        if slot.get("option_format") in ("interval", "direction"):
            slot["format_reason"] = f"{FORM_LABELS[slot['option_format']]}配额（本套非精确 {total} 道，同篇至多 {per_material} 道）"


def ensure_typical(slots: list[dict], bases: list[str], floor: int, catalog: dict, rng: random.Random) -> None:
    def typical_of(slot):
        return next((v for v in kv.variants_for(slot.get("tag"), catalog)
                     if v.get("typical") and v.get("kind") == slot.get("kind") and kv._fits_material(v, slot)), None)

    used = {(s.get("tag"), s.get("kaofa_variant")) for s in slots if s.get("kaofa_variant")}
    have = sum(1 for s in slots if typical_of(s) and s.get("kaofa_variant") == typical_of(s)["id"])
    candidates = [i for i, s in enumerate(slots) if s.get("kaofa_variant") and typical_of(s)
                  and s["kaofa_variant"] != typical_of(s)["id"] and (s.get("tag"), typical_of(s)["id"]) not in used]
    rng.shuffle(candidates)
    for index in candidates[:max(0, floor - have)]:
        slot, variant = slots[index], typical_of(slots[index])
        if (slot.get("tag"), variant["id"]) in used:
            continue
        used.add((slot.get("tag"), variant["id"]))
        slot.update({"kaofa_variant": variant["id"], "kaofa_variant_name": variant["name"],
                     "brief": (bases[index] + "；" if bases[index] else "") + kv.variant_brief(variant),
                     "variant_reason": "典型考法保底"})
        slot.pop("kaofa_need", None)
        if variant.get("need"):
            slot["kaofa_need"] = variant["need"]


RATIO_CAP = 2


def asks_ratio(slot: dict) -> bool:
    return slot.get("kind") == "multiple" or "倍" in str(slot.get("kaofa_variant_name") or "")


def violations(slots: list[dict], level: dict) -> list[str]:
    problems = []
    keys = Counter(wording(s) for s in slots)
    if any(c > 1 for c in keys.values()):
        problems.append("问法重复")
    kinds = Counter(s.get("kind") for s in slots)
    problems += [f"缺经典题型 {KIND_LABELS.get(k, k)}" for k in level["classic"] if not kinds[k]]
    non_exact = [i for i, s in enumerate(slots) if s.get("option_format") not in (None, "exact")]
    if not any(s.get("option_format") == "interval" for s in slots):
        problems.append("缺区间式选项")
    if max(Counter(i // 5 for i in non_exact).values(), default=0) > level["per_material"]:
        problems.append("非精确选项同篇过多")
    forms = Counter(f for f in map(answer_form, slots) if f)
    problems += [f"{FORM_LABELS[f]} {n} 道" for f, n in forms.items() if n > FORM_CAP]
    for m in range(4):
        kinds_here = {s.get("kind") for s in slots[m * 5:m * 5 + 5]}
        if {"average", "average_diff"} <= kinds_here:
            problems.append("同篇同时有现期平均数与平均数差值，后者会泄露前者答案")
    ratio = [i for i, s in enumerate(slots) if asks_ratio(s)]
    if len(ratio) > RATIO_CAP or max(Counter(i // 5 for i in ratio).values(), default=0) > 1:
        problems.append("“是……的多少倍”问法过多")
    typical = sum(1 for s in slots if s.get("variant_reason") == "典型考法保底" or s.get("kaofa_variant_typical"))
    if typical < level["typical"]:
        problems.append(f"典型考法 {typical} 道")
    try:
        validate_gd_quota(slots, count=20)
    except ValueError as exc:
        problems.append(str(exc))
    return problems


def mark_reasons(slots: list[dict], recent_kinds: list, kind_boost: dict, variant_boost: dict,
                 used: Counter, catalog: dict) -> None:
    for slot in slots:
        kind = slot.get("kind")
        if kind in KIND_SPECS:
            factor, boost = _recency_factor(kind, recent_kinds), kind_boost.get(kind, 1.0)
            slot["kind_reason"] = (f"真题权重{KIND_SPECS[kind]['weight']}×近期系数{factor:.2f}"
                                   + (f"×表现系数{boost:.2f}" if boost != 1.0 else ""))
        variant_id = slot.get("kaofa_variant")
        if not variant_id:
            continue
        variant = next((v for v in kv.variants_for(slot.get("tag"), catalog) if v["id"] == variant_id), {})
        slot["kaofa_variant_typical"] = bool(variant.get("typical"))
        if "variant_reason" not in slot:
            key = (slot.get("tag"), variant_id)
            parts = [f"真题权重{variant.get('weight', 1)}"]
            if variant_boost.get(key, 1.0) > 1:
                parts.append(f"错得多×{variant_boost[key]:.2f}")
            parts.append(f"近期练过{used.get(key, 0):g}次")
            slot["variant_reason"] = "，".join(parts)


def build_blueprint(*, seed: str, tier: str = "mid", overrides: dict | None = None, adaptive: dict | None = None,
                    output_dir: Path = PAPER_DIR, db: Path = DB, catalog: dict | None = None,
                    ledger: Path | None = None, today: dt.date | None = None) -> dict:
    started = time.monotonic()
    adaptive = adaptive or {"kind_boost": {}, "variant_boost": {}, "mix_boost": {}}
    catalog = kv.load_catalog() if catalog is None else catalog
    used = kv.usage(ledger, today)
    rotation = imported_dirs(output_dir, db, max(ROTATION_PAPERS, THEME_PAPERS))
    recent_kinds, recent_types, recent_mixes, recent_themes = recent_rotation(rotation)
    for level_index, level in enumerate(LEVELS):
        for attempt in range(ATTEMPTS_PER_LEVEL):
            key = f"{seed}:{level_index}:{attempt}"
            rng = random.Random(key)
            types, slots = gd_rotating_paper(tier, rng, recent_kinds, recent_types, adaptive.get("kind_boost"),
                                             recent_mixes, adaptive.get("mix_boost"))
            slots = apply_difficulty_overrides(slots, overrides or {})
            bases = [str(s.get("brief") or "").strip() for s in slots]
            slots = kv.assign_ziliao_variants(slots, seed=key, catalog=catalog, ledger=ledger, today=today,
                                              boost=adaptive.get("variant_boost"))
            ensure_typical(slots, bases, level["typical"], catalog, rng)
            mark_reasons(slots, recent_kinds, adaptive.get("kind_boost") or {}, adaptive.get("variant_boost") or {},
                         used, catalog)
            assign_formats(slots, rng, level["per_material"])
            if violations(slots, level):
                continue
            for group_index, letters in enumerate(planned_ziliao_groups(rng)):
                for offset, letter in enumerate(letters):
                    slots[group_index * 5 + offset]["answer_key"] = letter
            return {
                "version": 1, "seed": seed, "tier": tier, "material_types": types, "slots": slots,
                "relaxed": [note for note in RELAX_NOTES[1:level_index + 1]],
                "rotation_papers": [d.name for d in rotation[:ROTATION_PAPERS]],
                "recent_themes": sorted(recent_themes),
                "seconds": round(time.monotonic() - started, 3),
            }
    raise RuntimeError("蓝图在全部放宽后仍排不出：问法不重复与题型配额无法同时满足")


def format_blueprint(blueprint: dict, themes: list[str] | None = None) -> str:
    fmt = {"exact": "精确", "interval": "区间", "direction": "升降"}
    lines = [f"资料分析整卷蓝图（{blueprint['tier']}，{blueprint['seconds']}s）"
             + (f"；已放宽：{'、'.join(blueprint['relaxed'])}" if blueprint["relaxed"] else "")]
    for m in range(4):
        theme = f" · {themes[m]}" if themes else ""
        lines.append(f"M0{m + 1} {blueprint['material_types'][m]}{theme}")
        for q in range(5):
            s = blueprint["slots"][m * 5 + q]
            if s.get("kind") == "judge":
                desc = f"综合分析｜{s.get('judge_stem')}｜{s.get('judge_mix_id')}"
            else:
                desc = (f"{s.get('kind_label') or KIND_LABELS.get(s.get('kind'), s.get('kind'))}"
                        f"｜{s.get('kaofa_variant_name') or '—'}｜{fmt.get(s.get('option_format'), '精确')}")
            lines.append(f"  Q{q + 1} [{s.get('answer_key')}] {desc}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default=dt.datetime.now().strftime("%Y%m%d%H%M%S"))
    parser.add_argument("--difficulty", default="mid")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    from ziliao_performance import adaptive_plan
    blueprint = build_blueprint(seed=args.seed, tier=args.difficulty, adaptive=adaptive_plan(DB))
    print(json.dumps(blueprint, ensure_ascii=False, indent=2) if args.json else format_blueprint(blueprint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

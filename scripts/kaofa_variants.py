#!/usr/bin/env python3
"""考法变式轮转：特训时给每题分配一个考法变式，入库后记账，下次优先补近期少练的变式。

变式清单在 hermes-skills/quiz-pipeline/references/kaofa-variants.json，按末级知识点 tag 索引。
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "hermes-skills" / "quiz-pipeline" / "references" / "kaofa-variants.json"
LEDGER = ROOT / "data" / "kaofa-variant-ledger.jsonl"
MODULES = {"数量关系", "言语理解与表达", "判断推理"}
RECENT_DAYS = 30
HISTORY_DAYS = 120
TYPICAL_HANDICAP = 2.0


def load_catalog(path: Path = CATALOG) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def variants_for(tag: str, catalog: dict) -> list[dict]:
    entry = catalog.get(str(tag)) or {}
    return [v for v in entry.get("variants") or [] if isinstance(v, dict) and v.get("id") and v.get("ask")]


def usage(ledger: Path = LEDGER, today: dt.date | None = None) -> Counter:
    """近 30 天每次记 1，30–120 天记 0.5。"""
    today = today or dt.date.today()
    used: Counter = Counter()
    if not ledger.is_file():
        return used
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            age = (today - dt.date.fromisoformat(row["date"])).days
        except (ValueError, KeyError, TypeError):
            continue
        if age <= RECENT_DAYS:
            used[(row["tag"], row["variant"])] += 1
        elif age <= HISTORY_DAYS:
            used[(row["tag"], row["variant"])] += 0.5
    return used


def pick(tag: str, variants: list[dict], used: Counter, taken: Counter, rng: random.Random) -> dict:
    def score(v):
        load = used[(tag, v["id"])] + (TYPICAL_HANDICAP if v.get("typical") else 0)
        return (taken[v["id"]], load / max(1, int(v.get("weight") or 1)), rng.random())
    return min(variants, key=score)


def variant_brief(variant: dict) -> str:
    text = f"本题考法变式：{variant['name']}。{variant['ask']}"
    if variant.get("example"):
        text += f"真题设问参考（只借鉴设问结构，不照抄情境和数字）：{variant['example']}"
    return text + "必须按此变式命题，不得退回本考点最常见的默认考法。"


LOCKING_BRIEF = re.compile(r"同构|只(?:练|出|考|要)|仅(?:练|出|考)|全部(?:按|出|是|用)|都(?:按|出|用|是)|固定(?:考法|结构|模型)|同一(?:考法|模型|结构)|不要换")


def assign_variants(module: str, slots: list[dict], *, seed: str = "", catalog: dict | None = None,
                    ledger: Path = LEDGER, today: dt.date | None = None) -> list[dict]:
    """把有变式清单的槽位拆成每题一个，并写入变式要求。
    brief 锁定考法（同构、只练某种）时保持原样；其余倾向性要求与变式叠加。"""
    if module not in MODULES:
        return slots
    catalog = load_catalog() if catalog is None else catalog
    used = usage(ledger, today)
    rng = random.Random(seed or None)
    taken_by_tag: dict[str, Counter] = {}
    result = []
    for slot in slots:
        variants = variants_for(slot["tag"], catalog)
        user_brief = str(slot.get("brief") or "").strip()
        if not variants or LOCKING_BRIEF.search(user_brief):
            result.append(slot)
            continue
        taken = taken_by_tag.setdefault(str(slot["tag"]), Counter())
        for _ in range(int(slot["count"])):
            variant = pick(str(slot["tag"]), variants, used, taken, rng)
            taken[variant["id"]] += 1
            brief = variant_brief(variant) + (f"另需满足用户要求：{user_brief}" if user_brief else "")
            result.append({**slot, "count": 1, "kaofa_variant": variant["id"],
                           "kaofa_variant_name": variant["name"], "brief": brief})
    return result


def record_variants(batch_id: str, slots: list[dict], ledger: Path = LEDGER, today: dt.date | None = None) -> int:
    rows = [{"date": (today or dt.date.today()).isoformat(), "batch_id": batch_id, "tag": s["tag"],
             "variant": s["kaofa_variant"]} for s in slots if s.get("kaofa_variant")
            for _ in range(int(s.get("count") or 1))]
    if rows:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def leaf_usage(db: Path = ROOT / "data" / "exam.db", days: int = HISTORY_DAYS) -> Counter:
    """近 120 天题库里各知识点（主标签）的出题量，父知识点出题时优先分给练得少的子考点。"""
    import sqlite3
    used: Counter = Counter()
    if not Path(db).is_file():
        return used
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    try:
        for (tags,) in conn.execute("SELECT tags FROM questions WHERE batch_id IS NOT NULL AND created_at >= ?", (since,)):
            try:
                primary = (json.loads(tags or "[]") or [""])[0]
            except (TypeError, ValueError):
                continue
            if primary:
                used[primary] += 1
    finally:
        conn.close()
    return used


def coverage(catalog: dict | None = None, ledger: Path = LEDGER) -> dict:
    """每个知识点各变式累计练过几次，供 Hermes 排计划时查看。"""
    catalog = load_catalog() if catalog is None else catalog
    used = usage(ledger)
    return {tag: {v["id"]: used[(tag, v["id"])] for v in variants_for(tag, catalog)} for tag in catalog}


if __name__ == "__main__":
    import sys
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    cov = coverage()
    print(json.dumps({tag: cov.get(tag)} if tag else cov, ensure_ascii=False, indent=2))

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


def load_catalog(path: Path | None = None) -> dict:
    path = path or CATALOG
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def variants_for(tag: str, catalog: dict) -> list[dict]:
    entry = catalog.get(str(tag)) or {}
    return [v for v in entry.get("variants") or [] if isinstance(v, dict) and v.get("id") and v.get("ask")]


def usage(ledger: Path | None = None, today: dt.date | None = None) -> Counter:
    """近 30 天每次记 1，30–120 天记 0.5。"""
    today = today or dt.date.today()
    ledger = ledger or LEDGER
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


ZILIAO_SKIP_KINDS = {"judge", "chart_match"}


def assign_ziliao_variants(slots: list[dict], *, seed: str = "", targeted: bool = False, catalog: dict | None = None,
                           ledger: Path = LEDGER, today: dt.date | None = None,
                           boost: dict | None = None) -> list[dict]:
    """资料分析每题挑一个细分考法。整套卷按槽位题型（kind）与材料形态筛选，保留原有题型配额；
    专项不限题型，在该考点全部细分考法里轮转。综合判断、图表匹配、定性快判和锁定考法的槽位不动。"""
    catalog = load_catalog() if catalog is None else catalog
    used = usage(ledger, today)
    rng = random.Random(seed or None)
    taken_by_tag: dict[str, Counter] = {}
    result = []
    for slot in slots:
        slot = dict(slot)
        variants = variants_for(slot.get("tag"), catalog)
        if (not variants or slot.get("kind") in ZILIAO_SKIP_KINDS or slot.get("quick")
                or LOCKING_BRIEF.search(str(slot.get("brief") or ""))):
            result.append(slot)
            continue
        pool = [v for v in variants
                if (targeted or v.get("kind") == slot.get("kind")) and _fits_material(v, slot)]
        if not pool:
            result.append(slot)
            continue
        tag = str(slot["tag"])
        taken = taken_by_tag.setdefault(tag, Counter())
        variant = _ziliao_pick(tag, pool, used, taken, rng, boost)
        taken[variant["id"]] += 1
        brief = str(slot.get("brief") or "").strip()
        slot.update({"kaofa_variant": variant["id"], "kaofa_variant_name": variant["name"],
                     "brief": (brief + "；" if brief else "") + variant_brief(variant)})
        if variant.get("need"):
            slot["kaofa_need"] = variant["need"]
        result.append(slot)
    return result


ZILIAO_RECENT_DECAY = 0.7


def _ziliao_pick(tag: str, variants: list[dict], used: Counter, taken: Counter, rng: random.Random,
                 boost: dict | None = None) -> dict:
    """资料分析按真题权重抽取：同批先不重复，近期每练一次权重乘 0.7，常考考法仍更常出现；
    boost 为学员表现系数（错得多的细分考法 >1）。"""
    boost = boost or {}
    least = min(taken[v["id"]] for v in variants)
    pool = [v for v in variants if taken[v["id"]] == least]
    weights = [max(1, int(v.get("weight") or 1)) * ZILIAO_RECENT_DECAY ** used[(tag, v["id"])]
               * boost.get((tag, v["id"]), 1.0) for v in pool]
    point = rng.random() * sum(weights)
    for variant, weight in zip(pool, weights):
        point -= weight
        if point <= 0:
            return variant
    return pool[-1]


def _fits_material(variant: dict, slot: dict) -> bool:
    types = variant.get("types")
    if not types:
        return True
    if slot.get("material_type"):
        return slot["material_type"] in types
    if slot.get("material_format"):
        from ziliao_tracks import MATERIAL_TYPES
        return any(MATERIAL_TYPES.get(t, {}).get("format") == slot["material_format"] for t in types)
    return True


def ziliao_variant_issues(variant: dict) -> list[str]:
    from ziliao_tracks import KIND_SPECS, MATERIAL_TYPES
    issues = []
    if variant.get("kind") not in KIND_SPECS:
        issues.append(f"资料分析变式须写 kind（{'/'.join(KIND_SPECS)}）：{variant.get('id')}")
    bad = [t for t in variant.get("types") or [] if t not in MATERIAL_TYPES]
    if bad:
        issues.append(f"types 只能是 {'/'.join(MATERIAL_TYPES)}：{bad}")
    return issues


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


ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def _bigrams(text: str) -> set:
    text = re.sub(r"\s", "", text)
    return {text[i:i + 2] for i in range(len(text) - 1)}


def similar(a: str, b: str) -> float:
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def entry_issues(entry: dict) -> list[str]:
    variants = entry.get("variants") or []
    issues = []
    if len(variants) < 3:
        issues.append("每个知识点至少保留 3 个变式")
    if sum(bool(v.get("typical")) for v in variants) != 1:
        issues.append("每个知识点恰好一个 typical")
    ids = [v.get("id") for v in variants]
    if len(set(ids)) != len(ids):
        issues.append("变式 id 重复")
    for v in variants:
        if not ID_RE.fullmatch(str(v.get("id") or "")):
            issues.append(f"id 须为小写字母数字连字符、≤40 字符：{v.get('id')}")
        if not v.get("name") or len(v["name"]) > 16:
            issues.append(f"name 须为 1–16 字：{v.get('name')}")
        if not v.get("ask") or len(v["ask"]) > 120:
            issues.append(f"ask 须为 1–120 字：{v.get('id')}")
        if int(v.get("weight") or 0) not in range(1, 6):
            issues.append(f"weight 须为 1–5：{v.get('id')}")
        if len(variant_brief(v)) > 600:
            issues.append(f"变式要求超过 600 字：{v.get('id')}")
    return issues


def save_catalog(catalog: dict, path: Path | None = None) -> None:
    path = path or CATALOG
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def leaf_titles() -> dict[str, str]:
    from quiz_scope import catalog as knowledge_catalog
    return {tag: node.get("title") or tag for tag, node in knowledge_catalog().items()}


def resolve_tag(query: str, catalog: dict) -> str:
    """完整 tag 原样返回；否则按标题或 tag 片段唯一匹配（先找清单，再找知识点目录）。"""
    query = query.strip()
    if query in catalog:
        return query
    hits = [t for t, e in catalog.items() if query == e.get("title") or query in t or query in str(e.get("title"))]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        titles = leaf_titles()
        hits = [t for t, title in titles.items() if query == title or query in t or query in title]
        if len(hits) == 1:
            return hits[0]
    if not hits:
        raise SystemExit(json.dumps({"ok": False, "error": f"找不到知识点：{query}；先用 list 或 knowledge-content.mjs find 查完整 tag"}, ensure_ascii=False))
    raise SystemExit(json.dumps({"ok": False, "error": "匹配到多个知识点，请用完整 tag", "candidates": hits[:20]}, ensure_ascii=False))


def _apply_ziliao_fields(variant: dict, args) -> None:
    if getattr(args, "kind", None) is not None:
        variant["kind"] = args.kind.strip()
    if getattr(args, "types", None) is not None:
        types = [t.strip() for t in args.types.split(",") if t.strip()]
        if types:
            variant["types"] = types
        else:
            variant.pop("types", None)
    if getattr(args, "need", None) is not None:
        if args.need.strip():
            variant["need"] = args.need.strip()
        else:
            variant.pop("need", None)


def _fail(message: str, **extra):
    raise SystemExit(json.dumps({"ok": False, "error": message, **extra}, ensure_ascii=False))


def cli(argv: list[str] | None = None) -> dict:
    import argparse
    parser = argparse.ArgumentParser(description="考法变式清单：查看、新增、修改、删除")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="列出某知识点的变式及近期练习次数")
    p.add_argument("tag")
    p = sub.add_parser("add", help="新增变式（自动校验与查重）")
    p.add_argument("tag")
    p.add_argument("--name", required=True)
    p.add_argument("--ask", required=True, help="题干结构与解题动作，≤120 字")
    p.add_argument("--example", default="", help="真题出处与题干片段，如“粤2025：……”；没有就留空，不得编造")
    p.add_argument("--weight", type=int, default=2)
    p.add_argument("--id", dest="vid")
    p.add_argument("--force", action="store_true", help="与现有变式相似度高时仍然新增")
    ziliao_help = ("资料分析专用：kind 为所属题型（见 ziliao_tracks.KIND_SPECS），types 为适用材料形态（逗号分隔，留空不限），"
                   "need 为材料须提供的数据")
    for field in ("kind", "types", "need"):
        p.add_argument(f"--{field}", help=ziliao_help)
    p = sub.add_parser("edit", help="修改变式字段")
    p.add_argument("tag")
    p.add_argument("id")
    for field in ("name", "ask", "example", "kind", "types", "need"):
        p.add_argument(f"--{field}")
    p.add_argument("--weight", type=int)
    p.add_argument("--typical", action="store_true", help="设为本知识点的典型默认考法")
    p = sub.add_parser("remove", help="删除变式")
    p.add_argument("tag")
    p.add_argument("id")
    args = parser.parse_args(argv)

    catalog = load_catalog()
    tag = resolve_tag(args.tag, catalog)
    entry = catalog.get(tag)
    if args.cmd == "list":
        if not entry:
            return {"ok": True, "tag": tag, "variants": [], "note": "该知识点还没有变式清单，可用 add 新增"}
        used = usage()
        return {"ok": True, "tag": tag, "title": entry.get("title"), "variants": [
            {**v, "recent_uses": used[(tag, v["id"])]} for v in entry["variants"]]}

    if args.cmd == "add":
        if entry is None:
            if tag not in leaf_titles():
                _fail(f"知识点目录里没有 {tag}；先在知识点页登记节点")
            entry = {"title": leaf_titles()[tag], "variants": []}
        for v in entry["variants"]:
            score = max(similar(args.name, v["name"]), similar(args.ask, v["ask"]))
            if score >= 0.6 and not args.force:
                _fail("与现有变式高度相似，可能重复；确认是新考法再加 --force", similar_to=v, score=round(score, 2))
        vid = args.vid or f"custom-{len(entry['variants']) + 1}"
        while vid in {v["id"] for v in entry["variants"]}:
            vid += "-x"
        variant = {"id": vid, "name": args.name.strip(), "ask": args.ask.strip(), "example": args.example.strip(),
                   "weight": args.weight, "typical": not entry["variants"]}
        _apply_ziliao_fields(variant, args)
        candidate = {**entry, "variants": entry["variants"] + [variant]}
        issues = [i for i in entry_issues(candidate) if not (i.startswith("每个知识点至少") and len(candidate["variants"]) < 3)]
        if tag.startswith("资料分析-"):
            issues += ziliao_variant_issues(variant)
        if issues:
            _fail("校验未通过", issues=issues)
        catalog[tag] = candidate
        save_catalog(catalog)
        return {"ok": True, "tag": tag, "added": variant, "total": len(candidate["variants"])}

    if not entry:
        _fail(f"{tag} 还没有变式清单")
    target = next((v for v in entry["variants"] if v["id"] == args.id), None)
    if target is None:
        _fail(f"{tag} 没有变式 {args.id}", ids=[v["id"] for v in entry["variants"]])
    if args.cmd == "edit":
        updated = dict(target)
        for field in ("name", "ask", "example"):
            if getattr(args, field) is not None:
                updated[field] = getattr(args, field).strip()
        if args.weight is not None:
            updated["weight"] = args.weight
        _apply_ziliao_fields(updated, args)
        variants = [updated if v["id"] == args.id else dict(v) for v in entry["variants"]]
        if args.typical:
            for v in variants:
                v["typical"] = v["id"] == args.id
        candidate = {**entry, "variants": variants}
    else:
        if target.get("typical"):
            _fail("不能直接删除典型考法；先用 edit --typical 把别的变式设为典型")
        candidate = {**entry, "variants": [v for v in entry["variants"] if v["id"] != args.id]}
    issues = entry_issues(candidate)
    if tag.startswith("资料分析-"):
        issues += [i for v in candidate["variants"] for i in ziliao_variant_issues(v)]
    if issues:
        _fail("校验未通过", issues=issues)
    catalog[tag] = candidate
    save_catalog(catalog)
    return {"ok": True, "tag": tag, {"edit": "edited", "remove": "removed"}[args.cmd]: args.id,
            "total": len(candidate["variants"])}


if __name__ == "__main__":
    print(json.dumps(cli(), ensure_ascii=False, indent=2))

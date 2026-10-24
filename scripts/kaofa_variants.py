#!/usr/bin/env python3
"""考法变式轮转：特训时给每题分配一个考法变式，入库后记账，下次优先补近期少练的变式。

变式清单在 hermes-skills/quiz-pipeline/references/kaofa-variants.json，按末级知识点 tag 索引。
"""
from __future__ import annotations

import datetime as dt
import json
import os
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
# 典型（最常见默认）考法按其真题频率降权：乘一个 <1 的系数，而不是固定加罚分。
# 固定加罚分会导致高频典型考法被压到低频非典型后面（真题常考的反而少练）；乘系数则
# 既让默认考法不易霸占轮转，又保留“真题频率高就该多出”的权重排序。
TYPICAL_DISCOUNT = 0.6


def load_catalog(path: Path | None = None) -> dict:
    path = path or CATALOG
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def variants_for(tag: str, catalog: dict) -> list[dict]:
    entry = catalog.get(str(tag)) or {}
    return [v for v in entry.get("variants") or [] if isinstance(v, dict) and v.get("id") and v.get("ask")]


def ledger_path(path: Path | None = None) -> Path:
    """调用时再解析账本路径：测试与离线演练用 KAOFA_LEDGER 指到临时文件，避免污染真实账本。"""
    return Path(path) if path else Path(os.environ.get("KAOFA_LEDGER") or LEDGER)


UNANSWERED_SHARE = 0.5


def answered_questions(question_ids: list[str], db: Path | None = None) -> set[str]:
    """账本题号里有作答记录的（按题库 external_id 查）；查不到库就当全部没做。"""
    import sqlite3
    db = Path(db or os.environ.get("EXAM_DB") or ROOT / "data" / "exam.db")
    if not question_ids or not db.is_file():
        return set()
    done: set[str] = set()
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error:
        return done
    try:
        for start in range(0, len(question_ids), 500):
            chunk = question_ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            done.update(str(external) for (external,) in conn.execute(
                f"""SELECT DISTINCT q.external_id FROM practice_answers pa JOIN questions q ON q.id = pa.question_id
                     WHERE q.external_id IN ({marks})""", chunk))
    except sqlite3.Error:
        return set()
    finally:
        conn.close()
    return done


def usage(ledger: Path | None = None, today: dt.date | None = None, db: Path | None = None) -> Counter:
    """近 30 天每次记 1，30–120 天记 0.5；带题号但一次没做过的题只算一半（出了没练不算真练过）。"""
    today = today or dt.date.today()
    ledger = ledger_path(ledger)
    used: Counter = Counter()
    if not ledger.is_file():
        return used
    rows = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            age = (today - dt.date.fromisoformat(row["date"])).days
        except (ValueError, KeyError, TypeError):
            continue
        if age <= HISTORY_DAYS:
            rows.append((row, age))
    done = answered_questions([str(r["question_id"]) for r, _ in rows if r.get("question_id")], db)
    for row, age in rows:
        weight = 1 if age <= RECENT_DAYS else 0.5
        if row.get("question_id") and str(row["question_id"]) not in done:
            weight *= UNANSWERED_SHARE
        used[(row["tag"], row["variant"])] += weight
    return used


WEAK_EXTRA_SHARE = 1.4   # 表现系数达到此值的变式，同批可占两份
WEAK_FOCUS = 1.15        # kaofa_focus=weak 时入选的最低表现系数


LEVEL_POOLS = {"easy": {1}, "mid": {1, 2}, "hard": {2, 3}}
TOP_LEVEL_BONUS = 2      # hard 档里层级 3 的变式权重倍数


def level_pool(variants: list[dict], tier: str | None) -> list[dict]:
    """easy/mid/hard 按变式层级筛选；未标层级的变式各档都可用，筛空则退回全部。"""
    allowed = LEVEL_POOLS.get(str(tier or ""))
    if not allowed:
        return variants
    return [v for v in variants if v.get("level") in allowed or "level" not in v] or variants


def pick(tag: str, variants: list[dict], used: Counter, taken: Counter, rng: random.Random,
         boost: dict | None = None, tier: str | None = None) -> dict:
    """同批先铺开不重复；错得多的变式（boost 高）权重放大、同批可占两份；近期练得多的降权。"""
    boost = boost or {}

    def score(v):
        w = max(1, int(v.get("weight") or 1))
        if v.get("typical"):
            # 典型考法按真实频率降权，但保留权重排序：高频典型仍优先于低频非典型。
            w = max(1, int(round(w * TYPICAL_DISCOUNT)))
        if tier == "hard" and v.get("level") == 3:
            w *= TOP_LEVEL_BONUS
        b = boost.get((tag, v["id"]), 1.0)
        share = 2 if b >= WEAK_EXTRA_SHARE else 1
        load = used[(tag, v["id"])]
        return (taken[v["id"]] / share, load / (w * b), rng.random())
    return min(variants, key=score)


def variant_brief(variant: dict) -> str:
    text = f"本题考法变式：{variant['name']}。{variant['ask']}"
    if variant.get("example"):
        text += f"真题设问参考（只借鉴设问结构，不照抄情境和数字）：{variant['example']}"
    return text + "必须按此变式命题，不得退回本考点最常见的默认考法。"


LOCKING_BRIEF = re.compile(r"同构|只(?:练|出|考|要)|仅(?:练|出|考)|全部(?:按|出|是|用)|都(?:按|出|用|是)|固定(?:考法|结构|模型)|同一(?:考法|模型|结构)|不要换")


def resolve_variants(tag: str, wanted, variants: list[dict]) -> list[dict]:
    """槽位点名的变式（id 或名称，单个或列表）→ 变式对象；名称允许唯一片段匹配。"""
    names = [wanted] if isinstance(wanted, str) else list(wanted or [])
    chosen = []
    for name in names:
        name = str(name).strip()
        hits = [v for v in variants if name in (v["id"], v["name"])] or \
               [v for v in variants if name and (name in v["name"] or name in v["id"])]
        if len(hits) != 1:
            raise ValueError(f"{tag} 没有唯一匹配“{name}”的考法变式；可选：" +
                             "、".join(f"{v['name']}({v['id']})" for v in variants))
        if hits[0] not in chosen:
            chosen.append(hits[0])
    return chosen


def assign_variants(module: str, slots: list[dict], *, seed: str = "", catalog: dict | None = None,
                    ledger: Path | None = None, today: dt.date | None = None,
                    boost: dict | None = None, difficulty: str | None = None) -> list[dict]:
    """把有变式清单的槽位拆成每题一个，并写入变式要求。

    - 默认：在该考点全部变式里轮转，近期少练、错得多（boost）的优先，错得多的同批可占两份。
    - 槽位 difficulty（缺省用 difficulty 参数）为 easy/mid/hard 时按变式 level 筛选，见 level_pool。
    - 槽位 kaofa_variant：点名一个或几个变式（id/名称），只在这些里出，可重复。
    - 槽位 kaofa_focus="weak"：只在表现系数偏高（错得多）的变式里出；没有足够做题数据时退回全部变式。
    - brief 锁定考法（同构、只练某种）且未点名变式时保持原样；其余倾向性要求与变式叠加。
    """
    if module not in MODULES:
        return slots
    catalog = load_catalog() if catalog is None else catalog
    used = usage(ledger, today)
    if boost is None:
        boost = variant_boosts(variant_performance(ledger=ledger, today=today))
    rng = random.Random(seed or None)
    taken_by_tag: dict[str, Counter] = {}
    result = []
    for slot in slots:
        variants = variants_for(slot["tag"], catalog)
        user_brief = str(slot.get("brief") or "").strip()
        wanted = slot.get("kaofa_variant")
        if not variants or (LOCKING_BRIEF.search(user_brief) and not wanted):
            result.append(slot)
            continue
        tag = str(slot["tag"])
        tier = slot.get("difficulty") or difficulty
        pool = variants
        if wanted:
            pool = resolve_variants(tag, wanted, variants)
        else:
            if slot.get("kaofa_focus") == "weak":
                weak = [v for v in variants if boost.get((tag, v["id"]), 1.0) >= WEAK_FOCUS]
                pool = weak or variants
            pool = level_pool(pool, tier)
        taken = taken_by_tag.setdefault(tag, Counter())
        base = {k: v for k, v in slot.items() if k not in ("kaofa_variant", "kaofa_focus")}
        for _ in range(int(slot["count"])):
            variant = pick(tag, pool, used, taken, rng, boost, tier)
            taken[variant["id"]] += 1
            brief = variant_brief(variant) + (f"另需满足用户要求：{user_brief}" if user_brief else "")
            result.append({**base, "count": 1, "kaofa_variant": variant["id"],
                           "kaofa_variant_name": variant["name"], "brief": brief})
    return result


ZILIAO_SKIP_KINDS = {"judge", "chart_match"}


def assign_ziliao_variants(slots: list[dict], *, seed: str = "", targeted: bool = False, catalog: dict | None = None,
                           ledger: Path | None = None, today: dt.date | None = None,
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
        if slot.get("difficulty") in ("easy", "hard"):
            # 资料默认 mid 不筛，保持原有题型与考法轮转；只有整篇/单题调成易或难才按层级缩小范围。
            pool = level_pool(pool, slot["difficulty"])
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


def record_variants(batch_id: str, slots: list[dict], ledger: Path | None = None, today: dt.date | None = None,
                    question_ids: list[str] | None = None) -> int:
    """入库后记账。question_ids 与槽位逐题对齐时一并写入题号，供按变式统计正确率。"""
    day = (today or dt.date.today()).isoformat()
    rows = []
    for index, slot in enumerate(s for s in slots for _ in range(int(s.get("count") or 1))):
        if not slot.get("kaofa_variant"):
            continue
        row = {"date": day, "batch_id": batch_id, "tag": slot["tag"], "variant": slot["kaofa_variant"]}
        if question_ids and index < len(question_ids):
            row["question_id"] = question_ids[index]
        rows.append(row)
    if rows:
        ledger = ledger_path(ledger)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


PERF_DAYS = 90
PERF_MIN_N = 2
SKIP_SECONDS = 5


def variant_performance(db: Path | None = None, ledger: Path | None = None, today: dt.date | None = None,
                        days: int = PERF_DAYS) -> dict:
    """近 90 天各变式的首次作答正确率 {(tag, variant): {"n", "correct"}}。
    只统计账本里带题号的题；重做旧题、几秒翻过的空题不算。"""
    import sqlite3
    db = Path(db or os.environ.get("EXAM_DB") or ROOT / "data" / "exam.db")
    ledger = ledger_path(ledger)
    if not db.is_file() or not ledger.is_file():
        return {}
    by_question = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("question_id"):
            by_question[str(row["question_id"])] = (row["tag"], row["variant"])
    if not by_question:
        return {}
    since = ((today or dt.date.today()) - dt.timedelta(days=days)).isoformat()
    stats: dict = {}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    try:
        ids = list(by_question)
        seen = set()
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for qid, external, answer, correct, seconds, when in conn.execute(
                    f"""SELECT pa.question_id, q.external_id, pa.user_answer, pa.is_correct, pa.time_spent_sec, pa.answered_at
                          FROM practice_answers pa JOIN questions q ON q.id = pa.question_id
                         WHERE q.external_id IN ({marks}) ORDER BY pa.answered_at, pa.id""", chunk):
                if qid in seen:
                    continue
                seen.add(qid)
                if str(when or "")[:10] < since or (not str(answer or "").strip() and (seconds or 0) < SKIP_SECONDS):
                    continue
                key = by_question[str(external)]
                row = stats.setdefault(key, {"n": 0, "correct": 0})
                row["n"] += 1
                row["correct"] += 1 if correct else 0
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return stats


def variant_boosts(stats: dict) -> dict:
    """正确率 → 出题系数（与资料分析同一换算）：错得多 >1，稳定全对 <1，样本少不调。"""
    from ziliao_performance import boost_of
    return {key: boost_of(row["n"], row["correct"]) for key, row in stats.items() if row["n"] >= PERF_MIN_N}


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


def coverage(catalog: dict | None = None, ledger: Path | None = None) -> dict:
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
        if "level" in v and v["level"] not in (1, 2, 3):
            issues.append(f"level 须为 1（入门）/2（进阶）/3（真题难点）：{v.get('id')}")
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
    p = sub.add_parser("list", help="列出某知识点的变式及近期练习次数、近 90 天正确率")
    p.add_argument("tag")
    p = sub.add_parser("weak", help="按错得多到少排列某知识点的变式（只列有做题数据的）")
    p.add_argument("tag")
    p = sub.add_parser("add", help="新增变式（自动校验与查重）")
    p.add_argument("tag")
    p.add_argument("--name", required=True)
    p.add_argument("--ask", required=True, help="题干结构与解题动作，≤120 字")
    p.add_argument("--example", default="", help="真题出处与题干片段，如“粤2025：……”；没有就留空，不得编造")
    p.add_argument("--weight", type=int, default=2)
    p.add_argument("--id", dest="vid")
    p.add_argument("--level", type=int, choices=[1, 2, 3], help="难度层级：1 入门 / 2 进阶 / 3 真题难点；easy/mid/hard 出题按层级挑变式")
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
    p.add_argument("--level", type=int, choices=[0, 1, 2, 3], help="难度层级 1/2/3；0 表示清除层级")
    p.add_argument("--typical", action="store_true", help="设为本知识点的典型默认考法")
    p = sub.add_parser("remove", help="删除变式")
    p.add_argument("tag")
    p.add_argument("id")
    args = parser.parse_args(argv)

    catalog = load_catalog()
    tag = resolve_tag(args.tag, catalog)
    entry = catalog.get(tag)
    if args.cmd in ("list", "weak"):
        if not entry:
            return {"ok": True, "tag": tag, "variants": [], "note": "该知识点还没有变式清单，可用 add 新增"}
        used = usage()
        stats = variant_performance()
        boosts = variant_boosts(stats)

        def accuracy(v):
            row = stats.get((tag, v["id"]))
            return ({"n": row["n"], "correct": row["correct"], "rate": round(row["correct"] / row["n"], 2)}
                    if row else None)
        rows = [{**v, "recent_uses": used[(tag, v["id"])], "accuracy": accuracy(v),
                 "boost": boosts.get((tag, v["id"]), 1.0)} for v in entry["variants"]]
        if args.cmd == "weak":
            rows = sorted((r for r in rows if r["accuracy"]), key=lambda r: (r["accuracy"]["rate"], -r["accuracy"]["n"]))
            note = ("近 90 天还没有带考法记录的作答，先按知识点特训几批再看" if not rows else
                    "出题时槽位写 kaofa_variant 点名，或 kaofa_focus=weak 只练错得多的")
            return {"ok": True, "tag": tag, "title": entry.get("title"), "variants": rows, "note": note}
        return {"ok": True, "tag": tag, "title": entry.get("title"), "variants": rows}

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
        if args.level:
            variant["level"] = args.level
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
        if args.level is not None:
            if args.level:
                updated["level"] = args.level
            else:
                updated.pop("level", None)
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

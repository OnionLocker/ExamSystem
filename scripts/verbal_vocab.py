#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逻辑填空从词语学习词库抽词。

词库是 src/studyBoost/vocab-packs/：每日读报追加的实词、成语，加上基础实词和真题成语。
同一天、同一 batch 抽到的词稳定；只把「今天零点之前」近 30 天题面里已经用过的词往后排，
这样同一批次反复导入不会中途换词。
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "src" / "studyBoost" / "vocab-packs"
IDIOM_PACKS = {"zhenti-idioms", "hot-idioms", "recent-gd-idioms"}
HISTORY_DAYS = 30


def target_kinds(tag: str, variant_name: str = "") -> set[str]:
    """逻辑填空要哪类词。片段阅读和语句表达不抽词。"""
    text = str(tag or "")
    if "逻辑填空" not in text:
        return set()
    name = str(variant_name or "")
    if "词的辨析" in text or "语境分析" in text:
        return {"word"}
    if "混合" in name:
        return {"idiom", "word"}
    if "实词" in name and "成语" not in name:
        return {"word"}
    return {"idiom"}


def vocab_issues(question: dict, slot: dict) -> list[str]:
    """正确项必须用上指定词，题干不能把词写出来。"""
    word = str((slot or {}).get("vocab_word") or "")
    if not word:
        return []
    stem = str(question.get("stem") or "")
    if word in stem:
        return [f"题干写出了词库指定词「{word}」，空格题不能把答案露在题干里"]
    answer = str(question.get("answer") or "")
    correct = ""
    for option in question.get("options") or []:
        if isinstance(option, dict) and str(option.get("key") or "") == answer:
            correct = str(option.get("text") or "")
    if word not in correct:
        return [f"正确项未使用词库指定词「{word}」"]
    return []


def _kind(entry: dict, pack_id: str) -> str:
    word_type = entry.get("wordType")
    if word_type == "word":
        return "word"
    if word_type == "idiom":
        return "idiom"
    if word_type == "collocation":
        return ""
    if pack_id in IDIOM_PACKS or "idiom" in pack_id:
        return "idiom"
    return ""


def _age(created: str, today: dt.date) -> int:
    try:
        day = dt.date.fromisoformat(str(created)[:10])
    except ValueError:
        return 9999
    return max(0, (today - day).days)


def load_bank(packs_dir: Path | None = None, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    base = Path(packs_dir) if packs_dir else PACKS
    by_word: dict[str, dict] = {}
    if not base.is_dir():
        return []
    for path in sorted(base.glob("*.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pack_id = str(pack.get("pack_id") or path.stem)
        age = _age(pack.get("created_at") or "", today)
        for entry in pack.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            word = str(entry.get("word") or "").strip()
            explanation = str(entry.get("explanation") or "").strip()
            kind = _kind(entry, pack_id)
            if not word or not explanation or not kind or not 2 <= len(word) <= 12:
                continue
            row = {
                "word": word,
                "kind": kind,
                "age": age,
                "explanation": explanation,
                "usage": str(entry.get("usage") or "").strip(),
                "trap": str(entry.get("trap") or "").strip(),
                "rivals": [str(item).strip() for item in (entry.get("rivals") or entry.get("synonyms") or []) if str(item).strip()],
                "collocations": [str(item).strip() for item in (entry.get("collocations") or []) if str(item).strip()],
            }
            old = by_word.get(word)
            if old is None:
                by_word[word] = row
                continue
            old["age"] = min(int(old["age"]), age)
            for key in ("explanation", "usage", "trap"):
                if len(row[key]) > len(old[key]):
                    old[key] = row[key]
            if row["kind"] == "idiom":
                old["kind"] = "idiom"
            for key in ("rivals", "collocations"):
                for item in row[key]:
                    if item not in old[key]:
                        old[key].append(item)
    return list(by_word.values())


def brief_for(entry: dict) -> str:
    label = "成语" if entry["kind"] == "idiom" else "实词"
    parts = [f"指定词：{entry['word']}（{label}）", f"释义：{entry['explanation'][:80]}"]
    if entry.get("usage"):
        parts.append(f"用法：{entry['usage'][:80]}")
    if entry.get("trap"):
        parts.append(f"易错：{entry['trap'][:80]}")
    rivals = "、".join((entry.get("rivals") or [])[:4])
    if rivals:
        parts.append(f"易混：{rivals}")
    cols = "、".join((entry.get("collocations") or [])[:3])
    if cols:
        parts.append(f"常见搭配：{cols}（不是唯一合法搭配）")
    return "。".join(parts)


def recent_word_texts(db: Path | None, today: dt.date | None = None) -> list[str]:
    """今天零点之前近 30 天的言语题面。同一天内这个集合不变。"""
    today = today or dt.date.today()
    path = Path(db) if db else None
    if path is None or not path.is_file():
        return []
    start = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            """
            SELECT content, options FROM questions
            WHERE category = '言语理解与表达'
              AND created_at >= ? AND created_at < ?
            """,
            (start, today.isoformat()),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [f"{content or ''}\n{options or ''}" for content, options in rows]


def _pick(pool: list[dict], used: set[str], taken: set[str], rng: random.Random) -> dict | None:
    fresh = [entry for entry in pool if entry["word"] not in taken]
    if not fresh:
        fresh = list(pool)
    if not fresh:
        return None
    ranked = sorted(fresh, key=lambda entry: (entry["word"] in used, int(entry["age"]), rng.random()))
    return ranked[0]


def assign_vocab(slots: list[dict], *, seed: str = "", db: Path | None = None,
                 today: dt.date | None = None, packs_dir: Path | None = None,
                 bank: list[dict] | None = None, recent_texts: list[str] | None = None) -> list[dict]:
    """给还没有指定词的逻辑填空槽位写上 vocab_word / vocab_brief。已有的不改。"""
    today = today or dt.date.today()
    entries = bank if bank is not None else load_bank(packs_dir, today)
    if not entries:
        return slots
    texts = recent_texts if recent_texts is not None else recent_word_texts(db, today)
    blob = "\n".join(texts)
    used = {entry["word"] for entry in entries if entry["word"] in blob}
    rng = random.Random(seed or None)
    taken: set[str] = {str(slot.get("vocab_word") or "") for slot in slots if slot.get("vocab_word")}
    taken.discard("")
    for slot in slots:
        if slot.get("vocab_word"):
            continue
        kinds = target_kinds(slot.get("tag") or "", slot.get("kaofa_variant_name") or "")
        if not kinds:
            continue
        pool = [entry for entry in entries if entry["kind"] in kinds]
        if not pool and "idiom" in kinds:
            pool = [entry for entry in entries if entry["kind"] == "word"]
        chosen = _pick(pool, used, taken, rng)
        if chosen is None:
            continue
        taken.add(chosen["word"])
        slot["vocab_word"] = chosen["word"]
        slot["vocab_brief"] = brief_for(chosen)
    return slots

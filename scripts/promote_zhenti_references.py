#!/usr/bin/env python3
"""把 data/zhenti 有答案、无缺图的真题写入 reference_questions。

不进 AI 练题页。带图题和无答案卷跳过。与已有粉笔题按题干签名去重。

用法:
  python3 scripts/promote_zhenti_references.py --dry-run
  python3 scripts/promote_zhenti_references.py
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZHENTI_DIR = ROOT / "data" / "zhenti"
DEFAULT_DB = ROOT / "data" / "exam.db"
CATEGORIES = {
    "政治理论",
    "常识判断",
    "言语理解与表达",
    "数量关系",
    "判断推理",
    "资料分析",
}
JUDGE_MARK = re.compile(r"[（(]\s*判断题\s*[）)]")
PUNCT = re.compile(r"[^一-鿿A-Za-z0-9]+")
SPACE = re.compile(r"\s+")


def compact(value: object) -> str:
    return SPACE.sub(" ", str(value or "")).strip()


def stem_key(stem: str) -> str:
    text = compact(stem)
    text = re.sub(r"^【.*?】\s*", "", text)
    text = text.replace("[依托材料]", "")
    return compact(text)


def make_external_id(title: str, number: object) -> str:
    ident = f"zhenti-{PUNCT.sub('', title)}-Q{number}"
    return ident[:120]


def region_of(title: str, exam: str) -> str:
    blob = f"{title} {exam}"
    if "广东" in blob:
        return "广东"
    if "国家" in blob or "国考" in blob:
        return "国家"
    return compact(exam) or "未知"


def category_of(module: str) -> str:
    if module == "科学推理":
        return "判断推理"
    return module if module in CATEGORIES else ""


def sub_category_of(module: str, subtype: str) -> str:
    blob = f"{module} {subtype}"
    mapping = (
        ("类比推理", "类比推理"),
        ("定义判断", "定义判断"),
        ("图形推理", "图形推理"),
        ("逻辑判断", "逻辑判断"),
        ("科学推理", "科学推理"),
        ("数字推理", "数字推理"),
        ("数学运算", "数学运算"),
        ("逻辑填空", "逻辑填空"),
        ("片段阅读", "片段阅读"),
        ("语句", "语句表达"),
        ("新思想", "新思想"),
        ("时政", "时事政治"),
        ("时事", "时事政治"),
        ("毛中特", "毛中特"),
        ("马克思", "马克思主义"),
        ("法律", "法律常识"),
        ("人文", "人文常识"),
        ("科技", "科技常识"),
        ("经济", "经济常识"),
        ("地理", "地理国情"),
        ("综合分析", "综合分析"),
        ("比重", "比重"),
        ("平均数", "平均数"),
        ("增长率", "增长率"),
        ("增长量", "增长量"),
    )
    for needle, name in mapping:
        if needle in blob:
            return name
    if "-" in subtype:
        head, tail = subtype.split("-", 1)
        return tail or head
    return subtype or module or "未细分"


def tags_of(category: str, subtype: str, points: list[str]) -> list[str]:
    tags: list[str] = []
    for item in [subtype, *points]:
        text = compact(item)
        if text and text not in tags:
            tags.append(text)
    if not tags:
        tags.append(category)
    return tags[:20]


def options_of(raw: object) -> list[dict[str, object]]:
    if isinstance(raw, dict):
        return [
            {"key": str(key), "text": str(value or ""), "images": []}
            for key, value in raw.items()
            if value not in (None, "")
        ]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def iter_candidates(zhenti_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(zhenti_dir.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        title = compact(document.get("title") or path.stem)
        year = document.get("year")
        exam = compact(document.get("exam"))
        region = region_of(title, exam)
        materials = {
            compact(item.get("ref")): str(item.get("text") or "")
            for item in document.get("materials") or []
            if isinstance(item, dict)
        }
        for question in document.get("questions") or []:
            if not isinstance(question, dict):
                continue
            category = category_of(compact(question.get("module")))
            if not category:
                continue
            skip = ""
            if question.get("has_figure"):
                skip = "has_figure"
            answer = compact(question.get("correct_answer")).upper()
            if not answer:
                skip = skip or "no_answer"
            stem = compact(question.get("stem")).replace("[依托材料]", "").strip()
            if not stem:
                skip = skip or "empty_stem"
            options = options_of(question.get("options"))
            is_judge = bool(JUDGE_MARK.search(stem))
            if is_judge:
                question_type = "judge"
                answer = {"A": "T", "B": "F", "T": "T", "F": "F", "对": "T", "错": "F"}.get(answer, "")
                if answer not in {"T", "F"}:
                    skip = skip or "bad_judge_answer"
                options = []
            elif len(options) < 2:
                skip = skip or "broken_options"
                question_type = "single"
            else:
                question_type = "multi" if len(answer) > 1 else "single"
            material_ref = compact(question.get("material_ref"))
            material = materials.get(material_ref, "")
            content = f"【{material_ref}】\n{material}\n\n{stem}" if material else stem
            rows.append(
                {
                    "skip": skip,
                    "paper": "gd" if region == "广东" else ("gk" if region == "国家" else "other"),
                    "external_id": make_external_id(title, question.get("number")),
                    "category": category,
                    "sub_category": sub_category_of(category, compact(question.get("subtype"))),
                    "question_type": question_type,
                    "content": content,
                    "stem_images": "[]",
                    "options": json.dumps(options, ensure_ascii=False),
                    "correct_answer": answer,
                    "explanation": "",
                    "explanation_images": "[]",
                    "difficulty": 3,
                    "tags": json.dumps(
                        tags_of(
                            category,
                            compact(question.get("subtype")),
                            [compact(x) for x in (question.get("knowledge_points") or []) if compact(x)],
                        ),
                        ensure_ascii=False,
                    ),
                    "source": f"{title}第{question.get('number')}题",
                    "year": year,
                    "region": region,
                    "source_url": None,
                    "imported_by": "zhenti-promote",
                    "stem_key": stem_key(stem),
                }
            )
    return rows


def load_existing_keys(conn: sqlite3.Connection) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    keys: set[str] = set()
    for external_id, content in conn.execute("SELECT external_id, content FROM reference_questions"):
        ids.add(str(external_id))
        keys.add(stem_key(content))
    return ids, keys


UPSERT = """
INSERT INTO reference_questions (
  external_id, category, sub_category, question_type, content,
  stem_images, options, correct_answer, explanation, explanation_images,
  difficulty, tags, source, year, region, source_url, imported_by
) VALUES (
  :external_id, :category, :sub_category, :question_type, :content,
  :stem_images, :options, :correct_answer, :explanation, :explanation_images,
  :difficulty, :tags, :source, :year, :region, :source_url, :imported_by
)
ON CONFLICT(external_id) DO UPDATE SET
  category = excluded.category,
  sub_category = excluded.sub_category,
  question_type = excluded.question_type,
  content = excluded.content,
  options = excluded.options,
  correct_answer = excluded.correct_answer,
  tags = excluded.tags,
  source = excluded.source,
  year = excluded.year,
  region = excluded.region,
  imported_by = excluded.imported_by,
  updated_at = CURRENT_TIMESTAMP
"""


def promote(db_path: Path, zhenti_dir: Path, dry_run: bool) -> dict[str, int]:
    rows = iter_candidates(zhenti_dir)
    conn = sqlite3.connect(db_path)
    existing_ids, existing_keys = load_existing_keys(conn)
    stats: Counter[str] = Counter()
    seen_keys = set(existing_keys)
    keep: list[dict[str, object]] = []
    for row in rows:
        stats["scanned"] += 1
        stats[f"paper_{row['paper']}"] += 1
        if row["skip"]:
            stats[row["skip"]] += 1
            continue
        if row["external_id"] in existing_ids:
            stats["refresh"] += 1
            keep.append(row)
            continue
        if row["stem_key"] in seen_keys:
            stats["dedup"] += 1
            continue
        seen_keys.add(row["stem_key"])
        stats[f"insert_{row['paper']}"] += 1
        keep.append(row)
    if not dry_run:
        payload = [{k: v for k, v in row.items() if k not in {"skip", "paper", "stem_key"}} for row in keep]
        conn.executemany(UPSERT, payload)
        conn.commit()
    conn.close()
    stats["written"] = len(keep)
    return dict(stats)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--zhenti-dir", type=Path, default=ZHENTI_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"数据库不存在：{args.db}", file=sys.stderr)
        return 2
    stats = promote(args.db, args.zhenti_dir, args.dry_run)
    label = "试运行" if args.dry_run else "已写入"
    print(
        f"{label} 扫描 {stats.get('scanned', 0)}｜"
        f"写入 {stats.get('written', 0)}｜"
        f"省考新入 {stats.get('insert_gd', 0)}｜"
        f"国考新入 {stats.get('insert_gk', 0)}｜"
        f"刷新 {stats.get('refresh', 0)}｜"
        f"去重 {stats.get('dedup', 0)}"
    )
    print(
        f"跳过 缺图 {stats.get('has_figure', 0)}｜"
        f"无答案 {stats.get('no_answer', 0)}｜"
        f"选项残缺 {stats.get('broken_options', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

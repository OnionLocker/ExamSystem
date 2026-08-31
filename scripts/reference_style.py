#!/usr/bin/env python3
"""把真题参考库整理成 Hermes 可复用的风格提纲，并按考点选择少量样本。

用法：
  python3 scripts/reference_style.py build
  python3 scripts/reference_style.py status
  python3 scripts/reference_style.py context --role generate \
    --category 判断推理 --sub-category 逻辑判断 \
    --tag 判断推理-逻辑判断-加强论证 --count 5

不调用外部模型。定量画像和逐题内容哈希由本脚本生成；定性命题规则维护在
quiz-pipeline/references/reference-style-principles.md。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

from kaodian_taxonomy import canonicalize


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "exam.db"
ZHENTI_DIR = ROOT / "data" / "zhenti"
DEFAULT_OUTPUT_DIR = (
    Path.home() / ".hermes" / "skills" / "kaogong" / "quiz-pipeline" / "references"
)
DIGEST_VERSION = "GONGKAO-STYLE-v1"
PROFILE_NAME = "reference-style-profile.md"
STATUS_NAME = "reference-style-status.json"
EVALUATION_ONLY_IMPORTER = "approved-ai-holdout"
GENERATION_ONLY_IMPORTER = "approved-ai-generate"
PRINCIPLES_NAME = "reference-style-principles.md"
CANONICAL_GUIDE = ROOT / "docs" / "AI_PRACTICE_STYLE_GUIDE.md"

SOURCE_TIER_SCORE = {
    "gd-real": 5,
    "national-real": 4,
    "other-real": 3,
    "gd-mock": 2,
    "other-mock": 1,
    "unknown": 0,
}
SOURCE_TIER_LABEL = {
    "gd-real": "广东/深圳/广州真题",
    "gd-mock": "广东地区模拟题",
    "national-real": "国考真题",
    "other-real": "其他地区真题",
    "other-mock": "其他模拟题",
    "unknown": "来源待确认",
}
TAG_OVERRIDES = {
    "粉笔-2022-上海B类-马克思主义-91": ["政治理论-马克思主义-唯物史观"],
}
GD_GENERATE_BLOCK = ("定义判断", "类比推理")
MANUAL_EXCLUSIONS = {
    "粉笔-2026-福建-片段阅读-48": "回忆文本末句语义疑似错字，不能作为生成范本",
    "粉笔-2024-青海-语句表达-48": "回忆文本中的时代顺序疑似错置",
    "粉笔-2025-四川-语句表达-44": "回忆文本存在明显语病或漏字",
    "粉笔-2026-国家-语句表达-48": "关键希腊字母在导入时丢失",
    "粉笔-2026-浙江C类-数学运算-58": "部门总人数与选派人数边界疑似缺失",
    "粉笔-2024-黑龙江-逻辑判断-96": "选项文字被截断",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS reference_digest_items (
  external_id      TEXT PRIMARY KEY,
  content_hash     TEXT NOT NULL,
  digest_version   TEXT NOT NULL,
  status           TEXT NOT NULL,
  source_tier      TEXT NOT NULL,
  note             TEXT,
  generation_uses  INTEGER NOT NULL DEFAULT 0,
  evaluation_uses  INTEGER NOT NULL DEFAULT 0,
  last_used_at     TEXT,
  processed_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (external_id) REFERENCES reference_questions(external_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_reference_digest_status
  ON reference_digest_items(digest_version, status);

CREATE TABLE IF NOT EXISTS reference_context_runs (
  context_id       TEXT PRIMARY KEY,
  role             TEXT NOT NULL,
  digest_version   TEXT NOT NULL,
  target           TEXT NOT NULL,
  reference_ids    TEXT NOT NULL,
  batch_id         TEXT,
  created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reference_context_created
  ON reference_context_runs(created_at);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def effective_tags(row: sqlite3.Row | dict[str, Any]) -> list[Any]:
    return TAG_OVERRIDES.get(row["external_id"], json_list(row["tags"]))


def canonical_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    out = {
        "external_id": row["external_id"],
        "category": row["category"],
        "sub_category": row["sub_category"],
        "question_type": row["question_type"],
        "content": compact_text(row["content"]),
        "stem_images": json_list(row["stem_images"]),
        "options": json_list(row["options"]),
        "correct_answer": row["correct_answer"],
        "explanation": compact_text(row["explanation"]),
        "explanation_images": json_list(row["explanation_images"]),
        "difficulty": row["difficulty"],
        "tags": effective_tags(row),
        "source": compact_text(row["source"]),
        "year": row["year"],
        "region": compact_text(row["region"]),
    }
    return out


def content_hash(row: sqlite3.Row | dict[str, Any]) -> str:
    raw = json.dumps(
        canonical_payload(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def duplicate_signature(row: sqlite3.Row | dict[str, Any]) -> str:
    # 同一句通用图推题干配不同图片不是重复题，所以图片路径也参与签名。
    payload = canonical_payload(row)
    raw = json.dumps(
        {
            "content": payload["content"],
            "stem_images": payload["stem_images"],
            "options": payload["options"],
            "question_type": payload["question_type"],
            "correct_answer": payload["correct_answer"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def blocked_gd_reference(row: sqlite3.Row | dict[str, Any]) -> bool:
    blob = " ".join(
        [
            compact_text(row["sub_category"]),
            compact_text(row["source"]),
            *[str(tag) for tag in effective_tags(row)],
        ]
    )
    return any(word in blob for word in GD_GENERATE_BLOCK)


def item_tier(row: sqlite3.Row | dict[str, Any], item: sqlite3.Row | dict[str, Any]) -> str:
    if isinstance(item, dict):
        return str(item.get("source_tier") or source_tier(row))
    return str(item["source_tier"] if item["source_tier"] else source_tier(row))


def pick_mixed(
    candidates: list[tuple[sqlite3.Row | dict[str, Any], sqlite3.Row | dict[str, Any], int, float]],
    role: str,
    count: int,
) -> list[tuple[sqlite3.Row | dict[str, Any], sqlite3.Row | dict[str, Any], int, float]]:
    ranked = sorted(
        candidates,
        key=lambda item: (-item[3], content_hash(item[0]), item[0]["external_id"]),
    )
    gd = [item for item in ranked if item_tier(item[0], item[1]) == "gd-real"]
    gk = [item for item in ranked if item_tier(item[0], item[1]) == "national-real"]
    other = [
        item
        for item in ranked
        if item_tier(item[0], item[1]) not in {"gd-real", "national-real"}
    ]
    if role == "evaluate":
        return (gd + other + gk)[:count]
    want_gk = min(2, len(gk)) if count >= 4 else (1 if count >= 2 and gk else 0)
    want_gd = min(3, count - want_gk, len(gd))
    chosen = gd[:want_gd] + gk[:want_gk]
    seen = {item[0]["external_id"] for item in chosen}
    for pool in (gd[want_gd:], other, gk[want_gk:]):
        for item in pool:
            if len(chosen) >= count:
                break
            if item[0]["external_id"] not in seen:
                chosen.append(item)
                seen.add(item[0]["external_id"])
    return chosen[:count]


def source_tier(row: sqlite3.Row | dict[str, Any]) -> str:
    source = compact_text(row["source"])
    region = compact_text(row["region"])
    joined = f"{source} {region}"
    is_mock = any(word in joined for word in ("模拟", "模考"))
    is_gd = any(word in joined for word in ("广东", "深圳", "广州"))
    is_national = region == "国家" or "国家公务员" in joined or "国考" in joined
    if is_gd:
        return "gd-mock" if is_mock else "gd-real"
    if is_national and not is_mock:
        return "national-real"
    if is_mock:
        return "other-mock"
    if source or region:
        return "other-real"
    return "unknown"


def public_image_to_local(public_path: str) -> Path | None:
    if not public_path.startswith("/q-images/"):
        return None
    relative = unquote(public_path.removeprefix("/")).replace("..", "")
    return ROOT / "public" / relative


def image_paths(row: sqlite3.Row | dict[str, Any]) -> list[str]:
    paths = [str(x) for x in json_list(row["stem_images"])]
    paths.extend(str(x) for x in json_list(row["explanation_images"]))
    for option in json_list(row["options"]):
        if isinstance(option, dict):
            paths.extend(str(x) for x in json_list(option.get("images")))
    return [p for p in paths if p]


def structural_issue(row: sqlite3.Row | dict[str, Any]) -> str | None:
    if row["external_id"] in MANUAL_EXCLUSIONS:
        return MANUAL_EXCLUSIONS[row["external_id"]]
    if not compact_text(row["content"]):
        return "题干为空"
    if not compact_text(row["correct_answer"]):
        return "答案为空"
    q_type = row["question_type"] or "single"
    options = json_list(row["options"])
    if q_type != "judge" and len(options) < 2:
        return "非判断题选项不足"
    missing: list[str] = []
    for public_path in image_paths(row):
        local = public_image_to_local(public_path)
        if local is not None and not local.exists():
            missing.append(public_path)
    if missing:
        return f"引用图片缺失：{', '.join(missing[:2])}"
    return None


def load_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT external_id, category, sub_category, question_type, content,
               stem_images, options, correct_answer, explanation,
               explanation_images, difficulty, tags, source, year, region,
               source_url, imported_by, created_at, updated_at
          FROM reference_questions
         ORDER BY id
        """
    ).fetchall()


def load_legacy_rows(category: str) -> list[dict[str, Any]]:
    """读取旧结构化真题作缺类回退。资料分析 PDF 只抽出导语、丢掉表/图，不能当参考。"""
    rows: list[dict[str, Any]] = []
    if category == "资料分析" or not ZHENTI_DIR.is_dir() or not category:
        return rows
    for source_path in sorted(ZHENTI_DIR.glob("*.json")):
        try:
            document = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        title = compact_text(document.get("title") or source_path.stem)
        year = document.get("year")
        region = (
            "广东"
            if "广东" in title
            else ("国家" if "国家公务员" in title else compact_text(document.get("exam")))
        )
        materials = {
            compact_text(item.get("ref")): str(item.get("text") or "")
            for item in document.get("materials") or []
            if isinstance(item, dict)
        }
        for question in document.get("questions") or []:
            if not isinstance(question, dict) or question.get("module") != category:
                continue
            if question.get("has_figure"):
                # 旧 JSON 只有 figure_note，没有可读取的实际切图，不能冒充视觉参考。
                continue
            raw_options = question.get("options") or {}
            if isinstance(raw_options, dict):
                options = [
                    {"key": str(key), "text": str(value or ""), "images": []}
                    for key, value in raw_options.items()
                    if value not in (None, "")
                ]
            elif isinstance(raw_options, list):
                options = raw_options
            else:
                options = []
            answer = compact_text(question.get("correct_answer"))
            if len(options) < 2 or not answer:
                continue
            subtype = compact_text(question.get("subtype")) or category
            sub_category = subtype.split("-", 1)[1] if "-" in subtype else subtype
            knowledge_points = [
                compact_text(value)
                for value in question.get("knowledge_points") or []
                if compact_text(value)
            ]
            tags = [subtype]
            tags.extend(f"{subtype}-{point}" for point in knowledge_points)
            material_ref = compact_text(question.get("material_ref"))
            material = materials.get(material_ref, "")
            external_id = f"legacy:{source_path.stem}:Q{question.get('number')}"
            rows.append(
                {
                    "external_id": external_id,
                    "category": category,
                    "sub_category": sub_category,
                    "question_type": "multi" if len(answer) > 1 else "single",
                    "content": str(question.get("stem") or "").replace("[依托材料]", "").strip(),
                    "stem_images": "[]",
                    "options": json.dumps(options, ensure_ascii=False),
                    "correct_answer": answer,
                    "explanation": "",
                    "explanation_images": "[]",
                    "difficulty": 3,
                    "tags": json.dumps(tags, ensure_ascii=False),
                    "source": f"{title} 第{question.get('number')}题",
                    "year": year,
                    "region": region,
                    "material": material,
                    "material_ref": material_ref,
                    "legacy": True,
                }
            )
    return rows


def choose_assignments(rows: list[sqlite3.Row]) -> dict[str, dict[str, str]]:
    assignments: dict[str, dict[str, str]] = {}
    duplicate_groups: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in rows:
        issue = structural_issue(row)
        tier = source_tier(row)
        if issue:
            assignments[row["external_id"]] = {
                "status": "excluded",
                "source_tier": tier,
                "note": issue,
            }
        else:
            duplicate_groups[duplicate_signature(row)].append(row)

    usable: list[sqlite3.Row] = []
    for group in duplicate_groups.values():
        ranked = sorted(
            group,
            key=lambda row: (
                -SOURCE_TIER_SCORE[source_tier(row)],
                -(int(row["year"]) if row["year"] else 0),
                str(row["external_id"]),
            ),
        )
        usable.append(ranked[0])
        for duplicate in ranked[1:]:
            assignments[duplicate["external_id"]] = {
                "status": "excluded",
                "source_tier": source_tier(duplicate),
                "note": f"与 {ranked[0]['external_id']} 整题重复",
            }

    evaluation_only_ids = {
        row["external_id"]
        for row in usable
        if row["imported_by"] == EVALUATION_ONLY_IMPORTER
    }
    generation_only_ids = {
        row["external_id"]
        for row in usable
        if row["imported_by"] == GENERATION_ONLY_IMPORTER
    }
    for row in usable:
        if row["external_id"] in evaluation_only_ids:
            assignments[row["external_id"]] = {
                "status": "holdout",
                "source_tier": source_tier(row),
                "note": "approved batch evaluation-only",
            }
        elif row["external_id"] in generation_only_ids:
            assignments[row["external_id"]] = {
                "status": "accepted",
                "source_tier": source_tier(row),
                "note": "approved batch generation-only",
            }

    by_group: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in usable:
        if row["external_id"] in evaluation_only_ids or row["external_id"] in generation_only_ids:
            continue
        by_group[(row["category"], row["sub_category"] or "未细分")].append(row)

    for group_rows in by_group.values():
        holdout_ids = {
            row["external_id"]
            for row in group_rows
            if int(content_hash(row)[:8], 16) % 100 < 15
        }
        # 每个有一定规模的题型至少留一题做独立风格评测。
        if len(group_rows) >= 6 and not holdout_ids:
            holdout_ids.add(min(group_rows, key=lambda row: content_hash(row))["external_id"])
        # 小样本题型最多留 20%，避免可检索样本被切得过薄。
        max_holdout = max(1, round(len(group_rows) * 0.2))
        if len(holdout_ids) > max_holdout:
            ordered = sorted(
                (row for row in group_rows if row["external_id"] in holdout_ids),
                key=lambda row: content_hash(row),
            )
            holdout_ids = {row["external_id"] for row in ordered[:max_holdout]}

        for row in group_rows:
            assignments[row["external_id"]] = {
                "status": "holdout" if row["external_id"] in holdout_ids else "accepted",
                "source_tier": source_tier(row),
                "note": "独立风格评测留出集" if row["external_id"] in holdout_ids else "",
            }

    by_category: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in usable:
        by_category[row["category"]].append(row)
    for category_rows in by_category.values():
        if len(category_rows) < 6 or any(
            assignments[row["external_id"]]["status"] == "holdout"
            for row in category_rows
        ):
            continue
        row = min(category_rows, key=content_hash)
        assignments[row["external_id"]] = {
            "status": "holdout",
            "source_tier": source_tier(row),
            "note": "独立风格评测留出集",
        }

    return assignments


def percentile(values: Iterable[int], ratio: float) -> int:
    ordered = sorted(int(v) for v in values)
    if not ordered:
        return 0
    index = round((len(ordered) - 1) * ratio)
    return ordered[max(0, min(index, len(ordered) - 1))]


def visible_length(value: Any) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def option_lengths(row: sqlite3.Row | dict[str, Any]) -> list[int]:
    lengths: list[int] = []
    for option in json_list(row["options"]):
        if isinstance(option, dict):
            length = visible_length(option.get("text"))
            if length or json_list(option.get("images")):
                lengths.append(length)
    return lengths


def question_tail(content: Any) -> str:
    text = compact_text(content)
    if not text:
        return ""
    ask_pattern = re.compile(
        r"((?:下列|以下|关于|根据|依次填入|填入|将以上|请问|这段文字|上述文字|"
        r"最可能|最能够|最能)[^。！？?：:]{2,110}(?:[。！？?：:]|$))"
    )
    asks = [compact_text(match.group(1)) for match in ask_pattern.finditer(text)]
    if asks:
        return asks[-1]
    if len(text) <= 90:
        return text
    tail = text[-150:]
    cuts = [match.end() for match in re.finditer(r"[。！？?；;]", tail[:-8])]
    if cuts:
        tail = tail[cuts[-1] :]
    tail = tail.strip()
    return tail if len(tail) <= 100 else tail[-100:]


def summarize_rows(rows: list[sqlite3.Row]) -> dict[str, Any]:
    stems = [visible_length(row["content"]) for row in rows]
    option_lens = [n for row in rows for n in option_lengths(row)]
    tiers = Counter(source_tier(row) for row in rows)
    types = Counter((row["question_type"] or "single") for row in rows)
    answers = Counter(compact_text(row["correct_answer"]) for row in rows)
    tags = Counter(tag for row in rows for tag in effective_tags(row) if isinstance(tag, str))
    years = [int(row["year"]) for row in rows if row["year"]]
    image_count = sum(bool(image_paths(row)) for row in rows)
    explanation_count = sum(bool(compact_text(row["explanation"])) for row in rows)

    representatives = sorted(
        rows,
        key=lambda row: (
            -SOURCE_TIER_SCORE[source_tier(row)],
            -(int(row["year"]) if row["year"] else 0),
            content_hash(row),
        ),
    )
    tails: list[str] = []
    for row in representatives:
        tail = question_tail(row["content"])
        if tail and tail not in tails:
            tails.append(tail)
        if len(tails) >= 4:
            break

    return {
        "count": len(rows),
        "stem": {
            "p25": percentile(stems, 0.25),
            "p50": percentile(stems, 0.5),
            "p75": percentile(stems, 0.75),
        },
        "option": {
            "p25": percentile(option_lens, 0.25),
            "p50": percentile(option_lens, 0.5),
            "p75": percentile(option_lens, 0.75),
        },
        "source_tiers": dict(tiers),
        "question_types": dict(types),
        "answers": dict(answers),
        "top_tags": tags.most_common(6),
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "image_count": image_count,
        "explanation_count": explanation_count,
        "question_tails": tails,
    }


def markdown_escape(text: str) -> str:
    return text.replace("|", "｜").replace("\n", " ")


def render_profile(
    rows: list[sqlite3.Row],
    assignments: dict[str, dict[str, str]],
    corpus_hash: str,
    built_at: str,
) -> str:
    included = [
        row
        for row in rows
        if assignments[row["external_id"]]["status"] in {"accepted", "holdout"}
    ]
    gd_rows = [row for row in included if source_tier(row) == "gd-real"]
    gk_rows = [row for row in included if source_tier(row) == "national-real"]
    counts = Counter(item["status"] for item in assignments.values())
    all_summary = summarize_rows(included)
    target_summary = summarize_rows(gd_rows) if gd_rows else None
    by_group: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in included:
        by_group[(row["category"], row["sub_category"] or "未细分")].append(row)

    lines = [
        "# 真题参考库风格数据档",
        "",
        f"> 内化标记：`{DIGEST_VERSION}`  ",
        f"> 构建时间：`{built_at}`  ",
        f"> 语料哈希：`{corpus_hash}`  ",
        f"> 已处理：{len(rows)}｜生成参考：{counts['accepted']}｜评测留出：{counts['holdout']}｜排除：{counts['excluded']}｜待处理：0",
        "",
        "本文件由 `scripts/reference_style.py build` 根据参考库重建。它给出真实题面的定量边界；",
        "定性命题规则见同目录 `reference-style-principles.md`。不得把本文件中的设问样例当题干模板机械替换。",
        "",
        "## 使用纪律",
        "",
        "- 生成包默认省考 3 道定题面，再混 1–2 道同考点国考作难度上限；`holdout` 只供独立质量审查，且优先省考。",
        "- **默认目标分位只看广东真题。** 国考分位见文末「国考拔高分位」，只约束认知步数和干扰深度，不拉长题干。",
        "- 定义判断、类比推理不进入广东批次参考包。",
        "- 参考题用于学习认知步骤、设问、信息密度和选项关系，严禁复用实体、数字、人物关系或连续措辞。",
        "- 带图题必须实际读取本地图片；只看通用题干不能算使用过参考题。",
        "- 参考库没有解析，干扰项机理只能作为待复核假设，不能凭空写成“真题规律”。",
        "",
        "## 全库概况",
        "",
        f"- 可用样本：{all_summary['count']}（广东 {len(gd_rows)}／国考 {len(gk_rows)}）；"
        f"含图 {all_summary['image_count']}；含解析 {all_summary['explanation_count']}。",
        "- 来源层级："
        + "；".join(
            f"{SOURCE_TIER_LABEL.get(tier, tier)} {count}"
            for tier, count in sorted(
                all_summary["source_tiers"].items(),
                key=lambda item: -SOURCE_TIER_SCORE.get(item[0], 0),
            )
        )
        + "。",
    ]
    if target_summary:
        lines.extend(
            [
                f"- **默认目标分位（仅广东真题 {target_summary['count']} 道）：**"
                f"题干 P25/P50/P75：{target_summary['stem']['p25']}/{target_summary['stem']['p50']}/{target_summary['stem']['p75']}；"
                f"选项：{target_summary['option']['p25']}/{target_summary['option']['p50']}/{target_summary['option']['p75']}。",
                "",
            ]
        )
    else:
        lines.extend(["- 当前没有广东真题样本，先不要用全库混合分位当默认目标。", ""])

    lines.extend(["## 分题型画像（默认分位=广东）", ""])

    for (category, sub_category), group_rows in sorted(by_group.items()):
        summary = summarize_rows(group_rows)
        gd_group = [row for row in group_rows if source_tier(row) == "gd-real"]
        target = summarize_rows(gd_group) if gd_group else None
        lines.extend(
            [
                f"### {category}｜{sub_category}",
                "",
                f"- 样本 {summary['count']}；年份 {summary['year_min'] or '未知'}–{summary['year_max'] or '未知'}；"
                f"含图 {summary['image_count']}；含解析 {summary['explanation_count']}。",
                "- 来源："
                + "；".join(
                    f"{SOURCE_TIER_LABEL.get(tier, tier)} {count}"
                    for tier, count in sorted(
                        summary["source_tiers"].items(),
                        key=lambda item: -SOURCE_TIER_SCORE.get(item[0], 0),
                    )
                )
                + "。",
            ]
        )
        if target:
            lines.append(
                f"- **目标分位（广东 {target['count']}）：**"
                f"题干 P25/P50/P75：{target['stem']['p25']}/{target['stem']['p50']}/{target['stem']['p75']}；"
                f"选项：{target['option']['p25']}/{target['option']['p50']}/{target['option']['p75']}。"
            )
        else:
            lines.append("- 无广东真题样本，本小节分位不作为默认目标。")
        if summary["top_tags"]:
            lines.append(
                "- 高频标签："
                + "；".join(
                    f"{markdown_escape(tag)}（{count}）"
                    for tag, count in summary["top_tags"]
                )
                + "。"
            )
        if target and target["question_tails"]:
            lines.append("- 代表性设问收尾（只学结构，取自广东）：")
            lines.extend(
                f"  - {markdown_escape(tail)}" for tail in target["question_tails"]
            )
        lines.append("")

    if gk_rows:
        gk_groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in gk_rows:
            gk_groups[(row["category"], row["sub_category"] or "未细分")].append(row)
        gk_summary = summarize_rows(gk_rows)
        lines.extend(
            [
                "## 国考拔高分位",
                "",
                "只用来卡认知步数和干扰深度，不替代上面的广东目标分位。",
                f"- 国考可用样本：{gk_summary['count']}；"
                f"题干 P25/P50/P75：{gk_summary['stem']['p25']}/{gk_summary['stem']['p50']}/{gk_summary['stem']['p75']}。",
                "",
            ]
        )
        for (category, sub_category), group_rows in sorted(gk_groups.items()):
            summary = summarize_rows(group_rows)
            lines.append(
                f"- {category}｜{sub_category}：{summary['count']} 道；"
                f"题干 {summary['stem']['p25']}/{summary['stem']['p50']}/{summary['stem']['p75']}。"
            )
        lines.append("")

    excluded = [
        row
        for row in rows
        if assignments[row["external_id"]]["status"] == "excluded"
    ]
    if excluded:
        lines.extend(["## 排除清单", ""])
        for row in excluded:
            note = assignments[row["external_id"]]["note"] or "不宜作为生成范本"
            lines.append(f"- `{markdown_escape(row['external_id'])}`：{markdown_escape(note)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def compute_corpus_hash(
    rows: list[sqlite3.Row], assignments: dict[str, dict[str, str]]
) -> str:
    pieces = [
        f"{row['external_id']}:{content_hash(row)}:{assignments[row['external_id']]['status']}"
        for row in sorted(rows, key=lambda item: item["external_id"])
    ]
    return hashlib.sha256("\n".join(pieces).encode("utf-8")).hexdigest()


def current_state(
    conn: sqlite3.Connection, rows: list[sqlite3.Row] | None = None
) -> dict[str, Any]:
    rows = rows if rows is not None else load_rows(conn)
    ledger = {
        row["external_id"]: row
        for row in conn.execute("SELECT * FROM reference_digest_items")
    }
    current: list[sqlite3.Row] = []
    pending: list[str] = []
    statuses: Counter[str] = Counter()
    for row in rows:
        item = ledger.get(row["external_id"])
        if (
            not item
            or item["digest_version"] != DIGEST_VERSION
            or item["content_hash"] != content_hash(row)
        ):
            pending.append(row["external_id"])
            continue
        current.append(row)
        statuses[item["status"]] += 1
    stale = [external_id for external_id in ledger if external_id not in {r["external_id"] for r in rows}]
    return {
        "marker": DIGEST_VERSION,
        "total": len(rows),
        "current": len(current),
        "accepted": statuses["accepted"],
        "holdout": statuses["holdout"],
        "excluded": statuses["excluded"],
        "pending": len(pending),
        "pending_ids": pending,
        "stale": len(stale),
        "stale_ids": stale,
        "generation_uses": sum(
            int(item["generation_uses"] or 0) for item in ledger.values()
        ),
        "evaluation_uses": sum(
            int(item["evaluation_uses"] or 0) for item in ledger.values()
        ),
    }


def artifacts_current(rows: list[sqlite3.Row], output_dir: Path) -> bool:
    profile_path = output_dir / PROFILE_NAME
    status_path = output_dir / STATUS_NAME
    principles_path = output_dir / PRINCIPLES_NAME
    if (
        not profile_path.is_file()
        or not status_path.is_file()
        or not principles_path.is_file()
        or not CANONICAL_GUIDE.is_file()
    ):
        return False
    try:
        status_doc = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    assignments = choose_assignments(rows)
    return (
        status_doc.get("marker") == DIGEST_VERSION
        and status_doc.get("corpus_hash") == compute_corpus_hash(rows, assignments)
        and status_doc.get("total") == len(rows)
        and principles_path.read_bytes() == CANONICAL_GUIDE.read_bytes()
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def build_digest(conn: sqlite3.Connection, output_dir: Path) -> dict[str, Any]:
    rows = load_rows(conn)
    assignments = choose_assignments(rows)
    corpus_hash = compute_corpus_hash(rows, assignments)
    built_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    profile = render_profile(rows, assignments, corpus_hash, built_at)
    counts = Counter(item["status"] for item in assignments.values())
    status_doc = {
        "marker": DIGEST_VERSION,
        "built_at": built_at,
        "corpus_hash": corpus_hash,
        "total": len(rows),
        "accepted": counts["accepted"],
        "holdout": counts["holdout"],
        "excluded": counts["excluded"],
        "pending": 0,
        "profile": str(output_dir / PROFILE_NAME),
    }

    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = {
            row["external_id"]: row
            for row in conn.execute("SELECT * FROM reference_digest_items")
        }
        live_ids = {row["external_id"] for row in rows}
        for stale_id in set(existing) - live_ids:
            conn.execute(
                "DELETE FROM reference_digest_items WHERE external_id = ?", (stale_id,)
            )

        for row in rows:
            external_id = row["external_id"]
            assignment = assignments[external_id]
            digest_hash = content_hash(row)
            old = existing.get(external_id)
            values = (
                digest_hash,
                DIGEST_VERSION,
                assignment["status"],
                assignment["source_tier"],
                assignment["note"] or None,
                external_id,
            )
            changed = (
                not old
                or old["content_hash"] != digest_hash
                or old["digest_version"] != DIGEST_VERSION
                or old["status"] != assignment["status"]
                or old["source_tier"] != assignment["source_tier"]
                or (old["note"] or "") != (assignment["note"] or "")
            )
            if not old:
                conn.execute(
                    """
                    INSERT INTO reference_digest_items (
                      content_hash, digest_version, status, source_tier, note, external_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            elif changed:
                conn.execute(
                    """
                    UPDATE reference_digest_items
                       SET content_hash = ?, digest_version = ?, status = ?,
                           source_tier = ?, note = ?, processed_at = CURRENT_TIMESTAMP
                     WHERE external_id = ?
                    """,
                    values,
                )

        # 只有提纲和状态文件均成功落盘，才提交逐题“已内化”标记。
        atomic_write(
            output_dir / PRINCIPLES_NAME,
            CANONICAL_GUIDE.read_text(encoding="utf-8"),
        )
        atomic_write(output_dir / PROFILE_NAME, profile)
        atomic_write(
            output_dir / STATUS_NAME,
            json.dumps(status_doc, ensure_ascii=False, indent=2) + "\n",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return status_doc


def tag_parts(tag: str) -> list[str]:
    return [part for part in re.split(r"[-/—>＞]+", compact_text(tag)) if part]


def match_level(
    row: sqlite3.Row,
    category: str,
    sub_category: str,
    target_tag: str,
) -> int:
    if category and row["category"] != category:
        return -1
    if sub_category and row["sub_category"] and row["sub_category"] != sub_category:
        return -1
    row_tags = [str(tag) for tag in effective_tags(row) if str(tag).strip()]
    if target_tag and category == "言语理解与表达":
        def yanyu_family(value: str) -> str:
            if "逻辑填空" in value:
                if any(word in value for word in ("词语辨析", "词的辨析", "实词", "成语", "混搭")):
                    return "逻辑填空-词语"
                if any(word in value for word in ("逻辑对应", "对应关系", "解释说明", "转折", "并列")):
                    return "逻辑填空-对应"
                if "宏观" in value:
                    return "逻辑填空-宏观"
                return "逻辑填空-其他"
            if "语句排序" in value:
                return "语句排序"
            if any(word in value for word in ("语句填入", "语句填空", "语句衔接")):
                return "语句填入"
            if "标题" in value:
                return "标题"
            if any(word in value for word in ("下文推断", "承接叙述")):
                return "下文推断"
            if "细节" in value:
                return "细节判断"
            if "意图" in value:
                return "意图判断"
            if any(word in value for word in ("主旨", "中心理解")):
                return "主旨概括"
            return ""

        target_family = yanyu_family(target_tag)
        row_families = {yanyu_family(tag) for tag in row_tags}
        if target_family and target_family in row_families:
            return 6
        return 0
    if target_tag and sub_category in {"科学推理", "图形推理", "逻辑判断"}:
        def semantic_parts(value: str) -> list[str]:
            parts = tag_parts(value)
            if len(parts) > 1 and parts[0] == "判断推理" and parts[1] in {"科学推理", "图形推理", "逻辑判断"}:
                return parts[1:]
            return parts

        target_parts = semantic_parts(target_tag)
        best = 0
        for row_tag in row_tags:
            parts = semantic_parts(row_tag)
            if parts == target_parts:
                return 6
            common = 0
            for left, right in zip(target_parts, parts):
                if left != right:
                    break
                common += 1
            if common >= 2:
                best = max(best, 5 if common == min(len(target_parts), len(parts)) else 4)
            elif target_parts and parts and target_parts[0] == parts[0] and set(target_parts[1:]) & set(parts[1:]):
                best = max(best, 2)
        return best
    if target_tag:
        target_canon = canonicalize(target_tag, category or row["category"] or "")
        row_canons = [canonicalize(tag, row["category"] or category or "") for tag in row_tags]
        if target_tag in row_tags or (target_canon and target_canon in row_canons):
            return 6
        target_parts = tag_parts(target_tag)
        best = 0
        for row_tag in row_tags:
            parts = tag_parts(row_tag)
            common = 0
            for left, right in zip(target_parts, parts):
                if left != right:
                    break
                common += 1
            if common == min(len(target_parts), len(parts)) and common >= 2:
                best = max(best, 5)
            elif common >= 2:
                best = max(best, 4)
            elif set(target_parts[1:]) & set(parts[1:]):
                best = max(best, 2)
        if best:
            return best
    if sub_category and row["sub_category"] == sub_category:
        return 3
    if category and row["category"] == category:
        return 1
    return 0


def has_images(row: sqlite3.Row | dict[str, Any]) -> bool:
    return bool(image_paths(row))


def row_for_context(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    def with_local(paths: list[Any]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for value in paths:
            public = str(value)
            local = public_image_to_local(public)
            out.append(
                {
                    "public": public,
                    "local": str(local) if local is not None else "",
                }
            )
        return out

    options = []
    for option in json_list(row["options"]):
        if not isinstance(option, dict):
            continue
        options.append(
            {
                "key": option.get("key"),
                "text": option.get("text") or "",
                "images": with_local(json_list(option.get("images"))),
            }
        )
    return {
        "external_id": row["external_id"],
        "category": row["category"],
        "sub_category": row["sub_category"],
        "question_type": row["question_type"],
        "stem": row["content"],
        "stem_images": with_local(json_list(row["stem_images"])),
        "options": options,
        "answer": row["correct_answer"],
        "difficulty": row["difficulty"],
        "tags": effective_tags(row),
        "source": row["source"],
        "year": row["year"],
        "region": row["region"],
        "source_tier": source_tier(row),
    }
    if isinstance(row, dict) and row.get("legacy"):
        out["material_ref"] = row.get("material_ref") or None
        out["material"] = row.get("material") or ""
        out["reference_source"] = "data/zhenti fallback"
    return out


def select_context(
    conn: sqlite3.Connection,
    *,
    role: str,
    category: str,
    sub_category: str,
    target_tag: str,
    count: int,
    image_mode: str,
) -> dict[str, Any]:
    rows = load_rows(conn)
    ledger = {
        row["external_id"]: row
        for row in conn.execute(
            "SELECT * FROM reference_digest_items WHERE digest_version = ?",
            (DIGEST_VERSION,),
        )
    }
    wanted_status = "accepted" if role == "generate" else "holdout"
    use_column = "generation_uses" if role == "generate" else "evaluation_uses"
    candidates: list[
        tuple[sqlite3.Row | dict[str, Any], sqlite3.Row | dict[str, Any], int, float]
    ] = []
    selection_source = "reference_questions"

    for row in rows:
        item = ledger.get(row["external_id"])
        if (
            not item
            or item["status"] != wanted_status
            or item["content_hash"] != content_hash(row)
        ):
            continue
        if image_mode == "yes" and not has_images(row):
            continue
        if image_mode == "no" and has_images(row):
            continue
        if blocked_gd_reference(row):
            continue
        level = match_level(row, category, sub_category, target_tag)
        minimum_level = 2 if target_tag else (3 if sub_category else (1 if category else 0))
        if level < minimum_level:
            continue
        source_score = SOURCE_TIER_SCORE.get(item["source_tier"], 0)
        year = int(row["year"]) if row["year"] else 0
        uses = int(item[use_column] or 0)
        # 相关性始终优先；同等相关时近期/广东真题优先，反复用过后轮换到其他真题。
        rank = level * 1000 + source_score * 35 + min(year, 2030) - uses * 18
        candidates.append((row, item, level, rank))

    if not candidates:
        selection_source = "data/zhenti fallback"
        legacy_uses: Counter[str] = Counter()
        for run in conn.execute(
            """
            SELECT reference_ids FROM reference_context_runs
             WHERE role = ? AND digest_version = ?
            """,
            (role, DIGEST_VERSION),
        ):
            for external_id in json_list(run["reference_ids"]):
                if str(external_id).startswith("legacy:"):
                    legacy_uses[str(external_id)] += 1
        for row in load_legacy_rows(category):
            if image_mode == "yes":
                continue
            if blocked_gd_reference(row):
                continue
            level = match_level(row, category, sub_category, target_tag)
            minimum_level = 2 if target_tag else (3 if sub_category else 1)
            if level < minimum_level:
                continue
            is_holdout = int(content_hash(row)[:8], 16) % 100 < 15
            if (role == "evaluate") != is_holdout:
                continue
            tier = source_tier(row)
            uses = legacy_uses[row["external_id"]]
            item = {
                "source_tier": tier,
                "generation_uses": uses if role == "generate" else 0,
                "evaluation_uses": uses if role == "evaluate" else 0,
            }
            source_score = SOURCE_TIER_SCORE.get(tier, 0)
            year = int(row["year"]) if row["year"] else 0
            rank = level * 1000 + source_score * 35 + min(year, 2030) - uses * 18
            candidates.append((row, item, level, rank))

    if not candidates:
        raise RuntimeError("没有匹配的已内化参考题；请检查 category/tag 或先运行 build")

    chosen = pick_mixed(candidates, role, count)
    chosen_rows = [item[0] for item in chosen]
    chosen_ids = [row["external_id"] for row in chosen_rows]
    context_id = f"refctx-{uuid.uuid4().hex}"
    target = {
        "category": category or None,
        "sub_category": sub_category or None,
        "tag": target_tag or None,
        "image_mode": image_mode,
    }

    conn.execute("BEGIN IMMEDIATE")
    try:
        placeholders = ",".join("?" for _ in chosen_ids)
        conn.execute(
            f"""
            UPDATE reference_digest_items
               SET {use_column} = {use_column} + 1,
                   last_used_at = CURRENT_TIMESTAMP
             WHERE external_id IN ({placeholders})
            """,
            chosen_ids,
        )
        conn.execute(
            """
            INSERT INTO reference_context_runs (
              context_id, role, digest_version, target, reference_ids
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                context_id,
                role,
                DIGEST_VERSION,
                json.dumps(target, ensure_ascii=False),
                json.dumps(chosen_ids, ensure_ascii=False),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    same_level_rows = [
        row
        for row, _item, level, _rank in candidates
        if level == max(item[2] for item in candidates)
    ]
    return {
        "marker": DIGEST_VERSION,
        "context_id": context_id,
        "role": role,
        "target": target,
        "selection": {
            "selected": len(chosen_rows),
            "candidate_count": len(candidates),
            "source": selection_source,
            "rule": "省考定题面（最多3道）+ 国考垫高（1–2道）；evaluate 优先省考 holdout；定义判断/类比不入包",
        },
        "style_profile": summarize_rows(same_level_rows or chosen_rows),
        "reference_ids": chosen_ids,
        "references": [row_for_context(row) for row in chosen_rows],
        "usage": (
            "只学习题型结构、信息边界、设问和干扰项关系；不得复用连续措辞、实体、数字或人物关系。"
            if role == "generate"
            else "仅供独立质量审查与真题风格对照，不得回传给命题者改写成模板。"
        ),
    }


def practiced_ids(conn: sqlite3.Connection) -> set[str]:
    try:
        return {
            str(row[0])
            for row in conn.execute("SELECT external_id FROM questions")
            if row[0]
        }
    except sqlite3.Error:
        return set()


def as_practice_question(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = row_for_context(row)
    return {
        "external_id": item["external_id"],
        "origin": "zhenti",
        "category": item["category"],
        "sub_category": item["sub_category"],
        "question_type": item["question_type"] or "single",
        "stem": item["stem"],
        "stem_images": [img["public"] for img in item["stem_images"] if img.get("public")],
        "options": [
            {"key": option["key"], "text": option["text"], "images": []}
            for option in item["options"]
        ],
        "answer": item["answer"],
        "difficulty": item["difficulty"],
        "tags": item["tags"],
        "source": item["source"],
        "year": item["year"],
        "region": item["region"],
    }


def pick_practice(
    conn: sqlite3.Connection,
    *,
    category: str,
    sub_category: str,
    target_tag: str,
    count: int,
) -> dict[str, Any]:
    rows = load_rows(conn)
    ledger = {
        row["external_id"]: row
        for row in conn.execute(
            "SELECT * FROM reference_digest_items WHERE digest_version = ?",
            (DIGEST_VERSION,),
        )
    }
    seen = practiced_ids(conn)
    candidates: list[tuple[Any, Any, int, float]] = []
    for row in rows:
        item = ledger.get(row["external_id"])
        if not item or item["status"] != "accepted":
            continue
        if blocked_gd_reference(row):
            continue
        level = match_level(row, category, sub_category, target_tag)
        minimum = 4 if target_tag else (3 if sub_category else 1)
        if level < minimum:
            continue
        year = int(row["year"]) if row["year"] else 0
        uses = int(item["generation_uses"] or 0)
        used = 500 if row["external_id"] in seen else 0
        rank = (
            level * 1000
            + SOURCE_TIER_SCORE.get(item["source_tier"], 0) * 35
            + min(year, 2030)
            - uses * 18
            - used
        )
        candidates.append((row, item, level, rank))
    chosen = pick_mixed(candidates, "evaluate", count)
    chosen_rows = [item[0] for item in chosen]
    chosen_ids = [row["external_id"] for row in chosen_rows]
    if chosen_ids:
        placeholders = ",".join("?" for _ in chosen_ids)
        conn.execute(
            f"""
            UPDATE reference_digest_items
               SET last_used_at = CURRENT_TIMESTAMP
             WHERE external_id IN ({placeholders})
            """,
            chosen_ids,
        )
        conn.commit()
    return {
        "marker": DIGEST_VERSION,
        "role": "practice",
        "target": {
            "category": category or None,
            "sub_category": sub_category or None,
            "tag": target_tag or None,
        },
        "selected": len(chosen_rows),
        "reference_ids": chosen_ids,
        "questions": [as_practice_question(row) for row in chosen_rows],
    }


def ensure_current(
    conn: sqlite3.Connection, output_dir: Path, auto_refresh: bool
) -> dict[str, Any]:
    rows = load_rows(conn)
    state = current_state(conn, rows)
    stale_artifacts = not artifacts_current(rows, output_dir)
    if state["pending"] or state["stale"] or stale_artifacts:
        if not auto_refresh:
            raise RuntimeError(
                f"参考库有 {state['pending']} 道待处理、{state['stale']} 条失效标记，"
                f"提纲需重建={stale_artifacts}，请先运行 build"
            )
        print(
            f"[reference-style] 检测到 {state['pending']} 道新增/修改题，"
            f"提纲需重建={stale_artifacts}，自动增量内化",
            file=sys.stderr,
        )
        build_digest(conn, output_dir)
        state = current_state(conn)
    return state


def print_status(state: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    print(state["marker"])
    print(
        f"总题数 {state['total']}｜已内化 {state['current']}｜"
        f"生成参考 {state['accepted']}｜评测留出 {state['holdout']}｜"
        f"排除 {state['excluded']}｜待处理 {state['pending']}"
    )
    print(
        f"实际选用次数：生成 {state['generation_uses']}｜评测 {state['evaluation_uses']}"
    )
    if "artifacts_current" in state:
        print(f"提纲文件：{'当前版本' if state['artifacts_current'] else '需要重建'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=Path(os.environ.get("EXAM_DB", DEFAULT_DB))
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("REFERENCE_STYLE_DIR", DEFAULT_OUTPUT_DIR)),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="重建风格数据档并标记新增/修改题")
    status_parser = sub.add_parser("status", help="查看内化与实际选用状态")
    status_parser.add_argument("--json", action="store_true")

    context_parser = sub.add_parser("context", help="按目标组装生成或评测参考包")
    context_parser.add_argument("--role", choices=("generate", "evaluate"), required=True)
    context_parser.add_argument("--category", default="")
    context_parser.add_argument("--sub-category", default="")
    context_parser.add_argument("--tag", default="")
    context_parser.add_argument("--count", type=int, default=5)
    context_parser.add_argument("--images", choices=("any", "yes", "no"), default="any")
    context_parser.add_argument("--no-refresh", action="store_true")
    context_parser.add_argument("--output", type=Path)

    practice_parser = sub.add_parser("practice", help="按知识点抽真题进 AI 练题（默认 2 道）")
    practice_parser.add_argument("--category", default="")
    practice_parser.add_argument("--sub-category", default="")
    practice_parser.add_argument("--tag", default="")
    practice_parser.add_argument("--count", type=int, default=2)
    practice_parser.add_argument("--no-refresh", action="store_true")
    practice_parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.db.exists():
        print(f"数据库不存在：{args.db}", file=sys.stderr)
        return 2
    conn = connect(args.db)
    try:
        if args.command == "build":
            result = build_digest(conn, args.output_dir)
            print(result["marker"])
            print(
                f"已处理 {result['total']}｜生成参考 {result['accepted']}｜"
                f"评测留出 {result['holdout']}｜排除 {result['excluded']}｜待处理 0"
            )
            print(f"提纲数据：{result['profile']}")
            return 0

        if args.command == "status":
            rows = load_rows(conn)
            state = current_state(conn, rows)
            state["artifacts_current"] = artifacts_current(rows, args.output_dir)
            print_status(state, args.json)
            return 0

        if args.command == "context":
            if args.count < 1 or args.count > 8:
                print("--count 必须是 1~8", file=sys.stderr)
                return 2
            ensure_current(conn, args.output_dir, not args.no_refresh)
            result = select_context(
                conn,
                role=args.role,
                category=compact_text(args.category),
                sub_category=compact_text(args.sub_category),
                target_tag=compact_text(args.tag),
                count=args.count,
                image_mode=args.images,
            )
            output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            if args.output:
                atomic_write(args.output, output)
                print(
                    json.dumps(
                        {
                            "marker": result["marker"],
                            "context_id": result["context_id"],
                            "role": result["role"],
                            "reference_ids": result["reference_ids"],
                            "output": str(args.output),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(output, end="")
            return 0

        if args.command == "practice":
            if args.count < 1 or args.count > 4:
                print("--count 必须是 1~4", file=sys.stderr)
                return 2
            if not compact_text(args.tag) and not compact_text(args.category):
                print("practice 需要 --tag 或 --category", file=sys.stderr)
                return 2
            ensure_current(conn, args.output_dir, not args.no_refresh)
            result = pick_practice(
                conn,
                category=compact_text(args.category),
                sub_category=compact_text(args.sub_category),
                target_tag=compact_text(args.tag),
                count=args.count,
            )
            output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            if args.output:
                atomic_write(args.output, output)
                print(
                    json.dumps(
                        {
                            "selected": result["selected"],
                            "reference_ids": result["reference_ids"],
                            "output": str(args.output),
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                print(output, end="")
            return 0
    finally:
        conn.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

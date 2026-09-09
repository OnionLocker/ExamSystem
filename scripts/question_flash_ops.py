#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flash 出题运维：读打回原因和坏图，只改必须改的字段，不重写整卷。"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Callable

from figure_flash_qa import MODEL, BASE_URL, api_key, image_part, parse_json, resize_png, response_text
from image_kinds import GRAPHIC_KIND_BY_MOVE

OPS_MAX = 1
SPLIT_RE = re.compile(r"[\n;；]")

SYSTEM = """你是公考出题运维，不是命题员。题已被质检打回。
根据题干、选项、打回原因和（如有）预览图，只决定下一步，不要重写整卷。

动作只能是这两个：
- patch：覆盖必须改的字段。可写 stem / options / analysis / figure_contract / stem_images / has_stem_image
- regen：考点或装置本身出不了合格题，整题作废，必须换考点

figure_contract 只能是：
{"kind":"circuit","must_show":["R1","A"],"must_not":["木块"],"must_derive":["干路电流最大"]}
kind 必须能对上题干考点。must_show 必须是题干里已有的标号。must_derive 禁止画在图上。

错项若有「一定是/必然/唯一」，只改该错项，不要改正确答案。
题干用甲乙则解析/选项不得改用 ρ_A、液体A。

纯文字题若被指出不需要图片，必须把 stem_images 设为 []、has_stem_image 设为 false，并清除 figure。

只输出一个 JSON 对象：
{"action":"patch","stem":null,"options":null,"analysis":null,"figure_contract":null,"stem_images":null,"has_stem_image":null,"clear_figure":false,"reason":"中文短句"}
不改的字段用 null。options 若改必须仍是 A-D 四项。
"""


def is_graphic(question: dict) -> bool:
    return str(question.get("exam_move") or "") in GRAPHIC_KIND_BY_MOVE


def issue_lines(error: str, qid: str = "") -> list[str]:
    lines = []
    for part in SPLIT_RE.split(str(error or "")):
        text = part.strip()
        if not text:
            continue
        if qid and qid not in text and not text.startswith("Flash") and "FIGURE_REGEN" not in text:
            if "图上" not in text and "giveaway" not in text and "notation" not in text:
                continue
        lines.append(text[:240])
    return list(dict.fromkeys(lines))[:8]


def local_issues(question: dict) -> list[str]:
    from quality_orchestrator import local_quality_issues

    return [str(item) for item in local_quality_issues(question) if item]


def stem_png(question: dict, batch_dir: Path | None) -> Path | None:
    if not batch_dir:
        return None
    for rel in question.get("stem_images") or []:
        path = Path(batch_dir) / str(rel)
        if path.is_file():
            return path
    return None


def parse_decision(raw) -> dict:
    if isinstance(raw, dict):
        value = raw
    else:
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        match = re.search(r"\{[\s\S]*\}", text)
        value = json.loads(match.group(0) if match else text)
    action = str(value.get("action") or "patch").strip().lower()
    if action not in {"patch", "regen"}:
        action = "patch"
    options = value.get("options")
    if not isinstance(options, list):
        options = None
    contract = value.get("figure_contract")
    if not isinstance(contract, dict):
        contract = None
    stem = value.get("stem")
    analysis = value.get("analysis")
    stem_images = value.get("stem_images")
    if stem_images is not None and not isinstance(stem_images, list):
        stem_images = []
    return {
        "action": action,
        "stem": None if stem in (None, "") else str(stem),
        "options": options,
        "analysis": None if analysis in (None, "") else str(analysis),
        "figure_contract": contract,
        "stem_images": stem_images,
        "has_stem_image": value.get("has_stem_image"),
        "clear_figure": bool(value.get("clear_figure")),
        "reason": str(value.get("reason") or "").strip(),
    }


def apply_decision(decision: dict, question: dict) -> dict:
    row = dict(question)
    if str(decision.get("action") or "") == "regen":
        row["_ops_regen"] = True
        return row
    if decision.get("stem"):
        row["stem"] = decision["stem"]
    if decision.get("analysis"):
        row["analysis"] = decision["analysis"]
        row["explanation"] = decision["analysis"]
    if decision.get("options"):
        parsed = []
        raw = decision["options"]
        if isinstance(raw, dict):
            raw = [{"key": key, "text": value} for key, value in raw.items()]
        for item in raw or []:
            if isinstance(item, dict):
                parsed.append({"key": str(item.get("key") or ""), "text": str(item.get("text") or "")})
        if len(parsed) == 4:
            row["options"] = parsed
    if decision.get("figure_contract"):
        old = dict(row.get("figure_contract") or {}) if isinstance(row.get("figure_contract"), dict) else {}
        old.update(decision["figure_contract"])
        row["figure_contract"] = old
        kind = str(old.get("kind") or "").strip()
        if kind:
            row["figure_template"] = kind
            fig = dict(row.get("figure") or {}) if isinstance(row.get("figure"), dict) else {}
            fig["kind"] = kind
            row["figure"] = fig
    if decision.get("stem_images") is not None:
        row["stem_images"] = [str(item) for item in decision["stem_images"] if str(item)]
    if decision.get("has_stem_image") is not None:
        row["has_stem_image"] = bool(decision["has_stem_image"])
    if decision.get("clear_figure"):
        row.pop("figure", None)
        row.pop("figure_contract", None)
        row.pop("figure_template", None)
    if not row.get("stem_images"):
        row.pop("has_stem_image", None)
    row.pop("_ops_regen", None)
    return row


def decide(
    question: dict,
    issues: list[str],
    *,
    image_path: Path | None = None,
    caller: Callable | None = None,
) -> dict:
    payload = {
        "external_id": question.get("external_id") or "",
        "stem": question.get("stem") or "",
        "tags": list(question.get("tags") or []),
        "options": question.get("options") or [],
        "answer": question.get("answer") or "",
        "analysis": str(question.get("analysis") or question.get("explanation") or "")[:400],
        "figure_contract": question.get("figure_contract") or {},
        "figure_template": question.get("figure_template") or "",
        "issues": [str(item) for item in issues[:8]],
    }
    if caller is not None:
        return parse_decision(caller(SYSTEM, payload))
    if os.environ.get("QUESTION_FLASH_OPS", "1") == "0":
        return {"action": "regen", "stem": None, "options": None, "analysis": None, "figure_contract": None, "reason": "ops off"}
    user: list | str
    if image_path and Path(image_path).is_file():
        user = [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)},
            {"type": "text", "text": "这是被打回的题图预览，只作对照："},
            image_part(resize_png(Path(image_path), 480)),
        ]
    else:
        user = json.dumps(payload, ensure_ascii=False)
    body = json.dumps(
        {
            "model": MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        chat = json.loads(response.read().decode("utf-8"))
    return parse_decision(parse_json(response_text(chat)))


def patch_one(
    question: dict,
    issues: list[str],
    *,
    image_path: Path | None = None,
    caller: Callable | None = None,
) -> dict:
    if is_graphic(question) or not issues:
        return {"question": question, "applied": False, "regen": False, "decision": {}}
    try:
        decision = decide(question, issues, image_path=image_path, caller=caller)
    except Exception as exc:
        return {
            "question": question,
            "applied": False,
            "regen": True,
            "decision": {"action": "regen", "reason": f"Flash出题运维失败：{exc}"},
        }
    before = {key: question.get(key) for key in ("stem", "options", "analysis", "explanation", "figure_contract", "figure", "figure_template", "stem_images", "has_stem_image")}
    row = apply_decision(decision, question)
    after = {key: row.get(key) for key in before}
    changed = before != after
    if not changed and str(decision.get("action") or "") == "patch":
        decision = {**decision, "action": "regen", "reason": "运维修补未改变任何字段，转整题重出"}
        row = dict(question)
        row["_ops_regen"] = True
    regen = bool(row.get("_ops_regen")) or str(decision.get("action") or "") == "regen"
    return {"question": row, "applied": changed and not regen, "regen": regen, "decision": decision}


def preflight_draft(
    draft: dict,
    batch_dir: Path | None = None,
    error: str | None = None,
    *,
    only_ids: list[str] | None = None,
    caller: Callable | None = None,
) -> dict:
    questions = list(draft.get("questions") or [])
    wanted = set(only_ids or [])
    patched: list[str] = []
    need_gemini: list[str] = []
    out = []
    for question in questions:
        if not isinstance(question, dict):
            out.append(question)
            continue
        qid = str(question.get("external_id") or "")
        if wanted and qid not in wanted:
            out.append(question)
            continue
        if is_graphic(question):
            out.append(question)
            continue
        issues = local_issues(question) + issue_lines(error or "", qid)
        if not issues:
            out.append(question)
            continue
        result = patch_one(question, issues, image_path=stem_png(question, batch_dir), caller=caller)
        row = result["question"]
        out.append(row)
        if result["regen"] or local_issues(row):
            need_gemini.append(qid)
        elif result["applied"]:
            patched.append(qid)
        else:
            need_gemini.append(qid)
    draft["questions"] = out
    block = []
    for qid in need_gemini:
        block.append(f"{qid}: 出题运维要求改题")
    return {
        "patched": patched,
        "need_gemini": need_gemini,
        "block_render": bool(need_gemini) and not error,
        "error": "\n".join(block),
    }


def issue_brief(error: str) -> str:
    keep = []
    for part in SPLIT_RE.split(str(error or "")):
        text = part.strip()
        if not text:
            continue
        if any(token in text for token in ("图上", "FIGURE_REGEN", "giveaway", "notation", "Flash看图", "像素", "出题运维")):
            keep.append(text[:240])
    if not keep:
        return ""
    return "# 本题失败原文，必须对着改，不要只看 class。\n- " + "\n- ".join(keep[:12])

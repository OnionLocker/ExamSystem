#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flash draw ops: pick render_kind / fallback / regen. Do not draw lines."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Callable

from draw_fallback import apply_fallback
from draw_tools import render_kind
from figure_flash_qa import MODEL, BASE_URL, api_key, parse_json, response_text
from program_figure import is_program_kind

OPS_MAX = 2
AVAILABLE = (
    "circuit", "lever", "tank", "force", "pulley",
    "front", "breeze", "earth", "contour", "food", "pedigree", "reflex",
    "cube_net", "views", "section", "section_oblique", "section_abc_quiz",
)

SYSTEM = """你是公��出图运维，不是画图员��图已经被质棢�打回〄1�7
根据题干和打回原因，只决定下丢�步，不要描述怎么画线〄1�7

动作只能是这三个＄1�7
- render_kind：换丢�个能画出来的程序图种，kind 必须圄1�7 available_kinds 里，且能对上题干
- fallback：题干仍是原考点，用安全程序兜底重画
- regen：题干本身没法画出可解题图（考点和图种冲突��必须出现的装置画不出来），必须改题干重凄1�7

禁止反复选择已经试过且失败的 kind〄1�7
只输出一丄1�7 JSON 对象＄1�7
{"action":"render_kind","kind":"circuit","params":{},"reason":"中文短句"}
"""


def parse_decision(raw) -> dict:
    if isinstance(raw, dict):
        value = raw
    else:
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        match = re.search(r"\{[\s\S]*\}", text)
        value = json.loads(match.group(0) if match else text)
    action = str(value.get("action") or "fallback").strip().lower()
    if action not in {"render_kind", "fallback", "regen"}:
        action = "fallback"
    kind = str(value.get("kind") or "").strip()
    params = value.get("params") if isinstance(value.get("params"), dict) else {}
    reason = str(value.get("reason") or "").strip()
    return {"action": action, "kind": kind, "params": params, "reason": reason}


def decide(
    request: dict,
    issues: list[str],
    tried: list[str],
    *,
    caller: Callable | None = None,
) -> dict:
    payload = {
        "stem": request.get("stem") or "",
        "tags": list(request.get("tags") or []),
        "kind_hint": request.get("kind_hint") or "",
        "must_show": list(request.get("must_show") or []),
        "issues": [str(item) for item in issues[:8]],
        "tried_kinds": [str(item) for item in tried if item],
        "available_kinds": list(AVAILABLE),
    }
    if caller is not None:
        return parse_decision(caller(SYSTEM, payload))
    if os.environ.get("DRAW_FLASH_OPS", "1") == "0":
        return {"action": "fallback", "kind": "", "params": {}, "reason": "ops off"}
    body = json.dumps(
        {
            "model": MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
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


def apply_decision(decision: dict, request: dict, dest: Path, renderer=None) -> dict:
    action = str(decision.get("action") or "fallback")
    kind = str(decision.get("kind") or request.get("kind_hint") or "")
    if request.get("kind_locked") and request.get("kind_hint"):
        kind = str(request.get("kind_hint") or kind)
        if action == "regen":
            action = "render_kind"
    params = dict(request.get("params") or {})
    params.update(decision.get("params") or {})
    if action == "regen":
        return {
            "ok": False,
            "regen": True,
            "kind": kind,
            "issues": [decision.get("reason") or "题干无法出图，需改题"],
        }
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if action == "render_kind" and kind and is_program_kind(kind):
        result = render_kind(kind, params, dest, renderer)
        return {**result, "ops": decision, "regen": False}
    fallback = apply_fallback(request, dest, renderer)
    return {**fallback, "ops": decision, "regen": False}

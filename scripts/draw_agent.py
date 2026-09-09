#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw agent: render_kind / compose / inspect. Locked kinds skip compose."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from draw_contract import normalize_request, request_from_question, result_ok
from draw_fallback import apply_fallback
from figure_flash_ops import OPS_MAX, apply_decision, decide
from draw_tools import compose_svg, inspect_figure, list_kinds, pixel_draw, render_kind
from program_figure import is_program_kind, kind_from_kepui_tag, kind_from_stem, render_program

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("DRAW_AGENT_MODEL") or os.environ.get(
    "DAILY_GEMINI_MODEL", "gemini-3.8-flash-high"
)
MAX_ROUNDS = 8
PROMPT = """You are the exam-figure drawer. DRAW_REQUEST is the only spec.

Call tools. Do not write the question. Do not put answers, must_derive, or teaching arrows on the figure.
Prefer compose_svg for this request so the figure matches THIS stem, not a generic clipart.
Use render_kind only if its params can express the same apparatus (two vessels, net+stickers, section dash, three views).
pixel_draw is last resort and never for circuits, meters, levers, tanks, or force diagrams.
must_show labels must appear as SVG text, font-size >= 22. Fill the canvas. Black-and-white line exam figure.
must_not must not appear.
If inspect reports issues, render again with different elements.
Local inspect is cheap SVG/ink checks. After it passes, Gemini Flash looks at the single iPad practice view (768x480 contain)  1�7 the sizes a reviewer actually sees. A label-only or contradictory figure will fail even if SVG tags exist.
Never emit a label-only canvas. Circuits need multiple <line> wires connecting lamps/battery/switch; pedigree needs generation <line> connectors between symbols; weather front needs <polygon> cold/warm air masses; sea-breeze needs circulation arrows. Do not stack circles/rects at (0,0).

DRAW_REQUEST:
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_kinds",
            "description": "List programmable figure families.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_kind",
            "description": "Render a known exam figure family to PNG/SVG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compose_svg",
            "description": "Compose a black-and-white line figure from primitives. Coordinates MUST be [x,y] arrays in pixels, e.g. {\"type\":\"rect\",\"x\":200,\"y\":180,\"w\":280,\"h\":260} and {\"type\":\"text\",\"p\":[340,150],\"text\":\"甲\",\"size\":28}. Do not use {x:..} objects or 0,0 placeholders. Fill most of the 1100x560 canvas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "elements": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["elements"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pixel_draw",
            "description": "Last-resort pixel image from visible facts only.",
            "parameters": {
                "type": "object",
                "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
            },
        },
    },
]


def api_key() -> str:
    key = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if key:
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("CLIPROXY_API_KEY not found")


def _json_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _tool_calls(message: dict) -> list[dict]:
    calls = message.get("tool_calls") or message.get("function_call")
    if isinstance(calls, dict):
        calls = [calls]
    rows = []
    for item in calls or []:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else item
        name = str(fn.get("name") or item.get("name") or "")
        if not name:
            continue
        rows.append({"id": str(item.get("id") or name), "name": name, "arguments": _json_args(fn.get("arguments") or item.get("arguments"))})
    if rows:
        return rows
    text = message.get("content") or ""
    if isinstance(text, list):
        text = "\n".join(str(part.get("text") or "") for part in text if isinstance(part, dict))
    text = str(text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    if not cleaned:
        return []
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, dict):
        return []
    name = str(payload.get("tool") or payload.get("name") or "")
    if name:
        return [{"id": name, "name": name, "arguments": payload.get("arguments") or payload.get("params") or {}}]
    return []


def chat(messages: list, deadline: float | None = None) -> dict:
    timeout = 120
    if deadline:
        timeout = max(40, min(180, int(deadline - time.monotonic() - 5)))
    payload = {
        "model": MODEL,
        "temperature": 0.1,
        "max_tokens": 4096,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "required",
    }
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key()}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return (data.get("choices") or [{}])[0].get("message") or {}


def _hint_kind(request: dict) -> str:
    hint = str(request.get("kind_hint") or "")
    if is_program_kind(hint):
        return hint
    tag = " ".join(request.get("tags") or [])
    return kind_from_kepui_tag(tag) or kind_from_stem(request.get("stem") or "") or hint


def _guess_params(request: dict) -> dict:
    params = dict(request.get("params") or {})
    kind = _hint_kind(request)
    if kind:
        params.setdefault("kind", kind)
    names = [token for token in request.get("must_show") or [] if token in {"甄1�7", "乄1�7"}]
    if len(names) >= 2:
        params.setdefault("names", names[:2])
    blob = " ".join(str(item) for item in request.get("must_show") or []) + str(request.get("stem") or "")
    if any(token in blob for token in ("木板", "轻绳")):
        params.setdefault("board", True)
    if kind == "circuit":
        if "R1" in blob:
            params.setdefault("left", "R1")
            params.setdefault("right", "R2" if "R2" in blob else "R2")
        if "A1" in blob:
            params.setdefault("meter", "A1")
        if "干路" in blob or re.search(r"电流表\s*A(?!\d)", blob):
            params.setdefault("main_meter", "A")
        if "电压衄1�7" not in blob and "伏特衄1�7" not in blob:
            params.setdefault("voltmeter", False)
    return params


def run_tool(name: str, args: dict, request: dict, dest: Path, renderer, pixel) -> dict:
    if name == "list_kinds":
        return list_kinds()
    if name == "render_kind":
        params = dict(request.get("params") or {})
        params.update(args.get("params") or {})
        return render_kind(str(args.get("kind") or params.get("kind") or ""), params, dest, renderer)
    if name == "compose_svg":
        return compose_svg(args.get("elements") or [], dest, int(args.get("width") or 1100), int(args.get("height") or 560), renderer)
    if name == "pixel_draw":
        facts = list(args.get("facts") or request.get("must_show") or [])
        return pixel_draw(facts, dest, pixel, str(request.get("kind_hint") or ""))
    return {"ok": False, "issues": [f"unknown tool {name}"]}


def _write_log(dest: Path, payload: dict) -> None:
    dest.with_suffix(".draw.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def draw_figure(
    request: dict,
    dest: Path,
    *,
    deadline: float | None = None,
    renderer: Callable | None = None,
    pixel_renderer: Callable | None = None,
    llm: Callable | None = None,
    batch_dir: Path | None = None,
) -> dict:
    request = normalize_request(request)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    renderer = renderer or render_program
    inspect_root = batch_dir or dest.parent
    kind = _hint_kind(request)
    params = _guess_params(request)
    rounds = 0
    agent = False

    if kind and is_program_kind(kind) and os.environ.get("DRAW_AGENT_FORCE", "0") != "1":
        render_kind(kind, params, dest, renderer)
        checked = inspect_figure(request, dest, inspect_root, vision=False)
        if checked.get("stub"):
            return result_ok(dest, kind, [], {"agent": False, "rounds": 0, "stub": True})
        if checked["ok"]:
            out = result_ok(dest, kind, [], {"agent": False, "rounds": 0})
            _write_log(dest, out)
            return out
        first_issues = checked.get("issues") or []
    else:
        first_issues = ["no program kind; need agent"]

    use_llm = os.environ.get("DRAW_AGENT", "1") != "0"

    messages = [{"role": "user", "content": PROMPT + json.dumps(request, ensure_ascii=False)}]
    chat_fn = llm or chat
    last_issues = first_issues
    last_kind = kind
    render_fails = 0
    flash_used = 0
    used_fallback = False
    FLASH_MAX = 2

    def check(vision: bool) -> dict:
        return inspect_figure(request, dest, inspect_root, vision=vision)

    def check_with_flash(*, allow_skip: bool = False) -> dict:
        # ponytail: local inspect only; Flash ops decides the next draw
        return check(False)

    tried_kinds = [k for k in [kind] if k]
    ops_used = 0

    def try_ops(issues: list[str], *, ops_fn=None) -> dict | None:
        nonlocal last_kind, last_issues, ops_used
        if os.environ.get("DRAW_FLASH_OPS", "1") == "0":
            return try_fallback("; ".join(issues))
        if ops_used >= OPS_MAX:
            return None
        ops_used += 1
        decide_fn = ops_fn or decide
        try:
            decision = decide_fn(request, issues, tried_kinds)
        except Exception as exc:
            last_issues = [f"Flash运维失败：{exc}"]
            return try_fallback("; ".join(issues))
        applied = apply_decision(decision, request, dest, renderer)
        last_kind = str(applied.get("kind") or decision.get("kind") or last_kind)
        if last_kind:
            tried_kinds.append(last_kind)
        if applied.get("regen"):
            last_issues = list(applied.get("issues") or issues)
            out = result_ok(dest, last_kind, last_issues, {"agent": True, "rounds": rounds, "regen": True, "ops": decision})
            _write_log(dest, out)
            return out
        if not dest.is_file():
            last_issues = list(applied.get("issues") or issues)
            return None
        checked = check_with_flash(allow_skip=True)
        last_issues = checked.get("issues") or []
        if checked.get("ok"):
            out = result_ok(dest, last_kind, [], {"agent": True, "rounds": rounds, "ops": decision})
            _write_log(dest, out)
            return out
        return None

    def try_fallback(reason: str) -> dict | None:
        nonlocal last_kind, last_issues, used_fallback
        if used_fallback:
            return None
        used_fallback = True
        fallback = apply_fallback(request, dest, renderer)
        last_kind = str(fallback.get("kind") or last_kind)
        if not dest.is_file():
            last_issues = list(fallback.get("issues") or [reason])
            return None
        checked = check_with_flash(allow_skip=True)
        last_issues = checked.get("issues") or []
        if checked.get("ok"):
            out = result_ok(dest, last_kind, [], {"agent": True, "rounds": rounds, "fallback": True})
            _write_log(dest, out)
            return out
        return None

    if first_issues and dest.is_file():
        recovered = try_ops(first_issues)
        if recovered:
            if recovered.get("regen") and not recovered.get("ok"):
                raise RuntimeError("FIGURE_REGEN: " + "; ".join(recovered.get("issues") or first_issues))
            return recovered

    if request.get("kind_locked"):
        out = result_ok(dest, kind, [], {"agent": False, "rounds": rounds, "locked": True})
        _write_log(dest, out)
        return out

    if not use_llm:
        out = result_ok(dest, kind, last_issues, {"agent": False, "rounds": 0, "regen": bool(last_issues)})
        _write_log(dest, out)
        if not out["ok"]:
            raise RuntimeError("FIGURE_REGEN: " + ("; ".join(last_issues) or "figure inspect failed"))
        return out

    while rounds < MAX_ROUNDS:
        if deadline and deadline - time.monotonic() < 25:
            break
        rounds += 1
        agent = True
        try:
            message = chat_fn(messages, deadline) if chat_fn is chat else chat_fn(messages, deadline)
        except TypeError:
            message = chat_fn(messages)
        if not isinstance(message, dict):
            message = {"content": str(message)}
        messages.append(message)
        calls = _tool_calls(message)
        if not calls:
            recovered = try_ops(last_issues) or try_fallback("; ".join(last_issues))
            if recovered:
                if recovered.get("regen") and not recovered.get("ok"):
                    raise RuntimeError("FIGURE_REGEN: " + "; ".join(recovered.get("issues") or last_issues))
                return recovered
            break
        for call in calls:
            result = run_tool(call["name"], call.get("arguments") or {}, request, dest, renderer, pixel_renderer)
            last_kind = str(result.get("kind") or last_kind)
            if call["name"] in {"render_kind", "compose_svg", "pixel_draw"} and dest.is_file():
                checked = check_with_flash()
                result["inspect"] = checked
                last_issues = checked.get("issues") or []
                if checked.get("ok"):
                    out = result_ok(dest, last_kind, [], {"agent": True, "rounds": rounds, "fallback": used_fallback})
                    _write_log(dest, out)
                    return out
                render_fails += 1
                if render_fails >= 1:
                    recovered = try_ops(last_issues)
                    if recovered:
                        if recovered.get("regen") and not recovered.get("ok"):
                            raise RuntimeError("FIGURE_REGEN: " + "; ".join(recovered.get("issues") or last_issues))
                        return recovered
                    result["ops_inspect"] = {"issues": last_issues}
                    break
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        if last_issues:
            messages.append(
                {
                    "role": "user",
                    "content": "质检未过，必须再调用 compose_svg 戄1�7 render_kind 重画，不要重复原点坐标��问题："
                    + "＄1�7".join(last_issues[:6]),
                }
            )
    recovered = try_ops(last_issues) or try_fallback("; ".join(last_issues))
    if recovered:
        if recovered.get("regen") and not recovered.get("ok"):
            raise RuntimeError("FIGURE_REGEN: " + "; ".join(recovered.get("issues") or last_issues))
        return recovered
    out = result_ok(dest, last_kind, last_issues, {"agent": agent, "rounds": rounds, "fallback": used_fallback, "regen": True})
    _write_log(dest, out)
    if not out["ok"]:
        raise RuntimeError("FIGURE_REGEN: " + ("; ".join(last_issues) or "figure inspect failed"))
    return out


def _default_pixel(facts: list[str], dest: Path) -> None:
    import subprocess
    import sys

    prompt_file = dest.with_suffix(".prompt.txt")
    prompt_file.write_text("\n".join(facts), encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate-question-image.py"), "--prompt-file", str(prompt_file), "--output", str(dest)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
    finally:
        prompt_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "pixel draw failed")[-1500:])


def main() -> None:
    parser = argparse.ArgumentParser(description="Exam figure drawing agent")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stem", default="")
    parser.add_argument("--kind-hint", default="")
    parser.add_argument("--must-show", action="append", default=[])
    parser.add_argument("--module", default="")
    args = parser.parse_args()
    if args.request:
        request = json.loads(args.request.read_text(encoding="utf-8"))
    else:
        request = {
            "stem": args.stem,
            "kind_hint": args.kind_hint,
            "must_show": args.must_show,
            "module": args.module,
        }
    dest = args.output or Path(request.get("output") or "images/draw-stem.png")
    result = draw_figure(request, dest, pixel_renderer=_default_pixel)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

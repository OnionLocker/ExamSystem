#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画图服务的标准化输入 / 输出。出题侧只交事实，不锁死某一张 clipart。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from figure_qa import FACT_TOKEN_RE, PLACEHOLDER_FACTS
from program_figure import kind_from_kepui_tag

LEAK_DEFAULT = (
    "冷锋",
    "暖锋",
    "感受器",
    "传入神经",
    "神经中枢",
    "传出神经",
    "效应器",
)


def _str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in PLACEHOLDER_FACTS and text not in out:
            out.append(text)
    return out


def tokens_in(text: str) -> list[str]:
    return list(dict.fromkeys(FACT_TOKEN_RE.findall(str(text or ""))))


STEM_LABELS = ("甲", "乙", "丙", "丁", "R1", "R2", "A1", "A", "L1", "L2", "钩码", "①", "②", "③", "④", "⑤")


def contract_of(question: dict | None) -> dict:
    raw = (question or {}).get("figure_contract")
    return dict(raw) if isinstance(raw, dict) else {}


def spec_from_question(question: dict, existing: dict | None = None) -> dict:
    contract = contract_of(question)
    existing = existing if isinstance(existing, dict) else {}
    facts: list[str] = []
    for item in list(contract.get("must_show") or []) + list(existing.get("image_facts") or []):
        text = str(item or "").strip()
        if text and text not in PLACEHOLDER_FACTS and text not in facts:
            facts.append(text)
    stem = str(question.get("stem") or "")
    if "科学推理" in str(question.get("category") or ""):
        facts = [text for text in facts if text in stem]
    for token in STEM_LABELS:
        if token in stem and token not in facts:
            facts.append(token)
    only = list(contract.get("must_show") or existing.get("image_only_facts") or [])
    only = [str(item).strip() for item in only if str(item).strip() and str(item) not in PLACEHOLDER_FACTS]
    return {
        "question_id": str(question.get("external_id") or ""),
        "image_facts": facts or ["程序绘制的图形"],
        "image_only_facts": only or ["程序图形中的可见结构与标号"],
        "must_derive": [str(item) for item in (contract.get("must_derive") or existing.get("must_derive") or []) if str(item).strip()],
        "must_not": [str(item) for item in (contract.get("must_not") or []) if str(item).strip()],
        "kind": str(contract.get("kind") or (question.get("figure") or {}).get("kind") or question.get("figure_template") or ""),
    }



def normalize_request(raw: dict | None) -> dict:
    src = dict(raw or {})
    params = src.get("params") if isinstance(src.get("params"), dict) else {}
    kind = str(src.get("kind_hint") or src.get("kind") or params.get("kind") or "").strip()
    must_show = _str_list(src.get("must_show") or src.get("image_facts"))
    for token in tokens_in(src.get("stem") or ""):
        if token not in must_show:
            must_show.append(token)
    must_not = _str_list(src.get("must_not") or [])
    for item in src.get("must_derive") or []:
        text = str(item or "").strip()
        if text and text not in must_not:
            must_not.append(text)
    for leak in LEAK_DEFAULT:
        if leak in str(src.get("must_derive") or "") and leak not in must_not:
            must_not.append(leak)
    output = str(src.get("output") or src.get("file") or "").strip()
    tags = _str_list(src.get("tags"))
    locked = bool(src.get("kind_locked"))
    return {
        "question_id": str(src.get("question_id") or src.get("qid") or ""),
        "module": str(src.get("module") or ""),
        "exam_move": str(src.get("exam_move") or ""),
        "tags": tags,
        "stem": str(src.get("stem") or "").strip(),
        "must_show": must_show,
        "must_not": must_not,
        "must_derive": _str_list(src.get("must_derive")),
        "kind_hint": kind,
        "params": dict(params),
        "output": output,
        "kind_locked": locked,
        "need_dash": "虚线" in str(src.get("stem") or "") or "虚线" in " ".join(must_show),
    }


def request_from_question(
    question: dict,
    spec: dict | None,
    fig: dict | None,
    dest: Path,
    batch_dir: Path | None = None,
) -> dict:
    spec = spec if isinstance(spec, dict) else {}
    fig = fig if isinstance(fig, dict) else {}
    rel = dest.name
    if batch_dir:
        try:
            rel = str(dest.relative_to(batch_dir))
        except ValueError:
            rel = str(dest)
    contract = contract_of(question)
    built = spec_from_question(question, spec)
    return normalize_request(
        {
            "question_id": str(question.get("external_id") or ""),
            "module": str(question.get("category") or ""),
            "exam_move": str(question.get("exam_move") or ""),
            "tags": list(question.get("tags") or []),
            "stem": str(question.get("stem") or ""),
            "must_show": list(contract.get("must_show") or []) or list(built.get("image_facts") or []),
            "must_not": list(contract.get("must_not") or []),
            "must_derive": list(contract.get("must_derive") or built.get("must_derive") or []),
            "kind_hint": str(contract.get("kind") or fig.get("kind") or question.get("figure_template") or ""),
            "params": {key: value for key, value in fig.items() if key not in {"file"}},
            "output": rel,
            "kind_locked": bool(kind_from_kepui_tag(" ".join(str(item) for item in (question.get("tags") or [])))),
        }
    )


def result_ok(path: Path, kind: str, issues: list[str], extra: dict | None = None) -> dict:
    payload = {
        "ok": not issues,
        "path": str(path),
        "svg": str(path.with_suffix(".svg")) if path.with_suffix(".svg").is_file() else "",
        "kind": kind,
        "issues": list(issues),
        "agent": False,
        "rounds": 0,
    }
    if extra:
        payload.update(extra)
    return payload

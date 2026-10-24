#!/usr/bin/env python3
"""同一批次多轮闸门之间的审核记忆：已通过的题不重审、不改动。

按批次名存一份 JSON，整套闸门和单篇回修（目录不同、批次名相同）共用：
- reviews：质量审核结果，键是送审内容的哈希，内容不变才命中；
- passed：已通过整套闸门的题号 → 题面指纹，指纹变了即视为改过、自动解锁。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def store_path(batch_dir: Path) -> Path:
    base = Path(os.environ.get("QUALITY_CACHE_DIR") or ROOT / "data" / "quality-cache")
    return base / f"{Path(batch_dir).name}.json"


def fingerprint(question: dict) -> str:
    body = {
        "stem": question.get("stem"),
        "options": [{k: option.get(k) for k in ("key", "text", "images")}
                    for option in question.get("options") or [] if isinstance(option, dict)],
        "answer": str(question.get("answer") or "").strip().upper(),
        "explanation": question.get("explanation"),
    }
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"reviews": {}, "passed": {}}
    if not isinstance(data, dict):
        return {"reviews": {}, "passed": {}}
    return {"reviews": data.get("reviews") or {}, "passed": data.get("passed") or {}}


def load(batch_dir: Path) -> dict:
    return _read(store_path(batch_dir))


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def update(batch_dir: Path, reviews: dict | None = None, passed: dict | None = None,
           rejected: list[str] | None = None) -> None:
    path = store_path(batch_dir)
    try:
        with _locked(path):
            data = _read(path)
            data["reviews"].update(reviews or {})
            data["passed"].update(passed or {})
            for qid in rejected or []:
                data["passed"].pop(qid, None)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
    except OSError:
        pass


def locked_ids(batch_dir: Path, questions: list[dict]) -> set[str]:
    passed = load(batch_dir)["passed"]
    return {
        str(question.get("external_id"))
        for question in questions
        if passed.get(str(question.get("external_id"))) == fingerprint(question)
    }

"""选择能加载本仓库 better-sqlite3 的 Node。

Hermes 会把自带的 Node 26 放到 PATH 最前面。node_modules 里的原生模块是按
Node 22（NODE_MODULE_VERSION 127）编译的，和考试服务用的是同一套 ABI。
出题脚本如果直接调用 PATH 上的 node，会在读考点目录时退出。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_cached: str | None = None


def service_node() -> str:
    global _cached
    if _cached:
        return _cached
    candidates: list[str] = []
    for raw in (
        os.environ.get("EXAM_NODE", ""),
        str(Path.home() / ".local" / "bin" / "node"),
        "/usr/local/bin/node",
        "/usr/bin/node",
        shutil.which("node") or "",
    ):
        if raw and raw not in candidates:
            candidates.append(raw)
    probe = "new (require('better-sqlite3'))(':memory:')"
    errors: list[str] = []
    for raw in candidates:
        if not Path(raw).exists():
            continue
        try:
            result = subprocess.run(
                [raw, "-e", probe],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{raw}: {exc}")
            continue
        if result.returncode == 0:
            _cached = raw
            return _cached
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        errors.append(f"{raw}: {tail[-1] if tail else 'exit ' + str(result.returncode)}")
    detail = "；".join(errors) or "没有可执行的 node"
    raise RuntimeError("找不到能加载 better-sqlite3 的 Node。" + detail)

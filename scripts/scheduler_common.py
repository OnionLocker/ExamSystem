#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for daily batch and daily plan schedulers."""

from __future__ import annotations

import datetime as dt
import fcntl
import re
import os
import sqlite3
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("EXAM_DB") or ROOT / "data" / "exam.db")
TZ = ZoneInfo("Asia/Shanghai")
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_LOCKED = 75

MODULE_QUOTAS = (
    ("言语理解与表达", "yanyu", 15),
    ("判断推理", "panduan", 20),
    ("数量关系", "shuliang", 15),
    ("资料分析", "ziliao", 20),
)

DAILY_SOURCE_PREFIX = "广东省考行测"
_DAILY_BATCH_ID = re.compile(r"^daily-(\d{8})-")


def daily_source_name(module: str, plan_date: dt.date | str) -> str:
    if isinstance(plan_date, dt.date):
        compact = f"{plan_date:%Y%m%d}"
    else:
        compact = "".join(ch for ch in str(plan_date) if ch.isdigit())[:8]
    return f"{DAILY_SOURCE_PREFIX}-{module}-{compact}"


def daily_source_for_batch(batch_id: str, module: str) -> str | None:
    match = _DAILY_BATCH_ID.match(str(batch_id or ""))
    if not match or not module:
        return None
    return daily_source_name(module, match.group(1))


class AlreadyLocked(RuntimeError):
    pass


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise AlreadyLocked(str(self.path)) from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(self, *_):
        if self.handle is not None:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()


def wait_unlocked(path: Path, timeout: int, interval: float = 10) -> None:
    if timeout <= 0:
        return
    deadline = time.monotonic() + timeout
    while True:
        try:
            with FileLock(path):
                return
        except AlreadyLocked:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"waiting for {path} timed out")
            time.sleep(min(interval, remaining))


def local_today() -> dt.date:
    return dt.datetime.now(TZ).date()


def now_iso() -> str:
    return dt.datetime.now(TZ).isoformat(timespec="seconds")


# 日练难度两档，按 plan_date 隔天轮换：
#   公历序数（toordinal）为偶数的日期 → "easy"（简单），奇数 → "hard"（难），因此相邻两天必然一简单一难。
#   例：2026-09-21(偶)=简单，2026-09-22(奇)=难，2026-09-23(偶)=简单……
#   仅调节“弯子多少”，不改广东卷结构/知识点硬规则/模块配比（module-hard-rules 继续生效）。
def difficulty_tier(plan_date: "dt.date | str") -> str:
    if isinstance(plan_date, str):
        plan_date = dt.date.fromisoformat(plan_date[:10])
    return "easy" if plan_date.toordinal() % 2 == 0 else "hard"


def ensure_run_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_daily_batch_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          plan_date TEXT NOT NULL,
          module TEXT NOT NULL,
          batch_id TEXT,
          status TEXT NOT NULL DEFAULT 'scheduled',
          error TEXT,
          planned_count INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL DEFAULT 'hermes',
          generated_at TEXT,
          imported_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(plan_date, module)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_daily_batch_runs_batch "
        "ON ai_daily_batch_runs(batch_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_daily_batch_runs_status "
        "ON ai_daily_batch_runs(plan_date,status)"
    )
    conn.commit()


def new_batch_id(day: dt.date, slug: str) -> str:
    return f"daily-{day:%Y%m%d}-{slug}-{uuid.uuid4().hex[:20]}"


def reserve_runs(conn: sqlite3.Connection, day: dt.date) -> list[dict]:
    ensure_run_schema(conn)
    for module, slug, count in MODULE_QUOTAS:
        batch_id = new_batch_id(day, slug)
        while conn.execute(
            "SELECT 1 FROM ai_daily_batch_runs WHERE batch_id=?", (batch_id,)
        ).fetchone():
            batch_id = new_batch_id(day, slug)
        conn.execute(
            """
            INSERT INTO ai_daily_batch_runs(
              plan_date,module,batch_id,status,planned_count,source
            ) VALUES (?,?,?,?,?,?)
            ON CONFLICT(plan_date,module) DO NOTHING
            """,
            (
                str(day),
                module,
                batch_id,
                "scheduled",
                count,
                "daily-scheduler",
            ),
        )
    conn.commit()
    return load_runs(conn, day)


def load_runs(
    conn: sqlite3.Connection, day: dt.date, *, ensure_schema: bool = True
) -> list[dict]:
    if ensure_schema:
        ensure_run_schema(conn)
    elif not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='ai_daily_batch_runs'"
    ).fetchone():
        return []
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT plan_date,module,batch_id,status,error,planned_count,source,
               generated_at,imported_at,created_at,updated_at
          FROM ai_daily_batch_runs
         WHERE plan_date=?
         ORDER BY id
        """,
        (str(day),),
    ).fetchall()
    return [dict(row) for row in rows]


def preview_runs(day: dt.date) -> list[dict]:
    return [
        {
            "plan_date": str(day),
            "module": module,
            "batch_id": new_batch_id(day, slug),
            "status": "dry-run",
            "planned_count": count,
            "source": "daily-scheduler",
        }
        for module, slug, count in MODULE_QUOTAS
    ]


def update_run(
    conn: sqlite3.Connection,
    batch_id: str,
    status: str,
    *,
    error: str | None = None,
    generated: bool = False,
    imported: bool = False,
) -> None:
    generated_sql = ", generated_at=?" if generated else ""
    imported_sql = ", imported_at=?" if imported else ""
    values: list[str | None] = [status, error]
    if generated:
        values.append(now_iso())
    if imported:
        values.append(now_iso())
    values.append(batch_id)
    conn.execute(
        f"""
        UPDATE ai_daily_batch_runs
           SET status=?, error=?{generated_sql}{imported_sql},
               updated_at=CURRENT_TIMESTAMP
         WHERE batch_id=?
        """,
        values,
    )
    conn.commit()


def load_snapshot(conn: sqlite3.Connection) -> dict:
    from learner_snapshot import build_snapshot

    return build_snapshot(conn)

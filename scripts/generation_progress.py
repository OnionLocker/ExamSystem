#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出题进度。写库失败不影响出题。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DDL = """
CREATE TABLE IF NOT EXISTS generation_jobs (
  batch_id TEXT PRIMARY KEY,
  module TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  planned_count INTEGER NOT NULL DEFAULT 0,
  passed_count INTEGER NOT NULL DEFAULT 0,
  round_no INTEGER NOT NULL DEFAULT 0,
  stage TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  progress INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running',
  error TEXT,
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT
);
"""


def db_path() -> str:
    return os.environ.get("EXAM_DB") or str(ROOT / "data" / "exam.db")


def report(batch_id, *, module="", title="", planned=0, passed=0, round_no=0,
           stage="", detail="", progress=0, status="running", error=None) -> None:
    if not batch_id:
        return
    try:
        status = status if status in ("running", "done", "failed") else "running"
        progress = max(0, min(100, int(progress or 0)))
        conn = sqlite3.connect(db_path(), timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(DDL)
            conn.execute(
                """
                INSERT INTO generation_jobs (
                  batch_id, module, title, planned_count, passed_count, round_no,
                  stage, detail, progress, status, error, finished_at
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  CASE WHEN ? IN ('done', 'failed') THEN datetime('now') END
                )
                ON CONFLICT(batch_id) DO UPDATE SET
                  module = CASE WHEN excluded.module != '' THEN excluded.module ELSE generation_jobs.module END,
                  title = CASE WHEN excluded.title != '' THEN excluded.title ELSE generation_jobs.title END,
                  planned_count = CASE WHEN excluded.planned_count > 0 THEN excluded.planned_count ELSE generation_jobs.planned_count END,
                  passed_count = excluded.passed_count,
                  round_no = excluded.round_no,
                  stage = excluded.stage,
                  detail = excluded.detail,
                  progress = excluded.progress,
                  status = excluded.status,
                  error = excluded.error,
                  updated_at = datetime('now'),
                  finished_at = CASE
                    WHEN excluded.status IN ('done', 'failed') THEN datetime('now')
                    ELSE NULL
                  END
                """,
                (
                    str(batch_id),
                    module or "",
                    title or "",
                    int(planned or 0),
                    int(passed or 0),
                    int(round_no or 0),
                    stage or "",
                    detail or "",
                    progress,
                    status,
                    (str(error)[:600] if error else None),
                    status,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return


class Job:
    """一次出题。终态之后再写会被丢掉，避免失败覆盖已入库。"""

    def __init__(self, batch_id, *, module="", title="", planned=0):
        self.batch_id = batch_id
        self.module = module
        self.title = title
        self.planned = planned
        self.done = False

    def update(self, **kwargs):
        if self.done or not self.batch_id:
            return
        if "planned" in kwargs:
            self.planned = kwargs.pop("planned")
        status = kwargs.pop("status", "running")
        if status in ("done", "failed"):
            self.done = True
        report(
            self.batch_id,
            module=self.module,
            title=self.title,
            planned=self.planned,
            status=status,
            **kwargs,
        )

    def finish(self, **kwargs):
        self.update(**kwargs)

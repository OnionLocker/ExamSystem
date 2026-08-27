#!/usr/bin/env python3
"""reference_style.py 的最小端到端自检。"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reference_style.py"


REFERENCE_SCHEMA = """
CREATE TABLE reference_questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  sub_category TEXT NOT NULL,
  question_type TEXT NOT NULL DEFAULT 'single',
  content TEXT NOT NULL,
  stem_images TEXT,
  options TEXT,
  correct_answer TEXT NOT NULL,
  explanation TEXT,
  explanation_images TEXT,
  difficulty INTEGER NOT NULL DEFAULT 3,
  tags TEXT,
  source TEXT NOT NULL,
  year INTEGER,
  region TEXT,
  source_url TEXT,
  imported_by TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def run(db: Path, output_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--output-dir",
            str(output_dir),
            *args,
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reference-style-test-") as temp:
        root = Path(temp)
        db_path = root / "exam.db"
        output_dir = root / "style"
        conn = sqlite3.connect(db_path)
        conn.executescript(REFERENCE_SCHEMA)
        options = json.dumps(
            [
                {"key": "A", "text": "支持论点"},
                {"key": "B", "text": "无关信息"},
                {"key": "C", "text": "削弱论据"},
                {"key": "D", "text": "重复结论"},
            ],
            ensure_ascii=False,
        )
        for index in range(12):
            conn.execute(
                """
                INSERT INTO reference_questions (
                  external_id, category, sub_category, question_type, content,
                  stem_images, options, correct_answer, explanation_images,
                  difficulty, tags, source, year, region, imported_by
                ) VALUES (?, '判断推理', '逻辑判断', 'single', ?, '[]', ?, 'C',
                          '[]', 3, ?, ?, 2026, ?, 'test')
                """,
                (
                    f"ref-{index:02d}",
                    f"某项研究提出第{index}个观点。以下哪项如果为真，最能削弱上述观点？",
                    options,
                    json.dumps(["判断推理-逻辑判断-削弱论点"], ensure_ascii=False),
                    f"2026年{'广东' if index < 4 else '其他省'}公务员录用考试第{index}题",
                    "广东" if index < 4 else "浙江",
                ),
            )
        # 整题重复项应被排除，但原题仍保留。
        conn.execute(
            """
            INSERT INTO reference_questions (
              external_id, category, sub_category, question_type, content,
              stem_images, options, correct_answer, explanation_images,
              difficulty, tags, source, year, region, imported_by
            )
            SELECT 'ref-duplicate', category, sub_category, question_type, content,
                   stem_images, options, correct_answer, explanation_images,
                   difficulty, tags, '模拟重复题', year, region, 'test'
              FROM reference_questions WHERE external_id = 'ref-00'
            """
        )
        conn.commit()
        conn.close()

        run(db_path, output_dir, "build")
        status = json.loads(run(db_path, output_dir, "status", "--json").stdout)
        assert status["total"] == 13
        assert status["current"] == 13
        assert status["pending"] == 0
        assert status["excluded"] == 1
        assert status["holdout"] >= 1
        assert (output_dir / "reference-style-profile.md").exists()

        generated = json.loads(
            run(
                db_path,
                output_dir,
                "context",
                "--role",
                "generate",
                "--category",
                "判断推理",
                "--sub-category",
                "逻辑判断",
                "--tag",
                "判断推理-逻辑判断-削弱论点",
                "--count",
                "3",
            ).stdout
        )
        assert generated["role"] == "generate"
        assert generated["context_id"].startswith("refctx-")
        assert len(generated["reference_ids"]) == 3

        evaluated = json.loads(
            run(
                db_path,
                output_dir,
                "context",
                "--role",
                "evaluate",
                "--category",
                "判断推理",
                "--sub-category",
                "逻辑判断",
                "--tag",
                "判断推理-逻辑判断-削弱论点",
                "--count",
                "1",
            ).stdout
        )
        assert evaluated["role"] == "evaluate"
        assert set(evaluated["reference_ids"]).isdisjoint(generated["reference_ids"])

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE reference_questions SET content = content || '（更新）' WHERE external_id = 'ref-01'"
        )
        conn.commit()
        conn.close()
        changed = json.loads(run(db_path, output_dir, "status", "--json").stdout)
        assert changed["pending"] == 1

        # context 默认自动增量内化，修改后的题不需要人工清标记。
        run(
            db_path,
            output_dir,
            "context",
            "--role",
            "generate",
            "--category",
            "判断推理",
            "--tag",
            "判断推理-逻辑判断-削弱论点",
            "--count",
            "1",
        )
        refreshed = json.loads(run(db_path, output_dir, "status", "--json").stdout)
        assert refreshed["pending"] == 0
        assert refreshed["generation_uses"] == 4
        assert refreshed["evaluation_uses"] == 1

    print("reference style pipeline: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

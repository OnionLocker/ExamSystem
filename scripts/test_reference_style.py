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
                    f"2026年{'广东' if index < 6 else '其他省'}公务员录用考试第{index}题",
                    "广东" if index < 6 else "浙江",
                ),
            )
        for index in range(6):
            conn.execute(
                """
                INSERT INTO reference_questions (
                  external_id, category, sub_category, question_type, content,
                  stem_images, options, correct_answer, explanation_images,
                  difficulty, tags, source, year, region, imported_by
                ) VALUES (?, '判断推理', '逻辑判断', 'single', ?, '[]', ?, 'C',
                          '[]', 3, ?, ?, 2026, '国家', 'test')
                """,
                (
                    f"ref-gk-{index:02d}",
                    f"国考研究提出第{index}个更长论证链。以下哪项如果为真，最能削弱上述观点？",
                    options,
                    json.dumps(["判断推理-逻辑判断-削弱论点"], ensure_ascii=False),
                    f"2026年国家公务员录用考试第{index}题",
                ),
            )
        for index in range(2):
            conn.execute(
                """
                INSERT INTO reference_questions (
                  external_id, category, sub_category, question_type, content,
                  stem_images, options, correct_answer, explanation_images,
                  difficulty, tags, source, year, region, imported_by
                ) VALUES (?, '判断推理', '定义判断', 'single', ?, '[]', ?, 'C',
                          '[]', 3, ?, ?, 2026, '国家', 'test')
                """,
                (
                    f"ref-dy-{index:02d}",
                    f"根据所给定义，下列最符合第{index}种情形的是？",
                    options,
                    json.dumps(["判断推理-定义判断-符合定义"], ensure_ascii=False),
                    f"2026年国家公务员录用考试定义判断第{index}题",
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
        conn.execute(
            "UPDATE reference_questions SET imported_by = ? WHERE external_id = ?",
            ("approved-ai-holdout", "ref-gk-05"),
        )
        conn.execute(
            "UPDATE reference_questions SET imported_by = ? WHERE external_id = ?",
            ("approved-ai-generate", "ref-gk-04"),
        )
        conn.commit()
        conn.close()

        run(db_path, output_dir, "build")
        status = json.loads(run(db_path, output_dir, "status", "--json").stdout)
        assert status["total"] == 21
        assert status["current"] == 21
        assert status["pending"] == 0
        assert status["excluded"] == 1
        assert status["holdout"] >= 1
        conn = sqlite3.connect(db_path)
        forced_status = conn.execute(
            "SELECT status FROM reference_digest_items WHERE external_id = ?",
            ("ref-gk-05",),
        ).fetchone()[0]
        generation_status = conn.execute(
            "SELECT status FROM reference_digest_items WHERE external_id = ?",
            ("ref-gk-04",),
        ).fetchone()[0]
        conn.close()
        assert forced_status == "holdout"
        assert generation_status == "accepted"
        profile = (output_dir / "reference-style-profile.md").read_text(encoding="utf-8")
        assert "默认目标分位" in profile
        assert "国考拔高分位" in profile

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
        gen_tiers = [item["source_tier"] for item in generated["references"]]
        assert gen_tiers.count("gd-real") == 2
        assert gen_tiers.count("national-real") == 1

        mixed = json.loads(
            run(
                db_path,
                output_dir,
                "context",
                "--role",
                "generate",
                "--category",
                "判断推理",
                "--count",
                "5",
            ).stdout
        )
        mixed_tiers = [item["source_tier"] for item in mixed["references"]]
        assert mixed_tiers.count("gd-real") == 3
        assert 1 <= mixed_tiers.count("national-real") <= 2
        assert all("定义判断" not in item["sub_category"] for item in mixed["references"])
        assert all(not str(item["external_id"]).startswith("ref-dy-") for item in mixed["references"])

        practiced = json.loads(
            run(
                db_path,
                output_dir,
                "practice",
                "--category",
                "判断推理",
                "--tag",
                "判断推理-逻辑判断-削弱论点",
                "--count",
                "2",
            ).stdout
        )
        assert practiced["selected"] == 2
        assert all(item["origin"] == "zhenti" for item in practiced["questions"])
        assert all(item["answer"] for item in practiced["questions"])

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
        assert refreshed["generation_uses"] == 9
        assert refreshed["evaluation_uses"] == 1
        # practice 只更新 last_used，不计入 generation_uses

    print("reference style pipeline: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

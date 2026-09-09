#!/usr/bin/env python3
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_figure_review import MODULE_NAME, seed

SCHEMA = """
CREATE TABLE review_modules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sort_order INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE review_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id INTEGER NOT NULL,
  filename TEXT NOT NULL,
  orig_name TEXT,
  mime TEXT DEFAULT 'image/png',
  sort_order INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (module_id) REFERENCES review_modules(id) ON DELETE CASCADE
);
"""


class SeedFigureReviewTest(unittest.TestCase):
    def test_seed_creates_module_and_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "lab"
            src.mkdir()
            catalog = {
                "groups": [
                    {
                        "title": "图形推理",
                        "items": [{"id": "a", "title": "立方体", "file": "a.svg"}],
                    }
                ]
            }
            (src / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            (src / "a.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
            db = root / "exam.db"
            con = sqlite3.connect(db)
            con.executescript(SCHEMA)
            con.close()
            dest = root / "review-images"

            def fake(items, _src):
                return [(f"{it['group']} · {it['title']}.png", b"png-bytes") for it in items]

            with patch("seed_figure_review.rasterize_svgs", fake):
                n = seed(db, dest, src / "catalog.json", src)
            self.assertEqual(n, 1)
            con = sqlite3.connect(db)
            name, count = con.execute(
                "SELECT name, (SELECT COUNT(*) FROM review_images) FROM review_modules"
            ).fetchone()
            self.assertEqual(name, MODULE_NAME)
            self.assertEqual(count, 1)
            fn, orig = con.execute("SELECT filename, orig_name FROM review_images").fetchone()
            self.assertTrue((dest / fn).exists())
            self.assertIn("立方体", orig)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_figure_batch as pub


class PublishFigureBatchTest(unittest.TestCase):
    def test_upsert_puts_full_group_first(self):
        catalog = {"style": "black-white-line", "groups": [{"id": "qty", "title": "qty", "items": []}]}
        group = {"id": "batch-x", "title": "demo", "items": [{"id": "a", "title": "A", "file": "a.png"}]}
        out = pub.upsert_group(catalog, group)
        self.assertEqual(out["groups"][0]["id"], "batch-x")
        self.assertEqual(len(out["groups"][0]["items"]), 1)
        self.assertEqual(out["groups"][1]["id"], "qty")

    def test_collect_all_pngs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for qid in ("k01", "p02"):
                d = root / qid
                d.mkdir()
                (d / "stem.png").write_bytes(b"png")
                (d / "request.json").write_text(json.dumps({"tags": [f"mod-{qid}"]}), encoding="utf-8")
                (d / "result.json").write_text(json.dumps({"ok": qid != "p02"}), encoding="utf-8")
            rows = pub.collect_batch(root)
            self.assertEqual([r["id"] for r in rows], ["k01", "p02"])
            self.assertIn("未过检", rows[1]["title"])


if __name__ == "__main__":
    unittest.main()

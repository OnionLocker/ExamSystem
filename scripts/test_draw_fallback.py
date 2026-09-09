#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from draw_fallback import apply_fallback, fallback_name
from draw_tools import inspect_figure


class DrawFallbackTest(unittest.TestCase):
    def test_failed_kepui_kinds_pass_local_inspect(self):
        root = Path(__file__).resolve().parents[1] / "data" / "figure-agent-demo" / "2026-09-08-flash"
        if not root.is_dir():
            self.skipTest("no flash demo requests")
        with tempfile.TemporaryDirectory() as temp:
            for qid in ("k03", "k04", "k10", "p07"):
                req = json.loads((root / qid / "request.json").read_text(encoding="utf-8"))
                dest = Path(temp) / f"{qid}.png"
                apply_fallback(req, dest)
                checked = inspect_figure(req, dest, Path(temp), vision=False)
                self.assertTrue(checked["ok"], (qid, fallback_name(req), checked["issues"]))


    def test_must_not_single_letter_ignores_svg_attributes(self):
        from program_figure import render_program
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "tank.png"
            render_program({"kind": "tank", "names": ["甲", "乙"], "object": "木块"}, dest)
            checked = inspect_figure(
                {"stem": "如图甲乙，木块漂浮", "must_show": ["甲", "乙", "木块"], "must_not": ["A", "B"]},
                dest,
                Path(temp),
                vision=False,
            )
            self.assertTrue(checked["ok"], checked["issues"])


if __name__ == "__main__":
    unittest.main()

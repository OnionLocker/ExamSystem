#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figure_flash_qa as flash
from draw_tools import inspect_figure


def _png(path: Path, size=(1400, 700), ink=True) -> Path:
    im = Image.new("RGB", size, "white")
    if ink:
        from PIL import ImageDraw
        draw = ImageDraw.Draw(im)
        draw.rectangle((80, 80, 1000, 520), outline=(0, 0, 0), width=4)
        draw.line((80, 200, 1000, 200), fill=(0, 0, 0), width=4)
        draw.line((80, 360, 1000, 360), fill=(0, 0, 0), width=4)
        draw.rectangle((200, 220, 360, 340), outline=(0, 0, 0), width=4)
    im.save(path)
    path.with_suffix(".svg").write_text(
        '<svg width="1400" height="700">'
        '<rect x="80" y="80" width="400" height="300"/>'
        '<line x1="80" y1="80" x2="480" y2="380"/>'
        '<line x1="90" y1="90" x2="400" y2="90"/>'
        '<line x1="90" y1="200" x2="400" y2="200"/>'
        '<text font-size="28">甲</text><text font-size="28">乙</text></svg>',
        encoding="utf-8",
    )
    return path


class FigureFlashQaTest(unittest.TestCase):
    def test_resize_matches_ipad_practice(self):
        with tempfile.TemporaryDirectory() as temp:
            png = _png(Path(temp) / "q.png")
            review = Image.open(BytesIO(flash.fit_ipad_png(png)))
        # 1400x700 contain in 768x480 -> 768x384
        self.assertEqual(review.size, (768, 384))

    def test_review_figure_sends_one_image(self):
        seen = []

        def caller(system, parts):
            seen.append(parts)
            return {
                "verdict": "PASS",
                "checks": {key: True for key in flash.CHECK_LABELS},
                "issues": [],
            }

        with tempfile.TemporaryDirectory() as temp:
            png = _png(Path(temp) / "q.png")
            flash.review_figure({"stem": "x"}, png, caller=caller)
        images = [part for part in seen[0] if part.get("type") == "image_url"]
        self.assertEqual(len(images), 1)

    def test_reject_payload_becomes_issues(self):
        issues = flash.issues_from_result(
            {
                "verdict": "REJECT",
                "checks": {
                    "apparatus": False,
                    "readable": True,
                    "kind_match": True,
                    "no_contradiction": True,
                    "no_leak": True,
                },
                "issues": ["几乎只有文字标签"],
            }
        )
        self.assertIn("几乎只有文字标签", issues)
        self.assertIn("缩小后看不见完整装置", issues)
        self.assertEqual(
            flash.issues_from_result(
                {
                    "verdict": "PASS",
                    "checks": {
                        "apparatus": True,
                        "readable": True,
                        "kind_match": True,
                        "no_contradiction": True,
                        "no_leak": True,
                    },
                    "issues": [],
                }
            ),
            [],
        )

    def test_inspect_calls_flash_only_when_local_passes(self):
        calls = []

        def fake_review(request, dest):
            calls.append((request.get("stem"), dest.name))
            return ["Flash看图：电路看不到导线"]

        with tempfile.TemporaryDirectory() as temp:
            png = _png(Path(temp) / "stem.png")
            checked = inspect_figure(
                {"stem": "如图电路甲、乙。", "tags": ["科学推理-电学-电路故障"], "must_show": ["甲", "乙"]},
                png,
                vision=True,
                flash_review=fake_review,
            )
        self.assertEqual(len(calls), 1)
        self.assertFalse(checked["ok"])
        self.assertTrue(any("Flash看图" in item for item in checked["issues"]))

    def test_inspect_skips_flash_when_local_fails(self):
        calls = []

        def fake_review(request, dest):
            calls.append(dest)
            return []

        with tempfile.TemporaryDirectory() as temp:
            png = Path(temp) / "stem.png"
            Image.new("RGB", (200, 200), "white").save(png)
            png.with_suffix(".svg").write_text('<svg><text font-size="13">甲</text></svg>', encoding="utf-8")
            checked = inspect_figure(
                {"stem": "如图甲乙", "must_show": ["甲"]},
                png,
                vision=True,
                flash_review=fake_review,
            )
        self.assertEqual(calls, [])
        self.assertFalse(checked["ok"])


if __name__ == "__main__":
    unittest.main()

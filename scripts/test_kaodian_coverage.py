#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""覆盖查询与均衡配题：Hermes 回答「题型全面吗 / 均衡出题」用的两个接口。"""
import sqlite3
import unittest

from kaodian_profile import coverage_report, ensure_schema, plan_blueprint
from kaodian_taxonomy import LEGACY_TAGS, canon_index

EXTREME = "数量关系-既烧脑又能套公式的最值问题"


class CanonIndexTest(unittest.TestCase):
    def test_split_card_maps_every_bullet_to_a_tag(self):
        card = next(c for c in canon_index("数量关系") if c["title"].startswith("08 既烧脑"))
        self.assertEqual(len(card["tags"]), 4)
        self.assertTrue(all(b["tag"] for b in card["bullets"]))

    def test_unsplit_card_leaves_bullets_untagged(self):
        card = next(c for c in canon_index("数量关系") if c["title"].startswith("11 要抓住"))
        self.assertEqual(len(card["tags"]), 1)
        self.assertTrue(any(not b["tag"] for b in card["bullets"]))


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_graphic_cards_are_excluded(self):
        cards = coverage_report(self.conn)
        self.assertTrue(cards)
        for card in cards:
            for row in card["rows"]:
                self.assertNotIn("图形推理", row["tag"])

    def test_keyword_narrows_to_one_card(self):
        cards = coverage_report(self.conn, "最值")
        self.assertEqual(len(cards), 1)
        self.assertEqual(len(cards[0]["rows"]), 4)
        self.assertEqual(cards[0]["untagged"], [])

    def test_untagged_listed_only_when_single_tag(self):
        card = coverage_report(self.conn, "要抓住常考图形")[0]
        self.assertEqual(len(card["rows"]), 1)
        self.assertTrue(card["untagged"])


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_counts_sum_to_requested_total(self):
        plan = plan_blueprint(self.conn, "最值", 10)
        self.assertEqual(sum(s["count"] for s in plan["slots"]), 10)
        self.assertEqual(len(plan["slots"]), 4)

    def test_skips_legacy_merged_tag(self):
        plan = plan_blueprint(self.conn, "排列组合", 6)
        tags = {s["tag"] for s in plan["slots"]}
        self.assertFalse(tags & LEGACY_TAGS)

    def test_unknown_keyword_fails_loudly(self):
        with self.assertRaises(SystemExit):
            plan_blueprint(self.conn, "查无此考点", 5)


if __name__ == "__main__":
    unittest.main()

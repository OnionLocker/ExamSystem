#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""粉笔树：旧长标签归一、短名出题、L4 登记后立刻可 --tag。"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fenbi_taxonomy import (
    LEGACY_TO_FENBI,
    fenbi_l3_tags,
    is_fenbi_l4,
    kaodian_family,
    parse_fenbi_tag,
)
from kaodian_profile import ensure_schema, register_knowledge_point
from kaodian_taxonomy import (
    NUM_AVERAGE,
    NUM_ENGINEERING,
    NUM_EXTREME,
    NUM_PERM,
    NUM_PROB,
    TRANSLATION,
    YANYU_MAIN,
    canonicalize,
    seed_aliases,
    validate_ai_primary_tag,
)
from quiz_generator import infer_subcategory, resolve_slots
from spoken_quiz_intent import resolve_tag


OLD_GROUP = "数量关系-逢考必有的排列组合与概率-分堆分配与定序消序"
OLD_DRAWER = "数量关系-既烧脑又能套公式的最值问题-最不利原则与抽屉"
OLD_SUPPORT = "判断推理-逻辑判断-逻辑论证-支持与前提假设"
L4_AVG = "数量关系-数学运算-平均数问题-加权平均数"
L4_GROUP = NUM_PERM + "-分堆分配与消序"


class FenbiTreeTest(unittest.TestCase):
    def test_exact_names_present(self):
        tags = fenbi_l3_tags()
        self.assertIn(NUM_AVERAGE, tags)
        self.assertIn("判断推理-逻辑判断-组合排列-单题", tags)
        self.assertIn("政治理论-时事政治-时事政治-其他", tags)
        self.assertIn("数量关系-数字推理-数字推理-其他", tags)
        self.assertIn("判断推理-科学推理-科学推理-物理", tags)
        self.assertNotIn("资料分析-ABRX类-基期量计算与比较", tags)

    def test_hyphenated_l3_parses(self):
        parsed = parse_fenbi_tag("判断推理-逻辑判断-组合排列-单题")
        self.assertEqual(parsed, ("判断推理", "逻辑判断", "组合排列-单题", ""))
        parsed_l4 = parse_fenbi_tag("判断推理-逻辑判断-组合排列-单题-两组对应")
        self.assertEqual(parsed_l4[3], "两组对应")
        self.assertTrue(is_fenbi_l4("数量关系-数学运算-平均数问题-加权平均数"))

    def test_shared_json_aliases(self):
        self.assertEqual(LEGACY_TO_FENBI[OLD_GROUP], L4_GROUP)
        self.assertEqual(
            LEGACY_TO_FENBI["判断推理-逻辑判断-逻辑论证-支持与前提假设"],
            "判断推理-逻辑判断-加强题型",
        )


class CanonicalizeOldToNewTest(unittest.TestCase):
    def test_old_quantity_tags(self):
        self.assertEqual(canonicalize(OLD_GROUP), L4_GROUP)
        self.assertEqual(canonicalize(OLD_DRAWER), NUM_EXTREME)
        self.assertEqual(
            canonicalize("数量关系-逢考必有的排列组合与概率-古典概型与定位秒杀"),
            NUM_PROB + "-定位法与同组概率",
        )
        self.assertEqual(
            canonicalize("数量关系-熟练掌握可“轻松拿下”的工程问题-工程效率与分段合作"),
            NUM_ENGINEERING,
        )
        self.assertEqual(canonicalize(OLD_SUPPORT), "判断推理-逻辑判断-加强题型")

    def test_short_names(self):
        self.assertEqual(canonicalize("平均数问题"), NUM_AVERAGE)
        self.assertEqual(canonicalize("工程问题", "数量关系"), NUM_ENGINEERING)
        self.assertEqual(canonicalize("片段阅读"), YANYU_MAIN)
        self.assertEqual(canonicalize("翻译推理"), TRANSLATION)

    def test_fenbi_primary_accepted(self):
        self.assertEqual(validate_ai_primary_tag(NUM_AVERAGE, "数量关系"), NUM_AVERAGE)
        self.assertEqual(validate_ai_primary_tag("判断推理-逻辑判断-翻译推理"), TRANSLATION)
        with self.assertRaises(ValueError):
            validate_ai_primary_tag("数量关系-数学运算-排列组合", "数量关系")


class SpokenIntentTest(unittest.TestCase):
    def test_average_engineering_passage(self):
        self.assertEqual(resolve_tag("给我出五道平均数问题"), NUM_AVERAGE)
        self.assertEqual(resolve_tag("来三道工程"), NUM_ENGINEERING)
        self.assertEqual(resolve_tag("刷五道片段阅读"), YANYU_MAIN)


class RegisterL4Test(unittest.TestCase):
    def test_register_then_quiz_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "exam.db"
            os.environ["EXAM_DB"] = str(db)
            conn = sqlite3.connect(db)
            ensure_schema(conn)
            register_knowledge_point(
                conn, L4_AVG, "数量关系", "数学运算", "加权平均数：权不同，先乘再除"
            )
            conn.commit()
            conn.close()
            self.assertEqual(canonicalize(L4_AVG, "数量关系"), L4_AVG)
            self.assertEqual(validate_ai_primary_tag(L4_AVG, "数量关系"), L4_AVG)
            import argparse
            args = argparse.Namespace(module="数量关系", tag=L4_AVG, count=3, blueprint=None, difficulty=None)
            module, slots = resolve_slots(args)
            self.assertEqual(module, "数量关系")
            self.assertEqual(slots[0]["tag"], L4_AVG)
            self.assertEqual(infer_subcategory(L4_AVG, "数量关系"), "数学运算")
            del os.environ["EXAM_DB"]

    def test_rejects_l3_not_on_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(Path(tmp) / "t.db")
            ensure_schema(conn)
            with self.assertRaises(ValueError):
                register_knowledge_point(conn, "政治理论-党史党建-党的组织路线", "政治理论", "党史党建")
            conn.close()


class AliasSeedTest(unittest.TestCase):
    def test_old_alias_points_to_fenbi(self):
        conn = sqlite3.connect(":memory:")
        ensure_schema(conn)
        mappings = seed_aliases(conn)
        self.assertEqual(mappings[OLD_GROUP], L4_GROUP)
        self.assertEqual(kaodian_family(OLD_GROUP), NUM_PERM)
        self.assertEqual(kaodian_family(L4_AVG), NUM_AVERAGE)
        conn.close()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""粉笔树：旧长标签归一、短名出题、L4 登记后立刻可 --tag。"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    NUM_EXTREME_DRAWER,
    NUM_EXTREME_HEDING,
    NUM_EXTREME_QUAD,
    NUM_EXTREME_REVERSE,
    NUM_PERM,
    NUM_PROB,
    TRANSLATION,
    YANYU_MAIN,
    canonicalize,
    database_aliases,
    registered_knowledge_points,
    resolve_database_alias,
    seed_aliases,
    validate_ai_primary_tag,
)
from quiz_generator import _static_canon_card, infer_subcategory, resolve_slots
from spoken_quiz_intent import resolve_tag


OLD_PROB_TAG = "数量关系-数学运算-概率问题-抽签与对立事件"
NEW_PROB_TAG = "数量关系-数学运算-概率问题-古典概型与对立事件"
L4_DRAWER = NUM_EXTREME_DRAWER  # L4 标签
L4_AVG = "数量关系-数学运算-平均数问题-加权平均数"


def setUpModule():
    global _temporary, _environment
    _temporary = tempfile.TemporaryDirectory()
    _environment = patch.dict(os.environ, EXAM_DB=str(Path(_temporary.name) / "absent.db"),
                              EXAM_KNOWLEDGE_DB=str(Path(_temporary.name) / "knowledge.db"))
    _environment.start()


def tearDownModule():
    _environment.stop()
    _temporary.cleanup()


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
        # 旧标签 -> 新标签（使用真实有效的映射）
        self.assertEqual(LEGACY_TO_FENBI[OLD_PROB_TAG], NEW_PROB_TAG)
        # 自映射（标签映射到自己）
        self.assertEqual(
            LEGACY_TO_FENBI["数量关系-数字推理-递推数列"],
            "数量关系-数字推理-递推数列",
        )


class CanonicalizeOldToNewTest(unittest.TestCase):
    def test_old_quantity_tags(self):
        # 旧标签 -> 新标签
        self.assertEqual(canonicalize(OLD_PROB_TAG), NEW_PROB_TAG)
        # 新标签 -> 原样返回
        self.assertEqual(canonicalize(NEW_PROB_TAG), NEW_PROB_TAG)
        self.assertEqual(canonicalize(L4_DRAWER), L4_DRAWER)

        # L3 标签原样返回
        self.assertEqual(canonicalize(NUM_AVERAGE), NUM_AVERAGE)

    def test_short_names(self):
        self.assertEqual(canonicalize("平均数问题"), NUM_AVERAGE)
        self.assertEqual(canonicalize("工程问题", "数量关系"), NUM_ENGINEERING)
        self.assertEqual(canonicalize("片段阅读"), YANYU_MAIN)
        self.assertEqual(canonicalize("翻译推理"), TRANSLATION)
        self.assertEqual(canonicalize("逻辑填空-实词"), "言语理解与表达-逻辑填空-实词填空")

    def test_fenbi_primary_accepted(self):
        self.assertEqual(validate_ai_primary_tag(NUM_AVERAGE, "数量关系"), NUM_AVERAGE)
        self.assertEqual(validate_ai_primary_tag("判断推理-逻辑判断-翻译推理"), TRANSLATION)
        with self.assertRaises(ValueError):
            validate_ai_primary_tag("数量关系-数学运算-排列组合", "数量关系")

    def test_parent_short_names_do_not_become_a_child(self):
        for name in ("最值问题", "函数最值问题", "工程问题"):
            parent = f"数量关系-数学运算-{name}"
            self.assertEqual(canonicalize(name, "数量关系"), parent)
            self.assertEqual(canonicalize(parent, "数量关系"), parent)

    def test_restored_aliases_keep_the_intended_canon(self):
        cases = {
            "数量关系-有规律的周期循环与要算准的日期星期-周期排班与公倍数": "数量关系-数学运算-周期问题",
            "判断推理-逻辑判断-逻辑论证-一般质疑": "判断推理-逻辑判断-削弱题型",
            "言语理解-片段阅读-语句排序": "言语理解与表达-语句表达-语句排序题",
        }
        for old, new in cases.items():
            self.assertEqual(canonicalize(old), new)
        self.assertIn("工程问题", _static_canon_card("数量关系", NUM_ENGINEERING))

    def test_category_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "模块与考点不一致"):
            validate_ai_primary_tag(NUM_ENGINEERING, "政治理论")
        with self.assertRaisesRegex(ValueError, "模块与考点不一致"):
            validate_ai_primary_tag("科学推理-力学-受力平衡", "判断推理")


class SpokenIntentTest(unittest.TestCase):
    def test_average_engineering_passage(self):
        self.assertEqual(resolve_tag("给我出五道平均数问题"), NUM_AVERAGE)
        self.assertEqual(resolve_tag("来三道工程"), NUM_ENGINEERING)
        self.assertEqual(resolve_tag("刷五道片段阅读"), "言语理解与表达-片段阅读")


class RegisterL4Test(unittest.TestCase):
    def test_register_then_quiz_tag(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
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
        # 旧标签 -> 新标签
        self.assertEqual(mappings[OLD_PROB_TAG], NEW_PROB_TAG)
        # L4 标签的 family 应该是其 L3
        self.assertEqual(kaodian_family(L4_DRAWER), "数量关系-数学运算-最值问题")
        self.assertEqual(kaodian_family(L4_AVG), NUM_AVERAGE)
        conn.close()

    def test_database_rename_survives_seeding_and_deduplicates_definitions(self):
        old = NUM_ENGINEERING + "-旧考法"
        new = NUM_ENGINEERING + "-新考法"
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, EXAM_DB=f"{tmp}/exam.db"):
            with sqlite3.connect(os.environ["EXAM_DB"]) as conn:
                ensure_schema(conn)
                register_knowledge_point(conn, old, "数量关系", "数学运算", "旧定义")
                register_knowledge_point(conn, new, "数量关系", "数学运算", "新定义")
                conn.execute("UPDATE kaodian_aliases SET canonical=? WHERE alias=?", (new, old))
                seed_aliases(conn)
                self.assertEqual(database_aliases(conn)[old], new)
                conn.commit()
                self.assertEqual(canonicalize(old), new)
                self.assertEqual(registered_knowledge_points()[new]["definition"], "新定义")
                self.assertNotIn(old, registered_knowledge_points())
                with self.assertRaisesRegex(ValueError, "模块与考点不一致"):
                    register_knowledge_point(conn, new, "政治理论", "数学运算", "定义")

    def test_alias_cycle_fails_and_static_rename_cannot_be_reversed(self):
        with self.assertRaisesRegex(ValueError, "循环"):
            resolve_database_alias("a", {"a": "b", "b": "a"})
        self.assertEqual(resolve_database_alias(NEW_PROB_TAG, {NEW_PROB_TAG: OLD_PROB_TAG}), NEW_PROB_TAG)


if __name__ == "__main__":
    unittest.main()

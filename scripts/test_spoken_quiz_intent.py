#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

from datetime import date

from kaodian_taxonomy import NUM_AVERAGE, NUM_ENGINEERING, NUM_PERM, TRANSLATION, YANYU_MAIN
from spoken_quiz_intent import extract_count, parse_spoken_intent, resolve_tag, suggest_batch_id, wants_quiz


class SpokenQuizIntentTest(unittest.TestCase):
    def test_special_model_maps_to_fenbi_perm(self):
        text = "给我出五道排列组合与概率的经典模型专项"
        self.assertEqual(resolve_tag(text), NUM_PERM)
        self.assertTrue(wants_quiz(text))
        intent = parse_spoken_intent(text)
        self.assertEqual(intent["module"], "数量关系")
        self.assertEqual(intent["count"], 5)
        self.assertTrue(intent["wants_quiz"])
        self.assertIn("排列组合", intent["batch_id"])
        self.assertEqual(
            suggest_batch_id(
                NUM_PERM,
                today=date(2026, 9, 10),
                taken={"20260910_hermes_排列组合_01"},
            ),
            "20260910_hermes_排列组合_02",
        )

    def test_does_not_steal_named_perm_for_extreme(self):
        text = "来两道翻译推理"
        intent = parse_spoken_intent(text)
        self.assertEqual(intent["tag"], TRANSLATION)
        self.assertEqual(intent["count"], 2)

    def test_basic_perm_and_average_engineering_passage(self):
        self.assertEqual(resolve_tag("出三道排列组合基础原理"), NUM_PERM)
        self.assertEqual(extract_count("出三道排列组合"), 3)
        self.assertEqual(resolve_tag("出五道平均数问题"), NUM_AVERAGE)
        self.assertEqual(resolve_tag("来几道工程问题"), NUM_ENGINEERING)
        self.assertEqual(resolve_tag("刷片段阅读"), YANYU_MAIN)

    def test_plain_chat_is_not_quiz(self):
        intent = parse_spoken_intent("今天天气怎么样")
        self.assertFalse(intent["wants_quiz"])
        self.assertEqual(intent["tag"], "")


if __name__ == "__main__":
    unittest.main()

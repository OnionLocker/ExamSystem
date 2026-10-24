#!/usr/bin/env python3
import unittest

import logic_model as lm

TRANSLATION = {
    "vars": [{"name": n, "values": ["bool"]} for n in ("考核", "证书", "小陈培训")],
    "constraints": ["implies(证书, 考核)", "not 考核"],
    "options": {"A": "not 证书", "B": "考核", "C": "证书 or 考核", "D": "not 小陈培训"},
    "ask": "must_true",
}

# 甲：乙说谎；乙：丙说谎；丙：甲乙都说谎。只有一人说真话。
TRUTH = {
    "vars": {"甲真": ["bool"], "乙真": ["bool"], "丙真": ["bool"]},
    "constraints": ["iff(甲真, not 乙真)", "iff(乙真, not 丙真)", "iff(丙真, not 甲真 and not 乙真)",
                    "exactly(1, 甲真, 乙真, 丙真)"],
    "options": {"A": "甲真", "B": "乙真", "C": "丙真", "D": "not 乙真"},
    "ask": "must_true",
}

# 甲乙丙丁排 1–4 号；甲不在 1 号，乙紧挨丙，丁在乙前面。
ARRANGE = {
    "vars": {n: ["1", "2", "3", "4"] for n in ("甲", "乙", "丙", "丁")},
    "constraints": ["distinct(甲, 乙, 丙, 丁)", "甲 != 1", "adjacent(乙, 丙)", "丁 < 乙"],
    "options": {"A": "丁 == 1", "B": "甲 == 4", "C": "丙 == 4", "D": "乙 == 2"},
    "ask": "must_true",
}


class LogicModelTest(unittest.TestCase):
    def test_translation_entailment_and_echo(self):
        self.assertEqual(lm.check(TRANSLATION, "A", depth=False)["verdict"], "PASS")
        wrong = lm.check(TRANSLATION, "B")
        self.assertIn("满足设问的是 A", wrong["issues"][0])
        echo = {**TRANSLATION, "options": {**TRANSLATION["options"], "A": "not 考核"}}
        self.assertIn("复述题干", lm.check(echo, "A")["issues"][0])

    def test_truth_teller_unique(self):
        result = lm.check(TRUTH, "B", depth=False)
        self.assertEqual(result["verdict"], "PASS", result)
        self.assertEqual(result["models"], 1)

    def test_arrangement_detects_double_answer(self):
        result = lm.solve(ARRANGE)
        self.assertEqual(result["correct"], ["A"])
        double = {**ARRANGE, "options": {**ARRANGE["options"], "D": "乙 != 1"}}
        self.assertIn("A、D 都满足", lm.check(double, "A")["issues"][0])

    def test_possible_not_must_and_premise(self):
        possible = {**ARRANGE, "ask": "possible", "options": {"A": "甲 == 1", "B": "丙 == 2", "C": "丁 == 4", "D": "乙 == 1"}}
        self.assertEqual(lm.solve(possible)["correct"], ["B"])
        premise = {"vars": {n: ["bool"] for n in ("面试", "笔试", "录用")},
                   "constraints": ["implies(面试, 笔试)"], "conclusion": "implies(面试, 录用)",
                   "options": {"A": "implies(笔试, 录用)", "B": "implies(录用, 笔试)", "C": "not 面试 and not 笔试 and 录用 and False",
                               "D": "implies(录用, 面试)"},
                   "ask": "sufficient_premise"}
        out = lm.check(premise, "A", depth=False)
        self.assertEqual(out["verdict"], "PASS", out)
        self.assertEqual(out["options"]["C"], "补充后与题干矛盾")

    def test_max_question(self):
        formal = {"vars": {n: ["bool"] for n in ("甲", "乙", "丙", "丁")},
                  "constraints": ["implies(甲, not 乙)", "implies(丙, 丁)", "not (乙 and 丁)"],
                  "target": "count(甲, 乙, 丙, 丁)", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "ask": "max"}
        self.assertEqual(lm.check(formal, "C", depth=False)["verdict"], "PASS")

    def test_depth_rejects_padding_and_spares_background(self):
        padded = {**ARRANGE, "constraints": ARRANGE["constraints"] + ["甲 != 2 or 甲 != 3", "丙 != 0"]}
        out = lm.check(padded, "A")
        self.assertIn("凑数", out["issues"][0])
        tight = {**ARRANGE, "background": ["distinct(甲, 乙, 丙, 丁)"], "constraints": ARRANGE["constraints"][1:]}
        self.assertEqual(lm.check(tight, "A")["verdict"], "PASS", lm.check(tight, "A"))
        one_step = {**TRANSLATION, "background": ["implies(证书, 考核)"], "constraints": ["not 考核"]}
        self.assertIn("只靠 1 个条件", lm.check(one_step, "A")["issues"][0])

    def test_rejects_unsafe_or_malformed(self):
        for bad, needle in [({**TRANSLATION, "constraints": ["__import__('os')"]}, "只能调用"),
                            ({**TRANSLATION, "constraints": ["未声明 == 1"]}, "未声明"),
                            ({**TRANSLATION, "ask": "guess"}, "ask 只能是"),
                            ({**TRANSLATION, "options": {"A": "证书"}}, "A/B/C/D"),
                            ({**TRANSLATION, "constraints": ["证书.real"]}, "不允许的语法"),
                            ({"vars": {f"x{i}": list(range(10)) for i in range(7)}, "constraints": ["x0 == 1"],
                              "options": dict.fromkeys("ABCD", "x0 == 1"), "ask": "must_true"}, "超过")]:
            with self.subTest(needle=needle):
                result = lm.check(bad, "A")
                self.assertEqual(result["verdict"], "REJECT")
                self.assertIn(needle, result["issues"][0])
        contradiction = {**TRANSLATION, "constraints": ["考核", "not 考核"]}
        self.assertIn("自相矛盾", lm.check(contradiction, "A")["issues"][0])


if __name__ == "__main__":
    unittest.main()

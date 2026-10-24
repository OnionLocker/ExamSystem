#!/usr/bin/env python3
import random
import unittest

import ziliao_material_tools as tools
import ziliao_parallel_runner as runner
from ziliao_checklist import rounding_issues
from ziliao_tracks import ZILIAO_SHARE, range_calculation_issues

MID = "b-M02"
RAW_MATERIAL = {
    "content": "2024年，广州市甲区114.4亿元、乙区86.2亿元、丙区43.7亿元，三区合计{{G1}}亿元。",
    "figure": {"kind": "bars", "categories": ["甲", "乙", "丙", "合计"],
               "series": [{"name": "2024", "values": [114.4, 86.2, 43.7, "{{G1}}"]}]},
    "groups": [{"id": "G1", "label": "2024年三区合计", "unit": "亿元", "places": 1,
                "parts": [{"label": "甲", "shown": "114.4"}, {"label": "乙", "shown": "86.2"},
                          {"label": "丙", "shown": "43.7"}]}],
}


class MaterialTest(unittest.TestCase):
    def test_totals_and_ledger_pass_checklist(self):
        for seed in range(50):
            material = tools.finalize_material(RAW_MATERIAL, random.Random(seed))
            self.assertEqual(rounding_issues(material), [], seed)
            self.assertNotIn("{{", material["content"])
            self.assertIsInstance(material["figure"]["series"][0]["values"][3], float)

    def test_missing_group_is_rejected(self):
        with self.assertRaises(ValueError):
            tools.finalize_material({**RAW_MATERIAL, "groups": []}, random.Random(1))


class OptionTest(unittest.TestCase):
    def test_intervals_are_ordered_and_valid(self):
        for value in (3.71, 13.69, 47.2, 0.86, 128.4, 9.93):
            for position in range(4):
                texts, ranges, hit = tools.interval_options(value, "%", position)
                with self.subTest(value=value, position=position):
                    self.assertEqual(range_calculation_issues(value, ranges, "ABCD"[hit], set("ABCD")), [])
                    edges = [ranges["B"][0], ranges["C"][0], ranges["D"][0]]
                    self.assertEqual(edges, sorted(edges))
                    self.assertTrue(texts[0].startswith("不到") and texts[3].startswith("超过"))

    def test_intervals_hit_planned_position_when_possible(self):
        hits = [tools.interval_options(v, "%", p)[2] == p for v in (13.69, 47.2, 128.4) for p in range(4)]
        self.assertGreaterEqual(sum(hits), 10)

    def test_interval_separates_common_errors(self):
        texts, ranges, hit = tools.interval_options(9.53, "%", 0, traps=[8.70, 10.53])
        edges = [ranges["B"][0], ranges["C"][0], ranges["D"][0]]
        self.assertEqual(range_calculation_issues(9.53, ranges, "ABCD"[hit], set("ABCD")), [])
        self.assertNotEqual(tools._bin(8.70, edges), hit, texts)
        self.assertNotEqual(tools._bin(10.53, edges), hit, texts)

    def test_interval_gives_every_wrong_bin_a_path(self):
        texts, ranges, hit = tools.interval_options(38.25, "%", 3, traps=[9.14, 17.38, 23.90])
        edges = [ranges["B"][0], ranges["C"][0], ranges["D"][0]]
        self.assertEqual({tools._bin(t, edges) for t in (9.14, 17.38, 23.90)} | {hit}, {0, 1, 2, 3}, texts)

    def test_count_options_avoid_zero(self):
        slot = {"kind": "count", "family": "avg_cmp", "tag": ZILIAO_SHARE, "answer_key": "D"}
        question, _ = tools.build_question({"stem": "有几个（ ）", "analysis": "逐一判断。", "value_expr": "3", "unit": "个"},
                                           slot, 3, MID)
        self.assertNotIn("0个", [o["text"] for o in question["options"]])

    def test_direction_options(self):
        for value, position in ((1.23, 0), (1.23, 1), (-0.84, 2), (-0.84, 3)):
            texts, ranges, hit = tools.direction_options(value, "个百分点", "上升了", "下降了", position)
            self.assertEqual(range_calculation_issues(value, ranges, "ABCD"[hit], set("ABCD")), [])
            self.assertEqual(hit, position)


class ModeTest(unittest.TestCase):
    def test_entity_and_qualitative_slots_use_name_options(self):
        self.assertEqual(tools.mode_of({"kind": "share_change", "quick": True, "option_format": "exact"}), "choice")
        self.assertEqual(tools.mode_of({"kind": "growth_rate", "kaofa_variant_name": "多主体增速比较",
                                        "brief": "本题考法变式：多主体增速比较。比较同比增长率最高或最低者"}), "choice")
        self.assertEqual(tools.mode_of({"kind": "share_change", "kaofa_variant_name": "两期比重差算百分点",
                                        "brief": "本题考法变式：两期比重差算百分点。求比重提高多少个百分点"}), "numeric")


class BuildQuestionTest(unittest.TestCase):
    slot = {"kind": "share", "family": "share_add", "tag": ZILIAO_SHARE, "answer_key": "C",
            "option_format": "exact", "difficulty_score": 2}

    def test_numeric_question_passes_question_checks(self):
        raw = {"stem": "2024年，甲区占三区合计的比重约为（ ）", "analysis": "甲区114.4亿元，三区合计244.3亿元。",
               "unit": "%", "decimals": 1, "correct_expr": "114.4/244.3*100",
               "distractors": [{"expr": "86.2/244.3*100", "why": "取错部分，用了乙区"},
                               {"expr": "43.7/244.3*100", "why": "取错部分，用了丙区"},
                               {"expr": "114.4/(244.3-114.4)*100", "why": "分母误用其余两区之和"}]}
        question, calc = tools.build_question(raw, self.slot, 1, MID)
        values = [float(o["text"].rstrip("%")) for o in question["options"]]
        self.assertEqual(values, sorted(values))
        self.assertEqual(question["answer"], "C")
        errors = runner.question_errors(question, calc, {"external_id": MID}, {"track": "gd"}, f"{MID}-Q1",
                                        self.slot, [])
        self.assertEqual(errors, [])

    def test_percent_times_100_is_normalized(self):
        from ziliao_checklist import explanation_math_issues
        text = tools.normalize_analysis("比重=318.7÷1184.3×100≈26.91%，增速=(426.3−381.2)÷381.2*100=11.83%。")
        self.assertNotIn("100≈", text)
        self.assertEqual(explanation_math_issues(text), [])

    def test_root_expressions_are_supported(self):
        slot = {"kind": "annual_growth", "family": "avg_cmp", "tag": ZILIAO_SHARE, "answer_key": "B",
                "option_format": "exact", "difficulty_score": 3}
        raw = {"stem": "2020—2024年年均增长率约为（ ）", "analysis": "2024年1250.4，2020年980.2，开4次方。",
               "unit": "%", "decimals": 1, "correct_expr": "((1250.4/980.2)^(1/4)-1)*100",
               "distractors": [{"expr": "(1250.4/980.2-1)*100/5", "why": "年份差误用5"},
                               {"expr": "(1250.4/980.2-1)*100", "why": "求成总增长率"},
                               {"expr": "((1250.4/980.2)^(1/3)-1)*100", "why": "年份差误用3"}]}
        question, calc = tools.build_question(raw, slot, 3, MID)
        self.assertNotIn("^", question["explanation"])
        self.assertIn("开4次方", question["explanation"])
        errors = runner.question_errors(question, calc, {"external_id": MID}, {"track": "gd"}, f"{MID}-Q3", slot, [])
        self.assertFalse([e for e in errors if "计算" in e or "精度" in e or "干扰项" in e], errors)

    def test_choice_question_moves_answer_and_maps_letters(self):
        slot = {"kind": "sort", "family": "avg_cmp", "tag": ZILIAO_SHARE, "answer_key": "D"}
        raw = {"stem": "排序正确的是（ ）", "correct": 0, "analysis": "[1]正确；[2]把乙丙颠倒；[3]错；[4]错",
               "options": [{"text": "甲>乙>丙"}, {"text": "甲>丙>乙"}, {"text": "乙>甲>丙"}, {"text": "丙>乙>甲"}]}
        question, calc = tools.build_question(raw, slot, 2, MID)
        self.assertEqual(question["answer"], "D")
        self.assertEqual(question["options"][3]["text"], "甲>乙>丙")
        self.assertIn("D项正确", question["explanation"])
        self.assertEqual(calc["options"]["D"], 1)


if __name__ == "__main__":
    unittest.main()

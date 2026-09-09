#!/usr/bin/env python3
"""判断推理 20 题套（图5+逻辑15）与独立科学推理 5 题。"""

from __future__ import annotations

import random
import unittest

import panduan_pack as pack


def item(index: int, kind: str, tag: str, category: str | None = None) -> dict:
    sub = {
        "graphic": pack.SUB_GRAPHIC,
        "logic": pack.SUB_LOGIC,
        "science": pack.SUB_SCIENCE,
    }[kind]
    return {
        "external_id": f"Q{index:02d}",
        "category": category or (pack.CAT_KEPUI if kind == "science" else pack.CAT_PANDUAN),
        "sub_category": sub,
        "tags": [tag],
        "answer": "A",
        "stem_images": ["images/k.png"] if kind == "science" else [],
    }


def paper_from_slots(slots: list[dict], *, science: bool = False) -> list[dict]:
    out = []
    for index, slot in enumerate(slots, start=1):
        section = slot["section"]
        kind = {"graphic": "graphic", "logic": "logic", "science": "science"}[section]
        out.append(item(index, kind, slot["tag"], pack.CAT_KEPUI if science else None))
    return out


class PanduanPackTest(unittest.TestCase):
    def test_default_pack_is_20_logic_no_graphic(self):
        slots = pack.select_panduan_paper({}, {}, letters=list("ABCD" * 5), rng=random.Random("daily-p"))
        self.assertEqual(len(slots), 20)
        self.assertEqual([slot["section"] for slot in slots], ["logic"] * 20)
        self.assertFalse(any(slot["section"] == "science" for slot in slots))
        self.assertLessEqual(sum(1 for slot in slots if "翻译推理" in slot["tag"]), 2)
        pack.validate_panduan_paper(paper_from_slots(slots))

    def test_rejects_all_translation(self):
        questions = [item(i, "logic", pack.TRANSLATION_TAG) for i in range(1, 21)]
        with self.assertRaisesRegex(ValueError, "翻译推理每年只考"):
            pack.validate_panduan_paper(questions)

    def test_rejects_science_inside_panduan20(self):
        slots = pack.select_panduan_paper({}, {})
        questions = paper_from_slots(slots)
        for index in range(15, 20):
            questions[index] = item(
                index + 1,
                "science",
                "科学推理-力学-受力平衡",
                category=pack.CAT_PANDUAN,
            )
        with self.assertRaisesRegex(ValueError, "不得含科学推理"):
            pack.validate_panduan_paper(questions)

    def test_skips_non_20_sets(self):
        questions = [item(i, "logic", pack.TRANSLATION_TAG) for i in range(1, 11)]
        pack.validate_panduan_paper(questions)

    def test_compact_has_twenty_slots(self):
        compact = pack.compact_panduan_pack(
            {"paper_style": "gd", "slots": pack.select_panduan_paper({}, {})}
        )
        self.assertEqual(len(compact["slots"]), 20)
        self.assertEqual(compact["layout"], pack.LAYOUT_NAME)
        self.assertEqual(compact["layout"], "20_logic_no_graphic")
        self.assertTrue(all(slot.get("exam_move") for slot in compact["slots"]))
        # 同标签允许不同 exam_move；不同标签的 exam_move 不必全唯一（选项池 < 槽数）
        same_tag_moves = {slot["tag"]: set() for slot in compact["slots"]}
        for slot in compact["slots"]:
            same_tag_moves[slot["tag"]].add(slot["exam_move"])
        self.assertTrue(all(len(moves) <= 3 for moves in same_tag_moves.values()))

    def test_kaodian_rejects_structure_slot_without_ask(self):
        questions = paper_from_slots(pack.select_panduan_paper({}, {}))
        ask_by_key = (
            ("支持", "最能支持上述结论的是"),
            ("质疑", "最能削弱上述结论的是"),
            ("分析", "根据以上信息可以推出对应关系的是"),
            ("解释", "最能解释上述现象的是"),
            ("翻译", "由此可以推出"),
            ("归因", "最能质疑该归因的是"),
        )
        for item in questions:
            if item["sub_category"] != pack.SUB_LOGIC:
                continue
            tag = item["tags"][0]
            if "秒杀" in tag or "结构" in tag:
                item["stem"] = "某单位四位职工对驻村人选作了预测，已知只有一人说假话。由此可以推出。" + "补充。" * 8
                continue
            ask = next((text for key, text in ask_by_key if key in tag), "根据以上信息可以推出")
            item["stem"] = ("背景叙述。" * 8) + ask
        with self.assertRaisesRegex(ValueError, "考点与设问不符"):
            pack.validate_panduan_kaodian(questions)


class KepuiPackTest(unittest.TestCase):
    def test_default_pack_is_five_distinct_subjects(self):
        slots = pack.select_kepui_paper({}, {}, letters=list("ABCDE"), rng=random.Random("daily-k"))
        self.assertEqual(len(slots), 5)
        self.assertEqual([slot["section"] for slot in slots], ["science"] * 5)
        questions = paper_from_slots(slots, science=True)
        pack.validate_kepui_paper(questions, require_images=True)
        buckets = [pack.kepui_bucket(pack._blob(q)) for q in questions]
        self.assertEqual(len(set(buckets)), 5)
        self.assertIn("生物", buckets)
        self.assertIn("地理", buckets)

    def test_rejects_same_science_subject(self):
        slots = pack.select_kepui_paper({}, {})
        questions = paper_from_slots(slots, science=True)
        for index in range(5):
            questions[index]["tags"] = ["科学推理-力学-受力平衡"]
        with self.assertRaisesRegex(ValueError, "同一学科"):
            pack.validate_kepui_paper(questions)

    def test_rejects_panduan_category_on_kepui_paper(self):
        slots = pack.select_kepui_paper({}, {})
        questions = paper_from_slots(slots, science=True)
        for question in questions:
            question["category"] = pack.CAT_PANDUAN
        with self.assertRaisesRegex(ValueError, "category 必须是科学推理"):
            pack.validate_kepui_paper(questions)

    def test_compact_has_five_slots(self):
        compact = pack.compact_kepui_pack(
            {"paper_style": "gd", "slots": pack.select_kepui_paper({}, {})}
        )
        self.assertEqual(len(compact["slots"]), 5)
        self.assertEqual(compact["layout"], pack.KEPUI_LAYOUT_NAME)

    def test_geo_contour_can_appear_and_stays_medium(self):
        contour = "科学推理-地理-等高线"
        self.assertEqual(pack.tag_difficulty(contour), 3)
        seen = set()
        for seed in range(80):
            slots = pack.select_kepui_paper({}, {}, rng=random.Random(seed))
            geo = [slot["tag"] for slot in slots if "地理" in slot["tag"]]
            self.assertEqual(len(geo), 1)
            seen.add(geo[0])
            if geo[0] == contour:
                self.assertEqual(
                    [slot["difficulty"] for slot in slots if slot["tag"] == contour],
                    [3],
                )
        self.assertIn(contour, seen)
        self.assertGreater(len(seen), 3)
        front = "科学推理-地理-锋面天气"
        many = [
            pack.select_kepui_paper({}, {}, rng=random.Random(seed), recent={front})
            for seed in range(40)
        ]
        geo = [slot["tag"] for slots in many for slot in slots if "地理" in slot["tag"]]
        self.assertNotEqual(set(geo), {front})
        self.assertLess(geo.count(front) / len(geo), 0.35)

    def test_shuliang_and_yanyu_rotate_off_recent(self):
        date = "数量关系-有规律的周期循环与要算准的日期星期-日期推算与余数"
        detail = "言语理解与表达-片段阅读-细节判断"
        math = [
            slot["tag"]
            for slot in pack.select_shuliang_paper(rng=random.Random(3), recent={date})
            if slot["section"] == "math"
        ]
        self.assertNotIn(date, math)
        papers = [pack.select_yanyu_paper(rng=random.Random(seed)) for seed in range(12)]
        self.assertTrue(any("语句" in slot["tag"] for slots in papers for slot in slots))
        self.assertGreater(
            len({slot["tag"] for slots in papers for slot in slots if slot["section"] == "read"}),
            2,
        )
        filled = [
            slot["tag"]
            for slot in pack.select_yanyu_paper(rng=random.Random(3), recent={detail})
            if slot["section"] == "read"
        ]
        self.assertLessEqual(filled.count(detail), 2)

    def test_weak_contour_still_wins(self):
        contour = "科学推理-地理-等高线"
        slots = pack.select_kepui_paper(
            {contour: {"mastery": 30, "confidence": 70, "streak": -2}},
            {contour: 2},
            rng=random.Random(0),
        )
        geo = [slot["tag"] for slot in slots if "地理" in slot["tag"]]
        self.assertEqual(geo, [contour])


if __name__ == "__main__":
    unittest.main()

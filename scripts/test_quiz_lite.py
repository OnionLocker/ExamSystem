#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path

import quiz_lite
from generation_gate import validate_lite_review

TAG = "数量关系-数学运算-最值问题"
SLOT = {"tag": TAG, "count": 1, "difficulty": "hard"}


def question(index, answer="A", stem=None, analysis=None):
    return {
        "index": index,
        "stem": stem or f"某单位将{90 + index}本业务用书分给若干科室，各科室所得互不相同，问第三名最多分得多少本？",
        "options": [
            {"key": "A", "text": "25本"},
            {"key": "B", "text": "26本"},
            {"key": "C", "text": "27本"},
            {"key": "D", "text": "28本"},
        ],
        "answer": answer,
        "analysis": analysis
        or "设第三名为 X，其余按底牌取极限，列式 3X + 24 ≤ 100，解得 X ≤ 25.33，问最多向下取整得 25，故选 A。",
    }


def stamped(batch_id, index, answer="A"):
    run = {"module": "数量关系", "batch_id": batch_id}
    return quiz_lite.stamp(run, question(index, answer), index - 1, SLOT, "源")


class FakeModel:
    """按角色分派的假模型。writer 逐轮出稿，blind/examiner 按题号查表。"""

    def __init__(self, writer_rounds, blind, examiner):
        self.writer_rounds = [list(items) for items in writer_rounds]
        self.blind = blind
        self.examiner = examiner
        self.writer_prompts = []

    def __call__(self, system, prompt, temperature, timeout):
        if system == quiz_lite.WRITER_SYSTEM:
            self.writer_prompts.append(prompt)
            return {"questions": self.writer_rounds.pop(0)}
        table = self.blind if system == quiz_lite.BLIND_SYSTEM else self.examiner
        return {"questions": [dict(row, id=qid) for qid, row in table.items()]}


def blind_ok(answer="A"):
    return {"answer": answer, "also_valid": [], "unsolvable": False, "steps": "3X+24<=100"}


def examiner_ok():
    return {
        "verdict": "PASS",
        "difficulty_ok": True,
        "kaodian_ok": True,
        "style_ok": True,
        "analysis_ok": True,
        "brief_ok": True,
        "issues": [],
    }


class LocalChecks(unittest.TestCase):
    def test_clean_question_has_no_local_issue(self):
        self.assertEqual(quiz_lite.local_issues(stamped("b", 1)), [])

    def test_yanyu_requires_signal(self):
        row = stamped("b", 1)
        row["category"] = "言语理解与表达"
        row["tags"] = ["言语理解与表达-逻辑填空-成语填空"]
        row["stem"] = "这是一段有________的题干。"
        row["analysis"] = "根据语境辨析词语的感情色彩和搭配关系，结合上下文确定唯一选项，故选 A。"
        self.assertTrue(any("缺少 kaodian_signal" in issue for issue in quiz_lite.local_issues(row)))

    def test_duplicate_option_text_is_caught(self):
        row = stamped("b", 1)
        row["options"][1]["text"] = row["options"][0]["text"]
        self.assertIn("选项文本重复", quiz_lite.local_issues(row))

    def test_answer_outside_options_is_caught(self):
        row = stamped("b", 1)
        row["answer"] = "E"
        self.assertIn("answer 不在选项内", quiz_lite.local_issues(row))

    def test_missing_option_is_caught(self):
        row = stamped("b", 1)
        row["options"] = row["options"][:3]
        self.assertIn("选项必须是 A/B/C/D 四项", quiz_lite.local_issues(row))

    def test_non_object_option_is_rejected_without_crashing(self):
        row = stamped("b", 1)
        row["options"][1] = "not-an-option-object"
        self.assertIn("选项必须是 A/B/C/D 四项", quiz_lite.local_issues(row))

    def test_writer_shape_normalizes_question_and_packed_options(self):
        row = quiz_lite.normalize_writer_shape({
            "question": "题干足够长，且包含一个________空格。",
            "options": ["A. 甲 B. 乙 C. 丙 D. 丁"],
        })
        self.assertEqual(row["stem"], "题干足够长，且包含一个________空格。")
        self.assertEqual([item["key"] for item in row["options"]], ["A", "B", "C", "D"])

    def test_writer_shape_normalizes_options_string_and_mapping(self):
        packed = quiz_lite.normalize_writer_shape({
            "stem": "题干足够长足够长足够长足够",
            "options": "A. 1/8 B. 1/6 C. 1/5 D. 1/4",
        })
        self.assertEqual([item["text"] for item in packed["options"]], ["1/8", "1/6", "1/5", "1/4"])
        mapped = quiz_lite.normalize_writer_shape({
            "stem": "题干足够长足够长足够长足够",
            "options": {"A": "1/8", "B": "1/6", "C": "1/5", "D": "1/4"},
        })
        self.assertEqual([item["key"] for item in mapped["options"]], ["A", "B", "C", "D"])

    def test_stamp_and_public_tolerate_string_options(self):
        raw = question(1)
        raw["options"] = "A. 25本 B. 26本 C. 27本 D. 28本"
        row = quiz_lite.stamp({"module": "数量关系", "batch_id": "b"}, raw, 0, SLOT, "源")
        self.assertEqual(quiz_lite.local_issues(row), [])
        self.assertEqual([item["key"] for item in quiz_lite.public(row, False)["options"]], ["A", "B", "C", "D"])

    def test_yanyu_mold_validator_is_applied_to_final_batch(self):
        rows = [stamped("b", 1), stamped("b", 2)]
        for row in rows:
            row["category"] = "言语理解与表达"
            row["tags"] = ["言语理解与表达-逻辑填空-成语填空"]
            row["stem"] = "不仅需要统筹规划，更是要________，才能完成任务。"
            row["kaodian_signal"] = "成语语境辨析"
        with self.assertRaises(ValueError):
            quiz_lite.validate_yanyu_fills(rows)

    def test_short_analysis_is_caught(self):
        row = stamped("b", 1)
        row["analysis"] = "选 A"
        self.assertIn("解析过短，无法复算", quiz_lite.local_issues(row))

    def test_unordered_numeric_options_are_caught(self):
        row = stamped("b", 1)
        for option, text in zip(row["options"], ["10", "12", "18", "15"]):
            option["text"] = text
        self.assertIn("数值选项没按大小排，A→D 要么升序要么降序", quiz_lite.local_issues(row))

    def test_ordered_numeric_options_pass(self):
        for texts in (
            ["10", "12", "15", "18"],
            ["18个", "15个", "12个", "10个"],
            ["5/16", "3/8", "7/16", "9/16"],
        ):
            row = stamped("b", 1)
            for option, text in zip(row["options"], texts):
                option["text"] = text
            self.assertEqual(quiz_lite.local_issues(row), [], texts)

    def test_text_options_skip_the_ordering_check(self):
        row = stamped("b", 1)
        row["category"] = "判断推理"
        for option, text in zip(row["options"], ["甲", "乙", "丙", "丁"]):
            option["text"] = text
        self.assertEqual(quiz_lite.local_issues(row), [])

    def test_item_index_tolerates_junk(self):
        self.assertEqual(quiz_lite.item_index({"index": "3"}), 3)
        self.assertEqual(quiz_lite.item_index({"index": "第三题"}), 0)
        self.assertEqual(quiz_lite.item_index({}), 0)

    def test_duplicate_stem_detects_near_identical(self):
        stem = "某单位将100本书分给6个科室，各科室互不相同，问第三名最多分得多少本？"
        near = "某单位将100本书分给6个科室，各科室互不相同，问第三名最多分到多少本？"
        self.assertTrue(quiz_lite.duplicate_stem(stem, [near]))
        self.assertFalse(quiz_lite.duplicate_stem(stem, ["某企业7名骨干总分590分，问第四名最少得多少分？"]))

    def test_stamp_strips_images_and_keeps_the_writers_own_answer(self):
        raw = question(1, answer="B")
        raw["stem_images"] = ["images/x.png"]
        row = quiz_lite.stamp({"module": "数量关系", "batch_id": "b"}, raw, 0, SLOT, "源")
        self.assertNotIn("stem_images", row)
        self.assertEqual(row["external_id"], "b_01")
        self.assertEqual(row["tags"], [TAG])
        # 不再按计划表改字母：一改就给了模型倒推数据去凑字母的理由。
        self.assertEqual(row["answer"], "B")
        self.assertEqual(
            [o["text"] for o in row["options"]], ["25本", "26本", "27本", "28本"]
        )

    def test_mixed_slots_source_label_is_ladder_not_first_slot(self):
        slots = [
            {"tag": TAG, "count": 4, "difficulty": "easy"},
            {"tag": TAG, "count": 3, "difficulty": "mid"},
            {"tag": TAG, "count": 3, "difficulty": "hard"},
        ]
        self.assertEqual(
            quiz_lite.source_difficulty_label("20260921_hermes_gailv_chouqian_01", None, slots),
            "ladder",
        )
        self.assertEqual(
            quiz_lite.source_difficulty_label(
                "20260921_hermes_gailv_chouqian_ladder_01", None, [{"tag": TAG, "count": 10}]
            ),
            "ladder",
        )
        self.assertEqual(
            quiz_lite.source_difficulty_label("b", "hard", [{"tag": TAG, "count": 5, "difficulty": "hard"}]),
            "hard",
        )

    def test_stamp_overwrites_model_difficulty_with_declared_tier(self):
        raw = question(1)
        raw["difficulty"] = "easy"  # 模型爱写字符串，题库要 1~5 的整数
        row = quiz_lite.stamp({"module": "数量关系", "batch_id": "b"}, raw, 0, SLOT, "源")
        self.assertEqual(row["difficulty"], quiz_lite.TIER_TO_LEVEL["hard"])

    def test_partial_ladder_defaults_missing_slot_to_mid(self):
        slots = [{"tag": TAG, "count": 1, "difficulty": "hard"}, {"tag": TAG, "count": 1}]
        self.assertEqual(quiz_lite.source_difficulty_label("b", None, slots), "ladder")
        self.assertEqual(quiz_lite.tier_of({"difficulty": "ladder"}, slots[1]), "mid")
        self.assertEqual(quiz_lite.source_difficulty_label("b", None, [slots[1]]), "mid")
        self.assertEqual(quiz_lite.source_difficulty_label("b", "mid", [slots[0]]), "hard")

    def test_scratchpad_leak_in_analysis_is_caught(self):
        row = stamped("b", 1)
        row["analysis"] = (
            "设第三名为 X，列式 3X + 24 ≤ 100。为了让答案等于 12，把总数调整为 112 本，"
            "因此解得 X = 12，故选 B。"
        )
        self.assertTrue(
            any("倒推答案的草稿" in issue for issue in quiz_lite.local_issues(row))
        )


class ReviewDecisions(unittest.TestCase):
    def setUp(self):
        self.run = {
            "module": "数量关系",
            "batch_id": "b",
            "difficulty": "hard",
            "slots": [{"tag": TAG, "count": 1}],
        }
        self.per_item = [{"tag": TAG, "count": 1, "difficulty": "hard"}]
        self.questions = [stamped("b", 1)]
        self.original_call = quiz_lite.call

    def tearDown(self):
        quiz_lite.call = self.original_call

    def review_with(self, blind, examiner):
        quiz_lite.call = FakeModel([], {"b_01": blind}, {"b_01": examiner})
        return quiz_lite.review(self.run, self.questions, self.per_item)["b_01"]

    def test_agreeing_reviewers_pass(self):
        self.assertEqual(self.review_with(blind_ok(), examiner_ok())["verdict"], "PASS")

    def test_incomplete_or_wrong_type_blind_evidence_rejects(self):
        for field, bad in (("unsolvable", "false"), ("also_valid", ""), ("steps", [])):
            for missing in (True, False):
                with self.subTest(field=field, missing=missing):
                    blind = blind_ok()
                    if missing:
                        blind.pop(field)
                    else:
                        blind[field] = bad
                    self.assertEqual(self.review_with(blind, examiner_ok())["verdict"], "REJECT")

    def test_reject_without_explanation_and_failed_brief_reject(self):
        for override in ({"verdict": "REJECT", "issues": []}, {"brief_ok": False}):
            self.assertEqual(self.review_with(blind_ok(), {**examiner_ok(), **override})["verdict"], "REJECT")

    def test_brief_reaches_examiner_but_blind_gets_no_writer_hint(self):
        self.per_item[0]["brief"] = "至少一道比较不同年份"
        self.questions[0]["kaodian_signal"] = "writer-secret-hint"
        prompts = {}
        def fake(system, prompt, temperature, timeout):
            prompts[system] = prompt
            row = blind_ok() if system == quiz_lite.BLIND_SYSTEM else examiner_ok()
            return {"questions": [dict(row, id="b_01")]}
        quiz_lite.call = fake
        quiz_lite.review(self.run, self.questions, self.per_item)
        self.assertIn(self.per_item[0]["brief"], prompts[quiz_lite.EXAMINER_SYSTEM])
        self.assertIn('"batch_questions"', prompts[quiz_lite.EXAMINER_SYSTEM])
        self.assertNotIn("writer-secret-hint", prompts[quiz_lite.BLIND_SYSTEM])

    def test_blind_answering_differently_rejects(self):
        result = self.review_with(blind_ok("B"), examiner_ok())
        self.assertEqual(result["verdict"], "REJECT")
        self.assertTrue(any("盲解官独立解出 B" in issue for issue in result["issues"]))

    def test_second_valid_option_rejects(self):
        blind = blind_ok()
        blind["also_valid"] = ["C"]
        result = self.review_with(blind, examiner_ok())
        self.assertEqual(result["verdict"], "REJECT")
        self.assertTrue(any("答案不唯一" in issue for issue in result["issues"]))

    def test_unsolvable_rejects(self):
        blind = blind_ok()
        blind.update({"unsolvable": True, "reason": "四个选项都不含正确值 30"})
        result = self.review_with(blind, examiner_ok())
        self.assertEqual(result["verdict"], "REJECT")
        self.assertTrue(any("无解" in issue for issue in result["issues"]))

    def test_examiner_flag_rejects_even_when_blind_agrees(self):
        examiner = examiner_ok()
        examiner.update({"verdict": "REJECT", "difficulty_ok": False, "issues": ["一步就出答案"]})
        result = self.review_with(blind_ok(), examiner)
        self.assertEqual(result["verdict"], "REJECT")
        self.assertIn("难度不匹配声明档位", result["issues"])

    def test_missing_reviewer_rejects(self):
        quiz_lite.call = FakeModel([], {}, {"b_01": examiner_ok()})
        result = quiz_lite.review(self.run, self.questions, self.per_item)["b_01"]
        self.assertEqual(result["verdict"], "REJECT")
        self.assertIn("盲解官无结论", result["issues"])


class PartialReissue(unittest.TestCase):
    def setUp(self):
        self.original_call = quiz_lite.call
        self.run = {
            "module": "数量关系",
            "batch_id": "b",
            "planned_count": 2,
            "slots": [{"tag": TAG, "count": 2, "difficulty": "hard"}],
            "difficulty": "hard",
        }

    def tearDown(self):
        quiz_lite.call = self.original_call

    def test_only_the_rejected_index_is_asked_again(self):
        first = [question(1), question(2, stem="某企业7名骨干总分590分，问排名第四者最少得多少分？")]
        second = [question(2, stem="某机关8个科室共620件督办任务，问第二名最少完成多少件？")]
        fake = FakeModel(
            [first, second],
            {"b_01": blind_ok(), "b_02": blind_ok()},
            {"b_01": examiner_ok(), "b_02": examiner_ok()},
        )
        # 第一轮第 2 题被盲解官否掉，第二轮同一个 id 必须换成一致的结论。
        rounds = {"n": 0}

        def call(system, prompt, temperature, timeout):
            if system == quiz_lite.BLIND_SYSTEM:
                rounds["n"] += 1
                if rounds["n"] == 1:
                    return {
                        "questions": [
                            dict(blind_ok(), id="b_01"),
                            dict(blind_ok("D"), id="b_02"),
                        ]
                    }
            return fake(system, prompt, temperature, timeout)

        quiz_lite.call = call
        questions, results, log = quiz_lite.build_batch(self.run, 3, "源")

        self.assertEqual([q["external_id"] for q in questions], ["b_01", "b_02"])
        self.assertEqual(sorted(results), ["b_01", "b_02"])
        self.assertTrue(all(item["verdict"] == "PASS" for item in results.values()))
        self.assertEqual([entry["asked"] for entry in log], [[1, 2], [2]])
        self.assertEqual([row["question_id"] for row in log[0]["rejected"]], ["b_02"])
        self.assertTrue(
            any("盲解官独立解出 D" in issue for issue in log[0]["rejected"][0]["issues"])
        )
        self.assertEqual(log[1]["rejected"], [])
        # 第二轮的出稿提示必须带上退回原因和已保留的题，免得重出时撞题。
        self.assertIn("上一轮被退回的原因", fake.writer_prompts[1])
        self.assertIn("本批次已通过的题", fake.writer_prompts[1])

    def test_exhausting_rounds_raises_with_reason(self):
        bad = [[question(1)], [question(1)]]
        fake = FakeModel(bad, {"b_01": blind_ok("D")}, {"b_01": examiner_ok()})
        quiz_lite.call = fake
        run = dict(self.run, planned_count=1, slots=[{"tag": TAG, "count": 1}])
        with self.assertRaises(RuntimeError) as caught:
            quiz_lite.build_batch(run, 2, "源")
        self.assertIn("盲解官独立解出 D", str(caught.exception))

    def test_brief_rechecks_kept_items_after_replacement(self):
        self.run["slots"][0]["brief"] = "至少一题用不同场景"
        fake = FakeModel([[question(1), question(2, stem="某企业7名骨干总分590分，问排名第四者最少得多少分？")],
                          [question(2, stem="某机关8个科室共620件督办任务，问第二名最少完成多少件？")]],
                         {"b_01": blind_ok(), "b_02": blind_ok()}, {"b_01": examiner_ok(), "b_02": examiner_ok()})
        prompts = []
        rounds = 0
        def call(system, prompt, temperature, timeout):
            nonlocal rounds
            if system == quiz_lite.BLIND_SYSTEM:
                rounds += 1
                if rounds == 1:
                    return {"questions": [dict(blind_ok(), id="b_01"), dict(blind_ok("D"), id="b_02")]}
            if system == quiz_lite.EXAMINER_SYSTEM:
                prompts.append(json.loads(prompt.split("\n", 1)[1]))
            return fake(system, prompt, temperature, timeout)
        quiz_lite.call = call
        quiz_lite.build_batch(self.run, 3, "源")
        self.assertEqual(len(prompts), 2)
        self.assertEqual(len(prompts[1]["items"]), 2)


class LiteReceipt(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "manifest.json").write_text(
            json.dumps({"batch_id": "b", "kind": "ai-generated"}), encoding="utf-8"
        )
        (self.dir / "questions.json").write_text(
            json.dumps([stamped("b", 1)], ensure_ascii=False), encoding="utf-8"
        )

    def evidence(self, **overrides):
        import hashlib

        base = {
            "kind": "examsystem-lite-review",
            "batch_id": "b",
            "model": "gemini-3.8-flash-high",
            "verdict": "PASS",
            "questions_sha256": hashlib.sha256(
                (self.dir / "questions.json").read_bytes()
            ).hexdigest(),
            "results": [
                {
                    "question_id": "b_01",
                    "answer": "A",
                    "verdict": "PASS",
                    "blind": blind_ok(),
                    "examiner": examiner_ok(),
                }
            ],
        }
        base.update(overrides)
        return base

    def test_consistent_evidence_passes(self):
        validate_lite_review(self.dir, self.evidence(), ["b_01"])

    def test_consistent_but_forged_answers_do_not_override_question(self):
        evidence = self.evidence()
        evidence["results"][0]["answer"] = "B"
        evidence["results"][0]["blind"]["answer"] = "B"
        with self.assertRaises(ValueError):
            validate_lite_review(self.dir, evidence, ["b_01"])

    def test_edited_questions_file_fails(self):
        evidence = self.evidence()
        (self.dir / "questions.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_lite_review(self.dir, evidence, ["b_01"])

    def test_blind_answer_mismatch_fails(self):
        evidence = self.evidence()
        evidence["results"][0]["blind"]["answer"] = "C"
        with self.assertRaises(ValueError):
            validate_lite_review(self.dir, evidence, ["b_01"])

    def test_second_valid_option_fails(self):
        evidence = self.evidence()
        evidence["results"][0]["blind"]["also_valid"] = ["B"]
        with self.assertRaises(ValueError):
            validate_lite_review(self.dir, evidence, ["b_01"])

    def test_uncovered_question_fails(self):
        with self.assertRaises(ValueError):
            validate_lite_review(self.dir, self.evidence(), ["b_01", "b_02"])

    def test_non_flash_model_fails(self):
        with self.assertRaises(ValueError):
            validate_lite_review(self.dir, self.evidence(model="gemini-3.8-pro"), ["b_01"])


if __name__ == "__main__":
    unittest.main()

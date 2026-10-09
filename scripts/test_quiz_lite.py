#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import quiz_lite
import quiz_quantity
from generation_gate import validate_lite_review, verify

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
        self.writer_schemas = []

    def __call__(self, system, prompt, temperature, timeout, *, schema=None):
        if system == quiz_lite.WRITER_SYSTEM:
            self.writer_prompts.append(prompt)
            self.writer_schemas.append(schema)
            return {"questions": self.writer_rounds.pop(0)}
        table = self.blind if system in (quiz_lite.BLIND_SYSTEM, quiz_quantity.BLIND) else self.examiner
        return {"questions": [dict(row, id=qid) for qid, row in table.items()]}


def blind_ok(answer="A", tier="hard"):
    return {"answer": answer, "also_valid": [], "unsolvable": False, "steps": "3X+24<=100",
            "actual_difficulty": tier, "difficulty_reason": "需要比较两个失败分支，任一目标删除会改变保证发生的界。"}


def examiner_ok(tier="hard"):
    return {
        "actual_difficulty": tier,
        "difficulty_reason": "需比较两个不同的失败分支，删除其中任一目标会改变保证发生的界。",
        "analysis_check": "逐项核查界限与构造，紧邻的更优整数不可行；没有把可行分配误说成唯一分配。",
        "necessity_claims": [],
        "necessity_checks": [],
        "verdict": "PASS",
        "difficulty_ok": True,
        "kaodian_ok": True,
        "style_ok": True,
        "analysis_ok": True,
        "brief_ok": True,
        "issues": [],
    }


class LocalChecks(unittest.TestCase):
    def test_calendar_keeps_concrete_year_and_month_length_for_learner(self):
        row = stamped('b', 1)
        row['tags'] = ['数量关系-数学运算-星期日期问题']
        row['stem'] = '某年7月份共有31天，求这年9月1日是星期几？'
        self.assertTrue(any('具体公历年份' in x for x in quiz_lite.local_issues(row)))
        self.assertTrue(any('月天数' in x for x in quiz_lite.local_issues(row)))
        row['stem'] = '已知2024年3月1日是星期五，该月共有31天。问星期一、三、五一共有多少天？'
        self.assertTrue(any('月天数' in x for x in quiz_lite.local_issues(row)))
        row['stem'] = '2026年7月1日开始轮值，每隔5天值班一次，问9月1日前共轮值多少次？'
        self.assertFalse(any('公历年份' in x or '月天数' in x for x in quiz_lite.local_issues(row)))

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

    def test_writer_shape_repairs_escaped_prose_without_corrupting_tex(self):
        raw = {"stem": r"题干。\n\n以下哪项？", "analysis": r"第一步。\r\n第二步。$x\neq y,\nu=1$"}
        row = quiz_lite.normalize_writer_shape(raw)
        self.assertEqual(row["stem"], "题干。\n\n以下哪项？")
        self.assertEqual(row["analysis"], "第一步。\n第二步。" + r"$x\neq y,\nu=1$")
        self.assertEqual(raw["stem"], r"题干。\n\n以下哪项？")

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
            "mid",
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

    def test_unspecified_difficulty_is_auto_for_knowledge_practice(self):
        self.assertEqual(quiz_lite.tier_of({"module": "数量关系"}, {}), "auto")
        self.assertEqual(quiz_lite.tier_of({"module": "言语理解与表达"}, {}), "auto")
        self.assertEqual(quiz_lite.tier_of({"module": "判断推理"}, {}), "auto")
        self.assertEqual(quiz_lite.tier_of({"module": "数量关系", "difficulty": "hard"}, {}), "hard")
        self.assertEqual(quiz_lite.tier_of({"module": "数量关系", "difficulty": "hard"}, {"difficulty": "easy"}), "easy")

    def test_scratchpad_leak_in_analysis_is_caught(self):
        row = stamped("b", 1)
        row["analysis"] = (
            "设第三名为 X，列式 3X + 24 ≤ 100。为了让答案等于 12，把总数调整为 112 本，"
            "因此解得 X = 12，故选 B。"
        )
        self.assertTrue(
            any("倒推答案的草稿" in issue for issue in quiz_lite.local_issues(row))
        )

    def test_delivered_logic_analysis_rejects_self_correction_drafts(self):
        for phrase in ("等等，重新验证", "等一下", "调整本题答案为A更稳妥"):
            row = stamped("b", 1)
            row["category"] = "判断推理"
            row["analysis"] = "根据题干依次验证每个选项。" + phrase + "，重新检查逻辑推理无漏洞，对应A项。"
            self.assertTrue(any("倒推答案的草稿" in issue for issue in quiz_lite.local_issues(row)), phrase)


class UpstreamFailures(unittest.TestCase):
    def test_quantity_structured_output_never_salvages_multiple_drafts(self):
        draft = {'questions': [question(1)]}
        encoded = json.dumps(draft)
        tool = {'function': {'name': 'submit_questions', 'arguments': encoded}}
        messages = [
            ({'content': '修改草稿', 'tool_calls': [tool]}, True),
            ({'content': encoded}, True),
            ({'content': encoded + encoded}, False),
            ({'content': encoded + '\n再次检查第1题：修改题干'}, False),
            ({'tool_calls': [tool, tool]}, False),
            ({'content': encoded, 'tool_calls': [{'function': {
                'name': 'submit_questions', 'arguments': encoded + encoded}}]}, False),
        ]
        for message, valid in messages:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({'choices': [{
                'finish_reason': 'stop', 'message': message,
            }]}).encode()
            with self.subTest(message=message), patch.object(quiz_lite, 'api_key', return_value='test'), \
                    patch.object(quiz_lite.urllib.request, 'urlopen', return_value=response) as request:
                if valid:
                    self.assertEqual(quiz_lite.call(quiz_lite.WRITER_SYSTEM, 'prompt', 0.5, 1,
                                                   schema=quiz_quantity.WRITER_SCHEMA), draft)
                else:
                    with self.assertRaisesRegex(RuntimeError, '无法解析.*未自动重试'):
                        quiz_lite.call(quiz_lite.WRITER_SYSTEM, 'prompt', 0.5, 1,
                                       schema=quiz_quantity.WRITER_SCHEMA)
                request.assert_called_once()
                body = json.loads(request.call_args.args[0].data)
                self.assertEqual(body['tool_choice']['function']['name'], 'submit_questions')
                self.assertEqual(body['tools'][0]['function']['parameters'], quiz_quantity.WRITER_SCHEMA)
                self.assertNotIn('response_format', body)

    def test_structured_review_requires_one_valid_tool_result_without_retry(self):
        row = {'c0': 'REJECT 词义限制不成立，有自然用法反例'}
        tool = {'function': {'name': 'submit_review', 'arguments': json.dumps(row)}}
        for calls, valid in [([tool], True), ([], False), ([tool, tool], False),
                             ([{'function': {'name': 'other', 'arguments': json.dumps(row)}}], False),
                             ([{'function': {'name': 'submit_review', 'arguments': json.dumps({'c0': 'PASS'})}}], False),
                             ([{'function': {'name': 'submit_review', 'arguments': json.dumps({'c1': 'PASS 依据'})}}], False),
                             ([{'function': {'name': 'submit_review', 'arguments': '{'}}], False)]:
            response = MagicMock()
            # Text is not a fallback for missing or malformed structured review.
            payload = {'choices': [{'finish_reason': 'tool_calls', 'message': {
                'content': json.dumps(row), 'tool_calls': calls}}]}
            response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            with self.subTest(calls=calls), patch.object(quiz_lite, 'api_key', return_value='test'), \
                    patch.object(quiz_lite.urllib.request, 'urlopen', return_value=response) as request:
                if valid:
                    self.assertEqual(quiz_lite.call('system', 'prompt', 0, 1, schema={'type': 'object', 'required': ['c0']}), row)
                else:
                    with self.assertRaisesRegex(RuntimeError, '无法解析.*未自动重试'):
                        quiz_lite.call('system', 'prompt', 0, 1, schema={'type': 'object', 'required': ['c0']})
                request.assert_called_once()
                sent = json.loads(request.call_args.args[0].data)
                self.assertEqual(sent['model'], 'gemini-3.8-flash-high')
                self.assertNotIn('response_format', sent)
                self.assertEqual(sent['tool_choice']['function']['name'], 'submit_review')

    def test_invalid_escape_is_preserved_without_another_model_call(self):
        content = r'{"questions":[{"index":1,"analysis":"$\alpha+\\beta$，路径 C:\math"}]}'
        payload = {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with tempfile.TemporaryDirectory() as tmp:
            token = quiz_lite.MODEL_AUDIT_DIR.set(Path(tmp))
            try:
                with patch.object(quiz_lite, 'api_key', return_value='test'), \
                        patch.object(quiz_lite.urllib.request, 'urlopen', return_value=response) as request:
                    parsed = quiz_lite.call('system', 'prompt', 0, 1)
                self.assertEqual(parsed['questions'][0]['analysis'], r'$\alpha+\beta$，路径 C:\math')
                request.assert_called_once()
                record = json.loads(next(Path(tmp).glob('*.json')).read_text())
                self.assertEqual(json.loads(record['response']), payload)
            finally:
                quiz_lite.MODEL_AUDIT_DIR.reset(token)

    def test_broken_structure_still_fails_and_retains_original_response(self):
        content = '{"questions":[{"answer":"A"}'
        payload = {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with tempfile.TemporaryDirectory() as tmp:
            token = quiz_lite.MODEL_AUDIT_DIR.set(Path(tmp))
            try:
                with patch.object(quiz_lite, 'api_key', return_value='test'), \
                        patch.object(quiz_lite.urllib.request, 'urlopen', return_value=response) as request:
                    with self.assertRaisesRegex(RuntimeError, '无法解析.*未自动重试'):
                        quiz_lite.call('system', 'prompt', 0, 1)
                request.assert_called_once()
                record = json.loads(next(Path(tmp).glob('*.json')).read_text())
                self.assertEqual(json.loads(record['response']), payload)
            finally:
                quiz_lite.MODEL_AUDIT_DIR.reset(token)

    def test_truncated_json_never_reaches_parser(self):
        payload = {"choices": [{"finish_reason": "length", "message": {"content": '{"questions":[]}'}}]}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with patch.object(quiz_lite, "api_key", return_value="test"), \
                patch.object(quiz_lite.urllib.request, "urlopen", return_value=response) as request, \
                patch.object(quiz_lite, "parse_json") as parser:
            with self.assertRaisesRegex(RuntimeError, "回答被截断.*未完成"):
                quiz_lite.call("system", "prompt", 0, 1)
        request.assert_called_once()
        parser.assert_not_called()

    def test_upstream_error_is_reported_without_retry(self):
        with patch.object(quiz_lite, "api_key", return_value="test"), \
                patch.object(quiz_lite.urllib.request, "urlopen", side_effect=TimeoutError("timeout")) as request:
            with self.assertRaisesRegex(RuntimeError, "上游调用失败，未自动重试"):
                quiz_lite.call("system", "prompt", 0, 1)
        request.assert_called_once()


class ScopePlan(unittest.TestCase):
    def test_source_name_preserves_scope_and_labels_chinese_difficulty(self):
        from datetime import date
        today = date(2026, 9, 25)
        base = {'tag': TAG + '-@test', 'count': 1, 'scope_title': '排列组合问题'}
        for tier, label in [('easy', '简单'), ('mid', '中等'), ('hard', '困难'), ('auto', '综合')]:
            with self.subTest(tier=tier):
                self.assertEqual(quiz_lite.source_name('数量关系', [{**base, 'difficulty': tier}], today),
                                 f'广东省考行测-数量关系-排列组合问题-{label}-20260925')
        slots = [{**base, 'difficulty': tier} for tier in ['easy', 'mid', 'hard']]
        self.assertEqual(quiz_lite.source_name('数量关系', slots, today),
                         '广东省考行测-数量关系-排列组合问题-综合-20260925')
        child = {**base, 'scope_title': '排列组合问题-位置限制与排队'}
        self.assertEqual(quiz_lite.source_name('数量关系', [child], today, 'hard'),
                         '广东省考行测-数量关系-排列组合问题-位置限制与排队-困难-20260925')
        self.assertEqual(quiz_lite.source_name('数量关系', [child], today),
                         '广东省考行测-数量关系-排列组合问题-位置限制与排队-中等-20260925')

    def test_default_source_modules_expand_current_children(self):
        import policy_quiz
        import quiz_scope
        for module, count in (("政治理论", 10), ("常识判断", 6)):
            with self.subTest(module=module), tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
                seeds = policy_quiz.module_slots(module, count, "mid")
                tags = list(dict.fromkeys(slot["tag"] for slot in seeds))
                nodes = {tag: {"tag": tag, "title": tag.split("-")[-1], "parentTag": None} for tag in tags}
                parent = tags[0]
                children = [parent + "-@new-one", parent + "-@new-two"]
                nodes.update({tag: {"tag": tag, "title": f"新增子点{i+1}", "parentTag": parent,
                                    "definition": f"只考新增子点{i+1}的边界", "content": True,
                                    "content_revision": 2} for i, tag in enumerate(children)})
                args = ["quiz_lite.py", "--module", module, "--count", str(count),
                        "--batch-id", "default-plan", "--plan-only", "--db", str(Path(tmp) / "absent.db")]
                output = io.StringIO()
                with patch.object(sys, "argv", args), patch.object(quiz_scope, "catalog", return_value=nodes), \
                        patch.object(quiz_lite, "source_pack") as sources, \
                        patch.object(quiz_lite, "build_batch") as generate, contextlib.redirect_stdout(output):
                    self.assertEqual(quiz_lite.main(), 0)
                slots = json.loads(output.getvalue())["slots"]
                allocated = [slot["tag"] for slot in slots if slot["scope_tag"] == parent]
                self.assertEqual(allocated, children)
                self.assertEqual(sum(slot["count"] for slot in slots), count)
                self.assertTrue(all(slot["difficulty"] == "auto" for slot in slots))
                sources.assert_not_called()
                generate.assert_not_called()

    def test_titles_name_the_whole_scope_and_hide_node_ids(self):
        slots = [{"tag": TAG + "-和定最值与构造", "count": 2},
                 {"tag": TAG + "-最不利原则与抽屉", "count": 2}]
        self.assertEqual(quiz_lite.source_topic("数量关系", slots), "最值问题")
        self.assertEqual(quiz_lite.source_topic("数量关系", slots[:1]), "最值问题-和定最值与构造")
        dynamic = [{"tag": "数量关系-数学运算-工程问题-@test-node", "count": 2,
                    "display_title": "给定效率比例"}]
        self.assertEqual(quiz_lite.source_topic("数量关系", dynamic), "工程问题-给定效率比例")
        dynamic[0].pop("display_title")
        with self.assertRaisesRegex(ValueError, "展示名称"):
            quiz_lite.source_topic("数量关系", dynamic)
        language = [{"tag": f"言语理解与表达-片段阅读-{name}", "count": 1}
                    for name in ("中心理解题", "细节判断题", "标题填入题")]
        self.assertEqual(quiz_lite.source_topic("言语理解与表达", language), "片段阅读")
        # A parent request stays a parent title even when its quota picks one leaf.
        dynamic[0]['scope_title'] = '工程问题'
        self.assertEqual(quiz_lite.source_topic('数量关系', dynamic), '工程问题')
        dynamic[0]['scope_title'] = '工程问题-效率变化 · 计划与实际'
        self.assertEqual(quiz_lite.source_topic('数量关系', dynamic), '工程问题-效率变化 · 计划与实际')

    def test_plan_only_is_read_only_and_resolves_all_difficulty_slots(self):
        for module, tag in [("数量关系", TAG), ("政治理论", "政治理论-时事政治-重要文件")]:
            with self.subTest(module=module), tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
                slots = [{"tag": tag, "count": 1, "difficulty": "easy"}, {"tag": tag, "count": 1}]
                args = ["quiz_lite.py", "--module", module, "--tag", tag, "--count", "2",
                        "--difficulty", "hard", "--batch-id", "scope-plan", "--plan-only",
                        "--db", str(Path(tmp) / "never-created.db")]
                output = io.StringIO()
                with patch.object(sys, "argv", args), patch.object(quiz_lite, "resolve_slots", return_value=(module, slots)), \
                        patch.object(quiz_lite.sqlite3, "connect") as connect, \
                        patch.object(quiz_lite, "source_pack") as sources, \
                        patch.object(quiz_lite, "build_batch") as generate, \
                        contextlib.redirect_stdout(output):
                    self.assertEqual(quiz_lite.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(plan["status"], "planned")
                self.assertEqual(plan["count"], 2)
                self.assertEqual([s["difficulty"] for s in plan["slots"]], ["easy", "hard"])
                self.assertTrue(plan["source"].startswith(f"广东省考行测-{module}-{tag.split('-')[-1]}-"))
                self.assertNotIn("-ladder-", plan["source"])
                self.assertIn('-综合-', plan['source'])
                connect.assert_not_called()
                sources.assert_not_called()
                generate.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_manifest_and_gate_enforce_actual_slots_for_nonpolitical_lite(self):
        other = "数量关系-数学运算-工程问题"
        slots = [{"tag": TAG, "count": 1, "difficulty": "easy"},
                 {"tag": other, "count": 1}]
        run = {"module": "数量关系", "batch_id": "slot-gate", "difficulty": "hard", "slots": slots}
        rows = [quiz_lite.stamp(run, question(i + 1), i, slot, "test") for i, slot in enumerate(slots)]
        results = {q["external_id"]: {"question_id": q["external_id"], "answer": "A", "verdict": "PASS",
                   "blind": blind_ok(tier=quiz_lite.tier_of(run, slot)),
                   "examiner": examiner_ok(tier=quiz_lite.tier_of(run, slot))}
                   for q, slot in zip(rows, slots)}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            quiz_lite.write_batch(run, directory, rows, "test")
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertEqual(manifest["difficulty_tier"], "ladder")
            self.assertEqual([s["difficulty"] for s in manifest["generation"]["batch_constraints"]["slot_plan"]],
                             ["easy", "hard"])
            quiz_lite.sign(directory, run, results, [])
            self.assertTrue(verify(directory)["ok"])
            # Re-sign each malformed artifact: the hard check must catch it, not merely the hash.
            for defect in ("difficulty", "order", "count", "missing_plan"):
                altered = json.loads(json.dumps(rows))
                if defect == "difficulty":
                    altered[0]["difficulty"] = 4
                elif defect == "order":
                    altered[0]["tags"], altered[1]["tags"] = altered[1]["tags"], altered[0]["tags"]
                elif defect == "count":
                    altered.pop()
                quiz_lite.write_batch(run, directory, altered, "test")
                if defect == "missing_plan":
                    manifest = json.loads((directory / "manifest.json").read_text())
                    manifest["generation"]["batch_constraints"].pop("slot_plan")
                    (directory / "manifest.json").write_text(json.dumps(manifest))
                quiz_lite.sign(directory, run, results, [])
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    verify(directory)


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

    def test_repeated_review_ids_cannot_override_a_rejection(self):
        for role in ('blind', 'examiner'):
            blind = [dict(blind_ok(), id='b_01')]
            examiner = [dict(examiner_ok(), id='b_01')]
            if role == 'blind':
                blind.insert(0, dict(blind_ok('B'), id='b_01'))
            else:
                examiner.insert(0, dict(examiner_ok(), id='b_01', verdict='REJECT', analysis_ok=False))
            with self.subTest(role=role), patch.object(quiz_lite, 'call', side_effect=[
                    {'questions': blind}, {'questions': examiner}]):
                result = quiz_lite.review(self.run, self.questions, self.per_item)['b_01']
            self.assertEqual(result['verdict'], 'REJECT')
            self.assertIn('盲解官无结论' if role == 'blind' else '考官无结论', result['issues'])

    def test_auto_difficulty_disagreement_does_not_waive_math_checks(self):
        self.run['difficulty'] = 'auto'
        self.per_item[0]['difficulty'] = 'auto'
        self.assertEqual(self.review_with(blind_ok(tier='easy'), examiner_ok('mid'))['verdict'], 'PASS')
        self.assertEqual(self.review_with(blind_ok('B', 'easy'), examiner_ok('mid'))['verdict'], 'REJECT')
        self.assertEqual(self.review_with(blind_ok(tier='easy'), {**examiner_ok('mid'), 'analysis_ok': False})['verdict'], 'REJECT')

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
        self.per_item[0]['sibling_topics'] = [{'tag': '数量关系-数学运算-牛吃草问题', 'title': '牛吃草问题'}]
        self.questions[0]["kaodian_signal"] = "writer-secret-hint"
        prompts = {}
        def fake(system, prompt, temperature, timeout):
            prompts[system] = prompt
            row = blind_ok() if system in (quiz_lite.BLIND_SYSTEM, quiz_quantity.BLIND) else examiner_ok()
            return {"questions": [dict(row, id="b_01")]}
        quiz_lite.call = fake
        quiz_lite.review(self.run, self.questions, self.per_item)
        self.assertIn(self.per_item[0]["brief"], prompts[quiz_quantity.EXAMINER])
        self.assertIn('"batch_questions"', prompts[quiz_quantity.EXAMINER])
        self.assertNotIn("writer-secret-hint", prompts[quiz_quantity.BLIND])
        self.assertNotIn('"declared_difficulty"', prompts[quiz_quantity.BLIND])
        examiner_payload = json.loads(prompts[quiz_quantity.EXAMINER].split("\n", 1)[1])
        self.assertNotIn("blind_work", examiner_payload["items"][0])
        self.assertEqual(examiner_payload['items'][0]['sibling_topics'], self.per_item[0]['sibling_topics'])
        self.run['slots'] = self.per_item
        prompt = quiz_lite.writer_prompt(self.run, [{'tag': TAG, 'index': 1}], [])
        self.assertEqual(json.loads(prompt.splitlines()[1])['sibling_topics'][TAG], self.per_item[0]['sibling_topics'])

    def test_quantity_has_independent_rules_without_template_constraints(self):
        writer = quiz_lite.writer_prompt(self.run, [{"tag": TAG, "difficulty": "hard", "index": 1}], [])
        self.assertIn(quiz_quantity.DIFFICULTY, writer)
        self.assertIn(quiz_quantity.MATH, writer)
        self.assertNotIn(quiz_lite.DIFFICULTY_RULES, writer)
        self.assertNotIn("唯一解题动作", writer)
        self.assertIn("任何适用且正确的解法", writer)
        self.assertIn("界限和可达性", quiz_quantity.BLIND)
        self.assertIn("相邻整数", quiz_quantity.EXAMINER)
        self.assertEqual(self.review_with(blind_ok(), {**examiner_ok(), "analysis_ok": False})["verdict"], "REJECT")

    def test_examiner_must_substantiate_difficulty_and_analysis(self):
        for field in ("actual_difficulty", "difficulty_reason", "analysis_check"):
            for value in (None, "", []):
                with self.subTest(field=field, value=value):
                    result = self.review_with(blind_ok(), {**examiner_ok(), field: value})
                    self.assertEqual(result["verdict"], "REJECT")
        result = self.review_with(blind_ok(), examiner_ok("mid"))
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["examiner"]["actual_difficulty"], "mid")
        self.assertEqual(result["examiner"]["analysis_check"], examiner_ok()["analysis_check"])

    def test_quantity_hard_accepts_mid_but_not_easy_from_either_reviewer(self):
        result = self.review_with(blind_ok(tier="mid"), examiner_ok())
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["blind"]["actual_difficulty"], "mid")
        for blind, examiner in ((blind_ok(tier="easy"), examiner_ok()),
                                (blind_ok(), examiner_ok("easy"))):
            self.assertEqual(self.review_with(blind, examiner)["verdict"], "REJECT")
        for field in ("actual_difficulty", "difficulty_reason"):
            result = self.review_with({**blind_ok(), field: None}, examiner_ok())
            self.assertEqual(result["verdict"], "REJECT")

    def test_necessity_claim_requires_exact_check_and_valid_reason(self):
        claim = "奇数人次只能分给非目标组，因此必须有一个人承担三项"
        self.questions[0]["analysis"] += "\n" + claim + "。"
        self.assertEqual(self.review_with(blind_ok(), examiner_ok())["verdict"], "REJECT")
        good = {"claim_index": 0, "valid": True, "reason": "已排除其他合法分配"}
        for changes in ({"valid": False, "reason": "余数可交给一个目标者"},
                        {"claim_index": 1}, {"claim_index": True}, {"reason": ""}, {"valid": "true"}):
            row = {**examiner_ok(), "necessity_checks": [{**good, **changes}]}
            self.assertEqual(self.review_with(blind_ok(), row)["verdict"], "REJECT")
        self.assertEqual(self.review_with(blind_ok(), {**examiner_ok(), "necessity_checks": [good]})["verdict"], "PASS")

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

    def test_quantity_groups_keep_global_indices_and_actual_difficulty(self):
        run = {**self.run, 'planned_count': 10, 'difficulty': None,
               'slots': [{'tag': TAG, 'count': 10, 'difficulty': 'auto',
                          'brief': '广东省考难度，命题倾向，非硬性难度门槛'}]}
        stems = ['甲乙两队合作完成工程，甲单独需要十二天，乙十八天，合作多少天？',
                 '袋中红球三只蓝球五只，随机取出两个，颜色相同的概率是多少？',
                 '商品原价三百元，打八折再减二十元，实际售价为多少元？',
                 '五名选手分数共一百六十分，最高四十五分，第二名至少多少分？',
                 '甲乙两车在相距三百公里的两地同时相向出发，何时相遇？',
                 '六人随机排成一行，其中指定两人不相邻的排法有多少种？',
                 '数列各项由前两项相加得到，前两项为一和二，第八项为多少？',
                 '某班参加书法与绘画的人数分别为十八和二十，都参加的有六人，至少参加一项的有多少人？',
                 '长方形的周长四十厘米，长比宽多四厘米，面积是多少平方厘米？',
                 '三个部门共采购一百二十台电脑，其中研发部是行政部的两倍，销售部占多少台？']
        rows = [question(i + 1, stem=stem) for i, stem in enumerate(stems)]
        fake = FakeModel([rows[start:start + 3] for start in range(0, 10, 3)],
                         {f'b_{i:02d}': blind_ok(tier='easy') for i in range(1, 11)},
                         {f'b_{i:02d}': examiner_ok('easy' if i % 2 else 'mid') for i in range(1, 11)})
        quiz_lite.call = fake
        with tempfile.TemporaryDirectory() as tmp:
            questions, results, log = quiz_lite.build_batch(run, 1, 'test', Path(tmp))
            attempt = json.loads((Path(tmp) / 'attempt-1.json').read_text())
            quiz_lite.write_batch(run, Path(tmp), questions, 'test')
            quiz_lite.sign(Path(tmp), run, results, log)
            self.assertTrue(verify(Path(tmp))['ok'])
        self.assertEqual([q['external_id'] for q in questions], [f'b_{i:02d}' for i in range(1, 11)])
        self.assertEqual([q['difficulty'] for q in questions], [2, 3] * 5)
        self.assertEqual([[i['index'] for i in g['items']] for g in attempt['groups']],
                         [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10]])
        self.assertEqual(fake.writer_schemas, [quiz_quantity.WRITER_SCHEMA] * 4)
        self.assertTrue(all('只调用一次submit_questions' in prompt for prompt in fake.writer_prompts))
        self.assertTrue(all('非硬性难度门槛' in prompt for prompt in fake.writer_prompts))

    def test_quantity_groups_ignore_foreign_and_repeated_indices_without_changing_response(self):
        run = {**self.run, 'planned_count': 4, 'difficulty': None,
               'slots': [{'tag': TAG, 'count': 4, 'difficulty': 'auto'}]}
        stems = ['甲乙两队合作完成工程，甲单独需要十二天，乙十八天，合作多少天？',
                 '袋中红球三只蓝球五只，随机取出两个，颜色相同的概率是多少？',
                 '商品原价三百元，打八折再减二十元，实际售价为多少元？',
                 '五名选手分数共一百六十分，最高四十五分，第二名至少多少分？']
        rows = [question(i + 1, stem=stem) for i, stem in enumerate(stems)]
        missing_index = {key: value for key, value in rows[3].items() if key != 'index'}
        responses = [rows[:3] + [question(2, stem='重复索引'), question(4, stem='前组越界')],
                     [missing_index, question(4, stem='后组重复'), question(1, stem='后组越界')],
                     [rows[1], missing_index]]
        fake = FakeModel(responses,
                         {f'b_{i:02d}': blind_ok(tier='easy') for i in range(1, 5)},
                         {f'b_{i:02d}': examiner_ok('easy') for i in range(1, 5)})
        quiz_lite.call = fake
        with tempfile.TemporaryDirectory() as tmp:
            questions, _, log = quiz_lite.build_batch(run, 2, 'test', Path(tmp))
            attempt = json.loads((Path(tmp) / 'attempt-1.json').read_text())
            retry = json.loads((Path(tmp) / 'attempt-2.json').read_text())
        self.assertEqual([q['stem'] for q in questions], stems)
        self.assertEqual([q['index'] for q in attempt['draft']['questions']], [1, 3])
        self.assertEqual(sorted(attempt['review']), ['b_01', 'b_03'])
        self.assertEqual([row['asked'] for row in log], [[1, 2, 3, 4], [2, 4]])
        self.assertEqual([q['index'] for q in retry['draft']['questions']], [2, 4])
        self.assertEqual([group['response']['questions'] for group in attempt['groups']], responses[:2])
        self.assertEqual(retry['groups'][0]['response']['questions'], responses[2])
        self.assertNotIn('index', missing_index)

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

        def call(system, prompt, temperature, timeout, **kwargs):
            if system in (quiz_lite.BLIND_SYSTEM, quiz_quantity.BLIND):
                rounds["n"] += 1
                if rounds["n"] == 1:
                    return {
                        "questions": [
                            dict(blind_ok(), id="b_01"),
                            dict(blind_ok("D"), id="b_02"),
                        ]
                    }
            return fake(system, prompt, temperature, timeout, **kwargs)

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
        self.assertIn(first[0]['stem'], fake.writer_prompts[1])
        second_items = json.loads(fake.writer_prompts[1].splitlines()[1])['items']
        self.assertEqual(second_items[0]['上一轮题目']['stem'], first[1]['stem'])
        self.assertEqual(second_items[0]['上一轮题目']['answer'], first[1]['answer'])

    def test_exhausting_rounds_raises_with_reason(self):
        bad = [[question(1)], [question(1)]]
        fake = FakeModel(bad, {"b_01": blind_ok("D")}, {"b_01": examiner_ok()})
        quiz_lite.call = fake
        run = dict(self.run, planned_count=1, slots=[{"tag": TAG, "count": 1}])
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaises(RuntimeError) as caught:
                quiz_lite.build_batch(run, 2, "源", directory)
            first = json.loads((directory / "attempt-1.json").read_text())
            last = json.loads((directory / "attempt-2.json").read_text())
            self.assertEqual(first["draft"]["questions"], bad[0])
            self.assertEqual(last["review"]["b_01"]["verdict"], "REJECT")
            self.assertIn("盲解官独立解出 D", last["rejected"][0]["issues"][0])
            self.assertEqual(json.loads((directory / "generation-input.json").read_text())["slots"], run["slots"])
            self.assertFalse((directory / "questions.json").exists())
            self.assertFalse((directory / quiz_lite.RECEIPT).exists())
        self.assertIn("盲解官独立解出 D", str(caught.exception))

    def test_candidate_survives_review_upstream_failure_without_retry(self):
        run = dict(self.run, planned_count=1, slots=[{"tag": TAG, "count": 1}])
        draft = {"questions": [question(1)]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                quiz_lite, "call", side_effect=[draft, RuntimeError("upstream failed")]) as call:
            directory = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "upstream failed"):
                quiz_lite.build_batch(run, 3, "源", directory)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(json.loads((directory / "attempt-1.json").read_text())["draft"], draft)
            self.assertFalse((directory / "questions.json").exists())

    def test_existing_audit_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(quiz_lite, "call") as call:
            directory = Path(tmp)
            old = directory / "questions.json"
            old.write_text('[{"old": true}]')
            with self.assertRaisesRegex(ValueError, "不能覆盖旧证据"):
                quiz_lite.build_batch(self.run, 3, "源", directory)
            call.assert_not_called()
            self.assertEqual(old.read_text(), '[{"old": true}]')
            self.assertEqual(list(directory.iterdir()), [old])

    def test_brief_rechecks_kept_items_after_replacement(self):
        self.run["slots"][0]["brief"] = "至少一题用不同场景"
        fake = FakeModel([[question(1), question(2, stem="某企业7名骨干总分590分，问排名第四者最少得多少分？")],
                          [question(2, stem="某机关8个科室共620件督办任务，问第二名最少完成多少件？")]],
                         {"b_01": blind_ok(), "b_02": blind_ok()}, {"b_01": examiner_ok(), "b_02": examiner_ok()})
        prompts = []
        rounds = 0
        def call(system, prompt, temperature, timeout, **kwargs):
            nonlocal rounds
            if system in (quiz_lite.BLIND_SYSTEM, quiz_quantity.BLIND):
                rounds += 1
                if rounds == 1:
                    return {"questions": [dict(blind_ok(), id="b_01"), dict(blind_ok("D"), id="b_02")]}
            if system in (quiz_lite.EXAMINER_SYSTEM, quiz_quantity.EXAMINER):
                prompts.append(json.loads(prompt.split("\n", 1)[1]))
            return fake(system, prompt, temperature, timeout, **kwargs)
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

    def test_v3_reasoning_tampering_fails_even_after_resigning(self):
        run = {"module": "数量关系", "batch_id": "b", "difficulty": "hard",
               "slots": [{"tag": TAG, "count": 1, "difficulty": "hard"}]}
        row = stamped("b", 1)
        row["analysis"] += " 由于数量为整数，最终人数必须取整数。"
        row["explanation"] = row["analysis"]
        claims = quiz_lite.lite_necessity_claims(row)
        examiner = {**examiner_ok(), "necessity_claims": claims,
                    "necessity_checks": [{"claim_index": 0, "valid": True, "reason": "题干人数为整数。"}]}
        results = {"b_01": {"question_id": "b_01", "answer": "A", "verdict": "PASS",
                            "blind": blind_ok(), "examiner": examiner}}
        quiz_lite.write_batch(run, self.dir, [row], "test")
        quiz_lite.sign(self.dir, run, results, [])
        outcome = verify(self.dir)
        self.assertEqual(outcome["review_schema_version"], 3)
        self.assertFalse(outcome["legacy_review"])
        for defect in ("blind_tier", "examiner_tier", "blind_reason", "analysis_reason",
                       "claims", "missing_check", "invalid_check", "check_index", "check_reason"):
            altered = json.loads(json.dumps(results))
            b, e = altered["b_01"]["blind"], altered["b_01"]["examiner"]
            if defect == "blind_tier":
                b["actual_difficulty"] = "easy"
            elif defect == "examiner_tier":
                e["actual_difficulty"] = "easy"
            elif defect == "blind_reason":
                b["difficulty_reason"] = " "
            elif defect == "analysis_reason":
                e.pop("analysis_check")
            elif defect == "claims":
                e["necessity_claims"] = []
            elif defect == "missing_check":
                e["necessity_checks"] = []
            elif defect == "invalid_check":
                e["necessity_checks"][0]["valid"] = False
            elif defect == "check_index":
                e["necessity_checks"][0]["claim_index"] = True
            else:
                e["necessity_checks"][0]["reason"] = " "
            quiz_lite.sign(self.dir, run, altered, [])
            with self.subTest(defect=defect), self.assertRaisesRegex(ValueError, "必要性断言|轻量推导核验"):
                verify(self.dir)

    def test_v1_remains_readable_but_marked_legacy(self):
        run = {"module": "数量关系", "batch_id": "b", "difficulty": "hard",
               "slots": [{"tag": TAG, "count": 1, "difficulty": "hard"}]}
        quiz_lite.write_batch(run, self.dir, [stamped("b", 1)], "test")
        manifest_path = self.dir / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['generation'].pop('quantity_hard_policy')
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        old = self.evidence(version=1)
        for role in ("blind", "examiner"):
            old["results"][0][role].pop("actual_difficulty")
            old["results"][0][role].pop("difficulty_reason")
        for key in ("analysis_check", "necessity_claims", "necessity_checks"):
            old["results"][0]["examiner"].pop(key)
        quiz_lite.sign(self.dir, run, {"b_01": old["results"][0]}, [])
        path = self.dir / "evidence" / "lite-review.json"
        path.write_text(json.dumps(old), encoding="utf-8")
        receipt_path = self.dir / quiz_lite.RECEIPT
        receipt = json.loads(receipt_path.read_text())
        receipt["lite_review"]["sha256"] = quiz_lite.digest(path)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        outcome = verify(self.dir)
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["review_schema_version"], 1)
        self.assertTrue(outcome["legacy_review"])

    def test_v2_keeps_reasoning_checks_and_is_marked_legacy(self):
        run = {"module": "数量关系", "batch_id": "b", "difficulty": "hard",
               "slots": [{"tag": TAG, "count": 1, "difficulty": "hard"}]}
        quiz_lite.write_batch(run, self.dir, [stamped("b", 1)], "test")
        manifest_path = self.dir / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['generation'].pop('quantity_hard_policy')
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        results = {"b_01": self.evidence()["results"][0]}
        for altered in (False, True):
            quiz_lite.sign(self.dir, run, results, [])
            path = self.dir / "evidence" / "lite-review.json"
            evidence = json.loads(path.read_text())
            evidence["version"] = 2
            evidence.pop('quantity_hard_policy')
            if altered:
                evidence["results"][0]["blind"]["actual_difficulty"] = "easy"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            receipt_path = self.dir / quiz_lite.RECEIPT
            receipt = json.loads(receipt_path.read_text())
            receipt["lite_review"]["sha256"] = quiz_lite.digest(path)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            if altered:
                with self.assertRaisesRegex(ValueError, "轻量推导核验"):
                    verify(self.dir)
            else:
                outcome = verify(self.dir)
                self.assertTrue(outcome["ok"])
                self.assertEqual(outcome["review_schema_version"], 2)
                self.assertTrue(outcome["legacy_review"])

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

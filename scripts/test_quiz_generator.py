#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

import argparse
import tempfile
from pathlib import Path

from PIL import Image

from normalize_ai_batch import generation_payload_extras

from quiz_generator import (
    align_answers,
    build_calculations,
    build_prompt,
    holdout_matches,
    infer_subcategory,
    canon_card,
    module_of,
    reject_unsupported,
    render_question_figures,
    render_figure,
    resolve_slots,
    slot_tags,
    stamp_questions,
    validate_question_contract,
    yanyu_contract_issues,
)


EXTREME = "数量关系-数学运算-"
FENBI_EXTREME = "数量关系-数学运算-最值问题"
FENBI_PERM = "数量关系-数学运算-排列组合问题"

def prompt_extras(run):
    """提示测试要用生产形状的 extras：里面有字母上限，build_prompt 会读。"""
    return generation_payload_extras(
        run["module"], int(run["planned_count"]), str(run["batch_id"])
    )



def blueprint_args(blueprint=None, tag=None, count=None, module="数量关系"):
    return argparse.Namespace(
        module=module, tag=tag, count=count, blueprint=blueprint, difficulty=None
    )


class QuizGeneratorTest(unittest.TestCase):
    def test_module_and_sub(self):
        tag = "判断推理-逻辑判断-翻译推理"
        self.assertEqual(module_of(tag, ""), "判断推理")
        self.assertEqual(infer_subcategory(tag, "判断推理"), "逻辑判断")

    def test_reject_figures(self):
        with self.assertRaises(ValueError):
            reject_unsupported("科学推理", "科学推理-力学-杠杆滑轮")
        with self.assertRaises(ValueError):
            reject_unsupported("判断推理", "判断推理-图形推理-空间类")

    def test_required_figure_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "缺 figure 规格"):
                render_question_figures(
                    [{"external_id": "demo_01"}], Path(directory), required=True
                )

    def test_science_tag_stays_in_independent_module(self):
        args = argparse.Namespace(
            module="科学推理",
            tag="科学推理-力学-杠杆滑轮",
            count=1,
            blueprint=None,
            difficulty=None,
        )
        module, slots = resolve_slots(args)
        self.assertEqual(module, "科学推理")
        self.assertEqual(slots[0]["tag"], "科学推理-力学-杠杆滑轮")
        self.assertEqual(infer_subcategory(slots[0]["tag"], module), "科学推理")

    def test_unknown_figure_element_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "不支持的元素类型"):
                render_question_figures(
                    [{
                        "external_id": "demo_01",
                        "figure": {
                            "image_only_facts": ["方向"],
                            "elements": [{"type": "freehand", "x": 0, "y": 0}],
                        },
                    }],
                    Path(directory),
                    required=True,
                )

    def test_figure_accepts_x1_y1_width_height_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "figure.png"
            render_figure(
                {
                    "elements": [
                        {"type": "line", "x1": 0.1, "y1": 0.5, "x2": 0.9, "y2": 0.5},
                        {"type": "rect", "x": 0.2, "y": 0.2, "width": 0.2, "height": 0.2},
                    ]
                },
                output,
            )
            self.assertGreater(output.stat().st_size, 1000)

    def test_figure_content_is_fitted_when_coordinates_use_small_cluster(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "figure.png"
            render_figure(
                {
                    "elements": [
                        {"type": "line", "x1": 0.05, "y1": 0.2, "x2": 0.25, "y2": 0.2},
                        {"type": "text", "x": 0.12, "y": 0.25, "text": "O"},
                    ]
                },
                output,
            )
            with Image.open(output) as image:
                pixels = list(image.convert("RGB").getdata())
            nonwhite = sum(pixel != (255, 255, 255) for pixel in pixels)
            self.assertGreater(nonwhite, len(pixels) * 0.01)

    def test_non_object_figure_element_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "非对象"):
                render_question_figures(
                    [{
                        "external_id": "demo_01",
                        "figure": {
                            "image_only_facts": ["方向"],
                            "elements": ["line"],
                        },
                    }],
                    Path(directory),
                    required=True,
                )

    def test_science_tag_validates_without_category(self):
        from kaodian_taxonomy import validate_ai_primary_tag

        self.assertEqual(
            validate_ai_primary_tag("科学推理-力学-杠杆滑轮"),
            "科学推理-力学-杠杆滑轮",
        )

    def test_science_prompt_uses_gd_canon(self):
        run = {
            "module": "科学推理",
            "focus_tag": "科学推理-力学-杠杆滑轮",
            "planned_count": 1,
            "batch_id": "science",
            "plan_date": "2026-09-10",
            "slots": [{"tag": "科学推理-力学-杠杆滑轮", "count": 1}],
        }
        text = build_prompt(run, {}, prompt_extras(run))
        self.assertIn("广东独有", text)
        self.assertIn("杠杆 F1 L1 = F2 L2", text)

    def test_yanyu_contract_requires_signal_and_shape(self):
        run = {
            "module": "言语理解与表达",
            "planned_count": 1,
            "focus_tag": "言语理解与表达-逻辑填空-成语填空",
            "slots": [{"tag": "言语理解与表达-逻辑填空-成语填空", "count": 1}],
        }
        with self.assertRaisesRegex(ValueError, "未命中指定言语考法"):
            validate_question_contract(
                run,
                [{"external_id": "demo_01", "stem": "没有空格", "kaodian_signal": "成语辨析"}],
            )

    def test_yanyu_subtype_collapse_is_rejected(self):
        question = {
            "stem": "这是一段有________的题干。",
            "tags": ["言语理解与表达-逻辑填空-成语填空"],
            "kaodian_signal": "根据语境辨析实词的词义和搭配",
        }
        self.assertTrue(any("成语填空" in issue for issue in yanyu_contract_issues(question)))

    def test_focus_prompt(self):
        run = {
            "module": "判断推理",
            "focus_tag": "判断推理-逻辑判断-翻译推理",
            "planned_count": 2,
            "batch_id": "x",
            "plan_date": "2026-09-10",
        }
        extras = prompt_extras(run)
        text = build_prompt(run, {}, extras)
        self.assertIn("判断推理-逻辑判断-翻译推理", text)
        self.assertIn("echo_given_fact", text)
        self.assertNotIn("5_graphic_plus_15_logic", text)

    def test_stamp_keeps_the_writers_own_letter(self):
        run = {
            "module": "判断推理",
            "focus_tag": "判断推理-逻辑判断-翻译推理",
            "planned_count": 1,
            "batch_id": "demo",
        }
        questions = stamp_questions(
            run,
            [
                {
                    "stem": "若P则Q。已知非Q。",
                    "options": [
                        {"key": "A", "text": "甲"},
                        {"key": "B", "text": "乙"},
                        {"key": "C", "text": "丙"},
                        {"key": "D", "text": "丁"},
                    ],
                    "answer": "A",
                    "analysis": "逆否。故选A。",
                }
            ],
            "src",
        )
        # 打标签不碰答案：换字母的诱因就是模型倒推数据去凑字母的来源。
        self.assertEqual(questions[0]["answer"], "A")
        self.assertIn("故选A", questions[0]["analysis"])
        self.assertEqual(questions[0]["external_id"], "demo_01")
        self.assertEqual(questions[0]["tags"], ["判断推理-逻辑判断-翻译推理"])

    def test_quantity_prompt_asks_calculations(self):
        run = {
            "module": "数量关系",
            "focus_tag": "数量关系-数学运算-排列组合问题",
            "planned_count": 5,
            "batch_id": "x",
            "plan_date": "2026-09-10",
        }
        extras = prompt_extras(run)
        text = build_prompt(run, {}, extras)
        self.assertIn("calculations", text)
        self.assertIn("8*7*6/(3*2*1)", text)
        self.assertIn("禁止改成数列", text)

    def test_calculations_follow_aligned_keys(self):
        questions = [
            {
                "external_id": "demo_01",
                "answer": "A",
                "options": [
                    {"key": "A", "text": "56种"},
                    {"key": "B", "text": "48种"},
                    {"key": "C", "text": "36种"},
                    {"key": "D", "text": "24种"},
                ],
                "calculations": {
                    "correct": "8*7",
                    "options": {"A": "8*7", "B": "48", "C": "36", "D": "24"},
                    "tolerance": 0.01,
                },
            }
        ]
        align_answers(questions, ["C"])
        self.assertEqual(questions[0]["answer"], "C")
        calc = build_calculations(questions)
        row = calc["questions"][0]
        self.assertEqual(row["options"]["C"], "8*7")
        self.assertEqual(row["correct"], "8*7")
        self.assertNotIn("calculations", questions[0])

    def test_holdout_must_share_family(self):
        tag = FENBI_PERM
        self.assertTrue(
            holdout_matches(
                tag,
                {"references": [{"tags": ["数量关系-数学运算-排列组合问题"], "stem": "分组"}]},
            )
        )
        self.assertFalse(
            holdout_matches(
                tag,
                {"references": [{"tags": ["数量关系-数学运算-和差倍比问题"], "stem": "容积"}]},
            )
        )


class BlueprintTest(unittest.TestCase):
    """--blueprint 让 Hermes 在一批里编排同一知识点下的不同考法。"""

    def test_single_tag_still_works(self):
        module, slots = resolve_slots(blueprint_args(tag=FENBI_EXTREME, count=10))
        self.assertEqual(module, "数量关系")
        self.assertEqual(slots, [{"tag": FENBI_EXTREME, "count": 10}])

    def test_slots_expand_per_item(self):
        blueprint = (
            '{"slots":['
            '{"tag":"' + EXTREME + '最值问题","count":2},'
            '{"tag":"' + EXTREME + '函数最值问题","count":3}]}'
        )
        _, slots = resolve_slots(blueprint_args(blueprint=blueprint))
        run = {"slots": slots, "module": "数量关系"}
        self.assertEqual(
            slot_tags(run),
            [EXTREME + "最值问题"] * 2 + [EXTREME + "函数最值问题"] * 3,
        )

    def test_prompt_names_each_slot_range(self):
        _, slots = resolve_slots(
            blueprint_args(
                blueprint='{"slots":[{"tag":"抽屉原理","count":2},{"tag":"和定最值","count":1}]}'
            )
        )
        run = {
            "module": "数量关系",
            "focus_tag": slots[0]["tag"],
            "slots": slots,
            "planned_count": 3,
            "batch_id": "x",
            "plan_date": "2026-09-14",
        }
        extras = prompt_extras(run)
        text = build_prompt(run, {}, extras)
        self.assertIn("items 1-2: tags[0] = " + FENBI_EXTREME, text)
        self.assertIn("item 3: tags[0] = " + FENBI_EXTREME, text)

    def test_short_tags_canonicalize(self):
        _, slots = resolve_slots(blueprint_args(blueprint='{"slots":[{"tag":"抽屉原理","count":1}]}'))
        self.assertEqual(slots[0]["tag"], FENBI_EXTREME)

    def test_rejects_bad_blueprints(self):
        cases = [
            blueprint_args(blueprint="{}", tag="t", count=1),
            blueprint_args(blueprint='{"slots":[{"tag":"数量关系-瞎编-不存在","count":3}]}'),
            blueprint_args(blueprint='{"slots":[{"tag":"抽屉原理"}]}'),
            blueprint_args(
                blueprint='{"slots":[{"tag":"抽屉原理","count":1},'
                '{"tag":"判断推理-逻辑判断-翻译推理","count":1}]}'
            ),
        ]
        for args in cases:
            with self.assertRaises((SystemExit, ValueError)):
                resolve_slots(args)


class CanonInjectionTest(unittest.TestCase):
    """生成侧必须拿到考法口径，而不是只有一个标签字符串。"""

    def test_card_is_sliced_to_the_named_考法(self):
        card = canon_card("数量关系", "数量关系-既烧脑又能套公式的最值问题-最不利原则与抽屉")
        self.assertIn("考法二", card)
        self.assertIn("抽屉", card)
        self.assertNotIn("考法一", card)
        self.assertNotIn("考法三", card)

    def test_multiline_bullets_keep_their_sub_lines(self):
        card = canon_card("数量关系", "数量关系-数学运算-排列组合问题-分堆分配与定序消序")
        self.assertIn("插板法", card)
        self.assertIn("部分均等分堆", card)   # 平均分堆的子行没有被切掉
        self.assertNotIn("捆绑法", card)      # 别的槽位的模型没渗进来

    def test_whole_card_when_tag_is_not_per_考法(self):
        card = canon_card("判断推理", "判断推理-逻辑判断-翻译推理")
        self.assertIn("固定识别", card)
        self.assertIn("逆否", card)

    def test_unknown_tag_yields_nothing(self):
        self.assertEqual(canon_card("数量关系", "数量关系-查无此点-查无此点"), "")

    def test_brief_reaches_the_prompt(self):
        _, slots = resolve_slots(
            blueprint_args(
                blueprint=(
                    '{"slots":[{"tag":"抽屉原理","count":2,'
                    '"brief":"必须出现残缺抽屉；禁止退化成和定排大小"}]}'
                )
            )
        )
        self.assertEqual(slots[0]["brief"], "必须出现残缺抽屉；禁止退化成和定排大小")
        run = {
            "module": "数量关系",
            "focus_tag": slots[0]["tag"],
            "slots": slots,
            "planned_count": 2,
            "batch_id": "x",
            "plan_date": "2026-09-14",
        }
        extras = prompt_extras(run)
        text = build_prompt(run, {}, extras)
        self.assertIn("必须出现残缺抽屉", text)
        self.assertIn("只能收紧不得放宽", text)
        self.assertIn("考法二", text)


if __name__ == "__main__":
    unittest.main()

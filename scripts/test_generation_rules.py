#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""广东通用卷机械硬规则闸门测试（generation_gate.validate_paper_hard_rules 等）。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kaodian_taxonomy import is_shuliang_paper, validate_shuliang_paper, validate_ziliao_variety
from generation_gate import validate_paper_hard_rules


def opts(n=4):
    return [{"key": k, "text": f"选项{k}"} for k in "ABCD"[:n]]


def q(qid, category, sub, tag, answer="A", options=None, stem="题干", **extra):
    d = dict(external_id=qid, category=category, sub_category=sub, question_type="single",
             stem=stem, options=options if options is not None else opts(), answer=answer, tags=[tag])
    d.update(extra)
    return d


def shuliang_paper(seq=5):
    items = []
    for i in range(seq):
        items.append(q(f"S{i}", "数量关系", "数字推理", "数量关系-数字推理-数字推理"))
    for i in range(15 - seq):
        items.append(q(f"M{i}", "数量关系", "数学运算", "数量关系-能“七十二变”的行程问题-基础行程、平均速度与相对运动"))
    return items


def ziliao_paper(distinct=True):
    packs = [["资料分析-ABRX类-基期量计算与比较", "资料分析-ABRX类-增长率计算模型",
              "资料分析-ABRX类-增长量计算与现期推算", "资料分析-比重类-现期、基期与隔级比重",
              "资料分析-平均类-一般平均值与年均增速/增量"]] * 4
    if distinct:
        packs[1] = ["资料分析-基础知识-统计术语与常考概念", "资料分析-比重类-比重趋势、比重差与比值差",
                    "资料分析-盐水类-十字交叉法与混合增长率", "资料分析-比较类-双线法与增量比较",
                    "资料分析-特殊考点-拉动增长、贡献率与容斥"]
    items = []
    for m in range(4):
        for k in range(5):
            items.append(q(f"Z{m}{k}", "资料分析", None, packs[m][k], material_id=f"M{m}"))
    return items


class ShuliangTest(unittest.TestCase):
    def test_valid_15(self):
        validate_shuliang_paper(shuliang_paper(5))

    def test_zero_sequence_rejected(self):
        with self.assertRaisesRegex(ValueError, "不得 0 数字推理"):
            validate_shuliang_paper(shuliang_paper(0))

    def test_wrong_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "数字推理 5"):
            validate_shuliang_paper(shuliang_paper(3))

    def test_non_shuliang_skipped(self):
        validate_shuliang_paper([q("X", "言语理解与表达", "片段阅读", "言语理解与表达-片段阅读-主旨概括")])
        self.assertFalse(is_shuliang_paper([q("X", "判断推理", "图形推理", "判断推理-图形推理-位置规律")]))


class ZiliaoVarietyTest(unittest.TestCase):
    def test_clone_rejected(self):
        with self.assertRaisesRegex(ValueError, "同一套五连招"):
            validate_ziliao_variety(ziliao_paper(distinct=False))

    def test_distinct_ok(self):
        validate_ziliao_variety(ziliao_paper(distinct=True))


class HardRulesTest(unittest.TestCase):
    def test_clean_shuliang_passes(self):
        validate_paper_hard_rules({}, shuliang_paper(5))

    def test_double_answer_guard(self):
        bad = q("X", "判断推理", "逻辑判断", "判断推理-逻辑判断-翻译推理", answer="AB")
        with self.assertRaisesRegex(ValueError, "唯一选项字母"):
            validate_paper_hard_rules({}, [bad])

    def test_duplicate_option_rejected(self):
        dup = q("X", "判断推理", "逻辑判断", "判断推理-逻辑判断-翻译推理",
                options=[{"key": k, "text": "一样"} for k in "ABCD"])
        with self.assertRaisesRegex(ValueError, "重复选项"):
            validate_paper_hard_rules({}, [dup])

    def test_leibi_dingyi_rejected(self):
        with self.assertRaisesRegex(ValueError, "类比推理 / 定义判断"):
            validate_paper_hard_rules({}, [q("X", "判断推理", "定义判断", "判断推理-定义判断-单定义")])

    def test_kegang_word_rejected(self):
        with self.assertRaisesRegex(ValueError, "课纲词"):
            validate_paper_hard_rules({}, [q("X", "数量关系", "数学运算",
                                             "数量关系-和差倍比与方程法-方程、比例与代入验证",
                                             stem="本题考察方程思想。")])

    def test_yanyu_composition_tail_rejected(self):
        with self.assertRaisesRegex(ValueError, "因此亟须"):
            validate_paper_hard_rules({}, [q("X", "言语理解与表达", "片段阅读",
                                             "言语理解与表达-片段阅读-主旨概括",
                                             stem="……因此亟须加强治理。")])

    def test_ziliao_moushengSi_and_dirty(self):
        items = ziliao_paper(distinct=True)
        with tempfile.TemporaryDirectory() as d:
            mats = [{"external_id": f"M{m}", "content": "某省2024年产值6400万元，增长25%。"} for m in range(4)]
            Path(d, "materials.json").write_text(json.dumps(mats, ensure_ascii=False), "utf-8")
            with self.assertRaisesRegex(ValueError, "某省"):
                validate_paper_hard_rules({}, items, Path(d))

    def test_ziliao_dirty_ratio_rejected(self):
        items = ziliao_paper(distinct=True)
        with tempfile.TemporaryDirectory() as d:
            mats = [{"external_id": f"M{m}", "content": "2024年产值6400万元，增长25%，占比40%。"} for m in range(4)]
            Path(d, "materials.json").write_text(json.dumps(mats, ensure_ascii=False), "utf-8")
            with self.assertRaisesRegex(ValueError, "脏数字"):
                validate_paper_hard_rules({}, items, Path(d))

    def test_ziliao_clean_passes(self):
        items = ziliao_paper(distinct=True)
        with tempfile.TemporaryDirectory() as d:
            mats = [{"external_id": f"M{m}",
                     "content": f"2024年，G省第{m}产业实现增加值{1876.43 + m}亿元，同比增长{12.7 + m}%。"}
                    for m in range(4)]
            Path(d, "materials.json").write_text(json.dumps(mats, ensure_ascii=False), "utf-8")
            validate_paper_hard_rules({}, items, Path(d))


if __name__ == "__main__":
    unittest.main()

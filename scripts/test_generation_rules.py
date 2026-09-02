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


def _balance(items):
    for i, it in enumerate(items):        # 默认答案轮换均衡，避免触发 balance gate
        it["answer"] = "ABCD"[i % 4]
    return items


def shuliang_paper(seq=5):
    items = []
    for i in range(seq):
        items.append(q(f"S{i}", "数量关系", "数字推理", "数量关系-数字推理-数字推理"))
    for i in range(15 - seq):
        items.append(q(f"M{i}", "数量关系", "数学运算", "数量关系-能“七十二变”的行程问题-基础行程、平均速度与相对运动"))
    return _balance(items)


def ziliao_paper(distinct=True):
    packs = [["资料分析-ABRX类-基期量计算与比较", "资料分析-ABRX类-增长率计算模型",
              "资料分析-ABRX类-增长量计算与现期推算", "资料分析-比重类-现期、基期与隔级比重",
              "资料分析-平均类-一般平均值与年均增速/增量"]] * 4
    if distinct:
        packs[1] = ["资料分析-基础知识-统计术语与常考概念", "资料分析-比重类-比重趋势、比重差与比值差",
                    "资料分析-盐水类-十字交叉法与混合增长率", "资料分析-比较类-双线法与增量比较",
                    "资料分析-特殊考点-拉动增长、贡献率与容斥"]
    judge_forms = [
        "根据资料，以下说法可以判断属实的是（  ）。",
        "根据资料，以下说法不能从上述资料中推出的是（  ）。",
        "根据资料，下列说法正确的有（  ）。",
        "根据资料，能够从上述资料中推出的是（  ）。",
    ]
    items = []
    for m in range(4):
        for k in range(5):
            stem = judge_forms[m] if k == 4 else f"第{m}篇第{k}题"
            items.append(q(f"Z{m}{k}", "资料分析", None, packs[m][k], material_id=f"M{m}", stem=stem))
    return items


def science_paper(n=5, with_images=True):
    buckets = [("科学推理-力学-杠杆滑轮", "杠杆"), ("科学推理-压强与浮力-阿基米德原理", "浮力"),
               ("科学推理-电学-串并联", "电路"), ("科学推理-地理-海陆风", "海陆风"),
               ("科学推理-生物-食物网", "食物网")]
    out = []
    for i in range(n):
        tag, kw = buckets[i % len(buckets)]
        item = q(f"K{i}", "科学推理", "科学推理", tag, stem=f"如图，关于{kw}的问题。")
        if with_images:
            item["stem_images"] = [f"images/k{i}.png"]
        out.append(item)
    return _balance(out)


LOGIC_TAGS = (
    "判断推理-逻辑判断-逻辑论证-支持与前提假设",
    "判断推理-逻辑判断-逻辑论证-一般质疑",
    "判断推理-逻辑判断-分析类-日常分析推理",
    "判断推理-逻辑判断-比例类论证与解释说明",
    "判断推理-逻辑判断-秒杀模型与速解技巧",
)


def panduan_paper(g=5, lg=15):
    out = []
    for i in range(g):
        out.append(q(f"G{i}", "判断推理", "图形推理", "判断推理-图形推理-位置规律"))
    for i in range(lg):
        out.append(q(f"L{i}", "判断推理", "逻辑判断", LOGIC_TAGS[i % len(LOGIC_TAGS)]))
    return _balance(out)


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

    def _clean_ziliao_dir(self, d):
        mats = [{"external_id": f"M{m}",
                 "content": f"2024年，G省第{m}产业实现增加值{1876.43 + m}亿元，同比增长{12.7 + m}%。"}
                for m in range(4)]
        Path(d, "materials.json").write_text(json.dumps(mats, ensure_ascii=False), "utf-8")

    def test_ziliao_missing_judge_rejected(self):
        items = ziliao_paper(distinct=True)
        for it in items:                      # 抹掉全部综合判断题干
            if "根据资料" in it["stem"]:
                it["stem"] = "普通计算题"
        with tempfile.TemporaryDirectory() as d:
            self._clean_ziliao_dir(d)
            with self.assertRaisesRegex(ValueError, "综合判断"):
                validate_paper_hard_rules({}, items, Path(d))

    def test_ziliao_same_judge_form_rejected(self):
        items = ziliao_paper(distinct=True)
        for it in items:                      # 四篇综合判断都用“属实”同一形式
            if "根据资料" in it["stem"]:
                it["stem"] = "根据资料，以下说法可以判断属实的是（  ）。"
        with tempfile.TemporaryDirectory() as d:
            self._clean_ziliao_dir(d)
            with self.assertRaisesRegex(ValueError, "跨篇轮换"):
                validate_paper_hard_rules({}, items, Path(d))


class ScienceTest(unittest.TestCase):
    def test_clean_passes(self):
        validate_paper_hard_rules({}, science_paper(5, with_images=True))

    def test_missing_image_rejected(self):
        with self.assertRaisesRegex(ValueError, "必带图"):
            validate_paper_hard_rules({}, science_paper(5, with_images=False))

    def test_wrong_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "科学推理须为 5 题"):
            validate_paper_hard_rules({}, science_paper(4, with_images=True))

    def test_panduan_category_on_kepui_rejected(self):
        paper = science_paper(5, with_images=True)
        for item in paper:
            item["category"] = "判断推理"
        with self.assertRaisesRegex(ValueError, "category 必须是科学推理"):
            validate_paper_hard_rules({}, paper)


class AnswerBalanceTest(unittest.TestCase):
    def test_shuliang_skew_rejected(self):
        p = shuliang_paper(5)
        for q in p:                       # 全部答 B → 15/15 远超 40%
            q["answer"] = "B"
        with self.assertRaisesRegex(ValueError, "扎堆"):
            validate_paper_hard_rules({}, p)

    def test_shuliang_balanced_passes(self):
        p = shuliang_paper(5)
        for i, q in enumerate(p):         # ABCD 轮流 → 最多 4/15，通过
            q["answer"] = "ABCD"[i % 4]
        validate_paper_hard_rules({}, p)

    def test_cap_is_forty_percent(self):
        p = shuliang_paper(5)
        for i, q in enumerate(p):         # 7 个 A（>6）应拦下
            q["answer"] = "A" if i < 7 else "ABCD"[i % 4]
        with self.assertRaisesRegex(ValueError, "扎堆"):
            validate_paper_hard_rules({}, p)

    def test_kepui_all_same_letter_rejected(self):
        paper = science_paper(5, with_images=True)
        for item in paper:
            item["answer"] = "D"
        with self.assertRaisesRegex(ValueError, "答案字母须分散"):
            validate_paper_hard_rules({}, paper)

    def test_kepui_legal_distribution_passes(self):
        paper = science_paper(5, with_images=True)
        for item, letter in zip(paper, "ABCDA"):
            item["answer"] = letter
        validate_paper_hard_rules({}, paper)


class ScienceLevelTest(unittest.TestCase):
    def test_overlevel_rejected(self):
        sp = science_paper(5, with_images=True)
        sp[0]["stem"] = "如图，一定质量的理想气体经历等温过程，求末状态压强。"
        with self.assertRaisesRegex(ValueError, "初中难度"):
            validate_paper_hard_rules({}, sp)

    def test_momentum_rejected(self):
        sp = science_paper(5, with_images=True)
        sp[1]["stem"] = "如图，两滑块碰撞，由动量守恒求碰后速度。"
        with self.assertRaisesRegex(ValueError, "初中难度"):
            validate_paper_hard_rules({}, sp)


def compressed_daily_paper():
    """旧日练压缩模型：5 图形 + 10 逻辑 + 5 科学，全部 category=判断推理。"""
    out = panduan_paper(5, 10)
    science = science_paper(5, with_images=True)
    for i, item in enumerate(science):
        item["external_id"] = f"PK{i}"
        item["category"] = "判断推理"
        item["sub_category"] = "科学推理"
    return _balance(out + science)


class PanduanLayoutTest(unittest.TestCase):
    def test_clean_passes(self):
        validate_paper_hard_rules({}, panduan_paper(5, 15))

    def test_wrong_split_rejected(self):
        with self.assertRaisesRegex(ValueError, "图形 5 \\+ 逻辑 15"):
            validate_paper_hard_rules({}, panduan_paper(6, 14))

    def test_compressed_kepui_tail_rejected(self):
        with self.assertRaisesRegex(ValueError, "不得含科学推理"):
            validate_paper_hard_rules({}, compressed_daily_paper())

    def test_science_inside_panduan20_rejected_even_without_images(self):
        paper = panduan_paper(5, 15)
        paper[19]["sub_category"] = "科学推理"
        paper[19]["tags"] = ["科学推理-力学-杠杆滑轮"]
        with self.assertRaisesRegex(ValueError, "不得含科学推理"):
            validate_paper_hard_rules({}, paper)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Offline gates for 资料分析轨 A/B quotas, labels, and realism checks."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ziliao_tracks as tracks
from kaodian_taxonomy import ZILIAO_MIX, ZILIAO_QI


class QuotaTest(unittest.TestCase):
    def test_gd_20_matches_yuekao_mix(self):
        slots = tracks.gd_slots_20()
        self.assertEqual(len(slots), 20)
        tracks.validate_gd_quota(slots)
        counts = tracks.family_counts(slots)
        self.assertTrue(3 <= counts["detail"] <= 4)
        self.assertEqual(counts["judge"], 4)
        self.assertTrue(3 <= counts["share_add"] <= 4)
        self.assertEqual(counts["growth"], 3)
        self.assertEqual(counts["base_share"], 2)
        self.assertEqual(counts["avg_cmp"], 2)
        self.assertTrue(1 <= counts["mix_pull"] <= 2)
        self.assertEqual([s["family"] for s in slots[4::5]], ["judge"] * 4)
        long = slots[:5]
        self.assertGreaterEqual(sum(s["family"] in {"detail", "judge"} for s in long), 3)
        self.assertGreaterEqual(sum(s["family"] in {"share_add", "growth"} for s in long), 2)

    def test_classic_20_is_ten_by_two(self):
        slots = tracks.classic_slots(20, 4)
        tags = [s["tag"] for s in slots]
        self.assertEqual(len(set(tags)), 10)
        self.assertTrue(all(tags.count(tag) == 2 for tag in set(tags)))
        self.assertTrue(all(s["family"] == "classic" for s in slots))

    def test_over_mix_rejected(self):
        slots = tracks.gd_slots_20()
        slots[0]["family"] = "mix_pull"
        slots[2]["family"] = "mix_pull"
        with self.assertRaisesRegex(ValueError, "混合或拉动|mix_pull"):
            tracks.validate_gd_quota(slots)

    def test_resolve_defaults(self):
        gd = tracks.resolve_track_slots("gd", 20, 4, "mid")
        classic = tracks.resolve_track_slots("classic", 20, 4, "mid")
        self.assertEqual(gd[0]["family"], "detail")
        self.assertEqual(classic[0]["family"], "classic")
        self.assertEqual(tracks.default_formats("gd", 4, False), ["text", "table", "chart", "chart"])
        self.assertEqual(tracks.default_formats("classic", 4, False), ["chart", "table", "text", "chart"])


class LabelTest(unittest.TestCase):
    def test_gd_source_is_yuekao_daily(self):
        source = tracks.batch_source("gd", False, "mid", "20260927")
        self.assertEqual(source, "粤考日练-资料分析-mid-20260927")
        tracks.assert_source_label("gd", source)
        with self.assertRaisesRegex(ValueError, "综合训练"):
            tracks.assert_source_label("gd", "广东省考行测-资料分析-综合训练-mid-20260927")

    def test_classic_must_not_use_guangdong_brand(self):
        source = tracks.batch_source("classic", False, "mid", "20260927")
        self.assertTrue(source.startswith("经典计算加练-"))
        self.assertNotIn("广东省考", source)
        self.assertNotIn("综合训练", source)
        tracks.assert_source_label("classic", source)
        with self.assertRaisesRegex(ValueError, "轨B不得标成广东省考"):
            tracks.assert_source_label("classic", "广东省考行测-资料分析-综合训练-mid-20260927")


class RealismTest(unittest.TestCase):
    def test_arithmetic_first_and_second_diff(self):
        self.assertTrue(tracks.is_arithmetic_series([100, 140, 180, 220]))
        self.assertTrue(tracks.is_arithmetic_series([140, 180, 230, 290, 360, 440]))
        self.assertFalse(tracks.is_arithmetic_series([1876.4, 2011.2, 1988.7, 2210.5]))

    def test_round_total_per_capita(self):
        material = {
            "content": "2023年全省主要海洋产业增加值10000亿元，从业人员400万人。",
            "figure": {"kind": "none"},
        }
        errors = tracks.material_realism_errors(material, long_text=False)
        self.assertTrue(any("人均" in err for err in errors))

    def test_round_base_period(self):
        material = {
            "content": "规模以上研发设计服务业实现营业收入2530亿元，同比增长26.5%。",
            "figure": {},
        }
        # 2530/1.265 = 2000
        self.assertTrue(any("基期" in err for err in tracks.material_realism_errors(material)))

    def test_long_text_needs_decoys(self):
        material = {"content": "G省产值12.3亿元。", "figure": {}}
        errors = tracks.material_realism_errors(material, track="gd", long_text=True)
        self.assertTrue(any("350" in err or "干扰" in err for err in errors))

    def test_clean_irregular_series_ok(self):
        body = (
            "2023年G省现代服务业增加值68412.7亿元，同比增长5.2%。"
            "数字信息服务业占现代服务业36.4%。研发设计营业收入2517.6亿元，同比增长15.3%。"
            "高技术服务业投资4561.8亿元，知识产权服务企业1247家，营收318.6亿元。"
            "承接国际服务外包286.4亿美元。此外会展业场地出租率61.8%，夜间经济指数72.4，"
            "两指标仅作背景，不进入本篇计算。"
        )
        material = {
            "content": body + "冗余说明用于凑足粤考长文篇幅。" * 20,
            "figure": {"kind": "bars", "series": [{"values": [1250.4, 1511.2, 1488.9, 1802.3, 1994.7]}]},
        }
        self.assertGreaterEqual(len(material["content"]), 350)
        self.assertFalse(tracks.material_realism_errors(material, track="gd", long_text=True))


class DifficultyAndExplainTest(unittest.TestCase):
    def test_scores_are_graded(self):
        slots = tracks.gd_slots_20()
        scores = {slot["difficulty_score"] for slot in slots}
        self.assertGreaterEqual(len(scores), 3)
        self.assertIn(1, scores)
        self.assertIn(4, scores)
        questions = [{"difficulty": slot["difficulty_score"]} for slot in slots]
        tracks.validate_difficulty_gradient(questions, track="gd")
        with self.assertRaisesRegex(ValueError, "全员"):
            tracks.validate_difficulty_gradient([{"difficulty": 3}] * 20, track="gd")

    def test_comparison_must_list_every_year(self):
        question = {
            "external_id": "Q18",
            "stem": "2019—2023年风电同比增速最快的是",
            "family": "avg_cmp",
            "tags": ["资料分析-比较类-双线法与增量比较"],
            "explanation": "2019年28.6%，2020年27.8%，2021年26.1%，2023年22.2%，选2019。",
        }
        with self.assertRaisesRegex(ValueError, "2022"):
            tracks.validate_comparison_explanations([question])
        question["explanation"] += "2022年24.1%。"
        tracks.validate_comparison_explanations([question])

    def test_infer_judge_and_detail(self):
        self.assertEqual(tracks.infer_family_from_question({"stem": "根据资料，下列说法有误的是"}), "judge")
        self.assertEqual(tracks.infer_family_from_question({"stem": "资料未提及的是"}), "detail")
        questions = (
            [{"stem": "未提及的是"}] * 3
            + [{"stem": "下列说法正确的是"}] * 4
            + [{"stem": "占全省的比重"}] * 4
            + [{"stem": "同比增长"}] * 3
            + [{"tags": ["资料分析-ABRX类-基期量计算与比较"]}] * 2
            + [{"tags": ["资料分析-比较类-双线法与增量比较"]}] * 2
            + [{"tags": [ZILIAO_MIX]}] * 2
        )
        tracks.validate_gd_question_mix(questions)

    def test_chart_match_is_hook_only(self):
        self.assertFalse(tracks.CHART_MATCH_HOOK["implemented"])
        question = {
            "external_id": "M04-Q1",
            "options": [
                {"key": "A", "figure": {"kind": "pie"}},
                {"key": "B", "text": "文字"},
            ],
        }
        called = []
        with tempfile.TemporaryDirectory() as tmp:
            ok = tracks.render_option_figures(
                question, Path(tmp), renderer=lambda fig, path: called.append((fig, path))
            )
        self.assertTrue(ok)
        self.assertEqual(called[0][0]["kind"], "pie")
        self.assertIn("images/", question["options"][0]["images"][0])


class GeminiConfigTest(unittest.TestCase):
    def test_model_reads_env_only(self):
        with patch.dict(os.environ, {"ZILIAO_GEMINI_MODEL": "gemini-test-high"}, clear=False):
            self.assertEqual(tracks.resolve_gemini_model(), "gemini-test-high")
        with patch.dict(os.environ, {"ZILIAO_GEMINI_MODEL": "", "DAILY_GEMINI_MODEL": ""}, clear=False):
            os.environ.pop("ZILIAO_GEMINI_MODEL", None)
            self.assertTrue(tracks.resolve_gemini_model().startswith("gemini-"))

    def test_credentials_do_not_read_repo_dotenv(self):
        with patch.dict(os.environ, {"CLIPROXY_API_KEY": ""}, clear=False):
            os.environ.pop("CLIPROXY_API_KEY", None)
            with patch.object(tracks.Path, "home", return_value=Path("/tmp/no-such-hermes-home")):
                self.assertFalse(tracks.has_gemini_credentials())
        with patch.dict(os.environ, {"CLIPROXY_API_KEY": "secret-from-env"}):
            self.assertTrue(tracks.has_gemini_credentials())


class GateIntegrationTest(unittest.TestCase):
    def test_generation_gate_rejects_flat_difficulty_on_track_a(self):
        import generation_gate

        judge = [
            "根据资料，下列说法正确的是",
            "根据资料，下列说法有误的是",
            "下列说法正确的有几个",
            "不能从上述资料中推出的是",
        ]
        families = tracks.gd_slots_20()
        questions = []
        for i, slot in enumerate(families):
            mid, qn = i // 5 + 1, i % 5 + 1
            if slot["family"] == "judge":
                stem = judge[mid - 1]
            elif slot["family"] == "detail":
                stem = "资料未提及的是" if qn % 2 else "该材料主题是"
            elif slot["family"] == "mix_pull":
                stem = "混合增长率约为"
            else:
                stem = "2023年该指标占全省的比重"
            questions.append({
                "category": "资料分析",
                "question_type": "single",
                "external_id": f"M{mid:02d}-Q{qn}",
                "material_id": f"M{mid:02d}",
                "stem": stem,
                "options": [{"key": k, "text": k} for k in "ABCD"],
                "answer": "A",
                "difficulty": 3,
                "tags": [slot["tag"]],
            })
        manifest = {
            "source": "粤考日练-资料分析-mid-20260927",
            "batch_id": "20260927_hermes_ziliao_tracka",
            "generation": {"batch_constraints": {"track": "gd", "targeted_drill": False, "question_count": 20}},
        }
        long = (
            "2023年G省现代服务业增加值68412.7亿元，同比增长5.2%。数字信息服务业占36.4%，"
            "研发设计营业收入2517.6亿元，同比增长15.3%。高技术服务业投资4561.8亿元，"
            "知识产权服务企业1247家，营收318.6亿元。承接国际服务外包286.4亿美元。"
            "此外会展业场地出租率61.8%，该指标不进入本篇计算题。"
            "同期商务部门还公布了夜间经济活跃商圈指数72.4，仅作背景。"
        )
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "materials.json").write_text(json.dumps([
                {"external_id": "M01", "content": long, "figure": {"kind": "none"}},
                *[{"external_id": f"M{m:02d}",
                   "content": f"2024年G省第{m}产业实现增加值{1876.43 + m}亿元，同比增长{12.7 + m}%。"}
                  for m in range(2, 5)]
            ]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "难度|difficulty"):
                generation_gate.validate_paper_hard_rules(manifest, questions, Path(tmp))


if __name__ == "__main__":
    unittest.main()

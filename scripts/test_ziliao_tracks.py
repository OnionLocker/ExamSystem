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
        self.assertLessEqual(counts["detail"], 1)
        self.assertEqual(counts["judge"], 4)
        self.assertEqual([s["family"] for s in slots[4::5]], ["judge"] * 4)
        kinds = [s["kind"] for s in slots]
        self.assertEqual(set(kinds), set(tracks.REQUIRED_KINDS))
        self.assertTrue(all(kinds.count(k) <= 3 for k in set(kinds) if k != tracks.KIND_JUDGE))
        self.assertEqual(len({s["judge_mix"] for s in slots[4::5]}), 4)

    def test_kind_quota_rejects_missing_or_excess(self):
        slots = tracks.gd_slots_20()
        for index, slot in enumerate(slots):
            if slot.get("kind") in (tracks.KIND_SHARE, tracks.KIND_SHARE_CHANGE):
                slots[index] = dict(slot, kind=tracks.KIND_MULTIPLE, family=tracks.FAMILY_SHARE_ADD)
        with self.assertRaisesRegex(ValueError, "比重类"):
            tracks.validate_gd_kinds(slots)
        slots = tracks.gd_slots_20()
        for index in (12, 16, 18):
            slots[index].update(kind=tracks.KIND_RATE)
        with self.assertRaisesRegex(ValueError, "同一题型至多3题"):
            tracks.validate_gd_kinds(slots)

    def test_classic_20_is_ten_by_two(self):
        slots = tracks.classic_slots(20, 4)
        tags = [s["tag"] for s in slots]
        self.assertEqual(len(set(tags)), 10)
        self.assertTrue(all(tags.count(tag) == 2 for tag in set(tags)))
        self.assertTrue(all(s["family"] == "classic" for s in slots))

    def test_over_mix_rejected(self):
        slots = tracks.gd_slots_20()
        slots[7]["family"] = "mix_pull"
        slots[8]["family"] = "mix_pull"
        with self.assertRaisesRegex(ValueError, "混合或拉动|mix_pull"):
            tracks.validate_gd_quota(slots)

    def test_gd_20_forces_average_growth_and_qualitative_share_change(self):
        slots = tracks.gd_slots_20()
        self.assertIn("平均数增长率", slots[7]["brief"])
        qualitative = slots[18]
        self.assertEqual(qualitative["kind"], tracks.KIND_SHARE_CHANGE)
        self.assertTrue(qualitative["quick"])
        self.assertEqual(qualitative["difficulty_score"], 2)
        self.assertEqual([s["kind"] for s in slots].count(tracks.KIND_SHARE_CHANGE), 2)
        self.assertIn("总量减去已列分项", tracks.track_material_rules("gd", {"id": "M02"}))


class DifficultyBlueprintTest(unittest.TestCase):
    def test_material_then_question_overrides(self):
        tier, overrides = tracks.parse_difficulty_blueprint(
            '{"difficulty":"mid","slots":{"M03-Q4":{"difficulty":"hard","note":"贴近真题"},"M03":"easy"}}')
        self.assertEqual(tier, "mid")
        slots = tracks.apply_difficulty_overrides(tracks.gd_slots_20("mid"), overrides)
        self.assertEqual([s["difficulty"] for s in slots[10:15]], ["easy", "easy", "easy", "hard", "easy"])
        self.assertEqual(slots[13]["difficulty_score"], 4)
        self.assertEqual(slots[13]["difficulty_note"], "贴近真题")
        self.assertEqual(slots[0]["difficulty"], "mid")
        tracks.validate_gd_quota(slots)
        rules = tracks.track_question_rules("gd", slots[13], 4)
        self.assertIn("难档", rules)
        self.assertIn("贴近真题", rules)
        self.assertIn("两增速直接相减", rules)

    def test_rejects_structure_changes(self):
        bad = [
            '{"slots":{"M05":"hard"}}',
            '{"slots":{"M01-Q6":"hard"}}',
            '{"slots":{"M01":"insane"}}',
            '{"slots":{"M01":{"difficulty":"hard","kind":"mixed_growth"}}}',
            '{"difficulty":"hard","count":10}',
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                tracks.parse_difficulty_blueprint(raw)

    def test_hard_tier_raises_calculation_scores_only(self):
        mid, hard = tracks.gd_slots_20("mid"), tracks.gd_slots_20("hard")
        self.assertEqual(hard[0]["difficulty_score"], mid[0]["difficulty_score"])
        self.assertEqual(hard[18]["difficulty_score"], mid[18]["difficulty_score"])
        self.assertEqual(hard[1]["difficulty_score"], mid[1]["difficulty_score"] + 1)

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
    def test_material_retry_records_local_rejection(self):
        import ziliao_parallel_runner as runner
        valid = {"material": {"content": "深圳市收入合计200.5亿元，其中甲114.4亿元、乙86.2亿元。", "figure": {"kind": "none"},
                              "rounding_checks": [{"label": "收入", "unit": "亿元", "places": 1,
                                                   "parts": [{"label": "甲", "raw": "114.36", "shown": "114.4"},
                                                             {"label": "乙", "raw": "86.16", "shown": "86.2"}],
                                                   "total": {"label": "合计", "raw": "200.52", "shown": "200.5"}}]}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "call", side_effect=[{"material": {}}, valid]), patch.object(
            runner, "review_ziliao_material", return_value={"verdict": "PASS", "issues": []}
        ) as reviewer:
            runner.material_call({"track": "classic"}, {"id": "M01", "format": "text"}, "b", Path(tmp))
            attempts = json.loads(Path(tmp, "evidence", "m01-material.json").read_text())["attempts"]
            self.assertEqual([a["review"]["verdict"] for a in attempts], ["REJECT", "PASS"])
            self.assertEqual(reviewer.call_count, 1)

    def test_arithmetic_first_and_second_diff(self):
        self.assertTrue(tracks.is_arithmetic_series([100, 140, 180, 220]))
        self.assertTrue(tracks.is_arithmetic_series([140, 180, 230, 290, 360, 440]))
        self.assertFalse(tracks.is_arithmetic_series([1876.4, 2011.2, 1988.7, 2210.5]))

    def test_money_bars_reject_coarse_rounding_but_not_counts(self):
        figure = {"kind": "bars", "unit": "亿元", "series": [{"values": [8940, 9610, 10250, 11820, 12580, 13950]}]}
        self.assertTrue(tracks.material_realism_errors({"figure": figure}))
        figure["unit"] = "家"
        self.assertFalse(tracks.material_realism_errors({"figure": figure}))
        figure["unit"] = "亿元"
        figure["series"][0]["values"] = [8941.3, 9618.4, 10257.8, 11826.1, 12582.9, 13953.6]
        self.assertFalse(tracks.material_realism_errors({"figure": figure}))

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
    def test_actual_difficulty_survives_slot_stamping(self):
        q = {"difficulty": 2}
        tracks.apply_slot_difficulty(q, {"family": "judge", "difficulty_score": 4})
        self.assertEqual(q["difficulty"], 2)
        self.assertEqual(q["family"], "judge")

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
            [{"stem": "未提及的是"}]
            + [{"stem": "下列说法正确的是"}] * 4
            + [{"stem": "占全省的比重"}] * 5
            + [{"stem": "同比增长"}] * 4
            + [{"tags": ["资料分析-ABRX类-基期量计算与比较"]}] * 2
            + [{"tags": ["资料分析-比较类-双线法与增量比较"]}] * 2
            + [{"tags": [ZILIAO_MIX]}] * 2
        )
        tracks.validate_gd_question_mix(questions)
        with self.assertRaisesRegex(ValueError, "细节查找"):
            tracks.validate_gd_question_mix([{"stem": "未提及的是"}] * 2 + questions[1:19])

    def test_chart_match_renders_option_figures(self):
        self.assertTrue(tracks.CHART_MATCH_HOOK["implemented"])
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


class JudgeFormTest(unittest.TestCase):
    def test_track_a_assigns_at_least_two_forms(self):
        slots = tracks.gd_slots_20()
        finals = slots[4::5]
        forms = [slot["judge_form"] for slot in finals]
        self.assertEqual(forms, ["属实", "无法推出", "计数", "能推出"])
        self.assertGreaterEqual(len(set(forms)), 2)
        self.assertEqual(
            [tracks.classify_judge_form(slot["judge_stem"]) for slot in finals],
            forms,
        )
        for slot in finals:
            self.assertIn(slot["judge_stem"], slot["brief"])
            self.assertNotIn("正确/有误", slot["brief"])

    def test_generic_correct_or_wrong_collapses_to_one_form(self):
        correct = ["根据资料，下列说法正确的是"] * 4
        wrong = ["根据资料，下列说法有误的是"] * 4
        self.assertEqual(len({tracks.classify_judge_form(stem) for stem in correct}), 1)
        self.assertEqual(len({tracks.classify_judge_form(stem) for stem in wrong}), 1)

    def test_quota_rejects_single_wording(self):
        slots = tracks.gd_slots_20()
        for slot in slots[4::5]:
            slot["judge_stem"] = "根据资料，下列说法正确的是"
        with self.assertRaisesRegex(ValueError, "至少 2 种"):
            tracks.validate_gd_quota(slots)

    def test_prompts_lock_assigned_stem(self):
        import ziliao_parallel_runner as runner
        slots = tracks.gd_slots_20()
        plan = {"id": "M02", "track": "gd", "slots": slots[5:10], "count": 5}
        material = {"content": "G省增加值1876.4亿元", "external_id": "b-M02", "figure": {}}
        prompt = runner.paper_prompt(material, plan, "b")
        self.assertIn("不能从上述资料中推出的是", prompt)
        self.assertNotIn("或同等正确/有误", prompt)
        self.assertNotIn("第5题必须是综合正误（正确/有误/不正确）", prompt)
        qprompt = runner.question_prompt(material, plan, 5, "b", slots[9])
        self.assertIn("不能从上述资料中推出的是", qprompt)
        self.assertNotIn("或同等正确/有误", qprompt)

    def test_gd_design_survives_question_repair(self):
        import ziliao_parallel_runner as runner
        slots = tracks.gd_slots_20()
        self.assertNotIn("required_trap", slots[9])
        plan = {"id": "M04", "track": "gd", "slots": slots[15:20], "count": 5}
        material = {"content": "比率从8.6%下降到6.3%。", "external_id": "b-M04", "figure": {}}
        q = {"external_id": "b-M04-Q5"}
        prompts = [runner.paper_prompt(material, plan, "b"),
                   runner.question_prompt(material, plan, 5, "b", slots[19]),
                   runner.question_repair_prompt(material, plan, q, {}, "修正解析")]
        for prompt in prompts:
            self.assertIn(tracks.GD_DESIGN_RULES, prompt)
            self.assertIn("估算+多步混合", prompt)
            self.assertIn("能够从上述资料中推出的是", prompt)
        plan["track"] = "classic"
        self.assertNotIn(tracks.GD_DESIGN_RULES, runner.paper_prompt(material, plan, "b"))

    def test_question_errors_reject_generic_correct(self):
        import ziliao_parallel_runner as runner
        slot = tracks.gd_slots_20()[4]
        question = {
            "external_id": "b-M01-Q5",
            "material_id": "b-M01",
            "stem": "根据资料，下列说法正确的是",
            "options": [{"key": key, "text": key} for key in "ABCD"],
            "answer": "A",
            "tags": [slot["tag"]],
            "explanation": "",
        }
        errors = runner.question_errors(
            question, {}, {"external_id": "b-M01"}, {}, "b-M01-Q5", slot, [],
        )
        self.assertTrue(any("可以判断属实" in err or "属实" in err for err in errors))

    def test_gate_rejects_all_generic_correct(self):
        import generation_gate
        questions = []
        for i in range(20):
            mid = i // 5 + 1
            questions.append({
                "category": "资料分析",
                "question_type": "single",
                "external_id": f"M{mid:02d}-Q{(i % 5) + 1}",
                "material_id": f"M{mid:02d}",
                "stem": "根据资料，下列说法正确的是" if i % 5 == 4 else "2023年比重是多少",
                "options": [{"key": key, "text": key} for key in "ABCD"],
                "answer": "A",
                "difficulty": 2,
                "tags": ["资料分析-基础知识-统计术语与常考概念"],
            })
        manifest = {"generation": {"batch_constraints": {"track": "gd", "targeted_drill": False}}}
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "materials.json").write_text(json.dumps([
                {"external_id": f"M{m:02d}", "content": f"2024年G省第{m}产业增加值{1876.43 + m}亿元，同比增长{12.7 + m}%。"}
                for m in range(1, 5)
            ]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "跨篇轮换"):
                generation_gate.validate_paper_hard_rules(manifest, questions, Path(tmp))


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
    def test_rating_only_failure_does_not_regenerate_question(self):
        import generation_gate as gate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            report = {"results": [{"question_id": "batch-M01-Q1", "verdict": "PASS",
                "correctness": {"verdict": "PASS"}, "quality": {"verdict": "PASS",
                    "issues": [],
                    "review": {"actual_difficulty": 2, "difficulty_reason": "一步除法"}}}]}
            (root / "evidence/system-quality.json").write_text(json.dumps(report))
            questions = [{"external_id": "batch-M01-Q1", "category": "资料分析", "difficulty": 3, "stem": "保留题面"}]
            (root / "questions.json").write_text(json.dumps(questions))
            gate.record_ziliao_difficulty(root, root / "evidence/system-quality.json")
            questions = json.loads((root / "questions.json").read_text())
            self.assertEqual(questions[0]["difficulty"], 2)
            self.assertEqual(questions[0]["stem"], "保留题面")
            evidence = json.loads((root / "evidence/system-quality.json").read_text())
            self.assertEqual(evidence["questions_sha256"], gate.digest(root / "questions.json"))

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


class RotationTest(unittest.TestCase):
    def test_rotating_papers_pass_quota_and_vary(self):
        import random
        from collections import Counter
        rng = random.Random(3)
        recent_kinds, recent_types, seen, totals = [], [], set(), Counter()
        for _ in range(40):
            types, slots = tracks.gd_rotating_paper("mid", rng, recent_kinds, recent_types)
            tracks.validate_gd_quota(slots, count=20)
            self.assertEqual(types[0], "text")
            self.assertTrue(any(t in tracks.TABLE_TYPES for t in types) and any(t in tracks.CHART_TYPES for t in types))
            kinds = [s["kind"] for s in slots]
            self.assertEqual([s["family"] for s in slots[4::5]], ["judge"] * 4)
            for kind, count in Counter(k for k in kinds if k != tracks.KIND_JUDGE).items():
                self.assertLessEqual(count, tracks.kind_cap(kind) if kind in tracks.KIND_SPECS else 1)
            for index, slot in enumerate(slots):
                if slot["kind"] in tracks.KIND_SPECS:
                    self.assertIn(types[index // 5], tracks.KIND_SPECS[slot["kind"]]["types"])
            self.assertGreaterEqual(sum(s.get("option_format") in ("interval", "direction") for s in slots), 2)
            seen.add(tuple(kinds))
            totals.update(kinds)
            recent_kinds = [set(kinds)] + recent_kinds[:2]
            recent_types = [set(types)] + recent_types[:2]
        self.assertGreater(len(seen), 35)
        for kind in (tracks.KIND_COUNT, tracks.KIND_SORT, tracks.KIND_AVG_DIFF, tracks.KIND_CHART_MATCH,
                     tracks.KIND_PROJECTION, tracks.KIND_CUMULATIVE, tracks.KIND_TEXT_READING):
            self.assertGreater(totals[kind], 0, kind)
        self.assertGreater(totals[tracks.KIND_SHARE], totals[tracks.KIND_MIX])

    def test_recent_kinds_are_downweighted(self):
        import random
        from collections import Counter
        fresh, penalized = Counter(), Counter()
        for seed in range(60):
            _, slots = tracks.gd_rotating_paper("mid", random.Random(seed))
            fresh.update(s["kind"] for s in slots)
            _, slots = tracks.gd_rotating_paper("mid", random.Random(seed), [{tracks.KIND_COUNT, tracks.KIND_SORT}] * 3)
            penalized.update(s["kind"] for s in slots)
        self.assertLess(penalized[tracks.KIND_COUNT] + penalized[tracks.KIND_SORT],
                        (fresh[tracks.KIND_COUNT] + fresh[tracks.KIND_SORT]) * 0.6)

    def test_question_plan_lists_kinds_and_data_needs(self):
        import random
        types, slots = tracks.gd_rotating_paper("mid", random.Random(5))
        plan = tracks.material_question_plan(types[1], slots[5:10])
        self.assertIn("五题题型依次为", plan)
        self.assertIn(tracks.MATERIAL_TYPES[types[1]]["plan"][:10], plan)

    def test_ranged_calculation(self):
        ranges = {"A": [None, 5], "B": [5, 10], "C": [10, 15], "D": [15, None]}
        self.assertEqual(tracks.range_calculation_issues(7.3, ranges, "B", set("ABCD")), [])
        self.assertTrue(tracks.range_calculation_issues(7.3, ranges, "C", set("ABCD")))
        self.assertTrue(any("过近" in i for i in tracks.range_calculation_issues(10.1, ranges, "C", set("ABCD"))))
        direction = {"A": [0, 1000], "B": [1000, None], "C": [-1000, 0], "D": [None, -1000]}
        self.assertEqual(tracks.range_calculation_issues(-1320, direction, "D", set("ABCD")), [])
        self.assertTrue(tracks.range_calculation_issues(5, {"A": [0, 1]}, "A", set("ABCD")))

    def test_chart_match_checks_target_and_distinguishable_shapes(self):
        cats = ["同城", "异地", "国际", "其他"]
        good = {"answer": "B", "options": [
            {"key": "A", "text": "", "figure": {"kind": "pie", "categories": cats, "values": [40, 40, 10, 10]}},
            {"key": "B", "text": "", "figure": {"kind": "pie", "categories": cats, "values": [19, 59, 15, 7]}},
            {"key": "C", "text": "", "figure": {"kind": "pie", "categories": cats, "values": [59, 19, 15, 7]}},
            {"key": "D", "text": "", "figure": {"kind": "pie", "categories": cats, "values": [19, 45, 29, 7]}},
        ]}
        calc = {"target": ["58.3", "182.6", "46.9", "21.4"]}
        self.assertEqual(tracks.chart_match_issues(good, calc), [])
        close = json.loads(json.dumps(good))
        close["options"][3]["figure"]["values"] = [20, 57, 16, 7]
        self.assertTrue(any("无法区分" in i for i in tracks.chart_match_issues(close, calc)))
        wrong = json.loads(json.dumps(good))
        wrong["answer"] = "A"
        self.assertTrue(any("target" in i for i in tracks.chart_match_issues(wrong, calc)))
        years = ["2021", "2022", "2023", "2024"]
        trend = {"answer": "A", "options": [
            {"key": k, "text": "", "figure": {"kind": "line", "categories": years, "values": v}}
            for k, v in zip("ABCD", ([5.5, 1.3, -3.3, 5.6], [1.3, 5.5, -3.3, 5.6], [5.5, 1.3, 3.3, 5.6], [-5.5, 1.3, -3.3, 5.6]))
        ]}
        self.assertEqual(tracks.chart_match_issues(trend, {"target": ["5.5", "1.3", "-3.3", "5.6"]}), [])

    def test_ranged_and_chart_slots_skip_exact_option_rules(self):
        from ziliao_checklist import question_style_issues
        interval = {"family": "growth", "stem": "2024年某指标同比增长", "answer": "B", "explanation": "算得7.3%，落在B区间。",
                    "options": [{"key": "A", "text": "不到5%"}, {"key": "B", "text": "在5%到10%之间"},
                                {"key": "C", "text": "在10%到15%之间"}, {"key": "D", "text": "超过15%"}]}
        slot = {"family": "growth", "kind": tracks.KIND_RATE, "option_format": "interval"}
        self.assertEqual(question_style_issues(interval, slot=slot), [])
        direction = {"family": "avg_cmp", "stem": "平均每笔金额比上年同期", "answer": "B", "explanation": "算得多1320元。",
                     "options": [{"key": "A", "text": "上升了不到1000元"}, {"key": "B", "text": "上升了1000元以上"},
                                 {"key": "C", "text": "下降了不到1000元"}, {"key": "D", "text": "下降了1000元以上"}]}
        slot = {"family": "avg_cmp", "kind": tracks.KIND_AVG_DIFF, "option_format": "direction"}
        self.assertEqual(question_style_issues(direction, slot=slot), [])
        figure_on_plain = {"family": "share_add", "options": [{"key": "A", "figure": {"kind": "pie"}}]}
        self.assertTrue(any("chart_match" in i for i in question_style_issues(figure_on_plain, slot={"kind": tracks.KIND_SHARE})))


if __name__ == "__main__":
    unittest.main()

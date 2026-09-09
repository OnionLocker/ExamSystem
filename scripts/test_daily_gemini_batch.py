#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for direct Gemini daily drafts."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import daily_batch_scheduler
import daily_gemini_batch
from scheduler_common import ensure_run_schema


CAT_SHULIANG = "\u6570\u91cf\u5173\u7cfb"
SRC_SHULIANG = "\u5e7f\u4e1c\u7701\u8003\u884c\u6d4b-\u6570\u91cf\u5173\u7cfb-20260920"
TAG_SHULIANG = "\u6570\u91cf\u5173\u7cfb-\u6570\u5b57\u63a8\u7406-\u6570\u5b57\u63a8\u7406"
SUB_SEQ = "\u6570\u5b57\u63a8\u7406"


class ParseJsonTest(unittest.TestCase):
    def test_strips_fences_and_list(self):
        raw = '```json\n[{"stem": "x"}]\n```'
        self.assertEqual(daily_gemini_batch.parse_json(raw)["questions"][0]["stem"], "x")

    def test_extracts_object_from_prose(self):
        raw = 'here\n{"questions": [{"stem": "y"}]}\nok'
        self.assertEqual(daily_gemini_batch.parse_json(raw)["questions"][0]["stem"], "y")


class WriteBatchTest(unittest.TestCase):
    def test_writes_manifest_and_stamps_source(self):
        run = {
            "plan_date": "2026-09-20",
            "module": CAT_SHULIANG,
            "planned_count": 2,
            "batch_id": "daily-20260920-shuliang-abc",
        }
        draft = {
            "questions": [
                {
                    "stem": "1,2,3,?",
                    "options": {"A": "4", "B": "5", "C": "6", "D": "7"},
                    "answer": "A",
                    "analysis": "diff",
                    "tags": [TAG_SHULIANG],
                    "sub_category": SUB_SEQ,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            daily_gemini_batch.write_batch(run, batch_dir, draft)
            questions = json.loads((batch_dir / "questions.json").read_text(encoding="utf-8"))
            manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(questions[0]["external_id"], "daily-20260920-shuliang-abc_01")
            self.assertEqual(questions[0]["source"], SRC_SHULIANG)
            self.assertEqual(questions[0]["options"][0]["key"], "A")
            self.assertEqual(manifest["kind"], "ai-generated")
            self.assertEqual(manifest["difficulty_tier"], "hard")
            self.assertEqual(manifest["generation"]["evaluation_contexts"], [])

    def test_write_batch_keeps_locked_kepui_slots(self):
        run = {"plan_date": "2026-09-08", "module": daily_gemini_batch.CAT_KEPUI, "planned_count": 5, "batch_id": "k"}
        locked = [
            "科学推理-电学-串并联",
            "科学推理-力学-摩擦与惯性",
            "科学推理-压强与浮力-容器底部受力",
            "科学推理-地理-区域地理",
            "科学推理-生物-生态系统与能量",
        ]
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            (batch_dir / "locked-slots.json").write_text(
                json.dumps([{"index": i, "tag": tag} for i, tag in enumerate(locked, 1)], ensure_ascii=False),
                encoding="utf-8",
            )
            daily_gemini_batch.write_batch(
                run,
                batch_dir,
                {"questions": [{"stem": "如图所示为甲、乙两地的气候资料图。"}, {"stem": "x"}, {"stem": "y"}, {"stem": "z"}, {"stem": "w"}]},
            )
            rows = json.loads((batch_dir / "questions.json").read_text(encoding="utf-8"))
            self.assertEqual([row["tags"][0] for row in rows], locked)
            kept = json.loads((batch_dir / "locked-slots.json").read_text(encoding="utf-8"))
            self.assertEqual([item["tag"] for item in kept], locked)

class RenderFigureTest(unittest.TestCase):
    def setUp(self):
        self._draw_in_batch = os.environ.get("DRAW_IN_BATCH")
        self._q_ops = os.environ.get("QUESTION_FLASH_OPS")
        os.environ["DRAW_IN_BATCH"] = "0"
        os.environ["QUESTION_FLASH_OPS"] = "0"

    def tearDown(self):
        if self._draw_in_batch is None:
            os.environ.pop("DRAW_IN_BATCH", None)
        else:
            os.environ["DRAW_IN_BATCH"] = self._draw_in_batch
        if self._q_ops is None:
            os.environ.pop("QUESTION_FLASH_OPS", None)
        else:
            os.environ["QUESTION_FLASH_OPS"] = self._q_ops

    def test_graphic_retry_does_not_reinterpret_bank_metadata(self):
        slots = [{'tag': '判断推理-图形推理-数量规律', 'exam_move': '封闭面递增', 'answer': 'A'}]
        run = {'module': '判断推理', 'planned_count': 20, 'batch_id': 'graphic-retry'}
        draft = {'questions': [{'external_id': 'graphic-retry_01', 'stem_images': ['images/old.png']}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'questions.json').write_text(json.dumps(draft['questions']))
            with mock.patch.object(daily_gemini_batch, 'generation_payload_extras', return_value={'panduan_pack': {'slots': [{**slots[0], 'section': 'graphic'}]}}), \
                 mock.patch.object(daily_gemini_batch, 'write_batch'), \
                 mock.patch.object(daily_gemini_batch, 'run_cmd', return_value=''), \
                 mock.patch.object(daily_gemini_batch, 'call_gemini') as generate:
                daily_gemini_batch.generate_and_import(run=run, batch_dir=root, db_path=root/'db', timeout=60, prompt='test')
            generate.assert_not_called()
            questions = json.loads((root/'questions.json').read_text())
            self.assertNotIn('figure', questions[0])
            self.assertIn('同一张题图下方', questions[0]['stem'])

    def test_unnumbered_gate_failure_revises_draft(self):
        run = {'module': '言语理解与表达', 'planned_count': 1, 'batch_id': 'retry-test'}
        draft = {'questions': [{'external_id': 'retry-test_01', 'stem': 'old'}]}
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(daily_gemini_batch, 'call_gemini', side_effect=[
                draft, {'questions': [{'external_id': 'retry-test_01', 'stem': 'fixed'}]},
            ]) as generate, mock.patch.object(daily_gemini_batch, 'write_batch'), \
                 mock.patch.object(daily_gemini_batch, 'render_assets'), \
                 mock.patch.object(daily_gemini_batch, 'reload_draft_files'), \
                 mock.patch.object(daily_gemini_batch, 'run_cmd', side_effect=[RuntimeError('batch layout invalid'), '', '']):
                daily_gemini_batch.generate_and_import(run=run, batch_dir=Path(temp), db_path=Path(temp)/'db', timeout=60, prompt='test')
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(draft['questions'][0]['stem'], 'fixed')

    def test_renders_table_and_strips_figure(self):
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            draft = {
                "questions": [],
                "materials": [
                    {
                        "content": "see figure",
                        "figure": {
                            "kind": "table",
                            "file": "images/m-01-table.png",
                            "title": "value",
                            "headers": ["y", "v"],
                            "rows": [["2024", "10"]],
                        },
                    }
                ],
            }
            daily_gemini_batch.render_assets(batch_dir, draft, deadline=10**12)
            dest = batch_dir / "images" / "m-01-table.png"
            self.assertTrue(dest.is_file())
            self.assertNotIn("figure", draft["materials"][0])
            self.assertEqual(draft["materials"][0]["images"], ["images/m-01-table.png"])

    def test_kepui_stem_draws_without_figure_spec(self):
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            draft = {
                "questions": [{
                    "external_id": "k_03",
                    "stem": "电路中定值电阻 R1 与 R2 并联。电流表 A1 在 R1 支路，电流表 A 位于干路。",
                }],
                "image_specs": {"questions": [{"question_id": "k_03", "image_facts": ["R1"]}]},
            }
            captured = []
            def fake(fig, dest):
                captured.append(dict(fig))
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"png")
            with mock.patch.object(daily_gemini_batch, "render_program", side_effect=fake):
                with mock.patch.object(daily_gemini_batch, "generate_line_image") as ai:
                    daily_gemini_batch.render_assets(batch_dir, draft, deadline=10**12)
            ai.assert_not_called()
            self.assertEqual(captured[0]["kind"], "circuit")
            self.assertEqual(captured[0]["left"], "R1")
            self.assertTrue((batch_dir / "images" / "q-01-stem.png").is_file())

    def test_program_figure_beats_image_facts(self):
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            draft = {
                "questions": [
                    {
                        "external_id": "q1",
                        "figure": {"kind": "cube_iso", "file": "images/q-01-stem.png", "marks": {"top": "plus"}},
                        "stem_images": ["images/q-01-stem.png"],
                    }
                ],
                "image_specs": {"questions": [{"question_id": "q1", "image_facts": ["do not draw this"]}]},
            }
            with mock.patch.object(daily_gemini_batch, "render_program", side_effect=lambda fig, dest: dest.write_bytes(b"png")):
                with mock.patch.object(daily_gemini_batch, "generate_line_image") as ai:
                    daily_gemini_batch.render_assets(batch_dir, draft, deadline=10**12)
            ai.assert_not_called()
            self.assertTrue((batch_dir / "images" / "q-01-stem.png").is_file())
            self.assertNotIn("figure", draft["questions"][0])

    def test_write_batch_flags_program_figures(self):
        run = {
            "plan_date": "2026-09-03",
            "module": "判断推理",
            "planned_count": 10,
            "batch_id": "fig-x",
            "figure_control": True,
            "source": "广东省考行测-空间科学推理-20260903",
        }
        with tempfile.TemporaryDirectory() as temp:
            daily_gemini_batch.write_batch(run, Path(temp), {"questions": [{"stem": "如图", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "answer": "A"}]})
            manifest = json.loads((Path(temp) / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["generation"]["batch_constraints"]["program_figures"])
            self.assertEqual(manifest["source"], "广东省考行测-空间科学推理-20260903")

    def test_focused_kepui_skips_five_subject_layout(self):
        run = {
            "plan_date": "2026-09-07",
            "module": "科学推理",
            "planned_count": 2,
            "batch_id": "hermes-ganggan",
            "focus_tag": "科学推理-力学-杠杆滑轮",
        }
        with tempfile.TemporaryDirectory() as temp:
            daily_gemini_batch.write_batch(
                run,
                Path(temp),
                {"questions": [{"stem": "如图", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "answer": "A"}]},
            )
            constraints = json.loads((Path(temp) / "manifest.json").read_text(encoding="utf-8"))[
                "generation"
            ]["batch_constraints"]
            self.assertEqual(constraints["focus_tag"], "科学推理-力学-杠杆滑轮")
            self.assertNotIn("kepui_layout", constraints)
            self.assertTrue(constraints["program_figures"])

    def test_stamp_locks_kepui_kind_from_tag(self):
        run = {
            "plan_date": "2026-09-08",
            "module": "科学推理",
            "planned_count": 1,
            "batch_id": "daily-k",
        }
        rows = daily_gemini_batch.stamp_questions(
            run,
            [{
                "stem": "如图所示为某锋面天气系统剖面示意图。",
                "tags": ["科学推理-地理-海陆风"],
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "A",
            }],
        )
        self.assertEqual(rows[0]["figure_template"], "breeze")

    def test_stamp_keeps_plain_logic_tags(self):
        run = {
            "plan_date": "2026-09-08",
            "module": "判断推理",
            "planned_count": 20,
            "batch_id": "s",
        }
        rows = daily_gemini_batch.stamp_questions(
            run,
            [{"stem": "题干设问", "tags": ["判断推理-逻辑判断-逻辑论证-一般质疑"], "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "answer": "A"}] * 20,
        )
        self.assertEqual(rows[0]["category"], "判断推理")
        self.assertEqual(rows[0]["tags"][0], "判断推理-逻辑判断-逻辑论证-一般质疑")
        self.assertNotIn("figure", rows[0])

    def test_slot_retry_does_not_collapse_kinds(self):
        text = daily_gemini_batch.slot_retry_prompt("base", {"module": "科学推理"}, [], ["x"], "err")
        self.assertNotIn("(tank/circuit/lever/front/reflex)", text)
        self.assertIn("locked by kepui_pack", text)

    def test_stamp_clears_verbal_sub_and_defaults_difficulty(self):
        run = {
            "plan_date": "2026-09-07",
            "module": "言语理解与表达",
            "planned_count": 1,
            "batch_id": "daily-y",
        }
        rows = daily_gemini_batch.stamp_questions(
            run,
            [{"stem": "x", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "answer": "A", "sub_category": "逻辑填空"}],
        )
        self.assertNotIn("sub_category", rows[0])
        self.assertEqual(rows[0]["difficulty"], 2)
        ziliao = daily_gemini_batch.stamp_questions(
            {"plan_date": "2026-09-07", "module": "资料分析", "batch_id": "daily-z"},
            [{"stem": "x", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "answer": "A", "sub_category": "资料分析"}],
        )
        self.assertNotIn("sub_category", ziliao[0])


    def test_draw_in_batch_calls_draw_figure(self):
        os.environ["DRAW_IN_BATCH"] = "1"
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            draft = {
                "questions": [{
                    "external_id": "k_01",
                    "category": "科学推理",
                    "stem": "如图电路中 R1 与 R2 并联。",
                    "figure": {"kind": "circuit", "file": "images/q-01-stem.png"},
                }]
            }
            called = []
            def fake_draw(request, dest, batch_dir=None, **kwargs):
                called.append(request)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"png")
            with mock.patch("draw_agent.draw_figure", side_effect=fake_draw):
                with mock.patch.object(daily_gemini_batch, "generate_line_image") as ai:
                    daily_gemini_batch.render_assets(batch_dir, draft, deadline=10**12)
            ai.assert_not_called()
            self.assertEqual(len(called), 1)
            self.assertTrue((batch_dir / "images" / "q-01-stem.png").is_file())

    def test_figure_regen_retries_the_question(self):
        os.environ["DRAW_IN_BATCH"] = "1"
        run = {"module": "科学推理", "planned_count": 1, "batch_id": "regen-test"}
        first = {"questions": [{"external_id": "regen-test_01", "stem": "old", "category": "科学推理"}]}
        second = {"questions": [{"external_id": "regen-test_01", "stem": "new circuit", "category": "科学推理"}]}
        renders = {"n": 0}
        def fake_render(batch_dir, draft, deadline):
            renders["n"] += 1
            if renders["n"] == 1:
                raise RuntimeError("regen-test_01: FIGURE_REGEN: 题干无法出图")
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(daily_gemini_batch, "call_gemini", side_effect=[first, second]) as generate, \
                 mock.patch.object(daily_gemini_batch, "write_batch"), \
                 mock.patch.object(daily_gemini_batch, "render_assets", side_effect=fake_render), \
                 mock.patch.object(daily_gemini_batch, "reload_draft_files"), \
                 mock.patch.object(daily_gemini_batch, "run_cmd", return_value=""):
                daily_gemini_batch.generate_and_import(
                    run=run, batch_dir=Path(temp), db_path=Path(temp) / "db", timeout=60, prompt="test"
                )
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(renders["n"], 2)
            self.assertEqual(first["questions"][0]["stem"], "new circuit")



    def test_write_batch_keeps_figure_contract(self):
        run = {
            "plan_date": "2026-09-08",
            "module": "科学推理",
            "planned_count": 1,
            "batch_id": "daily-contract",
        }
        draft = {
            "questions": [{
                "stem": "如图电路中 R1 与 R2 并联，电流表 A 在干路。",
                "tags": ["科学推理-电学-电路故障"],
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "A",
                "figure_contract": {
                    "kind": "circuit",
                    "must_show": ["R1", "R2", "A"],
                    "must_not": ["木块"],
                    "must_derive": ["干路电流最大"],
                },
            }]
        }
        with tempfile.TemporaryDirectory() as temp:
            daily_gemini_batch.write_batch(run, Path(temp), draft)
            specs = json.loads((Path(temp) / "image-specs.json").read_text(encoding="utf-8"))
            row = specs["questions"][0]
            self.assertEqual(row["image_facts"][:3], ["R1", "R2", "A"])
            self.assertIn("木块", row["must_not"])
            self.assertEqual(draft["questions"][0]["figure_contract"]["kind"], "circuit")
            self.assertEqual(draft["questions"][0]["figure_template"], "circuit")

    def test_ops_patch_skips_gemini_retry(self):
        os.environ["QUESTION_FLASH_OPS"] = "1"
        run = {"module": "科学推理", "planned_count": 1, "batch_id": "ops-test"}
        first = {"questions": [{
            "external_id": "ops-test_01",
            "stem": "old",
            "category": "科学推理",
            "options": [
                {"key": "A", "text": "甲"},
                {"key": "B", "text": "一定是乙"},
                {"key": "C", "text": "丙"},
                {"key": "D", "text": "丁"},
            ],
            "answer": "A",
            "analysis": "甲对",
        }]}
        renders = {"n": 0}
        def fake_render(batch_dir, draft, deadline):
            renders["n"] += 1
        def fake_pre(draft, batch_dir, error, only_ids=None, caller=None):
            if only_ids:
                return {"patched": ["ops-test_01"], "need_gemini": [], "block_render": False, "error": ""}
            return {"patched": [], "need_gemini": [], "block_render": False, "error": ""}
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(daily_gemini_batch, "call_gemini", side_effect=[first]) as generate, \
                 mock.patch.object(daily_gemini_batch, "write_batch"), \
                 mock.patch.object(daily_gemini_batch, "preflight_draft", side_effect=fake_pre), \
                 mock.patch.object(daily_gemini_batch, "render_assets", side_effect=fake_render), \
                 mock.patch.object(daily_gemini_batch, "reload_draft_files"), \
                 mock.patch.object(daily_gemini_batch, "run_cmd", side_effect=[RuntimeError("ops-test_01: giveaway extreme-word distractor"), "", ""]):
                daily_gemini_batch.generate_and_import(
                    run=run, batch_dir=Path(temp), db_path=Path(temp) / "db", timeout=60, prompt="test"
                )
            self.assertEqual(generate.call_count, 1)
            self.assertEqual(renders["n"], 2)


class AugmentPromptTest(unittest.TestCase):
    def test_retry_block_omits_raw_gate_dump(self):
        run = {"module": "科学推理"}
        raw = "ExamSystem 系统质检失败：" + ("DUMP" * 400)
        text = daily_gemini_batch.augment_prompt("base", run, Path("."), raw)
        self.assertNotIn("DUMPDUMP", text)
        blocked = daily_gemini_batch.augment_prompt("base", run, Path("."), "解析混用 ρ_A、ρ_B")
        self.assertIn("notation_stem_mismatch", blocked)
        self.assertNotIn(raw[-80:], blocked)


class SchedulerPromptTest(unittest.TestCase):
    def test_run_one_calls_gemini_not_hermes(self):
        run = {
            "plan_date": "2026-09-20",
            "module": CAT_SHULIANG,
            "planned_count": 15,
            "batch_id": "daily-x",
        }
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "exam.db"
            conn = sqlite3.connect(db)
            ensure_run_schema(conn)
            conn.execute(
                "INSERT INTO ai_daily_batch_runs(plan_date,module,batch_id,status,planned_count,source) "
                "VALUES (?,?,?,?,?,?)",
                ("2026-09-20", CAT_SHULIANG, "daily-x", "scheduled", 15, "daily-scheduler"),
            )
            conn.execute("CREATE TABLE questions (batch_id TEXT)")
            conn.commit()
            conn.close()
            with (
                mock.patch.object(daily_batch_scheduler, "generate_and_import") as gen,
                mock.patch.object(daily_batch_scheduler, "imported_count", return_value=15),
            ):
                out = daily_batch_scheduler.run_one(
                    run, {"compact": ""}, db, Path(temp) / "out", timeout=30
                )
            gen.assert_called_once()
            self.assertNotIn("hermes", str(gen.call_args).lower())
            self.assertEqual(out["status"], "imported")



class SlotRetryTest(unittest.TestCase):
    def test_parse_json_rejected(self):
        qs = [{"external_id": "b_01"}, {"external_id": "b_02"}, {"external_id": "b_03"}]
        err = 'gate failed: {"rejected": ["b_02"], "item_issues": ["b_02: x"]}'
        self.assertEqual(daily_gemini_batch.parse_rejected_question_ids(err, qs), ["b_02"])

    def test_parse_figure_regen_qid(self):
        qs = [{"external_id": "regen-test_01"}, {"external_id": "regen-test_02"}]
        err = "regen-test_01: FIGURE_REGEN: 题干无法出图"
        self.assertEqual(daily_gemini_batch.parse_rejected_question_ids(err, qs), ["regen-test_01"])

    def test_parse_qid_in_prose(self):
        qs = [{"external_id": "daily-x_11"}, {"external_id": "daily-x_14"}]
        err = "mismatch: daily-x_14 tag"
        self.assertEqual(daily_gemini_batch.parse_rejected_question_ids(err, qs), ["daily-x_14"])

    def test_ziliao_does_not_expand_item_failures(self):
        qs = [
            {"external_id": f"z_{i:02d}", "material_id": "M01" if i <= 5 else "M02"}
            for i in range(1, 11)
        ]
        self.assertEqual(
            daily_gemini_batch.expand_retry_ids(daily_gemini_batch.CAT_ZILIAO, ["z_03"], qs),
            ["z_03"],
        )
        self.assertEqual(
            daily_gemini_batch.expand_retry_ids(daily_gemini_batch.CAT_ZILIAO, ["z_03", "z_05"], qs),
            ["z_03", "z_05"],
        )
        self.assertEqual(
            daily_gemini_batch.expand_retry_ids(daily_gemini_batch.CAT_PANDUAN, ["z_03"], qs),
            ["z_03"],
        )

    def test_ziliao_slot_keep_context(self):
        qs = [
            {
                "external_id": f"z_{i:02d}",
                "material_id": "M01",
                "stem": f"s{i}",
                "answer": "A",
                "tags": ["资料分析-ABRX类-增长量计算与现期推算"],
            }
            for i in range(1, 6)
        ]
        q3 = daily_gemini_batch.ziliao_slot_keep_context(qs, ["z_03"])
        self.assertEqual(q3[0]["slot"], 3)
        self.assertEqual([row["external_id"] for row in q3[0]["keep_questions"]], ["z_01", "z_02", "z_04", "z_05"])
        self.assertIn("第3题", q3[0]["task"])
        both = daily_gemini_batch.ziliao_slot_keep_context(qs, ["z_03", "z_05"])
        self.assertEqual([row["replace_id"] for row in both], ["z_03", "z_05"])
        self.assertEqual(both[1]["slot"], 5)
        self.assertIn("综合判断", both[1]["task"])

    def test_merge_keeps_passers(self):
        old = [
            {"external_id": "a_01", "stem": "keep"},
            {"external_id": "a_02", "stem": "old"},
        ]
        out = daily_gemini_batch.merge_retry_questions(
            old, [{"external_id": "a_02", "stem": "fresh"}], {"a_02"}
        )
        self.assertEqual(out[0]["stem"], "keep")
        self.assertEqual(out[1]["stem"], "fresh")
        self.assertEqual(out[1]["external_id"], "a_02")

    def test_sit_together_uses_batch_issues(self):
        qs = [{"external_id": f"z_{i:02d}"} for i in range(1, 6)]
        err = json.dumps(
            {
                "rejected": [f"z_{i:02d}" for i in range(1, 6)],
                "batch_issues": [{"question_id": "z_03", "description": "pie"}],
                "item_issues": [],
            }
        )
        self.assertEqual(daily_gemini_batch.parse_rejected_question_ids(err, qs), ["z_03"])

    def test_parse_missing_material_image(self):
        qs = [
            {"external_id": "z_06", "material_id": "batch-M02"},
            {"external_id": "z_01", "material_id": "batch-M01"},
        ]
        mats = [{"external_id": "batch-M02", "images": ["images/m-02-table.png"]}]
        err = "generation gate failed: 图片缺失或路径非法：images/m-02-table.png"
        self.assertEqual(
            daily_gemini_batch.parse_rejected_question_ids(err, qs, mats),
            ["z_06"],
        )

    def test_parse_material_id_marks_group(self):
        qs = [
            {"external_id": "z_01", "material_id": "batch-M02"},
            {"external_id": "z_02", "material_id": "batch-M01"},
        ]
        err = "batch-M01: y1 must be greater than or equal to y0"
        self.assertEqual(daily_gemini_batch.parse_rejected_question_ids(err, qs), ["z_02"])

    def test_merge_calculations_keeps_others(self):
        old = {"questions": [
            {"question_id": "z_01", "correct": 1},
            {"question_id": "z_06", "correct": 6},
        ]}
        incoming = {"questions": [{"question_id": "z_06", "correct": 60}]}
        out = daily_gemini_batch.merge_calculations(old, incoming, {"z_06"})
        by_id = {row["question_id"]: row["correct"] for row in out["questions"]}
        self.assertEqual(by_id["z_01"], 1)
        self.assertEqual(by_id["z_06"], 60)

    def test_merge_image_specs_keeps_others(self):
        old = {
            "questions": [
                {"question_id": "a_01", "image_facts": ["old1"]},
                {"question_id": "a_02", "image_facts": ["old2"]},
            ]
        }
        incoming = {"questions": [{"question_id": "a_02", "image_facts": ["new2"]}]}
        out = daily_gemini_batch.merge_image_specs(old, incoming, {"a_02"})
        by_id = {row["question_id"]: row["image_facts"] for row in out["questions"]}
        self.assertEqual(by_id["a_01"], ["old1"])
        self.assertEqual(by_id["a_02"], ["new2"])




class SkipOkFigureTest(unittest.TestCase):
    def test_render_one_skips_ok_draw_log(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "q.png"
            dest.write_bytes(b"png")
            dest.with_suffix(".svg").write_text("<svg></svg>", encoding="utf-8")
            dest.with_suffix(".draw.json").write_text('{"ok": true}', encoding="utf-8")
            with mock.patch("draw_agent.draw_figure") as draw:
                daily_gemini_batch.render_one(
                    {"kind": "circuit"},
                    dest,
                    question={"stem": "如图", "tags": ["科学推理-电学-串并联"]},
                )
            draw.assert_not_called()

    def test_dump_pipe_reads_locked_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            daily_gemini_batch.dump(
                batch_dir / "locked-slots.json",
                [{"index": 1, "tag": "科学推理-地理-海陆风", "kind": "breeze"}],
            )
            daily_gemini_batch.dump_pipe(batch_dir, {"status": "ok"})
            payload = json.loads((batch_dir / "pipeline-timing.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["slots"], ["科学推理-地理-海陆风"])




    def test_program_figure_gate_error(self):
        self.assertTrue(
            daily_gemini_batch.program_figure_gate_error(
                "generation gate failed: 程序作图质检未过：q_04: 题干有甲乙，图上没有"
            )
        )
        self.assertFalse(daily_gemini_batch.program_figure_gate_error("quality hard/zero/regression failure"))


if __name__ == "__main__":
    unittest.main()

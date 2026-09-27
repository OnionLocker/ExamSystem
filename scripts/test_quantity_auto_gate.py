#!/usr/bin/env python3
"""数量实际难度与困难档容差；简单/中等、历史证据和其他模块不放宽。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from generation_gate import QUANTITY_HARD_POLICY, digest, validate_batch_constraints, validate_lite_review, verify
import quiz_lite
from test_quiz_lite import FakeModel, TAG, blind_ok, examiner_ok, question
from unittest.mock import patch


class QuantityAutoGate(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.question = {
            "external_id": "auto_gate_01", "category": "数量关系",
            "tags": ["数量关系-数学运算-概率问题"], "difficulty": 3,
            "answer": "A", "analysis": "三种等可能结果中两种满足要求，概率为三分之二。",
        }
        self.manifest = {
            "batch_id": "auto_gate", "difficulty_tier": "auto",
            "generation": {"pipeline": "quiz_lite", "batch_constraints": {
                "question_count": 1,
                "slot_plan": [{"tag": self.question["tags"][0], "count": 1, "difficulty": "auto"}],
            }},
        }
        self.evidence = {
            "version": 3, "kind": "examsystem-lite-review", "batch_id": "auto_gate",
            "model": "gemini-flash", "verdict": "PASS", "results": [{
                "question_id": "auto_gate_01", "answer": "A", "verdict": "PASS",
                "blind": {"answer": "A", "also_valid": [], "unsolvable": False,
                          "steps": "2/3", "actual_difficulty": "easy", "difficulty_reason": "直接计数。"},
                "examiner": {"actual_difficulty": "mid", "difficulty_reason": "需转化条件。",
                             "analysis_check": "分母覆盖全部等可能结果，分子计数正确。",
                             "necessity_claims": [], "necessity_checks": [], "verdict": "PASS",
                             "difficulty_ok": True, "kaodian_ok": True, "style_ok": True,
                             "analysis_ok": True, "brief_ok": True},
            }],
        }

    def check(self):
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.directory / "questions.json").write_text(json.dumps([self.question]), encoding="utf-8")
        # Recompute hashes deliberately: semantic checks must survive re-signing.
        self.evidence["questions_sha256"] = digest(self.directory / "questions.json")
        validate_batch_constraints(self.manifest, [self.question])
        validate_lite_review(self.directory, self.evidence, [self.question["external_id"]])

    def test_auto_records_examiner_level_without_forcing_role_agreement(self):
        self.check()
        self.question["difficulty"] = 2
        with self.assertRaisesRegex(ValueError, "实际难度与考官评级不一致"):
            self.check()

    def test_auto_keeps_required_reasoning_and_content_checks(self):
        original = copy.deepcopy(self.evidence)
        for role, field, value in (("blind", "actual_difficulty", None),
                                   ("blind", "difficulty_reason", ""),
                                   ("blind", "answer", "B"),
                                   ("blind", "also_valid", ["B"]),
                                   ("examiner", "analysis_check", ""),
                                   ("examiner", "analysis_ok", False)):
            self.evidence = copy.deepcopy(original)
            self.evidence["results"][0][role][field] = value
            with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                self.check()

    def test_explicit_tier_remains_strict(self):
        self.manifest["generation"]["batch_constraints"]["slot_plan"][0]["difficulty"] = "mid"
        with self.assertRaisesRegex(ValueError, "盲解官实际评定为 easy.*直接计数"):
            self.check()

    def test_auto_cannot_use_other_modules_or_legacy_review(self):
        self.question["category"] = "判断推理"
        with self.assertRaisesRegex(ValueError, "仅适用于数量关系"):
            self.check()
        self.question["category"] = "数量关系"
        for version in (1, 2):
            self.evidence["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "须使用新版"):
                self.check()

    def test_historical_missing_tier_still_means_mid(self):
        self.manifest.pop("difficulty_tier")
        self.manifest["generation"]["batch_constraints"]["slot_plan"][0].pop("difficulty")
        for version in (2, 3):
            self.evidence["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "不匹配声明档位 mid"):
                self.check()
        self.evidence["results"][0]["blind"]["actual_difficulty"] = "mid"
        self.check()

    def test_quantity_hard_policy_keeps_truthful_difficulty_and_rejects_easy(self):
        self.manifest['difficulty_tier'] = 'hard'
        self.manifest['generation']['batch_constraints']['slot_plan'][0]['difficulty'] = 'hard'
        self.manifest['generation']['quantity_hard_policy'] = QUANTITY_HARD_POLICY
        self.evidence['quantity_hard_policy'] = QUANTITY_HARD_POLICY
        item = self.evidence['results'][0]
        for blind, examiner in (('mid', 'hard'), ('hard', 'mid'), ('mid', 'mid'), ('hard', 'hard')):
            item['blind']['actual_difficulty'] = blind
            item['examiner']['actual_difficulty'] = examiner
            self.question['difficulty'] = 4 if blind == examiner == 'hard' else 3
            with self.subTest(blind=blind, examiner=examiner):
                self.check()
        self.question['difficulty'] = 4
        item['blind']['actual_difficulty'] = 'mid'
        with self.assertRaisesRegex(ValueError, '较低评级'):
            self.check()
        self.question['difficulty'] = 3
        for role in ('blind', 'examiner'):
            original = copy.deepcopy(item[role])
            for field, value in (('actual_difficulty', 'easy'), ('actual_difficulty', None),
                                 ('difficulty_reason', '')):
                item[role] = {**original, field: value}
                with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                    self.check()
            item[role] = original
        item['examiner']['analysis_ok'] = False
        with self.assertRaisesRegex(ValueError, '检查字段'):
            self.check()

    def test_policy_cannot_relax_easy_mid_legacy_or_other_modules(self):
        item = self.evidence['results'][0]
        self.manifest['generation']['quantity_hard_policy'] = QUANTITY_HARD_POLICY
        self.evidence['quantity_hard_policy'] = QUANTITY_HARD_POLICY
        slot = self.manifest['generation']['batch_constraints']['slot_plan'][0]
        for tier, actual in (('easy', 'mid'), ('mid', 'easy')):
            slot['difficulty'] = tier
            self.question['difficulty'] = {'easy': 2, 'mid': 3}[tier]
            for role in ('blind', 'examiner'):
                item['blind']['actual_difficulty'] = tier
                item['examiner']['actual_difficulty'] = tier
                item[role]['actual_difficulty'] = actual
                with self.subTest(tier=tier, role=role), self.assertRaisesRegex(ValueError, '不匹配声明档位'):
                    self.check()
        slot['difficulty'] = 'hard'
        self.question['difficulty'] = 4
        item['blind']['actual_difficulty'] = 'mid'
        item['examiner']['actual_difficulty'] = 'hard'
        self.question['category'] = '判断推理'
        with self.assertRaisesRegex(ValueError, '不匹配声明档位 hard'):
            self.check()
        self.question['category'] = '数量关系'
        self.evidence.pop('quantity_hard_policy')
        with self.assertRaisesRegex(ValueError, '策略与复核记录不一致'):
            self.check()
        self.manifest['generation'].pop('quantity_hard_policy')
        with self.assertRaisesRegex(ValueError, '不匹配声明档位 hard'):
            self.check()

    def test_generated_hard_mid_disagreement_survives_sign_and_import_gate(self):
        run = {'module': '数量关系', 'batch_id': 'b', 'difficulty': 'hard',
               'planned_count': 1, 'slots': [{'tag': TAG, 'count': 1, 'difficulty': 'hard'}]}
        fake = FakeModel([[question(1)]], {'b_01': blind_ok(tier='mid')}, {'b_01': examiner_ok()})
        with patch.object(quiz_lite, 'call', fake):
            questions, results, log = quiz_lite.build_batch(run, 1, 'test')
        self.assertEqual(questions[0]['difficulty'], 3)
        self.assertEqual(len(log), 1)
        quiz_lite.write_batch(run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, run, results, log)
        self.assertTrue(verify(self.directory)['ok'])


if __name__ == "__main__":
    unittest.main()

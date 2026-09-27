import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import quiz_lite
import quiz_verbal
from generation_gate import HARD_POLICY, VERBAL_PRACTICE_POLICY, QUANTITY_HARD_POLICY, verify, lite_necessity_claims, lite_reasoning_issues, lite_allowed_tiers
from test_quiz_lite import blind_ok, examiner_ok

TAG = '言语理解与表达-片段阅读-中心理解题'
RAW = {'index': 1, 'stem': '城市公共空间的价值不仅在于设施数量，还在于居民能否便利地使用。因此，规划既要考虑布局，也要关注开放时间和使用门槛。这段文字主要强调：',
       'options': [{'key': k, 'text': text} for k, text in zip('ABCD', ['公共空间规划应关注实际可达性', '增加设施数量即可改善服务', '开放时间决定城市规划布局', '公共空间的规模应不断扩大'])],
       'answer': 'A', 'kaodian_signal': '归纳文段重点',
       'analysis': '文段指出公共空间价值取决于实际使用，布局、开放时间和门槛都是可达性的方面。A概括核心，B忽略使用条件，C倒置关系，D偏离重点。'}


class VerbalReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.run = {'module': '言语理解与表达', 'batch_id': 'v', 'planned_count': 1,
                    'difficulty': 'hard', 'slots': [{'tag': TAG, 'count': 1, 'difficulty': 'hard'}],
                    'kaofa_canon': {TAG: '只考文段中心理解，不限定题面及解法。'}}

    def model(self, blind, examiner):
        def call(system, prompt, temperature, timeout, *, schema=None):
            if system == quiz_lite.WRITER_SYSTEM:
                return {'questions': [copy.deepcopy(RAW)]}
            if system == quiz_verbal.BLIND:
                self.assertNotIn('"answer"', prompt)
                self.assertNotIn('"analysis"', prompt)
                return {'questions': [dict(blind, id='v_01')]}
            if system == quiz_verbal.USAGE:
                self.assertEqual(set(schema["required"]), set(json.loads(prompt)))
                payload = json.loads(prompt)
                return {key: 'PASS 测试逐句核查' for key in payload}
            self.assertEqual(system, quiz_verbal.EXAMINER)
            self.assertNotIn('"blind_work"', prompt)
            payload = json.loads(prompt.split('\n', 1)[1])
            checks = [dict(claim_index=i, valid=True, reason='测试原句核查') for i in range(len(payload['items'][0]['necessity_claims']))]
            return {'questions': [dict(examiner, id='v_01', necessity_checks=checks)]}
        return call

    def test_training_accepts_difficulty_variation_and_records_actual_rating(self):
        # Mock ratings exercise plumbing; live acceptance separately checks actual content difficulty.
        for b, e in [('easy', 'mid'), ('hard', 'easy'), ('mid', 'hard'), ('hard', 'mid'), ('mid', 'mid'), ('hard', 'hard')]:
            with self.subTest(blind=b, examiner=e), patch.object(quiz_lite, 'call', self.model(blind_ok(tier=b), examiner_ok(e))):
                questions, results, log = quiz_lite.build_batch(self.run, 1, 'test')
            self.assertEqual(questions[0]['difficulty'], min(quiz_lite.TIER_TO_LEVEL[t] for t in (b, e)))
            quiz_lite.write_batch(self.run, self.directory, questions, 'test')
            quiz_lite.sign(self.directory, self.run, results, log)
            self.assertTrue(verify(self.directory)['ok'])
            manifest = json.loads((self.directory / 'manifest.json').read_text())
            self.assertEqual(manifest['generation']['verbal_difficulty_policy'], VERBAL_PRACTICE_POLICY)
            evidence = json.loads((self.directory / 'evidence/lite-review.json').read_text())
            self.assertEqual(evidence['usage_model'], 'gemini-3.8-flash-high')
            self.assertEqual(evidence['model'], evidence['usage_model'])

    def test_relaxed_difficulty_keeps_scope_answer_uniqueness_and_reasoning_checks(self):
        question = quiz_lite.stamp(self.run, RAW, 0, self.run['slots'][0], 'test')
        cases = [(blind_ok('B'), examiner_ok()), ({**blind_ok(), 'also_valid': ['B']}, examiner_ok()),
                 (blind_ok(), {**examiner_ok(), 'kaodian_ok': False}),
                 (blind_ok(), {**examiner_ok(), 'analysis_ok': False}),
                 (blind_ok(), {**examiner_ok(), 'difficulty_reason': ''})]
        for blind, examiner in cases:
            with self.subTest(blind=blind, examiner=examiner), patch.object(quiz_lite, 'call', self.model(blind, examiner)):
                result = quiz_lite.review(self.run, [question], self.run['slots'])['v_01']
                self.assertEqual(result['verdict'], 'REJECT')
        self.run['slots'][0]['difficulty'] = 'mid'
        with patch.object(quiz_lite, 'call', self.model(blind_ok(tier='easy'), examiner_ok('mid'))):
            self.assertEqual(quiz_lite.review(self.run, [question], self.run['slots'])['v_01']['verdict'], 'PASS')

    def test_auto_defaults_and_relaxation_stay_verbal_only(self):
        self.assertEqual(quiz_lite.tier_of({'module': '言语理解与表达'}, {}), 'auto')
        self.run['difficulty'] = 'auto'
        self.run['slots'][0]['difficulty'] = 'auto'
        with patch.object(quiz_lite, 'call', side_effect=self.model(blind_ok(tier='easy'), examiner_ok('mid'))) as model:
            questions, results, log = quiz_lite.build_batch(self.run, 1, 'test')
        self.assertEqual(model.call_count, 3, 'ordinary explanation needs only writer, blind and examiner')
        self.assertEqual(questions[0]['difficulty'], 2)
        quiz_lite.write_batch(self.run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, self.run, results, log)
        self.assertTrue(verify(self.directory)['ok'])
        self.assertEqual(lite_allowed_tiers('hard', '数量关系', QUANTITY_HARD_POLICY), ('mid', 'hard'))
        self.assertEqual(lite_allowed_tiers('mid', '数量关系', QUANTITY_HARD_POLICY), ('mid',))
        self.assertEqual(lite_allowed_tiers('hard', '判断推理', VERBAL_PRACTICE_POLICY), ('hard',))
        for requested in ('easy', 'mid', 'hard'):
            self.assertEqual(lite_allowed_tiers(requested, '言语理解与表达', VERBAL_PRACTICE_POLICY), ('easy', 'mid', 'hard'))

    def test_old_verbal_evidence_remains_strict_and_actual_rating_cannot_be_inflated(self):
        with patch.object(quiz_lite, 'call', self.model(blind_ok(tier='mid'), examiner_ok('hard'))):
            questions, results, log = quiz_lite.build_batch(self.run, 1, 'test')
        questions[0]['difficulty'] = 4
        quiz_lite.write_batch(self.run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, self.run, results, log)
        with self.assertRaisesRegex(ValueError, '较低评级'):
            verify(self.directory)
        for filename in ['manifest.json', 'evidence/lite-review.json']:
            path = self.directory / filename
            data = json.loads(path.read_text())
            (data['generation'] if filename == 'manifest.json' else data).pop('verbal_difficulty_policy')
            if filename != 'manifest.json':
                data['version'] = 5
            path.write_text(json.dumps(data))
        from generation_gate import digest, validate_lite_review
        evidence = json.loads((self.directory / 'evidence/lite-review.json').read_text())
        evidence['questions_sha256'] = digest(self.directory / 'questions.json')
        with self.assertRaisesRegex(ValueError, '不匹配声明档位 hard'):
            validate_lite_review(self.directory, evidence, ['v_01'])
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        manifest['generation']['hard_difficulty_policy'] = HARD_POLICY
        (self.directory / 'manifest.json').write_text(json.dumps(manifest))
        evidence['hard_difficulty_policy'] = HARD_POLICY
        with self.assertRaisesRegex(ValueError, '较低评级'):
            validate_lite_review(self.directory, evidence, ['v_01'])

    def test_grouping_keeps_global_slots_and_rejects_foreign_indices(self):
        self.run['planned_count'] = 4
        self.run['slots'][0]['count'] = 4
        stems = ['文物保护应兼顾公众使用，修缮方案要考虑居民出行与游客参观的不同需求。这段文字主要强调什么？',
                 '江河治理需要跨区域协同，上游的污染治理与下游的生态修复不能各自推进。作者意在说明什么？',
                 '科学假说必须接受实践检验，能够解释已有现象还不足以证明它适用于未知条件。文段的中心是什么？',
                 '社区议事重在表达不同诉求，公开讨论应给持不同观点的居民充分说明理由的机会。主旨最恰当的是？']
        calls = []
        def model(system, prompt, temperature, timeout, *, schema=None):
            if system == quiz_lite.WRITER_SYSTEM:
                items = json.loads(prompt.splitlines()[1])['items']
                indices = [item['index'] for item in items]
                calls.append(indices)
                rows = [dict(copy.deepcopy(RAW), index=i, stem=stems[i - 1]) for i in indices]
                if indices == [1, 2]:
                    rows += [dict(copy.deepcopy(RAW), index=2), dict(copy.deepcopy(RAW), index=4)]
                return {'questions': rows}
            if system == quiz_verbal.USAGE:
                return {key: 'PASS 测试逐句核查' for key in json.loads(prompt)}
            payload = json.loads(prompt.split('\n', 1)[1])
            if system == quiz_verbal.BLIND:
                self.assertLessEqual(len(payload['questions']), 3)
                return {'questions': [dict(blind_ok(tier='mid'), id=q['id']) for q in payload['questions']]}
            return {'questions': [dict(examiner_ok('mid'), id=i['question']['id'], necessity_checks=[dict(claim_index=j,valid=True,reason='测试原句核查') for j in range(len(i['necessity_claims']))]) for i in payload['items']]}
        with patch.object(quiz_lite, 'call', model):
            questions, _, log = quiz_lite.build_batch(self.run, 2, 'test')
        self.assertEqual(calls, [[1, 2], [3, 4], [2]])
        self.assertEqual([q['stem'] for q in questions], stems)
        self.assertEqual([q['difficulty'] for q in questions], [3] * 4)
        self.assertEqual(log[1]['asked'], [2])

    def test_verbal_usage_claims_require_each_check_and_preserve_legacy(self):
        q = {'category': '言语理解与表达', 'analysis': '梳理与权责边界搭配不当。此词不能用于抽象对象。A更贴切。'}
        self.assertEqual(lite_necessity_claims(q), [])
        claims = lite_necessity_claims(q, verbal=True)
        self.assertEqual(len(claims), 2)
        self.assertIn('必要性断言核验未覆盖全部原句', lite_reasoning_issues(blind_ok(), examiner_ok(), 'hard', claims))
        examiner = examiner_ok()
        examiner['necessity_checks'] = [{'claim_index': i, 'valid': i != 0, 'reason': '存在自然反例' if i == 0 else '对象冲突'} for i in range(2)]
        self.assertTrue(any('必要性断言不成立' in issue for issue in lite_reasoning_issues(blind_ok(), examiner, 'hard', claims)))

    def test_new_usage_review_is_targeted_without_changing_legacy_full_review(self):
        question = {'category': '言语理解与表达', 'analysis':
                    'A概括了文段重点。B只能用于具体对象。C为中性词，不能出现在批评语境。D仅重复背景。'}
        targeted = lite_necessity_claims(question, verbal=True, usage_v2=True)
        self.assertEqual(targeted, ['B只能用于具体对象', 'C为中性词，不能出现在批评语境'])
        self.assertEqual(len(lite_necessity_claims(question, verbal=True, usage_v2=True, verbal_all=True)), 4)
        ordinary = {**question, 'analysis': RAW['analysis']}
        self.assertEqual(lite_necessity_claims(ordinary, verbal=True, usage_v2=True), [])

    def test_training_policy_requires_matching_manifest_and_verbal_category(self):
        with patch.object(quiz_lite, 'call', self.model(blind_ok(tier='easy'), examiner_ok('mid'))):
            questions, results, log = quiz_lite.build_batch(self.run, 1, 'test')
        quiz_lite.write_batch(self.run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, self.run, results, log)
        from generation_gate import digest, validate_lite_review
        evidence = json.loads((self.directory / 'evidence/lite-review.json').read_text())
        mismatched = {**evidence, 'verbal_difficulty_policy': None}
        with self.assertRaisesRegex(ValueError, '策略与复核记录不一致'):
            validate_lite_review(self.directory, mismatched, ['v_01'])
        questions[0]['category'] = '数量关系'
        (self.directory / 'questions.json').write_text(json.dumps(questions))
        evidence['questions_sha256'] = digest(self.directory / 'questions.json')
        with self.assertRaisesRegex(ValueError, '仅适用于言语'):
            validate_lite_review(self.directory, evidence, ['v_01'])

    def test_analysis_repair_preserves_solved_question_and_is_fully_reviewed(self):
        base = self.model(blind_ok(tier='mid'), examiner_ok('mid'))
        writers, usage_calls, reviews = [], [], []
        def model(system, prompt, temperature, timeout, **kwargs):
            if system == quiz_lite.WRITER_SYSTEM:
                ask = json.loads(prompt.splitlines()[1])['items'][0]
                writers.append(ask)
                return {'questions': [{**RAW, 'analysis': RAW['analysis'] + '可达性只能用于开放时间。'} if len(writers) == 1 else {
                    **RAW, 'stem': '不应替换题面', 'answer': 'B', 'analysis': RAW['analysis'] + '这是修正后的完整说明。'}]}
            if system == quiz_verbal.USAGE:
                usage_calls.append(prompt)
                return {key: 'REJECT 解析理由错误'
                        for key in json.loads(prompt)}
            if system == quiz_verbal.EXAMINER:
                reviews.append(prompt)
            return base(system, prompt, temperature, timeout, **kwargs)
        with patch.object(quiz_lite, 'call', model):
            questions, results, log = quiz_lite.build_batch(self.run, 2, 'test')
        self.assertEqual(writers[1]['repair'], 'analysis_only')
        self.assertEqual(questions[0]['stem'], RAW['stem'])
        self.assertEqual(questions[0]['answer'], RAW['answer'])
        self.assertIn('修正后的完整说明', questions[0]['analysis'])
        self.assertEqual(len(usage_calls), 1)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(results['v_01']['verdict'], 'PASS')

    def test_signed_verbal_receipt_requires_independent_usage_checks(self):
        raw = {**RAW, 'analysis': RAW['analysis'] + 'B只能表达设施规模。'}
        exam = examiner_ok('mid')
        exam['necessity_checks'] = [{'claim_index': 0, 'valid': True, 'reason': '核对选项语义'}]
        base = self.model(blind_ok(tier='mid'), exam)
        def model(system, prompt, temperature, timeout, *, schema=None):
            if system == quiz_lite.WRITER_SYSTEM:
                return {'questions': [raw]}
            if system == quiz_verbal.USAGE:
                self.assertNotIn('"answer"', prompt)
                return {key: 'PASS 核对原句范围' for key in json.loads(prompt)}
            return base(system, prompt, temperature, timeout)
        with patch.object(quiz_lite, 'call', model):
            questions, results, log = quiz_lite.build_batch(self.run, 1, 'test')
        quiz_lite.write_batch(self.run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, self.run, results, log)
        self.assertTrue(verify(self.directory)['ok'])
        results['v_01']['examiner']['usage_checks'] = []
        quiz_lite.sign(self.directory, self.run, results, log)
        with self.assertRaisesRegex(ValueError, '未覆盖全部原句'):
            verify(self.directory)


if __name__ == '__main__':
    unittest.main()

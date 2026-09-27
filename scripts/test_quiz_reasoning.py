import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import quiz_lite
import quiz_reasoning
from generation_gate import REASONING_PRACTICE_POLICY, digest, lite_necessity_claims, validate_lite_review, verify
from test_quiz_lite import blind_ok, examiner_ok

TAG = '判断推理-逻辑判断-翻译推理'
RAW = {'index': 1, 'stem': '某培训中心规定，只有通过考核，才能取得证书。小陈未通过考核。根据以上信息，以下哪项必然成立？',
       'options': [dict(key=k, text=t) for k, t in zip('ABCD', [
           '小陈不能取得证书', '通过考核的人都能取得证书', '未取得证书的人都未通过考核', '小陈没有参加培训'])],
       'answer': 'A', 'kaodian_signal': '必要条件与逆否推理',
       'analysis': '取得证书以通过考核为必要条件。小陈未通过考核，因此不能取得证书，选A。B将必要条件误当充分条件，C否定前件，D未提及。'}


class ReasoningReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.run = dict(module='判断推理', batch_id='r', planned_count=1, difficulty='hard',
                        slots=[dict(tag=TAG, count=1, difficulty='hard')],
                        kaofa_canon={TAG: '考查条件翻译、推理与选项辨析，不限步骤。'})

    def model(self, blind, examiner):
        def call(system, prompt, temperature, timeout, *, schema=None):
            if system == quiz_lite.WRITER_SYSTEM:
                return {'questions': [copy.deepcopy(RAW)]}
            if system == quiz_reasoning.BLIND:
                for field in ('"answer"', '"analysis"', '"declared_difficulty"'):
                    self.assertNotIn(field, prompt)
                return {'questions': [dict(blind, id='r_01')]}
            if system == quiz_reasoning.CLAIMS:
                self.assertNotIn('"answer"', prompt)
                self.assertEqual(set(schema['required']), set(json.loads(prompt)))
                return {k: 'PASS 题干与选项支持该句' for k in json.loads(prompt)}
            self.assertEqual(system, quiz_reasoning.EXAMINER)
            self.assertNotIn('"blind_work"', prompt)
            items = json.loads(prompt.split('\n', 1)[1])['items']
            checks = [dict(claim_index=i, valid=True, reason='取得证书蕴含通过考核，逆否成立')
                      for i in range(len(items[0]['necessity_claims']))]
            return {'questions': [dict(examiner, id='r_01', necessity_checks=examiner.get('necessity_checks') or checks)]}
        return call

    def build(self, b='easy', e='mid'):
        with patch.object(quiz_lite, 'call', self.model(blind_ok(tier=b), examiner_ok(e))):
            questions, results, log = quiz_lite.build_batch(self.run, 1, 'test')
        quiz_lite.write_batch(self.run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, self.run, results, log)
        return questions, json.loads((self.directory / 'evidence/lite-review.json').read_text())

    def test_relaxed_difficulty_is_honest_signed_and_independent(self):
        for requested in ('auto', 'easy', 'mid', 'hard'):
            self.run['difficulty'] = self.run['slots'][0]['difficulty'] = requested
            for b, e in [('easy', 'mid'), ('hard', 'easy'), ('mid', 'hard')]:
                with self.subTest(requested=requested, b=b, e=e):
                    questions, evidence = self.build(b, e)
                    self.assertEqual(questions[0]['difficulty'], min(quiz_lite.TIER_TO_LEVEL[t] for t in (b, e)))
                    self.assertEqual(evidence['version'], 9)
                    self.assertEqual(evidence['reasoning_difficulty_policy'], REASONING_PRACTICE_POLICY)
                    self.assertTrue(verify(self.directory)['ok'])

    def test_answer_scope_ambiguity_and_false_claims_still_fail(self):
        q = quiz_lite.stamp(self.run, RAW, 0, self.run['slots'][0], 'test')
        q['analysis'] += '小陈必须参加培训。'
        cases = [(blind_ok('B'), examiner_ok()), ({**blind_ok(), 'also_valid': ['B']}, examiner_ok()),
                 ({**blind_ok(), 'unsolvable': True}, examiner_ok()),
                 (blind_ok(), {**examiner_ok(), 'kaodian_ok': False}),
                 (blind_ok(), {**examiner_ok(), 'analysis_ok': False}),
                 (blind_ok(), {**examiner_ok(), 'necessity_checks': [dict(claim_index=0, valid=False, reason='培训无依据')]} )]
        for b, e in cases:
            with self.subTest(b=b, e=e), patch.object(quiz_lite, 'call', self.model(b, e)):
                self.assertEqual(quiz_lite.review(self.run, [q], self.run['slots'])['r_01']['verdict'], 'REJECT')

    def test_evidence_cannot_inflate_difficulty_relax_old_reviews_or_escape_module(self):
        questions, evidence = self.build()
        original = copy.deepcopy(questions)
        questions[0]['difficulty'] = 4
        (self.directory / 'questions.json').write_text(json.dumps(questions))
        evidence['questions_sha256'] = digest(self.directory / 'questions.json')
        with self.assertRaisesRegex(ValueError, '较低评级'):
            validate_lite_review(self.directory, evidence, ['r_01'])
        for category, sub in [('数量关系', '数学运算'), ('判断推理', '图形推理')]:
            questions = copy.deepcopy(original)
            questions[0].update(category=category, sub_category=sub)
            (self.directory / 'questions.json').write_text(json.dumps(questions))
            evidence['questions_sha256'] = digest(self.directory / 'questions.json')
            with self.assertRaisesRegex(ValueError, '仅适用于逻辑判断'):
                validate_lite_review(self.directory, evidence, ['r_01'])
        for change in ({'version': 3}, {'reasoning_difficulty_policy': None}):
            with self.assertRaisesRegex(ValueError, '策略与复核版本不一致'):
                validate_lite_review(self.directory, {**evidence, **change}, ['r_01'])
        (self.directory / 'questions.json').write_text(json.dumps(original))
        evidence.update(version=3, questions_sha256=digest(self.directory / 'questions.json'))
        evidence.pop('reasoning_difficulty_policy')
        evidence['results'][0]['examiner']['necessity_claims'] = lite_necessity_claims(original[0])
        evidence['results'][0]['examiner']['necessity_checks'] = []
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        manifest['generation'].pop('reasoning_difficulty_policy')
        (self.directory / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, '不匹配声明档位 hard'):
            validate_lite_review(self.directory, evidence, ['r_01'])

    def test_new_review_covers_each_original_sentence_and_legacy_is_unchanged(self):
        q = dict(category='判断推理', analysis='科长D为假。等等，科长D为真。另一城市也下降，因此切断因果。')
        self.assertEqual(lite_necessity_claims(q), [])
        self.assertEqual(len(lite_necessity_claims(q, reasoning=True)), 3)
        _, evidence = self.build()
        evidence['results'][0]['examiner']['necessity_checks'].pop()
        with self.assertRaisesRegex(ValueError, '未覆盖全部原句'):
            validate_lite_review(self.directory, evidence, ['r_01'])

    def test_independent_claim_rejection_repairs_only_analysis_and_cannot_be_omitted(self):
        base = self.model(blind_ok(tier='easy'), examiner_ok('mid'))
        writers, checks = [], []
        def model(system, prompt, temperature, timeout, **kwargs):
            if system == quiz_lite.WRITER_SYSTEM:
                writers.append(json.loads(prompt.splitlines()[1])['items'][0])
                return {'questions': [dict(RAW, analysis=RAW['analysis'] + '修订后的说明。')]} if len(writers) > 1 else base(system, prompt, temperature, timeout)
            if system == quiz_reasoning.CLAIMS:
                checks.append(prompt)
                return {k: ('REJECT 测试错误理由' if len(checks) == 1 and k.startswith('c') else 'PASS 题干可推出') for k in json.loads(prompt)}
            return base(system, prompt, temperature, timeout, **kwargs)
        with patch.object(quiz_lite, 'call', model):
            questions, results, log = quiz_lite.build_batch(self.run, 2, 'test')
        self.assertEqual(writers[1]['repair'], 'analysis_only')
        self.assertEqual(questions[0]['stem'], RAW['stem'])
        self.assertEqual(len(checks), 2)
        quiz_lite.write_batch(self.run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, self.run, results, log)
        self.assertTrue(verify(self.directory)['ok'])
        evidence = json.loads((self.directory / 'evidence/lite-review.json').read_text())
        evidence['results'][0]['examiner']['usage_checks'] = []
        with self.assertRaisesRegex(ValueError, '未覆盖全部原句'):
            validate_lite_review(self.directory, evidence, ['r_01'])

    def test_independent_question_check_cannot_be_omitted_or_repaired_as_analysis(self):
        base = self.model(blind_ok(), examiner_ok())
        writers = []
        def model(system, prompt, temperature, timeout, **kwargs):
            if system == quiz_lite.WRITER_SYSTEM:
                writers.append(json.loads(prompt.splitlines()[1])['items'][0])
            if system == quiz_reasoning.CLAIMS:
                return {k: ('REJECT 两项同构' if k.startswith('q') and len(writers) == 1 else 'PASS 原文支持')
                        for k in json.loads(prompt)}
            return base(system, prompt, temperature, timeout, **kwargs)
        with patch.object(quiz_lite, 'call', model):
            questions, results, log = quiz_lite.build_batch(self.run, 2, 'test')
        self.assertNotIn('repair', writers[1], 'Ambiguous question needs a rewrite, not just new explanation')
        quiz_lite.write_batch(self.run, self.directory, questions, 'test')
        quiz_lite.sign(self.directory, self.run, results, log)
        evidence = json.loads((self.directory / 'evidence/lite-review.json').read_text())
        evidence['results'][0]['examiner'].pop('question_check')
        with self.assertRaisesRegex(ValueError, '独立题面核查缺失'):
            validate_lite_review(self.directory, evidence, ['r_01'])

    def test_structured_writer_uses_native_tool_and_fails_closed(self):
        for rows, valid in [([RAW], True), ('not an array', False), (['not an object'], False)]:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({'choices': [{
                'finish_reason': 'tool_calls', 'message': {'content': 'ignored', 'tool_calls': [{
                    'function': {'name': 'submit_questions', 'arguments': json.dumps({'questions': rows})},
                }]},
            }]}).encode()
            with self.subTest(rows=rows), patch.object(quiz_lite, 'api_key', return_value='test'), \
                    patch.object(quiz_lite.urllib.request, 'urlopen', return_value=response) as request:
                if valid:
                    self.assertEqual(quiz_lite.call('system', 'prompt', 0, 1, schema=quiz_reasoning.WRITER_SCHEMA), {'questions': rows})
                else:
                    with self.assertRaisesRegex(RuntimeError, '无法解析.*未自动重试'):
                        quiz_lite.call('system', 'prompt', 0, 1, schema=quiz_reasoning.WRITER_SCHEMA)
                request.assert_called_once()
                body = json.loads(request.call_args.args[0].data)
                self.assertEqual(body['tool_choice']['function']['name'], 'submit_questions')
                self.assertEqual(body['model'], 'gemini-3.8-flash-high')

    def test_writer_accepts_only_complete_json_when_provider_uses_content(self):
        for content, valid in [(json.dumps({'questions': [RAW]}), True),
                               (json.dumps({'questions': [RAW]}) + '附言', False)]:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({'choices': [{
                'finish_reason': 'stop', 'message': {'content': content},
            }]}).encode()
            with self.subTest(valid=valid), patch.object(quiz_lite, 'api_key', return_value='test'), \
                    patch.object(quiz_lite.urllib.request, 'urlopen', return_value=response) as request:
                if valid:
                    self.assertEqual(quiz_lite.call('system', 'prompt', 0, 1, schema=quiz_reasoning.WRITER_SCHEMA), {'questions': [RAW]})
                else:
                    with self.assertRaisesRegex(RuntimeError, '无法解析.*未自动重试'):
                        quiz_lite.call('system', 'prompt', 0, 1, schema=quiz_reasoning.WRITER_SCHEMA)
                request.assert_called_once()


if __name__ == '__main__':
    unittest.main()

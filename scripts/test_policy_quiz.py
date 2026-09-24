import copy
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generation_gate
import policy_quiz
import policy_sources as sources
import quiz_lite
from mastery_assessment import assess

TAG = '政治理论-时事政治-重要文件'
TEXT = '提升领导干部和公务员把握新质生产力培育和发展方向、应对人工智能带来的深刻变革的能力。'
PARAGRAPH_ID = 'p-' + sources.sha(TEXT)[:16]


def pack():
    return {'as_of': sources.today().isoformat(), 'sources': [{'id': 'official', 'url': 'https://www.gd.gov.cn/a.html',
        'title': '测试文件', 'kind': 'policy', 'scope': 'as_published', 'published_at': '2026-09-01',
        'tags': [TAG], 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'sha256': sources.sha(TEXT),
        'paragraphs': [{'id': PARAGRAPH_ID, 'text': TEXT}]}]}


def checks(kind, answer):
    return [{'key': key, 'valid': (answer == 'A') if kind == 'judge' else key in answer,
             'reason': '根据给定文件逐项核对主体和适用范围',
             'citations': [{'source_id': 'official', 'paragraph_id': PARAGRAPH_ID, 'quote': TEXT}]} for key in
            (['statement'] if kind == 'judge' else ['A', 'B', 'C', 'D'])]


class PolicyWorkflow(unittest.TestCase):
    def test_default_mix_keeps_short_drills_useful(self):
        self.assertEqual(policy_quiz.default_question_types(1), ['single'])
        self.assertEqual(policy_quiz.default_question_types(5), ['judge'] * 2 + ['single'] * 2 + ['multi'])
        self.assertEqual(policy_quiz.default_question_types(10), ['judge'] * 4 + ['single'] * 4 + ['multi'] * 2)

    def test_three_types_verify_and_tamper_fails(self):
        run = {'module': '政治理论', 'batch_id': 'policy-test', 'planned_count': 3, 'source_pack': pack(),
               'slots': [{'tag': TAG, 'count': 1, 'question_type': kind} for kind in ('judge', 'single', 'multi')]}
        qs = [quiz_lite.stamp(run, {'stem': '根据文件，下列关于科学素质提升行动的说法是否正确？',
                'options': [{'key': key, 'text': '不同选项内容' + key} for key in 'ABCD'],
                'answer': answer, 'analysis': '根据文件原文，核对主体、范围、条件，每一项均能明确判断，不能用文件没有提及推断事实错误。'},
                i, slot, '测试') for i, (slot, answer) in enumerate(zip(run['slots'], ('B', 'C', 'ACD')))]
        payloads = {}
        def fake(system, prompt, temperature, timeout):
            payloads[system] = json.loads(prompt)
            result = []
            for q in qs:
                row = {'id': q['external_id'], 'checks': checks(q['question_type'], q['answer'])}
                if system == policy_quiz.BLIND:
                    row.update(answer=q['answer'], steps='先看题型和设问，再独立逐项核对完整原文', unsolvable=False, also_valid=[])
                else:
                    row.update(verdict='PASS', difficulty_ok=True, kaodian_ok=True, style_ok=True, analysis_ok=True, brief_ok=True, source_ok=True, issues=[])
                result.append(row)
            return {'questions': result}
        with patch.object(quiz_lite, 'call', side_effect=fake):
            results = quiz_lite.review(run, qs, run['slots'])
        self.assertTrue(all(r['verdict'] == 'PASS' for r in results.values()), results)
        self.assertNotIn('answer', payloads[policy_quiz.BLIND]['questions'][0])
        self.assertNotIn('analysis', payloads[policy_quiz.BLIND]['questions'][0])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quiz_lite.write_batch(run, root, qs, '测试')
            quiz_lite.sign(root, run, results, [])
            self.assertTrue(generation_gate.verify(root)['ok'])
            with (root / 'sources.json').open('a') as f:
                f.write(' ')
            with self.assertRaisesRegex(ValueError, '快照'):
                generation_gate.verify(root)

    def test_citations_must_exist_and_cover_every_option(self):
        q = {'question_type': 'multi', 'answer': 'AC'}
        valid = checks('multi', 'AC')
        self.assertEqual(sources.citation_issues(valid, pack(), q), [])
        for mutate in ('missing', 'invented_quote', 'invented_id', 'answer'):
            data = copy.deepcopy(valid)
            if mutate == 'missing': data.pop()
            elif mutate == 'invented_quote': data[0]['citations'][0]['quote'] = '根本不存在的捏造的政策原文表述'
            elif mutate == 'invented_id': data[0]['citations'][0]['source_id'] = 'invented'
            else: data[0]['valid'] = False
            self.assertTrue(sources.citation_issues(data, pack(), q), mutate)

    def test_stale_sources_fail_closed_and_future_sources_excluded(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, EXAM_POLICY_DIR=tmp):
            source = pack()['sources'][0]
            spec = {k: v for k, v in source.items() if k not in {'paragraphs', 'checked_at', 'sha256'}}
            source['checked_at'] = '2026-01-01T00:00:00+00:00'
            sources.atomic_json(Path(tmp) / 'official.json', source)
            with patch.object(sources, 'registry', return_value={'official': spec}), patch.object(sources, 'refresh', side_effect=OSError('network down')):
                with self.assertRaisesRegex(OSError, 'network down'):
                    sources.source_pack([{'tag': TAG}])
            spec['published_at'] = '2030-01-01'
            with patch.object(sources, 'registry', return_value={'official': spec}):
                with self.assertRaisesRegex(ValueError, '缺少'):
                    sources.source_pack([{'tag': TAG}])

    def test_source_changes_only_flag_affected_claims(self):
        evidence = sources.evidence_for({'question_type': 'judge'}, checks('judge', 'A'), pack())
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, EXAM_POLICY_DIR=tmp), patch.object(sources, 'registry', return_value={}):
            current = copy.deepcopy(pack()['sources'][0])
            current['sha256'] = 'changed'
            sources.atomic_json(Path(tmp) / 'official.json', current)
            self.assertEqual(sources.evidence_status(evidence)['outdated'], [])
            current['paragraphs'][0]['text'] = '被修订的原文'
            sources.atomic_json(Path(tmp) / 'official.json', current)
            self.assertEqual(sources.evidence_status(evidence)['outdated'], ['official'])

    def test_only_authoritative_https_public_hosts(self):
        for bad in ('http://www.gov.cn/x', 'https://www.gov.cn.attacker.com/x', 'https://127.0.0.1/x', 'https://a:password@www.gov.cn/x'):
            with self.assertRaises(ValueError): sources.trusted_url(bad)
        sources.trusted_url('https://www.gd.gov.cn/x')

    def test_pack_dates_integrity_and_malformed_citations(self):
        sources.validate_pack(pack())
        for field, value in [('published_at', '2099-01-01'), ('sha256', 'fake'),
                             ('checked_at', '2099-01-01T00:00:00+00:00'), ('expires_at', '2020-01-01')]:
            altered = pack()
            altered['sources'][0][field] = value
            with self.assertRaises(ValueError, msg=field):
                sources.validate_pack(altered)
        for malformed in ([None], [{'key': []}], [{'key': 'statement', 'valid': True, 'reason': '依据',
                'citations': [{'source_id': [], 'quote': TEXT}]}]):
            self.assertTrue(sources.citation_issues(malformed, pack(), {'question_type': 'judge', 'answer': 'A'}))

    @unittest.skipUnless(os.environ.get('POLICY_LIVE_REVIEW') == '1', 'opt-in live model semantic regression')
    def test_weakened_threshold_is_not_a_false_option(self):
        text = '到2030年，公民具备科学素质的比例超过25%，科普服务能力持续提升。'
        source = pack()['sources'][0]
        source.update(sha256=sources.sha(text), paragraphs=[{'id': 'p-' + sources.sha(text)[:16], 'text': text}])
        run = {'module': '政治理论', 'batch_id': 'threshold-regression', 'planned_count': 1,
               'source_pack': {'as_of': sources.today().isoformat(), 'sources': [source]},
               'slots': [{'tag': TAG, 'count': 1, 'question_type': 'single', 'difficulty': 'easy'}]}
        q = quiz_lite.stamp(run, {'stem': '根据测试文件，下列关于2030年科学素质目标的说法，正确的是（ ）。',
            'options': [{'key': key, 'text': value} for key, value in zip('ABCD', [
                '公民具备科学素质的比例超过20%', '公民具备科学素质的比例超过25%',
                '公民具备科学素质的比例不超过10%', '科普服务能力不再提升'])],
            'answer': 'B', 'analysis': 'A项将25%改成20%，与原文不同，错误；B项符合原文，正确；C项与超过25%矛盾；D项与持续提升矛盾。'},
            0, run['slots'][0], '测试')
        result = quiz_lite.review(run, [q], run['slots'])[q['external_id']]
        self.assertEqual(result['verdict'], 'REJECT', result)

    def test_claim_repetition_and_question_type_dont_inflate_mastery(self):
        events = []
        for i in range(6):
            review = dict(independence='independent', process='correct', basis='explanation', execution='smooth',
                          reason='能独立解释原文主体与限制条件', template=f'variation-{i}', variant=True, mixed=True)
            events.append(dict(id=i, question_id=i, session_id=i, evidence_type='practice', is_correct=True,
                answered_at=f'2026-09-{10+i//3:02} 00:00:00', assessment_json=json.dumps(review), claim_ids=['same-clause'], question_type='judge'))
        now = dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc)
        result = assess(events, now)
        self.assertEqual(result['independent_samples'], 2)
        self.assertEqual(result['by_question_type']['judge']['samples'], 6)
        unique = [{**e, 'claim_ids': [f'clause-{i}']} for i,e in enumerate(events)]
        self.assertNotIn(assess(unique, now)['level'], {'mastered', 'stable'})
        unique[-1]['question_type'] = 'single'
        self.assertEqual(assess(unique, now)['level'], 'mastered')
        unique[-1]['source_outdated'] = True
        self.assertTrue(assess(unique, now)['source_update_due'])


if __name__ == '__main__':
    unittest.main()

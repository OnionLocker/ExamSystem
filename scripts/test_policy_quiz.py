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
             'source_relation': 'entailed' if ((answer == 'A') if kind == 'judge' else key in answer) else 'contradicted',
             'subject_comparison': '选项与原文均讨论同一群体的职责',
             'premise_comparison': '选项与原文适用相同时间和条件',
             'strength_comparison': '逐项对照原文的规定与选项断言，没有添加优先序或排他结论',
             'reason': '根据给定文件逐项核对主体和适用范围',
             'competitive_distractor': kind == 'single' and key not in answer,
             'competition_reason': '需要核对相邻主体的适用职责边界',
             'citations': [{'source_id': 'official', 'paragraph_id': PARAGRAPH_ID, 'quote': TEXT}]} for key in
            (['statement'] if kind == 'judge' else ['A', 'B', 'C', 'D'])]


class PolicyWorkflow(unittest.TestCase):
    def test_shared_document_title_is_not_a_duplicate_question(self):
        prefix = '依据《广东省全民科学素质行动规划纲要实施方案（2026—2030年）》，在领导干部和公务员科学素质提升行动中，'
        a = {'category': '政治理论', 'question_type': 'single', 'stem': prefix + '牵头部门是？',
             'options': [{'key': k, 'text': t} for k, t in zip('ABCD', ['省委组织部', '省科技厅', '省科协', '省教育厅'])]}
        b = {'category': '政治理论', 'question_type': 'multi', 'stem': prefix + '具体要求包括？',
             'options': [{'key': k, 'text': t} for k, t in zip('ABCD', ['加强科学素质评估', '提高人工智能认知', '分级分类培训', '建立交流机制'])]}
        self.assertTrue(quiz_lite.duplicate_stem(a['stem'], [b['stem']]))
        self.assertFalse(quiz_lite.duplicate_question(a, [b]))
        self.assertFalse(quiz_lite.duplicate_question(a, [{**b, 'question_type': 'single'}]))
        self.assertTrue(quiz_lite.duplicate_question(a, [{**a, 'options': list(reversed(a['options']))}]))
        quantity = {**a, 'category': '数量关系'}
        self.assertTrue(quiz_lite.duplicate_question(quantity, [{**quantity, 'options': b['options']}]))

    def test_source_scope_and_no_extra_facts_reach_writer_and_both_reviewers(self):
        for rule in ('科技法律的义务、职责、制度定位', '不得补写给定原文未支持'):
            self.assertIn(rule, policy_quiz.STYLE)
            self.assertIn(rule, policy_quiz.BLIND)
            self.assertIn(rule, policy_quiz.EXAMINER)
        with patch.object(policy_quiz, 'references', return_value=[]):
            prompt = policy_quiz.writer_prompt({'module': '常识判断', 'source_pack': pack()}, [], [])
        self.assertIn(policy_quiz.STYLE, prompt)

    def test_default_mix_keeps_short_drills_useful(self):
        self.assertEqual(policy_quiz.default_question_types(1), ['single'])
        self.assertEqual(policy_quiz.default_question_types(5), ['judge'] * 2 + ['single'] * 2 + ['multi'])
        self.assertEqual(policy_quiz.default_question_types(10), ['judge'] * 4 + ['single'] * 4 + ['multi'] * 2)

    def test_three_types_verify_and_tamper_fails(self):
        run = {'module': '政治理论', 'batch_id': 'policy-test', 'planned_count': 3, 'source_pack': pack(),
               'slots': [{'tag': TAG, 'count': 1, 'difficulty': 'mid', 'question_type': kind} for kind in ('judge', 'single', 'multi')]}
        qs = [quiz_lite.stamp(run, {'stem': '根据文件，下列关于科学素质提升行动的说法是否正确？',
                'options': [{'key': key, 'text': '不同选项内容' + key} for key in 'ABCD'],
                'answer': answer, 'analysis': '根据文件原文，核对主体、范围、条件，每一项均能明确判断，不能用文件没有提及推断事实错误。'},
                i, slot, '测试') for i, (slot, answer) in enumerate(zip(run['slots'], ('B', 'C', 'ACD')))]
        payloads = {}
        def fake(system, prompt, temperature, timeout):
            payloads[system] = json.loads(prompt)
            result = []
            for q in qs:
                row = {'id': q['external_id'], 'checks': checks(q['question_type'], q['answer']),
                       'selection_rule': 'select_true', 'unsupported_analysis_claims': [],
                       'actual_difficulty': 'mid', 'difficulty_reason': '需辨析政策适用主体与相邻职责，两者容易混淆'}
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
        self.assertNotIn('declared_difficulty', json.dumps(payloads[policy_quiz.BLIND]))
        self.assertNotIn('batch_slots', payloads[policy_quiz.BLIND])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quiz_lite.write_batch(run, root, qs, '测试')
            quiz_lite.sign(root, run, results, [])
            self.assertTrue(generation_gate.verify(root)['ok'])
            for role in ('blind', 'examiner'):
                for defect in ({'actual_difficulty': 'easy'}, {'difficulty_reason': ''}):
                    malformed = copy.deepcopy(results)
                    malformed[qs[0]['external_id']][role].update(defect)
                    quiz_lite.sign(root, run, malformed, [])
                    with self.assertRaisesRegex(ValueError, '难度'):
                        generation_gate.verify(root)
            for role, defect in (('blind', {'selection_rule': None}),
                                 ('examiner', {'unsupported_analysis_claims': None}),
                                 ('examiner', {'unsupported_analysis_claims': ['解析新增原文未定的首要地位']})):
                malformed = copy.deepcopy(results)
                malformed[qs[0]['external_id']][role].update(defect)
                quiz_lite.sign(root, run, malformed, [])
                with self.assertRaisesRegex(ValueError, '设问方向|未证断言'):
                    generation_gate.verify(root)
            legacy_questions = copy.deepcopy(qs)
            legacy_results = copy.deepcopy(results)
            for q in legacy_questions:
                item = legacy_results[q['external_id']]
                for role in ('blind', 'examiner'):
                    item[role].pop('selection_rule')
                    item[role].pop('unsupported_analysis_claims')
                    for check in item[role]['checks']:
                        for field in ('source_relation', 'subject_comparison', 'premise_comparison', 'strength_comparison'):
                            check.pop(field)
                q['source_evidence'] = sources.evidence_for(q, item['examiner']['checks'], run['source_pack'])
            manifest = json.loads((root / 'manifest.json').read_text())
            for version in (1, 2):
                policy_quiz.validate_receipt(root, manifest, legacy_questions, legacy_results, version)
            with self.assertRaisesRegex(ValueError, '资料核验失败'):
                policy_quiz.validate_receipt(root, manifest, legacy_questions, legacy_results, 3)
            quiz_lite.sign(root, run, results, [])
            with (root / 'sources.json').open('a') as f:
                f.write(' ')
            with self.assertRaisesRegex(ValueError, '快照'):
                generation_gate.verify(root)

    def test_independent_difficulty_failures_reject_even_with_other_flags_true(self):
        run = {'module': '政治理论', 'batch_id': 'difficulty-test', 'source_pack': pack(),
               'slots': [{'tag': TAG, 'count': 1, 'difficulty': 'mid'}]}
        q = quiz_lite.stamp(run, {'stem': '根据测试文件，下列关于学习行动的说法正确的是？',
            'options': [{'key': k, 'text': '不同选项' + k} for k in 'ABCD'], 'answer': 'A',
            'analysis': '依据原文的适用主体与职责边界逐项判断，A符合条件，B混淆主体，C超出范围，D倒置条件。'},
            0, run['slots'][0], 'test')
        for role in ('blind', 'examiner'):
            for bad in ({'actual_difficulty': None}, {'actual_difficulty': []},
                        {'difficulty_reason': ''}, {'difficulty_reason': []}):
                with self.subTest(role=role, bad=bad):
                    def fake(system, prompt, temperature, timeout):
                        current = 'blind' if system == policy_quiz.BLIND else 'examiner'
                        row = {'id': q['external_id'], 'checks': checks('single', 'A'),
                               'selection_rule': 'select_true', 'unsupported_analysis_claims': [],
                               'actual_difficulty': 'mid', 'difficulty_reason': '需辨析主体与职责，B/C是竞争错项',
                               'answer': 'A', 'steps': '逐项对照原文', 'unsolvable': False, 'also_valid': [],
                               'verdict': 'PASS', 'difficulty_ok': True, 'kaodian_ok': True, 'style_ok': True,
                               'analysis_ok': True, 'brief_ok': True, 'source_ok': True, 'issues': []}
                        if current == role:
                            row.update(bad)
                        return {'questions': [row]}
                    with patch.object(quiz_lite, 'call', side_effect=fake):
                        result = quiz_lite.review(run, [copy.deepcopy(q)], run['slots'])[q['external_id']]
                    self.assertEqual(result['verdict'], 'REJECT', result)
                    self.assertTrue(any('难度' in issue for issue in result['issues']))

    def test_mid_single_needs_competing_distractors_with_evidence(self):
        row = {'actual_difficulty': 'mid', 'difficulty_reason': '需辨析概念', 'checks': checks('single', 'A')}
        self.assertEqual(policy_quiz.difficulty_issues(row, 'mid', 'blind', {'question_type':'single'}), [])
        for change in ('missing', 'one', 'correct_only'):
            data = copy.deepcopy(row)
            if change == 'missing':
                data['checks'][1].pop('competition_reason')
            else:
                for check in data['checks']:
                    check['competitive_distractor'] = check['key'] == ('B' if change == 'one' else 'A')
            self.assertTrue(policy_quiz.difficulty_issues(data, 'mid', 'blind', {'question_type':'single'}))
        easy = {'actual_difficulty': 'easy', 'difficulty_reason': '直接识记原文定义', 'checks': []}
        self.assertEqual(policy_quiz.difficulty_issues(easy, 'easy', 'blind', {'question_type':'single'}), [])
        row['checks'][0]['competition_reason'] = ''  # 正确项不是竞争错项，无需多写无意义理由。
        self.assertEqual(policy_quiz.difficulty_issues(row, 'mid', 'blind', {'question_type':'single'}), [])

    def test_semantic_defects_reject_despite_other_pass_flags(self):
        run = {'module': '政治理论', 'batch_id': 'semantic-test', 'source_pack': pack(),
               'slots': [{'tag': TAG, 'count': 1, 'difficulty': 'mid'}]}
        q = quiz_lite.stamp(run, {'stem': '根据测试文件，下列关于学习行动的说法正确的是？',
            'options': [{'key': k, 'text': '不同选项' + k} for k in 'ABCD'], 'answer': 'A',
            'analysis': '依据原文的适用主体与职责边界逐项判断，A符合条件，B混淆主体，C超出范围，D倒置条件。'},
            0, run['slots'][0], 'test')
        for role, defect in (('blind', 'undetermined'), ('examiner', 'undetermined'),
                             ('blind', 'direction'), ('examiner', 'claims'), ('examiner', 'missing_claims')):
            with self.subTest(role=role, defect=defect):
                def fake(system, prompt, temperature, timeout):
                    current = 'blind' if system == policy_quiz.BLIND else 'examiner'
                    row = {'id': q['external_id'], 'checks': checks('single', 'A'),
                           'selection_rule': 'select_true', 'unsupported_analysis_claims': [],
                           'actual_difficulty': 'mid', 'difficulty_reason': '需辨析主体与职责，B/C是竞争错项',
                           'answer': 'A', 'steps': '逐项对照原文', 'unsolvable': False, 'also_valid': [],
                           'verdict': 'PASS', 'difficulty_ok': True, 'kaodian_ok': True, 'style_ok': True,
                           'analysis_ok': True, 'brief_ok': True, 'source_ok': True, 'issues': []}
                    if current == role:
                        if defect == 'undetermined': row['checks'][1]['source_relation'] = 'undetermined'
                        elif defect == 'direction': row['selection_rule'] = 'select_false'
                        elif defect == 'claims': row['unsupported_analysis_claims'] = ['解析增加原文不支持的首要地位']
                        else: row.pop('unsupported_analysis_claims')
                    return {'questions': [row]}
                with patch.object(quiz_lite, 'call', side_effect=fake):
                    result = quiz_lite.review(run, [copy.deepcopy(q)], run['slots'])[q['external_id']]
                self.assertEqual(result['verdict'], 'REJECT', result)

    def test_citations_must_exist_and_cover_every_option(self):
        q = {'question_type': 'multi', 'answer': 'AC'}
        valid = checks('multi', 'AC')
        self.assertEqual(sources.citation_issues(valid, pack(), q, 'select_true'), [])
        for mutate in ('missing', 'invented_quote', 'invented_id', 'answer'):
            data = copy.deepcopy(valid)
            if mutate == 'missing': data.pop()
            elif mutate == 'invented_quote': data[0]['citations'][0]['quote'] = '根本不存在的捏造的政策原文表述'
            elif mutate == 'invented_id': data[0]['citations'][0]['source_id'] = 'invented'
            else: data[0]['valid'] = False
            self.assertTrue(sources.citation_issues(data, pack(), q, 'select_true'), mutate)

    def test_source_relation_is_distinct_from_selection_direction(self):
        q = {'question_type': 'single', 'answer': 'A'}
        data = checks('single', 'A')
        for c in data:
            c['source_relation'] = 'contradicted' if c['valid'] else 'entailed'
        self.assertEqual(sources.citation_issues(data, pack(), q, 'select_false'), [])
        self.assertTrue(sources.citation_issues(data, pack(), q, 'select_true'))
        self.assertTrue(sources.citation_issues(data, pack(), q))
        for relation in ('undetermined', None, [], 'false'):
            altered = copy.deepcopy(data)
            altered[1]['source_relation'] = relation
            self.assertTrue(sources.citation_issues(altered, pack(), q, 'select_false'))
        for field in ('subject_comparison', 'premise_comparison', 'strength_comparison'):
            altered = copy.deepcopy(data)
            altered[0][field] = ''
            self.assertTrue(sources.citation_issues(altered, pack(), q, 'select_false'))
        judge = checks('judge', 'B')
        jq = {'question_type': 'judge', 'answer': 'B'}
        self.assertEqual(sources.citation_issues(judge, pack(), jq, 'select_true'), [])
        judge[0]['source_relation'] = 'undetermined'
        self.assertTrue(sources.citation_issues(judge, pack(), jq, 'select_true'))
        self.assertTrue(sources.citation_issues(judge, pack(), jq, 'select_false'))

    def test_legacy_citations_do_not_claim_v3_semantics(self):
        data = checks('single', 'A')
        for c in data:
            for key in ('source_relation', 'subject_comparison', 'premise_comparison', 'strength_comparison'):
                c.pop(key)
        q = {'question_type': 'single', 'answer': 'A'}
        for version in (1, 2):
            self.assertEqual(sources.citation_issues(data, pack(), q, review_version=version), [])
        self.assertTrue(sources.citation_issues(data, pack(), q, review_version=3))

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


    def test_knowledge_first_keeps_truth_checks_and_records_lower_rating(self):
        self.assertEqual(quiz_lite.tier_of({'module': '政治理论'}, {}), 'auto')
        self.assertEqual(quiz_lite.tier_of({'module': '常识判断'}, {}), 'auto')
        for requested in ('auto', 'easy', 'mid', 'hard'):
            for actual in ('easy', 'mid', 'hard'):
                row = {'actual_difficulty': actual, 'difficulty_reason': '核对概念与条件', 'checks': []}
                self.assertEqual(policy_quiz.difficulty_issues(row, requested, 'test', {'question_type': 'single'}, training=True), [])
        run = {'module': '常识判断', 'batch_id': 'training', 'planned_count': 1,
               'source_pack': pack(), 'slots': [{'tag': TAG, 'count': 1, 'difficulty': 'hard'}]}
        raw = {'stem': '根据测试文件，下列关于科学素质教育培训的说法正确的是？',
               'options': [{'key': k, 'text': '不同选项内容' + k} for k in 'ABCD'], 'answer': 'A',
               'analysis': '依据原文，A项符合规定的对象与条件，B、C、D分别混淆适用对象、内容和实施范围。'}
        q = quiz_lite.stamp(run, raw, 0, run['slots'][0], 'test')
        def fake(system, prompt, temperature, timeout):
            row = {'id': q['external_id'], 'checks': checks('single', 'A'), 'selection_rule': 'select_true',
                   'actual_difficulty': 'easy' if system == policy_quiz.BLIND else 'mid',
                   'difficulty_reason': '原文直接对应', 'answer': 'A', 'steps': '逐项核对原文',
                   'unsolvable': False, 'also_valid': [], 'unsupported_analysis_claims': [],
                   'verdict': 'PASS', 'difficulty_ok': True, 'kaodian_ok': True, 'style_ok': True,
                   'analysis_ok': True, 'brief_ok': True, 'source_ok': True, 'issues': []}
            return {'questions': [row]}
        with patch.object(quiz_lite, 'call', fake):
            result = quiz_lite.review(run, [q], run['slots'])
        self.assertEqual(q['difficulty'], 2)
        self.assertEqual(result[q['external_id']]['verdict'], 'PASS')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quiz_lite.write_batch(run, root, [q], 'test')
            quiz_lite.sign(root, run, result, [])
            generation_gate.validate_lite_review(root, json.loads((root/'evidence/lite-review.json').read_text()), [q['external_id']])
            q['difficulty'] = 4
            quiz_lite.write_batch(run, root, [q], 'test')
            quiz_lite.sign(root, run, result, [])
            with self.assertRaisesRegex(ValueError, '较低评级'):
                generation_gate.validate_lite_review(root, json.loads((root/'evidence/lite-review.json').read_text()), [q['external_id']])

    def test_fresh_import_requires_real_update_check_but_history_survives(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, EXAM_POLICY_DIR=tmp):
            record = pack()['sources'][0]
            spec = {k:v for k,v in record.items() if k not in ('checked_at', 'sha256', 'paragraphs')}
            sources.atomic_json(Path(tmp)/'official.json', record)
            with patch.object(sources, 'registry', return_value={'official':spec}):
                with self.assertRaisesRegex(ValueError, '今日'):
                    sources.require_current_sources(pack())
                page = sources.Page();page.parts = [TEXT * 4]
                with patch.object(sources, 'fetch', return_value=(page, spec['url'])), patch.object(sources, 'refresh', return_value=record):
                    sources.review_updates({'source_ids':['official'],'urls':[spec['url']],
                        'findings':[{'url':spec['url'],'quote':TEXT,'finding':'核对正式原文适用主体与文件要求，限定该文件口径出题。'}],
                        'note':'已核对主管部门正式原文、发布信息及适用日期，本批按该文件明确时点命题，不延伸声称现行全部政策。'})
                sources.require_current_sources(pack())
                audit = {'evidence': [{'url': spec['url'], 'text': TEXT}]}
                with self.assertRaisesRegex(ValueError, 'findings'):
                    sources.validate_update_findings(audit)
                audit['findings'] = [{'url':spec['url'], 'quote':'仅返回HTTP200，并没有阅读到真实正文内容。', 'finding':'检查网站仍可以访问但不代表文件没有更新。'}]
                with self.assertRaisesRegex(ValueError, '连续原文'):
                    sources.validate_update_findings(audit)
                original_review = json.loads((Path(tmp)/'update-reviews.json').read_text())
                expired_review = copy.deepcopy(original_review)
                expired_review['official']['checked_at'] = '2020-01-01T00:00:00+00:00'
                sources.atomic_json(Path(tmp)/'update-reviews.json', expired_review)
                with patch.object(sources, 'fetch', return_value=(page, spec['url'])):
                    sources.refresh(spec)
                self.assertEqual(json.loads((Path(tmp)/'update-reviews.json').read_text()), expired_review)
                with self.assertRaisesRegex(ValueError, '今日'):
                    sources.source_pack([{'tag': TAG}], ['official'])
                sources.atomic_json(Path(tmp)/'official.json', record)
                sources.atomic_json(Path(tmp)/'update-reviews.json', original_review)
                changed = copy.deepcopy(record)
                changed['sha256'] = 'different-body'
                sources.atomic_json(Path(tmp)/'official.json', changed)
                with self.assertRaisesRegex(ValueError, '变化'):
                    sources.require_current_sources(pack())
                sources.atomic_json(Path(tmp)/'official.json', record)
                stale = pack();stale['sources'][0]['checked_at']='2020-01-01T00:00:00+00:00'
                sources.validate_pack(stale)
                with self.assertRaisesRegex(ValueError, '过期'):
                    sources.require_current_sources(stale)
                spec['superseded_by']='replacement'
                with self.assertRaisesRegex(ValueError, '失效'):
                    sources.require_current_sources(pack())
                spec.pop('superseded_by')
                expiring = {**record, 'expires_at': sources.today().isoformat()}
                spec['expires_at'] = expiring['expires_at']
                sources.atomic_json(Path(tmp)/'official.json', expiring)
                historical = {'as_of': (sources.today()-dt.timedelta(days=1)).isoformat(), 'sources': [expiring]}
                sources.validate_pack(historical)
                with self.assertRaisesRegex(ValueError, '失效'):
                    sources.require_current_sources(historical)
                spec.pop('expires_at')
                spec.update(kind='law', scope='current')
                law = {**record, 'kind': 'law', 'scope': 'current'}
                sources.atomic_json(Path(tmp)/'official.json', law)
                with self.assertRaisesRegex(ValueError, '生效日期'):
                    sources.require_current_sources({'as_of': sources.today().isoformat(), 'sources': [law]})

    def test_discovery_preserves_unseen_pending_candidates(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, EXAM_POLICY_DIR=tmp):
            old={'url':'https://www.gov.cn/older','title':'上次发现的重要政策文件','status':'candidate_unverified'}
            sources.atomic_json(Path(tmp)/'candidates.json',{'candidates':[old]})
            page=sources.Page();page.links=[('/new','关于推进科技创新的政策文件')]
            config=Path(tmp)/'config.json';config.write_text(json.dumps({'watch_pages':['https://www.gov.cn/'],'watch_terms':['科技']}))
            with patch.object(sources,'CONFIG',config),patch.object(sources,'registry',return_value={}),patch.object(sources,'fetch',return_value=(page,'https://www.gov.cn/')):
                result=sources.discover()
            self.assertEqual(len(result['candidates']),2)
            self.assertEqual(result['candidates'][0],old)

    def test_source_selection_filters_before_limit_and_covers_each_tag(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, EXAM_POLICY_DIR=tmp):
            base=pack()['sources'][0];entries={}
            for i in range(12):
                row={**base,'id':f'entry-{i}','published_at':f'2026-08-{i+1:02d}','kind':'foundation'}
                if i==11: row['superseded_by']='newer'
                entries[row['id']]={k:v for k,v in row.items() if k not in ('checked_at','sha256','paragraphs')}
                sources.atomic_json(Path(tmp)/(row['id']+'.json'),row)
            with patch.object(sources,'registry',return_value=entries):
                result=sources.source_pack([{'tag':TAG}])
            self.assertEqual(len(result['sources']),8)
            self.assertEqual(result['sources'][0]['id'],'entry-10')
            self.assertNotIn('entry-11',[r['id'] for r in result['sources']])

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

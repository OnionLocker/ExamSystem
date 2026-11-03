import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from collections import Counter
from pathlib import Path
from argparse import Namespace

import policy_daily_plan as plan

DAY = dt.date(2026, 10, 30)


def topic(index, module='政治理论', category='时事政治', kind='policy'):
    tag = f'{module}-{category}-其他'
    return {'id': f's{index}:p{index}', 'source_id': f's{index}', 'paragraph_id': f'p{index}',
            'title': f'考点{index}', 'text': '可核验的具体考点与条件。' * 8,
            'source_title': f'文件{index}', 'published_at': '2026-10-29', 'kind': kind,
            'tag': tag, 'tags': [tag]}


def attempt(gap, correct=True, kind='single', seconds=40):
    return {'day': DAY - dt.timedelta(days=gap), 'correct': correct, 'kind': kind, 'seconds': seconds}


class StateTest(unittest.TestCase):
    def test_intervals_and_distinct_day_successes(self):
        self.assertFalse(plan.state([attempt(2)], DAY)['due'])
        self.assertTrue(plan.state([attempt(3)], DAY)['due'])
        self.assertFalse(plan.state([attempt(10), attempt(6)], DAY)['due'])
        self.assertTrue(plan.state([attempt(10), attempt(7)], DAY)['due'])
        self.assertEqual(plan.state([attempt(7), attempt(7)], DAY)['streak'], 1)

    def test_wrong_slow_and_judge_only_return_earlier(self):
        for rows in ([attempt(1, False)], [attempt(1, seconds=100)], [attempt(1, kind='judge')]):
            self.assertTrue(plan.state(rows, DAY)['due'])
        self.assertEqual(plan.state([attempt(5, kind='judge'), attempt(1, kind='judge')], DAY)['streak'], 0)
        self.assertTrue(plan.state([attempt(0, False), attempt(0)], DAY)['weak'])

    def test_recent_error_needs_two_successful_days_before_clearing(self):
        self.assertTrue(plan.state([attempt(8, False), attempt(4)], DAY)['weak'])
        self.assertFalse(plan.state([attempt(10, False), attempt(8), attempt(7)], DAY)['weak'])


class SelectionTest(unittest.TestCase):
    def test_candidates_exclude_meeting_procedures_and_orphan_law_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = {
                'science': {'id': 'science', 'title': '中子源科技成果', 'kind': 'event',
                            'published_at': '2026-09-07', 'tags': ['常识判断-科技常识-科技理论与成就']},
                'law': {'id': 'law', 'title': '审计条例', 'kind': 'law',
                        'published_at': '2026-09-24', 'tags': ['常识判断-法律常识-其他法律法规']},
            }
            (root/'science.json').write_text(json.dumps({'paragraphs': [
                {'id': 'p-meeting', 'text': '专家委员会听取致辞并主持会议。' * 5},
                {'id': 'p-result', 'text': '四项成果包括工程材料中子衍射谱仪和中子成像谱仪，已完成科技成果鉴定。' * 2}]}))
            (root/'law.json').write_text(json.dumps({'paragraphs': [
                {'id': 'p-fragment', 'text': '（四）审计机关提出的关于财务收支、财政收支改进工作的建议；' * 2},
                {'id': 'p-article', 'text': '第三条 审计机关依法对财政收支、财务收支的真实、合法和效益进行监督。' * 2}]}))
            with patch.object(plan.sources, 'registry', return_value=specs), \
                    patch.object(plan.sources, 'directory', return_value=root):
                selected = plan.candidates('常识判断')
            self.assertEqual({p['paragraph_id'] for p in selected}, {'p-result', 'p-article'})

    def test_cold_start_backfills_instead_of_inventing_wrong_points(self):
        pool = [dict(topic(i), source_id=f's{i // 2}') for i in range(12)]
        pool += [topic(20, kind='foundation'), topic(21, kind='foundation')]
        result = plan.select('政治理论', 10, pool, {}, Counter(), DAY, {'文件0': 110})
        counts = Counter(p['role'] for p in result)
        self.assertEqual(counts, {'hot': 3, 'foundation': 2, 'coverage': 5})
        self.assertEqual(result[0]['source_id'], 's0')
        self.assertEqual(len({p['id'] for p in result}), 10)
        self.assertLessEqual(len({p['source_id'] for p in result}), 8)

    def test_due_wrong_points_and_weekly_category_coverage(self):
        categories = ['法律常识', '科技常识', '经济常识', '人文常识', '地理国情']
        pool = [topic(i, '常识判断', category) for i, category in enumerate(categories)]
        pool += [dict(p, id=p['id'] + '-2') for p in pool]
        attempts = {pool[0]['id']: [attempt(1, False)], pool[1]['id']: [attempt(0, False)]}
        result = plan.select('常识判断', 5, pool, attempts, Counter(), DAY, {})
        self.assertEqual(result[0]['id'], pool[0]['id'])
        self.assertEqual(result[0]['role'], 'weak')
        self.assertNotEqual(result[1]['role'], 'weak')
        self.assertEqual(len({p['tag'] for p in result}), 5)

    def test_two_due_wrong_points_in_same_category_are_not_displaced(self):
        pool = [topic(i, '常识判断', '法律常识') for i in range(2)]
        pool += [topic(i + 2, '常识判断', category) for i, category in enumerate(
            ('科技常识', '经济常识', '人文常识', '地理国情'))]
        attempts = {p['id']: [attempt(1, False)] for p in pool[:2]}
        result = plan.select('常识判断', 5, pool, attempts, Counter(), DAY, {})
        self.assertEqual({p['id'] for p in result[:2]}, {p['id'] for p in pool[:2]})
        self.assertTrue(all(p['role'] == 'weak' for p in result[:2]))

    def test_recently_practised_categories_yield_to_other_coverage(self):
        pool = [topic(0, '常识判断', '法律常识'), topic(1, '常识判断', '科技常识')]
        attempts = {pool[0]['id']: [attempt(0)]}
        result = plan.select('常识判断', 1, pool, attempts, Counter(), DAY, {})
        self.assertEqual(result[0]['id'], pool[1]['id'])

    def test_common_sparse_pool_does_not_invent_sources_or_force_categories(self):
        pool = [topic(i, '常识判断', '科技常识') for i in range(6)]
        result = plan.select('常识判断', 5, pool, {}, Counter(), DAY, {})
        self.assertEqual(len(result), 5)
        self.assertTrue(all(p['id'] in {p['id'] for p in pool} for p in result))
        self.assertTrue(all(p['role'] == 'coverage' for p in result))

    def test_guangdong_role_is_not_locked_to_economics_or_national_geography(self):
        pool = [topic(i, '常识判断', '地理国情') for i in range(6)]
        pool += [dict(topic(8, '常识判断', '科技常识'), source_title='广东科技成果')]
        pool += [dict(topic(9, '常识判断', '科技常识'), source_title='广东另一科技成果')]
        pool += [dict(topic(10, '常识判断', '科技常识'), source_title='粤港澳科技成果')]
        result = plan.select('常识判断', 5, pool, {}, Counter(), DAY, {})
        self.assertEqual([p['role'] for p in result[2:4]], ['gd', 'gd'])
        self.assertIn('高价值包', result[2]['reason'])
        self.assertTrue(all(p['gd'] for p in result[2:4]))
        self.assertIn('-科技常识-', result[3]['tag'])
        national = plan.select('常识判断', 5, pool[:6], {}, Counter(), DAY, {})
        self.assertEqual([p['role'] for p in national[2:4]], ['coverage', 'coverage'])

    def test_high_value_guangdong_packs_rotate_by_recent_use(self):
        core = list(plan.GD_PRIORITY[:3])
        pool = [dict(topic(i), source_id=ident, id=f'{ident}:p{i}', source_title='广东材料')
                for i, ident in enumerate(core)]
        pool += [dict(topic(10 + i), source_id=f'n{i // 2}') for i in range(10)]
        picks = []
        for _ in range(3):
            recent = {'sources': {'政治理论': Counter(picks)}, 'paragraphs': {}}
            chosen = plan.select('政治理论', 10, pool, {}, Counter(), DAY, {}, recent)
            gd_core = [p for p in chosen if p['role'] == 'gd_core']
            self.assertEqual(len(gd_core), 1)
            picks.append(gd_core[0]['source_id'])
        self.assertEqual(picks, core)

    def test_fourteen_day_source_and_paragraph_limits(self):
        pool = [dict(topic(i), source_id='busy') for i in range(6)]
        pool += [dict(topic(10 + i), source_id=f'n{i // 2}') for i in range(12)]
        recent = {'sources': {'政治理论': Counter({'busy': plan.SOURCE_CAP['政治理论']})},
                  'paragraphs': {'s10:p10': DAY - dt.timedelta(days=3)}}
        chosen = plan.select('政治理论', 10, pool, {}, Counter(), DAY, {}, recent)
        self.assertNotIn('busy', {p['source_id'] for p in chosen})
        self.assertNotIn('s10:p10', {p['id'] for p in chosen})
        self.assertTrue(all(count <= plan.DAILY_SOURCE_CAP
                            for count in Counter(p['source_id'] for p in chosen).values()))

    def test_wrong_point_retest_is_exempt_from_limits(self):
        pool = [dict(topic(i), source_id=f's{i // 2}') for i in range(12)]
        attempts = {pool[0]['id']: [attempt(1, False)]}
        recent = {'sources': {'政治理论': Counter({'s0': 9})}, 'paragraphs': {pool[0]['id']: DAY - dt.timedelta(days=1)}}
        chosen = plan.select('政治理论', 10, pool, attempts, Counter(), DAY, {}, recent)
        weak = [p for p in chosen if p['role'] == 'weak']
        self.assertEqual([p['id'] for p in weak], [pool[0]['id']])
        slots = [{'source_id': p['source_id'], 'question_type': 'single',
                  'policy_point': {'id': p['id'], 'role': p['role']},
                  'plan_audit': {k: p.get(k) for k in ('gd', 'source_prior_uses', 'paragraph_last_used', 'limit_relaxed')}}
                 for p in chosen]
        with patch.object(plan.sources, 'registry', return_value={}):
            audit = plan.quota_audit('政治理论', slots)
        self.assertEqual(audit['limit_violations'], [])
        self.assertEqual(audit['count'], 10)

    def test_same_source_can_repeat_with_different_target_paragraphs(self):
        pool = [dict(topic(i), source_id='same') for i in range(10)]
        result = plan.select('政治理论', 10, pool, {}, Counter(), DAY, {})
        self.assertEqual(len(result), 10)
        self.assertEqual(len({p['id'] for p in result}), 10)

    def test_guangdong_slot_keeps_its_actual_science_tag(self):
        point = dict(topic(0, '常识判断', '科技常识'), role='gd', reason='广东相关重点')
        point['tags'].append('常识判断-地理国情-其他')
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(plan.sources, 'usage_path', return_value=Path(tmp) / 'absent.db'), \
                patch.object(plan, 'candidates', return_value=[point]), \
                patch.object(plan, 'select', return_value=[point]):
            slots = plan.build_slots('常识判断', 1, 'auto', {}, ['single'])
        self.assertEqual(slots[0]['tag'], point['tag'])
        self.assertEqual(slots[0]['policy_point']['role'], 'gd')


class HistoryTest(unittest.TestCase):
    def test_slot_boundary_preserves_point_and_rejects_different_source(self):
        from quiz_generator import resolve_slots
        point = {'id': 'source:p1', 'paragraph_id': 'p1', 'title': '任务定位',
                 'role': 'hot', 'reason': '近期重点'}
        slot = {'tag': '政治理论-时事政治-重要文件', 'count': 1, 'source_id': 'source',
                'policy_point': point, 'difficulty': 'auto'}
        args = Namespace(blueprint=json.dumps({'slots': [slot]}), tag=None, count=None,
                         module='政治理论', difficulty='auto')
        _, slots = resolve_slots(args)
        self.assertEqual(slots[0]['policy_point'], point)
        slot['policy_point'] = {**point, 'id': 'another:p1'}
        args.blueprint = json.dumps({'slots': [slot]})
        with self.assertRaisesRegex(ValueError, '与绑定原文不一致'):
            resolve_slots(args)

    def test_first_attempt_only_and_specific_old_evidence(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.executescript('CREATE TABLE questions(id INTEGER, external_id TEXT, question_type TEXT, '
                           'category TEXT, source_evidence TEXT); CREATE TABLE practice_answers('
                           'id INTEGER, question_id INTEGER, user_answer TEXT, is_correct INTEGER, '
                           'time_spent_sec INTEGER, answered_at TEXT);')
        for i, claims in enumerate((['s:p'], ['s:p', 's:p2']), 1):
            conn.execute('INSERT INTO questions VALUES(?,?,?,?,?)',
                         (i, f'q{i}', 'single', '政治理论', json.dumps({'claim_ids': claims})))
        conn.executemany('INSERT INTO practice_answers VALUES(?,?,?,?,?,?)', [
            (1, 1, 'B', 0, 20, '2026-10-28 02:00:00'),
            (2, 1, 'A', 1, 10, '2026-10-29 02:00:00'),
            (3, 2, 'A', 1, 30, '2026-10-29 02:00:00')])
        rows, _ = plan.history(conn, '政治理论')
        self.assertEqual(len(rows['s:p']), 1)
        self.assertFalse(rows['s:p'][0]['correct'])
        self.assertEqual(set(rows), {'s:p'})

    def test_repacked_set_copy_is_the_same_question(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.executescript('CREATE TABLE questions(id INTEGER, external_id TEXT, question_type TEXT, '
                           'category TEXT, batch_id TEXT, source_evidence TEXT, created_at TEXT); '
                           'CREATE TABLE practice_answers(id INTEGER, question_id INTEGER, user_answer TEXT, '
                           'is_correct INTEGER, time_spent_sec INTEGER, answered_at TEXT);')
        evidence = json.dumps({'claim_ids': ['s:p']})
        copy_batch = plan.REPACK_BATCH_PREFIX + '01-20261028'
        conn.executemany('INSERT INTO questions VALUES(?,?,?,?,?,?,?)', [
            (1, 'q1', 'single', '政治理论', 'daily', evidence, '2026-10-28 01:00:00'),
            (2, copy_batch + plan.REPACK_SEPARATOR + 'q1', 'single', '政治理论', copy_batch, evidence,
             '2026-10-29 01:00:00')])
        conn.executemany('INSERT INTO practice_answers VALUES(?,?,?,?,?,?)', [
            (1, 1, 'B', 0, 20, '2026-10-28 02:00:00'), (2, 2, 'A', 1, 20, '2026-10-29 02:00:00')])
        rows, _ = plan.history(conn, '政治理论')
        self.assertEqual(len(rows['s:p']), 1)
        usage = plan.recent_usage(conn, DAY)
        self.assertEqual(usage['sources']['政治理论']['s'], 1)
        self.assertEqual(usage['paragraphs']['s:p'], dt.date(2026, 10, 28))

    def test_successful_import_plan_keeps_question_point_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.db'
            point = {'id': 'source:p1', 'paragraph_id': 'p1', 'title': '任务定位',
                     'role': 'hot', 'reason': '近期重点'}
            run = {'module': '政治理论', 'batch_id': 'new', 'slots': [
                {'tag': '政治理论-时事政治-重要文件', 'count': 1, 'source_id': 'source', 'policy_point': point}]}
            plan.record_plan(path, run, [{'external_id': 'new_01'}])
            with sqlite3.connect(path) as conn:
                raw, = conn.execute('SELECT plan_json FROM daily_review_plans').fetchone()
                self.assertEqual(json.loads(raw)['questions'][0]['point_id'], 'source:p1')
                _, generated = plan.history(conn, '政治理论')
                self.assertEqual(generated['source:p1'], 1)


if __name__ == '__main__':
    unittest.main()

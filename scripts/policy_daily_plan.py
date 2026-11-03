#!/usr/bin/env python3
"""政治/常识每日选题：热点、具体原文段落复测、基础理论与分类覆盖。"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from collections import Counter, defaultdict

import policy_sources as sources
from daily_review_plan import _day, save_plan
from kaodian_profile import blank_weight

VERSION = 'policy-daily-v2'
PLAN_VERSIONS = {'policy-daily-v1', VERSION}
# 政治：中央热点3 + 基础2 + 广东2（其一必取高价值广东包）+ 错点2 + 覆盖1；常识：错点2 + 广东2 + 覆盖1。
# 基础排在广东前：广东名额回落覆盖时不会先占走仅有的基础理论段落。
QUOTAS = {
    '政治理论': ('hot', 'hot', 'hot', 'foundation', 'foundation', 'gd_core', 'gd', 'weak', 'weak', 'coverage'),
    '常识判断': ('weak', 'weak', 'gd_core', 'gd', 'coverage'),
}
LABELS = {'hot': '近期重点', 'weak': '错点复测', 'foundation': '基础理论',
          'coverage': '补充覆盖', 'gd': '广东相关重点', 'gd_core': '广东高价值包轮转'}
# 粤考高价值广东包：按序轮转，近14天用得最少、最久未出的先上。
GD_PRIORITY = (
    'xi-guangdong-inspection-202511',
    'gd-higher-ed-chongyiliu-202605',
    'gd-services-expansion-202606',
    'gd-high-quality-conference-202602',
    'national-games-15th-opening-202511',
    'national-games-15th-closing-202511',
    'gd-national-games-summary-202601',
    'gd-15th-plan-2026',
    'gd-four-chains-new-quality-202601',
    'gd-work-report-2026',
    'gd-overview-history-jzyg',
    'gd-overview-geography-zrdl',
)
GD_TITLE_WORDS = ('广东', '粤港澳', '大湾区', '全运会', '全国运动会', '十五运会', '深圳', '广州')
GD_TEXT_WORDS = ('广东', '粤港澳大湾区')
RECENT_DAYS = 14
SOURCE_CAP = {'政治理论': 3, '常识判断': 2}
FOUNDATION_SOURCE_CAP = 4  # 基础理论原文只有几篇，段落仍不得重复。
DAILY_SOURCE_CAP = 2
# 成套卷副本与原日练是同一道题：作答归并回原题，出题限频也不重复计。
REPACK_BATCH_PREFIX = 'gd-zhengli-set-'
REPACK_SEPARATOR = '::'


def canonical_external_id(external_id):
    text = str(external_id or '')
    return text.split(REPACK_SEPARATOR, 1)[1] if REPACK_SEPARATOR in text else text


def is_gd_source(source_id, title=''):
    return str(source_id).startswith('gd-') or str(source_id) in GD_PRIORITY or any(
        word in str(title) for word in GD_TITLE_WORDS)


def is_gd(point):
    return is_gd_source(point['source_id'], point.get('source_title', '')) or any(
        word in point.get('text', '') for word in GD_TEXT_WORDS)


def source_cap(module, kind):
    return FOUNDATION_SOURCE_CAP if kind == 'foundation' else SOURCE_CAP[module]


def recent_usage(conn, day, window=RECENT_DAYS):
    """近 window 天（不含未来）每个模块按原文计题数、按段落记最近出题日；以题目原文依据为准。"""
    usage = {'sources': {module: Counter() for module in QUOTAS}, 'paragraphs': {}}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'questions' not in tables or 'source_evidence' not in {
            row[1] for row in conn.execute('PRAGMA table_info(questions)')}:
        return usage
    cutoff = (day - dt.timedelta(days=window + 1)).isoformat()
    rows = conn.execute(
        'SELECT category, batch_id, source_evidence, created_at FROM questions '
        'WHERE category IN (?, ?) AND source_evidence IS NOT NULL AND created_at >= ?',
        (*QUOTAS, cutoff))
    for module, batch_id, raw, created in rows:
        when = _day(created)
        if when is None or when > day or (day - when).days >= window:
            continue
        if str(batch_id or '').startswith(REPACK_BATCH_PREFIX):
            continue
        try:
            evidence = json.loads(raw)
        except (TypeError, ValueError):
            continue
        claims = [str(c) for c in evidence.get('claim_ids') or [] if ':' in str(c)]
        if not claims:
            claims = [f"{c['source_id']}:{c['paragraph_id']}" for check in evidence.get('checks') or []
                      if isinstance(check, dict) for c in check.get('citations') or []
                      if isinstance(c, dict) and c.get('source_id') and c.get('paragraph_id')]
        ids = {c.split(':', 1)[0] for c in claims} or {
            str(s.get('id')) for s in evidence.get('sources') or [] if isinstance(s, dict) and s.get('id')}
        for ident in ids:
            usage['sources'][module][ident] += 1
        for claim in claims:
            previous = usage['paragraphs'].get(claim)
            usage['paragraphs'][claim] = max(previous, when) if previous else when
    return usage


def candidates(module):
    out = []
    for spec in sources.registry().values():
        tags = [t for t in spec['tags'] if t.startswith(module + '-')]
        if not tags or not sources.applicable(spec, sources.today()):
            continue
        if module == '常识判断' and '-科技常识-' in tags[0] and any(
                word in spec['title'] for word in ('意见', '立场', '规划', '会议', '大会', '贺信', '讲话', '条例')):
            # 政策职责、治理主张不冒充科学原理或科技成果。
            tags = [t for t in tags if '-科技常识-' not in t]
            if not tags:
                continue
        path = sources.directory() / (spec['id'] + '.json')
        if not path.exists():
            continue
        cached = json.loads(path.read_text(encoding='utf-8'))
        for paragraph in cached.get('paragraphs', []):
            text = paragraph['text']
            if len(text) < 40:
                continue
            if module == '常识判断':
                if spec['kind'] == 'law' and re.match(r'^[（(][一二三四五六七八九十]+[）)]', text):
                    continue  # 条款下的孤立列项缺少主句，优先选可独立核验的完整条文。
                if '-科技常识-' in tags[0] and (any(word in text for word in ('主持', '致辞', '专家委员会'))
                                              or text.startswith('未来，')):
                    continue
                if '-经济常识-' in tags[0] and not any(word in text for word in (
                        '生产', '经营', '市场', '消费', '收入', '粮食', '产业', '贸易', '就业',
                        '财税', '金融', '资本', '资源配置', '承包', '财政')):
                    continue
            title = text.split('。', 1)[0][:90]
            out.append({'id': spec['id'] + ':' + paragraph['id'], 'source_id': spec['id'],
                        'paragraph_id': paragraph['id'], 'title': title, 'text': text,
                        'source_title': spec['title'], 'published_at': spec['published_at'],
                        'kind': spec['kind'], 'tags': tags, 'tag': tags[0]})
    return out


def history(conn, module):
    """只用首次有效作答；同题重做不增加独立证据，不把出题次数当掌握度。"""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    mapping, generated = {}, Counter()
    if 'daily_review_plans' in tables:
        for raw, in conn.execute('SELECT plan_json FROM daily_review_plans WHERE module=?', (module,)):
            plan = json.loads(raw)
            if plan.get('policy_version') not in PLAN_VERSIONS:
                continue
            for item in plan.get('questions', []):
                mapping[item['external_id']] = item['point_id']
                generated[item['point_id']] += 1
    attempts = defaultdict(list)
    if not {'practice_answers', 'questions'} <= tables:
        return attempts, generated
    evidence_col = 'source_evidence' in {row[1] for row in conn.execute('PRAGMA table_info(questions)')}
    evidence = 'q.source_evidence' if evidence_col else 'NULL'
    rows = conn.execute(
        f'SELECT q.id, q.external_id, q.question_type, {evidence}, pa.user_answer, '
        'pa.is_correct, pa.time_spent_sec, pa.answered_at FROM practice_answers pa '
        'JOIN questions q ON q.id=pa.question_id WHERE q.category=? ORDER BY pa.answered_at, pa.id',
        (module,))
    seen = set()
    for qid, external_id, kind, raw, answer, correct, seconds, when in rows:
        day = _day(when)
        original = canonical_external_id(external_id) or qid
        if original in seen or day is None or (not answer and blank_weight(int(seconds or 0)) == 0):
            continue
        seen.add(original)
        point = mapping.get(canonical_external_id(external_id))
        if not point and raw:
            # 旧题只在依据唯一定位到一个段落时继承，不能把整篇文件都算练过。
            claims = json.loads(raw).get('claim_ids', [])
            if len(claims) == 1:
                point = claims[0]
        if point:
            attempts[point].append({'day': day, 'correct': bool(answer) and bool(correct),
                                    'seconds': int(seconds or 0), 'kind': kind})
    return attempts, generated


def state(items, day):
    # 同日同段落只计一次：任一错误保留；判断题正确不能单独推进掌握认证。
    days = {}
    for item in items:
        if item['day'] > day:
            continue
        current = days.setdefault(item['day'], {'correct': True, 'qualified': False, 'slow': False})
        current['correct'] &= item['correct']
        current['qualified'] |= item['correct'] and item['kind'] != 'judge'
        current['slow'] |= item['seconds'] <= 0 or item['seconds'] > (90 if item['kind'] == 'multi' else 60)
    ordered = sorted(days.items())
    streak = 0
    for _, value in reversed(ordered):
        if not value['correct']:
            break
        if value['qualified'] and not value['slow']:
            streak += 1
    if not ordered:
        return {'weak': False, 'due': False, 'gap': None, 'streak': 0, 'failures': 0}
    last_day, last = ordered[-1]
    weak = not last['correct'] or (streak < 2 and any(not value['correct'] for _, value in ordered))
    interval = 1 if weak or last['slow'] or not last['qualified'] else 7 if streak >= 2 else 3
    gap = (day - last_day).days
    failures = sum(not value['correct'] for _, value in ordered[-2:])
    return {'weak': weak, 'due': gap >= interval, 'gap': gap, 'streak': streak, 'failures': failures}


def _eligible(role, point, value):
    if role == 'weak':
        return value['weak'] and value['due']
    if role == 'hot':
        return point['kind'] != 'foundation' and not is_gd(point)
    if role == 'foundation':
        return point['kind'] == 'foundation' or any('-毛中特-' in t for t in point['tags'])
    if role == 'gd_core':
        return point['source_id'] in GD_PRIORITY
    if role == 'gd':
        return is_gd(point)
    return True


def select(module, count, pool, attempts, generated, day, weights, recent=None):
    if not pool:
        raise ValueError(f'{module}没有可用原文段落，先补充并核验资料')
    recent = recent or {'sources': {}, 'paragraphs': {}}
    prior = recent['sources'].get(module, Counter())
    recent_paragraphs = recent['paragraphs']
    scored = {p['id']: state(attempts.get(p['id'], []), day) for p in pool}
    category_seen = Counter()
    for point in pool:
        category_seen[point['tag'].split('-')[1]] += sum(
            (day - row['day']).days <= 7 for row in attempts.get(point['id'], []) if row['day'] <= day)
    chosen_ids, source_counts = set(), Counter()
    roles = QUOTAS[module]

    def uses(point):
        return prior[point['source_id']] + source_counts[point['source_id']]

    def within_limits(point):
        # 错点复测本就要回到同一段落，换设问重考，不受限频约束。
        return (point['id'] not in recent_paragraphs
                and source_counts[point['source_id']] < DAILY_SOURCE_CAP
                and uses(point) < source_cap(module, point['kind']))

    def candidates_for(wanted, fallback):
        available = [p for p in pool if p['id'] not in chosen_ids and
                     (len(source_counts) < 8 or p['source_id'] in source_counts)]
        if not available:
            raise ValueError('可用资料不足以组成不重复的每日卷，请补充原文')
        fresh = [p for p in available if within_limits(p)]
        suitable = [p for p in (available if wanted == 'weak' else fresh)
                    if _eligible(wanted, p, scored[p['id']])]
        if suitable:
            return wanted, '', False, suitable
        if wanted == 'gd_core':
            suitable = [p for p in fresh if _eligible('gd', p, scored[p['id']])]
            if suitable:
                return 'gd', f'（{LABELS[wanted]}近{RECENT_DAYS}天均已达限频，转其他广东原文）', False, suitable
        if not fallback:
            return None
        if fresh:
            return 'coverage', f'（{LABELS[wanted]}暂无可用证据或来源，名额转覆盖）', False, fresh
        # 资料不够轮转时宁可同源换段落，也不重复近期段落；仍不够才整体放宽并在理由中注明。
        return ('coverage', f'（{LABELS[wanted]}在{RECENT_DAYS}天限频内无可用原文，已放宽，需补充资料）', True,
                [p for p in available if p['id'] not in recent_paragraphs] or available)

    # 先让每个名额按本角色取点，再给落空的名额补覆盖，免得覆盖名额先占走广东包或基础段落。
    picked = {}
    for fallback in (False, True):
        for index in range(count):
            if index in picked:
                continue
            wanted = roles[index % len(roles)]
            found = candidates_for(wanted, fallback)
            if found is None:
                continue
            role, note, relaxed, suitable = found

            def rank(point):
                value = scored[point['id']]
                hotspot = max((w for term, w in weights.items() if term in point['source_title'] + point['text']),
                              default=0)
                category = point['tag'].split('-')[1]
                if role == 'hot':
                    return (source_counts[point['source_id']], -hotspot, uses(point),
                            -dt.date.fromisoformat(point['published_at']).toordinal(), generated[point['id']],
                            point['id'])
                if role in ('gd_core', 'gd'):
                    order = (GD_PRIORITY.index(point['source_id']) if point['source_id'] in GD_PRIORITY
                             else len(GD_PRIORITY))
                    return (source_counts[point['source_id']], uses(point), order, -hotspot,
                            generated[point['id']], point['id'])
                coverage = (category_seen[category], source_counts[point['source_id']]) if module == '常识判断' else (
                    source_counts[point['source_id']], category_seen[category])
                return (not value['due'], *coverage, uses(point),
                        generated[point['id']], -(value['gap'] or 0), point['id'])
            pick = min(suitable, key=rank)
            value = scored[pick['id']]
            reason = LABELS[role] + note
            if value['gap'] is not None:
                reason += f'；距上次有效作答{value["gap"]}天'
            if value['failures'] >= 2:
                reason += '；连续两轮未改善，先讲清概念再验证，今日不加量'
            reason += f'；同源近{RECENT_DAYS}天已出{prior[pick["source_id"]]}题'
            picked[index] = {**pick, 'role': role, 'reason': reason, 'gd': is_gd(pick),
                             'source_prior_uses': prior[pick['source_id']], 'limit_relaxed': relaxed,
                             'paragraph_last_used': (recent_paragraphs[pick['id']].isoformat()
                                                     if pick['id'] in recent_paragraphs else None)}
            chosen_ids.add(pick['id'])
            source_counts[pick['source_id']] += 1
            category_seen[pick['tag'].split('-')[1]] += 1
    return [picked[index] for index in range(count)]


def build_slots(module, count, difficulty, weights, types):
    day = sources.today()
    path = sources.usage_path()
    attempts, generated, recent = {}, Counter(), None
    if path.exists():
        with sqlite3.connect(f'file:{path.resolve()}?mode=ro', uri=True) as conn:
            attempts, generated = history(conn, module)
            recent = recent_usage(conn, day)
    selected = select(module, count, candidates(module), attempts, generated, day, weights, recent)
    slots = []
    for point, question_type in zip(selected, types):
        tag = point['tag']
        brief = (f'只依据《{point["source_title"]}》；本题锁定原文段落{point["paragraph_id"]}，'
                 f'辨析重点：{point["title"]}。{point["reason"]}。'
                 '换设问与干扰项，不能以记住旧题字母代替理解。')
        if point.get('gd'):
            brief += '优先考广东本土表述与全国口径的区别，干扰项用粤考常见的张冠李戴。'
        slots.append({'tag': tag, 'count': 1, 'question_type': question_type,
                      'difficulty': difficulty or 'mid', 'source_id': point['source_id'], 'brief': brief,
                      'policy_point': {k: point[k] for k in ('id', 'paragraph_id', 'title', 'role', 'reason')},
                      'plan_audit': {k: point.get(k) for k in (
                          'gd', 'source_prior_uses', 'paragraph_last_used', 'limit_relaxed')}})
    return slots


def quota_audit(module, slots):
    """日志可核验的配额与限频摘要：角色、广东题数、判断题数、同源/同段落是否越限。"""
    roles, sources_today, capped_today, types = Counter(), Counter(), Counter(), Counter()
    gd = gd_core = 0
    violations, relaxed = [], []
    registry = sources.registry()
    for slot in slots:
        point, audit = slot.get('policy_point') or {}, slot.get('plan_audit') or {}
        roles[point.get('role')] += 1
        types[slot.get('question_type', 'single')] += 1
        sources_today[slot.get('source_id')] += 1
        if point.get('role') != 'weak':
            capped_today[slot.get('source_id')] += 1
        gd += bool(audit.get('gd'))
        gd_core += point.get('role') == 'gd_core'
        if audit.get('limit_relaxed'):
            relaxed.append(point.get('id'))
        if point.get('role') != 'weak' and audit.get('paragraph_last_used'):
            violations.append(f'{point.get("id")} 段落{audit["paragraph_last_used"]}已出过')
    prior = {s.get('source_id'): (s.get('plan_audit') or {}).get('source_prior_uses') or 0 for s in slots}
    for ident, today in capped_today.items():
        if ident is None:
            continue
        cap = source_cap(module, (registry.get(ident) or {}).get('kind'))
        if today > DAILY_SOURCE_CAP or prior[ident] + today > cap:
            violations.append(f'{ident} 当日{today}题、近{RECENT_DAYS}天累计{prior[ident] + today}题（上限{cap}）')
    return {'module': module, 'count': len(slots), 'roles': dict(roles), 'question_types': dict(types),
            'gd_count': gd, 'gd_core_count': gd_core,
            'gd_core_sources': [s['source_id'] for s in slots
                                if (s.get('policy_point') or {}).get('role') == 'gd_core'],
            'sources': {ident: {'today': n, 'prior_14d': prior[ident]} for ident, n in sources_today.items()},
            'limit_violations': violations, 'limit_relaxed': relaxed}


def record_plan(db_path, run, questions):
    slots = [slot for slot in run['slots'] for _ in range(int(slot['count']))]
    if not any(slot.get('policy_point') for slot in slots):
        return
    points = defaultdict(lambda: {'count': 0, 'reasons': []})
    records = []
    for slot, question in zip(slots, questions):
        point = slot.get('policy_point')
        if not point:
            continue
        records.append({'external_id': question['external_id'], 'point_id': point['id'],
                        'source_id': slot['source_id'], 'title': point['title'], 'role': point['role']})
        group = points[slot['tag']]
        group['count'] += 1
        if point['reason'] not in group['reasons']:
            group['reasons'].append(point['reason'])
    plan = {'plan_date': sources.today().isoformat(), 'module': run['module'], 'policy_version': VERSION,
            'questions': records, 'slots': slots,
            'points': [{'tag': tag, 'count': value['count'], 'reason': '；'.join(value['reasons'])}
                       for tag, value in points.items()]}
    with sqlite3.connect(db_path, timeout=30) as conn:
        save_plan(conn, run['batch_id'], plan)

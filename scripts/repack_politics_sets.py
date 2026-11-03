#!/usr/bin/env python3
"""把政治理论/常识判断日练按原出题日重组为独立套卷批次（每天一套，政治在前、常识在后）。

题干、选项、答案、解析与原文依据原样搬运；external_id 记作 ``<套卷前缀>::<原题external_id>``，
policy_daily_plan 据此把套卷作答归并回原题，避免同题重做被当成新证据、也不重复计入原文限频。

用法：
  python3 scripts/repack_politics_sets.py --start 2026-10-27 --end 2026-11-03          # 生成 batches/<套卷>/
  node scripts/import-batch.mjs batches/<套卷目录>                                      # 逐套导入
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from policy_daily_plan import REPACK_BATCH_PREFIX, REPACK_SEPARATOR  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data' / 'exam.db'
MODULES = ('政治理论', '常识判断')
TYPE_ORDER = {'judge': 0, 'single': 1, 'multi': 2}


def daily_batches(conn, start: dt.date, end: dt.date) -> list[tuple[dt.date, str]]:
    """每个出题日只取一套：优先当天政治+常识合卷，DSH 手工日卷同样按日期归位。"""
    rows = conn.execute(
        "SELECT batch_id, MIN(created_at) FROM questions WHERE category IN (?,?) "
        "AND batch_id IS NOT NULL GROUP BY batch_id", MODULES).fetchall()
    found: dict[dt.date, str] = {}
    for batch_id, _ in rows:
        if batch_id.startswith(REPACK_BATCH_PREFIX):
            continue
        if batch_id.startswith('daily-') and '-zhengzhi-' in batch_id:
            day = dt.datetime.strptime(batch_id[6:14], '%Y%m%d').date()
        elif batch_id[:8].isdigit() and '_zhengzhi_' in batch_id:
            day = dt.datetime.strptime(batch_id[:8], '%Y%m%d').date()
        else:
            continue
        if start <= day <= end:
            if day in found:
                raise SystemExit(f'{day} 有多套政治日卷（{found[day]} / {batch_id}），请人工指定')
            found[day] = batch_id
    return sorted(found.items())


def load_questions(conn, batch_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, external_id, category, question_type, content, options, correct_answer, explanation, "
        "difficulty, tags, source_evidence FROM questions WHERE batch_id=? ORDER BY id", (batch_id,)).fetchall()
    out = []
    for qid, ext, category, kind, content, options, answer, explanation, difficulty, tags, evidence in rows:
        if category not in MODULES:
            raise SystemExit(f'{batch_id} 混入非政治/常识题：{qid} {category}')
        if not explanation or not answer:
            raise SystemExit(f'{batch_id} 题 {qid} 缺答案或解析，不能成套导入')
        out.append({'_id': qid, 'external_id': ext, 'category': category, 'question_type': kind or 'single',
                    'stem': content, 'options': json.loads(options or '[]'), 'answer': answer,
                    'explanation': explanation, 'difficulty': int(difficulty or 2),
                    'tags': json.loads(tags or '[]'),
                    'source_evidence': json.loads(evidence) if evidence else None})
    out.sort(key=lambda q: (MODULES.index(q['category']),
                            TYPE_ORDER.get(q['question_type'], 9) if q['category'] == '政治理论' else 0, q['_id']))
    return out


def build(start: dt.date, end: dt.date, out_root: Path, db: Path) -> list[dict]:
    with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as conn:
        days = daily_batches(conn, start, end)
        summary = []
        for number, (day, origin) in enumerate(days, 1):
            questions = load_questions(conn, origin)
            counts = {m: sum(q['category'] == m for q in questions) for m in MODULES}
            batch_id = f'{REPACK_BATCH_PREFIX}{number:02d}-{day:%Y%m%d}'
            source = f'粤考政理常识套卷 第{number}套（{day:%m月%d日}日练·政治{counts["政治理论"]}+常识{counts["常识判断"]}）'
            manifest = {
                'batch_id': batch_id, 'source': source, 'region': '广东-模拟', 'year': day.year,
                'kind': 'repack', 'origin_batch_id': origin, 'origin_date': day.isoformat(),
                'license': '仅个人学习使用',
                'created_at': dt.date.today().isoformat(),
                'notes': (f'由 {day.isoformat()} 政治理论/常识判断日练（{origin}）原样重组为独立套卷；'
                          '题干、选项、答案、解析与原文依据未改动，原批次已通过出题双闸门。'),
            }
            items = []
            for q in questions:
                row = {k: v for k, v in q.items() if not k.startswith('_')}
                row['external_id'] = f'{batch_id}{REPACK_SEPARATOR}{q["external_id"]}'
                row['source'] = source
                if row['source_evidence'] is None:
                    row.pop('source_evidence')
                items.append(row)
            target = out_root / batch_id
            target.mkdir(parents=True, exist_ok=True)
            (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            (target / 'questions.json').write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            summary.append({'batch_id': batch_id, 'origin': origin, 'date': day.isoformat(), 'dir': str(target),
                            **counts, 'types': {t: sum(q['question_type'] == t for q in questions)
                                                for t in TYPE_ORDER}})
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--start', type=dt.date.fromisoformat, required=True)
    parser.add_argument('--end', type=dt.date.fromisoformat, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'batches')
    parser.add_argument('--db', type=Path, default=DB)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.start, args.end, args.out, args.db), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

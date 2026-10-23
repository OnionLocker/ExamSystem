#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""题材池检索脚本：用 DeepSeek Search/Fetch API 抓真实中文语料做题干素材。

用法：
  python3 scripts/corpus_fetch.py --module verbal --topics '{"科技":[["考古发现","最新研究","中国"],["深海探测","突破","2025"]],"文化":[["非遗","传承","数字化"]]}'
  python3 scripts/corpus_fetch.py --module verbal --topics-file data/manual-verbal-corpus/topics.json
  python3 scripts/corpus_fetch.py --module verbal --list

只读 Search/Fetch API，输出 JSON 到 data/manual-<module>-corpus/<today>/。
不修改任何现有出题链路。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / '.env'
SEARCH_URL = 'https://api.deepseek.com/v1/tools/search'
FETCH_URL = 'https://api.deepseek.com/v1/tools/fetch'
MIN_AUTHORITY = 3          # authority>=3 视为权威源
DEFAULT_COUNT = 6          # 每个检索词默认取 6 条
DEFAULT_TOPICS = {
    '科技': [['考古发现', '最新研究', '中国'], ['深海探测', '突破', '2025'], ['人工智能', '应用', '进展']],
    '文化': [['非遗', '传承', '数字化'], ['古籍', '修复', '保护'], ['博物馆', '展陈', '创新']],
    '经济': [['县域经济', '发展', '数据'], ['新型消费', '趋势', '调查'], ['中小企业', '创新', '报告']],
    '生态': [['湿地', '保护', '修复'], ['生物多样性', '调查', '中国'], ['蓝碳', '研究', '进展']],
}


def today() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()


def read_api_key() -> str:
    """从 .env 读取 DEEPSEEK_API_KEY（兼容 GB18030/UTF-8）。"""
    if not ENV_FILE.is_file():
        raise SystemExit(f'.env 不存在：{ENV_FILE}')
    raw = ENV_FILE.read_bytes()
    for enc in ('utf-8', 'gb18030', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit('.env 编码无法识别')
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('DEEPSEEK_API_KEY='):
            key = line.split('=', 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise SystemExit('.env 里没有 DEEPSEEK_API_KEY')


def search(key: str, query: str, count: int = DEFAULT_COUNT) -> list[dict]:
    body = json.dumps({'query': query, 'count': count, 'need_content': False}).encode('utf-8')
    req = urllib.request.Request(
        SEARCH_URL, data=body,
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8')).get('results', [])


def fetch(key: str, url: str) -> dict | None:
    body = json.dumps({'url': url}).encode('utf-8')
    req = urllib.request.Request(
        FETCH_URL, data=body,
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError:
        return None


def normalize_topics(topics_raw) -> dict[str, list[list[str]]]:
    if isinstance(topics_raw, dict):
        return topics_raw
    raise ValueError('题材清单必须是 {"题材": [["检索词1","检索词2"], ...]} 结构')


def main() -> int:
    ap = argparse.ArgumentParser(description='题材池检索脚本')
    ap.add_argument('--module', choices=['verbal', 'logic', 'ziliao'], default='verbal',
                    help='素材库模块：verbal=片段阅读, logic=逻辑判断, ziliao=资料分析')
    ap.add_argument('--topics', help='题材清单 JSON 字符串，如 {"科技":[["考古","最新"]]}')
    ap.add_argument('--topics-file', help='题材清单 JSON 文件路径')
    ap.add_argument('--count', type=int, default=DEFAULT_COUNT, help='每个检索词返回条数')
    ap.add_argument('--min-authority', type=int, default=MIN_AUTHORITY, help='最低权威度过滤')
    ap.add_argument('--fetch-body', action='store_true', help='额外用 Fetch API 抓正文（按 URL 去重）')
    ap.add_argument('--list', action='store_true', help='列出素材库已登记的主题指纹')
    ap.add_argument('--dry-run', action='store_true', help='只检索不写文件')
    args = ap.parse_args()

    if args.list:
        return list_topics(args.module)

    if args.topics and args.topics_file:
        raise SystemExit('--topics 与 --topics-file 只能二选一')
    if args.topics_file:
        with open(args.topics_file, encoding='utf-8') as f:
            topics = normalize_topics(json.load(f))
    elif args.topics:
        topics = normalize_topics(json.loads(args.topics))
    else:
        topics = DEFAULT_TOPICS

    key = read_api_key()
    out_dir = ROOT / f'data/manual-{args.module}-corpus' / today()
    out_dir.mkdir(parents=True, exist_ok=True)

    collected: dict[str, list[dict]] = {}
    seen_urls: set[str] = set()
    for category, queries in topics.items():
        collected.setdefault(category, [])
        for q in queries:
            query = ' '.join(q) + ' lang:zh'
            try:
                results = search(key, query, args.count)
            except urllib.error.HTTPError as e:
                print(f'[检索失败] {query}: HTTP {e.code}', file=sys.stderr)
                continue
            except Exception as e:  # noqa: BLE001
                print(f'[检索异常] {query}: {e}', file=sys.stderr)
                continue
            for r in results:
                url = r.get('url', '')
                authority = r.get('authority', -1)
                if authority < args.min_authority:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                item = {
                    'topic': category,
                    'query': query,
                    'title': r.get('title', ''),
                    'url': url,
                    'site': r.get('site_name'),
                    'date': r.get('date'),
                    'authority': authority,
                    'snippet': r.get('snippet', ''),
                    'summary': r.get('summary', ''),
                }
                collected[category].append(item)
            print(f'[{category}] {query} -> 已收 {len(collected[category])} 条', file=sys.stderr)

    if args.fetch_body:
        total = sum(len(v) for v in collected.values())
        done = 0
        for items in collected.values():
            for item in items:
                page = fetch(key, item['url'])
                if page:
                    item['content'] = page.get('content', '')
                done += 1
                print(f'  [fetch] {done}/{total} {item["title"][:20]}', file=sys.stderr)

    if args.dry_run:
        total = sum(len(v) for v in collected.values())
        print(json.dumps({'dry_run': True, 'total': total,
                          'categories': {k: len(v) for k, v in collected.items()}}, ensure_ascii=False))
        return 0

    manifest = {
        'module': args.module,
        'fetched_at': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        'count': sum(len(v) for v in collected.values()),
        'topics': topics,
        'results': collected,
    }
    out_file = out_dir / 'corpus.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f'素材已写入 {out_file}（共 {manifest["count"]} 条）')
    return 0


def list_topics(module: str) -> int:
    """列出素材库最近登记的主题指纹，供出题前避让参考。"""
    base = ROOT / f'data/manual-{module}-corpus'
    if not base.is_dir():
        print(f'素材库不存在：{base}')
        return 0
    seen: dict[str, str] = {}
    for day in sorted(base.iterdir(), reverse=True)[:14]:
        corpus = day / 'corpus.json'
        if not corpus.is_file():
            continue
        try:
            with open(corpus, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for cat, items in data.get('results', {}).items():
            for item in items:
                key = (item.get('title') or '')[:30]
                seen.setdefault(key, cat)
    print(f'=== {module} 素材库近 14 天主题（{len(seen)} 条）===')
    for title, cat in seen.items():
        print(f'  [{cat}] {title}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

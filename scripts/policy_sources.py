#!/usr/bin/env python3
"""Fetch official source snapshots; no model summaries are accepted as evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'hermes-skills/quiz-pipeline/references/policy-sources.json'
SOURCE_MODULES = {'政治理论', '常识判断'}
TRUSTED = ('gov.cn', 'qstheory.cn', '12371.cn', 'people.com.cn', 'xinhuanet.com',
           'news.cn', 'cas.cn', 'edu.cn', 'smartedu.cn')
MAX_BYTES = 4 * 1024 * 1024


def directory():
    return Path(os.environ.get('EXAM_POLICY_DIR') or ROOT / 'data/manual-policy-sources')


def today():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def trusted_url(url, resolve=False):
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or '').lower()
    if (p.scheme != 'https' or p.username or p.password or p.port not in (None, 443)
            or not any(host == d or host.endswith('.' + d) for d in TRUSTED)):
        raise ValueError('只接收权威机构 HTTPS 原文地址：' + str(url))
    if resolve:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('资料地址不得指向内网')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trusted_url(newurl, resolve=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.buf = [], [], []
        self.skip = 0
        self.anchor = None

    def flush(self):
        text = re.sub(r'\s+', ' ', ''.join(self.buf)).strip()
        if text:
            self.parts.append(text)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self.skip += 1
        if self.skip:
            return
        if tag in {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'tr'}:
            self.flush()
        if tag == 'a':
            self.anchor = [dict(attrs).get('href', ''), '']

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self.skip = max(0, self.skip - 1)
        if self.skip:
            return
        if tag in {'p', 'div', 'li', 'h1', 'h2', 'h3', 'tr'}:
            self.flush()
        if tag == 'a' and self.anchor:
            self.links.append(self.anchor)
            self.anchor = None

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)
            if self.anchor:
                self.anchor[1] += data


def fetch(url):
    trusted_url(url, resolve=True)
    request = urllib.request.Request(urllib.parse.quote(url, safe=':/?=&%+#'),
                                     headers={'User-Agent': 'ExamSystem source verification/1.0'})
    with urllib.request.build_opener(SafeRedirect).open(request, timeout=25) as response:
        trusted_url(response.url)
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('资料超过 4MB，请提供具体原文页面')
        if 'html' not in (response.headers.get('Content-Type') or '').lower():
            raise ValueError('目前只收可直接核验正文的 HTML 原文，不收搜索摘要或附件下载页')
        charset = response.headers.get_content_charset()
        if not charset:
            match = re.search(br'charset=["\x27]?([\w-]+)', raw[:6000], re.I)
            charset = match.group(1).decode() if match else 'utf-8'
        page = Page()
        page.feed(raw.decode(charset))
        page.flush()
        return page, response.url


def registry():
    entries = json.loads(CONFIG.read_text())['sources'] if CONFIG.exists() else []
    extra = directory() / 'registry.json'
    additions = json.loads(extra.read_text()) if extra.exists() else []
    return {v['id']: v for v in entries + additions}


def validate_spec(spec):
    from kaodian_taxonomy import validate_ai_primary_tag
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,79}', spec.get('id', '')):
        raise ValueError('source id 须为 2–80 位小写字母、数字、下划线或连字符')
    trusted_url(spec['url'])
    if not spec.get('title') or spec.get('kind') not in {'foundation', 'policy', 'law', 'event'}:
        raise ValueError('资料须注明 title 与 kind: foundation/policy/law/event')
    if not spec.get('tags') or not isinstance(spec['tags'], list):
        raise ValueError('资料须绑定已有知识点 tags')
    for tag in spec['tags']:
        if validate_ai_primary_tag(tag) != tag:
            raise ValueError('请使用规范知识点标签：' + tag)
    for name in ('published_at', 'effective_at', 'expires_at'):
        if spec.get(name):
            dt.date.fromisoformat(spec[name])
    if not spec.get('published_at') or dt.date.fromisoformat(spec['published_at']) > today():
        raise ValueError('必须提供已发布的日期，不可把未来文件作为依据')
    if spec.get('scope', 'as_published') not in {'as_published', 'current'}:
        raise ValueError('scope 须为 as_published 或 current')
    return spec


def refresh(spec):
    validate_spec(spec)
    page, url = fetch(spec['url'])
    paragraphs = list(dict.fromkeys(p for p in page.parts if len(p) >= 20))
    focus = spec.get('focus') or []
    if focus:
        paragraphs = [p for p in paragraphs if any(word in p for word in focus)]
    if not paragraphs or sum(map(len, paragraphs)) < 120:
        raise ValueError('原文提取不足，不能把空页或访问拦截当资料：' + spec['id'])
    full_text = '\n'.join(paragraphs)
    if sum(map(len, paragraphs)) > 60000:
        raise ValueError('原文过长，请在资料登记中用 focus 明确原文范围，不会静默截断')
    record = {**spec, 'url': url, 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'sha256': sha(full_text),
              'paragraphs': [{'id': 'p-' + sha(p)[:16], 'text': p} for p in paragraphs]}
    target = directory() / (spec['id'] + '.json')
    old = json.loads(target.read_text()) if target.exists() else None
    if old and old['sha256'] != record['sha256']:
        atomic_json(directory() / 'versions' / f"{spec['id']}-{old['sha256']}.json", old)
    atomic_json(target, record)
    return record


def add(spec):
    record = refresh(spec)
    path = directory() / 'registry.json'
    entries = {v['id']: v for v in json.loads(path.read_text())} if path.exists() else {}
    entries[spec['id']] = spec
    atomic_json(path, list(entries.values()))
    return record


def matches(spec, tag):
    return any(tag == t or tag.startswith(t + '-') or t.startswith(tag + '-') for t in spec['tags'])


def source_pack(slots, ids=None, as_of=None):
    cutoff = dt.date.fromisoformat(as_of) if as_of else today()
    if cutoff > today():
        raise ValueError('资料截止日不能在未来')
    entries = registry()
    selected = ids or list(dict.fromkeys(
        ident for slot in slots for ident, spec in entries.items() if matches(spec, slot['tag'])))
    if not selected or len(selected) > 8:
        raise ValueError('请先登记权威原文或用 --sources 选择 1–8 份相关资料')
    sources = []
    for ident in selected:
        if ident not in entries:
            raise ValueError('未登记资料：' + ident)
        spec = entries[ident]
        if dt.date.fromisoformat(spec['published_at']) > cutoff:
            continue
        if spec.get('expires_at') and dt.date.fromisoformat(spec['expires_at']) <= cutoff:
            continue
        if spec.get('superseded_by'):
            continue
        if spec.get('scope') == 'current' and spec.get('effective_at') and dt.date.fromisoformat(spec['effective_at']) > cutoff:
            continue
        path = directory() / (ident + '.json')
        cached = json.loads(path.read_text()) if path.exists() else None
        max_age = 7 if spec['kind'] == 'foundation' else 1
        fresh = cached and all(cached.get(k) == v for k, v in spec.items()) and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cached['checked_at'])).total_seconds() < max_age * 86400
        # Failure propagates. A stale cache is never silently relabeled as checked.
        record = cached if fresh else refresh(spec)
        sources.append(record)
    for slot in slots:
        if not any(matches(s, slot['tag']) for s in sources):
            raise ValueError('缺少此考点的有效原文，请先 sources add：' + slot['tag'])
    if sum(len(p['text']) for s in sources for p in s['paragraphs']) > 80000:
        raise ValueError('本批资料过多，请缩小考点或指定 --sources')
    pack = {'as_of': cutoff.isoformat(), 'sources': sources}
    validate_pack(pack)
    return pack


def validate_pack(pack):
    """Check saved source metadata and body integrity at generation and import."""
    cutoff = dt.date.fromisoformat(pack['as_of'])
    records = pack.get('sources')
    if cutoff > today() or not isinstance(records, list) or not 1 <= len(records) <= 8:
        raise ValueError('资料截止日期或份数无效')
    seen = set()
    for record in records:
        validate_spec(record)
        if record['id'] in seen:
            raise ValueError('资料ID重复')
        seen.add(record['id'])
        if (dt.date.fromisoformat(record['published_at']) > cutoff
                or record.get('superseded_by')
                or (record.get('expires_at') and dt.date.fromisoformat(record['expires_at']) <= cutoff)
                or (record.get('scope') == 'current' and record.get('effective_at')
                    and dt.date.fromisoformat(record['effective_at']) > cutoff)):
            raise ValueError('资料日期/效力不适用于本批口径')
        checked = dt.datetime.fromisoformat(record['checked_at'])
        if checked.tzinfo is None or checked > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
            raise ValueError('资料核验时间无效')
        paragraphs = record.get('paragraphs')
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ValueError('缺少资料原文')
        for p in paragraphs:
            if not isinstance(p, dict) or not isinstance(p.get('text'), str) or p.get('id') != 'p-' + sha(p['text'])[:16]:
                raise ValueError('原文段落标识与正文不一致')
        if sha('\n'.join(p['text'] for p in paragraphs)) != record.get('sha256'):
            raise ValueError('资料正文与摘要哈希不一致')


def citation_issues(checks, pack, question):
    """Require an independently verifiable citation for every option/statement."""
    keys = ['statement'] if question.get('question_type') == 'judge' else ['A', 'B', 'C', 'D']
    if (not isinstance(checks, list) or len(checks) != len(keys)
            or any(not isinstance(v, dict) or v.get('key') not in keys for v in checks)
            or len({v['key'] for v in checks}) != len(keys)):
        return ['逐项依据未覆盖全部选项/判断句']
    sources = {s['id']: s for s in pack['sources']}
    issues = []
    for check in checks:
        if type(check.get('valid')) is not bool or not str(check.get('reason') or '').strip():
            issues.append('逐项判断缺少明确真假或理由')
        citations = check.get('citations')
        if not isinstance(citations, list) or not citations:
            issues.append('每项必须有原文依据')
            continue
        for cite in citations:
            if not isinstance(cite, dict):
                issues.append('引用格式错误')
                continue
            source = sources.get(cite['source_id']) if isinstance(cite.get('source_id'), str) else None
            paragraph = next((p['text'] for p in source['paragraphs'] if p['id'] == cite.get('paragraph_id')), '') if source else ''
            quote = cite.get('quote')
            if not isinstance(quote, str) or not 12 <= len(quote.strip()) <= 200 or quote not in paragraph:
                issues.append('引用片段不存在或过短，无法核验')
    if not issues:
        selected = ''.join(sorted(v['key'] for v in checks if v['valid']))
        if keys == ['statement']:
            selected = 'A' if checks[0]['valid'] else 'B'
        if selected != question.get('answer'):
            issues.append('逐项核验结论与答案不一致')
    return issues


def evidence_for(question, checks, pack):
    used = {c['source_id'] for item in checks for c in item['citations']}
    sources = [{k: s.get(k) for k in ('id', 'url', 'title', 'published_at', 'effective_at', 'scope', 'sha256', 'checked_at')}
               for s in pack['sources'] if s['id'] in used]
    claims = sorted({c['source_id'] + ':' + c['paragraph_id'] for item in checks for c in item['citations']})
    return {'as_of': pack['as_of'], 'sources': sources, 'checks': checks,
            'claim_ids': claims, 'question_type': question['question_type']}


def evidence_status(evidence):
    """Only mark changed cited passages, preserving unaffected historical knowledge."""
    outdated, unchecked = [], []
    specs = registry()
    for source in evidence.get('sources', []):
        path = directory() / (source['id'] + '.json')
        if not path.exists():
            unchecked.append(source['id'])
            continue
        current = json.loads(path.read_text())
        spec = specs.get(source['id'], current)
        if spec.get('superseded_by') or (spec.get('expires_at') and spec['expires_at'] <= today().isoformat()):
            outdated.append(source['id'])
        elif current['sha256'] != source['sha256']:
            claims = [c for item in evidence.get('checks', []) for c in item['citations'] if c['source_id'] == source['id']]
            text = '\n'.join(p['text'] for p in current['paragraphs'])
            if any(c['quote'] not in text for c in claims):
                outdated.append(source['id'])
        max_age = 7 if spec.get('kind') == 'foundation' else 1
        if (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(current['checked_at'])).total_seconds() >= max_age * 86400:
            unchecked.append(source['id'])
    return {'outdated': outdated, 'unchecked': unchecked}


def discover():
    config = json.loads(CONFIG.read_text())
    found, errors = {}, []
    for url in config.get('watch_pages', []):
        try:
            page, final = fetch(url)
            for href, title in page.links:
                if len(title.strip()) < 10 or not any(term in title for term in config['watch_terms']):
                    continue
                link = urllib.parse.urljoin(final, href)
                try:
                    trusted_url(link)
                except ValueError:
                    continue
                found[link] = {'url': link, 'title': title.strip(), 'status': 'candidate_unverified'}
        except Exception as exc:
            errors.append({'url': url, 'error': str(exc)})
    result = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'candidates': list(found.values()), 'errors': errors}
    atomic_json(directory() / 'candidates.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    add_p = sub.add_parser('add'); add_p.add_argument('spec', help='@JSON文件或JSON对象；不接受手写正文')
    sub.add_parser('refresh')
    sub.add_parser('discover')
    sub.add_parser('status')
    args = parser.parse_args()
    if args.command == 'add':
        raw = Path(args.spec[1:]).read_text() if args.spec.startswith('@') else args.spec
        result = add(json.loads(raw)); print(json.dumps({k: result[k] for k in ('id', 'title', 'checked_at', 'sha256')}, ensure_ascii=False))
    elif args.command == 'discover':
        print(json.dumps(discover(), ensure_ascii=False))
    elif args.command == 'refresh':
        results = []
        for spec in registry().values():
            try:
                row = refresh(spec); results.append({'id': row['id'], 'ok': True, 'checked_at': row['checked_at']})
            except Exception as exc:
                results.append({'id': spec['id'], 'ok': False, 'error': str(exc)})
        atomic_json(directory() / 'refresh-status.json', results)
        discovery = discover()
        print(json.dumps(results, ensure_ascii=False))
        return 0 if all(r['ok'] for r in results) and not discovery['errors'] else 1
    else:
        rows = []
        for spec in registry().values():
            path = directory() / (spec['id'] + '.json')
            saved = json.loads(path.read_text()) if path.exists() else {}
            rows.append({**spec, 'checked_at': saved.get('checked_at'), 'sha256': saved.get('sha256')})
        print(json.dumps({'sources': rows, 'candidates_file': str(directory() / 'candidates.json')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

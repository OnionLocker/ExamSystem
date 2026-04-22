#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 UTF-8 文件被错误地 "按 GBK 读取 → 按 UTF-8 写回" 导致的双重编码。

用法：
    python3 scripts/fix-mojibake.py <文件1> [<文件2> ...]
    python3 scripts/fix-mojibake.py --all        # 扫描整个项目
    python3 scripts/fix-mojibake.py --dry-run <文件>   # 仅预览，不写回

算法：
    1) 读入 UTF-8 文本。
    2) 逐段扫描连续 CJK 字符。
    3) 对每段尝试反向还原： text.encode('gbk').decode('utf-8')
    4) 仅当还原结果也是合法 CJK 文本时才替换（避免误伤原本就正确的 UTF-8 中文）。

备份：
    修复前会在同目录生成 .bak 文件。
"""
from __future__ import annotations
import argparse
import os
import re
import shutil
import sys

CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffef]+')

SAFE_EXT = {'.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.md',
            '.json', '.sql', '.env', '.yml', '.yaml'}
SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', '.cache', 'data', 'public'}


def try_reverse(seg: str) -> tuple[bool, str]:
    if not seg:
        return False, seg
    try:
        gbk_bytes = seg.encode('gbk')
    except UnicodeEncodeError:
        return False, seg
    try:
        recovered = gbk_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return False, seg
    bad = 0
    for c in recovered:
        if '\u4e00' <= c <= '\u9fff':
            continue
        if c in '，。！？、：；""\'\'…—《》（）()·•【】':
            continue
        if c in ' \t\r\n':
            continue
        if ord(c) < 128:
            continue
        bad += 1
    if bad > max(1, len(recovered) // 5):
        return False, seg
    return True, recovered


def fix_text(text: str) -> tuple[str, int]:
    out = []
    last = 0
    changed = 0
    for m in CJK_RE.finditer(text):
        out.append(text[last:m.start()])
        seg = m.group()
        ok, recovered = try_reverse(seg)
        if ok and recovered != seg:
            out.append(recovered)
            changed += 1
        else:
            out.append(seg)
        last = m.end()
    out.append(text[last:])
    return ''.join(out), changed


def process_file(path: str, dry_run: bool = False) -> bool:
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        text = raw.decode('utf-8')
    except (UnicodeDecodeError, OSError) as e:
        print(f'SKIP  {path}: {e}', file=sys.stderr)
        return False

    fixed, n = fix_text(text)
    if n == 0:
        print(f'OK    {path}')
        return False

    print(f'FIXED {path}: {n} segment(s) reverted')
    if dry_run:
        return True
    shutil.copy2(path, path + '.bak')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(fixed)
    return True


def walk_project(root: str):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in fns:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SAFE_EXT:
                yield os.path.join(dp, fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--all', action='store_true', help='扫描整个项目（当前工作目录）')
    ap.add_argument('--dry-run', action='store_true', help='只预览，不写回')
    args = ap.parse_args()

    if args.all:
        paths = list(walk_project(os.getcwd()))
    else:
        paths = args.paths
    if not paths:
        ap.print_help()
        sys.exit(1)

    any_fixed = False
    for p in paths:
        if process_file(p, dry_run=args.dry_run):
            any_fixed = True
    sys.exit(0 if any_fixed or not args.dry_run else 0)


if __name__ == '__main__':
    main()

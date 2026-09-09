#!/usr/bin/env python3
"""Run the real generation chain and persist per-module timings and failures."""
import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

import daily_gemini_batch as generator
import quiz_generator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--module', action='append', help='Only run these modules')
    parser.add_argument('--repeat', type=int, default=1)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    original_draft = generator.call_gemini
    original_command = generator.run_cmd
    original_open = generator.urllib.request.urlopen
    planned = [('科学推理', 5)] * max(1, args.repeat) if args.module == ['科学推理'] else [
        ('言语理解与表达', 15), ('判断推理', 20), ('科学推理', 5),
        ('数量关系', 15), ('资料分析', 20),
    ]
    for index, (module, count) in enumerate(planned, 1):
        if args.module and module not in args.module:
            continue
        batch_id = f'{args.output.name}-{index}'
        metrics = dict(module=module, count=count, batch_id=batch_id,
                       draft_calls=0, http_calls=0, gate_attempts=0, gate_rejections=0, errors=[])

        def draft(*a, **kw):
            metrics['draft_calls'] += 1
            return original_draft(*a, **kw)

        def request(*a, **kw):
            metrics['http_calls'] += 1
            return original_open(*a, **kw)

        def command(cmd, *a, **kw):
            is_gate = str(generator.GATE_SCRIPT) in cmd
            metrics['gate_attempts'] += int(is_gate)
            try:
                return original_command(cmd, *a, **kw)
            except RuntimeError as exc:
                metrics['gate_rejections'] += int(is_gate)
                metrics['errors'].append(str(exc)[:2000])
                raise

        generator.call_gemini, generator.run_cmd = draft, command
        generator.urllib.request.urlopen = request
        sys.argv = ['quiz_generator.py', '--module', module, '--count', str(count),
                    '--batch-id', batch_id, '--output-dir', str(args.output),
                    '--timeout', str(args.timeout), '--interactive']
        started = time.monotonic()
        print(f'Start {module}: {batch_id}', flush=True)
        with (args.output / f'{batch_id}.log').open('w') as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                try:
                    metrics['exit_code'] = quiz_generator.main()
                except Exception as exc:
                    metrics['exit_code'] = 1
                    metrics['errors'].append(f'{type(exc).__name__}: {exc}')
        metrics['elapsed_sec'] = round(time.monotonic() - started, 2)
        for line in (args.output / f'{batch_id}.log').read_text().splitlines():
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict) and result.get('status') == 'error':
                metrics['errors'].append(result.get('error', 'unknown failure'))
        quality = args.output / quiz_generator.local_today().isoformat() / batch_id / 'evidence/system-quality.json'
        metrics['quality'] = json.loads(quality.read_text()) if quality.exists() else None
        metrics['imported'] = metrics['exit_code'] == 0
        results.append(metrics)
        (args.output / 'metrics.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(json.dumps({k: v for k, v in metrics.items() if k != 'quality'}, ensure_ascii=False), flush=True)
    generator.call_gemini, generator.run_cmd = original_draft, original_command
    generator.urllib.request.urlopen = original_open


if __name__ == '__main__':
    main()

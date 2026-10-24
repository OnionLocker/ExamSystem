#!/usr/bin/env python3
"""灵活出题：Hermes 与 DSH 共用。

只接受数量关系、言语理解、判断推理里的逻辑判断、资料分析。
资料分析是一篇材料、N 题（1–10）；点名考法变式后，这一篇全部是该变式。
文字题 Hermes 调 quiz_lite 写完；DSH 只拿同一份槽位，自己写题。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "数量关系": "数量关系", "数量": "数量关系", "数量速推": "数量关系",
    "言语理解与表达": "言语理解与表达", "言语理解": "言语理解与表达", "言语": "言语理解与表达",
    "判断推理": "判断推理", "逻辑判断": "判断推理", "逻辑推理": "判断推理", "文字逻辑": "判断推理",
    "资料分析": "资料分析", "资料": "资料分析",
}
BLOCKED = ("图形推理", "定义判断", "类比推理", "科学推理")


def resolve_module(name: str) -> str:
    key = re.sub(r"\s+", "", name or "")
    if key not in ALIASES:
        raise SystemExit("模块只能是数量关系、言语理解、逻辑判断、资料分析")
    return ALIASES[key]


def resolve_ziliao_point(point: str) -> str:
    from kaodian_taxonomy import KNOWN_ZILIAO_TAGS, ZILIAO_METHOD_TAGS
    text = point.strip()
    usable = KNOWN_ZILIAO_TAGS - ZILIAO_METHOD_TAGS
    if text in usable:
        return text
    hits = [tag for tag in sorted(usable) if text and (text == tag.split("-")[-1] or text in tag)]
    if len(hits) == 1:
        return hits[0]
    if text in ZILIAO_METHOD_TAGS:
        raise SystemExit(f"{text} 是速算方法，不是出题知识点")
    shown = "、".join(tag.split("-", 1)[-1] for tag in sorted(usable))
    raise SystemExit(f"资料知识点「{point}」无法唯一对应。可选：{shown}")


def last_json(text: str) -> dict:
    """流水线把摘要印成多行 JSON。取最后一个带批次结果的对象。"""
    decoder = json.JSONDecoder()
    found = {}
    start = 0
    while True:
        mark = text.find("{", start)
        if mark < 0:
            return found
        try:
            value, end = decoder.raw_decode(text, mark)
        except json.JSONDecodeError:
            start = mark + 1
            continue
        if isinstance(value, dict) and any(key in value for key in ("passed", "status", "batch_id")):
            found = value
        start = mark + end


def run(cmd: list[str]) -> tuple[int, str, str, dict]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode, proc.stdout, proc.stderr, last_json(proc.stdout)


def finish(status: str, batch_id: str, imported: int, module: str, point: str, variant: str, count: int) -> int:
    print(json.dumps({
        "status": status, "batch_id": batch_id, "imported": imported,
        "module": module, "point": point, "variant": variant, "count": count,
    }, ensure_ascii=False))
    return 0 if status in {"success", "planned"} else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--point", required=True, help="知识点，可写简称，如 统计术语、削弱题型")
    parser.add_argument("--variant", default="", help="考法变式名称或 id；省略则在该知识点内自行分配")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--actor", choices=("hermes", "dsh"), default="hermes")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--import", dest="import_batch", action="store_true")
    parser.add_argument("--difficulty", default="")
    parser.add_argument("--format", default="", help="仅资料：text/table/chart/饼图等")
    parser.add_argument("--focus", choices=("weak",))
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "exam.db")
    args = parser.parse_args()
    if any(word in args.point for word in BLOCKED):
        raise SystemExit("这条指令不出图形推理、定义判断、类比推理和科学推理")
    module = resolve_module(args.module)
    stamp = dt.date.today().strftime("%Y%m%d")
    slug = re.sub(r"[^\w]+", "", args.variant or args.point)[:16] or "drill"
    batch_id = args.batch_id or f"{stamp}_{args.actor}_gm_{slug}_{uuid.uuid4().hex[:6]}"
    if module == "资料分析":
        if not 1 <= args.count <= 10:
            raise SystemExit("资料分析一篇的题量是 1–10")
        tag = resolve_ziliao_point(args.point)
        cmd = [sys.executable, str(ROOT / "scripts" / "ziliao_material_pipeline.py"),
               "--tag", tag, "--count", str(args.count), "--one-paper",
               "--batch-id", batch_id, "--db", str(args.db),
               "--output-dir", str(ROOT / "data" / "manual-ziliao-material")]
        if args.variant:
            cmd += ["--variant", args.variant]
        if args.format:
            cmd += ["--format", args.format]
        if args.difficulty:
            cmd += ["--difficulty", args.difficulty]
        if args.plan_only:
            cmd.append("--plan-only")
        elif args.import_batch:
            cmd.append("--import")
        code, _, _, payload = run(cmd)
        imported = int(payload.get("imported") or 0)
        if args.plan_only:
            status = "planned" if code == 0 else "error"
        else:
            status = "success" if code == 0 and payload.get("passed") is True else "error"
        return finish(status, str(payload.get("batch_id") or batch_id), imported, module, tag, args.variant, args.count)

    if not 1 <= args.count <= 15:
        raise SystemExit("文字题题量是 1–15")
    plan_only = args.plan_only or args.actor == "dsh"
    cmd = [sys.executable, str(ROOT / "scripts" / "quiz_lite.py"),
           "--module", module, "--tag", args.point, "--count", str(args.count),
           "--batch-id", batch_id, "--db", str(args.db)]
    if args.variant:
        cmd += ["--variant", args.variant]
    if args.focus:
        cmd += ["--focus", args.focus]
    if args.difficulty:
        cmd += ["--difficulty", args.difficulty]
    if plan_only:
        cmd.append("--plan-only")
    elif not args.import_batch:
        cmd.append("--no-import")
    code, _, _, payload = run(cmd)
    slots = payload.get("slots") or []
    if module == "判断推理" and slots and any(not str(slot.get("tag") or "").startswith("判断推理-逻辑判断") for slot in slots):
        raise SystemExit("逻辑判断专项只能出「判断推理-逻辑判断」下的知识点")
    imported = int(payload.get("imported") or 0)
    if plan_only:
        status = "planned" if code == 0 else "error"
        if args.actor == "dsh" and not args.plan_only and code == 0:
            print("DSH 文字题请按上面 slots 的 kaofa_variant_name 自己写题并走审核，不要调用出题模型。", file=sys.stderr)
    else:
        status = "success" if code == 0 and payload.get("status") == "success" else "error"
    return finish(status, str(payload.get("batch_id") or batch_id), imported, module, args.point, args.variant, args.count)


if __name__ == "__main__":
    raise SystemExit(main())

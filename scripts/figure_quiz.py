#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""带图题专项出题：程序生成题目结构 → 只从结构画图 → 独立判题器只看图核对 → 签收据 → 入库。

不调用任何模型，题图、答案、解析都由题型族程序给出（见 scripts/figure_families/）。
Hermes 不直接调这个脚本：quiz_lite.py 收到带图考点时会转到这里，参数完全一样。

用法：
  python3 scripts/figure_quiz.py --tag '判断推理-图形推理-空间类-六面体' --count 5 --batch-id 20261015_hermes_六面体_01
  python3 scripts/figure_quiz.py --tag '判断推理-图形推理-空间类' --count 5 ...   # 空间类各题型轮着出
  python3 scripts/figure_quiz.py --module '科学推理' --count 5 ...               # 科学推理各题型轮着出
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scheduler_common import DB, ROOT, local_today  # noqa: E402
from service_node import service_node  # noqa: E402

MAX_COUNT = 15
MODULE_SCOPES = {"判断推理": "判断推理-图形推理", "科学推理": "科学推理"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scope_families(tag: str) -> list:
    """考点或范围 -> 题型族列表。精确题型族优先；父级范围（如 空间类、科学推理-电学）展开成其下全部题型族。"""
    tag = (tag or "").strip()
    fams = list(families().values())
    exact = [f for f in fams if f.TAG == tag]
    if exact:
        return exact
    return [f for f in fams if f.TAG.startswith(tag + "-")]


def scope_title(tag: str, fams: list) -> str:
    if len(fams) == 1 and fams[0].TAG == tag:
        return fams[0].TITLE
    parts = tag.split("-")
    if tag.startswith("科学推理"):
        return "-".join(parts[1:]) or "科学推理"
    return "-".join(parts[2:]) or (parts[1] if len(parts) > 1 else tag)


def requested_tags(args, routing: bool = False) -> list[tuple[str, int, str | None]]:
    """routing=True 是 quiz_lite 转发判断用：只认显式考点，模块名只把「科学推理」整体当带图题。"""
    if args.blueprint:
        text = args.blueprint.strip()
        if text.startswith("@"):
            text = Path(text[1:]).expanduser().read_text(encoding="utf-8")
        data = json.loads(text)
        raw = data.get("slots") if isinstance(data, dict) else data
        if not isinstance(raw, list) or not raw:
            raise ValueError("blueprint 需要非空的 slots 列表")
        return [(str(s.get("tag") or ""), s.get("count"), s.get("difficulty")) for s in raw]
    scopes = {"科学推理": "科学推理"} if routing else MODULE_SCOPES
    tag = args.tag or scopes.get(args.module or "", "")
    count = args.count if args.count is not None else 5
    return [(tag, count, args.difficulty)] if tag else []


def is_figure_request(args) -> bool:
    """quiz_lite 用：这个请求是不是带图题。部分带图、部分文字的请求直接报错，不混出。"""
    try:
        tags = [tag for tag, _, _ in requested_tags(args, routing=True)]
    except (ValueError, json.JSONDecodeError):
        return False
    hits = [bool(scope_families(tag)) for tag in tags]
    if any(hits) and not all(hits):
        raise ValueError("带图题和文字题请分两批出：同一批只能全是带图题型或全是文字题")
    return bool(tags) and all(hits)


def plan(args) -> tuple[str, list[dict]]:
    slots = []
    requested = requested_tags(args)
    if not requested:
        raise ValueError("需要 --tag、--blueprint，或 --module 判断推理/科学推理")
    for index, (tag, count, difficulty) in enumerate(requested):
        fams = scope_families(tag)
        if not fams:
            raise ValueError(f"不是程序出图支持的题型：{tag}")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("槽位 count 须为正整数")
        if difficulty not in (None, "", "auto", *TIERS):
            raise ValueError("difficulty 须为 easy / mid / hard / auto")
        title = scope_title(tag, fams)
        offset = index
        for k in range(count):
            fam = fams[(offset + k) % len(fams)]
            slots.append({"tag": fam.TAG, "count": 1, "difficulty": difficulty or "auto", "family": fam.NAME,
                          "scope_title": title})
    modules = {families()[s["family"]].CATEGORY for s in slots}
    if len(modules) != 1:
        raise ValueError(f"一个批次只能一个模块，收到 {sorted(modules)}")
    merged: list[dict] = []
    for slot in slots:  # 相邻同题型合并成一个槽，保持出题顺序
        if merged and all(merged[-1][k] == slot[k] for k in ("tag", "difficulty", "family", "scope_title")):
            merged[-1]["count"] += 1
        else:
            merged.append(dict(slot))
    return modules.pop(), merged


def balanced_letters(n: int, rng: random.Random) -> list[str]:
    letters = []
    while len(letters) < n:
        block = list(LETTERS)
        rng.shuffle(block)
        letters += block
    return letters[:n]


def difficulty_label(slots: list[dict]) -> str:
    tiers = {s["difficulty"] for s in slots}
    return next(iter(tiers)) if len(tiers) == 1 and next(iter(tiers)) in TIERS else "auto"


def build(module: str, slots: list[dict], batch_id: str, batch_dir: Path, source: str, progress=None) -> tuple[list, list]:
    fams = families()
    total = sum(s["count"] for s in slots)
    rng = random.Random(f"letters|{batch_id}")
    letters = balanced_letters(total, rng)
    (batch_dir / "images").mkdir(parents=True, exist_ok=True)
    (batch_dir / "figures").mkdir(parents=True, exist_ok=True)
    questions, results = [], []
    index = 0
    for slot in slots:
        fam = fams[slot["family"]]
        for _ in range(slot["count"]):
            index += 1
            qid = f"{batch_id}-{index:02d}"
            seed = f"{batch_id}|{index}"
            started = time.monotonic()
            item = make_item(fam, seed, slot["difficulty"], letters[index - 1])
            parts = [part for part in fam.PARTS if part in item["svgs"]]
            for part in parts:
                svg_rel, png_rel = part_paths(qid, part)
                (batch_dir / svg_rel).write_text(item["svgs"][part], encoding="utf-8")
                (batch_dir / png_rel).write_bytes(item["pngs"][part])
            questions.append({
                "external_id": qid,
                "category": fam.CATEGORY,
                "sub_category": fam.SUB_CATEGORY,
                "tags": [fam.TAG],
                "question_type": "single",
                "stem": item["draft"]["stem"],
                "stem_images": [part_paths(qid, part)[1] for part in parts],
                "options": [{"key": letter, "text": text} for letter, text in zip(LETTERS, item["option_texts"])],
                "answer": letters[index - 1],
                "explanation": item["explanation"],
                "difficulty": int(item["draft"]["difficulty"]),
                "source": source,
                "figure": {"family": fam.NAME, "version": fam.VERSION, "seed": seed, "attempt": item["attempt"],
                           "parts": parts},
            })
            results.append({"question_id": qid, "family": fam.NAME, "family_version": fam.VERSION,
                            "seed": seed, "attempt": item["attempt"], "rejected_drafts": item["rejected"],
                            "correct": item["verdict"].get("correct"), "issues": [],
                            "seconds": round(time.monotonic() - started, 2)})
            if progress:
                progress(stage="出题", detail=f"第 {index}/{total} 题（{fam.TITLE}）", passed=index,
                         progress=5 + int(80 * index / total), status="running")
    return questions, results


def write_manifest(batch_dir: Path, batch_id: str, source: str, slots: list[dict], questions: list[dict], scope: str) -> None:
    from generation_gate import FIGURE_VERSION

    counts: dict[str, int] = {}
    for q in questions:
        counts[q["answer"]] = counts.get(q["answer"], 0) + 1
    tag_counts: dict[str, int] = {}
    for q in questions:
        tag_counts[q["tags"][0]] = tag_counts.get(q["tags"][0], 0) + 1
    manifest = {
        "batch_id": batch_id,
        "source": source,
        "region": "广东-省直",
        "year": local_today().year,
        "kind": "ai-generated",
        "difficulty_tier": difficulty_label(slots),
        "generation": {
            "style_marker": "GONGKAO-STYLE-v1",
            "pipeline": "figure_quiz",
            "figure_version": FIGURE_VERSION,
            "requested_scope": scope,
            "batch_constraints": {
                "all_original": True,
                "question_count": len(questions),
                "targeted_drill": True,
                "image_dependent_count": {"min": len(questions), "max": len(questions)},
                "answer_max_per_letter": max(counts.values()),
                "answer_min_letters": len(counts),
                "tag_counts": tag_counts,
                "slot_plan": slots,
            },
            "generation_contexts": [],
            "evaluation_contexts": [],
        },
    }
    (batch_dir / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (batch_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sign(batch_dir: Path, batch_id: str, questions: list[dict], results: list[dict]) -> None:
    """签发前再审一遍落盘的文件（判题器只看文件），全过才写收据。"""
    from generation_gate import FIGURE_VERSION, RECEIPT, artifact_digests

    issues = audit_batch(batch_dir, questions)
    if issues:
        raise RuntimeError("落盘后复审不过：" + "；".join(issues[:6]))
    evidence = {
        "version": 1,
        "kind": "examsystem-figure-audit",
        "batch_id": batch_id,
        "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "questions_sha256": _digest(batch_dir / "questions.json"),
        "results": results,
    }
    evidence_path = batch_dir / "evidence" / "figure-audit.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "version": FIGURE_VERSION,
        "batch_id": batch_id,
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha256": _digest(batch_dir / "manifest.json"),
        "questions_sha256": _digest(batch_dir / "questions.json"),
        "question_ids": [q["external_id"] for q in questions],
        "artifacts": {**artifact_digests(batch_dir), **figure_digests(batch_dir, questions)},
        "figure_audit": {"path": str(evidence_path.relative_to(batch_dir)), "sha256": _digest(evidence_path)},
    }
    (batch_dir / RECEIPT).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def register_tags(slots: list[dict], db: Path) -> None:
    """题型族的子考点先登记定义，validate_ai_primary_tag 才认；不制造作答记录。"""
    from fenbi_taxonomy import parse_fenbi_tag
    from kaodian_profile import ensure_schema, register_knowledge_point

    fams = families()
    with sqlite3.connect(db, timeout=30) as conn:
        ensure_schema(conn)
        for slot in slots:
            fam = fams[slot["family"]]
            parsed = parse_fenbi_tag(fam.TAG)
            if not parsed or not parsed[3]:
                continue  # 粉笔三级或科学推理标签本身就合法
            row = conn.execute("SELECT definition FROM kaodian_profile WHERE kaodian=?", (fam.TAG,)).fetchone()
            if not row or row[0] != fam.DEFINITION:
                register_knowledge_point(conn, fam.TAG, parsed[0], parsed[1], fam.DEFINITION)


def import_batch(batch_dir: Path, db: Path, batch_id: str) -> int:
    env = {**os.environ, "EXAM_DB": str(db)}
    result = subprocess.run([service_node(), str(ROOT / "scripts" / "import-batch.mjs"), str(batch_dir)], cwd=ROOT, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "import failed").strip()[-2000:])
    with sqlite3.connect(db, timeout=30) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM questions WHERE batch_id=?", (batch_id,)).fetchone()[0])


def run(args) -> int:
    started = time.monotonic()
    os.environ["EXAM_DB"] = str(args.db)
    batch_dir = None
    tracked = finished = False
    try:
        module, slots = plan(args)
        total = sum(s["count"] for s in slots)
        if not 1 <= total <= MAX_COUNT:
            raise ValueError(f"带图题专项题量须为 1–{MAX_COUNT}")
        from quiz_scope import source_name

        today = local_today()
        source = source_name(module, slots, today)
        if args.plan_only:
            print(json.dumps({"status": "planned", "module": module, "slots": slots, "count": total, "source": source},
                             ensure_ascii=False))
            return 0
        batch_dir = args.output_dir / today.isoformat() / args.batch_id
        if batch_dir.exists() and any(batch_dir.iterdir()):
            raise ValueError("批次目录已有产物，不能覆盖旧证据；请使用新的 batch_id")
        with sqlite3.connect(args.db, timeout=30) as conn:
            try:
                exists = int(conn.execute("SELECT COUNT(*) FROM questions WHERE batch_id=?", (args.batch_id,)).fetchone()[0])
            except sqlite3.OperationalError:
                exists = 0
        if exists:
            raise RuntimeError(f"batch_id 已入库 {exists} 题，换一个序号")
        from generation_progress import report

        def tick(**kwargs):
            nonlocal tracked, finished
            if finished:
                return
            tracked = True
            if kwargs.get("status") in ("done", "failed"):
                finished = True
            report(args.batch_id, module=module, title=source, planned=total, **kwargs)

        tick(stage="准备出题", detail=f"共 {total} 题（程序出图）", progress=2, passed=0, status="running")
        batch_dir.mkdir(parents=True, exist_ok=True)
        questions, results = build(module, slots, args.batch_id, batch_dir, source, progress=tick)
        write_manifest(batch_dir, args.batch_id, source, slots, questions, args.tag or args.module or "")
        tick(stage="复审签收", detail="判题器重新读图核对", passed=total, progress=88, status="running")
        sign(batch_dir, args.batch_id, questions, results)
        register_tags(slots, args.db)
        from generation_gate import verify

        verify(batch_dir)
        if args.no_import:
            imported = 0
            tick(status="done", stage="已通过", detail=f"已出题 {total} 题，未入库", passed=total, progress=100)
        else:
            tick(stage="入库", detail="正在写入题库", passed=total, progress=95, status="running")
            imported = import_batch(batch_dir, args.db, args.batch_id)
            tick(status="done", stage="已入库", detail=f"已入库 {imported} 题", passed=total, progress=100)
        print(json.dumps({
            "status": "success", "batch_id": args.batch_id, "imported": imported, "batch_dir": str(batch_dir),
            "pipeline": "figure_quiz", "slots": slots, "source": source,
            "families": sorted({s["family"] for s in slots}),
            "redrafts": sum(len(r["rejected_drafts"]) for r in results),
            "seconds": round(time.monotonic() - started, 1),
            "message": f"已{'出题' if args.no_import else '入库'} {total} 题（程序出图、判题器复核），批次 {args.batch_id}",
        }, ensure_ascii=False))
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        if tracked and not finished:
            from generation_progress import report

            report(args.batch_id, status="failed", stage="失败", error=str(exc), detail=str(exc)[:160])
        print(json.dumps({"status": "error", "batch_id": args.batch_id,
                          "batch_dir": str(batch_dir) if batch_dir else None, "error": str(exc)[:2000],
                          "seconds": round(time.monotonic() - started, 1),
                          "message": f"出题失败：{str(exc)[:600]}"}, ensure_ascii=False))
        return 1


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="带图题专项出题（程序出图 + 独立判题器）")
    parser.add_argument("--module", default="", help="判断推理 / 科学推理")
    parser.add_argument("--tag", help="题型族标签或父级范围，如 判断推理-图形推理-空间类-六面体、判断推理-图形推理-空间类")
    parser.add_argument("--count", type=int)
    parser.add_argument("--blueprint", help='{"slots":[{"tag":"...","count":3,"difficulty":"mid"}]}，内联 JSON 或 @路径')
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--difficulty", choices=["easy", "mid", "hard", "auto"])
    parser.add_argument("--rounds", type=int, default=3, help="兼容 quiz_lite 参数，程序出图不用")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "hermes-batches")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--no-import", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args(argv)


def list_families() -> list[dict]:
    return [{"tag": f.TAG, "title": f.TITLE, "module": f.CATEGORY, "family": f.NAME} for f in families().values()]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        print(json.dumps(list_families(), ensure_ascii=False, indent=2))
        raise SystemExit(0)
    raise SystemExit(run(parse_args()))

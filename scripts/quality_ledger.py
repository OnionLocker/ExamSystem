#!/usr/bin/env python3
"""质检打回账本：记 class，不记长文。"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "data" / "quality-ledger" / "rejects.jsonl"

CLASSES = (
    "fig_missing_label",
    "fig_no_intersection",
    "fig_extra_object",
    "fig_kind_mismatch",
    "fig_leak_answer",
    "fig_low_res",
    "notation_stem_mismatch",
    "giveaway_extreme",
    "empty_analysis",
    "echo_given",
    "flash_visual_missing",
    "flash_quality",
    "flash_correct",
    "paper_rules",
    "other",
)

NO_PROMOTE = frozenset({"flash_visual_missing"})

CHECKERS = {
    "fig_missing_label": "figure_qa.check_question",
    "fig_no_intersection": "figure_qa.check_question",
    "fig_extra_object": "figure_qa.check_question",
    "fig_kind_mismatch": "figure_qa.check_question",
    "fig_leak_answer": "figure_qa.check_question",
    "fig_low_res": "figure_qa.check_question",
    "notation_stem_mismatch": "quality_orchestrator.notation_stem_issues",
    "giveaway_extreme": "quality_orchestrator.giveaway_extreme_issues",
    "empty_analysis": "quality_orchestrator.local_quality_issues",
    "echo_given": "quality_orchestrator.translation_echo_issues",
}

MUST_FIX = {
    "fig_missing_label": "图上必须出现题干/清单里的甲乙、①–⑤、轴标，禁止缺标号。",
    "fig_no_intersection": "清单要求交点时折线必须相交，刻度要能读出交点坐标。",
    "fig_extra_object": "图上不得多画清单/题干没有的铁块、木块、草兔等。",
    "fig_kind_mismatch": "锋面用剖面、等高线用平面图、反射弧不得配食物网。",
    "fig_leak_answer": "图上不得写出冷锋/感受器等 must_derive。",
    "fig_low_res": "题图至少 1400x500，字号至少 20。",
    "notation_stem_mismatch": "题干用甲乙则解析/选项不得改用 ρ_A、液体A。",
    "giveaway_extreme": "错项禁止「一定是/必然/唯一」等送分绝对词。",
    "empty_analysis": "每题必须有解析。",
    "echo_given": "翻译推理正确项不得复述已知实例。",
    "flash_visual_missing": "看图审核未通过（噪声，不升级成规则）。",
    "flash_quality": "质量盲审未过：事实闭环、答案唯一、干扰可诊断。",
    "flash_correct": "正确性/看图答案不唯一或与键不一致。",
    "paper_rules": "卷面结构/答案字母/模块配比硬规则未满足。",
    "other": "未命名失败，先修本题，禁止据此追加长 R 条目。",
}

LAYER_FOR = {
    "fig_missing_label": "figure_qa",
    "fig_no_intersection": "figure_qa",
    "fig_extra_object": "figure_qa",
    "fig_kind_mismatch": "figure_qa",
    "fig_leak_answer": "figure_qa",
    "fig_low_res": "figure_qa",
    "notation_stem_mismatch": "local",
    "giveaway_extreme": "local",
    "empty_analysis": "local",
    "echo_given": "local",
    "flash_visual_missing": "flash_visual",
    "flash_quality": "flash_quality",
    "flash_correct": "flash_correct",
    "paper_rules": "paper_rules",
    "other": "paper_rules",
}

MODULE_SLUG = {
    "yanyu": "言语理解与表达",
    "panduan": "判断推理",
    "kepui": "科学推理",
    "shuliang": "数量关系",
    "ziliao": "资料分析",
}

QID_RE = re.compile(
    r"(daily-\d{8}-[a-z]+-[0-9a-f]+_\d{2}|[A-Za-z0-9._-]+_\d{2})"
)
BATCH_RE = re.compile(r"daily-(\d{8})-([a-z]+)-[0-9a-f]+")

SEED_20260907 = (
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_01",
        "layer": "figure_qa",
        "class": "fig_low_res",
        "detail": "像素过低 1280x720；字号 14",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_01",
        "layer": "figure_qa",
        "class": "fig_missing_label",
        "detail": "题干有甲乙，图上没有",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_03",
        "layer": "figure_qa",
        "class": "fig_missing_label",
        "detail": "清单有甲、乙，图上没有",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_03",
        "layer": "figure_qa",
        "class": "fig_extra_object",
        "detail": "图上多了清单/题干没有的「木块」",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_04",
        "layer": "figure_qa",
        "class": "fig_missing_label",
        "detail": "清单有感受器、效应器、神经节，图上没有",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_04",
        "layer": "local",
        "class": "giveaway_extreme",
        "detail": "C项「损伤部位一定是①」绝对词送分",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_01",
        "layer": "flash_visual",
        "class": "flash_visual_missing",
        "detail": "candidate/setter visual review rejected",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_02",
        "layer": "flash_visual",
        "class": "flash_visual_missing",
        "detail": "setter visual review rejected or missing",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_03",
        "layer": "flash_visual",
        "class": "flash_visual_missing",
        "detail": "setter visual review rejected or missing",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_03",
        "layer": "local",
        "class": "notation_stem_mismatch",
        "detail": "题干甲乙，解析混用 ρ_A、ρ_B",
    },
    {
        "plan_date": "2026-09-07",
        "module": "科学推理",
        "batch_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a",
        "question_id": "daily-20260907-kepui-f3b9b0dd1c394c0b889a_03",
        "layer": "flash_quality",
        "class": "flash_quality",
        "detail": "quality reviewer rejected; notation_inconsistency",
    },
)


def ledger_path() -> Path:
    override = os.environ.get("QUALITY_LEDGER")
    return Path(override) if override else DEFAULT_LEDGER


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def module_of(batch_id: str, fallback: str = "") -> str:
    match = BATCH_RE.search(str(batch_id or ""))
    if match:
        return MODULE_SLUG.get(match.group(2), fallback or match.group(2))
    return fallback


def plan_date_of(batch_id: str) -> str:
    match = BATCH_RE.search(str(batch_id or ""))
    if not match:
        return ""
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def classify_figure_issue(text: str) -> str:
    blob = str(text or "")
    if any(token in blob for token in ("像素过低", "字号")):
        return "fig_low_res"
    if any(token in blob for token in ("must_derive", "图上写了")):
        return "fig_leak_answer"
    if any(token in blob for token in ("等高线图", "食物网", "没有椭圆")):
        return "fig_kind_mismatch"
    if any(token in blob for token in ("交点", "不相交")):
        return "fig_no_intersection"
    if "图上多了" in blob:
        return "fig_extra_object"
    if any(token in blob for token in ("图上没有", "清单有", "题干有甲乙")):
        return "fig_missing_label"
    return "other"


def classify_chunk(text: str) -> str:
    blob = str(text or "")
    if "程序作图质检未过" in blob or any(
        token in blob
        for token in ("图上没有", "图上多了", "像素过低", "字号", "折线不相交", "食物网", "等高线图")
    ):
        return classify_figure_issue(blob)
    if any(token in blob for token in ("ρ_A", "ρ_B", "液体A", "液体B", "notation_inconsistency", "符号与题干")):
        return "notation_stem_mismatch"
    if any(token in blob for token in ("一定是", "绝对化", "giveaway", "extreme-word", "极端词")):
        return "giveaway_extreme"
    if "restates a 已知" in blob or "echo_given" in blob:
        return "echo_given"
    if "no analysis" in blob or "没有解析" in blob:
        return "empty_analysis"
    if "visual review" in blob:
        return "flash_visual_missing"
    if any(
        token in blob
        for token in (
            "quality reviewer",
            "quality score",
            "facts are not closed",
            "quality hard",
            "style mismatch",
        )
    ):
        return "flash_quality"
    if any(token in blob for token in ("candidate answer", "correctness", "系统正确性")):
        return "flash_correct"
    if any(token in blob for token in ("答案字母", "batch_constraints", "无法凑满", "科推")):
        return "paper_rules"
    return "other"


def extract_qids(text: str) -> list[str]:
    found = []
    for match in QID_RE.finditer(str(text or "")):
        qid = match.group(1)
        if qid not in found:
            found.append(qid)
    return found


def classify_error(error: str, batch_id: str = "") -> list[dict]:
    raw = str(error or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in re.split(r"[；;\n]", raw) if part.strip()]
    events = []
    seen: set[tuple[str, str]] = set()
    for part in parts or [raw]:
        klass = classify_chunk(part)
        qids = extract_qids(part) or extract_qids(raw) or ["*"]
        for qid in qids:
            key = (qid, klass)
            if key in seen:
                continue
            seen.add(key)
            events.append(
                {
                    "question_id": qid,
                    "class": klass,
                    "layer": LAYER_FOR.get(klass, "paper_rules"),
                    "detail": part[:240],
                    "batch_id": batch_id,
                }
            )
    return events


def _read_rows(path: Path | None = None) -> list[dict]:
    path = path or ledger_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_rows(rows: list[dict], path: Path | None = None) -> None:
    path = path or ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def record_event(event: dict, path: Path | None = None) -> dict:
    path = path or ledger_path()
    rows = _read_rows(path)
    batch_id = str(event.get("batch_id") or "")
    qid = str(event.get("question_id") or "*")
    klass = str(event.get("class") or "other")
    if klass not in CLASSES:
        klass = "other"
    for row in rows:
        if (
            str(row.get("batch_id") or "") == batch_id
            and str(row.get("question_id") or "") == qid
            and str(row.get("class") or "") == klass
        ):
            row["count"] = int(row.get("count") or 1) + 1
            row["ts"] = event.get("ts") or now_iso()
            row["detail"] = str(event.get("detail") or row.get("detail") or "")[:240]
            _write_rows(rows, path)
            return row
    stored = {
        "ts": event.get("ts") or now_iso(),
        "plan_date": event.get("plan_date") or plan_date_of(batch_id),
        "module": event.get("module") or module_of(batch_id),
        "batch_id": batch_id,
        "question_id": qid,
        "layer": event.get("layer") or LAYER_FOR.get(klass, "paper_rules"),
        "class": klass,
        "detail": str(event.get("detail") or "")[:240],
        "count": int(event.get("count") or 1),
    }
    rows.append(stored)
    _write_rows(rows, path)
    return stored


def record_gate_failure(batch_dir: Path, error: str) -> list[dict]:
    batch_id = ""
    module = ""
    try:
        manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
        batch_id = str(manifest.get("batch_id") or "")
        questions = json.loads((batch_dir / "questions.json").read_text(encoding="utf-8"))
        if isinstance(questions, list) and questions:
            module = str(questions[0].get("category") or "")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    module = module or module_of(batch_id)
    recorded = []
    for event in classify_error(error, batch_id):
        event["batch_id"] = batch_id or event.get("batch_id")
        event["module"] = module
        event["plan_date"] = plan_date_of(event["batch_id"])
        recorded.append(record_event(event))
    if not recorded:
        recorded.append(
            record_event(
                {
                    "batch_id": batch_id,
                    "module": module,
                    "question_id": "*",
                    "class": "other",
                    "detail": str(error)[:240],
                }
            )
        )
    return recorded


def seed_kepui_20260907(path: Path | None = None) -> int:
    added = 0
    for event in SEED_20260907:
        before = _read_rows(path)
        keys = {
            (str(row.get("batch_id")), str(row.get("question_id")), str(row.get("class")))
            for row in before
        }
        key = (event["batch_id"], event["question_id"], event["class"])
        if key in keys:
            continue
        record_event({**event, "ts": "2026-09-03T15:00:00+00:00"}, path)
        added += 1
    return added


def recent_classes(module: str = "", limit: int = 8, path: Path | None = None) -> list[str]:
    rows = sorted(_read_rows(path), key=lambda row: str(row.get("ts") or ""), reverse=True)
    found: list[str] = []
    for row in rows:
        if module and str(row.get("module") or "") != module:
            continue
        klass = str(row.get("class") or "")
        if klass in NO_PROMOTE or klass not in CLASSES:
            continue
        if klass not in found:
            found.append(klass)
        if len(found) >= limit:
            break
    return found


def retry_prompt_block(module: str = "", error: str | None = None, path: Path | None = None) -> str:
    classes = recent_classes(module, limit=8, path=path)
    if error:
        for event in classify_error(error):
            klass = event["class"]
            if klass in NO_PROMOTE:
                continue
            if klass not in classes:
                classes.append(klass)
    classes = [klass for klass in classes if klass in CLASSES][:8]
    if not classes:
        classes = ["other"]
    lines = [
        "# Previous generation_gate failure classes. Fix these defects.",
        "# Do not echo raw gate JSON. Known dirty classes must not recur.",
    ]
    for klass in classes:
        lines.append(f"- {klass}: {MUST_FIX[klass]}")
    return "\n".join(lines)


def ledger_rules_for_module(module: str = "", path: Path | None = None) -> str:
    classes = recent_classes(module, limit=8, path=path)
    if not classes:
        return ""
    lines = ["# Ledger hard fails for this module"]
    for klass in classes:
        lines.append(f"- {klass}: {MUST_FIX[klass]}")
    return "\n".join(lines)


def _parse_ts(value: str) -> datetime | None:
    raw = str(value or "").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def summarize(days: int = 14, path: Path | None = None) -> dict[str, Counter]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    tallies: dict[str, Counter] = {}
    for row in _read_rows(path):
        ts = _parse_ts(str(row.get("ts") or ""))
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts is not None and ts < cutoff:
            continue
        module = str(row.get("module") or "?")
        tallies.setdefault(module, Counter())[str(row.get("class") or "other")] += int(
            row.get("count") or 1
        )
    return tallies


def promote_advice(klass: str, path: Path | None = None) -> str:
    if klass not in CLASSES:
        return f"{klass}: 不是固定 class，禁止追加长 R 条目。"
    if klass in NO_PROMOTE:
        return f"{klass}: 审核噪声不升级。"
    total = sum(int(row.get("count") or 1) for row in _read_rows(path) if row.get("class") == klass)
    if total < 2:
        return f"{klass}: 单次失败不升级，禁止追加长 R 条目。"
    checker = CHECKERS.get(klass)
    if checker:
        return f"{klass}: 该写检查器（已有 {checker}）。出现 {total} 次。"
    return f"{klass}: 做不到机械检查，保持短规则。出现 {total} 次。禁止追加长 R 条目。"


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summary")
    summary.add_argument("--days", type=int, default=14)
    promote = sub.add_parser("promote")
    promote.add_argument("--class", dest="klass", required=True)
    sub.add_parser("seed")
    args = parser.parse_args()
    if args.command == "seed":
        added = seed_kepui_20260907()
        print(json.dumps({"seeded": added, "path": str(ledger_path())}, ensure_ascii=False))
        return 0
    if args.command == "promote":
        print(promote_advice(args.klass))
        return 0
    tallies = summarize(args.days)
    payload = {module: dict(counter) for module, counter in sorted(tallies.items())}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

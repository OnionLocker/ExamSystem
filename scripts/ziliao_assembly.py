#!/usr/bin/env python3
"""资料分析整卷组装与轻量闸门：每篇已在篇内过完整审核并签名，整卷只核对签名、内容未变与整卷规则，不再整卷重审。"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ASSEMBLY_VERSION = "ziliao-assembly-v1"
RECEIPT = ".gate.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assemble(out: Path, worker_dirs: list[Path], slots: list[dict], source: str, tier: str,
             targeted: bool = False) -> None:
    """把4篇已签名的单篇产物原样拼成整卷；只补整卷层面的记账字段，不动题面、选项与答案。"""
    from normalize_ai_batch import ensure_batch_constraints, stamp_daily_source
    materials, questions, calculations, canon, manifest = [], [], [], {}, None
    (out / "images").mkdir(parents=True, exist_ok=True)
    for work in worker_dirs:
        materials += read_json(work / "materials.json")
        questions += read_json(work / "questions.json")
        calculations += read_json(work / "calculations.json")["questions"]
        manifest = read_json(work / "manifest.json")
        canon.update(manifest["generation"].get("kaofa_canon") or {})
        for image in (work / "images").glob("*.png"):
            shutil.copy2(image, out / "images" / image.name)
    manifest.update(batch_id=out.name, source=source, difficulty_tier=tier)
    generation = manifest["generation"]
    generation["kaofa_canon"] = canon
    constraints = generation["batch_constraints"]
    constraints.update(question_count=len(questions), targeted_drill=targeted, slot_plan=slots, difficulty_tier=tier,
                       tag_counts=dict(Counter(s["tag"] for s in slots)))
    constraints.pop("answer_max_per_letter", None)
    constraints.pop("answer_min_letters", None)
    constraints.pop("answer_distribution", None)
    ensure_batch_constraints(manifest, questions)
    stamp_daily_source(manifest, questions, materials)
    write_json(out / "materials.json", materials)
    write_json(out / "questions.json", questions)
    write_json(out / "calculations.json", {"questions": calculations})
    write_json(out / "manifest.json", manifest)


def assembly_issues(out: Path, worker_dirs: list[Path], verify_worker=None) -> list[str]:
    from generation_gate import digest, validate_batch_constraints, validate_paper_hard_rules, verify
    verify_worker = verify_worker or verify
    from normalize_ai_batch import answer_distribution_ok
    from quality_memory import fingerprint
    from ziliao_tracks import validate_gd_quota
    issues = []
    manifest = read_json(out / "manifest.json")
    questions = read_json(out / "questions.json")
    materials = {m["external_id"]: m for m in read_json(out / "materials.json")}
    slots = (manifest.get("generation") or {}).get("batch_constraints", {}).get("slot_plan") or []
    signed_questions, signed_materials = [], {}
    for work in worker_dirs:
        try:
            verify_worker(work)
        except Exception as exc:
            issues.append(f"{work.parent.name} 单篇签名无效：{exc}")
            continue
        signed_questions += read_json(work / "questions.json")
        for material in read_json(work / "materials.json"):
            signed_materials[material["external_id"]] = material
        for image in (work / "images").glob("*.png"):
            copied = out / "images" / image.name
            if not copied.is_file() or digest(copied) != digest(image):
                issues.append(f"图片与单篇签发时不一致：{image.name}")
    if [q["external_id"] for q in questions] != [q["external_id"] for q in signed_questions]:
        issues.append("整卷题目与各篇签发的题目不一致")
    else:
        for question, signed in zip(questions, signed_questions):
            if fingerprint(question) != fingerprint(signed) or question.get("tags") != signed.get("tags"):
                issues.append(f"{question['external_id']} 在单篇签发后被改动")
    for mid, signed in signed_materials.items():
        mine = materials.get(mid) or {}
        if any(mine.get(k) != signed.get(k) for k in ("content", "figure", "images", "rounding_checks")):
            issues.append(f"{mid} 材料在单篇签发后被改动")
    expected = [f"{out.name}-M{m:02d}-Q{q}" for m in range(1, 5) for q in range(1, 6)]
    if len(questions) == 20 and [q["external_id"] for q in questions] != expected:
        issues.append("题号须为 M01-Q1 至 M04-Q5 连续")
    if len(slots) != len(questions):
        issues.append("slot_plan 与题量不一致")
    else:
        for index, (slot, question) in enumerate(zip(slots, questions), 1):
            if (question.get("tags") or [""])[0] != slot.get("tag") or question.get("family") != slot.get("family"):
                issues.append(f"第{index}题题型或主标签与蓝图槽位不符")
        try:
            validate_gd_quota(slots, count=len(slots))
        except ValueError as exc:
            issues.append(f"蓝图配额：{exc}")
    if not answer_distribution_ok(manifest, questions):
        issues.append("答案分布不符合整卷规则（4篇中恰好3篇为ABCD各一加一个重复）")
    for check in (lambda: validate_batch_constraints(manifest, questions),
                  lambda: validate_paper_hard_rules(manifest, questions, out)):
        try:
            check()
        except ValueError as exc:
            issues.append(str(exc)[:600])
    return issues


def issue_assembly(out: Path, worker_dirs: list[Path], verify_worker=None) -> dict:
    from generation_gate import artifact_digests, digest, question_ids
    issues = assembly_issues(out, worker_dirs, verify_worker)
    if issues:
        raise ValueError("整卷轻量闸门未通过：" + "；".join(issues[:8]))
    manifest = read_json(out / "manifest.json")
    receipt = {
        "version": ASSEMBLY_VERSION,
        "batch_id": manifest.get("batch_id"),
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha256": digest(out / "manifest.json"),
        "questions_sha256": digest(out / "questions.json"),
        "artifacts": artifact_digests(out),
        "question_ids": question_ids(out),
        "workers": {work.parent.name: {"path": str(work.relative_to(out)), "receipt_sha256": digest(work / RECEIPT)}
                    for work in worker_dirs},
    }
    write_json(out / RECEIPT, receipt)
    return receipt


def verify_assembly(out: Path, receipt: dict, verify_worker=None) -> dict:
    from generation_gate import artifact_digests, digest, question_ids, safe_child
    manifest = read_json(out / "manifest.json")
    if receipt.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("整卷回执 batch_id 不一致")
    if receipt.get("question_ids") != question_ids(out):
        raise ValueError("整卷回执题目列表不一致")
    if receipt.get("manifest_sha256") != digest(out / "manifest.json"):
        raise ValueError("manifest 在整卷签发后被修改")
    if receipt.get("questions_sha256") != digest(out / "questions.json"):
        raise ValueError("questions 在整卷签发后被修改")
    if receipt.get("artifacts") != artifact_digests(out):
        raise ValueError("材料、计算清单或图片在整卷签发后被修改")
    workers = []
    for mid, meta in sorted((receipt.get("workers") or {}).items()):
        work = safe_child(out, str(meta.get("path") or ""))
        if not (work / RECEIPT).is_file() or digest(work / RECEIPT) != meta.get("receipt_sha256"):
            raise ValueError(f"{mid} 单篇回执缺失或被替换")
        workers.append(work)
    materials = {q.get("material_id") for q in read_json(out / "questions.json")}
    if not workers or len(workers) != len(materials):
        raise ValueError("整卷须由各篇已签名的单篇组成，篇数与题目所属材料一致")
    issues = assembly_issues(out, workers, verify_worker)
    if issues:
        raise ValueError("整卷轻量闸门复核未通过：" + "；".join(issues[:8]))
    return {"ok": True, "batch_id": receipt["batch_id"], "question_count": len(receipt["question_ids"]),
            "issued_at": receipt["issued_at"], "pipeline": "ziliao_assembly"}

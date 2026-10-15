"""批次审计：签发前和入库前都跑。只看批次目录里的文件，重新判一遍每道题。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import families
from .core import check, rasterize


def part_paths(qid: str, part: str) -> tuple[str, str]:
    return f"figures/{qid}-{part}.svg", f"images/{qid}-{part}.png"


def audit_question(batch_dir: Path, question: dict) -> list[str]:
    meta = question.get("figure") or {}
    family = families().get(meta.get("family"))
    qid = str(question.get("external_id"))
    if family is None:
        return [f"{qid}：未知题型族 {meta.get('family')!r}"]
    if meta.get("version") != family.VERSION:
        return [f"{qid}：题型族 {family.NAME} 版本已从 {meta.get('version')} 变为 {family.VERSION}，需重新出题"]
    if question.get("tags", [None])[0] != family.TAG:
        return [f"{qid}：主标签与题型族不一致"]
    issues, svgs, pngs = [], {}, {}
    expected = []
    parts = list(meta.get("parts") or family.PARTS)
    if not parts or any(part not in family.PARTS for part in parts):
        return [f"{qid}：题图部件不在题型族约定里"]
    for part in parts:
        svg_rel, png_rel = part_paths(qid, part)
        expected.append(png_rel)
        try:
            svgs[part] = (batch_dir / svg_rel).read_text(encoding="utf-8")
            pngs[part] = (batch_dir / png_rel).read_bytes()
        except OSError:
            return [f"{qid}：缺少 {part} 的矢量稿或图片"]
        if rasterize(svgs[part]) != pngs[part]:
            issues.append(f"{qid}：{part} 图片与矢量稿不一致")
    if list(question.get("stem_images") or []) != expected:
        issues.append(f"{qid}：题图列表与题型族约定不一致")
    texts = [str(option.get("text") or "") for option in question.get("options") or []]
    found, _ = check(family, svgs, pngs, str(question.get("answer") or ""), str(question.get("stem") or ""), texts)
    return issues + [f"{qid}：{issue}" for issue in found]


def audit_batch(batch_dir: Path, questions: list[dict]) -> list[str]:
    issues = []
    for question in questions:
        issues += audit_question(batch_dir, question)
    return issues


def figure_digests(batch_dir: Path, questions: list[dict]) -> dict[str, str]:
    out = {}
    for question in questions:
        meta = question.get("figure") or {}
        family = families().get(meta.get("family"))
        if family is None:
            continue
        for part in meta.get("parts") or family.PARTS:
            for rel in part_paths(str(question["external_id"]), part):
                path = batch_dir / rel
                if path.is_file():
                    out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out

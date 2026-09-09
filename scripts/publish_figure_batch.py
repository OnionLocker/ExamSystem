#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Put one full draw batch into the sidebar figure preview. One group per batch."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "figure-lab"
CATALOG = PUBLIC / "catalog.json"


TITLES = {
    "k01": "容器底部受力",
    "k02": "固体压强",
    "k03": "电路故障",
    "k04": "遗传系谱",
    "k05": "食物网",
    "k06": "海陆风",
    "k07": "锋面天气",
    "k08": "地球自转",
    "k09": "摩擦与惯性",
    "k10": "平抛运动",
    "p01": "六面体展开还原",
    "p02": "立方体截面",
    "p03": "小方块三视图",
    "p04": "封闭面递增",
    "p05": "箭头平移转向",
    "p06": "去同存异",
    "p07": "对称性分类",
    "p08": "开闭性分类",
    "p09": "对比实验装置",
    "p10": "对象属性匹配",
}


def _title_of(qid: str, req: dict, ok: bool) -> str:
    name = str(req.get("title") or "").strip() or TITLES.get(qid)
    if not name:
        tags = req.get("tags") or []
        tag = str(tags[0] if tags else "").strip()
        name = tag.split("-")[-1] if tag else qid
    if not ok:
        name = f"{name} · 未过检"
    return name


def collect_batch(batch_dir: Path) -> list[dict]:
    rows = []
    for dest in sorted(p for p in batch_dir.iterdir() if p.is_dir()):
        png = dest / "stem.png"
        if not png.is_file():
            continue
        req = {}
        if (dest / "request.json").is_file():
            req = json.loads((dest / "request.json").read_text(encoding="utf-8"))
        ok = True
        if (dest / "result.json").is_file():
            ok = bool(json.loads((dest / "result.json").read_text(encoding="utf-8")).get("ok", True))
        rows.append({"id": dest.name, "png": png, "title": _title_of(dest.name, req, ok), "ok": ok})
    if not rows:
        raise SystemExit(f"no stem.png under {batch_dir}")
    return rows


def upsert_group(catalog: dict, group: dict) -> dict:
    others = [g for g in catalog.get("groups") or [] if g.get("id") != group["id"]]
    catalog["groups"] = [group, *others]
    catalog.setdefault("style", "black-white-line")
    return catalog


def publish(batch_dir: Path, *, title: str, group_id: str | None = None) -> dict:
    batch_dir = Path(batch_dir)
    group_id = group_id or f"batch-{batch_dir.name}"
    rows = collect_batch(batch_dir)
    dest = PUBLIC / "batches" / group_id
    dest.mkdir(parents=True, exist_ok=True)
    items = []
    for row in rows:
        name = f"{row['id']}.png"
        shutil.copy2(row["png"], dest / name)
        items.append({
            "id": f"{group_id}-{row['id']}",
            "title": row["title"],
            "file": f"batches/{group_id}/{name}",
            "ok": bool(row.get("ok", True)),
        })
    group = {"id": group_id, "title": title, "items": items}
    catalog = {"style": "black-white-line", "groups": []}
    if CATALOG.is_file():
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    upsert_group(catalog, group)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return group


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a draw batch into figure preview")
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--id")
    args = parser.parse_args()
    group = publish(args.batch_dir, title=args.title, group_id=args.id)
    print(f"published {len(group['items'])} figures -> {group['title']}")


if __name__ == "__main__":
    main()

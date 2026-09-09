#!/usr/bin/env python3
"""把 figure-lab 黑白图样种进复习模块「图样预览」。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "public" / "figure-lab" / "catalog.json"
DB = Path(__file__).resolve().parents[1] / "data" / "exam.db"
IMAGE_DIR = ROOT / "data" / "review-images"
MODULE_NAME = "图样预览"


def rasterize_svgs(items: list[dict], src_dir: Path) -> list[tuple[str, bytes]]:
    from playwright.sync_api import sync_playwright

    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium-browser",
            args=["--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page(viewport={"width": 800, "height": 500})
        for item in items:
            svg = (src_dir / item["file"]).read_text(encoding="utf-8")
            page.set_content(svg)
            png = page.locator("svg").screenshot(type="png")
            title = f"{item['group']} · {item['title']}.png"
            out.append((title, png))
        browser.close()
    return out


def catalog_items(catalog_path: Path = CATALOG) -> list[dict]:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    items = []
    for group in data["groups"]:
        for item in group["items"]:
            items.append({**item, "group": group["title"]})
    return items


def seed(
    db_path: Path = DB,
    image_dir: Path = IMAGE_DIR,
    catalog_path: Path = CATALOG,
    src_dir: Path | None = None,
) -> int:
    src_dir = src_dir or catalog_path.parent
    items = catalog_items(catalog_path)
    if not items:
        raise SystemExit("catalog empty")
    pngs = rasterize_svgs(items, src_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    row = con.execute("SELECT id FROM review_modules WHERE name = ?", (MODULE_NAME,)).fetchone()
    if row:
        module_id = row[0]
        old = con.execute("SELECT filename FROM review_images WHERE module_id = ?", (module_id,)).fetchall()
        con.execute("DELETE FROM review_images WHERE module_id = ?", (module_id,))
        for (fn,) in old:
            if fn and ".." not in fn and "/" not in fn:
                (image_dir / fn).unlink(missing_ok=True)
        con.execute(
            "UPDATE review_modules SET updated_at = datetime('now', '+8 hours'), sort_order = 0 WHERE id = ?",
            (module_id,),
        )
    else:
        cur = con.execute(
            """INSERT INTO review_modules (name, sort_order, updated_at)
               VALUES (?, 0, datetime('now', '+8 hours'))""",
            (MODULE_NAME,),
        )
        module_id = cur.lastrowid

    for i, (title, blob) in enumerate(pngs, start=1):
        filename = f"{uuid.uuid4()}.png"
        (image_dir / filename).write_bytes(blob)
        con.execute(
            """INSERT INTO review_images (module_id, filename, orig_name, mime, sort_order)
               VALUES (?, ?, ?, 'image/png', ?)""",
            (module_id, filename, title, i),
        )
    con.commit()
    con.close()
    return len(pngs)


if __name__ == "__main__":
    n = seed()
    print(f"seeded {n} images → module {MODULE_NAME}")

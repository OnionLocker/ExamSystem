#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemini 3.8 Flash 逐题裁剪补跑：对整页缺失的题单题喂图。

与 DeepSeek 的 crop 脚本同构，仅 API 换成 cliproxy + gemini-3.8-flash-high。
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz

QPDF = Path("data/uploads/真题/省考/2026年广东省公务员录用考试《行测》题（网友回忆版）.pdf")
OUT = Path("/tmp/gemini_vision_eval")
BASE_URL = os.environ.get("GEMINI_EVAL_BASE", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("GEMINI_EVAL_MODEL", "gemini-3.8-flash-high")
WORKERS = 3
MAX_TOKENS = 6000

KEY = ""
for line in Path.home().joinpath(".hermes/.env").read_text(encoding="utf-8").splitlines():
    if line.startswith("CLIPROXY_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
        break
assert KEY, "CLIPROXY_API_KEY not found"

# 缺失题 → pdf 页（0-based）
MISSING = {10: 1, 24: 3, 29: 4, 53: 8, 58: 9, 69: 12}

LINE_RE = re.compile(r"^\s*(\d{1,3})\s*[\.、:：]\s*([A-Ha-h]{1,6})\s*$")


def collect_q_positions(doc, page_idx: int) -> dict[int, float]:
    page = doc[page_idx]
    t = page.get_text("dict")
    pos = {}
    for block in t["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                m = re.match(r"^(\d{1,3})[\.、]$", span["text"].strip())
                if m:
                    q = int(m.group(1))
                    y = span["bbox"][1]
                    if q not in pos or y < pos[q]:
                        pos[q] = y
    return pos


def crop_question(doc, page_idx: int, qnum: int, dpi=200) -> Path:
    page = doc[page_idx]
    rect = page.rect
    pos = collect_q_positions(doc, page_idx)
    if qnum not in pos:
        raise ValueError(f"页 {page_idx+1} 找不到题号 {qnum}")
    y0 = pos[qnum] - 8
    nxt = min((v for k, v in pos.items() if k > qnum), default=rect.height)
    y1 = min(nxt - 4, rect.height)
    clip = fitz.Rect(0, max(0, y0), rect.width, y1)
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    fn = OUT / f"q{qnum}_crop.png"
    pix.save(fn)
    return fn


def call_vision(img_path: Path, qnum: int) -> str:
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    f"这是广东省考行测真题第 {qnum} 题（题目图片）。请用视觉仔细阅读题目和选项，"
                    f"作答第 {qnum} 题。只输出一个选项字母（多选输出所有字母如 BD）。"
                    "只输出字母，不要解释。"
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        "max_tokens": MAX_TOKENS,
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
            content = d["choices"][0]["message"].get("content", "") or ""
            if content.strip():
                return content
        except urllib.error.HTTPError as e:
            print(f"  [q{qnum}] HTTP {e.code}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  [q{qnum}] 异常: {e}", file=sys.stderr)
        time.sleep(4)
    return ""


def parse_answer(text: str) -> str | None:
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            return m.group(2).upper()
    m = re.search(r"\b([A-H]{1,4})\b", text)
    return m.group(1).upper() if m else None


def main() -> int:
    answers = json.loads((OUT / "answers.json").read_text(encoding="utf-8"))
    answers = {int(k): v for k, v in answers.items()}
    doc = fitz.open(str(QPDF))
    tasks = []
    for q, pg in MISSING.items():
        if q in answers:
            continue
        try:
            img = crop_question(doc, pg, q)
        except Exception as e:  # noqa: BLE001
            print(f"  [q{q}] 裁剪失败: {e}", file=sys.stderr)
            continue
        tasks.append((q, img))
    doc.close()
    print(f"Gemini 逐题裁剪补跑 {len(tasks)} 题", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(call_vision, img, q): q for q, img in tasks}
        for fut in as_completed(futs):
            q = futs[fut]
            try:
                text = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [q{q}] 异常: {e}", file=sys.stderr)
                continue
            a = parse_answer(text)
            if a:
                answers[q] = a
                print(f"  q{q}: OK {a}", flush=True)
            else:
                print(f"  q{q}: 空", flush=True)
            (OUT / f"q{q}_crop_raw.txt").write_text(text or "", encoding="utf-8")

    (OUT / "answers.json").write_text(
        json.dumps({str(k): v for k, v in sorted(answers.items())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"补跑完成，answers 共 {len(answers)} 题", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

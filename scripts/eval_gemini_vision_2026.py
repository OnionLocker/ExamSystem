#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026 广东行测真题 · Gemini 3.8 Flash 原生视觉作答评测（与 DeepSeek 同图对比）。

复用 /tmp/ds_vision_eval/page_*.png（dpi=150，与 DeepSeek 完全同一批渲染图），
通过 cliproxy 的 chat/completions 喂给 gemini-3.8-flash-high。

用法: python3 scripts/eval_gemini_vision_2026.py
输出: /tmp/gemini_vision_eval/answers.json
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
APDF = Path("data/uploads/真题/省考答案/2026年广东省公务员录用考试《行测》题（网友回忆版）.pdf")
SRC = Path("/tmp/ds_vision_eval")  # 复用 DeepSeek 渲染的页面图
OUT = Path("/tmp/gemini_vision_eval")
OUT.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("GEMINI_EVAL_BASE", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("GEMINI_EVAL_MODEL", "gemini-3.8-flash-high")
WORKERS = 3
MAX_TOKENS = 8000

KEY = ""
for line in Path.home().joinpath(".hermes/.env").read_text(encoding="utf-8").splitlines():
    if line.startswith("CLIPROXY_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
        break
assert KEY, "CLIPROXY_API_KEY not found"


def extract_answer_key(apdf: Path) -> list[str]:
    doc = fitz.open(str(apdf))
    full = "\n".join(pg.get_text() for pg in doc)
    doc.close()
    pat = re.compile(r"正确答案[：:]\s*([A-H](?:\s*[A-H])*)")
    hits = pat.findall(full)
    return ["".join(h.split()) for h in hits]


ANSWER_KEY = extract_answer_key(APDF)
TOTAL = len(ANSWER_KEY)
LINE_RE = re.compile(r"^\s*(\d{1,3})\s*[\.、:：]\s*([A-Ha-h]{1,6})\s*$")


def call_vision(img_path: Path, page_no: int) -> str:
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    f"这是广东省考行测真题第 {page_no} 页。请用视觉仔细阅读这一页上的所有题目，"
                    "逐题作答，每题只输出一个选项字母（多选输出所有字母如 BD）。"
                    "输出格式：每行「题号.答案字母」，如「1.A」。只输出题号和答案，不要解释。"
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
            print(f"  [page {page_no}] HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  [page {page_no}] 异常: {e}", file=sys.stderr)
        time.sleep(6)
    return ""


def parse_answers(text: str) -> dict[int, str]:
    out = {}
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            out[int(m.group(1))] = m.group(2).upper()
    return out


def main() -> int:
    # 复用 DeepSeek 已渲染的整页图（第 2-18 页，pdf idx 1-17）
    rendered = {}
    for idx in range(1, 18):
        src = SRC / f"page_{idx + 1}.png"
        if not src.exists():
            doc = fitz.open(str(QPDF))
            pix = doc[idx].get_pixmap(dpi=150)
            pix.save(src)
            doc.close()
        rendered[idx] = src

    print(f"共 17 页待作答，模型 {MODEL}，并发 {WORKERS}", flush=True)
    answers: dict[int, str] = {}
    seen: set[int] = set()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(call_vision, rendered[i], i): i for i in range(1, 18)}
        for fut in as_completed(futs):
            page_no = futs[fut]
            try:
                text = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [page {page_no}] 异常: {e}", file=sys.stderr)
                continue
            page_ans = parse_answers(text)
            new = {q: a for q, a in page_ans.items() if q not in seen}
            answers.update(new)
            seen.update(new.keys())
            print(
                f"  page {page_no}: 本页给出 {len(page_ans)} 题，新增 {len(new)} 题，累计 {len(seen)} 题 "
                f"（{time.time()-t0:.0f}s）",
                flush=True,
            )
            (OUT / f"page_{page_no}_raw.txt").write_text(text, encoding="utf-8")

    (OUT / "answers.json").write_text(
        json.dumps({str(k): v for k, v in sorted(answers.items())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"整页作答完成，answers 共 {len(answers)} 题", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

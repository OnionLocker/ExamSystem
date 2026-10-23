#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补跑：对首轮空答的页面用更高清晰度 + 更大 token 上限重试。

首轮 17 页里 6 页返回空（推理耗光 max_tokens / 图太密读不清）。
这里只重试这些页：dpi=200、max_tokens=20000、明确要求逐题作答。
结果合并进 answers.json。
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
OUT = Path("/tmp/ds_vision_eval")
KEY = ""
for line in Path.home().joinpath(".hermes/.env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DEEPSEEK_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
        break
assert KEY, "DEEPSEEK_API_KEY not found"
MODEL = os.environ.get("DS_VISION_MODEL", "deepseek-flash")
WORKERS = 3
MAX_TOKENS = 20000

# 首轮空答的页（pdf index，1-based 文件名页码 = idx+1）
# + page_9/page_10：低 DPI 下模型把题号读错 +5，需要高 DPI 重读修正
RETRY_PAGES = [7, 8, 9, 10, 11, 12, 13, 15]

LINE_RE = re.compile(r"^\s*(\d{1,3})\s*[\.、:：]\s*([A-Ha-h]{1,6})\s*$")


def render_high(page_idx: int, dpi=200) -> Path:
    doc = fitz.open(str(QPDF))
    pix = doc[page_idx].get_pixmap(dpi=dpi)
    fn = OUT / f"page_{page_idx + 1}_hi.png"
    pix.save(fn)
    doc.close()
    return fn


def call_vision(img_path: Path, page_no: int) -> str:
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    f"这是广东省考行测真题第 {page_no} 页的高清扫描页。请非常仔细地用视觉阅读这一页，"
                    "找出这一页上的所有题目。逐题作答，每题只输出一个选项字母（多选输出所有字母如 BD）。"
                    "输出格式：每行「题号.答案字母」，如「1.A」。只输出题号和答案，不要解释，不要省略任何题目。"
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        "max_tokens": MAX_TOKENS,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=420) as r:
                d = json.loads(r.read().decode("utf-8"))
            content = d["choices"][0]["message"].get("content", "") or ""
            if content.strip():
                return content
            print(f"  [page {page_no}] 第{attempt+1}次仍为空，重试", file=sys.stderr)
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
    answers = json.loads((OUT / "answers.json").read_text(encoding="utf-8"))
    answers = {int(k): v for k, v in answers.items()}
    # 首轮 page_9/page_10 的题号被模型读错（+5），49-62 段整体丢弃，以补跑结果为准
    for q in range(49, 63):
        answers.pop(q, None)
    # 缺答 22 题的其它段（46-48, 63-70, 76-80）以补跑覆盖
    for q in list(answers):
        if q in (46, 47, 48) or (63 <= q <= 70) or (76 <= q <= 80):
            answers.pop(q, None)
    print(f"补跑 {len(RETRY_PAGES)} 页（dpi=200, max_tokens={MAX_TOKENS}），模型 {MODEL}", flush=True)
    print(f"清理后已有 {len(answers)} 题", flush=True)

    rendered = {p: render_high(p - 1) for p in RETRY_PAGES}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(call_vision, rendered[p], p): p for p in RETRY_PAGES}
        for fut in as_completed(futs):
            p = futs[fut]
            try:
                text = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [page {p}] 异常: {e}", file=sys.stderr)
                continue
            (OUT / f"page_{p}_retry_raw.txt").write_text(text, encoding="utf-8")
            page_ans = parse_answers(text)
            answers.update(page_ans)
            print(f"  page {p}: 给出 {len(page_ans)} 题（补后累计 {len(answers)}）", flush=True)

    (OUT / "answers.json").write_text(
        json.dumps({str(k): v for k, v in sorted(answers.items())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"补跑完成，answers 共 {len(answers)} 题", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐题裁剪补跑：对首轮/补跑仍未答出的题，把题目区域裁出来单题喂 DeepSeek。

整页喂对图密集页会触发超长推理→输出被吃光。逐题裁剪后每次只处理一题，
推理负担小，成功率高。

用法: python3 scripts/eval_deepseek_vision_crop.py
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
WORKERS = 4
MAX_TOKENS = 6000

# 缺失题 → pdf 页（0-based）
# 46-80 整段来自整页跑 + 被中断的补跑，来源不可靠（题号错位/空答），统一逐题裁剪重答
MISSING = {
    q: pg for q, pg in {
        46: 6, 47: 7, 48: 7, 49: 8, 50: 8, 51: 8, 52: 8, 53: 8,
        54: 9, 55: 9, 56: 9, 57: 9, 58: 9,
        59: 10, 60: 10, 61: 10, 62: 10, 63: 10,
        64: 11, 65: 11, 66: 11, 67: 12, 68: 12, 69: 12, 70: 13,
        71: 14, 72: 14, 73: 14, 74: 14, 75: 14,
        76: 15, 77: 15, 78: 15, 79: 15, 80: 15,
    }.items()
}

LINE_RE = re.compile(r"^\s*(\d{1,3})\s*[\.、:：]\s*([A-Ha-h]{1,6})\s*$")


def collect_q_positions(doc, page_idx: int) -> dict[int, float]:
    """页内所有「N.」题号的 y 坐标（取最靠上的）。"""
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
    """裁出第 qnum 题的图像区域：从该题号 y 到下一题号 y（或页底）。"""
    page = doc[page_idx]
    rect = page.rect
    pos = collect_q_positions(doc, page_idx)
    if qnum not in pos:
        raise ValueError(f"页 {page_idx+1} 找不到题号 {qnum}")
    y0 = pos[qnum] - 8
    # 下一题号作为下边界；没有就到底部
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
        "https://api.deepseek.com/v1/chat/completions",
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
    # 兜底：全文找独立字母
    m = re.search(r"\b([A-H]{1,4})\b", text)
    return m.group(1).upper() if m else None


def main() -> int:
    answers = json.loads((OUT / "answers.json").read_text(encoding="utf-8"))
    answers = {int(k): v for k, v in answers.items()}
    # 46-80 整段旧答案来源不可靠，先清除，全部用逐题裁剪结果
    for q in range(46, 81):
        answers.pop(q, None)
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
    print(f"逐题裁剪补跑 {len(tasks)} 题（模型 {MODEL}）", flush=True)

    results = {}
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
            results[q] = {"answer": a, "raw": text}
            print(f"  q{q}: {'OK ' + a if a else '空'}", flush=True)

    for q, r in results.items():
        if r["answer"]:
            answers[q] = r["answer"]
        (OUT / f"q{q}_crop_raw.txt").write_text(r["raw"] or "", encoding="utf-8")

    (OUT / "answers.json").write_text(
        json.dumps({str(k): v for k, v in sorted(answers.items())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"逐题补跑完成，answers 共 {len(answers)} 题", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026 广东行测真题 · DeepSeek 原生视觉作答评测。

流程：
1. 把题目 PDF 第 2-18 页渲染成 PNG（dpi=150）
2. 逐页调用 DeepSeek 官方 API（deepseek-flash，原生视觉），让模型读图作答
3. 解析「N.字母」格式答案，合并 1-90 题
4. 与答案 PDF 的正确答案序列对拍，算分

用法: python3 scripts/eval_deepseek_vision_2026.py
输出: /tmp/ds_vision_eval/answers.json + 报告打印
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
OUT = Path("/tmp/ds_vision_eval")
OUT.mkdir(parents=True, exist_ok=True)


def extract_answer_key(apdf: Path) -> list[str]:
    """从答案 PDF 顺序抽取每题的标准答案，返回「每题一个答案串」的列表。

    多选题答案形如「B D」「A C D」，一组就是一道题的标准答案（如 "BD" / "ACD"）。
    """
    doc = fitz.open(str(apdf))
    full = "\n".join(pg.get_text() for pg in doc)
    doc.close()
    pat = re.compile(r"正确答案[：:]\s*([A-H](?:\s*[A-H])*)")
    hits = pat.findall(full)
    if not hits:
        raise RuntimeError("答案 PDF 未抽取到正确答案")
    return ["".join(h.split()) for h in hits]


ANSWER_KEY = extract_answer_key(APDF)
TOTAL = len(ANSWER_KEY)
assert TOTAL >= 80, f"答案组数 {TOTAL} 过短，解析可能出错"

KEY = ""
for line in Path.home().joinpath(".hermes/.env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DEEPSEEK_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
        break
assert KEY, "DEEPSEEK_API_KEY not found"

MODEL = os.environ.get("DS_VISION_MODEL", "deepseek-flash")
WORKERS = 3
MAX_TOKENS = 12000


def api_key_env():
    return KEY


def render_page(doc, idx, dpi=150):
    pix = doc[idx].get_pixmap(dpi=dpi)
    fn = OUT / f"page_{idx + 1}.png"
    pix.save(fn)
    return fn


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
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    last_err = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
            return d["choices"][0]["message"].get("content", "") or ""
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.read().decode()[:200]}"
            time.sleep(5)
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            time.sleep(5)
    print(f"  [page {page_no}] 3 次失败: {last_err}", file=sys.stderr)
    return ""


LINE_RE = re.compile(r"^\s*(\d{1,3})\s*[\.、:：]\s*([A-Ha-h]{1,6})\s*$")


def parse_answers(text: str) -> dict[int, str]:
    out = {}
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            out[int(m.group(1))] = m.group(2).upper()
    return out


def main() -> int:
    doc = fitz.open(str(QPDF))
    # 题目在第 2-18 页（index 1-17），跳过封面和尾页
    pages = [(i, p) for i, p in enumerate(range(1, 18), start=1)]
    rendered = {}
    for idx in range(1, 18):
        rendered[idx] = render_page(doc, idx)
    doc.close()

    print(f"共 {len(pages)} 页待作答（第 2-18 页），模型 {MODEL}，并发 {WORKERS}", flush=True)

    answers: dict[int, str] = {}
    seen: set[int] = set()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(call_vision, rendered[i], i): i for i, _ in pages}
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

    # 保存原始答案
    (OUT / "answers.json").write_text(
        json.dumps({str(k): v for k, v in sorted(answers.items())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 对答案
    missing = [n for n in range(1, TOTAL + 1) if n not in answers]
    correct = 0
    wrong = []
    for n in range(1, TOTAL + 1):
        a = answers.get(n)
        if a is None:
            continue
        # 标准答案可能是单字母；多选答案按集合比较
        key = ANSWER_KEY[n - 1]
        ok = (a == key) or (set(a) == set(key) and len(a) == len(key))
        if ok:
            correct += 1
        else:
            wrong.append((n, a, key))

    print("\n" + "=" * 60)
    print(f"2026 广东行测 · DeepSeek({MODEL}) 原生视觉作答")
    print(f"总题数 {TOTAL} · 作答 {len(answers)} · 缺答 {len(missing)} · 正确 {correct}")
    pct = correct / TOTAL * 100 if TOTAL else 0
    print(f"得分率: {pct:.1f}%  （缺答按错计: {correct/(len(answers) or 1)*100:.1f}% / 已答正确率）")
    if missing:
        print(f"缺答题号: {missing}")
    if wrong:
        print(f"错题（题号, 模型答案, 标准答案）:")
        for n, a, k in wrong[:40]:
            print(f"  {n}: {a} ≠ {k}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

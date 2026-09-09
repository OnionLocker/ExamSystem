#!/usr/bin/env python3
"""真题 PDF → 结构化题库 JSON。

文字层用 fitz 本地提取（免费），只把文本交给 cliproxy 的 gemini-flash 做
切题 + 考点打标。整页渲染送 vision 贵一个数量级，且这批粉笔 PDF 都有文字层。

用法:
    python3 scripts/parse_zhenti.py                  # 解析全部，跳过已完成
    python3 scripts/parse_zhenti.py --only 省考      # 只跑省考
    python3 scripts/parse_zhenti.py --force          # 重跑
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "data" / "uploads" / "真题"
OUT_DIR = ROOT / "data" / "zhenti"

BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("CLIPROXY_PDF_MODEL", "gemini-3.8-flash-high")
PAGES_PER_CHUNK = 4
WORKERS = 2
RETRIES = 3

MODULES = [
    "政治理论", "常识判断", "言语理解与表达", "数量关系",
    "判断推理", "科学推理", "资料分析",
]

PROMPT = """你是公考真题结构化标注员。下面是一份行测真题 PDF 的连续文本片段（含页码标记）。

把其中的**每一道题**抽成 JSON。注意这份文本是 PDF 文字层直抽的，题号常常出现在题干**之后**、选项之前，你要正确归位。

对每道题输出：
- number: 题号（整数）。看不到题号就填 null。
- module: 必须是这七个之一 —— 政治理论 / 常识判断 / 言语理解与表达 / 数量关系 / 判断推理 / 科学推理 / 资料分析。文本里的大标题（如"六. 科学推理"）是权威依据。
- subtype: 细分题型。用行业通用叫法，例如：逻辑填空、片段阅读-主旨概括、片段阅读-意图判断、语句填空、语句排序、承接叙述、细节判断、定义判断、类比推理、图形推理、逻辑判断-加强、逻辑判断-削弱、逻辑判断-翻译推理、逻辑判断-真假话、逻辑判断-分析推理、逻辑判断-原因解释、逻辑判断-论证结构相似、数学运算-行程、数学运算-工程、数学运算-排列组合、数学运算-容斥、数字推理、资料分析-增长率、资料分析-比重、资料分析-平均数、资料分析-综合分析、科学推理-力学、科学推理-电学、科学推理-光学、科学推理-热学、科学推理-压强浮力、科学推理-化学、科学推理-生物、科学推理-地理、常识-法律、常识-科技、常识-历史人文、常识-地理国情、政治理论-新思想、政治理论-党史党建、政治理论-时政、政治理论-广东省情。列表之外的题型可以自己命名，保持同一叫法。
- knowledge_points: 数组，1-3 个具体考点标签。第一个必须是规范主标签，格式为"模块-一级知识点-二级知识点"；同一考点不得临场换同义词。政治理论一级标签固定为：新思想与时政理论、马克思主义哲学、政治经济学与社会发展规律、中国式现代化与高质量发展、人民民主与全面依法治国、文化思想与生态文明、改革开放与国家治理、党史党建、广东省情。常识判断一级标签固定为：宪法与国家制度、行政法与行政救济、民法与民事权利、刑法与犯罪构成、物理与工程技术、生命科学与医学、信息能源与前沿科技、中国历史与制度沿革、文学艺术与思想文化、世界史与国际常识、经济与管理、地理国情、广东省情与区域发展、时政与政策文件。其他模块也必须落到具体模型，例如："言语理解-逻辑填空-反义对应"、"数量关系-数学运算-行程"、"判断推理-翻译推理-逆否命题"、"科学推理-压强与浮力-液体压强"、"资料分析-比重类-比重趋势、比重差与比值差"。不要写"理解能力"、"常识综合"等空话。
- stem: 完整题干原文（不含选项）。资料分析题若题干依赖前面的材料，在 stem 开头写 "[依托材料]"。
- options: {"A": "...", "B": "...", "C": "...", "D": "..."}。选项文本原样保留。
- has_figure: true/false。判断依据：题干出现"如图""下图""图中""示意图""下列图形"，或选项内容是 "A" "B" "C" "D" 这种占位（说明选项本身是图）。图形推理题几乎都是 true。
- figure_note: has_figure 为 true 时，用一句话描述这题的图大概是什么（从文字推断即可，看不出就写"未知"）。否则 null。
- material_ref: 资料分析题填它依托的材料编号或首句摘要；其他题填 null。

硬性要求：
- 只输出 JSON，不要 markdown 代码围栏，不要任何解释文字。
- 顶层格式：{"questions": [...], "materials": [...]}
- materials 是资料分析的材料正文数组，每项 {"ref": "材料一", "text": "完整材料原文含表格数据"}。没有就给 []。
- 片段不完整的题（开头或结尾被截断）也要输出，把能看到的部分填上，number 尽量填。
- 不要漏题。不要合并题。不要编造原文里没有的内容。

文本片段：
---
{CHUNK}
---"""


def api_key() -> str:
    key = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if key:
        return key
    env = Path.home() / ".hermes" / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("CLIPROXY_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("CLIPROXY_API_KEY not found")


KEY = api_key()


def call_model(chunk: str) -> dict:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 16384,
        "temperature": 0,
        "messages": [{"role": "user", "content": PROMPT.replace("{CHUNK}", chunk)}],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    last = ""
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            # 429 是上游账号池冷却，退避要长；见 memory cliproxy-429-not-prompt-size
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(last)


def chunks_of(pdf: Path) -> list[str]:
    doc = fitz.open(pdf)
    try:
        pages = [f"\n[[PAGE {i+1}]]\n{doc[i].get_text()}" for i in range(len(doc))]
    finally:
        doc.close()
    out = []
    i = 0
    while i < len(pages):
        # 1 页重叠，避免跨页题被切断；后面按题号去重
        start = max(0, i - 1) if i else 0
        out.append("".join(pages[start:i + PAGES_PER_CHUNK]))
        i += PAGES_PER_CHUNK
    return out


def parse_pdf(pdf: Path) -> dict:
    qs: dict[int, dict] = {}
    orphans: list[dict] = []
    mats: dict[str, dict] = {}
    for idx, chunk in enumerate(chunks_of(pdf)):
        res = call_model(chunk)
        for q in res.get("questions") or []:
            n = q.get("number")
            if isinstance(n, int):
                # 后出现的片段更可能完整（重叠页里前半截被截断）
                if n not in qs or len(str(q.get("stem") or "")) > len(str(qs[n].get("stem") or "")):
                    qs[n] = q
            else:
                orphans.append(q)
        for m in res.get("materials") or []:
            ref = str(m.get("ref") or "")
            if ref and (ref not in mats or len(str(m.get("text") or "")) > len(str(mats[ref].get("text") or ""))):
                mats[ref] = m
        print(f"    chunk {idx+1}: +{len(res.get('questions') or [])} 题", flush=True)

    name = pdf.stem
    year = int(re.search(r"(20\d{2})", name).group(1))
    return {
        "source_file": str(pdf.relative_to(ROOT)),
        "title": name,
        "exam": "省考" if "广东" in name else "国考",
        "year": year,
        "paper": ("乡镇卷" if "乡镇" in name else "县级卷" if "县级" in name
                  else "副省级" if "副省" in name else "地市级" if "地市" in name
                  else "行政执法" if "行政执法" in name else "通用卷"),
        "question_count": len(qs),
        "materials": list(mats.values()),
        "questions": [qs[k] for k in sorted(qs)] + orphans,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(SRC_DIR.rglob("*.pdf"))
    if args.only:
        pdfs = [p for p in pdfs if args.only in str(p)]
    # 年份新的先跑：权重高，早出结果
    pdfs.sort(key=lambda p: p.stem, reverse=True)

    def work(pdf: Path):
        out = OUT_DIR / f"{pdf.stem}.json"
        if out.exists() and not args.force:
            print(f"[skip] {pdf.name}", flush=True)
            return
        print(f"[start] {pdf.name}", flush=True)
        try:
            data = parse_pdf(pdf)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {pdf.name}: {exc}", file=sys.stderr, flush=True)
            return
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[done] {pdf.name} -> {data['question_count']} 题", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, pdfs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""让 gemini-flash 独立做真题，统计它的公考实战能力。

隔离保证（这是本脚本的重点，改代码时不要破坏）：
1. **不给答案**：prompt 只含 stem + options，correct_answer 字段绝不进 prompt。
2. **不能联网**：请求走 cliproxy 的纯 chat/completions，不带任何 tools/function
   声明，模型没有可调用的检索工具。已在 assert 里锁死 payload 不含 tools。
3. **每题独立**：一题一次请求，messages 只有当前题，无历史。同卷内不串题。
4. **不给题型提示**：subtype / knowledge_points 也不进 prompt，避免变相提示。
5. **带图题跳过**：has_figure 的题看不到图，做了也没意义，单独统计为「未作答」。

用法:
    python3 scripts/eval_flash.py --papers 2026年广东,2025年广东   # 指定卷
    python3 scripts/eval_flash.py --all-sheng                      # 全部省考
    python3 scripts/eval_flash.py --report                         # 只出报告
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZHENTI = ROOT / "data" / "zhenti"
DB = ROOT / "data" / "exam.db"

BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("CLIPROXY_PDF_MODEL", "gemini-3.8-flash-high")
WORKERS = 3
RETRIES = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS flash_eval (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper       TEXT NOT NULL,
    exam        TEXT NOT NULL,
    year        INTEGER NOT NULL,
    number      INTEGER NOT NULL,
    module      TEXT,
    subtype     TEXT,
    is_multi    INTEGER NOT NULL DEFAULT 0,
    correct     TEXT NOT NULL,
    answered    TEXT,
    is_correct  INTEGER,
    latency_ms  INTEGER,
    raw         TEXT,
    model       TEXT NOT NULL,
    run_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(paper, number, model)
);
"""

# 不给任何解题提示、不给题型、不暗示难度。就是一个考生坐在考场里。
PROMPT = """你正在参加中国公务员录用考试的《行政职业能力测验》。独立作答，不得查阅任何资料。
{MATERIAL}
题目：
{STEM}

选项：
{OPTIONS}

要求：
- 先简短推理（不超过 80 字），再给答案。
- 最后一行必须是 `答案：X`。单选填一个字母；如果题干标注（多选题），填出所有正确字母（如 `答案：BD`）。
- 必须作答，不允许留空或说无法确定。"""


def api_key() -> str:
    k = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if k:
        return k
    for line in (Path.home() / ".hermes" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("CLIPROXY_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("CLIPROXY_API_KEY not found")


KEY = api_key()
RE_ANS = re.compile(r"答案[：:]\s*\**\s*([A-Da-d][A-Da-d\s、,，]*)")


def ask(stem: str, options: dict, material: str = "") -> tuple[str, str, int]:
    """→ (归一化答案, 原始回复, 耗时ms)。绝不接收 correct_answer。"""
    opt_text = "\n".join(f"{k}. {options[k]}" for k in sorted(options) if options.get(k))
    mat = f"\n给定资料：\n{material}\n" if material else ""
    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "temperature": 0,
        "messages": [{"role": "user",
                      "content": PROMPT.replace("{MATERIAL}", mat)
                                       .replace("{STEM}", stem)
                                       .replace("{OPTIONS}", opt_text)}],
    }
    # 隔离断言：没有工具声明 = 模型无法联网检索
    assert "tools" not in payload and "functions" not in payload
    body = json.dumps(payload).encode("utf-8")

    for attempt in range(RETRIES):
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/chat/completions", data=body, method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ms = int((time.monotonic() - t0) * 1000)
            raw = (data["choices"][0]["message"].get("content") or "").strip()
            m = RE_ANS.search(raw)
            if not m:  # 兜底：取回复末尾孤立的大写字母
                m = re.search(r"\b([A-D]{1,4})\b\s*$", raw)
            picked = "".join(sorted(set(re.findall(r"[A-D]", (m.group(1) if m else "").upper()))))
            return picked, raw, ms
        except Exception as exc:  # noqa: BLE001
            if attempt == RETRIES - 1:
                return "", f"[ERROR] {type(exc).__name__}: {exc}", 0
            time.sleep(20 * (attempt + 1))
    return "", "[ERROR] unreachable", 0


def eval_paper(path: Path, conn_path: Path) -> None:
    d = json.loads(path.read_text(encoding="utf-8"))
    paper = d["title"]
    todo = [q for q in d["questions"]
            if q.get("correct_answer") and isinstance(q.get("number"), int)
            and not q.get("has_figure") and q.get("options")]
    if not todo:
        print(f"[skip·无可评题] {paper[:40]}", flush=True)
        return

    conn = sqlite3.connect(conn_path, timeout=60)
    conn.executescript(SCHEMA)
    done = {r[0] for r in conn.execute(
        "SELECT number FROM flash_eval WHERE paper=? AND model=?", (paper, MODEL))}
    todo = [q for q in todo if q["number"] not in done]
    if not todo:
        print(f"[done·已评完] {paper[:40]}", flush=True)
        conn.close()
        return

    print(f"[start] {paper[:44]} 待评 {len(todo)} 题", flush=True)
    lock_rows = []
    # 资料分析题依托材料，不喂材料就是逼模型瞎猜，测不出真实水平
    mats = {str(m.get("ref") or ""): str(m.get("text") or "") for m in (d.get("materials") or [])}

    def one(q):
        ref = str(q.get("material_ref") or "")
        material = mats.get(ref, "")
        if not material and ref:  # ref 写法不一致时按包含匹配兜底
            material = next((v for k, v in mats.items() if k and (k in ref or ref in k)), "")
        picked, raw, ms = ask(q["stem"], q["options"], material)
        gold = "".join(sorted(q["correct_answer"].upper()))
        return (paper, d["exam"], d["year"], q["number"], q.get("module"), q.get("subtype"),
                1 if len(gold) > 1 else 0, gold, picked,
                1 if picked == gold else 0, ms, raw[:2000], MODEL)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, row in enumerate(ex.map(one, todo), 1):
            lock_rows.append(row)
            if i % 20 == 0:
                conn.executemany(
                    "INSERT OR REPLACE INTO flash_eval (paper,exam,year,number,module,subtype,"
                    "is_multi,correct,answered,is_correct,latency_ms,raw,model) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", lock_rows)
                conn.commit()
                acc = sum(r[9] for r in lock_rows) / len(lock_rows)
                print(f"    {paper[:26]} {i}/{len(todo)} 累计正确率 {acc:.0%}", flush=True)
                lock_rows = []
    if lock_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO flash_eval (paper,exam,year,number,module,subtype,"
            "is_multi,correct,answered,is_correct,latency_ms,raw,model) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", lock_rows)
        conn.commit()
    n, c = conn.execute("SELECT COUNT(*), SUM(is_correct) FROM flash_eval WHERE paper=? AND model=?",
                        (paper, MODEL)).fetchone()
    print(f"[done] {paper[:44]}  {c}/{n} = {c/n:.1%}", flush=True)
    conn.close()


def report() -> None:
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    q = conn.execute

    print(f"\n{'='*78}\ngemini-flash 独立应试成绩报告   model={MODEL}\n{'='*78}")
    row = q("SELECT COUNT(*), SUM(is_correct) FROM flash_eval WHERE model=?", (MODEL,)).fetchone()
    if not row[0]:
        print("暂无评测数据")
        return
    print(f"\n总计：{row[1]}/{row[0]} = {row[1]/row[0]:.1%}")

    print("\n## 分卷成绩（不含带图题）\n")
    print(f"{'试卷':46s} {'题数':>4s} {'正确':>4s} {'正确率':>7s} {'均耗时':>7s}")
    for r in q("""SELECT paper, COUNT(*), SUM(is_correct), AVG(latency_ms)
                  FROM flash_eval WHERE model=? GROUP BY paper
                  ORDER BY exam DESC, year DESC""", (MODEL,)):
        print(f"{r[0][:44]:46s} {r[1]:4d} {r[2]:4d} {r[2]/r[1]:6.1%} {r[3]/1000:6.1f}s")

    print("\n## 分模块正确率（省考卷）\n")
    print(f"{'模块':16s} {'题数':>4s} {'正确':>4s} {'正确率':>7s}")
    for r in q("""SELECT module, COUNT(*), SUM(is_correct) FROM flash_eval
                  WHERE model=? AND exam='省考' GROUP BY module
                  ORDER BY SUM(is_correct)*1.0/COUNT(*) ASC""", (MODEL,)):
        print(f"{r[0] or '未标注':16s} {r[1]:4d} {r[2]:4d} {r[2]/r[1]:6.1%}")

    print("\n## 最弱题型（省考，≥3 题）\n")
    print(f"{'题型':30s} {'题数':>4s} {'正确率':>7s}")
    for r in q("""SELECT subtype, COUNT(*) n, SUM(is_correct) c FROM flash_eval
                  WHERE model=? AND exam='省考' GROUP BY subtype HAVING n>=3
                  ORDER BY c*1.0/n ASC LIMIT 12""", (MODEL,)):
        print(f"{r[0] or '未标注':30s} {r[1]:4d} {r[2]/r[1]:6.1%}")

    print("\n## 单选 vs 多选\n")
    for r in q("""SELECT is_multi, COUNT(*), SUM(is_correct) FROM flash_eval
                  WHERE model=? GROUP BY is_multi""", (MODEL,)):
        print(f"{'多选题' if r[0] else '单选题'}: {r[2]}/{r[1]} = {r[2]/r[1]:.1%}")

    blank = q("SELECT COUNT(*) FROM flash_eval WHERE model=? AND (answered IS NULL OR answered='')",
              (MODEL,)).fetchone()[0]
    print(f"\n解析失败/未给答案：{blank} 题")
    conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default="", help="逗号分隔的卷名关键字")
    ap.add_argument("--all-sheng", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        report()
        return 0

    files = sorted(ZHENTI.glob("*.json"), reverse=True)
    if args.papers:
        keys = [k.strip() for k in args.papers.split(",") if k.strip()]
        files = [f for f in files if any(k in f.stem for k in keys)]
    elif args.all_sheng:
        files = [f for f in files if "广东" in f.stem]
    elif not args.all:
        print("需指定 --papers / --all-sheng / --all", file=sys.stderr)
        return 2

    for f in files:
        eval_paper(f, DB)
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

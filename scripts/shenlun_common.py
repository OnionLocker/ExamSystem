"""申论模块公共件：建表、试卷读写、模型调用（文字与图片）、引文核对、字数。

可靠性的底线：
  - 材料只能逐字摘自已登记原文或导入的真题卷，程序核对；
  - 要点表的每个要点要引用材料原句，批改的每个「命中」要引用考生原句，程序都核对是不是原文里真有；
  - 分数由程序按要点相加，不让模型直接给总分。
"""

from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

from quiz_generator import BASE_URL, api_key
from scheduler_common import DB, ROOT

MODEL = "gemini-3.8-flash-high"
LEVEL = "县镇卷"
PAPER_TYPES = ("县镇卷", "省市卷")
QTYPES = ("归纳概括", "综合分析", "提出对策", "贯彻执行", "文章写作")
# 2024–2026 年广东真题的整卷结构（8 份材料、三题 20/30/50），见 quiz-pipeline/references/shenlun-style.md
LAYOUTS = {
    "县镇卷": (
        {"qtype": "归纳概括", "score": 20, "words_max": 200},
        {"qtype": "提出对策", "score": 30, "words_max": 300},
        {"qtype": "文章写作", "score": 50, "words_min": 800, "words_max": 1000},
    ),
    "省市卷": (
        {"qtype": "归纳概括", "score": 20, "words_max": 200},
        {"qtype": "提出对策", "score": 30, "words_max": 300},
        {"qtype": "文章写作", "score": 50, "words_min": 900, "words_max": 1100},
    ),
}
# 题型特训的单题默认值；综合分析、贯彻执行取自 2023 年乡镇卷与县级卷
DRILL_DEFAULTS = {
    "归纳概括": {"qtype": "归纳概括", "score": 20, "words_max": 200},
    "综合分析": {"qtype": "综合分析", "score": 20, "words_max": 300},
    "提出对策": {"qtype": "提出对策", "score": 30, "words_max": 300},
    "贯彻执行": {"qtype": "贯彻执行", "score": 30, "words_max": 400},
    "文章写作": {"qtype": "文章写作", "score": 50, "words_min": 800, "words_max": 1000},
}
DEFAULT_LAYOUT = LAYOUTS[LEVEL]
TIME_LIMIT_MIN = 150
UPLOAD_DIR = ROOT / "data" / "shenlun-uploads"
BATCH_DIR = ROOT / "data" / "shenlun-batches"
INBOX_DIR = ROOT / "data" / "shenlun-inbox"
# 大作文档次（广东 40 分作文的常见切分），按满分等比缩放
ESSAY_LEVELS = (("一类文", 0.83, 1.0), ("二类文", 0.63, 0.82), ("三类文", 0.43, 0.62), ("四类文", 0.0, 0.42))
ESSAY_DIMENSIONS = ("立意", "结构", "论证", "语言")

SCHEMA = """
CREATE TABLE IF NOT EXISTS shenlun_papers (
  id             TEXT PRIMARY KEY,
  title          TEXT NOT NULL,
  kind           TEXT NOT NULL,              -- zhenti / ai
  level          TEXT NOT NULL DEFAULT '县级',
  region         TEXT,
  year           INTEGER,
  time_limit_min INTEGER,
  source_note    TEXT,
  materials      TEXT NOT NULL,              -- JSON: [{id,title,paragraphs:[{id,text,source?}]}]
  meta           TEXT,                       -- JSON：出题来源、审核记录摘要
  created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shenlun_questions (
  id               TEXT PRIMARY KEY,
  paper_id         TEXT NOT NULL REFERENCES shenlun_papers(id) ON DELETE CASCADE,
  no               INTEGER NOT NULL,
  qtype            TEXT NOT NULL,
  prompt           TEXT NOT NULL,
  requirements     TEXT NOT NULL,            -- JSON: {score, words_min, words_max, material_ids}
  rubric           TEXT NOT NULL,            -- JSON：要点表或作文档次细则
  reference_answer TEXT
);
CREATE TABLE IF NOT EXISTS shenlun_attempts (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id    TEXT NOT NULL REFERENCES shenlun_questions(id) ON DELETE CASCADE,
  images         TEXT NOT NULL DEFAULT '[]', -- JSON：照片相对路径，按页序
  answer_text    TEXT,                       -- 照片转写或直接输入的答案
  word_count     INTEGER,
  time_spent_sec INTEGER,
  status         TEXT NOT NULL DEFAULT 'uploaded', -- grading/graded/failed
  error          TEXT,
  grading        TEXT,                       -- JSON：批改明细
  score          REAL,
  max_score      REAL,
  created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_shenlun_attempts_q ON shenlun_attempts(question_id);
CREATE TABLE IF NOT EXISTS shenlun_submissions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_id       TEXT NOT NULL REFERENCES shenlun_papers(id) ON DELETE CASCADE,
  status         TEXT NOT NULL DEFAULT 'submitted', -- submitted/grading/graded/reviewed/failed
  time_spent_sec INTEGER,
  score          REAL,
  max_score      REAL,
  report_path    TEXT,
  comment_path   TEXT,
  error          TEXT,
  created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
STYLE_GUIDE = ROOT / "hermes-skills" / "quiz-pipeline" / "references" / "shenlun-style.md"
STANDARD = ROOT / "hermes-skills" / "gd-gongkao-coach" / "references" / "shenlun-review-standard.md"
REVIEW_DIR = ROOT / "data" / "practice-reviews" / "shenlun"
DEFAULT_PARAMS = {
    "partial_ratio": 0.5,
    "expression_levels": {"A": 1.0, "B": 0.5, "C": 0.0},
    "dispute_policy": "lower",
    "essay_levels": [{"name": n, "min": lo, "max": hi} for n, lo, hi in ESSAY_LEVELS],
    "essay_off_topic_level": "四类文",
    "overflow_note_only": True,
}


def connect(db: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db or DB), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(shenlun_attempts)")}
    if "submission_id" not in cols:  # 草稿 submission_id 为空；交卷后挂到 shenlun_submissions
        conn.execute("ALTER TABLE shenlun_attempts ADD COLUMN submission_id INTEGER REFERENCES shenlun_submissions(id) ON DELETE CASCADE")
        conn.commit()
    return conn


def load_standard() -> tuple[dict[str, str], dict]:
    """读用户维护的评判标准：按 `## 标题` 切段，「评分参数」里的 JSON 代码块作程序参数。"""
    text = STANDARD.read_text(encoding="utf-8") if STANDARD.exists() else ""
    sections: dict[str, str] = {}
    for chunk in re.split(r"(?m)^## ", text)[1:]:
        title, _, body = chunk.partition("\n")
        sections[title.strip()] = body.strip()
    params = dict(DEFAULT_PARAMS)
    found = re.search(r"```json\s*(\{.*?\})\s*```", sections.get("评分参数", ""), re.S)
    if found:
        try:
            params.update(json.loads(found.group(1)))
        except json.JSONDecodeError as exc:
            raise ValueError(f"评判标准里「评分参数」的 JSON 写错了：{exc}") from exc
    return sections, params


def standard_for(qtype: str) -> str:
    sections, _ = load_standard()
    parts = [f"【通用】\n{sections['通用']}" if sections.get("通用") else "",
             f"【{qtype}】\n{sections[qtype]}" if sections.get(qtype) else ""]
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------- 文本
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[\s，。、；：？！“”‘’（）《》【】—…·,.;:?!\"'()\[\]<>\-]+")


def squash(text: str) -> str:
    """比对用：去掉空白和标点。OCR 和模型转述常在这两处出差异。"""
    return _PUNCT.sub("", text or "")


def contains(haystack: str, quote: str, min_len: int = 4) -> bool:
    q = squash(quote)
    return len(q) >= min_len and q in squash(haystack)


def word_count(text: str) -> int:
    """按稿纸格子数：除空白外每个字符（含标点）占一格。"""
    return len(_SPACE.sub("", text or ""))


# ---------------------------------------------------------------- 模型
def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def image_part(path: Path, max_side: int = 2000) -> dict:
    """手机照片统一转成 JPEG、长边不超过 2000px 再送模型。"""
    from PIL import Image, ImageOps

    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((max_side, max_side))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=88)
    encoded = base64.b64encode(out.getvalue()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}


def call(system: str, content, *, temperature: float = 0.2, timeout: int = 420, audit: Path | None = None,
         max_tokens: int = 16384) -> dict:
    """调一次模型，要求返回 JSON 对象。失败直接抛错，不自动重试（cliproxy 有限流冷却）。"""
    body = {
        "model": MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
    }
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"模型调用失败，未自动重试：{type(exc).__name__}: {exc}") from exc
    if audit is not None:
        audit.mkdir(parents=True, exist_ok=True)
        (audit / f"{time.time_ns()}.json").write_text(
            json.dumps({"role": system.splitlines()[0], "model": MODEL, "response": raw}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    payload = json.loads(raw)
    choice = payload["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("模型回答被截断（finish_reason=length），本次未完成，未自动重试")
    try:
        return _parse_json(choice["message"].get("content") or "")
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"模型返回的不是合法 JSON：{exc}") from exc


# ---------------------------------------------------------------- 试卷
def paragraph_index(materials: list[dict]) -> dict[str, dict]:
    return {p["id"]: {**p, "material": m["id"]} for m in materials for p in m["paragraphs"]}


def materials_text(materials: list[dict], ids: list[str] | None = None, with_ids: bool = True) -> str:
    out = []
    for m in materials:
        if ids and m["id"] not in ids:
            continue
        out.append(f"【{m['title']}】")
        for p in m["paragraphs"]:
            out.append(f"[{p['id']}] {p['text']}" if with_ids else p["text"])
    return "\n".join(out)


def load_paper(conn: sqlite3.Connection, paper_id: str) -> dict:
    row = conn.execute("SELECT * FROM shenlun_papers WHERE id=?", (paper_id,)).fetchone()
    if row is None:
        raise ValueError(f"没有这份试卷：{paper_id}")
    paper = dict(row)
    paper["materials"] = json.loads(paper["materials"])
    paper["meta"] = json.loads(paper["meta"] or "{}")
    paper["questions"] = []
    for q in conn.execute("SELECT * FROM shenlun_questions WHERE paper_id=? ORDER BY no", (paper_id,)):
        q = dict(q)
        q["requirements"] = json.loads(q["requirements"])
        q["rubric"] = json.loads(q["rubric"])
        paper["questions"].append(q)
    return paper


def save_paper(conn: sqlite3.Connection, paper: dict) -> None:
    with conn:
        conn.execute("DELETE FROM shenlun_papers WHERE id=?", (paper["id"],))
        conn.execute(
            "INSERT INTO shenlun_papers (id,title,kind,level,region,year,time_limit_min,source_note,materials,meta)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (paper["id"], paper["title"], paper["kind"], paper.get("level") or LEVEL, paper.get("region") or "广东",
             paper.get("year"), paper.get("time_limit_min") or TIME_LIMIT_MIN, paper.get("source_note"),
             json.dumps(paper["materials"], ensure_ascii=False), json.dumps(paper.get("meta") or {}, ensure_ascii=False)))
        for q in paper["questions"]:
            conn.execute(
                "INSERT INTO shenlun_questions (id,paper_id,no,qtype,prompt,requirements,rubric,reference_answer)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (f"{paper['id']}-q{q['no']}", paper["id"], q["no"], q["qtype"], q["prompt"],
                 json.dumps(q["requirements"], ensure_ascii=False), json.dumps(q["rubric"], ensure_ascii=False),
                 q.get("reference_answer")))


def repair_evidence(question: dict, materials: list[dict]) -> int:
    """引文不是原文但意思很近时，换成该段里最接近的原句；引文只是「去材料哪里找这一分」的指针。返回修了几处。"""
    import difflib

    index = paragraph_index(materials)
    rubric = question.get("rubric") or {}
    fixed = 0
    for item in (rubric.get("points") or []) + (rubric.get("must_cover") or []):
        for ev in item.get("evidence") or []:
            para = index.get(ev.get("para"))
            quote = str(ev.get("quote") or "")
            if para is None or contains(para["text"], quote):
                continue
            sentences = [s for s in re.split(r"(?<=[。！？；])", para["text"]) if len(squash(s)) >= 6]
            if not sentences:
                continue
            best = max(sentences, key=lambda s: difflib.SequenceMatcher(None, squash(s), squash(quote)).ratio())
            if difflib.SequenceMatcher(None, squash(best), squash(quote)).ratio() >= 0.45:
                ev["quote"] = best.strip()[:60]
                fixed += 1
    return fixed


def check_rubric(question: dict, materials: list[dict]) -> list[str]:
    """程序核对要点表：引文必须是材料原文，且落在本题指定的材料里；分值加起来等于满分。"""
    issues = []
    qno = question.get("no")
    req = question["requirements"]
    rubric = question.get("rubric") or {}
    index = paragraph_index(materials)
    scope = set(req.get("material_ids") or [m["id"] for m in materials])
    score = float(req.get("score") or 0)
    if rubric.get("kind") == "essay":
        if not rubric.get("theme"):
            issues.append(f"第{qno}题：作文缺立意说明")
        for item in rubric.get("must_cover") or []:
            for ev in item.get("evidence") or []:
                para = index.get(ev.get("para"))
                if para is None or not contains(para["text"], ev.get("quote", "")):
                    issues.append(f"第{qno}题 {item.get('id')}：引文不在材料 {ev.get('para')} 里")
        return issues
    points = rubric.get("points") or []
    if len(points) < 2:
        issues.append(f"第{qno}题：要点少于 2 个")
    total = sum(float(p.get("score") or 0) for p in points + (rubric.get("format_points") or []))
    expression = float(rubric.get("expression_score") or 0)
    if not 0 <= expression <= 3:
        issues.append(f"第{qno}题：表述分 {expression:g} 分太多（最多 3 分），差的分数要补成要点")
    total += expression
    if abs(total - score) > 0.01:
        issues.append(f"第{qno}题：要点分 + 格式分 + 表述分 = {total:g}，不等于满分 {score:g}")
    for point in points:
        # 30 分及以上的题（对策题）一条对策可值 3 分，其余题一个意思 1–2 分
        allowed = (1.0, 2.0, 3.0) if score >= 30 else (1.0, 2.0)
        if float(point.get("score") or 0) not in allowed:
            issues.append(f"第{qno}题 {point.get('id')}：要点分值须为 {'、'.join(f'{a:g}' for a in allowed)} 分，现为 {point.get('score')}")
        if len(str(point.get("text") or "")) > 40:
            issues.append(f"第{qno}题 {point.get('id')}：要点太长（{len(str(point.get('text')))} 字），一个要点只写一个意思")
        evidence = point.get("evidence") or []
        if not evidence:
            issues.append(f"第{qno}题 {point.get('id')}：要点没有材料依据")
        for ev in evidence:
            para = index.get(ev.get("para"))
            if para is None:
                issues.append(f"第{qno}题 {point.get('id')}：引用了不存在的段落 {ev.get('para')}")
            elif para["material"] not in scope:
                issues.append(f"第{qno}题 {point.get('id')}：引文 {ev.get('para')} 不在本题指定材料里")
            elif not contains(para["text"], ev.get("quote", "")):
                issues.append(f"第{qno}题 {point.get('id')}：引文不是 {ev.get('para')} 的原文")
    ids = [p.get("id") for p in points]
    if len(set(ids)) != len(ids):
        issues.append(f"第{qno}题：要点编号重复")
    return issues


def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)

#!/usr/bin/env python3
"""Deterministic cube-net figures with Gemini-selected question plans."""
from __future__ import annotations

import base64
import concurrent.futures
import datetime as dt
import json
import os
import random
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("SPACE_GEMINI_MODEL", "gemini-3.8-flash-high")
BASE = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
NET = {"A": (0, 0), "B": (1, 0), "C": (2, 0), "D": (3, 0), "E": (1, 1), "F": (1, -1)}
OPPOSITES = {"A": "C", "C": "A", "B": "D", "D": "B", "E": "F", "F": "E"}
SYMBOLS = ("△", "○", "□", "★", "◇", "＋")
SUPPORTED_FOCUSES = {"三面共顶点", "相对面排除", "公共边关系", "展开图折叠后的可见面"}


def api_key() -> str:
    value = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if value:
        return value
    for line in (Path.home() / ".hermes" / ".env").read_text().splitlines():
        if line.startswith("CLIPROXY_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("CLIPROXY_API_KEY not found")


def call(prompt: str, max_tokens: int = 3000) -> dict:
    body = json.dumps({
        "model": MODEL, "temperature": 0.35, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    request = urllib.request.Request(
        BASE + "/chat/completions", body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key()},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        content = json.loads(response.read())["choices"][0]["message"]["content"]
    text = content if isinstance(content, str) else "".join(x.get("text", "") for x in content)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Gemini returned no JSON object")
    return json.loads(text[start:end + 1])


def call_parts(system: str, parts: list[dict], max_tokens: int = 1200) -> dict:
    body = json.dumps({
        "model": MODEL, "temperature": 0, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": parts}],
    }).encode()
    request = urllib.request.Request(
        BASE + "/chat/completions", body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key()},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        content = json.loads(response.read())["choices"][0]["message"]["content"]
    text = content if isinstance(content, str) else "".join(x.get("text", "") for x in content)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Gemini visual review returned no JSON object")
    return json.loads(text[start:end + 1])


def plan_prompt() -> str:
    return """你是广东省考图形推理命题规划器，只规划5道空间类题，不画图、不写题干。
输出JSON：{"questions":[{"id":"Q01","type":"cube_corner或cube_opposite","difficulty":2或3或4,"focus":"...","trap":"..."}, ...]}。
要求：至少3道cube_corner、至少1道cube_opposite；5题的focus和trap不得完全重复。可选focus只能是：三面共顶点、相对面排除、公共边关系、展开图折叠后的可见面。第一版不考察面内图案旋转、镜像方向或手性。图形将由程序确定性生成，不能要求自由绘图。"""


def fallback_plan() -> list[dict]:
    return [
        {"id": "Q01", "type": "cube_corner", "difficulty": 3, "focus": "三面共顶点", "trap": "把相对面当成相邻面"},
        {"id": "Q02", "type": "cube_opposite", "difficulty": 2, "focus": "相对面排除", "trap": "把相邻面误判为相对面"},
        {"id": "Q03", "type": "cube_corner", "difficulty": 4, "focus": "公共边关系", "trap": "只核对两面而忽略第三面"},
        {"id": "Q04", "type": "cube_corner", "difficulty": 3, "focus": "标记面方向", "trap": "折叠后方向旋转错误"},
        {"id": "Q05", "type": "cube_corner", "difficulty": 2, "focus": "展开图折叠后的可见面", "trap": "混淆相对面和同一顶点"},
    ]


def normalize_plan(raw: dict) -> list[dict]:
    items = raw.get("questions") if isinstance(raw, dict) else None
    if not isinstance(items, list) or len(items) != 5:
        return fallback_plan()
    out = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or item.get("type") not in {"cube_corner", "cube_opposite"}:
            return fallback_plan()
        focus = str(item.get("focus") or "空间关系")
        if focus not in SUPPORTED_FOCUSES:
            focus = "三面共顶点" if item["type"] == "cube_corner" else "相对面排除"
        out.append({
            "id": f"Q{index:02d}", "type": item["type"],
            "difficulty": max(2, min(4, int(item.get("difficulty", 3)))),
            "focus": focus,
            "trap": str(item.get("trap") or "相邻面与相对面混淆"),
        })
    if sum(x["type"] == "cube_corner" for x in out) < 3 or not any(x["type"] == "cube_opposite" for x in out):
        return fallback_plan()
    return out


def face_symbols(rng: random.Random) -> dict[str, str]:
    shuffled = list(SYMBOLS)
    rng.shuffle(shuffled)
    return dict(zip(NET, shuffled))


def opposite_pairs(symbols: dict[str, str]) -> set[frozenset[str]]:
    return {frozenset((symbols[a], symbols[b])) for a, b in (("A", "C"), ("B", "D"), ("E", "F"))}


def valid_corner(triple: tuple[str, ...], opposites: set[frozenset[str]]) -> bool:
    return not any(frozenset(pair) in opposites for pair in ((triple[0], triple[1]), (triple[0], triple[2]), (triple[1], triple[2])))


def options_for(kind: str, symbols: dict[str, str], rng: random.Random) -> tuple[list[tuple[str, ...]], int]:
    opposite = opposite_pairs(symbols)
    faces = list(symbols.values())
    if kind == "cube_opposite":
        correct = list(rng.choice(sorted(opposite, key=lambda x: sorted(x))))
        wrong = [tuple(pair) for pair in __import__("itertools").combinations(faces, 2) if frozenset(pair) not in opposite]
        selected = [tuple(correct)] + rng.sample(wrong, 3)
    else:
        triples = list(__import__("itertools").combinations(faces, 3))
        correct = rng.choice([x for x in triples if valid_corner(x, opposite)])
        wrong = [x for x in triples if not valid_corner(x, opposite)]
        selected = [correct] + rng.sample(wrong, 3)
    rng.shuffle(selected)
    return selected, selected.index(tuple(correct))


def face_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index=2)


def render_net(symbols: dict[str, str], out: Path) -> None:
    cell, ox, oy = 96, 70, 250
    image = Image.new("RGB", (520, 500), "white")
    draw = ImageDraw.Draw(image)
    label_face, symbol_face = face_font(20), face_font(34)
    for face, (x, y) in NET.items():
        x0, y0 = ox + x * cell, oy - y * cell
        draw.rectangle((x0, y0, x0 + cell, y0 + cell), outline="black", width=3)
        symbol = symbols[face]
        box = draw.textbbox((0, 0), symbol, font=symbol_face)
        draw.text((x0 + (cell - box[2]) / 2, y0 + (cell - (box[3] - box[1])) / 2 - 4), symbol, fill="black", font=symbol_face)
        draw.text((x0 + 7, y0 + 6), face, fill="black", font=label_face)
    image.save(out)


def render_option(values: tuple[str, ...], kind: str, out: Path) -> None:
    image = Image.new("RGB", (420, 250), "white")
    draw = ImageDraw.Draw(image)
    symbol_face = face_font(42)
    if kind == "cube_opposite":
        for i, value in enumerate(values):
            x = 90 + i * 150
            draw.rectangle((x, 90, x + 82, 172), outline="black", width=3)
            box = draw.textbbox((0, 0), value, font=symbol_face)
            draw.text((x + (82 - box[2]) / 2, 105), value, fill="black", font=symbol_face)
        draw.line((172, 130, 238, 130), fill="black", width=2)
    else:
        cx, cy, s = 210, 126, 72
        top = [(cx, cy - s), (cx + s, cy - s // 2), (cx, cy), (cx - s, cy - s // 2)]
        left = [(cx - s, cy - s // 2), (cx, cy), (cx, cy + s), (cx - s, cy + s // 2)]
        right = [(cx, cy), (cx + s, cy - s // 2), (cx + s, cy + s // 2), (cx, cy + s)]
        for polygon, value in zip((top, left, right), values):
            draw.polygon(polygon, fill="white", outline="black")
            box = draw.textbbox((0, 0), value, font=symbol_face)
            px = sum(x for x, _ in polygon) / 4 - box[2] / 2
            py = sum(y for _, y in polygon) / 4 - (box[3] - box[1]) / 2
            draw.text((px, py), value, fill="black", font=symbol_face)
    image.save(out)


def writer_prompt(plan: dict, symbols: dict[str, str], options: list[tuple[str, ...]], answer: str) -> str:
    return f"""你是广东省考图形推理命题人，只负责写一道已经冻结图形的题面和解析，不改变图形事实。
考法：{json.dumps(plan, ensure_ascii=False)}
展开图面符号：{json.dumps(symbols, ensure_ascii=False)}
选项从A到D依次为：{json.dumps(options, ensure_ascii=False)}；程序已验证唯一正确选项是{answer}。
输出JSON：{{"stem":"...","explanation":"..."}}。
cube_corner题干必须问“下列哪组三个面可以同时作为立方体的三个可见面”或同义表达；cube_opposite题干必须问“下列哪两个面互为相对面”或同义表达。题干不要泄露答案，解析只能指出相对面或三面共顶点的判断依据，不得声称程序没有验证的面内图案方向或镜像关系。"""


def image_part(path: Path) -> dict:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}}


def review_prompt(question: dict) -> str:
    return f"""你是独立的广东省考图形推理考生视角质检员。只看题面和实际图片。
题目：{question['stem']}
考法：{question['figure']['type']}；考察：{question['figure']['focus']}
程序答案：{question['answer']}
检查展开图和四个选项是否完整、黑白线条和符号是否清晰、题干是否真正依赖图形、是否只有程序答案一个选项成立。
只输出JSON：{{"verdict":"PASS或REJECT","readable":true,"image_required":true,"unique":true,"answer_matches":true,"issues":[]}}。"""


def main() -> int:
    started = time.monotonic()
    batch_id = dt.date.today().strftime("%Y%m%d") + "_hermes_space_cube_min_01"
    out = ROOT / "data" / "space-batches" / dt.date.today().isoformat() / batch_id
    image_dir = out / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    try:
        plans = normalize_plan(call(plan_prompt()))
    except Exception:
        plans = fallback_plan()
    jobs = []
    for index, plan in enumerate(plans, 1):
        rng = random.Random(f"{batch_id}-{index}")
        symbols = face_symbols(rng)
        options, answer_index = options_for(plan["type"], symbols, rng)
        answer = "ABCD"[answer_index]
        render_net(symbols, image_dir / f"q{index:02d}-stem.png")
        for option_index, values in enumerate(options):
            render_option(values, plan["type"], image_dir / f"q{index:02d}-{option_index}.png")
        jobs.append((index, plan, symbols, options, answer))

    def write(job):
        index, plan, symbols, options, answer = job
        try:
            return call(writer_prompt(plan, symbols, options, answer))
        except Exception:
            kind = "三个面" if plan["type"] == "cube_corner" else "两个面"
            return {"stem": f"下图展开图折叠后，以下哪{kind}符合题意？", "explanation": f"程序核验：正确选项为{answer}。"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        written = list(pool.map(write, jobs))
    questions = []
    for (index, plan, symbols, options, answer), text in zip(jobs, written):
        qid = f"{batch_id}-Q{index:02d}"
        questions.append({
            "external_id": qid, "category": "判断推理", "sub_category": "图形推理",
            "tags": ["判断推理-图形推理-空间类"], "question_type": "single",
            "stem": text.get("stem") or "下图中符合题意的是：", "stem_images": [f"images/q{index:02d}-stem.png"],
            "options": [{"key": "ABCD"[i], "text": "", "images": [f"images/q{index:02d}-{i}.png"]} for i in range(4)],
            "answer": answer, "explanation": text.get("explanation") or "", "difficulty": plan["difficulty"],
            "figure": {"kind": "cube_net", "net": NET, "symbols": symbols, "option_values": options,
                       "type": plan["type"], "focus": plan["focus"]},
        })
    checks = []
    for question in questions:
        figure = question["figure"]
        opposite = opposite_pairs(figure["symbols"])
        good = []
        for option in figure["option_values"]:
            good.append((not any(frozenset(pair) in opposite for pair in __import__("itertools").combinations(option, 2))) if figure["type"] == "cube_corner" else frozenset(option) in opposite)
        checks.append({"question_id": question["external_id"], "answer": question["answer"], "valid_options": ["ABCD"[i] for i, value in enumerate(good) if value], "pass": good.count(True) == 1 and good["ABCD".index(question["answer"])]})
    if not all(item["pass"] for item in checks):
        raise RuntimeError(f"deterministic geometry validation failed: {checks}")
    manifest = {
        "batch_id": batch_id,
        "kind": "examsystem-space-validation",
        "source": "广东省考行测-图形推理-空间专项",
        "region": "广东-省直",
        "year": dt.date.today().year,
        "question_count": 5,
        "created_at": dt.date.today().isoformat(),
        "validation": {
            "geometry": "geometry-check.json",
            "visual_review": "visual-reviews.json",
            "images": 25,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (out / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2))
    (out / "plan.json").write_text(json.dumps({"questions": plans}, ensure_ascii=False, indent=2))
    (out / "geometry-check.json").write_text(json.dumps({"checks": checks}, ensure_ascii=False, indent=2))
    def review(question: dict) -> dict:
        index = question["external_id"].rsplit("Q", 1)[1]
        parts = [{"type": "text", "text": review_prompt(question)}, {"type": "text", "text": "展开图"}, image_part(image_dir / f"q{index}-stem.png")]
        for letter, option_index in zip("ABCD", range(4)):
            parts.extend([{"type": "text", "text": "选项" + letter}, image_part(image_dir / f"q{index}-{option_index}.png")])
        try:
            return {"question_id": question["external_id"], **call_parts("独立质检，不要改写题目。", parts)}
        except Exception as exc:
            return {"question_id": question["external_id"], "verdict": "REJECT", "issues": [str(exc)]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        reviews = list(pool.map(review, questions))
    (out / "visual-reviews.json").write_text(json.dumps({"model": MODEL, "reviews": reviews}, ensure_ascii=False, indent=2))
    if not all(item.get("verdict") == "PASS" and all(item.get(key) is True for key in ("readable", "image_required", "unique", "answer_matches")) and not item.get("issues") for item in reviews):
        raise RuntimeError("Gemini visual review rejected at least one space question")
    (out / "timing.json").write_text(json.dumps({"seconds": round(time.monotonic() - started, 2), "plan_source": "Gemini with deterministic fallback", "question_count": 5}, ensure_ascii=False, indent=2))
    print(json.dumps({"batch": str(out), "questions": len(questions), "checks": checks, "seconds": round(time.monotonic() - started, 2)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

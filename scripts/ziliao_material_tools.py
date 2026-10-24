#!/usr/bin/env python3
"""资料分析单篇流水线的程序部分（不调模型）：舍入台账与合计、选项生成与排布、解析里的错误算式行。"""
from __future__ import annotations

import json
import math
import random
import re
from decimal import ROUND_HALF_UP, Decimal

from quality_orchestrator import safe_eval
from ziliao_tracks import KIND_CHART_MATCH, KIND_COUNT, skip_calculation

LETTERS = "ABCD"
NICE = (1, 2, 2.5, 5)
PLACEHOLDER = re.compile(r"\{\{\s*(G\d+)\s*\}\}")


def build_rounding(groups: list, rng: random.Random) -> tuple[list[dict], dict[str, str]]:
    """从分项展示值反推高精度底数，独立舍入出合计；至少一组保留真实舍入缺口。"""
    if not isinstance(groups, list) or not groups:
        raise ValueError("缺少groups：至少给1组穷尽分项及其合计占位符")
    built, totals = [], {}
    for group in groups:
        places = int(group["places"])
        quantum = Decimal(1).scaleb(-places)
        shown = [Decimal(str(p["shown"])).quantize(quantum, rounding=ROUND_HALF_UP) for p in group["parts"]]
        if not 2 <= len(shown) <= 24:
            raise ValueError(f"{group.get('id')}：分项须为2—24项")
        best = None
        for _ in range(400):
            raws = [s + Decimal(rng.randint(-49, 49)) * quantum / 100 for s in shown]
            total_raw = sum(raws)
            total_shown = total_raw.quantize(quantum, rounding=ROUND_HALF_UP)
            best = (raws, total_raw, total_shown)
            if sum(shown) != total_shown:
                break
        raws, total_raw, total_shown = best
        totals[str(group["id"])] = str(total_shown)
        built.append({
            "label": str(group.get("label") or group["id"]), "unit": str(group.get("unit") or ""), "places": places,
            "parts": [{"label": str(p["label"]), "raw": str(r), "shown": str(s)}
                      for p, r, s in zip(group["parts"], raws, shown)],
            "total": {"label": "合计", "raw": str(total_raw), "shown": str(total_shown)},
        })
    return built, totals


def fill_placeholders(value, totals: dict[str, str], numeric: bool = False):
    if isinstance(value, str):
        whole = PLACEHOLDER.fullmatch(value.strip())
        if whole and numeric:
            return float(totals[whole[1]])
        return PLACEHOLDER.sub(lambda m: totals[m[1]], value)
    if isinstance(value, list):
        return [fill_placeholders(v, totals, numeric) for v in value]
    if isinstance(value, dict):
        return {k: fill_placeholders(v, totals, numeric or k in ("values",)) for k, v in value.items()}
    return value


def finalize_material(raw: dict, rng: random.Random) -> dict:
    checks, totals = build_rounding(raw.get("groups"), rng)
    missing = set(PLACEHOLDER.findall(json.dumps([raw.get("content"), raw.get("figure")], ensure_ascii=False))) - set(totals)
    if missing:
        raise ValueError(f"占位符{sorted(missing)}没有对应的groups")
    content = fill_placeholders(str(raw.get("content") or ""), totals)
    figure = fill_placeholders(raw.get("figure") or {}, totals)
    if any(f"{{{{{gid}}}}}" not in json.dumps(raw, ensure_ascii=False).replace(" ", "") for gid in totals):
        raise ValueError("每组groups的合计须在正文或图表中用{{Gn}}占位出现")
    return {"content": content, "figure": figure, "rounding_checks": checks}


def mode_of(slot: dict) -> str:
    kind = slot.get("kind")
    if kind == KIND_CHART_MATCH:
        return "chart"
    if slot.get("option_format") in ("interval", "direction"):
        return slot["option_format"]
    if kind == KIND_COUNT:
        return "count"
    if slot.get("quick") or skip_calculation(slot) or kind in ("text_reading",):
        return "choice"
    from ziliao_blueprint import entity_answer
    if entity_answer(slot):  # “下列哪个最高”“占比上升的是”：选项是主体名称，不是数值
        return "choice"
    return "numeric"


POWER = re.compile(r"\^|\*\*")


def _power_eval(expression: str) -> float:
    import ast
    import operator
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow}

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -walk(node.operand) if isinstance(node.op, ast.USub) else walk(node.operand)
        raise ValueError(f"算式只能含数字、+-*/、^和括号：{expression}")

    return walk(ast.parse(expression.replace("^", "**"), mode="eval"))


def calc_value(expression):
    """写进验算记录的值：闸门求值器不支持乘方，含乘方的算式改记数值。"""
    text = str(expression).replace("×", "*").replace("÷", "/")
    return f"{_power_eval(text):.10g}" if POWER.search(text) else str(expression)


def evaluate(expression) -> float:
    text = str(expression).replace("×", "*").replace("÷", "/")
    if POWER.search(text):
        return _power_eval(text)
    return float(safe_eval(text))


def pretty(expression) -> str:
    text = str(expression).replace(" ", "").replace("**", "^")
    text = re.sub(r"\^\(1/(\d+)\)", r"开\1次方", text)
    text = re.sub(r"\^(\d+)", r"的\1次方", text)
    return text.replace("*", "×").replace("/", "÷")


def number_text(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def nice_steps(magnitude: float) -> list[float]:
    base = 10 ** math.floor(math.log10(max(magnitude, 1e-9)))
    return [n * base * scale for scale in (0.1, 1, 10) for n in NICE]


def edge_text(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _bin(value: float, edges: list[float]) -> int:
    return sum(value >= e for e in edges)


def interval_options(value: float, unit: str, position: int,
                     traps: list[float] | None = None) -> tuple[list[str], dict, int]:
    """整齐档位的四个首尾相接区间，按真题顺序从小到大；尽量让正确值落在预分配的位置，
    并让常见错法算出的值落进别的区间（错法与正确值同区间时陷阱就失效了）。"""
    magnitude, traps = abs(value), [t for t in traps or [] if math.isfinite(t)]
    steps = [s for s in sorted(nice_steps(magnitude), key=lambda s: abs(s - magnitude * 0.2))
             if magnitude * 0.06 <= s <= magnitude * 0.6]
    best = None
    for want in [position] + [p for p in range(4) if p != position]:
        for step in steps:
            k = math.floor(value / step)
            first = (k + 1) * step if want == 0 else (k - want + 1) * step
            edges = [first + i * step for i in range(3)]
            if value > 0 and edges[0] <= 0:
                continue
            if min(abs(value - e) for e in edges) / magnitude < 0.03:
                continue
            caught = sum(_bin(t, edges) != want and min(abs(t - e) for e in edges) / max(abs(t), 1e-9) >= 0.02
                         for t in traps)
            covered = len({_bin(t, edges) for t in traps} - {want})  # 有错法落入的错误档数，3 即每个错误选项都有来路
            score = (caught, covered, want == position)
            if best is None or score > best[0]:
                best = (score, edges, want)
        if best and best[0][0] == len(traps) and best[2] == position:
            break
    if best is None:
        raise ValueError(f"正确值{value:g}无法划出整齐区间")
    _, edges, want = best
    u = unit
    texts = [f"不到{edge_text(edges[0])}{u}", f"在{edge_text(edges[0])}{u}到{edge_text(edges[1])}{u}之间",
             f"在{edge_text(edges[1])}{u}到{edge_text(edges[2])}{u}之间", f"超过{edge_text(edges[2])}{u}"]
    ranges = {"A": [None, edges[0]], "B": [edges[0], edges[1]], "C": [edges[1], edges[2]], "D": [edges[2], None]}
    return texts, ranges, want


def direction_options(value: float, unit: str, up: str, down: str, position: int) -> tuple[list[str], dict, int]:
    magnitude = abs(value)
    if magnitude == 0:
        raise ValueError("升降题正确值不能为0")
    want_over = position in (1, 3)
    for step in sorted(nice_steps(magnitude), key=lambda s: abs(s - magnitude)):
        for threshold in (step, step * 2, step * 3, step * 4, step * 5):
            over = magnitude > threshold
            if over != want_over or abs(magnitude - threshold) / threshold < 0.05:
                continue
            x = edge_text(threshold)
            texts = [f"{up}不到{x}{unit}", f"{up}超过{x}{unit}", f"{down}不到{x}{unit}", f"{down}超过{x}{unit}"]
            ranges = {"A": [0, threshold], "B": [threshold, None], "C": [-threshold, 0], "D": [None, -threshold]}
            return texts, ranges, (0 if value > 0 else 2) + (1 if over else 0)
    raise ValueError(f"正确值{value:g}找不到合适的升降阈值")


PERCENT_TIMES_100 = re.compile(r"\s*[×*]\s*100\s*(?=[≈=＝]\s*-?\d+(?:\.\d+)?\s*[%％])")


def normalize_analysis(text: str) -> str:
    """“a÷b×100≈26.91%”里的×100与%重复（精度检查会再乘一次100），统一写成“a÷b≈26.91%”。"""
    return PERCENT_TIMES_100.sub("", text)


def map_letters(text: str, order: list[int]) -> str:
    return re.sub(r"\[(\d)\]", lambda m: f"{LETTERS[order.index(int(m[1]) - 1)]}项" if 1 <= int(m[1]) <= 4 else m[0], text)


def build_question(raw: dict, slot: dict, index: int, material_id: str) -> tuple[dict, dict]:
    """把出题员的算式与错误路径变成符合闸门格式的题目与验算。"""
    mode, qid = mode_of(slot), f"{material_id}-Q{index}"
    position = LETTERS.index(slot.get("answer_key") or "A")
    stem = str(raw.get("stem") or "").strip()
    analysis = normalize_analysis(str(raw.get("analysis") or "").strip())
    question = {"external_id": qid, "category": "资料分析", "question_type": "single", "material_id": material_id,
                "tags": [slot["tag"]], "difficulty": int(slot.get("difficulty_score") or 2), "family": slot.get("family")}
    calc = {"question_id": qid}
    if mode == "numeric":
        decimals = int(raw.get("decimals") if raw.get("decimals") is not None else 1)
        unit = str(raw.get("unit") or "")
        items = [(str(raw["correct_expr"]), "正确", True)] + [(str(d["expr"]), str(d.get("why") or ""), False)
                                                           for d in raw.get("distractors") or []]
        if len(items) != 4:
            raise ValueError("须给出正确算式和3个干扰算式")
        valued = sorted(((evaluate(e), e, why, ok) for e, why, ok in items), key=lambda x: x[0])
        correct_at = next(i for i, item in enumerate(valued) if item[3])
        if correct_at != position:  # 出题员没按位置给干扰值时，其余仍升序，正确项放到预定位置
            valued.insert(position, valued.pop(correct_at))
        options, lines = [], []
        for key, (value, expr, why, ok) in zip(LETTERS, valued):
            options.append({"key": key, "text": number_text(value, decimals) + unit})
            calc.setdefault("options", {})[key] = calc_value(expr)
            shown = (f"{pretty(expr)}≈{value:.{decimals + 1}f}" if re.search(r"\d\s*[-+*/^]", str(expr).strip().lstrip("-"))
                     else f"{value:g}")
            lines.append(f"{key}项：{shown}，" + ("为正确答案。" if ok else f"{why}。"))
            if ok:
                question["answer"], calc["correct"] = key, calc_value(expr)
        calc["tolerance"] = 1e-9
        explanation = analysis + "\n" + "\n".join(lines)
    elif mode in ("interval", "direction"):
        value, unit = evaluate(raw["value_expr"]), str(raw.get("unit") or "")
        traps = [(str(d["expr"]), str(d.get("why") or ""), evaluate(d["expr"])) for d in raw.get("distractors") or []]
        if mode == "interval":
            texts, ranges, hit = interval_options(value, unit, position, [t[2] for t in traps])
        else:
            texts, ranges, hit = direction_options(value, unit, str(raw.get("up") or "上升了"),
                                                   str(raw.get("down") or "下降了"), position)
        options = [{"key": k, "text": t} for k, t in zip(LETTERS, texts)]
        question["answer"] = LETTERS[hit]
        calc.update(correct=calc_value(raw["value_expr"]), ranges=ranges)
        decimals = int(raw.get("decimals") if raw.get("decimals") is not None else 1)
        edges = [ranges["B"][0], ranges["C"][0], ranges["D"][0]] if mode == "interval" else None
        lines = [f"若{why}：{pretty(expr)}≈{v:.{decimals + 1}f}"
                 + (f"，会误选{LETTERS[_bin(v, edges)]}项" if edges and _bin(v, edges) != hit else "")
                 for expr, why, v in traps]
        explanation = (analysis + f"\n算得{pretty(raw['value_expr'])}≈{value:.{decimals + 1}f}，"
                       f"对应“{texts[hit]}”，故选{LETTERS[hit]}项。" + ("\n" + "；".join(lines) + "。" if lines else ""))
    elif mode == "count":
        value = int(round(evaluate(raw["value_expr"])))
        start = max(1 if value >= 1 else 0, value - position)
        counts = list(range(start, start + 4))
        unit = str(raw.get("unit") or "个")
        options = [{"key": k, "text": f"{c}{unit}"} for k, c in zip(LETTERS, counts)]
        question["answer"] = LETTERS[counts.index(value)]
        calc.update(correct=value, options={k: c for k, c in zip(LETTERS, counts)}, tolerance=1e-9)
        explanation = analysis + f"\n满足条件的共{value}{unit}，故选{question['answer']}项。"
    elif mode == "choice":
        given = raw.get("options") or []
        correct = int(raw["correct"])
        if len(given) != 4 or not 0 <= correct <= 3:
            raise ValueError("须给出4个选项和正确序号0—3")
        order = [i for i in range(4) if i != correct]
        order.insert(position, correct)
        options = [{"key": k, "text": str(given[i]["text"])} for k, i in zip(LETTERS, order)]
        question["answer"] = LETTERS[position]
        calc.update(correct=1, options={k: int(i == correct) for k, i in zip(LETTERS, order)}, tolerance=1e-9)
        explanation = map_letters(analysis, order) + f"\n故正确答案为{LETTERS[position]}项。"
        judge_stem = str(slot.get("judge_stem") or "")
        if judge_stem and judge_stem not in stem:
            stem = judge_stem + "（ ）"
    else:  # chart
        chart = raw.get("chart") or {}
        target = [evaluate(e) for e in raw.get("target") or []]
        figures = [[round(v, 2) for v in target]] + [[float(v) for v in d.get("values") or []]
                                                      for d in raw.get("distractors") or []]
        whys = ["正确"] + [str(d.get("why") or "") for d in raw.get("distractors") or []]
        if len(figures) != 4:
            raise ValueError("图表匹配须给出正确图target和3个干扰图")
        order = [1, 2, 3]
        order.insert(position, 0)
        options = [{"key": k, "text": "", "figure": {"kind": chart.get("kind"), "categories": chart.get("categories"),
                                                     "values": figures[i]}} for k, i in zip(LETTERS, order)]
        question["answer"] = LETTERS[position]
        calc.update(correct=1, options={k: int(i == 0) for k, i in zip(LETTERS, order)}, tolerance=1e-9,
                    target=[str(e) for e in raw.get("target") or []])
        explanation = analysis + "\n" + "\n".join(f"{k}项：{whys[i]}" for k, i in zip(LETTERS, order) if i)
    question.update(stem=stem, options=options, explanation=explanation)
    return question, calc

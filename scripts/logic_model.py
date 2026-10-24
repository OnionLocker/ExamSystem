#!/usr/bin/env python3
"""演绎类逻辑题的形式化判定：穷举有限情形，确定哪些选项满足设问、答案是否唯一。

命题人把题干写成变量与约束，把每个选项写成表达式；判定交给程序，不靠模型逐句自证。
适用翻译推理、真假推理、组合排列（分析推理）。论证类（加强、削弱、解释等）不适用。

formal 结构：
  {
    "vars": [{"name": "甲", "values": ["1", "2", "3"]}, {"name": "面试", "values": ["bool"]}],
    "background": ["distinct(甲, 乙, 丙)"],   # 题目结构设定（每人一个、只选一人、无并列），不查冗余
    "constraints": ["implies(面试, 笔试)", "exactly(1, 甲说真, 乙说真)"],
    "options": {"A": "甲 == 1", "B": "...", "C": "...", "D": "..."},
    "ask": "must_true",
    "conclusion": "...",   # ask=sufficient_premise 时必填
    "target": "..."        # ask=max/min 时必填，选项写成数值
  }

表达式是 Python 语法子集：and/or/not、比较、in、+ - * %、整数与带引号字符串，以及
implies(p, q)、iff(p, q)、count(...)、exactly/atleast/atmost(k, ...)、distinct(...)、adjacent(a, b)、abs(x)。

用法：python3 scripts/logic_model.py formal.json [--answer B]
"""
from __future__ import annotations

import ast
import itertools
import json
import re
import sys

MAX_SPACE = 400_000
KEYS = ("A", "B", "C", "D")

ASKS = {
    "must_true": "一定为真",
    "must_false": "一定为假",
    "possible": "可能为真",
    "not_must_true": "不一定为真",
    "sufficient_premise": "补充后能推出结论",
    "max": "最大值",
    "min": "最小值",
}

FUNCS = {
    "implies": lambda p, q: (not p) or bool(q),
    "iff": lambda p, q: bool(p) == bool(q),
    "count": lambda *xs: sum(bool(x) for x in xs),
    "exactly": lambda k, *xs: sum(bool(x) for x in xs) == k,
    "atleast": lambda k, *xs: sum(bool(x) for x in xs) >= k,
    "atmost": lambda k, *xs: sum(bool(x) for x in xs) <= k,
    "distinct": lambda *xs: len(set(xs)) == len(xs),
    "adjacent": lambda a, b: abs(a - b) == 1,
    "abs": abs,
    "int": int,
    "min": min,
    "max": max,
}

ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
           ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Mod, ast.Compare, ast.Eq, ast.NotEq, ast.Lt,
           ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Name, ast.Load, ast.Constant, ast.Tuple,
           ast.List, ast.Call)


DEDUCTION_WORDS = ("翻译推理", "真假推理", "组合排列", "分析推理", "分析类")


def family_of(tag) -> str:
    """逻辑判断标签 → 题型族：deduction（可形式化）/ structure / daily / argument。"""
    text = str(tag or "")
    if any(word in text for word in DEDUCTION_WORDS):
        return "deduction"
    if "论证结构" in text:
        return "structure"
    if "日常结论" in text:
        return "daily"
    return "argument"


class FormalError(ValueError):
    pass


def _value(raw):
    if isinstance(raw, bool) or isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text.lower() in ("true", "真"):
        return True
    if text.lower() in ("false", "假"):
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse_vars(spec) -> dict[str, list]:
    """vars 可写成 [{"name","values"}] 或 {"名": [取值]}；取值写 "bool" 表示真/假两种。"""
    items = spec.items() if isinstance(spec, dict) else (
        (row.get("name"), row.get("values")) for row in spec or [] if isinstance(row, dict))
    domains: dict[str, list] = {}
    for name, values in items:
        name = str(name or "").strip()
        if not name.isidentifier() or name in FUNCS or name in ("True", "False"):
            raise FormalError(f"变量名不合法：{name!r}（须为不含空格和符号的标识符，不能与函数同名）")
        if name in domains:
            raise FormalError(f"变量重复声明：{name}")
        values = list(values or [])
        if [str(v).lower() for v in values] in (["bool"], ["boolean"]):
            values = [False, True]
        values = list(dict.fromkeys(_value(v) for v in values))
        if not values:
            raise FormalError(f"变量 {name} 没有取值")
        domains[name] = values
    if not domains:
        raise FormalError("形式化缺少变量")
    return domains


def compile_expr(text, names: set[str], label: str):
    source = str(text or "").strip()
    if not source:
        raise FormalError(f"{label} 表达式为空")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise FormalError(f"{label} 表达式语法错误：{source}（{exc.msg}）") from None
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED):
            raise FormalError(f"{label} 含不允许的语法 {type(node).__name__}：{source}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in FUNCS and not node.keywords):
            raise FormalError(f"{label} 只能调用 {'/'.join(FUNCS)}：{source}")
        if isinstance(node, ast.Name) and node.id not in names and node.id not in FUNCS and node.id not in ("True", "False"):
            raise FormalError(f"{label} 用了未声明的变量 {node.id}：{source}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (bool, int, str)):
            raise FormalError(f"{label} 常量只能是整数、真假或字符串：{source}")
    return compile(tree, f"<{label}>", "eval")


def _squash(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def solve(formal: dict) -> dict:
    """穷举全部情形，返回每个选项的状态与满足设问的选项。"""
    if not isinstance(formal, dict):
        raise FormalError("formal 必须是对象")
    ask = str(formal.get("ask") or "").strip()
    if ask not in ASKS:
        raise FormalError(f"ask 只能是 {'/'.join(ASKS)}，收到 {ask!r}")
    domains = parse_vars(formal.get("vars"))
    names = set(domains)
    space = 1
    for values in domains.values():
        space *= len(values)
    if space > MAX_SPACE:
        raise FormalError(f"情形总数 {space} 超过 {MAX_SPACE}，请缩小取值范围或改用更紧凑的变量")
    constraints = [compile_expr(c, names, f"设定{i + 1}") for i, c in enumerate(formal.get("background") or [])]
    constraints += [compile_expr(c, names, f"约束{i + 1}") for i, c in enumerate(formal.get("constraints") or [])]
    if not formal.get("constraints"):
        raise FormalError("形式化缺少题干约束")
    options = formal.get("options") or {}
    if sorted(options) != list(KEYS):
        raise FormalError("options 须恰好给出 A/B/C/D 四项")
    numeric = ask in ("max", "min")
    if numeric:
        target = compile_expr(formal.get("target"), names, "target")
        try:
            wanted = {key: int(str(options[key]).strip()) for key in KEYS}
        except ValueError:
            raise FormalError("ask=max/min 时选项须写成整数") from None
        compiled = {}
    else:
        compiled = {key: compile_expr(options[key], names, f"选项{key}") for key in KEYS}
    conclusion = compile_expr(formal.get("conclusion"), names, "conclusion") if ask == "sufficient_premise" else None

    env_globals = {"__builtins__": {}, **FUNCS}
    order = list(domains)
    models = 0
    truth = {key: [0, 0] for key in KEYS}          # [成立次数, 不成立次数]
    premise = {key: [0, 0] for key in KEYS}        # sufficient_premise：[加上后情形数, 其中结论不成立数]
    values_seen: set = set()
    for combo in itertools.product(*(domains[n] for n in order)):
        env = dict(zip(order, combo))
        try:
            if not all(eval(code, env_globals, env) for code in constraints):
                continue
            models += 1
            if numeric:
                values_seen.add(eval(target, env_globals, env))
                continue
            concl = eval(conclusion, env_globals, env) if conclusion is not None else None
            for key, code in compiled.items():
                held = bool(eval(code, env_globals, env))
                truth[key][0 if held else 1] += 1
                if conclusion is not None and held:
                    premise[key][0] += 1
                    premise[key][1] += 0 if concl else 1
        except FormalError:
            raise
        except Exception as exc:  # 类型不匹配等：如字符串与整数比较
            raise FormalError(f"表达式求值出错：{type(exc).__name__}: {exc}") from None

    status, correct = {}, []
    if numeric:
        best = (max if ask == "max" else min)(values_seen) if values_seen else None
        for key in KEYS:
            status[key] = f"{wanted[key]}" + ("（=" + ASKS[ask] + "）" if wanted[key] == best else "")
            if best is not None and wanted[key] == best:
                correct.append(key)
    else:
        for key in KEYS:
            yes, no = truth[key]
            if models == 0:
                status[key] = "题干无可行情形"
            elif no == 0:
                status[key] = "一定为真"
            elif yes == 0:
                status[key] = "一定为假"
            else:
                status[key] = "可能为真也可能为假"
            hit = {
                "must_true": models and no == 0,
                "must_false": models and yes == 0,
                "possible": yes > 0,
                "not_must_true": models and no > 0,
                "sufficient_premise": premise[key][0] > 0 and premise[key][1] == 0,
            }[ask]
            if ask == "sufficient_premise":
                status[key] = ("补充后能推出结论" if hit else
                               "补充后与题干矛盾" if premise[key][0] == 0 else "补充后仍推不出结论")
            if hit:
                correct.append(key)
    result = {"ask": ask, "space": space, "models": models, "options": status, "correct": correct}
    if numeric:
        result["target_values"] = sorted(values_seen)[:20]
    return result


REDUNDANT_MAX = 1          # 去掉后答案仍唯一的条件最多 1 条（真题偶有铺垫条件）
NEEDED_MIN = 2             # 真正参与推出答案的条件至少 2 条，杜绝一条件一步推出
DEPTH_SPACE_MAX = 50_000   # 逐条删减要重算多次，情形太多时不做深度检查


def redundant_constraints(formal: dict, answer: str) -> list[int]:
    """逐条去掉题干条件重判：去掉后仍恰好推出同一答案的条件，说明对作答无用。"""
    constraints = list(formal.get("constraints") or [])
    redundant = []
    for index in range(len(constraints)):
        reduced = {**formal, "constraints": constraints[:index] + constraints[index + 1:]}
        if not reduced["constraints"]:
            continue
        try:
            result = solve(reduced)
        except FormalError:
            continue
        if result["models"] and result["correct"] == [answer]:
            redundant.append(index)
    return redundant


def check(formal: dict, answer: str, *, depth: bool = True) -> dict:
    """判定并核对唯一答案；depth=True 时另查条件是否凑数。issues 为空即通过；措辞直接给命题人看。"""
    try:
        result = solve(formal)
    except FormalError as exc:
        return {"verdict": "REJECT", "issues": [f"形式化无法判定：{exc}"]}
    issues = []
    answer = str(answer or "").strip().upper()
    status = "；".join(f"{k}：{v}" for k, v in result["options"].items())
    if result["models"] == 0:
        issues.append("按形式化，题干条件自相矛盾，没有任何情形同时满足全部条件")
    elif not result["correct"]:
        issues.append(f"按形式化，没有选项满足设问「{ASKS[result['ask']]}」（{status}）")
    elif len(result["correct"]) > 1:
        issues.append(f"按形式化，{'、'.join(result['correct'])} 都满足设问「{ASKS[result['ask']]}」，答案不唯一（{status}）")
    elif result["correct"] != [answer]:
        issues.append(f"按形式化，满足设问的是 {result['correct'][0]}，题面键定 {answer}（{status}）")
    if not issues and result["ask"] in ("must_true", "possible"):
        given = {_squash(c) for c in [*(formal.get("background") or []), *(formal.get("constraints") or [])]}
        if _squash((formal.get("options") or {}).get(answer)) in given:
            issues.append("正确项只是复述题干已给条件，不需要推理，须改为推出的新结论")
    if not issues and depth and result["space"] <= DEPTH_SPACE_MAX:
        constraints = list(formal.get("constraints") or [])
        redundant = redundant_constraints(formal, answer)
        needed = len(constraints) - len(redundant)
        result["redundant"] = redundant
        if len(redundant) > REDUNDANT_MAX:
            issues.append("题干条件凑数：去掉第 " + "、".join(str(i + 1) for i in redundant)
                          + " 条约束后答案仍唯一，题目一两步就能做完；每个条件都要参与推理，或改用让这些条件起作用的设问")
        elif needed < NEEDED_MIN:
            issues.append(f"只靠 {needed} 个条件就能推出答案，达不到广东省考真题的推理量；须让至少两个条件串联或交叉才能定答案")
    return {**result, "verdict": "PASS" if not issues else "REJECT", "issues": issues}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="演绎类逻辑题形式化判定")
    parser.add_argument("formal", help="formal JSON 文件路径，- 表示标准输入")
    parser.add_argument("--answer", default="")
    args = parser.parse_args(argv)
    text = sys.stdin.read() if args.formal == "-" else open(args.formal, encoding="utf-8").read()
    formal = json.loads(text)
    out = check(formal, args.answer) if args.answer else solve(formal)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not args.answer or out.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

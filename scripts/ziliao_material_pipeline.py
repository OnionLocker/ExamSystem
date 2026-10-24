#!/usr/bin/env python3
"""资料分析单篇流水线（职责拆分）：材料员 → 程序核对 → 材料审核 → 出题员 → 程序排选项 → 单题回修 → 篇内闸门。

每个模型请求只拿本角色需要的提示词和数据，不带历史对话：
- 材料员只写正文、图表与分项；合计与舍入台账由程序从高精度底数独立舍入生成；
- 出题员只写题干、解析与各选项的算式/错误路径；选项文字、精度、顺序与“X项：错误算式=结果”由程序生成；
- 回修只给被拒的那道题、反馈与同篇题干摘要。
产物目录与 ziliao_agent_trial 的 worker 一致，可直接走 generation_gate 与整卷组装。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ziliao_agent_trial import Trial  # noqa: E402

import ziliao_parallel_runner as runner  # noqa: E402
from generation_gate import verify  # noqa: E402
from generation_progress import Job  # noqa: E402
from kaofa_variants import record_variants  # noqa: E402
from service_node import service_node  # noqa: E402
from ziliao_material_tools import LETTERS, build_question, finalize_material, mode_of  # noqa: E402
from ziliao_checklist import KIND_STEM_RULES, material_text_issues, rounding_issues  # noqa: E402
from ziliao_tracks import (MATERIAL_TYPES, ZILIAO_FIGURE_RULES, ZILIAO_INFERENCE_RULES,  # noqa: E402
                           material_question_plan, slot_difficulty_rules, track_material_rules, typical_error_rules)

ROOT = Path(__file__).resolve().parents[1]
MATERIAL_TRIES = 4
QUESTION_TRIES = 3
GATE_TRIES = 3

FIGURE_SHAPE = ("bars的categories为4-8个、line为5-8期，每个series.values为等长非空数字数组；pie只有一个series，"
                "categories为3-6个部分名称、values为各部分绝对量；table至少6行、至少4列。不要双轴。")
NATURAL = ("数字要像真实统计公报：数值带自然的小数与尾数，不要整十整百或末位全是0/5；"
           "百分比至少三分之二带一位小数；各分项、各年份有高有低，增速有快有慢。")
GROUP_RULE = (
    "凡“若干分项加起来等于一个合计”的数据（地区合计、门类合计、全年合计等），写进groups："
    "{\"id\":\"G1\",\"label\":\"2024年××合计\",\"unit\":\"亿元\",\"places\":1,"
    "\"parts\":[{\"label\":\"甲\",\"shown\":\"114.4\"},…]}，parts须穷尽该合计的全部分项（2—8项），shown按places位小数书写。"
    "正文和图表里该合计一律写占位符{{G1}}（图表数值处写字符串\"{{G1}}\"），不要自己算合计——程序会从高精度底数独立舍入后填入，"
    "因此合计可能与分项相加差0.1左右，这是正常的舍入缺口。至少给1组、至多4组。")

class Stats:
    def __init__(self, log: Path):
        self.log, self.started = log, time.monotonic()
        self.stages: dict[str, float] = {}
        self.rejections: list[dict] = []

    def reject(self, stage: str, target: str, reasons: list[str]) -> None:
        self.rejections.append({"stage": stage, "target": target, "reasons": [str(r)[:300] for r in reasons]})

    def requests(self) -> Counter:
        return Counter(self.log.read_text().split()) if self.log.is_file() else Counter()


GENERAL_RULES = """只依据材料数据命题，不用材料外常识；分子分母同口径（同年份、同范围、同单位）。
题干用广东省考真题口吻，结尾带“（ ）”。
解析像老师讲题：先写从材料哪里取数，再写算式；算式等号右边写算好的结果，保留两位小数，必须算准；百分数写成“318.7÷1184.3≈26.91%”，不要再写×100。
解析里不写A、B、C、D等选项字母，也不逐项评价选项；选项文字、顺序和各选项的错误算式由程序根据你给的算式生成。
干扰项必须是考生真会犯的错并写清错法；禁止“计算失误、估算误差、粗心”这类空话，禁止除以(1+2r)、乘无关系数这类凑数公式。
算式只含数字与+-*/()；乘方、开方用^（如((a/b)^(1/4)-1)*100），解析正文里写“开4次方”，不写^。"""

NUMERIC_RULES = "正确值不得恰好是整数百分比或整数倍；四个选项两两相对差距至少3%，估算即可区分。"

MODE_RULES = {
    "interval": "选项是四个首尾相接的区间，由程序按整齐档位生成；你给正确值算式和3个不同的常见错法算式（结果大小要拉开，有偏大也有偏小），程序会让每个错误区间都对应一种错法。",
    "direction": "选项是“上升了不到X／上升了超过X／下降了不到X／下降了超过X”，由程序生成；你给带符号的正确值算式（下降为负）和1—2个常见错法算式。",
    "count": "解析逐一列出每个主体或时期的判断算式与结论，再汇总个数；四个个数选项由程序生成。",
}
KIND_RULES = {
    "sort": "选项为四种不同排列（用主体名和“＞”连接），解析逐项算出排序依据的数值。",
    "text_reading": "四个选项是对原文的表述，错项与原文有明确出入；解析指出每项对应的原文依据。",
    "detail_lookup": "直接定位或读数，一步可得，不做计算；解析指出数据在材料中的位置。",
}

MODE_CONTRACT = {
    "numeric": ('{"stem":"…（ ）","analysis":"取数与正确答案的算式",'
                '"unit":"选项单位，如%、亿元、倍、个百分点","decimals":选项保留的小数位数,'
                '"correct_expr":"正确值算式（百分数写成×100后的数值）",'
                '"distractors":[{"expr":"错误算式","why":"错法，如漏除(1+r)、用现期代替基期"},…共3个]}'),
    "interval": ('{"stem":"…（ ）","analysis":"取数与正确答案的算式","unit":"%或亿元等","decimals":1,'
                 '"value_expr":"正确值算式","distractors":[{"expr":"常见错法算式","why":"错法，如用现期作分母"},…共3个，三种不同错法]}'),
    "direction": ('{"stem":"…（ ）","analysis":"取数与正确答案的算式","unit":"个百分点或亿元等","decimals":1,'
                  '"value_expr":"带符号的正确值算式","up":"上升了/增加了","down":"下降了/减少了",'
                  '"distractors":[{"expr":"常见错法算式","why":"错法，如直接相减两增速"},…1—2个]}'),
    "count": '{"stem":"…有几个（ ）","analysis":"逐一判断的算式与结论","value_expr":"正确个数（整数）","unit":"个或项"}',
    "choice": ('{"stem":"…（ ）","options":[{"text":"选项内容","why":"成立或不成立的依据"},…共4个],"correct":正确选项序号0-3,'
               '"analysis":"用[1][2][3][4]指代四个选项逐项分析，每项写出取数与算式"}'),
    "chart": ('{"stem":"下列哪幅图最能准确反映……（ ）","analysis":"正确图各点的算式与走势",'
              '"chart":{"kind":"line或pie","categories":["期次或部分名称"]},'
              '"target":["正确图各点的算式，与categories一一对应"],'
              '"distractors":[{"values":[与categories等长的数值],"why":"对应的真实错误，如把增量当增速"},…共3个]}'),
}

CALL_DIR: Path | None = None
_CALL_LOCK = threading.Lock()
HEDGE_AFTER = {"material": 75, "material_repair": 75, "questions": 60, "question_repair": 60}
HEDGES: list[str] = []


def _archive(role: str, prompt: str, response, error) -> None:
    if not CALL_DIR:
        return
    with _CALL_LOCK:
        CALL_DIR.mkdir(parents=True, exist_ok=True)
        index = len(list(CALL_DIR.glob("*.json"))) + 1
        (CALL_DIR / f"{index:02d}-{role}.json").write_text(json.dumps(
            {"role": role, "prompt": prompt, "response": response, "error": error}, ensure_ascii=False, indent=1))


def _ask_once(role: str, prompt: str, max_tokens: int) -> dict:
    response, error = None, None
    try:
        response = runner.call(prompt, max_tokens, role=role)
        return response
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _archive(role, prompt, response, error)


def ask(role: str, prompt: str, max_tokens: int = 12000) -> dict:
    """单次请求超过阈值仍未返回，就补发一次同样的请求，用先成功的那个；慢的那个在守护线程里自行结束。"""
    delay = HEDGE_AFTER.get(role)
    if not delay:
        return _ask_once(role, prompt, max_tokens)
    results: queue.Queue = queue.Queue()

    def worker(tag: str) -> None:
        try:
            results.put((tag, _ask_once(tag, prompt, max_tokens), None))
        except Exception as exc:
            results.put((tag, None, exc))

    threading.Thread(target=worker, args=(role,), daemon=True).start()
    try:
        tag, value, error = results.get(timeout=delay)
        if error is None:
            return value
        raise error
    except queue.Empty:
        HEDGES.append(role)
        threading.Thread(target=worker, args=(role + "_hedge",), daemon=True).start()
    errors = []
    for _ in range(2):
        tag, value, error = results.get()
        if error is None:
            return value
        errors.append(error)
    raise errors[0]


# ---------------------------------------------------------------- 材料
def material_needs(plan: dict) -> str:
    judge = next((s for s in plan["slots"] if s.get("kind") == "judge"), {})
    extra = f"第5题综合分析的考查组合是：{judge['judge_mix']}材料须提供能支撑这种判断的数据。" if judge.get("judge_mix") else ""
    return plan["question_plan"] + extra


def material_prompt(plan: dict) -> str:
    kind = runner.figure_kind(plan)
    return f"""你是资料分析材料员，只写一篇原创统计材料，不出题。
主题：{plan['theme']}；地区：{plan['region']}；难度：{plan['difficulty']}。
材料形态：figure.kind必须为「{kind}」（none表示纯文字）。{FIGURE_SHAPE}
本篇5道题已经分配好，材料必须提供它们要用的数据：{material_needs(plan)}
{track_material_rules('gd', plan)}
{ZILIAO_FIGURE_RULES}
地名用广东省及其地市真实名称，禁止G省、S市、某省等占位；不写“按现价计算”“四舍五入”等附注。
{NATURAL}
{GROUP_RULE}
只输出JSON：{{"content":"正文","figure":{{"kind":"{kind}","title":"…","unit":"…","headers":[],"rows":[],"categories":[],"series":[]}},"groups":[…]}}"""


def material_repair_prompt(plan: dict, previous: dict, issues: list[str]) -> str:
    return (f"你是资料分析材料员。下面是你上一版材料（JSON），未通过检查。只修正列出的问题，其余保持不变；"
            f"合计仍用占位符{{{{G1}}}}，groups规则不变。\n{GROUP_RULE}\n{NATURAL}\n"
            f"本篇题目所需数据：{material_needs(plan)}\n上一版：{json.dumps(previous, ensure_ascii=False)}\n"
            f"问题：\n- " + "\n- ".join(issues) + "\n只输出修正后的完整JSON（content、figure、groups）。")


def issues_of(result: dict) -> list[str]:
    if result.get("material_review"):
        review = result["material_review"]
        return [str(i) for i in review.get("issues") or []] or [json.dumps(review, ensure_ascii=False)[:600]]
    items = result.get("issues") or []
    return [str(i.get("message") if isinstance(i, dict) else i) for i in items] or [str(result.get("error") or result)]


def local_material_issues(trial: Trial, candidate: dict) -> list[str]:
    """与 Trial.submit_material 的本地检查一致，先在不花审核请求的情况下拦掉。"""
    kind = runner.figure_kind(trial.plan)
    if (not candidate.get("content") or (candidate.get("figure") or {}).get("kind") != kind
            or not runner.valid_material({"material": candidate})):
        return [f"须非空正文和指定figure.kind={kind}，图表规格见要求"]
    return (runner.material_realism_errors(candidate, track="gd", long_text=trial.plan["format"] == "text")
            + rounding_issues(candidate) + material_text_issues(candidate) + trial.figure_shape_issues(candidate))


def make_material_and_drafts(trial: Trial, plan: dict, slots: list[dict], stats: Stats, progress,
                             rng: random.Random) -> dict[int, dict]:
    """材料过本地检查后，材料审核与5题初稿同时进行；审核不过才丢弃初稿重来。材料定稿后后台先查材料图。"""
    raw = ask("material", material_prompt(plan))
    for attempt in range(1, MATERIAL_TRIES + 1):
        try:
            candidate = finalize_material(raw, rng)
            issues = local_material_issues(trial, candidate)
        except Exception as exc:
            candidate, issues = None, [f"{type(exc).__name__}: {exc}"]
        drafts: dict[int, dict] = {}
        if not issues:
            progress.update(stage="材料审核", detail="材料审核与5题初稿同时进行", progress=25)
            with ThreadPoolExecutor(max_workers=2) as pool:
                review = pool.submit(trial.submit_material, json.loads(json.dumps(candidate)))
                drafting = pool.submit(ask_many, "questions",
                                       {i: question_prompt(candidate, slots, i) for i in range(1, 6)})
                result = review.result()
                if result.get("ok"):
                    stats.stages["材料"] = round(time.monotonic() - stats.started, 1)
                    threading.Thread(target=precheck_images, args=(trial.out,), daemon=True).start()
                    drafts = drafting.result()
                    return drafts
                drafting.result()
            issues = issues_of(result)
            stats.reject("material_review", "材料", issues)
        else:
            stats.reject("material_check", "材料", issues)
        progress.update(stage="材料", detail=f"材料第{attempt}版未过：{issues[0][:60]}", progress=10 + attempt * 3)
        if attempt == MATERIAL_TRIES:
            raise RuntimeError("材料多次修正仍未通过：" + "；".join(issues[:3]))
        raw = ask("material_repair", material_repair_prompt(plan, raw, issues))
    raise RuntimeError("材料未完成")


def precheck_images(out: Path) -> None:
    try:
        from ziliao_visual_gate import precheck_material_images
        precheck_material_images(out)
    except Exception:
        pass  # 只是提前缓存，失败了篇内审核会照常检查


def align_answers(trial: Trial, slots: list[dict], raws: dict[int, dict], planned: list[str], stats: Stats) -> None:
    """让本篇5题的答案字母组合与蓝图一致。先算出每题实际能落到哪些字母（区间要隔开错法、个数按数值排，
    不是每个位置都可行），再找改动最少的分配；纯程序计算，不调模型。"""
    ids = {i: f"{trial.material_id}-Q{i}" for i in range(1, 6)}
    current = {i: trial.questions[ids[i]]["answer"] for i in ids}
    if Counter(current.values()) == Counter(planned):
        return
    reachable: dict[int, dict[str, str]] = {}
    unnatural: set[tuple[int, str]] = set()  # 数值题只有打乱升序才能落到的字母，尽量不用
    for i in ids:
        options = {}
        for key in LETTERS:
            try:
                built, _ = build_question(raws[i], dict(slots[i - 1], answer_key=key), i, trial.material_id)
            except Exception:
                continue
            options.setdefault(built["answer"], key)
            if mode_of(slots[i - 1]) == "numeric":
                values = [float(re.sub(r"[^\d.\-]", "", o["text"]) or 0) for o in built["options"]]
                if values != sorted(values):
                    unnatural.add((i, built["answer"]))
        reachable[i] = options or {current[i]: slots[i - 1].get("answer_key") or current[i]}
    target = Counter(planned)
    best: list = [None, (-1, -99)]

    def search(i: int, chosen: dict, left: Counter, score: tuple) -> None:
        if i > 5:
            if score > best[1]:
                best[0], best[1] = dict(chosen), score
            return
        for letter in sorted(reachable[i], key=lambda l: l != current[i]):
            if left[letter] > 0:
                left[letter] -= 1
                chosen[i] = letter
                search(i + 1, chosen, left, (score[0] - ((i, letter) in unnatural),
                                             score[1] + (letter == current[i])))
                left[letter] += 1
                chosen.pop(i)

    search(1, {}, target.copy(), (0, 0))
    if best[0] is None:
        stats.reject("answer_align", "字母对齐", [f"无法凑成蓝图答案组合{planned}，保留现状{list(current.values())}"])
        return
    built, calcs = [], []
    for i, letter in best[0].items():
        if letter == current[i]:
            continue
        slots[i - 1]["answer_key"] = reachable[i][letter]
        q, c = build_question(raws[i], slots[i - 1], i, trial.material_id)
        built.append(q)
        calcs.append(c)
    result = trial.put_questions(built, calcs)
    if not result.get("ok"):
        stats.reject("answer_align", "字母对齐", issues_of(result))


# ---------------------------------------------------------------- 出题
def slot_rules(slot: dict) -> str:
    kind, mode = str(slot.get("kind") or ""), mode_of(slot)
    if kind == "judge":
        form = ("四句陈述放在题干里并编号①②③④，四个选项为“1个／2个／3个／4个”。"
                if slot.get("judge_form") == "计数" else "四个选项各是一句陈述。")
        return (f"题干必须以「{slot.get('judge_stem')}」开头，不得改成其他问法。{form}"
                f"考查组合：{slot.get('judge_mix') or ''}每句陈述都能用材料数据核算，解析每句写出取数与算式，"
                "至少两句需要计算；错误的陈述必须确实不成立，解析写“不成立/与材料不符”，不要写“无法判断”（除非确实缺数据）；"
                "“百分点与百分比”“累计当当年”“缺数据无法比较”这类文字陷阱至多一句。\n"
                + ZILIAO_INFERENCE_RULES)
    if slot.get("quick"):
        return ("定性判断：逐项比较各主体增速与整体增速（部分增速高于整体则比重上升），解析写出每项的两个增速及比较结论，"
                "不要编造错误算式。" + slot_difficulty_rules("gd", slot))
    parts = [slot_difficulty_rules("gd", slot), typical_error_rules(slot)]
    if kind != "multiple" and "倍" not in str(slot.get("kaofa_variant_name") or ""):
        parts.append("不要问成“是……的多少倍”，按本题题型的常规问法设问。")
    if kind in KIND_STEM_RULES:
        parts.append(KIND_STEM_RULES[kind][1] + "。")
    if mode == "numeric":
        parts.append(NUMERIC_RULES)
    parts.append(MODE_RULES.get(mode, "") + KIND_RULES.get(kind, ""))
    return "".join(p for p in parts if p)


def placement_hint(slot: dict) -> str:
    position = LETTERS.index(slot.get("answer_key") or "A")
    if mode_of(slot) == "numeric":
        return (f"四个选项会按数值从小到大排列，请让正确值排第{position + 1}位："
                f"给出{position}个比正确值小、{3 - position}个比正确值大的干扰值。")
    return ""


def slot_label(slot: dict) -> str:
    if slot.get("kind") == "judge":
        return "综合分析"
    return f"{slot.get('kind_label') or slot.get('kind')}（{slot.get('kaofa_variant_name') or '—'}）"


def material_view(material: dict) -> str:
    return f"材料正文：{material['content']}\n图表数据：{json.dumps(material.get('figure') or {}, ensure_ascii=False)}"


def question_prompt(material: dict, slots: list[dict], index: int) -> str:
    slot, mode = slots[index - 1], mode_of(slots[index - 1])
    others = "；".join(f"第{i}题 {slot_label(s)}" for i, s in enumerate(slots, 1) if i != index)
    return f"""你是资料分析出题员，只出本篇第{index}题。材料已冻结，不得修改任何数字、单位或口径。
{material_view(material)}

本题要求：{slot.get('brief') or ''}
{slot_rules(slot)}
{placement_hint(slot)}
本篇其他题（不要和它们求同一个量，也不要泄露它们的答案）：{others}

{GENERAL_RULES}
只输出这一道题的JSON：{MODE_CONTRACT[mode]}"""


def question_repair_prompt(material: dict, slots: list[dict], index: int, previous: dict, issues: list[str],
                           siblings: list[str]) -> str:
    return (question_prompt(material, slots, index)
            + f"\n\n同篇其他题题干：{json.dumps(siblings, ensure_ascii=False)}"
            + f"\n上一版（未通过）：{json.dumps(previous, ensure_ascii=False)}\n未通过原因：\n- " + "\n- ".join(issues)
            + "\n只针对原因修改，输出修正后的这一道题JSON。")


def ask_many(role: str, prompts: dict[int, str]) -> dict[int, dict]:
    with ThreadPoolExecutor(max_workers=max(1, len(prompts))) as pool:
        futures = {i: pool.submit(ask, role, p) for i, p in prompts.items()}
        results = {}
        for i, future in futures.items():
            try:
                results[i] = future.result()
            except Exception as exc:
                results[i] = {"_error": f"{type(exc).__name__}: {exc}"}
        return results


def settle(trial: Trial, slots: list[dict], raws: dict[int, dict], targets, stats: Stats, job,
           stage: str) -> None:
    """把 targets 这几题组装、提交并回修到全部保存为止。一次提交里有一题不合格则整批不保存，所以每轮整组重交。"""
    todo = set(targets)
    for attempt in range(1, QUESTION_TRIES + 2):
        built, calcs, failures = [], [], {}
        for i in sorted(todo):
            try:
                if i not in raws or raws[i].get("_error"):
                    raise ValueError("出题请求失败：" + str((raws.get(i) or {}).get("_error") or "没有返回这道题"))
                q, c = build_question(raws[i], slots[i - 1], i, trial.material_id)
                built.append(q)
                calcs.append(c)
            except Exception as exc:
                failures[i] = [f"{type(exc).__name__}: {exc}"]
        if built:
            result = trial.put_questions(built, calcs)
            if result.get("ok"):
                todo -= {int(q["external_id"][-1]) for q in built}
            else:
                for item in result.get("issues") or [{"target": "", "message": result.get("error")}]:
                    match = re.search(r"-Q(\d)$", str(item.get("target") or ""))
                    failures.setdefault(int(match[1]) if match else 0, []).append(str(item.get("message")))
                for i in [k for k in failures if k == 0]:
                    for j in todo:
                        failures.setdefault(j, []).extend(failures[i])
                    failures.pop(i)
        for i, reasons in failures.items():
            stats.reject(stage, f"Q{i}", reasons)
        if not todo:
            return
        if attempt > QUESTION_TRIES:
            raise RuntimeError("多次修正仍未通过本地校验：" + json.dumps(failures, ensure_ascii=False)[:800])
        job.update(stage="出题", detail=f"本地校验退回 {len(failures)} 题，单题回修中", progress=50 + attempt * 5)
        siblings = [str(q.get("stem") or "") for q in trial.questions.values()]
        raws.update(ask_many("question_repair", {
            i: question_repair_prompt(trial.material, slots, i, raws.get(i, {}), failures[i], siblings)
            for i in sorted(failures)}))


def gate_failures(trial: Trial, result: dict) -> tuple[dict[int, list[str]], list[str]]:
    """只把审核真正点名的题拿去回修：单题正确性/质量未过，或整篇审核点名了该题。"""
    per_question, other = {}, []
    evidence = result.get("evidence") or {}
    quality = evidence.get("system-quality.json") or {}
    for item in quality.get("results") or []:
        match = re.search(r"-Q(\d)$", str(item.get("question_id") or ""))
        correctness, style = item.get("correctness") or {}, item.get("quality") or {}
        reasons = []
        if correctness.get("verdict") != "PASS":
            reasons += [str(r) for r in correctness.get("issues") or ["正确性核验未通过"]]
        if style.get("verdict") != "PASS":
            reasons += [str(r) for r in style.get("issues") or []]
            reasons += [str(r) for r in (style.get("review") or {}).get("issues") or []]
        if match and reasons:
            per_question.setdefault(int(match[1]), []).extend(r[:400] for r in reasons)
    for issue in ((quality.get("batch_quality") or {}).get("review") or {}).get("issues") or []:
        text = json.dumps(issue, ensure_ascii=False) if isinstance(issue, dict) else str(issue)
        match = re.search(re.escape(trial.material_id) + r"-Q(\d)", text) or re.search(r"第(\d)题", text)
        if match:
            per_question.setdefault(int(match[1]), []).append("整篇审核：" + text[:500])
        else:
            other.append("整篇审核：" + text[:500])
    visual = json.dumps(evidence.get("ziliao-visual-quality.json") or {}, ensure_ascii=False)
    for qid in set(re.findall(re.escape(trial.material_id) + r"-Q(\d)", visual)):
        per_question.setdefault(int(qid), []).append("视觉质检未通过：" + visual[:400])
    if not per_question and not other:
        other.append(str(result.get("gate_error") or result)[-800:])
    return per_question, other


def run_gate(trial: Trial, slots: list[dict], raws: dict[int, dict], stats: Stats, job, planned: list[str]) -> None:
    for attempt in range(1, GATE_TRIES + 1):
        job.update(stage="篇内审核", detail=f"第{attempt}轮：盲解、考官、视觉质检", progress=75 + attempt * 5)
        result = trial.review()
        if result.get("ok"):
            return
        if result.get("issues"):  # 本地整篇清单，不耗审核次数
            failures = {}
            for item in result["issues"]:
                match = re.search(r"-Q(\d)", str(item.get("message") or ""))
                failures.setdefault(int(match[1]) if match else 0, []).append(str(item.get("message")))
            per_question, other = {k: v for k, v in failures.items() if k}, failures.get(0, [])
        else:
            per_question, other = gate_failures(trial, result)
        for i, reasons in per_question.items():
            stats.reject("gate", f"Q{i}", reasons)
        if other:
            stats.reject("gate", "整篇", other)
        if attempt == GATE_TRIES or not per_question:
            raise RuntimeError("篇内审核未通过：" + json.dumps(per_question or other, ensure_ascii=False)[:800])
        job.update(stage="篇内审核", detail=f"审核点名 {len(per_question)} 题，单题回修中", progress=80 + attempt * 4)
        siblings = [str(q.get("stem") or "") for q in trial.questions.values()]
        raws.update(ask_many("question_repair", {
            i: question_repair_prompt(trial.material, slots, i, raws.get(i, {}), reasons + other, siblings)
            for i, reasons in sorted(per_question.items())}))
        settle(trial, slots, raws, per_question, stats, job, "question_check")
        align_answers(trial, slots, raws, planned, stats)


# ---------------------------------------------------------------- 入口
def plan_from_blueprint(seed: str, material: int, db: Path) -> tuple[dict, list[str]]:
    """答案字母只留给程序排选项，不进计划与批次清单（审核员能看到清单，会把它当硬要求）。"""
    from ziliao_agent_paper import THEME_POOL, REGIONS
    from ziliao_blueprint import build_blueprint, pick_themes, plan_slot
    from ziliao_performance import adaptive_plan
    blueprint = build_blueprint(seed=seed, adaptive=adaptive_plan(db), db=db)
    rng = random.Random(seed)
    themes = pick_themes(THEME_POOL, set(blueprint["recent_themes"]), rng)
    mtype = blueprint["material_types"][material]
    picked = blueprint["slots"][material * 5:material * 5 + 5]
    slots = [plan_slot(s) for s in picked]
    keys = [s["answer_key"] for s in picked]
    region = "广东省" if material == 0 else rng.choice(REGIONS[1:])
    plan = {"id": f"M{material + 1:02}", "track": "gd", "difficulty": blueprint["tier"],
            "format": MATERIAL_TYPES[mtype]["format"], "figure_kind": MATERIAL_TYPES[mtype]["figure_kind"],
            "material_type": mtype, "theme": f"{region}{themes[material]}", "theme_key": themes[material],
            "region": region, "count": 5, "slots": slots,
            "question_plan": material_question_plan(mtype, slots), "figure_shape": MATERIAL_TYPES[mtype]["figure_shape"],
            "focus": "真实统计公报信息组织，地名用真实广东地名；显示数从高精度底数独立舍入", "chart_tasks": []}
    return plan, keys


CHART_TYPES = ("years", "two_series", "line", "pie")
FORMAT_ALIASES = {"chart": CHART_TYPES, "bars": ("years", "two_series"), "柱图": ("years", "two_series"),
                  "折线": ("line",), "饼图": ("pie",), "表格": ("table", "monthly"), "文字": ("text",)}


def material_types_for(fmt: str | None) -> tuple[str, ...]:
    if not fmt:
        return tuple(MATERIAL_TYPES)
    if fmt in MATERIAL_TYPES:
        return (fmt,)
    if fmt in FORMAT_ALIASES:
        return FORMAT_ALIASES[fmt]
    raise ValueError(f"材料形态只能是 {'/'.join(MATERIAL_TYPES)} 或 chart/柱图/折线/饼图/表格/文字")


def base_plan(material_id: str, mtype: str, tier: str, theme: str, region: str, slots: list[dict]) -> dict:
    return {"id": material_id, "track": "gd", "difficulty": tier,
            "format": MATERIAL_TYPES[mtype]["format"], "figure_kind": MATERIAL_TYPES[mtype]["figure_kind"],
            "material_type": mtype, "theme": f"{region}{theme}", "theme_key": theme, "region": region, "count": 5,
            "slots": slots, "question_plan": material_question_plan(mtype, slots),
            "figure_shape": MATERIAL_TYPES[mtype]["figure_shape"],
            "focus": "真实统计公报信息组织，地名用真实广东地名；显示数从高精度底数独立舍入", "chart_tasks": []}


def targeted_plans(tag: str, count: int, tier: str, fmt: str | None, brief: str, seed: str,
                   db: Path) -> tuple[list[dict], list[list[str]]]:
    """指定考点专项：每篇5题都考该考点，题型在它对应的几种题型里轮转，细分考法按近期少练、错得多优先。"""
    import kaofa_variants as kv
    from kaodian_taxonomy import _abcd_plus_one
    from ziliao_agent_paper import REGIONS, THEME_POOL
    from ziliao_blueprint import imported_dirs, non_exact_ok, pick_themes, plan_slot, recent_rotation
    from ziliao_performance import adaptive_plan
    from ziliao_tracks import KIND_SPECS, KIND_TAGS, rotating_slot
    if count not in (5, 10):
        raise ValueError("资料分析专项按篇出，每篇5题：题量只能是5或10")
    kinds = [k for k, t in KIND_TAGS.items() if t == tag]
    if not kinds:
        raise ValueError(f"{tag} 不是资料分析出题主标签；可用：{'、'.join(sorted(set(KIND_TAGS.values())))}")
    rng = random.Random(seed)
    adaptive = adaptive_plan(db)
    _, _, _, recent_themes = recent_rotation(imported_dirs(ROOT / "data" / "manual-ziliao-agent-paper", db, 6))
    themes = pick_themes(THEME_POOL, recent_themes, rng)
    plans, keys = [], []
    for m in range(count // 5):
        types = [t for t in material_types_for(fmt) if any(t in KIND_SPECS[k]["types"] for k in kinds)]
        if not types:
            raise ValueError(f"{tag} 没有能用 {fmt} 材料出的题型")
        mtype = rng.choice(types)
        usable = [k for k in kinds if mtype in KIND_SPECS[k]["types"]]
        slots = []
        for q in range(5):
            slot = rotating_slot(usable[q % len(usable)], mtype, tier, "exact", rng)
            if brief:
                slot["brief"] = f"{slot['brief']}；用户要求：{brief}"
            slots.append(slot)
        slots = kv.assign_ziliao_variants(slots, seed=f"{seed}-{m}", boost=adaptive.get("variant_boost"))
        eligible = [s for s in slots if non_exact_ok(s) and "interval" in KIND_SPECS[s["kind"]]["formats"]]
        if eligible and rng.random() < 0.5:
            rng.choice(eligible)["option_format"] = "interval"
        region = "广东省" if m == 0 else rng.choice(REGIONS[1:])
        plans.append(base_plan(f"M{m + 1:02}", mtype, tier, themes[m], region, [plan_slot(s) for s in slots]))
        keys.append(_abcd_plus_one(rng))
    return plans, keys


def single_plan(seed: str, fmt: str | None, db: Path) -> tuple[list[dict], list[list[str]]]:
    """不指定考点的单篇：从整卷蓝图里取一篇（指定材料形态时取形态匹配的那篇）。"""
    from ziliao_blueprint import build_blueprint
    from ziliao_performance import adaptive_plan
    blueprint = build_blueprint(seed=seed, adaptive=adaptive_plan(db), db=db)
    wanted = material_types_for(fmt) if fmt else None
    picks = [i for i, t in enumerate(blueprint["material_types"]) if not wanted or t in wanted]
    material = picks[0] if wanted and picks else random.Random(seed).randrange(4)
    plan, keys = plan_from_blueprint(seed, material, db)
    return [dict(plan, id="M01")], [keys]


def run_set(plans: list[dict], keys: list[list[str]], out: Path, db: Path, do_import: bool,
            targeted: bool) -> dict:
    """1篇直接出并入库；2篇在子进程并行出，各自签名后由整卷组装闸门合成一批入库。"""
    if len(plans) == 1:
        return run_pipeline(plans[0], keys[0], out, db, do_import)
    from ziliao_assembly import assemble, issue_assembly
    out.mkdir(parents=True, exist_ok=False)
    job = Job(out.name, module="资料分析", title=f"资料分析专项·{plans[0]['slots'][0]['tag'].split('-', 1)[1]}",
              planned=5 * len(plans))
    started, runs = time.monotonic(), []

    def worker(index: int) -> Path:
        plan = plans[index]
        (out / f"{plan['id']}-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        work = out / "workers" / plan["id"] / out.name
        work.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(Path(__file__)), "--plan", str(out / f"{plan['id']}-plan.json"),
               "--keys", "".join(keys[index]), "--out", str(work), "--db", str(db),
               "--progress", str(work.parent / "progress.json")]
        with (out / f"{plan['id']}-pipeline.log").open("w") as handle:
            proc = subprocess.run(["timeout", "--signal=TERM", "--kill-after=10s", "20m", *cmd],
                                  cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        summary_path = work / "pipeline-summary.json"
        runs.append(json.loads(summary_path.read_text()) if summary_path.is_file() else {"material": plan["id"]})
        if proc.returncode:
            raise RuntimeError(f"{plan['id']} 未通过：{runs[-1].get('error') or '见日志'}")
        return work

    error, imported = None, 0
    try:
        job.update(stage="出题", detail=f"{len(plans)} 篇并行", progress=10)
        with ThreadPoolExecutor(max_workers=len(plans)) as pool:
            paths = list(pool.map(worker, range(len(plans))))
        slots = [s for p in plans for s in p["slots"]]
        tier = plans[0]["difficulty"]
        source = runner.batch_source("gd", targeted, tier, dt.date.today().strftime("%Y%m%d"), slots)
        assemble(out, paths, slots, source, tier, targeted=targeted)
        issue_assembly(out, paths)
        if do_import:
            imported = import_batch(out, db)
            record_variants(out.name, slots)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    if error:
        job.finish(status="failed", stage="失败", error=error, detail=error[:160])
    else:
        job.finish(status="done", stage="已入库" if imported else "已通过", detail=f"{imported or 5 * len(plans)} 题",
                   passed=5 * len(plans), progress=100)
    requests = Counter()
    for run in runs:
        requests.update(run.get("requests") or {})
    summary = {"batch_id": out.name, "passed": error is None, "imported": imported, "error": error,
               "seconds": round(time.monotonic() - started, 1), "requests": dict(requests), "materials": runs}
    (out / "pipeline-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def import_batch(out: Path, db: Path) -> int:
    count = verify(out)["question_count"]
    proc = subprocess.run([service_node(), str(ROOT / "scripts/import-batch.mjs"), str(out)], cwd=ROOT,
                          env={**os.environ, "EXAM_DB": str(db)}, capture_output=True, text=True, timeout=180)
    (out / "import-output.txt").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError("入库失败：" + (proc.stdout + proc.stderr)[-1200:])
    return count


class FileProgress:
    """worker 模式：进度写进文件，由整卷流程汇总成一行分篇进度。"""
    def __init__(self, path: Path, label: str):
        self.path, self.label = path, label

    def update(self, **fields) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"label": self.label, **fields}, ensure_ascii=False))
        tmp.replace(self.path)

    def finish(self, **fields) -> None:
        self.update(**fields)


def run_pipeline(plan: dict, keys: list[str], out: Path, db: Path, do_import: bool = False,
                 progress_file: Path | None = None) -> dict:
    global CALL_DIR
    batch_id = out.name
    stats = Stats(out.parent / f"{batch_id}.calls")
    out.parent.mkdir(parents=True, exist_ok=True)
    stats.log.unlink(missing_ok=True)
    os.environ["MODEL_CALL_LOG"] = str(stats.log)
    os.environ["EXAM_DB"] = str(db)
    trial = Trial(out, db, plan)
    CALL_DIR = out / "calls"
    HEDGES.clear()
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    slots = [dict(s, answer_key=k) for s, k in zip(plan["slots"], keys)]
    progress = (FileProgress(progress_file, plan["id"]) if progress_file else
                Job(batch_id, module="资料分析", title=f"资料分析单篇·{plan['theme']}", planned=5))
    rng = random.Random(batch_id + plan["id"])
    error, imported = None, 0
    try:
        progress.update(stage="材料", detail="材料员撰写中", progress=5)
        raws = make_material_and_drafts(trial, plan, slots, stats, progress, rng)
        mark = time.monotonic()
        progress.update(stage="出题", detail="5题初稿已出，本地校验中", progress=45)
        settle(trial, slots, raws, range(1, 6), stats, progress, "question_check")
        align_answers(trial, slots, raws, keys, stats)
        stats.stages["出题"] = round(time.monotonic() - mark, 1)
        mark = time.monotonic()
        run_gate(trial, slots, raws, stats, progress, keys)
        stats.stages["篇内审核"] = round(time.monotonic() - mark, 1)
        if do_import:
            progress.update(stage="入库", detail="写入题库", progress=96)
            imported = import_batch(out, db)
            record_variants(batch_id, plan["slots"])
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    if error:
        progress.finish(status="failed", stage="失败", error=error, detail=error[:160])
    else:
        progress.finish(status="done", stage="已入库" if imported else "已通过", detail=f"{imported or 5} 题",
                        passed=5, progress=100)
    summary = {"batch_id": batch_id, "material": plan["id"], "passed": error is None, "imported": imported,
               "error": error, "seconds": round(time.monotonic() - stats.started, 1), "stages": stats.stages,
               "requests": dict(stats.requests()), "hedged": list(HEDGES), "material_reviews": trial.material_reviews,
               "gate_rounds": trial.gate_attempts, "rejections": stats.rejections,
               "material_type": plan["material_type"], "theme": plan["theme"],
               "slots": [{"kind": s.get("kind_label"), "variant": s.get("kaofa_variant_name"),
                          "option_format": s.get("option_format"), "planned_answer": k,
                          "answer": (trial.questions.get(f"{trial.material_id}-Q{i}") or {}).get("answer")}
                         for i, (s, k) in enumerate(zip(slots, keys), 1)]}
    (out / "pipeline-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "manual-ziliao-material")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "exam.db")
    parser.add_argument("--batch-id")
    parser.add_argument("--tag", help="指定考点专项：资料分析出题主标签，如 资料分析-ABRX类-增长量计算与现期推算")
    parser.add_argument("--count", type=int, default=5, help="题量：5（1篇）或10（2篇，仅专项）")
    parser.add_argument("--difficulty", choices=("easy", "mid", "hard"), default="mid")
    parser.add_argument("--format", help="材料形态：text/table/monthly/years/two_series/pie/line，或 chart/柱图/折线/饼图/表格/文字")
    parser.add_argument("--brief", default="", help="用户对本次专项的额外要求，原话写入每题出题要求")
    parser.add_argument("--seed", help="蓝图种子，默认用批次号；复现同一套槽位时指定")
    parser.add_argument("--material", type=int, choices=(1, 2, 3, 4), help="单篇：指定取蓝图第几篇")
    parser.add_argument("--plan-only", action="store_true", help="只打印本次各篇材料形态与5个槽位，不调模型")
    parser.add_argument("--import", dest="import_batch", action="store_true")
    parser.add_argument("--plan", type=Path, help="worker 模式：整卷流程冻结好的单篇计划")
    parser.add_argument("--keys", help="worker 模式：本篇5题的预分配答案字母，如 ABCDA")
    parser.add_argument("--out", type=Path, help="worker 模式：单篇产物目录（目录名即批次号）")
    parser.add_argument("--progress", type=Path, help="worker 模式：进度文件")
    args = parser.parse_args()
    db = args.db.resolve()
    if args.plan:
        if not (args.keys and args.out) or len(args.keys) != 5:
            parser.error("worker 模式须同时给 --plan、--keys（5个字母）与 --out")
        summary = run_pipeline(json.loads(args.plan.read_text()), list(args.keys), args.out.resolve(), db, False,
                               args.progress)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["passed"] else 1
    if args.batch_id and not re.fullmatch(r"[\w-]{1,160}", args.batch_id):
        parser.error("batch-id 只能包含字母、数字、汉字、下划线和连字符")
    batch_id = args.batch_id or f"{dt.date.today():%Y%m%d}_hermes_ziliao_{uuid.uuid4().hex[:8]}"
    seed = args.seed or batch_id
    try:
        if args.tag:
            plans, keys = targeted_plans(args.tag, args.count, args.difficulty, args.format, args.brief, seed, db)
        elif args.count != 5:
            parser.error("不指定考点时只出1篇5题；20题整套用 ziliao_agent_paper.py，10题须指定考点")
        elif args.material:
            plan, k = plan_from_blueprint(seed, args.material - 1, db)
            plans, keys = [dict(plan, id="M01")], [k]
        else:
            plans, keys = single_plan(seed, args.format, db)
    except ValueError as exc:
        parser.error(str(exc))
    if args.plan_only:
        print(json.dumps({"batch_id": batch_id, "materials": [
            {"id": p["id"], "material_type": p["material_type"], "theme": p["theme"],
             "slots": [{"kind": s.get("kind_label"), "variant": s.get("kaofa_variant_name"),
                        "option_format": s.get("option_format")} for s in p["slots"]]} for p in plans]},
            ensure_ascii=False, indent=2))
        return 0
    summary = run_set(plans, keys, args.output_dir.resolve() / batch_id, db, args.import_batch, bool(args.tag))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

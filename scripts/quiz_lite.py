#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes 轻量专项出题：一次出稿 + 独立盲解/对照审核 → 只重出不合格的题 → 入库。

重的那条路仍在 quiz_generator.py（四条 correctness 路线、真题 holdout、
资料分析视觉质检、一题不合格整批重出），留给日练成套卷与带图卷。

这里只解一件事：Hermes 点名一个考法，快速拿到一批答案唯一、难度对档的纯文字题。
答案正确性不靠硬编码验算，靠盲解官——不给它答案与解析，让它自己把题做一遍。
给了答案的模型会去论证那个答案，不给答案的模型才会真的算。
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generation_gate import (LITE_VERSION, RECEIPT, QUANTITY_HARD_POLICY, VERBAL_PRACTICE_POLICY, POLICY_PRACTICE_POLICY, REASONING_PRACTICE_POLICY, current_hard_policy, digest,
                             lite_allowed_tiers, lite_necessity_claims, lite_reasoning_issues)
from normalize_ai_batch import scratchpad_leak
from quiz_scope import source_name, source_topic
from yanyu_variety import duplicate_fill_ids, recent_yanyu_avoid, topic_conflict, validate_yanyu_fills
from verbal_vocab import assign_vocab, vocab_issues
from quiz_generator import (
    BASE_URL,
    api_key,
    run_canon_card,
    infer_subcategory,
    parse_json,
    reject_unsupported,
    resolve_slots,
    yanyu_contract_issues,
)
from scheduler_common import DB, ROOT, local_today
from service_node import service_node
from policy_sources import SOURCE_MODULES, source_pack
import model_router

MODEL = model_router.resolve_model("quiz_lite")
# CLIProxy 本身不限并发，按凭据轮询。启用中的反重力账号有 3 个，AI Studio key 也在池里。
# 三路同时打满时，多路会停在 503 换凭据上直到客户端超时；两路可以完成。全流程共用这一个上限。
MODEL_PARALLEL = 2
_MODEL_SLOTS = threading.BoundedSemaphore(MODEL_PARALLEL)
MAX_COUNT = 15
# 凌晨的每日复习卷（batch_id 以 daily- 开头）整卷 20 题；Hermes 点名的专项仍是 15。
DAILY_MAX_COUNT = 20
DUP_RATIO = 0.82
MODEL_AUDIT_DIR = ContextVar('quiz_model_audit_dir', default=None)
# 选项开头的数值：整数、小数，或 5/16 这样的分数。带单位的「23个」也认。
OPTION_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?")
# 题库的 difficulty 是 1–5 的整数，主体落在 2–4。声明档位按槽位换算，
# 不收模型自己写的 difficulty——它会直接把 "easy" 这种字符串塞进来。
TIER_TO_LEVEL = {"easy": 2, "mid": 3, "hard": 4}

DIFFICULTY_RULES = """统一难度与解析标准（出题与独立审核使用同一口径）：
- easy：直接识别目标模型，完成该模型的常规步骤即可求解。
- mid：在基础模型之外，至少有一个会改变可行范围的额外独立条件，或一次非例行的表示转化。
- hard：至少两个相互制约的有效条件，或必须分段讨论（含分别求界后合并两种失败分支）、完成两次非例行转化；不能仍是纯套公式。
- 言语/逻辑难度看必要辨析动作和近似干扰的竞争度，不机械套数学条件数：mid 至少有两个需要结合文段
  或逻辑条件辨析的竞争错项；仅凭“唯一/完全/反向词”即可排除不计。显式尾句的直接同义替换属于 easy。
- 模型自带的常规前置步骤不算额外难度：例如通过人数转未通过人数、常规组合数确定抽屉数，
  再代入反向构造或抽屉公式，仍是直接模型。不能仅因题干长、数字多、计算步数多或换了场景提高档位。
- 难度须做删条件对照：逐条去掉所声称增加难度的条件，说明它实际改变了哪个界、最优值或必要解法。
  仅出现在题面、在常规最优构造中顺手满足的条件不计额外难度；两条这样的条件也不能凑成 hard。
  若常规总量/人次公式已给出实际最优值，附加条件只在可达性构造时验证，最多算 mid；
  不能把配对分配写得长或给常规可达验证冠以高级数学名称后升为 hard。
- 难度增加仍须锁定本子考点；无法达到槽位难度时返回 unsuitable:true，不能跨考法凑难度。
- 解析先明确优化的是哪个量、求它的最大还是最小；口头原则、取极端的方向、算式和具体构造必须一致。
  名次最末不代表求该人的最小值；即使选项正确，原则说反或中间论证错误也不合格。
- 必要结论和可行构造必须分开：“可取一种分配”不能写成“只能如此”。对“必须/只能/必然”尝试反例；
  人次除法的余数也可能交给另一目标组的人，不能默认所有人次必须由非目标组承担。
  例如每个非目标者至少占 k 人次，S=q*k+r、0<r<k 时，q 人各占 k 项、另一个目标者占 r 项
  也可能可行；不能声称为了得到 q 个非目标者只能把余数塞进这 q 人中的某人。须核对原题约束。
- 不等式须逐步保证蕴含关系：x>=a 与 x>=b 只能合成 x>=max(a,b)，不能推出 a>=b 或 a<=b。
- 最值结论必须同时说明界限与可达性：给出满足所有原条件的具体分配/分组构造，或可核查的存在性论证。
  只用总和、人次除法得到上下界，未验证每项数量、整数和交集等限制能同时满足，不得声称已求到最值。
- 一个分配可行不代表最优。整数最值须证明更优整数不可能；尤其要检验紧邻的更优整数，
  即使它没有出现在选项里也不能跳过。不得把“选项中最小的可行值”冒充真正最小值。
"""

WRITER_SYSTEM = (
    "你是广东省考行测命题人。只输出一个 JSON 对象，不要 markdown 围栏，不要任何解释文字。"
)

BLIND_SYSTEM = (
    "你是独立做题人。你看不到出题人的答案与解析，必须自己把题解出来。\n"
    + DIFFICULTY_RULES +
    "你也不知道声明难度；按实际必需解法独立填写 actual_difficulty（easy/mid/hard），"
    "difficulty_reason 必须说明附加条件删除前后的界或必需解法，不能按条件条数或构造篇幅定级。\n"
    "解完之后，再逐个选项回头检查：除了你选的那个，还有没有别的选项也站得住。\n"
    '只输出 JSON：{"questions":[{"id":"...","answer":"A","steps":"...",'
    '"actual_difficulty":"mid","difficulty_reason":"实际必需解法及删条件对照...",'
    '"also_valid":[],"unsolvable":false,"reason":"..."}]}\n'
    "answer 必须是你自己算出来的那一项，不要猜、不要凑。\n"
    "steps 要写出每一步的算式和数值结果，含取整方向（向上/向下），禁止跳步心算。\n"
    "最值题先独立求真实最值，再匹配选项；可行构造不等于最优，须排除更优值。"
    "整数最值必须检验紧邻的更优整数，即使该整数不在选项里；不能用选项间隔跳过检验。\n"
    "also_valid 列出除 answer 之外同样成立的选项字母，没有就给空数组。\n"
    "若题干条件不足、自相矛盾，或四个选项里没有正确答案，unsolvable 置 true 并在 reason 说明。"
)

EXAMINER_SYSTEM = (
    "你是广东省考行测命题审核官，能看到答案与解析。\n"
    + DIFFICULTY_RULES +
    "逐题检查五项：\n"
    "difficulty_ok：按统一标准检查真正有效的额外条件/转化；基础模型常规步骤不重复计难度。\n"
    "先独立填写 actual_difficulty（easy/mid/hard），再与 declared_difficulty 比较；"
    "difficulty_reason 写出具体解法及删条件对照，不能只复述题干有几个条件。\n"
    "kaodian_ok：是否100%严格落在指定考法的固定识别与考场步骤上！"
    "严禁任何考法发散或串台（例如考古典定位法却出现了赛制或独立关卡，直接判 false 毙掉）。\n"
    "style_ok：题干情境、设问方式、选项设置、篇幅是否像广东省考真题，"
    "不是奥数题、不是教材例题、不是脑筋急转弯。\n"
    "analysis_ok：每一步可复算、结论等于键定选项；解析原则、优化方向和计算须一致；"
    "最值须证明界可达；不能只因最终答案正确而放过论证错误。\n"
    "analysis_check 写出核查过的关键推导、界限和构造；对必要性断言尝试其他合法分配，"
    "对整数最值检验紧邻的更优整数，不得仅填“正确/可复算”。\n"
    "对照 blind_work 的独立推导逐项核验原解析，两者都可能错。独立解法若给出原解析声称不可能的合法构造，"
    "必须据原题验证，不能因答案相同忽略矛盾；原解析把可行分配写成唯一必要分配须 analysis_ok=false。\n"
    "analysis_check 必须逐字引用原解析中最强的“只能/必须/必然”断言并检验其必要性；"
    "若存在另一合法分配，该必要性断言即为错误，即使两种分配最终答案相同，也须拒绝。"
    "不得把原文的“只能”默默改读成“可以”。没有必要性断言则核查最关键的不等式蕴含。\n"
    "necessity_claims 是从原解析抽取的必要性断言。对每条原句返回 necessity_checks："
    "claim_index 对应原句编号，valid 表示整句是否必然成立，reason 给出推导或合法反例。"
    "只以题干为已知条件：不能把待证明解析自加的“余下人次全部交给非目标组”等分配假设当题干条件。"
    "先尝试否定断言并构造满足原题的反例，再给判定；证明一种分配可行不等于排除了其他分配。"
    "不得遗漏；一条不成立即 analysis_ok=false。没有此类原句时返回空数组。\n"
    "brief_ok：逐题满足 declared_brief 的额外命题要求；跨题配额按 batch_slots 和整批题核对。无额外要求则为 true。\n"
    "variant_match：declared_brief 里注明了“本题考法变式：xxx”时，必须核对本题实际设问结构与解题动作是否属于该变式，"
    "返回 {\"ok\": true, \"reason\": \"依据\"}；退回该考点最常见默认考法、或只换场景不换解题动作 → ok=false 并在 reason 写明差在哪。"
    "没有注明考法变式就给 {\"ok\": true, \"reason\": \"无细分考法\"}。\n"
    '只输出 JSON：{"questions":[{"id":"...","actual_difficulty":"mid",'
    '"difficulty_reason":"具体解法与删条件对照...","analysis_check":"关键推导与反例检查...",'
    '"necessity_checks":[{"claim_index":0,"valid":true,"reason":"具体推导或反例"}],'
    '"verdict":"PASS","difficulty_ok":true,'
    '"kaodian_ok":true,"style_ok":true,"analysis_ok":true,"brief_ok":true,"variant_match":{"ok":true,"reason":"依据"},"issues":[]}]}\n'
    "五项全 true 才给 PASS；任一为 false 必须 REJECT，并在 issues 里写明具体哪一步错、怎么错的。"
)


def parallel_map(fns: list):
    """按提交顺序取回结果。同时打到模型的请求数由 call 里的信号量卡住。"""
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(MODEL_PARALLEL, len(fns))) as pool:
        futures = [pool.submit(copy_context().run, fn) for fn in fns]
        return [future.result() for future in futures]


def call(system: str, prompt: str, temperature: float, timeout: int, *,
         schema: dict | None = None) -> dict:
    with _MODEL_SLOTS:
        return _call(system, prompt, temperature, timeout, schema=schema)


def _call(system: str, prompt: str, temperature: float, timeout: int, *,
          schema: dict | None = None) -> dict:
    structured_questions = schema is not None and 'questions' in schema.get('properties', {})
    if structured_questions:
        system = '你是广东省考行测命题人。必须调用一次submit_questions提交所有题目，不在正文输出JSON或总结。'
    body = {
            "model": MODEL,
            "temperature": temperature,
            "max_tokens": 16384,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system + '\nJSON 字符串中的反斜线必须写成双反斜线；优先用普通数学记号，不要产生非法转义。正文引用词语使用中文引号“”，不要产生未转义的英文双引号。'},
                {"role": "user", "content": prompt},
            ],
    }
    if schema is not None:
        body.pop('response_format')
        function_name = 'submit_questions' if structured_questions else 'submit_review'
        body['tools'] = [{'type': 'function', 'function': {
            'name': function_name, 'description': '提交题目' if structured_questions else '提交逐句审核结果', 'parameters': schema,
        }}]
        body['tool_choice'] = {'type': 'function', 'function': {'name': function_name}}
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode('utf-8'),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_response = response.read().decode("utf-8")
        audit_dir = MODEL_AUDIT_DIR.get()
        if audit_dir is not None:
            audit_dir.mkdir(parents=True, exist_ok=True)
            (audit_dir / f'{time.time_ns()}-{threading.get_ident()}.json').write_text(
                json.dumps({'role': system.splitlines()[0], 'requested_model': MODEL,
                            'response': raw_response}, ensure_ascii=False, indent=2),
                encoding='utf-8')
        payload = json.loads(raw_response)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"出题上游调用失败，未自动重试：{type(exc).__name__}: {exc}") from exc
    choice = payload["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("模型回答被截断（finish_reason=length），本次出题未完成，已停止且未自动重试；请用户要求继续后再执行。")
    try:
        message = choice['message']
        if schema is not None:
            calls = message.get('tool_calls') or []
            if structured_questions and not calls:
                # Some providers return the requested object in content despite tool_choice.
                # Only drafts allow this envelope; review evidence still requires the native tool.
                records = json.loads(message.get('content') or '')
            else:
                if len(calls) != 1 or calls[0].get('function', {}).get('name') != function_name:
                    raise ValueError(f'缺少唯一的 {function_name} 结构化结果')
                records = json.loads(calls[0]['function'].get('arguments') or '')
            if not isinstance(records, dict) or set(records) != set(schema['required']):
                raise ValueError('逐句审核未覆盖全部编号或含未知编号')
            if structured_questions:
                if not isinstance(records['questions'], list) or not all(isinstance(q, dict) for q in records['questions']):
                    raise ValueError('结构化题目须为对象数组')
                return records
            if any(not isinstance(v, str) or not re.match(r'^(?:PASS|REJECT)\b\W*\S+', v) for v in records.values()):
                raise ValueError('逐句审核缺少有效结论及依据')
            return records
        return parse_json((message.get("content") or "").strip())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"模型返回的数据无法解析，本次未完成且未自动重试：{exc}") from exc


def indexed(payload: dict) -> dict[str, dict]:
    out, repeated = {}, set()
    for item in payload.get("questions") or []:
        if isinstance(item, dict) and item.get("id"):
            ident = str(item["id"])
            if ident in out:
                repeated.add(ident)
            out[ident] = item
    return {ident: item for ident, item in out.items() if ident not in repeated}


def item_index(item: dict) -> int:
    """模型偶尔把 index 写成字符串或漏掉，认不出就返回 0，交给按位次兜底。"""
    try:
        return int(item.get("index") or 0)
    except (TypeError, ValueError):
        return 0


def expand_slots(slots: list[dict]) -> list[dict]:
    """槽位摊平成「每题一份口径」，下标即题号 - 1。"""
    per_item: list[dict] = []
    for slot in slots:
        per_item.extend([slot] * int(slot["count"]))
    return per_item


def public(question: dict, with_answer: bool) -> dict:
    options = question.get("options")
    if isinstance(options, str):
        options = packed_options(options)
    else:
        options = [
            {"key": option.get("key"), "text": option.get("text")}
            if isinstance(option, dict)
            else {"key": "", "text": str(option)}
            for option in options or []
        ]
    out = {
        "id": question.get("external_id"),
        "category": question.get("category"),
        "sub_category": question.get("sub_category"),
        "tags": question.get("tags") or [],
        "stem": question.get("stem"),
        "question_type": question.get("question_type", "single"),
        "options": options,
    }
    if with_answer:
        out["kaodian_signal"] = question.get("kaodian_signal")
        out["answer"] = question.get("answer")
        out["analysis"] = question.get("analysis")
    return out


def writer_prompt(run: dict, asks: list[dict], kept: list[str]) -> str:
    cards: dict[str, str] = {}
    for ask in asks:
        tag = str(ask["tag"])
        if tag not in cards:
            cards[tag] = run_canon_card(run, tag)
    if run['module'] == '数量关系':
        from quiz_quantity import writer_prompt as quantity_prompt
        return quantity_prompt(run, asks, kept, cards)
    if run['module'] == '言语理解与表达':
        from quiz_verbal import writer_prompt as verbal_prompt
        return verbal_prompt(run, asks, kept, cards)
    if run['module'] == '判断推理':
        from quiz_reasoning import writer_prompt as reasoning_prompt
        return reasoning_prompt(run, asks, kept, cards)
    if run['module'] in SOURCE_MODULES:
        from policy_quiz import writer_prompt as grounded_prompt
        return grounded_prompt(run, asks, kept)
    lines = [
        "严格按下面每一条 item 出题，一条一道，数量不多不少。",
        json.dumps(
            {"module": run["module"], "batch_id": run["batch_id"], "items": asks},
            ensure_ascii=False,
        ),
        "",
        "考法口径（按 item 的 tag 各自对照，不要让别的考法渗进来）：",
    ]
    for tag, card in cards.items():
        lines.append(f"[{tag}]\n{card}" if card else f"[{tag}]（此考法无卡片，按标签字面出题）")
    lines += [
        "",
        "硬要求：",
        DIFFICULTY_RULES,
        "- 【考法严格闭环（严禁发散）】：每道题必须100%严格落在对应 item 的 tag 及【考场步骤】指定的唯一解题动作上！",
        "  严禁发散到同卡片下的其他考法或外部模型；无法满足指定考法时输出 unsuitable:true。",
        "- 每题四个选项 A/B/C/D，有且只有一个正确；另外三项必须各有一个致命缺陷，",
        "不能是同样成立的另一种合理答案。",
        "- 每道题的正确项放哪个字母由你自己定，不要为了凑某个字母去改数据；"
        f"但本次这 {len(asks)} 道题的正确项字母要分散，同一个字母不要超过 "
        f"{max(1, round(len(asks) * 0.4))} 道。",
        "- analysis 写出完整可复算的步骤：每一步的算式、数值结果、取整方向，"
        "最后一行给出结论并指明等于哪个选项。",
        "- 先按题干原样的数据算出真答案，再据此设选项。一旦发现选项与真答案对不上，"
        "改的是选项，不是题干数据，更不是解析里的数据。",
        "- analysis 是给考生看的解题步骤，不是你的草稿纸。里面不得出现"
        "「修改题干」「调整数据」「为了让答案等于…」这类自言自语；"
        "解析解的必须是题干原样的那道题。",
        "- 数值题的四个选项必须围绕取整之后的最终答案设置，正确答案必须真的在选项里；"
        "四个选项按大小排好，A→D 升序（或统一降序），不许乱序。",
        "- 纯文字题，不带图、不引用图；禁止照搬真题；主体用某单位/某企业/某科室这类中性称谓。",
        "- 题干与设问要像广东省考真题：情境简洁、设问明确、篇幅不超过真题常见长度。",
        "- 可适量用科技创新、AI应用、广东产业等场景，但用户指定考点/难度优先，不强塞热点。"
        "数量和资料模拟数据要在题面明确给足，不冒充真实统计；言语答案只凭给定文段；"
        "逻辑题不能要求题干以外的专业知识。涉及真实政策原话或具体时事数据时，"
        "必须有已核验原文，否则用不声称真实事件的中性场景。",
    ]
    if kept:
        lines += [
            "",
            "本批次已通过的题（新题不得与它们同模型同数据，情境也要换）：",
            *[f"- {stem[:120]}" for stem in kept],
        ]
    lines += [
        "",
        "输出字段必须严格使用 stem（不要写 question/content）、options（必须是四个对象，不要合并成字符串）：",
        '{"questions":[{"index":1,"kaodian_signal":"...","stem":"...","options":[{"key":"A","text":"..."},{"key":"B","text":"..."},{"key":"C","text":"..."},{"key":"D","text":"..."}],"answer":"A","analysis":"..."}]}',
        "每题可带 unsuitable 字段；不要输出 schema 之外的包装对象。",
    ]
    return "\n".join(lines)


def option_number(text: str) -> float | None:
    match = OPTION_NUMBER.match(text)
    if not match:
        return None
    top, bottom = match.group(1), match.group(2)
    try:
        return float(top) / float(bottom) if bottom else float(top)
    except (ValueError, ZeroDivisionError):
        return None


def unordered_numbers(question: dict, texts: list[str]) -> bool:
    """数值选项乱序（A:10 B:12 C:18 D:15）一眼就露怯，真题不会这样排。"""
    if str(question.get("category") or "") != "数量关系" or len(texts) != 4:
        return False
    values = [option_number(text) for text in texts]
    if any(value is None for value in values):
        return False
    return values != sorted(values) and values != sorted(values, reverse=True)


MATH_SPAN = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$\n]+?\$")
TEX_COMMANDS = ("dfrac|tfrac|frac|sqrt|times|div|cdot|pi|leq|le|geq|ge|neq|approx|pm|circ|angle|triangle|"
                "alpha|beta|theta|infty|cdots|ldots|overline|left|right")
BARE_TEX = re.compile(r"\d*(?:\\(?:" + TEX_COMMANDS + r")(?![A-Za-z])(?:\{[^{}]*\})*\d*)+")
BARE_TEX_LEFT = re.compile(r"\\[A-Za-z]{2,}")


def outside_math(text: str) -> list[str]:
    return MATH_SPAN.split(text or "")


def wrap_bare_tex(text: str) -> str:
    """前端只渲染 $…$ 内的公式，漏写定界符的 \\frac 等命令连同紧邻数字补成 $…$。"""
    if "\\" not in (text or ""):
        return text
    plain, spans = outside_math(text), MATH_SPAN.findall(text)
    out = []
    for i, part in enumerate(plain):
        out.append(BARE_TEX.sub(lambda m: f"${m.group(0)}$", part))
        if i < len(spans):
            out.append(spans[i])
    return "".join(out)


def bare_tex_issues(question: dict) -> list[str]:
    fields = [question.get("stem"), question.get("analysis")] + [
        option.get("text") for option in question.get("options") or [] if isinstance(option, dict)]
    leftover = sorted({m for text in fields for part in outside_math(str(text or ""))
                       for m in BARE_TEX_LEFT.findall(part)})
    return [f"公式命令未包在 $…$ 中（{'、'.join(leftover[:3])}），网页会显示成源码"] if leftover else []


PROBABILITY_DECIMAL = re.compile(r"%|％|\d\.\d")


def probability_format_issues(question: dict) -> list[str]:
    if not any("概率问题" in str(tag) for tag in question.get("tags") or []):
        return []
    texts = [str(option.get("text") or "") for option in question.get("options") or [] if isinstance(option, dict)]
    if any(PROBABILITY_DECIMAL.search(text) for text in texts):
        return ["概率题选项须用最简分数（如 $\\frac{3}{8}$），不用百分数或小数；题干给出的单次概率也改用分数"]
    return []


def local_issues(question: dict) -> list[str]:
    """不花模型调用就能查的结构问题，送审前先筛掉。"""
    issues = []
    options = question.get("options") or []
    keys = [str(option.get("key") or "") if isinstance(option, dict) else "" for option in options]
    kind = question.get('question_type', 'single')
    expected = ['A', 'B'] if kind == 'judge' else ['A', 'B', 'C', 'D']
    if keys != expected:
        issues.append("判断题必须 A/B 两项" if kind == 'judge' else "选项必须是 A/B/C/D 四项")
    if kind not in {'single', 'multi', 'judge'}:
        issues.append('题型非法')
    texts = [str(option.get("text") or "").strip() if isinstance(option, dict) else str(option).strip() for option in options]
    if any(not text for text in texts):
        issues.append("存在空选项")
    elif len(set(texts)) != len(texts):
        issues.append("选项文本重复")
    elif unordered_numbers(question, texts):
        issues.append("数值选项没按大小排，A→D 要么升序要么降序")
    answer = str(question.get('answer') or '')
    valid_answer = (2 <= len(answer) <= 4 and answer == ''.join(sorted(set(answer))) and set(answer) <= set(keys)) if kind == 'multi' else answer in set(keys)
    if not valid_answer:
        issues.append("answer 不在选项内")
    if kind == 'judge' and texts != ['正确', '错误']:
        issues.append('判断题 A=正确、B=错误')
    if question.get('unsuitable'):
        issues.append('模型无法满足此槽位')
    if len(str(question.get("stem") or "").strip()) < 15:
        issues.append("题干过短")
    if any('星期日期问题' in str(tag) for tag in question.get('tags') or []):
        stem = str(question.get('stem') or '')
        if not re.search(r'\d{4}\s*年', stem) or '某年' in stem or '某一年' in stem:
            issues.append('星期日期题须用具体公历年份，不用某年替代；让考生自行判断日历条件')
        if re.search(r'(?:\d+月份?|[该本当]月)(?:共|共有|有|一共|总共|总计)?\s*\d+天', stem):
            issues.append('题干不得直接给出月天数，须保留日期判断步骤')
    analysis = str(question.get("analysis") or "").strip()
    if len(analysis) < 30:
        issues.append("解析过短，无法复算")
    if leaked := scratchpad_leak(question):
        issues.append(
            f"解析里留着倒推答案的草稿（{'、'.join(leaked)}），题干与解析已脱节，重写这道题"
        )
    issues.extend(bare_tex_issues(question))
    issues.extend(probability_format_issues(question))
    if str(question.get("category") or "") == "言语理解与表达":
        issues.extend(yanyu_contract_issues(question))
    return issues


def duplicate_stem(stem: str, others: list[str]) -> bool:
    return any(
        difflib.SequenceMatcher(None, stem, other).ratio() >= DUP_RATIO for other in others
    )


def duplicate_question(question: dict, others: list[dict]) -> bool:
    if question.get('category') not in SOURCE_MODULES:
        return duplicate_stem(question.get('stem', ''), [q.get('stem', '') for q in others])
    # Policy stems often share a long document title; compare the tested options too.
    def content(q):
        stem = re.sub(r'《[^》]+》', '', q.get('stem', ''))
        return stem + '\n' + '\n'.join(sorted(o.get('text', '') for o in q.get('options', [])))
    return duplicate_stem(content(question), [content(q) for q in others
                           if q.get('question_type') == question.get('question_type')])


HISTORY_DAYS = 60


def history_scope(tag: str) -> str:
    """同一父考点下的子考点互相查重：换子考点出同一道题也算撞题。"""
    return str(tag).split("-@")[0]


def load_history(db_path: Path, module: str, slots: list[dict], batch_id: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            for scope in {history_scope(slot["tag"]) for slot in slots}:
                rows = conn.execute(
                    "SELECT external_id, content, options, question_type FROM questions "
                    "WHERE category = ? AND batch_id != ? AND tags LIKE ? AND created_at >= datetime('now', ?)",
                    (module, batch_id, f'%"{scope}%', f"-{HISTORY_DAYS} days"),
                ).fetchall()
                out[scope] = []
                for external_id, content, options, question_type in rows:
                    try:
                        parsed = json.loads(options or "[]")
                    except json.JSONDecodeError:
                        parsed = []
                    out[scope].append({"external_id": external_id, "stem": content or "",
                                       "options": parsed if isinstance(parsed, list) else [],
                                       "question_type": question_type, "category": module})
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return out


def history_duplicate(run: dict, question: dict, tag: str) -> str | None:
    for old in (run.get("history") or {}).get(history_scope(tag), []):
        if duplicate_question(question, [old]):
            return str(old["external_id"])
    return None


def tier_of(run: dict, slot: dict) -> str:
    value = slot.get("difficulty") or run.get("difficulty")
    if value in TIER_TO_LEVEL:
        return value
    return "auto" if run.get("module") in {"数量关系", "言语理解与表达", "判断推理", *SOURCE_MODULES} else "mid"


def source_difficulty_label(batch_id: str, cli_diff, slots: list) -> str | None:
    """Manifest 保留机器难度值；中文显示标题由 source_name 生成。"""
    inferred = next((token for token in ("easy", "mid", "hard")
                     if f"_{token}_" in batch_id or batch_id.endswith(f"_{token}")), "mid")
    slot_diffs = [str(slot.get("difficulty") or cli_diff or inferred) for slot in slots]
    uniq = list(dict.fromkeys(slot_diffs))
    if len(uniq) > 1:
        return "ladder"
    if uniq:
        return uniq[0]
    return str(cli_diff or inferred)


def packed_options(text: str) -> list[dict]:
    matches = list(re.finditer(r"(?:^|\s)([ABCD])[\.、:：]\s*(.*?)(?=\s+[ABCD][\.、:：]|$)", text or ""))
    return [{"key": match.group(1), "text": match.group(2).strip()} for match in matches]


def normalize_writer_shape(raw: dict) -> dict:
    """Accept harmless field/option formatting drift; leave semantic defects for local_issues."""
    row = dict(raw)
    if not str(row.get("stem") or "").strip() and row.get("question"):
        row["stem"] = row.get("question")
    # \n before a non-letter is a prose break; \neq / \nu stay TeX.
    # \\\\frac is a doubled JSON escape. KaTeX reads \\ as a line break, so collapse to \frac.
    for field in ("stem", "analysis", "explanation"):
        if isinstance(row.get(field), str):
            # 字面 \n 后接大写字母或汉字是换行（“\nA项”）；TeX 命令（\neq、\nabla）都是小写。
            row[field] = re.sub(r"\\r\\n|\\n(?![a-z])", "\n", row[field])
            row[field] = wrap_bare_tex(re.sub(r"\\{2,}(?=[A-Za-z])", r"\\", row[field]))
    options = row.get("options")
    if isinstance(options, str):
        parsed = packed_options(options)
        if parsed:
            row["options"] = parsed
    elif isinstance(options, dict):
        row["options"] = [{"key": str(key), "text": str(value).strip()} for key, value in options.items()]
    elif isinstance(options, list) and options and not all(isinstance(item, dict) for item in options):
        parsed = packed_options(" ".join(str(item).strip() for item in options if str(item).strip()))
        if parsed:
            row["options"] = parsed
    options = row.get("options")
    if isinstance(options, list):
        row["options"] = [
            {**item, "text": wrap_bare_tex(re.sub(r"\\{2,}(?=[A-Za-z])", r"\\", item["text"]))}
            if isinstance(item, dict) and isinstance(item.get("text"), str) else item
            for item in options
        ]
    elif isinstance(options, str):
        row["options"] = re.sub(r"\\{2,}(?=[A-Za-z])", r"\\", options)
    return row


def stamp(run: dict, raw: dict, index: int, slot: dict, source: str) -> dict:
    """给单题打上批次身份；只动簿记字段，不改题面内容。"""
    tag = str(slot["tag"])
    row = normalize_writer_shape(raw)
    for field in ("index", "origin", "calculations", "stem_images", "explanation_images"):
        row.pop(field, None)
    row["difficulty"] = TIER_TO_LEVEL.get(tier_of(run, slot), 3)
    row["external_id"] = f"{run['batch_id']}_{index + 1:02d}"
    row["category"] = run["module"]
    # 言语与资料分析标签自身已包含分类，数据库校验要求该模块 sub_category 为空。
    row["sub_category"] = None if run["module"] in {"言语理解与表达", "资料分析", *SOURCE_MODULES} else infer_subcategory(tag, run["module"])
    row["tags"] = [tag]
    row["question_type"] = slot.get('question_type', 'single')
    if raw.get('question_type') and raw['question_type'] != row['question_type']:
        row['unsuitable'] = True
    if row['question_type'] == 'judge':
        row['options'] = [{'key': 'A', 'text': '正确'}, {'key': 'B', 'text': '错误'}]
        row['answer'] = {'T': 'A', 'F': 'B', '对': 'A', '错': 'B'}.get(str(row.get('answer')), row.get('answer'))
    elif row['question_type'] == 'multi':
        value = row.get('answer') or ''
        if isinstance(value, (str, list)):
            row['answer'] = ''.join(sorted(value))
    row["source"] = source
    row["year"] = 2026
    row["region"] = "广东-省直"
    row["options"] = [
        {"key": str(option.get("key") or ""), "text": str(option.get("text") or "").strip()}
        if isinstance(option, dict)
        else {"key": "", "text": str(option).strip()}
        for option in row.get("options") or []
    ]
    analysis = str(row.get("analysis") or row.get("explanation") or "").strip()
    row["analysis"] = analysis
    row["explanation"] = analysis
    return row


def formal_check(run: dict, question: dict) -> dict | None:
    """演绎类逻辑题带 formal 时由程序穷举判定；不适用时返回 None，照旧走逐句审核。"""
    if run['module'] != '判断推理' or question.get('question_type', 'single') != 'single' \
            or not isinstance(question.get('formal'), dict):
        return None
    from logic_model import check, family_of
    if family_of((question.get('tags') or [''])[0]) != 'deduction':
        return None
    return check(question['formal'], question.get('answer'))


def model_failure_review(chunk: list[dict], exc: BaseException) -> dict[str, dict]:
    """一组审核调用失败时，只退回这一组，不让同批其他题重审。"""
    message = f"本组审核未完成，只重审这几题：{exc}"[:500]
    out = {}
    for question in chunk:
        qid = str(question.get("external_id") or "")
        out[qid] = {
            "question_id": qid,
            "answer": str(question.get("answer") or ""),
            "verdict": "REJECT",
            "blind": {"answer": "", "also_valid": [], "unsolvable": True, "steps": "",
                      "actual_difficulty": "", "difficulty_reason": ""},
            "examiner": {"actual_difficulty": "", "difficulty_reason": "", "kaodian_ok": False,
                         "style_ok": False, "analysis_ok": False, "brief_ok": False,
                         "verdict": "REJECT", "issues": [message]},
            "issues": [message],
        }
    return out


def review(run: dict, questions: list[dict], per_item: list[dict], batch_questions=None) -> dict[str, dict]:
    """独立作答与命题审核；言语对高风险用法断言另作核对。"""
    if not questions:
        return {}
    quantity = run['module'] == '数量关系'
    if run['module'] == '判断推理':
        from logic_model import family_of
        from quiz_reasoning import FAMILY_ORDER
        questions = sorted(questions, key=lambda q: FAMILY_ORDER.index(family_of((q.get('tags') or [''])[0])))
    if run['module'] == '言语理解与表达':
        from quiz_verbal import FAMILY_ORDER as VERBAL_ORDER, family_of as verbal_family
        questions = sorted(questions, key=lambda q: VERBAL_ORDER.index(verbal_family((q.get('tags') or [''])[0])))
    if run['module'] in {'数量关系', '言语理解与表达', '判断推理'} and len(questions) > 3:
        chunks = [questions[start:start + 3] for start in range(0, len(questions), 3)]

        def review_chunk(chunk):
            try:
                return review(run, chunk, per_item, batch_questions or questions)
            except RuntimeError as exc:
                return model_failure_review(chunk, exc)

        parts = parallel_map([
            (lambda chunk=chunk: review_chunk(chunk))
            for chunk in chunks
        ])
        out = {}
        for part in parts:
            out.update(part)
        return out
    if run['module'] in SOURCE_MODULES:
        from policy_quiz import review as grounded_review
        return grounded_review(run, questions, per_item, batch_questions or questions,
                               call, public, local_issues, tier_of)
    if quantity:
        from quiz_quantity import BLIND, EXAMINER
    elif run['module'] == '言语理解与表达':
        from quiz_verbal import blind_system, examiner_system, family_of as verbal_family
        families = {verbal_family((q.get('tags') or [''])[0]) for q in questions}
        BLIND, EXAMINER = blind_system(families), examiner_system(families)
    elif run['module'] == '判断推理':
        from logic_model import family_of
        from quiz_reasoning import blind_system, examiner_system
        families = {family_of((q.get('tags') or [''])[0]) for q in questions}
        BLIND, EXAMINER = blind_system(families), examiner_system(families)
    else:
        BLIND, EXAMINER = BLIND_SYSTEM, EXAMINER_SYSTEM
    formal = {str(q["external_id"]): formal_check(run, q) for q in questions}
    formal = {qid: result for qid, result in formal.items() if result and result['verdict'] == 'PASS'}
    blind_payload = json.dumps(
        {"questions": [public(q, with_answer=False) for q in questions]}, ensure_ascii=False
    )
    # 数量、言语、判断的考官不看盲解结论，盲解、考官、用法审核一起提交，由上面的两路上限排队。
    # 其余模块的考官要读盲解结论，所以等盲解返回再审。
    independent = run['module'] in {'数量关系', '言语理解与表达', '判断推理'}
    cards: dict[str, str] = {}
    examiner_items = []
    claims_by_id = {}
    for question in questions:
        index = int(str(question["external_id"]).rsplit("_", 1)[1]) - 1
        slot = per_item[index]
        tag = str(slot["tag"])
        if tag not in cards:
            cards[tag] = run_canon_card(run, tag)
        claims_by_id[str(question["external_id"])] = lite_necessity_claims(question, verbal=True, usage_v2=True, reasoning=run['module'] == '判断推理')
        item = {
            "question": public(question, with_answer=True),
            "declared_kaofa": tag,
            "declared_difficulty": tier_of(run, slot),
            "declared_brief": slot.get("brief", ""),
            "necessity_claims": [{"claim_index": i, "claim": claim}
                                 for i, claim in enumerate(claims_by_id[str(question["external_id"])])],
        }
        if quantity:
            item['sibling_topics'] = slot.get('sibling_topics', [])
        if str(question["external_id"]) in formal:
            result = formal[str(question["external_id"])]
            item['formal'] = question['formal']
            item['formal_result'] = {key: result[key] for key in ('ask', 'models', 'options', 'correct')}
        examiner_items.append(item)

    def examiner_call(items):
        payload = json.dumps(
            {
                "items": items,
                "kaofa_canon": {tag: card for tag, card in cards.items() if card},
                "batch_slots": run.get("slots", []),
                "batch_questions": [public(q, with_answer=True) for q in (
                    (batch_questions or questions) if not quantity or any(s.get('brief') for s in per_item) else questions)],
            },
            ensure_ascii=False,
        )
        return indexed(call(EXAMINER, "逐题审核：\n" + payload, 0.0, 300))

    usage_spec = None
    if run['module'] in {'言语理解与表达', '判断推理'}:
        if run['module'] == '判断推理':
            from quiz_reasoning import CLAIMS as USAGE
        else:
            from quiz_verbal import USAGE
        # 程序已判定唯一的演绎题不再逐句核查断言与题面，由考官核对 formal 是否忠实于题面。
        unchecked = [q for q in questions if str(q['external_id']) not in formal]
        claims = [{'id': f'{q["external_id"]}:{i}', 'claim': claim, 'context': q['stem'], 'options': q['options']}
                  for q in unchecked for i, claim in enumerate(claims_by_id[q['external_id']])]
        if claims or run['module'] == '判断推理' and unchecked:
            fields = {f'c{i}': claim for i, claim in enumerate(claims)}
            if run['module'] == '判断推理':
                fields.update({f'q{i}': {'id': q['external_id'], 'task': 'question_check',
                                       'context': q['stem'], 'options': q['options']}
                               for i, q in enumerate(unchecked)})
            schema = {'type': 'object', 'properties': {key: {
                'type': 'string', 'description': 'PASS或REJECT，后接该句具体依据或反例',
            } for key in fields}, 'required': list(fields), 'additionalProperties': False}
            usage_spec = (USAGE, fields, schema)

    jobs = [lambda: indexed(call(BLIND, "逐题独立作答：\n" + blind_payload, 0.0, 300))]
    if independent:
        jobs.append(lambda: examiner_call(examiner_items))
    if usage_spec is not None:
        usage_system, usage_fields, usage_schema = usage_spec
        jobs.append(lambda: call(usage_system, json.dumps(usage_fields, ensure_ascii=False), 0.0, 300, schema=usage_schema))
    results = parallel_map(jobs)
    blind = results[0]
    cursor = 1
    if independent:
        examiner = results[cursor]
        cursor += 1
    else:
        for item, question in zip(examiner_items, questions):
            item["blind_work"] = blind.get(str(question["external_id"]))
        examiner = examiner_call(examiner_items)
    usage = {}
    if usage_spec is not None:
        checked = results[cursor]
        usage = {claim['id']: {'id': claim['id'], 'valid': checked[key].startswith('PASS'),
                              'reason': checked[key]} for key, claim in usage_spec[1].items()}

    out = {}
    for question in questions:
        qid = str(question["external_id"])
        answer = str(question.get("answer") or "")
        issues = local_issues(question)
        blind_item = blind.get(qid)
        examiner_item = examiner.get(qid)
        index = int(qid.rsplit("_", 1)[1]) - 1
        issues.extend(lite_reasoning_issues(blind_item or {}, examiner_item or {},
                                          tier_of(run, per_item[index]), claims_by_id[qid],
                                          run['module'], current_hard_policy(run['module'])))
        usage_checks = []
        formal_result = formal.get(qid)
        question_check = usage.get(qid) if run['module'] == '判断推理' and not formal_result else None
        if formal_result:
            if (examiner_item or {}).get('formal_ok') is not True:
                issues.append('考官认为形式化与题面不一致：' + str((examiner_item or {}).get('formal_reason') or '缺少核对')[:300])
        elif run['module'] == '判断推理' and (not question_check or question_check['valid'] is not True):
            issues.append('独立题面核查未通过：' + str((question_check or {}).get('reason') or '缺少核查'))
        if run['module'] in {'言语理解与表达', '判断推理'} and not formal_result:
            usage_checks = [{**usage[f'{qid}:{i}'], 'claim_index': i}
                            for i in range(len(claims_by_id[qid])) if f'{qid}:{i}' in usage]
            errors = lite_reasoning_issues(blind_item or {}, {**(examiner_item or {}), 'necessity_checks': usage_checks},
                                           tier_of(run, per_item[index]), claims_by_id[qid],
                                           run['module'], current_hard_policy(run['module']))
            issues.extend(('独立断言核查：' if run['module'] == '判断推理' else '独立用法核查：') + error for error in errors if error not in issues)
        if not blind_item:
            issues.append("盲解官无结论")
        else:
            if not isinstance(blind_item.get("unsolvable"), bool):
                issues.append("盲解官缺少有效 unsolvable 判定")
            alternatives = blind_item.get("also_valid")
            if not isinstance(alternatives, list) or any(key not in ("A", "B", "C", "D") for key in alternatives):
                issues.append("盲解官缺少有效 also_valid 唯一性检查")
            if not isinstance(blind_item.get("steps"), str) or not blind_item["steps"].strip():
                issues.append("盲解官缺少独立解题步骤")
            if blind_item.get("unsolvable") is True:
                issues.append(f"盲解官认为此题无解：{str(blind_item.get('reason') or '')[:300]}")
            blind_answer = str(blind_item.get("answer") or "").strip().upper()
            if blind_answer != answer:
                issues.append(
                    f"盲解官独立解出 {blind_answer or '空'}，题面键定 {answer}："
                    f"{str(blind_item.get('steps') or '')[:400]}"
                )
            extra = [str(key).strip().upper() for key in alternatives] if isinstance(alternatives, list) else []
            extra = [key for key in extra if key and key != answer]
            if extra:
                issues.append(f"盲解官认为 {'/'.join(extra)} 同样成立，答案不唯一")
        if not examiner_item:
            issues.append("考官无结论")
        else:
            flags = {
                "难度不匹配声明档位": examiner_item.get("difficulty_ok"),
                "没落在指定考法上": examiner_item.get("kaodian_ok"),
                "不像广东省考真题": examiner_item.get("style_ok"),
                "解析无法复算或与答案不自洽": examiner_item.get("analysis_ok"),
                "未满足额外命题要求": examiner_item.get("brief_ok"),
            }
            for label, ok in flags.items():
                if ok is not True:
                    issues.append(label)
            # 考法变式程序化核对（服务器链路，与 DSH 链路一致）：槽位分配了细分考法时，
            # 考官必须证明本题确按该变式的设问结构与解题动作命题，退回默认考法/只换场景会被打回。
            variant_name = str(per_item[index].get("kaofa_variant_name") or "").strip()
            if variant_name:
                match = examiner_item.get("variant_match")
                if not isinstance(match, dict) or match.get("ok") is not True \
                        or not str(match.get("reason") or "").strip():
                    issues.append(f"未按细分考法「{variant_name}」命题，须对照该变式的解题动作重出")
            if str(examiner_item.get("verdict") or "").upper() != "PASS":
                issues.append("考官未明确通过")
                if isinstance(examiner_item.get("issues"), list):
                    issues.extend(str(item)[:300] for item in examiner_item["issues"])
        out[qid] = {
            "question_id": qid,
            "answer": answer,
            "verdict": "PASS" if not issues else "REJECT",
            "blind": {
                "actual_difficulty": (blind_item or {}).get("actual_difficulty"),
                "difficulty_reason": (blind_item or {}).get("difficulty_reason"),
                "answer": str((blind_item or {}).get("answer") or "").strip().upper(),
                "also_valid": [
                    key
                    for key in (
                        str(k).strip().upper() for k in ((blind_item or {}).get("also_valid") if isinstance((blind_item or {}).get("also_valid"), list) else [])
                    )
                    if key and key != answer
                ],
                "unsolvable": (blind_item or {}).get("unsolvable"),
                "steps": str((blind_item or {}).get("steps") or "")[:1500],
            },
            "examiner": {
                "actual_difficulty": (examiner_item or {}).get("actual_difficulty"),
                "difficulty_reason": (examiner_item or {}).get("difficulty_reason"),
                "analysis_check": (examiner_item or {}).get("analysis_check"),
                "necessity_checks": (examiner_item or {}).get("necessity_checks"),
                "necessity_claims": claims_by_id[qid],
                "usage_checks": usage_checks,
                **({'question_check': question_check} if run['module'] == '判断推理' and not formal_result else {}),
                **({'formal': question['formal'], 'formal_check': formal_result,
                    'formal_ok': (examiner_item or {}).get('formal_ok'),
                    'formal_reason': (examiner_item or {}).get('formal_reason')} if formal_result else {}),
                "verdict": str((examiner_item or {}).get("verdict") or "REJECT").upper(),
                "difficulty_ok": (examiner_item or {}).get("difficulty_ok"),
                "kaodian_ok": (examiner_item or {}).get("kaodian_ok"),
                "style_ok": (examiner_item or {}).get("style_ok"),
                "analysis_ok": (examiner_item or {}).get("analysis_ok"),
                "brief_ok": (examiner_item or {}).get("brief_ok"),
                "variant_match": (examiner_item or {}).get("variant_match"),
                "issues": [str(item)[:300] for item in (examiner_item or {}).get("issues") or []],
            },
            "issues": issues,
        }
    return out


QUOTE_MIN = 6


def quote_in_question(quote, question: dict) -> bool:
    """变式核对须引用本题原文，防止沿用改稿前的旧理由。"""
    squash = lambda text: re.sub(r"\s+", "", str(text or ""))
    quote = squash(quote)
    body = squash(question.get("stem")) + "".join(squash(o.get("text")) for o in question.get("options") or [])
    return len(quote) >= QUOTE_MIN and quote in body


def dsh_claims(run: dict, question: dict) -> list[str]:
    """与 sign() 写出的证据版本、generation_gate 的复核口径保持同一套原句切分。"""
    return lite_necessity_claims(question, verbal=run['module'] == '言语理解与表达',
                                 usage_v2=True, reasoning=run['module'] == '判断推理')


def align_claim_checks(checks, claims: list[str]) -> tuple[list[dict], list[str]]:
    """把审查方逐句判定对齐到程序原句编号；可写 claim_index，也可直接抄原句。

    缺句、对不上原句、缺判定或依据都逐条列出，不替审查方补成通过。
    """
    problems: list[str] = []
    if checks is None:
        checks = []
    if not isinstance(checks, list):
        return [], ["须为数组"]
    picked: dict[int, dict] = {}
    for check in checks:
        if not isinstance(check, dict):
            problems.append("存在非对象条目")
            continue
        index = check.get("claim_index")
        if type(index) is not int or not 0 <= index < len(claims):
            text = str(check.get("claim") or "").strip()
            index = None
            if text:
                ratios = [difflib.SequenceMatcher(None, text, claim).ratio() for claim in claims]
                best = max(range(len(claims)), key=ratios.__getitem__, default=None)
                if best is not None and (text == claims[best] or ratios[best] >= 0.8):
                    index = best
            if index is None:
                problems.append(f"对不上解析原句：{text[:60] or check.get('claim_index')}")
                continue
        valid, reason = check.get("valid"), str(check.get("reason") or "").strip()
        if not isinstance(valid, bool) or not reason:
            problems.append(f"第{index}句缺少 valid 判定或依据：{claims[index][:60]}")
            continue
        if index in picked and picked[index]["valid"] is False:
            continue
        picked[index] = {"claim_index": index, "valid": valid, "reason": reason}
    missing = [i for i in range(len(claims))
               if i not in picked and not any(f"第{i}句" in p for p in problems)]
    if missing:
        problems.append(f"未核查第{'、'.join(map(str, missing))}句（共{len(claims)}句，"
                        f"原句见 --dsh-claims；如第{missing[0]}句：{claims[missing[0]][:40]}）")
    for index, item in sorted(picked.items()):
        if item["valid"] is False:
            problems.append(f"第{index}句不成立：{claims[index][:60]}；{item['reason'][:200]}")
    return [picked[i] for i in sorted(picked)], problems


def build_dsh_review(run: dict, review_path: Path, source: str, progress=None) -> tuple[list[dict], dict, list[dict]]:
    """DSH 出题模式：读入 DSH 生成的题目与子 agent 审核证据，不经服务器模型。

    review.json 结构：
    {
      "module": "数量关系",                      # 须与 --module 一致
      "auditor": "dsh-subagent",                # 审核方标识（evidence.model 用）
      "questions": [                            # 原始题目，须含 stem/options/answer/analysis
        {"stem": "...", "options": [{"key": "A", "text": "..."}, ...],
         "answer": "A", "analysis": "...", "question_type": "single"}
      ],
      "review": {
        "blind": {                              # 盲解官：DSH 子 agent 不给答案独立做题
          "1": {"answer": "A", "steps": "...", "also_valid": [], "unsolvable": false,
                "actual_difficulty": "mid", "difficulty_reason": "..."}
        },
        "examiner": {                           # 考官：看答案核对五维
          "1": {"verdict": "PASS", "actual_difficulty": "mid", "difficulty_reason": "...",
                "analysis_check": "...", "difficulty_ok": true, "kaodian_ok": true,
                "style_ok": true, "analysis_ok": true, "brief_ok": true,
                "necessity_checks": [{"claim_index": 0, "valid": true, "reason": "..."}],
                "usage_checks": [...],            # 言语、判断推理：独立核查官逐句判定，格式同上
                "question_check": {...},          # 判断推理
                "issues": []}
        }
      }
    }

    结构校验（local_issues）与闸门逐项校验照常执行。原句清单由 --dsh-claims 给出；
    necessity_checks / usage_checks 每条写 claim_index 或原句 claim，须覆盖全部原句且成立。
    """
    import difflib

    if not review_path.is_file():
        raise ValueError(f"DSH 审核证据不存在：{review_path}")
    try:
        payload = json.loads(review_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"DSH 审核证据 JSON 无法解析：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("DSH 审核证据须为 JSON 对象")
    run['dsh_auditor'] = str(payload.get("auditor") or "dsh-subagent").strip() or "dsh-subagent"
    if str(payload.get("module") or "") != run["module"]:
        raise ValueError(f"DSH 审核证据 module 不一致：{payload.get('module')}，期望 {run['module']}")
    total = int(run["planned_count"])
    per_item = expand_slots(run["slots"])
    raw_questions = payload.get("questions") or []
    if not isinstance(raw_questions, list) or len(raw_questions) != total:
        raise ValueError(f"DSH 题目数量须为 {total}，实际 {len(raw_questions)}")
    review = payload.get("review") or {}
    blind_all = review.get("blind") or {}
    examiner_all = review.get("examiner") or {}
    if not isinstance(blind_all, dict) or not isinstance(examiner_all, dict):
        raise ValueError("DSH 审核证据缺少 blind/examiner 角色记录")

    questions: list[dict] = []
    results: dict[str, dict] = {}
    feedback: dict[int, list[str]] = {}
    rejected = []
    started = time.monotonic()

    def note(**kwargs):
        if progress is None:
            return
        try:
            progress(**kwargs)
        except Exception:
            return

    note(stage="DSH 导入", detail=f"校验 {total} 题结构与审核证据", progress=10, status="running")
    for index, raw in enumerate(raw_questions):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index + 1} 题不是对象")
        slot = per_item[index]
        tag = str(slot["tag"])
        qid = f"{run['batch_id']}_{index + 1:02d}"
        question = stamp(run, raw, index, slot, source)
        issues = local_issues(question)
        judged = formal_check(run, question)
        if judged and judged['verdict'] != 'PASS':
            issues.extend('形式化判定：' + issue for issue in judged['issues'])
        if run['module'] == '判断推理':
            from quiz_reasoning import stem_issues
            issues.extend(stem_issues(question))
        if duplicate_question(question, questions):
            issues.append("与本批次已有题目撞题，换情境与数据重出")
        old = history_duplicate(run, question, tag)
        if old:
            issues.append(f"与历史题 {old} 撞题（近{HISTORY_DAYS}天同考点），换情境与陈述结构重出")
        if issues:
            feedback[index] = issues
            rejected.append({"question_id": qid, "issues": issues})
            continue
        blind_item = blind_all.get(str(index + 1)) or {}
        examiner_item = examiner_all.get(str(index + 1)) or {}
        if not isinstance(blind_item, dict) or not isinstance(examiner_item, dict):
            issues.append("缺少盲解官或考官证据")
        else:
            if run['module'] == '言语理解与表达':
                conflict = topic_conflict(str(question.get('stem') or ''), run.get('yanyu_avoid') or {})
                if conflict:
                    issues.append(conflict)
                issues.extend(vocab_issues(question, slot))
            # 盲解官独立解出的答案必须等于题面键定答案
            blind_answer = str(blind_item.get("answer") or "").strip().upper()
            if blind_answer != str(question.get("answer") or "").strip().upper():
                issues.append(f"盲解官独立解出 {blind_answer or '空'}，题面键定 {question.get('answer')}："
                              f"{str(blind_item.get('steps') or '')[:400]}")
            extras = [str(k).strip().upper() for k in (blind_item.get("also_valid") or []) if str(k).strip().upper() != str(question.get("answer") or "").strip().upper()]
            if extras:
                issues.append(f"盲解官认为 {'/'.join(extras)} 同样成立，答案不唯一")
            if blind_item.get("unsolvable") is not False:
                issues.append(f"盲解官认为此题无解：{str(blind_item.get('reason') or '')[:300]}")
            for key, label in (("difficulty_ok", "难度不匹配声明档位"), ("kaodian_ok", "没落在指定考法上"),
                               ("style_ok", "不像广东省考真题"), ("analysis_ok", "解析无法复算或与答案不自洽"),
                               ("brief_ok", "未满足额外命题要求")):
                if examiner_item.get(key) is not True:
                    issues.append(label)
            # 考法变式程序化核对：槽位分配了细分考法时，考官必须证明本题确按该变式的
            # 设问结构与解题动作命题，退回最常见默认考法/只换场景会被打回。
            variant_name = str(slot.get("kaofa_variant_name") or "").strip()
            if variant_name:
                match = examiner_item.get("variant_match")
                if not isinstance(match, dict) or match.get("ok") is not True \
                        or not str(match.get("reason") or "").strip():
                    issues.append(f"未按细分考法「{variant_name}」命题，须对照该变式的解题动作重出")
                elif not quote_in_question(match.get("quote"), question):
                    issues.append(f"考官变式核对缺少本题原文引用：variant_match.quote 须从题干或选项原样摘出"
                                  f"体现「{variant_name}」的一段（≥{QUOTE_MIN}字）")

            if str(examiner_item.get("verdict") or "").upper() != "PASS":
                issues.append("考官未明确通过")
            # 原句由程序切分（--dsh-claims 可提前列出），审查方逐句判定；这里只负责把
            # claim_index / 原句文本对齐成闸门格式，缺句和反例逐条报出，不代填通过。
            claims = dsh_claims(run, question)
            aligned, problems = align_claim_checks(examiner_item.get("necessity_checks"), claims)
            issues.extend("考官必要性断言核查：" + p for p in problems)
            examiner_item = {**examiner_item, "necessity_checks": aligned}
            if judged:
                # 程序已判定唯一：免独立核查官逐句核查与题面核查，改由考官确认 formal 忠实于题面。
                if examiner_item.get('formal_ok') is not True or not str(examiner_item.get('formal_reason') or '').strip():
                    issues.append('考官须确认形式化忠实于题面：formal_ok=true 并写 formal_reason')
            elif run['module'] in {'言语理解与表达', '判断推理'}:
                label = '独立断言核查：' if run['module'] == '判断推理' else '独立用法核查：'
                usage_aligned, usage_problems = align_claim_checks(examiner_item.get("usage_checks"), claims)
                issues.extend(label + p for p in usage_problems)
                examiner_item = {**examiner_item, "usage_checks": usage_aligned}
            reasoning_issues = lite_reasoning_issues(blind_item or {}, examiner_item or {}, tier_of(run, slot),
                                                     claims, run['module'], current_hard_policy(run['module']))
            issues.extend(e for e in reasoning_issues
                          if not problems or not e.startswith(("必要性断言", "考官缺少必要性断言")))
            if run['module'] == '判断推理' and not judged:
                check = examiner_item.get('question_check')
                if not isinstance(check, dict) or check.get('valid') is not True or not str(check.get('reason') or '').startswith('PASS'):
                    issues.append('独立题面核查缺失或未通过')
        if issues:
            feedback[index] = issues
            rejected.append({"question_id": qid, "issues": issues})
            continue
        # auto 难度落库：言语/判断/政治常识按两位审核较低评级（与 build_batch 一致），其余按考官实际评级
        _tier = tier_of(run, slot)
        if _tier == 'auto':
            _blind_level = TIER_TO_LEVEL.get((blind_item or {}).get('actual_difficulty'))
            _examiner_level = TIER_TO_LEVEL.get((examiner_item or {}).get('actual_difficulty'))
            if _blind_level is None or _examiner_level is None:
                issues.append(f"第 {index + 1} 题盲解官或考官未给出有效实际难度")
                feedback[index] = issues
                rejected.append({"question_id": qid, "issues": issues})
                continue
            if run['module'] in {'言语理解与表达', '判断推理', *SOURCE_MODULES}:
                question['difficulty'] = min(_blind_level, _examiner_level)
            else:
                question['difficulty'] = _examiner_level
        # 通过：按 review() 输出结构记录（necessity_checks 已对齐）
        results[qid] = {
            "question_id": qid,
            "answer": str(question.get("answer") or ""),
            "verdict": "PASS",
            "blind": {
                "actual_difficulty": (blind_item or {}).get("actual_difficulty"),
                "difficulty_reason": (blind_item or {}).get("difficulty_reason"),
                "answer": str((blind_item or {}).get("answer") or "").strip().upper(),
                "also_valid": [str(k).strip().upper() for k in (blind_item or {}).get("also_valid") or []],
                "unsolvable": (blind_item or {}).get("unsolvable"),
                "steps": str((blind_item or {}).get("steps") or "")[:1500],
            },
            "examiner": {
                "actual_difficulty": (examiner_item or {}).get("actual_difficulty"),
                "difficulty_reason": (examiner_item or {}).get("difficulty_reason"),
                "analysis_check": (examiner_item or {}).get("analysis_check"),
                "necessity_checks": (examiner_item or {}).get("necessity_checks"),
                **({"formal": question['formal'], "formal_check": judged,
                    "formal_ok": examiner_item.get('formal_ok'), "formal_reason": examiner_item.get('formal_reason')}
                   if judged else {"usage_checks": (examiner_item or {}).get("usage_checks"),
                                   "question_check": (examiner_item or {}).get("question_check")}),
                "necessity_claims": claims,
                "verdict": str((examiner_item or {}).get("verdict") or "REJECT").upper(),
                "difficulty_ok": (examiner_item or {}).get("difficulty_ok"),
                "kaodian_ok": (examiner_item or {}).get("kaodian_ok"),
                "style_ok": (examiner_item or {}).get("style_ok"),
                "analysis_ok": (examiner_item or {}).get("analysis_ok"),
                "brief_ok": (examiner_item or {}).get("brief_ok"),
                "topic_ok": (examiner_item or {}).get("topic_ok"),
                "variant_match": (examiner_item or {}).get("variant_match"),
                "issues": [str(item)[:300] for item in (examiner_item or {}).get("issues") or []],
            },
            "issues": [],
        }
        questions.append(question)

    if rejected or len(questions) != total:
        passed_indices = {int(str(q["external_id"]).rsplit("_", 1)[1]) - 1 for q in questions}
        detail = "; ".join(
            f"第{index + 1}题：{'、'.join(feedback.get(index, ['未产出']))[:300]}"
            for index in range(total) if index not in passed_indices
        )
        raise RuntimeError(f"DSH 审核未通过 {len(questions)}/{total} 题（{detail}）")
    log = [{
        "round": 1,
        "asked": list(range(1, total + 1)),
        "accepted": total,
        "rejected": rejected,
        "seconds": round(time.monotonic() - started, 1),
    }]
    return questions, results, log


def build_batch(run: dict, rounds: int, source: str, audit_dir: Path | None = None, progress=None) -> tuple[list[dict], dict, list[dict]]:
    """出稿 → 双审 → 只重出不合格的题。返回题目、逐题证据、每轮记录。"""
    if audit_dir is not None and audit_dir.exists() and any(audit_dir.iterdir()):
        raise ValueError("批次目录已有产物，不能覆盖旧证据；请使用新的 batch_id")
    total = int(run["planned_count"])
    per_item = expand_slots(run["slots"])
    slots: list[dict | None] = [None] * total
    results: dict[str, dict] = {}
    feedback: dict[int, list[str]] = {}
    previous: dict[int, dict] = {}
    analysis_repairs: set[int] = set()
    repaired: set[int] = set()
    log = []

    def note(**kwargs):
        if progress is None:
            return
        try:
            progress(**kwargs)
        except Exception:
            return

    def passed_count():
        return sum(value is not None for value in slots)

    for attempt in range(1, rounds + 1):
        todo = [index for index, value in enumerate(slots) if value is None]
        if not todo:
            break
        asks = []
        for index in todo:
            slot = per_item[index]
            ask = {
                "index": index + 1,
                "tag": str(slot["tag"]),
                "difficulty": tier_of(run, slot),
                "question_type": slot.get('question_type', 'single'),
            }
            if slot.get("brief"):
                ask["brief"] = str(slot["brief"])
            if slot.get("vocab_word"):
                ask["vocab_word"] = str(slot["vocab_word"])
                ask["vocab_brief"] = str(slot.get("vocab_brief") or "")
            if feedback.get(index):
                ask["上一轮被退回的原因"] = feedback[index]
                if run['module'] in {'数量关系', '言语理解与表达', '判断推理'} and index in previous:
                    ask['上一轮题目'] = public(previous[index], with_answer=True)
                if index in analysis_repairs:
                    ask['repair'] = 'analysis_only'
            asks.append(ask)
        kept = [str(value.get("stem") or "") for value in slots if value]
        started = time.monotonic()
        # Freeze all selected definitions before the first bounded model request.
        for ask in asks:
            run_canon_card(run, ask['tag'])
        if audit_dir is not None and attempt == 1:
            audit_dir.mkdir(parents=True, exist_ok=True)
            (audit_dir / "generation-input.json").write_text(
                json.dumps({k: v for k, v in run.items() if k != "history"},
                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        draft = {"questions": []}
        attempt_record = {"round": attempt, "items": asks, "draft": draft, "groups": []}
        group_size = 3 if run['module'] in {'数量关系', '判断推理', *SOURCE_MODULES} else len(asks)
        strict_indices = run['module'] in {'数量关系', '言语理解与表达', '判断推理', *SOURCE_MODULES}
        writer_options = {}
        if run['module'] == '数量关系':
            from quiz_quantity import WRITER_SCHEMA
            writer_options['schema'] = WRITER_SCHEMA
        elif run['module'] == '判断推理':
            from quiz_reasoning import WRITER_SCHEMA
            writer_options['schema'] = WRITER_SCHEMA
        elif run['module'] == '言语理解与表达':
            from quiz_verbal import WRITER_SCHEMA
            writer_options['schema'] = WRITER_SCHEMA
        grouped = asks
        if run['module'] == '判断推理':
            from logic_model import family_of
            from quiz_reasoning import FAMILY_ORDER
            grouped = sorted(asks, key=lambda ask: FAMILY_ORDER.index(family_of(ask['tag'])))
        if run['module'] == '言语理解与表达':
            from quiz_verbal import verbal_groups
            groups = verbal_groups(grouped)
        else:
            groups = [grouped[start:start + group_size] for start in range(0, len(grouped), group_size)]
        # 同一轮各组同时出。组间看不到彼此的题干，撞题留到本组返回后的查重。
        finished: list[dict | None] = [None] * len(groups)
        file_lock = threading.Lock()

        def produce(position: int) -> dict:
            group = groups[position]
            drafted = passed_count()
            first, last = group[0]["index"], group[-1]["index"]
            span = str(first) if first == last else f"{first}–{last}"
            note(stage="命题", detail=f"第{attempt}轮 · 正在出第 {span} 题",
                 passed=drafted, round_no=attempt, status="running",
                 progress=min(85, drafted * 85 // total) if total else 0)
            try:
                response = call(WRITER_SYSTEM, writer_prompt(run, group, list(kept)), 0.5, 600, **writer_options)
            except RuntimeError as exc:
                response = {"questions": [], "error": f"本组生成失败，只重出这几题：{exc}"[:500]}
            produced_group = [q for q in response.get('questions') or [] if isinstance(q, dict)]
            requested, candidates = {ask['index'] for ask in group}, []
            for offset, raw in enumerate(produced_group):
                # Missing indices fall back within this group, never to the first global slots.
                index = item_index(raw)
                if index == 0 and offset < len(group):
                    index = group[offset]['index']
                if strict_indices and index not in requested:
                    continue
                candidates.append({**raw, 'index': index})
            indices = [item['index'] for item in candidates]
            accepted = [item for item in candidates if not strict_indices or indices.count(item['index']) == 1]
            record = {'items': group, 'response': response, 'accepted': accepted}
            with file_lock:
                finished[position] = record
                attempt_record['groups'] = [
                    {'items': row['items'], 'response': row['response']} for row in finished if row
                ]
                attempt_record['draft'] = {
                    'questions': [item for row in finished if row for item in row['accepted']]
                }
                if audit_dir is not None:
                    (audit_dir / f"attempt-{attempt}.json").write_text(
                        json.dumps(attempt_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return record

        records = parallel_map([lambda position=position: produce(position) for position in range(len(groups))])
        draft['questions'] = [item for record in records for item in record['accepted']]
        attempt_record['groups'] = [{'items': record['items'], 'response': record['response']} for record in records]
        attempt_record['draft'] = draft

        produced = [item for item in draft.get("questions") or [] if isinstance(item, dict)]
        fresh: list[dict] = []
        rejected = []
        for record in records:
            error = str((record.get("response") or {}).get("error") or "")
            if not error:
                continue
            for ask in record["items"]:
                index = int(ask["index"]) - 1
                feedback[index] = [error]
                rejected.append({"question_id": f"{run['batch_id']}_{index + 1:02d}", "issues": [error]})
        for position, index in enumerate(todo):
            raw = next(
                (item for item in produced if item_index(item) == index + 1),
                produced[position] if not strict_indices and position < len(produced) else None,
            )
            if raw is None:
                continue
            if index in analysis_repairs:
                # Retain the already solved question; the replacement still receives full review.
                raw = {**previous[index], 'analysis': raw.get('analysis') or raw.get('explanation') or '',
                       'unsuitable': raw.get('unsuitable', False)}
                repaired.add(index)
                analysis_repairs.discard(index)
            question = stamp(run, raw, index, per_item[index], source)
            previous[index] = question
            others = [value for value in slots if value]
            # 结构问题和撞题都不花审核调用，当场退回。
            reasons = local_issues(question)
            judged = formal_check(run, question)
            if judged and judged['verdict'] != 'PASS':
                reasons.extend('形式化判定：' + issue for issue in judged['issues'])
            if run['module'] == '判断推理':
                from quiz_reasoning import stem_issues
                reasons.extend(stem_issues(question))
            if duplicate_question(question, others):
                reasons.append("与本批次已有题目撞题，换情境与数据重出")
            old = history_duplicate(run, question, str(per_item[index]["tag"]))
            if old:
                reasons.append(f"与历史题 {old} 撞题（近{HISTORY_DAYS}天同考点），换情境与陈述结构重出")
            if run['module'] == '言语理解与表达':
                conflict = topic_conflict(str(question.get('stem') or ''), run.get('yanyu_avoid') or {})
                if conflict:
                    reasons.append(conflict)
                reasons.extend(vocab_issues(question, per_item[index]))
            if reasons:
                feedback[index] = reasons
                rejected.append({"question_id": str(question["external_id"]), "issues": reasons})
                continue
            slots[index] = question
            fresh.append(question)

        if fresh and run["module"] == "言语理解与表达":
            bad = set(duplicate_fill_ids([value for value in slots if value]))
            if bad:
                kept_fresh = []
                for question in fresh:
                    if str(question.get("external_id") or "") not in bad:
                        kept_fresh.append(question)
                        continue
                    index = int(str(question["external_id"]).rsplit("_", 1)[1]) - 1
                    slots[index] = None
                    feedback[index] = ["同批逻辑填空题干重复，只重出重复的这一题"]
                    rejected.append({"question_id": str(question["external_id"]), "issues": feedback[index]})
                fresh = kept_fresh

        current = [value for value in slots if value]
        if fresh and run["module"] == "言语理解与表达":
            from quiz_verbal import balance_verbal_letters
            balance_verbal_letters(current, locked=set(results), seed=f"{run['batch_id']}:{attempt}")
        # 只审本轮新出的题；已过关的题不重审。跨题要求由新题审核时对照 batch_questions（整批现有题）检查。
        reviewed = fresh
        drafted = passed_count()
        note(stage="审核", detail=f"第{attempt}轮 · 正在审核 {len(reviewed)} 题",
             passed=drafted, round_no=attempt, status="running",
             progress=min(85, drafted * 85 // total) if total else 0)
        round_results = review(run, reviewed, per_item, current)
        results.update(round_results)
        for question in reviewed:
            qid = str(question["external_id"])
            if round_results[qid]["verdict"] == "PASS":
                index = int(qid.rsplit("_", 1)[1]) - 1
                if run['module'] in {'言语理解与表达', '判断推理', *SOURCE_MODULES}:
                    question['difficulty'] = min(TIER_TO_LEVEL[round_results[qid][role]['actual_difficulty']]
                                                 for role in ('blind', 'examiner'))
                elif tier_of(run, per_item[index]) == 'auto':
                    question['difficulty'] = TIER_TO_LEVEL[round_results[qid]['examiner']['actual_difficulty']]
                elif lite_allowed_tiers(tier_of(run, per_item[index]), run['module'], current_hard_policy(run['module'])) == ('mid', 'hard'):
                    question['difficulty'] = min(TIER_TO_LEVEL[round_results[qid][role]['actual_difficulty']]
                                                 for role in ('blind', 'examiner'))
                continue
            index = int(qid.rsplit("_", 1)[1]) - 1
            slots[index] = None
            feedback[index] = round_results[qid]["issues"]
            if run['module'] in {'言语理解与表达', '判断推理'} and index not in repaired:
                item = round_results[qid]
                blind, examiner = item['blind'], item['examiner']
                allowed = lite_allowed_tiers(tier_of(run, per_item[index]), run['module'], current_hard_policy(run['module']))
                if (blind['answer'] == question['answer'] and blind['unsolvable'] is False
                        and blind['also_valid'] == [] and all(role['actual_difficulty'] in allowed for role in (blind, examiner))
                        and (run['module'] != '判断推理' or (examiner.get('question_check') or {}).get('valid') is True
                             or (examiner.get('formal_check') or {}).get('verdict') == 'PASS' and examiner.get('formal_ok') is True)
                        and all(examiner[key] is True for key in ('kaodian_ok', 'style_ok', 'brief_ok'))):
                    analysis_repairs.add(index)
            results.pop(qid, None)
            # 退掉的题不会进 results，原因留在这里，否则事后无从判断审核官是否过严。
            rejected.append({"question_id": qid, "issues": round_results[qid]["issues"]})
        log.append(
            {
                "round": attempt,
                "asked": [index + 1 for index in todo],
                "accepted": sum(1 for index in todo if slots[index] is not None),
                "rejected": rejected,
                "seconds": round(time.monotonic() - started, 1),
            }
        )
        if audit_dir is not None:
            attempt_record.update({**log[-1], "review": round_results})
            (audit_dir / f"attempt-{attempt}.json").write_text(
                json.dumps(attempt_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        accepted = passed_count()
        note(stage="审核", detail=f"第{attempt}轮 · 已过审 {accepted}/{total}",
             passed=accepted, round_no=attempt, status="running",
             progress=min(85, accepted * 85 // total) if total else 0)

    missing = [index + 1 for index, value in enumerate(slots) if value is None]
    if missing:
        detail = "; ".join(
            f"第{index}题：{'、'.join(feedback.get(index - 1) or ['未产出'])[:300]}"
            for index in missing
        )
        raise RuntimeError(f"{rounds} 轮后仍有 {len(missing)} 道不合格（{detail}）")
    return [value for value in slots if value], results, log


def write_batch(run: dict, batch_dir: Path, questions: list[dict], source: str) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    if run["module"] == "言语理解与表达":
        validate_yanyu_fills(questions)
    letters = [str(question.get("answer") or "") for question in questions]
    counts: dict[str, int] = {}
    for letter in letters:
        counts[letter] = counts.get(letter, 0) + 1
    manifest = {
        "batch_id": run["batch_id"],
        "source": source,
        "region": "广东-省直",
        "year": 2026,
        "kind": "ai-generated",
        "difficulty_tier": source_difficulty_label(
            run.get("batch_id") or "", run.get("difficulty"),
            [{**slot, "difficulty": tier_of(run, slot)} for slot in run["slots"]],
        ),
        "generation": {
            "style_marker": "GONGKAO-STYLE-v1",
            "pipeline": "quiz_lite",
            "requested_scope": run.get("requested_scope"),
            "kaofa_canon": run.get("kaofa_canon", {}),
            "batch_constraints": {
                "all_original": True,
                "question_count": len(questions),
                "targeted_drill": True,
                "no_images": True,
                "answer_max_per_letter": (
                    -(-len(questions) // 4)
                    if run["module"] == "言语理解与表达" and len(questions) >= 4
                    else (max(counts.values()) if counts else 1)
                ),
                "answer_min_letters": (
                    min(4, len(questions))
                    if run["module"] == "言语理解与表达" and len(questions) >= 4
                    else len(counts)
                ),
                "tag_counts": {
                    str(slot["tag"]): sum(
                        int(other["count"])
                        for other in run["slots"]
                        if str(other["tag"]) == str(slot["tag"])
                    )
                    for slot in run["slots"]
                },
                "slot_plan": [
                    {key: value for key, value in {**slot, "difficulty": tier_of(run, slot)}.items()
                     if value not in (None, "")}
                    for slot in run["slots"]
                ],
            },
            "generation_contexts": [],
            "evaluation_contexts": [],
        },
    }
    if run['module'] == '数量关系':
        manifest['generation']['quantity_hard_policy'] = QUANTITY_HARD_POLICY
    elif run['module'] == '言语理解与表达':
        manifest['generation']['verbal_difficulty_policy'] = VERBAL_PRACTICE_POLICY
    elif run['module'] == '判断推理':
        manifest['generation']['reasoning_difficulty_policy'] = REASONING_PRACTICE_POLICY
    if run['module'] in SOURCE_MODULES:
        manifest['generation']['policy_difficulty_policy'] = POLICY_PRACTICE_POLICY
        (batch_dir / 'sources.json').write_text(json.dumps(run['source_pack'], ensure_ascii=False, indent=2), encoding='utf-8')
        manifest['generation'].update(source_grounded=True, source_as_of=run['source_pack']['as_of'],
                                      sources_sha256=digest(batch_dir / 'sources.json'))
    (batch_dir / "questions.json").write_text(
        json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sign(batch_dir: Path, run: dict, results: dict[str, dict], log: list[dict], *, model_label: str | None = None) -> None:
    """写逐题复核证据并签发精简收据，import-batch 仍然要校验它。"""
    questions = json.loads((batch_dir / "questions.json").read_text(encoding="utf-8"))
    ids = [str(question["external_id"]) for question in questions]
    evidence = {
        "version": 9 if run['module'] == '判断推理' else 8 if run['module'] in SOURCE_MODULES else 7 if run['module'] == '言语理解与表达' else 3,
        "kind": "examsystem-lite-review",
        "batch_id": run["batch_id"],
        "model": model_label or MODEL,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": "PASS" if all(results[qid]["verdict"] == "PASS" for qid in ids) else "REJECT",
        "rounds": log,
        "questions_sha256": digest(batch_dir / "questions.json"),
        "results": [results[qid] for qid in ids],
    }
    evidence_dir = batch_dir / "evidence"
    if run['module'] in SOURCE_MODULES:
        evidence['policy_difficulty_policy'] = POLICY_PRACTICE_POLICY
    if run['module'] in {'言语理解与表达', '判断推理'}:
        evidence['usage_model'] = model_label or MODEL
    if run['module'] == '数量关系':
        evidence['quantity_hard_policy'] = QUANTITY_HARD_POLICY
    elif run['module'] == '言语理解与表达':
        evidence['verbal_difficulty_policy'] = VERBAL_PRACTICE_POLICY
    elif run['module'] == '判断推理':
        evidence['reasoning_difficulty_policy'] = REASONING_PRACTICE_POLICY
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "lite-review.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    receipt = {
        "version": LITE_VERSION,
        "batch_id": run["batch_id"],
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha256": digest(batch_dir / "manifest.json"),
        "questions_sha256": digest(batch_dir / "questions.json"),
        "question_ids": ids,
        "lite_review": {
            "path": str(evidence_path.relative_to(batch_dir)),
            "sha256": digest(evidence_path),
            "model": model_label or MODEL,
        },
    }
    (batch_dir / RECEIPT).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def archive_dsh_residue(output_dir: Path, path: Path) -> Path:
    """失败证据移出批次路径保留备查，batch_id 可直接重导。"""
    target = output_dir / "_dsh-failed" / f"{path.name}-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def import_batch(batch_dir: Path, db_path: Path) -> int:
    env = {**os.environ, "EXAM_DB": str(db_path)}
    result = subprocess.run(
        [service_node(), str(ROOT / "scripts" / "import-batch.mjs"), str(batch_dir)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "import failed").strip()[-2000:])
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM questions WHERE batch_id=?", (batch_dir.name,)
            ).fetchone()[0]
        )
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes 轻量专项出题（盲解官 + 考官双审）")
    parser.add_argument("--module", default="", help="政治理论 / 常识判断 / 判断推理 / 数量关系 / 言语理解与表达 / 资料分析")
    parser.add_argument("--tag", help="规范主标签，如 判断推理-逻辑判断-翻译推理")
    parser.add_argument("--count", type=int)
    parser.add_argument(
        "--blueprint",
        help='多考法编排，内联 JSON 或 @路径：{"slots":[{"tag":"...","count":3,"difficulty":"hard"}]}',
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--variant", help="点名考法变式（id 或名称，逗号分隔可多个），只在这些变式里出")
    parser.add_argument("--focus", choices=["weak"], help="weak：只在错得多的考法变式里出（无数据时退回全部变式）")
    parser.add_argument("--difficulty", choices=["easy", "mid", "hard", "auto"])
    parser.add_argument("--rounds", type=int, default=3, help="最多几轮补题，默认 3")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "hermes-batches")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--no-import", action="store_true", help="只出题签收据，不写库")
    parser.add_argument("--plan-only", action="store_true", help="只输出考点、配额和难度，不出题、不注册、不入库")
    parser.add_argument("--balance-verbal", type=Path, help="派审前把言语题正确项字母摊开，打印题目 JSON，不入库")
    parser.add_argument('--sources', help='政治/常识权威资料 ID，逗号分隔；默认按标签匹配')
    parser.add_argument('--as-of', help='资料截止日期 YYYY-MM-DD，默认今天')
    parser.add_argument('--question-type', choices=['single', 'multi', 'judge'], help='政治单考点可指定题型')
    parser.add_argument(
        '--dsh-import', type=Path,
        help='DSH 出题模式：读入 DSH 生成的题目+审核证据 JSON（由 DSH 子 agent 审核，不经服务器模型），'
             '复用现有签名/闸门/入库管线。JSON 结构见 build_dsh_review。',
    )
    parser.add_argument(
        '--dsh-claims', type=Path,
        help='DSH：读题目 JSON（题目数组或含 questions 的 review.json），按闸门同一切分输出每题待核查原句及编号，'
             '供考官 / 独立核查官逐句判定。不写目录、不入库。',
    )
    parser.add_argument(
        '--dsh-check', type=Path,
        help='DSH：预检 review.json，在临时目录跑完导入校验 + 签收 + 闸门复核，一次报出全部问题；'
             '不写批次目录、不登记、不入库，batch_id 不会被占用。',
    )
    args = parser.parse_args()
    if sum(bool(x) for x in (args.dsh_import, args.dsh_claims, args.dsh_check)) > 1:
        parser.error('--dsh-import / --dsh-claims / --dsh-check 只能选一个')
    return args


def main() -> int:
    args = parse_args()
    os.environ["EXAM_DB"] = str(args.db)
    started = time.monotonic()
    batch_dir = None
    tracked = False
    finished = False
    try:
        if args.balance_verbal:
            from quiz_verbal import balance_verbal_letters
            payload = json.loads(args.balance_verbal.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("review"):
                raise ValueError("答案打乱必须在派审之前做；已有审核记录时不能再改字母")
            questions = payload.get("questions") if isinstance(payload, dict) else payload
            if not isinstance(questions, list):
                raise ValueError("题目文件须为数组，或 {\"questions\": [...]}")
            for index, question in enumerate(questions):
                if isinstance(question, dict):
                    question.setdefault("category", "言语理解与表达")
                    question.setdefault("external_id", f"{args.batch_id}_{index + 1:02d}")
            balance_verbal_letters(questions, locked=set(), seed=str(args.batch_id))
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        # 带图题型（图形推理、空间类、科学推理）由程序出图：转给 figure_quiz，参数原样沿用
        from figure_quiz import is_figure_request, run as run_figure
        if is_figure_request(args):
            return run_figure(args)
        if args.module in SOURCE_MODULES and not args.tag and not args.blueprint:
            from policy_quiz import module_slots
            module = args.module
            count = args.count if args.count is not None else (10 if module == '政治理论' else 5)
            if not 1 <= count <= MAX_COUNT:
                raise ValueError('题量须为1–15')
            seeded = module_slots(module, count, args.difficulty)
            module, slots = resolve_slots(argparse.Namespace(**{
                **vars(args), "blueprint": json.dumps({"slots": seeded}, ensure_ascii=False),
                "tag": None, "count": None,
            }))
        else:
            module, slots = resolve_slots(args)
        if args.question_type:
            if module != '政治理论' and args.question_type != 'single':
                raise ValueError('仅政治理论支持判断/多选专项')
            for slot in slots:
                slot.setdefault('question_type', args.question_type)
        if module == '政治理论':
            from policy_quiz import default_question_types
            layout = default_question_types(sum(slot['count'] for slot in slots))
            expanded, cursor = [], 0
            for slot in slots:
                for _ in range(slot['count']):
                    expanded.append({**slot, 'count': 1, 'question_type': slot.get('question_type') or layout[cursor]})
                    cursor += 1
            slots = expanded
        from kaofa_variants import assign_variants
        # B-2：变式分配种子与 batch_id 解耦——改用请求自身（module + 蓝图/标签配额）做稳定种子。
        # 这样换 batch_id（清理目录残留、失败重导）不再重排变式；同一请求重导时各题 kaofa_variant_name 保持一致。
        _variant_seed = json.dumps({"module": module, "slots": slots, "difficulty": args.difficulty},
                                   sort_keys=True, ensure_ascii=False)
        _variant_seed = hashlib.sha1(_variant_seed.encode('utf-8')).hexdigest()
        slots = assign_variants(module, slots, seed=_variant_seed, difficulty=args.difficulty)
        total = sum(int(slot["count"]) for slot in slots)
        if args.difficulty == 'auto' and module not in {'数量关系', '言语理解与表达', '判断推理', *SOURCE_MODULES}:
            raise ValueError('auto 难度目前仅用于数量关系、言语理解与表达、文字判断、政治理论和常识判断')
        if str(args.batch_id).startswith("daily-"):
            if total < 1 or total > DAILY_MAX_COUNT:
                raise SystemExit(f"每日复习卷题量必须是 1–{DAILY_MAX_COUNT}")
        elif total < 1 or total > MAX_COUNT:
            raise SystemExit(f"专项题量必须是 1–{MAX_COUNT}；成套卷走日练")
        for slot in slots:
            reject_unsupported(module, str(slot["tag"]))
            slot["difficulty"] = tier_of(
                {"module": module, "difficulty": args.difficulty}, slot,
            )
        today = local_today()
        batch_dir = args.output_dir / today.isoformat() / args.batch_id
        run = {
            "module": module,
            "batch_id": args.batch_id,
            "planned_count": total,
            "slots": slots,
            "difficulty": args.difficulty,
            "requested_scope": args.tag,
        }
        source = source_name(module, slots, today, args.difficulty)
        if module == "言语理解与表达":
            assign_vocab(slots, seed=f"{args.batch_id}:{_variant_seed}:{today.isoformat()}", db=args.db)
            run["yanyu_avoid"] = recent_yanyu_avoid(args.db)
        if args.plan_only:
            print(json.dumps({"status": "planned", "module": module, "slots": slots,
                              "count": total, "source": source}, ensure_ascii=False))
            return 0
        if args.dsh_claims:
            payload = json.loads(args.dsh_claims.read_text(encoding="utf-8"))
            raw_questions = payload.get("questions") if isinstance(payload, dict) else payload
            if not isinstance(raw_questions, list) or len(raw_questions) != total:
                raise ValueError(f"题目数量须为 {total}，实际 "
                                 f"{len(raw_questions) if isinstance(raw_questions, list) else 0}")
            per_item = expand_slots(slots)
            items = []
            for index, raw in enumerate(raw_questions):
                if not isinstance(raw, dict):
                    raise ValueError(f"第 {index + 1} 题不是对象")
                stamped_question = stamp(run, raw, index, per_item[index], source)
                claims = dsh_claims(run, stamped_question)
                item = {"question": str(index + 1),
                        "kaofa_variant_name": per_item[index].get("kaofa_variant_name") or "",
                        "claims": [{"claim_index": i, "claim": c} for i, c in enumerate(claims)]}
                if per_item[index].get("vocab_word"):
                    item["vocab_word"] = per_item[index]["vocab_word"]
                    item["vocab_brief"] = per_item[index].get("vocab_brief") or ""
                judged = formal_check(run, stamped_question)
                if judged:
                    item["formal"] = {key: judged.get(key) for key in ("verdict", "issues", "correct", "options", "models")}
                    item["fields"] = (["necessity_checks", "formal_ok", "formal_reason"] if judged["verdict"] == "PASS"
                                      else ["先按 formal.issues 改题，重跑 --dsh-claims 再派审"])
                items.append(item)
            fields = {"necessity_checks": "考官逐句判定，覆盖全部 claims"}
            if module in {'言语理解与表达', '判断推理'}:
                fields["usage_checks"] = "独立核查官（不看答案）逐句判定，覆盖全部 claims"
            if module == '判断推理':
                fields["question_check"] = "独立核查官：题面条件完整、答案唯一，reason 以 PASS 开头"
                fields["formal_ok"] = ("仅带 formal 且判定 PASS 的演绎题：考官核对 formal 忠实于题面，给 formal_ok 与 formal_reason；"
                                       "这类题免 usage_checks 与 question_check（以 items[].fields 为准）")
            print(json.dumps({"status": "claims", "module": module, "count": total,
                              "fields": fields, "items": items}, ensure_ascii=False))
            return 0
        if args.dsh_import:
            # 闸门复核失败的残留会归档，不再占用 batch_id；是否已入库由下方数据库检查把关。
            pass
        elif not args.dsh_check and batch_dir.exists() and any(batch_dir.iterdir()):
            raise ValueError("批次目录已有产物，不能覆盖旧证据；请使用新的 batch_id")
        if module in SOURCE_MODULES:
            run['source_pack'] = source_pack(slots, args.sources.split(',') if args.sources else None, args.as_of)
        conn = sqlite3.connect(args.db, timeout=30)
        try:
            exists = int(
                conn.execute(
                    "SELECT COUNT(*) FROM questions WHERE batch_id=?", (args.batch_id,)
                ).fetchone()[0]
            )
        finally:
            conn.close()
        if exists:
            raise RuntimeError(f"batch_id 已入库 {exists} 题，换一个序号")
        run["history"] = load_history(args.db, module, slots, args.batch_id)
        if args.dsh_check:
            from generation_gate import verify
            with tempfile.TemporaryDirectory(prefix="dsh-check-") as tmp:
                check_dir = Path(tmp) / args.batch_id
                questions, results, log = build_dsh_review(run, args.dsh_check, source)
                write_batch(run, check_dir, questions, source)
                sign(check_dir, run, results, log, model_label=run.get('dsh_auditor'))
                verify(check_dir)
            print(json.dumps({"status": "checked", "batch_id": args.batch_id, "passed": len(questions),
                              "count": total, "message": f"预检通过 {len(questions)}/{total} 题，"
                              "可用同一参数改 --dsh-import 正式入库"}, ensure_ascii=False))
            return 0
        from generation_progress import report

        def tick(**kwargs):
            nonlocal tracked, finished
            if finished:
                return
            tracked = True
            if kwargs.get("status") in ("done", "failed"):
                finished = True
            report(args.batch_id, module=module, title=source, planned=total, **kwargs)

        tick(stage="准备出题", detail=f"共 {total} 题", progress=2, passed=0, status="running")
        from quiz_scope import register_slots
        register_slots(slots, args.db)
        audit_token = MODEL_AUDIT_DIR.set(batch_dir / 'model-responses')
        try:
            if args.dsh_import:
                questions, results, log = build_dsh_review(run, args.dsh_import, source, progress=tick)
            else:
                questions, results, log = build_batch(run, max(1, args.rounds), source, batch_dir, progress=tick)
        finally:
            MODEL_AUDIT_DIR.reset(audit_token)
        # 复核与签发之间不许有任何东西再动 questions.json，否则证据对不上题面。
        tick(stage="签收", detail=f"已过审 {len(questions)}/{total}", passed=len(questions),
             progress=92, round_no=len(log), status="running")
        if args.dsh_import:
            # DSH 先在暂存目录签收并过闸门，通过后才落到正式批次目录。
            stage_dir = args.output_dir / ".dsh-staging" / args.batch_id
            if stage_dir.exists():
                shutil.rmtree(stage_dir)
        else:
            stage_dir = batch_dir
        write_batch(run, stage_dir, questions, source)
        sign(stage_dir, run, results, log,
             model_label=run.get('dsh_auditor') if args.dsh_import else None)
        from generation_gate import verify
        tick(stage="闸门", detail="正在核验收据", passed=len(questions), progress=95, status="running")
        verify(stage_dir)
        if stage_dir != batch_dir:
            if batch_dir.exists():
                archive_dsh_residue(args.output_dir, batch_dir)
            batch_dir.parent.mkdir(parents=True, exist_ok=True)
            stage_dir.rename(batch_dir)
            try:
                stage_dir.parent.rmdir()
            except OSError:
                pass
        if args.no_import:
            imported = 0
            tick(status="done", stage="已通过", detail=f"已出题 {len(questions)} 题，未入库",
                 passed=len(questions), progress=100)
        else:
            tick(stage="入库", detail="正在写入题库", passed=len(questions), progress=97, status="running")
            imported = import_batch(batch_dir, args.db)
            if imported:
                from kaofa_variants import record_variants
                record_variants(str(args.batch_id), slots,
                                question_ids=[f"{args.batch_id}_{i + 1:02d}" for i in range(len(questions))])
            tick(status="done", stage="已入库", detail=f"已入库 {imported} 题",
                 passed=len(questions), progress=100)
        print(
            json.dumps(
                {
                    "status": "success",
                    "batch_id": args.batch_id,
                    "imported": imported,
                    "batch_dir": str(batch_dir),
                    "slots": slots,
                    "actual_difficulty_counts": {
                        tier: sum(q['difficulty'] == level for q in questions)
                        for tier, level in TIER_TO_LEVEL.items()
                    },
                    "rounds": log,
                    "seconds": round(time.monotonic() - started, 1),
                    "message": f"已{'出题' if args.no_import else '入库'} {len(questions)} 题，"
                    f"批次 {args.batch_id}，耗时 {round(time.monotonic() - started)} 秒",
                },
                ensure_ascii=False,
            )
        )
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        if tracked and not finished:
            from generation_progress import report
            report(args.batch_id, status="failed", stage="失败", error=str(exc), detail=str(exc)[:160])
        stage_dir = args.output_dir / ".dsh-staging" / args.batch_id
        if args.dsh_import and stage_dir.exists():
            archive_dsh_residue(args.output_dir, stage_dir)
        print(
            json.dumps(
                {
                    "status": "error",
                    "batch_id": args.batch_id,
                    "batch_dir": str(batch_dir) if batch_dir is not None else None,
                    "error": str(exc)[:2000],
                    "seconds": round(time.monotonic() - started, 1),
                    "message": f"{'预检未通过' if args.dsh_check else '出题失败'}：{str(exc)[:600]}",
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

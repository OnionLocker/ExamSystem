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
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generation_gate import (LITE_VERSION, RECEIPT, QUANTITY_HARD_POLICY, VERBAL_PRACTICE_POLICY, POLICY_PRACTICE_POLICY, REASONING_PRACTICE_POLICY, current_hard_policy, digest,
                             lite_allowed_tiers, lite_necessity_claims, lite_reasoning_issues)
from normalize_ai_batch import scratchpad_leak
from quiz_scope import source_name, source_topic
from yanyu_variety import recent_yanyu_avoid, validate_yanyu_fills
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
from policy_sources import SOURCE_MODULES, source_pack

MODEL = "gemini-3.8-flash-high"
MAX_COUNT = 15
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
    '只输出 JSON：{"questions":[{"id":"...","actual_difficulty":"mid",'
    '"difficulty_reason":"具体解法与删条件对照...","analysis_check":"关键推导与反例检查...",'
    '"necessity_checks":[{"claim_index":0,"valid":true,"reason":"具体推导或反例"}],'
    '"verdict":"PASS","difficulty_ok":true,'
    '"kaodian_ok":true,"style_ok":true,"analysis_ok":true,"brief_ok":true,"issues":[]}]}\n'
    "五项全 true 才给 PASS；任一为 false 必须 REJECT，并在 issues 里写明具体哪一步错、怎么错的。"
)


def call(system: str, prompt: str, temperature: float, timeout: int, *,
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
            (audit_dir / f'{time.time_ns()}.json').write_text(
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
    # Only repair escaped prose line breaks; do not decode TeX such as \\neq or \\nu.
    for field in ("stem", "analysis", "explanation"):
        if isinstance(row.get(field), str):
            row[field] = re.sub(r"\\r\\n|\\n(?![A-Za-z])", "\n", row[field])
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


def review(run: dict, questions: list[dict], per_item: list[dict], batch_questions=None) -> dict[str, dict]:
    """独立作答与命题审核；言语对高风险用法断言另作核对。"""
    if not questions:
        return {}
    quantity = run['module'] == '数量关系'
    if run['module'] in {'数量关系', '言语理解与表达', '判断推理'} and len(questions) > 3:
        out = {}
        for start in range(0, len(questions), 3):
            out.update(review(run, questions[start:start + 3], per_item, batch_questions or questions))
        return out
    if run['module'] in SOURCE_MODULES:
        from policy_quiz import review as grounded_review
        return grounded_review(run, questions, per_item, batch_questions or questions,
                               call, public, local_issues, tier_of)
    if quantity:
        from quiz_quantity import BLIND, EXAMINER
    elif run['module'] == '言语理解与表达':
        from quiz_verbal import BLIND, EXAMINER
    elif run['module'] == '判断推理':
        from quiz_reasoning import BLIND, EXAMINER
    else:
        BLIND, EXAMINER = BLIND_SYSTEM, EXAMINER_SYSTEM
    blind_payload = json.dumps(
        {"questions": [public(q, with_answer=False) for q in questions]}, ensure_ascii=False
    )
    blind = indexed(call(BLIND, "逐题独立作答：\n" + blind_payload, 0.0, 300))
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
        examiner_items.append(
            {
                "question": public(question, with_answer=True),
                "declared_kaofa": tag,
                "declared_difficulty": tier_of(run, slot),
                "declared_brief": slot.get("brief", ""),
                "blind_work": blind.get(str(question["external_id"])),
                "necessity_claims": [{"claim_index": i, "claim": claim}
                                     for i, claim in enumerate(claims_by_id[str(question["external_id"])])],
            }
        )
        if run['module'] in {'数量关系', '言语理解与表达', '判断推理'}:
            # Each examiner reasons independently of the other reviewer's answer.
            examiner_items[-1].pop("blind_work")
        if quantity:
            examiner_items[-1]['sibling_topics'] = slot.get('sibling_topics', [])
    examiner_payload = json.dumps(
        {
            "items": examiner_items,
            "kaofa_canon": {tag: card for tag, card in cards.items() if card},
            "batch_slots": run.get("slots", []),
            "batch_questions": [public(q, with_answer=True) for q in (
                (batch_questions or questions) if not quantity or any(s.get('brief') for s in per_item) else questions)],
        },
        ensure_ascii=False,
    )
    examiner = indexed(call(EXAMINER, "逐题审核：\n" + examiner_payload, 0.0, 300))

    usage = {}
    if run['module'] in {'言语理解与表达', '判断推理'}:
        if run['module'] == '判断推理':
            from quiz_reasoning import CLAIMS as USAGE
        else:
            from quiz_verbal import USAGE
        claims = [{'id': f'{q["external_id"]}:{i}', 'claim': claim, 'context': q['stem'], 'options': q['options']}
                  for q in questions for i, claim in enumerate(claims_by_id[q['external_id']])]
        if claims:
            fields = {f'c{i}': claim for i, claim in enumerate(claims)}
            if run['module'] == '判断推理':
                fields.update({f'q{i}': {'id': q['external_id'], 'task': 'question_check',
                                       'context': q['stem'], 'options': q['options']}
                               for i, q in enumerate(questions)})
            schema = {'type': 'object', 'properties': {key: {
                'type': 'string', 'description': 'PASS或REJECT，后接该句具体依据或反例',
            } for key in fields}, 'required': list(fields), 'additionalProperties': False}
            checked = call(USAGE, json.dumps(fields, ensure_ascii=False), 0.0, 300,
                           schema=schema)
            usage = {claim['id']: {'id': claim['id'], 'valid': checked[key].startswith('PASS'),
                                  'reason': checked[key]} for key, claim in fields.items()}

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
        question_check = usage.get(qid) if run['module'] == '判断推理' else None
        if run['module'] == '判断推理' and (not question_check or question_check['valid'] is not True):
            issues.append('独立题面核查未通过：' + str((question_check or {}).get('reason') or '缺少核查'))
        if run['module'] in {'言语理解与表达', '判断推理'}:
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
                **({'question_check': question_check} if run['module'] == '判断推理' else {}),
                "verdict": str((examiner_item or {}).get("verdict") or "REJECT").upper(),
                "difficulty_ok": (examiner_item or {}).get("difficulty_ok"),
                "kaodian_ok": (examiner_item or {}).get("kaodian_ok"),
                "style_ok": (examiner_item or {}).get("style_ok"),
                "analysis_ok": (examiner_item or {}).get("analysis_ok"),
                "brief_ok": (examiner_item or {}).get("brief_ok"),
                "issues": [str(item)[:300] for item in (examiner_item or {}).get("issues") or []],
            },
            "issues": issues,
        }
    return out


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
                json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        draft = {"questions": []}
        attempt_record = {"round": attempt, "items": asks, "draft": draft, "groups": []}
        group_size = 3 if run['module'] in {'数量关系', '判断推理', *SOURCE_MODULES} else 2 if run['module'] == '言语理解与表达' else len(asks)
        strict_indices = run['module'] in {'数量关系', '言语理解与表达', '判断推理', *SOURCE_MODULES}
        for start in range(0, len(asks), group_size):
            group = asks[start:start + group_size]
            prior = kept + [str(q.get('stem') or '') for q in draft['questions'] if isinstance(q, dict)]
            writer_options = {}
            if run['module'] == '数量关系':
                from quiz_quantity import WRITER_SCHEMA
                writer_options['schema'] = WRITER_SCHEMA
            elif run['module'] == '判断推理':
                from quiz_reasoning import WRITER_SCHEMA
                writer_options['schema'] = WRITER_SCHEMA
            drafted = passed_count()
            first, last = group[0]["index"], group[-1]["index"]
            span = str(first) if first == last else f"{first}–{last}"
            note(stage="命题", detail=f"第{attempt}轮 · 正在出第 {span} 题",
                 passed=drafted, round_no=attempt, status="running",
                 progress=min(85, drafted * 85 // total) if total else 0)
            response = call(WRITER_SYSTEM, writer_prompt(run, group, prior), 0.5, 600, **writer_options)
            produced_group = [q for q in response.get('questions') or [] if isinstance(q, dict)]
            requested, candidates = {ask['index'] for ask in group}, []
            for position, raw in enumerate(produced_group):
                # Missing indices fall back within this group, never to the first global slots.
                index = item_index(raw)
                if index == 0 and position < len(group):
                    index = group[position]['index']
                if strict_indices and index not in requested:
                    continue
                candidates.append({**raw, 'index': index})
            indices = [item['index'] for item in candidates]
            draft['questions'].extend(item for item in candidates
                                      if not strict_indices or indices.count(item['index']) == 1)
            attempt_record['groups'].append({'items': group, 'response': response})
            if audit_dir is not None:
                (audit_dir / f"attempt-{attempt}.json").write_text(
                    json.dumps(attempt_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        produced = [item for item in draft.get("questions") or [] if isinstance(item, dict)]
        fresh: list[dict] = []
        rejected = []
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
            if duplicate_question(question, others):
                reasons.append("与本批次已有题目撞题，换情境与数据重出")
            if reasons:
                feedback[index] = reasons
                rejected.append({"question_id": str(question["external_id"]), "issues": reasons})
                continue
            slots[index] = question
            fresh.append(question)

        if fresh and run["module"] == "言语理解与表达":
            try:
                validate_yanyu_fills([value for value in slots if value])
            except ValueError as exc:
                reason = str(exc)
                for question in fresh:
                    index = int(str(question["external_id"]).rsplit("_", 1)[1]) - 1
                    slots[index] = None
                    feedback[index] = [reason]
                    rejected.append({"question_id": str(question["external_id"]), "issues": [reason]})
                fresh = []

        current = [value for value in slots if value]
        # 批次要求可能依赖别题；换题后同时重审保留题，避免沿用旧组合的结论。
        reviewed = current if fresh and any(slot.get("brief") for slot in per_item) else fresh
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
                        and (run['module'] != '判断推理' or (examiner.get('question_check') or {}).get('valid') is True)
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
                "answer_max_per_letter": max(counts.values()) if counts else 1,
                "answer_min_letters": len(counts),
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


def sign(batch_dir: Path, run: dict, results: dict[str, dict], log: list[dict]) -> None:
    """写逐题复核证据并签发精简收据，import-batch 仍然要校验它。"""
    questions = json.loads((batch_dir / "questions.json").read_text(encoding="utf-8"))
    ids = [str(question["external_id"]) for question in questions]
    evidence = {
        "version": 9 if run['module'] == '判断推理' else 8 if run['module'] in SOURCE_MODULES else 7 if run['module'] == '言语理解与表达' else 3,
        "kind": "examsystem-lite-review",
        "batch_id": run["batch_id"],
        "model": MODEL,
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
        evidence['usage_model'] = MODEL
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
            "model": MODEL,
        },
    }
    (batch_dir / RECEIPT).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def import_batch(batch_dir: Path, db_path: Path) -> int:
    env = {**os.environ, "EXAM_DB": str(db_path)}
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "import-batch.mjs"), str(batch_dir)],
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
    parser.add_argument("--difficulty", choices=["easy", "mid", "hard", "auto"])
    parser.add_argument("--rounds", type=int, default=3, help="最多几轮补题，默认 3")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "hermes-batches")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--no-import", action="store_true", help="只出题签收据，不写库")
    parser.add_argument("--plan-only", action="store_true", help="只输出考点、配额和难度，不出题、不注册、不入库")
    parser.add_argument('--sources', help='政治/常识权威资料 ID，逗号分隔；默认按标签匹配')
    parser.add_argument('--as-of', help='资料截止日期 YYYY-MM-DD，默认今天')
    parser.add_argument('--question-type', choices=['single', 'multi', 'judge'], help='政治单考点可指定题型')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["EXAM_DB"] = str(args.db)
    started = time.monotonic()
    batch_dir = None
    tracked = False
    finished = False
    try:
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
        total = sum(int(slot["count"]) for slot in slots)
        if args.difficulty == 'auto' and module not in {'数量关系', '言语理解与表达', '判断推理', *SOURCE_MODULES}:
            raise ValueError('auto 难度目前仅用于数量关系、言语理解与表达、文字判断、政治理论和常识判断')
        if total < 1 or total > MAX_COUNT:
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
        if args.plan_only:
            print(json.dumps({"status": "planned", "module": module, "slots": slots,
                              "count": total, "source": source}, ensure_ascii=False))
            return 0
        if batch_dir.exists() and any(batch_dir.iterdir()):
            raise ValueError("批次目录已有产物，不能覆盖旧证据；请使用新的 batch_id")
        if module in SOURCE_MODULES:
            run['source_pack'] = source_pack(slots, args.sources.split(',') if args.sources else None, args.as_of)
        if module == "言语理解与表达":
            run["yanyu_avoid"] = recent_yanyu_avoid(args.db)
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
            questions, results, log = build_batch(run, max(1, args.rounds), source, batch_dir, progress=tick)
        finally:
            MODEL_AUDIT_DIR.reset(audit_token)
        # 复核与签发之间不许有任何东西再动 questions.json，否则证据对不上题面。
        tick(stage="签收", detail=f"已过审 {len(questions)}/{total}", passed=len(questions),
             progress=92, round_no=len(log), status="running")
        write_batch(run, batch_dir, questions, source)
        sign(batch_dir, run, results, log)
        from generation_gate import verify
        tick(stage="闸门", detail="正在核验收据", passed=len(questions), progress=95, status="running")
        verify(batch_dir)
        if args.no_import:
            imported = 0
            tick(status="done", stage="已通过", detail=f"已出题 {len(questions)} 题，未入库",
                 passed=len(questions), progress=100)
        else:
            tick(stage="入库", detail="正在写入题库", passed=len(questions), progress=97, status="running")
            imported = import_batch(batch_dir, args.db)
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
        print(
            json.dumps(
                {
                    "status": "error",
                    "batch_id": args.batch_id,
                    "batch_dir": str(batch_dir) if batch_dir is not None else None,
                    "error": str(exc)[:2000],
                    "seconds": round(time.monotonic() - started, 1),
                    "message": f"出题失败：{str(exc)[:600]}",
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes 轻量专项出题：一次出稿 + 盲解官/考官并行双审 → 只重出不合格的题 → 入库。

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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fenbi_taxonomy import parse_fenbi_tag
from generation_gate import LITE_VERSION, RECEIPT, digest
from normalize_ai_batch import scratchpad_leak
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
from spoken_quiz_intent import slug_of
from policy_sources import SOURCE_MODULES, source_pack

MODEL = os.environ.get("QUIZ_LITE_MODEL", "gemini-3.8-flash-high")
HTTP_RETRIES = 3
MAX_COUNT = 15
DUP_RATIO = 0.82
# 选项开头的数值：整数、小数，或 5/16 这样的分数。带单位的「23个」也认。
OPTION_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?")
# 题库的 difficulty 是 1–5 的整数，主体落在 2–4。声明档位按槽位换算，
# 不收模型自己写的 difficulty——它会直接把 "easy" 这种字符串塞进来。
TIER_TO_LEVEL = {"easy": 2, "mid": 3, "hard": 4}

WRITER_SYSTEM = (
    "你是广东省考行测命题人。只输出一个 JSON 对象，不要 markdown 围栏，不要任何解释文字。"
)

BLIND_SYSTEM = (
    "你是独立做题人。你看不到出题人的答案与解析，必须自己把题解出来。\n"
    "解完之后，再逐个选项回头检查：除了你选的那个，还有没有别的选项也站得住。\n"
    '只输出 JSON：{"questions":[{"id":"...","answer":"A","steps":"...",'
    '"also_valid":[],"unsolvable":false,"reason":"..."}]}\n'
    "answer 必须是你自己算出来的那一项，不要猜、不要凑。\n"
    "steps 要写出每一步的算式和数值结果，含取整方向（向上/向下），禁止跳步心算。\n"
    "also_valid 列出除 answer 之外同样成立的选项字母，没有就给空数组。\n"
    "若题干条件不足、自相矛盾，或四个选项里没有正确答案，unsolvable 置 true 并在 reason 说明。"
)

EXAMINER_SYSTEM = (
    "你是广东省考行测命题审核官，能看到答案与解析。逐题只判四件事：\n"
    "difficulty_ok：难度是否匹配声明的档位。easy 是一两步直问；mid 多一层转化；"
    "hard 是表述变形或多重约束，但仍必须是同一个考点，不许换成偏题怪题。\n"
    "kaodian_ok：是否100%严格落在指定考法的固定识别与考场步骤上！"
    "严禁任何考法发散或串台（例如考古典定位法却出现了赛制或独立关卡，直接判 false 毙掉）。\n"
    "style_ok：题干情境、设问方式、选项设置、篇幅是否像广东省考真题，"
    "不是奥数题、不是教材例题、不是脑筋急转弯。\n"
    "analysis_ok：解析每一步是否可复算，最后结论是否确实等于键定选项；算式与数值必须自洽。\n"
    "brief_ok：逐题满足 declared_brief 的额外命题要求；跨题配额按 batch_slots 和整批题核对。无额外要求则为 true。\n"
    '只输出 JSON：{"questions":[{"id":"...","verdict":"PASS","difficulty_ok":true,'
    '"kaodian_ok":true,"style_ok":true,"analysis_ok":true,"brief_ok":true,"issues":[]}]}\n'
    "五项全 true 才给 PASS；任一为 false 必须 REJECT，并在 issues 里写明具体哪一步错、怎么错的。"
)


def call(system: str, prompt: str, temperature: float, timeout: int) -> dict:
    body = json.dumps(
        {
            "model": MODEL,
            "temperature": temperature,
            "max_tokens": 16384,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    last = ""
    for attempt in range(HTTP_RETRIES):
        try:
            request = urllib.request.Request(
                f"{BASE_URL}/chat/completions",
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key()}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return parse_json((payload["choices"][0]["message"].get("content") or "").strip())
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < HTTP_RETRIES:
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(last)


def indexed(payload: dict) -> dict[str, dict]:
    out = {}
    for item in payload.get("questions") or []:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


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
    if run["module"] == "言语理解与表达":
        lines += [
            "- 言语题必须严格命中 item 的 tag。额外输出 kaodian_signal，写明本题实际使用的识别动作和题型；"
            "指定逻辑填空必须有空格，指定语句排序必须真问排序，指定标题/细节/接语必须体现对应动作。"
            "不得把难的考点改写成中心理解题。",
            "- 言语题主题、领域、语体、开篇必须换（说明、叙事、对话、实验记录、文化科普均可），"
            "不得只换皮或复用同一句法骨架；同批题干开篇和骨架不能明显重复。",
            "- 成语填空必须有空且四个选项均为成语；语句排序必须给出句子并真问排序；细节判断必须按原文细节正误判断。",
            "- 不得因为某考点较难或素材不好写而换成相邻简单考点；无法满足指定考法时输出 unsuitable:true，"
            "该题会被退回重出，不得伪装成另一题型。",
            f"近期言语禁用模具与开篇：{json.dumps(run.get('yanyu_avoid') or {}, ensure_ascii=False)}",
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


def tier_of(run: dict, slot: dict) -> str:
    value = slot.get("difficulty") or run.get("difficulty")
    return value if value in TIER_TO_LEVEL else "mid"


def source_difficulty_label(batch_id: str, cli_diff, slots: list) -> str | None:
    """卡片标题用的难度后缀。混档给 ladder，不拿第一槽当整批名字。"""
    inferred = next((token for token in ("easy", "mid", "hard")
                     if f"_{token}_" in batch_id or batch_id.endswith(f"_{token}")), "mid")
    slot_diffs = [str(slot.get("difficulty") or cli_diff or inferred) for slot in slots]
    uniq = list(dict.fromkeys(slot_diffs))
    if len(uniq) > 1:
        return "ladder"
    bid = str(batch_id or "")
    if "_ladder_" in bid or bid.endswith("_ladder"):
        return "ladder"
    if uniq:
        return uniq[0]
    if cli_diff:
        return str(cli_diff)
    for token in ("easy", "mid", "hard"):
        if f"_{token}_" in bid or bid.endswith(f"_{token}"):
            return token
    return "mid"


def packed_options(text: str) -> list[dict]:
    matches = list(re.finditer(r"(?:^|\s)([ABCD])[\.、:：]\s*(.*?)(?=\s+[ABCD][\.、:：]|$)", text or ""))
    return [{"key": match.group(1), "text": match.group(2).strip()} for match in matches]


def normalize_writer_shape(raw: dict) -> dict:
    """Accept harmless field/option formatting drift; leave semantic defects for local_issues."""
    row = dict(raw)
    if not str(row.get("stem") or "").strip() and row.get("question"):
        row["stem"] = row.get("question")
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
    """盲解官与考官并行各跑一次，返回逐题结论。"""
    if not questions:
        return {}
    if run['module'] in SOURCE_MODULES:
        from policy_quiz import review as grounded_review
        return grounded_review(run, questions, per_item, batch_questions or questions,
                               call, public, local_issues, tier_of)
    blind_payload = json.dumps(
        {"questions": [public(q, with_answer=False) for q in questions]}, ensure_ascii=False
    )
    cards: dict[str, str] = {}
    examiner_items = []
    for question in questions:
        index = int(str(question["external_id"]).rsplit("_", 1)[1]) - 1
        slot = per_item[index]
        tag = str(slot["tag"])
        if tag not in cards:
            cards[tag] = run_canon_card(run, tag)
        examiner_items.append(
            {
                "question": public(question, with_answer=True),
                "declared_kaofa": tag,
                "declared_difficulty": tier_of(run, slot),
                "declared_brief": slot.get("brief", ""),
            }
        )
    examiner_payload = json.dumps(
        {
            "items": examiner_items,
            "kaofa_canon": {tag: card for tag, card in cards.items() if card},
            "batch_slots": run.get("slots", []),
            "batch_questions": [public(q, with_answer=True) for q in (batch_questions or questions)],
        },
        ensure_ascii=False,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        blind_future = pool.submit(
            call, BLIND_SYSTEM, "逐题独立作答：\n" + blind_payload, 0.0, 300
        )
        examiner_future = pool.submit(
            call, EXAMINER_SYSTEM, "逐题审核：\n" + examiner_payload, 0.0, 300
        )
        blind = indexed(blind_future.result())
        examiner = indexed(examiner_future.result())

    out = {}
    for question in questions:
        qid = str(question["external_id"])
        answer = str(question.get("answer") or "")
        issues = local_issues(question)
        blind_item = blind.get(qid)
        examiner_item = examiner.get(qid)
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


def build_batch(run: dict, rounds: int, source: str) -> tuple[list[dict], dict, list[dict]]:
    """出稿 → 双审 → 只重出不合格的题。返回题目、逐题证据、每轮记录。"""
    total = int(run["planned_count"])
    per_item = expand_slots(run["slots"])
    slots: list[dict | None] = [None] * total
    results: dict[str, dict] = {}
    feedback: dict[int, list[str]] = {}
    log = []

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
            asks.append(ask)
        kept = [str(value.get("stem") or "") for value in slots if value]
        started = time.monotonic()
        draft = call(WRITER_SYSTEM, writer_prompt(run, asks, kept), 0.5, 600)

        produced = [item for item in draft.get("questions") or [] if isinstance(item, dict)]
        fresh: list[dict] = []
        rejected = []
        for position, index in enumerate(todo):
            raw = next(
                (item for item in produced if item_index(item) == index + 1),
                produced[position] if position < len(produced) else None,
            )
            if raw is None:
                continue
            question = stamp(run, raw, index, per_item[index], source)
            others = [str(value.get("stem") or "") for value in slots if value]
            others += [str(value.get("stem") or "") for value in fresh]
            # 结构问题和撞题都不花审核调用，当场退回。
            reasons = local_issues(question)
            if duplicate_stem(str(question.get("stem") or ""), others):
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
        round_results = review(run, reviewed, per_item, current)
        results.update(round_results)
        for question in reviewed:
            qid = str(question["external_id"])
            if round_results[qid]["verdict"] == "PASS":
                continue
            index = int(qid.rsplit("_", 1)[1]) - 1
            slots[index] = None
            feedback[index] = round_results[qid]["issues"]
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
        "difficulty_tier": run.get("difficulty")
        or source_difficulty_label(run.get("batch_id") or "", None, run.get("slots") or [])
        or "mid",
        "generation": {
            "style_marker": "GONGKAO-STYLE-v1",
            "pipeline": "quiz_lite",
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
                    {key: value for key, value in slot.items() if value not in (None, "")}
                    for slot in run["slots"]
                ],
            },
            "generation_contexts": [],
            "evaluation_contexts": [],
        },
    }
    if run['module'] in SOURCE_MODULES:
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
        "version": 1,
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
    parser.add_argument("--difficulty", choices=["easy", "mid", "hard"])
    parser.add_argument("--rounds", type=int, default=3, help="最多几轮补题，默认 3")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "hermes-batches")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--no-import", action="store_true", help="只出题签收据，不写库")
    parser.add_argument('--sources', help='政治/常识权威资料 ID，逗号分隔；默认按标签匹配')
    parser.add_argument('--as-of', help='资料截止日期 YYYY-MM-DD，默认今天')
    parser.add_argument('--question-type', choices=['single', 'multi', 'judge'], help='政治单考点可指定题型')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["EXAM_DB"] = str(args.db)
    started = time.monotonic()
    try:
        if args.module in SOURCE_MODULES and not args.tag and not args.blueprint:
            from policy_quiz import module_slots
            module = args.module
            count = args.count if args.count is not None else (10 if module == '政治理论' else 5)
            if not 1 <= count <= MAX_COUNT:
                raise ValueError('题量须为1–15')
            slots = module_slots(module, count, args.difficulty)
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
        if total < 1 or total > MAX_COUNT:
            raise SystemExit(f"专项题量必须是 1–{MAX_COUNT}；成套卷走日练")
        for slot in slots:
            reject_unsupported(module, str(slot["tag"]))
        today = local_today()
        run = {
            "module": module,
            "batch_id": args.batch_id,
            "planned_count": total,
            "slots": slots,
            "difficulty": args.difficulty,
        }
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

        tag_str = str(slots[0]["tag"])
        parsed_tag = parse_fenbi_tag(tag_str)
        if parsed_tag and parsed_tag[3]:
            # L4 子考法：模块-二级知识点-子考法
            topic = f"{parsed_tag[2]}-{parsed_tag[3]}"
        else:
            topic = slug_of(slots[0]["tag"])
            if topic == "专项":
                topic = tag_str.split("-")[-1]
        diff = source_difficulty_label(args.batch_id, getattr(args, "difficulty", None), slots)
        if diff in TIER_TO_LEVEL:
            run["difficulty"] = diff
        diff_suffix = f"-{diff}" if diff else ""
        source = f"广东省考行测-{module}-{topic}{diff_suffix}-{today:%Y%m%d}"
        batch_dir = args.output_dir / today.isoformat() / args.batch_id

        questions, results, log = build_batch(run, max(1, args.rounds), source)
        # 复核与签发之间不许有任何东西再动 questions.json，否则证据对不上题面。
        write_batch(run, batch_dir, questions, source)
        sign(batch_dir, run, results, log)
        from generation_gate import verify
        verify(batch_dir)
        imported = 0 if args.no_import else import_batch(batch_dir, args.db)
        print(
            json.dumps(
                {
                    "status": "success",
                    "batch_id": args.batch_id,
                    "imported": imported,
                    "batch_dir": str(batch_dir),
                    "slots": slots,
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
        print(
            json.dumps(
                {
                    "status": "error",
                    "batch_id": args.batch_id,
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

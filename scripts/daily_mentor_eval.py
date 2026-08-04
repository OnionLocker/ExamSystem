#!/usr/bin/env python3
"""每日 Hermes 对话 → ExamSystem 热力图。

规则：只有被判定为「真实公考学习内容」的交流才写入 study_log / 加热力。
闲聊、问候、系统折腾、只收计划不学 → 不加分。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

HERMES_DB = os.path.expanduser("~/.hermes/state.db")
EXAM_DB = "/home/ubuntu/ExamSystem/data/exam.db"
REPORTS_DIR = "/home/ubuntu/ExamSystem/data/reports"

# 评委模型的凭据不写进仓库，也不再单独维护一份。
#
# 最早这里硬编码了 URL + key，随 a843437 推到公开仓库，任何人都能匿名取到，
# 而 Hermes 用的是同一把 key，被打爆后 429 会连带把主模型打进 1 小时冷却。
# 改成读环境变量之后又出了第二个问题：Hermes 换成本地代理，这边没人同步，
# 脚本连着三天拿 401，而失败只落在 cron 日志里，热力图就静悄悄断了。
#
# 现在直接读 Hermes 的 config.yaml：它自己能跑通，评委就一定能跑通。
HERMES_CONFIG = os.path.expanduser("~/.hermes/config.yaml")
MODEL_NAME = os.environ.get("MENTOR_EVAL_MODEL", "gemini-3.5-flash-low")


def load_judge_endpoint():
    """评委模型复用 Hermes 自己那条通道。

    以前这里单独存一份 URL + key：Hermes 换成本地代理之后没人同步这边，
    脚本连着好几天拿 401，可失败只落在 cron 日志里，热力图就这么静悄悄断了。
    改成直接读 Hermes 的 config.yaml —— 它自己能跑通，评委就一定能跑通。
    环境变量只在配置里读不到时兜底。
    """
    url = os.environ.get("CLIPROXY_URL", "")
    key = os.environ.get("CLIPROXY_API_KEY", "")
    try:
        import yaml

        with open(HERMES_CONFIG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        prov = (cfg.get("providers") or {}).get("cliproxy") or {}
        base = str(prov.get("base_url") or "").rstrip("/")
        if base:
            url = base + "/chat/completions"
        if prov.get("api_key"):
            key = str(prov["api_key"])
    except Exception as e:
        print(f"读取 Hermes 配置失败，回退到环境变量: {e}", file=sys.stderr)
    return url, key


TZ = timezone(timedelta(hours=8))
MAX_MSG_CHARS = 1200
MAX_LOG_CHARS = 28000


def get_today_time_range():
    now = datetime.now(TZ)
    start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=TZ)
    end = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=TZ)
    return start.timestamp(), end.timestamp(), now.strftime("%Y-%m-%d")


def _clip(text: str, limit: int = MAX_MSG_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…(已截断)…"


def fetch_today_messages(start_ts, end_ts):
    if not os.path.exists(HERMES_DB):
        print(f"Hermes state.db not found at {HERMES_DB}", file=sys.stderr)
        return []
    conn = sqlite3.connect(HERMES_DB)
    try:
        rows = conn.execute(
            """
            SELECT role, content, timestamp
            FROM messages
            WHERE timestamp >= ? AND timestamp <= ?
              AND role IN ('user', 'assistant')
            ORDER BY timestamp ASC
            """,
            (start_ts, end_ts),
        ).fetchall()
    finally:
        conn.close()

    out = []
    for role, content, ts in rows:
        content = (content or "").strip()
        if not content:
            continue
        # 跳过明显的自动化脚本提示，避免污染评判
        if role == "user" and content.strip() in {
            "Run daily mentor eval script.",
            "run daily mentor eval script.",
        }:
            continue
        out.append({"role": role, "content": content, "ts": ts})
    return out


def query_gemini_evaluation(messages):
    import urllib.request

    chat_parts = []
    for m in messages:
        label = "学员" if m["role"] == "user" else "导师"
        chat_parts.append(f"{label}: {_clip(m['content'])}")
    chat_log_str = "\n\n".join(chat_parts)
    if len(chat_log_str) > MAX_LOG_CHARS:
        chat_log_str = chat_log_str[-MAX_LOG_CHARS:]

    prompt = f"""
你是广东省考备考的「学习有效性裁判」，同时兼任严厉导师。
任务：判断今天学员与 Hermes 导师的对话里，是否存在**真实公考学习内容**；只有有效学习才给热力分。

--- 对话日志开始 ---
{chat_log_str}
--- 对话日志结束 ---

【什么算有效学习 valid_study=true】必须出现至少一类实质内容：
1. 具体题目讲解/对答案/错题归因（数量、资料、言语、判断、常识、科学推理等）
2. 申论：审题、提纲、段落批改、规范表述点评（不是空聊“今天写申论吗”）
3. 知识点精讲、公式/技巧拆解、字形间架/书写训练的具体反馈
4. 刷题复盘：明确题量、正误、薄弱点，并有针对性改进
5. 学员带着材料/PDF/截图/题干在学，导师在教

【什么算无效 valid_study=false → score 必须为 0，不得加热力图】
- 打招呼、闲聊、吐槽、心情、天气、吃什么
- 只问“在吗/今晚干啥/系统好用吗”
- 只收到每日计划推送，或只回 ✅/❌/收到，没有真正学
- 讨论 ExamSystem/Hermes/代码/打卡机制本身、修 bug、加功能
- 空泛说“要加油/明天开始学”，没有任何题目或知识点内容
- 自动化脚本、工具调用日志、与备考无关的技术话题

【给分（仅当 valid_study=true）】
- 12–22：有少量实质学习（1–2 题/一小段知识点），互动浅
- 23–35：多题或成块知识点辅导，有明确产出
- 36–50：深度批改/复杂推理/系统复盘，改进计划具体
分数只能是整数；无效学习必须 score=0、minutes=0。

只输出纯 JSON（不要 markdown 代码块），字段如下：
{{
  "valid_study": false,
  "reason": "一句话说明为何有效或无效",
  "summary": "若有效：15–40字学习摘要；若无效：写「今日无有效学习」",
  "score": 0,
  "minutes": 0,
  "study_topics": [],
  "evidence": ["从日志摘1–3条支撑判定的短证据，无效可为空数组"],
  "report": "Markdown 短评：1)判定结论 2)今日内容 3)若无效说明为何不加热力；若有效给薄弱点与明日任务。语气简洁严厉。"
}}
"""

    url, key = load_judge_endpoint()
    if not key:
        print(
            "judge endpoint has no api_key — refusing to call the judge.\n"
            "  Put it in ~/.hermes/.env as CLIPROXY_API_KEY=<key> (chmod 600).",
            file=sys.stderr,
        )
        return None

    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content.rsplit("\n", 1)[0]
            content = content.strip()
        # 容错：有时模型包一层文字
        if not content.startswith("{"):
            l = content.find("{")
            r = content.rfind("}")
            if l >= 0 and r > l:
                content = content[l : r + 1]
        return json.loads(content)
    except Exception as e:
        print(f"Error querying cliproxy: {e}", file=sys.stderr)
        return None


def _load_log(cursor):
    cursor.execute("SELECT v FROM user_kv WHERE k = 'study_log_v1'")
    row = cursor.fetchone()
    if not row:
        return []
    try:
        data = json.loads(row[0])
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Error parsing study_log_v1: {e}", file=sys.stderr)
        return []


def _strip_today_chat(log_list, date_str):
    kept = []
    removed = 0
    for item in log_list:
        item_ts = item.get("ts", 0) / 1000.0
        try:
            item_date = datetime.fromtimestamp(item_ts, TZ).strftime("%Y-%m-%d")
        except Exception:
            kept.append(item)
            continue
        if item.get("type") == "chat" and item_date == date_str:
            removed += 1
            continue
        kept.append(item)
    return kept, removed


def _save_log(cursor, log_list):
    v_str = json.dumps(log_list, ensure_ascii=False)
    cursor.execute(
        """
        INSERT INTO user_kv (k, v, updated_at)
        VALUES ('study_log_v1', ?, datetime('now'))
        ON CONFLICT(k) DO UPDATE SET
          v = excluded.v,
          updated_at = datetime('now')
        """,
        (v_str,),
    )


def clear_today_chat_heat(date_str):
    """无效学习时：清掉当日 chat 热力（若有）。"""
    if not os.path.exists(EXAM_DB):
        print(f"Exam db not found at {EXAM_DB}", file=sys.stderr)
        return False
    conn = sqlite3.connect(EXAM_DB)
    try:
        cursor = conn.cursor()
        log_list = _load_log(cursor)
        new_list, removed = _strip_today_chat(log_list, date_str)
        if removed:
            _save_log(cursor, new_list)
            conn.commit()
            print(f"Cleared {removed} chat heat entr(y/ies) for {date_str}.", file=sys.stderr)
        else:
            print(f"No chat heat to clear for {date_str}.", file=sys.stderr)
        return True
    finally:
        conn.close()


def update_study_log(date_str, summary, score, minutes, topics=None):
    if not os.path.exists(EXAM_DB):
        print(f"Exam db not found at {EXAM_DB}", file=sys.stderr)
        return False

    score = int(score or 0)
    minutes = int(minutes or 0)
    if score <= 0:
        return clear_today_chat_heat(date_str)

    conn = sqlite3.connect(EXAM_DB)
    try:
        cursor = conn.cursor()
        log_list = _load_log(cursor)
        new_log_list, _ = _strip_today_chat(log_list, date_str)

        now_ms = int(time.time() * 1000)
        topic_hint = ""
        if topics:
            topic_hint = " · " + "/".join(str(t) for t in topics[:4])
        new_entry = {
            "id": now_ms + int(time.time() % 100),
            "ts": now_ms,
            "type": "chat",
            "module": f"导师辅导: {summary}{topic_hint}",
            "score": score,
            "minutes": max(0, minutes),
            "valid_study": True,
        }
        new_log_list.insert(0, new_entry)
        _save_log(cursor, new_log_list)
        conn.commit()
        print(
            f"Wrote valid chat heat. Score: +{score}, Minutes: {minutes}",
            file=sys.stderr,
        )
        return True
    finally:
        conn.close()


def save_report(date_str, report_content):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"{date_str}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content or "")
    print(f"Report saved to {report_path}", file=sys.stderr)


def normalize_eval(result: dict) -> dict:
    """强制无效学习归零，防止模型嘴上 false 手里仍给分。"""
    valid = bool(result.get("valid_study"))
    try:
        score = int(result.get("score") or 0)
    except Exception:
        score = 0
    try:
        minutes = int(result.get("minutes") or 0)
    except Exception:
        minutes = 0

    if not valid:
        score = 0
        minutes = 0
        summary = result.get("summary") or "今日无有效学习"
    else:
        # 有效学习也设下限，避免 1 分噪声；但允许裁判给较低分
        if score < 12:
            # 模型标了有效却给超低分：当作无效，宁缺毋滥
            valid = False
            score = 0
            minutes = 0
            summary = "今日学习证据不足，不计入热力"
            result["reason"] = (result.get("reason") or "") + "（有效性不足，已降为不计分）"
        else:
            score = max(12, min(50, score))
            minutes = max(5, min(180, minutes))
            summary = result.get("summary") or "公考辅导互动"

    result["valid_study"] = valid
    result["score"] = score
    result["minutes"] = minutes
    result["summary"] = summary
    if not isinstance(result.get("study_topics"), list):
        result["study_topics"] = []
    return result


def main():
    start_ts, end_ts, date_str = get_today_time_range()
    print(f"Running mentor eval for {date_str}...", file=sys.stderr)

    messages = fetch_today_messages(start_ts, end_ts)
    if not messages:
        print(f"No chat messages found for {date_str}. Skipping.", file=sys.stderr)
        clear_today_chat_heat(date_str)
        msg = f"""📋 【{date_str} 导师今日评估报告】
━━━━━━━━━━━━━━━━━━━━━━━━━━
❄️ 今日无 Hermes 交流，不加热力图。"""
        print(msg)
        return 0

    user_msgs = [m for m in messages if m["role"] == "user"]
    print(
        f"Found {len(messages)} messages ({len(user_msgs)} from user). Evaluating...",
        file=sys.stderr,
    )

    eval_result = query_gemini_evaluation(messages)
    if not eval_result:
        # 评委叫不通时也要留下痕迹：之前这里直接 return 1，报告不写、热力不动，
        # 结果连着三天没人发现评委的 key 已经废了。
        save_report(
            date_str,
            f"# {date_str} 导师评估\n\n"
            "- 评估失败：评委模型没能给出结果（看 cron 日志里的具体报错）\n"
            "- 今日热力未改动，既没加也没清\n",
        )
        print("Failed to get evaluation from the judge model.", file=sys.stderr)
        return 1

    eval_result = normalize_eval(eval_result)
    valid = eval_result["valid_study"]
    summary = eval_result["summary"]
    score = eval_result["score"]
    minutes = eval_result["minutes"]
    report = eval_result.get("report") or ""
    reason = eval_result.get("reason") or ""
    topics = eval_result.get("study_topics") or []

    print(f"valid_study={valid} reason={reason}", file=sys.stderr)
    print(f"Summary: {summary}", file=sys.stderr)
    print(f"Score: {score}", file=sys.stderr)
    print(f"Minutes: {minutes}", file=sys.stderr)

    # 无论有效无效都写报告；只有有效才写入热力
    report_full = (
        f"# {date_str} 导师评估\n\n"
        f"- valid_study: {valid}\n"
        f"- reason: {reason}\n"
        f"- score: {score}\n"
        f"- minutes: {minutes}\n"
        f"- topics: {', '.join(topics) if topics else '—'}\n\n"
        f"{report}\n"
    )
    save_report(date_str, report_full)

    if valid and score > 0:
        ok = update_study_log(date_str, summary, score, minutes, topics)
        heat_line = f"🔥 今日学习得分：+{score} 分 (预估有效学习 {minutes} 分钟)"
    else:
        ok = clear_today_chat_heat(date_str)
        heat_line = f"❄️ 未计入热力图（无效/闲聊）\n原因：{reason or '无实质公考学习内容'}"

    if not ok:
        print("Failed to update database.", file=sys.stderr)
        return 1

    user_facing_msg = f"""📋 【{date_str} 导师今日评估报告】
━━━━━━━━━━━━━━━━━━━━━━━━━━
{heat_line}
📝 交流概要：{summary}

{report}"""
    print(user_facing_msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())

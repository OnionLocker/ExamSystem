#!/usr/bin/env python3
"""每日政治理论 + 常识判断真题样式卷（政治 10 题 + 常识 5 题 = 15 题）。

Hermes 定时任务每天调用（与数量/资料同一机制）：
  1) policy_sources discover + refresh（脚本级抓取，无需 AI）
  2) 对今日生成会选中的非基础资料做"今日核验"：
       正文 sha 与登记一致 → 机械登记 update-review（原文引用 + "未发现新发布/修订/替代"结论）
       正文已变化      → 不机械登记，整批失败并报"需 AI 复核"（严守不凭旧文出题的纪律）
  3) quiz_lite 出政治理论 10 题（2判断+6单选+2多选）与常识判断 5 题（5单选），直接入库
  4) ai_daily_batch_runs 记账，练题页「定时任务」可看到生成中/失败卡片

--dry-run 只选点并打印 quota_audit（角色、广东题数、题型、同源/同段落14天限频），不写库不出题。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from policy_sources import (  # noqa: E402
    ROOT,
    discover,
    registry,
    refresh,
    review_updates,
    update_review,
)
from policy_daily_plan import quota_audit  # noqa: E402
from scheduler_common import (  # noqa: E402
    DB,
    EXIT_ERROR,
    EXIT_OK,
    FileLock,
    ensure_run_schema,
    local_today,
    new_batch_id,
)

LOCK_FILE = Path("/tmp/examsystem-daily-politics.lock")
OUTPUT_ROOT = ROOT / "data" / "daily-batches"
QUOTAS = (("政治理论", "zhengzhi", 10), ("常识判断", "changshi", 5))
# 角色配额见 policy_daily_plan.QUOTAS（政治含广东2、常识含广东2，其一必取高价值广东包）。
# 具体原文段落绑定选题，成功入库保存首次作答复测关联；无错点时转覆盖。
PER_ROUND_TIMEOUT = 2500
ROUNDS = 5
SERVICE_PATH = f"{Path.home() / '.local' / 'bin'}:/usr/local/bin:/usr/bin:/bin"


def imported_count(conn, batch_id: str) -> int:
    try:
        return int(conn.execute(
            "SELECT COUNT(*) FROM questions WHERE batch_id=?", (batch_id,)
        ).fetchone()[0])
    except Exception:
        return 0


def already_done(conn, module: str, day: dt.date) -> bool:
    """当天该模块已成功入库（或用户已删除）就不再出；失败会重试。"""
    row = conn.execute(
        "SELECT batch_id, status FROM ai_daily_batch_runs WHERE plan_date=? AND module=?",
        (str(day), module),
    ).fetchone()
    if not row:
        return False
    batch_id, status = str(row[0] or ""), row[1]
    if status == "deleted":
        return True
    if status in ("imported", "completed"):
        return True
    return False


def select_sources_without_gate(slots: list[dict]) -> list[dict]:
    """按槽位绑定的原文取资料，不做"今日核验"闸门（核验由本脚本随后统一做）。"""
    from policy_sources import applicable, refresh as _refresh
    today = dt.date.today()
    entries = registry()
    wanted = [str(s["source_id"]) for s in slots if s.get("source_id")]
    if not wanted:
        raise ValueError("本批没有绑定原文：政治/常识按原文出题，先登记并核验权威原文")
    records = []
    for ident in dict.fromkeys(wanted):
        spec = entries.get(ident)
        if not spec:
            raise ValueError(f"未登记资料：{ident}；先 policy_sources.py sources add 登记并核验")
        if not applicable(spec, today):
            raise ValueError(f"资料已失效或不适用于今日：{ident}")
        saved = (Path(os.environ.get("EXAM_POLICY_DIR") or ROOT / "data" / "manual-policy-sources")
                 / (ident + ".json"))
        cached = json.loads(saved.read_text()) if saved.exists() else None
        max_age = 7 if spec["kind"] == "foundation" else 1
        fresh = (cached and all(cached.get(k) == v for k, v in spec.items())
                 and (dt.datetime.now(dt.timezone.utc)
                      - dt.datetime.fromisoformat(cached["checked_at"])).total_seconds()
                 < max_age * 86400)
        try:
            records.append(cached if fresh else _refresh(spec))
        except Exception as exc:
            raise ValueError(f"资料 {ident} 刷新失败：{exc}") from exc
    return records


def resolve_generation_slots(module: str, slots: list[dict]) -> list[dict]:
    """Resolve the same leaf allocation quiz_lite will generate, before source checks."""
    from argparse import Namespace
    from quiz_generator import resolve_slots
    blueprint = json.dumps({"slots": slots}, ensure_ascii=False)
    resolved_module, resolved = resolve_slots(Namespace(
        blueprint=blueprint, tag=None, count=None, module=module,
        difficulty="mid", db=DB,
    ))
    if resolved_module != module:
        raise ValueError(f"蓝图模块不一致：请求{module}，解析为{resolved_module}")
    return resolved


def mechanical_review(spec) -> dict:
    """正文与登记一致时，机械登记今日 update-review（引用原文 + 版本一致结论）。

    正文已变化 → 抛 ValueError，调用方让整批失败，由 Hermes/AI 复核后重试。
    段落口径与 refresh 完全一致（≥20 字、去重、按 focus 过滤），sha 才能可比。
    """
    from policy_sources import fetch, sha
    saved = Path(os.environ.get("EXAM_POLICY_DIR")
                 or ROOT / "data" / "manual-policy-sources") / (spec["id"] + ".json")
    old_sha = None
    if saved.exists():
        try:
            old_sha = json.loads(saved.read_text()).get("sha256")
        except Exception:
            old_sha = None
    page, url = fetch(spec["url"])
    paragraphs = list(dict.fromkeys(p for p in page.parts if len(p) >= 20))
    focus = spec.get("focus") or []
    if focus:
        paragraphs = [p for p in paragraphs if any(word in p for word in focus)]
    if not paragraphs or sum(map(len, paragraphs)) < 120:
        raise ValueError(f"资料 {spec['id']} 原文提取不足，无法完成今日核验")
    new_sha = sha("\n".join(paragraphs))
    if old_sha is not None and new_sha != old_sha:
        raise ValueError(f"资料 {spec['id']} 正文已更新（sha 变化），需 AI 复核后重试；本次不出题")
    quote = paragraphs[0][:500]
    finding = ("机械核验：页面正文与登记版本一致（sha 相同），未发现新发布/修订/替代，"
               "版本口径适用于当日命题。")
    return review_updates({
        "source_ids": [spec["id"]],
        "urls": [url],
        "note": f"每日定时核验 {spec['id']}：正文一致，未见更新，可用于当日命题。",
        "findings": [{"url": url, "quote": quote, "finding": finding}],
    })


def ensure_selected_sources_current(slots: list[dict]) -> list[str]:
    """对今天选点会用的非基础资料做今日核验，返回未能核验的资料 id（调用方据此失败）。"""
    records = select_sources_without_gate(slots)
    stuck = []
    for record in records:
        if record["kind"] == "foundation":
            continue
        try:
            update_review(record)
            continue  # 今日已核验过
        except ValueError:
            pass
        try:
            mechanical_review(record)
        except ValueError as exc:
            stuck.append(str(exc))
    return stuck


def plan_slots(module: str, count: int) -> list[dict]:
    from policy_quiz import daily_question_types, module_slots
    return module_slots(module, count, "mid", layout=daily_question_types)


def dry_run(day: dt.date) -> dict:
    """只选点与审计，不登记运行、不核验资料、不调用模型。"""
    plans = []
    for module, _slug, count in QUOTAS:
        slots = plan_slots(module, count)
        resolve_generation_slots(module, slots)
        plans.append({
            "quota_audit": quota_audit(module, slots),
            "slots": [{"question_type": s["question_type"], "tag": s["tag"], "source_id": s["source_id"],
                       "point": s["policy_point"]["id"], "role": s["policy_point"]["role"],
                       "reason": s["policy_point"]["reason"]} for s in slots],
        })
    violations = [v for p in plans for v in p["quota_audit"]["limit_violations"]]
    return {"ok": not violations, "dry_run": True, "date": str(day), "plans": plans}


def run_politics_round(module: str, slug: str, count: int, day: dt.date) -> dict:
    base = {"plan_date": str(day), "module": module, "planned_count": count}
    conn = None
    batch_id = None
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB), timeout=30)
        ensure_run_schema(conn)
        if already_done(conn, module, day):
            conn.close()
            conn = None
            return {**base, "status": "skipped_imported"}
        request_slots = plan_slots(module, count)
        audit = quota_audit(module, request_slots)
        base["quota_audit"] = audit
        slots = resolve_generation_slots(module, request_slots)
        batch_id = new_batch_id(day, slug)
        conn.execute(
            """
            INSERT INTO ai_daily_batch_runs(plan_date,module,batch_id,status,planned_count,source)
            VALUES (?,?,?,'running',?,'daily-politics')
            ON CONFLICT(plan_date,module) DO UPDATE SET
              batch_id=excluded.batch_id, status='running', error=NULL,
              planned_count=excluded.planned_count, source=excluded.source,
              generated_at=NULL, imported_at=NULL, updated_at=CURRENT_TIMESTAMP
            """,
            (str(day), module, batch_id, count),
        )
        conn.commit()
        stuck = ensure_selected_sources_current(slots)
        if stuck:
            error = "；".join(stuck)[-2000:]
            conn.execute(
                "UPDATE ai_daily_batch_runs SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE batch_id=?",
                (error, batch_id),
            )
            conn.commit()
            conn.close()
            conn = None
            return {**base, "batch_id": batch_id, "status": "failed", "error": error}
    except Exception as exc:
        if conn is not None:
            if batch_id is not None:
                try:
                    conn.execute(
                        "UPDATE ai_daily_batch_runs SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE batch_id=?",
                        (str(exc)[-2000:], batch_id),
                    )
                    conn.commit()
                except Exception:
                    pass
            conn.close()
        return {**base, "batch_id": batch_id, "status": "failed", "error": str(exc)[-2000:]}
    if conn is not None:
        conn.close()

    command = [
        sys.executable, str(ROOT / "scripts" / "quiz_lite.py"),
        "--module", module,
    ]
    command += ["--blueprint", json.dumps({"slots": slots}, ensure_ascii=False)]
    command += [
        "--batch-id", batch_id,
        "--rounds", str(ROUNDS),
        "--output-dir", str(OUTPUT_ROOT),
        "--db", str(DB),
    ]
    env = {**os.environ, "EXAM_DB": str(DB), "PATH": f"{SERVICE_PATH}:{os.environ.get('PATH', '')}"}
    started = time.monotonic()
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
            timeout=PER_ROUND_TIMEOUT,
        )
        outcome = _last_json(result.stdout)
        error = None
        if result.returncode != 0 or outcome.get("status") != "success":
            error = str(outcome.get("error") or (result.stderr or result.stdout or "quiz_lite 出题失败").strip())
    except subprocess.TimeoutExpired:
        error = f"出题超过 {PER_ROUND_TIMEOUT} 秒未完成，已停止"
    conn = sqlite3_connect()
    try:
        imported = imported_count(conn, batch_id)
        if error is None and imported < count:
            error = f"quiz_lite 返回成功，但只入库 {imported}/{count} 题"
        if error:
            conn.execute(
                "UPDATE ai_daily_batch_runs SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE batch_id=?",
                (error[-2000:], batch_id),
            )
        else:
            conn.execute(
                "UPDATE ai_daily_batch_runs SET status='imported', generated_at=CURRENT_TIMESTAMP,"
                " imported_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE batch_id=?",
                (batch_id,),
            )
        conn.commit()
    finally:
        conn.close()
    return {**base, "batch_id": batch_id, "status": "failed" if error else "imported",
            "error": error, "imported_count": imported, "elapsed_sec": round(time.monotonic() - started, 1)}


def sqlite3_connect():
    import sqlite3
    return sqlite3.connect(str(DB), timeout=30)


def _last_json(text: str) -> dict:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def merge_into_single_paper(results: list[dict]) -> dict | None:
    """政治理论 + 常识判断各自出好后，拼接成一套 15 题（同一 batch_id）。

    常识判断的题并入政治理论批次：meta 按 batch_id 聚合 → 练题页显示为一套。
    只有两套都成功才拼；任一套失败就各自独立保留（仍可练）。
    """
    zz = next((r for r in results
               if r.get("module") == "政治理论" and r.get("status") == "imported" and r.get("batch_id")), None)
    cs = next((r for r in results
               if r.get("module") == "常识判断" and r.get("status") == "imported" and r.get("batch_id")), None)
    if not zz or not cs or zz["batch_id"] == cs["batch_id"]:
        return None
    conn = sqlite3_connect()
    try:
        from daily_review_plan import save_plan
        old_plan = conn.execute('SELECT plan_json FROM daily_review_plans WHERE batch_id=?',
                                (cs['batch_id'],)).fetchone() if conn.execute(
                                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_review_plans'").fetchone() else None
        if old_plan:
            # 保留原题 external_id，合卷后错点仍能回溯到常识题的具体原文段落。
            plan = json.loads(old_plan[0])
            zz_plan = conn.execute('SELECT plan_json FROM daily_review_plans WHERE batch_id=?',
                                   (zz['batch_id'],)).fetchone()
            if zz_plan:
                merged_plan = json.loads(zz_plan[0])
                merged_plan['questions'].extend(plan.get('questions', []))
                merged_plan['points'].extend(plan.get('points', []))
                save_plan(conn, zz['batch_id'], merged_plan)
        conn.execute("UPDATE questions SET batch_id=? WHERE batch_id=?", (zz["batch_id"], cs["batch_id"]))
        conn.execute(
            "UPDATE ai_daily_batch_runs SET batch_id=?, updated_at=CURRENT_TIMESTAMP WHERE batch_id=?",
            (zz["batch_id"], cs["batch_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"merged_batch_id": zz["batch_id"],
            "total": int(zz.get("planned_count") or 0) + int(cs.get("planned_count") or 0)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=dt.date.fromisoformat, default=local_today())
    parser.add_argument("--force", action="store_true", help="当天已出过也重出（调试用）")
    parser.add_argument("--dry-run", action="store_true", help="只打印选点与配额/限频审计，不写库不出题")
    args = parser.parse_args(argv)
    day = args.date
    os.environ["EXAM_DB"] = str(DB)
    if args.dry_run:
        try:
            out = dry_run(day)
        except Exception as exc:
            out = {"ok": False, "dry_run": True, "error": str(exc)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return EXIT_OK if out["ok"] else EXIT_ERROR
    try:
        with FileLock(LOCK_FILE):
            try:
                discover()
            except Exception as exc:
                print(json.dumps({"ok": False, "error": f"资料发现失败：{exc}"}, ensure_ascii=False))
                return EXIT_ERROR
            results = [run_politics_round(module, slug, count, day) for module, slug, count in QUOTAS]
            failed = [row for row in results if row["status"] == "failed"]
            merged = None
            if not failed:
                merged = merge_into_single_paper(results)
            out = {"ok": not failed, "date": str(day), "runs": results}
            if merged:
                out["merged"] = merged
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return EXIT_ERROR if failed else EXIT_OK
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

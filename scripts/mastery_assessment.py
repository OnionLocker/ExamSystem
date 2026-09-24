"""Evidence-based mastery and fluency. Thresholds are policy, not probabilities."""

import datetime as dt
import json
import math
import statistics

VERSION = 2
TZ = dt.timezone(dt.timedelta(hours=8))
LABELS = {"unassessed": "待评估", "developing": "尚未掌握", "initial": "初步掌握",
          "mastered": "已掌握", "stable": "稳定掌握"}
FLUENCY = {"unassessed": "待评估", "slow": "需提速", "standard": "达标", "fluent": "熟练"}


def timestamp(raw):
    try:
        value = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value
    except (ValueError, TypeError):
        return None


def validate_review(value):
    if not isinstance(value, dict):
        raise ValueError("assessment must be an object")
    enums = {"independence": {"independent", "assisted", "unknown"},
             "process": {"correct", "partial", "incorrect", "unknown"},
             "basis": {"draft", "explanation", "unavailable"},
             "execution": {"smooth", "hesitant", "unknown"}}
    allowed = set(enums) | {"reason", "template", "variant", "mixed", "timing_valid",
                            "target_seconds", "target_basis"}
    if set(value) - allowed:
        raise ValueError("unknown assessment fields: " + ", ".join(sorted(set(value) - allowed)))
    for key, choices in enums.items():
        if value.get(key) not in choices:
            raise ValueError(f"{key} must be one of {sorted(choices)}")
    for key in ("variant", "mixed", "timing_valid"):
        if type(value.get(key, False)) is not bool:
            raise ValueError(f"{key} must be boolean")
    for key in ("reason", "template", "target_basis"):
        if not isinstance(value.get(key, ""), str) or len(value.get(key, "")) > 2000:
            raise ValueError(f"invalid {key}")
    if not value.get("reason", "").strip():
        raise ValueError("reason must cite the observed evidence or missing evidence")
    if value["process"] != "unknown" and value["basis"] == "unavailable":
        raise ValueError("a process judgment requires draft or explanation evidence")
    target = value.get("target_seconds")
    if target is not None:
        if type(target) not in (int, float) or not math.isfinite(target) or not 0 < target <= 3600:
            raise ValueError("target_seconds must be within (0, 3600]")
        if not value.get("target_basis", "").strip():
            raise ValueError("target_basis is required for a time target")
    return dict(value)


def decode_review(raw):
    try:
        return validate_review(json.loads(raw)) if raw else None
    except (ValueError, TypeError):
        return None


def history_summary(events):
    """Use recorded first answers for a provisional baseline, never certify a process."""
    outcomes = [e for e in events if e.get("objective_result") or e.get("evidence_type") == "exam"]
    recent = outcomes[-10:]
    correct = sum(bool(e.get("is_correct")) for e in recent)
    n = len(recent)
    status = "limited"
    if n >= 3:
        status = "weak" if correct / n < .5 else "mixed" if correct / n < .8 else "strong"
    sessions = {}
    for e in outcomes:
        key = (e.get("evidence_type"), e.get("session_id"))
        if key[1] is not None:
            sessions.setdefault(key, []).append(e)
    rounds = [items for items in sessions.values() if len(items) >= 3][-2:]
    rates = [sum(bool(e.get("is_correct")) for e in items) / len(items) for items in rounds]
    plateau = len(rates) == 2 and max(rates) <= .6 and rates[-1] <= rates[0]
    times = [e["elapsed_ms"] / 1000 for e in recent if e.get("is_correct") and (e.get("elapsed_ms") or 0) > 0]
    return {"status": status, "samples": len(outcomes), "recent_samples": n,
            "correct": correct, "days": len({e["day"] for e in recent}),
            "median_seconds": round(statistics.median(times), 1) if times else None,
            "plateau": plateau, "last_at": recent[-1]["when"].isoformat() if recent else None,
            "evidence": [{"question_id": e.get("question_id"), "session_id": e.get("session_id"),
                          "date": e["day"], "correct": bool(e.get("is_correct")),
                          "elapsed_seconds": round((e.get("elapsed_ms") or 0) / 1000, 1)} for e in recent[-5:][::-1]]}


def assess(events, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    ordered = sorted(events, key=lambda e: (timestamp(e.get("answered_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), e.get("id", 0)))
    seen_questions, seen_templates = set(), set()
    first_answers = []
    evidence, repeats, unreviewed, assisted = [], 0, 0, 0
    seen_claims = set()
    for event in ordered:
        source, qid = event.get("evidence_type"), event.get("question_id")
        # Exam item numbers are local to an exam; practice question IDs are global.
        identity = (source, event.get("session_id") if source == "exam" else None, qid)
        repeated = qid is not None and (identity in seen_questions or event.get("is_repeat"))
        if qid is not None:
            seen_questions.add(identity)
        if repeated:
            repeats += 1
            continue
        review = decode_review(event.get("assessment_json"))
        when = timestamp(event.get("answered_at"))
        if not when or when > now:
            unreviewed += 1
            continue
        day = when.astimezone(TZ).date().isoformat()
        if not review or review["independence"] != "assisted":
            first_answers.append({**event, "when": when, "day": day})
        if not review:
            unreviewed += 1
            continue
        if review["independence"] != "independent":
            assisted += 1
            continue
        if review["process"] == "unknown":
            unreviewed += 1
            continue
        claims = event.get('claim_ids') or []
        if claims and all((day, claim) in seen_claims for claim in claims):
            repeats += 1
            continue
        seen_claims.update((day, claim) for claim in claims)
        template = (day, review.get("template", "").strip() or "unspecified")
        if template in seen_templates:
            repeats += 1
            continue
        seen_templates.add(template)
        evidence.append({**event, "review": review, "when": when, "day": day,
                         "supports": review["process"] == "correct" and (not event.get('claim_ids') or bool(event.get('is_correct')))})

    level, mastered_at, stable = "unassessed", None, False
    for i, event in enumerate(evidence):
        window = evidence[max(0, i - 4):i + 1]
        positives = sum(e["supports"] for e in window)
        passed = (len(window) == 5 and positives >= 4
                  and len({e["day"] for e in window}) >= 2
                  and any(e["supports"] and e["review"].get("variant") for e in window))
        if any(e.get('claim_ids') for e in window):
            passed = passed and any(e['supports'] and e.get('question_type') in {'single', 'multi'} for e in window)
        if passed:
            if mastered_at is None:
                mastered_at = event["when"]
            if (event["supports"] and (event["when"] - mastered_at).total_seconds() >= 7 * 86400
                    and any(e["supports"] and e["review"].get("mixed") for e in window)):
                stable = True
            level = "stable" if stable else "mastered"
        else:
            mastered_at, stable = None, False
            recent_errors = sum(e["review"]["process"] == "incorrect" for e in window[-3:])
            level = "developing" if recent_errors >= 2 else "initial" if positives else "unassessed"

    recent = evidence[-5:]
    outdated_sources = sum(bool(e.get('source_outdated')) for e in recent)
    by_type = {}
    for e in first_answers:
        kind = e.get('question_type')
        if kind:
            bucket = by_type.setdefault(kind, {'samples': 0, 'correct': 0})
            bucket['samples'] += 1
            bucket['correct'] += int(bool(e.get('is_correct')))
    history = history_summary(first_answers)
    last_seen = evidence[-1]["when"] if evidence else timestamp(history["last_at"])
    stale = bool(last_seen and (now - last_seen).total_seconds() >= 30 * 86400)
    timed = [e for e in recent if e["supports"] and e.get("is_correct")
             and e["review"].get("timing_valid") and e["review"].get("target_seconds")
             and e["review"]["execution"] != "unknown" and (e.get("elapsed_ms") or 0) > 0]
    ratios = [e["elapsed_ms"] / 1000 / e["review"]["target_seconds"] for e in timed]
    fluency = "unassessed"
    if len(timed) >= 3 and len({e["day"] for e in timed}) >= 2 and not stale:
        on_time = sum(r <= 1 for r in ratios) / len(ratios)
        smooth = sum(e["review"]["execution"] == "smooth" for e in timed) / len(timed)
        fluency = "fluent" if on_time >= .8 and smooth >= .8 else "standard" if on_time >= .6 else "slow"
    correct = sum(bool(e.get("is_correct")) for e in recent)
    calibration = [e for e in evidence if e.get("prior_level") in {"mastered", "stable"}]
    basis = "reviewed" if level != "unassessed" else "history" if history["recent_samples"] else "activity" if events else "none"
    label = LABELS[level] if basis == "reviewed" else {
        "weak": "历史薄弱", "mixed": "历史待巩固", "strong": "历史表现较好", "limited": "已有作答"
    }[history["status"]] if basis == "history" else "已有学习记录" if basis == "activity" else LABELS[level]
    return {
        "version": VERSION, "level": level, "label": label, "basis": basis,
        "history": history, "activity_count": len(events),
        "fluency": fluency, "fluency_label": FLUENCY[fluency], "review_due": stale or bool(outdated_sources),
        "source_update_due": bool(outdated_sources), "by_question_type": by_type,
        "independent_samples": len(evidence), "recent_samples": len(recent),
        "process_correct": sum(e["supports"] for e in recent), "answer_correct": correct,
        "days": len({e["day"] for e in recent}), "repeats_excluded": repeats,
        "unreviewed": unreviewed, "assisted_or_unknown": assisted,
        "variant_verified": any(e["supports"] and e["review"].get("variant") for e in recent),
        "delayed_verified": stable, "timed_samples": len(timed),
        "median_seconds": round(statistics.median(e["elapsed_ms"] / 1000 for e in timed), 1) if timed else None,
        "median_target_ratio": round(statistics.median(ratios), 2) if ratios else None,
        "last_evidence_at": last_seen.isoformat() if last_seen else None,
        "calibration": {"samples": len(calibration), "correct": sum(bool(e.get("is_correct")) for e in calibration)},
        "evidence": [{"question_id": e.get("question_id"), "session_id": e.get("session_id"),
                      "date": e["day"], "correct": bool(e.get("is_correct")),
                      "elapsed_seconds": round((e.get("elapsed_ms") or 0) / 1000, 1),
                      **e["review"]} for e in reversed(recent)],
    }

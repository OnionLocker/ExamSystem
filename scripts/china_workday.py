#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026 年中国国务院调休工作日判断。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from functools import lru_cache
from pathlib import Path


CALENDAR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "calendar"
    / "cn_workdays_2026.json"
)


@lru_cache(maxsize=4)
def load_calendar(path: Path = CALENDAR) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    workdays = frozenset(dt.date.fromisoformat(value) for value in data["workdays"])
    holidays = frozenset(dt.date.fromisoformat(value) for value in data["holidays"])
    if workdays & holidays:
        raise ValueError("workdays 与 holidays 不能重叠")
    year = int(data["year"])
    if any(day.year != year for day in workdays | holidays):
        raise ValueError("日历日期与 year 不一致")
    return {**data, "workdays": workdays, "holidays": holidays}


def workday_reason(day: dt.date, calendar_path: Path = CALENDAR) -> tuple[bool, str]:
    data = load_calendar(calendar_path)
    if day.year != data["year"]:
        raise ValueError(f"仅支持 {data['year']} 年工作日日历")
    if day in data["workdays"]:
        return True, "makeup_workday"
    if day in data["holidays"]:
        return False, "statutory_holiday"
    if day.weekday() >= 5:
        return False, "weekend"
    return True, "weekday"


def is_workday(day: dt.date, calendar_path: Path = CALENDAR) -> bool:
    return workday_reason(day, calendar_path)[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", type=dt.date.fromisoformat)
    parser.add_argument("--calendar", type=Path, default=CALENDAR)
    args = parser.parse_args(argv)
    try:
        allowed, reason = workday_reason(args.date, args.calendar.resolve())
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {"date": str(args.date), "workday": allowed, "reason": reason},
            ensure_ascii=False,
        )
    )
    return 0 if allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())

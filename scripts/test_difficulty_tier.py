#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日练难度隔天轮换：difficulty_tier + generation_prompt 含档位。"""
from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

import daily_batch_scheduler
from scheduler_common import difficulty_tier


class DifficultyTierTest(unittest.TestCase):
    def test_alternates_by_date(self):
        base = dt.date(2026, 9, 20)
        tiers = [difficulty_tier(base + dt.timedelta(days=i)) for i in range(6)]
        # 相邻两天必然一简单一难
        for a, b in zip(tiers, tiers[1:]):
            self.assertNotEqual(a, b)
        self.assertTrue(set(tiers) == {"easy", "hard"})

    def test_deterministic_and_str_input(self):
        self.assertEqual(difficulty_tier("2026-09-21"), difficulty_tier(dt.date(2026, 9, 21)))
        self.assertIn(difficulty_tier("2026-09-21"), ("easy", "hard"))
        # 偶数序数=easy、奇数=hard
        self.assertEqual(difficulty_tier("2026-09-21"), "easy")   # 序数偶
        self.assertEqual(difficulty_tier("2026-09-20"), "hard")   # 序数奇

    def test_prompt_carries_tier(self):
        snap = {"summary": {}, "compact": ""}
        easy_run = {"plan_date": "2026-09-21", "module": "数量关系", "planned_count": 15, "batch_id": "d-e"}
        hard_run = {"plan_date": "2026-09-20", "module": "数量关系", "planned_count": 15, "batch_id": "d-h"}
        pe = daily_batch_scheduler.generation_prompt(easy_run, snap, Path("/tmp/b"))
        ph = daily_batch_scheduler.generation_prompt(hard_run, snap, Path("/tmp/b"))
        self.assertIn("difficulty_tier=easy", pe)
        self.assertIn("简单档 easy", pe)
        self.assertIn("difficulty_tier=hard", ph)
        self.assertIn("难档 hard", ph)
        # 两档都强调结构/配比不变
        self.assertIn("模块配比不变", pe)


if __name__ == "__main__":
    unittest.main()

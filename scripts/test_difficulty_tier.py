#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日练难度隔天轮换：difficulty_tier。"""
from __future__ import annotations

import datetime as dt
import unittest

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


if __name__ == "__main__":
    unittest.main()

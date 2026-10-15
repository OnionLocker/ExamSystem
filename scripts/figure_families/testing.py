"""各题型族共用的回归用例：固定种子出题都要过判题器、同种子出同一道题、自检负例全部拦下。"""

from __future__ import annotations

import unittest

from . import families
from .core import make_item


def family_suite(names: tuple[str, ...], per_tier: int = 2) -> type:
    class FamilyTest(unittest.TestCase):
        pass

    def add(name):
        def test_generate(self):
            fam = families()[name]
            for i, tier in enumerate(("easy", "mid", "hard") * per_tier):
                item = make_item(fam, f"regression-{i}", tier, "ABCD"[i % 4])
                self.assertEqual(item["verdict"]["correct"], ["ABCD"[i % 4]], f"{name} 第 {i} 题")
                self.assertTrue(item["explanation"].strip())
                self.assertIn(item["draft"]["difficulty"], (2, 3, 4))
                self.assertTrue(item["draft"]["stem"].strip())

        def test_deterministic(self):
            fam = families()[name]
            a = make_item(fam, "same-seed", "mid", "C")
            b = make_item(fam, "same-seed", "mid", "C")
            self.assertEqual(a["svgs"], b["svgs"])
            self.assertEqual(a["pngs"], b["pngs"])

        def test_negatives(self):
            fam = families()[name]
            for case, blocked, detail in fam.self_test():
                self.assertTrue(blocked, f"{name}：{case} 没拦下（{detail}）")

        setattr(FamilyTest, f"test_{name}_generate", test_generate)
        setattr(FamilyTest, f"test_{name}_deterministic", test_deterministic)
        setattr(FamilyTest, f"test_{name}_negatives", test_negatives)

    for name in names:
        add(name)
    return FamilyTest

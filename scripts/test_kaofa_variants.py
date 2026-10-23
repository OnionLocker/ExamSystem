#!/usr/bin/env python3
import datetime as dt
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import kaofa_variants as kv

TAG = "数量关系-数学运算-最值问题-@extreme-heding"
CATALOG = {TAG: {"title": "和定最值", "variants": [
    {"id": "distinct", "name": "互不相同", "ask": "互不相同求名次极值", "weight": 3, "typical": True},
    {"id": "repeat", "name": "允许相同", "ask": "允许相同求名次极值", "weight": 2},
    {"id": "vote", "name": "选票排名", "ask": "选票排名求最多票", "weight": 2, "example": "粤2022：……最多为（）张"},
    {"id": "average", "name": "平均数约束", "ask": "给平均数求极值", "weight": 1},
]}}


class VariantTest(unittest.TestCase):
    def test_splits_slots_and_rotates_away_from_typical(self):
        slots = [{"tag": TAG, "count": 4}]
        with tempfile.TemporaryDirectory() as tmp:
            out = kv.assign_variants("数量关系", slots, seed="b1", catalog=CATALOG, ledger=Path(tmp, "l.jsonl"))
        self.assertEqual(len(out), 4)
        self.assertTrue(all(s["count"] == 1 for s in out))
        self.assertEqual(len({s["kaofa_variant"] for s in out}), 4)
        self.assertNotEqual(out[0]["kaofa_variant"], "distinct")
        self.assertIn("本题考法变式", out[0]["brief"])

    def test_ledger_makes_next_batch_pick_unused(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp, "l.jsonl")
            first = kv.assign_variants("数量关系", [{"tag": TAG, "count": 2}], seed="a", catalog=CATALOG, ledger=ledger)
            kv.record_variants("a", first, ledger)
            second = kv.assign_variants("数量关系", [{"tag": TAG, "count": 2}], seed="b", catalog=CATALOG, ledger=ledger)
        never = {"repeat", "vote", "average"} - {s["kaofa_variant"] for s in first}
        self.assertTrue(never)
        self.assertEqual(second[0]["kaofa_variant"], never.pop())

    def test_old_usage_decays_and_user_brief_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp, "l.jsonl")
            old = (dt.date.today() - dt.timedelta(days=200)).isoformat()
            ledger.write_text(json.dumps({"date": old, "batch_id": "x", "tag": TAG, "variant": "repeat"}) + "\n")
            self.assertEqual(kv.usage(ledger), Counter())
            kept = kv.assign_variants("数量关系", [{"tag": TAG, "count": 3, "brief": "全部出允许相同"}],
                                      catalog=CATALOG, ledger=ledger)
            merged = kv.assign_variants("数量关系", [{"tag": TAG, "count": 2, "brief": "贴近广东真题，稍难"}],
                                        catalog=CATALOG, ledger=ledger)
        self.assertEqual(kept, [{"tag": TAG, "count": 3, "brief": "全部出允许相同"}])
        self.assertEqual(len(merged), 2)
        self.assertTrue(all("本题考法变式" in s["brief"] and "贴近广东真题" in s["brief"] for s in merged))

    def test_other_modules_and_unknown_tags_untouched(self):
        slots = [{"tag": "资料分析-比重类-现期、基期与隔级比重", "count": 2}]
        self.assertEqual(kv.assign_variants("资料分析", slots, catalog=CATALOG), slots)
        unknown = [{"tag": "数量关系-数学运算-未知", "count": 2}]
        self.assertEqual(kv.assign_variants("数量关系", unknown, catalog=CATALOG), unknown)

    def test_shipped_catalog_is_well_formed(self):
        catalog = kv.load_catalog()
        for tag, entry in catalog.items():
            variants = entry.get("variants") or []
            self.assertGreaterEqual(len(variants), 3, tag)
            self.assertEqual(sum(bool(v.get("typical")) for v in variants), 1, tag)
            self.assertEqual(len({v["id"] for v in variants}), len(variants), tag)
            for v in variants:
                self.assertTrue(v.get("name") and v.get("ask"), tag)
                self.assertIn(int(v.get("weight") or 0), range(1, 6), tag)
                self.assertLessEqual(len(kv.variant_brief(v)), 600, tag)


if __name__ == "__main__":
    unittest.main()

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
    def test_splits_slots_into_one_per_question(self):
        slots = [{"tag": TAG, "count": 4}]
        with tempfile.TemporaryDirectory() as tmp:
            out = kv.assign_variants("数量关系", slots, seed="b1", catalog=CATALOG, ledger=Path(tmp, "l.jsonl"))
        self.assertEqual(len(out), 4)
        self.assertTrue(all(s["count"] == 1 for s in out))
        self.assertEqual(len({s["kaofa_variant"] for s in out}), 4)
        self.assertIn("本题考法变式", out[0]["brief"])

    def test_high_weight_typical_can_beat_low_weight_non_typical_when_fresh(self):
        """回归：典型考法被固定加罚分时，真题高频的典型会输给低频非典型（真题常考的反而不出）。
        改为按权重乘系数降权后，高频典型在全新账本下不应被确定性排斥。"""
        hot = "数量关系-数学运算-最值问题-@hot"
        catalog = {hot: {"title": "高频典型", "variants": [
            {"id": "typical-hot", "name": "高频典型", "ask": "高频典型考法", "weight": 5, "typical": True},
            {"id": "cold", "name": "低频冷门", "ask": "低频冷门考法", "weight": 1},
        ]}}
        hot_picked = 0
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp, "l.jsonl")
            for seed in range(60):
                out = kv.assign_variants("数量关系", [{"tag": hot, "count": 1}], seed=str(seed),
                                         catalog=catalog, ledger=ledger)
                if out[0]["kaofa_variant"] == "typical-hot":
                    hot_picked += 1
        self.assertGreater(hot_picked, 0, "高频典型考法被确定性排斥（新账本下应有机会被选中）")

    def test_ledger_makes_next_batch_pick_unused(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp, "l.jsonl")
            first = kv.assign_variants("数量关系", [{"tag": TAG, "count": 2}], seed="a", catalog=CATALOG, ledger=ledger)
            kv.record_variants("a", first, ledger)
            second = kv.assign_variants("数量关系", [{"tag": TAG, "count": 2}], seed="b", catalog=CATALOG, ledger=ledger)
        used_in_first = {s["kaofa_variant"] for s in first}
        second_variants = {s["kaofa_variant"] for s in second}
        # 第二次批应优先补第一次没用到的变式（它们账本负载为 0，必先被选）
        self.assertEqual(len(second_variants & used_in_first), 0)
        self.assertEqual(len(second_variants), 2)

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

    def test_cli_list_add_edit_remove(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "catalog.json")
            path.write_text(json.dumps(CATALOG, ensure_ascii=False))
            with patch.object(kv, "CATALOG", path), patch.object(kv, "LEDGER", Path(tmp, "l.jsonl")):
                listed = kv.cli(["list", "和定最值"])
                self.assertEqual(len(listed["variants"]), 4)
                added = kv.cli(["add", TAG, "--name", "两轮分配求极值", "--ask", "先按规则分配一轮，再在剩余总量中二次分配，求某名次极值",
                                "--example", "粤2027：……", "--id", "two-round"])
                self.assertEqual(added["total"], 5)
                with self.assertRaises(SystemExit) as dup:
                    kv.cli(["add", TAG, "--name", "允许相同", "--ask", "允许相同求名次极值"])
                self.assertIn("高度相似", str(dup.exception))
                kv.cli(["edit", TAG, "two-round", "--weight", "4", "--typical"])
                entry = kv.load_catalog()[TAG]
                self.assertEqual([v["id"] for v in entry["variants"] if v["typical"]], ["two-round"])
                with self.assertRaises(SystemExit):
                    kv.cli(["remove", TAG, "two-round"])
                kv.cli(["remove", TAG, "average"])
                with self.assertRaises(SystemExit) as too_few:
                    kv.cli(["remove", TAG, "vote"]); kv.cli(["remove", TAG, "repeat"])
                self.assertIn("至少保留 3 个", str(too_few.exception))
                self.assertEqual(len(kv.load_catalog()[TAG]["variants"]), 3)

    def test_ziliao_paper_keeps_kind_and_filters_material(self):
        share = "资料分析-比重类-现期、基期与隔级比重"
        catalog = {share: {"title": "比重", "variants": [
            {"id": "current", "name": "现期比重", "ask": "求现期比重", "weight": 3, "typical": True, "kind": "share"},
            {"id": "multi", "name": "多部分合计", "ask": "多部分合计占比", "weight": 3, "kind": "share", "types": ["table"]},
            {"id": "other-kind", "name": "两期比重", "ask": "两期比重差", "weight": 3, "kind": "share_change"},
        ]}}
        slots = [{"tag": share, "kind": "share", "material_type": "years", "brief": "比重"},
                 {"tag": share, "kind": "share", "material_type": "table", "brief": "比重"},
                 {"tag": share, "kind": "judge", "brief": "综合"},
                 {"tag": share, "kind": "share", "quick": True, "brief": "定性"}]
        with tempfile.TemporaryDirectory() as tmp:
            out = kv.assign_ziliao_variants(slots, seed="p", catalog=catalog, ledger=Path(tmp, "l.jsonl"))
        self.assertEqual(out[0]["kaofa_variant"], "current")
        self.assertEqual(out[1]["kaofa_variant"], "multi")
        self.assertTrue(out[1]["brief"].startswith("比重；本题考法变式"))
        self.assertEqual(out[2:], slots[2:])

    def test_ziliao_drill_rotates_all_kinds_and_respects_format(self):
        share = "资料分析-比重类-现期、基期与隔级比重"
        catalog = {share: {"title": "比重", "variants": [
            {"id": "current", "name": "现期比重", "ask": "求现期比重", "weight": 3, "typical": True, "kind": "share"},
            {"id": "monthly-only", "name": "月度累计", "ask": "月度累计占比", "weight": 5, "kind": "share", "types": ["monthly"]},
            {"id": "two-period", "name": "两期比重", "ask": "两期比重差", "weight": 3, "kind": "share_change"},
        ]}}
        slots = [{"tag": share, "count": 1, "material_format": "chart"} for _ in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp, "l.jsonl")
            out = kv.assign_ziliao_variants(slots, seed="d", targeted=True, catalog=catalog, ledger=ledger)
            self.assertEqual(kv.record_variants("d", out, ledger), 3)
        self.assertNotIn("monthly-only", {s["kaofa_variant"] for s in out})
        self.assertEqual({s["kaofa_variant"] for s in out[:2]}, {"current", "two-period"})
        locked = [{"tag": share, "count": 1, "brief": "只练现期比重"}]
        self.assertEqual(kv.assign_ziliao_variants(locked, targeted=True, catalog=catalog), locked)

    def test_cli_ziliao_requires_kind(self):
        from unittest.mock import patch
        share = "资料分析-比重类-现期、基期与隔级比重"
        catalog = {share: {"title": "比重", "variants": [
            {"id": f"v{i}", "name": f"考法{i}", "ask": f"第{i}种比重问法", "weight": 2, "typical": i == 0, "kind": "share"}
            for i in range(3)]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "catalog.json")
            path.write_text(json.dumps(catalog, ensure_ascii=False))
            with patch.object(kv, "CATALOG", path), patch.object(kv, "LEDGER", Path(tmp, "l.jsonl")):
                with self.assertRaises(SystemExit) as missing:
                    kv.cli(["add", share, "--name", "隔级比重", "--ask", "两级占比相乘求隔级比重"])
                self.assertIn("kind", str(missing.exception))
                added = kv.cli(["add", share, "--name", "隔级比重", "--ask", "两级占比相乘求隔级比重",
                                "--kind", "share", "--types", "table,text", "--need", "两级占比"])
                self.assertEqual(added["added"]["types"], ["table", "text"])
                with self.assertRaises(SystemExit):
                    kv.cli(["edit", share, added["added"]["id"], "--types", "bogus"])

    def test_named_variant_overrides_rotation_and_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp, "l.jsonl")
            one = kv.assign_variants("数量关系", [{"tag": TAG, "count": 3, "kaofa_variant": ["选票"]}],
                                     catalog=CATALOG, ledger=ledger, boost={})
            two = kv.assign_variants("数量关系", [{"tag": TAG, "count": 4, "kaofa_variant": ["vote", "允许相同"],
                                                  "brief": "只练这两种，稍难"}], catalog=CATALOG, ledger=ledger, boost={})
            with self.assertRaises(ValueError) as bad:
                kv.assign_variants("数量关系", [{"tag": TAG, "count": 1, "kaofa_variant": ["不存在"]}],
                                   catalog=CATALOG, ledger=ledger, boost={})
        self.assertEqual([s["kaofa_variant"] for s in one], ["vote"] * 3)
        self.assertNotIn("kaofa_focus", one[0])
        self.assertEqual(sorted(s["kaofa_variant"] for s in two), ["repeat", "repeat", "vote", "vote"])
        self.assertTrue(all("稍难" in s["brief"] for s in two))
        self.assertIn("可选", str(bad.exception))

    def test_weak_variants_get_extra_share_and_focus(self):
        boost = {(TAG, "average"): 1.6}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp, "l.jsonl")
            spread = kv.assign_variants("数量关系", [{"tag": TAG, "count": 5}], seed="w",
                                        catalog=CATALOG, ledger=ledger, boost=boost)
            focus = kv.assign_variants("数量关系", [{"tag": TAG, "count": 3, "kaofa_focus": "weak"}],
                                       catalog=CATALOG, ledger=ledger, boost=boost)
            fallback = kv.assign_variants("数量关系", [{"tag": TAG, "count": 4, "kaofa_focus": "weak"}],
                                          catalog=CATALOG, ledger=ledger, boost={})
        ids = [s["kaofa_variant"] for s in spread]
        self.assertEqual(ids.count("average"), 2)
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual({s["kaofa_variant"] for s in focus}, {"average"})
        self.assertEqual(len({s["kaofa_variant"] for s in fallback}), 4)

    def test_question_ids_enable_variant_accuracy(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            ledger, db = Path(tmp, "l.jsonl"), Path(tmp, "exam.db")
            slots = [{"tag": TAG, "count": 1, "kaofa_variant": v} for v in ("vote", "vote", "repeat")]
            self.assertEqual(kv.record_variants("b", slots, ledger, question_ids=["b_01", "b_02", "b_03"]), 3)
            with sqlite3.connect(db) as conn:
                conn.executescript("""CREATE TABLE questions(id INTEGER PRIMARY KEY, external_id TEXT);
                    CREATE TABLE practice_answers(id INTEGER PRIMARY KEY, question_id INTEGER, user_answer TEXT,
                                                  is_correct INTEGER, time_spent_sec INTEGER, answered_at TEXT);""")
                conn.executemany("INSERT INTO questions VALUES (?,?)", [(1, "b_01"), (2, "b_02"), (3, "b_03")])
                today = dt.date.today().isoformat()
                conn.executemany("INSERT INTO practice_answers(question_id,user_answer,is_correct,time_spent_sec,answered_at)"
                                 " VALUES (?,?,?,?,?)", [(1, "A", 0, 80, today), (2, "B", 0, 70, today),
                                                         (2, "C", 1, 30, today), (3, "D", 1, 40, today)])
            stats = kv.variant_performance(db, ledger)
            self.assertEqual(stats[(TAG, "vote")], {"n": 2, "correct": 0})
            self.assertEqual(stats[(TAG, "repeat")], {"n": 1, "correct": 1})
            self.assertGreater(kv.variant_boosts(stats)[(TAG, "vote")], 1.4)
            self.assertNotIn((TAG, "repeat"), kv.variant_boosts(stats))

    def test_shipped_catalog_is_well_formed(self):
        catalog = kv.load_catalog()
        for tag, entry in catalog.items():
            if tag.startswith("资料分析-"):
                for v in entry["variants"]:
                    self.assertEqual(kv.ziliao_variant_issues(v), [], tag)
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

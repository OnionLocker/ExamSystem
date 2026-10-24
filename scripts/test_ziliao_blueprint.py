#!/usr/bin/env python3
import json
import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import kaofa_variants as kv
import normalize_ai_batch as nab
import ziliao_blueprint as bp
from kaodian_taxonomy import validate_ziliao_paper_answers


class BlueprintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.catalog = kv.load_catalog()
        cls.papers = [bp.build_blueprint(seed=f"s{i}", output_dir=cls.root / "none", db=cls.root / "none.db",
                                         catalog=cls.catalog, ledger=cls.root / "l.jsonl") for i in range(150)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_paper_constraints_hold(self):
        for paper in self.papers:
            slots, level = paper["slots"], bp.LEVELS[len(paper["relaxed"])]
            with self.subTest(seed=paper["seed"]):
                self.assertEqual(len(slots), 20)
                self.assertEqual(bp.violations(slots, level), [])
                self.assertEqual(max(Counter(bp.wording(s) for s in slots).values()), 1)
                formats = Counter(s.get("option_format") for s in slots)
                self.assertIn(formats["interval"], (1, 2))
                self.assertLessEqual(formats["direction"], 1)
                forms = Counter(f for f in map(bp.answer_form, slots) if f)
                self.assertLessEqual(max(forms.values(), default=0), bp.FORM_CAP, forms)
                validate_ziliao_paper_answers([[s["answer_key"] for s in slots[m * 5:m * 5 + 5]] for m in range(4)])

    def test_no_leaking_pairs_and_few_ratio_asks(self):
        for paper in self.papers:
            slots = paper["slots"]
            ratio = [i for i, s in enumerate(slots) if bp.asks_ratio(s)]
            self.assertLessEqual(len(ratio), bp.RATIO_CAP)
            self.assertLessEqual(max(Counter(i // 5 for i in ratio).values(), default=0), 1)
            for m in range(4):
                self.assertFalse({"average", "average_diff"} <= {s.get("kind") for s in slots[m * 5:m * 5 + 5]})

    def test_rarely_relaxes(self):
        relaxed = sum(bool(p["relaxed"]) for p in self.papers)
        self.assertLess(relaxed, len(self.papers) * 0.1)

    def test_entity_answers_stay_exact(self):
        for paper in self.papers:
            for slot in paper["slots"]:
                if bp.entity_answer(slot):
                    self.assertEqual(slot.get("option_format"), "exact", slot.get("kaofa_variant_name"))
        slot = {"kaofa_variant_name": "多主体增速比较", "brief": "本题考法变式：多主体增速比较。比较同比增长率最高或最低者"}
        self.assertTrue(bp.entity_answer(slot))

    def test_same_seed_same_blueprint(self):
        again = bp.build_blueprint(seed="s0", output_dir=self.root / "none", db=self.root / "none.db",
                                   catalog=self.catalog, ledger=self.root / "l.jsonl")
        strip = lambda p: [bp.plan_slot(s) | {"answer_key": s["answer_key"]} for s in p["slots"]]
        self.assertEqual(strip(again), strip(self.papers[0]))

    def test_plan_slot_hides_blueprint_fields(self):
        slot = self.papers[0]["slots"][0]
        self.assertTrue(set(bp.BLUEPRINT_ONLY) & set(slot))
        self.assertFalse(set(bp.BLUEPRINT_ONLY) & set(bp.plan_slot(slot)))


class RotationTest(unittest.TestCase):
    def test_only_imported_papers_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("imported", "failed"):
                (root / name).mkdir()
                (root / name / "M01-plan.json").write_text(json.dumps(
                    {"theme_key": name, "slots": [{"kind": "share"}]}))
            conn = sqlite3.connect(root / "exam.db")
            conn.execute("CREATE TABLE questions(batch_id TEXT)")
            conn.execute("INSERT INTO questions VALUES ('imported')")
            conn.commit()
            conn.close()
            dirs = bp.imported_dirs(root, root / "exam.db", 6)
        self.assertEqual([d.name for d in dirs], ["imported"])


class BlueprintAnswersTest(unittest.TestCase):
    def test_redistribution_follows_blueprint_letters(self):
        questions = [{"external_id": f"b-M0{i // 5 + 1}-Q{i % 5 + 1}", "material_id": f"b-M0{i // 5 + 1}",
                      "category": "资料分析", "stem": "s", "answer": "B", "explanation": "故选B",
                      "options": [{"key": k, "text": k} for k in "ABCD"]} for i in range(20)]
        planned = list("ABCDA" "ABCDB" "ABCDA" "BCCDD")
        nab.redistribute_answers(questions, {"batch_id": "b", "generation": {}}, {}, None, planned)
        self.assertEqual([q["answer"] for q in questions], planned)


if __name__ == "__main__":
    unittest.main()

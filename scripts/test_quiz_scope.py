"""Exercise live content edits through Node and the actual Python quiz entrypoints."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kaodian_profile import coverage_report, ensure_schema, register_knowledge_point
from quiz_generator import resolve_slots
from quiz_lite import writer_prompt
from quiz_scope import catalog, register_slots, resolve_scope_tag, scope_slots, source_topic

ROOT = Path(__file__).resolve().parents[1]
ENGINEERING = "数量关系-数学运算-工程问题"
EXTREME = "数量关系-数学运算-最值问题"


class QuizScopeIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "exam.db")
        environment = patch.dict(os.environ, EXAM_DB=self.db,
                                 EXAM_KNOWLEDGE_DB=str(Path(self.tmp.name) / "knowledge.db"))
        environment.start()
        self.addCleanup(environment.stop)
        with sqlite3.connect(self.db) as conn:
            ensure_schema(conn)

    def mutate(self, patches):
        script = """
          import { openKnowledgeStore } from './server/knowledgeContent.js';
          const [tag, input] = process.argv.slice(1);
          const store = openKnowledgeStore();
          try {
            for (const patch of JSON.parse(input)) {
              store.mutate(tag, { revision: store.get(tag).revision, ...patch });
            }
            console.log(JSON.stringify(store.get(tag)));
          } finally { store.close(); }
        """
        result = subprocess.run(["node", "--input-type=module", "-e", script, ENGINEERING,
                                 json.dumps(patches, ensure_ascii=False)], cwd=ROOT,
                                check=True, text=True, capture_output=True)
        return json.loads(result.stdout)

    def test_engineering_split_rename_archive_and_zero_evidence(self):
        self.assertEqual([(s["tag"], s["count"]) for s in scope_slots(ENGINEERING, 6)],
                         [(ENGINEERING, 6)])
        doc = self.mutate([])
        generic = next(n for n in doc["nodes"] if n["parentId"] == "overview")
        titles = {"alternating": "交替合作", "changing": "效率变化", "stages": "分段施工"}
        self.mutate([{"op": "create", "id": ident, "parentId": generic["id"], "title": title,
                      "summary": title + "：按各阶段工作量建立等式，与另外两种施工模型区分。"}
                     for ident, title in titles.items()])
        slots = scope_slots(ENGINEERING, 6)
        expected = {ENGINEERING + "-@" + ident for ident in titles}
        self.assertEqual({s["tag"] for s in slots}, expected)
        self.assertEqual([s["count"] for s in slots], [2, 2, 2])
        self.assertTrue(all(s["content_revision"] == 3 for s in slots))
        self.assertEqual(source_topic('数量关系', slots), '工程问题')
        self.assertEqual(source_topic('数量关系', scope_slots(ENGINEERING, 1)), '工程问题')
        self.assertEqual(source_topic('数量关系', scope_slots('交替合作', 1)), '工程问题-交替合作')
        for slot in slots:
            neighbors = {n['tag'] for n in slot['sibling_topics']}
            self.assertIn('数量关系-数学运算-牛吃草问题', neighbors)
            self.assertEqual(neighbors & expected, expected - {slot['tag']})
        self.assertEqual([(s["tag"], s["count"]) for s in scope_slots("交替合作", 5)],
                         [(ENGINEERING + "-@alternating", 5)])
        self.assertEqual(resolve_scope_tag("请只出五道工程问题的交替合作"), ENGINEERING + "-@alternating")
        register_slots(slots, self.db)
        register_slots(slots, self.db)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*), SUM(attempts) FROM kaodian_profile").fetchone(), (3, 0))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM kaodian_events").fetchone()[0], 0)
        old_path = ENGINEERING + "-" + generic["title"] + "-交替合作"
        self.mutate([{"op": "update", "id": "alternating", "title": "轮流施工"}])
        renamed = scope_slots(ENGINEERING, 3)
        self.assertTrue(any(n['title'] == '轮流施工' for s in renamed for n in s['sibling_topics']))
        self.assertEqual(source_topic('数量关系', scope_slots(old_path, 1)), '工程问题-轮流施工')
        for request in [old_path, "轮流施工", ENGINEERING + "-@alternating"]:
            self.assertEqual(scope_slots(request, 2)[0]["tag"], ENGINEERING + "-@alternating")
        self.mutate([{"op": "archive", "id": ident} for ident in titles])
        with self.assertRaisesRegex(ValueError, "没有可出题"):
            scope_slots(ENGINEERING, 6)
        with self.assertRaisesRegex(ValueError, "停用"):
            scope_slots(ENGINEERING + "-@alternating", 1)

    def test_five_modules_exact_extreme_and_unknown_path(self):
        nodes = catalog()
        for module in ["政治理论", "常识判断", "言语理解与表达", "数量关系", "判断推理"]:
            with self.subTest(module=module):
                slots = scope_slots(module, 15, nodes=nodes)
                self.assertEqual(sum(s["count"] for s in slots), 15)
                self.assertTrue(all(s["tag"].startswith(module + "-") for s in slots))
                self.assertTrue(all(not any(x in s["tag"] for x in ["图形推理", "科学推理", "空间类"])
                                    for s in slots))
        slots = scope_slots(EXTREME, 6, nodes=nodes)
        self.assertEqual({s["tag"] for s in slots}, {EXTREME + "-@" + ident for ident in
                         ["extreme-heding", "extreme-drawer", "extreme-reverse-construct"]})
        self.assertEqual([s["count"] for s in slots], [2, 2, 2])
        self.assertEqual(resolve_scope_tag("来五道逻辑填空-实词填空"), "言语理解与表达-逻辑填空-实词填空")
        with self.assertRaisesRegex(ValueError, "未知完整知识点"):
            scope_slots(ENGINEERING + "-从未登记的施工考法", 3, nodes=nodes)

    def test_blueprint_uses_renamed_parent_and_current_child_titles(self):
        self.mutate([
            {"op": "update", "id": "overview", "title": "工程与合作"},
            {"op": "create", "id": "stages", "parentId": "overview", "title": "分段合作"},
            {"op": "create", "id": "changes", "parentId": "overview", "title": "效率变化 · 计划与实际"},
        ])
        raw = [{"tag": ENGINEERING + '-@' + node, "count": 1} for node in ['stages', 'changes']]
        module, slots = resolve_slots(argparse.Namespace(
            module='数量关系', tag=None, count=None, blueprint=json.dumps({'slots': raw}), difficulty=None))
        self.assertEqual(source_topic(module, slots), '工程与合作')
        self.assertEqual(source_topic(module, slots[1:]), '工程与合作-效率变化 · 计划与实际')
        self.assertEqual(source_topic(module, scope_slots(ENGINEERING, 1)), '工程与合作')
        selected = scope_slots(ENGINEERING, 1)[0]['tag']
        mixed = [{'tag': ENGINEERING, 'count': 1}, {'tag': selected, 'count': 1}]
        _, slots = resolve_slots(argparse.Namespace(
            module=module, tag=None, count=None, blueprint=json.dumps({'slots': mixed}), difficulty=None))
        self.assertEqual(source_topic(module, slots), '工程与合作')

    def test_unknown_full_path_in_a_sentence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "未知完整知识点"):
            resolve_scope_tag("给我出三道" + ENGINEERING + "-从未登记的施工考法")
        self.assertEqual(resolve_scope_tag(ENGINEERING + "出5道"), ENGINEERING)
        self.assertEqual(resolve_scope_tag("请针对" + EXTREME + "-和定最值与构造出五道题"),
                         EXTREME + "-@extreme-heding")

    def test_short_unique_legal_leaf_is_recognized_in_speech(self):
        nodes = catalog()
        for title in ["宪法", "刑法"]:
            expected = [tag for tag, node in nodes.items() if node["title"] == title]
            self.assertEqual(len(expected), 1)
            self.assertEqual(resolve_scope_tag("请出三道" + title), expected[0])

    def test_merge_redirects_old_names_and_keeps_destination_definition(self):
        old = EXTREME + "-和定最值与构造"
        new = EXTREME + "-最不利原则与抽屉"
        target = EXTREME + "-@extreme-drawer"
        with sqlite3.connect(self.db) as conn:
            # Reverse insertion order catches a source definition overwriting its destination.
            register_knowledge_point(conn, new, "数量关系", "数学运算", "目标定义：最坏情况加一")
            register_knowledge_point(conn, old, "数量关系", "数学运算", "旧定义：整数排序构造")
            conn.execute("UPDATE kaodian_aliases SET canonical=? WHERE alias=?", (new, old))
            nodes = catalog(conn)
            self.assertEqual(nodes[target]["definition"], "目标定义：最坏情况加一")
            self.assertEqual({s["tag"] for s in scope_slots(EXTREME, 6, nodes=nodes)},
                             {target, EXTREME + "-@extreme-reverse-construct"})
        for request in [old, "和定最值与构造", "请出两道和定最值与构造", EXTREME + "-@extreme-heding"]:
            with self.subTest(request=request):
                self.assertEqual(resolve_scope_tag(request), target)

    def test_stable_profile_snapshot_does_not_override_current_content(self):
        tag = EXTREME + "-@extreme-heding"
        current = catalog()[tag]["definition"]
        with sqlite3.connect(self.db) as conn:
            register_knowledge_point(conn, tag, "数量关系", "数学运算", "旧出题快照：已经过期")
            self.assertEqual(catalog(conn)[tag]["definition"], current)

    def test_semantic_registration_keeps_custom_boundaries(self):
        semantic = EXTREME + "-和定最值与构造"
        stable = EXTREME + "-@extreme-heding"
        with sqlite3.connect(self.db) as conn:
            register_knowledge_point(conn, semantic, "数量关系", "数学运算", "明确登记：只考可重复整数的排序界")
            register_knowledge_point(conn, stable, "数量关系", "数学运算", "旧出题快照：已经过期")
            self.assertEqual(catalog(conn)[stable]["definition"], "明确登记：只考可重复整数的排序界")

    def test_l3_registration_and_live_overview_reach_writer(self):
        registered = "只考已给效率比的工作总量，不考交替施工。"
        with sqlite3.connect(self.db) as conn:
            register_knowledge_point(conn, ENGINEERING, "数量关系", "数学运算", registered)
        slots = scope_slots(ENGINEERING, 3)
        self.assertEqual(slots[0]["tag"], ENGINEERING)
        self.assertEqual(slots[0]["definition"], registered)
        run = {"module": "数量关系", "batch_id": "scope-test", "slots": slots}
        self.assertIn(registered, writer_prompt(run, slots, []))

        summary = "只考单队效率变化，不考交替施工或已给效率比。"
        markdown = "## 当前边界\n按前后两段工作量建方程，必须交代提效时间。"
        self.mutate([{"op": "update", "id": "overview", "summary": summary, "markdown": markdown}])
        current = catalog()[ENGINEERING]["definition"]
        slots = scope_slots(ENGINEERING, 3)
        self.assertEqual(slots[0]["definition"], current)
        self.assertIn(summary, current)
        self.assertIn(markdown, current)
        self.assertNotIn(registered, current)
        run = {"module": "数量关系", "batch_id": "scope-test-updated", "slots": slots}
        prompt = writer_prompt(run, slots, [])
        self.assertIn(summary, prompt)
        payload = json.loads(prompt.splitlines()[1])
        self.assertIn(markdown, payload['topic_definitions'][ENGINEERING])
        self.assertNotIn(registered, prompt)

    def test_default_shared_verbal_card_does_not_expand_scope(self):
        nodes = catalog()
        for title in ["中心理解题", "标题填入题", "细节判断题", "语句排序题", "接语选择题"]:
            tag = "言语理解与表达-片段阅读-" + title
            if title in {"语句排序题", "接语选择题"}:
                tag = "言语理解与表达-语句表达-" + title
            with self.subTest(tag=tag):
                slots = scope_slots(tag, 2, nodes=nodes)
                self.assertEqual([s["tag"] for s in slots], [tag])
                self.assertEqual(slots[0]["definition"], nodes[tag]["definition"])
                run = {"module": "言语理解与表达", "batch_id": "scope-test-verbal", "slots": slots}
                prompt = writer_prompt(run, slots, [])
                self.assertIn(f"范围：{tag}；当前考点：{title}", prompt)
                self.assertNotIn("## 考场步骤", slots[0]["definition"])

    def test_alias_cycles_fail_closed_and_identity_is_valid(self):
        old = EXTREME + "-和定最值与构造"
        new = EXTREME + "-最不利原则与抽屉"
        with sqlite3.connect(self.db) as conn:
            register_knowledge_point(conn, old, "数量关系", "数学运算", "和定定义")
            register_knowledge_point(conn, new, "数量关系", "数学运算", "抽屉定义")
            self.assertEqual(len(scope_slots(EXTREME, 6, nodes=catalog(conn))), 3)
            conn.execute("UPDATE kaodian_aliases SET canonical=? WHERE alias=?", (new, old))
            conn.execute("UPDATE kaodian_aliases SET canonical=? WHERE alias=?", (old, new))
            with self.assertRaisesRegex(ValueError, "循环"):
                catalog(conn)

    def test_coverage_reports_all_leaves_beyond_quiz_limit(self):
        nodes = catalog()
        expected = {s["tag"] for s in scope_slots("数量关系", 15, nodes=nodes, all_leaves=True)}
        self.assertGreater(len(expected), 15)
        with sqlite3.connect(self.db) as conn:
            actual = {row["tag"] for card in coverage_report(conn, "数量关系") for row in card["rows"]}
        self.assertEqual(actual, expected)

    def test_node_database_startup_preserves_registered_zero_attempt_topics(self):
        slots = scope_slots(EXTREME, 6)
        register_slots(slots, self.db)
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO kaodian_profile(kaodian,module,subtype) VALUES (?,?,?)",
                         (ENGINEERING + "-empty-placeholder", "数量关系", "数学运算"))
            conn.execute("INSERT INTO kaodian_profile(kaodian,module,subtype,note) VALUES (?,?,?,?)",
                         (ENGINEERING + "-legacy-note", "数量关系", "数学运算", "旧版登记的效率定义"))
        # import-batch opens this module before validating dynamic tags in its Python child.
        subprocess.run(["node", "--input-type=module", "-e",
                        "import db from './server/db.js'; db.close();"],
                       cwd=ROOT, check=True, text=True, capture_output=True)
        from kaodian_taxonomy import validate_ai_primary_tag
        with sqlite3.connect(self.db) as conn:
            for slot in slots:
                self.assertEqual(conn.execute("SELECT definition,attempts FROM kaodian_profile WHERE kaodian=?",
                                              (slot["tag"],)).fetchone(), (slot["definition"][:4000], 0))
                self.assertEqual(validate_ai_primary_tag(slot["tag"], "数量关系"), slot["tag"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM kaodian_profile WHERE kaodian=?",
                                          (ENGINEERING + "-empty-placeholder",)).fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT note FROM kaodian_profile WHERE kaodian=?",
                                          (ENGINEERING + "-legacy-note",)).fetchone()[0], "旧版登记的效率定义")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM kaodian_events").fetchone()[0], 0)

    def test_explicit_difficulty_and_counts_survive_scope_expansion(self):
        slots = [{"tag": EXTREME, "count": 6, "difficulty": "easy", "brief": "先练基础构造"},
                 {"tag": EXTREME + "-和定最值与构造", "count": 2, "difficulty": "mid"},
                 {"tag": EXTREME + "-最不利原则与抽屉", "count": 1, "difficulty": "hard"}]
        module, expanded = resolve_slots(argparse.Namespace(
            module="数量关系", tag=None, count=None, blueprint=json.dumps({"slots": slots}), difficulty=None))
        self.assertEqual(module, "数量关系")
        totals = {level: sum(s["count"] for s in expanded if s["difficulty"] == level)
                  for level in ["easy", "mid", "hard"]}
        self.assertEqual(totals, {"easy": 6, "mid": 2, "hard": 1})
        self.assertEqual(len([s for s in expanded if s["difficulty"] == "easy"]), 3)
        self.assertTrue(all(s["brief"] == "先练基础构造" for s in expanded if s["difficulty"] == "easy"))
        self.assertEqual(expanded[-1]["tag"], EXTREME + "-@extreme-drawer")

    def test_repeated_parent_difficulty_slots_balance_over_all_children(self):
        raw = [{"tag": scope, "count": 2, "difficulty": level}
               for scope, level in [(EXTREME, "easy"), ("最值问题", "mid"), (EXTREME, "hard")]]
        _, expanded = resolve_slots(argparse.Namespace(
            module="数量关系", tag=None, count=None, blueprint=json.dumps({"slots": raw}), difficulty=None))
        tags = {EXTREME + "-@" + ident for ident in
                ["extreme-heding", "extreme-drawer", "extreme-reverse-construct"]}
        self.assertEqual({tag: sum(s["count"] for s in expanded if s["tag"] == tag) for tag in tags},
                         dict.fromkeys(tags, 2))
        self.assertEqual({level: sum(s["count"] for s in expanded if s["difficulty"] == level)
                          for level in ["easy", "mid", "hard"]}, {"easy": 2, "mid": 2, "hard": 2})


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""程序出图题：出题→落盘→签收据→闸门复核整条链，以及 quiz_lite 转发。只用临时目录和临时库，不入正式题库。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import figure_quiz  # noqa: E402
from generation_gate import verify  # noqa: E402


def args_for(**kw):
    base = dict(module="", tag=None, count=None, blueprint=None, batch_id="t", difficulty=None, rounds=3,
                output_dir=None, db=None, no_import=True, plan_only=False)
    base.update(kw)
    return argparse.Namespace(**base)


class FigurePipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="figure-pipeline-"))
        cls.db = Path(os.environ.get("EXAM_DB") or cls.tmp / "exam.db")
        args = args_for(tag="判断推理-图形推理-空间类", count=4, batch_id="20261015_test_空间_01",
                        output_dir=cls.tmp / "out", db=cls.db)
        code = figure_quiz.run(args)
        assert code == 0, "figure_quiz 应能出题并通过闸门"
        cls.batch = next((cls.tmp / "out").glob("*/20261015_test_空间_01"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy(self, name):
        dest = self.tmp / name
        shutil.copytree(self.batch, dest)
        return dest

    def test_signed_batch_verifies(self):
        result = verify(self.batch)
        self.assertTrue(result["ok"])
        self.assertEqual(result["question_count"], 4)
        questions = json.loads((self.batch / "questions.json").read_text(encoding="utf-8"))
        manifest = json.loads((self.batch / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["generation"]["pipeline"], "figure_quiz")
        self.assertTrue(all(q["figure"]["family"] for q in questions))
        self.assertTrue(all(q["explanation"] for q in questions))
        self.assertEqual({q["tags"][0] for q in questions} >= {"判断推理-图形推理-空间类-六面体"}, True)

    def test_changed_answer_is_rejected(self):
        dest = self.copy("tamper-answer")
        questions = json.loads((dest / "questions.json").read_text(encoding="utf-8"))
        questions[0]["answer"] = "A" if questions[0]["answer"] != "A" else "B"
        (dest / "questions.json").write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ValueError):
            verify(dest)

    def test_changed_image_is_rejected(self):
        dest = self.copy("tamper-image")
        image = sorted((dest / "images").glob("*-options.png"))[0]
        data = bytearray(image.read_bytes())
        data[-20] ^= 0xFF
        image.write_bytes(bytes(data))
        with self.assertRaises(ValueError):
            verify(dest)

    def test_resigned_wrong_answer_still_fails_judge(self):
        """连收据一起重签也不行：闸门会让判题器重新读图判一遍。"""
        dest = self.copy("tamper-resign")
        questions = json.loads((dest / "questions.json").read_text(encoding="utf-8"))
        questions[1]["answer"] = "A" if questions[1]["answer"] != "A" else "B"
        (dest / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            figure_quiz.sign(dest, "20261015_test_空间_01", questions, [])

    def test_routing(self):
        self.assertTrue(figure_quiz.is_figure_request(args_for(tag="判断推理-图形推理-空间类-六面体", count=3)))
        self.assertTrue(figure_quiz.is_figure_request(args_for(tag="判断推理-图形推理", count=3)))
        self.assertFalse(figure_quiz.is_figure_request(args_for(tag="判断推理-逻辑判断-翻译推理", count=3)))
        self.assertFalse(figure_quiz.is_figure_request(args_for(module="判断推理", tag=None)))
        mixed = json.dumps({"slots": [{"tag": "判断推理-图形推理-黑白块类", "count": 1},
                                      {"tag": "判断推理-逻辑判断-翻译推理", "count": 1}]}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            figure_quiz.is_figure_request(args_for(blueprint=mixed))

    def test_plan_spreads_parent_scope(self):
        module, slots = figure_quiz.plan(args_for(tag="判断推理-图形推理-空间类", count=6))
        self.assertEqual(module, "判断推理")
        self.assertEqual(sum(s["count"] for s in slots), 6)
        self.assertGreaterEqual(len({s["family"] for s in slots}), 3)
        with self.assertRaises(ValueError):
            figure_quiz.plan(args_for(tag="判断推理-图形推理-不存在的题型", count=2))


if __name__ == "__main__":
    unittest.main()

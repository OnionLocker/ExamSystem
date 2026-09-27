#!/usr/bin/env python3
"""Offline regression: rejected drafts cannot corrupt an accepted material/receipt."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from ziliao_agent_trial import Trial, verify
from ziliao_agent_paper import sync_reviewed_version


def main():
    with tempfile.TemporaryDirectory() as directory:
        trial = Trial(Path(directory) / "trial", Path(directory) / "unused.db")
        candidate = {"content": "甲114.4亿元、乙86.2亿元，合计200.5亿元。因四舍五入，分项和与合计略有差异。",
                     "figure": {"kind": "bars", "categories": ["甲", "乙", "丙", "丁"],
                     "series": [{"name": "数值", "values": [21.3, 37.8, 29.4, 58.1]}]},
                     "rounding_checks": [{"label": "收入", "unit": "亿元", "places": 1,
                       "parts": [{"label": "甲", "raw": "114.36", "shown": "114.4"},
                                 {"label": "乙", "raw": "86.16", "shown": "86.2"}],
                       "total": {"label": "合计", "raw": "200.52", "shown": "200.5"}}]}
        with patch("ziliao_agent_trial.runner.review_ziliao_material", return_value={"verdict": "PASS"}), \
             patch("ziliao_agent_trial.runner.render_material"):
            assert trial.submit_material(candidate)["ok"]
            (trial.out / ".gate.json").write_text("old receipt")
            with patch("ziliao_agent_trial.runner.review_ziliao_material", return_value={"verdict": "REJECT"}):
                assert not trial.submit_material(candidate)["ok"]
            assert (trial.out / ".gate.json").read_text() == "old receipt"
            invalid = json.loads(trial.invoke("put_questions", {"questions": [{"external_id": "foreign-Q1"}], "calculations": []}))
            assert not invalid["ok"] and (trial.out / ".gate.json").exists()
            trial.questions = {"old-Q1": {"external_id": "old-Q1"}}
            trial.calculations = {"old-Q1": {"question_id": "old-Q1"}}
            assert trial.submit_material(candidate)["ok"]
            assert not trial.questions and not trial.calculations
            assert not (trial.out / ".gate.json").exists()
            assert json.loads((trial.out / "questions.json").read_text()) == []
            try:
                verify(trial.out)
            except ValueError:
                pass
            else:
                raise AssertionError("No receipt must never count as success")
        print("PASS: rejection preserves state; material replacement invalidates all dependent artifacts")
        parent = Path(directory) / "paper"
        parent.mkdir()
        questions = [{"external_id": f"paper-M02-Q{i}", "material_id": "paper-M02",
                      "answer": "C"} for i in range(1, 6)]
        calculations = {"questions": [{"question_id": q["external_id"], "options": {"C": 1}} for q in questions]}
        (parent / "questions.json").write_text(json.dumps(questions))
        (parent / "calculations.json").write_text(json.dumps(calculations))
        (trial.out / ".gate.json").write_text("old")
        sync_reviewed_version(parent, trial.out, "M02", 1)
        assert json.loads((trial.out / "questions.json").read_text())[0]["answer"] == "C"
        assert json.loads((trial.out / "calculations.json").read_text()) == calculations
        assert not (trial.out / ".gate.json").exists()
        assert (trial.out / "before-full-repair-1/.gate.json").read_text() == "old"
        print("PASS: full-paper option normalization is synchronized before repair, old receipt invalidated")


if __name__ == "__main__":
    main()

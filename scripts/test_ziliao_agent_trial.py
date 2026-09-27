#!/usr/bin/env python3
"""Offline regression: rejected drafts cannot corrupt an accepted material/receipt."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from ziliao_agent_trial import Trial, verify


def main():
    with tempfile.TemporaryDirectory() as directory:
        trial = Trial(Path(directory) / "trial", Path(directory) / "unused.db")
        candidate = {"content": "统计正文", "figure": {"kind": "bars", "categories": ["甲", "乙", "丙", "丁"],
                     "series": [{"name": "数值", "values": [21.3, 37.8, 29.4, 58.1]}]}}
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


if __name__ == "__main__":
    main()

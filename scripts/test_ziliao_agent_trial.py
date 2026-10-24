#!/usr/bin/env python3
"""Offline regression: rejected drafts cannot corrupt an accepted material/receipt."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

from ziliao_agent_trial import Trial, verify
from ziliao_agent_paper import import_checked
from ziliao_tracks import ZILIAO_SHARE

PLAN = {"id": "M01", "track": "gd", "difficulty": "mid", "format": "chart", "figure_kind": "bars",
        "slots": [{"tag": ZILIAO_SHARE, "kind": "share", "family": "share_add", "brief": "比重"} for _ in range(5)]}


def main():
    with tempfile.TemporaryDirectory() as directory:
        trial = Trial(Path(directory) / "trial", Path(directory) / "unused.db", PLAN)
        candidate = {"content": "广州市甲114.4亿元、乙86.2亿元，合计200.5亿元。",
                     "figure": {"kind": "bars", "categories": ["甲", "乙", "丙", "丁"],
                     "series": [{"name": "数值", "values": [21.3, 37.8, 29.4, 58.1]}]},
                     "rounding_checks": [{"label": "收入", "unit": "亿元", "places": 1,
                       "parts": [{"label": "甲", "raw": "114.36", "shown": "114.4"},
                                 {"label": "乙", "raw": "86.16", "shown": "86.2"}],
                       "total": {"label": "合计", "raw": "200.52", "shown": "200.5"}}]}
        with patch("ziliao_agent_trial.runner.review_ziliao_material", return_value={"verdict": "PASS"}), \
             patch("ziliao_agent_trial.runner.render_material"):
            placeholder = dict(candidate, content=candidate["content"].replace("广州市", "G省"))
            assert "占位地名" in json.dumps(trial.submit_material(placeholder), ensure_ascii=False)
            trial.plan["figure_shape"] = "years"
            assert "时间序列" in json.dumps(trial.submit_material(candidate), ensure_ascii=False)
            trial.plan["figure_shape"] = None
            assert trial.material_reviews == 0
            assert trial.submit_material(candidate)["ok"]
            (trial.out / ".gate.json").write_text("old receipt")
            with patch("ziliao_agent_trial.runner.review_ziliao_material", return_value={"verdict": "REJECT"}):
                assert not trial.submit_material(candidate)["ok"]
            assert (trial.out / ".gate.json").read_text() == "old receipt"
            try:
                trial.put_questions([{"external_id": "foreign-Q1"}], [])
            except ValueError:
                pass
            else:
                raise AssertionError("foreign question id must be refused")
            assert (trial.out / ".gate.json").exists()
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
        with patch("ziliao_agent_paper.verify", side_effect=ValueError("stale receipt")), \
             patch("ziliao_agent_paper.subprocess.run") as importer:
            try:
                import_checked(trial.out, trial.db)
            except ValueError:
                pass
            else:
                raise AssertionError("Stale receipt must block import")
            importer.assert_not_called()
        for receipt in ({}, {"question_count": 0}, {"question_count": "1"}, {"question_count": True}):
            with patch("ziliao_agent_paper.verify", return_value=receipt), \
                 patch("ziliao_agent_paper.subprocess.run") as importer:
                try:
                    import_checked(trial.out, trial.db)
                except (KeyError, ValueError):
                    pass
                else:
                    raise AssertionError("Invalid question count must block import before any write")
                importer.assert_not_called()
        with patch("ziliao_agent_paper.verify", return_value={"question_count": 1}), \
             patch("ziliao_agent_paper.subprocess.run", return_value=SimpleNamespace(
                 returncode=0, stdout="imported", stderr="")) as importer:
            assert import_checked(trial.out, trial.db) == 1
            assert importer.call_args.kwargs["env"]["EXAM_DB"] == str(trial.db.resolve())
        with patch("ziliao_agent_paper.verify", return_value={"question_count": 1}), \
             patch("ziliao_agent_paper.subprocess.run", return_value=SimpleNamespace(
                 returncode=1, stdout="", stderr="database error")):
            try:
                import_checked(trial.out, trial.db)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Import failure must not be reported as success")
        print("PASS: import requires current receipt, uses selected database, propagates failure")

if __name__ == "__main__":
    main()

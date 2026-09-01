"""Locate Hermes quiz/coach skills.

Cloud agents only see this Git repo. The checked-in copy under
``hermes-skills/`` is the source of truth. A local Hermes install may
still keep the same files under ``~/.hermes/skills/``; we prefer the
repo copy when it exists.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_SKILLS = ROOT / "hermes-skills"


def _first_dir(*candidates: Path) -> Path:
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def quiz_pipeline_dir() -> Path:
    return _first_dir(
        REPO_SKILLS / "quiz-pipeline",
        Path.home() / ".hermes" / "skills" / "kaogong" / "quiz-pipeline",
    )


def quiz_pipeline_references() -> Path:
    return quiz_pipeline_dir() / "references"


def coach_dir() -> Path:
    return _first_dir(
        REPO_SKILLS / "gd-gongkao-coach",
        Path.home() / ".hermes" / "skills" / "productivity" / "gd-gongkao-coach",
    )


def coach_references() -> Path:
    return coach_dir() / "references"

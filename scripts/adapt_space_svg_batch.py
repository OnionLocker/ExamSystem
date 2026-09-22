#!/usr/bin/env python3
"""Convert the old deterministic SVG runner output to the import batch format."""

import json
import sys
from pathlib import Path


ITEMS = [("01", "pieces"), ("02", "stem"), ("03", "stem"), ("05", "stem"), ("06", "stem")]


def main(batch_dir: str) -> None:
    root = Path(batch_dir)
    questions = []
    for number, stem_name in ITEMS:
        result = json.loads((root / number / "result.json").read_text())
        question = result["question"]
        prefix = f"q{number}"
        questions.append(
            {
                "external_id": f"space-svg-min-20260920-{number}",
                "category": "判断推理",
                "sub_category": "图形推理",
                "question_type": "single",
                "stem": question["stem"],
                "stem_images": [f"images/{prefix}-stem.png"],
                "options": [
                    {"key": key, "text": "", "images": [f"images/{prefix}-{key}.png"]}
                    for key in "ABCD"
                ],
                "answer": result["answer"],
                "explanation": question["analysis"],
                "difficulty": 4,
                "tags": ["判断推理-图形推理-空间类", f"空间推理-{result['kind']}"],
                "source": "Gemini旧SVG确定性渲染实验",
                "year": 2026,
                "region": "广东-模拟",
            }
        )

    manifest = {
        "batch_id": "20260920_hermes_space_svg_min_01",
        "source": "Gemini旧SVG确定性渲染实验",
        "region": "广东-模拟",
        "year": 2026,
        "kind": "illustrated-service",
        "module": "判断推理",
        "question_count": len(questions),
        "renderer": "figure_lab.py + Chromium PNG rasterization",
        "generation": {
            "model": "gemini-3.8-flash-high",
            "programmatic_solver": "OR-Tools CP-SAT / Shapely",
            "visual_reviews_per_question": 2,
            "attempts": 1,
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (root / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(questions)} questions to {root}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: adapt_space_svg_batch.py <batch-dir>")
    main(sys.argv[1])

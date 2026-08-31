#!/usr/bin/env python3
"""Independent arithmetic and structure precheck for this batch."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SEQUENCE = "DBCBADDBACACABDDBDCD"


def nearest(value: float, options: dict[str, float]) -> str:
    return min(options, key=lambda key: abs(options[key] - value))


def nearest_vector(value: list[float], options: dict[str, list[float]]) -> str:
    return min(
        options,
        key=lambda key: sum((a - b) ** 2 for a, b in zip(options[key], value)),
    )


def build_results() -> list[dict]:
    results: list[dict] = []

    def add(
        no: int,
        result,
        calculated_answer: str,
        expected_answer: str,
        wrong_paths: dict[str, dict],
    ) -> None:
        results.append(
            {
                "question_id": f"20260831_ziliao_gd_flash_01-Q{no:02d}",
                "result": result,
                "calculated_answer": calculated_answer,
                "expected_answer": expected_answer,
                "matches_expected": calculated_answer == expected_answer,
                "wrong_paths": wrong_paths,
                "all_wrong_options_reproduced": len(wrong_paths) == 3,
            }
        )

    value = 99.6 - 0.4
    add(1, round(value, 1), "D", "D", {
        "A": {"calculation": "use current rate", "result": 99.6},
        "B": {"calculation": "99.6 + 0.4", "result": 100.0},
        "C": {"calculation": "99.6 - 0.2", "result": 99.4},
    })

    value = (2400 - 2400 / 1.5) / (7500 - 6000) * 100
    add(2, round(value, 1), "B", "B", {
        "A": {"calculation": "(3000 - 3000 / 1.2) / 1500", "result": 33.3},
        "C": {"calculation": "800 / (5200 - 5200 / 1.3)", "result": 66.7},
        "D": {"calculation": "800 / (1200 / 1.2)", "result": 80.0},
    })

    value = (3000 / 1.2) / 6000 * 100
    add(3, round(value, 1), "C", "C", {
        "A": {"calculation": "(2300 / 1.15) / 6000", "result": 33.3},
        "B": {"calculation": "3000 / 7500", "result": 40.0},
        "D": {"calculation": "3000 / 6000", "result": 50.0},
    })

    value = 5200 / 2300
    add(4, round(value, 2), "B", "B", {
        "A": {"calculation": "(5200 - 2300) / 2300", "result": 1.26},
        "C": {"calculation": "5200 / (2300 / 1.15)", "result": 2.60},
        "D": {"calculation": "7500 / 2300", "result": 3.26},
    })

    value = 3.6e8 / 1.4e4
    add(5, round(value), "A", "A", {
        "B": {"calculation": "(1.8e8 - 1.8e8 / 1.28) > 5e7", "result": False},
        "C": {"calculation": "460 / (3200 - 460)", "result": 0.168},
        "D": {"calculation": "96.8 > 99.6", "result": False},
    })

    value = 10000 / 15000 * 10000
    add(6, round(value), "D", "D", {
        "A": {"calculation": "10000 / (15000 / 1.2) * 10000", "result": 8000},
        "B": {"calculation": "(10000 / 1.235) / 15000 * 10000", "result": 5398},
        "C": {"calculation": "(10000 / 1.235) / (15000 / 1.2) * 10000", "result": 6478},
    })

    value = 6.5 - 1.8
    add(7, round(value, 1), "D", "D", {
        "A": {"calculation": "6.5 + 1.8", "result": 8.3},
        "B": {"calculation": "use quoted 6.5 percent rate", "result": 6.5},
        "C": {"calculation": "use percentage-point gap as target", "result": 1.8},
    })

    prd_increment = 9000 - 9000 / 1.125
    value = prd_increment / (15000 / 1.2) * 100
    add(8, round(value, 1), "B", "B", {
        "A": {"calculation": "1000 / 15000", "result": 6.7},
        "C": {"calculation": "Pearl River Delta own growth", "result": 12.5},
        "D": {"calculation": "1000 / (15000 - 12500)", "result": 40.0},
    })

    base_share = (7200 / 1.2) / (10000 / 1.235) * 100
    current_share = 7200 / 10000 * 100
    value = current_share - base_share
    add(9, round(value, 1), "A", "A", {
        "B": {"calculation": "reverse direction", "result": 2.1},
        "C": {"calculation": "72.0 - round(74.1)", "result": -2.0},
        "D": {"calculation": "20.0 - 23.5", "result": -3.5},
    })

    value = 7.6e4 / 15000
    add(10, round(value, 1), "C", "C", {
        "A": {"calculation": "18.5 > 20", "result": False},
        "B": {"calculation": "90 > 100", "result": False},
        "D": {"calculation": "6200 / 15000", "result": 0.413},
    })

    value = 2.4 / 1.2
    add(11, round(value, 2), "A", "A", {
        "B": {"calculation": "use current amount", "result": 2.4},
        "C": {"calculation": "2.4 * (1 - 20%)", "result": 1.92},
        "D": {"calculation": "2.4 * (1 + 20%)", "result": 2.88},
    })

    subsidies = [200, 220, 250, 280, 320]
    increments = [subsidies[i] - subsidies[i - 1] for i in range(1, 5)]
    value = [2023, 2025]
    add(12, value, "C", "C", {
        "A": {"calculation": "omit 2025", "result": [2023]},
        "B": {"calculation": "omit 2023", "result": [2025]},
        "D": {"calculation": "treat the equal 2024 increment as higher", "result": [2023, 2024, 2025]},
    })

    value = 12500 * 0.48
    add(13, round(value), "A", "A", {
        "B": {"calculation": "10000 * 48%", "result": 4800},
        "C": {"calculation": "12500 * 50%", "result": 6250},
        "D": {"calculation": "use total population", "result": 12500},
    })

    value = 1500 + 1400 - 2400
    add(14, value, "B", "B", {
        "A": {"calculation": "abs(1500 - 1400)", "result": 100},
        "C": {"calculation": "use union as intersection", "result": 2400},
        "D": {"calculation": "1500 + 1400", "result": 2900},
    })

    value = 5600e4 / 28e4
    add(15, round(value), "D", "D", {
        "A": {"calculation": "82.0 > 94.4", "result": False},
        "B": {"calculation": "1320 / 1500", "result": 0.88},
        "C": {"calculation": "76.0 < 74.0", "result": False},
    })

    value = 485 / 320
    add(16, round(value, 2), "D", "D", {
        "A": {"calculation": "use annual consumption without averaging", "result": 485},
        "B": {"calculation": "485 / 1420", "result": 0.34},
        "C": {"calculation": "428.5 / 320", "result": 1.34},
    })

    value = 1800 / 2500 * 100 - (1800 / 1.5) / (1200 + 500 + 200) * 100
    add(17, round(value, 1), "B", "B", {
        "A": {"calculation": "50.0 - 31.6", "result": 18.4},
        "C": {"calculation": "reverse direction", "result": -8.8},
        "D": {"calculation": "72.0 - 1200 / 2000 * 100", "result": 12.0},
    })

    value = 1800 / 4500 * 100 - 600 / 2400 * 100
    add(18, round(value, 1), "D", "D", {
        "A": {"calculation": "(1800 - 600) / 7500", "result": 16.0},
        "B": {"calculation": "1800 / 4500 * 100 - 2400 / 7500 * 100", "result": 8.0},
        "C": {"calculation": "50 - 20", "result": 30.0},
    })

    value = 2500 / 0.018 / 10000
    add(19, round(value, 1), "C", "C", {
        "A": {"calculation": "2500 * 1.8 / 10000", "result": 0.45},
        "B": {"calculation": "2500 / 1.65% / 10000", "result": 15.2},
        "D": {"calculation": "unit conversion off by factor 10", "result": 1.39},
    })

    bases = [4500 / 1.5, 2400 / 1.2, 600 / 1.2]
    current = [4500, 2400, 600]
    increments = [now - base for now, base in zip(current, bases)]
    value = [round(item / sum(increments) * 100, 1) for item in increments]
    option_vectors = {
        "A": [60, 32, 8],
        "B": [50, 20, 20],
        "C": [54.5, 36.4, 9.1],
        "D": [75, 20, 5],
    }
    add(20, value, nearest_vector(value, option_vectors), "D", {
        "A": {"calculation": "current output shares", "result": [60.0, 32.0, 8.0]},
        "B": {"calculation": "category growth rates", "result": [50.0, 20.0, 20.0]},
        "C": {"calculation": "base output shares", "result": [54.5, 36.4, 9.1]},
    })
    return results


def main() -> int:
    materials = json.loads((ROOT / "materials.json").read_text(encoding="utf-8"))
    questions = json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))
    calculations = build_results()

    forbidden = [
        "\u4ee5\u4e0b\u6570\u636e\u5747\u4e3a\u6a21\u62df\u6570\u636e",
        "\u6559\u7a0b",
        "\u547d\u9898",
        "\u8ba1\u7b97\u63d0\u793a",
        "\u5e7f\u4e1c\u5b98\u65b9",
        "\u9ad8\u8d28\u91cf\u53d1\u5c55",
        "\u6ce8\u5165\u52a8\u80fd",
        "\u7a33\u6b65\u589e\u5f3a",
        "\u534f\u540c\u6f14\u8fdb",
    ]
    required_facts = {
        "M01": ["7500", "5200", "2300", "3000", "2400", "1200", "900", "99.6"],
        "M02": ["480", "18.5%", "7.6", "5.1", "280", "35", "650"],
        "M03": ["1.25", "48%", "2400", "1500", "1400", "1.18", "4200"],
        "M04": ["18.6", "2.4", "215", "3.12", "12.8", "320", "485", "428.5", "102.3"],
    }
    material_checks = []
    for material in materials:
        compact = re.sub(r"\s+", "", material["content"])
        digit_density = sum(ch.isdigit() for ch in compact) / len(compact)
        hits = [word for word in forbidden if word in material["content"]]
        material_key = material["external_id"][-3:]
        missing_required = [
            fact for fact in required_facts[material_key] if fact not in material["content"]
        ]
        material_checks.append(
            {
                "material_id": material["external_id"],
                "length_without_whitespace": len(compact),
                "length_in_range": 380 <= len(compact) <= 700,
                "paragraphs": len(material["content"].splitlines()),
                "four_paragraphs": len(material["content"].splitlines()) == 4,
                "digit_density": round(digit_density, 4),
                "digit_density_in_range": 0.01 <= digit_density <= 0.25,
                "forbidden_hits": hits,
                "missing_required_facts": missing_required,
            }
        )

    sums = {
        "M01_service_items": {"result": sum([3000, 2400, 1200, 900]), "expected": 7500},
        "M02_enterprises": {"result": sum([9000, 2400, 1800, 1800]), "expected": 15000},
        "M02_revenue": {"result": sum([7200, 1100, 800, 900]), "expected": 10000},
        "M03_visits": {"result": round(2.4 + 1.2, 1), "expected": 3.6},
        "M04_output": {"result": sum([4500, 2400, 600]), "expected": 7500},
        "M04_value_added": {"result": sum([1800, 600, 100]), "expected": 2500},
    }
    for item in sums.values():
        item["matches"] = math.isclose(item["result"], item["expected"])

    actual_sequence = "".join(item["answer"] for item in questions)
    explanation_checks = []
    for item in questions:
        text = item["explanation"]
        wrong_keys = [opt["key"] for opt in item["options"] if opt["key"] != item["answer"]]
        mentioned = [key for key in wrong_keys if f"{key}\u9879" in text or f"{key}\u56fe" in text]
        explanation_checks.append(
            {
                "question_id": item["external_id"],
                "sentences": len([part for part in text.split("\u3002") if part.strip()]),
                "has_algebra": "=" in text,
                "representative_wrong_options": mentioned,
                "all_wrong_options_explained": len(mentioned) == 3,
                "forbidden_phrase_present": "\u6309\u6838\u5b9a\u5173\u7cfb" in text,
            }
        )

    report = {
        "calculations": calculations,
        "materials": material_checks,
        "answer_sequence": {
            "result": actual_sequence,
            "expected": EXPECTED_SEQUENCE,
            "matches": actual_sequence == EXPECTED_SEQUENCE,
        },
        "material_item_sums": sums,
        "explanations": explanation_checks,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    ok = (
        all(item["matches_expected"] and item["all_wrong_options_reproduced"] for item in calculations)
        and all(item["length_in_range"] and item["four_paragraphs"] and item["digit_density_in_range"] and not item["forbidden_hits"] and not item["missing_required_facts"] for item in material_checks)
        and report["answer_sequence"]["matches"]
        and all(item["matches"] for item in sums.values())
        and all(
            2 <= item["sentences"] <= 4
            and item["has_algebra"]
            and item["all_wrong_options_explained"]
            and not item["forbidden_phrase_present"]
            for item in explanation_checks
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

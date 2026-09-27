#!/usr/bin/env python3
"""Regression cases reported in the user's audit; no network or model calls."""
from copy import deepcopy
from ziliao_checklist import rounding_issues, question_style_issues, explanation_math_issues


def main():
    material = {"content": "收入合计200.5亿元，其中甲114.4亿元、乙86.2亿元。因四舍五入，分项之和略有差异。",
                "rounding_checks": [{"label": "收入", "unit": "亿元", "places": 1,
                                    "parts": [{"label": "甲", "raw": "114.36", "shown": "114.4"},
                                              {"label": "乙", "raw": "86.16", "shown": "86.2"}],
                                    "total": {"label": "合计", "raw": "200.52", "shown": "200.5"}}]}
    assert not rounding_issues(material)
    fake = deepcopy(material)
    fake["rounding_checks"][0]["total"]["raw"] = "200.53"
    assert any("底层分项" in s for s in rounding_issues(fake))
    fake = deepcopy(material)
    fake["rounding_checks"][0]["parts"][0]["shown"] = "114.3"
    assert any("舍入" in s for s in rounding_issues(fake))
    fake = deepcopy(material)
    fake["content"] = "收入合计200.6亿元，其中甲114.4亿元、乙86.2亿元。因四舍五入，略有差异。"
    fake["rounding_checks"][0]["total"] = {"label": "合计", "raw": "200.62", "shown": "200.6"}
    fake["rounding_checks"][0]["parts"][0]["raw"] = "114.44"
    fake["rounding_checks"][0]["parts"][1]["raw"] = "86.18"
    assert any("全部展示" in s for s in rounding_issues(fake))
    assert question_style_issues({"family": "growth", "stem": "利润率比上年约增长多少？"})
    assert not question_style_issues({"family": "base_share", "stem": "利润率比上年上升多少个百分点？"})
    assert not question_style_issues({"family": "growth", "stem": "利润额比上年约增长多少？"})
    q = {"family": "mix_pull", "answer": "A", "options": [{"key": "A", "text": "5.0倍"}]}
    assert question_style_issues(q)
    q["options"][0]["text"] = "5.3倍"
    assert not question_style_issues(q)
    assert question_style_issues({"family": "chart_match"})
    assert explanation_math_issues("5468.2 / (1 + 8.5%) ≈ 5041.6亿元")
    assert not explanation_math_issues("5468.2 / (1 + 8.5%) ≈ 5039.8亿元")
    assert not explanation_math_issues("两期比重差约0.43个百分点，9.1%≈1/11。")
    assert not explanation_math_issues("1952.7 × 9.1% / (1 + 9.1%) ≈ 162.9亿元")
    assert not explanation_math_issues("1952.7/(11+1)=1952.7/12≈162.7亿元")
    assert not explanation_math_issues("9.2%+6.2%+9.2%×6.2%=15.4%+0.5704%≈15.97%")
    assert not explanation_math_issues("0.6405×0.7%/1.049≈0.43个百分点")
    print("PASS: genuine rounding, fake rounding, percentage-point wording, integer mixture, unsupported charts")


if __name__ == "__main__":
    main()

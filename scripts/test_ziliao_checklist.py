#!/usr/bin/env python3
"""Regression cases reported in the user's audit; no network or model calls."""
from copy import deepcopy
from ziliao_checklist import (rounding_issues, question_style_issues, explanation_math_issues,
                              material_text_issues, paper_issues)


def main():
    material = {"content": "收入合计200.5亿元，其中甲114.4亿元、乙86.2亿元。",
                "rounding_checks": [{"label": "收入", "unit": "亿元", "places": 1,
                                    "parts": [{"label": "甲", "raw": "114.36", "shown": "114.4"},
                                              {"label": "乙", "raw": "86.16", "shown": "86.2"}],
                                    "total": {"label": "合计", "raw": "200.52", "shown": "200.5"}}]}
    assert not rounding_issues(material)
    noted = deepcopy(material)
    noted["content"] += "注：涉及金额及增速均按现价计算；部分数据因四舍五入，分项之和与总计略有差异。"
    assert any("附注" in s for s in rounding_issues(noted))
    fake = deepcopy(material)
    fake["rounding_checks"][0]["total"]["raw"] = "200.53"
    assert any("底层分项" in s for s in rounding_issues(fake))
    fake = deepcopy(material)
    fake["rounding_checks"][0]["parts"][0]["shown"] = "114.3"
    assert any("舍入" in s for s in rounding_issues(fake))
    fake = deepcopy(material)
    fake["content"] = "收入合计200.6亿元，其中甲114.4亿元、乙86.2亿元。"
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

    assert any("占位地名" in s for s in material_text_issues({"content": "G省港口吞吐量12.4亿吨。"}))
    assert any("真实地名" in s for s in material_text_issues({"content": "全省港口吞吐量12.4亿吨。"}))
    assert any("人造口径句" in s for s in material_text_issues({"content": "广东省本次统计范围严格限定为规上企业。"}))
    assert any("过整" in s for s in material_text_issues({"content": "深圳增长12%、15%、20%、8.6%。"}))
    assert not material_text_issues({"content": "广东省港口货物吞吐量21.36亿吨，增长3.4%，其中广州港6.85亿吨、深圳港3.12亿吨。"})

    slot = {"family": "growth", "kind": "growth_rate"}
    good = {"family": "growth", "stem": "2025年深圳港集装箱吞吐量同比增长约多少？", "answer": "B",
            "options": [{"key": "A", "text": "4.2%"}, {"key": "B", "text": "6.7%"},
                        {"key": "C", "text": "7.9%"}, {"key": "D", "text": "9.4%"}],
            "explanation": "(3312.6-3104.5)/3104.5≈6.7%，选B。A项：(3312.6-3180)/3180≈4.2%取错基期；"
                           "C项：(3312.6-3070)/3070≈7.9%取错年份；D项：(3312.6-3028)/3028≈9.4%取错行。"}
    assert not question_style_issues(good, slot=slot), question_style_issues(good, slot=slot)
    vague = deepcopy(good)
    vague["explanation"] = "(3312.6-3104.5)/3104.5≈6.7%，选B。A、C、D项为计算失误所致。"
    issues = question_style_issues(vague, slot=slot)
    assert any("计算失误" in s for s in issues) and any("干扰项" in s for s in issues)
    close = deepcopy(good)
    close["options"][0]["text"] = "6.6%"
    assert any("过近" in s for s in question_style_issues(close, slot=slot))
    whole = deepcopy(good)
    whole["options"][1]["text"] = "25.0%"
    assert any("整数百分比" in s for s in question_style_issues(whole, slot={"family": "growth", "kind": "share"}))
    assert any("年均" in s for s in question_style_issues(good, slot={"family": "avg_cmp", "kind": "annual_growth"}))
    assert any("间隔增长率" in s for s in question_style_issues(good, slot={"family": "growth", "kind": "interval_growth"}))

    chart = {"external_id": "b-M03", "content": "广东省快递业务量持续增长。",
             "figure": {"kind": "bars", "categories": ["2021年", "2022年", "2023年", "2024年", "2025年"],
                        "series": [{"name": "业务量", "values": [295.6, 301.2, 338.9, 362.4, 401.7]}]}}
    annual = {"external_id": "b-M03-Q1", "material_id": "b-M03", "family": "avg_cmp",
              "explanation": "(401.7-295.6)/4≈26.5亿件。"}
    judge = {"external_id": "b-M03-Q5", "material_id": "b-M03", "family": "judge",
             "explanation": "①362.4-338.9=23.5；②材料未给出2020年数据，无法比较；③累计值不能当当年。"}
    slots = [{"kind": "annual_growth", "family": "avg_cmp"}, {"kind": "judge", "family": "judge"}]
    assert not paper_issues([chart], [annual, dict(judge, explanation="①362.4-338.9=23.5；②401.7÷295.6≈1.36。")], slots)
    found = paper_issues([chart], [annual, judge], slots)
    assert any("文字陷阱" in s for s in found), found
    unused = dict(annual, explanation="增长约26亿件。")
    assert any("图表独有数据" in s for s in paper_issues([chart], [unused], slots[:1]))
    print("PASS: placeholder places, artificial scope, vague distractors, close options, kind keywords, chart usage, judge traps")

    point = {"external_id": "p-M01-Q4", "family": "growth", "answer": "B",
             "stem": "2024年外贸货物吞吐量同比增速比内贸货物吞吐量同比增速：",
             "options": [{"key": "A", "text": "高1.6个百分点"}, {"key": "B", "text": "高2.4个百分点"},
                         {"key": "C", "text": "高3.2个百分点"}, {"key": "D", "text": "高48.0%"}],
             "explanation": "外贸增长7.4%，内贸增长5.0%，7.4%-5.0%=2.4个百分点。A项：误取1.6个百分点；"
                            "C项：1.6×2=3.2；D项：(7.4-5.0)/5.0=48.0%。"}
    point_slot = {"family": "growth", "kind": "percentage_point"}
    assert any("相对比值" in s for s in question_style_issues(point, slot=point_slot))
    ratio = deepcopy(point)
    ratio["options"][3]["text"] = "是内贸的1.48倍"
    assert any("相对比值" in s for s in question_style_issues(ratio, slot=point_slot))
    unit = deepcopy(point)
    unit["options"][3]["text"] = "高2.4%"
    unit["explanation"] = unit["explanation"].replace("D项：(7.4-5.0)/5.0=48.0%", "D项：7.4-5.0=2.4，混淆百分点与百分比")
    assert not question_style_issues(unit, slot=point_slot), question_style_issues(unit, slot=point_slot)

    def q(mid, n, family, stem, explanation="由材料直接读出。"):
        return {"external_id": f"x-M{mid:02d}-Q{n}", "material_id": f"x-M{mid:02d}", "family": family,
                "stem": stem, "explanation": explanation}
    paper = [q(m, n, "judge" if n == 5 else "growth", "同比增长约多少", "(12.4-11.2)/11.2≈10.7%")
             for m in range(1, 5) for n in range(1, 6)]
    paper[0] = q(1, 1, "detail", "深圳港集装箱吞吐量为多少万标准箱？")
    assert not any("读图排序" in s for s in paper_issues([], paper))
    paper[15] = q(4, 1, "share_add", "床位数排在第二位的是：", "城区13115张、松山湖8056张，第二位为松山湖。")
    assert any("读图排序" in s for s in paper_issues([], paper))
    paper[15] = q(4, 1, "growth", "同比增量最多的是：", "2024年：218.4-191.8=26.6亿元，最多。")
    assert not any("读图排序" in s for s in paper_issues([], paper))
    print("PASS: percentage-point distractor equal to relative ratio, paper-wide lookup/sort limit")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import random

from kaodian_taxonomy import (
    NUM_PERM_SPECIAL,
    ZILIAO_ALT_PACK,
    ZILIAO_BASE,
    ZILIAO_CMP,
    ZILIAO_DEFAULT_PACK,
    ZILIAO_SHARE_DIFF,
    assign_ziliao_answers,
    canonicalize,
    is_abcd_plus_one,
    question_primary_tag,
    validate_ai_primary_tag,
    validate_ziliao_paper_answers,
)
from learner_snapshot import select_ziliao_paper, select_ziliao_slots

assert question_primary_tag({"knowledge_points": [NUM_PERM_SPECIAL]}) == NUM_PERM_SPECIAL
assert question_primary_tag({"tags": [NUM_PERM_SPECIAL]}) == NUM_PERM_SPECIAL
assert validate_ai_primary_tag(NUM_PERM_SPECIAL, "数量关系") == NUM_PERM_SPECIAL
try:
    validate_ai_primary_tag("数量关系-数学运算-排列组合", "数量关系")
except ValueError as exc:
    assert "过粗" in str(exc)
else:
    raise SystemExit("coarse tag should fail")
try:
    validate_ai_primary_tag("", "数量关系")
except ValueError as exc:
    assert "缺规范考点标签" in str(exc)
else:
    raise SystemExit("empty tag should fail")
assert canonicalize("资料分析-基期量-基期量计算", "资料分析") == ZILIAO_BASE
assert canonicalize("两期比重差", "资料分析") == ZILIAO_SHARE_DIFF
assert canonicalize("资料分析-综合分析-综合判断", "资料分析") == ZILIAO_CMP
assert validate_ai_primary_tag(ZILIAO_BASE, "资料分析") == ZILIAO_BASE
try:
    validate_ai_primary_tag("资料分析-基期量-基期量计算", "资料分析")
except ValueError as exc:
    assert "知识库主标签" in str(exc)
else:
    raise SystemExit("old ziliao tag should fail")
try:
    validate_ai_primary_tag("资料分析-综合分析-综合判断", "资料分析")
except ValueError as exc:
    assert "综合判断" in str(exc)
else:
    raise SystemExit("综合判断 tag should fail")
try:
    validate_ai_primary_tag("资料分析-速算技巧-加法与减法", "资料分析")
except ValueError as exc:
    assert "方法卡" in str(exc)
else:
    raise SystemExit("method tag should fail")

default_pack = select_ziliao_slots({}, {})
assert [slot["tag"] for slot in default_pack] == [
    "资料分析-ABRX类-基期量计算与比较",
    "资料分析-ABRX类-增长率计算模型",
    "资料分析-ABRX类-增长量计算与现期推算",
    "资料分析-比重类-现期、基期与隔级比重",
    "资料分析-平均类-一般平均值与年均增速/增量",
]
weak_pack = select_ziliao_slots(
    {
        "资料分析-比重类-比重趋势、比重差与比值差": {
            "mastery": 38, "confidence": 70, "streak": -2, "attempts": 8, "days_since": 5,
        },
        "资料分析-特殊考点-拉动增长、贡献率与容斥": {
            "mastery": 41, "confidence": 65, "streak": -1, "attempts": 6, "days_since": 9,
        },
    },
    {"资料分析-盐水类-十字交叉法与混合增长率": 3},
)
weak_tags = [slot["tag"] for slot in weak_pack]
assert len(weak_tags) == 5
assert len(set(weak_tags)) == 5
assert "资料分析-比重类-比重趋势、比重差与比值差" in weak_tags
assert "资料分析-盐水类-十字交叉法与混合增长率" in weak_tags
paper = select_ziliao_paper({}, {})
assert len(paper) == 4
assert [row["form"] for row in paper] == ["text", "table", "chart", "mixed"]
assert sum(len(row["slots"]) for row in paper) == 20
assert [slot["tag"] for slot in paper[0]["slots"]] == list(ZILIAO_DEFAULT_PACK)
assert [slot["tag"] for slot in paper[1]["slots"]] == list(ZILIAO_ALT_PACK)
assert [slot["tag"] for slot in paper[2]["slots"]] == list(ZILIAO_DEFAULT_PACK)
assert [slot["tag"] for slot in paper[3]["slots"]] == list(ZILIAO_ALT_PACK)
weak_paper = select_ziliao_paper(
    {
        "资料分析-比重类-比重趋势、比重差与比值差": {
            "mastery": 38, "confidence": 70, "streak": -2, "attempts": 8, "days_since": 5,
        },
        "资料分析-特殊考点-拉动增长、贡献率与容斥": {
            "mastery": 41, "confidence": 65, "streak": -1, "attempts": 6, "days_since": 9,
        },
    },
    {"资料分析-盐水类-十字交叉法与混合增长率": 3},
)
weak_sets = [tuple(slot["tag"] for slot in row["slots"]) for row in weak_paper]
assert len(weak_sets) == 4
assert len(set(weak_sets[0] + weak_sets[1])) == 10
assert weak_sets[2] != weak_sets[3]
assert set(weak_sets[2]) == set(weak_sets[0])
assert set(weak_sets[3]) == set(weak_sets[1])
plans = assign_ziliao_answers(4, rng=random.Random(1))
assert sum(1 for plan in plans if plan["kind"] == "abcd_plus_one") == 3
assert sum(1 for plan in plans if plan["kind"] == "scattered") == 1
assert all(is_abcd_plus_one(plan["answers"]) == (plan["kind"] == "abcd_plus_one") for plan in plans)
validate_ziliao_paper_answers([plan["answers"] for plan in plans])
try:
    validate_ziliao_paper_answers([["A", "B", "C", "D", "A"]] * 4)
except ValueError as exc:
    assert "3 篇" in str(exc)
else:
    raise SystemExit("all-cover paper should fail")
seeded = select_ziliao_paper({}, {}, rng=random.Random(2))
validate_ziliao_paper_answers([row["answers"] for row in seeded])
assert all(slot.get("answer") in "ABCD" for row in seeded for slot in row["slots"])
print("ai tags: ok")

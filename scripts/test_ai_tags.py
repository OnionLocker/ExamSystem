#!/usr/bin/env python3
from kaodian_taxonomy import (
    NUM_PERM_SPECIAL,
    question_primary_tag,
    validate_ai_primary_tag,
)

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
print("ai tags: ok")

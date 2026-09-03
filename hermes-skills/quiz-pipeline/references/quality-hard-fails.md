# 日练硬失败短清单

每个 class 三行。运行时只读本文件，不读 quality-feedback.md。

## fig_missing_label
- 必须打回：题干/清单有甲乙、①–⑤、t/s 等，图上没有。
- 可以通过：清单必现元素都在 SVG 文本里。
- 检查器：figure_qa.check_question

## fig_no_intersection
- 必须打回：清单要求交点，折线不相交或无刻度。
- 可以通过：折线相交，刻度能读出交点。
- 检查器：figure_qa.check_question

## fig_extra_object
- 必须打回：图上多了铁块、木块、草兔等清单外物体。
- 可以通过：图上只有题干/清单点名的对象。
- 检查器：figure_qa.check_question

## fig_kind_mismatch
- 必须打回：锋面配等高线平面图、反射弧配食物网、圆柱无椭圆。
- 可以通过：figure.kind 与题干对象一致。
- 检查器：figure_qa.check_question

## fig_leak_answer
- 必须打回：图上写出冷锋、感受器等 must_derive。
- 可以通过：答案只由考生从图结构推出。
- 检查器：figure_qa.check_question

## fig_low_res
- 必须打回：小于 1400×500 或字号小于 20。
- 可以通过：达到像素与字号下限。
- 检查器：figure_qa.check_question

## notation_stem_mismatch
- 必须打回：题干甲乙，解析/选项改用 ρ_A、液体A。
- 可以通过：符号与题干同一套称呼；下标写 $p_{\text{甲}}$，禁止原文 p_甲。
- 检查器：quality_orchestrator.notation_stem_issues

## giveaway_extreme
- 必须打回：科推/判断错项出现「一定是/必然/唯一」；言语三项都靠极端词。
- 可以通过：错项靠具体错因，不靠绝对词送分。
- 检查器：quality_orchestrator.giveaway_extreme_issues

## empty_analysis
- 必须打回：生成题没有解析。
- 可以通过：有完整解析。
- 检查器：quality_orchestrator.local_quality_issues

## echo_given
- 必须打回：翻译推理正确项复述已知实例。
- 可以通过：正确项经过逆否/选言/连锁。
- 检查器：quality_orchestrator.translation_echo_issues

## flash_visual_missing
- 必须打回：仅统计，不升级成规则。
- 可以通过：不写入生成提示。
- 检查器：仅 Flash（审核噪声）

## flash_quality
- 必须打回：盲审事实不闭环、答案不唯一、干扰不可诊断。
- 可以通过：分数≥10 且无 hard/zero/regression。
- 检查器：仅 Flash

## flash_correct
- 必须打回：看图/正确性答案不唯一或与键不一致。
- 可以通过：盲解与键一致且无并列成立项。
- 检查器：仅 Flash

## paper_rules
- 必须打回：卷面结构、答案字母、模块配比硬规则失败。
- 可以通过：判断 5+15、科推五科不同、字母不扎堆。
- 检查器：generation_gate.validate_paper_hard_rules

## other
- 必须打回：未命名失败，先修本题。
- 可以通过：不得据此追加长 R 条目。
- 检查器：无

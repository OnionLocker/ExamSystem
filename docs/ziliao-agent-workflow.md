# 资料分析 Gemini 工具子 Agent

这是资料分析整套的唯一入口：资料分析整套必须走 agent-paper 高质量通道，禁止用 parallel runner 出整套。Hermes 的 quiz-pipeline skill、`HERMES.md` 和网页每轮注入的 `src/hermes/quizPrompt.js` 都把 20 题、4 篇、“一套/整套”、广东省考/默认难度的请求（语音或文字）路由到这里；`ziliao_parallel_runner.py` 只保留单篇/指定考点专项，脚本本身拒绝整套请求。使用正式机已安装的 Hermes AIAgent，不修改 Hermes 核心、不新增依赖。命题、审材、盲解、质量审核和视觉审核均使用 Gemini；审核调用与命题对话隔离，但不代表不同模型之间的能力验证。

## 执行

在包含本次改造代码的检出目录执行，使用 Hermes 虚拟环境的 Python：

    set -a
    . /home/ubuntu/ExamSystem/.env
    . /home/ubuntu/.hermes/.env
    set +a
    export PYTHONUNBUFFERED=1
    export EXAM_DB=/home/ubuntu/ExamSystem/data/exam.db
    /home/ubuntu/.hermes/hermes-agent/.venv/bin/python scripts/ziliao_agent_paper.py \
      --output-dir /home/ubuntu/ExamSystem/data/manual-ziliao-agent-paper \
      --db /home/ubuntu/ExamSystem/data/exam.db --workers 2 --import

固定为轨 A、mid、4 篇 20 题，题型配额见 `ziliao_tracks.gd_slots_20`（每个槽位带 kind），四种 Q5 问法与四种考查组合跨篇轮换。四篇主题从 `ziliao_agent_paper.THEME_POOL` 中抽取并避开上一批（读 output-dir 中最新批次的 `M0*-plan.json` 的 theme_key），M01 固定广东省、其余三篇随机取深圳/广州/佛山等地市。四个独立进程各持有一篇上下文；默认最多同时运行两篇，避免对审核服务突发过多请求。不要拿这个入口替代用户点名的单知识点专项。

## 工具与验收边界

- 工具仅有计算、提交材料、保存/替换本篇题目、送审、读取本篇状态。无终端、任意文件写入、改闸门或入库工具。
- 分项与合计先由高精度底数推导，再分别舍入；台账记录底数、显示数、指标和单位。程序复算，独立 Gemini 检查台账是否对应材料；本篇至少一组有实际显示差异。不是给总计随手加减 0.1。
- 比率两期变化问百分点；增长率槽仍可问收入、利润额等绝对指标同比。禁止为修问法偷换槽位。
- 混合倍数正确项不接受整数倍；若换对象不足以修复，重新提交材料，不能改标答凑非整数。
- 四图选一尚未实现，本轮明确拒绝该槽位和选项图。
- 程序硬检查（`ziliao_checklist.py`，worker 保存/送审与整套闸门都执行；manifest 的 `ziliao_checklist` 为 `gd-agent-v2`）：占位地名与人造口径句、真实广东地名、整数百分比过多；题型关键词（年均、倍、平均、比重变化、百分点、间隔增长率）；干扰项须写“X项：错误算式”且禁用“计算失误/估算误差”；数值选项相对差 ≥3%；比重/增长率/平均数正确值非整数百分比、倍数非整数倍；每篇图表至少两个独有数据写进解析算式；年均增长使用图中至少两个年份数据；综合分析每题至少两处算式，百分点/累计/缺数据陷阱每篇至多一类、全卷至多两篇。
- 槽位配额检查（`validate_gd_quota` / `validate_gd_kinds`）：12 类题型全覆盖，同一题型 ≤3 题，细节查找/读数/读图排序全卷 ≤1 题（`paper_issues` 另按题干与解析复核），百分点题干扰项不得等于两增速相对比值（`point_ratio_issues`），四道综合组合互不相同。
- 材料替换会清空五题和旧回执；局部修题保留其他题。每次保存与送审均留原始输入、反馈和耗时。
- 每篇独立审材与整篇送审各最多六次；单次 worker 最多 40 轮模型交互、25 分钟。超限保留失败，不降低门槛放行。
- 合并后必须再过完整 20 题闸门。失败按题号/材料返回原 worker，保留原对话自主修复，最多三轮整套审核。
- 仅 generation_gate.py verify 验证最新文件通过才记成功。通过不等于统计学意义上的稳定，也不代替用户对题目风格的评价。

## 产物

入口返回 batch_dir。目录内有可入库结构的 manifest/materials/questions/calculations、图片、最终回执，以及：

- workers/M0*/批次/tool-log.json：全部工具反馈；对应 tool-*-input.json 保留输入。
- workers/M0*/批次/agent-result.json：实际 Gemini 模型、对话、调用量。
- gate-attempts/：每轮完整输入与独立审核证据。
- worker-runs.json / paper-summary.json：每篇及整套耗时、失败和自动回修次数。

入口默认只生成验收产物；添加 --import 后仅在最终回执验证通过时调用现有 import-batch 导入器。导入器再次执行 --for-import 回执校验。入库失败返回非零并保存日志，不能只凭 passed=true 声称入库成功。入口不会部署业务服务；线上部署及已有验收批次的导入时间以 deployment.json 为准。

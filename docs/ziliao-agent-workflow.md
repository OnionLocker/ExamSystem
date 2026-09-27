# 资料分析 Gemini 工具子 Agent

这是独立出题入口，暂未替换线上旧 runner。使用正式机已安装的 Hermes AIAgent，不修改 Hermes 核心、不新增依赖。命题、审材、盲解、质量审核和视觉审核均使用 Gemini；审核调用与命题对话隔离，但不代表不同模型之间的能力验证。

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
      --db /home/ubuntu/ExamSystem/data/exam.db --workers 2

固定为轨 A、mid、4 篇 20 题，保留现有题型配额及四种 Q5 问法。四个独立进程各持有一篇上下文；默认最多同时运行两篇，避免对审核服务突发过多请求。不要拿这个入口替代用户点名的单知识点专项。

## 工具与验收边界

- 工具仅有计算、提交材料、保存/替换本篇题目、送审、读取本篇状态。无终端、任意文件写入、改闸门或入库工具。
- 分项与合计先由高精度底数推导，再分别舍入；台账记录底数、显示数、指标和单位。程序复算，独立 Gemini 检查台账是否对应材料；本篇至少一组有实际显示差异。不是给总计随手加减 0.1。
- 比率两期变化问百分点；增长率槽仍可问收入、利润额等绝对指标同比。禁止为修问法偷换槽位。
- 混合倍数正确项不接受整数倍；若换对象不足以修复，重新提交材料，不能改标答凑非整数。
- 四图选一尚未实现，本轮明确拒绝该槽位和选项图。
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

入口从不入库或部署。线上入口是否切换须以部署记录为准，不能因开发分支实跑成功就声称线上已更新。

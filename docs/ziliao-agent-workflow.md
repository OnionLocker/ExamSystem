# 资料分析出题流水线

资料分析只有两个入口，Hermes、DSH 与每日定时任务共用：

| 请求 | 入口 |
|---|---|
| 整套（4篇20题、“一套/整套/日练”、广东省考默认） | `scripts/ziliao_agent_paper.py` |
| 单篇5题、点名材料形态、指定考点专项（5/10题） | `scripts/ziliao_material_pipeline.py` |

每日整套由 `scripts/daily_ziliao_scheduler.py`（Hermes 定时任务 04:40，07:40 仅在失败时补跑）调用整套入口。只做粤考日练（轨A）；经典计算加练（轨B）暂不提供。

## 执行

    set -a
    . /home/ubuntu/ExamSystem/.env
    . /home/ubuntu/.hermes/.env
    set +a
    export PYTHONUNBUFFERED=1
    export EXAM_DB=/home/ubuntu/ExamSystem/data/exam.db
    # 整套
    python3 scripts/ziliao_agent_paper.py \
      --output-dir /home/ubuntu/ExamSystem/data/manual-ziliao-agent-paper \
      --db /home/ubuntu/ExamSystem/data/exam.db --import
    # 单篇 / 专项
    python3 scripts/ziliao_material_pipeline.py --format chart --import
    python3 scripts/ziliao_material_pipeline.py --tag '资料分析-ABRX类-增长量计算与现期推算' --count 10 --import

整套参数：`--difficulty easy|mid|hard`、`--blueprint`（按篇 M01 或按题 M03-Q4 覆盖档位，可附 note，只开放难度）、`--plan-only`（打印蓝图与每题分配理由）、`--resume <批次目录>`（复用已签名的篇，只重做未通过的篇）、`--workers 1|2|4`（默认4）。

单篇/专项参数：`--tag`（资料分析出题主标签）、`--count 5|10`、`--format`、`--brief`（用户原话）、`--difficulty`、`--plan-only`。

## 三层结构

1. **蓝图调度器**（`scripts/ziliao_blueprint.py`，不调模型，几十毫秒）：锁定4篇材料形态与题材、20个槽位（题型、细分考法、选项形式）及答案字母。题型按广东真题频率、只按已入库卷子轮转；比重/增长率/增长量/基期量各至少1道；问法（题型+考法+选项形式）不重复；区间式每套1–2道、升降式0–1道，同一选项形式（区间/升降/排序/个数/选主体）每套≤2道，每篇非精确选项≤1道；“是……的多少倍”每套≤2道、每篇≤1道；同篇不同时出现期平均数与平均数差值；每个槽位写明分配理由，存为 `paper-blueprint.json`。排不出时按固定顺序放宽并记录。
2. **单篇流水线**（`scripts/ziliao_material_pipeline.py`，整套时每篇一个子进程，4篇并发）：
   - 材料员（一次请求）只写正文、图表与分项；合计和舍入台账由 `ziliao_material_tools.py` 从高精度底数独立舍入生成。
   - 程序核对材料硬检查，不过直接带问题退回；过了就一边做模型材料审核，一边让出题员 5 题并行。材料定稿后后台先做材料图视觉质检。
   - 出题员每题一个请求，只拿材料、本题规则与考法、其他题考什么；只写题干、解析、各选项算式与错法。选项文字、精度、顺序（数值升序、区间按整齐档位从小到大并让常见错法落入别的档、升降固定顺序）、答案字母与“X项：错误算式=结果”由程序生成；每篇答案组合与蓝图一致。
   - 本地校验或审核只退回点名的题，回修只带该题、反馈和同篇题干。
   - 篇内审核（`generation_gate.py issue`）：盲解、考官、整篇审核与视觉质检同时进行，通过后单篇签名；已通过且未改动的题、已查过的图不重审（`quality_memory.py`）。
   - 模型请求超过 60–75 秒未返回自动补发一次；每个请求的提示词与回复存档在 `calls/`。
3. **整卷轻量闸门**（`scripts/ziliao_assembly.py`）：不再整卷重审，只核对每篇签名有效、每题/材料/图片与单篇签发时一致、题号连续、答案分布（4篇中恰好3篇为ABCD各一加一个重复）、题量与主标签配比、蓝图配额与全卷机械规则，签发 `ziliao-assembly-v1` 回执；入库时 `generation_gate.py verify` 全部重新核对。专项10题同样经此闸门合成一批。

## 产物

整套 `data/manual-ziliao-agent-paper/<批次>/`：`paper-blueprint.json`、`M0*-plan.json`、`adaptive.json`、可入库的 manifest/materials/questions/calculations/images、整卷回执 `.gate.json`、`paper-summary.json`（耗时、请求数）、`worker-runs.json`，以及 `workers/M0*/<批次>/` 下每篇的签名产物、`pipeline-summary.json`（请求、退回、阶段耗时）和 `calls/`（各角色提示词与回复）。

单篇/专项 `data/manual-ziliao-material/<批次>/`：结构同单篇；10 题专项在其下有两个 `workers/`。

## 测试

- `scripts/test_ziliao_blueprint.py`：蓝图约束、轮转只认已入库、答案字母。
- `scripts/test_ziliao_material_tools.py`：舍入台账、选项生成、解析行、模式判定。
- `scripts/test_ziliao_material_cli.py`：单篇/专项计划与参数。
- `scripts/test_ziliao_material_pipeline.py`（脚本式）：离线回放整条流水线，含回修、对冲、4篇组装签发与篡改拦截。

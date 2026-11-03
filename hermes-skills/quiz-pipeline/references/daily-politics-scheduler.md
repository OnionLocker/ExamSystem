# 每日政治理论 + 常识判断真题样式卷（定时任务）

- 定时：每天 **05:10**（Hermes cron job `99ad1c4a263e2`，脚本 `~/.hermes/scripts/daily_exam_politics.py`，工作目录 `/home/ubuntu/ExamSystem`）。
- 产出：**政治理论 10 题（2 判断 + 6 单选 + 2 多选）+ 常识判断 5 题（5 单选）= 15 题**。日练判断题上限两成（2026-11-03 用户要求），回忆版真题为 4/4/2；用户自定的专项/整模块卷仍可按 4/4/2 或指定题型。
- **拼卷**：两套各自独立生成入库后，自动合并到政治理论批次（`UPDATE questions SET batch_id=政治批次`），练题页显示为**一套 15 题**，分类归"政治理论"；任一套失败则不合并、各自独立保留。批次 id 统一为 `daily-YYYYMMDD-zhengzhi-*`。

## 流程（scripts/daily_politics_scheduler.py）

1. `policy_sources.discover()`：抓 watch_pages 按 watch_terms 筛候选（纯脚本，无 AI）。
2. 选点 `policy_quiz.module_slots()`：按 **politics-hotspots.json 热点权重**优先命中考点（长征90周年、四中全会/十五五、新质生产力、政府工作报告、年度科技成就…），题型配额 2/6/2 与 5。角色配额见 `policy_daily_plan.QUOTAS`：
   - 政治：中央热点3 + 基础2 + 广东2（其一为 **高价值广东包轮转** `gd_core`）+ 错点2 + 覆盖1；
   - 常识：错点2 + 广东2（其一为 `gd_core`）+ 覆盖1；无错点时名额转覆盖。
   - `GD_PRIORITY` 是高价值广东包（广东考察讲话、冲一流、服务业扩能、高质量发展大会、十五运会开/闭幕与总结、广东十五五、四链、政府工作报告、省情概况），近14天用得最少、排序靠前的先上。
   - **14 天限频**：同一原文段落 14 天内不再作为新题依据；同一原文近14天累计政治≤3题、常识≤2题（基础理论原文≤4），单日同源≤2题。错点复测不受限（本就要回到原段落换设问）。资料不够时先放宽并在理由里注明“已放宽，需补充资料”。
   - 选点分两轮：各名额先按本角色取点，落空的名额再补覆盖，避免覆盖名额先占走广东包/基础段落。
   - 成套卷副本（`gd-zhengli-set-*`，external_id 为 `<套卷>::<原题>`）不计入限频，作答按原题归并，不算独立证据。
3. **版本核验**：已存在匹配当前正文的核验记录则复用；缺少依据时对选中资料 fetch，段落口径与 `refresh` 一致（≥20 字、去重、按 focus 过滤）算 sha——
   - 与登记一致 → `review_updates` 登记（引用原文 + "版本一致未见更新"结论）；
   - 已变化 → 整批失败，需 Hermes/AI 人工复核（`policy_sources.py inspect/show/review-updates`）。
   - 非基础资料须有与当前正文哈希匹配的可追溯核验依据；记录不因超过24小时失效。
4. `quiz_lite --module 政治理论 --count 10` 与 `--module 常识判断 --count 5`（盲解官+考官+判题器+引用核对），入库。
5. `ai_daily_batch_runs` 记账（练题页生成中/失败卡片）。

## 运维

- 手动跑一次：`python3 scripts/daily_politics_scheduler.py`（输出 JSON，`ok` 字段看成败；`runs[].quota_audit` 记录当日角色、广东题数、题型分布、各原文当日/近14天题数与越限项）。
- 干跑核验：`python3 scripts/daily_politics_scheduler.py --dry-run`，只选点并打印 `plans[].quota_audit` 与逐题选点理由，不写库、不核验资料、不调用模型；`limit_violations` 非空则 `ok=false`。
- 失败重试：cron 每早自动重试（当天已成功入库的模块不再出，失败会换新批次重出）。
- 排查：
  - 失败原因在输出 `runs[].error` 或 `ai_daily_batch_runs.error`；
  - "正文已更新（sha 变化）"→ 用 `policy_sources.py inspect <url>` 读新页 → `review-updates` 登记后重跑；
  - 题库没题 → 看 `generation_jobs` 状态（running/failed）与 `data/daily-batches/<date>/<batch>/attempt-*.json`。
- 调热点：改 `hermes-skills/quiz-pipeline/references/politics-hotspots.json`（weight/window/tags），次日生效。

## 纪律

- 政治/常识解析固定三段：【依据】逐项对错与出处；【易混对照】1–3组“是X不是Y”，两端都要落到原文或题面；【记忆钩子】≤20字口诀，只压缩原文要点、不加新事实。`quiz_lite.local_issues` 缺段/钩子超长直接退回，考官缺段判 `analysis_ok=false`。

- 出题必须基于已核验版本的原文（机械核验只放行"正文未变"；正文变化一律转人工/AI 复核）；不强制每日重复核验同一版本。
- 题库的题不会用旧口径重出：正文 sha 变了必须重新生成（`require_current_sources` 强制）。

## 默认难度（2026-11-02用户确认）

后续全部任务按广东省考常规真题难度出题，内部目标mid；不再下发宽松auto，也不自动升级hard。新文字批次的双审与入库均核对实际难度，入门直套和刻意拔高的题退回重出，不能只改标签。题量、选点覆盖和已入库历史保持原规则。

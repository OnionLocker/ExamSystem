---
name: quiz-pipeline
description: >
  出题流水线：政治理论、常识判断、数量关系、言语理解、文字逻辑判断、资料分析、图形推理（程序出图）、申论。
  触发词：出题、来几题、测测我、刷题、专项、来一套。文字题（数量/言语/文字逻辑/政治/常识）默认走 DSH 出题（--dsh-import：DSH 出题+子 agent 审核+入库，不用服务器模型 key，均已支持）；图推（程序出图）、资料整套（agent-paper）、申论、科学推理走各自专用入口或外采真题；只有用户明确要求服务器模型或 DSH 链路不适用时才走服务器 ExamSystem 脚本（model_router 可配置模型）。
whenToUse: 用户要求出题、安排专项练习或整卷时加载。排计划/复盘/审核不用本 skill。
metadata:
  tags: [kaogong, 出题, ExamSystem]
  related_skills: [gd-gongkao-coach]
---

# 出题流水线（DSH 版）

Hermes 只认意图。DSH 出题模式下题目由 DSH 生成、子 agent 双审，闸门与入库由脚本完成；服务器链路下出题、闸门、入库全部由脚本完成。DSH 侧负责抽取参数、出题、派审、后台调用与简报结果。

## 铁律

1. **不要绕过脚本出题。** 服务器链路不手写 questions.json、不手跑 generation_gate / import-batch；DSH 出题模式是受控例外：题目在 DSH 生成、经盲解官+考官子 agent 双审、再由 quiz_lite.py --dsh-import 走闸门入库，禁止跳过脚本或省略双审直接入库。
2. **脚本不存在或失败，就报失败。** 禁止回退到自己出题，禁止手跑闸门，禁止用旧 runner 冒充成功。
3. **对话里不要打印题干、选项、答案。** 成功只报批次名和题量。
4. **出题要几分钟，必须后台跑。** 用 pwsh 的 `run_in_background: true`，完成后用 job_output 读 JSON 回执。
5. 考点或题量不确定时，先查 `knowledge-content.mjs catalog` 或 `quiz_lite.py --plan-only`，不要瞎猜网页子点。

## 脚本位置（绝对路径）

```
/home/ubuntu/ExamSystem/scripts/quiz_lite.py            # 主入口：数量/言语/逻辑/政治/常识/图推
/home/ubuntu/ExamSystem/scripts/ziliao_agent_paper.py   # 资料分析整套（4篇20题，唯一入口）
/home/ubuntu/ExamSystem/scripts/ziliao_parallel_runner.py  # 资料单篇≤5题或指定考点专项≤2篇10题
/home/ubuntu/ExamSystem/scripts/shenlun_quiz.py         # 申论出卷/特训
/home/ubuntu/ExamSystem/scripts/knowledge-content.mjs   # 当前知识树 catalog 查询
/home/ubuntu/ExamSystem/scripts/learner_snapshot.py     # 学员状态快照（--compact）
/home/ubuntu/ExamSystem/scripts/policy_sources.py       # 政治/常识权威原文核验
/home/ubuntu/ExamSystem/scripts/model_router.py         # 统一模型路由（--show 查看，--apply-config 切换）
```

## 批次命名与推进节奏（用户长期要求）

- 题组显示名由脚本按目录生成：`广东省考行测-{模块}-{父知识点}-{难度}-{YYYYMMDD}`；指定子考法时在父知识点后、难度前追加该子点当前全名。难度显示“简单／中等／困难／综合”之一（easy/mid/hard 对应前三档，多档混合或 auto 为“综合”）。不自行简写知识点，不把“综合”粘到知识点名。
- `batch_id`：服务器链路 `YYYYMMDD_hermes_<考点或模块>_<两位序号>`；DSH 链路 `YYYYMMDD_dsh_<考点>_<两位序号>`。不得复用已有批次。
- **单考法闭环打穿**：同构变式卷 100% 锁在同一考法内，变情境与陷阱，不变底层解题动作，严禁跨考法发散。
- 训练量与难度按当前失分动作和 `exam-sprint-plan.md` 调整；日常数量默认少量 auto 验证，不自动为每个子考法连出 mid/hard 两套。

## 第 1 步：抽出参数

- **模块**：政治理论 / 常识判断 / 判断推理 / 数量关系 / 言语理解与表达 / 资料分析（文字专项）
- **考点 `--tag`**：用户点名父知识点则写成粉笔 `模块-一级-二级`；脚本按当前网页内容树的启用末级子点自动分配。先跑 catalog 确认精确标签：

```
node /home/ubuntu/ExamSystem/scripts/knowledge-content.mjs catalog '数量关系-数学运算-工程问题'
node /home/ubuntu/ExamSystem/scripts/knowledge-content.mjs catalog '判断推理'
```

- 用户只点模块或上层范围时，在 catalog 返回范围内按要求选当前知识点组成 blueprint，不能擅自缩成其中一个三级点。
- **题量**：用户说几道就几道；点名考点没说数量则 **5**；不要擅自出 10 题或成套 20 题。
- **难度**：“广东省考难度”“贴近真题”“稍难一点”“多点基础题”都保留 **auto**（命题倾向，非硬性难度门槛）；只有用户明确指定档位或配额（如“全部中等”“三道困难题”）才设置 easy/mid/hard。数量口径：easy 与 mid 严格区分，hard 接受 mid 或 hard、不接受 easy，按两位审核较低评级保存。

## 第 2 步：后台调用

**文字题（数量/言语/逻辑/政治/常识）默认走「DSH 出题模式」（下一节）：先在 DSH 生成题目+子 agent 双审，再 `--dsh-import` 入库。** 下面的服务器链路仅当用户明确要求用服务器模型、或模块不适用 DSH（图推/资料/申论）时才使用。

确认参数后（服务器链路），用 pwsh 后台执行（不要前台等）：

```
pwsh({
  description: "出题：数量排列组合 5 题",
  command: "python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '数量关系' --tag '数量关系-数学运算-排列组合问题' --count 5 --batch-id 'YYYYMMDD_hermes_排列组合_01'",
  workdir: "/home/ubuntu/ExamSystem",
  run_in_background: true
})
```

等后台完成通知，用 `job_output` 读回执。成功：`status=success`，直接使用回执，不再查库确认；简报时区分 slots 请求档位与 `actual_difficulty_counts` 实际评级（如“困难档训练，实际中等2题”）。失败：把 `message` 原样告诉用户。

需要核对父级配额或名称解析时，正式命令加 `--plan-only`（不生成、不登记、不入库），检查返回的实际子点和题量后再去掉该参数生成。明确请求直接出题且目标清楚时不必额外询问确认。

### 多考法混批：`--blueprint`

用户说「三种题型都要有」「难易结合」「3+3+4」这类**结构化要求**时，不要退化成单标签，也不要连跑三次。改传蓝图（与 `--tag/--count` 互斥）：

```
pwsh({
  description: "出题：最值阶梯 3+3+3",
  command: "python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '数量关系' --batch-id 'YYYYMMDD_hermes_最值阶梯_01' --blueprint '{\"slots\":[{\"tag\":\"数量关系-数学运算-最值问题\",\"count\":3,\"difficulty\":\"easy\"},{\"tag\":\"数量关系-数学运算-最值问题\",\"count\":3,\"difficulty\":\"mid\"},{\"tag\":\"数量关系-数学运算-最值问题\",\"count\":3,\"difficulty\":\"hard\"}]}'",
  workdir: "/home/ubuntu/ExamSystem",
  run_in_background: true
})
```

- `slots` 按顺序对应题号；每槽 `tag` 必填、`count` 必填、`difficulty` 选填。题量总和限 1–15；所有槽必须同一模块；蓝图不放宽标签校验。
- 槽位可带 `brief`（自由文本 ≤600 字）：只收紧、不放宽，传达考情侧重、要避开的退化写法；不写题干、答案、具体数字。
- 太长可写文件再传 `--blueprint @/tmp/bp.json`。

## DSH 出题模式（--dsh-import，文字题默认链路）

**文字题（数量/言语/逻辑/政治/常识）默认走这条链路**：**DSH 模型出题 → DSH 子 agent 双审 → 服务器入库**。用户说「你在 DSH 里出题」「不要用服务器 gemini/deepseek」「你出题你审核你入库」等也走此链路。全程不调用服务器上的 gemini/cliproxy 或 deepseek API key；闸门与入库管线复用，质量校验不缩水。仅当用户明确要求用服务器模型、或模块不适用 DSH（图推/资料/申论）时才走服务器链路。

### 流程总览

```
1. 抽取参数（模块/考点/题量/难度，同"第 1 步"）；言语先跑 `recent_yanyu_avoid` 查最近 14 天题库，避开重复题材/句式套路/开头句式（见下）
2. 从 catalog 取每个槽位的讲解卡 definition，写题和审核都带（镜像服务器 kaofa_canon）
3. 在 DSH 会话里直接生成题目 JSON（stem/options/answer/analysis/question_type）；≥15 题注意答案字母均衡（任一字母 ≤40%）
4. 派子 agent 审核（镜像服务器三角色）。**按 chunk 并行以提速：把题目按 ≤5 题/组拆开，每组各派一个盲解官 + 一个考官子 agent 并行跑；言语/判断再各配一个用法核查官。同时最多起 6 个子 agent（≈3 组并行）**；分批跑时等当前批返回再起下一批，不要无上限起。每组审核字段照下：
   - 盲解官：只给该组题干选项（不给答案），独立解题 → answer/steps/also_valid/unsolvable/actual_difficulty/difficulty_reason
   - 考官：给该组题干+选项+答案+解析+讲解卡，核对五维 → verdict/actual_difficulty/analysis_check/necessity_checks/五维标志/issues
   - 用法核查官（言语/判断推理）：不给答案，只核对解析里的用法断言/题面条件 → usage_checks / question_check
   - 合并时按题号对齐（blind.examiner 的下标 = 全局题号），不同组的证据拼成一个 review.json。
5. 组装 review.json（module/auditor/questions/review.blind/review.examiner）
6. 跑 quiz_lite.py --dsh-import review.json（后台）→ 闸门校验 → 入库
7. 被拒时修对应题重导（换新 batch_id），不整批重来
```

**话题/句式避让（言语）**：出题前跑
```
python3 -c "import sys; sys.path.insert(0,'scripts'); from yanyu_variety import recent_yanyu_avoid; import json; print(json.dumps(recent_yanyu_avoid('data/exam.db'), ensure_ascii=False))"
```
按返回的 `recent_molds`（连用≥2 次的句式套路避开）、`recent_openings`（开头 22 字避开）、`recent_topics`（主题指纹避开）命题，不写同主题同框架的题。

### review.json 格式

```json
{
  "module": "数量关系",
  "auditor": "dsh-subagent",
  "questions": [
    {"stem": "...", "options": [{"key": "A", "text": "..."}], "answer": "C", "analysis": "...", "question_type": "single"}
  ],
  "review": {
    "blind": {"1": {"answer": "C", "steps": "...", "also_valid": [], "unsolvable": false, "actual_difficulty": "easy", "difficulty_reason": "..."}},
    "examiner": {"1": {"verdict": "PASS", "actual_difficulty": "easy", "difficulty_reason": "...", "analysis_check": "...", "necessity_checks": [], "difficulty_ok": true, "kaodian_ok": true, "style_ok": true, "analysis_ok": true, "brief_ok": true, "variant_match": {"ok": true, "reason": "无细分考法"}, "issues": []}}
  }
}
```

- 言语题：考官项还需提供 `usage_checks`（用法断言逐条核查；解析无用法断言则给 []）；判断推理还需 `question_check`。言语 auto 难度按盲解官+考官两位**较低评级**记录（不虚标）。
- 槽位分配了考法变式（`kaofa_variant_name`）时，考官项还须提供 `variant_match`：核对本题实际设问结构与解题动作是否匹配该变式，`ok` 必须为 true 且 `reason` 给依据；缺字段或被判定不匹配会被闸门打回重出。

### 出题要求（DSH 生成题目时）

- 选项字母顺序须与数值匹配（`local_issues` 会查）：数值选项 A→D **要么升序要么降序**，否则被闸门拦截。
- 答案字母与选项一致；判断题 A=正确/B=错误；多选答案按升序拼接。
- analysis 至少 30 字，可复算；尽量避开「只能/必须/必然/不能」这类必要性断言——若出现，须在 necessity_checks/usage_checks 里逐条核验（见下）。
- 题干 ≥15 字，像广东省考真题，锁定考法不发散。

### 子 agent 审核 prompt 模板

**盲解官**（不给答案）：
```
你是广东省考行测独立做题人（盲解官）。用 read 读取 <题目文件>（只有题干选项，无答案）。
自己算每道题，输出 JSON：{"blind": {"1": {"answer": "A", "steps": "完整步骤", "also_valid": [], "unsolvable": false, "reason": "", "actual_difficulty": "easy/mid/hard", "difficulty_reason": "..."}}}
- steps 写出每一步算式和数值，禁止跳步；逐个选项检查还有没有第二个也成立（also_valid）
- 条件不足/矛盾/无正确选项 → unsolvable=true 并给 reason
- actual_difficulty 按实际必需解法评定：easy 常规步骤；mid 一个额外独立条件；hard 至少两个相互制约条件或分段讨论
```

**考官**（给答案解析+讲解卡）：
```
你是广东省考行测命题审核官。用 read 读取 <题目文件>（含题干选项答案解析）。下面附带各题考点讲解卡 definition，作为考法口径依据。
逐题核对五维：difficulty_ok（难度对档）/kaodian_ok（锁定考法，对照讲解卡）/style_ok（像真题）/analysis_ok（解析可复算）/brief_ok（无额外要求）。
输出 JSON：{"examiner": {"1": {"verdict": "PASS", "actual_difficulty": "easy/mid/hard", "difficulty_reason": "...", "analysis_check": "重算过的推导", "necessity_checks": [{"claim": "原句", "valid": true, "reason": "依据"}], "usage_checks": [], "variant_match": {"ok": true, "reason": "依据"}, "difficulty_ok": true, "kaodian_ok": true, "style_ok": true, "analysis_ok": true, "brief_ok": true, "issues": []}}}
- necessity_checks：从解析里提取含"必须/只能/必然/不能"的句子逐条核验；没有就给空数组（须与程序提取一致）
- usage_checks：言语必需字段——核查解析中含用法限制断言的句子（搭配不当/仅用于/多用于/通常用于/适用对象/为中性词等），逐条判定 valid；没有就给空数组
- question_check：判断推理必需字段——独立核对题面条件是否完整、答案是否唯一，给 {"valid": true, "reason": "PASS ..."} 形式
- variant_match：题目文件里若注明了“本题考法变式：xxx”（brief 或 requested_slot 的 kaofa_variant_name），则必须核对本题实际设问结构与解题动作是否属于该变式（对照讲解卡 definition 与变式要求），返回 {"ok": true, "reason": "依据"}；退回该考点最常见默认考法、或只换场景不换解题动作 → ok=false 并在 reason 写明差在哪。没有注明考法变式就给 {"ok": true, "reason": "无细分考法"}。
- 任一 false → REJECT 并在 issues 写明；全部 true 才 PASS
```

**用法核查官（第三角色，言语/判断推理）**：
```
你是现代汉语用法/逻辑条件独立核查官，不做选择题、不知道标答。用 read 读取 <题目文件>（含题干选项解析，不含答案也行）。
只核对解析里涉及用法限制或条件必然性的句子，逐条判定：PASS（该句成立且有依据）/ REJECT（存在自然反例或逻辑漏洞），reason 给具体反例或依据。
输出 JSON：{"usage": {"1": {"usage_checks": [{"claim": "原句", "valid": true, "reason": "..."}], "question_check": {"valid": true, "reason": "PASS ..."}}, ...}}
- usage_checks：言语用；从解析提取含"搭配不当/仅用于/多用于/通常用于/适用对象/为中性词/必须/只能/必然/不能"的句子逐条核验
- question_check：判断推理用；核对题面条件完整、答案唯一
- 该角色输出并入 review.json 的 examiner 项对应字段
```

### 组装与入库

用 write 工具把题目+两个子 agent 结果合并成 review.json（questions 用出题原文，review.blind/review.examiner 用子 agent 输出），然后后台入库：

```
pwsh({
  description: "DSH 出题入库：数量排列组合 3 题",
  command: "python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '数量关系' --batch-id 'YYYYMMDD_dsh_考点_01' --blueprint '{\"slots\":[{\"tag\":\"数量关系-数学运算-排列组合问题-@position-restriction\",\"count\":3}]}' --dsh-import /tmp/dsh-review.json",
  workdir: "/home/ubuntu/ExamSystem",
  run_in_background: true
})
```

- batch_id 用 `YYYYMMDD_dsh_<考点>_<两位序号>`（区别于 hermes 前缀）。
- 成功回执 `status=success`、`imported=N`；失败把 `message` 原样告诉用户。
- **闸门会校验**：盲解官答案必须等于题面键定答案、also_valid 为空、考官五维全 true、necessity_checks 覆盖全部必要性断言、批内不撞题（build_dsh_review 已加 duplicate_question 检查）、难度槽位一致、选项排序。槽位分配了考法变式时还校验 `variant_match` 必须 ok=true。审核证据不达标会被拒，不是故障。
- **被拒处理**：按 message 定位是哪题哪项没过，修对应题（题干/解析/审核证据），换新 batch_id 重导；已通过的题不用重写，保留在 review.json 里继续用。

### 注意事项

- 只有文字题能走 DSH 模式：数量/言语/逻辑/政治/常识（**均已跑通支持**）。图推（程序出图）、资料整套（agent-paper）、申论仍走各自专用入口。
- 审核采用三角色（镜像服务器）：盲解官（答案+唯一性）+ 考官（五维+必要性断言）+ 用法核查官（言语 usage_checks / 判断 question_check，输出并入考官项）；题目和审核都带讲解卡 definition。**DSH 审核按 ≤5 题/组拆并行，同时最多 6 个子 agent（≈3 组）；分批等返回再起下一批，避免无上限并发。**
- 言语/判断推理的审核证据更严格：言语考官项须含 `usage_checks`（解析无用法断言则 []），判断推理还须含 `question_check`；闸门强制校验，缺字段会被拒。言语/判断推理 auto 难度按盲解官+考官两位**较低评级**记录（build_dsh_review 已实现，与服务器模式一致）。
- 答案字母均衡：≥15 题时任一字母 ≤ 约 40%，按 answer_plan 均衡放置正确项。
- 审核证据的 `necessity_checks` 会与程序提取的 claims 按顺序对齐（相似度 ≥0.8），子 agent 输出时 claim 要逐字抄录解析原句。
- 子 agent 的 read 工具可能读不到 /tmp（后端绑定差异），题目文件可放在工作区或让子 agent 用 pwsh cat 读取。

## 各模块专用入口

### 政治理论、常识判断（先核验原文再出题）

复用 quiz_lite，强制权威原文快照、独立逐项核验。先 `python3 scripts/policy_sources.py status` 看资料；资料少时联网检索原发机关正文后 `policy_sources.py add @登记JSON`，由程序抓正文。不能自己编写资料正文或拿搜索摘要当原文。详情见 `hermes-skills/quiz-pipeline/references/politics-common-workflow.md`。**政治/常识同为文字题，默认走 DSH 出题模式**：先按本节的原文核验流程备好资料，再按「DSH 出题模式」生成题目+子 agent 双审+入库（审核时须核对选项的原文出处）。下面的命令是服务器链路示例。

```bash
# 只点模块：政治默认10题（4判断+4单选+2多选）、常识默认5题
python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '政治理论' --batch-id 'YYYYMMDD_hermes_政治理论_01'
python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '常识判断' --count 5 --batch-id 'YYYYMMDD_hermes_常识_01'
# 专项可指定题型与资料
python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '政治理论' --tag '政治理论-时事政治-重要文件' --count 3 --question-type multi --sources gd-science-literacy-2026 --batch-id 'YYYYMMDD_hermes_科学素质多选_01'
```

### 资料分析

- **整套（20题/4篇/“一套/整套/日练”）必须走 agent-paper 高质量通道**，禁止 parallel runner 出整套。后台执行，先 `--plan-only` 核对 20 槽位题型与档位再去掉它正式跑：

```bash
cd /home/ubuntu/ExamSystem && set -a && . /home/ubuntu/ExamSystem/.env && . /home/ubuntu/.hermes/.env && set +a && \
export PYTHONUNBUFFERED=1 EXAM_DB=/home/ubuntu/ExamSystem/data/exam.db && \
/home/ubuntu/.hermes/hermes-agent/.venv/bin/python scripts/ziliao_agent_paper.py \
  --output-dir /home/ubuntu/ExamSystem/data/manual-ziliao-agent-paper \
  --db /home/ubuntu/ExamSystem/data/exam.db --workers 2 --import
```

  成功必须是退出码 0、`passed=true`、error 为空且 `imported=20`。整套难度蓝图：`--difficulty hard|easy` 或 `--blueprint '{"difficulty":"mid","slots":{"M02":"easy","M03-Q4":{"difficulty":"hard","note":"..."}}}'`。详见 `hermes-skills/quiz-pipeline/SKILL.md`「默认粤考整套」。
- **单篇≤5题或指定考点专项**：`ziliao_parallel_runner.py --tag '资料分析-...' --count 5 --difficulty mid --materials 1 --formats text,table,chart`。不指定考点只出 1 篇 ≤5 题；指定考点至多 2 篇 10 题；整套请求会被脚本拒绝。
- 用户要 6–19 题非专项时，说明只提供单篇 5 题或高质量整套 20 题，请用户选择。

### 图形推理（程序出图）

由 `figure_quiz.py` 程序出题（六面体、三视图、立体拼接、立体旋转、折纸剪纸、截面、平面拼接、黑白块、数量规律、位置规律、属性规律、样式规律 12 类），仍只调 `quiz_lite.py`，参数照旧。全程不调模型，一道题不到 1 秒。

```
pwsh({
  description: "出题：图推空间类 5 题（程序出图）",
  command: "python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '判断推理' --tag '判断推理-图形推理-空间类' --count 5 --batch-id 'YYYYMMDD_hermes_空间类_01'",
  workdir: "/home/ubuntu/ExamSystem",
  run_in_background: true
})
```

- 同一批只能全是程序出图题，不能和文字逻辑题混在一个蓝图里。
- 这张表以外的图推细分（功能元素、图形间关系等）和科学推理**没有生成器，不要承诺出题**，用粉笔/外采真题。
- 排计划时图推主力仍是粉笔真题；程序题用于点名的弱项加练和变式，计划里写明「系统程序出图」。

### 申论（广东省考：县镇卷 / 省市卷）

只调 `shenlun_quiz.py`（后台跑，整卷约 5–10 分钟，特训约 2–4 分钟）：

```bash
python3 /home/ubuntu/ExamSystem/scripts/shenlun_quiz.py generate --batch-id 'YYYYMMDD_hermes_申论_01' --paper 县镇卷
```

- 整卷：不给 `--types`，按 2024–2026 真题结构出 8 份材料、3 题（归纳概括/提出对策/文章写作）。`--paper 省市卷` 出省市卷。
- 题型特训：`--types 归纳概括,提出对策`（可重复、最多 3 道），每道配一份两到四段短材料。
- `--theme` 指定主题（逗号分隔）；不给就从 THEME_POOL 随机抽。材料虚构（化名），宏观背景可用真实政策名。风格照 `references/shenlun-style.md`。
- 申论题不进 AI 练题，用户在网页「申论」页手写拍照作答，交卷后按 [SHENLUN_REVIEW] 流程评分复盘。要点表和参考答案在用户交卷评分之后才显示。

## 模型：统一走 model_router，不绑定 gemini

**本节只适用于服务器链路（以及资料/申论等专用入口）。DSH 出题模式不调用 model_router，由 DSH 侧模型出题、子 agent 审核。**

所有出题脚本用 `model_router.py` 解析模型（`resolve_model("quiz_lite")` 等），事实来源是 `~/.hermes/model-router.json` 的 active profile。**流程脚本本身不绑定 gemini 3.8 flash。**

- 查看当前模型：`python3 /home/ubuntu/ExamSystem/scripts/model_router.py --show`
- 切换 active（如切到 deepseek）：`python3 /home/ubuntu/ExamSystem/scripts/model_router.py --apply-config deepseek`，或直接改 `~/.hermes/model-router.json` 的 `active` 字段。
- 按用途环境变量仍可覆盖：`QUIZ_LITE_MODEL`（quiz_lite）、`ZILIAO_GEMINI_MODEL` / `DAILY_GEMINI_MODEL`（资料）、`CLIPROXY_PDF_MODEL`（PDF）等。
- **注意能力位**：`supports_vision=false` 的模型（如 deepseek）不能跑视觉任务（录屏复盘、图片生成/审核、图推判图）。文字出题（数量/言语/逻辑/政治/常识）不受影响。
- 默认 profile 是 `gemini-cliproxy`（cliproxy 反代，`http://127.0.0.1:8889/v1`，密钥 `CLIPROXY_API_KEY`）。切模型后可用 `--plan-only` 先验证再正式出题。

## 审核机制

- **DSH 出题模式**：审核由 DSH 子 agent 完成——盲解官（不给答案独立解题，检查第二可成立选项）+ 考官（看答案核对五维与用法断言），证据写进 review.json 由 `--dsh-import` 校验。
- **服务器链路**：脚本内置独立命题与盲解官+考官双审：盲解官拿不到答案自己做一遍并检查第二个可成立选项；考官看到答案复算/核对语境，不接收盲解步骤。不合格只退回那几道重出（最多 `--rounds` 默认 3 轮），已通过的保留。`rounds` 多轮、`rejected` 有题号都是正常回流，不是故障。
- 全部通过后脚本自己签精简闸门收据并入库。成功 = `status=success` 且 `imported` 数量符合预期；审核通过但入库失败不能宣称题库已更新。
- 详细要求（跨题整批检查、言语/逻辑断言核查、难度评级口径）以 `hermes-skills/quiz-pipeline/SKILL.md` 第 2a 节为准。

## 知识目录（新增/拆分子点）

用户明确要保存知识点调整时，按 `gd-gongkao-coach/references/knowledge-content/README.md` 的 outline/get/apply 流程处理指定节点（`node scripts/knowledge-content.mjs outline/get/apply`）。写清独立识别信号、解题动作和相邻边界，保存后再 catalog。不要直接改源码、把子页标题临时拼成新标签、或为了拆分先出题。

## 第 3 步：回复

```
已入库 5 题，批次 20261021_dsh_中心理解_01
去 ExamSystem → AI 练题。
```

`rounds` 里的补题轮次、`seconds` 是排查用的，不用报给用户。

## 禁止

- 为找入口无目标翻长参考、自己拼题目草稿、自己跑闸门
- 工具失败后改写题目再发
- 把日练 图形5+逻辑15 套进专项小卷
- 没听清录音就改出快照里的「下一步候选」

## 详细参考（同仓库，按需读取）

- `hermes-skills/quiz-pipeline/SKILL.md` — Hermes 版完整流程（批次命名、蓝图、审核 2a/2b、政治、资料、申论全量口径）
- `hermes-skills/quiz-pipeline/references/politics-common-workflow.md` — 政治/常识原文核验执行口径
- `hermes-skills/quiz-pipeline/references/shenlun-style.md` — 申论风格
- `hermes-skills/gd-gongkao-coach/SKILL.md` — 教练规约（排计划、掌握度）

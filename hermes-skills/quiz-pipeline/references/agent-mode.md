# DSH 写题步骤（`--dsh-import`）

DSH 上的文字题一律按本文出题：DSH 自己写题、派子 agent 审核，脚本只负责选点与变式分配、形式化判定、预检、闸门和入库；不调用服务器上的出题模型。Hermes 不用本文，走 SKILL.md 第 2 步的脚本入口。适用于文字题：数量 / 言语 / 文字逻辑判断 / 政治 / 常识。图推（程序出图）、资料、申论不走这条，用 SKILL.md 里各自的专用入口。资料分析在 DSH 上同样直接调用流水线脚本：整套 `scripts/ziliao_agent_paper.py`，单篇或指定考点专项 `scripts/ziliao_material_pipeline.py`（参数见 SKILL.md「资料分析」），用 `pwsh` 后台运行等回执即可，不要自己写资料题。

灵活出题（点名知识点、可选考法变式、指定题量）走 `scripts/quiz_gm.py`，Hermes 与 DSH 同一命令，只是 `--actor` 不同。模块只限数量关系、言语理解、逻辑判断、资料分析。

```bash
python3 scripts/quiz_gm.py --module '逻辑判断' --point '削弱题型' --variant '某变式名' --count 5 --actor dsh --plan-only
python3 scripts/quiz_gm.py --module '资料分析' --point '统计术语' --variant '直接定位读数' --count 6 --actor dsh --import
```

文字题先 `--plan-only`（`--actor dsh` 即使不加也只出槽位），按返回的每个 `kaofa_variant_name` 写题，再走本文的审核和入库。资料题不要自己写，`--import` 交给脚本跑完一篇 N 题；指定了变式就必须整篇都是该变式。省略变式则由脚本在该知识点内分配。

参数抽取、目录查询、命名、难度口径与 Hermes 完全相同（见 SKILL.md「一套流程，平台只决定谁写题」），本文只写 DSH 写题与派审的步骤。命令示例统一写成 shell 命令，按本平台的后台方式执行（见 SKILL.md「平台差异」）。

## 流程

1. 抽取参数（同 SKILL.md 第 1 步）。言语先查最近 14 天的避让清单（见下文「话题/句式避让」）。
2. **跑 `--plan-only` 取每题考法变式，这是出题对齐的硬前提**：

   ```bash
   python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '<模块>' --batch-id '<batch_id>' --blueprint '{"slots":[...]}' --plan-only
   ```

   返回的 `slots[]` 里每题有 `kaofa_variant_name`、`brief`（"本题考法变式：xxx…必须按此变式命题"）和讲解卡 `definition`。逐题按分配的变式命题，不出清单外的考法。言语逻辑填空另有 `vocab_word` 和 `vocab_brief`：正确选项必须包含该词，题干不能写出该词，不得照抄词库例句。同一 `batch_id` 重新导入时指定词不变。
3. 按变式生成题目 JSON（stem / options / answer / analysis / question_type）。≥15 题注意答案字母均衡（任一字母 ≤40%）。
   **言语题在派审前先打乱正确项字母**（选项没有大小关系，不能整卷堆在 A）：

   ```bash
   python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --batch-id '<batch_id>' --balance-verbal <题目文件>
   ```

   用打印出来的题目继续派审。文件里已经有 `review` 时不能再打乱。Hermes 走脚本出题时，这一步在审核前自动完成。
   **逻辑演绎题（翻译推理、真假推理、组合排列-单题）每题另写 `formal`**，程序穷举判定答案唯一，判定通过的题可免独立核查官（格式见下文「演绎题 formal」）。确实无法有限穷举的写 `formal_skip` 说明原因，照常走三角色审核。
4. **取待核查原句清单**：把题目（题目数组或 `{"questions":[...]}`）写成文件，用同一组 `--module / --blueprint / --batch-id` 跑：

   ```bash
   python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py <同一组参数> --dsh-claims <题目文件>
   ```

   返回每题 `claims`（带 `claim_index`，与闸门同一切分）和 `fields`（本模块要哪些核查字段）。**不要自己切句**；改了解析就重新取。
   带 `formal` 的题另返回 `items[].formal`：`verdict=REJECT` 时按 `issues`（如“A、D 都满足设问，答案不唯一”）先改题再重跑本步，**不要带着判定失败的题去派审**；`verdict=PASS` 时 `items[].fields` 只列考官要给的字段（`necessity_checks`、`formal_ok`、`formal_reason`）。
5. 派子 agent 审核（三角色，与 Hermes 脚本内审核同一口径）。按 ≤5 题一组拆开，每组一个盲解官 + 一个考官并行；言语/判断推理每组再加一个独立核查官——但 formal 判定 PASS 的演绎题不需要独立核查官，一组全是这类题就只派盲解官 + 考官。同时最多 6 个子 agent（约 3 组），当前批返回后再起下一批。
   - 盲解官：只给题干选项（不给答案）→ answer / steps / also_valid / unsolvable / actual_difficulty / difficulty_reason
   - 考官：给题干、选项、答案、解析、讲解卡、该题 `kaofa_variant_name`、该题 claims → verdict / actual_difficulty / analysis_check / necessity_checks / 五维标志 / variant_match / issues
   - 独立核查官（言语/判断推理）：不给答案，给题干选项和该题 claims → usage_checks；判断推理另给 question_check
6. 组装 review.json：blind / examiner 的键是全局题号（从 1 起），核查官的 usage_checks / question_check 并入同题 examiner 项。
7. **预检**：同一组参数加 `--dsh-check review.json`。它在临时目录跑完导入校验 + 签收 + 闸门复核，一次列出所有题的问题；不写批次目录、不入库、不占 batch_id。只修被点名的题或补漏判的句子，再预检，直到 `status=checked`。
8. 同一组参数加 `--dsh-import review.json`，后台执行 → 闸门 → 入库。成功回执 `status=success`、`imported=N`；失败把 `message` 原样告诉用户。
9. 万一正式导入仍失败：失败证据自动移到 `_dsh-failed/` 留档，**沿用同一 batch_id 和 blueprint** 修好重导，不换号、不整批重来。

## 话题/句式避让（言语）

```bash
cd /home/ubuntu/ExamSystem && python3 -c "import sys; sys.path.insert(0,'scripts'); from yanyu_variety import recent_yanyu_avoid; import json; print(json.dumps(recent_yanyu_avoid('data/exam.db'), ensure_ascii=False))"
```

按返回的 `recent_molds`（连用 ≥2 次的句式套路）、`recent_openings`（开头 22 字）、`recent_topics`（主题指纹）避开。`family_counts` 达到 3 次及以上的主题族必须换主题。10 题是一批，不要拆成两次 5 题；某一题不过就只改那一题。

## review.json 格式

```json
{
  "module": "数量关系",
  "auditor": "dsh-subagent",
  "questions": [
    {"stem": "...", "options": [{"key": "A", "text": "..."}], "answer": "C", "analysis": "...", "question_type": "single"}
  ],
  "review": {
    "blind": {"1": {"answer": "C", "steps": "...", "also_valid": [], "unsolvable": false, "actual_difficulty": "easy", "difficulty_reason": "..."}},
    "examiner": {"1": {"verdict": "PASS", "actual_difficulty": "easy", "difficulty_reason": "...", "analysis_check": "...", "necessity_checks": [{"claim_index": 0, "valid": true, "reason": "依据"}], "difficulty_ok": true, "kaodian_ok": true, "style_ok": true, "analysis_ok": true, "brief_ok": true, "variant_match": {"ok": true, "reason": "按'指标偷换属性'命题：论据是销量指标、结论是品质属性，识别指标不代表目标属性", "quote": "销量连续三年位居第一"}, "issues": []}}
  }
}
```

- `auditor` 固定写 `dsh-subagent`（闸门据 `dsh-` 前缀识别 DSH 审核）；写成其他前缀会被闸门拒绝。
- **逐句断言字段**（`necessity_checks` / `usage_checks`）：每条写 `claim_index`（取自 `--dsh-claims`，从 0 起）**或**直接抄原句 `claim`，加 `valid`（布尔）和 `reason`（依据）。必须覆盖该题 claims 的每一句；清单为空给 `[]`。缺句、对不上原句、缺依据或 `valid=false` 都会被逐条点名退回，脚本不代填通过。
- 各模块要哪些字段以 `--dsh-claims` 返回的 `fields` 为准：数量只要考官 `necessity_checks`（多数题清单为空）；言语另要独立核查官 `usage_checks`；判断推理的清单是**解析的每一句**，另要 `usage_checks` 和 `question_check`（`reason` 以 `PASS` 开头）。言语/判断/政治常识 auto 难度按盲解官+考官两位**较低评级**记录。
- 槽位分配了 `kaofa_variant_name` 时，考官项**必须**有 `variant_match`：`ok` 为 true，`reason` 写明"按『<变式名>』命题：<本题如何落到该变式的解题动作>"，不能写"无细分考法"；`quote` 从**当前**题干或选项原样摘出体现该变式的一段（≥6 字），程序会核对这段话确实在题面里。改稿后必须重新核对，不能沿用旧理由。
- 导入时会和数据库里近 60 天同一父考点的历史题查重（与批内撞题同一阈值）。报"与历史题 xxx 撞题"就换情境和陈述结构重出，只换人名物名不够。
- formal 判定 PASS 的演绎题：考官项加 `formal_ok: true` 与 `formal_reason`（逐条对照题干条件、选项与设问的依据），不写 `usage_checks`、`question_check`；闸门会按题目里的 `formal` 亲自重判。

## 演绎题 formal

写在题目对象里，与 stem 同级：

```json
"formal": {
  "vars": [{"name": "甲", "values": ["1", "2", "3", "4"]}, {"name": "考核", "values": ["bool"]}],
  "background": ["distinct(甲, 乙, 丙, 丁)"],
  "constraints": ["甲 != 1", "implies(证书, 考核)", "exactly(1, 甲真, 乙真, 丙真)"],
  "options": {"A": "丁 == 1", "B": "甲 == 4", "C": "丙 == 4", "D": "乙 == 2"},
  "ask": "must_true"
}
```

- 表达式用 Python 写法：and/or/not、比较、in、+ - * %，函数 implies/iff/count/exactly/atleast/atmost/distinct/adjacent/abs/int/min/max。数字写成字符串，程序自动当整数；类别值在表达式里加英文双引号。取值组合 ≤40 万。
- 真假推理：每人一句话设布尔量，`iff(甲真, 该句完整内容)` 绑定，再写真话人数。全称句对每个对象分别建模；“或”默认相容。
- `ask`：must_true（一定为真/可以推出）、must_false（一定为假）、possible（可能为真）、not_must_true（不能推出）、sufficient_premise（补充哪项能推出，另写 `conclusion`）、max/min（另写 `target`，选项写整数）。
- 自查命令：`python3 scripts/logic_model.py formal.json --answer B`。

## 出题要求

- 数值选项 A→D **要么升序要么降序**，否则被 `local_issues` 拦截。
- 分数、根号、π 等公式一律写在 `$…$` 里（带分数写 `$10\frac{10}{11}$`），裸写 `\frac` 网页会显示源码；脚本会自动补，补不上的会被退回。
- 概率题：题干的单次概率和四个选项一律用最简分数（胜率写 `$\frac{3}{5}$`，选项写 `$\frac{81}{625}$`），不用百分数或小数，否则被退回。
- 答案字母与选项一致；判断题 A=正确 / B=错误；多选答案按升序拼接。
- analysis 至少 30 字，可复算。判断推理的解析每一句都要被两位审查方逐句核查，写得简洁、每句都站得住；数量/言语尽量少用「只能/必须/必然」和用法限制断言，出现就会进入核查清单。
- 题干 ≥15 字，像广东省考真题，锁定考法不发散。
- **文字逻辑按广东真题的推理量出，默认 auto 也一样**（与 Hermes 命题要求同源，全文见 `scripts/quiz_reasoning.py` 的 `REAL_LEVEL`、`DEDUCTION_DEPTH`、`ARGUMENT_DEPTH`）：
  - 翻译推理给 3–4 条相互关联、句式混用的条件，或两条可串联的假言；不出“一条规则加一个事实”的一步题。题干不得替考生翻译（“即……”“也就是说”“换言之”“等价于”会被程序退回）。
  - 组合排列 3–5 条条件且每条都参与推理；设问多用“如果……则必然正确”“补充哪项可以确定”“判断错误/不可能的是”；不要四项都给完整对应、扫一遍就排除完。
  - 真假推理至少 3 人表态且含复合命题，需借助矛盾、反对关系或假设代入。
  - 论证题要有具体机制或数据和不直白的缺口；至少一个半对干扰项；设问覆盖“需要补充的前提”“最不能支持”等。
  - formal 的结构设定（每人一个、只选一人、无并列）写进 `background`；程序会逐条删去 `constraints` 重判，凑数条件超过 1 条或真正用到的条件少于 2 条即退回。

## 子 agent 提示词模板

**盲解官**（不给答案）：

```
你是广东省考行测独立做题人（盲解官）。读取 <题目文件>（只有题干选项，无答案）。
自己算每道题，输出 JSON：{"blind": {"1": {"answer": "A", "steps": "完整步骤", "also_valid": [], "unsolvable": false, "reason": "", "actual_difficulty": "easy/mid/hard", "difficulty_reason": "..."}}}
- steps 写出每一步算式和数值，禁止跳步；逐个选项检查还有没有第二个也成立（also_valid）
- 条件不足/矛盾/无正确选项 → unsolvable=true 并给 reason
- actual_difficulty 按实际必需解法评定：easy 常规步骤；mid 一个额外独立条件；hard 至少两个相互制约条件或分段讨论
- 言语改按辨析动作逐条对照，取最高一档：easy 线索直接指向答案、错项差别明显；mid 需结合上下文比较、辨析一对近义词或搭配、识别一层转折递进，或排除一个接近的干扰；hard 需两个及以上相互依赖的动作（线索隐含须先概括、多空相互制约、同时辨析程度与对象，或至少两个干扰项须细致比较）
- 判断推理改按思考动作逐条对照，取最高一档：easy 矛盾/标志词/论证缺口原样给出、一步可得；mid 需一次等价转换（只有…才、除非…否则）、反对关系、一次假设代入，或排除一个与正确项接近的干扰；hard 需两个及以上相互依赖的动作（多步转换、圈外复合命题判假后取反、假言连锁、分情况讨论，或至少两个干扰项须比较力度）
```

**考官**（给答案、解析、讲解卡、claims）：

```
你是广东省考行测命题审核官。读取 <题目文件>（含题干选项答案解析）。下面附带各题考点讲解卡 definition，作为考法口径依据；另附各题待核查原句清单 <claims，来自 --dsh-claims>。
逐题核对五维：difficulty_ok（难度对档）/kaodian_ok（锁定考法，对照讲解卡）/style_ok（像真题）/analysis_ok（解析可复算）/brief_ok（无额外要求）。
输出 JSON：{"examiner": {"1": {"verdict": "PASS", "actual_difficulty": "easy/mid/hard", "difficulty_reason": "...", "analysis_check": "重算过的推导", "necessity_checks": [{"claim_index": 0, "valid": true, "reason": "依据"}], "variant_match": {"ok": true, "reason": "依据", "quote": "题面原文片段"}, "difficulty_ok": true, "kaodian_ok": true, "style_ok": true, "analysis_ok": true, "brief_ok": true, "issues": []}}}
- actual_difficulty：判断推理按思考动作清单评档（与盲解官同一口径：easy 原样给出一步可得；mid 一次等价转换/反对关系/一次假设代入；hard 两个及以上相互依赖的动作），difficulty_reason 写出本题实际用到的动作。
- necessity_checks：对该题 claims 清单每一句给一条 {claim_index, valid, reason}；成立 valid=true 并写依据，存在反例或推理漏洞 valid=false 并写反例。清单为空给 []。不得跳句。
- variant_match：题目文件注明“本题考法变式：xxx”时，核对本题实际设问结构与解题动作是否属于该变式（对照讲解卡与变式要求），返回 {"ok": true, "reason": "按'xxx'命题：<本题如何落到该变式>", "quote": "从当前题干或选项原样摘出体现该变式的一段，≥6字"}；退回该考点最常见默认考法、或只换场景不换解题动作 → ok=false 并写明差在哪。题目文件确实没注明任何变式时，才给 {"ok": true, "reason": "无细分考法"}。
- 任一 false → REJECT 并在 issues 写明；全部 true 才 PASS
```

考官审带 formal 的演绎题时，另附该题 `formal` 与 `--dsh-claims` 返回的 `items[].formal`，并加一句：“核对 formal 是否忠实于题面：每个题干条件都有对应约束、无题干之外的条件、选项表达式与选项文字意思一致（全称/特称、或的相容、端点、主体）、ask 与设问一致；返回 formal_ok 与 formal_reason，不忠实则 REJECT。”

**独立核查官**（言语/判断推理，不给答案；formal 判定 PASS 的演绎题不需要）：

```
你是现代汉语用法/逻辑条件独立核查官，不做选择题、不知道标答。读取 <题目文件>（题干和选项），另附各题待核查原句清单 <claims，来自 --dsh-claims>。
对清单里每一句逐条判定：成立且有依据 → valid=true；存在自然反例或逻辑漏洞 → valid=false，reason 给具体反例。不得跳句，不得自己另挑句子。
输出 JSON：{"usage": {"1": {"usage_checks": [{"claim_index": 0, "valid": true, "reason": "..."}], "question_check": {"valid": true, "reason": "PASS ..."}}, ...}}
- usage_checks：言语、判断推理都要，覆盖该题 claims 全部句子；清单为空给 []
- question_check：仅判断推理；核对题面条件完整、答案唯一，reason 以 PASS 开头（不通过写 REJECT 及原因，valid=false）
- 输出并入 review.json 同题 examiner 项的对应字段
```

## 入库命令示例

```bash
python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '数量关系' --batch-id 'YYYYMMDD_dsh_排列组合_01' \
  --blueprint '{"slots":[{"tag":"数量关系-数学运算-排列组合问题","count":3}]}' --dsh-check /home/ubuntu/ExamSystem/data/manual-dsh/review.json
# status=checked 后，把 --dsh-check 换成 --dsh-import，后台执行
```

- **blueprint 必须与第 2 步 `--plan-only` 一致**（变式分配由 module + blueprint 决定，与 batch_id 无关）。
- **闸门校验**：盲解官答案等于题面键定答案、also_valid 为空、考官五维全 true、逐句断言覆盖全部原句且成立、批内不撞题、难度槽位一致、选项排序；有变式时 `variant_match` 须 ok=true 且 reason 非空。`--dsh-check` 与正式导入跑同一套校验。审核证据不达标会被拒，不是故障。
- **被拒处理**：只修被点名的题（题干/解析/审核证据）或补漏判的句子，沿用同一 batch_id 和 blueprint 重跑 `--dsh-check`；已通过的题不用重写。改了某题解析要重新 `--dsh-claims` 并重审该题断言。
- 子 agent 的读文件工具可能读不到 /tmp，题目文件和 review.json 放在 `/home/ubuntu/ExamSystem/data/manual-dsh/` 下，或让子 agent 用 shell 读取。
- 命中流程缺口（不改代码就过不去）时，按 `dsh-generality-gaps.md` 第 4 节兜底并登记 backlog，不改代码。

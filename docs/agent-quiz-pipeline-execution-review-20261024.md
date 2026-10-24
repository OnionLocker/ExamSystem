# 判断推理·真假推理 10 题出题执行过程复盘（Agent 出题链路）

> 面向工程师 Agent 的优化输入文档。记录一次真实的 agent 出题全过程（判断推理·真假推理，10 题），标注每个环节的耗时归因、真实摩擦点与可优化/可自动化点。
>
> - 日期：2026-10-24
> - 模块：判断推理　考点：`判断推理-逻辑判断-真假推理`
> - 题量：10　难度：auto　批次：`20261023_dsh_真假推理_03`
> - 总耗时：约 53 分钟（墙钟时间，绝大多数为等待）
> - 执行平台：DeepSeek Harness（DSH），agent 出题方式（`--dsh-claims / --dsh-check / --dsh-import`）

---

## 0. 结论先行（耗时归因摘要）

53 分钟墙钟时间的分布（约）：

| 环节 | 占比 | 说明 |
|---|---|---|
| **6 个子 agent 并行逐句审核 + 主 agent 逐批收尾等待** | ~70–80% | 墙钟主体 |
| **批号冲突排查 + 换号重核** | ~15% | `_01`/`_02` 已被占用 |
| **子 agent 输出不全补收、布尔字面量修正、quote 人工核对** | ~5–10% | 流程摩擦 |
| 脚本本身（plan-only / dsh-claims / dsh-check / dsh-import） | 秒级 | 非瓶颈 |

**并发声明**：6 个子 agent 是在同一个消息里一次性发起（真并发，同一轮 6 个 id 同时返回），并非串行。并发不缩短墙钟，因为每个子 agent 自身耗时较长（逐句断言），且主 agent 逐批收结果、逐批开新回合推进。

---

## 1. 完整执行过程

### 阶段 0：参数抽取与目录确认

1. `node scripts/knowledge-content.mjs catalog '判断推理'` —— 查当前知识树，确认"真假推理"的稳定标签（粉笔 `模块-一级-二级`）。
2. 用 grep 从 catalog 大输出里筛出"真假推理"子点，确认下辖 `@lp-analytical-truth`、`@truth-opposition` 两个细分。

> catalog 输出很大（全树数百 KB），需翻长文本。**可优化**：直接用 `catalog '判断推理-逻辑判断'` 或传叶子 scope，避免全树返回。

### 阶段 1：plan-only 取考法变式分配（出题对齐的硬前提）

3. 前台跑：
   `python3 scripts/quiz_lite.py --module '判断推理' --tag '判断推理-逻辑判断-真假推理' --count 10 --batch-id '20261023_dsh_真假推理_01' --plan-only`
4. 返回 10 个 slot，每个带：稳定叶子 tag、讲解卡 `definition`、`kaofa_variant_name`、`brief`（命题指令）。本次分配：
   1 假言连锁真假　2 变形假言矛盾　3 圈外复合命题取反　4 选言命题矛盾　5 所有与有的不　6 假设某句为真　7 多真多假配额　8 两个有的必一真　9 每人两次猜测　10 两个所有必一假

> 输出 JSON 含**完整讲解卡 definition 全文**（每个约 2–3KB 中文），10 题共几十 KB。**可优化**：同一 scope 重复返回同一段 definition，属冗余传输。

### 阶段 2：按变式手写 10 道题目（核心创作，主 agent 人工做）

5. 逐题设计：每个变式一道，推演事实真值表、确保"答案唯一 + 配额成立 + 解析逐句站得住"。
   - 例题1（假言连锁）：构造 `甲陈加班 / 乙陈不加班` 矛盾对 + 圈外 `丙陈→刘、丁刘→赵` 假言链，穷举 8 种真假组合验证唯一解。
6. 写成 `data/manual-dsh/questions.json`（每题 stem/options/answer/analysis/question_type/kaofa_variant）。
7. 用脚本生成派生文件：`blind_all.json`（去答案）、`examiner_all.json`（含答案）、`claims.json`、`definitions.json`。

> 这一步纯手写+人工推演，是"慢"里最可控也最不可省的部分（agent 出题的定义即由主 agent 写题）。优化空间有限，只能靠写题质量一次过、减少审核退回。

### 阶段 3：dsh-claims 取逐句核查清单

8. 前台跑：
   `python3 scripts/quiz_lite.py --module '判断推理' --tag '判断推理-逻辑判断-真假推理' --count 10 --batch-id '...01' --dsh-claims data/manual-dsh/questions.json`
9. 返回每题的 `claims`（带 claim_index 的逐句清单）和 `fields`（本模块要：necessity_checks / usage_checks / question_check）。

> 命令秒级。**注意**：claims 是脚本按固定切分规则从解析里切出的，主 agent 不能自己切句、不能改解析后凭记忆对齐；规范要求"改了解析就重新 --dsh-claims"。

### 阶段 4：派 6 个子 agent 并行审核（墙钟最大头）

10. **同一个消息一次性发起 6 个 `subagent`（真并发）**：
    - 盲解官 题1–5（只读题干选项，盲解 + 查 second-valid）
    - 考官　 题1–5（读题干/选项/答案/解析/definition/claims，五维核对 + 逐句断言 + 变式核对）
    - 独立核查官 题1–5（读题干选项 + claims，不看答案逐句验逻辑 + question_check）
    - 盲解官 题6–10　考官 题6–10　独立核查官 题6–10

> **最慢环节**。6 个子 agent 各自：读文件 → 逐题逐句推理 → 写大段 JSON。墙钟主体。真并发但完成不齐 → 主 agent 逐批收结果、逐批开新回合，等待被拉长。

### 阶段 5：收尾——组装 review.json（有波折）

11. 逐批收取 6 个结果（消息交错到达）。
12. **缺口补收**：考官（题1–5）首条只回摘要，主 agent `send_message` 补要完整 JSON，多一次往返。
13. 手写组装脚本 `assemble_review.py`，把 blind/examiner/usage 三来源合并成 `review.json`：
    - examiner 每项 = 考官五维 + necessity_checks，**并入**独立核查官的 usage_checks + question_check
    - blind 键 = 全局题号 1–10；auditor 必须为 `dsh-subagent`
14. **踩坑**：JSON 里小写 `false`/`true` 被 Python 当变量名，sed 修正布尔字面量后才跑通。
15. 校验：盲解答案 vs 标答逐题一致、necessity/usage 对 claims **逐句全覆盖**（用 claims.json 核对）、所有 `variant_match.quote` 必须在题面原文中。
16. **发现题9 的 quote 不在题干**（"每位观众各对其中两幅画各猜了一句" vs 题干"甲乙丙三位观众…"），修正为题干原句"各对其中两幅画各猜了一句"。

> 摩擦点：①子 agent 输出不全要补收；②布尔字面量手写错误；③quote 与题干一致性需人工逐条核。均属"可由程序兜底/断言"的环节。

### 阶段 6：预检 --dsh-check

17. 后台跑 `--dsh-check review.json`（用 batch `_01`）。
18. **失败**：`batch_id 已入库 10 题，换一个序号` —— `_01`、`_02` 当天已被其他会话占用。
19. 排查批次目录，改用 `_03`，**重新跑 plan-only** 确认变式分配与题目一致（结果完全一致，10 个变式同序）。
20. 用 `_03` 重新 `--dsh-check` → `status=checked, 10/10`。

> 批号冲突是真实摩擦。**可优化**：参数抽取阶段先探测/分配未占用的 batch_id，而非撞号再换号重来。

### 阶段 7：正式入库 --dsh-import

21. 后台跑（同参数）`--dsh-import review.json` → `status=success, imported=10`，实际难度 easy 2 / mid 5 / hard 3，无 rejected，耗时 2 秒。

---

## 2. 优化点清单（按收益排序）

1. **batch_id 分配前置**：阶段 1 前探测未占用序号，避免"撞号 → 换号 → 重跑 plan-only 核对"。（省约 15%）
2. **子 agent 输出契约**：要求每个子 agent 一次性返回完整结构化 JSON（schema 校验 + 必填字段），避免"先摘要后补要"的往返。（省若干轮）
3. **组装自动化**：assemble 应直接吞子 agent 的 JSON 输出，布尔/quote 一致性由程序断言兜底，减少人工核对与手写错误。
4. **审核并行/数量**：评估能否在写题前预分配角色更早并发启动，以及是否可用更少的角色覆盖（现状 3 角色 × 2 组）。
5. **读写冗余**：plan-only 重复返回完整 definition、子 agent 各自读文件 —— 可换更紧凑的共享上下文 / 精简提示词。

---

## 3. 附：关键命令与产物位置

- 主入口：`scripts/quiz_lite.py`（agent 出题用 `--dsh-claims / --dsh-check / --dsh-import`）
- 知识树：`scripts/knowledge-content.mjs catalog '<scope>'`
- 本次中间产物：`data/manual-dsh/`（questions / blind_all / examiner_all / claims / definitions / review / assemble_review.py）
- 入库批次：`data/hermes-batches/2026-10-23/20261023_dsh_真假推理_03/`

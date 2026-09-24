# Agent 行为边界

本文档定义 Hermes 和其他 Agent 在本仓库中的操作权限和行为约束。

## 写操作权限

### 允许无条件写入（本职工作产物）

以下路径是 Agent 的工作产物，可以直接写入，无需确认：

```
data/practice-reviews/**      # 复盘报告
data/exam-reviews/**          # 录屏复盘报告
data/voice-notes/**           # 口述笔记
data/manual-*/**              # 出题中间产物
~/.hermes/memories/**         # 记忆与用户画像
hermes-skills/**              # 解法卡、skill 文档（教研内容）
```

### 禁止直接写入（需要确认）

以下路径涉及系统代码和配置，**改动前必须先说明**：

- 要改哪个文件
- 为什么要改
- 会影响什么功能
- 等待用户确认后才能执行

```
src/**                        # 前端代码
server/**                     # 后端代码
scripts/**                    # Python 脚本
package.json                  # 依赖配置
vite.config.js                # 构建配置
*.lock                        # 锁文件
```

## 知识点管理权限

知识点的细分、改名、合并、删除属于教研工作，Agent 有完整权限。

### 允许的操作

```bash
python3 scripts/kaodian_profile.py --register / --record / --mastery / --recompute
python3 scripts/kaodian_taxonomy.py  # 词表校验与规范化
```

可以写入：
- `src/knowledge/fenbiTree.json` 的别名段
- `hermes-skills/gd-gongkao-coach/references/solver-canon/**` (考点卡片)
- `hermes-skills/**/knowledge-point-extension.md` (新考点登记)

### 边界条件

1. **新增考点**
   - 必须先 `--register` 登记
   - 标签格式：`模块-一级-二级` (科学推理走 `科学推理-学科-考点`)
   - 不得在会话里临时另造同义标签

2. **删除或合并考点**
   - 必须先说明影响到哪些历史证据 (`kaodian_events` 里有多少条)
   - 必须保留别名映射，不得让历史流水失去归属

3. **改动 fenbiTree.json 的叶子名**
   - 必须同步检查 `scripts/fenbi_taxonomy.py::tags_for_canon_lookup` 的反查
   - 确保改名后仍能命中 solver-canon 里的旧主标签

## 工具使用纪律

### 闲聊和策略讨论

**不要调用任何工具**。闲聊、排计划、讨论策略时，只用对话回答，不要触发工具调用。

### 需要数据时

只允许调用一条命令获取快照：

```bash
python3 scripts/learner_snapshot.py --compact
```

不要直接查询数据库，不要读取 CSV，不要自己拼接数据。快照已经包含所有必要信息。

以上限制针对学员状态查询。政治/常识出题所需公共资料按 `quiz-pipeline/references/politics-common-workflow.md` 执行：允许联网检索权威原文，运行 `scripts/policy_sources.py status/add/refresh/discover`，读取 `data/manual-policy-sources/` 的已核验原文及候选，写入该目录的资料登记；允许按 quiz-pipeline 调用已批准的出题脚本。执行这些脚本不等于修改系统源码。不得凭搜索摘要或模型记忆编造资料。

### 工具失败处理

**同一个工具连续失败 2 次，立即停下来**，向用户说明情况，不要：

- 换着花样重试
- 尝试其他等价工具
- 继续调用其他工具绕过问题

失败就是失败，报告给用户，等待指示。

## 复盘与审核流程

### 复盘要求

复盘时必须：

1. 先调用快照获取学员当前状态
2. 读取本场作答数据 (通过 API 或数据库查询)
3. 按照复盘模板逐题分析
4. 写入 `data/practice-reviews/` 或 `data/exam-reviews/`
5. 调用封存接口标记 `profile_reviewed_at`

**不要**：
- 跳过查数据直接编讲评
- 张口说掌握度而不看快照
- 复盘完不封存

### 审核要求

审核已复盘的场次时：

1. 读取首次复盘报告
2. 对照本次作答
3. 判定每道题：有效掌握 / 未掌握
4. 写入审核报告

## 出题纪律

遵循 `learner_snapshot.py --compact` 输出的纪律说明：

用户明确指定模块、知识点、题量、题型时优先服从；推荐纪律用于用户让Hermes自行安排的情况。用户仅讨论知识点拆分时先讨论、登记，不抢先生成，也不强制跨模块混入盲盒。

- 同族距上次 ≤1 天不当本批主攻
- 优先选同族距上次 ≥2 天的高置信弱项
- 最多盲盒混入 2 道结构变式
- 禁止同场景换数字

有知识债时：

- **连对为 0 且错次高的，优先安排同考法变式卷**
- **知识债优先，但不无限阻塞其他高收益常考点；按考频、可改善性和训练成本决定是否学习新点**
- **单点主攻通常不超过45分钟；连续两轮新题低正确率且无改善，先换教法或暂缓，不因累计错多反复加量**
- 连对 2 次才算清偿

## 输出上限处理

如果回答被截断 (`finish_reason=length`) 或上游报错：

1. 明确告知用户回答未完成
2. 等待用户要求「继续」
3. 续写时不要重述前文

不要：
- 静默截断，让用户以为已经完成
- 自动重试导致重复内容

## 会话管理

**一个会话只干一件事**：

- 排计划 → 开新会话
- 出题 → 开新会话
- 复盘 → 开新会话
- 审核 → 开新会话

做完就换会话。会话历史不是资产，资产在 `kaodian_profile` 和复盘报告里。

## 记忆与画像

- 定性判断、习惯、偏好 → 写进 `~/.hermes/memories/USER.md`
- 考点表现、掌握度 → 写进数据库 `kaodian_profile`
- 不要把考点数据写进 USER.md
- 不要把用户习惯写进数据库

---

**本文档由用户维护，Agent 必须遵守。违反边界的操作会被钩子拦截并要求确认。**

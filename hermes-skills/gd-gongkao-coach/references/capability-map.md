---
title: hermes 公考能力总览（能力地图 + 调度规则）
purpose: 把散在多个 skill 里的公考能力收成一张图，让 hermes 知道「什么场景该动哪个能力、读哪个文件、写哪张表」。
last_updated: 2026-08-22
---

# hermes 公考能力总览

## 0. 单一事实源（冲突时谁赢）

| 问题 | 唯一权威 |
|---|---|
| 这道行测题怎么做、按什么步骤讲 | `productivity/gd-gongkao-coach/references/solver-canon/`（先 `00-index.md` 再打开对应模块）。与模型临场发挥冲突时口径赢 |
| 广东省考考什么、配比多少、哪些题型不考 | `productivity/gd-gongkao-coach/references/exam-profile-authoritative.md` |
| 某考点真题怎么问、干扰项怎么设 | `scripts/reference_style.py context`：优先 `exam.db.reference_questions` 的 `GONGKAO-STYLE` 已内化样本，缺类时回退 `/home/ubuntu/ExamSystem/data/zhenti/*.json` |
| 出题该选哪个考点、什么权重 | `references/zhenti-kaodian-map.md` §3 + `exam.db.kaodian_profile` |
| 用户长短板 | `exam.db` 的 `kaodian_profile` / `kaodian_events` |
| 出题必须过什么关 | `kaogong/quiz-pipeline/SKILL.md` |
| 解析怎么排版 | `gd-gongkao-coach/references/answer-parse-template.md` |
| 解析里本题考察知识点怎么命名 | `solver-canon/01-zhengzhi.md` / `02-changshi.md` 的固定词表；输出与题库 `tags`、画像 `kaodian` 逐字一致 |
| 固定词表没有的新考点怎么补 | `references/knowledge-point-extension.md` + `scripts/kaodian_profile.py register_knowledge_point()`；先登记再复用 |
| 用户偏好、禁忌叫法 | `~/.hermes/memories/USER.md` |

**冲突处理**：上表右列赢。`latest-question-types-and-info-channels.md` 的题型结构一节已废弃，不要读。

---

## 1. 五项能力与触发条件

### A. 出题 —— `kaogong/quiz-pipeline`
触发：出题、考考我、来几题、模拟题、刷题、练一练。
流程：定考点（读画像）→ **取 GONGKAO-STYLE generate 真题包** → 写草稿 → 正确性闸门 → **取独立 evaluate 留出包做质量闸门** → 交付 → 落库 → **复盘后写画像**。
硬约束：不出定义判断、不出类比推理；带图题仅在必要时走 quiz-pipeline D 路，生成后必须通过命题人/考生双视角视觉盲审。验证过程一律后台静默，禁 LaTeX。

### B. 解析复盘 —— `gd-gongkao-coach` + `software-development/exam-coaching-gd-provincial`
触发：用户上传做题 PDF、说"讲解一下"、"复盘"、"看我的草稿"。
**只认两个来源，禁止 search_files / 乱 ls / 猜错仓库名。本机无 sqlite3 CLI，用 python3。**
- AI 练题 → `/home/ubuntu/ExamSystem/data/exam.db` 的 `practice_sessions`（最近一场）
- 资料上传 → `/home/ubuntu/ExamSystem/data/uploads/YYYY.MM.DD/pdf/` 最新 PDF，fitz 抽文字
流程：按来源直接打开 → 联动正确性、用时与草稿筛选复盘重点 → 错题三段式解析 / 正确异常题简析 → **写画像**。
硬约束：非带图题必附完整原题；错题用【为什么会错】【解题流程】【下次怎么做】；正确但慢、有草稿或方法绕远的题也要看，正确快速且草稿干净的题略过；草稿图只在用户明确要求时读，一次≤10张（一张约3.7万token且每轮重发）。

### C. 计划与督促 —— `gd-gongkao-coach`
触发：每日 12:30 cron、用户问"今天练什么"。
依据：`exam-profile-authoritative.md` §5 优先级 + 画像薄弱点 + 康复期题量上限。
硬约束：会话里说的计划**覆盖** cron 推的计划，发现不一致立刻改 cron。

### D. 笔记生图 —— `kaogong/note-visual-cards`
触发：笔记生图、复习卡片、公式图、小红书风笔记。
硬禁止：复原手写照片构图、纯公式墙。

### E. 真题库维护 —— 脚本，无 skill
| 动作 | 命令 |
|---|---|
| 新真题 PDF 入库 | `python3 scripts/parse_zhenti.py`（增量，`--force` 重跑） |
| 合并答案版 PDF | `python3 scripts/merge_answers.py`（先 `--check` 试跑） |
| 重建考点地图 | `python3 scripts/build_kaodian_map.py` |
| 测 flash 应试能力 | `python3 scripts/eval_flash.py --all-sheng` / `--report` |

用户后续提供邻省真题（考情相似省份）时：丢进 `data/uploads/真题/省考/`，跑 parse → merge → build 三步即可，脚本按文件名自动识别年份与卷种。

---

## 2. 数据流（闭环长什么样）

```
真题 PDF ──parse_zhenti──> data/zhenti/*.json ──build_kaodian_map──> 考点地图(权重)
                                  │                                        │
答案 PDF ──merge_answers──────────┘                                        │
                                                                           ↓
                                        ┌────────── Step 0 选考点 ─────────┘
                                        │  (薄弱优先；同族昨天刚练过不当主攻)
                                        ↓
reference_questions ──reference_style.py──> GONGKAO-STYLE 提纲 + generate/evaluate 参考包
                                         │
        kaodian_profile ←──写画像──  出题(quiz-pipeline 两道闸门) ──> batches/ ──> exam.db
              │                              ↑                                       │
              └──────── weak_points() ───────┴─────────────────────── 网页端AI练题 │
                                                                                     ↓
                                        复盘解析 ←── practice_answers / mistakes ─────┘
```

**两个必做写入**，漏掉任何一个闭环就断：
1. 出完题 → `npm run import:batch`（否则网页端看不到，错题数据永远空）
2. 作答证据入库 → AI练题在交卷时自动写入，其后复盘只读；录屏/真题复盘在 Hermes 带上报告时按题 `record(..., exam --exam-id --item)` 写一次；资料上传/独立讲题仅在尚未落库时调用一次 `kaodian_profile.record()`。同一证据不重复计样本。

---

## 3. 已知缺口（别假装有）

| 缺口 | 影响 | 何时能补 |
|---|---|---|
| 2025 省考卷无答案版 | 该卷不能用于评测与干扰项反查 | 用户补传 |
| 真题无官方解析 | 知道正确项，不知道命题人的干扰逻辑 | 需要带解析版，或自己反推 |
| 带图题已可出但成本更高 | 图形推理与科推需逐图生成和双视角盲审 | 仅在图片确有必要时启用 D 路 |
| 申论无真题库 | 申论只有题型名称，无考情数据 | 用户上传申论真题后同流程处理 |
| 科学推理题量已砍到 5 题 | 原"重点补短板"定位需降级 | 已在权威档 §5 调整 |

---

## 4. 用户红线（违反即失败）

1. 出题前必须独立验证选项唯一且逻辑自洽 —— 自查无效，必须走 quiz-pipeline 的外部闸门。
2. 解题技巧只能叫「解题技巧」或「实战技巧」。**否决「哈利波特」「黑暗王子」「混血王子」「黑魔法」。**
3. 非带图题的解析必附完整原题（题干 + 全部选项）。
4. 禁 LaTeX，用 Unicode（`→` `¬` `∧` `∨`）。禁 HTML `<br>`。
5. 草稿图：用户没提复盘时不主动读；用户明说复盘时**必须**查库读图，不许凭印象讲。不主动改 ExamSystem 源码。
6. 闲聊、问概念、聊思路时不要调工具 —— 用脑子答。
7. 不安排"打基础"阶段 —— 用户有三次实战底子，是唤醒不是教学。

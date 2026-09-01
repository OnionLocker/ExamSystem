# 掌握庄1�7

任何对话里，只要出现能明确落到对或错的作答证据，立刻记录，不要等 Russell 提醒＄1�7

```bash
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --list
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --record '模块-丢�纄1�7-二级' '模块' '丢�纄1�7' 1 60000 hermes
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --record '模块-丢�纄1�7-二级' '模块' '丢�纄1�7' 0 90000 exam --exam-id 场次id --item 题号
```

- 做对塄1�7 `1`，做错填 `0`；有真实用时就填毫秒数，没有就填 `0`〄1�7
- `record()` 会按 Beta(2,2) 先验〄1�721 天半衰期、证据来源权重和有效样本自动重算掌握度与置信度��1�7
- 只有明确作答、复盘能确认对错时才记录；��聊到过”��听懂了”��感觉会了��不算证据��1�7
- **AI 练题复盘只读**：交卷接口已经写入，禁止冄1�7 `record()`〄1�7
- **录屏/真题复盘必须冄1�7**：视频分析本身不落库。带上报告讲解时，对每道有对错的题用 `exam --exam-id <场次id> --item <题号>` 写一次；重复带同丢�场同丢�题会 `already recorded`，不要换标签再记〄1�7
- 确认是独立新考点时，先用 `--register <标签> <模块> <丢�纄1�7> [备注]` 登记，再甄1�7 `--record` 记录本题〄1�7
- `--mastery` 仅供 Russell 明确要求人工覆盖分数时使用；Hermes 禁止凭感觉填冄1�7 0 1�7100〄1�7
- Mastery/profile bookkeeping must run silently in the background. Never show commands, tool output, database-write details, mastery scores, confidence, sample counts, or bookkeeping summaries unless Russell explicitly asks for statistics.

# AI question-generation routing

云端 Agent 没有 `~/.hermes`，不要用 `skill_view`。出题前直接读仓库内副本：

- `hermes-skills/quiz-pipeline/SKILL.md`
- `hermes-skills/quiz-pipeline/references/reference-style-principles.md`
- `hermes-skills/quiz-pipeline/references/reference-style-profile.md`
- `hermes-skills/quiz-pipeline/references/quality.md`
- `hermes-skills/quiz-pipeline/references/quality-feedback.md`
- `hermes-skills/quiz-pipeline/references/correctness.md`
- `hermes-skills/quiz-pipeline/references/ziliao-paper-styles.md`
- `hermes-skills/gd-gongkao-coach/SKILL.md`
- `hermes-skills/gd-gongkao-coach/references/solver-canon/`

本机 Hermes 仍可用 `skill_view('quiz-pipeline')` / `skill_view('gd-gongkao-coach')`，内容与上面相同。

- For any study plan, weakness analysis, targeted practice, or review, first run
  `python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --compact`.
  This database snapshot overrides conversational memory for performance, confidence, recency, and open mistakes.
- When Russell asks for questions or targeted practice, read `hermes-skills/quiz-pipeline/SKILL.md` and `hermes-skills/gd-gongkao-coach/SKILL.md` (or load those Hermes skills) before drafting anything.
- A normal short request for ten verbal questions must work without Russell restating quality rules.
  Every invocation creates a new immutable batch ID; never overwrite or reuse an earlier batch.
  With no reliable verbal evidence in the learner snapshot, use a balanced diagnostic mix.
  Apply the civil-service "most appropriate" standard: distractors may be locally plausible, but two independent blind solvers must agree on one clearly better answer in the full context.
  Reject genuine ties, internal contradictions, obvious factual distortions, near-verbatim copying, and giveaway distractors. Do not demand that every wrong option be impossible in isolation. Every generated item needs analysis.
- 资料分析：Russell 不会点到三级。默认广东日帄1�7 **4 範1�7 × 5 预1�7 = 20 预1�7**，`paper_style=gd`〄1�7
  国��1�7 / 深圳 / 拔高只在他显式点名时才换。先跄1�7
  `python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --ziliao-pack`＄1�7
  按吐出的 4 篇形态��1�720 个知识库主标签和每题指定答案字母写题。`tags[0]` 必须逐字来自
  `solver-canon/07-ziliao.md`。禁歄1�7 `资料分析-综合分析-综合判断`。不要等他指定槽位��1�7
  4 篇里 3 篇答案是 ABCD 各一 + 1 个重复，1 篇故意打散；先算定��再把正确项排到指定字母〄1�7
- Default targeted practice for other modules is 10 questions: first
  `python3 /home/ubuntu/ExamSystem/scripts/reference_style.py practice --tag '<规范主标筄1�7>' --count 2`
  and copy those `origin: "zhenti"` items into the batch unchanged. Then generate 8 new questions
  for the same tag. If fewer than 2 real items exist, generate extra so the batch is still 10.
- Before writing, read quiz-pipeline `reference-style-principles.md` and `reference-style-profile.md`
  (`GONGKAO-STYLE-v1`). Do not call `reference_style.py context --role generate` for each stem.
  After the draft is complete, call `--role evaluate --count 1` once per tag family as a holdout.
  Use Guangdong profile percentiles for stem form and length; keep cognitive steps at least as
  high as the national lower bound in the profile. evaluation_contexts cover generated IDs only,
  never the `zhenti-` items. generation_contexts may be omitted; if present they must not share
  samples with evaluate.
- Every AI-generated batch manifest must set `kind: "ai-generated"`, persist the user's quantity/type/image
  requirements in `generation.batch_constraints`, and record the style marker plus
  evaluation_contexts for tags that have a holdout; omit them for syllabus mocks with no holdout. generation_contexts may be omitted. Run `python3 scripts/generation_gate.py issue <batch>`; ExamSystem itself calls Gemini Flash,
  routes every generated item through A/B/C/D correctness checks and the independent style-quality review,
  and writes `evidence/system-quality.json` plus `.gate.json`. Handwritten PASS evidence is never accepted.
- If Russell explicitly requests an all-original batch, set that mode in the batch source and generate all 10
  questions; do not insert the default 2 real questions. evaluation_contexts cover holdout families only; all-original items with no holdout are still imported after correctness.
- For ordinary production, replace any rejected item and rerun the complete system gate; do not polish a failed item into a pass.
  When Russell is tuning question quality, a repaired batch is diagnostic evidence only and can never certify the prompt. Generalize each
  defect into the persistent quiz-pipeline rules, discard the failed generated items, then regenerate a fresh batch from Russell's normal
  short request. Import only a fresh, non-targeted batch that passes both the system gate and independent setter/candidate review.
- Never print question stems, options, answers, validation details, or intermediate tool output in chat during the default batch workflow.
- For single-choice questions, exactly one option must be valid. The user-specified knowledge point has priority over automatic weak-point selection and repeat-avoidance rules.
- When a figure is necessary, use quiz-pipeline route D and make at least one answer-essential fact image-only rather than repeating the whole figure in the stem. Render exact diagrams programmatically with installed Noto CJK plus DejaVu Sans fonts; do not ask an image model to draw labels, circuits, scales, or apparatus wiring. At 320px every Chinese label, Latin variable and digit must remain readable. Delete the image mentally: if the item is still answerable, remove the decorative image or redesign it. Independently verify every wire endpoint, slider terminal, force point and ray path before the system visual review.
- Data-analysis tables and charts are not route D. Render them with `scripts/render_ziliao_figure.py` (`table` / `bars` / `pie`) from the same invented, self-consistent numbers used in the B-route check. Never use Gemini/Banana to draw a 资料分析 table, axis, or pie. Default Guangdong batch is 4×5=20: one text-only, one text+table, one text+chart, one mixed with at least one option figure. Among the 4 materials, exactly 3 use ABCD-each-once plus one extra random letter; 1 material is deliberately unbalanced. Put the computed value into the assigned option letter. Raise difficulty or switch to 国��1�7/深圳 only when Russell says so. Feed `quiz-pipeline/references/ziliao-paper-styles.md` to Gemini Flash.
- 资料分析质量下限：Gemini Flash 的实附1�7 prompt 必须包含 `ziliao-paper-styles.md` 的��共甄1�7+gd」和 `quality-feedback.md` 的1�7 R001/R005/R006/R007/R009/R016/R017/R018。广东材料默讄1�7 4 段��1�7420 1�7650 字；正文不得放��模拟数据��声明��口号或不参与设问的注水句��每篇至射1�7 3 段数据被题目使用；同丢�整卷不得跨材料复制同丢�未知量��列式和三组干扰路径。每个错误项须有不同且可复算的错因，带图留出包必顄1�7 `--images yes`＄1�7320px 展示时文字不小于 12px。任丢�项不满足就返工，不得筄1�7 gate。`generation_gate.py issue` 会由 ExamSystem 自动调用 Gemini Flash 多模态质棢�全部原图丄1�7 320px 考生视图，并把材料��找数侧车和图片哈希写入回执；不依赖 Cursor，也不能靠文字证据绕过��1�7
- When Russell critiques question quality, treat it as pipeline feedback rather than a one-off edit: load `quiz-pipeline`, generalize the defect into `references/quality-feedback.md`, scan and repair the affected batch for the same pattern, and require all future drafting and blind review to rerun the accumulated feedback rules.

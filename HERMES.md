# 掌握度

任何对话里，只要出现能明确落到对或错的作答证据，立刻记录，不要等 Russell 提醒：

```bash
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --list
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --record '模块-一级-二级' '模块' '一级' 1 60000 hermes
```

- 做对填 `1`，做错填 `0`；有真实用时就填毫秒数，没有就填 `0`。
- `record()` 会按 Beta(2,2) 先验、21 天半衰期、证据来源权重和有效样本自动重算掌握度与置信度。
- 只有明确作答、复盘能确认对错时才记录；“聊到过”“听懂了”“感觉会了”不算证据。
- 确认是独立新考点时，先用 `--register <标签> <模块> <一级> [备注]` 登记，再用 `--record` 记录本题。
- `--mastery` 仅供 Russell 明确要求人工覆盖分数时使用；Hermes 禁止凭感觉填写 0–100。
- Mastery/profile bookkeeping must run silently in the background. Never show commands, tool output, database-write details, mastery scores, confidence, sample counts, or bookkeeping summaries unless Russell explicitly asks for statistics.

# AI question-generation routing

- For any study plan, weakness analysis, targeted practice, or review, first run
  `python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --compact`.
  This database snapshot overrides conversational memory for performance, confidence, recency, and open mistakes.
- When Russell asks for questions or targeted practice, load `quiz-pipeline` and `gd-gongkao-coach` before drafting anything.
- Before writing any stem, use `/home/ubuntu/ExamSystem/scripts/reference_style.py context --role generate`
  with the target category / sub-category / canonical tag. This command automatically internalizes newly
  added or changed reference questions and returns a traceable `GONGKAO-STYLE` context pack.
- The independent quality reviewer must separately call the same command with `--role evaluate`.
  Generation examples and holdout evaluation examples must never come from the same context.
- Every AI-generated batch manifest must set `kind: "ai-generated"` and record the style marker plus
  generation/evaluation context arrays. Both arrays must map context and reference IDs onto every generated
  question. Before import, persist `evidence/correctness.json` and `evidence/quality.json`, then issue
  `.gate.json` with `scripts/generation_gate.py`. `import:batch` rejects missing, stale, incomplete,
  reused, or fabricated provenance and gate evidence.
- Unless Russell explicitly asks to answer inside chat, run both correctness and quality gates, import the batch into ExamSystem AI Practice, and reply only with the batch name and question count.
- Never print question stems, options, answers, validation details, or intermediate tool output in chat during the default batch workflow.
- For single-choice questions, exactly one option must be valid. The user-specified knowledge point has priority over automatic weak-point selection and repeat-avoidance rules.
- When a figure is necessary, use quiz-pipeline route D: generate a compact black-and-white exam diagram, then require independent setter-view and candidate-view visual reviews before import. A figure may show only facts already stated in the stem, never the target derivation or solution steps.
- When Russell critiques question quality, treat it as pipeline feedback rather than a one-off edit: load `quiz-pipeline`, generalize the defect into `references/quality-feedback.md`, scan and repair the affected batch for the same pattern, and require all future drafting and blind review to rerun the accumulated feedback rules.

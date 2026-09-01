# Hermes 出题技能（仓库内副本）

本机 Hermes 原来把出题提示词放在 `~/.hermes/skills/`，不在 ExamSystem 仓库里。
云端 Agent 只能连 GitHub，所以这里存了一份同样的文件。

出题或质检前先读：

- `quiz-pipeline/SKILL.md` — 出题流水线、正确性/质量闸门
- `quiz-pipeline/references/reference-style-principles.md` — 命题硬规则
- `quiz-pipeline/references/reference-style-profile.md` — 真题风格画像
- `quiz-pipeline/references/quality.md`、`quality-feedback.md`、`correctness.md`
- `quiz-pipeline/references/ziliao-paper-styles.md` — 资料分析卷面
- `gd-gongkao-coach/SKILL.md` — 复盘与教练口径
- `gd-gongkao-coach/references/solver-canon/` — 各模块解题步骤

本机 Hermes 仍可用 `skill_view('quiz-pipeline')`；没有 Hermes 时直接读这些文件。
脚本（`reference_style.py`、`quality_orchestrator.py` 等）优先读本目录。

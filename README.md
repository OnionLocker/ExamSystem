# ExamSystem · 广东省考学习系统

React + Vite 前端、Express + SQLite 后端，配合 Hermes 完成按考点练习、草稿复盘、知识点维护和学习记录。

## 当前使用范围

- AI 按需出题：数量文字题、言语、纯文字逻辑判断、资料分析（含确定性图表）、有权威原文依据的政治理论与常识。
- 图形推理、空间推理、科学推理使用外部真题；实验图题不进入正式 AI 出题流程。
- 知识点掌握度按独立作答与复盘证据评估，历史表现、证据不足和待复测分别展示。
- 学习强度按实际计时区间去重；未知时长不估算成学习时间。
- 成语学习支持单词学习、近义辨析组、练习和来源查看。

Hermes 的当前操作入口见 [教练技能](hermes-skills/gd-gongkao-coach/SKILL.md) 与 [出题流程](hermes-skills/quiz-pipeline/SKILL.md)。

## 运行

需要支持 `--env-file` 和 JSON import attributes 的 Node.js（建议 22.12+）、Python 3，以及已配置的 Hermes。Python 出题、图表与 PDF 工具按现有环境使用 Pillow、matplotlib、PyMuPDF 等依赖。

```bash
npm ci
cp .env.example .env
# 修改 .env 中的密码和 Hermes 连接配置
npm run dev
```

生产模式使用 `npm run prod`。单独更新前端运行 `npm run build`：先生成资源再原子替换入口，保留旧资源以供已打开的页面使用。

## 验证

```bash
npm run lint
npm test
node scripts/test-web-publish.mjs
```

`npm test` 在临时数据库中运行本地回归，不调用真实模型；输出的是测试脚本通过数，每个脚本含多条断言。发布检查会实际构建并更新 `dist`。Hermes 联网冒烟测试与政策模型盲审需要单独显式运行，不属于本地回归。

## 数据与维护

- `src/`：学习界面；`server/`：API；`scripts/`：出题、评估和维护工具。
- `hermes-skills/`：当前教研规则、流程和知识内容种子。
- `data/`：个人作答、复盘、知识内容数据库及运行记录；`public/q-images/`：导入题图；`.env`：本机配置。它们不随代码 push，须另行备份。
- 知识正文使用 `scripts/knowledge-content.mjs` 维护，无需改前端源码或重新构建。
- `docs/` 中带日期的计划和交付报告为历史记录；当前能力与操作以以上技能文档和实际代码为准。

字符编码约定见 [DEVELOPMENT.md](DEVELOPMENT.md)，Agent 操作边界见 [AGENTS.md](AGENTS.md)。

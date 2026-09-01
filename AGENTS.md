# AGENTS.md

## Cursor Cloud specific instructions

省考练习系统（"STUDY!"）是一个单仓库应用，包含三个服务（详见 `package.json` 的 scripts 与 `DEVELOPMENT.md`）：

| 服务 | 命令 | 端口 | 说明 |
|---|---|---|---|
| WEB（前端） | `npm run dev:web` | 5173（**HTTPS，自签证书**） | Vite + React。浏览器会报证书不受信任，需手动放行（Advanced → Proceed）。 |
| SERVER（后端） | `npm run dev:server` | 3001 | Express + better-sqlite3（nodemon 热重启）。启动时自动建库并 seed 3 道样题。 |
| HERMES（可选 AI 后端） | `npm run start:hermes` | 9119 | 依赖仓库外的 `hermes` 二进制，本环境**未安装**，启动会失败——属预期，不影响前后端练题主流程。 |

`npm run dev` 会用 concurrently 同时拉起以上三个。因为没有 `hermes` 二进制，HERMES 那一路会退出报错但不影响其余两路。若想要干净日志，分别单独跑 `dev:web` 和 `dev:server` 即可。前端通过 Vite 代理 `/api/*` → `http://localhost:3001`（含 WebSocket）。

启动前置：
- 必须有 `.env`（见 `.env.example`）。至少设置 `EXAM_PASSWORD`（登录密码），以及 `HERMES_SESSION_TOKEN`（否则 `start:hermes` 会因缺 token 直接退出）。
- 登录：前端登录页输入 `EXAM_PASSWORD` 的值即可（无用户名）。token 存于 `data/auth-tokens.json`。

非显而易见的坑：
- **npm 镜像**：提交的 `package-lock.json` 里 `resolved` 曾全部指向内网腾讯云镜像 `mirrors.tencentyun.com`，在云端不可达，会导致 `npm install` 失败（better-sqlite3 / tailwind oxide 等原生包下载不到）。update script 会把这些 URL 改写回 `registry.npmjs.org`（保留版本与 integrity，幂等）。如果该 lockfile 修复未被合并，每次拉新代码后这些内网 URL 会回来，靠 update script 里的 sed 兜底修复。
- `npm run lint`（eslint）可正常运行，但仓库有 **3 个预先存在的 lint 错误**（`src/hermes/HermesContextPickers.jsx`、`src/practice/NumericPractice.jsx`），与环境配置无关，非本次改动引入。
- 数据库文件在 `data/`（`*.db*`，git 忽略）。重置数据只需删掉 `data/exam.db*` 后重启后端。
- 全链路强制 UTF-8（无 BOM）。编辑任何文件都不要切成 GBK 保存，否则会双重编码乱码，详见 `DEVELOPMENT.md`。

### AI 练题 / 大模型 / Hermes

- **做题不需要大模型**：前端"AI 练题"模块（`src/aiPractice/`）消费的是数据库里按 `batch_id` 聚合的题组（`/api/questions/meta/batches`），做题、判分、错题落库全在本地，不调任何大模型。
- **出题 / 质检才调大模型**：`scripts/generation_gate.py` → `scripts/quality_orchestrator.py`（系统质检）、`scripts/eval_flash.py`（真题自测）、`scripts/ziliao_visual_gate.py`（资料分析视觉质检）等，都通过一个 **OpenAI 兼容端点（cliproxy）** 调 Gemini。相关环境变量（默认值）：
  - `CLIPROXY_BASE_URL`（默认 `http://127.0.0.1:8889/v1`）— 本机 cliproxy 代理地址；云端没有这个本地代理，需改指向可访问的 OpenAI 兼容端点。
  - `CLIPROXY_API_KEY`（必需，无默认）— 缺失时出题/质检脚本直接报错。
  - 模型默认 `gemini-3.7-flash-high`（`QUALITY_GATE_MODEL` / `CLIPROXY_PDF_MODEL` / `MENTOR_EVAL_MODEL` / `ZILIAO_VISUAL_REVIEW_MODEL`）；配图用 `gemini-3.1-flash-image`（`QUESTION_IMAGE_MODEL`）。
  - 未配置上述任何变量时，**AI 出题/质检无法运行**；但做题、普通练习、导入已生成批次（若数据库已有对应真题库/上下文）不受影响。
- **AI 出题批次导入依赖历史数据**：`import-batch.mjs` 会跑 `generation_gate.py verify`，要求数据库里存在 `reference_context_runs` 记录与真题库（`reference_questions`）。这些是本机长期积累、`data/` 不入 git 的数据，全新数据库导入现成 `batches/*` 会因缺上下文而失败。调试做题闭环时可直接向 `questions` 表插入带 `batch_id` 的题（前端即会列为 `imported` 批次）。
- **Hermes 是本机专有 CLI**（`hermes serve`，见 `scripts/start-hermes.mjs`、`server/routes/hermesChat.js`），不在本仓库、不在公共源，云端无法安装，`/api/hermes/ws` 会一直 `ECONNREFUSED 9119`。Hermes 只是对话外壳，真正出题逻辑在本仓库脚本里；出题技能提示词的仓库内副本见 `hermes-skills/`。
- **Python 依赖**：出题/质检/PDF 管线需要 `Pillow`（`PIL`）与 `PyMuPDF`（`fitz`），仓库无 `requirements.txt`，由 update script 用 `pip install --user` 安装。

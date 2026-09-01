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

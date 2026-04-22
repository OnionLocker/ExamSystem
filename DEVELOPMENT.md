# 省考练习系统 - 开发规范

## 一、字符编码（最高优先级，必须严格遵守）

**本项目从磁盘到浏览器全链路使用 UTF-8，不允许任何环节使用 GBK / GB18030 / GB2312 / CP936。**

### 1.1 文件保存编码

| 文件类型 | 编码 | BOM | 换行 |
|---|---|---|---|
| `.js` / `.jsx` / `.ts` / `.tsx` | **UTF-8** | **无 BOM** | `LF` |
| `.html` | **UTF-8** | **无 BOM** | `LF` |
| `.css` / `.scss` | **UTF-8** | **无 BOM** | `LF` |
| `.json` | **UTF-8** | **无 BOM** | `LF` |
| `.md` | **UTF-8** | **无 BOM** | `LF` |
| `.env` / `.env.example` | **UTF-8** | **无 BOM** | `LF` |
| `.sql` | **UTF-8** | **无 BOM** | `LF` |

> 为什么不能有 BOM：部分 Node 解析器（尤其老版本）会把 BOM 当成普通字符，导致 JSON 解析失败、Shebang 失效等。

### 1.2 编辑器配置（必须）

项目根目录已提供 `.editorconfig`，所有编辑器需要安装/启用对该规范的支持。

- **VS Code / Cursor**：安装插件 `EditorConfig for VS Code`
- **JetBrains 系**：内置支持，确认已启用
- **Vim/Neovim**：安装 `editorconfig-vim`

**禁止**在编辑器里手动切换成 GBK 打开/保存项目里的任何文件。

### 1.3 终端 / Shell 编码

开发机需要使用 UTF-8 locale：

```bash
# Linux / macOS - 放到 ~/.bashrc / ~/.zshrc
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# 验证
locale            # 应显示 *.UTF-8
echo $LANG        # 应为 en_US.UTF-8 或 zh_CN.UTF-8
```

- **Windows**：使用 Windows Terminal + PowerShell 7+，并将系统语言设置为支持 UTF-8（控制面板 → 区域 → 管理 → Beta: 使用 UTF-8 提供全球语言支持）。**禁止**使用自带 `cmd.exe`（默认 CP936）。
- **服务器**：部署机必须是 `en_US.UTF-8`。`/etc/locale.gen` 启用后执行 `locale-gen`。

### 1.4 Git 配置

```bash
# 全局（推荐）
git config --global core.autocrlf input        # Linux/macOS
git config --global core.autocrlf false        # Windows 也建议 false，交由 .editorconfig 控制
git config --global core.quotepath false       # 路径里的中文不转义
git config --global i18n.commitEncoding utf-8
git config --global i18n.logOutputEncoding utf-8
```

项目已提供 `.gitattributes`，显式声明文本文件 `text / eol=lf / working-tree-encoding=UTF-8`，进一步防止本地编码错误污染仓库。

### 1.5 HTTP / 浏览器编码

**前端（Vite）**

- `index.html` 的 `<head>` **第一行**必须是 `<meta charset="UTF-8" />`
- `vite.config.js` 的 `forceUtf8Plugin` 插件强制所有 text 响应带 `; charset=utf-8`
- 禁止在 `index.html` 的 meta 之前插入任何 `<script>` 或含非 ASCII 的内容

**后端（Express）**

- `res.json(...)` 默认会带 `Content-Type: application/json; charset=utf-8`，无需额外处理
- 自定义 `res.send(text)` 必须显式设置：`res.setHeader('Content-Type', 'text/plain; charset=utf-8')`
- 数据库（SQLite）文本列默认按 UTF-8 存储，better-sqlite3 无需额外配置

### 1.6 数据库编码

- **SQLite**：本项目使用 better-sqlite3。文本列默认 UTF-8 存储。禁止用 BLOB 存字符串。
- 如未来切到 **MySQL**：必须 `utf8mb4` + `utf8mb4_unicode_ci`，不允许 `utf8`（MySQL 的 `utf8` 只是 3 字节，存不下 emoji）。
- 如未来切到 **PostgreSQL**：`CREATE DATABASE ... ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8' LC_CTYPE='en_US.UTF-8'`

### 1.7 常见乱码案例速查

| 现象 | 原因 | 修法 |
|---|---|---|
| 浏览器显示 `浣犲ソ` / `閹兼粎閸岋拷` 类乱码 | UTF-8 文件被浏览器按 GBK 解析 | 检查响应头是否带 `charset=utf-8`；检查 `<meta charset>` 位置是否在 `<head>` 开头 |
| 终端/日志里中文是 `??` | Locale 不是 UTF-8 | `export LANG=en_US.UTF-8` |
| `git log` 中文变 `\346\200` 八进制 | 未开启 `core.quotepath` | `git config --global core.quotepath false` |
| 粘贴代码后出现不可见字符 `\ufeff` | 文件有 UTF-8 BOM | 用 `dos2unix` 或编辑器"无 BOM 保存" |
| SSH 连上服务器中文乱码 | 客户端 locale 没传过去 | SSH 客户端设置 `SendEnv LANG LC_*`，服务端 `AcceptEnv LANG LC_*` |

### 1.8 双重编码（Mojibake）的识别与修复

**典型症状**：文件 `file --mime-encoding` 显示是 `utf-8`、响应头也带 `charset=utf-8`，但浏览器里中文全是乱码，且乱码字符本身都是生僻繁体/异体字（如 `鑰冪敓`、`閸楀洨楠囬弬瑙勵攳`、`浣犲ソ`）。

**原因**：文件曾被 "按 UTF-8 读字节 → 按 GBK 解码成文本 → 再按 UTF-8 保存" 处理过，造成双重编码。

**快速判断**（跑一次命令）：

```bash
python3 -c "
t = open('src/App.jsx','rb').read().decode('utf-8')
try:
    print('可能的原文:', t.encode('gbk').decode('utf-8')[:200])
except Exception:
    print('文件是干净的 UTF-8，不是 mojibake')
"
```

如果 "可能的原文" 读起来是通顺的中文，就说明被重编码了。

**修复**：项目内自带脚本 `scripts/fix-mojibake.py`，按启发式反解，不会伤及纯英文。

```bash
# 修复单个文件（会自动备份为 .bak）
python3 scripts/fix-mojibake.py src/App.jsx

# 仅预览不写入
python3 scripts/fix-mojibake.py --dry-run src/App.jsx

# 扫描整个项目
python3 scripts/fix-mojibake.py --all
```

**预防措施**：

1. 任何编辑器在打开本项目文件时必须用 UTF-8 打开，不要让编辑器"自动猜"编码。
2. 禁止在 VS Code / Cursor 中走 "Reopen with Encoding → GBK/GB18030" 后保存。
3. 传输用 `scp` / `rsync` / `git`，不要用会"智能转换编码"的工具（如某些 Windows SFTP 客户端的"文本模式"）。
4. SSH 两端 locale 都必须是 UTF-8（见 1.3）。

### 1.9 提交前自查命令

```bash
# 扫描整个项目，确认所有文本文件都是 UTF-8（或纯 ASCII）
find . -type f \
  \( -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" \
     -o -name "*.html" -o -name "*.css" -o -name "*.md" -o -name "*.json" -o -name "*.sql" \) \
  -not -path "./node_modules/*" -not -path "./.git/*" -not -path "./dist/*" \
  -exec sh -c 'enc=$(file -b --mime-encoding "$1"); case "$enc" in utf-8|us-ascii) ;; *) echo "NON-UTF8: $1 ($enc)";; esac' _ {} \;

# 扫描是否有 UTF-8 BOM
grep -rlI $'^\xEF\xBB\xBF' --include="*.{js,jsx,ts,tsx,html,css,md,json}" . 2>/dev/null
```

---

## 二、项目结构

```
ExamSystem/
├── index.html              # 入口 HTML（charset 必须最先声明）
├── vite.config.js          # Vite 配置（含 forceUtf8Plugin）
├── src/                    # 前端 React 源码
│   ├── main.jsx            # 入口
│   ├── App.jsx             # 根组件
│   ├── Login.jsx           # 登录页
│   ├── api.js              # 前端 API 封装
│   └── index.css           # 全局样式（Tailwind）
├── server/                 # 后端 Express 源码
│   ├── index.js            # 入口
│   ├── db.js               # better-sqlite3 封装
│   ├── auth.js             # 登录鉴权
│   └── routes/             # 业务路由
│       ├── questions.js
│       ├── practice.js
│       ├── mistakes.js
│       ├── reviews.js
│       └── stats.js
├── data/                   # SQLite 数据库文件（不进 git）
├── public/                 # 静态资源（favicon 等）
├── .env                    # 本地环境变量（不进 git）
├── .env.example            # 环境变量示例
└── DEVELOPMENT.md          # 本文档
```

---

## 三、本地开发

```bash
# 1. 安装依赖（只需首次）
npm install

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，至少设置 EXAM_PASSWORD=自定义密码

# 3. 同时启动前后端
npm run dev
# 前端 http://localhost:5173/
# 后端 http://localhost:3001/api/health
```

## 四、端口约定

| 端口 | 用途 |
|---|---|
| `5173` | Vite 前端开发服 |
| `3001` | Express 后端 API |

前端通过 Vite 代理 `/api/*` → `http://localhost:3001`，所以浏览器只需访问 `5173`。

## 五、常用命令

```bash
npm run dev          # 启动前后端（带 HMR）
npm run dev:web      # 仅启动前端
npm run dev:server   # 仅启动后端（nodemon 热重启）
npm run build        # 生产构建
npm run preview      # 预览 build 产物
npm run lint         # ESLint 检查
```

## 六、代码风格

- **组件**：函数组件 + Hooks，不使用 Class
- **命名**：React 组件 PascalCase；普通函数 camelCase；常量 UPPER_SNAKE_CASE
- **注释**：只在解释"为什么"时写，不写"这个循环是做什么"这种废话
- **中文**：UI 文案用中文；代码里的变量名/函数名/日志用英文
- **禁止**：任何形式的隐式变量污染、`var` 声明

## 七、Git 提交规范

```
<type>: <subject>

<body>
```

type 取值：`feat` / `fix` / `style` / `refactor` / `perf` / `test` / `docs` / `chore`

---

**最后强调一次：所有文件、所有终端、所有网络传输、所有数据库存储，一律使用 UTF-8，无 BOM。**

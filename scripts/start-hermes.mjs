// 启动 Hermes 后端（headless），供 ExamSystem 的 Hermes 对话页连接。
//
// 只绑 127.0.0.1：Hermes 自己的 WS 守卫会拒绝非 loopback 来源，对外暴露也没意义。
// 浏览器统一经 Express 的 /api/hermes/ws 代理进来。
//
// 由 npm run dev / npm run prod 通过 concurrently 拉起；--env-file=.env 已注入 token。
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const HOST = process.env.HERMES_HOST || '127.0.0.1';
const PORT = process.env.HERMES_PORT || '9119';
const TOKEN = process.env.HERMES_SESSION_TOKEN || '';

if (!TOKEN) {
  console.error('[hermes] ✗ .env 里缺少 HERMES_SESSION_TOKEN，无法启动');
  console.error('[hermes]   生成一个：node -e "console.log(require(\'crypto\').randomBytes(32).toString(\'base64url\'))"');
  process.exit(1);
}

// 找 hermes 可执行文件：PATH 之外还兜底几个常见安装位置
const candidates = [
  process.env.HERMES_BIN,
  path.join(os.homedir(), '.local/bin/hermes'),
  path.join(os.homedir(), '.hermes/bin/hermes'),
  '/usr/local/bin/hermes',
].filter(Boolean);

const bin = candidates.find((p) => {
  try { return fs.statSync(p).isFile(); } catch { return false; }
}) || 'hermes';

console.log(`[hermes] 启动 ${bin} serve → ${HOST}:${PORT}`);

const child = spawn(
  bin,
  ['serve', '--host', HOST, '--port', String(PORT), '--skip-build'],
  {
    stdio: 'inherit',
    env: { ...process.env, HERMES_DASHBOARD_SESSION_TOKEN: TOKEN },
  },
);

child.on('error', (err) => {
  console.error(`[hermes] ✗ 无法启动 ${bin}：${err.message}`);
  console.error('[hermes]   若 hermes 不在 PATH 里，可在 .env 设置 HERMES_BIN=/绝对/路径/hermes');
  process.exit(1);
});

child.on('exit', (code, signal) => {
  console.log(`[hermes] 已退出 code=${code} signal=${signal ?? 'none'}`);
  process.exit(code ?? 0);
});

// concurrently -k 会发信号过来，转发给子进程，避免留下孤儿
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    if (!child.killed) child.kill(sig);
  });
}

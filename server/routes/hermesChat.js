// Hermes 对话 WebSocket 代理
//
// 浏览器无法直连 Hermes：它的 WS 守卫会拒绝非 loopback 来源和 Origin 不匹配的连接
// （hermes_cli/web_server.py 的 _ws_client_is_allowed / _ws_host_origin_reason）。
// 所以这里由 Express 做一层逐帧转发：
//
//   浏览器 ──/api/hermes/ws?token=<exam_token>──▶ 本代理 ──?token=<hermes token>──▶ 127.0.0.1:9119/api/ws
//
// 浏览器侧用 ExamSystem 现有的 exam_token 鉴权；Hermes 的 session token 只存在于
// 服务端进程环境里，永远不下发到前端。协议本身不做任何改写，纯透传。
import { WebSocketServer, WebSocket } from 'ws';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Router } from 'express';

import { isValidToken } from '../auth.js';

const HERMES_HOST = process.env.HERMES_HOST || '127.0.0.1';
const HERMES_PORT = process.env.HERMES_PORT || '9119';
const HERMES_TOKEN = process.env.HERMES_SESSION_TOKEN || '';

const WS_PATH = '/api/hermes/ws';
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

// 浏览器只需要知道 Hermes 应该在哪个项目目录工作；绝对路径由服务端决定，
// 避免把开发机路径写进前端或提示词。
export const hermesRouter = Router();
hermesRouter.get('/context', (_req, res) => {
  res.json({
    project_root: PROJECT_ROOT,
    upload_root: path.join(PROJECT_ROOT, 'data', 'uploads'),
  });
});

// 上游地址。Hermes 只绑 loopback，故固定 ws:// 明文（不出本机）
const upstreamUrl = () =>
  `ws://${HERMES_HOST}:${HERMES_PORT}/api/ws?token=${encodeURIComponent(HERMES_TOKEN)}`;

// 给浏览器发一条 gateway 风格的 error 事件帧，让前端能显示原因而不是静默断线
const sendError = (ws, message, code) => {
  if (ws.readyState !== WebSocket.OPEN) return;
  ws.send(
    JSON.stringify({
      jsonrpc: '2.0',
      method: 'event',
      params: { type: 'error', payload: { message, code } },
    }) + '\n',
  );
};

export function attachHermesWs(httpServer) {
  if (!HERMES_TOKEN) {
    console.warn('[hermes] ⚠️  未配置 HERMES_SESSION_TOKEN，Hermes 对话页将无法连接');
  }

  const wss = new WebSocketServer({ noServer: true });

  httpServer.on('upgrade', (req, socket, head) => {
    let pathname;
    let token;
    try {
      const url = new URL(req.url, 'http://localhost');
      pathname = url.pathname;
      token = url.searchParams.get('token') || '';
    } catch {
      socket.destroy();
      return;
    }

    // 只接管自己的路径，其余 upgrade 留给别人（例如 Vite HMR）
    if (pathname !== WS_PATH) return;

    // 鉴权失败在 upgrade 阶段就拒绝，不建立 WebSocket
    if (!isValidToken(token)) {
      socket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n');
      socket.destroy();
      return;
    }

    wss.handleUpgrade(req, socket, head, (client) => bridge(client));
  });

  console.log(`[hermes] WS 代理已挂载 ${WS_PATH} → ${HERMES_HOST}:${HERMES_PORT}`);
}

// 建立 浏览器 ⇄ Hermes 的双向桥接
function bridge(client) {
  if (!HERMES_TOKEN) {
    sendError(client, '服务端未配置 HERMES_SESSION_TOKEN', 'no_token');
    client.close(1011, 'no token');
    return;
  }

  let upstream;
  try {
    upstream = new WebSocket(upstreamUrl());
  } catch (err) {
    sendError(client, `无法连接 Hermes：${err.message}`, 'upstream_error');
    client.close(1011, 'upstream error');
    return;
  }

  // 上游握手完成前，浏览器可能已经在发帧，先缓存
  const queue = [];
  let upstreamOpen = false;

  upstream.on('open', () => {
    upstreamOpen = true;
    for (const frame of queue.splice(0)) upstream.send(frame);
  });

  upstream.on('message', (data, isBinary) => {
    if (client.readyState === WebSocket.OPEN) client.send(data, { binary: isBinary });
  });

  upstream.on('error', (err) => {
    sendError(
      client,
      `Hermes 后端未启动或连接失败（${HERMES_HOST}:${HERMES_PORT}）：${err.message}`,
      'upstream_error',
    );
    if (client.readyState === WebSocket.OPEN) client.close(1011, 'upstream error');
  });

  upstream.on('close', (code, reason) => {
    if (client.readyState !== WebSocket.OPEN) return;
    // 1005/1006 是"无状态码/异常关闭"，不能原样回传给浏览器，否则 close 帧非法
    const safe = code >= 1000 && code <= 4999 && code !== 1005 && code !== 1006 ? code : 1000;
    client.close(safe, reason?.toString?.().slice(0, 120) || '');
  });

  client.on('message', (data, isBinary) => {
    if (upstreamOpen && upstream.readyState === WebSocket.OPEN) {
      upstream.send(data, { binary: isBinary });
    } else if (upstream.readyState === WebSocket.CONNECTING) {
      queue.push(data);
    }
  });

  client.on('close', () => {
    queue.length = 0;
    if (upstream.readyState === WebSocket.OPEN || upstream.readyState === WebSocket.CONNECTING) {
      upstream.close(1000, 'client gone');
    }
  });

  client.on('error', () => {
    if (upstream.readyState === WebSocket.OPEN) upstream.close(1011, 'client error');
  });
}

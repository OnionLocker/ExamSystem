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
import { execFile } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import { promisify } from 'node:util';
import { Router } from 'express';

import { isValidToken } from '../auth.js';

const runFile = promisify(execFile);

const HERMES_HOST = process.env.HERMES_HOST || '127.0.0.1';
const HERMES_PORT = process.env.HERMES_PORT || '9119';
const HERMES_TOKEN = process.env.HERMES_SESSION_TOKEN || '';

const WS_PATH = '/api/hermes/ws';
const WS_MAX_PAYLOAD = 256 * 1024 * 1024;
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

const TRANSCRIBE_MAX = 8 * 1024 * 1024;

hermesRouter.post('/transcribe', async (req, res) => {
  const dataUrl = String(req.body?.data_url || '');
  if (!dataUrl.startsWith('data:audio/') || !dataUrl.includes(',')) {
    return res.status(400).json({ error: '需要录音' });
  }
  const payload = dataUrl.slice(dataUrl.indexOf(',') + 1);
  const bytes = Buffer.byteLength(payload, 'base64');
  if (bytes < 200) return res.status(400).json({ error: '录音太短' });
  if (bytes > TRANSCRIBE_MAX) return res.status(400).json({ error: '录音过长，请分段说' });

  const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'hermes-voice-'));
  const dataFile = path.join(tmp, 'audio.url');
  try {
    await fs.writeFile(dataFile, dataUrl);
    const { stdout } = await runFile(
      'python3',
      [path.join(PROJECT_ROOT, 'scripts', 'transcribe_voice.py'), '--data-url-file', dataFile],
      { cwd: PROJECT_ROOT, timeout: 90_000, maxBuffer: 2 * 1024 * 1024 },
    );
    const result = JSON.parse(String(stdout || '').trim() || '{}');
    if (result.status === 'error') {
      return res.status(502).json({ error: result.message || '转写失败', ...result });
    }
    return res.json(result);
  } catch (err) {
    return res.status(502).json({ error: err?.message || '转写失败' });
  } finally {
    await fs.rm(tmp, { recursive: true, force: true }).catch(() => {});
  }
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

const hubs = new Map();

const upstreamLive = (ws) =>
  ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING);

const closeClient = (ws, code, reason) => {
  if (ws.readyState !== WebSocket.OPEN) return;
  const safe = code >= 1000 && code <= 4999 && code !== 1005 && code !== 1006 ? code : 1000;
  ws.close(safe, String(reason || '').slice(0, 120));
};

const getHub = (token) => {
  const existing = hubs.get(token);
  if (existing && upstreamLive(existing.upstream)) return existing;
  if (existing) {
    for (const client of existing.clients) closeClient(client, 1000, 'upstream replaced');
    existing.clients.clear();
  }

  const upstream = new WebSocket(upstreamUrl(), { maxPayload: WS_MAX_PAYLOAD });
  const hub = { token, upstream, clients: new Set(), queue: [] };
  hubs.set(token, hub);

  upstream.on('open', () => {
    for (const frame of hub.queue.splice(0)) {
      if (upstream.readyState === WebSocket.OPEN) upstream.send(frame);
    }
  });

  upstream.on('message', (data, isBinary) => {
    for (const client of hub.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(data, { binary: isBinary });
    }
  });

  upstream.on('error', (err) => {
    for (const client of hub.clients) {
      sendError(
        client,
        `Hermes 后端未启动或连接失败（${HERMES_HOST}:${HERMES_PORT}）：${err.message}`,
        'upstream_error',
      );
      closeClient(client, 1011, 'upstream error');
    }
  });

  upstream.on('close', (code, reason) => {
    if (hubs.get(token) === hub) hubs.delete(token);
    const text = reason?.toString?.() || '';
    for (const client of [...hub.clients]) closeClient(client, code, text);
    hub.clients.clear();
  });

  return hub;
};

export function attachHermesWs(httpServer) {
  if (!HERMES_TOKEN) {
    console.warn('[hermes] ⚠️  未配置 HERMES_SESSION_TOKEN，Hermes 对话页将无法连接');
  }

  const wss = new WebSocketServer({ noServer: true, maxPayload: WS_MAX_PAYLOAD });

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

    // 只接管自己的路径，其它 upgrade 留给别人（例如 Vite HMR）
    if (pathname !== WS_PATH) return;

    // 鉴权失败在 upgrade 阶段就拒绝，不建立 WebSocket
    if (!isValidToken(token)) {
      socket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n');
      socket.destroy();
      return;
    }

    wss.handleUpgrade(req, socket, head, (client) => bridge(client, token));
  });

  console.log(`[hermes] WS 代理已挂载 ${WS_PATH} → ${HERMES_HOST}:${HERMES_PORT}`);
}

// 浏览器断开时绝不关掉 Hermes：手机切后台 / 关网页不能把正在跑的一轮掐死。
// 同一 exam_token 重连接到同一条上游，事件继续流，前端 session.resume 把答完的内容捞回来。
function bridge(client, token) {
  if (!HERMES_TOKEN) {
    sendError(client, '服务端未配置 HERMES_SESSION_TOKEN', 'no_token');
    client.close(1011, 'no token');
    return;
  }

  let hub;
  try {
    hub = getHub(token);
  } catch (err) {
    sendError(client, `无法连接 Hermes：${err.message}`, 'upstream_error');
    client.close(1011, 'upstream error');
    return;
  }

  hub.clients.add(client);

  client.on('message', (data, isBinary) => {
    const { upstream } = hub;
    if (upstream.readyState === WebSocket.OPEN) {
      upstream.send(data, { binary: isBinary });
    } else if (upstream.readyState === WebSocket.CONNECTING) {
      hub.queue.push(data);
    }
  });

  const detach = () => {
    hub.clients.delete(client);
  };
  client.on('close', detach);
  client.on('error', detach);
}

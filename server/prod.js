// 生产模式启动器：纯 HTTP 静态服务 + API 代理
// 用法：node server/prod.js
// 在 4173 端口提供 dist/ 目录，/api 请求代理到后端 3001
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.join(__dirname, '..', 'dist');
const QUESTION_IMAGES = path.join(__dirname, '..', 'public', 'q-images');
const PORT = 5173;
const API_HOST = '127.0.0.1';
const API_PORT = 3001;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'text/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff': 'font/woff',
  '.woff2':'font/woff2',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.ogg': 'audio/ogg',
};

function serveStatic(req, res) {
  const rawUrl = req.url === '/' ? '/index.html' : req.url.split('?')[0];
  let cleanUrl;
  try {
    cleanUrl = decodeURIComponent(rawUrl);
  } catch {
    res.writeHead(400);
    res.end('Bad Request');
    return;
  }
  // 解码后再检查，连 %2e%2e 形式的越目录也一起拒绝。
  if (cleanUrl.includes('..')) {
    res.writeHead(400);
    res.end('Bad Request');
    return;
  }
  const reqExt = path.extname(cleanUrl);
  // 题库图片会在运行时持续导入，不能依赖 vite build 时复制到 dist。
  // /q-images/* 直接读取 public/q-images，其余前端资源仍走 dist。
  const isQuestionImage = cleanUrl.startsWith('/q-images/');
  let filePath = isQuestionImage
    ? path.join(QUESTION_IMAGES, cleanUrl.slice('/q-images/'.length))
    : path.join(DIST, cleanUrl);

  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) {
      // 关键：带扩展名的资源（.js / .css / .mp3 / .png 等）一律真 404，
      // 否则会把 HTML 当成 JS 返回，浏览器解析失败 → 整页白屏
      if (reqExt) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end('Not Found');
        return;
      }
      // 仅对无扩展名（SPA 路由路径）兜底到 index.html
      filePath = path.join(DIST, 'index.html');
    }

    const ext = path.extname(filePath);
    const mime = MIME[ext] || 'application/octet-stream';
    const isHtml = ext === '.html';

    fs.readFile(filePath, (readErr, data) => {
      if (readErr) {
        res.writeHead(500);
        res.end('Internal Server Error');
        return;
      }
      res.writeHead(200, {
        'Content-Type': mime,
        // index.html 不缓存，资源带 hash 可长期缓存
        'Cache-Control': isHtml ? 'no-cache, no-store, must-revalidate' : 'public, max-age=86400',
      });
      res.end(data);
    });
  });
}

function proxyApi(req, res) {
  const opts = {
    hostname: API_HOST,
    port: API_PORT,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `${API_HOST}:${API_PORT}` },
  };

  const proxyReq = http.request(opts, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on('error', () => {
    res.writeHead(502);
    res.end('Bad Gateway: API server unreachable');
  });

  req.pipe(proxyReq, { end: true });
}

// WebSocket 转发：Hermes 对话页走 /api/hermes/ws，需要把 upgrade 握手透传到 3001
function proxyUpgrade(req, clientSocket, head) {
  const proxyReq = http.request({
    hostname: API_HOST,
    port: API_PORT,
    path: req.url,
    method: 'GET',
    headers: { ...req.headers, host: `${API_HOST}:${API_PORT}` },
    // 升级请求得独占一条连接：走 keep-alive 连接池可能拿到已被后端关掉的旧 socket，
    // 而且 agent 的 5s 空闲超时会跟着套在升级后的长连接上
    agent: false,
  });

  proxyReq.on('upgrade', (proxyRes, upstreamSocket, upstreamHead) => {
    const lines = Object.entries(proxyRes.headers).map(([k, v]) =>
      Array.isArray(v) ? v.map((x) => `${k}: ${x}`).join('\r\n') : `${k}: ${v}`,
    );
    clientSocket.write(
      `HTTP/1.1 101 Switching Protocols\r\n${lines.join('\r\n')}\r\n\r\n`,
    );

    // 握手响应后面往往粘着对方发来的第一批数据帧（upstreamHead / head）。
    // 这些字节必须退回各自来源那一端的读缓冲，再开双向管道；
    // 退错了地方（把上游发来的帧 unshift 到 clientSocket），它会被当成浏览器发的帧
    // 原样回灌给上游 —— 服务端收到一个没掩码的帧，按协议错误 1002 直接断开。
    if (upstreamHead?.length) upstreamSocket.unshift(upstreamHead);
    if (head?.length) clientSocket.unshift(head);

    // 升级后就是一条长连接：去掉继承来的空闲超时，关掉 Nagle 攒包，底层开 TCP 保活
    for (const s of [clientSocket, upstreamSocket]) {
      s.setTimeout(0);
      s.setNoDelay(true);
      s.setKeepAlive(true, 30000);
    }

    upstreamSocket.pipe(clientSocket);
    clientSocket.pipe(upstreamSocket);

    // 任一端没了就把另一端一起收掉，不留半开连接
    const shutdown = () => { upstreamSocket.destroy(); clientSocket.destroy(); };
    upstreamSocket.on('error', shutdown);
    clientSocket.on('error', shutdown);
    upstreamSocket.on('close', shutdown);
    clientSocket.on('close', shutdown);
  });

  // 后端拒绝升级（例如 401）：把状态行回给浏览器再断开
  proxyReq.on('response', (proxyRes) => {
    clientSocket.write(`HTTP/1.1 ${proxyRes.statusCode} ${proxyRes.statusMessage}\r\n\r\n`);
    clientSocket.destroy();
  });

  proxyReq.on('error', () => clientSocket.destroy());
  // 注意：head 不能写进 proxyReq（那是 HTTP 请求体，会把握手包弄脏），
  // 升级成功后再退回 clientSocket 让它顺着管道走
  proxyReq.end();
}

const server = http.createServer((req, res) => {
  if (req.url.startsWith('/api')) {
    proxyApi(req, res);
  } else {
    serveStatic(req, res);
  }
});

server.on('upgrade', (req, socket, head) => {
  if (req.url.startsWith('/api')) proxyUpgrade(req, socket, head);
  else socket.destroy();
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`✅ 生产服务已启动：http://0.0.0.0:${PORT}`);
  console.log(`   API 代理 → http://${API_HOST}:${API_PORT}`);
});

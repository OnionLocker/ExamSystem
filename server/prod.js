// 生产模式启动器：纯 HTTP 静态服务 + API 代理
// 用法：node server/prod.js
// 在 4173 端口提供 dist/ 目录，/api 请求代理到后端 3001
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.join(__dirname, '..', 'dist');
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
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff': 'font/woff',
  '.woff2':'font/woff2',
};

function serveStatic(req, res) {
  const cleanUrl = req.url === '/' ? '/index.html' : req.url.split('?')[0];
  // 防越权：拒绝 .. 越目录
  if (cleanUrl.includes('..')) {
    res.writeHead(400);
    res.end('Bad Request');
    return;
  }
  const reqExt = path.extname(cleanUrl);
  let filePath = path.join(DIST, cleanUrl);

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
  });

  proxyReq.on('upgrade', (proxyRes, upstreamSocket, upstreamHead) => {
    const lines = Object.entries(proxyRes.headers).map(([k, v]) =>
      Array.isArray(v) ? v.map((x) => `${k}: ${x}`).join('\r\n') : `${k}: ${v}`,
    );
    clientSocket.write(
      `HTTP/1.1 101 Switching Protocols\r\n${lines.join('\r\n')}\r\n\r\n`,
    );
    if (upstreamHead?.length) clientSocket.unshift(upstreamHead);
    upstreamSocket.pipe(clientSocket);
    clientSocket.pipe(upstreamSocket);
    upstreamSocket.on('error', () => clientSocket.destroy());
    clientSocket.on('error', () => upstreamSocket.destroy());
  });

  // 后端拒绝升级（例如 401）：把状态行回给浏览器再断开
  proxyReq.on('response', (proxyRes) => {
    clientSocket.write(`HTTP/1.1 ${proxyRes.statusCode} ${proxyRes.statusMessage}\r\n\r\n`);
    clientSocket.destroy();
  });

  proxyReq.on('error', () => clientSocket.destroy());
  if (head?.length) proxyReq.write(head);
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

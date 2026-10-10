import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import vm from 'node:vm';
import { once } from 'node:events';
import { WebSocket, WebSocketServer } from 'ws';

// Exercise the real proxy against a delayed local handshake; no live auth or Hermes.
const source = fs.readFileSync(new URL('../server/routes/hermesChat.js', import.meta.url), 'utf8');
const received = [];
const upstream = new WebSocketServer({
  host: '127.0.0.1', port: 0,
  verifyClient: (_info, done) => setTimeout(() => done(true), 80),
});
await once(upstream, 'listening');
upstream.on('connection', (ws) => ws.on('message', (data, isBinary) => {
  received.push({ text: String(data), isBinary });
  ws.send(data, { binary: isBinary });
}));
const proxy = http.createServer();
const context = {
  WebSocket, WebSocketServer, URL,
  WS_MAX_PAYLOAD: 1024 * 1024, WS_PATH: '/api/hermes/ws',
  HERMES_TOKEN: 'isolated-test', HERMES_HOST: '127.0.0.1', HERMES_PORT: upstream.address().port,
  upstreamUrl: () => `ws://127.0.0.1:${upstream.address().port}`,
  isValidToken: (token) => token === 'isolated-test',
  sendError: (_ws, message) => { throw new Error(message); },
  console,
};
vm.runInNewContext(source.slice(source.indexOf('const hubs = new Map();')).replace('export function attachHermesWs', 'function attachHermesWs'), context);
context.attachHermesWs(proxy);
proxy.listen(0, '127.0.0.1');
await once(proxy, 'listening');
const client = new WebSocket(`ws://127.0.0.1:${proxy.address().port}/api/hermes/ws?token=isolated-test`);
let timer;
try {
  await once(client, 'open');
  const echoes = new Promise((resolve, reject) => {
    let count = 0;
    timer = setTimeout(() => reject(new Error('queued frames timed out')), 3000);
    client.on('message', () => { if (++count === 2) resolve(); });
  });
  client.send('queued-rpc');
  client.send(Buffer.from('queued-binary'));
  await echoes;
  assert.deepEqual(received, [
    { text: 'queued-rpc', isBinary: false },
    { text: 'queued-binary', isBinary: true },
  ]);
} finally {
  clearTimeout(timer);
  client.terminate();
  for (const ws of upstream.clients) ws.terminate();
  await Promise.all([
    new Promise((resolve) => upstream.close(resolve)),
    new Promise((resolve) => proxy.close(resolve)),
  ]);
}
console.log('Hermes queued WebSocket frames preserve text/binary type: ok');

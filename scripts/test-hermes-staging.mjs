import assert from 'node:assert/strict';
import fs from 'node:fs';
import WebSocket from 'ws';

const port = process.env.HERMES_STAGING_PORT || '8643';
const token = process.env.HERMES_SESSION_TOKEN || '';
const useProxy = process.env.HERMES_USE_EXAM_PROXY === '1';
let examToken = '';
if (useProxy) {
  const login = await fetch('http://127.0.0.1:3001/api/auth/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ password: process.env.EXAM_PASSWORD }),
  });
  ({ token: examToken } = await login.json());
  assert.ok(login.ok && examToken, 'ExamSystem login failed');
}
const url = useProxy
  ? `ws://127.0.0.1:3001/api/hermes/ws?token=${encodeURIComponent(examToken)}`
  : `ws://127.0.0.1:${port}/api/ws${token ? `?token=${encodeURIComponent(token)}` : ''}`;

const wav = Buffer.alloc(44 + 16000 * 2 / 5);
wav.write('RIFF', 0);
wav.writeUInt32LE(wav.length - 8, 4);
wav.write('WAVEfmt ', 8);
wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20);
wav.writeUInt16LE(1, 22);
wav.writeUInt32LE(16000, 24);
wav.writeUInt32LE(32000, 28);
wav.writeUInt16LE(2, 32);
wav.writeUInt16LE(16, 34);
wav.write('data', 36);
wav.writeUInt32LE(wav.length - 44, 40);

const ws = new WebSocket(url, { maxPayload: 256 * 1024 * 1024 });
let nextId = 0;
const pending = new Map();
let completeResolve;
const complete = new Promise((resolve) => { completeResolve = resolve; });

const frame = (method, params = {}) => {
  const id = `test-${++nextId}`;
  ws.send(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
  return id;
};

const request = (method, params = {}) => new Promise((resolve, reject) => {
  const id = `test-${++nextId}`;
  const timer = setTimeout(() => {
    pending.delete(id);
    reject(new Error(`${method} timeout`));
  }, 180000);
  pending.set(id, { resolve, reject, timer });
  ws.send(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
});

ws.on('message', (data) => {
  for (const line of String(data).split('\n')) {
    if (!line.trim()) continue;
    const frame = JSON.parse(line);
    if (frame.id && pending.has(frame.id)) {
      const call = pending.get(frame.id);
      pending.delete(frame.id);
      clearTimeout(call.timer);
      if (frame.error) call.reject(new Error(frame.error.message));
      else call.resolve(frame.result);
      continue;
    }
    if (frame.params?.type === 'message.complete') completeResolve(frame.params.payload);
  }
});

await new Promise((resolve, reject) => {
  ws.once('open', resolve);
  ws.once('error', reject);
  ws.once('close', (code) => reject(new Error(`websocket closed: ${code}`)));
});

const session = await request('session.create', {
  cwd: '/home/ubuntu/ExamSystem',
  source: 'web',
  hidden: true,
  title: 'upgrade-smoke',
});
assert.ok(session.session_id);
const attached = await request('audio.attach_bytes', {
  session_id: session.session_id,
  content_base64: wav.toString('base64'),
  filename: 'staging-smoke.wav',
  duration_ms: 200,
});
assert.equal(attached.attached, true);
assert.equal(attached.format, 'wav');
let pdfAttached = false;
if (process.env.PDF_SMOKE_PATH) {
  const pdf = fs.readFileSync(process.env.PDF_SMOKE_PATH);
  const result = await request('pdf.attach', {
    session_id: session.session_id,
    content_base64: pdf.toString('base64'),
    filename: 'staging-smoke.pdf',
    first_page: 1,
    last_page: 1,
  });
  assert.equal(result.attached, true);
  assert.equal(result.pages_attached, 1);
  pdfAttached = true;
}
await request('prompt.submit', {
  session_id: session.session_id,
  text: '这是一条隔离升级冒烟测试。请不要调用工具，只回复 AUDIO_OK。',
});
let completeTimer;
const payload = await Promise.race([
  complete,
  new Promise((_, reject) => {
    completeTimer = setTimeout(() => reject(new Error('message.complete timeout')), 180000);
  }),
]);
clearTimeout(completeTimer);
assert.equal(payload?.status, 'complete');
assert.match(String(payload?.text || ''), /AUDIO_OK/i);
frame('session.close', { session_id: session.session_id });
ws.close();
if (useProxy) {
  await fetch('http://127.0.0.1:3001/api/auth/logout', {
    method: 'POST',
    headers: { authorization: `Bearer ${examToken}` },
  });
}
console.log(JSON.stringify({
  version: '0.20.6',
  transport: useProxy ? 'ExamSystem WS proxy' : 'direct',
  audio_attach: true,
  pdf_attach: pdfAttached,
  provider_round_trip: true,
  response: String(payload.text || '').trim(),
}));

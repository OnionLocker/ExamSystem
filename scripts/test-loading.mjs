import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { createGzip, gunzipSync } from 'node:zlib';
import { pipeline } from 'node:stream';
import { imageMimeOf } from '../src/hermes/hermesProtocol.js';
import { mergeSegments } from '../src/studyLog/studyTime.js';

// Execute the production static handler on isolated files and an ephemeral port.
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'exam-loading-'));
fs.mkdirSync(path.join(temp, 'assets'));
const js = 'const greeting = "你好";\n'.repeat(300);
fs.writeFileSync(path.join(temp, 'assets/test-abcdefgh.js'), js);
fs.writeFileSync(path.join(temp, 'index.html'), '<html>entry</html>');
const prod = fs.readFileSync(new URL('../server/prod.js', import.meta.url), 'utf8');
const staticSource = prod.slice(prod.indexOf('const MIME ='), prod.indexOf('function proxyApi'));
const handler = new Function('fs', 'path', 'createGzip', 'pipeline', 'DIST', 'QUESTION_IMAGES', `${staticSource}\nreturn serveStatic;`)(fs, path, createGzip, pipeline, temp, temp);
const server = http.createServer(handler).listen(0, '127.0.0.1');
await new Promise((resolve) => server.once('listening', resolve));
const request = (pathname, headers = {}, method = 'GET') => new Promise((resolve, reject) => {
  http.get({hostname: '127.0.0.1', port: server.address().port, path: pathname, headers, method}, (res) => {
    const chunks = [];
    res.on('data', (data) => chunks.push(data));
    res.on('end', () => resolve({status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks)}));
  }).on('error', reject);
});
try {
  const compressed = await request('/assets/test-abcdefgh.js', {'accept-encoding': 'gzip, br'});
  assert.equal(compressed.status, 200);
  assert.equal(compressed.headers['content-encoding'], 'gzip');
  assert.equal(gunzipSync(compressed.body).toString(), js);
  assert.match(compressed.headers['cache-control'], /immutable/);
  assert.equal(compressed.headers.vary, 'Accept-Encoding');
  const plain = await request('/assets/test-abcdefgh.js', {'accept-encoding': 'gzip;q=0, *;q=1'});
  assert.equal(plain.headers['content-encoding'], undefined);
  assert.equal(plain.body.toString(), js);
  const cached = await request('/assets/test-abcdefgh.js', {'if-none-match': compressed.headers.etag});
  assert.equal(cached.status, 304);
  assert.equal(cached.body.length, 0);
  const head = await request('/assets/test-abcdefgh.js', {}, 'HEAD');
  assert.equal(head.body.length, 0);
  assert.equal(Number(head.headers['content-length']), Buffer.byteLength(js));
  assert.equal((await request('/absent.js')).status, 404);
  assert.equal((await request('/some/page')).body.toString(), '<html>entry</html>');
  assert.equal((await request('/%2e%2e/private')).status, 400);
} finally {
  await new Promise((resolve) => server.close(resolve));
  fs.rmSync(temp, {recursive: true, force: true});
}

const chat = fs.readFileSync(new URL('../src/hermes/HermesChat.jsx', import.meta.url), 'utf8');
const ref = (current) => ({current});
const calls = [], applied = [], displayed = [];
const gateway = {connectionState: 'open', request(method, params) {
  return new Promise((resolve, reject) => calls.push({method, params, resolve, reject}));
}};
const requestRef = ref(null), version = ref(0), stored = ref('old'), live = ref('old-live');
const cachedMessages = [{id: 'a1', content: 'cached A'}];
const cache = ref(new Map([['A', cachedMessages]]));
let loading = false;
const source = chat.slice(chat.indexOf('  const resumeSession ='), chat.indexOf('  const historySupportedRef ='));
const names = ['useCallback', 'gwRef', 'sessionRequest', 'sessionVersion', 'activeStoredIdRef', 'setActiveStoredId', 'sidRef', 'setSid', 'setMessages', 'sessionCache', 'setUsage', 'setSessionLoading', 'setStatus', 'setBanner', 'lastSessionSync', 'applyResume'];
const noop = () => {};
const resume = new Function(...names, `${source}\nreturn resumeSession;`)((fn) => fn, ref(gateway), requestRef, version, stored, noop, live, noop, (m) => displayed.push(m), cache, noop, (v) => { loading = v; }, noop, noop, ref(0), (res, id) => applied.push({res, id}));
const first = resume('A');
assert.deepEqual(displayed.at(-1), cachedMessages);
assert.equal(live.current, null);
assert.equal(resume('A'), first);
assert.equal(calls.length, 1);
const second = resume('B');
assert.equal(calls.length, 2);
calls[1].resolve({session_id: 'B-live'});
await second;
calls[0].resolve({session_id: 'A-live'});
await first;
assert.deepEqual(applied.map((x) => x.id), ['B']);
assert.equal(loading, false);
const failed = resume('C');
calls[2].reject(new Error('offline'));
await failed;
assert.equal(requestRef.current, null);
assert.equal(loading, false);
const retry = resume('C');
calls[3].resolve({session_id: 'C-live'});
await retry;
assert.deepEqual(applied.map((x) => x.id), ['B', 'C']);

// Real attachment delivery: legacy pasted images/drafts use image.attach_bytes.
const deliverySource = chat.slice(chat.indexOf('    const deliver ='), chat.indexOf('\n    try {\n      const spokenText'));
const methods = [];
const deliver = new Function('gw', 'images', 'audio', 'imageMimeOf', `${deliverySource}\nreturn deliver;`)(
  {request: async (method) => methods.push(method)},
  [{name: 'paste.png', dataUrl: 'data:image/png;base64,AA=='}, {name: 'draft.png', hidden: true, dataUrl: 'data:image/png;base64,AA=='}, {name: 'paper.pdf', mime: 'application/pdf'}, {name: 'note.txt', mime: 'text/plain'}], null, imageMimeOf,
);
await deliver('session', '请看图片');
assert.deepEqual(methods, ['image.attach_bytes', 'image.attach_bytes', 'pdf.attach', 'file.attach', 'prompt.submit']);

// Attach a review: bounded parallelism, question order, failed drafts and user images preserved.
const attachSource = chat.slice(chat.indexOf('  const attachPractice ='), chat.indexOf('  // ---------- 带上某场真题复盘'));
const items = Array.from({length: 7}, (_, i) => ({question_id: i + 1, draft_url: '/draft'}));
let inFlight = 0, maxInFlight = 0, attached, review, requestCount = 0;
const attach = new Function('useCallback', 'setAttaching', 'setBanner', 'api', 'uid', 'setPendingImages', 'setPendingReview', 'fmtDateTime', 'setShowPicker', 'stickToBottom', 'taRef', `${attachSource}\nreturn attachPractice;`)(
  (fn) => fn, noop, noop, async (url) => {
    requestCount++;
    if (url.includes('/md?')) return {path: '/review.md', report: {session: {total: 7}, items}};
    const id = Number(url.split('/').at(-2));
    inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise((resolve) => setTimeout(resolve, (8 - id) * 2));
    inFlight--;
    if (id === 3) throw new Error('missing draft');
    return {data_url: `data:image/png;base64,${id}`};
  }, () => Math.random().toString(), (fn) => { attached = fn([{id: 'user-picture'}, {contextKind: 'practice', id: 'old-draft'}]); },
  (v) => { review = v; }, () => '', noop, ref(false), ref(null),
);
await attach(42);
assert.equal(maxInFlight, 4);
assert.equal(requestCount, 8);
assert.deepEqual(attached.map((item) => item.name || item.id), ['user-picture', 'q1-draft.png', 'q2-draft.png', 'q4-draft.png', 'q5-draft.png', 'q6-draft.png', 'q7-draft.png']);
assert.equal(review.draftCount, 6);
assert.equal(review.id, 42);
console.log('loading: static compression/cache, session races, image delivery, parallel review drafts OK');

// Hidden review pages must stop counting, without losing accumulated active time.
const reviewPage = fs.readFileSync(new URL('../src/review/Review.jsx', import.meta.url), 'utf8');
const dwellSource = reviewPage.slice(reviewPage.indexOf('const useReviewDwell ='), reviewPage.indexOf('const Review ='));
const timers = new Map(), dwellEntries = [];
const documentState = {visibilityState: 'visible', addEventListener() {}, removeEventListener() {}};
let cleanup, timerId = 0, clock = 100000;
const dwell = new Function('useEffect', 'setInterval', 'clearInterval', 'document', 'addEntry', 'mergeSegments', 'Date', `${dwellSource}\nreturn useReviewDwell;`)(
  (effect) => { cleanup?.(); cleanup = effect(); },
  (fn) => { timers.set(++timerId, fn); return timerId; }, (id) => timers.delete(id), documentState,
  entry => dwellEntries.push(entry), mergeSegments, {now: () => clock},
);
const tick = () => { clock += 1000; [...timers.values()].forEach((fn) => fn()); };
dwell(false); tick(); assert.equal(timers.size, 0);
dwell(true); tick();
dwell(false); tick(); assert.deepEqual(dwellEntries[0].timeSegments, [[101000, 102000]]);
dwell(true); documentState.visibilityState = 'hidden'; tick(); assert.equal(dwellEntries.length, 1);
documentState.visibilityState = 'visible'; tick(); tick();
dwell(false);
assert.deepEqual(dwellEntries[1].timeSegments, [[104000, 106000]]);
assert.equal(timers.size, 0);
console.log('loading: review dwell pauses while hidden OK');

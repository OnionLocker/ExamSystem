import assert from 'node:assert/strict';

import {
  coerceResumePayload,
  ensureStreamingAssistant,
  extractReview,
  finishAssistantMessage,
  isSystemInjectedNotice,
  mergeResumedMessages,
  normalizeHermesHistory,
  shouldAcceptRemoteResume,
} from '../src/hermes/hermesProtocol.js';
import { HIDDEN_SOURCES, sessionListReachable, sessionPickerMode } from '../src/hermes/hermesLayout.js';

let id = 0;
const nextId = () => `m${++id}`;
const deps = {
  nextId,
  parseAudioLen: () => 0,
  isAudioLabel: () => false,
};

assert.equal(isSystemInjectedNotice('[System: You edited code in this turn]'), true);
assert.equal(isSystemInjectedNotice('[CONTEXT COMPACTION — REFERENCE ONLY]'), true);
assert.equal(isSystemInjectedNotice(`\0json:[{"type":"text"}]`), true);
assert.equal(isSystemInjectedNotice('正常用户消息'), false);

const review = extractReview(
  '[USER_MESSAGE]\n复盘\n[/USER_MESSAGE]\n'
  + '/home/ubuntu/ExamSystem/data/practice-reviews/82-demo.md',
);
assert.equal(review.content, '复盘');
assert.equal(review.review.kind, 'practice');
assert.equal(review.review.id, 82);

const uploadReview = extractReview(
  '[USER_MESSAGE]\n\n[/USER_MESSAGE]\n'
  + '/home/ubuntu/ExamSystem/data/uploads/2026.08.16/pdf/专项智能练习（言语理解与表达）.pdf',
);
assert.equal(uploadReview.content, '');
assert.equal(uploadReview.review.kind, 'upload');
assert.equal(uploadReview.review.id, '2026.08.16/pdf/专项智能练习（言语理解与表达）.pdf');
assert.match(uploadReview.review.path, /data\/uploads\/2026\.08\.16\/pdf\//);
assert.equal(uploadReview.review.title, '专项智能练习（言语理解与表达）');

const history = normalizeHermesHistory([
  { role: 'user', text: '你好' },
  { role: 'user', text: '[Coding] Before you run tests/linters or call this done:' },
  { role: 'assistant', text: '这是一条足够长、用于验证上下文压缩恢复时完全相同消息会被去重的回复内容，并确保测试文本长度超过四十个字符。' },
  { role: 'assistant', text: '这是一条足够长、用于验证上下文压缩恢复时完全相同消息会被去重的回复内容，并确保测试文本长度超过四十个字符。' },
], deps);
assert.equal(history.length, 2);
assert.equal(history[0].role, 'user');
assert.equal(history[1].role, 'assistant');

let messages = ensureStreamingAssistant([], nextId);
messages = finishAssistantMessage(messages, '完成', nextId);
assert.equal(messages.length, 1);
messages = finishAssistantMessage(messages, '完成', nextId);
assert.equal(messages.length, 1);
messages = ensureStreamingAssistant(messages, nextId);
messages = finishAssistantMessage(messages, '完成', nextId);
assert.equal(messages.length, 1);

console.log('hermes protocol adapter: ok');

const { normalizeOriginalQuestionOptions } = await import('../src/hermes/reviewFormat.js');

const squeezed = normalizeOriginalQuestionOptions([
  '> **原题**',
  '> 下列哪个正确',
  '> **A.** 甲 **B.** 乙 **C.** 丙 **D.** 丁',
].join('\n'));
assert.match(squeezed, /> \*\*A\.\*\* 甲/);
assert.match(squeezed, /> \*\*B\.\*\* 乙/);

const places = [
  '> **原题**',
  '> 从A、B、C三个地点同时出发，到达D地。',
  '> **A.** 甲地',
  '> **B.** 乙地',
  '> **C.** 丙地',
  '> **D.** 丁地',
].join('\n');
const kept = normalizeOriginalQuestionOptions(places);
assert.match(kept, /从A、B、C三个地点同时出发，到达D地。/);
assert.doesNotMatch(kept, /> \*\*A\.\*\* B、C三个地点/);

const datacenter = normalizeOriginalQuestionOptions(
  '> **原题** 某大型数据中心运行准则规定：只有配备双路市电与自备发电机组，才能获批承接金融核心业务。已知某数据中心未配备双路市电与自备发电机组。由此可以推出： A. 该数据中心不能承接金融核心业务 B. 该数据中心签署了严苛的SLA容灾协议 C. 该数据中心未签署严苛的SLA容灾协议 D. 只要签署了SLA容灾协议，就能承接金融核心业务',
);
assert.match(datacenter, /> \*\*A\.\*\* 该数据中心不能承接金融核心业务/);
assert.match(datacenter, /> \*\*B\.\*\* 该数据中心签署了严苛的SLA容灾协议/);
assert.doesNotMatch(datacenter, /A\. 该数据中心不能承接金融核心业务 B\./);

const dottedStem = normalizeOriginalQuestionOptions(
  '> **原题** 从A. 甲地、B. 乙地、C. 丙地同时出发，到达D地。由此可以推出： A. 甲先到 B. 乙先到 C. 丙先到 D. 同时到',
);
assert.match(dottedStem, /从A\. 甲地、B\. 乙地、C\. 丙地同时出发/);
assert.match(dottedStem, /> \*\*A\.\*\* 甲先到/);

const compactPlaces = normalizeOriginalQuestionOptions('> **原题** 地点A.B.C.D同时出发。由此可以推出： A. 甲 B. 乙 C. 丙 D. 丁');
assert.match(compactPlaces, /地点A\.B\.C\.D同时出发/);
assert.match(compactPlaces, /> \*\*A\.\*\* 甲/);


const mathQ = normalizeOriginalQuestionOptions([
  '> **原题** 正方形区域 $OABC$（以 $O$ 为坐标原点）满足 $x+y\\le 4$。概率为：',
  '> **A.** $\\frac{4-\\pi}{8}$',
  '> **B.** $8-\\pi$',
  '> **C.** $\\frac{\\pi}{16}$',
  '> **D.** $\\frac{4-\\pi}{16}$',
].join('\n'));
assert.match(mathQ, /\$OABC\$/);
assert.match(mathQ, /\$x\+y\\le 4\$/);
assert.match(mathQ, /> \*\*A\.\*\* \$\\frac\{4-\\pi\}\{8\}\$/);
assert.match(mathQ, /\n>\n> \*\*A\.\*\*/);
assert.match(mathQ, /\n>\n> \*\*B\.\*\*/);
assert.doesNotMatch(mathQ, /OABCOABCOABC/);
assert.doesNotMatch(mathQ, /4-\\pi8/);

console.log('review option normalize: ok');

assert.equal(sessionPickerMode(767), 'sheet');
assert.equal(sessionPickerMode(768), 'sheet');
assert.equal(sessionPickerMode(1024), 'sheet');
assert.equal(sessionPickerMode(1366), 'sheet');
assert.equal(sessionPickerMode(1439), 'sheet');
assert.equal(sessionPickerMode(1440), 'docked');
assert.equal(sessionListReachable(820), true);
assert.equal(sessionListReachable(1024), true);
assert.equal(sessionListReachable(1366), true);
assert.ok(HIDDEN_SOURCES.has('weixin'));
assert.ok(HIDDEN_SOURCES.has('cron'));
console.log('hermes session picker layout: ok');

id = 0;
const syncDeps = {
  nextId,
  parseAudioLen: (text) => (String(text).includes('秒') ? 3 : 0),
  isAudioLabel: (text) => String(text).includes('语音'),
};
const localOnly = [
  {
    id: 'keep-1', role: 'user', content: 'hello', streaming: false,
    tools: [], thinking: '', images: [], audio: null, audioSec: 0, hadAudio: false, review: null,
  },
  {
    id: 'keep-2', role: 'assistant', content: 'hi there from hermes', streaming: false,
    tools: [], thinking: '',
  },
];
const remoteResume = coerceResumePayload({
  messages: [
    { role: 'user', text: 'hello' },
    { role: 'assistant', text: 'hi there from hermes' },
    { role: 'user', text: 'from phone' },
    { role: 'assistant', text: 'got your phone message' },
  ],
  running: false,
});
const synced = mergeResumedMessages(localOnly, remoteResume, syncDeps);
assert.equal(synced.some((message) => message.role === 'user' && message.content === 'from phone'), true);
assert.equal(synced.some((message) => message.role === 'assistant' && message.content === 'got your phone message'), true);
assert.equal(synced.filter((message) => message.role === 'user' && message.content === 'hello').length, 1);
assert.equal(shouldAcceptRemoteResume(localOnly, synced, remoteResume, false), true);

const inflightSynced = mergeResumedMessages(localOnly, {
  messages: [
    { role: 'user', text: 'hello' },
    { role: 'assistant', text: 'hi there from hermes' },
  ],
  inflight: { user: '[USER_MESSAGE]\nfrom phone\n[/USER_MESSAGE]', assistant: 'partial' },
  running: true,
}, syncDeps);
assert.equal(inflightSynced.some((message) => message.role === 'user' && message.content === 'from phone'), true);
assert.equal(inflightSynced[inflightSynced.length - 1].role, 'assistant');
assert.equal(inflightSynced[inflightSynced.length - 1].streaming, true);
console.log('hermes multi-client resume sync: ok');

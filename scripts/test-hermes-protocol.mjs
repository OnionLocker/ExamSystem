import assert from 'node:assert/strict';

import {
  ensureStreamingAssistant,
  extractReview,
  finishAssistantMessage,
  isSystemInjectedNotice,
  normalizeHermesHistory,
} from '../src/hermes/hermesProtocol.js';

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

const kepui = normalizeOriginalQuestionOptions([
  '> **原题**',
  '> 从A、B、C三个地点同时出发。下列分析正确的是： A. 电流减小 B. 电压减小 C. 功率增加 D. 总功率增加',
].join('\n'));
assert.match(kepui, /从A、B、C三个地点同时出发/);
assert.doesNotMatch(kepui, /> \*\*A\.\*\* 、B、C三个地点/);
assert.match(kepui, /> \*\*A\.\*\* 电流减小/);
assert.match(kepui, /> \*\*D\.\*\* 总功率增加/);

console.log('review option normalize: ok');

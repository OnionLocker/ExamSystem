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

console.log('review option normalize: ok');

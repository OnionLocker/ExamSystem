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

const {
  collapseMaterialBlankLines,
  formatPlainSubscripts,
  normalizeOriginalQuestionOptions,
  normalizePhysicsSubscripts,
  splitOrderingSentences,
} = await import('../src/hermes/reviewFormat.js');

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
assert.doesNotMatch(kepui, /\*\*原题\*\*/);

const ordering = normalizeOriginalQuestionOptions([
  '> **原题**',
  '> ①量子计算利用量子叠加与纠缠等特性，具备在特定问题上远超经典计算机的算力潜力。②然而，由于量子比特对环境噪声极度敏感，微小的温度波动或电磁干扰都会引发退相干效应。③如何有效抑制退相干并实现高精度的量子纠错，成为当前量子计算迈向商用化的核心瓶颈。④近年来，伴随物理学与信息技术的交叉融合，量子计算研发进入了加速发展阶段。⑤这一物理瓶颈导致量子计算在维持长时间相干态和大规模比特扩展上困难重重。⑥全球科研团队正通过超导电路、离子阱及拓扑量子等多种技术路径展开集中攻关。将以上6个句子重新排列，语序正确的是:',
  '> **A.** ①④②⑤③⑥',
  '> **B.** ④①②③⑤⑥',
  '> **C.** ④②①⑤⑥③',
  '> **D.** ①②⑤③④⑥',
].join('\n'));
assert.doesNotMatch(ordering, /原题/);
assert.match(ordering, /> ① 量子计算利用量子叠加/);
assert.match(ordering, /> ② 然而，由于量子比特/);
assert.match(ordering, /> ⑥ 全球科研团队正通过超导电路/);
assert.match(ordering, /将以上6个句子重新排列，语序正确的是/);
assert.match(ordering, /> \*\*A\.\*\* ①④②⑤③⑥/);
assert.doesNotMatch(ordering, /① 量子计算[^\n]*②/);
const orderLines = ordering.split('\n').filter((line) => /^> [①-⑥]/.test(line));
assert.equal(orderLines.length, 6);

const optionMarks = splitOrderingSentences('正确顺序是 A. ①④②⑤③⑥ B. ④①②③⑤⑥');
assert.equal(optionMarks, null);

const analysis = normalizeOriginalQuestionOptions([
  '> 三种结构：①前对策引出话题后直接给观点并论证；②后对策先分析再给对策；③总分结构总句是重点。',
].join('\n'));
assert.match(analysis, /三种结构：①前对策/);
assert.doesNotMatch(analysis, /> ① 前对策/);

console.log('review option normalize: ok');

const circuit = normalizePhysicsSubscripts(
  '此时 $R_1$ 的功率：$PR1(初) = I_1^2 R1 = (0.4)^2 \\times 10 = 1.6 W$。回路电流 $I1 = 0.4 A$。PR1(末) 另算。',
);
assert.match(circuit, /\$P_\{R_1\}\(\\text\{初\}\) = I_1\^2 R_1/);
assert.match(circuit, /\$I_1 = 0\.4 A\$/);
assert.match(circuit, /\$P_\{R_1\}\$\(末\)/);
assert.match(circuit, /\$R_1\$ 的功率/);
assert.equal(normalizePhysicsSubscripts(circuit), circuit);
assert.equal(normalizePhysicsSubscripts('$P_{R_1}$ $I_1^2 R_1$'), '$P_{R_1}$ $I_1^2 R_1$');
assert.match(normalizePhysicsSubscripts('$P_{R1}$'), /\$P_\{R_1\}\$/);
assert.equal(
  normalizePhysicsSubscripts('间隔增长率 R1＋R2＋R1×R2'),
  '间隔增长率 R1＋R2＋R1×R2',
);

assert.match(
  normalizePhysicsSubscripts('液体对容器底部的压强p_甲、p_乙及压力F_甲、F_乙'),
  /\$p_\{\\text\{甲\}\}\$.*\$F_\{\\text\{乙\}\}\$/,
);
assert.equal(
  collapseMaterialBlankLines('第一段。\n\n第二段。\n\n\n第三段。'),
  '第一段。\n第二段。\n第三段。',
);
const subParts = formatPlainSubscripts('压强p_甲 < p_乙');
assert.deepEqual(
  subParts.filter((part) => part.type === 'sub').map((part) => `${part.base}_${part.sub}`),
  ['p_甲', 'p_乙'],
);
console.log('review physics subscripts: ok');

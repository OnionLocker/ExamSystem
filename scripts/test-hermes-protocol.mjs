import assert from 'node:assert/strict';

import {
  appendAssistantDelta,
  coerceResumePayload,
  ensureStreamingAssistant,
  eventMatchesSession,
  extractReview,
  finishAssistantMessage,
  visibleAssistantReply,
  isSystemInjectedNotice,
  mergeResumedMessages,
  normalizeHermesHistory,
  parseBackgroundNotice,
  resumeMatchesSession,
  shouldAcceptRemoteResume,
} from '../src/hermes/hermesProtocol.js';
import { HIDDEN_SOURCES, sessionListReachable, sessionPickerMode } from '../src/hermes/hermesLayout.js';
import { audioLabelOf, isAudioLabel, parseAudioLen } from '../src/hermes/voiceLabel.js';

let id = 0;
const nextId = () => `m${++id}`;
const deps = {
  nextId,
  parseAudioLen: () => 0,
  isAudioLabel: () => false,
};

// 语音消息在对话里只留时长标签当正文，所以「产标签」和「认标签」必须互逆。
// 之前正文写成「请直接听录音」，isAudioLabel 认不出，气泡就退化成一行裸文字。
for (const sec of [1, 7, 12, 59, 60, 61, 90, 120, 125, 3599]) {
  const label = audioLabelOf(sec);
  assert.equal(isAudioLabel(label), true, `认不出 ${label}`);
  assert.equal(parseAudioLen(label), sec, `${label} 还原错了`);
}
assert.equal(audioLabelOf(0), '语音');
assert.equal(isAudioLabel('语音'), true);
assert.equal(isAudioLabel('请直接听录音'), false);
assert.equal(isAudioLabel('给我出10道题'), false);

// 只带语音发送时，水合出来必须是语音气泡，而不是把标签当正文显示
const voiceOnly = normalizeHermesHistory(
  [{ role: 'user', text: `[USER_MESSAGE]\n${audioLabelOf(12)}\n[/USER_MESSAGE]` }],
  { nextId, parseAudioLen, isAudioLabel },
);
assert.equal(voiceOnly[0].hadAudio, true);
assert.equal(voiceOnly[0].audioSec, 12);

const stamped = normalizeHermesHistory(
  [{ role: 'user', text: '[USER_MESSAGE]\n语音 3秒\n[/USER_MESSAGE]', timestamp: 1758031860 }],
  { nextId, parseAudioLen, isAudioLabel },
);
assert.equal(stamped[0].sentAt, 1758031860000);

assert.equal(isSystemInjectedNotice('[System: You edited code in this turn]'), true);
assert.equal(isSystemInjectedNotice('[CONTEXT COMPACTION — REFERENCE ONLY]'), true);
assert.equal(isSystemInjectedNotice(`\0json:[{"type":"text"}]`), true);
assert.equal(isSystemInjectedNotice('正常用户消息'), false);

// 后台脚本跑完，运行时把整段 stdout 当用户消息塞回来。它必须收成一张折叠卡片，
// 而不是在对话里铺一坨日志，也不能顶替「最后一条用户消息」。
const noticeText = '[IMPORTANT: Background process proc_b658b6818c25 exited (exit code 1).\n'
  + 'Command: python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module 数量关系 --count 10\n'
  + 'Output:\n{"status": "error", "batch_id": "20260914_x", "message": "generation gate failed"}]';
const notice = parseBackgroundNotice(noticeText);
assert.equal(notice.exitCode, 1);
assert.match(notice.command, /quiz_lite\.py/);
assert.match(notice.output, /generation gate failed/);
assert.equal(parseBackgroundNotice('正常用户消息'), null);
assert.equal(parseBackgroundNotice(''), null);

// 动词随退出方式变：成功是 completed normally，失败才是 exited。
// 第一版只认 exited，于是成功那条照样铺了一屏日志。
const okNotice = parseBackgroundNotice(
  '[IMPORTANT: Background process proc_48021296856f8 completed normally (exit code 0).\n'
  + 'Command: python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module 数量关系\n'
  + 'Output:\n{"status": "success", "batch_id": "20260914_hermes_zuizhi_02", "imported": 10, '
  + '"seconds": 181.01, "message": "已入库 10 题，批次 20260914_hermes_zuizhi_02，耗时 181 秒"}]',
);
assert.equal(okNotice.exitCode, 0);
assert.equal(okNotice.message, '已入库 10 题，批次 20260914_hermes_zuizhi_02，耗时 181 秒');
assert.equal(parseBackgroundNotice('[Background process proc_x was killed.]').exitCode, null);

const withNotice = normalizeHermesHistory([
  { role: 'user', text: '[USER_MESSAGE]\n来10道\n[/USER_MESSAGE]' },
  { role: 'assistant', text: '在出了' },
  { role: 'user', text: noticeText },
], deps);
assert.deepEqual(withNotice.map((m) => m.role), ['user', 'assistant', 'notice']);
assert.equal(withNotice[2].content, '');
assert.equal(withNotice[2].notice.exitCode, 1);

// 通知不能被当成待发送的用户消息重复上屏
const noticeInflight = mergeResumedMessages([], {
  messages: [{ role: 'user', text: '[USER_MESSAGE]\n来10道\n[/USER_MESSAGE]' }],
  inflight: { user: noticeText, assistant: '' },
  running: false,
}, deps);
assert.equal(noticeInflight.filter((m) => m.role === 'user').length, 1);
assert.equal(noticeInflight.some((m) => String(m.content).includes('Background process')), false);

const review = extractReview(
  '[USER_MESSAGE]\n复盘\n[/USER_MESSAGE]\n'
  + '/home/ubuntu/ExamSystem/data/practice-reviews/82-demo.md',
);
assert.equal(review.content, '');
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

const leakedAudit = [
  'The user wants me to do a review audit on:',
  '/home/ubuntu/ExamSystem/data/practice-reviews/313-demo.md',
  '',
  "Wait! First tool call MUST be reading the file!",
  'And the first line of the reply MUST be `### 01 · 题型名`!',
  '',
  "Let's carefully check the instructions:",
  '1. "第一件工具必须是打开上面这条路径"',
  '',
  'The user\'s voice message (39s):',
  '"感觉还是不会啊"',
].join('\n');
assert.equal(visibleAssistantReply(leakedAudit), '');
assert.equal(
  visibleAssistantReply(`${leakedAudit}\n\n### 01 · 古典概型\n\n> **原题**`),
  '### 01 · 古典概型\n\n> **原题**',
);
assert.equal(visibleAssistantReply('### 01 · 古典概型\n\n正文'), '### 01 · 古典概型\n\n正文');
assert.equal(visibleAssistantReply('立刻做 mid。'), '立刻做 mid。');

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

id = 0;
const oldAnswer = '### 01 · 数量关系\n\n> **原题** 某机关有66名新入职人员分配到甲、乙、丙、丁四个科室。';
const replayed = mergeResumedMessages(
  [
    { id: 'u1', role: 'user', content: '复盘', streaming: false, tools: [], thinking: '', images: [], review: null },
    { id: 'a1', role: 'assistant', content: oldAnswer, streaming: false, tools: [], thinking: '' },
  ],
  {
    messages: [
      { role: 'user', text: '复盘' },
      { role: 'assistant', text: oldAnswer },
    ],
    inflight: { assistant: oldAnswer },
    running: true,
  },
  deps,
);
assert.equal(replayed.filter((message) => message.role === 'assistant').length, 1);
assert.equal(replayed[replayed.length - 1].content, oldAnswer);

const alreadyDone = [
  { id: 'u1', role: 'user', content: '复盘', streaming: false, tools: [], thinking: '' },
  { id: 'a1', role: 'assistant', content: oldAnswer, streaming: false, tools: [], thinking: '' },
];
assert.equal(ensureStreamingAssistant(alreadyDone, nextId).filter((m) => m.role === 'assistant').length, 1);
assert.equal(appendAssistantDelta(alreadyDone, oldAnswer, nextId).filter((m) => m.role === 'assistant').length, 1);

const doubled = normalizeHermesHistory([
  { role: 'user', text: '复盘' },
  { role: 'assistant', text: oldAnswer },
  { role: 'assistant', text: oldAnswer },
], deps);
assert.equal(doubled.filter((message) => message.role === 'assistant').length, 1);
console.log('hermes duplicate assistant replay: ok');

id = 0;
const voiceLocal = [
  { id: 'u1', role: 'user', content: '复盘', streaming: false, tools: [], thinking: '', images: [], audio: null, audioSec: 0, hadAudio: false, review: null },
  { id: 'a1', role: 'assistant', content: oldAnswer, streaming: false, tools: [], thinking: '' },
  {
    id: 'v1', role: 'user', content: '', streaming: false, tools: [], thinking: '',
    images: [], audio: 'data:audio/webm;base64,xx', audioSec: 8, hadAudio: true, review: null,
  },
  {
    id: 's1', role: 'assistant', content: '', streaming: true,
    tools: [{ name: 'terminal', done: false }], thinking: '',
  },
];
const voiceResume = mergeResumedMessages(voiceLocal, {
  messages: [
    { role: 'user', text: '[USER_MESSAGE]\n复盘\n[/USER_MESSAGE]' },
    { role: 'assistant', text: oldAnswer },
    { role: 'user', text: `[USER_MESSAGE]\n${audioLabelOf(8)}\n[/USER_MESSAGE]` },
  ],
  inflight: { assistant: '' },
  running: true,
}, {
  nextId,
  parseAudioLen,
  isAudioLabel,
});
assert.equal(voiceResume.filter((message) => message.role === 'user' && message.hadAudio).length, 1);
assert.equal(voiceResume[voiceResume.length - 1].streaming, true);
assert.equal(voiceResume[voiceResume.length - 1].tools[0].name, 'terminal');
assert.equal(voiceResume.find((message) => message.hadAudio)?.audio, 'data:audio/webm;base64,xx');

const afterUser = [
  ...alreadyDone,
  { id: 'v2', role: 'user', content: audioLabelOf(8), streaming: false, tools: [], thinking: '', hadAudio: true, audioSec: 8 },
];
const started = ensureStreamingAssistant(afterUser, nextId);
assert.equal(started[started.length - 1].streaming, true);
assert.equal(started.filter((message) => message.role === 'assistant').length, 2);
console.log('hermes voice streaming resume: ok');

assert.equal(eventMatchesSession({ type: 'message.start', session_id: 'a' }, 'a', 'stored-a'), true);
assert.equal(eventMatchesSession({ type: 'message.start', session_id: 'b' }, 'a', 'stored-a'), false);
assert.equal(eventMatchesSession({ type: 'message.start', session_id: 'stored-a' }, 'a', 'stored-a'), true);
assert.equal(eventMatchesSession({ type: 'message.delta' }, 'a', 'stored-a'), true);
assert.equal(eventMatchesSession({ type: 'gateway.ready', session_id: 'b' }, 'a', 'stored-a'), true);
assert.equal(resumeMatchesSession({ session_id: 'live-b', session_key: 'stored-b' }, 'live-a', 'stored-a'), false);
assert.equal(resumeMatchesSession({ session_id: 'live-a', resumed: 'stored-a' }, 'live-a', 'stored-a'), true);
assert.equal(resumeMatchesSession({ messages: [] }, 'live-a', 'stored-a'), true);

console.log('hermes session-scoped events: ok');

id = 0;
const otherSessionVoice = [
  {
    id: 'foreign', role: 'assistant', content: 'previous session answer about naming batches that is long enough',
    streaming: false, tools: [], thinking: '',
  },
  {
    id: 'voice-a', role: 'user', content: audioLabelOf(106), streaming: false,
    tools: [], thinking: '', images: [], audio: 'data:audio/webm;base64,xx',
    audioSec: 106, hadAudio: true, review: null, storedSessionId: 'session-a', sentAt: 1,
  },
];
const sessionBResume = {
  session_id: 'live-b',
  stored_session_id: 'session-b',
  messages: [
    { role: 'user', text: 'how to name the batch' },
    { role: 'assistant', text: 'lock the question grain to one 考法; this reply is long enough for the merge path' },
  ],
  running: false,
};
const switched = mergeResumedMessages(otherSessionVoice, sessionBResume, {
  nextId, parseAudioLen, isAudioLabel, sameSession: false, storedId: 'session-b',
});
assert.equal(switched.some((message) => message.hadAudio || message.audio || message.audioSec === 106), false);

const stampedLeak = mergeResumedMessages(otherSessionVoice, sessionBResume, {
  nextId, parseAudioLen, isAudioLabel, storedId: 'session-b',
});
assert.equal(stampedLeak.some((message) => message.audio === 'data:audio/webm;base64,xx'), false);

const unstampedVoice = otherSessionVoice.map((message) => ({ ...message, storedSessionId: undefined }));
const droppedOnSwitch = mergeResumedMessages(unstampedVoice, sessionBResume, {
  nextId, parseAudioLen, isAudioLabel, sameSession: false, storedId: 'session-b',
});
assert.equal(droppedOnSwitch.some((message) => message.audioSec === 106), false);

const sameSessionPending = mergeResumedMessages(
  [{
    id: 'voice-b', role: 'user', content: audioLabelOf(8), streaming: false,
    tools: [], thinking: '', images: [], audio: 'data:audio/webm;base64,yy',
    audioSec: 8, hadAudio: true, review: null, storedSessionId: 'session-b',
  }],
  {
    session_id: 'live-b',
    stored_session_id: 'session-b',
    messages: [
      { role: 'user', text: 'hello' },
      { role: 'assistant', text: 'hi there from hermes' },
    ],
    running: false,
  },
  { nextId, parseAudioLen, isAudioLabel, storedId: 'session-b' },
);
assert.equal(sameSessionPending.some((message) => message.audioSec === 8 && message.audio === 'data:audio/webm;base64,yy'), true);
console.log('hermes cross-session voice isolation: ok');

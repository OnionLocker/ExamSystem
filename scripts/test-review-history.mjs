// 复盘结语对照用的历史：最近几场讲评存档里的结语和复盘后我说过的话。
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { recentReviewDigests } from '../server/hermesArchive.js';

const root = mkdtempSync(path.join(tmpdir(), 'review-history-'));
const dirs = { practice: path.join(root, 'practice'), exam: path.join(root, 'exam') };
dirs.upload = dirs.practice;
mkdirSync(dirs.practice);
mkdirSync(dirs.exam);

const archive = (dir, name, { title, type = 'AI 练题复盘', at, closing, followups = '' }) => writeFileSync(path.join(dir, name), [
  `# Hermes 复盘讲评：${title}`, '', `- 类型：${type}`, `- 复盘时间：${at}`, '- 系统报告：data/practice-reviews/1-x.md', '',
  '## 讲评', '', '### 01 · 某题', '', '#### 下次动作', '先写中项。', '',
  ...(closing ? ['### 本场结语', '', closing, ''] : []),
  ...(followups ? ['## 复盘后的追问', '', followups] : []),
].join('\n'));

try {
  archive(dirs.practice, '425-本场-20261014-1715.md', { title: '本场', at: '2026-10-14 17:15', closing: '本场自己的结语' });
  archive(dirs.practice, '424-重做-20261014-1400.md', {
    title: '计数模型重做', at: '2026-10-14 14:00',
    closing: '#### 以后怎么改\n1. 2 分钟止损。',
    followups: [
      '### 我：现在卡点还是在我的算数', '', '1. **先回答你的问题**：这是回复，不是我说的。', '',
      '### 我：语音 44秒（语音笔记）', '', '- 第 5 题没看懂。', '- 想把取模方法补进知识点。', '', '好的，我们逐个看。', '',
      '### 我：（附件或语音）', '', '收到。', '',
    ].join('\n'),
  });
  archive(dirs.practice, '423-没讲完-20261014-1200.md', { title: '没讲完', at: '2026-10-14 12:00' });
  archive(dirs.exam, '4-套题-20261013-0900.md', { title: '套题', type: '录屏复盘', at: '2026-10-13 09:00', closing: '旧结语\n\n### 本场结语\n\n后写的结语' });
  archive(dirs.practice, 'upload-粉笔卷-20261012-0800.md', { title: '粉笔卷', type: '粉笔 PDF 复盘', at: '2026-10-12 08:00', closing: 'x'.repeat(2000) });

  const got = recentReviewDigests({ kind: 'practice', id: 425, dirs });
  assert.deepEqual(got.map((r) => r.title), ['计数模型重做', '套题', '粉笔卷']);  // 跨目录按时间新的在前，跳过本场和没有结语的
  assert.equal(got[0].closing, '#### 以后怎么改\n1. 2 分钟止损。');
  assert.deepEqual(got[0].said, ['现在卡点还是在我的算数', '语音 44秒（语音笔记） - 第 5 题没看懂。 - 想把取模方法补进知识点。']);
  assert.equal(got[0].type, 'AI 练题复盘');
  assert.equal(got[0].at, '2026-10-14 14:00');
  assert.equal(got[1].closing, '后写的结语');  // 同一份讲评重写过结语时取最后一份
  assert.equal(got[2].closing.length, 1501);
  assert.ok(got[2].closing.endsWith('…'));

  assert.deepEqual(recentReviewDigests({ kind: 'practice', id: 999, dirs, limit: 1 }).map((r) => r.title), ['本场']);
  assert.deepEqual(recentReviewDigests({ kind: 'exam', id: 4, dirs }).map((r) => r.title), ['本场', '计数模型重做', '粉笔卷']);
  assert.deepEqual(recentReviewDigests({ kind: 'practice', id: 1, dirs: { practice: path.join(root, 'missing') } }), []);
} finally {
  rmSync(root, { recursive: true, force: true });
}

// 页面实际用的格式化与结语规则（从源码取出执行，防止改坏）
const chatSource = readFileSync(new URL('../src/hermes/HermesChat.jsx', import.meta.url), 'utf8');
const learningHistoryBlock = new Function(`return (${chatSource.match(/const learningHistoryBlock = ([\s\S]*?\n});/)[1]});`)();
assert.equal(learningHistoryBlock(null), '');
assert.equal(learningHistoryBlock({ focus: '', reviews: [] }), '');
const block = learningHistoryBlock({
  focus: '- 数量关系-数学运算-数列问题｜掌握：初步掌握',
  reviews: [{ at: '2026-10-14 14:00', type: 'AI 练题复盘', title: '计数模型重做', closing: '#### 以后怎么改\n1. 2 分钟止损。', said: ['现在卡点还是在我的算数'] }],
});
assert.match(block, /^\[LEARNING_HISTORY/);
assert.match(block, /\[\/LEARNING_HISTORY\]$/);
assert.match(block, /## 本场考点画像[^\n]*\n- 数量关系-数学运算-数列问题｜掌握：初步掌握/);
assert.match(block, /### 2026-10-14 14:00 · AI 练题复盘《计数模型重做》\n【以后怎么改】\n1\. 2 分钟止损。\n复盘后我说过：\n- 现在卡点还是在我的算数/);
assert.doesNotMatch(learningHistoryBlock({ focus: '- x', reviews: [] }), /最近几场复盘/);

const closingRule = new Function(`return (${chatSource.match(/const CLOSING_RULE = (\[[\s\S]*?\]\.join\('\\n'\));/)[1]});`)();
for (const part of ['### 本场结语', '#### 学情对照', '#### 主要问题', '#### 继续保持', '#### 下一步', '[LEARNING_HISTORY]', 'USER PROFILE', '白纸']) {
  assert.ok(closingRule.includes(part), part);
}
assert.ok(!closingRule.includes('#### 做得不好的'));
assert.equal(chatSource.match(/^\s+CLOSING_RULE,\n\s+STRICT_RULE,$/gm)?.length, 3);  // 练题、录屏、上传三种复盘共用

console.log('review history ok');

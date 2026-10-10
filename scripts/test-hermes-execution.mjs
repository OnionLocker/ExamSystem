import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm, symlink, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import express from 'express';
import { canDropVoiceContext, quizToolReceipt, quizExecutionStatus, verifyHermesExecution } from '../src/hermes/hermesExecution.js';
import { hermesRouter, readVoiceNoteStatus } from '../server/routes/hermesChat.js';

const args = { command: "python3 scripts/quiz_lite.py --batch-id 'test_batch' --count 10", background: true };
const receipt = quizToolReceipt({ name: 'terminal', args, result: { session_id: 'proc_test', pid: 123, exit_code: 0 } });
assert.equal(receipt.phase, 'started');
assert.equal(receipt.batchId, 'test_batch');
assert.equal(quizToolReceipt({ name: 'terminal', args: { command: 'cd /project && PYTHONUNBUFFERED=1 EXAM_DB=/project/data/exam.db /venv/bin/python scripts/ziliao_agent_paper.py --import' }, result: { session_id: 'p', pid: 1 } }).phase, 'started');
assert.equal(quizToolReceipt({ name: 'terminal', args, result: { output: 'I will generate questions.' } }).phase, 'unconfirmed');
assert.equal(quizToolReceipt({ name: 'terminal', args, result: { exit_code: 1, error: 'failed' } }).phase, 'failed');
assert.equal(quizToolReceipt({ name: 'terminal', args: { command: args.command + ' --plan-only' }, result: { session_id: 'p', pid: 1 } }), null);
assert.equal(quizToolReceipt({ name: 'terminal', args: { command: 'cat scripts/quiz_lite.py' }, result: {} }), null);
assert.equal(quizToolReceipt({ name: 'write_file', args, result: {} }), null);
assert.equal(quizExecutionStatus([], [], true).phase, 'unconfirmed');
assert.equal(quizExecutionStatus([], [], false), null);
assert.equal(quizExecutionStatus([receipt], [{ batch_id: 'another_batch', status: 'done' }], true).phase, 'running');
assert.match(quizExecutionStatus([receipt], [{ batch_id: 'test_batch', status: 'done', stage: '已入库', passed_count: 10 }]).text, /入库 10 题/);
assert.equal(quizExecutionStatus([receipt], [{ batch_id: 'test_batch', status: 'failed' }]).phase, 'failed');
assert.equal(quizExecutionStatus([receipt], [{ batch_id: 'test_batch', status: 'running', stale: true }]).phase, 'unconfirmed');
const inline = quizToolReceipt({ name: 'terminal', args, result: JSON.stringify({ exit_code: 0, output: 'log\n' + JSON.stringify({ status: 'success', batch_id: 'test_batch', imported: 10 }) }) });
assert.equal(inline.phase, 'done');

const pending = ['20261011-004718-voice.md', '20261011-010000-001-voice.md'];
const expected = { live: 'one', stored: 'saved-one', pending, turn: { userMessageId: 'first' } };
assert.equal(canDropVoiceContext(expected, { ...expected, sending: false }), true);
assert.equal(canDropVoiceContext(expected, { ...expected, sending: true }), false);
assert.equal(canDropVoiceContext(expected, { ...expected, live: 'two' }), false);
assert.equal(canDropVoiceContext(expected, { ...expected, stored: 'two' }), false);
assert.equal(canDropVoiceContext(expected, { ...expected, pending: [...pending] }), false);
assert.equal(canDropVoiceContext(expected, { ...expected, turn: { userMessageId: 'next-text-quiz' } }), false);
let result = await verifyHermesExecution({ noteNames: pending, receipts: [], wantsQuiz: true }, async () => [{ name: pending[0], saved: true }]);
assert.equal(result.allNotesSaved, false);
assert.match(result.voice, /保留/);
result = await verifyHermesExecution({ noteNames: pending, receipts: [], wantsQuiz: false }, async () => pending.map((name) => ({ name, saved: true, wantsQuiz: true })));
assert.equal(result.allNotesSaved, true);
assert.equal(result.quiz.phase, 'unconfirmed');
result = await verifyHermesExecution({ noteNames: pending, receipts: [receipt], wantsQuiz: true }, async () => { throw new Error('disconnected'); });
assert.equal(result.allNotesSaved, false);
assert.equal(result.quiz.phase, 'running');

const root = await mkdtemp(path.join(tmpdir(), 'voice-note-status-'));
const app = express();
app.use(express.json());
app.use('/api/hermes', hermesRouter);
const server = app.listen(0, '127.0.0.1');
await new Promise((resolve) => server.once('listening', resolve));
try {
  assert.equal((await readVoiceNoteStatus(pending[0], root)).saved, false);
  await writeFile(path.join(root, pending[0]), '## 我说了什么\n出10道题。\n## 语气与状态\n困惑\n## 你要做的事\n后台调用 quiz_lite.py 出10道题。\n## 值得长期记住的\n无\n');
  const saved = await readVoiceNoteStatus(pending[0], root);
  assert.equal(saved.saved, true);
  assert.equal(saved.wantsQuiz, true);
  await writeFile(path.join(root, pending[1]), 'I will write the note.');
  assert.equal((await readVoiceNoteStatus(pending[1], root)).saved, false);
  await rm(path.join(root, pending[1]));
  await symlink(path.join(root, pending[0]), path.join(root, pending[1]));
  assert.equal((await readVoiceNoteStatus(pending[1], root)).saved, false);
  await rm(path.join(root, pending[1]));
  await mkdir(path.join(root, pending[1]));
  assert.equal((await readVoiceNoteStatus(pending[1], root)).saved, false);
  await assert.rejects(readVoiceNoteStatus('../secret', root), /invalid/);
  for (const names of [['../secret'], ['bad.md'], [], 'bad', Array(101).fill(pending[0])]) {
    const res = await fetch(`http://127.0.0.1:${server.address().port}/api/hermes/voice-notes/status`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ names }),
    });
    assert.equal(res.status, 400);
  }
} finally {
  await new Promise((resolve) => server.close(resolve));
  await rm(root, { recursive: true, force: true });
}
console.log('Hermes execution receipts, voice artifacts and scoped cleanup: ok');

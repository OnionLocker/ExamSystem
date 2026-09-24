import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import express from 'express';

const temp = mkdtempSync(join(tmpdir(), 'learning-debt-'));
process.env.EXAM_DB = join(temp, 'exam.db');
const { default: db } = await import('../server/db.js');
const { default: router } = await import('../server/routes/kaodian.js');
const app = express();
app.use(express.json());
app.use('/api/kaodian', router);
const server = app.listen(0, '127.0.0.1');
await new Promise(resolve => server.once('listening', resolve));
const root = '数量关系-数学运算-概率问题';
const child = `${root}-古典概型`;
const other = `${root}-定位法与同组概率`;
const path = tag => `/learning/${encodeURIComponent(tag)}`;
const call = async (path, status, expected = 200) => {
  const response = await fetch(`http://127.0.0.1:${server.address().port}/api/kaodian${path}`, {
    method: status ? 'PUT' : 'GET',
    headers: { 'content-type': 'application/json' },
    ...(status ? { body: JSON.stringify({ status }) } : {}),
  });
  const data = await response.json();
  assert.equal(response.status, expected, JSON.stringify(data));
  return data;
};
const python = args => execFileSync('python3', ['scripts/kaodian_profile.py', ...args], { encoding: 'utf8' });
db.prepare("INSERT INTO questions(id,category,content,correct_answer) VALUES (99,'数量关系','test','A')").run();
const record = (tag, ok, id) => {
  db.prepare('INSERT OR IGNORE INTO practice_sessions(id) VALUES (?)').run(id);
  if (!db.prepare('SELECT 1 FROM practice_answers WHERE session_id=? AND question_id=99').get(id)) {
    db.prepare('INSERT INTO practice_answers(session_id,question_id,is_correct,time_spent_sec) VALUES (?,99,?,10)').run(id, Number(ok));
  }
  return python(['--record', tag, '数量关系', '数学运算', ok ? '1' : '0',
    '10000', 'practice', '--practice-id', String(id), '--item', '99']);
};
try {
  assert.equal((await call(path(root))).status, 'unstarted');
  record(child, false, 1);
  assert.equal((await call(path(child))).status, 'unconfirmed');
  assert.equal((await call('/debts')).summary.open, 0);
  await call(path(root), 'learning');
  record(child, false, 2);
  assert.equal((await call('/debts')).summary.open, 0);
  await call(path(root), 'learned');
  assert.notEqual((await call(path(child))).status, 'unconfirmed', '父级确认已学后，下级继承状态');
  const baseline = db.prepare('SELECT baseline_event_id FROM kaodian_learning WHERE kaodian=?').get(root);
  record(child, false, 3);
  let rows = (await call('/debts')).debts;
  assert.equal(rows.find(d => d.kaodian === child).wrongCount, 1);
  record(other, true, 4);
  record(other, true, 5);
  assert.equal((await call(path(child))).status, 'debt', '兄弟考法不能替当前考法清债');
  record(child, true, 6);
  record(child, true, 6); // Same question/session is idempotent.
  assert.equal((await call(path(child))).status, 'debt');
  record(child, true, 7);
  assert.equal((await call(path(child))).status, 'cleared');
  python(['--undo-practice', '7']);
  assert.equal((await call(path(child))).status, 'debt');
  await call(path(root), 'learned');
  assert.deepEqual(db.prepare('SELECT baseline_event_id FROM kaodian_learning WHERE kaodian=?').get(root), baseline);
  assert.equal((await call(path(child), 'learned')).status, 'debt', '重复确认不得清除新债');
  await call(path(root), 'learning', 409);
  await call(path(`${root}-@equal-groups`), 'learned', 400);
  await call(path('不存在的标签'), 'learned', 404);
  python(['--undo-practice', '3']);
  rows = (await call('/debts')).debts;
  assert.equal(rows.find(d => d.kaodian === child).wrongCount, 0, '撤销新错题后不能把旧错题回灌');
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM kaodian_events WHERE session_id IN (1,2)').get().n, 2);
  console.log('Learning gate, per-method debt, baseline, replay, undo, API validation: passed.');
} finally {
  await new Promise(resolve => server.close(resolve));
  db.close();
  rmSync(temp, { recursive: true, force: true });
}

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

import express from 'express';

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'practice-evolution-'));
process.env.EXAM_DB = path.join(temp, 'exam.db');
process.env.EXAM_DRAFT_DIR = path.join(temp, 'drafts');

const { default: db } = await import('../server/db.js');
const { default: practiceRouter } = await import('../server/routes/practice.js');

const alias = '数量关系-数学运算-排列组合';
const canonical = '数量关系-逢考必有的排列组合与概率-基础原理与几何概型';
const question = db.prepare('SELECT id FROM questions ORDER BY id LIMIT 1').get();
db.prepare(
  `UPDATE questions
      SET correct_answer='A', category='数量关系', sub_category='数学运算',
          tags=?, question_type='single'
    WHERE id=?`,
).run(JSON.stringify([alias, '插空法']), question.id);
db.prepare(
  `INSERT INTO kaodian_aliases(alias,canonical,module,subtype)
   VALUES (?,?, '数量关系','逢考必有的排列组合与概率')`,
).run(alias, canonical);

const app = express();
app.use(express.json({ limit: '2mb' }));
app.use('/api/practice', practiceRouter);
const server = app.listen(0, '127.0.0.1');
await new Promise((resolve) => server.once('listening', resolve));
const { port } = server.address();
const call = async (pathname, body) => {
  const response = await fetch(`http://127.0.0.1:${port}${pathname}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  assert.ok(response.ok, JSON.stringify(data));
  return data;
};

const sessions = [];
const submit = async (index, userAnswer) => {
  const session = await call('/api/practice/sessions', { category: `test-${index}` });
  sessions.push(session);
  return call(`/api/practice/sessions/${session.id}/submit`, {
    duration_sec: 10,
    answers: [{
      question_id: question.id,
      user_answer: userAnswer,
      time_spent_sec: 10,
    }],
  });
};

await submit(1, 'B');
await submit(2, 'A');
await submit(3, 'A');

assert.equal(db.prepare('SELECT COUNT(*) AS n FROM kaodian_events').get().n, 0);
assert.equal(db.prepare('SELECT kaodian FROM kaodian_profile WHERE kaodian=?').get(canonical), undefined);
assert.equal(db.prepare('SELECT kaodian FROM kaodian_debts WHERE kaodian=?').get(canonical), undefined);

const record = (sessionId, ok) => {
  const result = spawnSync('python3', [
    'scripts/kaodian_profile.py',
    '--record', alias, '数量关系', '逢考必有的排列组合与概率', ok, '10000', 'hermes',
    '--practice-id', String(sessionId),
    '--item', String(question.id),
  ], { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
  assert.equal(result.status, 0, (result.stderr || '') + (result.stdout || ''));
};
record(sessions[0].id, '0');
record(sessions[1].id, '1');
record(sessions[2].id, '1');

const debt = db.prepare(
  'SELECT wrong_count,recovery_streak,mastered FROM kaodian_debts WHERE kaodian=?',
).get(canonical);
assert.deepEqual(debt, { wrong_count: 1, recovery_streak: 2, mastered: 1 });
assert.equal(
  db.prepare('SELECT COUNT(*) AS n FROM kaodian_events WHERE kaodian=?').get(canonical).n,
  3,
);
assert.equal(
  db.prepare("SELECT COUNT(*) AS n FROM kaodian_events WHERE kaodian='插空法'").get().n,
  0,
);
assert.equal(
  db.prepare('SELECT attempts FROM kaodian_profile WHERE kaodian=?').get(canonical).attempts,
  3,
);

const sealed = spawnSync('python3', [
  'scripts/kaodian_profile.py', '--seal-practice', String(sessions[0].id),
], { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
assert.equal(sealed.status, 0, (sealed.stderr || '') + (sealed.stdout || ''));
const blocked = spawnSync('python3', [
  'scripts/kaodian_profile.py',
  '--record', alias, '数量关系', '逢考必有的排列组合与概率', '0', '10000', 'hermes',
  '--practice-id', String(sessions[0].id),
  '--item', String(question.id),
], { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
assert.equal(blocked.status, 0, (blocked.stderr || '') + (blocked.stdout || ''));
assert.match(blocked.stdout, /already sealed/);
assert.equal(
  db.prepare('SELECT COUNT(*) AS n FROM kaodian_events WHERE kaodian=?').get(canonical).n,
  3,
);
assert.equal(db.pragma('integrity_check', { simple: true }), 'ok');

const png = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);
const draftSession = await call('/api/practice/sessions', { category: 'draft-binary' });
const putBinary = await fetch(
  `http://127.0.0.1:${port}/api/practice/sessions/${draftSession.id}/drafts/${question.id}`,
  { method: 'PUT', headers: { 'content-type': 'image/png' }, body: png },
);
const putBinaryBody = await putBinary.json();
assert.ok(putBinary.ok, JSON.stringify(putBinaryBody));
assert.equal(putBinaryBody.ok, true);
assert.ok(putBinaryBody.bytes > 0);

const putJson = await fetch(
  `http://127.0.0.1:${port}/api/practice/sessions/${draftSession.id}/drafts/${question.id}`,
  {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ data: `data:image/png;base64,${png.toString('base64')}`, mime: 'image/png' }),
  },
);
const putJsonBody = await putJson.json();
assert.ok(putJson.ok, JSON.stringify(putJsonBody));

await new Promise((resolve) => server.close(resolve));
db.close();
fs.rmSync(temp, { recursive: true, force: true });
console.log('practice evolution write path: ok');

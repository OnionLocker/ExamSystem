import assert from 'node:assert/strict';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import express from 'express';

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'quiz-lite-api-'));
process.env.EXAM_DB = path.join(root, 'exam.db');
process.env.EXAM_DRAFT_DIR = path.join(root, 'drafts');
process.env.EXAM_PRACTICE_REVIEW_DIR = path.join(root, 'reviews');
const { default: db } = await import('../server/db.js');
const original = childProcess.execFile;
let generated = 0;
let lastArgs;
childProcess.execFile = (file, args, options, callback) => {
  assert.equal(file, 'python3');
  assert.equal(path.basename(args[0]), 'quiz_lite.py');
  const value = flag => args[args.indexOf(flag) + 1];
  assert.equal(args.includes('--output'), false);
  assert.equal(value('--db'), process.env.EXAM_DB);
  assert.equal(value('--difficulty'), 'mid');
  assert.equal(value('--count'), '2');
  assert.ok(options.timeout > 60000);
  generated += 1;
  lastArgs = args;
  setImmediate(() => {
    const batch = value('--batch-id');
    for (let i = 0; i < 2; i += 1) {
      db.prepare(`INSERT INTO questions (external_id,batch_id,category,content,correct_answer)
                  VALUES (?,?,'数量关系','mock question','A')`).run(`${batch}_${i}`, batch);
    }
    callback(null, '{}', '');
  });
};
syncBuiltinESMExports();
const { default: router } = await import('../server/routes/practice.js');
const app = express();
app.use(express.json());
app.use('/api/practice', router);
const server = app.listen(0, '127.0.0.1');
await new Promise(resolve => server.once('listening', resolve));
try {
  const url = `http://127.0.0.1:${server.address().port}/api/practice/quiz/lite`;
  const post = body => fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const base = { module: '数量关系', tag: '数量关系-数学运算-最值问题', count: 2 };
  for (const invalid of [{ count: 20 }, { count: 2.5 }, { difficulty: 'unknown' }, { tag: [] }]) {
    assert.equal((await post({ ...base, ...invalid })).status, 400);
  }
  assert.equal(generated, 0);
  const response = await post(base);
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.count, 2);
  assert.equal(generated, 1);
  const session = db.prepare('SELECT * FROM practice_sessions WHERE id=?').get(result.sessionId);
  assert.equal(session.category, result.category);
  assert.equal(session.assessment_baseline, '{}');
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM questions WHERE batch_id=?').get(result.category).n, 2);
  for (const invalid of [{ question_type: 'multi' }, { sources: ['bad/source'] }, { as_of: '2026-02-31' }]) {
    assert.equal((await post({ ...base, ...invalid })).status, 400);
  }
  const political = await post({ module: '政治理论', count: 2, question_type: 'multi',
    sources: ['gd-science-literacy-2026'], as_of: '2026-09-24' });
  assert.equal(political.status, 200);
  assert.equal(lastArgs.includes('--tag'), false);
  assert.equal(lastArgs[lastArgs.indexOf('--sources') + 1], 'gd-science-literacy-2026');
  assert.equal(lastArgs[lastArgs.indexOf('--question-type') + 1], 'multi');
  assert.equal(generated, 2);
  console.log('quiz lite API: ok');
} finally {
  await new Promise(resolve => server.close(resolve));
  childProcess.execFile = original;
  syncBuiltinESMExports();
  db.close();
  fs.rmSync(root, { recursive: true, force: true });
}

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import express from 'express';
import { normalizeAnswer, judgeOptions } from '../src/answers.js';

assert.equal(normalizeAnswer('T', 'judge'), 'A');
assert.equal(normalizeAnswer('错', 'judge'), 'B');
assert.equal(normalizeAnswer('DCA', 'multi'), 'ACD');
assert.deepEqual(judgeOptions([{ key: 'T', text: '正确' }, { key: 'F', text: '错误' }]).map(x => x.key), ['A', 'B']);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'answer-types-'));
process.env.EXAM_DB = path.join(tmp, 'exam.db');
process.env.EXAM_DRAFT_DIR = path.join(tmp, 'drafts');
process.env.EXAM_PRACTICE_REVIEW_DIR = path.join(tmp, 'reviews');
const { default: db } = await import('../server/db.js');
const { default: router } = await import('../server/routes/practice.js');
const { default: questions } = await import('../server/routes/questions.js');
const app = express(); app.use(express.json()); app.use('/practice', router); app.use('/questions', questions);
const server = app.listen(0, '127.0.0.1');
await new Promise(resolve => server.once('listening', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
try {
  const post = async (url, body) => {
    const response = await fetch(base + url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    assert.ok(response.ok); return response.json();
  };
  const insert = db.prepare("INSERT INTO questions(external_id,batch_id,category,question_type,content,correct_answer,tags) VALUES (?,'answer-test','政治理论',?,'测试题面',?,'[]')");
  const ids = [insert.run('judge-legacy', 'judge', 'T').lastInsertRowid, insert.run('multi-legacy', 'multi', 'DCA').lastInsertRowid];
  const listed = await (await fetch(base + '/questions?batch_id=answer-test')).json();
  assert.deepEqual(listed.items.map(q => q.correct_answer), ['A', 'ACD']);
  const session = await post('/practice/sessions', { category: 'answer-test' });
  const result = await post(`/practice/sessions/${session.id}/submit`, { duration_sec: 30,
    answers: ids.map((id, i) => ({ question_id: Number(id), user_answer: i ? 'CDA' : 'A', time_spent_sec: 15 })) });
  assert.equal(result.correct, 2);
  const session2 = await post('/practice/sessions', { category: 'answer-test' });
  const wrong = await post(`/practice/sessions/${session2.id}/submit`, { duration_sec: 30,
    answers: [{ question_id: Number(ids[1]), user_answer: 'AC', time_spent_sec: 30 }] });
  assert.equal(wrong.correct, 0);
  console.log('judge/multi API grading: ok');
} finally {
  await new Promise(resolve => server.close(resolve));
  db.close();
  // Background blank recording may still finish; this temporary directory has no learner data.
}

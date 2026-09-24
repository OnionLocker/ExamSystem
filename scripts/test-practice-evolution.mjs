import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

import express from 'express';

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'practice-evolution-'));
process.env.EXAM_DB = path.join(temp, 'exam.db');
process.env.EXAM_DRAFT_DIR = path.join(temp, 'drafts');
process.env.EXAM_PRACTICE_REVIEW_DIR = path.join(temp, 'reviews');

const { default: db } = await import('../server/db.js');
const { default: practiceRouter } = await import('../server/routes/practice.js');
const { default: kaodianRouter } = await import('../server/routes/kaodian.js');

const alias = '数量关系-数学运算-排列组合';
const canonical = '数量关系-数学运算-排列组合问题';
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
app.use('/api/kaodian', kaodianRouter);
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

const prematureAudit = await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${sessions[0].id}/audit`, { method: 'POST' });
assert.equal(prematureAudit.status, 409);

assert.equal(db.prepare("SELECT COUNT(*) AS n FROM kaodian_events WHERE evidence_type='practice'").get().n, 0);
assert.equal(db.prepare('SELECT attempts FROM kaodian_profile WHERE kaodian=?').get(canonical), undefined);
assert.equal(db.prepare('SELECT kaodian FROM kaodian_debts WHERE kaodian=?').get(canonical), undefined);

const record = (sessionId, ok) => {
  const result = spawnSync('python3', [
    'scripts/kaodian_profile.py',
    '--record', alias, '数量关系', '逢考必有的排列组合与概率', ok, '10000', 'practice',
    '--practice-id', String(sessionId),
    '--item', String(question.id),
  ], { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
  assert.equal(result.status, 0, (result.stderr || '') + (result.stdout || ''));
};
const incomplete = await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${sessions[0].id}/review-complete`, { method: 'POST' });
assert.equal(incomplete.status, 409);
record(sessions[0].id, '0');
record(sessions[1].id, '1');
record(sessions[2].id, '1');
assert.equal(
  db.prepare("SELECT COUNT(*) AS n FROM kaodian_events WHERE evidence_type='practice'").get().n,
  3,
);
assert.equal(
  db.prepare("SELECT COUNT(*) AS n FROM kaodian_events WHERE kaodian='插空法'").get().n,
  0,
);
assert.equal(db.prepare('SELECT COUNT(*) AS n FROM kaodian_profile WHERE attempts > 0').get().n, 1);

const sealed = spawnSync('python3', [
  'scripts/kaodian_profile.py', '--seal-practice', String(sessions[0].id),
], { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
assert.equal(sealed.status, 0, (sealed.stderr || '') + (sealed.stdout || ''));
const blocked = spawnSync('python3', [
  'scripts/kaodian_profile.py',
  '--record', alias, '数量关系', '逢考必有的排列组合与概率', '0', '10000', 'practice',
  '--practice-id', String(sessions[0].id),
  '--item', String(question.id),
], { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
assert.equal(blocked.status, 0, (blocked.stderr || '') + (blocked.stdout || ''));
assert.match(blocked.stdout, /already sealed/);
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM kaodian_events WHERE evidence_type='practice'").get().n, 3);

const review = {
  independence: 'independent', process: 'correct', basis: 'draft', execution: 'hesitant',
  reason: 'The draft establishes the right model but has an arithmetic slip.',
  template: 'first-model', timing_valid: true, target_seconds: 60, target_basis: 'Test exam budget',
};
for (let i = 0; i < 2; i += 1) {
  const assessed = spawnSync('python3', ['scripts/kaodian_profile.py', '--assess', 'practice',
    String(sessions[0].id), String(question.id), JSON.stringify(review)],
  { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
  assert.equal(assessed.status, 0, assessed.stderr);
  assert.equal(JSON.parse(assessed.stdout).updated, i === 0);
}
assert.equal(db.prepare('SELECT COUNT(*) AS n FROM kaodian_assessment_history').get().n, 1);
const profileResponse = await fetch(`http://127.0.0.1:${port}/api/kaodian`);
assert.equal(profileResponse.status, 200);
const returnedProfiles = (await profileResponse.json()).items;
const profile = returnedProfiles.find(row => row.kaodian === canonical);
assert.ok(profile, JSON.stringify(returnedProfiles));
assert.equal(profile.assessment.level, 'initial');
assert.equal(profile.assessment.independent_samples, 1);
assert.equal(profile.assessment.repeats_excluded, 2);
assert.equal(profile.assessment.evidence[0].correct, false);
assert.equal(profile.assessment.fluency, 'unassessed');
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM kaodian_events WHERE evidence_type='practice'").get().n, 3);

const auditResponse = await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${sessions[0].id}/audit`, { method: 'POST' });
const audit = await auditResponse.json();
assert.equal(auditResponse.status, 201);
assert.equal(JSON.parse(db.prepare('SELECT assessment_baseline FROM practice_sessions WHERE id=?').get(audit.id).assessment_baseline)[canonical], 'initial');
assert.equal(db.prepare('SELECT audit_of_session_id FROM practice_sessions WHERE id=?').get(audit.id).audit_of_session_id, sessions[0].id);
const auditSubmit = await call(`/api/practice/sessions/${audit.id}/submit`, {
  duration_sec: 12,
  answers: [{ question_id: question.id, user_answer: 'A', time_spent_sec: 12 }],
});
assert.equal(auditSubmit.total, 1);
assert.equal(db.prepare('SELECT profile_reviewed_at FROM practice_sessions WHERE id=?').get(sessions[0].id).profile_reviewed_at !== null, true);

const complete = await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${sessions[0].id}/review-complete`, { method: 'POST' });
assert.equal(complete.status, 200);
assert.equal(db.prepare('SELECT profile_reviewed_at IS NOT NULL AS reviewed FROM practice_sessions WHERE id=?').get(sessions[0].id).reviewed, 1);
assert.equal(db.pragma('integrity_check', { simple: true }), 'ok');

// ── 空题：交卷即写证据，不等模型自觉 ──
const [longBlank, shortBlank] = db.prepare(
  'SELECT id FROM questions WHERE id != ? ORDER BY id LIMIT 2',
).all(question.id);
for (const row of [longBlank, shortBlank]) {
  db.prepare(
    `UPDATE questions
        SET correct_answer='C', category='数量关系', sub_category='数学运算',
            tags=?, question_type='single'
      WHERE id=?`,
  ).run(JSON.stringify([alias]), row.id);
}

const blankSession = await call('/api/practice/sessions', { category: 'blank-evidence' });
await call(`/api/practice/sessions/${blankSession.id}/submit`, {
  duration_sec: 200,
  answers: [
    { question_id: longBlank.id, user_answer: '', time_spent_sec: 120 },
    { question_id: shortBlank.id, user_answer: '', time_spent_sec: 3 },
    { question_id: question.id, user_answer: 'B', time_spent_sec: 30 },
  ],
});

// 证据由子进程异步写入，轮询等它落库
const blankEvents = () => db.prepare(
  'SELECT question_id, is_correct, evidence_weight FROM kaodian_events WHERE session_id=?',
).all(blankSession.id);
for (let wait = 0; wait < 100 && blankEvents().length === 0; wait += 1) {
  await new Promise((resolve) => setTimeout(resolve, 100));
}
const written = blankEvents();
assert.equal(written.length, 1, '只有盯久了的那道空题算证据');
assert.equal(written[0].question_id, longBlank.id);
assert.equal(written[0].is_correct, 0, '空题记为不会');
assert.equal(written[0].evidence_weight, 1, '停留 120 秒是满权重证据');
assert.equal(db.prepare('SELECT COUNT(*) AS n FROM mistakes WHERE question_id=?').get(longBlank.id).n, 1);
assert.equal(db.prepare('SELECT COUNT(*) AS n FROM mistakes WHERE question_id=?').get(shortBlank.id).n, 0);

const coverage = async () => {
  const response = await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${blankSession.id}/coverage`);
  assert.equal(response.status, 200);
  return response.json();
};
assert.deepEqual(await coverage(), {total: 2, covered: 1, missing: 1, percentage: 50});
// 录屏和练习的编号会重叠，录屏证据既不能抵扣漏记，也不能挡住后续练习写入。
db.prepare(`INSERT INTO kaodian_events(kaodian,session_id,question_id,is_correct,evidence_type)
  VALUES (?,?,?,1,'exam')`).run(canonical, blankSession.id, question.id);
assert.deepEqual(await coverage(), {total: 2, covered: 1, missing: 1, percentage: 50});
const incompleteBlank = await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${blankSession.id}/review-complete`, {method:'POST'});
assert.equal(incompleteBlank.status, 409);

// 有作答的那道还没写证据，封存必须被拒绝
const seal = () => spawnSync('python3', [
  'scripts/kaodian_profile.py', '--seal-practice', String(blankSession.id),
], { cwd: path.resolve('scripts/..'), env: process.env, encoding: 'utf8' });
const refused = seal();
assert.equal(refused.status, 0, (refused.stderr || '') + (refused.stdout || ''));
assert.match(refused.stdout, /refused/);
assert.match(refused.stdout, new RegExp(String(question.id)));
assert.doesNotMatch(refused.stdout, new RegExp(String(shortBlank.id)), '秒过的空题不该算进分母');
assert.equal(
  db.prepare('SELECT profile_reviewed_at FROM practice_sessions WHERE id=?').get(blankSession.id).profile_reviewed_at,
  null,
);

// 补上那道，封存就该通过——秒过的空题不会把这一场永远卡住
record(blankSession.id, '0');
assert.deepEqual(await coverage(), {total: 2, covered: 2, missing: 0, percentage: 100});
const accepted = seal();
assert.equal(accepted.status, 0, (accepted.stderr || '') + (accepted.stdout || ''));
assert.match(accepted.stdout, /^sealed/);
assert.notEqual(
  db.prepare('SELECT profile_reviewed_at FROM practice_sessions WHERE id=?').get(blankSession.id).profile_reviewed_at,
  null,
);
// 在临时库里重新打开此场，验证 API 封存与 Python 封存使用同一分母。
db.prepare('UPDATE practice_sessions SET profile_reviewed_at=NULL WHERE id=?').run(blankSession.id);
const sealedBlank = await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${blankSession.id}/review-complete`, {method:'POST'});
assert.equal(sealedBlank.status, 200);
assert.equal((await sealedBlank.json()).sealed, true);

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

// Picker query must retain category filters, counts and the most recent limit.
const list = await (await fetch(`http://127.0.0.1:${port}/api/practice/sessions?limit=2`)).json();
assert.equal(list.length, 2);
assert.ok(list.every((row) => row.ended_at && row.total > 0));
const filtered = await (await fetch(`http://127.0.0.1:${port}/api/practice/sessions?category=test-1&limit=100`)).json();
assert.ok(filtered.length > 0);
assert.ok(filtered.every((row) => row.category === 'test-1'));
assert.equal(filtered.find((row) => row.id === sessions[0].id).wrong_count, 1);
const report = await (await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${sessions[0].id}/report`)).json();
const combined = await (await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${sessions[0].id}/md?include=report`)).json();
assert.deepEqual(combined.report, report);
assert.equal(fs.readFileSync(combined.path, 'utf8'), combined.markdown);
const original = await (await fetch(`http://127.0.0.1:${port}/api/practice/sessions/${sessions[0].id}/md`)).json();
assert.equal(original.report, undefined);
assert.equal(original.markdown, combined.markdown);

await new Promise((resolve) => server.close(resolve));
db.close();
fs.rmSync(temp, { recursive: true, force: true });
console.log('practice evolution write path: ok');

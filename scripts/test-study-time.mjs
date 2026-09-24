import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import express from 'express';
import { aggregateStudyTime, closeTimerSegments, segmentMinutes, studyOutputs, timeLevel, validSegments } from '../src/studyLog/studyTime.js';
import { aggregateByDay, mergeServerHeat } from '../src/studyLog/studyLog.js';

const start = Date.parse('2026-01-01T02:00:00Z');
const minute = 60000;
const timed = (id, from, to, extra = {}) => ({ id, type: 'mock', ts: to, timeSegments: [[from, to]], ...extra });
const first = timed('a', start, start + 60 * minute);
const overlap = timed('b', start + 30 * minute, start + 90 * minute, { type: 'pomodoro' });
assert.equal(aggregateStudyTime([first, overlap]).get('2026-01-01').minutes, 90);
assert.equal(aggregateStudyTime([first, first]).get('2026-01-01').minutes, 60);
const paused = closeTimerSegments({ timeSegments: [[start, start + 10 * minute]], runStartedAt: start + 40 * minute }, start + 50 * minute);
assert.equal(segmentMinutes(paused), 20, 'pause gaps must not count');
const midnight = Date.parse('2026-01-01T16:00:00Z');
const cross = timed('cross', midnight - 10 * minute, midnight + 20 * minute, { type: 'aiquiz', count: 5 });
const split = aggregateByDay([cross]);
assert.equal(split.get('2026-01-01').minutes, 10);
assert.equal(split.get('2026-01-02').minutes, 20);
assert.equal(studyOutputs(split.get('2026-01-01').entries).answered, 0);
const merged = mergeServerHeat(split, { '2026-01-02': { entries: [cross] } });
assert.equal(merged.get('2026-01-02').minutes, 20, 'merging must not double-count cross-day sources');
assert.equal(studyOutputs(merged.get('2026-01-02').entries).answered, 5);
const legacy = aggregateStudyTime([
  { id: 'chat', type: 'chat', ts: start, minutes: 180, score: 50 },
  { id: 'video', type: 'examReview', ts: start, videoMinutes: 90 },
  { id: 'preview', type: 'import', ts: start, score: 500, preview: true },
]).get('2026-01-01');
assert.equal(legacy.minutes, 0);
assert.equal(legacy.unknownCount, 2);
const source = { '2026-01-01': { entries: [timed('ai', start, start + 30 * minute, { type: 'aiquiz', count: 10, firstCount: 7, repeatCount: 3 })] } };
assert.equal(mergeServerHeat(new Map(), source).get('2026-01-01').minutes, 30);
assert.deepEqual(studyOutputs(mergeServerHeat(new Map(), source).get('2026-01-01').entries),
  { answered: 10, reviewed: 0, writing: 0, first: 7, repeat: 3 });
assert.equal(timeLevel(239), 5);
assert.equal(timeLevel(240), 6);
assert.equal(timeLevel(480), 8);
assert.equal(timeLevel(0), 0);
assert.equal(studyOutputs([{ type: 'numeric', count: 10, skipped: 3 }]).answered, 7);
assert.equal(validSegments([[start, start - 1]]), false);
assert.equal(validSegments([[start, Infinity]]), false);
assert.equal(validSegments([[Date.now(), Date.now() + 120000]]), false);

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'study-time-'));
process.env.EXAM_DB = path.join(temp, 'exam.db');
process.env.EXAM_DRAFT_DIR = path.join(temp, 'drafts');
process.env.EXAM_PRACTICE_REVIEW_DIR = path.join(temp, 'reviews');
const { default: db } = await import('../server/db.js');
const { default: router } = await import('../server/routes/practice.js');
const app = express();
app.use(express.json());
app.use('/api/practice', router);
const server = app.listen(0, '127.0.0.1');
await new Promise(resolve => server.once('listening', resolve));
const base = `http://127.0.0.1:${server.address().port}/api/practice`;
try {
  const question = db.prepare('SELECT id FROM questions LIMIT 1').get().id;
  const insert = db.prepare("INSERT INTO practice_sessions(category,total,correct,duration_sec,started_at,ended_at,timing_segments) VALUES ('same',1,1,600,'2026-01-01 02:00:00',?,?)");
  const a = insert.run('2026-01-01 02:10:00', JSON.stringify([[start, start + 10 * minute]])).lastInsertRowid;
  const b = insert.run('2026-01-01 02:30:00', JSON.stringify([[start + 20 * minute, start + 30 * minute]])).lastInsertRowid;
  for (const id of [a, b]) db.prepare("INSERT INTO practice_answers(session_id,question_id,user_answer,is_correct,time_spent_sec) VALUES (?,?,'A',1,600)").run(id, question);
  const heat = await fetch(`${base}/heat`).then(r => r.json());
  assert.equal(heat['2026-01-01'].entries.length, 2, 'same-batch repeats still represent study time');
  const actual = mergeServerHeat(new Map(), heat).get('2026-01-01');
  assert.equal(actual.minutes, 20);
  assert.equal(studyOutputs(actual.entries).first, 1);
  assert.equal(studyOutputs(actual.entries).repeat, 1);
  db.prepare("UPDATE practice_sessions SET profile_reviewed_at='2026-01-02 02:00:00' WHERE id=?").run(a);
  db.prepare("INSERT INTO exam_analyses(title,status,exam_date,duration_sec) VALUES ('recording','done','2026-01-02',5400)").run();
  const reviewedHeat = await fetch(`${base}/heat`).then(r => r.json());
  const reviewed = mergeServerHeat(new Map(), reviewedHeat).get('2026-01-02');
  assert.equal(reviewed.minutes, 0, 'recording length and sealed review are not measured study time');
  assert.equal(reviewed.unknownCount, 2);
  assert.equal(studyOutputs(reviewed.entries).reviewed, 1);
  const session = db.prepare("INSERT INTO practice_sessions(category) VALUES ('submit')").run().lastInsertRowid;
  const invalid = await fetch(`${base}/sessions/${session}/submit`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ answers: [{ question_id: question, user_answer: 'A' }], timeSegments: [[1, 2]] }) });
  assert.equal(invalid.status, 400);
  assert.equal(db.prepare('SELECT ended_at FROM practice_sessions WHERE id=?').get(session).ended_at, null);
  db.prepare("UPDATE practice_sessions SET started_at='2026-01-01 02:00:00' WHERE id=?").run(session);
  const timeSegments = [[start, start + minute], [start + minute / 2, start + 2 * minute]];
  const submitted = await fetch(`${base}/sessions/${session}/submit`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ answers: [{ question_id: question, user_answer: 'A' }], duration_sec: 120, timeSegments }) });
  assert.equal(submitted.status, 200);
  assert.deepEqual(JSON.parse(db.prepare('SELECT timing_segments FROM practice_sessions WHERE id=?').get(session).timing_segments), [[start, start + 2 * minute]]);
  const retry = await fetch(`${base}/sessions/${session}/submit`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ answers: [{ question_id: question, user_answer: 'A' }], timeSegments }) });
  assert.equal(retry.status, 409, 'resubmitting cannot duplicate a session');
} finally {
  await new Promise(resolve => server.close(resolve));
  // The submit route dispatches evidence recording to a short-lived Python process.
  await new Promise(resolve => setTimeout(resolve, 1500));
  db.close();
  fs.rmSync(temp, { recursive: true, force: true });
}
console.log('study time: overlap, pause, midnight, legacy, repeats and validation ok');

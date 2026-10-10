import assert from 'node:assert/strict';
import express from 'express';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const root = await mkdtemp(path.join(tmpdir(), 'generation-queue-'));
process.env.EXAM_DB = path.join(root, 'exam.db');
const { default: db } = await import('../server/db.js');
const { default: router } = await import('../server/routes/questions.js');
db.prepare("INSERT INTO generation_jobs (batch_id, status, stage, finished_at) VALUES (?, 'done', '已入库', datetime('now', '-1 day'))").run('old_batch');
db.prepare("INSERT INTO generation_jobs (batch_id, status) VALUES (?, 'running')").run('running_batch');
const app = express();
app.use(router);
const server = app.listen(0, '127.0.0.1');
await new Promise((resolve) => server.once('listening', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
try {
  const get = async (query) => (await fetch(base + '/generation-queue' + query)).json();
  assert.deepEqual((await get('')).map((row) => row.batch_id), ['running_batch']);
  assert.deepEqual((await get('?batch_id=old_batch')).map((row) => row.batch_id), ['old_batch']);
  assert.deepEqual(await get('?batch_id=missing'), []);
  assert.deepEqual(await get('?batch_id=' + encodeURIComponent("' OR 1=1 --")), []);
  assert.equal((await fetch(base + '/generation-queue?batch_id=')).status, 400);
} finally {
  await new Promise((resolve) => server.close(resolve));
  db.close();
  await rm(root, { recursive: true, force: true });
}
console.log('generation queue: exact batch lookup and isolation OK');

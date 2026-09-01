#!/usr/bin/env node

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import express from 'express';

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'daily-plans-'));
process.env.EXAM_DB = path.join(temp, 'exam.db');

const { default: db } = await import('../server/db.js');
const {
  default: dailyPlansRouter,
  getDailyPlan,
  getDailyRuns,
  saveDailyPlan,
} = await import('../server/routes/dailyPlans.js');
const { default: practiceRouter } = await import('../server/routes/practice.js');
const { default: questionsRouter } = await import('../server/routes/questions.js');

const date = '2026-09-01';
saveDailyPlan({
  planDate: date,
  source: 'test',
  items: [
    {
      id: 'ai',
      module: '判断推理',
      task_type: 'ai_practice',
      batch_id: '20260901_logic_01',
      count: 70,
      done: 1,
      route: '/practice',
      reason: 'test',
    },
    {
      id: 'quant',
      module: '资料分析',
      task_type: 'quant_groups',
      groups: [{ id: 'g1', count: 50 }],
      count: 50,
    },
  ],
});
assert.equal(getDailyRuns(date)[0].status, 'scheduled');

saveDailyPlan({
  planDate: date,
  source: 'test',
  items: [
    { id: 'ai', module: '判断推理', batch_id: '20260901_logic_01', count: 70 },
    {
      id: 'quant',
      module: '资料分析',
      task_type: 'quant_groups',
      groups: [{ id: 'g1', count: 50 }],
      count: 50,
    },
  ],
});
assert.equal(getDailyPlan(date).items[0].done, 1, 'save must preserve done');

const insertQuestion = db.prepare(`
  INSERT INTO questions(external_id, category, content, correct_answer, batch_id)
  VALUES (?, '判断推理', ?, 'A', '20260901_logic_01')
`);
const questionIds = [1, 2, 3].map((n) =>
  Number(insertQuestion.run(`daily-Q${n}`, `question ${n}`).lastInsertRowid));

const app = express();
app.use(express.json());
app.use('/api/daily-plans', dailyPlansRouter);
app.use('/api/practice', practiceRouter);
app.use('/api/questions', questionsRouter);
const server = app.listen(0, '127.0.0.1');
await new Promise((resolve) => server.once('listening', resolve));
const base = `http://127.0.0.1:${server.address().port}/api`;

try {
  const created = await fetch(`${base}/practice/sessions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ category: '20260901_logic_01' }),
  }).then((response) => response.json());
  const submitted = await fetch(`${base}/practice/sessions/${created.id}/submit`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      answers: questionIds.map((question_id) => ({ question_id, user_answer: 'A' })),
    }),
  });
  assert.equal(submitted.status, 200);
  assert.equal(getDailyPlan(date).items[0].done, 3, 'submit must reconcile batch');
  const todayPayload = await fetch(
    `${base}/daily-plans/today?date=${date}`,
  ).then((response) => response.json());
  assert.equal(todayPayload.plan.items[0].done, 3);
  assert.equal(todayPayload.runs[0].status, 'imported');

  const importedBatches = await fetch(
    `${base}/questions/meta/batches?date=${date}&module=${encodeURIComponent('判断推理')}`,
  ).then((response) => response.json());
  assert.equal(importedBatches.length, 1);
  assert.equal(importedBatches[0].category, '判断推理');
  assert.equal(importedBatches[0].status, 'imported');

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const progress = await fetch(`${base}/daily-plans/progress`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        date,
        item_id: 'quant',
        group_id: 'g1',
        question_id: 'material-1-Q1',
      }),
    });
    assert.equal(progress.status, 200);
  }
  assert.equal(getDailyPlan(date).items[1].groups[0].done, 1, 'question progress must dedupe');

  db.prepare(`
    INSERT INTO ai_daily_batch_runs(plan_date, module, batch_id, status, planned_count)
    VALUES ('2026-09-02', '言语理解与表达', '20260902_yanyu_01', 'scheduled', 70)
  `).run();
  const scheduled = await fetch(
    `${base}/questions/meta/batches?date=2026-09-02&module=${encodeURIComponent('言语理解与表达')}&include_scheduled=1`,
  ).then((response) => response.json());
  assert.equal(scheduled.length, 1);
  assert.equal(scheduled[0].status, 'scheduled');
  assert.equal(scheduled[0].plan_date, '2026-09-02');

  const removed = await fetch(`${base}/questions/batch/20260901_logic_01`, {
    method: 'DELETE',
  });
  assert.equal(removed.status, 200);
  assert.equal(getDailyRuns(date)[0].status, 'deleted');
} finally {
  await new Promise((resolve) => server.close(resolve));
  db.close();
  fs.rmSync(temp, { recursive: true, force: true });
}

console.log('daily plans backend: ok');

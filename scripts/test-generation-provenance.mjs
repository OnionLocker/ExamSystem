#!/usr/bin/env node
// AI 生成批次必须真实引用 generate/evaluate 两类参考包，并覆盖整批题。

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'generation-provenance-'));
const dbPath = path.join(tempRoot, 'exam.db');
const styleDir = path.join(tempRoot, 'style');
process.env.EXAM_DB = dbPath;

const { default: db } = await import('../server/db.js');

const insertReference = db.prepare(`
  INSERT INTO reference_questions (
    external_id, category, sub_category, question_type, content,
    stem_images, options, correct_answer, explanation_images,
    difficulty, tags, source, year, region, imported_by
  ) VALUES (
    @external_id, '判断推理', '逻辑判断', 'single', @content,
    '[]', @options, 'C', '[]', 3, @tags, @source, 2026, @region, 'test'
  )
`);
const options = JSON.stringify([
  { key: 'A', text: '支持论点' },
  { key: 'B', text: '无关信息' },
  { key: 'C', text: '削弱论点' },
  { key: 'D', text: '重复结论' },
]);
for (let index = 0; index < 12; index += 1) {
  insertReference.run({
    external_id: `provenance-ref-${index}`,
    content: `某研究团队提出第 ${index} 个观点。以下哪项如果为真，最能削弱上述观点？`,
    options,
    tags: JSON.stringify(['判断推理-逻辑判断-削弱论点']),
    source: `2026年${index < 4 ? '广东' : '浙江'}公务员录用考试第${index}题`,
    region: index < 4 ? '广东' : '浙江',
  });
}

const runPython = (...args) => {
  const result = spawnSync(
    'python3',
    [
      path.join(ROOT, 'scripts', 'reference_style.py'),
      '--db', dbPath,
      '--output-dir', styleDir,
      ...args,
    ],
    { cwd: ROOT, encoding: 'utf8' },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout;
};

runPython('build');
const generateContext = JSON.parse(runPython(
  'context', '--role', 'generate',
  '--category', '判断推理',
  '--sub-category', '逻辑判断',
  '--tag', '判断推理-逻辑判断-削弱论点',
  '--count', '3',
));
const evaluateContext = JSON.parse(runPython(
  'context', '--role', 'evaluate',
  '--category', '判断推理',
  '--sub-category', '逻辑判断',
  '--tag', '判断推理-逻辑判断-削弱论点',
  '--count', '1',
));

const makeBatch = (batchId, generation) => {
  const dir = path.join(tempRoot, batchId);
  fs.mkdirSync(dir);
  fs.writeFileSync(
    path.join(dir, 'manifest.json'),
    JSON.stringify({
      batch_id: batchId,
      source: '参考题溯源集成测试',
      region: '广东-模拟',
      year: 2026,
      kind: 'ai-generated',
      generation,
    }, null, 2),
  );
  fs.writeFileSync(
    path.join(dir, 'questions.json'),
    JSON.stringify([{
      external_id: `${batchId}-Q001`,
      category: '判断推理',
      sub_category: '逻辑判断',
      question_type: 'single',
      stem: '某项新研究得出一个结论。以下哪项如果为真，最能削弱该结论？',
      options: JSON.parse(options),
      answer: 'C',
      difficulty: 3,
      tags: ['判断推理-逻辑判断-削弱论点'],
    }], null, 2),
  );
  return dir;
};

const issueGate = (dir, questionId, evaluationContextIds) => {
  const evidenceDir = path.join(dir, 'evidence');
  fs.mkdirSync(evidenceDir);
  const correctness = path.join(evidenceDir, 'correctness.json');
  const quality = path.join(evidenceDir, 'quality.json');
  fs.writeFileSync(correctness, JSON.stringify({
    verdict: 'PASS',
    route: 'B',
    question_ids: [questionId],
    checks: ['答案唯一', '选项数值不碰撞'],
  }, null, 2));
  fs.writeFileSync(quality, JSON.stringify({
    verdict: 'PASS',
    question_ids: [questionId],
    evaluation_context_ids: evaluationContextIds,
    checks: ['考点单一', '真题信息密度', '干扰项有效'],
  }, null, 2));
  const result = spawnSync(
    'python3',
    [
      path.join(ROOT, 'scripts', 'generation_gate.py'),
      'issue', dir,
      '--correctness', correctness,
      '--quality', quality,
    ],
    { cwd: ROOT, encoding: 'utf8' },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
};

const batchId = 'provenance-test-good';
const questionId = `${batchId}-Q001`;
const goodDir = makeBatch(batchId, {
  style_marker: generateContext.marker,
  generation_contexts: [{
    context_id: generateContext.context_id,
    reference_ids: generateContext.reference_ids,
    question_ids: [questionId],
  }],
  evaluation_contexts: [{
    context_id: evaluateContext.context_id,
    reference_ids: evaluateContext.reference_ids,
    question_ids: [questionId],
  }],
});
issueGate(goodDir, questionId, [evaluateContext.context_id]);

const imported = spawnSync(
  process.execPath,
  [path.join(ROOT, 'scripts', 'import-batch.mjs'), goodDir],
  { cwd: ROOT, env: { ...process.env, EXAM_DB: dbPath }, encoding: 'utf8' },
);
assert.equal(imported.status, 0, imported.stderr || imported.stdout);
assert.equal(
  db.prepare('SELECT COUNT(*) AS n FROM questions WHERE external_id = ?').get(questionId).n,
  1,
);
assert.deepEqual(
  db.prepare(
    'SELECT DISTINCT batch_id FROM reference_context_runs WHERE context_id IN (?, ?) ORDER BY batch_id',
  ).all(generateContext.context_id, evaluateContext.context_id),
  [{ batch_id: batchId }],
);

const badBatchId = 'provenance-test-bad';
const badQuestionId = `${badBatchId}-Q001`;
const badDir = makeBatch(badBatchId, {
  style_marker: generateContext.marker,
  generation_contexts: [{
    context_id: 'refctx-00000000000000000000000000000000',
    reference_ids: generateContext.reference_ids,
    question_ids: [badQuestionId],
  }],
  evaluation_contexts: [{
    context_id: evaluateContext.context_id,
    reference_ids: evaluateContext.reference_ids,
    question_ids: [badQuestionId],
  }],
});
issueGate(badDir, badQuestionId, [evaluateContext.context_id]);
const rejected = spawnSync(
  process.execPath,
  [path.join(ROOT, 'scripts', 'import-batch.mjs'), badDir],
  { cwd: ROOT, env: { ...process.env, EXAM_DB: dbPath }, encoding: 'utf8' },
);
assert.notEqual(rejected.status, 0);
assert.match(`${rejected.stderr}\n${rejected.stdout}`, /参考包不存在/);
assert.equal(
  db.prepare('SELECT COUNT(*) AS n FROM questions WHERE external_id = ?').get(badQuestionId).n,
  0,
);

db.close();
fs.rmSync(tempRoot, { recursive: true, force: true });
console.log('generation provenance: ok');

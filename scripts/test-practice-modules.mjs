import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  DAILY_SLUG,
  MODULES,
  dailyDateOf,
  dailySourceFromBatchId,
  moduleFromBatchId,
  moduleOf,
  nameOf,
  stampDailySource,
} from '../src/aiPractice/practiceModules.js';

assert.equal(DAILY_SLUG.tuxing, '图形题目');
assert.ok(MODULES.includes('图形题目'));
assert.equal(moduleFromBatchId('daily-20260910-tuxing-abc123def'), '图形题目');
assert.equal(
  dailySourceFromBatchId('daily-20260910-tuxing-abc123def'),
  '广东省考行测-图形题目-20260910',
);
assert.equal(
  dailySourceFromBatchId('daily-20260909-yanyu-zzzz'),
  '广东省考行测-言语理解与表达-20260909',
);

const collected = {
  batch_id: 'daily-20260910-tuxing-deadbeef',
  module: '图形题目',
  category: '判断推理',
  source: '广东省考行测-图形题目-20260910',
};
assert.equal(moduleOf(collected), '图形题目');
assert.equal(dailyDateOf(collected), '2026-09-10');
assert.equal(nameOf(collected), '广东省考行测-图形题目-20260910');

assert.equal(
  moduleOf({
    category: '判断推理',
    source: '广东省考行测-图形题目-20260910',
    batch_id: 'daily-20260910-tuxing-1',
  }),
  '图形题目',
);
assert.equal(
  moduleOf({
    module: '判断推理',
    category: '判断推理',
    source: '广东省考行测-判断推理-20260910',
    batch_id: 'daily-20260910-panduan-1',
  }),
  '判断推理',
);
assert.equal(
  dailyDateOf({ batch_id: 'daily-20260910-tuxing-1' }),
  '2026-09-10',
);
assert.equal(
  nameOf({ batch_id: 'daily-20260910-tuxing-1', category: '科学推理' }),
  '广东省考行测-图形题目-20260910',
);

const manifest = {
  batch_id: 'daily-20260910-tuxing-cafe',
  source: '临时标题',
  module: '图形题目',
  kind: 'collected',
};
const questions = [{ category: '判断推理', source: '临时标题' }];
assert.equal(stampDailySource(manifest, questions, []), '广东省考行测-图形题目-20260910');
assert.equal(manifest.source, '广东省考行测-图形题目-20260910');
assert.equal(manifest.module, '图形题目');
assert.equal(questions[0].source, '广东省考行测-图形题目-20260910');

const importSrc = fs.readFileSync(fileURLToPath(new URL('./import-batch.mjs', import.meta.url)), 'utf8');
assert.match(importSrc, /if \(manifest\.kind !== 'ai-generated'\) return \[\];/);
assert.match(importSrc, /if \(manifest\.kind === 'ai-generated'\) \{/);

console.log('ok: practice modules / DAILY_SLUG tuxing');

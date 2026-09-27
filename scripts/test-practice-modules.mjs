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
for (const module of ['政治理论', '常识判断']) {
  assert.ok(MODULES.includes(module));
  assert.equal(moduleOf({ module }), module);
  assert.equal(moduleOf({ category: module }), module);
  assert.equal(moduleOf({ source: `广东省考行测-${module}-专项-20260924` }), module);
}
assert.equal(moduleOf({ source: '广东省考常识应用练习' }), '常识判断');
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

const targeted = {
  batch_id: '20260925_hermes_paizu_all_01', module: '数量关系',
  daily_plan_date: '2026-09-25',
  source: '广东省考行测-数量关系-排列组合问题综合-自主难度-20260925',
};
assert.equal(nameOf(targeted), '广东省考行测-数量关系-排列组合问题-综合-20260925');
assert.equal(nameOf({ ...targeted, source: '广东省考行测-数量关系-排列组合问题-位置限制与排队-mid-20260925' }),
  '广东省考行测-数量关系-排列组合问题-位置限制与排队-中等-20260925');
assert.equal(nameOf({ ...targeted, source: '广东省考行测-数量关系-排列组合问题-位置限制与排队-20260925' }),
  '广东省考行测-数量关系-排列组合问题-位置限制与排队-综合-20260925');
for (const [tier, label] of Object.entries({ easy: '简单', mid: '中等', hard: '困难', ladder: '综合', auto: '综合' })) {
  assert.equal(nameOf({ ...targeted, source: `广东省考行测-数量关系-排列组合问题-${tier}-20260925` }),
    `广东省考行测-数量关系-排列组合问题-${label}-20260925`);
  const source = `广东省考行测-数量关系-排列组合问题-位置限制与排队-${label}-20260925`;
  assert.equal(nameOf({ ...targeted, source }), source);
}
assert.equal(nameOf({ ...targeted, batch_id: 'daily-20260925-shuliang-123' }),
  '广东省考行测-数量关系-20260925');

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
assert.match(importSrc, /function upsertDailyRun/);
assert.match(importSrc, /collected-import/);

console.log('ok: practice modules / DAILY_SLUG tuxing');

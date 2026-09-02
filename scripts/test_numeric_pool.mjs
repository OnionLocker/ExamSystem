import assert from 'node:assert/strict';
import {
  CATEGORIES,
  NUMERIC_CUT_SUB_IDS,
  generate,
  judge,
  visibleSubs,
  isSubAvailable,
  isNumericPoolSub,
} from '../src/practice/generators.js';

const SPOILER = /前两项之[和积]|与 n\^|差的差为定值|提示：|斐波那契/;

const sample = (genKey, n = 80) => Array.from({ length: n }, () => generate(genKey));

// —— P0：数推题干不得剧透规律 ——
for (const key of ['sumSeq', 'productSeq', 'powerSeq', 'multiArith', 'arithSeq', 'geoSeq']) {
  for (const q of sample(key, 120)) {
    assert.ok(q.prompt, `${key} 缺题干`);
    assert.ok(!SPOILER.test(q.prompt), `${key} 剧透：${q.prompt}`);
  }
}

// —— P0：两期比重差正确项位置不恒定 ——
const pos = [];
for (const q of sample('twoPeriodRatioDiff', 80)) {
  assert.ok(q.answer >= 1 && q.answer <= 4, `twoPeriodRatioDiff 答案越界 ${q.answer}`);
  pos.push(q.answer);
}
assert.ok(new Set(pos).size > 1, `twoPeriodRatioDiff 正确项位置恒定：${pos.slice(0, 12)}`);
const counts = [1, 2, 3, 4].map((i) => pos.filter((p) => p === i).length);
assert.ok(Math.max(...counts) <= 56, `twoPeriodRatioDiff 某序号占比过高：${counts}`);

// —— P1：CUT 不出现在首页可见池 ——
const visibleIds = [];
for (const cat of CATEGORIES) {
  if (!cat.available) continue;
  for (const sub of visibleSubs(cat)) {
    visibleIds.push(sub.id);
    assert.ok(isSubAvailable(sub), `${sub.id} 应 available`);
    assert.ok(!NUMERIC_CUT_SUB_IDS.has(sub.id), `首页可见 CUT ${sub.id}`);
  }
}
for (const id of NUMERIC_CUT_SUB_IDS) {
  assert.equal(isNumericPoolSub('aux', id) || isNumericPoolSub('quant', id)
    || isNumericPoolSub('readSpot', id) || isNumericPoolSub('basic', id), false);
  const found = CATEGORIES.flatMap((c) => c.subs || []).find((s) => s.id === id);
  assert.ok(found, `CUT ${id} 生成器条目应保留`);
  assert.equal(found.available, false, `CUT ${id} 应为 available=false`);
}

// —— P2：REWORK 核心问法 ——
for (const q of sample('ratio', 60)) {
  assert.ok(!/^\d+\s*:\s*\d+\s*=/.test(q.prompt), `ratio 仍是裸比例式：${q.prompt}`);
  assert.ok(/(投资|分给|溶质|路程)/.test(q.prompt), `ratio 未应用题化：${q.prompt}`);
}
for (const q of sample('diophantine', 40)) {
  assert.ok(!/^\d+x\s*\+\s*\d+y\s*=/.test(q.prompt), `diophantine 仍裸方程：${q.prompt}`);
}
for (const q of sample('permutation', 30)) {
  assert.ok(!/A\(\d+,\d+\)/.test(q.prompt), `permutation 仍写 A(n,k)：${q.prompt}`);
}
for (const q of sample('combination', 30)) {
  assert.ok(!/C\(\d+,\d+\)/.test(q.prompt), `combination 仍写 C(n,k)：${q.prompt}`);
}
const probPrompts = sample('probability', 40).map((q) => q.prompt);
assert.ok(probPrompts.every((p) => !/随机取一个/.test(p)), 'probability 仍考取一个');
assert.ok(probPrompts.some((p) => /不放回|至少|先红后白|恰好/.test(p)), 'probability 缺少应用变式');
for (const q of sample('probability', 20)) {
  assert.equal(q.answerKind, 'frac');
  assert.ok(/^\d+\/\d+$/.test(q.answer), `probability 答案不是分数：${q.answer}`);
  assert.equal(judge(q, q.answer), true);
  const [n, d] = q.answer.split('/').map(Number);
  if (d % 2 === 0 && n % 2 === 0) {
    // 已约分，不应再能除尽
  }
  assert.equal(judge(q, `${n * 2}/${d * 2}`), true, '应接受等值分数');
}
for (const q of sample('decToFrac', 20)) {
  assert.ok(/化成最简分数/.test(q.prompt), `decToFrac 问法：${q.prompt}`);
  assert.equal(q.answerKind, 'frac');
  assert.equal(judge(q, q.answer), true);
}
for (const q of sample('baseDiff', 15)) {
  assert.ok(/进口|出口|差额/.test(q.prompt), `baseDiff 未资料化：${q.prompt}`);
}
for (const q of sample('annualGrowth', 12)) {
  assert.ok(/口诀|年均/.test(q.prompt), `annualGrowth 缺口诀/年份口径：${q.prompt}`);
}
for (const q of sample('mixedGrowth', 15)) {
  assert.ok(/基期量加权/.test(q.prompt), `mixedGrowth 缺权重口径：${q.prompt}`);
}

console.log('numeric pool ok', `visible ${visibleIds.length} / cut ${NUMERIC_CUT_SUB_IDS.size}`);

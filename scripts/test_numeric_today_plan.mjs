import assert from 'node:assert/strict';

const store = new Map();
globalThis.localStorage = {
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => { store.set(key, String(value)); },
  removeItem: (key) => { store.delete(key); },
};
globalThis.window = {
  dispatchEvent() {},
  addEventListener() {},
  removeEventListener() {},
};

const {
  NUMERIC_TODAY_TASK_LIMIT,
  ZILIAO_CAT_IDS,
  HANDS_CAT_IDS,
  applyRaceToTasks,
  buildNumericTodayTasks,
  fillMissingCategoryTasks,
  raceMeetsTask,
  REASON_ROTATION,
  QUANT_ROTATION,
  ZILIAO_DEFAULTS,
  HANDS_DEFAULTS,
} = await import('../src/practice/numericTodayPlan.js');
const { CATEGORIES, NUMERIC_CUT_SUB_IDS, isNumericPoolSub } = await import('../src/practice/generators.js');
const { getBaseMs } = await import('../src/practice/ranks.js');

const countHands = (t) => t.filter((x) => HANDS_CAT_IDS.has(x.catId)).length;
const countZiliao = (t) => t.filter((x) => ZILIAO_CAT_IDS.has(x.catId)).length;
const countCat = (t, id) => t.filter((x) => x.catId === id).length;

// —— 提分导向配比：任意模拟日都成立（含空画像与伪造弱项）——
const SIM_DAYS = ['2026-09-01', '2026-09-02', '2026-09-03', '2026-11-15', '2027-01-01'];
const fakeStats = {
  // 伪造若干弱项：资料/数量/数推各埋一个低正确率，验证弱项优先但不破坏配比
  baseRatio: { totalCount: 40, totalCorrect: 24, totalMs: 40 * 9000, lastPlayedAt: Date.now() - 5 * 86400000 },
  encounter: { totalCount: 30, totalCorrect: 18, totalMs: 30 * 12000, lastPlayedAt: Date.now() - 6 * 86400000 },
  geoSeq: { totalCount: 20, totalCorrect: 11, totalMs: 20 * 10000, lastPlayedAt: Date.now() - 8 * 86400000 },
};
for (const opts of [{ stats: {}, wrongCounts: {} }, { stats: fakeStats, wrongCounts: { baseRatio: 4 } }]) {
  for (const date of SIM_DAYS) {
    const t = buildNumericTodayTasks({ date, ...opts });
    assert.equal(t.length, 9, `${date} 应 9 格`);
    assert.equal(new Set(t.map((x) => x.subId)).size, 9, `${date} 子类不重复`);
    assert.ok(countHands(t) <= 2, `${date} 基础手速格应 ≤2，实为 ${countHands(t)}`);
    assert.ok(countZiliao(t) >= 3, `${date} 资料相关应 ≥3，实为 ${countZiliao(t)}`);
    assert.ok(countCat(t, 'numReason') >= 1, `${date} 数字推理应 ≥1`);
    assert.ok(countCat(t, 'quant') >= 1, `${date} 数量应用应 ≥1`);
    for (const task of t) {
      assert.equal(task.taskType, 'numeric');
      assert.equal(task.status, 'pending');
      assert.equal(task.minAccuracy, 0.9);
      assert.ok(CATEGORIES.some((cat) => cat.id === task.catId && cat.available));
      assert.ok(isNumericPoolSub(task.catId, task.subId), `${date} ${task.subId} 不应是 CUT`);
      assert.ok(!NUMERIC_CUT_SUB_IDS.has(task.subId), `${date} 九宫格出现 CUT ${task.subId}`);
      assert.equal(task.maxAvgMs, Math.round(getBaseMs(task.subId) * 2));
    }
  }
}

// —— 连续日期：数字推理子类轮换，不全是等差 ——
const reasonSubsByDay = [];
for (let i = 0; i < 6; i += 1) {
  const date = `2026-09-${String(10 + i).padStart(2, '0')}`;
  const t = buildNumericTodayTasks({ date, stats: {}, wrongCounts: {} });
  reasonSubsByDay.push(t.filter((x) => x.catId === 'numReason').map((x) => x.subId));
}
const flatReason = reasonSubsByDay.flat();
assert.ok(new Set(flatReason).size > 1, '连续日期数字推理子类应轮换，不能全同一个');
assert.ok(!flatReason.every((s) => s === 'arithSeq'), '数字推理不能连续多天只出等差');

const tasks = buildNumericTodayTasks({ date: '2026-09-01', stats: {}, wrongCounts: {} });
const patched = fillMissingCategoryTasks(tasks.slice(0, 4), { date: '2026-09-01', stats: {}, wrongCounts: {} });
assert.equal(patched.length, 9);
const topped = fillMissingCategoryTasks(tasks.slice(0, 8), { date: '2026-09-01', stats: {}, wrongCounts: {} });
assert.equal(topped.length, 9);

const task = {
  catId: 'basic',
  subId: 'add3',
  count: 30,
  minAccuracy: 0.9,
  maxAvgMs: 9000,
  status: 'pending',
};
assert.equal(raceMeetsTask(task, {
  catId: 'basic', subId: 'add3', total: 30, correct: 27, totalMs: 30 * 8000,
}), true);
assert.equal(raceMeetsTask(task, {
  catId: 'basic', subId: 'add3', total: 30, correct: 26, totalMs: 30 * 8000,
}), false);
assert.equal(raceMeetsTask(task, {
  catId: 'basic', subId: 'add3', total: 29, correct: 29, totalMs: 29 * 8000,
}), false);
assert.equal(raceMeetsTask(task, {
  catId: 'basic', subId: 'add3', total: 30, correct: 30, totalMs: 30 * 9001,
}), false);

const pending = [{ ...task, done: 0, lastRace: null }];
const fail = applyRaceToTasks(pending, {
  catId: 'basic', subId: 'add3', total: 30, correct: 20, totalMs: 30 * 5000,
});
assert.equal(fail.changed, true);
assert.equal(fail.tasks[0].status, 'partial');
assert.equal(fail.tasks[0].done, 0);

const pass = applyRaceToTasks(fail.tasks, {
  catId: 'basic', subId: 'add3', total: 30, correct: 27, totalMs: 30 * 8000,
});
assert.equal(pass.tasks[0].status, 'done');
assert.equal(pass.tasks[0].done, 30);

const locked = applyRaceToTasks(pass.tasks, {
  catId: 'basic', subId: 'add3', total: 30, correct: 0, totalMs: 30 * 20000,
});
assert.equal(locked.tasks[0].status, 'done');

for (const subId of NUMERIC_CUT_SUB_IDS) {
  assert.ok(!REASON_ROTATION.includes(subId), `REASON_ROTATION 含 CUT ${subId}`);
  assert.ok(!QUANT_ROTATION.includes(subId), `QUANT_ROTATION 含 CUT ${subId}`);
  assert.ok(!ZILIAO_DEFAULTS.includes(subId), `ZILIAO_DEFAULTS 含 CUT ${subId}`);
  assert.ok(!HANDS_DEFAULTS.includes(subId), `HANDS_DEFAULTS 含 CUT ${subId}`);
}

const dirty = [
  { subId: 'carryAdd', catId: 'aux' },
  { subId: 'chickenRabbit', catId: 'quant' },
  { subId: 'spotLogic', catId: 'readSpot' },
  { subId: 'add3', catId: 'basic' },
];
const cleaned = fillMissingCategoryTasks(dirty, { date: '2026-09-01', stats: {}, wrongCounts: {} });
assert.ok(cleaned.every((t) => !NUMERIC_CUT_SUB_IDS.has(t.subId)), 'fillMissing 应剔除 CUT');
assert.equal(cleaned.length, 9);

console.log('numeric today plan ok');

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
  applyRaceToTasks,
  buildNumericTodayTasks,
  fillMissingCategoryTasks,
  raceMeetsTask,
} = await import('../src/practice/numericTodayPlan.js');
const { CATEGORIES } = await import('../src/practice/generators.js');
const { getBaseMs } = await import('../src/practice/ranks.js');

const availableCats = CATEGORIES.filter((cat) => cat.available).map((cat) => cat.id);
const tasks = buildNumericTodayTasks({ date: '2026-09-01', stats: {}, wrongCounts: {} });
assert.equal(NUMERIC_TODAY_TASK_LIMIT, 9);
assert.equal(tasks.length, 9);
assert.deepEqual([...new Set(tasks.map((task) => task.catId))].sort(), [...availableCats].sort());
assert.equal(new Set(tasks.map((task) => task.catId)).size, 8);
assert.equal(new Set(tasks.map((task) => task.subId)).size, 9);

const patched = fillMissingCategoryTasks(tasks.slice(0, 4), { date: '2026-09-01', stats: {}, wrongCounts: {} });
assert.equal(patched.length, 9);
assert.equal(new Set(patched.map((task) => task.catId)).size, 8);

const topped = fillMissingCategoryTasks(tasks.slice(0, 8), { date: '2026-09-01', stats: {}, wrongCounts: {} });
assert.equal(topped.length, 9);
for (const task of tasks) {
  assert.equal(task.taskType, 'numeric');
  assert.equal(task.status, 'pending');
  assert.equal(task.minAccuracy, 0.9);
  assert.ok(CATEGORIES.some((cat) => cat.id === task.catId && cat.available));
  assert.equal(task.maxAvgMs, Math.round(getBaseMs(task.subId) * 2));
}

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

console.log('numeric today plan ok');

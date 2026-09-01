import { CATEGORIES } from './generators.js';
import { getBaseMs } from './ranks.js';
import { computeWeakSpots } from './weakSpots.js';

export const NUMERIC_TODAY_TASK_LIMIT = 9;
export const NUMERIC_TODAY_MIN_ACCURACY = 0.9;
export const NUMERIC_TODAY_SPEED_MULT = 2;

const COUNT_BY_CAT = {
  basic: 30,
  aux: 30,
  speedOps: 25,
  dataKill: 20,
  readSpot: 8,
  quant: 12,
  numReason: 12,
  data: 15,
};

export const east8Today = (now = new Date()) =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);

const countFor = (catId) => COUNT_BY_CAT[catId] || 15;

const makeTask = (date, pick, index) => {
  const subId = pick.id;
  const count = countFor(pick.catId);
  return {
    id: `numeric-${date}-${subId}`,
    taskType: 'numeric',
    catId: pick.catId,
    subId,
    module: pick.name,
    catName: pick.catName,
    count,
    plannedCount: count,
    done: 0,
    minAccuracy: NUMERIC_TODAY_MIN_ACCURACY,
    maxAvgMs: Math.round(getBaseMs(subId) * NUMERIC_TODAY_SPEED_MULT),
    status: 'pending',
    reason: pick.reason || '每日数字敏感度',
    lastRace: null,
    index,
  };
};

export const buildNumericTodayTasks = ({
  date,
  stats = {},
  wrongCounts = {},
  now = Date.now(),
} = {}) => {
  const { weak, unexplored } = computeWeakSpots({ stats, wrongCounts, now });
  const ranked = [...weak, ...unexplored];
  const usedCats = new Set();
  const usedSubs = new Set();
  const items = [];

  const take = (pick, allowRepeatCat = false) => {
    if (!pick?.catId || !pick.id) return;
    if (usedSubs.has(pick.id)) return;
    if (!allowRepeatCat && usedCats.has(pick.catId)) return;
    usedCats.add(pick.catId);
    usedSubs.add(pick.id);
    items.push(makeTask(date, pick, items.length));
  };

  for (const pick of ranked) {
    if (items.length >= NUMERIC_TODAY_TASK_LIMIT) break;
    take(pick, false);
  }

  if (items.length < NUMERIC_TODAY_TASK_LIMIT) {
    const leftover = CATEGORIES
      .filter((cat) => cat.available && !usedCats.has(cat.id))
      .sort((a, b) => (b.weight || 0) - (a.weight || 0));
    for (const cat of leftover) {
      if (items.length >= NUMERIC_TODAY_TASK_LIMIT) break;
      const sub = [...(cat.subs || [])].sort((a, b) => (b.weight || 0) - (a.weight || 0))[0];
      if (!sub) continue;
      take({
        ...sub,
        catId: cat.id,
        catName: cat.name,
        reason: '每日数字敏感度',
      }, false);
    }
  }

  for (const pick of ranked) {
    if (items.length >= NUMERIC_TODAY_TASK_LIMIT) break;
    take({ ...pick, reason: pick.reason || '加练' }, true);
  }

  return items;
};

export const fillMissingCategoryTasks = (items, opts = {}) => {
  if (items.length >= NUMERIC_TODAY_TASK_LIMIT) return items;
  const usedSubs = new Set(items.map((task) => task.subId));
  const extra = buildNumericTodayTasks(opts).filter((task) => !usedSubs.has(task.subId));
  if (!extra.length) return items;
  return [...items, ...extra]
    .slice(0, NUMERIC_TODAY_TASK_LIMIT)
    .map((task, index) => ({ ...task, index }));
};

export const raceMeetsTask = (task, race) => {
  if (!task || !race) return false;
  if (race.catId !== task.catId || race.subId !== task.subId) return false;
  const total = Number(race.total) || 0;
  if (total < task.count) return false;
  const accuracy = total > 0 ? Number(race.correct) / total : 0;
  const avgMs = total > 0 ? Number(race.totalMs) / total : Infinity;
  return accuracy >= task.minAccuracy && avgMs <= task.maxAvgMs;
};

export const applyRaceToTasks = (tasks, race) => {
  let changed = false;
  const next = tasks.map((task) => {
    if (race.catId !== task.catId || race.subId !== task.subId) return task;
    if (task.status === 'done') return task;
    const total = Number(race.total) || 0;
    const lastRace = {
      total,
      correct: Number(race.correct) || 0,
      totalMs: Number(race.totalMs) || 0,
      accuracy: total > 0 ? Number(race.correct) / total : 0,
      avgMs: total > 0 ? Number(race.totalMs) / total : 0,
    };
    const done = raceMeetsTask(task, race);
    changed = true;
    return {
      ...task,
      done: done ? task.count : 0,
      lastRace,
      status: done ? 'done' : total > 0 ? 'partial' : 'pending',
    };
  });
  return { tasks: next, changed };
};

export const litCategoryIds = (tasks) =>
  new Set(tasks.filter((task) => task.status === 'done').map((task) => task.catId));

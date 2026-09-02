import { CATEGORIES, isSubAvailable } from './generators.js';
import { getBaseMs } from './ranks.js';
import { computeWeakSpots } from './weakSpots.js';

export const NUMERIC_TODAY_TASK_LIMIT = 9;
export const NUMERIC_TODAY_MIN_ACCURACY = 0.9;
// 稍微放宽日挑战：王者基线 ×2 手感过狠（列式/精算常 14–22s），提到 2.8 仍保留速度门槛
export const NUMERIC_TODAY_SPEED_MULT = 2.8;

const COUNT_BY_CAT = {
  basic: 30,
  aux: 30,
  speedOps: 25,
  dataKill: 20,
  readSpot: 8,
  quant: 10,
  numReason: 10,
  data: 12,
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

// 提分导向的九格硬配比（不靠 weight 碰运气）：
//   基础手速 ≤2（basic / speedOps，纯手速热身，够用即可）
//   资料相关 ≥3（data / dataKill / readSpot：基期粗算、增量比重定性、增长率估速、两期比重、识别考点·资料…）
//   数字推理 ≥1（numReason，子类按日期轮换，禁止连续多天只出等差）
//   数量应用 ≥1（quant：行程/工程/比例等需列式的短冲刺）
//   其余用弱项填充，但基础手速始终 ≤2。
export const ZILIAO_CAT_IDS = new Set(['data', 'dataKill', 'readSpot']);
export const HANDS_CAT_IDS = new Set(['basic', 'speedOps']);
const REASON_CAT_ID = 'numReason';
const QUANT_CAT_ID = 'quant';
// 数字推理子类轮换表（相邻日期取不同子类；不会连续多天只出等差）
export const REASON_ROTATION = ['arithSeq', 'multiArith', 'sumSeq', 'geoSeq', 'powerSeq', 'productSeq'];
// 数量应用轮换（无弱项数据时的默认短冲刺；CUT 不进轮换）
export const QUANT_ROTATION = ['encounter', 'engineering', 'ratio', 'pursue', 'boat', 'probability'];
// 无画像时的资料/手速默认池（按提分优先级排序；CUT 不进池）
export const ZILIAO_DEFAULTS = [
  'baseQtyRough', 'growthShareEst', 'growthRate', 'twoPeriodRatioDiff',
  'baseRatio', 'growthAmt', 'spotZiliao', 'findAdv', 'percentagePoint',
];
export const HANDS_DEFAULTS = ['complement100', 'addOrSub3', 'rollingAdd3', 'add3', 'sub3'];
// 日挑战不主动塞精算：无画像/未练过时让位给粗算·增速·比重；练过且偏弱才可进弱项格
export const TODAY_DEPRIORITIZE = new Set(['baseQtyExact']);

const NUMERIC_TODAY_ZILIAO_MIN = 4;   // 资料相关下限（≥3 硬约束，取 4 以更贴合“提资料处理”目标）
const NUMERIC_TODAY_HANDS_MAX = 2;

// 每个 subId 的元信息（catId/catName/name），供无画像时按 subId 直接取用
const SUB_META = (() => {
  const map = new Map();
  for (const cat of CATEGORIES) {
    if (!cat.available) continue;
    for (const sub of cat.subs || []) {
      if (!isSubAvailable(sub)) continue;
      if (!map.has(sub.id)) {
        map.set(sub.id, { id: sub.id, name: sub.name, catId: cat.id, catName: cat.name });
      }
    }
  }
  return map;
})();

// 用 plan_date 求一个稳定的整数（东八日历日序），供子类轮换；相邻日期差 1。
const dateIndex = (date) => {
  const ms = Date.parse(`${date}T00:00:00Z`);
  if (!Number.isNaN(ms)) return Math.floor(ms / 86400000);
  let h = 0;
  for (const ch of String(date || '')) h = (h * 31 + ch.charCodeAt(0)) % 100000;
  return h;
};

export const buildNumericTodayTasks = ({
  date,
  stats = {},
  wrongCounts = {},
  now = Date.now(),
} = {}) => {
  const { weak, unexplored } = computeWeakSpots({ stats, wrongCounts, now });
  const ranked = [...weak, ...unexplored];
  const usedSubs = new Set();
  const items = [];
  const di = dateIndex(date);

  const push = (pick, reason) => {
    if (!pick?.catId || !pick.id) return false;
    if (!SUB_META.has(pick.id)) return false;
    if (usedSubs.has(pick.id)) return false;
    if (items.length >= NUMERIC_TODAY_TASK_LIMIT) return false;
    usedSubs.add(pick.id);
    items.push(makeTask(date, { ...pick, reason: reason || pick.reason || '每日数字敏感度' }, items.length));
    return true;
  };
  const pushSubId = (subId, reason) => push(SUB_META.get(subId), reason);
  const weakOf = (filterFn) => ranked.filter((p) => filterFn(p) && !usedSubs.has(p.id));
  const handsCount = () => items.filter((t) => HANDS_CAT_IDS.has(t.catId)).length;
  const ziliaoCount = () => items.filter((t) => ZILIAO_CAT_IDS.has(t.catId)).length;

  // 只认“练过的真弱项”做优先；没练过的（unexplored）不冻结轮换，交给按日期轮换保证变化。
  const weakPracticed = (filterFn) => weak.filter((p) => filterFn(p) && !usedSubs.has(p.id));

  // 1) 数字推理 ≥1：优先练过的弱项数推；否则按日期轮换子类（禁止连续多天只出等差）
  const weakReason = weakPracticed((p) => p.catId === REASON_CAT_ID);
  if (!(weakReason[0] && push(weakReason[0], weakReason[0].reason))) {
    for (let k = 0; k < REASON_ROTATION.length; k += 1) {
      if (pushSubId(REASON_ROTATION[(di + k) % REASON_ROTATION.length], '数字推理·轮换')) break;
    }
  }

  // 2) 资料相关 ≥3：只认练过的弱项，未练过的不抢默认池（避免精算等高权重新题挤进日格）
  const weakZiliao = weakPracticed((p) => ZILIAO_CAT_IDS.has(p.catId));
  for (const p of weakZiliao) {
    if (ziliaoCount() >= NUMERIC_TODAY_ZILIAO_MIN) break;
    push(p, p.reason);
  }
  for (const subId of ZILIAO_DEFAULTS) {
    if (ziliaoCount() >= NUMERIC_TODAY_ZILIAO_MIN) break;
    pushSubId(subId, '资料处理提分');
  }

  // 3) 数量应用 ≥1：练过的弱项优先，否则按日期轮换一个需列式的短冲刺
  const weakQuant = weakPracticed((p) => p.catId === QUANT_CAT_ID);
  if (!(weakQuant[0] && push(weakQuant[0], weakQuant[0].reason))) {
    for (let k = 0; k < QUANT_ROTATION.length; k += 1) {
      if (pushSubId(QUANT_ROTATION[(di + k) % QUANT_ROTATION.length], '数量列式冲刺')) break;
    }
  }

  // 4) 基础手速：最多 2 格，弱项优先，否则默认池
  for (const p of weakOf((x) => HANDS_CAT_IDS.has(x.catId))) {
    if (handsCount() >= NUMERIC_TODAY_HANDS_MAX) break;
    push(p, p.reason);
  }
  for (const subId of HANDS_DEFAULTS) {
    if (handsCount() >= NUMERIC_TODAY_HANDS_MAX || items.length >= NUMERIC_TODAY_TASK_LIMIT) break;
    pushSubId(subId, '手速热身');
  }

  // 5) 其余用弱项填充，但基础手速仍 ≤2（不再加 basic/speedOps）
  // 未练过的精算等不主动补位；练过且偏弱仍可进格
  const practicedIds = new Set(weak.map((p) => p.id));
  for (const p of weakOf((x) => !HANDS_CAT_IDS.has(x.catId))) {
    if (items.length >= NUMERIC_TODAY_TASK_LIMIT) break;
    if (TODAY_DEPRIORITIZE.has(p.id) && !practicedIds.has(p.id)) continue;
    push(p, p.reason || '加练');
  }
  // 兜底：仍不足 9，用资料/数量默认池补满（继续避开基础手速）
  for (const subId of [...ZILIAO_DEFAULTS, ...QUANT_ROTATION]) {
    if (items.length >= NUMERIC_TODAY_TASK_LIMIT) break;
    pushSubId(subId, '资料/数量补位');
  }

  return items.map((task, index) => ({ ...task, index }));
};

export const fillMissingCategoryTasks = (items, opts = {}) => {
  const kept = (items || []).filter((task) => SUB_META.has(task.subId));
  if (kept.length >= NUMERIC_TODAY_TASK_LIMIT) {
    return kept.slice(0, NUMERIC_TODAY_TASK_LIMIT).map((task, index) => ({ ...task, index }));
  }
  const usedSubs = new Set(kept.map((task) => task.subId));
  const extra = buildNumericTodayTasks(opts).filter((task) => !usedSubs.has(task.subId));
  if (!extra.length) return kept.map((task, index) => ({ ...task, index }));
  return [...kept, ...extra]
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

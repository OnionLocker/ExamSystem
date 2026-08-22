// ============================================================
// 错题池：让答错的题自己找上门
// ------------------------------------------------------------
// 之前每道题都是 generate() 现随机的，答错了这道题就永远消失。
// 实测历史里 79×2 错过 3 次、7.7%≈1/13 错过 3 次，都是同一道题反复
// 栽跟头而系统从不重出 —— 这个模块就是来堵这个洞的。
//
// 出池规则：答错入池，之后每答对一次 clearStreak +1，连对 CLEAR_TARGET
// 次才移出；中途再错则清零重来。
// ============================================================

import { cloudGet, cloudSet } from '../cloudStorage.js';
import { classifyError } from './errorKinds.js';

const POOL_KEY = 'numeric_wrong_pool_v1';

// 连对几次才算真的掌握、可以出池
const CLEAR_TARGET = 2;
// 出每道题时，有多大概率从错题池里抓一道来还
const RECALL_RATE = 0.35;
// 单个子项最多囤多少道，超了砍最久没错的，防止 JSON 无限膨胀
const MAX_PER_SUB = 60;

const loadPool = () => cloudGet(POOL_KEY, {});
const savePool = (pool) => cloudSet(POOL_KEY, pool);

// 题面即身份：同一个生成器出的同一道题，题面必然一样
const keyOf = (prompt) => prompt;

/**
 * 记一道做错的题。跳过的题同样算错、同样入池。
 */
export const recordWrong = (subId, { prompt, answer, tolerance, userAnswer }) => {
  if (!subId || !prompt) return;
  const pool = loadPool();
  const list = pool[subId] ? [...pool[subId]] : [];
  const k = keyOf(prompt);
  const idx = list.findIndex((it) => keyOf(it.prompt) === k);

  const base = {
    prompt,
    answer,
    tolerance: tolerance ?? 0,
    lastWrongAt: Date.now(),
    lastUserAnswer: userAnswer ?? null,
    kind: classifyError(userAnswer, answer).code,
  };

  if (idx >= 0) {
    list[idx] = { ...list[idx], ...base, wrongCount: (list[idx].wrongCount || 0) + 1, clearStreak: 0 };
  } else {
    list.push({ ...base, wrongCount: 1, clearStreak: 0 });
  }

  // 超量时砍最久没错过的：它们本来也快清了
  if (list.length > MAX_PER_SUB) {
    list.sort((a, b) => b.lastWrongAt - a.lastWrongAt);
    list.length = MAX_PER_SUB;
  }

  pool[subId] = list;
  savePool(pool);
};

/**
 * 一道重出的错题被答对了。连对够次数就出池。
 */
export const recordRecallCorrect = (subId, prompt) => {
  const pool = loadPool();
  const list = pool[subId];
  if (!list) return;
  const idx = list.findIndex((it) => keyOf(it.prompt) === keyOf(prompt));
  if (idx < 0) return;

  const streak = (list[idx].clearStreak || 0) + 1;
  if (streak >= CLEAR_TARGET) list.splice(idx, 1);
  else list[idx] = { ...list[idx], clearStreak: streak };

  if (list.length === 0) delete pool[subId];
  else pool[subId] = list;
  savePool(pool);
};

// 存进去的是纯数据，displayAnswer 这种函数丢了，重出时按 tolerance 还原
const rehydrate = (item) => {
  const q = { prompt: item.prompt, answer: item.answer, fromWrongPool: true };
  if (item.tolerance) {
    q.tolerance = item.tolerance;
    q.displayAnswer = (n) =>
      `${n}（精确值，允许 ${item.answer - item.tolerance} ~ ${item.answer + item.tolerance}）`;
  }
  return q;
};

/**
 * 抓一道待还的错题；池空、掷骰子没中、或都在本场出过了都返回 null。
 * @param {string[]} excludePrompts 本场已出过的题面
 */
export const pickWrong = (subId, excludePrompts = []) => {
  if (Math.random() >= RECALL_RATE) return null;
  const list = loadPool()[subId];
  if (!list || list.length === 0) return null;

  const seen = new Set(excludePrompts);
  const avail = list.filter((it) => !seen.has(keyOf(it.prompt)));
  if (avail.length === 0) return null;

  // 错得越多越优先，同样次数的里面随机挑一道
  const maxWrong = Math.max(...avail.map((it) => it.wrongCount || 1));
  const hottest = avail.filter((it) => (it.wrongCount || 1) === maxWrong);
  return rehydrate(hottest[Math.floor(Math.random() * hottest.length)]);
};

/** 某子项还欠多少道 */
export const countWrong = (subId) => (loadPool()[subId] || []).length;

/** 所有子项的欠账数：{ [subId]: n } */
export const wrongCountsBySub = () => {
  const pool = loadPool();
  const out = {};
  for (const [subId, list] of Object.entries(pool)) {
    if (list?.length) out[subId] = list.length;
  }
  return out;
};

/** 池子总量，给首页角标用 */
export const totalWrong = () =>
  Object.values(loadPool()).reduce((sum, list) => sum + (list?.length || 0), 0);

/** 某子项的错题明细，按错误次数降序 */
export const listWrong = (subId) =>
  [...(loadPool()[subId] || [])].sort((a, b) => (b.wrongCount || 0) - (a.wrongCount || 0));

export const clearSub = (subId) => {
  const pool = loadPool();
  delete pool[subId];
  savePool(pool);
};

export const clearAll = () => savePool({});

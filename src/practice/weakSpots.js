// ============================================================
// 弱项雷达：回答"我今天到底该练哪个"
// ------------------------------------------------------------
// 60 多个子项全靠手点，人自然会挑顺手的练。实测历史里
// 「2 的乘法」95% 正确率刷了 33 场，而 77% 正确率、平均 12.8 秒的
// 「三数加减」只做了 3 场就再没碰过 —— 越弱的越躲，正好练反了。
//
// 数据源用 numeric_rank_stats_v1 而不是练习历史：历史只留最近 100 场，
// 段位统计是累计的，不会被截断。
// ============================================================

import { CATEGORIES } from './generators.js';
import { getBaseMs, MIN_COUNT } from './ranks.js';

// 正确率练到这个水平就不算弱项了
const ACC_TARGET = 0.95;
// 超过这么多天没练，紧迫度不再继续涨
const IDLE_CAP_DAYS = 14;

// 各因素折算成紧迫度分数的系数。数值大小决定了推荐时更看重什么：
// 准度差 1% 记 1 分，速度慢一倍记 20 分，欠一道错题记 3 分。
const W_ACCURACY = 100;
const W_SPEED = 20;
const W_DEBT = 3;
const W_IDLE = 1.5;

const allSubs = () => {
  const out = [];
  for (const cat of CATEGORIES) {
    if (!cat.available) continue;
    for (const sub of cat.subs || []) {
      out.push({ ...sub, catId: cat.id, catName: cat.name, catWeight: cat.weight || 1 });
    }
  }
  return out;
};

/**
 * @param {Object} stats numeric_rank_stats_v1 的内容
 * @param {Object} wrongCounts { [subId]: 欠着的错题数 }
 * @param {number} now 当前时间戳，便于测试
 * @returns {{ weak: Array, unexplored: Array }}
 *   weak       已经练过、但还够不着目标的子项，按紧迫度降序
 *   unexplored 一次都没练过的子项，按考试权重降序
 */
export const computeWeakSpots = ({ stats = {}, wrongCounts = {}, now = Date.now() } = {}) => {
  const weak = [];
  const unexplored = [];

  for (const sub of allSubs()) {
    const st = stats[sub.id];
    const debt = wrongCounts[sub.id] || 0;

    if (!st || !st.totalCount) {
      unexplored.push({ ...sub, reason: '还没练过' });
      continue;
    }

    const accuracy = st.totalCorrect / st.totalCount;
    const avgMs = st.totalMs / st.totalCount;
    const speedRatio = avgMs / getBaseMs(sub.id);
    const daysIdle = st.lastPlayedAt ? (now - st.lastPlayedAt) / 86400000 : IDLE_CAP_DAYS;

    const accGap = Math.max(0, ACC_TARGET - accuracy);
    const speedGap = Math.max(0, speedRatio - 1);

    const urgency =
      accGap * W_ACCURACY +
      speedGap * W_SPEED +
      debt * W_DEBT +
      Math.min(daysIdle, IDLE_CAP_DAYS) * W_IDLE;

    // 题数不够的子项数据不可信，但也确实需要继续练，给一个温和的加成
    const thin = st.totalCount < MIN_COUNT;

    weak.push({
      ...sub,
      accuracy,
      avgMs,
      speedRatio,
      debt,
      daysIdle,
      thin,
      urgency: urgency * (sub.weight || 1) * (thin ? 1.2 : 1),
      // 给 UI 用的一句话解释，说明为什么推它
      reason: pickReason({ accGap, speedGap, debt, daysIdle, thin }),
    });
  }

  weak.sort((a, b) => b.urgency - a.urgency);
  unexplored.sort((a, b) => (b.weight || 0) * (b.catWeight || 1) - (a.weight || 0) * (a.catWeight || 1));
  return { weak, unexplored };
};

// 挑最突出的那个原因来说，别一次糊一堆标签给用户
const pickReason = ({ accGap, speedGap, debt, daysIdle, thin }) => {
  if (debt >= 3) return `欠着 ${debt} 道错题`;
  if (accGap >= 0.1) return '正确率明显偏低';
  if (speedGap >= 1) return '速度比基准慢一倍以上';
  if (accGap >= 0.05) return '正确率还差一口气';
  if (speedGap >= 0.3) return '算得偏慢';
  if (debt > 0) return `欠着 ${debt} 道错题`;
  if (thin) return '练的量还不够';
  if (daysIdle >= 7) return `${Math.floor(daysIdle)} 天没碰了`;
  return '再巩固一轮';
};

/**
 * 首页只需要一小撮：先给最急的几个弱项，不够再拿高权重的新项目补位。
 */
export const topPicks = (input, limit = 3) => {
  const { weak, unexplored } = computeWeakSpots(input);
  const picks = weak.slice(0, limit);
  if (picks.length < limit) {
    picks.push(...unexplored.slice(0, limit - picks.length));
  }
  return picks;
};

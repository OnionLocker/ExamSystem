// ============================================================
// 段位系统
// --------------------------------------
// 规则总纲（站在广东省考行测老师的角度）：
//   · 只有"晋升模式"（原冲刺模式）计入段位统计；训练模式自由刷不计。
//   · 每个子项独立评段，因为不同题型难度维度不同。
//   · 段位由两维度决定：平均用时（速度是主轴）+ 正确率（准度是闸门）。
//   · 累计"有效题数" < 20 题的子项显示"未评级"（Unranked）。
//   · 分类段位 = 该类所有已评级子项段位的平均值（四舍五入向下）。
//   · 整体段位 = 四大类的平均值。
// ============================================================

// ---------------- 段位定义（由低到高） ----------------
export const RANKS = [
  { id: 'unranked', label: '未评级', short: 'UR', value: 0, color: '#94a3b8', bg: '#e2e8f0', glow: null },
  { id: 'bronze',   label: '青铜',   short: 'B',  value: 1, color: '#a17b5d', bg: '#3b2a1f', glow: null },
  { id: 'silver',   label: '白银',   short: 'S',  value: 2, color: '#c0c7d1', bg: '#2c3340', glow: null },
  { id: 'gold',     label: '黄金',   short: 'G',  value: 3, color: '#fbc02d', bg: '#3d2f0a', glow: null },
  { id: 'platinum', label: '铂金',   short: 'P',  value: 4, color: '#4fd1c5', bg: '#0f2e2b', glow: null },
  { id: 'diamond',  label: '钻石',   short: 'D',  value: 5, color: '#60a5fa', bg: '#16264a', glow: '#60a5fa' },
  { id: 'master',   label: '大师',   short: 'M',  value: 6, color: '#a855f7', bg: '#2a143f', glow: '#a855f7' },
  { id: 'king',     label: '王者',   short: 'K',  value: 7, color: '#ff6b6b', bg: '#3b0f14', glow: '#ff6b6b' },
];

export const getRank = (id) => RANKS.find((r) => r.id === id) || RANKS[0];
export const getRankByValue = (v) => RANKS.find((r) => r.value === v) || RANKS[0];

// ---------------- 评级阈值（按 baseMs 的倍率 + 正确率闸门） ----------------
// [rankId, msMultiplier, minAccuracy]  由严到宽
const THRESHOLDS = [
  ['king',     1.0, 0.95],
  ['master',   1.3, 0.92],
  ['diamond',  1.7, 0.88],
  ['platinum', 2.2, 0.85],
  ['gold',     3.0, 0.80],
  ['silver',   4.0, 0.70],
];
// 其余达标但达不到白银 → 青铜

// ---------------- 子项基准用时 baseMs（毫秒） ----------------
// 这是"王者基线"：顶尖考生的平均每题用时。
export const SUB_BASE_MS = {
  // basic 基本计算
  add3:      8000,
  sub3:      8000,
  addsub3:   8000,
  add4:      10000,
  mul3x1:    9000,
  div3by1:   10000,
  mul2x2:    10000,
  big99:     6000,
  mulEst:    7000,
  div5by3:   15000,
  // aux 计算辅助
  carryAdd:  4000,
  borrowSub: 4000,
  mulBy2:    4000,
  mulBy3:    4000,
  mulBy4:    4000,
  mulBy5:    4000,
  mulBy6:    4000,
  mulBy9:    4000,
  mulBy11:   5000,
  mulBy15:   5000,
  fracToDec: 5000,
  decToFrac: 5000,
  pctToFrac: 5000,
  fracToPct: 5000,
  pctToFracEst: 8000,
  square:    4000,
  // quant 数量关系
  ratio:       25000,
  engineering: 25000,
  amgm:        25000,
  hanxin:      20000,
  diophantine: 25000,
  gcdQ:        20000,
  lcmQ:        20000,
  weekday:     18000,
  // data 资料分析
  baseQtyRough: 20000,
  baseQtyExact: 30000,
  growthAmt:    20000,
  growthRate:   20000,
  baseDiff:     30000,
  prodGrowth:   35000,
  divGrowth:    35000,
  avgGrowth:    35000,
  baseRatio:    40000,
  ratioDiff:    40000,
  pullGrowth:   40000,
  contribute:   40000,
  annualGrowth: 40000,
};

export const getBaseMs = (subId) => SUB_BASE_MS[subId] || 15000;

// 最少有效题数门槛（低于此数显示"未评级"）
export const MIN_COUNT = 20;

// ---------------- 核心评级函数 ----------------
// 输入：{ totalCount, totalCorrect, totalMs, subId }
// 输出：{ rankId, accuracy, avgMs, progressToNext (0~1) }
export const evaluate = (stat, subId) => {
  if (!stat || stat.totalCount < MIN_COUNT) {
    return {
      rankId: 'unranked',
      accuracy: stat && stat.totalCount ? stat.totalCorrect / stat.totalCount : 0,
      avgMs: stat && stat.totalCount ? stat.totalMs / stat.totalCount : 0,
      progressToNext: stat ? stat.totalCount / MIN_COUNT : 0,
      needMore: MIN_COUNT - (stat?.totalCount || 0),
    };
  }
  const accuracy = stat.totalCorrect / stat.totalCount;
  const avgMs = stat.totalMs / stat.totalCount;
  const base = getBaseMs(subId);

  let rankId = 'bronze';
  for (const [id, mul, acc] of THRESHOLDS) {
    if (avgMs <= base * mul && accuracy >= acc) {
      rankId = id;
      break;
    }
  }

  // 离下一段的进度（速度 + 准度各占一半）
  const nextIdx = THRESHOLDS.findIndex((t) => t[0] === rankId) - 1;
  let progressToNext = 1;
  if (rankId !== 'king') {
    const target = nextIdx >= 0 ? THRESHOLDS[nextIdx] : THRESHOLDS[0];
    const msTargetGap = base * (THRESHOLDS.find((t) => t[0] === rankId)?.[1] ?? 4.0) - base * target[1];
    const accTargetGap = target[2] - (THRESHOLDS.find((t) => t[0] === rankId)?.[2] ?? 0);
    const msProgress = msTargetGap <= 0 ? 1 :
      Math.max(0, Math.min(1, (base * (THRESHOLDS.find((t) => t[0] === rankId)?.[1] ?? 4.0) - avgMs) / msTargetGap));
    const accProgress = accTargetGap <= 0 ? 1 :
      Math.max(0, Math.min(1, (accuracy - (THRESHOLDS.find((t) => t[0] === rankId)?.[2] ?? 0)) / accTargetGap));
    progressToNext = (msProgress + accProgress) / 2;
  }

  return { rankId, accuracy, avgMs, progressToNext };
};

// ---------------- 存储层 ----------------
const STATS_KEY = 'numeric_rank_stats_v1';
// 数据结构：{ [subId]: { totalCount, totalCorrect, totalMs, bestAvgMs, plays, lastPlayedAt } }

export const loadStats = () => {
  try {
    return JSON.parse(localStorage.getItem(STATS_KEY) || '{}');
  } catch {
    return {};
  }
};

const saveStats = (stats) => {
  try {
    localStorage.setItem(STATS_KEY, JSON.stringify(stats));
  } catch {
    // ignore
  }
};

// 晋升模式完赛后：合并一场结果
export const recordPromotionResult = ({ subId, total, correct, totalMs }) => {
  if (!subId || !total) return null;
  const stats = loadStats();
  const prev = stats[subId] || {
    totalCount: 0, totalCorrect: 0, totalMs: 0, bestAvgMs: Infinity, plays: 0, lastPlayedAt: 0,
  };
  const avgMs = totalMs / total;
  const next = {
    totalCount: prev.totalCount + total,
    totalCorrect: prev.totalCorrect + correct,
    totalMs: prev.totalMs + totalMs,
    bestAvgMs: Math.min(prev.bestAvgMs ?? Infinity, avgMs),
    plays: prev.plays + 1,
    lastPlayedAt: Date.now(),
  };
  stats[subId] = next;
  saveStats(stats);
  try {
    window.dispatchEvent(new CustomEvent('numeric-rank-change'));
  } catch {
    // ignore
  }
  return { before: evaluate(prev, subId), after: evaluate(next, subId) };
};

// 清空（调试）
export const clearRankStats = () => {
  saveStats({});
  try {
    window.dispatchEvent(new CustomEvent('numeric-rank-change'));
  } catch {
    // ignore
  }
};

// ---------------- 聚合：分类段位 + 整体段位 ----------------
// 对一个分类：取其下所有已评级子项 rank.value 的平均值，向下取整 → 分类段位
// 整体：对四个分类段位再平均
export const computeCategoryRank = (cat, stats) => {
  const entries = cat.subs.map((s) => ({
    sub: s,
    stat: stats[s.id],
    eval: evaluate(stats[s.id], s.id),
  }));
  const ranked = entries.filter((e) => e.eval.rankId !== 'unranked');
  if (ranked.length === 0) {
    return {
      rankId: 'unranked',
      rankedCount: 0,
      totalSubs: cat.subs.length,
      entries,
    };
  }
  const avg = ranked.reduce((s, e) => s + getRank(e.eval.rankId).value, 0) / ranked.length;
  const v = Math.max(1, Math.round(avg));
  return {
    rankId: getRankByValue(v).id,
    rankedCount: ranked.length,
    totalSubs: cat.subs.length,
    entries,
    avgValue: avg,
  };
};

export const computeOverallRank = (categories, stats) => {
  const catRanks = categories.map((c) => computeCategoryRank(c, stats));
  const ranked = catRanks.filter((c) => c.rankId !== 'unranked');
  if (ranked.length === 0) {
    return { rankId: 'unranked', catRanks, totalScore: 0 };
  }
  const avg = ranked.reduce((s, c) => s + getRank(c.rankId).value, 0) / ranked.length;
  const v = Math.max(1, Math.round(avg));
  // 段位总分（展示用）：所有子项 rankValue*100 之和
  let totalScore = 0;
  for (const c of catRanks) {
    for (const e of c.entries) {
      totalScore += getRank(e.eval.rankId).value * 100;
    }
  }
  return {
    rankId: getRankByValue(v).id,
    catRanks,
    totalScore,
  };
};

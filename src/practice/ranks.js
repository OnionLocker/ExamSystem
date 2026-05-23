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

import { cloudGet, cloudSet } from '../cloudStorage.js';

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
export const THRESHOLDS = [
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
  encounter:    20000,
  pursue:       20000,
  boat:         25000,
  mixture:      30000,
  dilute:       25000,
  inclusion2:   25000,
  permutation:  20000,
  combination:  20000,
  probability:  20000,
  chickenRabbit: 20000,
  age:           25000,
  profit:        25000,
  planting:      18000,
  squareFormation: 18000,
  // numReason 数字推理（行测高频，每题平均 60s 是王者标准）
  arithSeq:    20000,
  geoSeq:      20000,
  sumSeq:      25000,
  productSeq:  25000,
  powerSeq:    30000,
  multiArith:  35000,
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
  mixedGrowth:  35000,
  multipleOf:   12000,
  percentagePoint: 18000,
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
// 数据结构（v1 → 现在的 stat）：
// {
//   [subId]: {
//     totalCount, totalCorrect, totalMs, bestAvgMs, plays, lastPlayedAt,
//     // —— 新增 LP 系统字段 ——
//     lp: 0~100,            // 当前 ladderRank 段位内的 LP
//     ladderRank: rankId,   // 显式段位（受 LP 升降影响，不同于累计 evaluate()）
//   }
// }
// 老用户没有 lp/ladderRank 字段时，第一次完赛会用 evaluate(prev) 的结果初始化。

export const loadStats = () => cloudGet(STATS_KEY, {});

const saveStats = (stats) => cloudSet(STATS_KEY, stats);

// ---------------- LP 系统 ----------------
// 每段位的「合格 perf 标准」：perf = (baseMs/avgMs) * accuracy
// 高于此值得正分，低于此值得负分
const PERF_STD = {
  unranked: 0.20,
  bronze:   0.30,
  silver:   0.45,
  gold:     0.60,
  platinum: 0.75,
  diamond:  0.90,
  master:   1.05,
  king:     1.20,
};

// 每场 LP 上下限（避免一场翻盘）
const LP_DELTA_MIN = -30;
const LP_DELTA_MAX = 40;

// 升段后留 30 LP 缓冲（避免立刻掉段）
const LP_AFTER_PROMOTE = 30;
// 掉段后留 70 LP 缓冲（不至于刚掉段又立马再掉）
const LP_AFTER_DEMOTE = 70;

// 累计段位下限保护：ladderRank 不能比 evaluate(累计) 低 N 阶以上
const PROTECT_GAP = 2;

// 给定 rankId 取上一段（更高）/ 下一段（更低）
// RANKS 顺序：unranked(0) → king(7)
const rankUp = (id) => {
  const v = getRank(id).value;
  return getRankByValue(Math.min(7, v + 1)).id;
};
const rankDown = (id) => {
  const v = getRank(id).value;
  // 不掉到 unranked
  return getRankByValue(Math.max(1, v - 1)).id;
};

/**
 * 计算单场比赛对 LP / 段位的影响
 * 输入：
 *   prevStat   - 该子项的上一次保存值（包含 lp/ladderRank，可能为 undefined 字段）
 *   raceResult - { total, correct, totalMs }
 *   subId
 *   cumulRankId - 累计 evaluate() 计算出的"真实段位"，用于下限保护
 * 输出：
 *   { lpDelta, lpBefore, lpAfter, rankBefore, rankAfter, promoted, demoted, perf, std, protected }
 */
export const computeRaceLpChange = (prevStat, raceResult, subId, cumulRankId) => {
  const total = raceResult.total;
  const correct = raceResult.correct;
  const accuracy = total > 0 ? correct / total : 0;
  const avgMs = total > 0 ? raceResult.totalMs / total : 0;
  const base = getBaseMs(subId);
  const speedRatio = avgMs > 0 ? base / avgMs : 0; // >1 = 比基线快

  // 当前段位（首次进入：用累计 evaluate 的结果或 bronze 兜底）
  const lpBefore = Number.isFinite(prevStat?.lp) ? prevStat.lp : 50;
  const rankBefore =
    prevStat?.ladderRank ||
    (cumulRankId !== 'unranked' ? cumulRankId : 'bronze');

  const std = PERF_STD[rankBefore] ?? PERF_STD.bronze;
  const perf = speedRatio * accuracy;

  // 准度奖惩
  let accBonus = 0;
  if (accuracy >= 0.95) accBonus = 10;
  else if (accuracy < 0.7) accBonus = -10;

  // 主体公式：(perf - std) × 80 + 准度奖惩，截断到 [-30, +40]
  let delta = Math.round((perf - std) * 80) + accBonus;
  delta = Math.max(LP_DELTA_MIN, Math.min(LP_DELTA_MAX, delta));

  // 应用 LP，处理升降段
  let lpAfter = lpBefore + delta;
  let rankAfter = rankBefore;
  let promoted = false;
  let demoted = false;
  let isProtected = false;

  if (lpAfter >= 100 && rankBefore !== 'king') {
    rankAfter = rankUp(rankBefore);
    lpAfter = LP_AFTER_PROMOTE;
    promoted = true;
  } else if (lpAfter < 0) {
    if (rankBefore === 'bronze' || rankBefore === 'unranked') {
      lpAfter = 0; // 已是底段，不再掉
    } else {
      rankAfter = rankDown(rankBefore);
      lpAfter = LP_AFTER_DEMOTE;
      demoted = true;
    }
  } else {
    lpAfter = Math.max(0, Math.min(100, lpAfter));
  }

  // 累计下限保护：rankAfter 不能比累计段位低 PROTECT_GAP 阶以上
  if (cumulRankId && cumulRankId !== 'unranked') {
    const cumulV = getRank(cumulRankId).value;
    const afterV = getRank(rankAfter).value;
    const minAllowedV = Math.max(1, cumulV - PROTECT_GAP);
    if (afterV < minAllowedV) {
      rankAfter = getRankByValue(minAllowedV).id;
      lpAfter = Math.max(lpAfter, LP_AFTER_DEMOTE); // 给个缓冲
      demoted = false; // 触发保护时不算掉段
      isProtected = true;
    }
  }

  return {
    lpDelta: delta,
    lpBefore,
    lpAfter,
    rankBefore,
    rankAfter,
    promoted,
    demoted,
    perf,
    std,
    accuracy,
    avgMs,
    protected: isProtected,
  };
};

// 晋升模式完赛后：合并一场结果
export const recordPromotionResult = ({ subId, total, correct, totalMs }) => {
  if (!subId || !total) return null;
  const stats = loadStats();
  const prev = stats[subId] || {
    totalCount: 0, totalCorrect: 0, totalMs: 0, bestAvgMs: Infinity, plays: 0, lastPlayedAt: 0,
  };
  const avgMs = totalMs / total;

  // 先算累计 evaluate（用于段位下限保护 + 「真实实力」展示）
  const evalBefore = evaluate(prev, subId);

  const cumulNext = {
    totalCount: prev.totalCount + total,
    totalCorrect: prev.totalCorrect + correct,
    totalMs: prev.totalMs + totalMs,
    bestAvgMs: Math.min(prev.bestAvgMs ?? Infinity, avgMs),
    plays: prev.plays + 1,
    lastPlayedAt: Date.now(),
  };
  const evalAfter = evaluate(cumulNext, subId);

  // 计算 LP 变化（用「应用本场后」的累计段位作为下限保护）
  const lp = computeRaceLpChange(
    prev,
    { total, correct, totalMs },
    subId,
    evalAfter.rankId,
  );

  // 合并写回（保留 LP 字段）
  const next = {
    ...cumulNext,
    lp: lp.lpAfter,
    ladderRank: lp.rankAfter,
  };
  stats[subId] = next;
  saveStats(stats);
  try {
    window.dispatchEvent(new CustomEvent('numeric-rank-change'));
  } catch {
    // ignore
  }
  return { before: evalBefore, after: evalAfter, lp };
};

// ---------------- LP 显示读取 ----------------
// 取某子项的"显示用段位"（ladderRank + lp），未玩过的就 fallback 到 evaluate
export const getLadderInfo = (subId, statsArg) => {
  const stats = statsArg || loadStats();
  const stat = stats[subId];
  const evalRes = evaluate(stat, subId);
  if (!stat || !stat.ladderRank) {
    return {
      rankId: evalRes.rankId,
      lp: stat?.lp ?? 0,
      hasLadder: false,
      cumulRankId: evalRes.rankId,
      progressToNext: evalRes.progressToNext,
    };
  }
  return {
    rankId: stat.ladderRank,
    lp: stat.lp ?? 0,
    hasLadder: true,
    cumulRankId: evalRes.rankId,
    progressToNext: evalRes.progressToNext,
  };
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
// v2: 加权平均聚合
//   · 分类段位 = Σ(rank.value × sub.weight) / Σ(sub.weight)，仅取已评级子项
//   · 整体段位 = Σ(rank.value × cat.weight) / Σ(cat.weight)，仅取已评级分类
// 子项 weight 反映真实省考出题频率（5=每年必考 / 1-2=偶尔），
// 分类 weight 反映真实考试分值占比（data 40 / quant 35 / aux 15 / basic 10）。
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
  // 加权平均（subject weight）
  let sumWV = 0;
  let sumW = 0;
  for (const e of ranked) {
    const w = e.sub.weight ?? 1;
    sumWV += getRank(e.eval.rankId).value * w;
    sumW += w;
  }
  const avg = sumWV / sumW;
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
  const catRanks = categories.map((c) => ({ ...computeCategoryRank(c, stats), cat: c }));
  const ranked = catRanks.filter((c) => c.rankId !== 'unranked');
  if (ranked.length === 0) {
    return { rankId: 'unranked', catRanks, totalScore: 0 };
  }
  // 加权平均（category weight）
  let sumWV = 0;
  let sumW = 0;
  for (const c of ranked) {
    const w = c.cat.weight ?? 1;
    sumWV += getRank(c.rankId).value * w;
    sumW += w;
  }
  const avg = sumWV / sumW;
  const v = Math.max(1, Math.round(avg));
  // 段位总分（展示用）：Σ(子项段位 × 子项权重 × 分类权重)
  let totalScore = 0;
  for (const c of catRanks) {
    for (const e of c.entries) {
      const subW = e.sub.weight ?? 1;
      const catW = c.cat.weight ?? 1;
      totalScore += getRank(e.eval.rankId).value * subW * catW;
    }
  }
  return {
    rankId: getRankByValue(v).id,
    catRanks,
    totalScore: Math.round(totalScore),
    avgValue: avg,
  };
};

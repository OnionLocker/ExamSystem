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
// 这是"王者基线"：顶尖考生做**本站生成题**的平均每题用时（含读题 + 心算 + 键入）。
//
// 口径必须对齐生成题、不能照搬真题耗时：生成题把读材料、定位数据、判断问法
// 全省了（资料分析尤其明显 —— 题干就是"基期 500，现期 700，增长率≈?"）。
// 基线按真题估会让 speedRatio 虚高，perf 轻松破王者线，正确率再低也一路涨段。
export const SUB_BASE_MS = {
  // basic 基本计算（题干就是算式，时间 = 心算 + 键入答案）
  add3:      4500,
  sub3:      4500,
  addOrSub3: 4500,
  addsub3:   6000,
  add4:      6500,
  mul3x1:    5000,
  div3by1:   5500,
  mul2x2:    6000,
  big99:     3000,
  mulEst:    4000,
  div5by3:   8000,
  // aux 计算辅助（记忆型速算，答案短）
  carryAdd:  1500,
  borrowSub: 1600,
  mulBy2:    1500,
  mulBy3:    1600,
  mulBy4:    1700,
  mulBy5:    1600,
  mulBy6:    1800,
  mulBy9:    1800,
  mulBy11:   2200,
  mulBy15:   2500,
  fracToDec: 2500,
  decToFrac: 2600,
  pctToFrac: 2200,
  fracToPct: 2200,
  pctToFracEst: 3500,
  square:    1800,
  // quant 数量关系（要读题建模，但题干只有一行、数字友好）
  ratio:       12000,
  engineering: 13000,
  amgm:         7000,
  hanxin:      16000,
  diophantine: 16000,
  gcdQ:         9000,
  lcmQ:         9000,
  weekday:      7000,
  encounter:    9000,
  pursue:       9000,
  boat:        11000,
  mixture:     14000,
  dilute:      11000,
  inclusion2:  11000,
  permutation:  9000,
  combination:  9000,
  probability:  7000,
  chickenRabbit: 9000,
  age:          11000,
  profit:       12000,
  planting:      7000,
  squareFormation: 4500,
  // numReason 数字推理（生成题带规律提示，比真题快得多）
  arithSeq:     7000,
  geoSeq:       7000,
  sumSeq:       7000,
  productSeq:   7000,
  powerSeq:    11000,
  multiArith:  12000,
  // data 资料分析（生成题是纯计算，没有读材料/定位数据的开销）
  baseQtyRough:  8000,
  baseQtyExact: 11000,
  growthAmt:     9000,
  growthRate:    7000,
  baseDiff:      8000,
  prodGrowth:    8000,
  divGrowth:    10000,
  avgGrowth:    10000,
  baseRatio:    12000,
  ratioDiff:    14000,
  pullGrowth:   11000,
  contribute:    7000,
  annualGrowth: 14000,
  mixedGrowth:  11000,
  multipleOf:    5000,
  percentagePoint: 6000,
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
export const PERF_STD = {
  unranked: 0.20,
  bronze:   0.30,
  silver:   0.45,
  gold:     0.60,
  platinum: 0.75,
  diamond:  0.90,
  master:   1.05,
  king:     1.20,
};

// 准度奖惩（LP 直接加减）：公考的失分点是准度而不是手速，低于 85% 就开始扣分。
// 旧规则只在 <70% 才罚，70~95% 是一整段"无所谓"的平地，于是刷手速最划算。
// [正确率下限, LP 奖惩]，由高到低取第一条命中的
export const ACC_BONUS_TIERS = [
  [0.95,  10],
  [0.85,   0],
  [0.75, -10],
  [0.65, -20],
  [0,    -30], // 抵掉全部速度优势：这个准度在考场上是不及格的
];

export const accBonusFor = (accuracy) =>
  ACC_BONUS_TIERS.find(([min]) => accuracy >= min)?.[1] ?? 0;

// 速度项封顶：比基线快 1.5 倍以上不再额外加分。
// 没有封顶时，1 秒做完基线 4 秒的题会算出 speedRatio=4、perf 远超王者线 1.20，
// 每场都吃 +40 上限，正确率再低也一路涨段 —— 段位就变成了纯手速榜。
export const SPEED_RATIO_CAP = 1.5;

// 每场 LP 上下限（避免一场翻盘）
export const LP_DELTA_MIN = -30;
export const LP_DELTA_MAX = 40;

// 升段后留 30 LP 缓冲（避免立刻掉段）
export const LP_AFTER_PROMOTE = 30;
// 掉段后留 70 LP 缓冲（不至于刚掉段又立马再掉）
export const LP_AFTER_DEMOTE = 70;

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
  // >1 = 比基线快；封顶之后再快也不换分，把胜负交回准度
  const speedRatio = avgMs > 0 ? Math.min(base / avgMs, SPEED_RATIO_CAP) : 0;

  // 当前段位（首次进入：用累计 evaluate 的结果或 bronze 兜底）
  const lpBefore = Number.isFinite(prevStat?.lp) ? prevStat.lp : 50;
  const rankBefore =
    prevStat?.ladderRank ||
    (cumulRankId !== 'unranked' ? cumulRankId : 'bronze');

  const std = PERF_STD[rankBefore] ?? PERF_STD.bronze;
  const perf = speedRatio * accuracy;

  const accBonus = accBonusFor(accuracy);

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
// v3: 覆盖度加权（防止「刷一个简单口算就上高段」）
//   · 分类段位 = Σ(rank.value × sub.weight) / Σ(全部 sub.weight)
//       —— 关键：未评级子项按 value=0 计入分母，所以想拿高分类段位
//          必须把该类大部分子项都练到又快又准（广度 + 深度）。
//   · 整体段位 = Σ(cat.avgValue × cat.weight) / Σ(全部 cat.weight)
//       —— 关键：没练的整类按 0 分计入分母（不再被忽略），
//          没覆盖资料分析/数量关系这些大类就上不了高段。
//   · 两级覆盖度叠加：高整体段位需要「全类覆盖 + 每类内广度」。
//   · 只要该类/整体至少有一个已评级子项，就至少显示青铜（不会因四舍五入回到未评级）。
// 子项 weight 反映真实省考出题频率（5=每年必考 / 1-2=偶尔），
// 分类 weight 反映真实考试分值占比（data 30 / quant 30 / numReason 15 / aux 15 / basic 10）。
export const computeCategoryRank = (cat, stats) => {
  const entries = cat.subs.map((s) => ({
    sub: s,
    stat: stats[s.id],
    eval: evaluate(stats[s.id], s.id),
  }));
  const ranked = entries.filter((e) => e.eval.rankId !== 'unranked');

  // 覆盖度加权：全部子项都计入分母，未评级子项 value=0
  let sumWV = 0;
  let sumW = 0;
  for (const e of entries) {
    const w = e.sub.weight ?? 1;
    sumW += w;
    sumWV += getRank(e.eval.rankId).value * w; // unranked → 0
  }
  const avgValue = sumW > 0 ? sumWV / sumW : 0;
  const rankId =
    ranked.length === 0 ? 'unranked' : getRankByValue(Math.max(1, Math.round(avgValue))).id;

  return {
    rankId,
    rankedCount: ranked.length,
    totalSubs: cat.subs.length,
    entries,
    avgValue,
  };
};

export const computeOverallRank = (categories, stats) => {
  const catRanks = categories.map((c) => ({ ...computeCategoryRank(c, stats), cat: c }));
  const anyRanked = catRanks.some((c) => c.rankId !== 'unranked');

  // 覆盖度加权：全部分类都计入分母，没练的类 avgValue=0
  // 用分类的连续 avgValue（未四舍五入）参与，避免二次取整造成断崖
  let sumWV = 0;
  let sumW = 0;
  for (const c of catRanks) {
    const w = c.cat.weight ?? 1;
    sumW += w;
    sumWV += (c.avgValue ?? 0) * w;
  }
  const avgValue = sumW > 0 ? sumWV / sumW : 0;
  const rankId = !anyRanked ? 'unranked' : getRankByValue(Math.max(1, Math.round(avgValue))).id;

  // 段位总分（展示用，随覆盖广度累加）：Σ(子项段位 × 子项权重 × 分类权重)
  let totalScore = 0;
  for (const c of catRanks) {
    for (const e of c.entries) {
      const subW = e.sub.weight ?? 1;
      const catW = c.cat.weight ?? 1;
      totalScore += getRank(e.eval.rankId).value * subW * catW;
    }
  }
  return {
    rankId,
    catRanks,
    totalScore: Math.round(totalScore),
    avgValue,
  };
};

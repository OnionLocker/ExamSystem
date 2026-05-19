// ============================================================
// SM-2 间隔重复算法（Anki 同款，简化版）
// ============================================================
// 每张卡的复习记录：{ ef, interval, reps, dueAt }
//   ef       熟练因子（默认 2.5，每次评分调整）
//   interval 当前复习间隔（天）
//   reps     连续答对次数
//   dueAt    下次到期时间戳（毫秒）
//
// 用户评分 q ∈ {0, 3, 4, 5}：
//   0 - 完全不会（重学）
//   3 - 想了一下才会（困难）
//   4 - 会但有点慢（一般）
//   5 - 立刻就会（简单）

const NEW_CARD_INTERVAL_HOURS = 4; // 新卡片首次重见间隔

export const newCardState = () => ({
  ef: 2.5,
  interval: 0,
  reps: 0,
  dueAt: Date.now(),
});

/**
 * 接受评分，返回新的卡片状态
 * @param {Object} prev - 之前的状态（{ ef, interval, reps, dueAt }）
 * @param {0|3|4|5} q - 用户评分
 * @returns {Object} 新状态
 */
export const review = (prev, q) => {
  const cur = prev || newCardState();

  if (q < 3) {
    // 答错：重置进度，4 小时后再来
    return {
      ef: Math.max(1.3, cur.ef - 0.2),
      interval: 0,
      reps: 0,
      dueAt: Date.now() + NEW_CARD_INTERVAL_HOURS * 3600 * 1000,
    };
  }

  // 答对：调整 EF
  let ef = cur.ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02));
  ef = Math.max(1.3, ef);

  let reps = cur.reps + 1;
  let interval; // 天数
  if (reps === 1) {
    interval = 1;
  } else if (reps === 2) {
    interval = 6;
  } else {
    interval = Math.round(cur.interval * ef);
  }

  return {
    ef,
    interval,
    reps,
    dueAt: Date.now() + interval * 86400 * 1000,
  };
};

// 是否到期可复习
export const isDue = (state) => {
  if (!state) return true;
  return Date.now() >= state.dueAt;
};

// localStorage 持久化
const STORAGE_KEY = 'flashcards_progress_v1';

export const loadProgress = () => {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
};
export const saveProgress = (data) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ignore
  }
};

// 取某卡的状态；不存在则返回新卡状态
export const getCardState = (cardId) => {
  const all = loadProgress();
  return all[cardId] || newCardState();
};
export const setCardState = (cardId, state) => {
  const all = loadProgress();
  all[cardId] = state;
  saveProgress(all);
  try {
    window.dispatchEvent(new CustomEvent('flashcards-change'));
  } catch {
    // ignore
  }
};

// 工具：从一组卡片里筛出今天要复习的（含未学过的新卡）
export const filterDueCards = (cards) => {
  const all = loadProgress();
  const due = [];
  const newCards = [];
  for (const c of cards) {
    const st = all[c.id];
    if (!st) {
      newCards.push(c);
    } else if (Date.now() >= st.dueAt) {
      due.push(c);
    }
  }
  // 优先到期复习（巩固已学的），再上新卡
  return { due, newCards, total: due.length + newCards.length };
};

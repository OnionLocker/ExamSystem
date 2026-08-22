// ============================================================
// 错因归类：把"你错了"变成"你为什么错"
// ------------------------------------------------------------
// 光看正确率没法指导训练 —— 89% 正确率背后可能是"进位老是漏"，
// 也可能是"1/13 和 1/14 记混了"，这两种要练的东西完全不同。
// 用户答案和正确答案的差值本身就带着诊断信息，白扔可惜。
//
// 判定只用两个数字，不看题面：够用，而且对所有生成器一视同仁。
// ============================================================

export const ERROR_KINDS = {
  carry: {
    label: '进位借位',
    color: '#ef4444',
    hint: '结果差整 10 / 整 100，是进位或借位漏了、多了。练「补数与滚加」最对症。',
  },
  confuse: {
    label: '记忆混淆',
    color: '#a855f7',
    hint: '答案和正确值只差一点，属于把相邻的两个值记串了，要成对对比着背。',
  },
  unit: {
    label: '个位偏差',
    color: '#f59e0b',
    hint: '只差 1，通常是末位加减看花了眼，放慢半拍复核末位即可。',
  },
  typo: {
    label: '手滑输错',
    color: '#94a3b8',
    hint: '多按或少按了一位，不是算错。这类不该算进能力评估。',
  },
  skipped: { label: '跳过', color: '#cbd5e1', hint: '没有作答。' },
  other: {
    label: '算错了',
    color: '#0ea5e9',
    hint: '结果偏离较大，是真算错或思路走偏，建议放慢速度重做一遍。',
  },
};

// 手滑：多按或少按一位，剩下的数字序列还是对的
const looksLikeTypo = (userStr, ansStr) => {
  if (userStr.length === ansStr.length) return false;
  const [long, short] = userStr.length > ansStr.length ? [userStr, ansStr] : [ansStr, userStr];
  if (long.length - short.length !== 1) return false;
  return long.startsWith(short) || long.endsWith(short);
};

/**
 * @param {string|number|null} userAnswer 用户输入，null 表示跳过
 * @param {number} answer 正确答案
 * @returns {{ code: string, label: string, color: string, hint: string }}
 */
export const classifyError = (userAnswer, answer) => {
  const wrap = (code) => ({ code, ...ERROR_KINDS[code] });

  if (userAnswer == null || userAnswer === '') return wrap('skipped');
  const user = Number(userAnswer);
  if (Number.isNaN(user)) return wrap('other');

  if (looksLikeTypo(String(userAnswer).replace('-', ''), String(answer).replace('-', ''))) {
    return wrap('typo');
  }

  const diff = Math.abs(user - answer);
  // 判错但数值相等：容差题的边界情况，不做归因
  if (diff === 0) return wrap('other');

  // 差整 10 的倍数 = 进位链上出了问题，这是最常见也最可训练的一类
  if (diff >= 10 && diff % 10 === 0) return wrap('carry');

  // 答案本身是小数字的题（分母、乘法表这类），差一点是记串了而不是算错
  if (Math.abs(answer) < 100) return wrap('confuse');

  if (diff === 1) return wrap('unit');
  return wrap('other');
};

/**
 * 把一场 records 聚合成错因分布，按数量降序。
 * @returns {Array<{ code, label, color, hint, count, pct }>}
 */
export const summarizeErrors = (records = []) => {
  const wrong = records.filter((r) => !r.isCorrect);
  if (wrong.length === 0) return [];

  const acc = {};
  for (const r of wrong) {
    const kind = r.skipped ? 'skipped' : classifyError(r.userAnswer, r.answer).code;
    acc[kind] = (acc[kind] || 0) + 1;
  }

  return Object.entries(acc)
    .map(([code, count]) => ({
      code,
      ...ERROR_KINDS[code],
      count,
      pct: Math.round((count / wrong.length) * 100),
    }))
    .sort((a, b) => b.count - a.count);
};

/**
 * 跨多场历史的错因分布，给首页诊断用。
 * @param {Array} history numeric_practice_history_v1 的内容
 */
export const summarizeHistoryErrors = (history = []) => {
  const all = [];
  for (const s of history) {
    if (Array.isArray(s.records)) all.push(...s.records);
  }
  return summarizeErrors(all);
};

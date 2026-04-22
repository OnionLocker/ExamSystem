// ---------------- 题目生成器 ----------------
// 每个生成器返回 { prompt, answer, displayAnswer?, tolerance? }
// - prompt: 题干字符串
// - answer: 标准答案（数字）
// - tolerance: 可选，允许的误差（如估算/资料分析）
// - displayAnswer: 可选，用于显示"正确答案"时的格式化函数

const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const round1 = (n) => Math.round(n * 10) / 10;

export const generators = {
  // -------- 基本计算 --------
  add3: () => {
    const a = rand(100, 999);
    const b = rand(100, 999);
    return { prompt: `${a} + ${b} =`, answer: a + b };
  },
  sub3: () => {
    const a = rand(200, 999);
    const b = rand(100, a);
    return { prompt: `${a} − ${b} =`, answer: a - b };
  },
  addsub3: () => {
    // 三位数加减混合：a ± b ± c（保证结果 ≥ 0）
    let a = rand(100, 999);
    let b = rand(100, 999);
    let c = rand(100, 999);
    const op1 = pick(['+', '-']);
    const op2 = pick(['+', '-']);
    // 确保不出现负数结果
    let step1 = op1 === '+' ? a + b : a - b;
    if (step1 < 0) {
      [a, b] = [b, a];
      step1 = op1 === '+' ? a + b : a - b;
    }
    let final = op2 === '+' ? step1 + c : step1 - c;
    if (final < 0) {
      c = rand(0, step1);
      final = op2 === '+' ? step1 + c : step1 - c;
    }
    const sign1 = op1 === '+' ? '+' : '−';
    const sign2 = op2 === '+' ? '+' : '−';
    return { prompt: `${a} ${sign1} ${b} ${sign2} ${c} =`, answer: final };
  },
  add4: () => {
    const nums = Array.from({ length: 4 }, () => rand(100, 999));
    return {
      prompt: nums.join(' + ') + ' =',
      answer: nums.reduce((a, b) => a + b, 0),
    };
  },
  mul3x1: () => {
    const a = rand(100, 999);
    const b = rand(2, 9);
    return { prompt: `${a} × ${b} =`, answer: a * b };
  },
  div3by1: () => {
    const b = rand(2, 9);
    const q = rand(100, 999);
    const a = q * b;
    return { prompt: `${a} ÷ ${b} =`, answer: q };
  },
  mul2x2: () => {
    const a = rand(11, 99);
    const b = rand(11, 99);
    return { prompt: `${a} × ${b} =`, answer: a * b };
  },
  big99: () => {
    const a = rand(11, 19);
    const b = rand(11, 19);
    return { prompt: `${a} × ${b} =`, answer: a * b };
  },
  mulEst: () => {
    // 乘法估算：三位数 × 三位数，答案取整到千位，允许 ±2% 误差
    const a = rand(120, 980);
    const b = rand(120, 980);
    const exact = a * b;
    return {
      prompt: `${a} × ${b} ≈ ?（估算，误差 ±2%）`,
      answer: exact,
      tolerance: Math.max(1000, exact * 0.02),
      displayAnswer: (n) => `${n}（精确值，范围 ${Math.round(exact * 0.98)} ~ ${Math.round(exact * 1.02)}）`,
    };
  },
  div5by3: () => {
    // 五位数 ÷ 三位数：整除版本
    const b = rand(100, 999);
    const q = rand(10, 99);
    const a = q * b;
    // 保证 a 为五位数
    if (a < 10000) {
      const factor = Math.ceil(10000 / a);
      return {
        prompt: `${a * factor} ÷ ${b * factor} =`,
        answer: q,
      };
    }
    return { prompt: `${a} ÷ ${b} =`, answer: q };
  },

  // -------- 资料分析公式 --------
  baseQty: () => {
    // 基期量 = 现期量 / (1 + r)
    const current = round1(rand(1000, 99999) / 10);
    const rPct = round1(rand(5, 300) / 10);
    const base = current / (1 + rPct / 100);
    const ans = round1(base);
    return {
      prompt: `现期量 ${current}，同比增长 ${rPct}%，求基期量（保留 1 位小数）=`,
      answer: ans,
      tolerance: 0.3,
    };
  },
  growthAmt: () => {
    // 增长量 = 现期量 × r / (1 + r)
    const current = round1(rand(1000, 99999) / 10);
    const rPct = round1(rand(5, 400) / 10);
    const g = (current * (rPct / 100)) / (1 + rPct / 100);
    const ans = round1(g);
    return {
      prompt: `现期量 ${current}，同比增长 ${rPct}%，求增长量（保留 1 位小数）=`,
      answer: ans,
      tolerance: 0.3,
    };
  },
};

// ---------------- 分类 / 子分类结构 ----------------
export const CATEGORIES = [
  {
    id: 'basic',
    name: '基本计算',
    desc: '训练最基本的加减乘除，打好数资基础',
    available: true,
    subs: [
      { id: 'add3', name: '三位数加法', gen: 'add3' },
      { id: 'sub3', name: '三位数减法', gen: 'sub3' },
      { id: 'addsub3', name: '三位数加减', gen: 'addsub3' },
      { id: 'add4', name: '四数相加', gen: 'add4' },
      { id: 'mul3x1', name: '三位数乘一位数', gen: 'mul3x1' },
      { id: 'div3by1', name: '三位数除一位数', gen: 'div3by1' },
      { id: 'mul2x2', name: '两位数乘两位数', gen: 'mul2x2' },
      { id: 'big99', name: '大九九乘法表', gen: 'big99' },
      { id: 'mulEst', name: '乘法估算', gen: 'mulEst' },
      { id: 'div5by3', name: '五位数除三位数', gen: 'div5by3' },
      { id: 'baseQty', name: '求基期量', gen: 'baseQty' },
      { id: 'growthAmt', name: '求增长量', gen: 'growthAmt' },
    ],
  },
  {
    id: 'aux',
    name: '计算辅助',
    desc: '提供计算练习的辅助针对性训练',
    available: false,
    subs: [],
  },
  {
    id: 'quant',
    name: '数量关系专项',
    desc: '通过大量训练提高数字的敏感性',
    available: false,
    subs: [],
  },
  {
    id: 'data',
    name: '资料分析专项',
    desc: '提供实际做题中常用公式的专项练习',
    available: false,
    subs: [],
  },
];

export const getCategory = (id) => CATEGORIES.find((c) => c.id === id);
export const getSub = (catId, subId) => {
  const cat = getCategory(catId);
  return cat?.subs.find((s) => s.id === subId);
};
export const generate = (genKey) => generators[genKey]();

// ---------------- 判题 ----------------
// 返回是否正确
export const judge = (question, userInput) => {
  if (userInput === '' || userInput == null) return false;
  const n = Number(userInput);
  if (Number.isNaN(n)) return false;
  const tol = question.tolerance ?? 0;
  return Math.abs(n - question.answer) <= tol;
};

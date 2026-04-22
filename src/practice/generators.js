// ---------------- 题目生成器 ----------------
// 每个生成器返回 { prompt, answer, displayAnswer?, tolerance? }
// - prompt: 题干字符串
// - answer: 标准答案（数字）
// - tolerance: 可选，允许的误差（如估算/资料分析）
// - displayAnswer: 可选，用于显示"正确答案"时的格式化函数

const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const round1 = (n) => Math.round(n * 10) / 10;
const round2 = (n) => Math.round(n * 100) / 100;
const gcd = (a, b) => (b === 0 ? a : gcd(b, a % b));
const lcm = (a, b) => (a * b) / gcd(a, b);

// 常见分数 ↔ 小数 ↔ 百分数 对照表（资料分析常用，非"百化分"专用）
const FRAC_TABLE = [
  { num: 1, den: 2, dec: 0.5, pct: 50 },
  { num: 1, den: 3, dec: 0.333, pct: 33.3 },
  { num: 2, den: 3, dec: 0.667, pct: 66.7 },
  { num: 1, den: 4, dec: 0.25, pct: 25 },
  { num: 3, den: 4, dec: 0.75, pct: 75 },
  { num: 1, den: 5, dec: 0.2, pct: 20 },
  { num: 2, den: 5, dec: 0.4, pct: 40 },
  { num: 3, den: 5, dec: 0.6, pct: 60 },
  { num: 4, den: 5, dec: 0.8, pct: 80 },
  { num: 1, den: 6, dec: 0.167, pct: 16.7 },
  { num: 5, den: 6, dec: 0.833, pct: 83.3 },
  { num: 1, den: 7, dec: 0.143, pct: 14.3 },
  { num: 2, den: 7, dec: 0.286, pct: 28.6 },
  { num: 3, den: 7, dec: 0.429, pct: 42.9 },
  { num: 1, den: 8, dec: 0.125, pct: 12.5 },
  { num: 3, den: 8, dec: 0.375, pct: 37.5 },
  { num: 5, den: 8, dec: 0.625, pct: 62.5 },
  { num: 7, den: 8, dec: 0.875, pct: 87.5 },
  { num: 1, den: 9, dec: 0.111, pct: 11.1 },
  { num: 2, den: 9, dec: 0.222, pct: 22.2 },
  { num: 1, den: 11, dec: 0.091, pct: 9.1 },
  { num: 1, den: 12, dec: 0.083, pct: 8.3 },
  { num: 1, den: 13, dec: 0.077, pct: 7.7 },
];

// 百化分固定专用：1/3 ~ 1/19 的分数对照表
// 百分比保留 1 位小数（用于背诵与做题判题）
export const BAI_HUA_FEN_TABLE = (() => {
  const list = [];
  for (let d = 3; d <= 19; d++) {
    const dec = 1 / d;
    list.push({
      num: 1,
      den: d,
      dec: Math.round(dec * 100) / 100, // 小数保留 2 位（内部使用）
      pct: Math.round(dec * 100 * 10) / 10, // 百分比保留 1 位
    });
  }
  return list;
})();

// 常见平方数对照表：11² ~ 29²（背诵用）
export const SQUARE_TABLE = (() => {
  const list = [];
  for (let n = 11; n <= 29; n++) {
    list.push({ n, sq: n * n });
  }
  return list;
})();

export const generators = {
  // ======================================================================
  // 基本计算（basic）
  // ======================================================================
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
    let a = rand(100, 999);
    let b = rand(100, 999);
    let c = rand(100, 999);
    const op1 = pick(['+', '-']);
    const op2 = pick(['+', '-']);
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
    const a = rand(120, 980);
    const b = rand(120, 980);
    const exact = a * b;
    return {
      prompt: `${a} × ${b} ≈ ?（估算，误差 ±2%）`,
      answer: exact,
      tolerance: Math.max(1000, exact * 0.02),
      displayAnswer: (n) =>
        `${n}（精确值，范围 ${Math.round(exact * 0.98)} ~ ${Math.round(exact * 1.02)}）`,
    };
  },
  div5by3: () => {
    const b = rand(100, 999);
    const q = rand(10, 99);
    const a = q * b;
    if (a < 10000) {
      const factor = Math.ceil(10000 / a);
      return { prompt: `${a * factor} ÷ ${b * factor} =`, answer: q };
    }
    return { prompt: `${a} ÷ ${b} =`, answer: q };
  },

  // ======================================================================
  // 计算辅助（aux）
  // ======================================================================
  // 进位加法：一位数 + 一位数，必须进位（结果 ≥ 10）
  carryAdd: () => {
    let a, b;
    do {
      a = rand(2, 9);
      b = rand(2, 9);
    } while (a + b < 10);
    return { prompt: `${a} + ${b} =`, answer: a + b };
  },
  // 退位减法：两位数（十几~十几）− 一位数，必须退位（被减数个位 < 减数）
  borrowSub: () => {
    let a, b;
    do {
      a = rand(11, 18);
      b = rand(2, 9);
    } while (a % 10 >= b); // 要求个位不够减，必须退位
    return { prompt: `${a} − ${b} =`, answer: a - b };
  },
  // 2-9 的乘法（两位数 × 一位数，一位因子固定）
  mulBy: (n) => () => {
    const a = rand(10, 99);
    return { prompt: `${a} × ${n} =`, answer: a * n };
  },
  mulBy2: null, // 占位，下面统一赋值
  mulBy3: null,
  mulBy4: null,
  mulBy5: null,
  mulBy6: null,
  mulBy9: null,
  // 两位数 × 11（尾首相加法）
  mulBy11: () => {
    const a = rand(10, 99);
    return { prompt: `${a} × 11 =`, answer: a * 11 };
  },
  // 两位数 × 15
  mulBy15: () => {
    const a = rand(10, 99);
    return { prompt: `${a} × 15 =`, answer: a * 15 };
  },
  // 分数化小数：如 3/8 = ? 保留 3 位
  fracToDec: () => {
    const f = pick(FRAC_TABLE);
    return {
      prompt: `${f.num}/${f.den} ≈ ?（小数，保留 3 位）`,
      answer: f.dec,
      tolerance: 0.005,
      displayAnswer: (n) => n.toString(),
    };
  },
  // 小数化分数（给小数，回答分母）
  decToFrac: () => {
    const f = pick(FRAC_TABLE);
    return {
      prompt: `${f.dec.toFixed(3)} ≈ ${f.num}/? `,
      answer: f.den,
    };
  },
  // 百化分（固定）：给百分比，回答分数（分母 3~19）
  pctToFrac: () => {
    const f = pick(BAI_HUA_FEN_TABLE);
    return {
      prompt: `${f.pct}% ≈ 1/?`,
      answer: f.den,
    };
  },
  // 分化百（固定）：给分数，回答百分比
  fracToPct: () => {
    const f = pick(FRAC_TABLE);
    return {
      prompt: `${f.num}/${f.den} ≈ ?%（保留 1 位小数）`,
      answer: f.pct,
      tolerance: 0.3,
    };
  },
  // 百化分估算：给任意 % 数（不在表里），估算到最近的常见分数（只答分母）
  pctToFracEst: () => {
    // 取常见分数对应的百分比，加个 ±2% 扰动
    const f = pick(FRAC_TABLE.filter((x) => x.num === 1));
    const noise = rand(-20, 20) / 10; // ±2%
    const pct = round1(f.pct + noise);
    return {
      prompt: `${pct}% ≈ 1/?（填最接近的整数分母）`,
      answer: f.den,
    };
  },
  // 常见平方数：11~29（与对照表一致）
  square: () => {
    const n = rand(11, 29);
    return { prompt: `${n}² =`, answer: n * n };
  },

  // ======================================================================
  // 数量关系（quant）
  // ======================================================================
  // 比例表达式：a:b = c:x，求 x（整除）
  ratio: () => {
    const k = rand(2, 12);
    const a = rand(2, 9);
    const b = rand(2, 9);
    const c = a * k;
    const x = b * k;
    return { prompt: `${a} : ${b} = ${c} : ? `, answer: x };
  },
  // 工程问题：甲 a 天、乙 b 天，合作几天？
  engineering: () => {
    const choices = [
      [6, 3], [6, 4], [8, 4], [10, 6], [12, 6], [12, 8], [10, 15], [20, 30],
      [6, 12], [8, 24], [15, 10],
    ];
    const [a, b] = pick(choices);
    const t = (a * b) / (a + b);
    return {
      prompt: `一项工程甲单独 ${a} 天、乙单独 ${b} 天，合作需要几天？（保留 1 位小数）`,
      answer: round1(t),
      tolerance: 0.1,
    };
  },
  // 均值不等式：a + b = S，求 a·b 的最大值（当 a=b=S/2）
  amgm: () => {
    const half = rand(4, 30);
    const S = 2 * half;
    const maxProd = half * half;
    return {
      prompt: `已知 a + b = ${S}（a,b > 0），求 ab 的最大值 =`,
      answer: maxProd,
    };
  },
  // 韩信点兵：除以 p 余 r1，除以 q 余 r2，求最小正整数
  hanxin: () => {
    // 取两个互素的小模，0~m-1 内的随机余数
    const pairs = [[3, 5], [3, 7], [4, 5], [4, 7], [5, 7], [5, 8], [3, 8], [5, 9]];
    const [p, q] = pick(pairs);
    const r1 = rand(0, p - 1);
    const r2 = rand(0, q - 1);
    // 暴力找最小正整数
    let ans = null;
    for (let n = 1; n < p * q * 2; n++) {
      if (n % p === r1 && n % q === r2) {
        ans = n;
        break;
      }
    }
    return {
      prompt: `一个数除以 ${p} 余 ${r1}，除以 ${q} 余 ${r2}，求最小正整数 =`,
      answer: ans,
    };
  },
  // 不定方程：a·x + b·y = c，x,y 为正整数，给出 x 值之一（通常只有一个解）
  diophantine: () => {
    // 构造：选 a,b 互素且不大，给定 x0,y0 生成 c，但要求解唯一
    let a, b, x, y, c;
    // 选 a,b 使得 c 的范围不大，但在正整数范围内只有一个解
    const tryGen = () => {
      a = rand(3, 9);
      b = rand(3, 9);
      if (gcd(a, b) !== 1 || a === b) return false;
      x = rand(1, 10);
      y = rand(1, 10);
      c = a * x + b * y;
      // 数出所有正整数解
      const sols = [];
      for (let i = 1; i * a < c; i++) {
        const rest = c - a * i;
        if (rest > 0 && rest % b === 0) sols.push([i, rest / b]);
      }
      return sols.length === 1;
    };
    for (let i = 0; i < 50; i++) if (tryGen()) break;
    return {
      prompt: `${a}x + ${b}y = ${c}（x, y 均为正整数），求 x =`,
      answer: x,
    };
  },
  // 最大公约数
  gcdQ: () => {
    const a = rand(20, 200);
    const b = rand(20, 200);
    return { prompt: `gcd(${a}, ${b}) =`, answer: gcd(a, b) };
  },
  // 最小公倍数
  lcmQ: () => {
    const a = rand(4, 30);
    const b = rand(4, 30);
    return { prompt: `lcm(${a}, ${b}) =`, answer: lcm(a, b) };
  },
  // 星期日期：某一天是周 X，过 N 天是周几？（答 1~7，周日=7）
  weekday: () => {
    const w = rand(1, 7); // 当前周几
    const days = rand(8, 365);
    const wName = ['一', '二', '三', '四', '五', '六', '日'];
    let ans = ((w - 1 + days) % 7) + 1;
    return {
      prompt: `今天是周${wName[w - 1]}，再过 ${days} 天是周几？（周一=1, 周日=7）`,
      answer: ans,
    };
  },

  // ======================================================================
  // 资料分析（data）
  // ======================================================================
  // 基期量粗算 = 现期量 / (1 + r)，保留整数
  baseQtyRough: () => {
    const current = rand(1000, 99999);
    const rPct = round1(rand(5, 300) / 10);
    const base = current / (1 + rPct / 100);
    return {
      prompt: `现期 ${current}，同比增长 ${rPct}%，基期 ≈ ?（保留整数，误差 ±1%）`,
      answer: Math.round(base),
      tolerance: Math.max(5, base * 0.01),
    };
  },
  // 基期量精算 = 现期量 / (1 + r)，保留 1 位小数
  baseQtyExact: () => {
    const current = round1(rand(1000, 99999) / 10);
    const rPct = round1(rand(5, 300) / 10);
    const base = current / (1 + rPct / 100);
    return {
      prompt: `现期 ${current}，同比增长 ${rPct}%，基期 =（保留 1 位小数）`,
      answer: round1(base),
      tolerance: 0.3,
    };
  },
  // 增长量 = 现期 × r / (1 + r)
  growthAmt: () => {
    const current = round1(rand(1000, 99999) / 10);
    const rPct = round1(rand(5, 400) / 10);
    const g = (current * (rPct / 100)) / (1 + rPct / 100);
    return {
      prompt: `现期 ${current}，同比增长 ${rPct}%，增长量 =（保留 1 位小数）`,
      answer: round1(g),
      tolerance: 0.3,
    };
  },
  // 增长率 = (现期 - 基期) / 基期
  growthRate: () => {
    const base = rand(500, 9999);
    const curr = Math.round(base * (1 + rand(-30, 60) / 100));
    const r = ((curr - base) / base) * 100;
    return {
      prompt: `基期 ${base}，现期 ${curr}，增长率 ≈ ?%（保留 1 位小数）`,
      answer: round1(r),
      tolerance: 0.15,
    };
  },
  // 基期差（两期差值的基期差）：A基=a, B基=b, A现=a', B现=b'，求 (a'-b') - (a-b)
  baseDiff: () => {
    const a = rand(500, 9999);
    const b = rand(500, 9999);
    const aCurr = Math.round(a * (1 + rand(-20, 50) / 100));
    const bCurr = Math.round(b * (1 + rand(-20, 50) / 100));
    const diff = (aCurr - bCurr) - (a - b);
    return {
      prompt: `A 基期 ${a}，现期 ${aCurr}；B 基期 ${b}，现期 ${bCurr}。现期差 − 基期差 =`,
      answer: diff,
    };
  },
  // 乘积增长率 = r1 + r2 + r1·r2 / 100
  prodGrowth: () => {
    const r1 = round1(rand(10, 300) / 10);
    const r2 = round1(rand(10, 300) / 10);
    const r = r1 + r2 + (r1 * r2) / 100;
    return {
      prompt: `A 增长 ${r1}%，B 增长 ${r2}%，则 A×B 增长 ≈ ?%（保留 1 位小数）`,
      answer: round1(r),
      tolerance: 0.15,
    };
  },
  // 除式增长率（两率相除）= (r1 - r2) / (1 + r2)
  divGrowth: () => {
    const r1 = round1(rand(10, 300) / 10);
    const r2 = round1(rand(10, 300) / 10);
    const r = ((r1 - r2) / (1 + r2 / 100));
    return {
      prompt: `A 增长 ${r1}%，B 增长 ${r2}%，则 A/B 增长 ≈ ?%（保留 1 位小数）`,
      answer: round1(r),
      tolerance: 0.25,
    };
  },
  // 平均数增长率 = (r_总 - r_个) / (1 + r_个)
  avgGrowth: () => {
    const rTot = round1(rand(30, 300) / 10);
    const rItem = round1(rand(10, 200) / 10);
    const r = (rTot - rItem) / (1 + rItem / 100);
    return {
      prompt: `总量增长 ${rTot}%，个体数增长 ${rItem}%，则平均数增长 ≈ ?%（保留 1 位小数）`,
      answer: round1(r),
      tolerance: 0.25,
    };
  },
  // 基期比重 = 现期比重 × (1 + r总) / (1 + r部)
  baseRatio: () => {
    const ratioNow = round1(rand(100, 800) / 10); // 现期比重 %
    const rPart = round1(rand(10, 300) / 10);
    const rTot = round1(rand(10, 300) / 10);
    const baseR = ratioNow * (1 + rTot / 100) / (1 + rPart / 100);
    return {
      prompt: `现期部分占 ${ratioNow}%，部分增长 ${rPart}%，整体增长 ${rTot}%，基期占比 ≈ ?%（保留 1 位小数）`,
      answer: round1(baseR),
      tolerance: 0.3,
    };
  },
  // 两期比重差 = 现期比重 × (r部 - r总) / (1 + r部)
  ratioDiff: () => {
    const ratioNow = round1(rand(100, 800) / 10);
    const rPart = round1(rand(10, 300) / 10);
    const rTot = round1(rand(10, 300) / 10);
    const diff = ratioNow * ((rPart - rTot) / 100) / (1 + rPart / 100);
    return {
      prompt: `现期部分占 ${ratioNow}%，部分增长 ${rPart}%，整体增长 ${rTot}%，现期比重 − 基期比重 ≈ ?（百分点，保留 2 位小数）`,
      answer: round2(diff),
      tolerance: 0.12,
    };
  },
  // 年均增长率 ≈ (末期/基期)^(1/n) - 1；常用近似：(r_总)/n - n(n-1)/2 ·(r/n)²（这里用精确公式）
  annualGrowth: () => {
    const years = rand(2, 5);
    const r0 = rand(10, 80) / 100;
    const base = 100;
    const end = round2(base * Math.pow(1 + r0, years));
    const ans = Math.pow(end / base, 1 / years) - 1;
    return {
      prompt: `${years} 年前为 ${base}，现在为 ${end}，年均增长率 ≈ ?%（保留 1 位小数）`,
      answer: round1(ans * 100),
      tolerance: 0.3,
    };
  },
  // 拉动增长率 = 部分增长量 / 整体基期
  pullGrowth: () => {
    const partBase = rand(100, 5000);
    const partCurr = Math.round(partBase * (1 + rand(10, 60) / 100));
    const totBase = rand(partBase * 3, partBase * 10);
    const pull = ((partCurr - partBase) / totBase) * 100;
    return {
      prompt: `部分基期 ${partBase}，现期 ${partCurr}，整体基期 ${totBase}，部分拉动整体 ≈ ?%（保留 2 位小数）`,
      answer: round2(pull),
      tolerance: 0.1,
    };
  },
  // 贡献率 = 部分增长量 / 整体增长量
  contribute: () => {
    const partG = rand(100, 2000);
    const totG = rand(partG + 100, partG * 5);
    const c = (partG / totG) * 100;
    return {
      prompt: `部分增长量 ${partG}，整体增长量 ${totG}，贡献率 ≈ ?%（保留 1 位小数）`,
      answer: round1(c),
      tolerance: 0.2,
    };
  },
};

// 动态生成 mulByN（避免重复代码）
[2, 3, 4, 5, 6, 9].forEach((n) => {
  generators[`mulBy${n}`] = () => {
    const a = rand(10, 99);
    return { prompt: `${a} × ${n} =`, answer: a * n };
  };
});

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
    ],
  },
  {
    id: 'aux',
    name: '计算辅助',
    desc: '提供计算练习的辅助针对性训练',
    available: true,
    subs: [
      { id: 'carryAdd', name: '进位加法', gen: 'carryAdd' },
      { id: 'borrowSub', name: '退位减法', gen: 'borrowSub' },
      { id: 'mulBy2', name: '2 的乘法', gen: 'mulBy2' },
      { id: 'mulBy3', name: '3 的乘法', gen: 'mulBy3' },
      { id: 'mulBy4', name: '4 的乘法', gen: 'mulBy4' },
      { id: 'mulBy5', name: '5 的乘法', gen: 'mulBy5' },
      { id: 'mulBy6', name: '6 的乘法', gen: 'mulBy6' },
      { id: 'mulBy9', name: '9 的乘法', gen: 'mulBy9' },
      { id: 'mulBy11', name: '两位数乘 11', gen: 'mulBy11' },
      { id: 'mulBy15', name: '两位数乘 15', gen: 'mulBy15' },
      { id: 'fracToDec', name: '分数化小数', gen: 'fracToDec' },
      { id: 'decToFrac', name: '小数化分数', gen: 'decToFrac' },
      { id: 'pctToFrac', name: '百化分固定', gen: 'pctToFrac' },
      { id: 'fracToPct', name: '分化百固定', gen: 'fracToPct' },
      { id: 'pctToFracEst', name: '百化分估算', gen: 'pctToFracEst' },
      { id: 'square', name: '常见平方数', gen: 'square' },
    ],
  },
  {
    id: 'quant',
    name: '数量关系专项',
    desc: '通过大量训练提高数字的敏感性',
    available: true,
    subs: [
      { id: 'ratio', name: '比例表达式', gen: 'ratio' },
      { id: 'engineering', name: '工程问题', gen: 'engineering' },
      { id: 'amgm', name: '均值不等式', gen: 'amgm' },
      { id: 'hanxin', name: '韩信点兵', gen: 'hanxin' },
      { id: 'diophantine', name: '不定方程', gen: 'diophantine' },
      { id: 'gcdQ', name: '最大公约数', gen: 'gcdQ' },
      { id: 'lcmQ', name: '最小公倍数', gen: 'lcmQ' },
      { id: 'weekday', name: '星期日期问题', gen: 'weekday' },
    ],
  },
  {
    id: 'data',
    name: '资料分析专项',
    desc: '提供实际做题中常用公式的专项练习',
    available: true,
    subs: [
      { id: 'baseQtyRough', name: '基期量（粗算）', gen: 'baseQtyRough' },
      { id: 'baseQtyExact', name: '基期量（精算）', gen: 'baseQtyExact' },
      { id: 'growthAmt', name: '增长量', gen: 'growthAmt' },
      { id: 'growthRate', name: '增长率', gen: 'growthRate' },
      { id: 'baseDiff', name: '基期差', gen: 'baseDiff' },
      { id: 'prodGrowth', name: '乘积增长率', gen: 'prodGrowth' },
      { id: 'divGrowth', name: '除式增长率', gen: 'divGrowth' },
      { id: 'avgGrowth', name: '平均数增长率', gen: 'avgGrowth' },
      { id: 'baseRatio', name: '基期比重', gen: 'baseRatio' },
      { id: 'ratioDiff', name: '两期比重差', gen: 'ratioDiff' },
      { id: 'pullGrowth', name: '拉动增长率', gen: 'pullGrowth' },
      { id: 'contribute', name: '贡献率', gen: 'contribute' },
      { id: 'annualGrowth', name: '年均增长率', gen: 'annualGrowth' },
    ],
  },
];

export const getCategory = (id) => CATEGORIES.find((c) => c.id === id);
export const getSub = (catId, subId) => {
  const cat = getCategory(catId);
  return cat?.subs.find((s) => s.id === subId);
};
export const generate = (genKey) => generators[genKey]();

// ---------------- 判题 ----------------
export const judge = (question, userInput) => {
  if (userInput === '' || userInput == null) return false;
  const n = Number(userInput);
  if (Number.isNaN(n)) return false;
  const tol = question.tolerance ?? 0;
  return Math.abs(n - question.answer) <= tol;
};

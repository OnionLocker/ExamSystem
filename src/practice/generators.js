import { READ_SPOT_GENERATORS, READ_SPOT_CATEGORY } from './readSpot.js';

// ---------------- 题目生成器 ----------------
// 每个生成器返回 { prompt, answer, displayAnswer?, tolerance?, answerKind? }
// - prompt: 题干字符串
// - answer: 标准答案（数字，或分数串如 3/8）
// - answerKind: 'frac' 时按最简分数/比判题
// - tolerance: 可选，允许的误差（如估算/资料分析）
// - displayAnswer: 可选，用于显示"正确答案"时的格式化函数

const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const round1 = (n) => Math.round(n * 10) / 10;
const round2 = (n) => Math.round(n * 100) / 100;
const gcd = (a, b) => (b === 0 ? a : gcd(b, a % b));
const lcm = (a, b) => (a * b) / gcd(a, b);

const shuffle = (arr) => {
  const out = arr.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = rand(0, i);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
};

const parseFrac = (s) => {
  const t = String(s).trim().replace(/\s/g, '').replace(/：/g, ':').replace(/／/g, '/');
  const m = t.match(/^(-?\d+)[/:](-?\d+)$/);
  if (!m) return null;
  const a = Number(m[1]);
  const b = Number(m[2]);
  if (!b) return null;
  const g = gcd(Math.abs(a), Math.abs(b));
  const sign = (a < 0) !== (b < 0) ? -1 : 1;
  return [sign * (Math.abs(a) / g), Math.abs(b) / g];
};

const fracEqual = (a, b) => {
  const pa = parseFrac(a);
  const pb = parseFrac(b);
  if (pa && pb) return pa[0] === pb[0] && pa[1] === pb[1];
  return String(a).trim() === String(b).trim();
};

const simplifyFrac = (num, den) => {
  const g = gcd(Math.abs(num), Math.abs(den));
  const n = num / g;
  const d = den / g;
  return d < 0 ? `${-n}/${-d}` : `${n}/${d}`;
};

const seqPrompt = (terms) => `数列：${terms.join('、')}、？  求下一项`;

// 审计 CUT：UI / 九宫格 / 弱项填充均不可见，生成器保留
export const NUMERIC_CUT_SUB_IDS = new Set([
  'carryAdd', 'borrowSub',
  'mulBy2', 'mulBy3', 'mulBy4', 'mulBy5', 'mulBy6',
  'spotLogic', 'spotVerbal',
  'amgm', 'hanxin', 'gcdQ', 'lcmQ', 'weekday',
  'chickenRabbit', 'planting', 'squareFormation',
]);

export const isSubAvailable = (sub) => Boolean(sub) && sub.available !== false;
export const visibleSubs = (cat) => (cat?.subs || []).filter(isSubAvailable);

// 给乘/除速算题统一加误差容忍：默认 ±1%，最少 ±1
// pctMin=0.01 表示 1%，floor=1 表示最少 ±1
const withTol = ({ prompt, answer }, pctMin = 0.01, floor = 1) => {
  const tol = Math.max(floor, Math.round(Math.abs(answer) * pctMin));
  // 题面尾部追加"允许误差 ±X"，避免歧义
  const tagged = `${prompt}（速算：允许误差 ±${tol}）`;
  return {
    prompt: tagged,
    answer,
    tolerance: tol,
    displayAnswer: (n) => `${n}（精确值，允许 ${answer - tol} ~ ${answer + tol}）`,
  };
};

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
  // 三位数加减（两数）：a + b 或 a - b，二选一
  addOrSub3: () => {
    const op = pick(['+', '-']);
    if (op === '+') {
      const a = rand(100, 999);
      const b = rand(100, 999);
      return { prompt: `${a} + ${b} =`, answer: a + b };
    }
    const a = rand(200, 999);
    const b = rand(100, a);
    return { prompt: `${a} − ${b} =`, answer: a - b };
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
    return withTol({ prompt: `${a} × ${b} =`, answer: a * b });
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
    return withTol({ prompt: `${a} × ${b} =`, answer: a * b });
  },
  big99: () => {
    const a = rand(11, 19);
    const b = rand(11, 19);
    return withTol({ prompt: `${a} × ${b} =`, answer: a * b });
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
      return withTol({ prompt: `${a * factor} ÷ ${b * factor} =`, answer: q });
    }
    return withTol({ prompt: `${a} ÷ ${b} =`, answer: q });
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
    return withTol({ prompt: `${a} × ${n} =`, answer: a * n });
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
    return withTol({ prompt: `${a} × 11 =`, answer: a * 11 });
  },
  // 两位数 × 15
  mulBy15: () => {
    const a = rand(10, 99);
    return withTol({ prompt: `${a} × 15 =`, answer: a * 15 });
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
  // 小数化最简分数（如 0.375 → 3/8）
  decToFrac: () => {
    const f = pick(FRAC_TABLE);
    const g = gcd(f.num, f.den);
    const num = f.num / g;
    const den = f.den / g;
    return {
      prompt: `把 ${f.dec.toFixed(3)} 化成最简分数`,
      answer: `${num}/${den}`,
      answerKind: 'frac',
      displayAnswer: () => `${num}/${den}`,
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
  // 百化分估算：给任意 % 数（不在表里），估算到最近的整数分母
  pctToFracEst: () => {
    // 取单位分数百分比再加 ±2% 扰动；答案必须按扰动后的 pct 重算，
    // 不能仍用种子分母（否则会像 9.2% 误标成 12，正确应为 11）
    const f = pick(FRAC_TABLE.filter((x) => x.num === 1));
    const noise = rand(-20, 20) / 10; // ±2%
    const pct = Math.max(0.1, round1(f.pct + noise));
    const den = Math.max(2, Math.round(100 / pct));
    return {
      prompt: `${pct}% ≈ 1/?（填最接近的整数分母）`,
      answer: den,
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
  // 比例应用：过滤 a=b、未约分/过整倍数废题
  ratio: () => {
    let a;
    let b;
    let k;
    do {
      a = rand(2, 12);
      b = rand(2, 12);
      k = rand(3, 16);
    } while (a === b || gcd(a, b) !== 1 || k === a || k === b);
    const scenes = [
      () => ({
        prompt: `甲乙投资比为 ${a}:${b}，乙投资 ${b * k} 万，甲投资多少万？`,
        answer: a * k,
      }),
      () => ({
        prompt: `一笔资金按 ${a}:${b} 分给甲乙两人，总额 ${(a + b) * k} 元，甲分得多少元？`,
        answer: a * k,
      }),
      () => ({
        prompt: `溶液中溶质与溶剂之比为 ${a}:${b}，溶剂 ${b * k} 克，溶质多少克？`,
        answer: a * k,
      }),
      () => ({
        prompt: `甲乙两地到丙地的路程比为 ${a}:${b}。甲地到丙地 ${a * k} 千米，乙地到丙地多少千米？`,
        answer: b * k,
      }),
    ];
    return pick(scenes)();
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
  // 不定方程：应用包装，不裸写 ax+by=c
  diophantine: () => {
    let a;
    let b;
    let x;
    let y;
    let c;
    const tryGen = () => {
      a = rand(3, 9);
      b = rand(3, 9);
      if (gcd(a, b) !== 1 || a === b) return false;
      x = rand(1, 10);
      y = rand(1, 10);
      c = a * x + b * y;
      const sols = [];
      for (let i = 1; i * a < c; i += 1) {
        const rest = c - a * i;
        if (rest > 0 && rest % b === 0) sols.push([i, rest / b]);
      }
      return sols.length === 1;
    };
    for (let i = 0; i < 50; i += 1) if (tryGen()) break;
    const wraps = [
      `钢笔每支 ${a} 元、本子每本 ${b} 元，一共花了 ${c} 元，两种都买了至少 1 件，钢笔买了几支？`,
      `成人票 ${a} 元、儿童票 ${b} 元，一笔收入共 ${c} 元，两种票都卖出至少 1 张，成人票几张？`,
      `大瓶饮料 ${a} 元、小瓶 ${b} 元，共花 ${c} 元，两种都买了至少 1 瓶，大瓶买了几瓶？`,
      `甲每天做 ${a} 件、乙每天做 ${b} 件，若干天后共完成 ${c} 件（两人开工天数均为正整数），甲做了几天？`,
    ];
    return { prompt: pick(wraps), answer: x };
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
  // ----- 行程问题 -----
  // 相遇问题：甲乙相向而行，初始相距 d 米，速度 va, vb（米/秒），求相遇时间（秒，保留 1 位小数）
  encounter: () => {
    const va = rand(3, 12);
    const vb = rand(3, 12);
    const t = rand(8, 60);
    const d = (va + vb) * t;
    return {
      prompt: `甲乙两人相向而行，初始相距 ${d} 米，甲速 ${va} 米/秒，乙速 ${vb} 米/秒，几秒后相遇？`,
      answer: t,
      tolerance: 0.5,
    };
  },
  // 追及问题：甲在前，乙在后，相距 d 米，乙快 va > vb，几秒追上
  pursue: () => {
    const vb = rand(3, 8);
    const diff = rand(2, 6);
    const va = vb + diff;
    const t = rand(10, 60);
    const d = (va - vb) * t;
    return {
      prompt: `甲在前乙在后相距 ${d} 米，甲速 ${vb} 米/秒，乙速 ${va} 米/秒（同向追击），几秒后乙追上甲？`,
      answer: t,
      tolerance: 0.5,
    };
  },
  // 流水行船：船静水速 v，水流速 w（v>w），顺水/逆水走 d 千米需多久（小时，保留 1 位）
  boat: () => {
    const v = rand(10, 30);
    const w = rand(2, Math.max(3, Math.floor(v / 3)));
    const direction = pick(['顺', '逆']);
    const speed = direction === '顺' ? v + w : v - w;
    const t = rand(2, 8);
    const d = speed * t;
    return {
      prompt: `船在静水中速度 ${v} 千米/小时，水流速度 ${w} 千米/小时，${direction}水行驶 ${d} 千米需要几小时？（保留 1 位）`,
      answer: round1(t),
      tolerance: 0.15,
    };
  },
  // ----- 浓度问题 -----
  // 浓度混合：m_a 克 a%，m_b 克 b%，混合后浓度（保留 1 位小数）
  mixture: () => {
    const ma = rand(50, 300);
    const mb = rand(50, 300);
    const ca = rand(5, 30);
    const cb = rand(5, 30);
    const c = (ma * ca + mb * cb) / (ma + mb);
    return {
      prompt: `${ma} 克 ${ca}% 的盐水与 ${mb} 克 ${cb}% 的盐水混合，新浓度 ≈ ?%（保留 1 位小数）`,
      answer: round1(c),
      tolerance: 0.15,
    };
  },
  // 浓度稀释：m 克 c% 的盐水加 w 克水，新浓度
  dilute: () => {
    const m = rand(100, 500);
    const c = rand(8, 40);
    const w = rand(50, 300);
    const newC = (m * c) / (m + w);
    return {
      prompt: `${m} 克 ${c}% 的盐水中加入 ${w} 克水，新浓度 ≈ ?%（保留 1 位小数）`,
      answer: round1(newC),
      tolerance: 0.15,
    };
  },
  // ----- 集合容斥 -----
  // 两集合：总人数 n，喜欢 A 的 a 人，喜欢 B 的 b 人，都不喜欢 z 人，问 A∩B
  inclusion2: () => {
    const n = rand(40, 100);
    const both = rand(5, 20);
    const onlyA = rand(8, 30);
    const onlyB = rand(8, 30);
    const z = n - both - onlyA - onlyB;
    if (z < 0) {
      // 兜底：重新构造一个保证非负的
      const n2 = onlyA + onlyB + both + rand(3, 15);
      const a = onlyA + both;
      const b = onlyB + both;
      const z2 = n2 - both - onlyA - onlyB;
      return {
        prompt: `班上 ${n2} 人，喜欢数学的 ${a} 人，喜欢英语的 ${b} 人，都不喜欢的 ${z2} 人，两科都喜欢多少人？`,
        answer: both,
      };
    }
    const a = onlyA + both;
    const b = onlyB + both;
    return {
      prompt: `班上 ${n} 人，喜欢数学的 ${a} 人，喜欢英语的 ${b} 人，都不喜欢的 ${z} 人，两科都喜欢多少人？`,
      answer: both,
    };
  },
  // ----- 排列组合（应用场景） -----
  permutation: () => {
    const n = rand(5, 9);
    const k = rand(2, Math.min(4, n));
    let ans = 1;
    for (let i = 0; i < k; i += 1) ans *= n - i;
    const scenes = [
      `从 ${n} 名选手中选 ${k} 人站成一排合影，有多少种排法？`,
      `${n} 本不同的书要选 ${k} 本按顺序排上书架，有多少种排法？`,
      `${n} 人中挑 ${k} 人按先后顺序领奖，有多少种排法？`,
    ];
    return { prompt: pick(scenes), answer: ans };
  },
  combination: () => {
    const n = rand(5, 10);
    const k = rand(2, Math.min(4, n - 1));
    let num = 1;
    let den = 1;
    for (let i = 0; i < k; i += 1) {
      num *= n - i;
      den *= i + 1;
    }
    const scenes = [
      `从 ${n} 本书中选 ${k} 本，有多少种选法？`,
      `${n} 人中选 ${k} 人组成小组，有多少种选法？`,
      `从 ${n} 道菜里点 ${k} 道（不分先后），有多少种点法？`,
    ];
    return { prompt: pick(scenes), answer: num / den };
  },
  // 古典概型：不考「只取一个」；答案用最简分数
  probability: () => {
    const r = rand(3, 8);
    const w = rand(3, 8);
    const n = r + w;
    const mode = pick(['twoRed', 'oneEach', 'seqRW', 'atLeastOne']);
    if (mode === 'twoRed') {
      const num = r * (r - 1);
      const den = n * (n - 1);
      return {
        prompt: `袋中 ${r} 个红球、${w} 个白球，不放回连取 2 个，两球都是红球的概率是多少？（最简分数）`,
        answer: simplifyFrac(num, den),
        answerKind: 'frac',
        displayAnswer: () => simplifyFrac(num, den),
      };
    }
    if (mode === 'oneEach') {
      const num = 2 * r * w;
      const den = n * (n - 1);
      return {
        prompt: `袋中 ${r} 个红球、${w} 个白球，不放回连取 2 个，恰好一红一白的概率是多少？（最简分数）`,
        answer: simplifyFrac(num, den),
        answerKind: 'frac',
        displayAnswer: () => simplifyFrac(num, den),
      };
    }
    if (mode === 'seqRW') {
      const num = r * w;
      const den = n * (n - 1);
      return {
        prompt: `袋中 ${r} 个红球、${w} 个白球，不放回依次取 2 个，先红后白的概率是多少？（最简分数）`,
        answer: simplifyFrac(num, den),
        answerKind: 'frac',
        displayAnswer: () => simplifyFrac(num, den),
      };
    }
    const noneRed = w * (w - 1);
    const den = n * (n - 1);
    const num = den - noneRed;
    return {
      prompt: `袋中 ${r} 个红球、${w} 个白球，不放回连取 2 个，至少有 1 个红球的概率是多少？（最简分数）`,
      answer: simplifyFrac(num, den),
      answerKind: 'frac',
      displayAnswer: () => simplifyFrac(num, den),
    };
  },
  // ----- 鸡兔同笼 -----
  // 头共 h 个，脚共 f 只，求兔子数
  chickenRabbit: () => {
    const rabbits = rand(3, 25);
    const chickens = rand(3, 25);
    const h = rabbits + chickens;
    const f = rabbits * 4 + chickens * 2;
    return {
      prompt: `鸡兔同笼，共 ${h} 个头 ${f} 只脚，问兔子有几只？`,
      answer: rabbits,
    };
  },
  // ----- 年龄问题 -----
  // 当前父年龄 P，子 S（P=k*S 或 P-S 已知）；几年后父是子 m 倍
  age: () => {
    // 现在父子年龄差 d 不变；m 年后父是子的 k 倍
    const childNow = rand(5, 12);
    const k = rand(2, 5);
    const dadNow = childNow * (k + rand(1, 3)); // 现在父>k倍
    const targetK = rand(2, k);
    // 几年后父是子的 targetK 倍：dadNow + y = targetK * (childNow + y) → y = (dadNow - targetK*childNow) / (targetK - 1)
    const y = (dadNow - targetK * childNow) / (targetK - 1);
    if (!Number.isInteger(y) || y <= 0) {
      // 兜底：重新生成（少见情况）
      const y2 = rand(3, 10);
      const newDad = dadNow + y2;
      const newChild = childNow + y2;
      const ratio = newDad / newChild;
      return {
        prompt: `父亲今年 ${dadNow} 岁，儿子今年 ${childNow} 岁，${y2} 年后父亲年龄是儿子的几倍？（保留 1 位小数）`,
        answer: round1(ratio),
        tolerance: 0.1,
      };
    }
    return {
      prompt: `父亲今年 ${dadNow} 岁，儿子今年 ${childNow} 岁，几年后父亲年龄是儿子的 ${targetK} 倍？`,
      answer: y,
    };
  },
  // ----- 盈亏问题 -----
  // n 个人分东西：每人发 a 个剩 m 个，每人发 b 个少 n_short 个，求人数
  profit: () => {
    const people = rand(5, 30);
    const a = rand(3, 8);
    const b = a + rand(1, 4);
    const total = people * a + rand(2, 15); // 每人 a 个剩 m 个
    const m = total - people * a;
    const shortage = people * b - total;
    if (shortage <= 0) {
      // 兜底：相同 a 不变，更大的 b
      const b2 = a + Math.ceil((m + 5) / people);
      const sh2 = people * b2 - total;
      return {
        prompt: `若每人发 ${a} 个则剩余 ${m} 个，若每人发 ${b2} 个则缺 ${sh2} 个，共有几人？`,
        answer: people,
      };
    }
    return {
      prompt: `若每人发 ${a} 个则剩余 ${m} 个，若每人发 ${b} 个则缺 ${shortage} 个，共有几人？`,
      answer: people,
    };
  },
  // ----- 植树问题 -----
  // 一条 L 米的路两端都栽，每隔 d 米栽一棵，需要几棵？答 = L/d + 1
  planting: () => {
    const d = pick([2, 3, 4, 5, 6, 8, 10]);
    const k = rand(8, 30);
    const L = d * k;
    const mode = pick(['两端都栽', '两端都不栽', '环形']);
    let ans;
    if (mode === '两端都栽') ans = k + 1;
    else if (mode === '两端都不栽') ans = k - 1;
    else ans = k;
    return {
      prompt: `一条 ${L} 米的${mode === '环形' ? '环形跑道' : '道路'}，每隔 ${d} 米栽一棵树（${mode}），共需几棵？`,
      answer: ans,
    };
  },
  // ----- 方阵问题 -----
  // 方阵：实心 n×n 共 n² 人；空心方阵外层 = 4(n-1)；总人数 = n² - (n-2k)² (k 为层数)
  squareFormation: () => {
    const n = rand(5, 25);
    const mode = pick(['solid', 'outer', 'twoLayer']);
    if (mode === 'solid') {
      return {
        prompt: `${n} × ${n} 实心方阵共有几人？`,
        answer: n * n,
      };
    }
    if (mode === 'outer') {
      return {
        prompt: `${n} × ${n} 方阵的最外层共有几人？`,
        answer: 4 * (n - 1),
      };
    }
    // 双层：外两层人数
    const inner = Math.max(1, n - 4);
    return {
      prompt: `${n} × ${n} 方阵的最外两层共有几人？`,
      answer: n * n - inner * inner,
    };
  },

  // ======================================================================
  // 数字推理（numReason）—— 只给数列，不写规律
  // 变式含隔项、分数、多重修正（广东常见），禁止题干剧透
  // ======================================================================
  arithSeq: () => {
    const a0 = rand(1, 30);
    const d = pick([2, 3, 4, 5, 6, 7, -3, -4, -5]);
    const seq = Array.from({ length: 5 }, (_, i) => a0 + d * i);
    return { prompt: seqPrompt(seq), answer: a0 + d * 5 };
  },
  geoSeq: () => {
    const a0 = pick([1, 2, 3, 4, 5, 6]);
    const q = pick([2, 3, -2]);
    const seq = Array.from({ length: 5 }, (_, i) => a0 * Math.pow(q, i));
    return { prompt: seqPrompt(seq), answer: a0 * Math.pow(q, 5) };
  },
  sumSeq: () => {
    const mode = pick(['fib', 'triple', 'plusC', 'skip']);
    if (mode === 'skip') {
      const o0 = rand(1, 8);
      const od = pick([2, 3, 4, 5]);
      const e0 = rand(2, 12);
      const ed = pick([2, 3, 4, 5, 6]);
      const seq = [];
      for (let i = 0; i < 6; i += 1) {
        seq.push(i % 2 === 0 ? o0 + od * (i / 2) : e0 + ed * ((i - 1) / 2));
      }
      return { prompt: seqPrompt(seq), answer: o0 + od * 3 };
    }
    if (mode === 'triple') {
      const seq = [rand(1, 5), rand(1, 5), rand(1, 5)];
      for (let i = 3; i < 6; i += 1) seq.push(seq[i - 1] + seq[i - 2] + seq[i - 3]);
      return { prompt: seqPrompt(seq.slice(0, 5)), answer: seq[5] };
    }
    if (mode === 'plusC') {
      const c = pick([1, 2, 3, -1]);
      const seq = [rand(1, 6), rand(1, 6)];
      for (let i = 2; i < 6; i += 1) seq.push(seq[i - 1] + seq[i - 2] + c);
      return { prompt: seqPrompt(seq.slice(0, 5)), answer: seq[5] };
    }
    const seq = [rand(1, 8), rand(1, 8)];
    for (let i = 2; i < 6; i += 1) seq.push(seq[i - 1] + seq[i - 2]);
    return { prompt: seqPrompt(seq.slice(0, 5)), answer: seq[5] };
  },
  productSeq: () => {
    const mode = pick(['pair', 'timesN', 'skip']);
    if (mode === 'timesN') {
      const seq = [pick([1, 2, 3])];
      for (let i = 1; i < 5; i += 1) seq.push(seq[i - 1] * (i + 1));
      return { prompt: seqPrompt(seq), answer: seq[4] * 6 };
    }
    if (mode === 'skip') {
      const o0 = pick([1, 2]);
      const e0 = pick([1, 2, 3]);
      const eq = pick([2, 3]);
      const seq = [];
      for (let i = 0; i < 6; i += 1) {
        seq.push(i % 2 === 0 ? o0 * (2 ** (i / 2)) : e0 * (eq ** ((i - 1) / 2)));
      }
      return { prompt: seqPrompt(seq), answer: o0 * (2 ** 3) };
    }
    const seq = [pick([1, 2, 2, 3]), pick([1, 2, 2, 3])];
    for (let i = 2; i < 5; i += 1) seq.push(seq[i - 1] * seq[i - 2]);
    return { prompt: seqPrompt(seq.slice(0, 4)), answer: seq[3] * seq[4] };
  },
  powerSeq: () => {
    const mode = pick(['n2c', 'n3c', 'n2n', 'fracDen', 'fracFib']);
    if (mode === 'fracDen') {
      const start = rand(2, 4);
      const shown = Array.from({ length: 4 }, (_, i) => `1/${(start + i) ** 2}`);
      const nextDen = (start + 4) ** 2;
      return {
        prompt: `${seqPrompt(shown)}（最简分数）`,
        answer: `1/${nextDen}`,
        answerKind: 'frac',
        displayAnswer: () => `1/${nextDen}`,
      };
    }
    if (mode === 'fracFib') {
      const fib = [1, 2, 3, 5, 8, 13];
      const shown = Array.from({ length: 4 }, (_, i) => `${fib[i]}/${fib[i + 1]}`);
      return {
        prompt: `${seqPrompt(shown)}（最简分数）`,
        answer: `${fib[4]}/${fib[5]}`,
        answerKind: 'frac',
        displayAnswer: () => `${fib[4]}/${fib[5]}`,
      };
    }
    if (mode === 'n2n') {
      const start = rand(2, 5);
      const sign = pick([1, -1]);
      const seq = Array.from({ length: 5 }, (_, i) => {
        const n = start + i;
        return n * n + sign * n;
      });
      const n = start + 5;
      return { prompt: seqPrompt(seq), answer: n * n + sign * n };
    }
    const power = mode === 'n3c' ? 3 : 2;
    const start = rand(1, 4);
    const c = rand(-3, 3);
    const seq = Array.from({ length: 5 }, (_, i) => (start + i) ** power + c);
    return { prompt: seqPrompt(seq), answer: (start + 5) ** power + c };
  },
  multiArith: () => {
    const mode = pick(['second', 'skip', 'third']);
    if (mode === 'skip') {
      const a0 = rand(1, 10);
      const da = rand(2, 6);
      const b0 = rand(1, 10);
      const db = rand(2, 6);
      const seq = [];
      for (let i = 0; i < 6; i += 1) {
        seq.push(i % 2 === 0 ? a0 + da * (i / 2) : b0 + db * ((i - 1) / 2));
      }
      return { prompt: seqPrompt(seq), answer: a0 + da * 3 };
    }
    if (mode === 'third') {
      const seq = [rand(1, 8)];
      let d = rand(1, 4);
      let e = rand(1, 3);
      const f = rand(1, 2);
      for (let i = 1; i < 6; i += 1) {
        seq.push(seq[i - 1] + d);
        d += e;
        e += f;
      }
      return { prompt: seqPrompt(seq.slice(0, 5)), answer: seq[5] };
    }
    const seq = [rand(1, 10)];
    let curD = rand(1, 5);
    const dd = rand(1, 4);
    for (let i = 1; i < 6; i += 1) {
      seq.push(seq[i - 1] + curD);
      curD += dd;
    }
    return { prompt: seqPrompt(seq.slice(0, 5)), answer: seq[5] };
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
  // 基期差：资料实战包装（进出口/产值差额的两年变化）
  baseDiff: () => {
    const a = rand(500, 9999);
    const b = rand(500, 9999);
    const aCurr = Math.round(a * (1 + rand(-20, 50) / 100));
    const bCurr = Math.round(b * (1 + rand(-20, 50) / 100));
    const diff = (aCurr - bCurr) - (a - b);
    const y0 = rand(2020, 2024);
    return {
      prompt: `${y0} 年甲进口 ${a}、乙出口 ${b}；${y0 + 1} 年甲进口 ${aCurr}、乙出口 ${bCurr}。甲减乙的差额比上年增加多少？`,
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
  // 年均增长率：资料年份口径 + 总增速/年数略下调的近似口诀
  annualGrowth: () => {
    const years = rand(2, 5);
    const r0 = rand(10, 80) / 100;
    const base = 100;
    const end = round2(base * Math.pow(1 + r0, years));
    const ans = Math.pow(end / base, 1 / years) - 1;
    const y0 = rand(2018, 2022);
    const totalPct = round1(end - base);
    return {
      prompt:
        `${y0} 年末某指标为 ${base}，${y0 + years} 年末为 ${end}（间隔 ${years} 年）。` +
        `年均增长率 ≈ ?%（保留 1 位小数；口诀：总增速约 ${totalPct}%，${years} 年年均略低于 ${totalPct}/${years}）`,
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
  // 混合增长率：按基期量加权（资料口径，不是现期份额）
  mixedGrowth: () => {
    const mode = pick(['share', 'qty']);
    const r1 = round1(rand(10, 200) / 10);
    const r2 = round1(rand(10, 200) / 10);
    if (mode === 'qty') {
      const baseA = rand(200, 900) * 10;
      const baseB = rand(200, 900) * 10;
      const r = (baseA * r1 + baseB * r2) / (baseA + baseB);
      return {
        prompt:
          `部分 A 基期 ${baseA}、增速 ${r1}%；部分 B 基期 ${baseB}、增速 ${r2}%。` +
          `总体增速（按基期量加权）≈ ?%（保留 1 位小数）`,
        answer: round1(r),
        tolerance: 0.2,
      };
    }
    const wA = rand(20, 80);
    const wB = 100 - wA;
    const r = (wA * r1 + wB * r2) / 100;
    return {
      prompt:
        `A、B 基期量分别占总量 ${wA}%、${wB}%，增速分别为 ${r1}%、${r2}%。` +
        `总体增速（按基期量加权）≈ ?%（保留 1 位小数）`,
      answer: round1(r),
      tolerance: 0.2,
    };
  },
  // 倍数关系辨析：A=300, B=100 → A 是 B 的 3 倍 / A 比 B 多 2 倍
  // 题目随机问"是几倍"或"多几倍"，考查辨析
  multipleOf: () => {
    const small = rand(50, 500);
    const k = rand(2, 9);
    const big = small * k;
    const mode = pick(['是几倍', '多几倍']);
    return {
      prompt: `${big} ${mode} ${small}？`,
      answer: mode === '是几倍' ? k : k - 1,
    };
  },
  // 百分点辨析：从 a% 涨到 b%，是涨了 (b-a) 个百分点；相对涨幅 = (b-a)/a 这是百分比
  // 这道题考"是百分点还是百分比"
  percentagePoint: () => {
    const a = round1(rand(20, 200) / 10);
    const delta = round1(rand(10, 80) / 10);
    const b = round1(a + delta);
    const mode = pick(['百分点', '百分比']);
    let answer, prompt;
    if (mode === '百分点') {
      answer = round1(b - a);
      prompt = `某指标从 ${a}% 上升到 ${b}%，涨了几个百分点？（保留 1 位小数）`;
    } else {
      answer = round1(((b - a) / a) * 100);
      prompt = `某指标从 ${a}% 上升到 ${b}%，相对涨幅 ≈ ?%（保留 1 位小数）`;
    }
    return { prompt, answer, tolerance: 0.15 };
  },
  // ======================================================================
  // 补数与滚加（speedOps）—— 行测实战心算路径
  // ======================================================================
  // 100 以内补数闪电：给 X∈[11,99]，答 100−X
  complement100: () => {
    const x = rand(11, 99);
    return {
      prompt: `${x} 的百补数（100 − ${x}）=`,
      answer: 100 - x,
    };
  },
  // 三位数凑整多减加回：强制产生退位感的减法，解析给补数路径
  subComplement3: () => {
    // 被减数；减数凑到「整百」后需加回补数
    const minuend = rand(320, 980);
    // 减数取「个位≥5 或 十位偏大」的三位数，且 < 被减数
    let subtrahend;
    let rounded;
    let complement;
    do {
      const hundreds = rand(1, Math.floor((minuend - 30) / 100));
      const tens = rand(5, 9);
      const ones = rand(5, 9);
      subtrahend = hundreds * 100 + tens * 10 + ones;
      rounded = Math.ceil(subtrahend / 100) * 100; // 向上凑整百
      complement = rounded - subtrahend; // 多减了就要加回
    } while (subtrahend >= minuend || complement === 0 || rounded - minuend > 200);

    const answer = minuend - subtrahend;
    // 路径：A − B = A − round(B) + (round(B)−B)
    const path = `${minuend} − ${rounded} + ${complement} = ${answer}`;
    return {
      prompt: `${minuend} − ${subtrahend} =`,
      answer,
      displayAnswer: () => `${answer}（凑整：${path}）`,
      hint: `凑整：${path}`,
    };
  },
  // 高位滚加：2~3 个三位数，提示从高位往低位加；答案正常读数输入即可
  rollingAdd3: () => {
    const n = pick([2, 3]);
    const nums = Array.from({ length: n }, () => rand(108, 897));
    return {
      prompt: `${nums.join(' + ')} =（高位→低位滚加）`,
      answer: nums.reduce((a, b) => a + b, 0),
    };
  },

  // ======================================================================
  // 资料分析·实战秒杀定性（dataKill）
  // 选项一律回填 1~4；对错看 answer 数字
  // ======================================================================
  // 增量比重 vs 现期比重：结论只看 a ? b
  growthShareEst: () => {
    const share = round1(rand(80, 750) / 10); // 现期比重 %
    let a = round1(rand(5, 350) / 10);
    let b = round1(rand(5, 350) / 10);
    // 偶尔相等，多数不相等
    if (rand(1, 10) === 1) b = a;
    else if (Math.abs(a - b) < 0.5) b = round1(a + pick([1.5, -1.5, 2.2, -2.2]));

    let rel; // 1更大 2更小 3相等
    if (a > b) rel = 1;
    else if (a < b) rel = 2;
    else rel = 3;

    const labels = ['更大', '更小', '相等', '无法判定'];
    return {
      prompt:
        `现期比重 ${share}%，部分增速 a=${a}%，整体增速 b=${b}%\n` +
        `增量比重 ΔA/ΔB 相对现期比重？\n` +
        `1)更大  2)更小  3)相等  4)无法判定`,
      answer: rel,
      displayAnswer: () =>
        `${rel}（${labels[rel - 1]}；口诀：a>b 则增量比重更大，a<b 更小，a=b 相等）`,
    };
  },
  // 两期比重差：升降看 a?b；|差| 必然 < |a−b| 个百分点
  twoPeriodRatioDiff: () => {
    let a = round1(rand(20, 400) / 10);
    let b = round1(rand(20, 400) / 10);
    if (Math.abs(a - b) < 1) b = round1(a + pick([2, -2, 3.5, -3.5]));
    const gap = round1(Math.abs(a - b));
    const rise = a > b;
    const correctText = rise
      ? `上升，且差值 < ${gap} 个百分点`
      : `下降，且差值 < ${gap} 个百分点`;
    const options = shuffle([
      `上升，且差值 < ${gap} 个百分点`,
      `上升，且差值可能 ≥ ${gap} 个百分点`,
      `下降，且差值 < ${gap} 个百分点`,
      `下降，且差值可能 ≥ ${gap} 个百分点`,
    ]);
    const answer = options.indexOf(correctText) + 1;
    return {
      prompt:
        `部分增速 a=${a}%，整体增速 b=${b}%\n` +
        `两期比重差（现期−基期）如何判定？\n` +
        options.map((t, i) => `${i + 1})${t}`).join('  '),
      answer,
      displayAnswer: () =>
        `${answer}（${correctText}；升降看 a?b，|差| 必然 < |a−b|=${gap} 个百分点）`,
    };
  },
  // 混合增长率线段法：部分 A 增速相对整体，定性另一部分 B
  mixtureRateEstimate: () => {
    const total = rand(200, 900) * 10; // 总量
    const shareA = rand(25, 75); // A 占总量 %
    const amtA = Math.round((total * shareA) / 100);
    const amtB = total - amtA;
    const r = round1(rand(20, 250) / 10); // 整体增速
    // A 增速刻意偏离整体，便于定性
    const delta = round1(pick([2, 3, 4, 5, 6, 8, 10]) * pick([1, -1]));
    const a = round1(Math.max(0.5, r + delta));
    // 线段法：A 在 r 一侧，则 B 必在另一侧
    let relB; // 1 B>r  2 B<r  3 B=r  4 无法判定
    if (a > r) relB = 2;
    else if (a < r) relB = 1;
    else relB = 3;

    // 精确 b 供解析（不要求学员算出）
    const bExact = round1((r * total - a * amtA) / amtB);

    const labels = ['大于整体', '小于整体', '等于整体', '无法判定'];
    return {
      prompt:
        `总量 ${total}（增速 ${r}%），其中 A=${amtA}（增速 ${a}%），其余为 B\n` +
        `B 的增速相对整体？\n` +
        `1)大于整体  2)小于整体  3)等于整体  4)无法判定`,
      answer: relB,
      displayAnswer: () =>
        `${relB}（${labels[relB - 1]}；线段法：A 在整体${a > r ? '上方' : a < r ? '下方' : '重合'}，则 B 在另一侧。B≈${bExact}%）`,
    };
  },
  ...READ_SPOT_GENERATORS,

};

// 动态生成 mulByN（避免重复代码）
[2, 3, 4, 5, 6, 9].forEach((n) => {
  generators[`mulBy${n}`] = () => {
    const a = rand(10, 99);
    return { prompt: `${a} × ${n} =`, answer: a * n };
  };
});

// ---------------- 分类 / 子分类结构 ----------------
// weight 1-5：子项在真实省考里的出题频率（5=每年必考，3=中频，1-2=偶尔/冷门）
// 分类的 weight 是百分比，4 个加起来 = 100，反映各类在真实考试里的分值占比
export const CATEGORIES = [
  {
    id: 'basic',
    name: '基本计算',
    desc: '训练最基本的加减乘除，打好数资基础',
    available: true,
    weight: 10, // 是技能基础，不是考点；段位整体权重低
    subs: [
      { id: 'add3', name: '三位数加法', gen: 'add3', weight: 3 },
      { id: 'sub3', name: '三位数减法', gen: 'sub3', weight: 3 },
      { id: 'addOrSub3', name: '三位数加减（两数）', gen: 'addOrSub3', weight: 3 },
      { id: 'addsub3', name: '三数加减（混合）', gen: 'addsub3', weight: 3 },
      { id: 'add4', name: '四数相加', gen: 'add4', weight: 3 },
      { id: 'mul3x1', name: '三位数乘一位数', gen: 'mul3x1', weight: 4 },
      { id: 'div3by1', name: '三位数除一位数', gen: 'div3by1', weight: 4 },
      { id: 'mul2x2', name: '两位数乘两位数', gen: 'mul2x2', weight: 4 },
      { id: 'big99', name: '大九九乘法表', gen: 'big99', weight: 3 },
      { id: 'mulEst', name: '乘法估算', gen: 'mulEst', weight: 3 },
      { id: 'div5by3', name: '五位数除三位数', gen: 'div5by3', weight: 3 },
    ],
  },
  {
    id: 'aux',
    name: '计算辅助',
    desc: '提供计算练习的辅助针对性训练',
    available: true,
    weight: 15, // 工具类，部分（百化分）资料分析高频用
    subs: [
      { id: 'carryAdd', name: '进位加法', gen: 'carryAdd', weight: 2, available: false },
      { id: 'borrowSub', name: '退位减法', gen: 'borrowSub', weight: 2, available: false },
      { id: 'mulBy2', name: '2 的乘法', gen: 'mulBy2', weight: 2, available: false },
      { id: 'mulBy3', name: '3 的乘法', gen: 'mulBy3', weight: 2, available: false },
      { id: 'mulBy4', name: '4 的乘法', gen: 'mulBy4', weight: 2, available: false },
      { id: 'mulBy5', name: '5 的乘法', gen: 'mulBy5', weight: 2, available: false },
      { id: 'mulBy6', name: '6 的乘法', gen: 'mulBy6', weight: 2, available: false },
      { id: 'mulBy9', name: '9 的乘法', gen: 'mulBy9', weight: 2 },
      { id: 'mulBy11', name: '两位数乘 11', gen: 'mulBy11', weight: 3 },
      { id: 'mulBy15', name: '两位数乘 15', gen: 'mulBy15', weight: 3 },
      { id: 'fracToDec', name: '分数化小数', gen: 'fracToDec', weight: 3 },
      { id: 'decToFrac', name: '化成最简分数', gen: 'decToFrac', weight: 3 },
      { id: 'pctToFrac', name: '百化分固定', gen: 'pctToFrac', weight: 4 },
      { id: 'fracToPct', name: '分化百固定', gen: 'fracToPct', weight: 4 },
      { id: 'pctToFracEst', name: '百化分估算', gen: 'pctToFracEst', weight: 4 },
      { id: 'square', name: '常见平方数', gen: 'square', weight: 3 },
    ],
  },
  {
    id: 'speedOps',
    name: '补数与滚加',
    desc: '【补数与滚加】消灭借位：百补数闪电、凑整多减加回、高位滚加',
    available: true,
    weight: 12,
    tag: '补数与滚加',
    subs: [
      { id: 'complement100', name: '100以内补数闪电', gen: 'complement100', weight: 5 },
      { id: 'subComplement3', name: '三位数凑整多减加回', gen: 'subComplement3', weight: 5 },
      { id: 'rollingAdd3', name: '高位滚加（2~3个数）', gen: 'rollingAdd3', weight: 4 },
    ],
  },
  {
    id: 'dataKill',
    name: '秒杀定性',
    desc: '【秒杀定性】资料分析实战口诀：增量比重、两期比重差、混合增速线段法',
    available: true,
    weight: 18,
    tag: '秒杀定性',
    subs: [
      { id: 'growthShareEst', name: '增量比重放缩定性', gen: 'growthShareEst', weight: 5 },
      { id: 'twoPeriodRatioDiff', name: '两期比重差秒判定', gen: 'twoPeriodRatioDiff', weight: 5 },
      { id: 'mixtureRateEstimate', name: '混合增长率定性线段', gen: 'mixtureRateEstimate', weight: 5 },
    ],
  },
  READ_SPOT_CATEGORY,
  {
    id: 'quant',
    name: '数量关系专项',
    desc: '通过大量训练提高数字的敏感性',
    available: true,
    weight: 30, // 行测 15 题
    subs: [
      { id: 'ratio', name: '比例应用', gen: 'ratio', weight: 4 },
      { id: 'engineering', name: '工程问题', gen: 'engineering', weight: 3 },
      { id: 'amgm', name: '均值不等式', gen: 'amgm', weight: 2, available: false },
      { id: 'hanxin', name: '韩信点兵', gen: 'hanxin', weight: 2, available: false },
      { id: 'diophantine', name: '不定方程应用', gen: 'diophantine', weight: 3 },
      { id: 'gcdQ', name: '最大公约数', gen: 'gcdQ', weight: 2, available: false },
      { id: 'lcmQ', name: '最小公倍数', gen: 'lcmQ', weight: 2, available: false },
      { id: 'weekday', name: '星期日期问题', gen: 'weekday', weight: 3, available: false },
      { id: 'encounter', name: '行程·相遇', gen: 'encounter', weight: 5 },
      { id: 'pursue', name: '行程·追及', gen: 'pursue', weight: 5 },
      { id: 'boat', name: '行程·流水', gen: 'boat', weight: 3 },
      { id: 'mixture', name: '浓度·混合', gen: 'mixture', weight: 5 },
      { id: 'dilute', name: '浓度·稀释', gen: 'dilute', weight: 3 },
      { id: 'inclusion2', name: '两集合容斥', gen: 'inclusion2', weight: 5 },
      { id: 'permutation', name: '排列应用', gen: 'permutation', weight: 5 },
      { id: 'combination', name: '组合应用', gen: 'combination', weight: 5 },
      { id: 'probability', name: '概率应用', gen: 'probability', weight: 5 },
      { id: 'chickenRabbit', name: '鸡兔同笼', gen: 'chickenRabbit', weight: 3, available: false },
      { id: 'age', name: '年龄问题', gen: 'age', weight: 3 },
      { id: 'profit', name: '盈亏问题', gen: 'profit', weight: 3 },
      { id: 'planting', name: '植树问题', gen: 'planting', weight: 2, available: false },
      { id: 'squareFormation', name: '方阵问题', gen: 'squareFormation', weight: 2, available: false },
    ],
  },
  {
    id: 'numReason',
    name: '数字推理',
    desc: '广东省考行测必考 5 题，找数列规律',
    available: true,
    weight: 15, // 5 题数推，难度高、区分度大
    subs: [
      { id: 'arithSeq', name: '等差数列', gen: 'arithSeq', weight: 5 },
      { id: 'geoSeq', name: '等比数列', gen: 'geoSeq', weight: 5 },
      { id: 'sumSeq', name: '和数列（斐波那契式）', gen: 'sumSeq', weight: 4 },
      { id: 'productSeq', name: '积数列', gen: 'productSeq', weight: 3 },
      { id: 'powerSeq', name: '平方立方数列', gen: 'powerSeq', weight: 4 },
      { id: 'multiArith', name: '多级等差', gen: 'multiArith', weight: 5 },
    ],
  },
  {
    id: 'data',
    name: '资料分析专项',
    desc: '提供实际做题中常用公式的专项练习',
    available: true,
    weight: 30, // 行测 10 题资料分析，分值最重之一
    subs: [
      { id: 'baseQtyRough', name: '基期量（粗算）', gen: 'baseQtyRough', weight: 5 },
      { id: 'baseQtyExact', name: '基期量（精算）', gen: 'baseQtyExact', weight: 5 },
      { id: 'growthAmt', name: '增长量', gen: 'growthAmt', weight: 5 },
      { id: 'growthRate', name: '增长率', gen: 'growthRate', weight: 5 },
      { id: 'baseDiff', name: '基期差', gen: 'baseDiff', weight: 3 },
      { id: 'prodGrowth', name: '乘积增长率', gen: 'prodGrowth', weight: 4 },
      { id: 'divGrowth', name: '除式增长率', gen: 'divGrowth', weight: 3 },
      { id: 'avgGrowth', name: '平均数增长率', gen: 'avgGrowth', weight: 3 },
      { id: 'baseRatio', name: '基期比重', gen: 'baseRatio', weight: 4 },
      { id: 'ratioDiff', name: '两期比重差', gen: 'ratioDiff', weight: 4 },
      { id: 'pullGrowth', name: '拉动增长率', gen: 'pullGrowth', weight: 3 },
      { id: 'contribute', name: '贡献率', gen: 'contribute', weight: 4 },
      { id: 'annualGrowth', name: '年均增长率', gen: 'annualGrowth', weight: 3 },
      { id: 'mixedGrowth', name: '混合增长率', gen: 'mixedGrowth', weight: 3 },
      { id: 'multipleOf', name: '倍数辨析', gen: 'multipleOf', weight: 4 },
      { id: 'percentagePoint', name: '百分点辨析', gen: 'percentagePoint', weight: 4 },
    ],
  },

];

export const getCategory = (id) => CATEGORIES.find((c) => c.id === id);
export const getSub = (catId, subId) => {
  const cat = getCategory(catId);
  return cat?.subs.find((s) => s.id === subId);
};
export const isNumericPoolSub = (catId, subId) => {
  const cat = getCategory(catId);
  if (!cat?.available) return false;
  return isSubAvailable(getSub(catId, subId));
};
export const generate = (genKey) => generators[genKey]();

// ---------------- 判题 ----------------
export const judge = (question, userInput) => {
  if (userInput === '' || userInput == null) return false;
  const raw = String(userInput).trim();
  if (
    question.answerKind === 'frac'
    || (typeof question.answer === 'string' && /[/:]/.test(question.answer))
  ) {
    return fracEqual(raw, String(question.answer));
  }
  const n = Number(raw);
  if (Number.isNaN(n)) return false;
  const tol = question.tolerance ?? 0;
  return Math.abs(n - question.answer) <= tol;
};

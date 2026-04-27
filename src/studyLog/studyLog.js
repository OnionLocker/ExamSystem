// ============================================================
// 学习日志：统一记录所有"真的学了"的行为，用于打卡热力图
// ============================================================
// 记录来源：
//   1) 番茄钟完成（完整走完一个工作番茄，中途停止不计）
//   2) 数资练习完成冲刺（冲刺模式结束）
//   3) 手动导入套题（用户在"今日学习录入"里填）
//   4) 错题复盘（后续扩展）
//
// 每条记录结构：
// {
//   id: number,          // 时间戳 + 随机
//   ts: number,          // 发生时间
//   type: 'pomodoro' | 'numeric' | 'import' | 'review',
//   module?: string,     // 对 type=import/review 使用，如 '言语理解'
//   minutes?: number,    // 对 pomodoro 使用
//   count?: number,      // 题数
//   correct?: number,    // 正确题数（数资）
//   score: number,       // 本条贡献的学习分
// }

const LOG_KEY = 'study_log_v1';

export const MODULES = [
  { id: 'yanyu', name: '言语理解', defaultSize: 40, color: '#3b82f6' },
  { id: 'panduan', name: '判断推理', defaultSize: 40, color: '#a855f7' },
  { id: 'shuliang', name: '数量关系', defaultSize: 15, color: '#ec4899' },
  { id: 'ziliao', name: '资料分析', defaultSize: 20, color: '#f59e0b' },
  { id: 'changshi', name: '常识判断', defaultSize: 20, color: '#10b981' },
  { id: 'shenlun', name: '申论', defaultSize: 5, color: '#ef4444' }, // 篇数
  { id: 'zhenti', name: '真题整套', defaultSize: 135, color: '#1a1a1a' },
];

export const loadLog = () => {
  try {
    return JSON.parse(localStorage.getItem(LOG_KEY) || '[]');
  } catch {
    return [];
  }
};

const saveLog = (list) => {
  try {
    localStorage.setItem(LOG_KEY, JSON.stringify(list));
  } catch {
    // ignore
  }
};

// 对外增加一条记录（通用）
export const addEntry = (entry) => {
  const list = loadLog();
  const rec = {
    id: Date.now() + Math.floor(Math.random() * 1000),
    ts: Date.now(),
    ...entry,
  };
  list.unshift(rec);
  // 保留 3 年
  saveLog(list.slice(0, 10000));
  // 广播变化事件（同页面内 storage 事件不触发，用自定义事件）
  try {
    window.dispatchEvent(new CustomEvent('study-log-change'));
  } catch {
    // ignore
  }
  return rec;
};

// ---------------- 分数计算 ----------------
// 完整番茄钟：每分钟 1 分
export const scorePomodoro = (minutes) => Math.round(minutes);

// 数资练习冲刺：题数 * 0.3 + 正确率 * 0.1
// 举例：10 题 / 正确 8 → 3 + 80*0.1 = 11 分
export const scoreNumeric = (total, correct) => {
  if (!total) return 0;
  const acc = Math.round((correct / total) * 100);
  return Math.round(total * 0.3 + acc * 0.1);
};

// 导入套题 / 真题：每题 1.5 分（申论按篇 × 20 折算）
export const scoreImport = (module, count) => {
  if (!count) return 0;
  const perQ = module === 'shenlun' ? 20 : 1.5;
  return Math.round(count * perQ);
};

// 错题复盘：每题 0.5 分
export const scoreReview = (count) => Math.round((count || 0) * 0.5);

// ---------------- 聚合查询 ----------------
// 日期键：YYYY-MM-DD（按本地时区）
const pad = (n) => String(n).padStart(2, '0');
export const dayKey = (ts) => {
  const d = new Date(ts);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

// 返回 Map<dayKey, { score, minutes, entries: [...] }>
export const aggregateByDay = (log = loadLog()) => {
  const m = new Map();
  for (const r of log) {
    const k = dayKey(r.ts);
    if (!m.has(k)) {
      m.set(k, { score: 0, minutes: 0, entries: [] });
    }
    const d = m.get(k);
    d.score += r.score || 0;
    d.minutes += r.minutes || 0;
    d.entries.push(r);
  }
  return m;
};

// 获取最近 N 天的日期键列表（从今天向前）
export const recentDayKeys = (days) => {
  const keys = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    keys.push(dayKey(d.getTime()));
  }
  return keys;
};

// 按分数分级（热力图颜色）
// 0: 未打卡 | 1-8: 8 档递进（分数阈值下方）
export const scoreLevel = (s) => {
  if (!s) return 0;
  if (s <= 10) return 1;
  if (s <= 25) return 2;
  if (s <= 45) return 3;
  if (s <= 70) return 4;
  if (s <= 100) return 5;
  if (s <= 150) return 6;
  if (s <= 220) return 7;
  return 8;
};

// 本周/本日/本月汇总
export const summarize = (log = loadLog()) => {
  const byDay = aggregateByDay(log);
  const todayKey = dayKey(Date.now());
  const today = byDay.get(todayKey) || { score: 0, minutes: 0, entries: [] };

  const now = new Date();
  const weekDay = (now.getDay() + 6) % 7; // 周一=0
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - weekDay);
  monday.setHours(0, 0, 0, 0);
  const thisMonth = new Date(now.getFullYear(), now.getMonth(), 1).getTime();

  let weekScore = 0,
    weekMin = 0,
    weekDays = 0;
  let monthScore = 0,
    monthMin = 0,
    monthDays = 0;

  for (const [k, v] of byDay) {
    const [y, m, d] = k.split('-').map(Number);
    const ts = new Date(y, m - 1, d).getTime();
    if (ts >= monday.getTime()) {
      weekScore += v.score;
      weekMin += v.minutes;
      if (v.score > 0) weekDays += 1;
    }
    if (ts >= thisMonth) {
      monthScore += v.score;
      monthMin += v.minutes;
      if (v.score > 0) monthDays += 1;
    }
  }

  // 连续打卡天数（从今天往前算，连续有分数的天）
  let streak = 0;
  for (let i = 0; i < 365; i++) {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - i);
    const v = byDay.get(dayKey(d.getTime()));
    if (v && v.score > 0) {
      streak += 1;
    } else {
      break;
    }
  }

  return {
    today,
    weekScore,
    weekMin,
    weekDays,
    monthScore,
    monthMin,
    monthDays,
    streak,
    totalDays: byDay.size,
  };
};

// 清空（调试用）
export const clearLog = () => {
  saveLog([]);
  try {
    window.dispatchEvent(new CustomEvent('study-log-change'));
  } catch {
    // ignore
  }
};

// 填充演示数据：覆盖 N 天，展示所有档位颜色
// 不清空原有数据，只追加带 preview: true 标记的假条目
export const fillPreviewData = () => {
  const list = loadLog();
  const now = new Date();
  now.setHours(12, 0, 0, 0);
  // 档位 1-8 对应的分数（取阈值内的中位数，保证稳定落到目标档位）
  const scoresPerLevel = [5, 18, 35, 58, 85, 125, 185, 280];
  // 从今天往前倒 N 天 × 8 档，让近 2~3 个月都被铺满
  const N = 12; // 12 个周期 × 8 档 ≈ 96 天
  let preset = [];
  for (let cycle = 0; cycle < N; cycle++) {
    for (let lvl = 0; lvl < 8; lvl++) {
      const daysAgo = cycle * 8 + lvl;
      const d = new Date(now);
      d.setDate(d.getDate() - daysAgo);
      preset.push({
        id: Date.now() + Math.random() * 10000 + daysAgo,
        ts: d.getTime(),
        type: 'import',
        module: '演示数据',
        count: lvl + 1,
        score: scoresPerLevel[lvl],
        preview: true,
      });
    }
  }
  saveLog([...preset, ...list]);
  try {
    window.dispatchEvent(new CustomEvent('study-log-change'));
  } catch {
    // ignore
  }
};

// 清除预览数据（保留真实记录）
export const clearPreviewData = () => {
  const list = loadLog().filter((r) => !r.preview);
  saveLog(list);
  try {
    window.dispatchEvent(new CustomEvent('study-log-change'));
  } catch {
    // ignore
  }
};

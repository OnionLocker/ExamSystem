// ============================================================
// 学习日志：统一记录所有"真的学了"的行为，用于打卡热力图
// ============================================================
// 记录来源：
//   1) 番茄钟完成或停止（只计实际运行时段）
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
//   timeSegments?: [[number, number]], // 实测开始、结束时间戳
// }

import { cloudGet, cloudSet } from '../cloudStorage.js';
import { aggregateStudyTime, emptyStudyDay, studyDayKey } from './studyTime.js';

const LOG_KEY = 'study_log_v1';
const DIGEST_KEY = 'study_digest_v1';

export const loadDigest = () => cloudGet(DIGEST_KEY, {});

export const MODULES = [
  { id: 'yanyu', name: '言语理解', defaultSize: 40, color: '#3b82f6' },
  { id: 'panduan', name: '判断推理', defaultSize: 40, color: '#a855f7' },
  { id: 'shuliang', name: '数量关系', defaultSize: 15, color: '#ec4899' },
  { id: 'ziliao', name: '资料分析', defaultSize: 20, color: '#f59e0b' },
  { id: 'changshi', name: '常识判断', defaultSize: 20, color: '#10b981' },
  { id: 'shenlun', name: '申论', defaultSize: 5, color: '#ef4444' }, // 篇数
  { id: 'zhenti', name: '真题整套', defaultSize: 135, color: '#1a1a1a' },
];

// 各来源的显示标签与配色。打卡面板的今日明细、仪表盘的今日概览都用这一份，
// 加新来源时只改这里，两处 UI 自动跟上。
export const ENTRY_TYPES = {
  pomodoro: { label: '番茄钟', color: '#ff6b6b' },
  numeric: { label: '数资练习', color: '#8d7348' },
  aiquiz: { label: 'AI 练题', color: '#e0a800' },
  mock: { label: '全卷模考', color: '#0ea5e9' },
  examReview: { label: '真题录屏', color: '#06b6d4' },
  setReview: { label: '套题录屏', color: '#0d9488' },
  import: { label: '导入套题', color: '#3b82f6' },
  review: { label: '错题复盘', color: '#22c55e' },
  reviewBrowse: { label: '复习浏览', color: '#14b8a6' },
  vocab: { label: '词汇练习', color: '#8b5cf6' },
  copybook: { label: '字帖练习', color: '#f97316' },
  chat: { label: '导师辅导', color: '#a855f7' },
};

export const loadLog = () => cloudGet(LOG_KEY, []);

const saveLog = (list) => cloudSet(LOG_KEY, list);

// 对外增加一条记录（通用）
export const addEntry = (entry) => {
  const list = loadLog();
  const rec = {
    id: Date.now() + Math.floor(Math.random() * 1000),
    ts: Date.now(),
    ...entry,
  };
  list.unshift(rec);
  // ponytail: 最多 10000 条；超过后需要服务端分页存储。
  saveLog(list.slice(0, 10000));
  // 广播变化事件（同页面内 storage 事件不触发，用自定义事件）
  try {
    window.dispatchEvent(new CustomEvent('study-log-change'));
  } catch {
    // ignore
  }
  return rec;
};

// 按 id 删除一条
export const removeEntry = (id) => {
  const next = loadLog().filter((r) => r.id !== id);
  saveLog(next);
  try {
    window.dispatchEvent(new CustomEvent('study-log-change'));
  } catch {
    // ignore
  }
};

// 当天已经记过这个类型就不再记，返回 null
export const addEntryOncePerDay = (type, entry) => {
  const today = dayKey(Date.now());
  const already = loadLog().some((r) => r.type === type && dayKey(r.ts) === today);
  if (already) return null;
  return addEntry({ type, ...entry });
};

// 当天某个类型已经记过了吗（UI 用来显示"今日已打卡"）
export const hasEntryToday = (type) => {
  const today = dayKey(Date.now());
  return loadLog().some((r) => r.type === type && dayKey(r.ts) === today);
};

// ---------------- 聚合查询 ----------------
// 日期键：YYYY-MM-DD（北京时间）
export const dayKey = studyDayKey;

// 返回 Map<dayKey, { minutes, unknownCount, entries, segments }>
export const aggregateByDay = (log = loadLog()) => aggregateStudyTime(log);

// 某天学了啥：导师总结里的科目 + 系统活动按科目合并。
// 84 场「2 的乘法」会收成一行，而不是 84 条。
export const chatTopics = (e) => {
  if (Array.isArray(e?.topics) && e.topics.length) {
    return e.topics.map((t) => String(t).trim()).filter(Boolean);
  }
  const mod = String(e?.module || '');
  const splitAt = mod.indexOf(' · ');
  if (splitAt >= 0) {
    return mod
      .slice(splitAt + 3)
      .split('/')
      .map((s) => s.trim())
      .filter(Boolean);
  }
  const summary = mod.replace(/^导师辅导:\s*/, '').trim();
  return summary ? [summary] : [];
};

export const digestDay = (entries = []) => {
  const lines = [];
  const seen = new Set();
  const groups = new Map();

  const push = (text) => {
    if (!text || seen.has(text)) return;
    seen.add(text);
    lines.push(text);
  };

  for (const e of entries) {
    if (e.type === 'chat') {
      const topics = chatTopics(e);
      if (topics.length) topics.forEach(push);
      else push('导师辅导');
      continue;
    }
    const title = e.module || ENTRY_TYPES[e.type]?.label || e.type;
    if (!title) continue;
    if (!groups.has(title)) {
      groups.set(title, { title, count: 0, correct: 0, hasCorrect: false, minutes: 0 });
    }
    const g = groups.get(title);
    g.count += e.count || 0;
    if (e.correct != null) {
      g.correct += e.correct;
      g.hasCorrect = true;
    }
    g.minutes += e.measuredMinutes || 0;
  }

  for (const g of groups.values()) {
    let s = g.title;
    if (g.count) {
      s += g.hasCorrect ? ` · ${g.correct}/${g.count}题` : ` · ${g.count}题`;
    } else if (g.minutes) {
      s += ` · ${g.minutes}分钟`;
    }
    push(s);
  }
  return lines;
};

// AI 练题的记录不在这份日志里，而是服务端按 practice_sessions 现算的
// （见 GET /api/practice/heat）。这里把它并进按天聚合的结果。
//
// 为什么不让前端交卷时往日志里写一条：这份日志是整体 PUT 的 JSON 数组，
// 服务端和前端同时往里写，晚写的一方会把对方的条目整个覆盖掉；而且现算
// 还顺带让历史场次不用回填脚本就能直接亮起来。
export const mergeServerHeat = (byDay, serverHeat) => {
  if (!serverHeat) return byDay;
  const entries = new Map();
  for (const day of byDay.values()) for (const entry of day.entries) {
    const source = entry.sourceEntry || entry;
    entries.set(`${source.type}:${source.id ?? source.ts}`, source);
  }
  for (const [key, day] of Object.entries(serverHeat)) {
    for (const e of day.entries || []) {
      // derived：派生条目删不掉，UI 不给删除按钮
      const id = e.id ?? `srv-${key}-${e.ts}-${e.count}`;
      entries.set(`${e.type}:${id}`, { ...e, id, day: key, derived: true });
    }
  }
  return aggregateStudyTime([...entries.values()]);
};

// 获取最近 N 天的日期键列表（从今天向前）
export const recentDayKeys = (days) => {
  const keys = [];
  const today = Date.now();
  for (let i = days - 1; i >= 0; i--) {
    keys.push(dayKey(today - i * 86400000));
  }
  return keys;
};

// 本周/本日/本月汇总
export const summarize = (log = loadLog(), serverHeat = null) => {
  const byDay = mergeServerHeat(aggregateByDay(log), serverHeat);
  const todayKey = dayKey(Date.now());
  const today = byDay.get(todayKey) || emptyStudyDay();

  const todayStart = Date.parse(`${todayKey}T00:00:00+08:00`);
  const weekDay = (new Date(`${todayKey}T00:00:00Z`).getUTCDay() + 6) % 7;
  const monday = dayKey(todayStart - weekDay * 86400000);
  const thisMonth = `${todayKey.slice(0, 7)}-01`;

  let weekMin = 0,
    weekDays = 0;
  let monthMin = 0,
    monthDays = 0;

  for (const [k, v] of byDay) {
    if (k > todayKey) continue;
    if (k >= monday) {
      weekMin += v.minutes;
      if (v.entries.length) weekDays += 1;
    }
    if (k >= thisMonth) {
      monthMin += v.minutes;
      if (v.entries.length) monthDays += 1;
    }
  }

  // 连续打卡天数（从今天往前算，连续有学习记录的天）
  let streak = 0;
  for (let i = 0; i < 365; i++) {
    const v = byDay.get(dayKey(todayStart - i * 86400000));
    if (v?.entries.length) {
      streak += 1;
    } else {
      break;
    }
  }

  return {
    today,
    weekMin,
    weekDays,
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

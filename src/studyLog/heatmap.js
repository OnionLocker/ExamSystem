import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import {
  loadLog,
  aggregateByDay,
  mergeServerHeat,
} from './studyLog.js';
import { timeLevel } from './studyTime.js';

// ============================================================
// 热力图相关工具：颜色梯度 + Hook
// 放在独立的 .js 文件里，避免与组件文件混在一起破坏 Fast Refresh
// ============================================================

// 固定时长区间，不能用正确率或题量兑换分钟。
export const HEAT_LEVELS = [
  { color: '#252525', text: '#a3a3a3', label: '无记录', range: '0' },
  { color: '#334155', text: '#f8fafc', label: '微量', range: '<30分钟' },
  { color: '#1d4ed8', text: '#ffffff', label: '较低', range: '30–60分钟' },
  { color: '#0891b2', text: '#071b22', label: '中低', range: '1–2小时' },
  { color: '#2dd4bf', text: '#062923', label: '中等', range: '2–3小时' },
  { color: '#facc15', text: '#342800', label: '中高', range: '3–4小时' },
  { color: '#fb923c', text: '#431407', label: '较高', range: '4–6小时' },
  { color: '#f87171', text: '#450a0a', label: '很高', range: '6–8小时' },
  { color: '#b91c1c', text: '#ffffff', label: '极高', range: '≥8小时' },
];
export const UNKNOWN_HEAT = { color: '#45454f', text: '#ffffff', label: '时长未知', range: '有学习记录' };

// AI 练题的热力由服务端按练习记录现算，不进本地学习日志。
// 这里统一拉一次，热力图和打卡面板共用，省得两处各查一遍。
export const useServerHeat = (version = 0) => {
  const [heat, setHeat] = useState(null);
  useEffect(() => {
    let alive = true;
    // 登录页也会挂这个 hook：没 token 时别把 {} 钉死，否则登录后 version
    // 不变就再也不拉了，日历热力整片空白，概览卡片却是对的（它登录后才挂载）。
    api('/api/practice/heat')
      .then((d) => { if (alive) setHeat(d || {}); })
      .catch(() => { if (alive) setHeat({}); });
    return () => { alive = false; };
  }, [version]);
  return heat;
};

// 供仪表盘日历使用：根据 dayKey 返回 { minutes, unknownCount, level, color, entries }
export const useStudyHeatmap = (version = 0) => {
  const serverHeat = useServerHeat(version);
  const byDay = useMemo(
    () => mergeServerHeat(aggregateByDay(loadLog()), serverHeat),
    // version 是有意的缓存失效信号：loadLog 读的是 localStorage，eslint 看不到这层依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version, serverHeat],
  );
  const getDay = (key) => {
    const v = byDay.get(key);
    if (!v) return null;
    const level = timeLevel(v.minutes);
    return { ...v, level, color: (v.minutes ? HEAT_LEVELS[level] : UNKNOWN_HEAT).color };
  };
  return { byDay, getDay, serverHeat };
};

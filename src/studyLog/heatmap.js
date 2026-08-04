import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import {
  loadLog,
  aggregateByDay,
  mergeServerHeat,
  scoreLevel,
} from './studyLog.js';

// ============================================================
// 热力图相关工具：颜色梯度 + Hook
// 放在独立的 .js 文件里，避免与组件文件混在一起破坏 Fast Refresh
// ============================================================

// 9 档颜色（含未打卡）：GitHub 风单色相琥珀，在黑底上层层递进
// 低档位贴近底色，高档位饱满发光，减少视觉噪点
export const LEVEL_COLORS = [
  null,      // 0: 无打卡（由调用方处理底色，通常是 rgba(255,255,255,0.04)）
  '#3d2e0a', // 1: 极弱（几乎和黑底融合的暗琥珀）
  '#5c4410', // 2: 弱
  '#82611a', // 3: 中低
  '#b08628', // 4: 中
  '#d4a43a', // 5: 中高
  '#ebbc4a', // 6: 高
  '#f8cf4d', // 7: 很高（品牌色 #fbc02d 附近）
  '#fde28a', // 8: 顶格（最亮，带发光感）
];

// AI 练题的热力由服务端按练习记录现算，不进本地学习日志。
// 这里统一拉一次，热力图和打卡面板共用，省得两处各查一遍。
export const useServerHeat = (version = 0) => {
  const [heat, setHeat] = useState(null);
  useEffect(() => {
    let alive = true;
    api('/api/practice/heat')
      .then((d) => alive && setHeat(d || {}))
      .catch(() => alive && setHeat({})); // 拿不到就只显示本地日志，不挡渲染
    return () => {
      alive = false;
    };
  }, [version]);
  return heat;
};

// 供仪表盘日历使用：根据 dayKey 返回 { score, minutes, level, color, entries }
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
    const level = scoreLevel(v.score);
    return { ...v, level, color: LEVEL_COLORS[level] };
  };
  return { byDay, getDay, serverHeat };
};

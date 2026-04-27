import { useMemo } from 'react';
import {
  loadLog,
  aggregateByDay,
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

// 供仪表盘日历使用：根据 dayKey 返回 { score, minutes, level, color, entries }
export const useStudyHeatmap = (version = 0) => {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const byDay = useMemo(() => aggregateByDay(loadLog()), [version]);
  const getDay = (key) => {
    const v = byDay.get(key);
    if (!v) return null;
    const level = scoreLevel(v.score);
    return { ...v, level, color: LEVEL_COLORS[level] };
  };
  return { byDay, getDay };
};

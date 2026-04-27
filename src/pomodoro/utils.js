// ---------------- 番茄钟相关工具函数 ----------------
// 放独立 .js 文件，避免与组件文件混在一起破坏 Fast Refresh

export const fmtHMS = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(m)}:${pad(sec)}`;
};

export const PHASE_LABELS = {
  idle: '未开始',
  work: '专注中',
  break: '休息中',
  longBreak: '长休中',
  paused: '已暂停',
};

// 判断时间戳是否属于今天
export const isToday = (ts) => {
  const d = new Date(ts);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
};

// 本周（周一为起点）
export const isThisWeek = (ts) => {
  const d = new Date(ts);
  const now = new Date();
  const day = (now.getDay() + 6) % 7; // 周一=0
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - day);
  return d >= monday && d <= now;
};

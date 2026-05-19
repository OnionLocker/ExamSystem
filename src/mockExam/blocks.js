// 全卷模考默认时间块
// 用户可以在 UI 里自定义（拖拽 / 改时长 / 增删），保存到 localStorage
//
// 默认推荐顺序：先做机械型（常识/言语），再做思考型（判断/资料/数运），
// 把最难的数量关系放最后，难题大胆放弃也能保证前面拿到分。

export const DEFAULT_BLOCKS = [
  { id: 'commonsense', name: '常识应用', minutes: 8,  color: '#a855f7' },
  { id: 'verbal',      name: '言语理解', minutes: 13, color: '#22c55e' },
  { id: 'numReason',   name: '数字推理', minutes: 6,  color: '#3b82f6' },
  { id: 'judgment',    name: '判断推理', minutes: 25, color: '#f97316' },
  { id: 'data',        name: '资料分析', minutes: 22, color: '#fbc02d' },
  { id: 'numCalc',     name: '数量关系', minutes: 13, color: '#ef4444' },
  { id: 'review',      name: '检查涂卡', minutes: 3,  color: '#94a3b8' },
];

// 添加新块时循环用的颜色池（避开默认 7 色）
export const COLOR_PALETTE = [
  '#06b6d4', '#ec4899', '#84cc16', '#eab308', '#8b5cf6', '#14b8a6', '#f43f5e',
];

// localStorage 持久化
const BLOCKS_KEY = 'mockexam_blocks_v2';

export const loadBlocks = () => {
  try {
    const raw = localStorage.getItem(BLOCKS_KEY);
    if (!raw) return DEFAULT_BLOCKS.map((b) => ({ ...b }));
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_BLOCKS.map((b) => ({ ...b }));
    }
    return parsed;
  } catch {
    return DEFAULT_BLOCKS.map((b) => ({ ...b }));
  }
};

export const saveBlocks = (blocks) => {
  try {
    localStorage.setItem(BLOCKS_KEY, JSON.stringify(blocks));
  } catch {
    // ignore
  }
};

export const resetBlocks = () => {
  try {
    localStorage.removeItem(BLOCKS_KEY);
  } catch {
    // ignore
  }
};

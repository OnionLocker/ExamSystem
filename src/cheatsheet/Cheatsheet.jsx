import { useEffect, useState } from 'react';
import { BookOpen, X, Search } from 'lucide-react';
import { FORMULA_GROUPS } from './formulas.js';

// ============================================================
// 公式速查面板
// 右下角悬浮按钮 → 抽屉式弹出 → 分类 tab + 搜索 + 卡片列表
// 全局可用，刷题时 1 秒查公式
// ============================================================

const Cheatsheet = () => {
  const [open, setOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState(FORMULA_GROUPS[0].id);
  const [query, setQuery] = useState('');

  // ESC 关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <>
      {/* 悬浮触发按钮 */}
      <button
        onClick={() => setOpen(true)}
        className={`fixed bottom-6 right-6 z-30 w-14 h-14 rounded-2xl bg-[#1a1a1a] text-white shadow-2xl shadow-black/30 flex items-center justify-center hover:scale-105 hover:bg-[#2c261c] hover:text-white transition-all ${
          open ? 'opacity-0 pointer-events-none' : 'opacity-100'
        }`}
        title="公式速查"
      >
        <BookOpen size={22} strokeWidth={2.4} />
      </button>

      {/* 抽屉 */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          onClick={() => setOpen(false)}
        >
          {/* 背景遮罩 */}
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          {/* 抽屉本体 */}
          <div
            className="relative w-full max-w-md h-full bg-white shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 标题栏 */}
            <div className="px-6 py-5 border-b border-[#e8d5b0] flex items-center justify-between flex-shrink-0">
              <div className="flex items-center space-x-3">
                <div className="w-9 h-9 rounded-xl bg-[#1a1a1a] text-white flex items-center justify-center">
                  <BookOpen size={16} />
                </div>
                <div>
                  <h3 className="font-black text-base tracking-tight">公式速查</h3>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-0.5">
                    Formula Cheatsheet
                  </p>
                </div>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="w-8 h-8 rounded-full bg-[#e8d5b0] hover:bg-[#e8e6dd] flex items-center justify-center"
              >
                <X size={14} />
              </button>
            </div>

            {/* 搜索 */}
            <div className="px-6 pt-4 flex-shrink-0">
              <div className="relative">
                <Search
                  size={14}
                  className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜公式名 / 适用场景"
                  className="w-full bg-[#e8d5b0]/60 border border-transparent rounded-full pl-10 pr-4 py-2.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-[#6b5428]"
                />
              </div>
            </div>

            {/* 分类 tab */}
            <div className="px-6 pt-4 flex-shrink-0">
              <div className="flex space-x-2 overflow-x-auto pb-2">
                {FORMULA_GROUPS.map((g) => {
                  const active = g.id === activeGroup;
                  return (
                    <button
                      key={g.id}
                      onClick={() => setActiveGroup(g.id)}
                      className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-black tracking-tight transition-all ${
                        active
                          ? 'bg-[#1a1a1a] text-white'
                          : 'bg-[#e8d5b0]/60 text-slate-500 hover:bg-[#e8d5b0]'
                      }`}
                      style={
                        active ? { backgroundColor: g.color, color: '#1a1a1a' } : undefined
                      }
                    >
                      {g.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 公式列表 */}
            <div className="flex-1 overflow-y-auto px-6 pb-6 mt-2">
              <FormulaList groupId={activeGroup} query={query} setActiveGroup={setActiveGroup} />
            </div>
          </div>
        </div>
      )}
    </>
  );
};

const FormulaList = ({ groupId, query, setActiveGroup }) => {
  const q = query.trim().toLowerCase();

  // 搜索：跨所有 group 查找；无搜索时只看当前 group
  const sourceGroups = q ? FORMULA_GROUPS : FORMULA_GROUPS.filter((g) => g.id === groupId);

  const matches = [];
  for (const g of sourceGroups) {
    for (const sec of g.sections) {
      for (const f of sec.formulas) {
        if (
          !q ||
          f.name.toLowerCase().includes(q) ||
          f.formula.toLowerCase().includes(q) ||
          (f.note && f.note.toLowerCase().includes(q))
        ) {
          matches.push({ group: g, section: sec, formula: f });
        }
      }
    }
  }

  if (matches.length === 0) {
    return (
      <div className="text-center py-12 text-sm font-bold text-slate-400">
        没有匹配的公式
      </div>
    );
  }

  if (q) {
    // 搜索结果模式：列表，每条带分组标签
    return (
      <div className="space-y-3 mt-2">
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
          找到 {matches.length} 条
        </p>
        {matches.map(({ group, section, formula }, i) => (
          <FormulaCard
            key={i}
            formula={formula}
            tag={`${group.name} · ${section.title}`}
            tagColor={group.color}
            onTagClick={() => setActiveGroup(group.id)}
          />
        ))}
      </div>
    );
  }

  // 浏览模式：分组渲染
  const g = sourceGroups[0];
  return (
    <div className="space-y-6 mt-2">
      {g.sections.map((sec, i) => (
        <div key={i}>
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">
            {sec.title}
          </p>
          <div className="space-y-2.5">
            {sec.formulas.map((f, j) => (
              <FormulaCard key={j} formula={f} accentColor={g.color} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

const FormulaCard = ({ formula, tag, tagColor, accentColor, onTagClick }) => (
  <div className="bg-[#e8d5b0]/40 hover:bg-[#e8d5b0]/70 rounded-2xl p-4 transition-colors">
    <div className="flex items-start justify-between gap-3 mb-2">
      <p className="font-black text-sm tracking-tight">{formula.name}</p>
      {tag && (
        <button
          onClick={onTagClick}
          className="flex-shrink-0 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest"
          style={{ backgroundColor: `${tagColor}20`, color: tagColor }}
        >
          {tag}
        </button>
      )}
    </div>
    <p
      className="font-mono text-xs font-bold mb-1.5 leading-relaxed"
      style={{ color: accentColor || '#1a1a1a' }}
    >
      {formula.formula}
    </p>
    {formula.note && (
      <p className="text-[11px] text-slate-500 font-medium leading-relaxed">
        {formula.note}
      </p>
    )}
    {formula.example && (
      <p className="text-[11px] text-slate-400 font-medium leading-relaxed mt-1.5 pl-2 border-l-2 border-slate-200">
        例：{formula.example}
      </p>
    )}
  </div>
);

export default Cheatsheet;

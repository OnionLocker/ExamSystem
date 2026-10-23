import { useEffect, useState } from 'react';
import { BookOpen, X, Search } from 'lucide-react';
import { FORMULA_GROUPS } from './formulas.js';
import { openKnowledge } from '../knowledge/nav.js';

const Cheatsheet = () => {
  const [open, setOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState(FORMULA_GROUPS[0].id);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const jump = (tag) => {
    setOpen(false);
    openKnowledge(tag);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`fixed bottom-6 right-6 z-30 w-14 h-14 rounded-2xl bg-[#1a1a1a] text-white shadow-2xl shadow-black/30 flex items-center justify-center hover:scale-105 hover:bg-[#2c261c] transition-all ${
          open ? 'opacity-0 pointer-events-none' : 'opacity-100'
        }`}
        title="公式速查"
      >
        <BookOpen size={22} strokeWidth={2.4} />
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6"
          onClick={() => setOpen(false)}
        >
          <div className="absolute inset-0 bg-black/45 backdrop-blur-sm" />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="cheatsheet-title"
            className="relative w-full max-w-6xl max-h-[min(92vh,940px)] bg-[#e8d5b0] text-[#2a2418] shadow-2xl rounded-3xl border border-[#b89f69] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 sm:px-7 py-4 bg-[#f0e3c5] border-b border-[#d1c09a] flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-[#1a1a1a] text-white flex items-center justify-center shadow-sm">
                  <BookOpen size={18} />
                </div>
                <div>
                  <h3 id="cheatsheet-title" className="font-black text-lg tracking-tight text-[#1a1a1a]">公式速查</h3>
                  <p className="text-xs font-bold tracking-wide text-[#746b5b] mt-0.5">
                    点每节旁的知识点，直接打开对应页
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-9 h-9 rounded-full bg-[#e2cfa8] text-[#343127] hover:bg-[#1a1a1a] hover:text-white flex items-center justify-center transition-colors"
                aria-label="关闭公式速查"
              >
                <X size={16} />
              </button>
            </div>

            <div className="px-6 sm:px-7 pt-4 pb-3 bg-[#f0e3c5]/60 border-b border-[#d9c7a0] flex-shrink-0">
              <div className="relative">
                <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#81755f]" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜公式、对照表或适用场景"
                  className="w-full bg-[#f2e4c4] border border-[#c9b489] rounded-2xl pl-11 pr-4 py-3 text-[15px] font-bold text-[#1a1a1a] placeholder:text-[#81755f] focus:outline-none focus:ring-2 focus:ring-[#6b5428] focus:border-[#6b5428] transition-all"
                />
              </div>

              <div className="flex gap-2.5 overflow-x-auto pt-3 pb-1">
                {FORMULA_GROUPS.map((g) => {
                  const active = g.id === activeGroup;
                  return (
                    <button
                      key={g.id}
                      type="button"
                      onClick={() => setActiveGroup(g.id)}
                      className={`flex-shrink-0 px-4.5 py-2 rounded-full text-sm font-black tracking-tight transition-all border ${
                        active
                          ? 'bg-[#1a1a1a] text-white border-[#1a1a1a] shadow-sm'
                          : 'bg-[#f2e4c4] text-[#574b35] border-[#cfb98e] hover:bg-[#e4d2ad] hover:text-[#1a1a1a]'
                      }`}
                    >
                      {g.name}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="hermes-scroll flex-1 overflow-y-auto px-6 sm:px-7 py-5">
              <FormulaList groupId={activeGroup} query={query} onJump={jump} />
            </div>
          </div>
        </div>
      )}
    </>
  );
};

const haystack = (section) => [
  section.title,
  section.tag,
  ...(section.formulas || []).flatMap((f) => [f.name, f.formula, f.note, f.example]),
  ...(section.tables || []).flatMap((t) => [t.title, ...t.columns, ...t.rows.flat()]),
].filter(Boolean).join('\n').toLowerCase();

const FormulaList = ({ groupId, query, onJump }) => {
  const q = query.trim().toLowerCase();
  const sourceGroups = q ? FORMULA_GROUPS : FORMULA_GROUPS.filter((g) => g.id === groupId);
  const sections = [];
  for (const g of sourceGroups) {
    for (const sec of g.sections) {
      if (!q || haystack(sec).includes(q)) sections.push({ group: g, section: sec });
    }
  }

  if (!sections.length) {
    return <div className="text-center py-14 text-base font-bold text-[#746b5b]">没有匹配的公式</div>;
  }

  return (
    <div>
      {q && (
        <p className="text-xs font-black tracking-widest text-[#6b5428] mb-4">
          找到 {sections.length} 节
        </p>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-6">
        {sections.map(({ group, section }) => (
          <SectionBlock key={`${group.id}-${section.title}`} group={group} section={section} onJump={onJump} showGroup={Boolean(q)} />
        ))}
      </div>
    </div>
  );
};

const SectionBlock = ({ group, section, onJump, showGroup }) => (
  <section className={section.wide ? 'xl:col-span-2' : undefined}>
    <div className="flex items-center justify-between gap-3 mb-3">
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="w-1.5 h-4 rounded-full bg-[#6b5428] flex-shrink-0" />
        <h4 className="text-base font-black tracking-tight text-[#2a2418] min-w-0">
          {showGroup ? `${group.name} · ` : ''}{section.title}
        </h4>
      </div>
      <button
        type="button"
        onClick={() => onJump(section.tag)}
        className="flex-shrink-0 px-3.5 py-1.5 rounded-full bg-[#f2e4c4] border border-[#b89f69] text-xs font-black text-[#574b35] hover:bg-[#1a1a1a] hover:text-white hover:border-[#1a1a1a] transition-colors"
        title={section.tag}
      >
        知识点
      </button>
    </div>
    {section.tables?.map((table) => <LookupTable key={table.title || table.columns.join()} table={table} />)}
    {section.formulas?.length > 0 && (
      <div className="space-y-3">
        {section.formulas.map((f) => (
          <FormulaCard key={f.name} formula={f} accentColor={group.color} />
        ))}
      </div>
    )}
  </section>
);

// table.group = 每组几格（分数/% 为 2，a/b/c 为 3）。数据仍按「一行多组、从左往右」书写，
// 这里重排成两大列、从上往下递增。tint: 'field' 按组内列区分底色，'group' 按组区分底色。
const GROUP_COLS = 2;
const FIELD_TINTS = ['#f6e7c4', '#ecd29c'];
const GROUP_TINTS = ['#f6e5bd', '#f0d3b4'];

const regroupTable = (table) => {
  const size = table.group;
  const items = table.rows.flatMap((row) => {
    const out = [];
    for (let i = 0; i < row.length; i += size) {
      const item = row.slice(i, i + size);
      if (item.some(Boolean)) out.push(item);
    }
    return out;
  });
  const height = Math.ceil(items.length / GROUP_COLS);
  const rows = Array.from({ length: height }, (_, r) =>
    Array.from({ length: GROUP_COLS }, (_, c) => items[c * height + r] || Array(size).fill('')).flat(),
  );
  const columns = Array.from({ length: GROUP_COLS }, () => table.columns.slice(0, size)).flat();
  return { columns, rows };
};

const GroupedTable = ({ table }) => {
  const size = table.group;
  const { columns, rows } = regroupTable(table);
  const tintOf = (i) => (table.tint === 'group'
    ? GROUP_TINTS[Math.floor(i / size) % GROUP_TINTS.length]
    : FIELD_TINTS[(i % size) % FIELD_TINTS.length]);
  const edge = (i) => (i > 0 && i % size === 0 ? 'border-l-2 border-[#c9ad78]' : '');
  return (
    <div className="mb-3 overflow-x-auto rounded-2xl border border-[#cfb98e] bg-[#f0e3c5] shadow-xs">
      {table.title && (
        <div className="px-4 py-2.5 bg-[#ead7b2] border-b border-[#d6c299]">
          <p className="text-[13px] font-black tracking-tight text-[#4a3a1c]">{table.title}</p>
        </div>
      )}
      <table className="w-full text-[15px] border-collapse">
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th
                key={`${col}-${i}`}
                className={`px-3.5 py-2 text-left text-xs font-black tracking-wider text-[#6e5f44] whitespace-nowrap ${edge(i)}`}
                style={{ backgroundColor: tintOf(i) }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr key={`${rowIdx}-${row.join('|')}`} className="border-t border-[#dfc9a0]">
              {row.map((cell, i) => (
                <td
                  key={`${cell}-${i}`}
                  className={`px-3.5 py-2.5 tabular-nums whitespace-nowrap ${edge(i)} ${
                    table.tint !== 'group' && i % size === 0
                      ? 'font-bold text-[#4a3d28]'
                      : 'font-black text-[#1a1a1a]'
                  }`}
                  style={{ backgroundColor: tintOf(i) }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const LookupTable = ({ table }) => (table.group ? <GroupedTable table={table} /> : (
  <div className="mb-3 overflow-x-auto rounded-2xl border border-[#cfb98e] bg-[#f0e3c5] shadow-xs">
    {table.title && (
      <div className="px-4 py-2.5 bg-[#ead7b2] border-b border-[#d6c299]">
        <p className="text-[13px] font-black tracking-tight text-[#4a3a1c]">{table.title}</p>
      </div>
    )}
    <table className="w-full text-[15px] border-collapse">
      <thead>
        <tr className="bg-[#ece0c3]/70">
          {table.columns.map((col, i) => (
            <th
              key={`${col}-${i}`}
              className="px-3.5 py-2 text-left text-xs font-black tracking-wider text-[#6e5f44] whitespace-nowrap"
            >
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.rows.map((row, rowIdx) => (
          <tr
            key={`${rowIdx}-${row.join('|')}`}
            className="border-t border-[#dfd0ae] hover:bg-[#e8d5b0]/55 transition-colors"
          >
            {row.map((cell, i) => (
              <td
                key={`${cell}-${i}`}
                className={`px-3.5 py-2.5 tabular-nums whitespace-nowrap ${
                  i % 2 === 0
                    ? 'font-bold text-[#4a3d28]'
                    : 'font-black text-[#1a1a1a]'
                }`}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
));

const FormulaCard = ({ formula, accentColor }) => (
  <div className="bg-[#f0e3c5] border border-[#cfb98e] hover:border-[#9e8450] rounded-2xl px-4.5 py-4 transition-colors shadow-xs">
    <p className="font-black text-[16px] tracking-tight text-[#1a1a1a] mb-1.5">{formula.name}</p>
    <p className="font-mono text-[15px] font-bold mb-2 leading-relaxed text-[#2a2012] bg-[#e6d5b2]/65 px-3 py-2 rounded-xl border border-[#d8c49b]">
      <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ backgroundColor: accentColor }} />
      {formula.formula}
    </p>
    {formula.note && (
      <p className="text-[13.5px] text-[#4d422f] font-semibold leading-relaxed">{formula.note}</p>
    )}
    {formula.example && (
      <p className="text-[13px] text-[#6b5c43] font-medium leading-relaxed mt-2 pl-3 border-l-2 border-[#b89f69]">
        例：{formula.example}
      </p>
    )}
  </div>
);

export default Cheatsheet;

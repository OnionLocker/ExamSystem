import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Moon, Sparkles } from 'lucide-react';
import { api } from '../api.js';

// ---------------- 题库分类结构 ----------------
// 与 DB 中 `category` / `sub_category` 完全一致（中文名做键）
// subs 为空数组 = 该类顶层整体刷题，不再细分
const BANK_CATEGORIES = [
  { name: '政治理论', subs: [] },
  { name: '常识判断', subs: [] },
  { name: '言语理解与表达', subs: [] },
  {
    name: '数量关系',
    subs: [
      { name: '数字推理' },
      { name: '数学运算' },
    ],
  },
  {
    name: '判断推理',
    subs: [
      { name: '图形推理' },
      { name: '逻辑判断' },
      { name: '科学推理' },
    ],
  },
  { name: '资料分析', subs: [] },
];

// 把扁平的 meta 行（{category, sub_category, count}）聚合成 map
const buildCountMap = (rows) => {
  const catTotal = new Map();
  const subTotal = new Map(); // key: `${cat}__${sub}`
  for (const r of rows || []) {
    catTotal.set(r.category, (catTotal.get(r.category) || 0) + (r.count || 0));
    if (r.sub_category) {
      subTotal.set(`${r.category}__${r.sub_category}`, r.count || 0);
    }
  }
  return { catTotal, subTotal };
};

// 四颗月亮：根据完成比例决定点亮数（done/total）
const MoonRow = ({ done, total }) => {
  const ratio = total > 0 ? done / total : 0;
  const filled = Math.min(4, Math.max(0, Math.round(ratio * 4)));
  return (
    <div className="flex items-center space-x-1">
      {Array.from({ length: 4 }).map((_, i) => (
        <Moon
          key={i}
          size={16}
          strokeWidth={2.5}
          className={
            i < filled
              ? 'text-[#fbc02d] fill-[#fbc02d]'
              : 'text-[#e8e6dd] fill-transparent'
          }
        />
      ))}
    </div>
  );
};

// 单行（顶层 or 子项共用）
// 可展开行：左侧 chevron 是独立按钮（切换展开/收起），其余主体是独立按钮（开始刷题）
const BankRow = ({
  name,
  done,
  total,
  expandable = false,
  expanded = false,
  isSub = false,
  mixHint = false, // 父类展开时，在名字后面提示"混合"
  onPractice,
  onToggle,
}) => {
  const hasData = total > 0;

  const containerCls = isSub
    ? 'bg-transparent hover:bg-[#f2f0e9]/60 pl-3'
    : 'bg-white hover:shadow-md shadow-sm border border-[#f2f0e9]';

  return (
    <div
      className={`w-full flex items-center rounded-[1.5rem] transition-all group ${containerCls}`}
    >
      {/* 左侧：chevron（可展开）/占位（子项）/小圆点（普通顶层） */}
      {expandable ? (
        <button
          type="button"
          onClick={onToggle}
          title={expanded ? '收起' : '展开'}
          aria-label={expanded ? '收起' : '展开'}
          className="pl-5 pr-2 py-5 flex-shrink-0 text-[#fbc02d] hover:text-[#1a1a1a] transition-colors"
        >
          <ChevronDown
            size={18}
            className={`transition-transform ${expanded ? '' : '-rotate-90'}`}
          />
        </button>
      ) : isSub ? (
        <span className="pl-11 flex-shrink-0" />
      ) : (
        <span className="pl-6 pr-3 flex-shrink-0">
          <span className="block w-2 h-2 rounded-full bg-[#e8e6dd]" />
        </span>
      )}

      {/* 主体：点击进入刷题 */}
      <button
        type="button"
        onClick={onPractice}
        className="flex-1 min-w-0 flex items-center justify-between pr-6 py-5 text-left"
      >
        <div className="flex items-center space-x-2 min-w-0">
          <span
            className={`font-bold truncate ${
              isSub ? 'text-sm text-[#444]' : 'text-base'
            }`}
          >
            {name}
          </span>
          {mixHint && hasData && (
            <span className="flex-shrink-0 text-[10px] font-black uppercase tracking-widest text-[#fbc02d] bg-[#fbc02d]/10 px-2 py-0.5 rounded-full">
              混合
            </span>
          )}
          {!hasData && (
            <span className="flex-shrink-0 text-[10px] font-black uppercase tracking-widest text-slate-400 bg-[#f2f0e9] px-2 py-0.5 rounded-full">
              暂无题目
            </span>
          )}
        </div>
        <div className="flex items-center space-x-4 flex-shrink-0">
          <MoonRow done={done} total={total} />
          <span className="font-mono tabular-nums text-xs font-bold text-slate-400 min-w-[70px] text-right">
            {done}/{total}
          </span>
          <ChevronRight
            size={18}
            className="text-slate-300 group-hover:text-[#1a1a1a] transition-colors"
          />
        </div>
      </button>
    </div>
  );
};

// "即将开放"占位弹层
const ComingSoonModal = ({ target, onClose }) => {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[2rem] p-10 max-w-md w-full shadow-2xl text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="w-16 h-16 mx-auto rounded-2xl bg-[#fbc02d] text-black flex items-center justify-center mb-5">
          <Sparkles size={28} />
        </div>
        <h3 className="text-2xl font-black italic mb-2">{target}</h3>
        <p className="text-sm font-medium text-slate-500 mb-6">
          题库导入功能开发中，敬请期待。
        </p>
        <button
          onClick={onClose}
          className="bg-[#1a1a1a] text-white font-black px-10 py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs"
        >
          知道了
        </button>
      </div>
    </div>
  );
};

const QuestionBank = () => {
  const [metaRows, setMetaRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(() => ({
    数量关系: true,
    判断推理: true,
  }));
  const [pending, setPending] = useState(null); // 点击的目标名（占位弹层）

  useEffect(() => {
    let aborted = false;
    api('/api/questions/meta/categories')
      .then((rows) => {
        if (aborted) return;
        setMetaRows(Array.isArray(rows) ? rows : []);
      })
      .catch(() => {
        if (!aborted) setMetaRows([]);
      })
      .finally(() => {
        if (!aborted) setLoading(false);
      });
    return () => {
      aborted = true;
    };
  }, []);

  const { catTotal, subTotal } = useMemo(() => buildCountMap(metaRows), [metaRows]);

  // TODO: done 需要从 practice_answers 汇总。目前占位为 0。
  const getDone = () => 0;

  const toggle = (name) =>
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));

  const handleClick = (label) => setPending(label);

  const grandTotal = Array.from(catTotal.values()).reduce((a, b) => a + b, 0);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* 顶部 banner */}
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-8 relative overflow-hidden">
        <div className="absolute top-6 right-6 w-32 h-32 bg-[#fbc02d] rounded-full blur-[40px] opacity-50" />
        <div className="relative z-10 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mb-1">
              公务员行测 · 广东省考
            </p>
            <h3 className="text-2xl font-black italic">按模块刷题</h3>
            <p className="text-sm font-medium opacity-60 mt-1">
              覆盖 6 大模块，真题模拟题按题型归类
            </p>
          </div>
          <div className="text-right">
            <p className="text-4xl font-black tabular-nums">{grandTotal}</p>
            <p className="text-[10px] font-black uppercase tracking-widest opacity-60">
              题库总量
            </p>
          </div>
        </div>
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="text-center text-sm font-bold text-slate-400 py-16">
          加载中...
        </div>
      ) : (
        <div className="space-y-3">
          {BANK_CATEGORIES.map((cat) => {
            const total = catTotal.get(cat.name) || 0;
            const done = getDone(cat.name);
            const hasSubs = cat.subs.length > 0;
            const isOpen = !!expanded[cat.name];

            return (
              <div key={cat.name} className="space-y-2">
                <BankRow
                  name={cat.name}
                  done={done}
                  total={total}
                  expandable={hasSubs}
                  expanded={isOpen}
                  mixHint={hasSubs}
                  onToggle={() => toggle(cat.name)}
                  onPractice={() =>
                    handleClick(hasSubs ? `${cat.name} · 混合随机` : cat.name)
                  }
                />
                {hasSubs && isOpen && (
                  <div className="space-y-1">
                    {cat.subs.map((s) => {
                      const key = `${cat.name}__${s.name}`;
                      const subT = subTotal.get(key) || 0;
                      return (
                        <BankRow
                          key={s.name}
                          isSub
                          name={s.name}
                          done={0}
                          total={subT}
                          onPractice={() => handleClick(`${cat.name} · ${s.name}`)}
                        />
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 底部提示 */}
      <div className="text-center py-4 space-y-1">
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
          点击左侧箭头展开子题型 · 点击模块名称开始刷题
        </p>
        <p className="text-[10px] font-medium text-slate-400">
          展开后：选子题型 = 只刷该子类；点父类 = 在所有子类里混合随机
        </p>
      </div>

      {pending && <ComingSoonModal target={pending} onClose={() => setPending(null)} />}
    </div>
  );
};

export default QuestionBank;

// 今日处方卡：把"该练什么"直接摆在首页，而不是让人对着 60 个子项自己挑
import { useMemo } from 'react';
import { Target, ChevronRight, Flame, Stethoscope } from 'lucide-react';
import { topPicks } from './weakSpots.js';
import { wrongCountsBySub, totalWrong } from './wrongPool.js';
import { loadStats } from './ranks.js';
import { summarizeHistoryErrors } from './errorKinds.js';
import { loadHistory } from './history.js';

// 错因对应的补救方案：知道哪里错还不够，得说清楚接下来练什么
const PRESCRIPTION = {
  carry: { text: '进位是主要失分点，去「补数与滚加」把凑整和滚加练成条件反射。', catId: 'speedOps' },
  confuse: { text: '属于把相邻的值记串了，回「百化分固定」对照表成对地背。', catId: 'aux' },
  unit: { text: '末位看花眼居多，作答前多花半秒复核个位。', catId: null },
  typo: { text: '大多是手滑输错，不是能力问题，按键慢半拍就行。', catId: null },
  other: { text: '偏差较大，建议降速重做，先保准确再提速。', catId: null },
};

const WeakSpots = ({ onPickSub }) => {
  const { picks, diagnosis, debt } = useMemo(() => {
    const stats = loadStats();
    const wrongCounts = wrongCountsBySub();
    const history = loadHistory();
    return {
      picks: topPicks({ stats, wrongCounts }),
      diagnosis: summarizeHistoryErrors(history),
      debt: totalWrong(),
    };
  }, []);

  if (picks.length === 0) return null;

  const top = diagnosis.find((d) => d.code !== 'skipped');
  const plan = top ? PRESCRIPTION[top.code] : null;

  return (
    <div className="rounded-[2rem] bg-white border border-[#e8d5b0] p-8 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-[#2c261c] text-white flex items-center justify-center">
            <Target size={18} />
          </div>
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
              今日处方
            </p>
            <h3 className="text-lg font-black italic">先练这几个</h3>
          </div>
        </div>
        {debt > 0 && (
          <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-[#ff6b6b]/10 text-[#ff6b6b]">
            <Flame size={13} />
            <span className="text-xs font-black tabular-nums">{debt} 道错题待还</span>
          </div>
        )}
      </div>

      <div className="space-y-2.5">
        {picks.map((p) => (
          <button
            key={p.id}
            onClick={() => onPickSub?.(p.catId, p.id)}
            className="w-full text-left rounded-2xl px-5 py-4 bg-[#e8d5b0]/60 hover:bg-[#1a1a1a] hover:text-white transition-all group flex items-center justify-between"
          >
            <div className="min-w-0">
              <div className="flex items-baseline space-x-2">
                <span className="text-sm font-black italic truncate">{p.name}</span>
                <span className="text-[10px] font-bold text-slate-400 group-hover:text-white/40 flex-shrink-0">
                  {p.catName}
                </span>
              </div>
              <p className="text-[11px] font-bold text-slate-400 group-hover:text-white/50 mt-0.5">
                {p.reason}
                {p.accuracy != null && (
                  <span className="tabular-nums">
                    {' · '}
                    {Math.round(p.accuracy * 100)}% · {(p.avgMs / 1000).toFixed(1)}s
                  </span>
                )}
              </p>
            </div>
            <ChevronRight
              size={18}
              className="flex-shrink-0 ml-3 opacity-30 group-hover:opacity-100 group-hover:translate-x-1 transition-all"
            />
          </button>
        ))}
      </div>

      {plan && (
        <div className="mt-6 pt-5 border-t border-[#e8d5b0] flex items-start space-x-3">
          <Stethoscope size={15} className="text-slate-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs font-bold text-slate-500 leading-relaxed">
            历史错题里
            <span className="text-[#1a1a1a]">
              {' '}
              {top.label} 占 {top.pct}%
            </span>
            。{plan.text}
          </p>
        </div>
      )}
    </div>
  );
};

export default WeakSpots;

import { useEffect, useMemo, useState } from 'react';
import { Trophy } from 'lucide-react';
import { CATEGORIES } from './generators.js';
import {
  RANKS,
  getRank,
  loadStats,
  computeCategoryRank,
  computeOverallRank,
  MIN_COUNT,
  clearRankStats,
} from './ranks.js';
import RankBadge from './RankBadge.jsx';
import RankInfo from './RankInfo.jsx';

// ============================================================
// 数资练习顶部横幅：展示整体段位 + 四大类小段位 + 简要说明
// 只统计"晋升模式"的累计结果
// ============================================================
const RankDashboard = ({ onClickCategory }) => {
  const [version, setVersion] = useState(0);
  const [showInfo, setShowInfo] = useState(false);

  useEffect(() => {
    const onChange = () => setVersion((v) => v + 1);
    window.addEventListener('numeric-rank-change', onChange);
    return () => window.removeEventListener('numeric-rank-change', onChange);
  }, []);

  // version 是有意的缓存失效信号：loadStats 读的是 localStorage，
  // eslint 看不到这层依赖，所以必须手动把 version 放进依赖里。
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stats = useMemo(() => loadStats(), [version]);
  const overall = useMemo(() => computeOverallRank(CATEGORIES, stats), [stats]);
  const overallRank = getRank(overall.rankId);

  // 总答题数、总场次
  const totalPlays = Object.values(stats).reduce((s, v) => s + (v.plays || 0), 0);
  const totalCount = Object.values(stats).reduce((s, v) => s + (v.totalCount || 0), 0);

  return (
    <div className="bg-[#1a1a1a] text-white rounded-[2rem] overflow-hidden relative">
      {/* 背景装饰光斑 */}
      <div
        className="absolute -top-10 -right-10 w-56 h-56 rounded-full blur-[80px] opacity-30 pointer-events-none"
        style={{ backgroundColor: overallRank.color }}
      />
      <div className="relative p-6 md:p-8">
        <div className="flex items-start md:items-center justify-between flex-col md:flex-row gap-6">
          {/* 左：整体段位 */}
          <div className="flex items-center space-x-5">
            <div className="flex-shrink-0">
              <RankBadge rankId={overall.rankId} size={72} />
            </div>
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.25em] text-white/40">
                你的段位
              </p>
              <div className="flex items-baseline space-x-2 mt-1">
                <span
                  className="text-3xl md:text-4xl font-black italic tracking-tight"
                  style={{ color: overallRank.color }}
                >
                  {overallRank.label}
                </span>
                <span className="text-[10px] font-black uppercase tracking-widest text-white/40">
                  {overallRank.short}
                </span>
              </div>
              <p className="text-xs font-medium text-white/50 mt-1.5">
                {overall.rankId === 'unranked' ? (
                  <>去任一类别下完成「晋升模式」即可评级</>
                ) : (
                  <>
                    累计 {totalPlays} 场 · {totalCount} 题 · 段位分{' '}
                    <span className="font-black text-[#6b5428] tabular-nums">
                      {overall.totalScore}
                    </span>
                  </>
                )}
              </p>
            </div>
          </div>

          {/* 右：四大类小段位 */}
          <div className="grid grid-cols-4 gap-2 md:gap-3 w-full md:w-auto">
            {overall.catRanks.map((cr, i) => {
              const cat = CATEGORIES[i];
              const r = getRank(cr.rankId);
              return (
                <button
                  key={cat.id}
                  onClick={() => onClickCategory?.(cat.id)}
                  className="group bg-white/[0.04] hover:bg-white/[0.08] rounded-2xl p-3 md:p-4 transition-all text-left"
                  title={`进入${cat.name}`}
                >
                  <div className="flex items-center justify-center mb-2">
                    <RankBadge rankId={cr.rankId} size={40} />
                  </div>
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/40 text-center">
                    {cat.name}
                  </p>
                  <p
                    className="text-xs font-black italic text-center mt-0.5"
                    style={{ color: r.color }}
                  >
                    {r.label}
                  </p>
                  <p className="text-[9px] font-black tabular-nums text-center text-white/30 mt-0.5">
                    {cr.rankedCount}/{cr.totalSubs}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* 底部：段位图例 + 段位图谱入口 */}
        <div className="mt-5 pt-5 border-t border-white/5 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center space-x-1 text-[10px] flex-wrap gap-y-1">
            {RANKS.slice(1).map((r) => (
              <div
                key={r.id}
                className="flex items-center space-x-1 px-2 py-1 rounded-full"
                style={{ backgroundColor: `${r.color}1a` }}
                title={`${r.label}`}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: r.color }}
                />
                <span className="font-black" style={{ color: r.color }}>
                  {r.label}
                </span>
              </div>
            ))}
          </div>
          <button
            onClick={() => setShowInfo(true)}
            className="flex items-center space-x-2 px-4 py-2 rounded-full bg-[#2c261c] text-white hover:brightness-110 text-[10px] font-black uppercase tracking-widest transition-all"
          >
            <Trophy size={12} strokeWidth={2.5} />
            <span>段位图谱</span>
          </button>
        </div>
      </div>

      {showInfo && <RankInfo onClose={() => setShowInfo(false)} />}
    </div>
  );
};

// 子项详情弹层：列出该分类每个子项的段位、平均用时、正确率、进度
export const CategoryRankDetail = ({ cat, onClose }) => {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const onChange = () => setVersion((v) => v + 1);
    window.addEventListener('numeric-rank-change', onChange);
    return () => window.removeEventListener('numeric-rank-change', onChange);
  }, []);
  // 同上：version 驱动 localStorage 重读
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stats = useMemo(() => loadStats(), [version]);
  const detail = useMemo(() => computeCategoryRank(cat, stats), [cat, stats]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[2rem] p-8 max-w-2xl w-full max-h-[85vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-4">
            <RankBadge rankId={detail.rankId} size={56} />
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                {cat.name} · 分类段位
              </p>
              <p
                className="text-2xl font-black italic"
                style={{ color: getRank(detail.rankId).color }}
              >
                {getRank(detail.rankId).label}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-xs font-black uppercase tracking-widest text-slate-400 hover:text-black"
          >
            关闭
          </button>
        </div>

        <div className="space-y-2">
          {detail.entries.map(({ sub, stat, eval: ev }) => (
            <SubRow key={sub.id} sub={sub} stat={stat} ev={ev} />
          ))}
        </div>
      </div>
    </div>
  );
};

const SubRow = ({ sub, stat, ev }) => {
  const rank = getRank(ev.rankId);
  const accPct = Math.round((ev.accuracy || 0) * 100);
  const avgMs = Math.round(ev.avgMs || 0);
  return (
    <div className="flex items-center justify-between py-3 px-4 rounded-xl bg-[#e8d5b0]/40 hover:bg-[#e8d5b0]">
      <div className="flex items-center space-x-3 min-w-0">
        <RankBadge rankId={ev.rankId} size={32} />
        <div className="min-w-0">
          <p className="text-sm font-black truncate">{sub.name}</p>
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-0.5">
            {stat ? `${stat.plays || 0} 场 · ${stat.totalCount} 题` : '未参与'}
          </p>
        </div>
      </div>
      <div className="flex items-center space-x-5 flex-shrink-0">
        {ev.rankId === 'unranked' ? (
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
            还需 {ev.needMore ?? MIN_COUNT} 题评级
          </span>
        ) : (
          <>
            <div className="text-right">
              <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">均时</p>
              <p className="text-xs font-black tabular-nums">
                {avgMs < 1000 ? `${avgMs}ms` : `${(avgMs / 1000).toFixed(1)}s`}
              </p>
            </div>
            <div className="text-right">
              <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">正确</p>
              <p className="text-xs font-black tabular-nums">{accPct}%</p>
            </div>
            <span
              className="px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest"
              style={{ backgroundColor: `${rank.color}22`, color: rank.color }}
            >
              {rank.label}
            </span>
          </>
        )}
      </div>
    </div>
  );
};

// 供调试用：清空段位统计
export const RankDevTools = () => (
  <button
    onClick={() => {
      if (confirm('清空全部段位统计？此操作不可撤销。')) clearRankStats();
    }}
    className="text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-[#ff6b6b]"
  >
    重置段位
  </button>
);

export default RankDashboard;

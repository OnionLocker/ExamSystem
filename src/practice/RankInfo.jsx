import { useState } from 'react';
import { X, Trophy, Target, Layers, Activity } from 'lucide-react';
import { RANKS, THRESHOLDS, MIN_COUNT, getRank, SUB_BASE_MS } from './ranks.js';
import { CATEGORIES } from './generators.js';
import RankBadge from './RankBadge.jsx';

// ============================================================
// 段位图谱（说明 / 预览）
// 一个 modal 展示：8 段位预览 + 阈值表 + 聚合规则 + 子项基线时间
// ============================================================

const RankInfo = ({ onClose }) => {
  const [tab, setTab] = useState('overview');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[2rem] w-full max-w-4xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-8 py-6 border-b border-[#f2f0e9]">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-[#1a1a1a] text-[#fbc02d] flex items-center justify-center">
              <Trophy size={18} />
            </div>
            <div>
              <h2 className="text-lg font-black tracking-tight">段位图谱</h2>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-0.5">
                Rank System Codex
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full bg-[#f2f0e9] hover:bg-[#e8e6dd] flex items-center justify-center"
          >
            <X size={16} />
          </button>
        </div>

        {/* tab 切换 */}
        <div className="flex space-x-2 px-8 pt-5">
          <TabBtn id="overview" tab={tab} setTab={setTab} IconCmp={Trophy}>段位预览</TabBtn>
          <TabBtn id="thresholds" tab={tab} setTab={setTab} IconCmp={Target}>评定阈值</TabBtn>
          <TabBtn id="aggregation" tab={tab} setTab={setTab} IconCmp={Layers}>聚合规则</TabBtn>
          <TabBtn id="baselines" tab={tab} setTab={setTab} IconCmp={Activity}>基线时间</TabBtn>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          {tab === 'overview' && <OverviewPanel />}
          {tab === 'thresholds' && <ThresholdsPanel />}
          {tab === 'aggregation' && <AggregationPanel />}
          {tab === 'baselines' && <BaselinesPanel />}
        </div>
      </div>
    </div>
  );
};

// eslint-disable-next-line no-unused-vars
const TabBtn = ({ id, tab, setTab, IconCmp, children }) => (
  <button
    onClick={() => setTab(id)}
    className={`flex items-center space-x-2 px-4 py-2 rounded-full text-xs font-black uppercase tracking-widest transition-all ${
      tab === id
        ? 'bg-[#1a1a1a] text-[#fbc02d]'
        : 'bg-[#f2f0e9]/60 text-slate-500 hover:bg-[#f2f0e9]'
    }`}
  >
    <IconCmp size={13} />
    <span>{children}</span>
  </button>
);

// ----- 段位预览 -----
const OverviewPanel = () => (
  <div className="space-y-8">
    <div>
      <h3 className="text-base font-black mb-1">8 段位</h3>
      <p className="text-xs text-slate-500 font-medium mb-5">
        从未评级到王者，每一阶都是数千题数据的累计成果
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {RANKS.map((r) => (
          <div
            key={r.id}
            className="rounded-2xl p-5 flex flex-col items-center text-center"
            style={{
              backgroundColor: r.id === 'unranked' ? '#f8fafc' : `${r.color}10`,
              border: `1.5px solid ${r.color}30`,
            }}
          >
            <RankBadge rankId={r.id} size={72} />
            <p
              className="mt-3 text-base font-black italic tracking-tight"
              style={{ color: r.color }}
            >
              {r.label}
            </p>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-0.5">
              {r.short} · LEVEL {r.value}
            </p>
            {r.glow && (
              <p className="text-[9px] font-bold uppercase tracking-widest mt-2 text-slate-400">
                ✨ 发光段位
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  </div>
);

// ----- 评定阈值 -----
const ThresholdsPanel = () => (
  <div className="space-y-6">
    <div>
      <h3 className="text-base font-black mb-1">速度 × 准度</h3>
      <p className="text-xs text-slate-500 font-medium leading-relaxed">
        每个子项的段位由两个维度的<span className="font-black text-black"> AND </span>关系决定：
        <br />
        <span className="font-black text-black">平均用时</span> ≤ 子项基线 ×「倍率」<span className="font-black text-black"> 且</span>{' '}
        <span className="font-black text-black">正确率</span> ≥「准度门槛」
      </p>
    </div>

    <div className="overflow-hidden rounded-2xl border border-[#f2f0e9]">
      <table className="w-full text-sm">
        <thead className="bg-[#1a1a1a] text-white">
          <tr>
            <th className="text-left px-5 py-3 text-[10px] font-black uppercase tracking-widest">段位</th>
            <th className="text-center px-5 py-3 text-[10px] font-black uppercase tracking-widest">速度上限</th>
            <th className="text-center px-5 py-3 text-[10px] font-black uppercase tracking-widest">准度下限</th>
            <th className="text-left px-5 py-3 text-[10px] font-black uppercase tracking-widest">举例（基线 10s）</th>
          </tr>
        </thead>
        <tbody>
          {THRESHOLDS.map(([id, mul, acc]) => {
            const r = getRank(id);
            return (
              <tr
                key={id}
                className="border-t border-[#f2f0e9] hover:bg-[#f2f0e9]/30"
              >
                <td className="px-5 py-3">
                  <div className="flex items-center space-x-3">
                    <RankBadge rankId={id} size={32} />
                    <span className="font-black italic" style={{ color: r.color }}>
                      {r.label}
                    </span>
                  </div>
                </td>
                <td className="text-center px-5 py-3">
                  <span className="font-black tabular-nums">≤ {mul}× 基线</span>
                </td>
                <td className="text-center px-5 py-3">
                  <span className="font-black tabular-nums">≥ {(acc * 100).toFixed(0)}%</span>
                </td>
                <td className="px-5 py-3 text-xs text-slate-500 font-medium tabular-nums">
                  ≤ {(10 * mul).toFixed(0)}s · 正确率 ≥ {(acc * 100).toFixed(0)}%
                </td>
              </tr>
            );
          })}
          <tr className="border-t border-[#f2f0e9] bg-[#a17b5d]/5">
            <td className="px-5 py-3">
              <div className="flex items-center space-x-3">
                <RankBadge rankId="bronze" size={32} />
                <span className="font-black italic text-[#a17b5d]">青铜</span>
              </div>
            </td>
            <td colSpan="3" className="px-5 py-3 text-xs text-slate-500 font-medium">
              达不到白银的兜底（已答 ≥ {MIN_COUNT} 题但速度或准度不达标）
            </td>
          </tr>
          <tr className="border-t border-[#f2f0e9] bg-slate-50">
            <td className="px-5 py-3">
              <div className="flex items-center space-x-3">
                <RankBadge rankId="unranked" size={32} />
                <span className="font-black italic text-slate-400">未评级</span>
              </div>
            </td>
            <td colSpan="3" className="px-5 py-3 text-xs text-slate-500 font-medium">
              累计答题不足 {MIN_COUNT} 题（数据量太小，无法评级）
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div className="bg-[#fef3c7] border border-[#fbc02d]/40 rounded-2xl p-5">
      <p className="text-xs font-black text-[#7c2d12] mb-2 uppercase tracking-widest">
        ⚠️ 为什么是 AND 不是平均？
      </p>
      <p className="text-xs text-[#7c2d12] leading-relaxed font-medium">
        速度和准度<span className="font-black"> 任一</span>不达标都会卡在低段位。
        这是为了模拟真实省考——错题的代价是<span className="font-black"> 一秒思考 + 一分扣减</span>，
        所以"快但容易错" 与"慢但很准" 都不算合格的应试状态。
      </p>
    </div>
  </div>
);

// ----- 聚合规则 -----
const AggregationPanel = () => (
  <div className="space-y-6">
    <div className="bg-[#1a1a1a] text-white rounded-2xl p-6">
      <p className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-2">
        段位的三层加权聚合
      </p>
      <div className="space-y-3 text-sm font-medium">
        <div className="flex items-center space-x-3">
          <span className="w-6 h-6 rounded-full bg-[#fbc02d] text-[#1a1a1a] flex items-center justify-center text-[10px] font-black">1</span>
          <span>
            <span className="font-black">子项段位</span> = 该子项累计数据 → 速度 × 准度阈值
          </span>
        </div>
        <div className="flex items-center space-x-3">
          <span className="w-6 h-6 rounded-full bg-[#fbc02d] text-[#1a1a1a] flex items-center justify-center text-[10px] font-black">2</span>
          <span>
            <span className="font-black">分类段位</span> = Σ(子项段位×<span className="text-[#fbc02d]">出题频率权重</span>) / Σ(权重)
          </span>
        </div>
        <div className="flex items-center space-x-3">
          <span className="w-6 h-6 rounded-full bg-[#fbc02d] text-[#1a1a1a] flex items-center justify-center text-[10px] font-black">3</span>
          <span>
            <span className="font-black">整体段位</span> = Σ(分类段位×<span className="text-[#fbc02d]">分类分值权重</span>) / Σ(权重)
          </span>
        </div>
      </div>
    </div>

    {/* 分类间权重 */}
    <div className="bg-white border border-[#f2f0e9] rounded-2xl overflow-hidden">
      <div className="px-5 py-3 border-b border-[#f2f0e9]">
        <p className="text-sm font-black">四大类的分值权重</p>
        <p className="text-[10px] text-slate-400 font-bold mt-0.5">
          基于真实省考行测的分值占比
        </p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4">
        {CATEGORIES.map((c) => (
          <div key={c.id} className="px-5 py-4 border-r border-[#f2f0e9] last:border-r-0">
            <p className="text-xs font-black truncate">{c.name}</p>
            <div className="mt-2 flex items-baseline space-x-1">
              <span className="text-2xl font-black tabular-nums text-[#fbc02d]">
                {c.weight}
              </span>
              <span className="text-[10px] font-bold text-slate-400">%</span>
            </div>
            <div className="mt-2 h-1.5 bg-[#f2f0e9] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#fbc02d]"
                style={{ width: `${c.weight}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>

    {/* 子项频率权重示例 */}
    <div className="bg-[#fef3c7] border border-[#fbc02d]/40 rounded-2xl p-5">
      <p className="text-xs font-black text-[#7c2d12] mb-2 uppercase tracking-widest">
        💡 子项频率权重（1-5 星）
      </p>
      <p className="text-xs text-[#7c2d12] leading-relaxed font-medium mb-3">
        <span className="font-black">⭐⭐⭐⭐⭐ 5星</span>：每年必考（行程·相遇 / 排列组合 / 增长率 等）<br />
        <span className="font-black">⭐⭐⭐⭐ 4星</span>：高频（百化分 / 比重 / 倍数辨析）<br />
        <span className="font-black">⭐⭐⭐ 3星</span>：中频（工程 / 不定方程 / 鸡兔同笼）<br />
        <span className="font-black">⭐⭐ 2星</span>：偶尔出现（韩信点兵 / 方阵 / 单数乘法）
      </p>
      <p className="text-[11px] text-[#7c2d12] leading-relaxed font-medium border-t border-[#7c2d12]/15 pt-3">
        高频子项的段位<span className="font-black">会显著拉高</span>分类段位；
        练 100 题韩信点兵不如练 20 题相遇追及。
      </p>
    </div>

    <div className="bg-white border border-[#f2f0e9] rounded-2xl p-6">
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">
        加权举例
      </p>
      <p className="text-xs text-slate-600 font-medium leading-relaxed">
        假设你「数量关系」只评了 3 项：行程·相遇 <span className="font-black">钻石(5)</span> · 权重 5，
        浓度混合 <span className="font-black">黄金(3)</span> · 权重 5，
        鸡兔同笼 <span className="font-black">白银(2)</span> · 权重 3
        <br />
        <br />
        → 加权平均 = (5×5 + 3×5 + 2×3) / (5+5+3) = 46/13 = <span className="font-black">3.54 → 黄金（向上取）</span>
        <br />
        如果按等权（旧算法）：(5+3+2)/3 = 3.33 → 也是黄金
        <br />
        差异在<span className="font-black">权重不均衡</span>时才显现：高频项拿低段会更"惩罚"，反之亦然
      </p>
    </div>
  </div>
);

// ----- 基线时间（含权重）-----
const BaselinesPanel = () => (
  <div className="space-y-6">
    <div>
      <h3 className="text-base font-black mb-1">子项基线 + 频率权重</h3>
      <p className="text-xs text-slate-500 font-medium leading-relaxed">
        <span className="font-black text-black">基线</span> = 顶尖考生该子项的平均每题用时；
        <span className="font-black text-black"> 权重</span> = 该子项在真实省考的出题频率（1~5 星）。
      </p>
    </div>

    <div className="space-y-4">
      {CATEGORIES.map((cat) => (
        <div key={cat.id} className="border border-[#f2f0e9] rounded-2xl overflow-hidden">
          <div className="bg-[#f2f0e9]/40 px-5 py-3 flex items-center justify-between">
            <div>
              <p className="font-black text-sm">{cat.name}</p>
              <p className="text-[10px] font-bold text-slate-400 mt-0.5">{cat.desc}</p>
            </div>
            <div className="text-right">
              <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">分值权重</p>
              <p className="text-base font-black tabular-nums text-[#fbc02d]">{cat.weight}%</p>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-[#f2f0e9]">
            {cat.subs.map((s) => {
              const ms = SUB_BASE_MS[s.id];
              const w = s.weight ?? 1;
              return (
                <div key={s.id} className="bg-white px-4 py-3 flex items-center justify-between">
                  <div className="min-w-0 flex-1 pr-2">
                    <p className="text-xs font-bold truncate">{s.name}</p>
                    <p className="text-[10px] text-yellow-600 font-black tracking-wider mt-0.5">
                      {'★'.repeat(w)}{'☆'.repeat(5 - w)}
                    </p>
                  </div>
                  <span className="text-[11px] font-black tabular-nums text-[#fbc02d] flex-shrink-0">
                    {ms ? (ms < 10000 ? `${(ms / 1000).toFixed(1)}s` : `${(ms / 1000).toFixed(0)}s`) : '?'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  </div>
);

export default RankInfo;

import { useEffect, useMemo, useState } from 'react';
import { Layers, RotateCcw, ChevronRight, Check, X, Eye, Sparkles } from 'lucide-react';
import { DECKS, getCard } from './decks.js';
import {
  loadProgress,
  filterDueCards,
  getCardState,
  setCardState,
  review,
} from './sm2.js';

// ============================================================
// 抽认卡（Anki 风格 SM-2 间隔重复）
// 4 个状态：home（卡组列表）→ session（复习中）→ flipped（看背面）→ done
// ============================================================

const Flashcards = () => {
  const [activeDeckId, setActiveDeckId] = useState(null);
  const [, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);

  // 监听存储变化
  useEffect(() => {
    const onChange = () => bump();
    window.addEventListener('flashcards-change', onChange);
    return () => window.removeEventListener('flashcards-change', onChange);
  }, []);

  if (activeDeckId) {
    const deck = DECKS.find((d) => d.id === activeDeckId);
    return (
      <ReviewSession
        deck={deck}
        onExit={() => setActiveDeckId(null)}
      />
    );
  }

  return <DeckList onSelect={setActiveDeckId} />;
};

// ============== 卡组列表 ==============
const DeckList = ({ onSelect }) => {
  const progress = loadProgress();

  const decksWithStats = DECKS.map((d) => {
    const { due, newCards } = filterDueCards(d.cards);
    const learned = d.cards.filter((c) => progress[c.id]).length;
    return { ...d, dueCount: due.length, newCount: newCards.length, learnedCount: learned };
  });

  const totalDue = decksWithStats.reduce((s, d) => s + d.dueCount + d.newCount, 0);

  return (
    <div className="space-y-8">
      {/* 头部 */}
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-8 relative overflow-hidden">
        <div className="absolute -top-10 -right-10 w-56 h-56 rounded-full blur-[80px] bg-[#fbc02d] opacity-30 pointer-events-none" />
        <div className="relative">
          <div className="flex items-center space-x-3 mb-1">
            <Layers size={20} className="text-[#fbc02d]" />
            <p className="text-[10px] font-black uppercase tracking-[0.25em] text-white/40">
              Spaced Repetition
            </p>
          </div>
          <h2 className="text-3xl font-black italic mt-1">
            今日待复习 <span className="text-[#fbc02d]">{totalDue}</span> 张
          </h2>
          <p className="text-xs font-bold text-white/50 mt-2 max-w-xl leading-relaxed">
            每张卡按 SM-2 算法自动安排：会的拉长间隔，不会的频繁回头。地铁上 10 分钟过 50 张卡，记住的远超死记硬背。
          </p>
        </div>
      </div>

      {/* 卡组网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {decksWithStats.map((d) => (
          <button
            key={d.id}
            onClick={() => onSelect(d.id)}
            disabled={d.dueCount + d.newCount === 0 && d.learnedCount === d.cards.length}
            className="group relative bg-white rounded-3xl p-6 text-left hover:shadow-xl hover:-translate-y-1 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
          >
            <div
              className="absolute top-0 left-0 right-0 h-1.5 rounded-t-3xl"
              style={{ backgroundColor: d.color }}
            />
            <div className="flex items-start justify-between mb-3">
              <p className="text-base font-black tracking-tight">{d.name}</p>
              <span
                className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full"
                style={{ backgroundColor: `${d.color}20`, color: d.color }}
              >
                {d.cards.length} 张
              </span>
            </div>
            <p className="text-xs text-slate-500 font-medium mb-4 leading-relaxed">{d.desc}</p>

            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="bg-[#f2f0e9]/40 rounded-xl py-2.5">
                <p className="text-2xl font-black tabular-nums" style={{ color: d.color }}>
                  {d.dueCount}
                </p>
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mt-0.5">
                  待复习
                </p>
              </div>
              <div className="bg-[#f2f0e9]/40 rounded-xl py-2.5">
                <p className="text-2xl font-black tabular-nums text-slate-700">
                  {d.newCount}
                </p>
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mt-0.5">
                  待新学
                </p>
              </div>
              <div className="bg-[#f2f0e9]/40 rounded-xl py-2.5">
                <p className="text-2xl font-black tabular-nums text-slate-700">
                  {d.learnedCount}
                </p>
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mt-0.5">
                  已学
                </p>
              </div>
            </div>

            <div className="mt-4 flex items-center justify-end text-xs font-black uppercase tracking-widest text-slate-400 group-hover:text-[#fbc02d] transition-colors">
              <span>开始</span>
              <ChevronRight size={14} className="ml-1" />
            </div>
          </button>
        ))}
      </div>

      {/* 评分说明 */}
      <div className="bg-[#fef3c7] border border-[#fbc02d]/40 rounded-2xl p-5">
        <p className="text-xs font-black text-[#7c2d12] mb-2 uppercase tracking-widest">
          💡 评分规则
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-[#7c2d12] font-medium">
          <div><span className="font-black">不会</span>：4 小时后再来</div>
          <div><span className="font-black">困难</span>：间隔小幅增加</div>
          <div><span className="font-black">一般</span>：标准间隔（×EF）</div>
          <div><span className="font-black">简单</span>：间隔大幅拉长</div>
        </div>
      </div>
    </div>
  );
};

// ============== 复习会话 ==============
const ReviewSession = ({ deck, onExit }) => {
  // 取出所有要做的卡（到期 + 新卡），shuffle
  const queue = useMemo(() => {
    const { due, newCards } = filterDueCards(deck.cards);
    // 到期优先，再上新卡
    const arr = [...due, ...newCards];
    // shuffle
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck.id]);

  const [idx, setIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [stats, setStats] = useState({ correct: 0, hard: 0, fail: 0 });

  const card = queue[idx];

  // 键盘快捷键
  useEffect(() => {
    const onKey = (e) => {
      if (!card) return;
      if (e.key === 'Escape') onExit();
      if (e.key === ' ') {
        e.preventDefault();
        setFlipped((f) => !f);
      }
      if (flipped) {
        if (e.key === '1') answer(0);
        if (e.key === '2') answer(3);
        if (e.key === '3') answer(4);
        if (e.key === '4') answer(5);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [card, flipped]);

  const answer = (q) => {
    if (!card) return;
    const newState = review(getCardState(card.id), q);
    setCardState(card.id, newState);
    setStats((s) => ({
      ...s,
      correct: s.correct + (q >= 4 ? 1 : 0),
      hard: s.hard + (q === 3 ? 1 : 0),
      fail: s.fail + (q === 0 ? 1 : 0),
    }));
    setFlipped(false);
    setIdx((i) => i + 1);
  };

  if (!card) {
    return <SessionDone deck={deck} stats={stats} onExit={onExit} />;
  }

  const progressPct = (idx / queue.length) * 100;

  return (
    <div className="space-y-6">
      {/* 顶栏 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <button
          onClick={onExit}
          className="text-xs font-black uppercase tracking-widest text-slate-400 hover:text-black flex items-center space-x-1.5"
        >
          <X size={14} />
          <span>退出</span>
        </button>
        <div className="text-xs font-black tabular-nums">
          <span style={{ color: deck.color }}>{idx + 1}</span>
          <span className="text-slate-400"> / {queue.length}</span>
          <span className="ml-3 text-slate-400">{deck.name}</span>
        </div>
      </div>

      {/* 进度条 */}
      <div className="h-1 bg-[#f2f0e9] rounded-full overflow-hidden">
        <div
          className="h-full transition-all duration-300"
          style={{ width: `${progressPct}%`, backgroundColor: deck.color }}
        />
      </div>

      {/* 卡片本体 */}
      <div
        className="bg-white rounded-[2.5rem] p-10 md:p-16 min-h-[360px] flex items-center justify-center cursor-pointer shadow-sm hover:shadow-md transition-all"
        onClick={() => setFlipped((f) => !f)}
      >
        <div className="text-center max-w-2xl">
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400 mb-4">
            {flipped ? 'Back · 释义' : 'Front · 题面'}
          </p>
          <p className={`tracking-tight leading-relaxed ${
            flipped ? 'text-base md:text-lg font-medium text-slate-700' : 'text-3xl md:text-4xl font-black italic'
          }`}>
            {flipped ? card.back : card.front}
          </p>
          {!flipped && (
            <p className="mt-8 text-[10px] font-black uppercase tracking-widest text-slate-300">
              点击卡片查看释义 · Space
            </p>
          )}
        </div>
      </div>

      {/* 评分按钮（只在翻开时显示）*/}
      {flipped ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <RateBtn label="不会" sub="4 小时后" color="#ef4444" key1="1" onClick={() => answer(0)} />
          <RateBtn label="困难" sub="小幅增加" color="#f97316" key1="2" onClick={() => answer(3)} />
          <RateBtn label="一般" sub="标准间隔" color="#3b82f6" key1="3" onClick={() => answer(4)} />
          <RateBtn label="简单" sub="大幅拉长" color="#22c55e" key1="4" onClick={() => answer(5)} />
        </div>
      ) : (
        <button
          onClick={() => setFlipped(true)}
          className="w-full bg-[#1a1a1a] text-white py-4 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-[#fbc02d] hover:text-[#1a1a1a] transition-all flex items-center justify-center space-x-2"
        >
          <Eye size={14} />
          <span>查看释义</span>
        </button>
      )}
    </div>
  );
};

const RateBtn = ({ label, sub, color, key1, onClick }) => (
  <button
    onClick={onClick}
    className="bg-white hover:scale-105 transition-all rounded-2xl p-4 text-center group relative"
    style={{ borderTop: `3px solid ${color}` }}
  >
    <p className="text-base font-black tracking-tight" style={{ color }}>
      {label}
    </p>
    <p className="text-[10px] font-bold text-slate-400 mt-0.5">{sub}</p>
    <span
      className="absolute top-2 right-2 w-5 h-5 rounded-full bg-[#f2f0e9] text-slate-400 text-[10px] font-black flex items-center justify-center"
      title={`快捷键 ${key1}`}
    >
      {key1}
    </span>
  </button>
);

// ============== 完成页 ==============
const SessionDone = ({ deck, stats, onExit }) => (
  <div className="space-y-6 text-center py-12">
    <div className="inline-flex w-20 h-20 rounded-3xl bg-[#fbc02d] text-[#1a1a1a] items-center justify-center">
      <Sparkles size={32} strokeWidth={2.4} />
    </div>
    <div>
      <h3 className="text-2xl font-black italic mb-1">本组复习完成 ✨</h3>
      <p className="text-sm font-bold text-slate-500">
        《{deck.name}》今日已无待复习卡片
      </p>
    </div>

    <div className="grid grid-cols-3 gap-4 max-w-md mx-auto">
      <StatBox label="掌握" value={stats.correct} color="#22c55e" Icon={Check} />
      <StatBox label="困难" value={stats.hard} color="#f97316" Icon={Eye} />
      <StatBox label="不会" value={stats.fail} color="#ef4444" Icon={RotateCcw} />
    </div>

    <button
      onClick={onExit}
      className="bg-[#1a1a1a] text-white px-8 py-3 rounded-2xl text-xs font-black uppercase tracking-widest hover:bg-[#fbc02d] hover:text-[#1a1a1a] transition-all"
    >
      返回卡组
    </button>
  </div>
);

const StatBox = ({ label, value, color, Icon }) => (
  <div className="bg-white rounded-2xl p-5">
    <Icon size={16} style={{ color }} className="mx-auto mb-1.5" />
    <p className="text-3xl font-black tabular-nums" style={{ color }}>
      {value}
    </p>
    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-1">
      {label}
    </p>
  </div>
);

export default Flashcards;

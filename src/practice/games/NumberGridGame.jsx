import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, RotateCcw, Play, Trophy, Zap, Timer as TimerIcon } from 'lucide-react';
import { playCorrect, playWrong } from '../sfx.js';
import { cloudGet, cloudSet } from '../../cloudStorage.js';

// ============================================================
// 点数字小游戏（Schulte Table）
// --------------------------------------
// 5×5 / 6×6 / 7×7 / 8×8 / 9×9 / 10×10 网格，打乱 1~N，从 1 依次点击到 N。
// 记录每种规格的最佳用时、平均用时、总场次。
// 点错会有抖动反馈 + 惩罚计时。
// ============================================================

const STORAGE_KEY = 'numeric_games_number_grid_v1';
const PENALTY_MS = 1000; // 点错惩罚 1 秒

const SIZES = [
  { n: 5, label: '5 × 5', desc: '标准训练', hintColor: '#fbc02d' },
  { n: 6, label: '6 × 6', desc: '高压挑战', hintColor: '#ff6b6b' },
  { n: 7, label: '7 × 7', desc: '进阶压缩', hintColor: '#a855f7' },
  { n: 8, label: '8 × 8', desc: '快速搜索', hintColor: '#3b82f6' },
  { n: 9, label: '9 × 9', desc: '超密集', hintColor: '#14b8a6' },
  { n: 10, label: '10 × 10', desc: '极限专注', hintColor: '#f97316' },
];

// 工具
const loadStore = () => cloudGet(STORAGE_KEY, {});
const saveStore = (s) => cloudSet(STORAGE_KEY, s);
const fmtTime = (ms) => {
  if (ms == null || ms === Infinity) return '—';
  const s = ms / 1000;
  if (s < 10) return `${s.toFixed(2)} s`;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  const rem = Math.floor(s % 60);
  return `${m}:${String(rem).padStart(2, '0')}`;
};
const shuffle = (arr) => {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

const NumberGridGame = ({ onBack }) => {
  const [size, setSize] = useState(5);
  const [state, setState] = useState('idle'); // idle | playing | done
  const [numbers, setNumbers] = useState([]); // 打乱后的数字数组（与网格一一对应）
  const [next, setNext] = useState(1);
  const [startedAt, setStartedAt] = useState(0);
  const [penaltyMs, setPenaltyMs] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [wrongIdx, setWrongIdx] = useState(null); // 最近点错的格子
  const [lastResult, setLastResult] = useState(null); // { size, durationMs, wrongCount, isNewBest }
  const [store, setStore] = useState(loadStore());
  const wrongCountRef = useRef(0);
  const rafRef = useRef(null);

  const total = size * size;
  const statsForSize = store[size] || { best: null, plays: 0, totalMs: 0, lastPlayedAt: 0 };

  // 驱动计时显示
  useEffect(() => {
    if (state !== 'playing') return;
    const tick = () => {
      setElapsed(Date.now() - startedAt + penaltyMs);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [state, startedAt, penaltyMs]);

  const start = useCallback(() => {
    const nums = shuffle(Array.from({ length: total }, (_, i) => i + 1));
    setNumbers(nums);
    setNext(1);
    setPenaltyMs(0);
    setElapsed(0);
    wrongCountRef.current = 0;
    setWrongIdx(null);
    setStartedAt(Date.now());
    setState('playing');
    setLastResult(null);
  }, [total]);

  const handleClick = (idx) => {
    if (state !== 'playing') return;
    const v = numbers[idx];
    if (v === next) {
      if (next === total) {
        // 完成
        playCorrect();
        const duration = Date.now() - startedAt + penaltyMs;
        const prev = store[size] || { best: null, plays: 0, totalMs: 0 };
        const isNewBest = prev.best == null || duration < prev.best;
        const nextStore = {
          ...store,
          [size]: {
            best: isNewBest ? duration : prev.best,
            plays: (prev.plays || 0) + 1,
            totalMs: (prev.totalMs || 0) + duration,
            lastPlayedAt: Date.now(),
            lastDuration: duration,
          },
        };
        setStore(nextStore);
        saveStore(nextStore);
        setLastResult({
          size,
          durationMs: duration,
          wrongCount: wrongCountRef.current,
          isNewBest,
          prevBest: prev.best,
        });
        setState('done');
      } else {
        setNext((n) => n + 1);
      }
    } else {
      // 点错：扣时 + 抖动
      playWrong();
      wrongCountRef.current += 1;
      setPenaltyMs((p) => p + PENALTY_MS);
      setWrongIdx(idx);
      setTimeout(() => setWrongIdx(null), 320);
    }
  };

  const reset = () => {
    setState('idle');
    setLastResult(null);
  };

  const resetAllStats = () => {
    if (!confirm('清空所有规格的最佳成绩？此操作不可恢复。')) return;
    saveStore({});
    setStore({});
  };

  return (
    <div className="max-w-[1360px] mx-auto space-y-6">
      {/* 顶部栏 */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">返回</span>
        </button>
        <h2 className="text-2xl font-black italic">点数字</h2>
        <button
          onClick={resetAllStats}
          title="清空历史最佳成绩"
          className="text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-[#ff6b6b] transition-colors"
        >
          重置成绩
        </button>
      </div>

      {/* 规格选择 */}
      <div className="bg-white rounded-[2rem] p-5 border border-[#f2f0e9]">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
          选择规格
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {SIZES.map((s) => {
            const active = s.n === size;
            const st = store[s.n];
            return (
              <button
                key={s.n}
                onClick={() => {
                  if (state === 'playing') return;
                  setSize(s.n);
                  setState('idle');
                }}
                disabled={state === 'playing'}
                className={`p-3 rounded-2xl border-2 transition-all text-left ${
                  active
                    ? 'border-[#1a1a1a] bg-[#1a1a1a] text-white'
                    : 'border-[#f2f0e9] bg-white hover:border-slate-300'
                } ${state === 'playing' ? 'opacity-40 cursor-not-allowed' : ''}`}
              >
                <p className="text-sm font-black italic">{s.label}</p>
                <p
                  className={`text-[10px] font-black uppercase tracking-widest mt-0.5 ${
                    active ? 'text-white/60' : 'text-slate-400'
                  }`}
                >
                  {s.desc}
                </p>
                <p
                  className={`text-[10px] font-black tabular-nums mt-2 ${
                    active ? 'text-[#fbc02d]' : 'text-slate-400'
                  }`}
                >
                  最佳 {fmtTime(st?.best)}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* 游戏区 */}
      <div className="relative isolate px-1 py-3 md:px-4 md:py-5">
        <div className="absolute left-8 top-6 h-32 w-32 rounded-full bg-[#fbc02d]/20 blur-3xl pointer-events-none" />
        <div className="absolute right-8 bottom-8 h-32 w-32 rounded-full bg-[#60a5fa]/18 blur-3xl pointer-events-none" />
        <div className="absolute inset-0 rounded-[3rem] bg-white/55 backdrop-blur-2xl border border-white/70 shadow-[0_20px_80px_rgba(15,23,42,0.08)]" />

        <div className="relative bg-[#1a1a1a]/96 text-white rounded-[2.5rem] p-6 md:p-8 overflow-hidden border border-white/8 shadow-[0_20px_60px_rgba(15,23,42,0.28)]">
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.08),transparent_32%),radial-gradient(circle_at_bottom_right,rgba(251,192,45,0.12),transparent_28%)]" />

          <div className="relative">
            {/* 信息栏 */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center space-x-5">
                <InfoCell
                  icon={Zap}
                  label="下一个"
                  value={state === 'playing' ? next : '—'}
                  accent="#fbc02d"
                  big
                />
                <InfoCell
                  icon={TimerIcon}
                  label="计时"
                  value={fmtTime(state === 'done' ? lastResult?.durationMs : elapsed)}
                  accent="#60a5fa"
                />
                {state === 'playing' && penaltyMs > 0 && (
                  <InfoCell
                    label="罚时"
                    value={`+${(penaltyMs / 1000).toFixed(0)}s`}
                    accent="#ff6b6b"
                  />
                )}
              </div>
              <div className="text-right">
                <p className="text-[10px] font-black uppercase tracking-widest text-white/40">
                  本规格最佳
                </p>
                <p className="text-lg font-black text-[#fbc02d] tabular-nums">
                  {fmtTime(statsForSize.best)}
                </p>
                <p className="text-[10px] font-black text-white/30 tabular-nums mt-0.5">
                  {statsForSize.plays} 局 · 均{' '}
                  {statsForSize.plays ? fmtTime(statsForSize.totalMs / statsForSize.plays) : '—'}
                </p>
              </div>
            </div>

            {/* 网格 / 起始屏 / 结果屏 */}
            {state === 'idle' && (
              <IdleScreen size={size} total={total} best={statsForSize.best} onStart={start} />
            )}

            {state === 'playing' && (
              <Grid
                size={size}
                numbers={numbers}
                next={next}
                wrongIdx={wrongIdx}
                onClick={handleClick}
              />
            )}

            {state === 'done' && lastResult && (
              <DoneScreen
                result={lastResult}
                onRetry={start}
                onBack={reset}
              />
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-6px); }
          75% { transform: translateX(6px); }
        }
        @keyframes cellPop {
          0% { transform: scale(0.9); opacity: 0.4; }
          50% { transform: scale(1.06); }
          100% { transform: scale(1); opacity: 1; }
        }
        @keyframes doneGlow {
          0% { transform: scale(0.6); opacity: 0; }
          60% { transform: scale(1.15); opacity: 1; }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
};

const InfoCell = ({ icon: Icon, label, value, accent, big }) => (
  <div>
    <div className="flex items-center space-x-1.5 mb-1">
      {Icon && <Icon size={12} style={{ color: accent }} />}
      <span className="text-[10px] font-black uppercase tracking-widest text-white/40">
        {label}
      </span>
    </div>
    <p
      className={`font-black tabular-nums ${big ? 'text-4xl' : 'text-xl'}`}
      style={{ color: accent }}
    >
      {value}
    </p>
  </div>
);

const IdleScreen = ({ size, total, best, onStart }) => (
  <div className="flex flex-col items-center py-16 space-y-6">
    <div
      className="w-20 h-20 rounded-2xl flex items-center justify-center"
      style={{ backgroundColor: '#fbc02d', color: '#1a1a1a' }}
    >
      <span className="text-3xl font-black tabular-nums">{size}²</span>
    </div>
    <div className="text-center">
      <p className="text-2xl font-black italic">从 1 点到 {total}</p>
      <p className="text-sm font-medium text-white/50 mt-1.5 max-w-sm">
        数字会被随机打乱。依次找到并点击，越快越好。
        <span className="text-[#ff6b6b]"> 点错罚 1 秒。</span>
      </p>
    </div>
    {best && (
      <p className="text-[11px] font-black text-white/40 uppercase tracking-widest tabular-nums">
        历史最佳 · {fmtTime(best)}
      </p>
    )}
    <button
      onClick={onStart}
      className="bg-[#fbc02d] text-black font-black px-10 py-4 rounded-2xl hover:brightness-110 transition-all uppercase tracking-widest text-xs flex items-center space-x-2"
    >
      <Play size={14} />
      <span>开始</span>
    </button>
  </div>
);

const Grid = ({ size, numbers, next, wrongIdx, onClick }) => {
  // 根据规格动态调整单元格大小 / 字号
  const cellClass = useMemo(() => {
    const map = {
      5: { size: 'h-[5rem] md:h-[6rem]', font: 'text-4xl md:text-5xl', gap: 'gap-3' },
      6: { size: 'h-[4.5rem] md:h-[5rem]', font: 'text-3xl md:text-4xl', gap: 'gap-2.5' },
      7: { size: 'h-[4rem] md:h-[4.5rem]', font: 'text-2xl md:text-3xl', gap: 'gap-2' },
      8: { size: 'h-[3.5rem] md:h-[4rem]', font: 'text-xl md:text-2xl', gap: 'gap-2' },
      9: { size: 'h-[3.2rem] md:h-[3.7rem]', font: 'text-lg md:text-xl', gap: 'gap-1.5' },
      10: { size: 'h-[3rem] md:h-[3.5rem]', font: 'text-base md:text-lg', gap: 'gap-1.5' },
    };
    return map[size] || map[5];
  }, [size]);

  return (
    <div
      className={`grid ${cellClass.gap} select-none`}
      style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}
    >
      {numbers.map((v, idx) => {
        const done = v < next;
        const wrong = idx === wrongIdx;
        return (
          <button
            key={idx}
            onClick={() => onClick(idx)}
            className={`${cellClass.size} ${cellClass.font} rounded-xl font-black tabular-nums transition-all duration-100 ${
              done
                ? 'bg-white/5 text-white/20 cursor-default'
                : 'bg-white text-[#1a1a1a] hover:bg-[#fbc02d] active:scale-95 shadow-sm'
            }`}
            style={{
              animation: wrong
                ? 'shake 280ms ease-in-out'
                : done
                  ? undefined
                  : 'cellPop 200ms ease-out',
              backgroundColor: wrong ? '#ff6b6b' : undefined,
              color: wrong ? '#ffffff' : undefined,
            }}
          >
            {v}
          </button>
        );
      })}
    </div>
  );
};

const DoneScreen = ({ result, onRetry, onBack }) => (
  <div className="flex flex-col items-center py-12 space-y-5" style={{ animation: 'doneGlow 0.6s ease-out' }}>
    <div
      className={`w-20 h-20 rounded-2xl flex items-center justify-center ${
        result.isNewBest ? 'bg-[#fbc02d] text-black' : 'bg-white/10 text-white'
      }`}
    >
      <Trophy size={36} />
    </div>
    <div className="text-center">
      <p className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-1">
        {result.size}×{result.size} 完成
      </p>
      <p className="text-5xl font-black tabular-nums">{fmtTime(result.durationMs)}</p>
      <p className="text-sm font-medium text-white/50 mt-2">
        点错 <span className="font-black text-[#ff6b6b]">{result.wrongCount}</span> 次
        {result.wrongCount > 0 && (
          <> · 含罚时 +{(result.wrongCount * PENALTY_MS) / 1000}s</>
        )}
      </p>
    </div>
    {result.isNewBest ? (
      <div className="bg-[#fbc02d] text-black px-5 py-2 rounded-full text-xs font-black uppercase tracking-widest">
        🎉 打破纪录！原 {fmtTime(result.prevBest)}
      </div>
    ) : (
      <p className="text-[11px] font-black text-white/40 uppercase tracking-widest tabular-nums">
        距最佳 +{fmtTime(result.durationMs - (result.prevBest || result.durationMs))}
      </p>
    )}
    <div className="flex space-x-3 pt-2">
      <button
        onClick={onRetry}
        className="bg-[#fbc02d] text-black font-black px-8 py-3 rounded-2xl hover:brightness-110 transition-all uppercase tracking-widest text-xs flex items-center space-x-2"
      >
        <RotateCcw size={14} />
        <span>再来一局</span>
      </button>
      <button
        onClick={onBack}
        className="bg-white/10 text-white font-black px-6 py-3 rounded-2xl hover:bg-white/20 transition-all uppercase tracking-widest text-xs"
      >
        换规格
      </button>
    </div>
  </div>
);

export default NumberGridGame;

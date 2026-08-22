import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { playCorrect, playWrong } from '../sfx.js';
import { cloudGet, cloudSet } from '../../cloudStorage.js';
import {
  ChevronLeft,
  RotateCcw,
  Play,
  Trophy,
  Eye,
  Layers,
  Check,
  X,
  ArrowDownToLine,
  ArrowUpFromLine,
} from 'lucide-react';

// ============================================================
// 数字记忆广度（Digit Span）
// --------------------------------------
// 屏幕按固定间隔（默认 800ms）依次显示 N 个数字，全部消失后让用户回忆。
// 模式：
//   ● forward —— 顺序回忆（基础）
//   ● backward —— 倒序回忆（高级，更接近资料分析"基期/现期"切换的工作记忆负担）
// 适应性算法：连对 2 次 → N+1；连错 2 次 → N-1。每场 8 轮。
// ============================================================

const STORAGE_KEY = 'numeric_games_digit_span_v1';
const TRIALS_PER_SESSION = 8;
const FLASH_MS = 800; // 每个数字停留时间
const GAP_MS = 200; // 数字之间的间隔
const COUNTDOWN_MS = 1500; // 开始前的预告
const RECALL_FEEDBACK_MS = 900;

const MODES = [
  {
    id: 'forward',
    label: '顺序回忆',
    desc: '看到什么按顺序敲什么',
    icon: ArrowDownToLine,
    color: '#22c55e',
  },
  {
    id: 'backward',
    label: '倒序回忆',
    desc: '看完后倒着敲（推荐）',
    icon: ArrowUpFromLine,
    color: '#8d7348',
  },
];

const START_LEN_DEFAULT = 5;
const MIN_LEN = 3;
const MAX_LEN = 12;

// ----------------- 工具 -----------------
const randDigit = () => Math.floor(Math.random() * 10);
// 生成不连续重复的数字串（更难记，更像考试场景）
const genSequence = (len) => {
  const arr = [];
  let last = -1;
  for (let i = 0; i < len; i++) {
    let d;
    do {
      d = randDigit();
    } while (d === last);
    arr.push(d);
    last = d;
  }
  return arr;
};
const loadStore = () => cloudGet(STORAGE_KEY, {});
const saveStore = (s) => cloudSet(STORAGE_KEY, s);
const arrEq = (a, b) =>
  a.length === b.length && a.every((v, i) => v === b[i]);

// ============================================================
// 主组件
// ============================================================
const DigitSpanGame = ({ onBack }) => {
  const [modeId, setModeId] = useState('backward');
  const [startLen, setStartLen] = useState(START_LEN_DEFAULT);
  const [phase, setPhase] = useState('idle');
  // idle | countdown | flash | recall | feedback | done

  const [store, setStore] = useState(loadStore());
  const [length, setLength] = useState(START_LEN_DEFAULT);
  const [trial, setTrial] = useState(0);
  const [sequence, setSequence] = useState([]);
  const [flashIdx, setFlashIdx] = useState(0);
  const [input, setInput] = useState([]);
  const [lastResult, setLastResult] = useState(null); // 'ok' | 'wrong'
  const [streakOk, setStreakOk] = useState(0);
  const [streakBad, setStreakBad] = useState(0);
  const [history, setHistory] = useState([]); // 每轮 {len, ok, expected, given}
  const [maxOkLen, setMaxOkLen] = useState(0);

  const timerRef = useRef(null);
  const mode = useMemo(() => MODES.find((m) => m.id === modeId), [modeId]);
  const stats = store[modeId] || { plays: 0, bestSpan: null, lastPlayedAt: 0 };

  // 清理定时器
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  // 倒计时（开始）
  useEffect(() => {
    if (phase !== 'countdown') return undefined;
    timerRef.current = setTimeout(() => {
      // 进入闪烁
      const seq = genSequence(length);
      setSequence(seq);
      setFlashIdx(0);
      setPhase('flash');
    }, COUNTDOWN_MS);
    return () => clearTimeout(timerRef.current);
  }, [length, phase]);

  // 闪烁阶段：依次显示
  useEffect(() => {
    if (phase !== 'flash') return undefined;
    if (flashIdx >= sequence.length) {
      // 闪完了，进入回忆阶段
      timerRef.current = setTimeout(() => {
        setInput([]);
        setPhase('recall');
      }, GAP_MS);
      return () => clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      setFlashIdx((i) => i + 1);
    }, FLASH_MS + GAP_MS);
    return () => clearTimeout(timerRef.current);
  }, [phase, flashIdx, sequence.length]);

  // 提交一题（在 input 满了之后会调用）
  const finishTrial = useCallback(
    (finalInput) => {
      const expected =
        modeId === 'backward' ? sequence.slice().reverse() : sequence.slice();
      const ok = arrEq(finalInput, expected);
      const newHistory = [...history, { len: length, ok, expected, given: finalInput }];
      let newStreakOk = ok ? streakOk + 1 : 0;
      let newStreakBad = ok ? 0 : streakBad + 1;
      let newLength = length;

      if (newStreakOk >= 2 && length < MAX_LEN) {
        newLength = length + 1;
        newStreakOk = 0;
      }
      if (newStreakBad >= 2 && length > MIN_LEN) {
        newLength = length - 1;
        newStreakBad = 0;
      }

      const newMax = ok ? Math.max(maxOkLen, length) : maxOkLen;

      if (ok) playCorrect(); else playWrong();

      setHistory(newHistory);
      setStreakOk(newStreakOk);
      setStreakBad(newStreakBad);
      setMaxOkLen(newMax);
      setLastResult(ok ? 'ok' : 'wrong');
      setPhase('feedback');

      timerRef.current = setTimeout(() => {
        if (trial + 1 >= TRIALS_PER_SESSION) {
          // 结束
          const prev = store[modeId] || { plays: 0, bestSpan: null };
          const isBest = prev.bestSpan == null || newMax > prev.bestSpan;
          const next = {
            plays: (prev.plays || 0) + 1,
            bestSpan: isBest ? newMax : prev.bestSpan,
            lastPlayedAt: Date.now(),
          };
          const newStore = { ...store, [modeId]: next };
          setStore(newStore);
          saveStore(newStore);
          setPhase('done');
        } else {
          setLength(newLength);
          setTrial((t) => t + 1);
          setSequence([]);
          setInput([]);
          setLastResult(null);
          setPhase('countdown');
        }
      }, RECALL_FEEDBACK_MS);
    },
    [
      history,
      length,
      maxOkLen,
      modeId,
      sequence,
      store,
      streakBad,
      streakOk,
      trial,
    ],
  );

  // 输入数字
  const addDigit = useCallback(
    (d) => {
      if (phase !== 'recall') return;
      setInput((prev) => {
        if (prev.length >= length) return prev;
        const next = [...prev, d];
        if (next.length === length) {
          // 立即结算（用最新 next）
          setTimeout(() => finishTrial(next), 0);
        }
        return next;
      });
    },
    [finishTrial, length, phase],
  );

  const removeDigit = useCallback(() => {
    if (phase !== 'recall') return;
    setInput((prev) => prev.slice(0, -1));
  }, [phase]);

  // 键盘
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (phase === 'recall') {
        if (e.key >= '0' && e.key <= '9') {
          e.preventDefault();
          addDigit(parseInt(e.key, 10));
        } else if (e.key === 'Backspace') {
          e.preventDefault();
          removeDigit();
        }
      }
      if (phase !== 'idle' && e.key === 'Escape') {
        e.preventDefault();
        if (timerRef.current) clearTimeout(timerRef.current);
        setPhase('idle');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [addDigit, phase, removeDigit]);

  // 启动
  const startSession = () => {
    setLength(startLen);
    setTrial(0);
    setSequence([]);
    setInput([]);
    setStreakOk(0);
    setStreakBad(0);
    setHistory([]);
    setMaxOkLen(0);
    setLastResult(null);
    setPhase('countdown');
  };

  // -------------- idle --------------
  if (phase === 'idle') {
    return (
      <div className="w-full max-w-3xl mx-auto px-2 sm:px-4 space-y-5 sm:space-y-7">
        <div className="flex items-center justify-between">
          <button
            onClick={onBack}
            className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
          >
            <ChevronLeft size={18} />
            <span className="text-xs font-black uppercase tracking-widest">返回</span>
          </button>
          <div className="flex items-center space-x-2">
            <Layers size={18} className="text-[#6b5428]" />
            <h2 className="text-xl sm:text-2xl font-black italic">数字记忆广度</h2>
          </div>
          <span className="w-14" />
        </div>

        <div className="bg-[#1a1a1a] text-white rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-7">
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[#6b5428]">
            训练目标
          </p>
          <h3 className="text-lg sm:text-xl font-black italic mt-2">
            扩容 working memory，治资料分析"翻页找数据"
          </h3>
          <p className="text-xs sm:text-sm font-medium opacity-70 mt-3 leading-relaxed">
            屏幕会按 0.8s 间隔依次闪 N 个数字，消失后让你
            <span className="text-[#6b5428] font-black mx-1">倒序</span>
            敲出来。倒序模式比顺序难一倍，但正是练"边记新的、边动旧的"。
            连对 2 次自动 +1 位，连错 2 次 -1 位，每场 {TRIALS_PER_SESSION} 轮。
          </p>
        </div>

        {/* 模式 */}
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
            选择模式
          </p>
          <div className="grid grid-cols-2 gap-3">
            {MODES.map((m) => {
              const Icon = m.icon;
              const active = m.id === modeId;
              const ms = store[m.id];
              return (
                <button
                  key={m.id}
                  onClick={() => setModeId(m.id)}
                  className={`p-4 sm:p-5 rounded-2xl text-left transition-all border ${
                    active
                      ? 'bg-[#1a1a1a] text-white border-[#1a1a1a] shadow-lg shadow-black/10'
                      : 'bg-white border-[#e8d5b0] hover:border-[#1a1a1a]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center"
                      style={{
                        backgroundColor: active ? m.color : `${m.color}22`,
                        color: active ? '#1a1a1a' : m.color,
                      }}
                    >
                      <Icon size={18} />
                    </div>
                    {ms?.bestSpan != null && (
                      <span className="text-[9px] font-black uppercase tracking-widest opacity-60">
                        最高 {ms.bestSpan} 位
                      </span>
                    )}
                  </div>
                  <p className="text-sm sm:text-base font-black italic">{m.label}</p>
                  <p
                    className={`text-[11px] sm:text-xs font-medium mt-1 ${
                      active ? 'opacity-70' : 'text-slate-400'
                    }`}
                  >
                    {m.desc}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* 起始位数 */}
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
            起始位数
          </p>
          <div className="flex flex-wrap gap-2">
            {[3, 4, 5, 6, 7].map((n) => {
              const active = n === startLen;
              return (
                <button
                  key={n}
                  onClick={() => setStartLen(n)}
                  className={`px-5 py-2.5 rounded-xl text-sm font-black transition-all border ${
                    active
                      ? 'bg-[#1a1a1a] text-white border-[#1a1a1a]'
                      : 'bg-white text-[#1a1a1a] border-[#e8d5b0] hover:border-[#1a1a1a]'
                  }`}
                >
                  {n} 位
                </button>
              );
            })}
          </div>
          <p className="text-[10px] font-medium text-slate-400 mt-2">
            建议倒序模式从 5 位开始；顺序模式可从 6-7 位起。
          </p>
        </div>

        <button
          onClick={startSession}
          className="w-full bg-[#1a1a1a] text-white font-black py-4 sm:py-5 rounded-2xl hover:bg-[#2c261c] hover:text-white transition-all uppercase tracking-widest text-xs sm:text-sm flex items-center justify-center space-x-2"
        >
          <Play size={16} />
          <span>开始训练</span>
        </button>

        {(stats.plays > 0 || stats.bestSpan != null) && (
          <div className="bg-white rounded-2xl border border-[#e8d5b0] p-4 sm:p-5 grid grid-cols-2 gap-3">
            <div className="text-center">
              <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                累计场次
              </p>
              <p className="text-base sm:text-lg font-black italic mt-1 tabular-nums">
                {stats.plays || 0}
              </p>
            </div>
            <div className="text-center">
              <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                最高位数
              </p>
              <p className="text-base sm:text-lg font-black italic mt-1 tabular-nums">
                {stats.bestSpan != null ? `${stats.bestSpan} 位` : '—'}
              </p>
            </div>
          </div>
        )}
      </div>
    );
  }

  // -------------- done --------------
  if (phase === 'done') {
    const okCount = history.filter((h) => h.ok).length;
    return (
      <div className="w-full max-w-2xl mx-auto px-2 sm:px-4 space-y-5">
        <div className="bg-[#1a1a1a] text-white rounded-[1.5rem] sm:rounded-[2rem] p-6 sm:p-10 text-center">
          <Trophy size={42} className="mx-auto text-[#6b5428]" />
          <h2 className="text-3xl sm:text-4xl font-black italic mt-4">完成！</h2>
          <p className="text-xs font-medium opacity-60 mt-2">
            {mode.label} · {TRIALS_PER_SESSION} 轮
          </p>

          <div className="grid grid-cols-2 gap-3 mt-7">
            <StatCard label="本场最高" value={`${maxOkLen || '—'} 位`} highlight />
            <StatCard
              label="正确轮数"
              value={`${okCount} / ${TRIALS_PER_SESSION}`}
            />
          </div>

          {/* 历史轮次 */}
          <div className="mt-6 grid grid-cols-4 gap-1.5">
            {history.map((h, i) => (
              <div
                key={i}
                className={`h-9 rounded-lg flex items-center justify-center text-xs font-black tabular-nums ${
                  h.ok ? 'bg-emerald-500/30 text-emerald-200' : 'bg-[#ff6b6b]/25 text-[#ffb4b4]'
                }`}
                title={`目标 ${h.expected.join(' ')} | 你 ${h.given.join(' ')}`}
              >
                {h.ok ? <Check size={14} /> : <X size={14} />}
                <span className="ml-1">{h.len}</span>
              </div>
            ))}
          </div>

          <p className="text-[10px] font-medium opacity-50 mt-4">
            悬停每个方块可看当轮目标 vs 你的回答
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={startSession}
            className="bg-[#1a1a1a] text-white font-black py-4 rounded-2xl hover:bg-[#2c261c] hover:text-white transition-all uppercase tracking-widest text-xs flex items-center justify-center space-x-2"
          >
            <RotateCcw size={14} />
            <span>再来一场</span>
          </button>
          <button
            onClick={() => setPhase('idle')}
            className="bg-white border border-[#e8d5b0] text-[#1a1a1a] font-black py-4 rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs"
          >
            换设置
          </button>
        </div>
      </div>
    );
  }

  // -------------- countdown / flash --------------
  if (phase === 'countdown' || phase === 'flash') {
    const showingNumber =
      phase === 'flash' && flashIdx < sequence.length ? sequence[flashIdx] : null;
    return (
      <div className="w-full max-w-2xl mx-auto px-2 sm:px-4 space-y-5">
        <div className="flex items-center justify-between">
          <button
            onClick={() => {
              if (timerRef.current) clearTimeout(timerRef.current);
              setPhase('idle');
            }}
            className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
          >
            <ChevronLeft size={18} />
            <span className="text-xs font-black uppercase tracking-widest">退出</span>
          </button>
          <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 tabular-nums">
            第 {trial + 1} / {TRIALS_PER_SESSION} 轮 · {length} 位 ·{' '}
            {modeId === 'backward' ? '倒序' : '顺序'}
          </div>
          <span className="w-12" />
        </div>

        <div className="bg-[#1a1a1a] text-white rounded-[1.5rem] sm:rounded-[2rem] aspect-video flex flex-col items-center justify-center select-none">
          {phase === 'countdown' && (
            <>
              <Eye size={48} className="text-[#6b5428]" />
              <p className="text-3xl sm:text-4xl font-black italic mt-4">看好了…</p>
              <p className="text-xs font-medium opacity-50 mt-3">
                {modeId === 'backward' ? '记下 → 倒着敲' : '记下 → 顺序敲'}
              </p>
            </>
          )}
          {phase === 'flash' && (
            <p
              key={flashIdx}
              className="text-[8rem] sm:text-[12rem] font-black tabular-nums leading-none"
              style={{ animation: 'ds-pulse 200ms ease-out' }}
            >
              {showingNumber != null ? showingNumber : '·'}
            </p>
          )}
        </div>

        {/* 进度点 */}
        <div className="flex items-center justify-center space-x-1.5">
          {Array.from({ length }, (_, i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full transition-all"
              style={{
                backgroundColor:
                  phase === 'flash' && i < flashIdx
                    ? '#8d7348'
                    : phase === 'flash' && i === flashIdx
                      ? '#8d7348'
                      : 'rgba(15,23,42,0.2)',
                transform:
                  phase === 'flash' && i === flashIdx ? 'scale(1.6)' : 'scale(1)',
              }}
            />
          ))}
        </div>

        <style>{`
          @keyframes ds-pulse {
            0% { transform: scale(0.85); opacity: 0; }
            60% { transform: scale(1.05); opacity: 1; }
            100% { transform: scale(1); opacity: 1; }
          }
        `}</style>
      </div>
    );
  }

  // -------------- recall / feedback --------------
  const expected =
    modeId === 'backward' ? sequence.slice().reverse() : sequence.slice();

  return (
    <div className="w-full max-w-xl mx-auto px-2 sm:px-4 space-y-4 sm:space-y-5">
      <div className="flex items-center justify-between">
        <button
          onClick={() => {
            if (timerRef.current) clearTimeout(timerRef.current);
            setPhase('idle');
          }}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">退出</span>
        </button>
        <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 tabular-nums">
          第 {trial + 1} / {TRIALS_PER_SESSION} 轮 · {length} 位 ·{' '}
          {modeId === 'backward' ? '倒序' : '顺序'}
        </div>
        <span className="w-12" />
      </div>

      <div className="bg-[#1a1a1a] text-white rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-8">
        <p className="text-center text-[10px] font-black uppercase tracking-[0.2em] text-[#6b5428]">
          {phase === 'recall'
            ? modeId === 'backward'
              ? '请倒着敲'
              : '请顺序敲'
            : lastResult === 'ok'
              ? '✓ 正确'
              : '✗ 答案如下'}
        </p>

        {/* 槽位 */}
        <div className="mt-5 sm:mt-6 flex flex-wrap items-end justify-center gap-2 sm:gap-3">
          {Array.from({ length }, (_, i) => {
            const cur = phase === 'recall' && i === input.length;
            const got = input[i];
            const exp = expected[i];
            const showAnswer = phase === 'feedback' && lastResult === 'wrong';
            const isWrongDigit =
              phase === 'feedback' &&
              lastResult === 'wrong' &&
              got != null &&
              got !== exp;
            return (
              <div
                key={i}
                className={`w-11 sm:w-14 h-14 sm:h-20 rounded-xl sm:rounded-2xl flex items-center justify-center text-2xl sm:text-4xl font-black tabular-nums transition-all ${
                  cur
                    ? 'bg-white text-[#1a1a1a] ring-2 ring-[#6b5428]'
                    : got != null
                      ? isWrongDigit
                        ? 'bg-[#ff6b6b]/30 text-white'
                        : phase === 'feedback' && lastResult === 'ok'
                          ? 'bg-emerald-500/30 text-white'
                          : 'bg-white/10 text-white'
                      : 'bg-white/5 text-white/30'
                }`}
                style={{ transform: cur ? 'scale(1.05)' : 'scale(1)' }}
              >
                {got != null ? got : showAnswer ? exp : '·'}
              </div>
            );
          })}
        </div>

        {/* 反馈/正确答案 */}
        {phase === 'feedback' && lastResult === 'wrong' && (
          <p className="text-center text-[11px] font-medium opacity-70 mt-4 tabular-nums">
            正确答案：{expected.join(' ')} | 你的回答：
            {input.length === 0 ? '—' : input.join(' ')}
          </p>
        )}
      </div>

      {/* 数字键盘 */}
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((d) => (
          <button
            key={d}
            disabled={phase !== 'recall'}
            onClick={() => addDigit(d)}
            className="bg-white border border-[#e8d5b0] hover:border-[#1a1a1a] active:bg-[#2c261c] active:scale-95 disabled:opacity-30 rounded-xl sm:rounded-2xl py-4 sm:py-5 text-2xl sm:text-3xl font-black tabular-nums transition-all select-none"
          >
            {d}
          </button>
        ))}
        <button
          disabled={phase !== 'recall'}
          onClick={removeDigit}
          className="bg-white border border-[#e8d5b0] hover:border-[#1a1a1a] active:bg-slate-200 active:scale-95 disabled:opacity-30 rounded-xl sm:rounded-2xl py-4 sm:py-5 text-sm font-black uppercase tracking-widest tabular-nums transition-all select-none"
        >
          删除
        </button>
        <button
          disabled={phase !== 'recall'}
          onClick={() => addDigit(0)}
          className="bg-white border border-[#e8d5b0] hover:border-[#1a1a1a] active:bg-[#2c261c] active:scale-95 disabled:opacity-30 rounded-xl sm:rounded-2xl py-4 sm:py-5 text-2xl sm:text-3xl font-black tabular-nums transition-all select-none"
        >
          0
        </button>
        <span />
      </div>
    </div>
  );
};

const StatCard = ({ label, value, highlight }) => (
  <div
    className={`rounded-2xl p-3 sm:p-4 ${
      highlight ? 'bg-[#2c261c] text-white' : 'bg-white/10'
    }`}
  >
    <p className="text-[9px] font-black uppercase tracking-widest opacity-70">{label}</p>
    <p className="text-base sm:text-xl font-black italic mt-1 tabular-nums">{value}</p>
  </div>
);

export default DigitSpanGame;

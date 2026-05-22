import { useCallback, useEffect, useMemo, useState } from 'react';
import { playCorrect, playWrong } from '../sfx.js';
import {
  ChevronLeft,
  RotateCcw,
  Play,
  Trophy,
  Check,
  X,
  Plus,
  Minus,
  Brain,
  Timer as TimerIcon,
} from 'lucide-react';

// ============================================================
// 移位加减（Mental Carry Drill）
// --------------------------------------
// 针对"记一忘一"的工作记忆瓶颈：
//   ● 题目：两数加减（2 位 / 3 位）
//   ● 玩法：强制按位（个 → 十 → 百）顺序输入答案的每一位
//   ● 每位答错立即提示，逼你重走"当前位 + 进位"的最小记忆路径
// 这样训练能把心算从"记 4-6 位数"压缩成"记 1 个进位 + 当前位"。
// ============================================================

const STORAGE_KEY = 'numeric_games_mental_carry_v1';
const SESSION_DEFAULT = 10; // 一组题数
const SESSION_PRESETS = [5, 10, 20];

const LEVELS = [
  {
    id: '2add',
    label: '2位 加法',
    desc: '两位数加法，3 位结果',
    op: '+',
    digits: 2,
    color: '#22c55e',
    icon: Plus,
  },
  {
    id: '2sub',
    label: '2位 减法',
    desc: '两位数减法，可借位',
    op: '-',
    digits: 2,
    color: '#3b82f6',
    icon: Minus,
  },
  {
    id: '3add',
    label: '3位 加法',
    desc: '三位数加法，治进位',
    op: '+',
    digits: 3,
    color: '#fbc02d',
    icon: Plus,
  },
  {
    id: '3sub',
    label: '3位 减法',
    desc: '三位数减法，治借位',
    op: '-',
    digits: 3,
    color: '#a855f7',
    icon: Minus,
  },
];

// ----------------- 工具 -----------------
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const loadStore = () => {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
};
const saveStore = (s) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
};
const fmtTime = (ms) => {
  if (ms == null || ms === Infinity) return '—';
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  const rem = Math.floor(s % 60);
  return `${m}:${String(rem).padStart(2, '0')}`;
};

// 生成一道题
const genQuestion = (level) => {
  const { op, digits } = level;
  if (digits === 2) {
    if (op === '+') {
      // 保证至少有一次进位的概率高（更有训练意义）
      const a = randInt(15, 99);
      const b = randInt(15, 99);
      return { a, b, op, answer: a + b, digits: 2 };
    }
    // 减法：保证 a > b 且至少 2 位结果
    let a = randInt(30, 99);
    let b = randInt(15, 90);
    if (a < b) [a, b] = [b, a];
    return { a, b, op, answer: a - b, digits: 2 };
  }
  // 3 位
  if (op === '+') {
    const a = randInt(150, 899);
    const b = randInt(150, 899);
    return { a, b, op, answer: a + b, digits: 3 };
  }
  // 减法
  let a = randInt(300, 999);
  let b = randInt(120, 800);
  if (a < b) [a, b] = [b, a];
  return { a, b, op, answer: a - b, digits: 3 };
};

// 把答案拆成位数组（个、十、百、千），不足补 0
const answerDigits = (n) => {
  const s = String(n);
  const arr = s.split('').map(Number).reverse(); // [个, 十, 百, ...]
  return arr;
};

// 答案应有的位数（按题目维度）
const expectedDigitCount = (q) => {
  // 加法 3 位：可能进到千位 → 4 位；2 位：3 位
  if (q.op === '+') {
    return q.digits === 2 ? 3 : 4;
  }
  // 减法：最多与原位数相同
  return q.digits;
};

const POS_NAMES = ['个位', '十位', '百位', '千位'];
const POS_COLORS = ['#fbc02d', '#22c55e', '#3b82f6', '#a855f7'];

// ============================================================
// 主组件
// ============================================================
const MentalCarryGame = ({ onBack }) => {
  const [levelId, setLevelId] = useState('3add');
  const [sessionSize, setSessionSize] = useState(SESSION_DEFAULT);
  const [phase, setPhase] = useState('idle'); // idle | playing | done

  const [question, setQuestion] = useState(null);
  const [posIndex, setPosIndex] = useState(0); // 当前要输入的位（0=个）
  const [enteredDigits, setEnteredDigits] = useState([]); // 已输入的位（个, 十, 百, ...）
  const [questionIdx, setQuestionIdx] = useState(0);
  const [feedback, setFeedback] = useState(null); // null | 'ok' | 'wrong'
  const [wrongShake, setWrongShake] = useState(0);
  const [questionStartedAt, setQuestionStartedAt] = useState(0);
  const [sessionStartedAt, setSessionStartedAt] = useState(0);
  const [records, setRecords] = useState([]); // 每题: {q, timeMs, wrongCount}
  const [questionWrongCount, setQuestionWrongCount] = useState(0);
  const [store, setStore] = useState(loadStore());
  const [lastSummary, setLastSummary] = useState(null);

  const [elapsed, setElapsed] = useState(0);
  const [sessionElapsed, setSessionElapsed] = useState(0);

  const level = useMemo(() => LEVELS.find((l) => l.id === levelId), [levelId]);
  const stats = store[levelId] || { plays: 0, bestAvgMs: null, bestAccuracy: null };

  // 计时器刷新
  useEffect(() => {
    if (phase !== 'playing') return undefined;
    const id = setInterval(() => {
      const now = Date.now();
      setElapsed(now - questionStartedAt);
      setSessionElapsed(now - sessionStartedAt);
    }, 100);
    return () => clearInterval(id);
  }, [phase, questionStartedAt, sessionStartedAt]);

  // 开始新一组
  const startSession = useCallback(() => {
    const q = genQuestion(level);
    const now = Date.now();
    setQuestion(q);
    setPosIndex(0);
    setEnteredDigits([]);
    setQuestionIdx(0);
    setFeedback(null);
    setQuestionStartedAt(now);
    setSessionStartedAt(now);
    setElapsed(0);
    setSessionElapsed(0);
    setRecords([]);
    setQuestionWrongCount(0);
    setLastSummary(null);
    setPhase('playing');
  }, [level]);

  // 下一题或结束
  const finishQuestionAndContinue = useCallback(
    (record) => {
      const newRecords = [...records, record];
      if (newRecords.length >= sessionSize) {
        // 结束
        const totalMs = newRecords.reduce((s, r) => s + r.timeMs, 0);
        const avgMs = Math.round(totalMs / newRecords.length);
        const totalWrong = newRecords.reduce((s, r) => s + r.wrongCount, 0);
        const totalDigits = newRecords.reduce((s, r) => s + r.digitCount, 0);
        const accuracy = totalDigits > 0 ? (totalDigits - totalWrong) / totalDigits : 0;

        // 更新存档
        const prev = store[levelId] || { plays: 0, bestAvgMs: null, bestAccuracy: null };
        const isNewBestSpeed = prev.bestAvgMs == null || avgMs < prev.bestAvgMs;
        const isNewBestAcc = prev.bestAccuracy == null || accuracy > prev.bestAccuracy;
        const next = {
          plays: prev.plays + 1,
          bestAvgMs: isNewBestSpeed ? avgMs : prev.bestAvgMs,
          bestAccuracy: isNewBestAcc ? accuracy : prev.bestAccuracy,
          lastPlayedAt: Date.now(),
        };
        const newStore = { ...store, [levelId]: next };
        setStore(newStore);
        saveStore(newStore);

        setLastSummary({
          totalMs,
          avgMs,
          accuracy,
          total: newRecords.length,
          totalWrong,
          totalDigits,
          isNewBestSpeed,
          isNewBestAcc,
        });
        setPhase('done');
        return;
      }
      const nq = genQuestion(level);
      setQuestion(nq);
      setPosIndex(0);
      setEnteredDigits([]);
      setQuestionIdx(newRecords.length);
      setFeedback(null);
      setQuestionStartedAt(Date.now());
      setQuestionWrongCount(0);
      setRecords(newRecords);
    },
    [level, levelId, records, sessionSize, store],
  );

  // 输入一位数字
  const submitDigit = useCallback(
    (d) => {
      if (phase !== 'playing' || !question || feedback) return;

      const expected = answerDigits(question.answer);
      const need = expectedDigitCount(question);
      const correctDigit = expected[posIndex] || 0;

      if (d === correctDigit) {
        const newEntered = [...enteredDigits, d];
        const nextPos = posIndex + 1;

        if (nextPos >= need) {
          // 题目完成
          playCorrect();
          const timeMs = Date.now() - questionStartedAt;
          setFeedback('ok');
          setEnteredDigits(newEntered);
          // 短暂展示后进入下一题
          setTimeout(() => {
            finishQuestionAndContinue({
              q: question,
              timeMs,
              wrongCount: questionWrongCount,
              digitCount: need,
            });
          }, 250);
        } else {
          setEnteredDigits(newEntered);
          setPosIndex(nextPos);
        }
      } else {
        // 答错
        playWrong();
        setQuestionWrongCount((c) => c + 1);
        setFeedback('wrong');
        setWrongShake((s) => s + 1);
        setTimeout(() => setFeedback(null), 280);
      }
    },
    [
      enteredDigits,
      feedback,
      finishQuestionAndContinue,
      phase,
      posIndex,
      question,
      questionStartedAt,
      questionWrongCount,
    ],
  );

  // 键盘输入
  useEffect(() => {
    if (phase !== 'playing') return undefined;
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key >= '0' && e.key <= '9') {
        e.preventDefault();
        submitDigit(parseInt(e.key, 10));
      } else if (e.key === 'Escape') {
        e.preventDefault();
        setPhase('idle');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, submitDigit]);

  // 进入下一题时重置 elapsed【在 questionStartedAt 变化时自动生效】

  // -------------- idle -------------
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
            <Brain size={18} className="text-[#fbc02d]" />
            <h2 className="text-xl sm:text-2xl font-black italic">移位加减</h2>
          </div>
          <span className="w-14" />
        </div>

        <div className="bg-[#1a1a1a] text-white rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-7">
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[#fbc02d]">
            训练目标
          </p>
          <h3 className="text-lg sm:text-xl font-black italic mt-2">
            治"记十位忘百位"的工作记忆瓶颈
          </h3>
          <p className="text-xs sm:text-sm font-medium opacity-70 mt-3 leading-relaxed">
            题目要求按 <span className="text-[#fbc02d] font-black">个位 → 十位 → 百位</span>{' '}
            的顺序逐位输入答案。每一步只用持有"当前位 + 进位（或借位）"，把整体记忆负担从 4-6
            位数压缩到 2 个 chunk。坚持训练 2 周，资料分析里的多数大幅提升肉眼可见。
          </p>
        </div>

        {/* 难度选择 */}
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
            选择难度
          </p>
          <div className="grid grid-cols-2 gap-3">
            {LEVELS.map((lv) => {
              const Icon = lv.icon;
              const active = lv.id === levelId;
              const lvStats = store[lv.id];
              return (
                <button
                  key={lv.id}
                  onClick={() => setLevelId(lv.id)}
                  className={`group p-4 sm:p-5 rounded-2xl text-left transition-all border ${
                    active
                      ? 'bg-[#1a1a1a] text-white border-[#1a1a1a] shadow-lg shadow-black/10'
                      : 'bg-white border-[#f2f0e9] hover:border-[#1a1a1a]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center"
                      style={{
                        backgroundColor: active ? lv.color : `${lv.color}22`,
                        color: active ? '#1a1a1a' : lv.color,
                      }}
                    >
                      <Icon size={18} />
                    </div>
                    {lvStats?.bestAvgMs && (
                      <span className="text-[9px] font-black uppercase tracking-widest opacity-60">
                        最佳 {fmtTime(lvStats.bestAvgMs)}/题
                      </span>
                    )}
                  </div>
                  <p className="text-sm sm:text-base font-black italic">{lv.label}</p>
                  <p
                    className={`text-[11px] sm:text-xs font-medium mt-1 ${
                      active ? 'opacity-70' : 'text-slate-400'
                    }`}
                  >
                    {lv.desc}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* 题数 */}
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
            本组题数
          </p>
          <div className="flex flex-wrap gap-2">
            {SESSION_PRESETS.map((n) => {
              const active = n === sessionSize;
              return (
                <button
                  key={n}
                  onClick={() => setSessionSize(n)}
                  className={`px-5 py-2.5 rounded-xl text-sm font-black transition-all border ${
                    active
                      ? 'bg-[#1a1a1a] text-[#fbc02d] border-[#1a1a1a]'
                      : 'bg-white text-[#1a1a1a] border-[#f2f0e9] hover:border-[#1a1a1a]'
                  }`}
                >
                  {n} 题
                </button>
              );
            })}
          </div>
        </div>

        {/* 开始 */}
        <button
          onClick={startSession}
          className="w-full bg-[#1a1a1a] text-white font-black py-4 sm:py-5 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs sm:text-sm flex items-center justify-center space-x-2"
        >
          <Play size={16} />
          <span>开始训练</span>
        </button>

        {/* 历史成绩简表 */}
        {(stats.plays > 0 || stats.bestAvgMs) && (
          <div className="bg-white rounded-2xl border border-[#f2f0e9] p-4 sm:p-5 grid grid-cols-3 gap-3">
            <SummaryStat label="累计场次" value={stats.plays || 0} />
            <SummaryStat
              label="最佳平均/题"
              value={stats.bestAvgMs ? fmtTime(stats.bestAvgMs) : '—'}
            />
            <SummaryStat
              label="最佳一次正确率"
              value={
                stats.bestAccuracy != null
                  ? `${Math.round(stats.bestAccuracy * 100)}%`
                  : '—'
              }
            />
          </div>
        )}
      </div>
    );
  }

  // -------------- done -------------
  if (phase === 'done' && lastSummary) {
    const acc = Math.round(lastSummary.accuracy * 100);
    return (
      <div className="w-full max-w-2xl mx-auto px-2 sm:px-4 space-y-5">
        <div className="bg-[#1a1a1a] text-white rounded-[1.5rem] sm:rounded-[2rem] p-6 sm:p-10 text-center">
          <Trophy size={42} className="mx-auto text-[#fbc02d]" />
          <h2 className="text-3xl sm:text-4xl font-black italic mt-4">完成！</h2>
          <p className="text-xs font-medium opacity-60 mt-2">
            {level.label} · {lastSummary.total} 题
          </p>

          <div className="grid grid-cols-3 gap-3 mt-7">
            <StatCard
              label="平均/题"
              value={fmtTime(lastSummary.avgMs)}
              highlight={lastSummary.isNewBestSpeed}
            />
            <StatCard label="总用时" value={fmtTime(lastSummary.totalMs)} />
            <StatCard
              label="按位正确率"
              value={`${acc}%`}
              highlight={lastSummary.isNewBestAcc}
            />
          </div>

          {(lastSummary.isNewBestSpeed || lastSummary.isNewBestAcc) && (
            <p className="text-[#fbc02d] text-sm font-black italic mt-5">
              ✨ 新纪录！
            </p>
          )}

          <p className="text-xs font-medium opacity-60 mt-5">
            共敲对 {lastSummary.totalDigits - lastSummary.totalWrong} / {lastSummary.totalDigits} 位，
            错误 {lastSummary.totalWrong} 次
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={startSession}
            className="bg-[#1a1a1a] text-white font-black py-4 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs flex items-center justify-center space-x-2"
          >
            <RotateCcw size={14} />
            <span>再来一组</span>
          </button>
          <button
            onClick={() => setPhase('idle')}
            className="bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black py-4 rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs"
          >
            换难度
          </button>
        </div>
      </div>
    );
  }

  // -------------- playing -------------
  const expected = question ? expectedDigitCount(question) : 0;
  const slots = Array.from({ length: expected }, (_, i) => {
    // i 是从右向左的索引（0=个位）；但在 UI 上要从左到右展示（高位在左）
    return i;
  }).reverse(); // 现在从高位到低位
  const accuracySoFar = (() => {
    const totalDigits = records.reduce((s, r) => s + r.digitCount, 0) + posIndex;
    const wrongDigits =
      records.reduce((s, r) => s + r.wrongCount, 0) + questionWrongCount;
    if (totalDigits === 0) return 1;
    return (totalDigits - wrongDigits) / totalDigits;
  })();

  return (
    <div className="w-full max-w-xl mx-auto px-2 sm:px-4 space-y-4 sm:space-y-5">
      {/* 顶部 */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setPhase('idle')}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">返回</span>
        </button>
        <div className="flex items-center space-x-3 text-[10px] font-black uppercase tracking-widest text-slate-400 tabular-nums">
          <span>
            {questionIdx + 1} / {sessionSize}
          </span>
          <span className="opacity-40">·</span>
          <span className="flex items-center space-x-1">
            <TimerIcon size={11} />
            <span>{fmtTime(sessionElapsed)}</span>
          </span>
        </div>
        <span className="w-12" />
      </div>

      {/* 题目卡 */}
      <div
        key={`shake-${wrongShake}`}
        className={`bg-[#1a1a1a] text-white rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-8 shadow-xl shadow-black/10 ${
          feedback === 'wrong' ? 'animate-mc-shake' : ''
        }`}
      >
        {/* 公式 */}
        <p className="text-center text-3xl sm:text-5xl font-black tracking-tight tabular-nums leading-tight">
          <span>{question.a}</span>
          <span className="mx-3 sm:mx-4 text-[#fbc02d]">{question.op}</span>
          <span>{question.b}</span>
          <span className="mx-3 sm:mx-4 opacity-50">=</span>
        </p>

        {/* 槽位（高位在左，低位在右） */}
        <div className="mt-6 sm:mt-8 flex items-end justify-center space-x-2 sm:space-x-3">
          {slots.map((digitIndex) => {
            const filled = digitIndex < posIndex;
            const isCurrent = digitIndex === posIndex;
            const value = enteredDigits[digitIndex];
            const posLabel = POS_NAMES[digitIndex] || `第${digitIndex + 1}位`;
            const posColor = POS_COLORS[digitIndex] || '#fbc02d';
            return (
              <div key={digitIndex} className="flex flex-col items-center">
                <span
                  className="text-[9px] font-black uppercase tracking-widest mb-1.5 transition-opacity"
                  style={{
                    color: posColor,
                    opacity: isCurrent ? 1 : 0.45,
                  }}
                >
                  {posLabel}
                </span>
                <div
                  className={`w-12 sm:w-16 h-14 sm:h-20 rounded-xl sm:rounded-2xl flex items-center justify-center text-3xl sm:text-5xl font-black tabular-nums transition-all ${
                    isCurrent
                      ? 'bg-white text-[#1a1a1a] ring-2 ring-[#fbc02d]'
                      : filled
                        ? 'bg-emerald-500/20 text-white'
                        : 'bg-white/10 text-white/30'
                  }`}
                  style={{
                    transform: isCurrent ? 'scale(1.05)' : 'scale(1)',
                  }}
                >
                  {filled || isCurrent ? (value != null ? value : '?') : '?'}
                </div>
              </div>
            );
          })}
        </div>

        {/* 反馈条 */}
        <div className="mt-5 sm:mt-6 h-7 flex items-center justify-center text-xs font-black uppercase tracking-widest">
          {feedback === 'wrong' && (
            <span className="flex items-center space-x-2 text-[#ff6b6b]">
              <X size={14} />
              <span>这位错了，想想"当前位 + 进位"</span>
            </span>
          )}
          {feedback === 'ok' && (
            <span className="flex items-center space-x-2 text-emerald-400">
              <Check size={14} />
              <span>正确！</span>
            </span>
          )}
          {!feedback && (
            <span className="text-white/40">
              {`输入 ${POS_NAMES[posIndex] || ''} 数字`}
            </span>
          )}
        </div>

        {/* 用时 / 正确率 */}
        <div className="mt-3 flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-white/40 tabular-nums">
          <span>本题 {fmtTime(elapsed)}</span>
          <span>正确率 {Math.round(accuracySoFar * 100)}%</span>
        </div>
      </div>

      {/* 数字键盘（移动端友好） */}
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((d) => (
          <button
            key={d}
            onClick={() => submitDigit(d)}
            className="bg-white border border-[#f2f0e9] hover:border-[#1a1a1a] active:bg-[#fbc02d] active:scale-95 rounded-xl sm:rounded-2xl py-4 sm:py-5 text-2xl sm:text-3xl font-black tabular-nums transition-all select-none"
          >
            {d}
          </button>
        ))}
        <span />
        <button
          onClick={() => submitDigit(0)}
          className="bg-white border border-[#f2f0e9] hover:border-[#1a1a1a] active:bg-[#fbc02d] active:scale-95 rounded-xl sm:rounded-2xl py-4 sm:py-5 text-2xl sm:text-3xl font-black tabular-nums transition-all select-none"
        >
          0
        </button>
        <span />
      </div>

      <style>{`
        @keyframes mc-shake {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-6px); }
          40% { transform: translateX(6px); }
          60% { transform: translateX(-4px); }
          80% { transform: translateX(4px); }
        }
        .animate-mc-shake { animation: mc-shake 280ms ease-in-out; }
      `}</style>
    </div>
  );
};

const SummaryStat = ({ label, value }) => (
  <div className="text-center">
    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</p>
    <p className="text-base sm:text-lg font-black italic mt-1 tabular-nums">{value}</p>
  </div>
);

const StatCard = ({ label, value, highlight }) => (
  <div
    className={`rounded-2xl p-3 sm:p-4 ${
      highlight ? 'bg-[#fbc02d] text-[#1a1a1a]' : 'bg-white/10'
    }`}
  >
    <p className="text-[9px] font-black uppercase tracking-widest opacity-70">{label}</p>
    <p className="text-base sm:text-xl font-black italic mt-1 tabular-nums">{value}</p>
  </div>
);

export default MentalCarryGame;

import { useEffect, useRef, useState } from 'react';
import {
  ChevronRight,
  ChevronLeft,
  Calculator,
  Wrench,
  BrainCircuit,
  BarChart3,
  History as HistoryIcon,
  Play,
  RotateCcw,
  Trophy,
  Check,
  X,
} from 'lucide-react';
import { CATEGORIES, generate, getSub, judge } from './generators.js';

const HISTORY_KEY = 'numeric_practice_history_v1';
const RACE_SIZE = 10;

// 作答反馈展示时长（毫秒）
const FEEDBACK_CORRECT_MS = 120;
const FEEDBACK_WRONG_MS = 600;
const FEEDBACK_SKIP_MS = 300;

const categoryIcons = {
  basic: Calculator,
  aux: Wrench,
  quant: BrainCircuit,
  data: BarChart3,
};

const fmtMs = (ms) => {
  if (ms < 1000) return `${ms} 毫秒`;
  return `${(ms / 1000).toFixed(1)} 秒`;
};
const loadHistory = () => {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch {
    return [];
  }
};
const saveHistory = (list) => {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
};

// ---------------- 主组件 ----------------
const NumericPractice = () => {
  const [view, setView] = useState('home');
  const [currentCat, setCurrentCat] = useState(null);
  const [currentSubId, setCurrentSubId] = useState(null);
  const [mode, setMode] = useState('train');

  const [session, setSession] = useState(null);
  const [sessionResult, setSessionResult] = useState(null);

  const goHome = () => {
    setView('home');
    setCurrentCat(null);
    setCurrentSubId(null);
    setSession(null);
    setSessionResult(null);
  };
  const openCategory = (catId) => {
    const cat = CATEGORIES.find((c) => c.id === catId);
    if (!cat?.available) return;
    setCurrentCat(cat);
    setCurrentSubId(cat.subs[0]?.id);
    setMode('train');
    setView('subs');
  };
  const startSession = () => {
    if (!currentCat || !currentSubId) return;
    const sub = getSub(currentCat.id, currentSubId);
    if (!sub) return;
    const total = mode === 'race' ? RACE_SIZE : Infinity;
    const firstQ = generate(sub.gen);
    setSession({
      catId: currentCat.id,
      subId: sub.id,
      subName: sub.name,
      genKey: sub.gen,
      mode,
      total,
      index: 0,
      current: firstQ,
      input: '',
      startedAt: Date.now(),
      questionStartedAt: Date.now(),
      records: [],
    });
    setView('session');
  };
  const finishRace = (records, catId, subId, subName) => {
    const totalMs = records.reduce((s, r) => s + r.timeMs, 0);
    const correct = records.filter((r) => r.isCorrect).length;
    const wrong = records.filter((r) => !r.isCorrect && !r.skipped).length;
    const skipped = records.filter((r) => r.skipped).length;
    const result = {
      id: Date.now(),
      catId,
      subId,
      subName,
      mode: 'race',
      completedAt: new Date().toISOString(),
      total: records.length,
      correct,
      wrong,
      skipped,
      totalMs,
      avgMs: Math.round(totalMs / records.length),
      records,
    };
    const list = loadHistory();
    list.unshift(result);
    saveHistory(list.slice(0, 100));
    setSessionResult(result);
    setView('result');
  };
  const openHistory = () => setView('history');

  if (view === 'home') return <HomeView onPick={openCategory} />;
  if (view === 'subs')
    return (
      <SubsView
        cat={currentCat}
        subId={currentSubId}
        mode={mode}
        onBack={goHome}
        onPickSub={setCurrentSubId}
        onPickMode={setMode}
        onStart={startSession}
        onOpenHistory={openHistory}
      />
    );
  if (view === 'session')
    return (
      <SessionView
        session={session}
        setSession={setSession}
        onExit={goHome}
        onFinishRace={finishRace}
      />
    );
  if (view === 'result')
    return (
      <ResultView
        result={sessionResult}
        onRetry={startSession}
        onHome={goHome}
        onSubs={() => setView('subs')}
      />
    );
  if (view === 'history') return <HistoryView onBack={goHome} />;
  return null;
};

// ---------------- Home ----------------
const HomeView = ({ onPick }) => {
  return (
    <div className="max-w-4xl mx-auto space-y-10">
      <div>
        <h2 className="text-4xl font-black tracking-tighter italic uppercase">数资练习</h2>
        <p className="text-sm font-medium text-slate-400 mt-2">
          选择一个练习分类，进入题库开始训练，或挑战限时冲刺模式。
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {CATEGORIES.map((cat) => {
          const Icon = categoryIcons[cat.id] || Calculator;
          const disabled = !cat.available;
          return (
            <button
              key={cat.id}
              onClick={() => onPick(cat.id)}
              disabled={disabled}
              className={`text-left rounded-[2rem] p-8 transition-all group ${
                disabled
                  ? 'bg-white border border-[#f2f0e9] opacity-60 cursor-not-allowed'
                  : 'bg-[#1a1a1a] text-white hover:-translate-y-1 hover:shadow-xl hover:shadow-black/10'
              }`}
            >
              <div className="flex items-center justify-between mb-6">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                    disabled ? 'bg-[#f2f0e9] text-[#1a1a1a]' : 'bg-[#fbc02d] text-black'
                  }`}
                >
                  <Icon size={22} />
                </div>
                {!disabled && (
                  <ChevronRight
                    size={22}
                    className="opacity-60 group-hover:opacity-100 group-hover:translate-x-1 transition-all"
                  />
                )}
                {disabled && (
                  <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                    敬请期待
                  </span>
                )}
              </div>
              <h3 className="text-xl font-black italic mb-2">{cat.name}</h3>
              <p
                className={`text-sm font-medium ${
                  disabled ? 'text-slate-400' : 'opacity-60'
                }`}
              >
                {cat.desc}
              </p>
              {!disabled && (
                <p className="text-[10px] font-black uppercase tracking-widest mt-6 opacity-50">
                  {cat.subs.length} 个子项
                </p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};

// ---------------- Subs ----------------
const SubsView = ({ cat, subId, mode, onBack, onPickSub, onPickMode, onStart, onOpenHistory }) => {
  if (!cat) return null;
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">返回</span>
        </button>
        <h2 className="text-2xl font-black italic">{cat.name}</h2>
        <button
          onClick={onOpenHistory}
          title="历史记录"
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <HistoryIcon size={16} />
          <span className="text-xs font-black uppercase tracking-widest hidden sm:inline">历史</span>
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {cat.subs.map((sub) => {
          const active = sub.id === subId;
          return (
            <button
              key={sub.id}
              onClick={() => onPickSub(sub.id)}
              className={`py-4 px-3 rounded-2xl font-bold text-sm transition-all border ${
                active
                  ? 'bg-[#1a1a1a] text-[#fbc02d] border-[#1a1a1a] shadow-lg shadow-black/10'
                  : 'bg-white text-[#1a1a1a] border-[#f2f0e9] hover:border-[#1a1a1a]'
              }`}
            >
              {sub.name}
            </button>
          );
        })}
      </div>

      <div className="bg-white rounded-[2rem] p-6 border border-[#f2f0e9] space-y-3">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">选择模式</p>
        <ModeOption
          label="训练模式"
          desc="不限题数，专注练习，按 Esc 可跳过当前题目，随时可退出。"
          checked={mode === 'train'}
          onClick={() => onPickMode('train')}
          color="#22c55e"
        />
        <ModeOption
          label="冲刺模式"
          desc={`${RACE_SIZE} 题限时挑战，结束后统计用时与正确率。`}
          checked={mode === 'race'}
          onClick={() => onPickMode('race')}
          color="#fbc02d"
        />
      </div>

      <div className="flex space-x-4">
        <button
          onClick={onStart}
          className="flex-1 bg-[#1a1a1a] text-white font-black py-5 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs flex items-center justify-center space-x-2"
        >
          <Play size={16} />
          <span>开始练习</span>
        </button>
        <button
          onClick={onOpenHistory}
          className="px-8 bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs flex items-center space-x-2"
        >
          <HistoryIcon size={14} />
          <span>历史记录</span>
        </button>
      </div>
    </div>
  );
};

const ModeOption = ({ label, desc, checked, onClick, color }) => (
  <button
    onClick={onClick}
    className={`w-full flex items-center space-x-4 p-4 rounded-2xl border transition-all text-left ${
      checked ? 'border-[#1a1a1a] bg-[#f2f0e9]/50' : 'border-[#f2f0e9] hover:border-slate-300'
    }`}
  >
    <span
      className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
        checked ? 'ring-2 ring-offset-2 ring-[#1a1a1a]' : 'border-2 border-slate-300'
      }`}
      style={checked ? { backgroundColor: color } : {}}
    >
      {checked && <Check size={14} className="text-white" strokeWidth={3} />}
    </span>
    <div className="flex-1">
      <p className="font-black text-sm italic">{label}</p>
      <p className="text-xs text-slate-400 font-medium mt-0.5">{desc}</p>
    </div>
  </button>
);

// ---------------- Session（做题页 + 键盘输入） ----------------
const SessionView = ({ session, setSession, onExit, onFinishRace }) => {
  const [, setTick] = useState(0);
  const [feedback, setFeedback] = useState(null); // null | { ok, skipped, answer }
  const timerRef = useRef(null);
  const pendingRef = useRef(null); // { newRecords, isLast }

  // 驱动"已用时"显示的定时刷新
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 100);
    return () => clearInterval(id);
  }, []);

  // 组件卸载时清理计时器
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  // 键盘事件监听
  useEffect(() => {
    const onKey = (e) => {
      if (!session) return;

      // 反馈展示期间：按 Enter/Space 可立即进入下一题
      if (feedback) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          flushAdvance();
        }
        return;
      }

      // 忽略带修饰键的组合
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      if (e.key >= '0' && e.key <= '9') {
        appendChar(e.key);
      } else if (e.key === '.') {
        appendChar('.');
      } else if (e.key === '-' && session.input === '') {
        appendChar('-');
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        backspace();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        submit();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        skip();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, feedback]);

  if (!session) return null;
  const { current, input, index, total, mode, records } = session;
  const now = Date.now();
  const elapsed = now - session.questionStartedAt;
  const totalElapsed = now - session.startedAt;

  const appendChar = (ch) => {
    setSession((s) => {
      if (!s) return s;
      if (s.input.length >= 12) return s;
      if (ch === '.' && s.input.includes('.')) return s;
      if (ch === '-' && s.input !== '') return s;
      return { ...s, input: s.input + ch };
    });
  };
  const backspace = () =>
    setSession((s) => (s ? { ...s, input: s.input.slice(0, -1) } : s));

  const scheduleAdvance = (newRecords, fb) => {
    pendingRef.current = { newRecords };
    setFeedback(fb);
    const delay = fb.skipped
      ? FEEDBACK_SKIP_MS
      : fb.ok
        ? FEEDBACK_CORRECT_MS
        : FEEDBACK_WRONG_MS;
    timerRef.current = setTimeout(flushAdvance, delay);
  };

  const flushAdvance = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const pending = pendingRef.current;
    pendingRef.current = null;
    setFeedback(null);
    if (!pending) return;
    const { newRecords } = pending;

    if (mode === 'race' && index + 1 >= total) {
      onFinishRace(newRecords, session.catId, session.subId, session.subName);
      return;
    }
    const nextQ = generate(session.genKey);
    setSession({
      ...session,
      index: index + 1,
      current: nextQ,
      input: '',
      questionStartedAt: Date.now(),
      records: newRecords,
    });
  };

  const submit = () => {
    if (feedback) return;
    if (input === '' || input === '-' || input === '.') return;
    const timeMs = Date.now() - session.questionStartedAt;
    const isCorrect = judge(current, input);
    const rec = {
      prompt: current.prompt,
      answer: current.answer,
      userAnswer: input,
      isCorrect,
      skipped: false,
      timeMs,
    };
    const newRecords = [...records, rec];
    scheduleAdvance(newRecords, { ok: isCorrect, skipped: false, answer: current.answer });
  };

  const skip = () => {
    if (feedback) return;
    const timeMs = Date.now() - session.questionStartedAt;
    const rec = {
      prompt: current.prompt,
      answer: current.answer,
      userAnswer: null,
      isCorrect: false,
      skipped: true,
      timeMs,
    };
    const newRecords = [...records, rec];
    scheduleAdvance(newRecords, { ok: false, skipped: true, answer: current.answer });
  };

  const totalStr = total === Infinity ? '∞' : String(total);
  const progress = `${index + 1} / ${totalStr}`;
  const correctCount = records.filter((r) => r.isCorrect).length;

  // 反馈区域背景
  const fbBg = feedback
    ? feedback.ok
      ? 'bg-emerald-500/25 ring-2 ring-emerald-400'
      : feedback.skipped
        ? 'bg-slate-400/20 ring-2 ring-slate-400'
        : 'bg-[#ff6b6b]/20 ring-2 ring-[#ff6b6b]'
    : 'bg-white/10 ring-0';

  return (
    <div className="max-w-2xl mx-auto">
      {/* 顶部导航 */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={onExit}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">退出</span>
        </button>
        <div className="text-xs font-black uppercase tracking-widest text-slate-400">
          {session.subName} · {mode === 'race' ? '冲刺模式' : '训练模式'}
        </div>
      </div>

      {/* 题目卡片 */}
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 shadow-xl shadow-black/10 relative overflow-hidden">
        {/* 反馈背景淡色层 */}
        {feedback && (
          <div
            className={`absolute inset-0 pointer-events-none transition-opacity ${
              feedback.ok
                ? 'bg-emerald-500/5'
                : feedback.skipped
                  ? 'bg-slate-500/5'
                  : 'bg-[#ff6b6b]/5'
            }`}
          />
        )}

        <div className="relative z-10">
          <div className="flex items-center justify-between text-xs font-black uppercase tracking-widest opacity-60 mb-10">
            <span>{progress}</span>
            <span>本题用时 {fmtMs(elapsed)}</span>
          </div>

          <div className="text-center py-8">
            <p className="text-4xl md:text-5xl font-black tracking-tight break-words leading-tight">
              {current.prompt}
            </p>
          </div>

          {/* 输入/反馈区 */}
          <div
            className={`rounded-2xl h-24 flex items-center justify-center px-6 transition-all duration-150 ${fbBg}`}
          >
            <div className="flex items-center justify-center space-x-4">
              {feedback && (
                <span
                  className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 ${
                    feedback.ok
                      ? 'bg-emerald-500 text-white'
                      : feedback.skipped
                        ? 'bg-slate-400 text-white'
                        : 'bg-[#ff6b6b] text-white'
                  }`}
                  style={{ animation: 'fb-pop 180ms ease-out' }}
                >
                  {feedback.ok ? (
                    <Check size={26} strokeWidth={3.5} />
                  ) : (
                    <X size={26} strokeWidth={3.5} />
                  )}
                </span>
              )}
              <p className="text-4xl font-black tracking-tight">
                {feedback && !feedback.ok ? (
                  <>
                    {!feedback.skipped && (
                      <span className="text-white/40 mr-3 line-through">{input}</span>
                    )}
                    <span className="text-[#fbc02d]">{feedback.answer}</span>
                  </>
                ) : input === '' ? (
                  <span className="opacity-30 text-2xl">输入答案后按 Enter 提交</span>
                ) : (
                  input
                )}
              </p>
            </div>
          </div>

          {/* 快捷键提示 + 计数 */}
          <div className="mt-6 flex items-center justify-between text-[10px] font-black uppercase tracking-widest opacity-40">
            <div className="flex items-center space-x-3">
              <span>Enter 提交</span>
              <span>·</span>
              <span>Backspace 删除</span>
              <span>·</span>
              <span>Esc 跳过</span>
            </div>
            <div>
              正确 {correctCount} / 已答 {records.length}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes fb-pop {
          0%   { transform: scale(0.3); opacity: 0; }
          60%  { transform: scale(1.15); opacity: 1; }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
};

// ---------------- Result ----------------
const ResultView = ({ result, onRetry, onHome, onSubs }) => {
  if (!result) return null;
  const accuracy = Math.round((result.correct / result.total) * 100);
  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 text-center relative overflow-hidden">
        <div className="absolute top-8 right-8 w-40 h-40 bg-[#fbc02d] rounded-full blur-[50px] opacity-40" />
        <div className="relative">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-[#fbc02d] text-black flex items-center justify-center mb-4">
            <Trophy size={28} />
          </div>
          <p className="text-xs font-black uppercase tracking-widest opacity-60 mb-1">
            {result.subName} · 冲刺结果
          </p>
          <p className="text-5xl font-black italic">{accuracy}%</p>
          <p className="text-sm font-medium opacity-60 mt-1">
            共 {result.total} 题 · 正确 {result.correct} · 错误 {result.wrong} · 跳过{' '}
            {result.skipped}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 mt-8">
          <StatCell label="总用时" value={fmtMs(result.totalMs)} />
          <StatCell label="平均用时" value={fmtMs(result.avgMs)} />
        </div>
      </div>

      <div className="bg-white rounded-[2rem] p-6 border border-[#f2f0e9]">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">答题明细</p>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {result.records.map((r, i) => (
            <div
              key={i}
              className="flex items-center justify-between py-2 border-b border-[#f2f0e9] last:border-0 text-sm"
            >
              <div className="flex items-center space-x-3 flex-1 min-w-0">
                <span className="text-[10px] font-black text-slate-400 w-6">#{i + 1}</span>
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
                    r.isCorrect
                      ? 'bg-emerald-500 text-white'
                      : r.skipped
                        ? 'bg-slate-300 text-white'
                        : 'bg-[#ff6b6b] text-white'
                  }`}
                >
                  {r.isCorrect ? <Check size={12} /> : <X size={12} />}
                </span>
                <span className="font-bold truncate">{r.prompt}</span>
              </div>
              <div className="flex items-center space-x-3 flex-shrink-0 ml-3">
                <span className="text-xs text-slate-400">
                  {r.skipped ? '已跳过' : `你的答案: ${r.userAnswer}`}
                </span>
                {!r.isCorrect && (
                  <span className="text-xs font-black text-[#fbc02d]">= {r.answer}</span>
                )}
                <span className="text-[10px] font-black text-slate-400 w-12 text-right">
                  {fmtMs(r.timeMs)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex space-x-3">
        <button
          onClick={onRetry}
          className="flex-1 bg-[#1a1a1a] text-white font-black py-4 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs flex items-center justify-center space-x-2"
        >
          <RotateCcw size={14} />
          <span>再来一组</span>
        </button>
        <button
          onClick={onSubs}
          className="px-6 bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs"
        >
          换个题型
        </button>
        <button
          onClick={onHome}
          className="px-6 bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs"
        >
          返回
        </button>
      </div>
    </div>
  );
};

const StatCell = ({ label, value }) => (
  <div className="bg-white/10 rounded-2xl p-4">
    <p className="text-[10px] font-black uppercase tracking-widest opacity-60">{label}</p>
    <p className="text-xl font-black italic mt-1">{value}</p>
  </div>
);

// ---------------- History ----------------
const HistoryView = ({ onBack }) => {
  const [list, setList] = useState(() => loadHistory());

  const clearAll = () => {
    if (list.length === 0) return;
    if (confirm('确定要清空所有历史记录吗？该操作不可恢复。')) {
      saveHistory([]);
      setList([]);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">返回</span>
        </button>
        <h2 className="text-2xl font-black italic">历史记录</h2>
        <button
          onClick={clearAll}
          disabled={list.length === 0}
          className="text-xs font-black uppercase tracking-widest text-slate-400 hover:text-[#ff6b6b] disabled:opacity-30 transition-colors"
        >
          清空
        </button>
      </div>

      {list.length === 0 ? (
        <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-16 text-center">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-[#f2f0e9] flex items-center justify-center mb-4 text-slate-400">
            <HistoryIcon size={28} />
          </div>
          <p className="text-sm font-bold text-slate-400">暂无历史记录</p>
          <p className="text-xs text-slate-400 mt-1">完成一次"冲刺模式"后会在此留下成绩</p>
        </div>
      ) : (
        <div className="space-y-3">
          {list.map((r) => {
            const accuracy = Math.round((r.correct / r.total) * 100);
            return (
              <div
                key={r.id}
                className="bg-white rounded-2xl border border-[#f2f0e9] p-5 flex items-center justify-between"
              >
                <div className="min-w-0">
                  <p className="text-sm font-black italic truncate">{r.subName}</p>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-1">
                    {new Date(r.completedAt).toLocaleString('zh-CN')}
                  </p>
                </div>
                <div className="flex items-center space-x-6 flex-shrink-0">
                  <HistoryStat label="正确率" value={`${accuracy}%`} accent />
                  <HistoryStat label="总用时" value={fmtMs(r.totalMs)} />
                  <HistoryStat label="平均" value={fmtMs(r.avgMs)} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const HistoryStat = ({ label, value, accent }) => (
  <div className="text-right">
    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</p>
    <p className={`text-sm font-black italic ${accent ? 'text-[#1a1a1a]' : 'text-slate-600'}`}>
      {value}
    </p>
  </div>
);

export default NumericPractice;

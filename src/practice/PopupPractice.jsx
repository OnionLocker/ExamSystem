import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, X, SkipForward, RotateCcw, Eye, EyeOff, Timer, BookOpen, ChevronLeft } from 'lucide-react';
import { CATEGORIES, generate, getSub, judge, BAI_HUA_FEN_TABLE, SQUARE_TABLE } from './generators.js';
import { recordPromotionResult, getRank } from './ranks.js';
import RankBadge from './RankBadge.jsx';
import { addEntry as addStudyEntry, scoreNumeric } from '../studyLog/studyLog.js';
import { loadHistory, saveHistory } from './history.js';


// 小窗练习组件
// 两种启动途径：
//   1) Document Picture-in-Picture（首选，无浏览器 chrome，始终置顶）
//      -> 由外部挂载，通过 props 传入 { catId, subId, mode, embedded: true }
//   2) window.open 弹窗（降级）
//      -> 通过 URL 参数 ?popup=1&cat=&sub=&mode= 传入

const FEEDBACK_CORRECT_MS = 120;
const FEEDBACK_WRONG_MS = 600;
const FEEDBACK_SKIP_MS = 300;

const RACE_SIZE_DEFAULT = 10;
const RACE_SIZE_PRESETS = [5, 10, 20, 50];

const readParams = () => {
  const p = new URLSearchParams(window.location.search);
  return {
    catId: p.get('cat') || 'basic',
    subId: p.get('sub') || '',
    mode: p.get('mode') || 'train',
  };
};

const fmtMs = (ms) => {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

// 较长时长用 mm:ss / h:mm:ss（给"总时间"用）
const fmtDuration = (ms) => {
  if (ms == null) return '—';
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  if (h > 0) return `${h}:${pad(m)}:${pad(sec)}`;
  return `${pad(m)}:${pad(sec)}`;
};

const PopupPractice = ({ catId: pCat, subId: pSub, mode: pMode, embedded = false } = {}) => {
  // 参数来源：props 优先（PiP 模式），否则读 URL；之后可在小窗内换模块
  const init = useMemo(() => {
    if (pCat || pSub) {
      return {
        catId: pCat || 'basic',
        subId: pSub || '',
        mode: pMode === 'race' ? 'race' : 'train',
      };
    }
    return readParams();
  }, [pCat, pSub, pMode]);

  const [catId, setCatId] = useState(init.catId);
  const [subId, setSubId] = useState(init.subId);
  const [mode, setMode] = useState(init.mode === 'race' ? 'race' : 'train');
  const [raceSize, setRaceSize] = useState(RACE_SIZE_DEFAULT);
  const [raceDone, setRaceDone] = useState(null); // 晋升结束小结
  // picking: null | 'cat' | 'sub' | 'mode'
  const [picking, setPicking] = useState(null);
  const [pickCatId, setPickCatId] = useState(null);
  const [draftCatId, setDraftCatId] = useState(null);
  const [draftSubId, setDraftSubId] = useState(null);
  const [draftMode, setDraftMode] = useState('train');
  const [draftRaceSize, setDraftRaceSize] = useState(RACE_SIZE_DEFAULT);

  const cat = CATEGORIES.find((c) => c.id === catId);
  const sub = getSub(catId, subId) || cat?.subs?.[0];
  const availableCats = useMemo(() => CATEGORIES.filter((c) => c.available), []);

  // stealth: 伪装模式（低调主题、可隐藏题目内容）
  const [stealth, setStealth] = useState(false);
  const [blurred, setBlurred] = useState(false);
  const [showTable, setShowTable] = useState(false);

  const [question, setQuestion] = useState(() => (sub ? generate(sub.gen) : null));
  const [input, setInput] = useState('');
  const [feedback, setFeedback] = useState(null); // { ok, skipped, answer }
  const [stats, setStats] = useState({
    correct: 0,
    wrong: 0,
    skipped: 0,
    totalMs: 0, // 全部答题累计用时
    bestMs: null, // 最快正确用时
  });

  // 本题开始时间（用 state 驱动 tick 渲染）
  const [qStartedAt, setQStartedAt] = useState(() => Date.now());
  // 本次会话开始时间（总时间）
  const [sessionStartedAt, setSessionStartedAt] = useState(() => Date.now());
  // 当前时刻由定时器推进。存时间戳而不是自增计数：渲染期直接调 Date.now()
  // 属于不纯（同一次渲染重跑结果不同），改成渲染只消费这个 state。
  const [now, setNow] = useState(() => Date.now());

  const timerRef = useRef(null);
  const pendingRef = useRef(null);
  const rootRef = useRef(null); // 根节点，用于定位组件真正所属的 window（PiP 模式下是 PiP 窗口）

  // 定时刷新当前题用时
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, []);

  // 挂载后把焦点交给组件所属窗口（PiP 窗口），键盘立即可用
  useEffect(() => {
    const win = rootRef.current?.ownerDocument?.defaultView;
    if (win && win !== window) {
      try { win.focus(); } catch { /* ignore */ }
    }
  }, []);

  // 标题随作答进度更新（嵌入 PiP 时不改主窗标题）
  useEffect(() => {
    if (embedded) return;
    const total = stats.correct + stats.wrong + stats.skipped;
    document.title = stealth ? '文档' : `${sub?.name || '练习'} · 已答 ${total}`;
  }, [stats, sub, stealth, embedded]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const nextQuestion = () => {
    if (!sub) return;
    setQuestion(generate(sub.gen));
    setInput('');
    setQStartedAt(Date.now());
  };

  const appendChar = (ch) => {
    setInput((s) => {
      if (s.length >= 12) return s;
      if (ch === '.' && s.includes('.')) return s;
      if (ch === '-' && s !== '') return s;
      return s + ch;
    });
  };
  const backspace = () => setInput((s) => s.slice(0, -1));

  const scheduleAdvance = (fb, nextStats) => {
    pendingRef.current = { stats: nextStats };
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
    if (!pendingRef.current) return;
    const snap = pendingRef.current;
    pendingRef.current = null;
    setFeedback(null);
    if (mode === 'race' && snap && typeof snap === 'object' && snap.stats) {
      const answered = snap.stats.correct + snap.stats.wrong + snap.stats.skipped;
      if (answered >= raceSize) {
        finishRaceSession(snap.stats);
        return;
      }
    }
    nextQuestion();
  };

  const submit = () => {
    if (feedback || !question || raceDone) return;
    if (input === '' || input === '-' || input === '.') return;
    const timeMs = now - qStartedAt;
    const isCorrect = judge(question, input);
    const nextStats = {
      ...stats,
      correct: stats.correct + (isCorrect ? 1 : 0),
      wrong: stats.wrong + (isCorrect ? 0 : 1),
      totalMs: stats.totalMs + timeMs,
      bestMs: isCorrect
        ? stats.bestMs == null
          ? timeMs
          : Math.min(stats.bestMs, timeMs)
        : stats.bestMs,
    };
    setStats(nextStats);
    scheduleAdvance({ ok: isCorrect, skipped: false, answer: typeof question.displayAnswer === 'function' ? question.displayAnswer(question.answer) : question.answer }, nextStats);
  };
  const skip = () => {
    if (feedback || !question || raceDone) return;
    const timeMs = now - qStartedAt;
    const nextStats = {
      ...stats,
      skipped: stats.skipped + 1,
      totalMs: stats.totalMs + timeMs,
    };
    setStats(nextStats);
    scheduleAdvance({ ok: false, skipped: true, answer: typeof question.displayAnswer === 'function' ? question.displayAnswer(question.answer) : question.answer }, nextStats);
  };
  const resetStats = () => {
    setStats({ correct: 0, wrong: 0, skipped: 0, totalMs: 0, bestMs: null });
    setSessionStartedAt(now);
    if (feedback) flushAdvance();
    nextQuestion();
  };

  // level: 'mode'（默认，回训练/晋升）| 'cat'（换大类）| 'sub'
  const openModulePicker = (level = 'mode') => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingRef.current = null;
    setFeedback(null);
    setShowTable(false);
    setRaceDone(null);
    // 纠正空 subId：界面可能正用 cat.subs[0] 出题，但 state 还是 ''
    const effectiveSub = getSub(catId, subId) || cat?.subs?.[0] || null;
    const effectiveSubId = effectiveSub?.id || '';
    const effectiveCatId = catId || effectiveSub && CATEGORIES.find((c) => c.subs.some((s) => s.id === effectiveSubId))?.id || 'basic';
    if (effectiveSubId && effectiveSubId !== subId) setSubId(effectiveSubId);
    if (effectiveCatId && effectiveCatId !== catId) setCatId(effectiveCatId);
    setPickCatId(effectiveCatId);
    setDraftCatId(effectiveCatId);
    setDraftSubId(effectiveSubId);
    setDraftMode(mode);
    setDraftRaceSize(raceSize);
    if (!effectiveSub) {
      setPicking('cat');
      return;
    }
    setPicking(level === 'cat' || level === 'sub' ? level : 'mode');
  };

  const pickCategory = (id) => {
    setPickCatId(id);
    setDraftCatId(id);
    const nextCat = CATEGORIES.find((c) => c.id === id);
    // 换大类时：若当前 draft 子项不属于该类，落到该类第一项
    const keep = draftSubId && getSub(id, draftSubId);
    setDraftSubId(keep ? draftSubId : (nextCat?.subs?.[0]?.id || ''));
    setPicking('sub');
  };

  const pickSub = (nextCatId, nextSubId) => {
    if (!getSub(nextCatId, nextSubId)) return;
    setDraftCatId(nextCatId);
    setDraftSubId(nextSubId);
    setDraftMode(mode);
    setDraftRaceSize(raceSize);
    setPicking('mode');
  };

  const beginSession = (nextCatId, nextSubId, nextMode, nextSize) => {
    const nextSub = getSub(nextCatId, nextSubId);
    if (!nextSub) return;
    const modeNext = nextMode === 'race' ? 'race' : 'train';
    const sizeNext = Math.max(1, Math.min(200, Number(nextSize) || RACE_SIZE_DEFAULT));
    setCatId(nextCatId);
    setSubId(nextSubId);
    setMode(modeNext);
    setRaceSize(sizeNext);
    setPicking(null);
    setPickCatId(null);
    setRaceDone(null);
    setInput('');
    setFeedback(null);
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingRef.current = null;
    setStats({ correct: 0, wrong: 0, skipped: 0, totalMs: 0, bestMs: null });
    setSessionStartedAt(Date.now());
    setQStartedAt(Date.now());
    setQuestion(generate(nextSub.gen));
  };

  const startFromPicker = () => {
    beginSession(
      draftCatId || pickCatId || catId,
      draftSubId || subId,
      draftMode,
      draftRaceSize,
    );
  };

  // 再来一局：沿用当前题型 / 模式 / 题数，直接开打
  const retrySameRace = () => {
    beginSession(catId, subId, mode, raceSize);
  };

  const finishRaceSession = (finalStats) => {
    const total = finalStats.correct + finalStats.wrong + finalStats.skipped;
    const totalMs = finalStats.totalMs;
    const rankChange = recordPromotionResult({
      subId,
      total,
      correct: finalStats.correct,
      totalMs,
    });
    const result = {
      id: Date.now(),
      catId,
      subId,
      subName: sub?.name || subId,
      mode: 'race',
      completedAt: new Date().toISOString(),
      total,
      correct: finalStats.correct,
      wrong: finalStats.wrong,
      skipped: finalStats.skipped,
      totalMs,
      avgMs: total > 0 ? Math.round(totalMs / total) : 0,
      rankChange,
    };
    const list = loadHistory();
    list.unshift(result);
    saveHistory(list);
    addStudyEntry({
      type: 'numeric',
      module: result.subName,
      count: result.total,
      correct: result.correct,
      score: scoreNumeric(result.total, result.correct),
    });
    setRaceDone(result);
  };

  // 键盘监听：绑定到组件 DOM 真正所属的 window。
  // PiP 模式下 React 虽在主窗口 realm 执行，但节点挂在 PiP 文档里，
  // 焦点在 PiP 窗口时键盘事件只会派发到 PiP window —— 必须监听它，
  // 否则鼠标点过 PiP 小窗后就再也接不到按键（焦点丢失）。
  useEffect(() => {
    const win =
      rootRef.current?.ownerDocument?.defaultView ||
      (typeof window !== 'undefined' ? window : null);
    if (!win) return;
    const onKey = (e) => {
      if (picking) {
        if (e.key === 'Escape') {
          e.preventDefault();
          if (picking === 'mode') setPicking('sub');
          else if (picking === 'sub') setPicking('cat');
          else setPicking(null);
        }
        return;
      }
      if (raceDone) {
        if (e.key === 'Escape' || e.key === 'Enter') {
          e.preventDefault();
          setRaceDone(null);
          openModulePicker();
        }
        return;
      }
      // 对照表打开时，只处理 ESC 关闭
      if (showTable) {
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowTable(false);
        }
        return;
      }
      if (feedback) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          flushAdvance();
        }
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'h' || e.key === 'H')) {
          e.preventDefault();
          setStealth((v) => !v);
        }
        if ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B')) {
          e.preventDefault();
          setBlurred((v) => !v);
        }
        return;
      }
      if (e.key >= '0' && e.key <= '9') appendChar(e.key);
      else if (e.key === '.') appendChar('.');
      else if (e.key === '-' && input === '') appendChar('-');
      else if (e.key === 'Backspace') {
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
    win.addEventListener('keydown', onKey);
    return () => win.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedback, input, question, qStartedAt, showTable, picking, raceDone, mode, raceSize, stats]);

  if ((!sub || !question) && !picking) {
    return (
      <div className="popup-root min-h-screen flex flex-col items-center justify-center bg-white text-slate-500 text-sm font-medium p-6 text-center gap-3">
        <span>未找到题型</span>
        <button
          type="button"
          onClick={openModulePicker}
          className="px-3 py-1.5 rounded-lg bg-[#1a1a1a] text-white text-xs font-black"
        >
          选择练习模块
        </button>
      </div>
    );
  }

  if (picking && (!sub || !question)) {
    return (
      <div
        ref={rootRef}
        tabIndex={-1}
        className={`popup-root relative h-full min-h-full flex flex-col ${stealth ? 'bg-[#fafafa] text-slate-700' : 'bg-[#1a1a1a] text-white'} select-none overflow-hidden focus:outline-none`}
      >
        <PopupModulePicker
          stealth={stealth}
          step={picking}
          cats={availableCats}
          pickCatId={pickCatId || availableCats[0]?.id}
          currentCatId={catId}
          currentSubId={subId}
          draftCatId={draftCatId}
          draftSubId={draftSubId}
          draftMode={draftMode}
          draftRaceSize={draftRaceSize}
          onBack={() => {
            if (picking === 'mode') setPicking('sub');
            else if (picking === 'sub') setPicking('cat');
            else setPicking(null);
          }}
          onPickCat={pickCategory}
          onPickSub={pickSub}
          onDraftMode={setDraftMode}
          onDraftRaceSize={setDraftRaceSize}
          onStart={startFromPicker}
        />
        <style>{`
          html, body, #root { height: 100%; }
          body { margin: 0; overflow: hidden; }
          @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
        `}</style>
      </div>
    );
  }

  // 配色：常规 = 黑黄；伪装 = 白灰（看起来像个文档）
  const theme = stealth
    ? {
        wrap: 'bg-[#fafafa] text-slate-700',
        card: 'bg-white border border-slate-200/80',
        prompt: 'text-slate-800',
        hint: 'text-slate-400',
        accent: 'text-slate-600',
        answer: 'text-slate-500',
        inputBg: 'bg-slate-50 border border-slate-100',
        fbOk: 'bg-emerald-50 ring-1 ring-emerald-200',
        fbWrong: 'bg-rose-50 ring-1 ring-rose-200',
        fbSkip: 'bg-slate-100 ring-1 ring-slate-200',
        strike: 'text-slate-300',
      }
    : {
        wrap: 'bg-gradient-to-br from-[#1a1a1a] via-[#1a1a1a] to-[#2a2618] text-white',
        card: 'bg-white/[0.04] border border-white/10 backdrop-blur',
        prompt: 'text-white',
        hint: 'text-white/35',
        accent: 'text-[#6b5428]',
        answer: 'text-[#6b5428]',
        inputBg: 'bg-black/30 border border-white/5',
        fbOk: 'bg-emerald-500/15 ring-1 ring-emerald-400/60',
        fbWrong: 'bg-[#ff6b6b]/15 ring-1 ring-[#ff6b6b]/60',
        fbSkip: 'bg-white/5 ring-1 ring-white/20',
        strike: 'text-white/30',
      };

  const fbCls = feedback
    ? feedback.ok
      ? theme.fbOk
      : feedback.skipped
        ? theme.fbSkip
        : theme.fbWrong
    : theme.inputBg;

  const total = stats.correct + stats.wrong + stats.skipped;
  const accuracy = total > 0 ? Math.round((stats.correct / total) * 100) : 0;
  const avgMs = total > 0 ? Math.round(stats.totalMs / total) : null;
  // 用定时器推进的 now，而不是渲染期再读一次时钟
  const currentMs = now - qStartedAt;
  const sessionMs = now - sessionStartedAt;

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      className={`popup-root relative h-full min-h-full flex flex-col ${theme.wrap} select-none overflow-hidden focus:outline-none`}
      style={{ fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' }}
      onPointerDown={() => {
        // 点击小窗任意处，把焦点抢回 PiP 窗口，保证键盘可用
        rootRef.current?.ownerDocument?.defaultView?.focus?.();
      }}
    >
      {/* 顶栏 */}
      <div
        className={`flex items-center justify-between px-3 pt-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-widest ${stealth ? 'text-slate-400' : 'text-white/50'}`}
      >
        <div className="flex items-center space-x-1.5 min-w-0">
          <button
            type="button"
            onClick={openModulePicker}
            title="返回选模式（训练/晋升）"
            className={`flex items-center gap-0.5 shrink-0 rounded-md px-1 py-0.5 transition-colors ${
              stealth
                ? 'text-slate-500 hover:text-slate-800 hover:bg-slate-100'
                : 'text-[#6b5428] hover:bg-white/10'
            }`}
          >
            <ChevronLeft size={14} />
            <span className="normal-case tracking-normal">返回</span>
          </button>
          <button
            type="button"
            onClick={openModulePicker}
            title="切换练习模块"
            className={`truncate text-left min-w-0 hover:opacity-100 opacity-90 ${stealth ? 'hover:text-slate-700' : 'hover:text-white'}`}
          >
            {stealth
              ? '文档 · 草稿'
              : `${sub?.name || '选模块'} · ${mode === 'race' ? '晋升' : '训练'}`}
          </button>
          <span className={`flex items-center space-x-1 ${theme.accent} normal-case tracking-normal`}>
            <Timer size={11} />
            <span className="font-mono tabular-nums text-[11px]">{fmtMs(currentMs)}</span>
          </span>
        </div>
        <div className="flex items-center space-x-0.5">
          {(sub.id === 'pctToFrac' || sub.id === 'square') && (
            <IconBtn
              onClick={() => setShowTable(true)}
              title={sub.id === 'square' ? '常见平方数对照表' : '百化分对照表'}
              stealth={stealth}
            >
              <BookOpen size={12} />
            </IconBtn>
          )}
          <IconBtn
            onClick={() => setBlurred((v) => !v)}
            title="Ctrl+B 模糊题目"
            stealth={stealth}
          >
            {blurred ? <EyeOff size={12} /> : <Eye size={12} />}
          </IconBtn>
          <IconBtn
            onClick={() => setStealth((v) => !v)}
            title="Ctrl+H 伪装模式"
            stealth={stealth}
            wide
          >
            {stealth ? 'NORMAL' : 'STEALTH'}
          </IconBtn>
          <IconBtn onClick={resetStats} title="重置计数" stealth={stealth}>
            <RotateCcw size={12} />
          </IconBtn>
        </div>
      </div>

      {/* 题目卡片 */}
      <div className="flex-1 flex items-center justify-center px-3 py-1 min-h-0">
        <div
          className={`w-full rounded-2xl px-5 py-4 ${theme.card} shadow-sm transition-colors`}
        >
          <div
            className={`text-center py-3 transition-all ${blurred ? 'blur-md' : ''}`}
          >
            <p
              className={`text-[28px] font-black tracking-tight break-words leading-tight ${theme.prompt}`}
            >
              {question.prompt}
            </p>
          </div>

          {/* 输入/反馈区 */}
          <div
            className={`mt-2 rounded-xl h-14 flex items-center justify-center px-4 transition-all ${fbCls}`}
          >
            <div className="flex items-center justify-center space-x-3 min-w-0">
              {feedback && (
                <span
                  className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                    feedback.ok
                      ? 'bg-emerald-500 text-white'
                      : feedback.skipped
                        ? 'bg-slate-400 text-white'
                        : 'bg-[#ff6b6b] text-white'
                  }`}
                  style={{ animation: 'pop 180ms ease-out' }}
                >
                  {feedback.ok ? (
                    <Check size={16} strokeWidth={3.5} />
                  ) : (
                    <X size={16} strokeWidth={3.5} />
                  )}
                </span>
              )}
              <p className="text-2xl font-black tracking-tight truncate">
                {feedback && !feedback.ok ? (
                  <>
                    {!feedback.skipped && (
                      <span className={`mr-2 line-through ${theme.strike}`}>{input}</span>
                    )}
                    <span className={theme.answer}>{feedback.answer}</span>
                  </>
                ) : input === '' ? (
                  <span className={`text-sm font-bold ${theme.hint}`}>
                    {stealth ? '输入后回车' : '输入答案 · Enter'}
                  </span>
                ) : (
                  <span className={`tabular-nums ${theme.prompt}`}>{input}</span>
                )}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 底栏：统计 */}
      <div
        className={`px-3 pt-1 pb-2 text-[10px] font-bold uppercase tracking-widest flex items-center justify-between ${stealth ? 'text-slate-400' : 'text-white/45'}`}
      >
        <div className="flex items-center space-x-2">
          {mode === 'race' && (
            <>
              <span className={`${theme.accent} text-[11px] normal-case tracking-normal`}>
                {Math.min(total, raceSize)}/{raceSize}
              </span>
              <span className="opacity-40">·</span>
            </>
          )}
          <span className={`${theme.accent} text-[11px]`}>{accuracy}%</span>
          <span className="opacity-40">·</span>
          <span className="normal-case tracking-normal font-semibold">
            <span className="text-emerald-400">✓</span> {stats.correct}
          </span>
          <span className="normal-case tracking-normal font-semibold">
            <span className="text-[#ff6b6b]">✗</span> {stats.wrong}
          </span>
          {stats.skipped > 0 && (
            <span className="normal-case tracking-normal font-semibold opacity-70">
              ↷ {stats.skipped}
            </span>
          )}
        </div>
        <div className="flex items-center space-x-2 font-mono tabular-nums normal-case tracking-normal">
          <span title="本次总时间" className={theme.accent}>
            {fmtDuration(sessionMs)}
          </span>
          <span className="opacity-40">·</span>
          <span title="平均用时">avg {fmtMs(avgMs)}</span>
          {stats.bestMs != null && (
            <>
              <span className="opacity-40">·</span>
              <span title="最快用时" className="opacity-70">
                best {fmtMs(stats.bestMs)}
              </span>
            </>
          )}
          <button
            onClick={skip}
            title="跳过 (Esc)"
            className="ml-1 p-1 rounded hover:opacity-100 opacity-70"
          >
            <SkipForward size={12} />
          </button>
        </div>
      </div>

      <style>{`
        @keyframes pop {
          0%   { transform: scale(0.3); opacity: 0; }
          60%  { transform: scale(1.15); opacity: 1; }
          100% { transform: scale(1); opacity: 1; }
        }
        html, body, #root { height: 100%; }
        body { margin: 0; overflow: hidden; }
        .popup-root ::-webkit-scrollbar { display: none; }
      `}</style>

      {raceDone && (
        <PopupRaceResult
          stealth={stealth}
          result={raceDone}
          onRetry={retrySameRace}
          onPickModule={() => {
            setRaceDone(null);
            openModulePicker('mode'); // 一层一层退：练习 → 模式 → 题型 → 大类
          }}
        />
      )}

      {picking && (
        <PopupModulePicker
          stealth={stealth}
          step={picking}
          cats={availableCats}
          pickCatId={pickCatId}
          currentCatId={catId}
          currentSubId={subId}
          draftCatId={draftCatId}
          draftSubId={draftSubId}
          draftMode={draftMode}
          draftRaceSize={draftRaceSize}
          onBack={() => {
            if (picking === 'mode') setPicking('sub');
            else if (picking === 'sub') setPicking('cat');
            else setPicking(null);
          }}
          onPickCat={pickCategory}
          onPickSub={pickSub}
          onDraftMode={setDraftMode}
          onDraftRaceSize={setDraftRaceSize}
          onStart={startFromPicker}
        />
      )}

      {showTable && sub?.id === 'square' && (
        <PopupSquareTable stealth={stealth} onClose={() => setShowTable(false)} />
      )}
      {showTable && sub?.id === 'pctToFrac' && (
        <PopupBaiHuaFenTable stealth={stealth} onClose={() => setShowTable(false)} />
      )}
    </div>
  );
};

const PopupRaceResult = ({ stealth, result, onRetry, onPickModule }) => {
  const lp = result?.rankChange?.lp;
  const before = lp ? getRank(lp.rankBefore) : null;
  const after = lp ? getRank(lp.rankAfter) : null;
  const delta = lp?.lpDelta ?? 0;
  const promoted = !!lp?.promoted;
  const demoted = !!lp?.demoted;
  const kept = !!lp && !promoted && !demoted;
  const deltaCls = delta > 0
    ? (stealth ? 'text-emerald-600' : 'text-emerald-400')
    : delta < 0
      ? (stealth ? 'text-rose-600' : 'text-[#ff6b6b]')
      : (stealth ? 'text-slate-500' : 'text-white/50');
  const status = promoted
    ? { text: '升段！', cls: stealth ? 'text-amber-600' : 'text-[#6b5428]' }
    : demoted
      ? { text: '掉段', cls: stealth ? 'text-rose-600' : 'text-[#ff6b6b]' }
      : lp?.protected
        ? { text: '保留段位 · 实力保护', cls: stealth ? 'text-emerald-600' : 'text-emerald-400' }
        : { text: '保留段位', cls: stealth ? 'text-slate-600' : 'text-white/70' };

  return (
    <div className={`absolute inset-0 z-30 flex flex-col ${stealth ? 'bg-[#fafafa] text-slate-800' : 'bg-[#1a1a1a] text-white'}`}>
      <div className="flex-1 flex flex-col items-center justify-center px-3 text-center gap-1.5 min-h-0 overflow-y-auto py-2">
        <p className="text-[10px] font-black uppercase tracking-widest opacity-60">晋升完成</p>
        <p className={`text-2xl font-black tabular-nums ${stealth ? '' : 'text-[#6b5428]'}`}>
          {result.correct}/{result.total}
        </p>
        <p className="text-[11px] font-bold opacity-70">
          用时 {fmtDuration(result.totalMs)} · 均 {fmtMs(result.avgMs)}
        </p>

        {lp && (
          <div className={`w-full mt-2 rounded-2xl border px-3 py-2.5 ${
            stealth ? 'border-slate-200 bg-white' : 'border-white/10 bg-white/[0.04]'
          }`}>
            <p className={`text-3xl font-black italic tabular-nums leading-none ${deltaCls}`}
              style={{ animation: 'pop 280ms ease-out' }}>
              {delta > 0 ? `+${delta}` : delta} LP
            </p>
            <p className={`text-xs font-black mt-1.5 ${status.cls}`}>{status.text}</p>

            <div className="flex items-center justify-center gap-3 mt-2.5">
              <div className="text-center opacity-55">
                <RankBadge rankId={before.id} size={36} />
                <p className="text-[9px] font-black mt-1 opacity-80">{before.label}</p>
                <p className="text-[9px] font-mono tabular-nums opacity-50">{lp.lpBefore}</p>
              </div>
              <span className={`text-lg font-black ${
                promoted ? (stealth ? 'text-amber-500' : 'text-[#6b5428]')
                  : demoted ? (stealth ? 'text-rose-500' : 'text-[#ff6b6b]')
                    : 'opacity-40'
              }`}>
                {promoted ? '⬆' : demoted ? '⬇' : '→'}
              </span>
              <div className="text-center">
                <RankBadge rankId={after.id} size={44} />
                <p className="text-[10px] font-black mt-1" style={{ color: after.color }}>{after.label}</p>
                <p className="text-[9px] font-mono tabular-nums opacity-70">
                  {after.id === 'king' ? 'MAX' : `${lp.lpAfter}/100`}
                </p>
              </div>
            </div>

            {kept && after.id !== 'king' && (
              <div className={`mt-2 h-1.5 rounded-full overflow-hidden ${stealth ? 'bg-slate-100' : 'bg-white/10'}`}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.max(0, Math.min(100, lp.lpAfter))}%`,
                    backgroundColor: after.color,
                  }}
                />
              </div>
            )}
          </div>
        )}
      </div>
      <div className="px-3 pb-3 flex gap-2 shrink-0">
        <button type="button" onClick={onRetry}
          className="flex-1 py-2 rounded-xl bg-[#2c261c] text-white text-xs font-black">
          再来一局
        </button>
        <button type="button" onClick={onPickModule}
          className={`flex-1 py-2 rounded-xl border text-xs font-black ${stealth ? 'border-slate-300' : 'border-white/20'}`}>
          返回
        </button>
      </div>
    </div>
  );
};

const PopupModulePicker = ({
  stealth,
  step,
  cats,
  pickCatId,
  currentCatId,
  currentSubId,
  draftCatId,
  draftSubId,
  draftMode,
  draftRaceSize,
  onBack,
  onPickCat,
  onPickSub,
  onDraftMode,
  onDraftRaceSize,
  onStart,
}) => {
  const bg = stealth ? 'bg-[#fafafa]' : 'bg-[#1a1a1a]';
  const muted = stealth ? 'text-slate-500' : 'text-white/60';
  const titleCls = stealth ? 'text-slate-800' : 'text-white';
  const cell = stealth
    ? 'bg-white border-slate-200 text-slate-800 hover:border-slate-400'
    : 'bg-white/[0.06] border-white/10 text-white hover:border-[#6b5428]/50 hover:bg-white/[0.1]';
  const active = stealth
    ? 'bg-slate-800 text-white border-slate-800'
    : 'bg-[#2c261c] text-white border-[#6b5428]';
  // 高亮跟「当前浏览」走，不要静默掉回 cats[0]/cats[1]
  const selectedCatId = pickCatId || draftCatId || currentCatId;
  const pickCat = cats.find((c) => c.id === selectedCatId) || null;
  const selectedSubId = draftSubId || (pickCat?.id === currentCatId ? currentSubId : '') || pickCat?.subs?.[0]?.id || '';
  const draftSub = getSub(pickCat?.id, selectedSubId);
  const head =
    step === 'mode'
      ? (draftSub?.name || '选择模式')
      : step === 'sub'
        ? (pickCat?.name || '子项')
        : '选择模块';
  const backLabel = step === 'mode' ? '题型' : step === 'sub' ? '模块' : '练习中';

  return (
    <div className={`absolute inset-0 ${bg} flex flex-col z-20`} style={{ animation: 'fade-in 120ms ease-out' }}>
      <div className={`flex items-center justify-between px-2.5 py-2 text-[11px] font-bold uppercase tracking-widest ${muted}`}>
        <button type="button" onClick={onBack} className={`flex items-center gap-0.5 ${titleCls}`}>
          <ChevronLeft size={14} />
          <span>{backLabel}</span>
        </button>
        <span className={`normal-case tracking-normal truncate max-w-[55%] ${titleCls}`}>{head}</span>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1.5">
        {step === 'cat' &&
          cats.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => onPickCat(c.id)}
              className={`w-full text-left px-3 py-2.5 rounded-xl border text-sm font-bold transition-colors ${
                c.id === selectedCatId ? active : cell
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate">{c.name}</span>
                <span className={`text-[10px] font-black uppercase tracking-widest opacity-60 ${c.id === selectedCatId ? '' : muted}`}>
                  {c.subs.length} 项
                </span>
              </div>
            </button>
          ))}
        {step === 'sub' &&
          (pickCat?.subs || []).map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => pickCat && onPickSub(pickCat.id, s.id)}
              className={`w-full text-left px-3 py-2 rounded-xl border text-sm font-bold transition-colors ${
                s.id === selectedSubId ? active : cell
              }`}
            >
              {s.name}
            </button>
          ))}
        {step === 'mode' && (
          <>
            <button
              type="button"
              onClick={() => onDraftMode('train')}
              className={`w-full text-left px-3 py-2.5 rounded-xl border text-sm font-bold transition-colors ${
                draftMode === 'train' ? active : cell
              }`}
            >
              <div>训练模式</div>
              <div className={`text-[10px] font-medium mt-0.5 normal-case tracking-normal ${draftMode === 'train' ? 'opacity-80' : muted}`}>
                不限题数，不计段位
              </div>
            </button>
            <button
              type="button"
              onClick={() => onDraftMode('race')}
              className={`w-full text-left px-3 py-2.5 rounded-xl border text-sm font-bold transition-colors ${
                draftMode === 'race' ? active : cell
              }`}
            >
              <div>晋升模式</div>
              <div className={`text-[10px] font-medium mt-0.5 normal-case tracking-normal ${draftMode === 'race' ? 'opacity-80' : muted}`}>
                限题挑战，计入段位
              </div>
            </button>
            {draftMode === 'race' && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {RACE_SIZE_PRESETS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => onDraftRaceSize(n)}
                    className={`px-2.5 py-1 rounded-lg border text-xs font-black ${
                      Number(draftRaceSize) === n ? active : cell
                    }`}
                  >
                    {n} 题
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={onStart}
              className="w-full mt-2 px-3 py-2.5 rounded-xl bg-[#2c261c] text-white text-sm font-black"
            >
              开始{draftMode === 'race' ? `晋升 · ${draftRaceSize}题` : '训练'}
            </button>
          </>
        )}
      </div>
    </div>
  );
};

const IconBtn = ({ children, onClick, title, stealth, wide }) => (
  <button
    onClick={onClick}
    title={title}
    className={`${wide ? 'px-1.5' : 'p-1'} rounded-md text-[9px] transition-colors ${
      stealth
        ? 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
        : 'text-white/50 hover:text-white hover:bg-white/10'
    }`}
  >
    {children}
  </button>
);

// 小窗内的百化分对照表（铺满整个小窗内容区）
const PopupBaiHuaFenTable = ({ stealth, onClose }) => {
  const bg = stealth ? 'bg-[#fafafa]' : 'bg-[#1a1a1a]';
  const cellBg = stealth ? 'bg-white border-slate-200' : 'bg-white/[0.06] border-white/10';
  const text = stealth ? 'text-slate-800' : 'text-white';

  return (
    <div
      className={`absolute inset-0 ${bg} flex flex-col`}
      onClick={onClose}
      style={{ animation: 'fade-in 150ms ease-out' }}
    >
      <div
        className={`flex items-center justify-between px-3 py-2 text-[11px] font-bold uppercase tracking-widest ${stealth ? 'text-slate-500' : 'text-white/70'}`}
      >
        <span>百化分 · 1/3 ~ 1/19</span>
        <span className="normal-case tracking-normal opacity-70">点空白 / ESC 关闭</span>
      </div>

      <div
        className="flex-1 overflow-y-auto px-2 pb-2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="grid grid-cols-3 gap-1.5">
          {BAI_HUA_FEN_TABLE.map((f) => (
            <div
              key={f.den}
              className={`flex items-center justify-between px-2.5 py-2 rounded-lg border ${cellBg}`}
            >
              <span className={`font-black text-base ${text}`}>1/{f.den}</span>
              <span className={`text-sm font-black tabular-nums ${text}`}>
                {f.pct}%
              </span>
            </div>
          ))}
        </div>
      </div>
      <style>{`
        @keyframes fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
    </div>
  );
};

// 小窗内的常见平方数对照表
const PopupSquareTable = ({ stealth, onClose }) => {
  const bg = stealth ? 'bg-[#fafafa]' : 'bg-[#1a1a1a]';
  const cellBg = stealth ? 'bg-white border-slate-200' : 'bg-white/[0.06] border-white/10';
  const text = stealth ? 'text-slate-800' : 'text-white';

  return (
    <div
      className={`absolute inset-0 ${bg} flex flex-col`}
      onClick={onClose}
      style={{ animation: 'fade-in 150ms ease-out' }}
    >
      <div
        className={`flex items-center justify-between px-3 py-2 text-[11px] font-bold uppercase tracking-widest ${stealth ? 'text-slate-500' : 'text-white/70'}`}
      >
        <span>常见平方数 · 11² ~ 29²</span>
        <span className="normal-case tracking-normal opacity-70">点空白 / ESC 关闭</span>
      </div>

      <div
        className="flex-1 overflow-y-auto px-2 pb-2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="grid grid-cols-3 gap-1.5">
          {SQUARE_TABLE.map((s) => (
            <div
              key={s.n}
              className={`flex items-center justify-between px-2.5 py-2 rounded-lg border ${cellBg}`}
            >
              <span className={`font-black text-base ${text}`}>{s.n}²</span>
              <div className={`text-sm font-black tabular-nums ${text}`}>
                {s.sq}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PopupPractice;

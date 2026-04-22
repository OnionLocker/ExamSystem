import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, X, SkipForward, RotateCcw, Eye, EyeOff, Timer, BookOpen } from 'lucide-react';
import { CATEGORIES, generate, getSub, judge, BAI_HUA_FEN_TABLE, SQUARE_TABLE } from './generators.js';

// 小窗练习组件
// 两种启动途径：
//   1) Document Picture-in-Picture（首选，无浏览器 chrome，始终置顶）
//      -> 由外部挂载，通过 props 传入 { catId, subId, mode, embedded: true }
//   2) window.open 弹窗（降级）
//      -> 通过 URL 参数 ?popup=1&cat=&sub=&mode= 传入

const FEEDBACK_CORRECT_MS = 120;
const FEEDBACK_WRONG_MS = 600;
const FEEDBACK_SKIP_MS = 300;

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
  // 参数来源：props 优先（PiP 模式），否则读 URL
  const { catId, subId } = useMemo(() => {
    if (pCat || pSub) return { catId: pCat || 'basic', subId: pSub || '', mode: pMode || 'train' };
    return readParams();
  }, [pCat, pSub, pMode]);

  const cat = CATEGORIES.find((c) => c.id === catId);
  const sub = getSub(catId, subId) || cat?.subs?.[0];

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
  const [, setTick] = useState(0);

  const timerRef = useRef(null);
  const pendingRef = useRef(null);

  // 定时刷新当前题用时
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 100);
    return () => clearInterval(id);
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

  const scheduleAdvance = (fb) => {
    pendingRef.current = true;
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
    pendingRef.current = null;
    setFeedback(null);
    nextQuestion();
  };

  const submit = () => {
    if (feedback || !question) return;
    if (input === '' || input === '-' || input === '.') return;
    const timeMs = Date.now() - qStartedAt;
    const isCorrect = judge(question, input);
    setStats((s) => ({
      ...s,
      correct: s.correct + (isCorrect ? 1 : 0),
      wrong: s.wrong + (isCorrect ? 0 : 1),
      totalMs: s.totalMs + timeMs,
      bestMs: isCorrect
        ? s.bestMs == null
          ? timeMs
          : Math.min(s.bestMs, timeMs)
        : s.bestMs,
    }));
    scheduleAdvance({ ok: isCorrect, skipped: false, answer: question.answer });
  };
  const skip = () => {
    if (feedback || !question) return;
    const timeMs = Date.now() - qStartedAt;
    setStats((s) => ({
      ...s,
      skipped: s.skipped + 1,
      totalMs: s.totalMs + timeMs,
    }));
    scheduleAdvance({ ok: false, skipped: true, answer: question.answer });
  };
  const resetStats = () => {
    setStats({ correct: 0, wrong: 0, skipped: 0, totalMs: 0, bestMs: null });
    setSessionStartedAt(Date.now());
    if (feedback) flushAdvance();
    nextQuestion();
  };

  // 键盘监听：监听组件所在 window（PiP 模式下是 PiP window）
  useEffect(() => {
    const win = typeof window !== 'undefined' ? window : null;
    if (!win) return;
    const onKey = (e) => {
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
  }, [feedback, input, question, qStartedAt, showTable]);

  if (!sub || !question) {
    return (
      <div className="popup-root min-h-screen flex items-center justify-center bg-white text-slate-500 text-sm font-medium p-6 text-center">
        未找到题型，请从主窗口重新打开小窗。
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
        accent: 'text-[#fbc02d]',
        answer: 'text-[#fbc02d]',
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
  const currentMs = Date.now() - qStartedAt;
  const sessionMs = Date.now() - sessionStartedAt;

  return (
    <div
      className={`popup-root relative h-full min-h-full flex flex-col ${theme.wrap} select-none overflow-hidden`}
      style={{ fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' }}
    >
      {/* 顶栏 */}
      <div
        className={`flex items-center justify-between px-3 pt-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-widest ${stealth ? 'text-slate-400' : 'text-white/50'}`}
      >
        <div className="flex items-center space-x-2 min-w-0">
          <span className="truncate">{stealth ? '文档 · 草稿' : sub.name}</span>
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

      {showTable && sub.id === 'square' && (
        <PopupSquareTable stealth={stealth} onClose={() => setShowTable(false)} />
      )}
      {showTable && sub.id === 'pctToFrac' && (
        <PopupBaiHuaFenTable stealth={stealth} onClose={() => setShowTable(false)} />
      )}
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
              <div className={`text-sm font-black tabular-nums ${text}`}>
                {(+f.pct.toFixed(1)).toString()}%
              </div>
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

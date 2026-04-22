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

// 缂佹稒妫冮。浠嬪矗瀹ュ娲柛瀣矌閺嗏偓闁哄啫鐖煎Λ鍧楁晬閸噥鍤戠紒澶嬪釜缁憋拷
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
  if (ms < 1000) return `${ms} 婵綆鍋嗛～姊�;
  return `${(ms / 1000).toFixed(1)} 缂佸濡�;
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

// ---------------- 濞戞捁宕电划宥嗙閿燂拷 ----------------
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
        <h2 className="text-4xl font-black tracking-tighter italic uppercase">闁轰焦濯界粊顐ょ磼閸愌呯槑</h2>
        <p className="text-sm font-medium text-slate-400 mt-2">
          濞寸姴楠搁悢鈧痪顓涘亾閻犱緤绱曢悾濠氬礆閹峰瞼銈柡鍌涚懃閸ㄥ酣寮搁幇鍓佺闁圭ǹ顦粭鎾淬亜閻熸澘鐎婚柛褎顨夐鍕磼閸愶腹鍋撻敓锟�
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
                    鐎点倝缂氶鏇熺▔閿燂拷
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
                  {cat.subs.length} 濞戞搩浜滈悺娆戠尵閿燂拷
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
          <span className="text-xs font-black uppercase tracking-widest">閺夆晜鏌ㄥú锟�</span>
        </button>
        <h2 className="text-2xl font-black italic">{cat.name}</h2>
        <button
          onClick={onOpenHistory}
          title="闁告ê妫楄ぐ鍓佹媼閺夎法绉�"
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <HistoryIcon size={16} />
          <span className="text-xs font-black uppercase tracking-widest hidden sm:inline">闁告ê妫楄ぐ锟�</span>
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
        <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">缂備礁鍟╃弧鍕熼垾宕囩</p>
        <ModeOption
          label="閻犱緡鍘剧划灞轿熼垾宕囩"
          desc="婵絽绻樻禍鐐紣濡偐鎽曢悗鐟拌嫰瀹撳棝寮伴崜褋浠涢悗闈涚秺閺佸﹪鏁嶅畝鍐ㄦ闁告柣鍔忕换姗€宕楅妷銈囩憮濞戞挴鍋撳Λ甯嫹"
          checked={mode === 'train'}
          onClick={() => onPickMode('train')}
          color="#22c55e"
        />
        <ModeOption
          label="缂佹梻鍋ら埀顒傚枑鑶╃€殿噯鎷�"
          desc={`${RACE_SIZE} 濡増眉缁斿绱掗崟鍓佺缂備焦鎸诲ḿ顐﹀触鎼淬垻婀介柟顒冨吹閺併倝寮捄鐑樺婵繐绲块垾姗€鎮抽崲绔�
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
          <span>鐎殿喒鍋撳┑顔碱儑缁本绋婇敓锟�</span>
        </button>
        <button
          onClick={onOpenHistory}
          className="px-8 bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs flex items-center space-x-2"
        >
          <HistoryIcon size={14} />
          <span>闁告ê妫楄ぐ鍓佹媼閺夎法绉�</span>
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

// ---------------- Session闁挎稑鐗忛崙浠嬫煥椤旂偓纾� + 闁告娅曞鍌炲矗瀹ュ娲柨娑虫嫹 ----------------
const SessionView = ({ session, setSession, onExit, onFinishRace }) => {
  const [, setTick] = useState(0);
  const [feedback, setFeedback] = useState(null); // null | { ok, skipped, answer }
  const timerRef = useRef(null);
  const pendingRef = useRef(null); // { newRecords, isLast }

  // 閻犱緤鎷�"闁哄牜鍓熼。浠嬫偨閵婏附顦�"闁归晲鑳堕悽濠氬即鐎涙ɑ鐓€
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 100);
    return () => clearInterval(id);
  }, []);

  // 闁告鐡曞ù鍥籍閼哥數顏搁悗瑙勭濡炲倿宕抽敓锟�
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  // 闂佹鍠氬ú蹇旀綇閹惧啿寮�
  useEffect(() => {
    const onKey = (e) => {
      if (!session) return;

      // 闁告瑥绉归々顓㈡⒓閼告鍞介柨娑欘儛nter/Space 缂佹柨顑呭畵鍡欐崉鐎圭姷绠栫紒娑橆槸缁讹拷
      if (feedback) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          flushAdvance();
        }
        return;
      }

      // 闊洨鏅弳鎰磼閸曨偅鍊ら梺鍖℃嫹
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

  const totalStr = total === Infinity ? '闁愁叏鎷�' : String(total);
  const progress = `${index + 1} / ${totalStr}`;
  const correctCount = records.filter((r) => r.isCorrect).length;

  // 闁告瑥绉归々顓㈠冀瀹勬壆纭€
  const fbBg = feedback
    ? feedback.ok
      ? 'bg-emerald-500/25 ring-2 ring-emerald-400'
      : feedback.skipped
        ? 'bg-slate-400/20 ring-2 ring-slate-400'
        : 'bg-[#ff6b6b]/20 ring-2 ring-[#ff6b6b]'
    : 'bg-white/10 ring-0';

  return (
    <div className="max-w-2xl mx-auto">
      {/* 濡炪倕鐖奸崕瀛樼┍閳╁啩绱栭柡澶涙嫹 */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={onExit}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">闂侇偀鍋撻柛鎴嫹</span>
        </button>
        <div className="text-xs font-black uppercase tracking-widest text-slate-400">
          {session.subName} 鐠猴拷 {mode === 'race' ? '缂佹梻鍋ら埀顒傚枑鑶╃€殿噯鎷�' : '閻犱緡鍘剧划灞轿熼垾宕囩'}
        </div>
      </div>

      {/* 濡増岣垮ú浼村础閿燂拷 */}
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 shadow-xl shadow-black/10 relative overflow-hidden">
        {/* 闁告瑥绉归々顓㈠籍閸撲焦鐣遍柡浣规綑瀹曢亶宕ｉ幋婵嗗辅 */}
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
            <span>闁哄牜鍓熼。浠嬫偨閵婏附顦� {fmtMs(elapsed)}</span>
          </div>

          <div className="text-center py-8">
            <p className="text-4xl md:text-5xl font-black tracking-tight break-words leading-tight">
              {current.prompt}
            </p>
          </div>

          {/* 閺夊牊鎸搁崣锟�/闁告瑥绉归々顓㈠礌閿燂拷 */}
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
                  <span className="opacity-30 text-2xl">閺夊牊鎸搁崣鍡欑驳閺冣偓椤㈠秹鏁嶇仦鎯х樆 Enter 缁绢収鍠涢锟�</span>
                ) : (
                  input
                )}
              </p>
            </div>
          </div>

          {/* 閹煎瓨娲熼崕纾嬬疀椤愶絽绁归梺娆惧枟瑜颁胶绮堥敓锟� + 閻忓繐绻楅锟� */}
          <div className="mt-6 flex items-center justify-between text-[10px] font-black uppercase tracking-widest opacity-40">
            <div className="flex items-center space-x-3">
              <span>Enter 缁绢収鍠涢锟�</span>
              <span>鐠猴拷</span>
              <span>Backspace 闁告帪鎷�</span>
              <span>鐠猴拷</span>
              <span>Esc 閻犲搫鐤囩换锟�</span>
            </div>
            <div>
              婵繐绲块垾锟� {correctCount} / 鐎规瓕灏欓悺锟� {records.length}
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
            {result.subName} 鐠猴拷 缂佹梻鍋ら埀顒傚枎閻ｎ剟骞嬮敓锟�
          </p>
          <p className="text-5xl font-black italic">{accuracy}%</p>
          <p className="text-sm font-medium opacity-60 mt-1">
            闁稿骏鎷� {result.total} 濡府鎷� 鐠猴拷 婵繐绲块垾锟� {result.correct} 鐠猴拷 闂佹寧鐟ㄩ锟� {result.wrong} 鐠猴拷 閻犲搫鐤囩换鍎�' '}
            {result.skipped}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 mt-8">
          <StatCell label="闁诡剝宕甸弫銈夊籍閿燂拷" value={fmtMs(result.totalMs)} />
          <StatCell label="妤犵偛鍟垮ḿ搴⌒掕箛娑辨毌" value={fmtMs(result.avgMs)} />
        </div>
      </div>

      <div className="bg-white rounded-[2rem] p-6 border border-[#f2f0e9]">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">闂侇偅鍔欓。浠嬪及鎼达絿鐭�</p>
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
                  {r.skipped ? '閻犲搫鐤囩换锟�' : `濞达綇鎷�: ${r.userAnswer}`}
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
          <span>闁告劕绉靛ḿ鍨▔閳ь剛绱掗敓锟�</span>
        </button>
        <button
          onClick={onSubs}
          className="px-6 bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs"
        >
          闁瑰箍鍨介。浠嬪垂閿燂拷
        </button>
        <button
          onClick={onHome}
          className="px-6 bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black rounded-2xl hover:border-[#1a1a1a] transition-all uppercase tracking-widest text-xs"
        >
          閺夆晜鏌ㄥú锟�
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
    if (confirm('缁绢収鍠栭悾鍓ф啺娴ｅ湱顏哥紒宀€鍎ゆ晶宥夊嫉婢跺﹤鍧婇柛娆掑蔼椤斿洩銇愰弴鐐村亱闁挎冻鎷�')) {
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
          <span className="text-xs font-black uppercase tracking-widest">閺夆晜鏌ㄥú锟�</span>
        </button>
        <h2 className="text-2xl font-black italic">闁告ê妫楄ぐ鍓佹媼閺夎法绉�</h2>
        <button
          onClick={clearAll}
          disabled={list.length === 0}
          className="text-xs font-black uppercase tracking-widest text-slate-400 hover:text-[#ff6b6b] disabled:opacity-30 transition-colors"
        >
          婵炴挸鎳愰埞锟�
        </button>
      </div>

      {list.length === 0 ? (
        <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-16 text-center">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-[#f2f0e9] flex items-center justify-center mb-4 text-slate-400">
            <HistoryIcon size={28} />
          </div>
          <p className="text-sm font-bold text-slate-400">闁哄棗鍊瑰Λ銈囩博閻愯　鍋撻悢铏圭煀濞戞梻濮鹃鍥亹閿燂拷</p>
          <p className="text-xs text-slate-400 mt-1">閻庣懓鏈崹姘▔閳ь剙鈻庨敓锟�"缂佹梻鍋ら埀顒傚枑鑶╃€殿噯鎷�"闁告艾绨肩槐浼存嚊椤忓嫬袟濞ｅ洦绻傞悺銊╁礆閹峰瞼绠归梺璇ф嫹</p>
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
                  <HistoryStat label="婵繐绲块垾姗€鎮抽敓锟�" value={`${accuracy}%`} accent />
                  <HistoryStat label="闁烩偓鍔嶅锟�" value={fmtMs(r.totalMs)} />
                  <HistoryStat label="妤犵偛鍟垮ḿ锟�" value={fmtMs(r.avgMs)} />
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

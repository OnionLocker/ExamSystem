import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
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
  PictureInPicture2,
  BookOpen,
  Gamepad2,
} from 'lucide-react';
import { CATEGORIES, generate, getSub, judge, BAI_HUA_FEN_TABLE, SQUARE_TABLE } from './generators.js';
import PopupPractice from './PopupPractice.jsx';
import { addEntry as addStudyEntry, scoreNumeric } from '../studyLog/studyLog.js';
import RankDashboard from './RankDashboard.jsx';
import RankBadge from './RankBadge.jsx';
import { recordPromotionResult, getRank, getBaseMs, getLadderInfo } from './ranks.js';
import GamesHome from './games/GamesHome.jsx';
import { playBgm, stopBgm } from './bgm.js';
import BgmControls from './BgmControls.jsx';

const HISTORY_KEY = 'numeric_practice_history_v1';
const RACE_SIZE_DEFAULT = 10;
const RACE_SIZE_PRESETS = [5, 10, 20, 50];
const RACE_SIZE_MIN = 1;
const RACE_SIZE_MAX = 200;

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

// 较长时长用 mm:ss / h:mm:ss
const fmtDuration = (ms) => {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  if (h > 0) return `${h}:${pad(m)}:${pad(sec)}`;
  return `${pad(m)}:${pad(sec)}`;
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
  const [raceSize, setRaceSize] = useState(RACE_SIZE_DEFAULT);

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
    const safeRace = Math.max(
      RACE_SIZE_MIN,
      Math.min(RACE_SIZE_MAX, Number(raceSize) || RACE_SIZE_DEFAULT),
    );
    const total = mode === 'race' ? safeRace : Infinity;
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
      // ready=false 时:渲染入场蒙版,等用户按空格才真正开始计时 + 起 BGM
      ready: false,
      startedAt: 0,
      questionStartedAt: 0,
      records: [],
    });
    setView('session');
  };
  const finishRace = (records, catId, subId, subName) => {
    const totalMs = records.reduce((s, r) => s + r.timeMs, 0);
    const correct = records.filter((r) => r.isCorrect).length;
    const wrong = records.filter((r) => !r.isCorrect && !r.skipped).length;
    const skipped = records.filter((r) => r.skipped).length;
    // 写入段位统计（只算晋升模式），拿到段位变化
    const rankChange = recordPromotionResult({
      subId,
      total: records.length,
      correct,
      totalMs,
    });
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
      rankChange, // { before, after }
    };
    const list = loadHistory();
    list.unshift(result);
    saveHistory(list.slice(0, 100));
    // 写入学习日志
    addStudyEntry({
      type: 'numeric',
      module: subName,
      count: result.total,
      correct: result.correct,
      score: scoreNumeric(result.total, result.correct),
    });
    setSessionResult(result);
    setView('result');
  };
  const openHistory = () => setView('history');

  if (view === 'home') return <HomeView onPick={openCategory} onOpenGames={() => setView('games')} />;
  if (view === 'games') return <GamesHome onBack={goHome} />;
  if (view === 'subs')
    return (
      <SubsView
        cat={currentCat}
        subId={currentSubId}
        mode={mode}
        raceSize={raceSize}
        onBack={goHome}
        onPickSub={setCurrentSubId}
        onPickMode={setMode}
        onPickRaceSize={setRaceSize}
        onStart={startSession}
        onOpenHistory={openHistory}
      />
    );
  if (view === 'session')
    return (
      <SessionView
        session={session}
        setSession={setSession}
        onExit={() => {
          setSession(null);
          setView('subs');
        }}
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
const HomeView = ({ onPick, onOpenGames }) => {
  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* 段位总览横幅 */}
      <RankDashboard onClickCategory={onPick} />

      <div>
        <h2 className="text-4xl font-black tracking-tighter italic uppercase">数资练习</h2>
        <p className="text-sm font-medium text-slate-400 mt-2">
          选择一个练习分类，进入题库开始训练，或挑战「晋升模式」冲击更高段位。
        </p>
      </div>

      <button
        onClick={onOpenGames}
        className="w-full text-left rounded-[2rem] p-6 bg-[#1a1a1a] text-white hover:-translate-y-1 hover:shadow-xl hover:shadow-black/10 transition-all group overflow-hidden relative"
      >
        <div className="absolute -right-10 -top-10 w-36 h-36 rounded-full bg-[#fbc02d]/15 blur-2xl" />
        <div className="relative flex flex-col md:flex-row md:items-center md:justify-between gap-5">
          <div className="flex items-start space-x-4">
            <div className="w-14 h-14 rounded-2xl bg-[#fbc02d] text-black flex items-center justify-center flex-shrink-0">
              <Gamepad2 size={24} />
            </div>
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.25em] text-[#fbc02d]">
                小游戏模块
              </p>
              <h3 className="text-2xl font-black italic mt-2">认知训练 · 3 款</h3>
              <p className="text-sm font-medium text-white/65 mt-1">
                点数字 · 移位加减 · 数字记忆广度。从找数到工作记忆扩容，专治考公心算的认知瓶颈。
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 md:flex-col md:items-end">
            <div className="flex items-center gap-2 flex-wrap justify-start md:justify-end text-[10px] font-black uppercase tracking-widest text-white/45">
              <span className="px-2.5 py-1 rounded-full bg-white/10">点数字</span>
              <span className="px-2.5 py-1 rounded-full bg-white/10">移位加减</span>
              <span className="px-2.5 py-1 rounded-full bg-white/10">记忆广度</span>
            </div>
            <div className="flex items-center space-x-2 text-xs font-black uppercase tracking-widest text-white/70 group-hover:text-[#fbc02d] transition-colors">
              <span>进入小游戏</span>
              <ChevronRight size={16} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </div>
      </button>

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
const SubsView = ({
  cat,
  subId,
  mode,
  raceSize,
  onBack,
  onPickSub,
  onPickMode,
  onPickRaceSize,
  onStart,
  onOpenHistory,
}) => {
  if (!cat) return null;

  const openPopup = async () => {
    if (!subId) return;
    const w = 420;
    const h = 300;

    // 方案 1：Document Picture-in-Picture（Chrome/Edge 116+）
    // 优势：无浏览器标题栏 + 地址栏，默认置顶悬浮
    if (window.documentPictureInPicture?.requestWindow) {
      try {
        const pipWin = await window.documentPictureInPicture.requestWindow({
          width: w,
          height: h,
        });

        // 将当前文档的所有样式（Vite 注入的 <style> 与 <link rel="stylesheet">）复制到 PiP 窗
        const copyStyles = () => {
          [...document.styleSheets].forEach((sheet) => {
            try {
              if (sheet.cssRules) {
                const style = pipWin.document.createElement('style');
                style.textContent = [...sheet.cssRules].map((r) => r.cssText).join('\n');
                pipWin.document.head.appendChild(style);
              }
            } catch {
              // 跨域样式表，降级用 <link>
              if (sheet.href) {
                const link = pipWin.document.createElement('link');
                link.rel = 'stylesheet';
                link.href = sheet.href;
                pipWin.document.head.appendChild(link);
              }
            }
          });
          // <style> 标签也拷贝一份（保险）
          document.head.querySelectorAll('style').forEach((node) => {
            pipWin.document.head.appendChild(node.cloneNode(true));
          });
        };
        copyStyles();

        // 基本样式
        const baseStyle = pipWin.document.createElement('style');
        baseStyle.textContent = `
          html, body { margin: 0; padding: 0; height: 100%; overflow: hidden;
            font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
          #pip-root { height: 100%; }
        `;
        pipWin.document.head.appendChild(baseStyle);

        // 挂载 React
        const container = pipWin.document.createElement('div');
        container.id = 'pip-root';
        pipWin.document.body.appendChild(container);
        const root = createRoot(container);
        root.render(
          <PopupPractice catId={cat.id} subId={subId} mode={mode} embedded />,
        );

        // 关闭时卸载
        pipWin.addEventListener('pagehide', () => {
          try {
            root.unmount();
          } catch {
            // ignore
          }
        });
        return;
      } catch (err) {
        // 用户拒绝或不支持 -> 降级
        console.warn('Document PiP failed, falling back to window.open:', err);
      }
    }

    // 方案 2：降级 window.open（会有标题栏/地址栏）
    const params = new URLSearchParams({
      popup: '1',
      cat: cat.id,
      sub: subId,
      mode,
    });
    const url = `${window.location.pathname}?${params.toString()}`;
    const left =
      (window.screen.availLeft || 0) + (window.screen.availWidth || 1280) - w - 40;
    const top =
      (window.screen.availTop || 0) + (window.screen.availHeight || 800) - h - 80;
    const features = [
      `width=${w}`,
      `height=${h}`,
      `left=${Math.max(0, left)}`,
      `top=${Math.max(0, top)}`,
      'popup=yes',
      'resizable=yes',
      'scrollbars=no',
      'menubar=no',
      'toolbar=no',
      'location=no',
      'status=no',
    ].join(',');
    const winRef = window.open(url, `study_popup_${cat.id}_${subId}`, features);
    if (winRef) winRef.focus();
  };

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
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400">选择模式</p>
          {subId && <SubRankChip subId={subId} subName={cat.subs.find((s) => s.id === subId)?.name} />}
        </div>
        <ModeOption
          label="训练模式"
          desc="不限题数，专注练习。按 Esc 可跳过，随时可退出。成绩不计入段位。"
          checked={mode === 'train'}
          onClick={() => onPickMode('train')}
          color="#22c55e"
        />
        <ModeOption
          label="晋升模式"
          desc={`${raceSize} 题限时挑战，计入段位统计。达到速度 + 准度双标即可晋升。`}
          checked={mode === 'race'}
          onClick={() => onPickMode('race')}
          color="#fbc02d"
          highlight
        />
        {mode === 'race' && (
          <RaceSizePicker value={raceSize} onChange={onPickRaceSize} />
        )}
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
          onClick={openPopup}
          title="悬浮小窗练习（Chrome/Edge 支持无边框悬浮窗）"
          className="px-6 bg-white border border-[#f2f0e9] text-[#1a1a1a] font-black rounded-2xl hover:border-[#1a1a1a] hover:bg-[#fbc02d] transition-all uppercase tracking-widest text-xs flex items-center space-x-2"
        >
          <PictureInPicture2 size={14} />
          <span className="hidden sm:inline">小窗练习</span>
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

const ModeOption = ({ label, desc, checked, onClick, color, highlight }) => (
  <button
    onClick={onClick}
    className={`w-full flex items-center space-x-4 p-4 rounded-2xl border transition-all text-left relative overflow-hidden ${
      checked ? 'border-[#1a1a1a] bg-[#f2f0e9]/50' : 'border-[#f2f0e9] hover:border-slate-300'
    }`}
  >
    {highlight && (
      <span
        className="absolute top-2 right-3 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full"
        style={{ backgroundColor: `${color}22`, color }}
      >
        计入段位
      </span>
    )}
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

// 子项段位小徽章（显示当前子项已达段位 + LP 进度）
const SubRankChip = ({ subId, subName }) => {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const onChange = () => setVersion((v) => v + 1);
    window.addEventListener('numeric-rank-change', onChange);
    return () => window.removeEventListener('numeric-rank-change', onChange);
  }, []);
  const ladder = (() => {
    // eslint-disable-next-line no-unused-expressions
    version; // 触发重算
    return getLadderInfo(subId);
  })();
  const rank = getRank(ladder.rankId);
  const base = getBaseMs(subId);
  const showLp = ladder.hasLadder && ladder.rankId !== 'unranked' && ladder.rankId !== 'king';
  return (
    <div
      className="flex items-center space-x-2 px-3 py-1.5 rounded-full"
      style={{ backgroundColor: `${rank.color}15` }}
      title={`${subName || ''} 当前段位：${rank.label} · LP ${ladder.lp}/100 · 基线 ${(base / 1000).toFixed(1)}s/题`}
    >
      <RankBadge rankId={ladder.rankId} size={20} />
      <span className="text-[11px] font-black italic" style={{ color: rank.color }}>
        {rank.label}
      </span>
      {showLp && (
        <span className="text-[9px] font-black tabular-nums text-slate-400">
          {ladder.lp} LP
        </span>
      )}
    </div>
  );
};

// 冲刺模式题数选择器：预设 + 自定义输入
const RaceSizePicker = ({ value, onChange }) => {
  const isPreset = RACE_SIZE_PRESETS.includes(Number(value));
  const clamp = (n) => Math.max(RACE_SIZE_MIN, Math.min(RACE_SIZE_MAX, n));
  return (
    <div className="ml-10 mt-2 flex items-center flex-wrap gap-2">
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 mr-1">
        题数
      </span>
      {RACE_SIZE_PRESETS.map((n) => {
        const active = Number(value) === n;
        return (
          <button
            key={n}
            onClick={() => onChange(n)}
            className={`px-3 py-1.5 rounded-xl text-xs font-black transition-all border ${
              active
                ? 'bg-[#1a1a1a] text-[#fbc02d] border-[#1a1a1a]'
                : 'bg-white text-[#1a1a1a] border-[#f2f0e9] hover:border-[#1a1a1a]'
            }`}
          >
            {n}
          </button>
        );
      })}
      <div
        className={`flex items-center space-x-1 rounded-xl border px-2 py-1 transition-all ${
          !isPreset
            ? 'bg-[#1a1a1a] border-[#1a1a1a]'
            : 'bg-white border-[#f2f0e9] hover:border-[#1a1a1a]'
        }`}
      >
        <span
          className={`text-[10px] font-black uppercase tracking-widest ${
            !isPreset ? 'text-[#fbc02d]' : 'text-slate-400'
          }`}
        >
          自定义
        </span>
        <input
          type="number"
          min={RACE_SIZE_MIN}
          max={RACE_SIZE_MAX}
          value={value}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') return onChange('');
            const n = parseInt(raw, 10);
            if (!Number.isNaN(n)) onChange(clamp(n));
          }}
          onBlur={(e) => {
            const n = parseInt(e.target.value, 10);
            if (Number.isNaN(n)) onChange(RACE_SIZE_DEFAULT);
            else onChange(clamp(n));
          }}
          className={`w-14 bg-transparent text-center text-xs font-black focus:outline-none tabular-nums ${
            !isPreset ? 'text-[#fbc02d]' : 'text-[#1a1a1a]'
          }`}
        />
      </div>
      <span className="text-[10px] font-medium text-slate-400">
        ({RACE_SIZE_MIN}–{RACE_SIZE_MAX})
      </span>
    </div>
  );
};

// ---------------- Session（做题页 + 键盘输入） ----------------
const SessionView = ({ session, setSession, onExit, onFinishRace }) => {
  const [, setTick] = useState(0);
  const [feedback, setFeedback] = useState(null); // null | { ok, skipped, answer }
  const [showTable, setShowTable] = useState(false);
  const timerRef = useRef(null);
  const pendingRef = useRef(null); // { newRecords, isLast }

  const ready = !!session?.ready;
  const isRace = session?.mode === 'race';

  // 蒙版按空格 → 开始（设 startedAt + 起 BGM）
  const handleReady = () => {
    if (!session || session.ready) return;
    const now = Date.now();
    setSession((s) => (s ? { ...s, ready: true, startedAt: now, questionStartedAt: now } : s));
    playBgm(isRace ? 'ranked' : 'training');
  };

  // session 结束 / 退出 → 停 BGM
  const handleExit = () => {
    stopBgm();
    onExit();
  };

  // 驱动"已用时"显示的定时刷新
  useEffect(() => {
    if (!ready) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 100);
    return () => clearInterval(id);
  }, [ready]);

  // 组件卸载时清理计时器 + 停 BGM
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      stopBgm();
    };
  }, []);

  // 键盘事件监听
  useEffect(() => {
    const onKey = (e) => {
      if (!session) return;
      // 对照表打开时，让弹层独占键盘（ESC 由弹层处理）
      if (showTable) return;

      // 入场蒙版状态：只响应 Space（开始）和 Esc（退出）
      if (!session.ready) {
        if (e.key === ' ') {
          e.preventDefault();
          handleReady();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          handleExit();
        }
        return;
      }

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
  }, [session, feedback, showTable]);

  if (!session) return null;
  const { current, input, index, total, mode, records } = session;
  const now = Date.now();
  const elapsed = ready ? now - session.questionStartedAt : 0;
  const totalElapsed = ready ? now - session.startedAt : 0;

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
    <div className="max-w-2xl mx-auto relative">
      <BgmControls position="top-right" />
      {/* 顶部导航 */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={handleExit}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">退出</span>
        </button>
        <div className="text-xs font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
          {isRace && (
            <span className="px-2 py-0.5 rounded-full bg-[#ff6b6b]/10 text-[#ff6b6b] text-[10px] tracking-widest">
              排位 · BOSS
            </span>
          )}
          <span>
            {session.subName} · {mode === 'race' ? '晋升模式' : '训练模式'}
          </span>
        </div>
        {session.subId === 'pctToFrac' || session.subId === 'square' ? (
          <button
            onClick={() => setShowTable(true)}
            title={session.subId === 'square' ? '查看常见平方数对照表（背诵用）' : '查看百化分对照表（背诵用）'}
            className="flex items-center space-x-1.5 text-slate-400 hover:text-[#fbc02d] transition-colors"
          >
            <BookOpen size={14} />
            <span className="text-xs font-black uppercase tracking-widest hidden sm:inline">对照表</span>
          </button>
        ) : (
          <span className="w-16" />
        )}
      </div>

      {/* 排位模式 BOSS HP 条（纯装饰，不影响判分） */}
      {isRace && ready && total !== Infinity && (
        <BossHpBar correctCount={correctCount} total={total} />
      )}

      {/* 题目卡片（外层套一个 relative 容器以承载入场蒙版） */}
      <div className="relative">
        <div className={`bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 shadow-xl shadow-black/10 relative overflow-hidden ${
          isRace && ready ? 'race-bg' : ''
        }`}>
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
            <span className="flex items-center space-x-3 tabular-nums">
              <span>本题 {fmtMs(elapsed)}</span>
              <span className="opacity-40">·</span>
              <span>总计 {fmtDuration(totalElapsed)}</span>
            </span>
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

      {/* 入场蒙版：未 ready 时盖在题目卡上 */}
      {!ready && (
        <div
          className="absolute inset-0 z-30 rounded-[2.5rem] overflow-hidden flex items-center justify-center cursor-pointer"
          onClick={handleReady}
          role="button"
          tabIndex={0}
          aria-label="按空格开始"
        >
          <div className="absolute inset-0 bg-[#1a1a1a]/95 backdrop-blur-md" />
          <div className="absolute inset-0 opacity-50" style={{
            background: isRace
              ? 'radial-gradient(circle at 30% 50%, rgba(255,107,107,0.30), transparent 60%)'
              : 'radial-gradient(circle at 70% 40%, rgba(251,192,45,0.25), transparent 60%)',
          }} />
          <div className="relative text-center px-6">
            <div className="text-[10px] font-black uppercase tracking-[0.4em] text-white/50 mb-3">
              {isRace ? 'RANKED · BOSS BATTLE' : 'TRAINING · FOCUS'}
            </div>
            <div
              className="inline-block text-5xl md:text-6xl font-black italic mb-4"
              style={{
                color: isRace ? '#ff6b6b' : '#fbc02d',
                animation: 'maskBreath 2.4s ease-in-out infinite',
                textShadow: isRace ? '0 0 32px rgba(255,107,107,0.5)' : '0 0 32px rgba(251,192,45,0.4)',
              }}
            >
              按 SPACE 开始
            </div>
            <div className="text-sm font-medium text-white/60 tracking-wide">
              {isRace
                ? 'BGM 即将响起 · 调整呼吸 · 进入战斗'
                : '调整状态 · 进入心流 · 计时与 BGM 同步开启'}
            </div>
            <div className="mt-8 inline-flex items-center justify-center gap-2 px-5 py-2 rounded-full bg-white/10 border border-white/15 text-xs font-black tracking-widest text-white/80"
              style={{ animation: 'maskBounce 1.6s ease-in-out infinite' }}
            >
              <span>⌨</span>
              <span>SPACE</span>
            </div>
          </div>
        </div>
      )}
      </div>

      <style>{`
        @keyframes fb-pop {
          0%   { transform: scale(0.3); opacity: 0; }
          60%  { transform: scale(1.15); opacity: 1; }
          100% { transform: scale(1); opacity: 1; }
        }
        @keyframes maskBreath {
          0%, 100% { transform: scale(1);    filter: brightness(1); }
          50%      { transform: scale(1.04); filter: brightness(1.2); }
        }
        @keyframes maskBounce {
          0%, 100% { transform: translateY(0); }
          50%      { transform: translateY(-6px); }
        }
        @keyframes scanLine {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        .race-bg::before {
          content: '';
          position: absolute;
          inset: 0;
          background: radial-gradient(ellipse at top, rgba(255,107,107,0.08), transparent 60%);
          pointer-events: none;
        }
        .race-bg::after {
          content: '';
          position: absolute;
          top: 0; left: 0;
          width: 30%; height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255,107,107,0.06), transparent);
          animation: scanLine 4s linear infinite;
          pointer-events: none;
        }
      `}</style>

      {showTable && session.subId === 'square' && (
        <SquareTableModal onClose={() => setShowTable(false)} />
      )}
      {showTable && session.subId === 'pctToFrac' && (
        <BaiHuaFenTableModal onClose={() => setShowTable(false)} />
      )}
    </div>
  );
};

// ---------------- BOSS HP 条（排位模式装饰） ----------------
const BossHpBar = ({ correctCount, total }) => {
  const hpPct = Math.max(0, 100 - (correctCount / total) * 100);
  const dead = hpPct <= 0;
  return (
    <div className="mb-3 px-1">
      <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest mb-1.5">
        <span className="flex items-center gap-1.5 text-[#ff6b6b]">
          <span className="text-base leading-none" style={{ animation: dead ? 'none' : 'maskBreath 1.6s ease-in-out infinite' }}>
            {dead ? '💀' : '👹'}
          </span>
          <span>BOSS HP</span>
        </span>
        <span className="tabular-nums text-slate-400">
          {Math.round(hpPct)} / 100
        </span>
      </div>
      <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
        <div
          className="h-full transition-all duration-500"
          style={{
            width: `${hpPct}%`,
            background: dead
              ? '#94a3b8'
              : 'linear-gradient(90deg,#ff6b6b 0%,#fbc02d 80%,#facc15 100%)',
            boxShadow: dead ? 'none' : '0 0 8px rgba(255,107,107,0.5)',
          }}
        />
      </div>
    </div>
  );
};

// ---------------- 百化分对照表弹层 ----------------
const BaiHuaFenTableModal = ({ onClose }) => {
  // ESC 关闭
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

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
          <div>
            <h3 className="text-2xl font-black italic">百化分对照表</h3>
            <p className="text-xs font-medium text-slate-400 mt-1">
              1/3 ~ 1/19，小数与百分比均保留 2 位
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-xl bg-[#f2f0e9] hover:bg-[#1a1a1a] hover:text-white transition-colors flex items-center justify-center"
          >
            <X size={16} />
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {BAI_HUA_FEN_TABLE.map((f) => (
            <div
              key={f.den}
              className="flex items-center justify-between px-4 py-3 rounded-xl bg-[#f2f0e9]/60 border border-[#f2f0e9] hover:border-[#1a1a1a] hover:bg-white transition-all"
            >
              <span className="font-black text-xl italic text-[#1a1a1a]">
                1/{f.den}
              </span>
              <div className="text-right leading-tight">
                <div className="text-lg font-black tabular-nums text-[#1a1a1a]">
                  {f.dec.toFixed(2)}
                </div>
                <div className="text-sm font-bold tabular-nums text-[#fbc02d] mt-0.5">
                  {f.pct.toFixed(2)}%
                </div>
              </div>
            </div>
          ))}
        </div>

        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-6 text-center">
          按 ESC 或点击空白处关闭
        </p>
      </div>
    </div>
  );
};

// ---------------- 常见平方数对照表弹层 ----------------
const SquareTableModal = ({ onClose }) => {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

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
          <div>
            <h3 className="text-2xl font-black italic">常见平方数对照表</h3>
            <p className="text-xs font-medium text-slate-400 mt-1">
              11² ~ 29²，考场必背
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-xl bg-[#f2f0e9] hover:bg-[#1a1a1a] hover:text-white transition-colors flex items-center justify-center"
          >
            <X size={16} />
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {SQUARE_TABLE.map((s) => (
            <div
              key={s.n}
              className="flex items-center justify-between px-4 py-3 rounded-xl bg-[#f2f0e9]/60 border border-[#f2f0e9] hover:border-[#1a1a1a] hover:bg-white transition-all"
            >
              <span className="font-black text-xl italic text-[#1a1a1a]">
                {s.n}²
              </span>
              <div className="text-lg font-black tabular-nums text-[#1a1a1a]">
                {s.sq}
              </div>
            </div>
          ))}
        </div>

        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-6 text-center">
          按 ESC 或点击空白处关闭
        </p>
      </div>
    </div>
  );
};

// ---------------- Result ----------------
const ResultView = ({ result, onRetry, onHome, onSubs }) => {
  if (!result) return null;
  const accuracy = Math.round((result.correct / result.total) * 100);
  const change = result.rankChange;
  const lpRes = change?.lp;
  const beforeRank = lpRes ? getRank(lpRes.rankBefore) : null;
  const afterRank = lpRes ? getRank(lpRes.rankAfter) : null;
  const promoted = lpRes?.promoted;
  const demoted = lpRes?.demoted;
  const isProtected = lpRes?.protected;
  const cumulRank = change ? getRank(change.after.rankId) : null;

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 text-center relative overflow-hidden">
        <div className="absolute top-8 right-8 w-40 h-40 bg-[#fbc02d] rounded-full blur-[50px] opacity-40" />
        <div className="relative">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-[#fbc02d] text-black flex items-center justify-center mb-4">
            <Trophy size={28} />
          </div>
          <p className="text-xs font-black uppercase tracking-widest opacity-60 mb-1">
            {result.subName} · 晋升结果
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

      {/* 段位评定卡片（基于 ladderRank + LP） */}
      {lpRes && (
        <div className={`bg-white rounded-[2rem] p-6 border border-[#f2f0e9] relative overflow-hidden ${
          promoted ? 'ring-2 ring-[#fbc02d]/40' : demoted ? 'ring-2 ring-rose-300' : ''
        }`}>
          {/* 升段时的金光背景 */}
          {promoted && (
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background: `radial-gradient(circle at 50% 50%, ${afterRank.color}15, transparent 70%)`,
                animation: 'glowPulse 1.6s ease-out',
              }}
            />
          )}
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4 relative">
            段位评定
            {promoted && <span className="ml-2 text-[#fbc02d]">· 晋升！</span>}
            {demoted && <span className="ml-2 text-rose-500">· 段位下滑</span>}
            {isProtected && <span className="ml-2 text-emerald-500">· 累计实力保护</span>}
          </p>

          {promoted ? (
            <div className="flex items-center justify-center space-x-5 py-4 relative">
              <div className="text-center opacity-50" style={{ animation: 'rankFadeOut 0.6s ease-out' }}>
                <RankBadge rankId={beforeRank.id} size={52} />
                <p className="text-[10px] font-black uppercase tracking-widest mt-2 text-slate-400">
                  {beforeRank.label}
                </p>
              </div>
              <div className="text-3xl font-black italic" style={{ color: afterRank.color, animation: 'rankUp 0.6s ease-out' }}>
                →
              </div>
              <div className="text-center" style={{ animation: 'rankUp 0.7s ease-out' }}>
                <RankBadge rankId={afterRank.id} size={68} />
                <p className="text-sm font-black italic mt-2 flex items-center justify-center gap-1" style={{ color: afterRank.color }}>
                  {afterRank.label}
                  <span style={{ animation: 'arrowFloat 1.6s ease-in-out infinite' }}>↑</span>
                </p>
              </div>
            </div>
          ) : demoted ? (
            <div className="flex items-center justify-center space-x-5 py-4">
              <div className="text-center opacity-60">
                <RankBadge rankId={beforeRank.id} size={52} />
                <p className="text-[10px] font-black uppercase tracking-widest mt-2 text-slate-400">
                  {beforeRank.label}
                </p>
              </div>
              <div className="text-3xl font-black italic text-slate-400">→</div>
              <div className="text-center" style={{ animation: 'rankDown 0.7s ease-out' }}>
                <RankBadge rankId={afterRank.id} size={64} />
                <p className="text-sm font-black italic mt-2 text-slate-500 flex items-center justify-center gap-1">
                  {afterRank.label}
                  <span>↓</span>
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center space-x-4 py-4">
              <RankBadge rankId={afterRank.id} size={56} />
              <div>
                <p className="text-lg font-black italic" style={{ color: afterRank.color }}>
                  {afterRank.label}
                </p>
                <p className="text-[11px] font-bold text-slate-400 mt-0.5">
                  {afterRank.id === 'king' ? '已达顶峰 · 保持！' : `${lpRes.lpAfter} / 100 LP`}
                </p>
              </div>
            </div>
          )}

          {/* LP 进度条 + delta 文案 */}
          {!promoted && !demoted && afterRank.id !== 'king' && (
            <LpBar lpBefore={lpRes.lpBefore} lpAfter={lpRes.lpAfter} delta={lpRes.lpDelta} color={afterRank.color} />
          )}
          {(promoted || demoted) && (
            <LpBar lpBefore={promoted ? 100 : 0} lpAfter={lpRes.lpAfter} delta={lpRes.lpDelta} color={afterRank.color} resetMode />
          )}

          {/* 累计段位 footer：让玩家知道"真实实力"在哪 */}
          {cumulRank && cumulRank.id !== 'unranked' && cumulRank.id !== afterRank.id && (
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-4 text-center">
              累计实力 · <span style={{ color: cumulRank.color }}>{cumulRank.label}</span>
            </p>
          )}
        </div>
      )}

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

      <style>{`
        @keyframes rankUp {
          0%   { transform: scale(0.5) rotate(-15deg); opacity: 0; }
          60%  { transform: scale(1.2) rotate(5deg); opacity: 1; }
          100% { transform: scale(1) rotate(0); opacity: 1; }
        }
        @keyframes rankDown {
          0%   { transform: translateY(-12px) scale(1.05); opacity: 1; filter: grayscale(0); }
          60%  { transform: translateY(8px)   scale(0.92); opacity: 0.7; filter: grayscale(0.6); }
          100% { transform: translateY(0)     scale(1);   opacity: 1; filter: grayscale(0.3); }
        }
        @keyframes rankFadeOut {
          0%   { opacity: 1; transform: scale(1); }
          100% { opacity: 0.5; transform: scale(0.9); }
        }
        @keyframes glowPulse {
          0%   { opacity: 0; }
          40%  { opacity: 1; }
          100% { opacity: 0; }
        }
        @keyframes arrowFloat {
          0%, 100% { transform: translateY(0); }
          50%      { transform: translateY(-3px); }
        }
        @keyframes lpDeltaPop {
          0%   { transform: translateY(8px) scale(0.6); opacity: 0; }
          50%  { transform: translateY(-4px) scale(1.2); opacity: 1; }
          100% { transform: translateY(0)   scale(1);   opacity: 1; }
        }
        @keyframes lpBarShake {
          0%, 100% { transform: translateX(0); }
          20%, 60% { transform: translateX(-3px); }
          40%, 80% { transform: translateX(3px); }
        }
      `}</style>
    </div>
  );
};

// ---------------- LP 进度条（带从 lpBefore 动画到 lpAfter） ----------------
const LpBar = ({ lpBefore, lpAfter, delta, color, resetMode }) => {
  // 初始状态是 lpBefore；mount 后 350ms 切到 lpAfter，触发 CSS transition
  const [pct, setPct] = useState(lpBefore);
  useEffect(() => {
    // 用 setTimeout 而非同步 setState：避免 react-hooks/set-state-in-effect 警告
    const t1 = setTimeout(() => setPct(lpAfter), 350);
    return () => clearTimeout(t1);
  }, [lpAfter]);
  const positive = delta >= 0;
  const barColor = positive ? color : '#f87171';
  return (
    <div className="mt-3 relative">
      <div
        className="h-2 rounded-full bg-[#f2f0e9] overflow-hidden"
        style={{ animation: !positive ? 'lpBarShake 0.4s ease-out 0.4s' : undefined }}
      >
        <div
          className="h-full transition-all duration-1000 ease-out"
          style={{
            width: `${Math.max(0, Math.min(100, pct))}%`,
            backgroundColor: barColor,
            boxShadow: positive ? `0 0 8px ${barColor}80` : 'none',
          }}
        />
      </div>
      <div className="mt-2 flex items-center justify-between text-[10px] font-black uppercase tracking-widest">
        <span className="text-slate-400 tabular-nums">
          {resetMode ? `LP 重置 · ${Math.round(lpAfter)} / 100` : `${Math.round(lpAfter)} / 100`}
        </span>
        <span
          className={`tabular-nums ${positive ? 'text-emerald-500' : 'text-rose-500'}`}
          style={{ animation: 'lpDeltaPop 0.6s ease-out' }}
        >
          {positive ? `+${delta}` : `${delta}`} LP
        </span>
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
          <p className="text-xs text-slate-400 mt-1">完成一次「晋升模式」后会在此留下成绩</p>
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

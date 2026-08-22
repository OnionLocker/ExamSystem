import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Play, Pause, Square, Timer as TimerIcon, Volume2, VolumeX } from 'lucide-react';
import { usePomodoro } from './PomodoroContext.jsx';
import { fmtHMS, PHASE_LABELS } from './utils.js';

const WORK_MINS = [15, 25, 45, 50, 60];
const BREAK_MINS = [0, 5, 10, 15];
const BGM_MINI = [
  { id: 'rain', name: '雨声' },
  { id: 'ocean', name: '海浪' },
  { id: 'forest', name: '森林' },
  { id: 'cafe', name: '咖啡厅' },
  { id: 'keyboard', name: '键盘' },
];

const Chip = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`px-2.5 py-1.5 rounded-xl text-[11px] font-black tabular-nums transition-all ${
      active ? 'bg-[#1a1a1a] text-white' : 'bg-[#e8d5b0] text-slate-500 hover:bg-slate-200'
    }`}
  >
    {children}
  </button>
);

const TopBarTimer = ({ onOpen }) => {
  const {
    settings,
    updateSettings,
    state,
    remaining,
    isActive,
    isPaused,
    startWork,
    startBreak,
    pause,
    resume,
    stop,
    toggleBGM,
  } = usePomodoro();

  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);
  const panelRef = useRef(null);
  const [panelPos, setPanelPos] = useState(null);
  const phase = state.phase;
  const workMin = Math.round(settings.workMs / 60000);
  const breakMin = Math.round(settings.breakMs / 60000);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (boxRef.current?.contains(e.target)) return;
      if (panelRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !boxRef.current) {
      setPanelPos(null);
      return undefined;
    }
    const place = () => {
      const r = boxRef.current.getBoundingClientRect();
      setPanelPos({
        top: r.bottom + 8,
        right: Math.max(8, window.innerWidth - r.right),
      });
    };
    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, [open]);

  const pickWork = (min) => updateSettings({ workMs: min * 60000 });
  const pickBreak = (min) => updateSettings({ breakMs: min * 60000 });
  const pickBgm = (id) => {
    if (!id) {
      updateSettings({ bgmEnabled: false });
      toggleBGM(false);
      return;
    }
    updateSettings({ bgmEnabled: true, bgmType: id });
    toggleBGM(true, { type: id });
  };

  const begin = (kind) => {
    if (kind === 'break') startBreak(false);
    else startWork();
    setOpen(false);
  };

  const panel = open && panelPos && createPortal(
    <div
      ref={panelRef}
      className="fixed w-[min(20rem,calc(100vw-1rem))] max-h-[min(70vh,28rem)] overflow-y-auto rounded-2xl bg-white shadow-2xl shadow-black/10 border border-black/5 z-[9999] p-4"
      style={{ top: panelPos.top, right: panelPos.right }}
    >
      {phase === 'idle' ? (
        <div className="space-y-3.5">
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">
              专注时长
            </p>
            <div className="flex flex-wrap gap-1.5">
              {WORK_MINS.map((m) => (
                <Chip key={m} active={workMin === m} onClick={() => pickWork(m)}>
                  {m} 分
                </Chip>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">
              休息时长
            </p>
            <div className="flex flex-wrap gap-1.5">
              {BREAK_MINS.map((m) => (
                <Chip key={m} active={breakMin === m} onClick={() => pickBreak(m)}>
                  {m === 0 ? '不休息' : `${m} 分`}
                </Chip>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">
              白噪音
            </p>
            <div className="flex flex-wrap gap-1.5">
              <Chip active={!settings.bgmEnabled} onClick={() => pickBgm(null)}>
                关
              </Chip>
              {BGM_MINI.map((t) => (
                <Chip
                  key={t.id}
                  active={settings.bgmEnabled && settings.bgmType === t.id}
                  onClick={() => pickBgm(t.id)}
                >
                  {t.name}
                </Chip>
              ))}
            </div>
            <div className="flex items-center space-x-2 mt-2">
              <VolumeX size={12} className="text-slate-400 flex-shrink-0" />
              <input
                type="range"
                min={0}
                max={100}
                value={Math.round(settings.bgmVolume * 100)}
                onChange={(e) => updateSettings({ bgmVolume: Number(e.target.value) / 100 })}
                className="flex-1 accent-[#1a1a1a]"
              />
              <Volume2 size={12} className="text-slate-400 flex-shrink-0" />
              <span className="text-[10px] font-black tabular-nums w-8 text-right text-slate-500">
                {Math.round(settings.bgmVolume * 100)}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() =>
              updateSettings({ soundEnabled: !settings.soundEnabled })
            }
            className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-[11px] font-black ${
              settings.soundEnabled
                ? 'bg-[#1a1a1a] text-white'
                : 'bg-[#e8d5b0] text-slate-500'
            }`}
          >
            <span className="flex items-center space-x-1.5">
              {settings.soundEnabled ? <Volume2 size={12} /> : <VolumeX size={12} />}
              <span>结束提醒音</span>
            </span>
            <span>{settings.soundEnabled ? '开' : '关'}</span>
          </button>
          <div className={`grid gap-2 pt-1 ${settings.breakMs ? 'grid-cols-2' : 'grid-cols-1'}`}>
            <button
              type="button"
              onClick={() => begin('work')}
              className="flex items-center justify-center space-x-1.5 py-3 rounded-2xl bg-[#2c261c] text-white text-xs font-black"
            >
              <Play size={14} />
              <span>开始专注</span>
            </button>
            {settings.breakMs > 0 && (
              <button
                type="button"
                onClick={() => begin('break')}
                className="flex items-center justify-center py-3 rounded-2xl bg-[#e8d5b0] text-slate-600 text-xs font-black"
              >
                直接休息
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-center py-2">
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">
              {PHASE_LABELS[phase] || PHASE_LABELS.idle}
            </p>
            <p className="text-4xl font-black tabular-nums tracking-tight">{fmtHMS(remaining)}</p>
          </div>
          {settings.bgmEnabled && (
            <div className="flex items-center space-x-2">
              <VolumeX size={12} className="text-slate-400 flex-shrink-0" />
              <input
                type="range"
                min={0}
                max={100}
                value={Math.round(settings.bgmVolume * 100)}
                onChange={(e) => updateSettings({ bgmVolume: Number(e.target.value) / 100 })}
                className="flex-1 accent-[#1a1a1a]"
              />
              <Volume2 size={12} className="text-slate-400 flex-shrink-0" />
              <span className="text-[10px] font-black tabular-nums w-8 text-right text-slate-500">
                {Math.round(settings.bgmVolume * 100)}
              </span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            {isActive && (
              <button
                type="button"
                onClick={pause}
                className="flex items-center justify-center space-x-1.5 py-3 rounded-2xl bg-[#1a1a1a] text-white text-xs font-black"
              >
                <Pause size={14} />
                <span>暂停</span>
              </button>
            )}
            {isPaused && (
              <button
                type="button"
                onClick={resume}
                className="flex items-center justify-center space-x-1.5 py-3 rounded-2xl bg-[#2c261c] text-white text-xs font-black"
              >
                <Play size={14} />
                <span>继续</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                stop();
                setOpen(false);
              }}
              className="flex items-center justify-center space-x-1.5 py-3 rounded-2xl bg-[#e8d5b0] text-slate-600 text-xs font-black"
            >
              <Square size={14} />
              <span>停止</span>
            </button>
          </div>
        </div>
      )}
      {onOpen && (
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            onOpen();
          }}
          className="w-full mt-3 pt-2 text-[10px] font-bold text-slate-300 hover:text-slate-500"
        >
          打开完整页面
        </button>
      )}
    </div>,
    document.body,
  );

  if (phase === 'idle') {
    return (
      <div className="relative" ref={boxRef}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={`flex items-center space-x-2 px-4 py-2 rounded-full bg-white border transition-all ${
            open ? 'border-[#1a1a1a]' : 'border-[#e8d5b0] hover:border-[#1a1a1a]'
          }`}
        >
          <TimerIcon size={14} className="text-slate-400" />
          <span className="text-xs font-black uppercase tracking-widest text-slate-500">
            番茄钟
          </span>
          <span className="text-[10px] font-bold text-slate-400 tabular-nums">{workMin}分</span>
        </button>
        {panel}
      </div>
    );
  }

  const phaseIsBreak = phase === 'break' || phase === 'longBreak';
  const bg = phaseIsBreak
    ? 'bg-emerald-700 text-white'
    : 'bg-[#1a1a1a] text-white';
  const accent = 'text-white';

  return (
    <div className={`relative flex items-center space-x-1 pl-4 pr-1 py-1 rounded-full ${bg}`} ref={boxRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="番茄钟"
        className="flex items-center space-x-2"
      >
        <span className="text-[10px] font-black uppercase tracking-widest opacity-70">
          {PHASE_LABELS[phase]}
        </span>
        <span className={`text-sm font-black tabular-nums ${accent}`}>{fmtHMS(remaining)}</span>
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          if (isActive) pause();
          else if (isPaused) resume();
        }}
        className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-white/20 transition-colors"
      >
        {isActive ? <Pause size={12} /> : <Play size={12} />}
      </button>
      {panel}
    </div>
  );
};

export default TopBarTimer;

import { Play, Pause, Timer as TimerIcon } from 'lucide-react';
import { usePomodoro } from './PomodoroContext.jsx';
import { fmtHMS, PHASE_LABELS } from './utils.js';

// 顶部工具条计时器：所有页面可见
// 点击整个胶囊跳转到番茄钟页
const TopBarTimer = ({ onOpen }) => {
  const { state, remaining, isActive, isPaused, pause, resume, startWork, settings } =
    usePomodoro();
  const phase = state.phase;

  // 未启动时显示紧凑的"开始"按钮
  if (phase === 'idle') {
    return (
      <button
        onClick={onOpen}
        className="flex items-center space-x-2 px-4 py-2 rounded-full bg-white border border-[#f2f0e9] hover:border-[#1a1a1a] transition-all"
      >
        <TimerIcon size={14} className="text-slate-400" />
        <span className="text-xs font-black uppercase tracking-widest text-slate-500">
          番茄钟
        </span>
        <span className="text-[10px] font-bold text-slate-400 tabular-nums">
          {Math.round(settings.workMs / 60000)}分
        </span>
      </button>
    );
  }

  const phaseIsWork = phase === 'work';
  const phaseIsBreak = phase === 'break' || phase === 'longBreak';
  const bg = phaseIsWork
    ? 'bg-[#1a1a1a] text-white'
    : phaseIsBreak
      ? 'bg-emerald-500 text-white'
      : 'bg-[#fbc02d] text-black'; // paused
  const accent = phaseIsWork ? 'text-[#fbc02d]' : 'text-white';

  return (
    <div className={`flex items-center space-x-1 pl-4 pr-1 py-1 rounded-full ${bg}`}>
      <button
        onClick={onOpen}
        title="打开番茄钟"
        className="flex items-center space-x-2"
      >
        <span className="text-[10px] font-black uppercase tracking-widest opacity-70">
          {PHASE_LABELS[phase]}
        </span>
        <span className={`text-sm font-black tabular-nums ${accent}`}>
          {fmtHMS(remaining)}
        </span>
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          if (isActive) pause();
          else if (isPaused) resume();
          else startWork();
        }}
        className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-white/20 transition-colors"
      >
        {isActive ? <Pause size={12} /> : <Play size={12} />}
      </button>
    </div>
  );
};

export default TopBarTimer;

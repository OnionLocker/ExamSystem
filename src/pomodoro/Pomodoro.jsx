import { useMemo, useState } from 'react';
import {
  Play,
  Pause,
  Square,
  RotateCcw,
  Coffee,
  Target,
  Bell,
  BellOff,
  Volume2,
  VolumeX,
  Trash2,
  CheckCircle2,
  Timer as TimerIcon,
  CloudRain,
  Music,
  Music2,
  Waves,
  Flame,
  Trees,
  Wind,
  Keyboard,
  Moon,
  Droplet,
  Zap,
} from 'lucide-react';
import { usePomodoro } from './PomodoroContext.jsx';
import { fmtHMS, PHASE_LABELS, isToday, isThisWeek } from './utils.js';

// 尝试读取数资练习历史（用来关联到番茄钟完成段）
const loadPracticeHistory = () => {
  try {
    return JSON.parse(localStorage.getItem('numeric_practice_history_v1') || '[]');
  } catch {
    return [];
  }
};

const Pomodoro = () => {
  const {
    settings,
    updateSettings,
    state,
    history,
    remaining,
    isActive,
    isPaused,
    startWork,
    startBreak,
    pause,
    resume,
    stop,
    resetRounds,
    clearHistory,
    toggleBGM,
  } = usePomodoro();

  const phase = state.phase;
  const total = state.durationMs || settings.workMs;
  const progress = total > 0 ? ((total - remaining) / total) * 100 : 0;
  const phaseColor =
    phase === 'break' || phase === 'longBreak'
      ? '#22c55e'
      : phase === 'paused'
        ? '#fbc02d'
        : '#1a1a1a';

  // 今日/本周统计
  const stats = useMemo(() => {
    const today = history.filter((r) => isToday(r.endedAt));
    const week = history.filter((r) => isThisWeek(r.endedAt));
    const todayMin = Math.round(today.reduce((s, r) => s + r.durationMs, 0) / 60000);
    const weekMin = Math.round(week.reduce((s, r) => s + r.durationMs, 0) / 60000);
    return {
      todayCount: today.length,
      weekCount: week.length,
      todayMin,
      weekMin,
    };
  }, [history]);

  // 关联最近一次完成的番茄钟与同期做题
  const lastSession = history[0];
  const lastPracticeStats = useMemo(() => {
    if (!lastSession) return null;
    const pr = loadPracticeHistory();
    const hit = pr.filter(
      (r) =>
        r.completedAt &&
        new Date(r.completedAt).getTime() >= lastSession.startedAt &&
        new Date(r.completedAt).getTime() <= lastSession.endedAt + 60000,
    );
    if (hit.length === 0) return null;
    const totalQ = hit.reduce((s, r) => s + (r.total || 0), 0);
    const correctQ = hit.reduce((s, r) => s + (r.correct || 0), 0);
    return {
      sessions: hit.length,
      total: totalQ,
      correct: correctQ,
      acc: totalQ > 0 ? Math.round((correctQ / totalQ) * 100) : 0,
    };
  }, [lastSession]);

  const onStart = () => {
    if (phase === 'idle') startWork();
    else if (phase === 'paused') resume();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h2 className="text-4xl font-black tracking-tighter italic uppercase">番茄钟</h2>
        <p className="text-sm font-medium text-slate-400 mt-2">
          专注 {Math.round(settings.workMs / 60000)} 分钟 · 休息 {Math.round(settings.breakMs / 60000)} 分钟，张弛有度。
        </p>
      </div>

      {/* 主计时盘 */}
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 md:p-14 text-center relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-20 transition-all"
          style={{
            background: `radial-gradient(circle at center, ${phaseColor}, transparent 70%)`,
          }}
        />
        <div className="relative z-10">
          <p className="text-xs font-black uppercase tracking-widest opacity-60 mb-4">
            {PHASE_LABELS[phase] || PHASE_LABELS.idle}
          </p>
          <div className="text-7xl md:text-8xl font-black tabular-nums tracking-tight">
            {fmtHMS(phase === 'idle' ? settings.workMs : remaining)}
          </div>

          {/* 进度条 */}
          <div className="max-w-md mx-auto mt-8 h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full transition-all duration-300"
              style={{ width: `${Math.min(100, progress)}%`, backgroundColor: phaseColor }}
            />
          </div>

          {/* 控制按钮 */}
          <div className="mt-10 flex items-center justify-center space-x-3">
            {!isActive && !isPaused && (
              <CtrlBtn primary onClick={() => startWork()} icon={Play} label="开始专注" />
            )}
            {isActive && (
              <>
                <CtrlBtn onClick={pause} icon={Pause} label="暂停" />
                <CtrlBtn onClick={stop} icon={Square} label="停止" />
              </>
            )}
            {isPaused && (
              <>
                <CtrlBtn primary onClick={resume} icon={Play} label="继续" />
                <CtrlBtn onClick={stop} icon={Square} label="停止" />
              </>
            )}
            {!isActive && !isPaused && (
              <CtrlBtn onClick={() => startBreak(false)} icon={Coffee} label="直接休息" subtle />
            )}
          </div>

          {/* 今日完成的小番茄 */}
          <div className="mt-10 flex items-center justify-center space-x-1.5 text-xs opacity-80">
            <span className="font-bold mr-2">本轮已完成</span>
            {Array.from({ length: settings.roundsBeforeLongBreak }).map((_, i) => (
              <span
                key={i}
                className={`w-2.5 h-2.5 rounded-full ${
                  i < state.roundsCompleted % settings.roundsBeforeLongBreak
                    ? 'bg-[#fbc02d]'
                    : 'bg-white/15'
                }`}
              />
            ))}
            <button
              onClick={resetRounds}
              title="重置轮次"
              className="ml-3 opacity-60 hover:opacity-100"
            >
              <RotateCcw size={12} />
            </button>
          </div>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={Target} label="今日" value={stats.todayCount} unit="个番茄" />
        <StatCard icon={TimerIcon} label="今日专注" value={stats.todayMin} unit="分钟" />
        <StatCard icon={CheckCircle2} label="本周" value={stats.weekCount} unit="个番茄" />
        <StatCard icon={TimerIcon} label="本周专注" value={stats.weekMin} unit="分钟" />
      </div>

      {/* 上次专注 × 做题 */}
      {lastPracticeStats && (
        <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-6">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
            最近一次专注期间的练习
          </p>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <span className="text-sm font-bold text-slate-500">
              {lastPracticeStats.sessions} 次冲刺 · 共 {lastPracticeStats.total} 题
            </span>
            <div className="flex items-center space-x-6">
              <div className="text-right">
                <div className="text-3xl font-black italic text-[#1a1a1a]">
                  {lastPracticeStats.acc}%
                </div>
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                  正确率
                </div>
              </div>
              <div className="text-right">
                <div className="text-lg font-black italic text-emerald-500">
                  ✓ {lastPracticeStats.correct}
                </div>
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                  正确
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 背景白噪音 */}
      <BGMBlock settings={settings} updateSettings={updateSettings} toggleBGM={toggleBGM} />

      {/* 设置 */}
      <SettingsBlock settings={settings} updateSettings={updateSettings} />

      {/* 历史 */}
      <HistoryBlock history={history} onClear={clearHistory} />
    </div>
  );
};

const CtrlBtn = ({ icon: Icon, label, onClick, primary, subtle }) => (
  <button
    onClick={onClick}
    className={`px-6 py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all flex items-center space-x-2 ${
      primary
        ? 'bg-[#fbc02d] text-black hover:scale-105'
        : subtle
          ? 'bg-white/5 text-white/70 hover:bg-white/10'
          : 'bg-white/10 text-white hover:bg-white/20'
    }`}
  >
    <Icon size={16} />
    <span>{label}</span>
  </button>
);

const StatCard = ({ icon: Icon, label, value, unit }) => (
  <div className="bg-white rounded-2xl border border-[#f2f0e9] p-5">
    <div className="flex items-center justify-between mb-2">
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
        {label}
      </span>
      <Icon size={14} className="text-slate-400" />
    </div>
    <div className="flex items-baseline space-x-1">
      <span className="text-3xl font-black italic text-[#1a1a1a] tabular-nums">{value}</span>
      <span className="text-xs font-bold text-slate-400">{unit}</span>
    </div>
  </div>
);

const SettingsBlock = ({ settings, updateSettings }) => {
  const [open, setOpen] = useState(false);
  const minInput = (v) => Math.max(1, Math.min(180, Number(v) || 1));
  return (
    <div className="bg-white rounded-[2rem] border border-[#f2f0e9]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-5 text-left"
      >
        <span className="text-xs font-black uppercase tracking-widest text-slate-500">
          设置（时长 · 提醒）
        </span>
        <span
          className={`text-[10px] font-black uppercase tracking-widest text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`}
        >
          ▾
        </span>
      </button>
      {open && (
        <div className="px-5 pb-6 space-y-5 border-t border-[#f2f0e9] pt-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <DurationInput
              label="工作时长（分钟）"
              value={Math.round(settings.workMs / 60000)}
              onChange={(v) => updateSettings({ workMs: minInput(v) * 60000 })}
            />
            <DurationInput
              label="休息时长（分钟）"
              value={Math.round(settings.breakMs / 60000)}
              onChange={(v) => updateSettings({ breakMs: minInput(v) * 60000 })}
            />
            <DurationInput
              label="长休时长（分钟）"
              value={Math.round(settings.longBreakMs / 60000)}
              onChange={(v) => updateSettings({ longBreakMs: minInput(v) * 60000 })}
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <ToggleRow
              icon={settings.soundEnabled ? Volume2 : VolumeX}
              label="声音提醒"
              checked={settings.soundEnabled}
              onChange={(v) => updateSettings({ soundEnabled: v })}
            />
            <ToggleRow
              icon={settings.notificationEnabled ? Bell : BellOff}
              label="浏览器通知"
              checked={settings.notificationEnabled}
              onChange={(v) => {
                updateSettings({ notificationEnabled: v });
                if (v && 'Notification' in window && Notification.permission === 'default') {
                  Notification.requestPermission().catch(() => {});
                }
              }}
            />
            <ToggleRow
              label="工作结束自动休息"
              checked={settings.autoStartBreak}
              onChange={(v) => updateSettings({ autoStartBreak: v })}
            />
            <ToggleRow
              label="休息结束自动工作"
              checked={settings.autoStartWork}
              onChange={(v) => updateSettings({ autoStartWork: v })}
            />
          </div>
        </div>
      )}
    </div>
  );
};

const DurationInput = ({ label, value, onChange }) => (
  <label className="block">
    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
      {label}
    </span>
    <input
      type="number"
      min={1}
      max={180}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="mt-1 w-full bg-[#f2f0e9]/60 border border-transparent rounded-xl py-3 px-4 text-sm font-black tabular-nums focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
    />
  </label>
);

const ToggleRow = ({ icon: Icon, label, checked, onChange }) => (
  <button
    onClick={() => onChange(!checked)}
    className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${
      checked
        ? 'bg-[#1a1a1a] text-white border-[#1a1a1a]'
        : 'bg-white text-slate-500 border-[#f2f0e9] hover:border-slate-300'
    }`}
  >
    <span className="flex items-center space-x-2">
      {Icon && <Icon size={14} />}
      <span className="text-xs font-black uppercase tracking-widest">{label}</span>
    </span>
    <span
      className={`w-9 h-5 rounded-full p-0.5 transition-all ${checked ? 'bg-[#fbc02d]' : 'bg-slate-200'}`}
    >
      <span
        className={`block w-4 h-4 rounded-full bg-white transition-transform ${checked ? 'translate-x-4' : ''}`}
      />
    </span>
  </button>
);

const HistoryBlock = ({ history, onClear }) => {
  const [expanded, setExpanded] = useState(false);
  const show = expanded ? history : history.slice(0, 5);
  return (
    <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-6">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-black uppercase tracking-widest text-slate-500">
          最近记录
        </span>
        {history.length > 0 && (
          <button
            onClick={() => {
              if (confirm('清空所有番茄钟记录？该操作不可恢复。')) onClear();
            }}
            className="text-xs font-black uppercase tracking-widest text-slate-400 hover:text-[#ff6b6b] flex items-center space-x-1"
          >
            <Trash2 size={12} />
            <span>清空</span>
          </button>
        )}
      </div>
      {history.length === 0 ? (
        <div className="text-center py-10 text-xs font-bold text-slate-400">
          完成第一个番茄钟后，这里会展示你的专注轨迹。
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {show.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between py-2.5 px-4 rounded-xl bg-[#f2f0e9]/40"
              >
                <div className="flex items-center space-x-3">
                  <CheckCircle2 size={14} className="text-emerald-500" />
                  <span className="text-xs font-bold text-slate-600 tabular-nums">
                    {new Date(r.startedAt).toLocaleString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
                <span className="text-xs font-black tabular-nums text-[#1a1a1a]">
                  {Math.round(r.durationMs / 60000)} 分钟
                </span>
              </div>
            ))}
          </div>
          {history.length > 5 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="w-full mt-3 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-[#1a1a1a]"
            >
              {expanded ? '收起' : `展开全部（${history.length}）`}
            </button>
          )}
        </>
      )}
    </div>
  );
};


const BGM_TYPES = [
  { id: 'rain', name: '雨声', desc: '低语般的细雨，最易专注', icon: CloudRain },
  { id: 'thunderstorm', name: '雷雨', desc: '雨声 + 偶尔远雷轰鸣', icon: Zap },
  { id: 'ocean', name: '海浪', desc: '缓慢起伏的潮汐，深度放松', icon: Waves },
  { id: 'stream', name: '溪流', desc: '潺潺流水 + 水花', icon: Droplet },
  { id: 'forest', name: '森林', desc: '微风吹拂 + 鸟鸣啾啾', icon: Trees },
  { id: 'fire', name: '篝火', desc: '木柴燃烧的噼啪声', icon: Flame },
  { id: 'wind', name: '风声', desc: '旷野低呼，适合冥想', icon: Wind },
  { id: 'night', name: '夜晚', desc: '蟋蟀虫鸣，夏夜氛围', icon: Moon },
  { id: 'cafe', name: '咖啡厅', desc: '嘈杂人声 + 杯盘碰撞', icon: Coffee },
  { id: 'keyboard', name: '键盘声', desc: '机械键盘敲击，办公氛围', icon: Keyboard },
  { id: 'brown', name: '棕噪音', desc: '低沉如远雷，催眠级别', icon: Music },
  { id: 'pink', name: '粉噪音', desc: '柔和均衡，最通用', icon: Music2 },
  { id: 'white', name: '白噪音', desc: '纯净嘶嘶声，屏蔽干扰', icon: Volume2 },
];

const BGMBlock = ({ settings, updateSettings, toggleBGM }) => {
  const enabled = settings.bgmEnabled;

  const onPickType = (id) => {
    updateSettings({ bgmType: id });
    // 用户主动切换类型 → 立即试听（即使不在工作阶段也播）
    if (enabled) toggleBGM(true, { type: id });
  };

  const onToggleEnabled = () => {
    const next = !enabled;
    updateSettings({ bgmEnabled: next });
    // 未在工作/休息阶段也允许即时试听
    if (next) toggleBGM(true);
    else toggleBGM(false);
  };

  return (
    <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-black italic">背景白噪音</p>
          <p className="text-xs font-medium text-slate-400 mt-0.5">
            帮助进入专注心流；进入工作阶段时自动播放。
          </p>
        </div>
        <button
          onClick={onToggleEnabled}
          className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${
            enabled
              ? 'bg-[#1a1a1a] text-[#fbc02d]'
              : 'bg-[#f2f0e9] text-slate-500 hover:bg-slate-200'
          }`}
        >
          {enabled ? '已开启' : '未开启'}
        </button>
      </div>

      {/* 类型选择 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
        {BGM_TYPES.map((t) => {
          const active = settings.bgmType === t.id;
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => onPickType(t.id)}
              className={`p-3 rounded-xl text-left transition-all border ${
                active
                  ? 'bg-[#1a1a1a] text-white border-[#1a1a1a]'
                  : 'bg-white text-[#1a1a1a] border-[#f2f0e9] hover:border-slate-300'
              }`}
            >
              <div className="flex items-center space-x-2 mb-1">
                <Icon size={14} className={active ? 'text-[#fbc02d]' : 'text-slate-400'} />
                <span className="text-sm font-black">{t.name}</span>
              </div>
              <p
                className={`text-[10px] font-medium leading-snug ${active ? 'text-white/60' : 'text-slate-400'}`}
              >
                {t.desc}
              </p>
            </button>
          );
        })}
      </div>

      {/* 音量 + 额外开关 */}
      <div className="space-y-3">
        <div className="flex items-center space-x-3">
          <VolumeX size={14} className="text-slate-400 flex-shrink-0" />
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(settings.bgmVolume * 100)}
            onChange={(e) => updateSettings({ bgmVolume: Number(e.target.value) / 100 })}
            className="flex-1 accent-[#1a1a1a]"
          />
          <Volume2 size={14} className="text-slate-400 flex-shrink-0" />
          <span className="text-xs font-black tabular-nums w-10 text-right">
            {Math.round(settings.bgmVolume * 100)}%
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ToggleRow
            label="进入工作阶段自动播"
            checked={settings.bgmAutoStart}
            onChange={(v) => updateSettings({ bgmAutoStart: v })}
          />
          <ToggleRow
            label="休息阶段也播放"
            checked={settings.bgmPlayInBreak}
            onChange={(v) => updateSettings({ bgmPlayInBreak: v })}
          />
        </div>
      </div>
    </div>
  );
};

export default Pomodoro;

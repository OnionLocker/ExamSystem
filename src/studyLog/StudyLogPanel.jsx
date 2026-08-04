import { useMemo, useState } from 'react';
import {
  Flame,
  Trophy,
  Clock as ClockIcon,
  CalendarDays,
  Plus,
  Minus,
  ChevronDown,
  Trash2,
} from 'lucide-react';
import {
  MODULES,
  addEntry,
  removeEntry,
  scoreImport,
  scoreReview,
  loadLog,
  summarize,
  ENTRY_TYPES,
} from './studyLog.js';
import { useServerHeat } from './heatmap.js';

// ============================================================
// 学习打卡主面板：顶部汇总 + 快速录入（可折叠）+ 今日明细
// ============================================================
const StudyLogPanel = ({ version, onChange }) => {
  // version 是有意的缓存失效信号：loadLog 读 localStorage，eslint 看不到这层依赖
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const log = useMemo(() => loadLog(), [version]);
  const serverHeat = useServerHeat(version);
  const stats = useMemo(() => summarize(log, serverHeat), [log, serverHeat]);
  const bump = () => onChange?.();
  const [importOpen, setImportOpen] = useState(false);

  return (
    <div className="space-y-6">
      {/* 打卡统计 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          icon={Flame}
          accent="#ff6b6b"
          label="连续打卡"
          value={stats.streak}
          unit="天"
        />
        <SummaryCard
          icon={Trophy}
          accent="#fbc02d"
          label="今日得分"
          value={stats.today.score}
          unit="分"
        />
        <SummaryCard
          icon={ClockIcon}
          accent="#1a1a1a"
          label="今日专注"
          value={stats.today.minutes}
          unit="分钟"
        />
        <SummaryCard
          icon={CalendarDays}
          accent="#22c55e"
          label="本周学习"
          value={stats.weekDays}
          unit="天"
        />
      </div>

      {/* 快速录入：大按钮 + 可折叠面板 */}
      <div className="bg-white rounded-[2rem] border border-[#f2f0e9] overflow-hidden">
        <button
          onClick={() => setImportOpen((v) => !v)}
          className={`w-full flex items-center justify-between p-5 transition-colors ${
            importOpen ? 'bg-[#1a1a1a] text-white' : 'hover:bg-[#f2f0e9]/50'
          }`}
        >
          <div className="flex items-center space-x-3">
            <span
              className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                importOpen ? 'bg-[#fbc02d] text-black' : 'bg-[#1a1a1a] text-[#fbc02d]'
              }`}
            >
              <Plus size={20} />
            </span>
            <div className="text-left">
              <p className={`text-sm font-black italic ${importOpen ? 'text-white' : ''}`}>
                快速录入今日学习
              </p>
              <p
                className={`text-xs font-medium mt-0.5 ${importOpen ? 'text-white/60' : 'text-slate-400'}`}
              >
                记录在粉笔 / 纸上完成的练习，一键打卡
              </p>
            </div>
          </div>
          <ChevronDown
            size={18}
            className={`transition-transform ${importOpen ? 'rotate-180 text-[#fbc02d]' : 'text-slate-400'}`}
          />
        </button>
        {importOpen && (
          <div className="p-5 border-t border-[#f2f0e9] bg-[#f2f0e9]/20">
            <ImportGrid onAdded={bump} />
          </div>
        )}
      </div>

      {/* 今日明细 */}
      <TodayDetailBlock
        today={stats.today}
        onRemove={(id) => {
          removeEntry(id);
          bump();
        }}
      />
    </div>
  );
};

const SummaryCard = ({ icon: Icon, accent, label, value, unit }) => (
  <div className="bg-white rounded-2xl border border-[#f2f0e9] p-5">
    <div className="flex items-center justify-between mb-2">
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
        {label}
      </span>
      <Icon size={14} style={{ color: accent }} />
    </div>
    <div className="flex items-baseline space-x-1">
      <span className="text-3xl font-black italic tabular-nums text-[#1a1a1a]">{value}</span>
      <span className="text-xs font-bold text-slate-400">{unit}</span>
    </div>
  </div>
);

// ---------------- 录入网格 ----------------
const ImportGrid = ({ onAdded }) => (
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
    {MODULES.map((m) => (
      <ModuleRow
        key={m.id}
        module={m}
        onSubmit={(count, correct) => {
          addEntry({
            type: 'import',
            module: m.name,
            count,
            correct,
            score: scoreImport(m.id, count),
          });
          onAdded?.();
        }}
      />
    ))}
    <ReviewRow
      onSubmit={(count) => {
        addEntry({
          type: 'review',
          module: '错题复盘',
          count,
          score: scoreReview(count),
        });
        onAdded?.();
      }}
    />
  </div>
);

const ModuleRow = ({ module, onSubmit }) => {
  const [count, setCount] = useState(module.defaultSize);
  const [correct, setCorrect] = useState('');
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

  const add = () => {
    const n = Number(count);
    if (!Number.isFinite(n) || n <= 0) return;
    const c = correct === '' ? undefined : Number(correct);
    onSubmit(n, c);
    setCount(module.defaultSize);
    setCorrect('');
  };

  return (
    <div className="flex flex-col p-3 rounded-2xl border border-[#f2f0e9] bg-white hover:border-slate-300 transition-all">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: module.color }}
          />
          <span className="text-sm font-black">{module.name}</span>
        </div>
      </div>
      <div className="flex items-center space-x-2">
        <NumberStepper
          value={count}
          onChange={(v) => setCount(clamp(v, 1, 500))}
          suffix={module.id === 'shenlun' ? '篇' : '题'}
        />
        {module.id !== 'shenlun' && (
          <input
            type="number"
            value={correct}
            onChange={(e) => setCorrect(e.target.value)}
            placeholder="对"
            className="w-14 bg-white border border-[#f2f0e9] rounded-lg py-1.5 px-2 text-xs font-bold tabular-nums focus:outline-none focus:ring-1 focus:ring-[#fbc02d] text-center"
          />
        )}
        <button
          onClick={add}
          className="flex-shrink-0 w-8 h-8 rounded-lg bg-[#1a1a1a] text-[#fbc02d] hover:bg-[#fbc02d] hover:text-black flex items-center justify-center transition-colors"
          title="添加记录"
        >
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
};

const ReviewRow = ({ onSubmit }) => {
  const [count, setCount] = useState(10);
  return (
    <div className="flex flex-col p-3 rounded-2xl border border-[#f2f0e9] bg-white hover:border-slate-300 transition-all">
      <div className="flex items-center space-x-2 mb-2">
        <span className="w-2 h-2 rounded-full bg-slate-400" />
        <span className="text-sm font-black">错题复盘</span>
      </div>
      <div className="flex items-center space-x-2">
        <NumberStepper
          value={count}
          onChange={(v) => setCount(Math.max(1, Math.min(200, v)))}
          suffix="题"
        />
        <button
          onClick={() => {
            onSubmit(count);
            setCount(10);
          }}
          className="flex-shrink-0 w-8 h-8 rounded-lg bg-[#1a1a1a] text-[#fbc02d] hover:bg-[#fbc02d] hover:text-black flex items-center justify-center"
        >
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
};

const NumberStepper = ({ value, onChange, suffix }) => (
  <div className="flex items-center flex-1 min-w-0 bg-white border border-[#f2f0e9] rounded-lg overflow-hidden">
    <button
      onClick={() => onChange(Number(value) - 1)}
      className="w-7 h-8 flex items-center justify-center hover:bg-[#f2f0e9] text-slate-400"
    >
      <Minus size={12} />
    </button>
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="flex-1 min-w-0 py-1.5 text-xs font-black tabular-nums text-center focus:outline-none"
    />
    <span className="px-2 text-[10px] font-black text-slate-400 select-none">{suffix}</span>
    <button
      onClick={() => onChange(Number(value) + 1)}
      className="w-7 h-8 flex items-center justify-center hover:bg-[#f2f0e9] text-slate-400"
    >
      <Plus size={12} />
    </button>
  </div>
);

// ---------------- 今日明细 ----------------

const TodayDetailBlock = ({ today, onRemove }) => {
  if (!today.entries.length) {
    return (
      <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-8 text-center">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400">
          今日明细
        </p>
        <p className="text-sm font-bold text-slate-400 mt-3">
          还没有记录，完成一个番茄钟或点上方"快速录入"吧～
        </p>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-6">
      <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">
        今日明细（{today.entries.length}）
      </p>
      <div className="space-y-2">
        {today.entries.map((e) => {
          const meta = ENTRY_TYPES[e.type] || { label: e.type, color: '#999' };
          return (
            <div
              key={e.id}
              className="group flex items-center justify-between py-2.5 px-4 rounded-xl bg-[#f2f0e9]/40 hover:bg-[#f2f0e9]"
            >
              <div className="flex items-center space-x-3 min-w-0">
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: meta.color }}
                />
                <span className="text-xs font-black uppercase tracking-widest text-slate-500 w-20">
                  {meta.label}
                </span>
                <span className="text-sm font-bold text-[#1a1a1a] truncate">
                  {formatEntry(e)}
                </span>
              </div>
              <div className="flex items-center space-x-3 flex-shrink-0">
                <span className="text-sm font-black tabular-nums text-[#fbc02d]">
                  +{e.score}
                </span>
                <span className="text-[10px] font-black text-slate-400 tabular-nums">
                  {new Date(e.ts).toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
                {/* 服务端现算出来的条目删不掉，要去掉得删那场练习本身 */}
                {e.derived ? (
                  <span className="w-3" />
                ) : (
                  <button
                    onClick={() => onRemove(e.id)}
                    title="删除"
                    className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-300 hover:text-[#ff6b6b]"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const formatEntry = (e) => {
  if (e.type === 'pomodoro') return `专注 ${e.minutes} 分钟`;
  if (e.type === 'numeric') {
    if (e.correct != null && e.count)
      return `${e.module} · ${e.correct}/${e.count} (${Math.round((e.correct / e.count) * 100)}%)`;
    return `${e.module} · ${e.count} 题`;
  }
  if (e.type === 'import') {
    if (e.correct != null) return `${e.module} · ${e.correct}/${e.count} 题`;
    return `${e.module} · ${e.count} ${e.module === '申论' ? '篇' : '题'}`;
  }
  if (e.type === 'review') return `复盘 ${e.count} 题`;
  if (e.type === 'chat') return e.module || '导师辅导';
  if (e.type === 'aiquiz') {
    const acc = e.count ? Math.round((e.correct / e.count) * 100) : 0;
    return `${e.module} · ${e.correct}/${e.count} (${acc}%)`;
  }
  if (e.type === 'mock') return `模考 ${e.minutes} 分钟`;
  if (e.type === 'reviewBrowse') return `翻复习资料 ${e.minutes} 分钟`;
  if (e.type === 'vocab') return `词汇 ${e.count} 题`;
  if (e.type === 'copybook') return e.module || '字帖临摹';
  return '';
};

export default StudyLogPanel;

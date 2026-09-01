import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Circle, Flame, Loader2, Target } from 'lucide-react';
import { topPicks } from './weakSpots.js';
import { wrongCountsBySub, totalWrong } from './wrongPool.js';
import { loadStats } from './ranks.js';
import {
  getTodayTasks,
  normalizeTaskRoute,
  refreshPendingTodayTasks,
  TODAY_TASKS_REFRESH_EVENT,
} from './todayTasks.js';

const STATUS_STYLE = {
  pending: {
    label: '待开始',
    icon: Circle,
    card: 'bg-[#e8d5b0]/70 hover:bg-[#1a1a1a] hover:text-white',
    badge: 'text-slate-500 group-hover:text-white/70',
  },
  partial: {
    label: '未达标',
    icon: Flame,
    card: 'bg-amber-50 border border-amber-200 hover:border-amber-400',
    badge: 'text-amber-700',
  },
  done: {
    label: '已点亮',
    icon: Check,
    card: 'bg-[#1a1a1a] text-white shadow-lg shadow-emerald-900/20 ring-2 ring-emerald-400/80',
    badge: 'text-emerald-300',
  },
};

const fmtSec = (ms) => {
  if (!Number.isFinite(ms) || ms <= 0) return '—';
  return `${(ms / 1000).toFixed(1)}s`;
};

const TaskCell = ({ task, onPickTask }) => {
  const status = STATUS_STYLE[task.status] || STATUS_STYLE.pending;
  const StatusIcon = status.icon;
  const last = task.lastRace;

  return (
    <button
      type="button"
      onClick={() => onPickTask?.(task)}
      className={`aspect-square w-full text-left rounded-2xl p-3.5 transition-all group flex flex-col ${status.card}`}
    >
      <p className="text-[10px] font-black tracking-widest text-slate-400 group-hover:text-white/50 truncate">
        {task.catName}
      </p>
      <p className="text-sm font-black italic leading-tight mt-1 line-clamp-2">
        {task.module}
      </p>
      <div className={`mt-auto pt-2 text-[10px] font-black tabular-nums ${status.badge}`}>
        <span className="inline-flex items-center gap-1">
          <StatusIcon size={11} />
          {status.label}
        </span>
        <p className="mt-1 opacity-80 leading-snug">
          {task.count}题 · ≥{Math.round((task.minAccuracy || 0) * 100)}% · ≤{fmtSec(task.maxAvgMs)}
        </p>
        {last && (
          <p className="mt-0.5 opacity-70">
            {last.correct}/{last.total} · {Math.round(last.accuracy * 100)}% · {fmtSec(last.avgMs)}
          </p>
        )}
      </div>
    </button>
  );
};

const WeakSpots = ({ onPickSub, onPickTask }) => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const { picks, debt } = useMemo(() => {
    const stats = loadStats();
    const wrongCounts = wrongCountsBySub();
    return {
      picks: topPicks({ stats, wrongCounts }),
      debt: totalWrong(),
    };
  }, []);

  const refresh = useCallback(async () => {
    try {
      setTasks(await getTodayTasks());
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = setTimeout(refresh, 0);
    const onHydrate = () => {
      refreshPendingTodayTasks();
      refresh();
    };
    window.addEventListener(TODAY_TASKS_REFRESH_EVENT, refresh);
    window.addEventListener('cloud-hydrated', onHydrate);
    return () => {
      clearTimeout(initialLoad);
      window.removeEventListener(TODAY_TASKS_REFRESH_EVENT, refresh);
      window.removeEventListener('cloud-hydrated', onHydrate);
    };
  }, [refresh]);

  const litCount = tasks.filter((task) => task.status === 'done').length;

  if (!loading && tasks.length === 0 && picks.length === 0) return null;

  return (
    <div className="rounded-[2rem] bg-white border border-[#e8d5b0] p-8 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-[#2c261c] text-white flex items-center justify-center">
            <Target size={18} />
          </div>
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
              TODAY TASKS
            </p>
            <h3 className="text-lg font-black italic">今日任务</h3>
          </div>
        </div>
        {tasks.length > 0 ? (
          <span className="text-xs font-black tabular-nums text-slate-400">
            {litCount}/{tasks.length} 已点亮
          </span>
        ) : debt > 0 ? (
          <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-[#ff6b6b]/10 text-[#ff6b6b]">
            <Flame size={13} />
            <span className="text-xs font-black tabular-nums">
              {debt} 道错题待练
            </span>
          </div>
        ) : null}
      </div>

      {loading ? (
        <div className="py-8 flex items-center justify-center text-slate-400">
          <Loader2 size={20} className="animate-spin" />
          <span className="ml-2 text-xs font-bold">正在加载今日任务</span>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {tasks.length > 0
            ? tasks.map((task) => (
                <TaskCell
                  key={task.id}
                  task={task}
                  onPickTask={(picked) => onPickTask?.({
                    ...picked,
                    ...normalizeTaskRoute(picked),
                  })}
                />
              ))
            : picks.map((pick) => (
                <button
                  key={pick.id}
                  onClick={() => onPickSub?.(pick.catId, pick.id)}
                  className="aspect-square w-full text-left rounded-2xl p-3.5 bg-[#e8d5b0]/70 hover:bg-[#1a1a1a] hover:text-white transition-all group flex flex-col"
                >
                  <p className="text-[10px] font-black tracking-widest text-slate-400 group-hover:text-white/50 truncate">
                    {pick.catName}
                  </p>
                  <p className="text-sm font-black italic leading-tight mt-1 line-clamp-2">
                    {pick.name}
                  </p>
                  <p className="mt-auto text-[10px] font-bold text-slate-400 group-hover:text-white/50 line-clamp-2">
                    {pick.reason}
                  </p>
                </button>
              ))}
        </div>
      )}

      {!loading && tasks.length > 0 && (
        <p className="mt-5 pt-4 border-t border-[#e8d5b0] text-xs font-bold text-slate-400">
          每天九宫格。冲刺模式做完指定题量，正确率和均速都达标才点亮。未达标可重开一场。
        </p>
      )}
    </div>
  );
};

export default WeakSpots;

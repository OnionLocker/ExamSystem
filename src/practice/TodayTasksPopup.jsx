import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Circle, Flame, Loader2 } from 'lucide-react';
import { CATEGORIES } from './generators.js';
import PopupPractice from './PopupPractice.jsx';
import {
  getTodayTasks,
  normalizeTaskRoute,
  TODAY_TASKS_REFRESH_EVENT,
} from './todayTasks.js';

const STEALTH_KEY = 'numeric_today_pip_stealth';
const HINT_KEY = 'numeric_today_pip_hint_v1';

const readStealth = () => {
  try {
    if (localStorage.getItem(STEALTH_KEY) === '0') return false;
  } catch { /* ignore */ }
  return true;
};

const fmtSec = (ms) => {
  if (!Number.isFinite(ms) || ms <= 0) return '—';
  return `${(ms / 1000).toFixed(1)}s`;
};

const isSelfReport = (task) => {
  const cat = CATEGORIES.find((c) => c.id === task?.catId);
  return cat?.kind === 'selfReport';
};

const STATUS = {
  pending: { label: '待开始', Icon: Circle },
  partial: { label: '未达标', Icon: Flame },
  done: { label: '已点亮', Icon: Check },
};

const taskMeta = (task) =>
  `${task.count}题 · ≥${Math.round((task.minAccuracy || 0) * 100)}% · ≤${fmtSec(task.maxAvgMs)}`;

export default function TodayTasksPopup({ embedded = false }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null);
  const [stealth, setStealth] = useState(readStealth);
  const [notice, setNotice] = useState('');
  const [hint, setHint] = useState(() => {
    try { return localStorage.getItem(HINT_KEY) !== '1'; }
    catch { return true; }
  });
  const rootRef = useRef(null);

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
    window.addEventListener(TODAY_TASKS_REFRESH_EVENT, refresh);
    window.addEventListener('cloud-hydrated', refresh);
    return () => {
      clearTimeout(initialLoad);
      window.removeEventListener(TODAY_TASKS_REFRESH_EVENT, refresh);
      window.removeEventListener('cloud-hydrated', refresh);
    };
  }, [refresh]);

  useEffect(() => {
    try { localStorage.setItem(STEALTH_KEY, stealth ? '1' : '0'); } catch { /* ignore */ }
  }, [stealth]);

  useEffect(() => {
    if (embedded) return;
    document.title = stealth ? '文档' : '今日任务';
  }, [stealth, embedded, active]);

  useEffect(() => {
    const win = rootRef.current?.ownerDocument?.defaultView;
    if (win && win !== window) {
      try { win.focus(); } catch { /* ignore */ }
      try { win.document.title = stealth ? '文档' : '今日任务'; } catch { /* ignore */ }
    }
  }, [stealth, active]);

  useEffect(() => {
    if (active) return undefined;
    const win = rootRef.current?.ownerDocument?.defaultView || window;
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'h' || e.key === 'H')) {
        e.preventDefault();
        setStealth((v) => !v);
      }
    };
    win.addEventListener('keydown', onKey);
    return () => win.removeEventListener('keydown', onKey);
  }, [active]);

  const pickTask = (task) => {
    if (isSelfReport(task)) {
      setNotice('识题反应要看材料，请在主界面完成');
      setTimeout(() => setNotice(''), 2200);
      return;
    }
    setNotice('');
    setActive(task);
  };

  const dismissHint = () => {
    setHint(false);
    try { localStorage.setItem(HINT_KEY, '1'); } catch { /* ignore */ }
  };

  if (active) {
    const route = normalizeTaskRoute(active);
    return (
      <PopupPractice
        key={active.id}
        catId={route.catId}
        subId={route.subId}
        mode="race"
        raceSize={active.plannedCount || active.count}
        embedded
        stealthDefault={stealth}
        todayTask={active}
        onStealthChange={setStealth}
        onExit={() => {
          setActive(null);
          refresh();
        }}
      />
    );
  }

  const litCount = tasks.filter((task) => task.status === 'done').length;
  const wrap = stealth
    ? 'bg-[#f2e4c4] text-[#2a2418]'
    : 'bg-[#f2e4c4] text-[#1a1a1a]';

  return (
    <div
      ref={rootRef}
      tabIndex={-1}
      className={`h-full min-h-full flex flex-col select-none overflow-hidden focus:outline-none ${wrap}`}
      onPointerDown={() => rootRef.current?.ownerDocument?.defaultView?.focus?.()}
    >
      <div className={`flex items-center justify-between px-2.5 pt-2 pb-1.5 ${
        stealth ? 'text-[#8d7348]' : 'text-[#8d7348]'
      }`}>
        <div className="min-w-0">
          <p className="text-[9px] font-black uppercase tracking-[0.18em] truncate">
            {stealth ? 'NOTES' : 'TODAY TASKS'}
          </p>
          <p className={`text-sm font-black italic leading-none mt-0.5 ${
            stealth ? 'text-[#1a1a1a]' : 'text-[#1a1a1a]'
          }`}>
            {stealth ? '文档' : '今日任务'}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-[11px] font-black tabular-nums">
            {litCount}/{tasks.length || 9}
          </span>
          <button
            type="button"
            onClick={() => setStealth((v) => !v)}
            title="Ctrl+H 伪装成文档"
            className={`px-1.5 py-0.5 rounded-md text-[9px] font-black tracking-widest ${
              stealth
                ? 'text-[#8d7348] hover:text-[#1a1a1a] hover:bg-[#e8d5b0]'
                : 'text-[#8d7348] hover:text-black hover:bg-[#e8d5b0]/60'
            }`}
          >
            {stealth ? 'NORMAL' : 'STEALTH'}
          </button>
        </div>
      </div>

      {notice && (
        <p className="px-2.5 pb-1 text-[10px] font-bold text-amber-700">{notice}</p>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-[#8d7348]">
          <Loader2 size={16} className="animate-spin" />
        </div>
      ) : stealth ? (
        <div className="flex-1 overflow-y-auto px-2 pb-1 space-y-1">
          {tasks.map((task, index) => {
            const status = STATUS[task.status] || STATUS.pending;
            const StatusIcon = status.Icon;
            return (
              <button
                key={task.id}
                type="button"
                onClick={() => pickTask(task)}
                className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-[#e8d5b0] flex items-start gap-2"
              >
                <span className="text-[10px] font-mono tabular-nums text-[#8d7348] w-4 shrink-0 pt-0.5">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] font-bold truncate text-[#1a1a1a]">
                    {task.module}
                  </span>
                </span>
                <span className={`flex items-center gap-0.5 text-[10px] font-bold shrink-0 ${
                  task.status === 'done' ? 'text-emerald-700' : 'text-[#8d7348]'
                }`}>
                  <StatusIcon size={11} />
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="flex-1 px-2 pb-1">
          <div className="grid grid-cols-3 gap-1.5 h-full">
            {tasks.map((task) => {
              const status = STATUS[task.status] || STATUS.pending;
              const StatusIcon = status.Icon;
              const done = task.status === 'done';
              return (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => pickTask(task)}
                  className={`min-h-0 rounded-xl p-2 text-left flex flex-col transition-colors ${
                    done
                      ? 'bg-[#1a1a1a] text-white'
                      : 'bg-[#e8d5b0]/80 hover:bg-[#1a1a1a] hover:text-white group'
                  }`}
                >
                  <p className={`text-[9px] font-black tracking-widest truncate ${
                    done ? 'text-white/50' : 'text-[#8d7348] group-hover:text-white/50'
                  }`}>
                    {task.catName}
                  </p>
                  <p className="text-[11px] font-black italic leading-tight mt-0.5 line-clamp-2">
                    {task.module}
                  </p>
                  <p className={`mt-auto pt-1 text-[9px] font-black tabular-nums ${
                    done ? 'text-emerald-300' : 'text-[#8d7348] group-hover:text-white/70'
                  }`}>
                    <span className="inline-flex items-center gap-0.5">
                      <StatusIcon size={10} />
                      {status.label}
                    </span>
                    <span className="block opacity-80 leading-snug">
                      {taskMeta(task)}
                    </span>
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className={`px-2.5 py-1.5 text-[9px] font-bold ${
        stealth ? 'text-[#8d7348]' : 'text-[#8d7348]'
      }`}>
        {hint && !stealth ? (
          <button type="button" onClick={dismissHint} className="text-left w-full">
            拖到屏幕左下角，下次会记住位置。Ctrl+H 伪装。点这里关掉提示。
          </button>
        ) : (
          <span>{stealth ? '回车确认' : '冲刺达标才点亮 · 未达标可重开'}</span>
        )}
      </div>
    </div>
  );
}

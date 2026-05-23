import { useEffect, useMemo, useState } from 'react';
import {
  LayoutDashboard,
  BookOpen,
  ChevronRight,
  ChevronLeft,
  LogOut,
  Calendar,
  Trash2,
  X,
  Timer as TimerIcon,
  Sliders,
  ClipboardList,
  Layers,
} from 'lucide-react';
import Login from './Login.jsx';
import NumericPractice from './practice/NumericPractice.jsx';
import Pomodoro from './pomodoro/Pomodoro.jsx';
import TopBarTimer from './pomodoro/TopBarTimer.jsx';
import { PomodoroProvider } from './pomodoro/PomodoroContext.jsx';
import StudyLogPanel from './studyLog/StudyLogPanel.jsx';
import { useStudyHeatmap, LEVEL_COLORS } from './studyLog/heatmap.js';
import { loadLog, summarize } from './studyLog/studyLog.js';
import Mixer from './mixer/Mixer.jsx';
import MockExam from './mockExam/MockExam.jsx';
import Cheatsheet from './cheatsheet/Cheatsheet.jsx';
import Flashcards from './flashcards/Flashcards.jsx';
import { checkAuth, clearToken, getToken, logout as apiLogout, setOnUnauthorized } from './api.js';
import { prewarmAllBgm } from './practice/bgm.js';
import { cloudGet, cloudSet, hydrateCloudStorage, flushCloudPending } from './cloudStorage.js';

// ---------------- date utils ----------------
const pad = (n) => String(n).padStart(2, '0');
const toKey = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;
const parseKey = (k) => {
  const [y, m, d] = k.split('-').map(Number);
  return new Date(y, m - 1, d);
};
const startOfDay = (date) => {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
};
const daysBetween = (from, to) => {
  const ms = startOfDay(to).getTime() - startOfDay(from).getTime();
  return Math.round(ms / 86400000);
};
const monthNames = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
];
const weekdayShort = ['一', '二', '三', '四', '五', '六', '日'];
const weekdayFull = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
const EVENTS_KEY = 'exam_calendar_events';

const AppInner = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [authed, setAuthed] = useState(!!getToken());
  const [bootChecked, setBootChecked] = useState(false);
  // 学习日志版本号：每次增删写入后 +1，驱动日历/面板重渲染
  const [studyVersion, setStudyVersion] = useState(0);
  const bumpStudy = () => setStudyVersion((v) => v + 1);
  const { getDay: getStudyDay } = useStudyHeatmap(studyVersion);

  // 监听学习日志变更事件（番茄钟完成、数资冲刺完成、导入、删除均会派发）
  useEffect(() => {
    const onChange = () => bumpStudy();
    window.addEventListener('study-log-change', onChange);
    return () => window.removeEventListener('study-log-change', onChange);
  }, []);

  const [viewMonth, setViewMonth] = useState(() => {
    const t = new Date();
    return { year: t.getFullYear(), month: t.getMonth() };
  });
  const [events, setEvents] = useState(() => cloudGet(EVENTS_KEY, {}));
  const [editingKey, setEditingKey] = useState(null);
  const [editingLabel, setEditingLabel] = useState('');

  useEffect(() => {
    setOnUnauthorized(() => setAuthed(false));
  }, []);

  // BGM 预热:首次任意手势触发(浏览器策略要求 user gesture 才允许 AudioContext)
  // 一次性,把 games / training / ranked 三条都 fetch + decode 好,
  // 后续 playBgm() 立刻有声,不需要等加载。
  useEffect(() => {
    let done = false;
    const trigger = () => {
      if (done) return;
      done = true;
      prewarmAllBgm();
      window.removeEventListener('pointerdown', trigger, true);
      window.removeEventListener('keydown', trigger, true);
    };
    window.addEventListener('pointerdown', trigger, true);
    window.addEventListener('keydown', trigger, true);
    return () => {
      window.removeEventListener('pointerdown', trigger, true);
      window.removeEventListener('keydown', trigger, true);
    };
  }, []);

  useEffect(() => {
    if (!getToken()) {
      setBootChecked(true);
      return;
    }
    checkAuth()
      .then(async (r) => {
        if (!r.authed) {
          clearToken();
          setAuthed(false);
          return;
        }
        // 已登录 → 拉服务器数据盖到本地,然后才让 UI 显示
        try {
          await hydrateCloudStorage();
        } catch {
          /* offline ok */
        }
        // hydrate 完之后,本地 EVENTS_KEY 可能被服务器覆盖了,重新读
        setEvents(cloudGet(EVENTS_KEY, {}));
        // 通知其他模块:云端数据已就绪,重新读取本地
        window.dispatchEvent(new Event('cloud-hydrated'));
      })
      .catch(() => {
        clearToken();
        setAuthed(false);
      })
      .finally(() => setBootChecked(true));
  }, []);

  // 退出前/标签关闭前把待推送的数据 flush 上去
  useEffect(() => {
    const onBeforeUnload = () => { flushCloudPending(); };
    window.addEventListener('beforeunload', onBeforeUnload);
    window.addEventListener('pagehide', onBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      window.removeEventListener('pagehide', onBeforeUnload);
    };
  }, []);

  useEffect(() => {
    cloudSet(EVENTS_KEY, events);
  }, [events]);

  const handleLogout = async () => {
    await apiLogout();
    clearToken();
    setAuthed(false);
  };

  const today = new Date();
  const todayKey = toKey(today.getFullYear(), today.getMonth(), today.getDate());

  const prevMonth = () =>
    setViewMonth((v) => (v.month === 0 ? { year: v.year - 1, month: 11 } : { year: v.year, month: v.month - 1 }));
  const nextMonth = () =>
    setViewMonth((v) => (v.month === 11 ? { year: v.year + 1, month: 0 } : { year: v.year, month: v.month + 1 }));
  const goToday = () => setViewMonth({ year: today.getFullYear(), month: today.getMonth() });

  const openEditor = (key) => {
    setEditingKey(key);
    setEditingLabel(events[key] || '');
  };
  const closeEditor = () => {
    setEditingKey(null);
    setEditingLabel('');
  };
  const saveEvent = () => {
    const label = editingLabel.trim();
    setEvents((prev) => {
      const next = { ...prev };
      if (label) next[editingKey] = label;
      else delete next[editingKey];
      return next;
    });
    closeEditor();
  };
  const deleteEvent = (key) => {
    setEvents((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };
  const clearAllEvents = () => {
    if (Object.keys(events).length === 0) return;
    if (confirm('确定要清空所有已设置的日子吗？该操作不可恢复。')) {
      setEvents({});
    }
  };

  const upcomingEvents = useMemo(() => {
    return Object.entries(events)
      .filter(([k]) => k >= todayKey)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([key, label]) => ({ key, label, days: daysBetween(today, parseKey(key)) }));
  }, [events, todayKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!bootChecked) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#f2f0e9] text-sm font-bold text-slate-400">
        正在加载...
      </div>
    );
  }

  if (!authed) {
    return (
      <Login
        onAuthed={async () => {
          // 登录成功后立刻拉服务器数据
          try {
            await hydrateCloudStorage();
          } catch {
            /* offline ok */
          }
          setEvents(cloudGet(EVENTS_KEY, {}));
          window.dispatchEvent(new Event('cloud-hydrated'));
          setAuthed(true);
        }}
      />
    );
  }


  const SidebarItem = ({ id, icon: Icon, label }) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`w-full flex items-center space-x-3 px-4 py-4 rounded-2xl transition-all duration-300 ${
        activeTab === id
          ? 'bg-[#1a1a1a] text-[#fbc02d] shadow-lg shadow-black/10'
          : 'text-[#666] hover:bg-black/5 hover:text-black'
      }`}
    >
      <Icon size={22} strokeWidth={activeTab === id ? 2.5 : 2} />
      <span className="font-bold tracking-tight">{label}</span>
    </button>
  );

  const renderCalendar = () => {
    const { year, month } = viewMonth;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstWeekday = new Date(year, month, 1).getDay();
    const offset = (firstWeekday + 6) % 7;
    const cells = [
      ...Array.from({ length: offset }, () => null),
      ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
    ];
    const hasEvents = Object.keys(events).length > 0;

    return (
      <div className="bg-[#1a1a1a] rounded-[2.5rem] p-8 text-white">
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-bold">打卡记录</h3>
          <div className="flex items-center space-x-1">
            <button
              onClick={prevMonth}
              className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors"
              title="上一月"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              onClick={goToday}
              className="px-3 py-1 rounded-full text-xs font-bold bg-[#fbc02d] text-black hover:brightness-110 transition-all"
              title="回到今天"
            >
              {year}年 {monthNames[month]}
            </button>
            <button
              onClick={nextMonth}
              className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors"
              title="下一月"
            >
              <ChevronRight size={16} />
            </button>
            {hasEvents && (
              <button
                onClick={clearAllEvents}
                className="ml-2 w-7 h-7 flex items-center justify-center rounded-full hover:bg-[#ff6b6b]/20 hover:text-[#ff6b6b] transition-colors"
                title="清空所有事件"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-7 gap-1.5 text-center text-[10px] font-bold text-white/30 mb-3">
          {weekdayShort.map((d, i) => (
            <div key={`wd-${i}`}>{d}</div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-1.5 text-center">
          {cells.map((day, i) => {
            if (day === null) return <div key={`cell-${i}`} className="aspect-square" />;
            const key = toKey(year, month, day);
            const isToday = key === todayKey;
            const hasEvent = !!events[key];
            const label = events[key];
            const study = getStudyDay(key); // { score, minutes, level, color } | null

            // GitHub 风：小圆角方块，数字做次要信息
            let cls =
              'relative aspect-square flex items-center justify-center rounded-md text-sm transition-all duration-200 cursor-pointer group ';
            let style = {};
            let numberCls = 'tabular-nums ';

            if (isToday) {
              // 今日：细琥珀描边 + 背景根据是否学习分两种
              cls += 'ring-1 ring-[#fbc02d] ';
              if (study) {
                style.backgroundColor = study.color;
                numberCls += study.level >= 6 ? 'text-[#1a1a1a] font-black' : 'text-white font-black';
              } else {
                cls += 'bg-white/[0.04] ';
                numberCls += 'text-[#fbc02d] font-black';
              }
            } else if (study) {
              style.backgroundColor = study.color;
              // 文字色：高档位用暗色保证可读，低档位用白色半透明当作点缀
              if (study.level >= 6) {
                numberCls += 'text-[#1a1a1a] font-black';
              } else if (study.level >= 3) {
                numberCls += 'text-white font-black';
              } else {
                numberCls += 'text-white/70 font-bold';
              }
            } else {
              cls += 'bg-white/[0.04] hover:bg-white/[0.08] ';
              numberCls += 'text-white/50 font-bold';
            }

            return (
              <div
                key={`cell-${i}`}
                className={cls + numberCls}
                style={style}
                onClick={() => openEditor(key)}
                title={
                  (hasEvent ? `${label}` : '') +
                  (study ? ` · 学习 ${study.score} 分 / ${study.minutes} 分钟` : '')
                }
              >
                <span className="relative z-10">{day}</span>
                {/* 事件标签：右上角小点 */}
                {hasEvent && (
                  <span className="absolute top-0.5 right-0.5 w-1 h-1 rounded-full bg-[#fbc02d]" />
                )}
              </div>
            );
          })}
        </div>

        {/* 图例 */}
        <div className="mt-6 pt-4 border-t border-white/[0.06] flex items-center justify-between">
          <span className="text-[10px] font-black uppercase tracking-widest text-white/30">
            学习强度
          </span>
          <div className="flex items-center space-x-1.5 text-[10px] font-bold text-white/30">
            <span>少</span>
            <div className="flex items-center space-x-[3px]">
              <span className="w-2.5 h-2.5 rounded-[3px] bg-white/[0.04]" />
              {LEVEL_COLORS.slice(1).map((c, i) => (
                <span
                  key={i}
                  className="w-2.5 h-2.5 rounded-[3px]"
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
            <span>多</span>
          </div>
        </div>
      </div>
    );
  };

  const renderCountdowns = () => {
    if (upcomingEvents.length === 0) return null;
    return (
      <div className="bg-white rounded-[2.5rem] p-8 shadow-sm border border-[#f2f0e9]">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-[#1a1a1a] text-[#fbc02d] flex items-center justify-center">
              <Calendar size={18} />
            </div>
            <h3 className="text-lg font-bold">重要日子倒计时</h3>
          </div>
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
            {upcomingEvents.length} 个
          </span>
        </div>

        <div className="flex space-x-4 overflow-x-auto overflow-y-visible py-2 -mx-1 px-1">
          {upcomingEvents.map(({ key, label, days }) => {
            const urgent = days <= 7;
            const soon = days <= 30;
            const ringColor = urgent
              ? 'ring-[#ff6b6b]'
              : soon
                ? 'ring-[#fbc02d]'
                : 'ring-[#1a1a1a]/20';
            const badgeColor = urgent ? 'text-[#ff6b6b]' : soon ? 'text-[#fbc02d]' : 'text-[#1a1a1a]';
            return (
              <div
                key={key}
                className={`flex-shrink-0 w-56 bg-white rounded-[1.75rem] p-5 ring-1 ${ringColor} shadow-sm shadow-black/[0.04] relative group transition-shadow hover:shadow-md`}
              >
                <button
                  onClick={() => deleteEvent(key)}
                  className="absolute top-3 right-3 w-6 h-6 rounded-full bg-white text-slate-400 hover:text-[#ff6b6b] opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                  title="删除"
                >
                  <X size={14} />
                </button>
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">{key}</p>
                <p className="text-base font-black italic truncate">{label}</p>
                <div className="mt-4 flex items-baseline space-x-1">
                  <span className={`text-4xl font-black tracking-tight ${badgeColor}`}>
                    {days === 0 ? '今天' : days}
                  </span>
                  {days > 0 && <span className="text-xs font-bold text-slate-400">天后</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderEditor = () => {
    if (!editingKey) return null;
    const current = events[editingKey];
    const d = parseKey(editingKey);
    const weekdayCN = weekdayFull[d.getDay()];
    return (
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        onClick={closeEditor}
      >
        <div
          className="bg-white rounded-[2rem] p-8 w-full max-w-sm shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-6">
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">设置事件</p>
              <p className="text-xl font-black italic">
                {editingKey} · {weekdayCN}
              </p>
            </div>
            <button
              onClick={closeEditor}
              className="w-8 h-8 rounded-full bg-[#f2f0e9] hover:bg-[#e8e6dd] flex items-center justify-center"
            >
              <X size={16} />
            </button>
          </div>

          <label className="text-xs font-bold text-slate-400 block mb-2">事件名称</label>
          <input
            type="text"
            autoFocus
            value={editingLabel}
            onChange={(e) => setEditingLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveEvent();
              if (e.key === 'Escape') closeEditor();
            }}
            placeholder="例如：广东省考"
            maxLength={30}
            className="w-full bg-[#f2f0e9]/60 border border-transparent rounded-2xl py-4 px-4 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-[#fbc02d] mb-6"
          />

          <div className="flex space-x-3">
            <button
              onClick={saveEvent}
              className="flex-1 bg-[#1a1a1a] text-white font-black py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs"
            >
              保存
            </button>
            {current && (
              <button
                onClick={() => {
                  deleteEvent(editingKey);
                  closeEditor();
                }}
                className="px-5 py-3 rounded-2xl text-[#ff6b6b] hover:bg-[#ff6b6b]/10 font-black text-xs uppercase tracking-widest"
              >
                删除
              </button>
            )}
            <button
              onClick={closeEditor}
              className="px-5 py-3 rounded-2xl text-slate-400 hover:bg-[#f2f0e9] font-black text-xs uppercase tracking-widest"
            >
              取消
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-[#f2f0e9] text-[#1a1a1a] font-sans overflow-hidden p-4">
      <aside className="w-24 lg:w-64 flex flex-col p-4 space-y-10">
        <div className="flex items-center space-x-3 px-4 py-2">
          <div className="w-10 h-10 bg-[#1a1a1a] rounded-xl flex items-center justify-center text-[#fbc02d] font-black">
            学
          </div>
          <h1 className="text-xl font-black tracking-tighter hidden lg:block uppercase">STUDY!</h1>
        </div>

        <nav className="flex-1 space-y-3">
          <SidebarItem id="dashboard" icon={LayoutDashboard} label="仪表盘" />
          <SidebarItem id="practice" icon={BookOpen} label="数资练习" />
          <SidebarItem id="flashcards" icon={Layers} label="抽认卡" />
          <SidebarItem id="pomodoro" icon={TimerIcon} label="番茄钟" />
          <SidebarItem id="mockexam" icon={ClipboardList} label="全卷模考" />
          <SidebarItem id="mixer" icon={Sliders} label="声音混音器" />
        </nav>

        <div className="pt-6 border-t border-black/5 space-y-2">
          <div className="flex items-center space-x-3 px-2 py-4">
            <div className="w-10 h-10 rounded-full bg-slate-300 overflow-hidden border-2 border-white shadow-sm">
              <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=Felix" alt="avatar" />
            </div>
            <div className="hidden lg:block overflow-hidden">
              <p className="text-sm font-bold truncate italic">Russell</p>
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">私人练习空间</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="退出登录"
            className="w-full flex items-center space-x-3 px-4 py-3 rounded-2xl text-[#666] hover:bg-black/5 hover:text-[#ff6b6b] transition-all"
          >
            <LogOut size={18} />
            <span className="hidden lg:block text-xs font-black uppercase tracking-widest">退出登录</span>
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden bg-white/60 backdrop-blur-xl rounded-[3rem] shadow-2xl shadow-black/[0.03] border border-white/50">
        <header className="h-24 flex items-center justify-between px-10">
          <div>
            <h2 className="text-2xl font-black tracking-tight">
              {activeTab === 'dashboard' && '欢迎回来，Russell！'}
              {activeTab === 'practice' && '数资练习'}
              {activeTab === 'flashcards' && '抽认卡'}
              {activeTab === 'pomodoro' && '番茄钟'}
              {activeTab === 'mockexam' && '全卷模考'}
              {activeTab === 'mixer' && '声音混音器'}
            </h2>
            <p className="text-sm font-medium text-slate-400">保持节奏，稳步提升。</p>
          </div>
          <TopBarTimer onOpen={() => setActiveTab('pomodoro')} />
        </header>

        <div className="flex-1 overflow-y-auto p-10 pt-4 space-y-10">
          {activeTab === 'dashboard' && (
            <div className="space-y-10">
              <StudyLogPanel version={studyVersion} onChange={bumpStudy} />

              {/* 今日概览 + 日历热力图 */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                <DashboardTodayCard studyVersion={studyVersion} />
                {renderCalendar()}
              </div>

              {renderCountdowns()}
            </div>
          )}

          {activeTab === 'practice' && <NumericPractice />}

          {activeTab === 'flashcards' && <Flashcards />}

          {activeTab === 'pomodoro' && <Pomodoro />}

          {activeTab === 'mockexam' && <MockExam />}

          {activeTab === 'mixer' && <Mixer />}
        </div>
      </main>

      {renderEditor()}
      <Cheatsheet />
    </div>
  );
};

const App = () => (
  <PomodoroProvider>
    <AppInner />
  </PomodoroProvider>
);

// ============ 今日概览卡片（接真实数据）============
const DashboardTodayCard = ({ studyVersion }) => {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const log = useMemo(() => loadLog(), [studyVersion]);
  const stats = useMemo(() => summarize(log), [log]);
  const today = stats.today;

  // 按 type 聚合今日明细（时长/次数）
  const byType = useMemo(() => {
    const acc = {
      pomodoro: { minutes: 0, count: 0, color: '#ff6b6b', label: '番茄专注' },
      numeric: { minutes: 0, count: 0, color: '#fbc02d', label: '数资练习' },
      import: { minutes: 0, count: 0, color: '#3b82f6', label: '导入套题' },
    };
    for (const e of today.entries) {
      if (!acc[e.type]) continue;
      acc[e.type].count += 1;
      acc[e.type].minutes += e.minutes || 0;
    }
    return acc;
  }, [today]);

  const totalScore = today.score;
  const totalMin = today.minutes;
  // 百分比条：按 type 得分占比（本日得分聚合）
  const scoreByType = useMemo(() => {
    const m = { pomodoro: 0, numeric: 0, import: 0 };
    for (const e of today.entries) {
      if (m[e.type] != null) m[e.type] += e.score || 0;
    }
    return m;
  }, [today]);

  return (
    <div className="lg:col-span-2 bg-[#dfdbcc] rounded-[2.5rem] p-10 relative overflow-hidden flex flex-col justify-between">
      <div className="relative z-10">
        <h3 className="text-xl font-bold mb-1">今日概览</h3>
        <p className="text-sm font-bold opacity-60">
          已连续打卡 {stats.streak} 天 · 本周学习 {stats.weekDays} 天
        </p>
      </div>

      <div className="absolute top-10 right-10 w-48 h-48 bg-[#fbc02d] rounded-full blur-[40px] opacity-60 animate-pulse" />
      <div className="absolute bottom-10 right-40 w-32 h-32 bg-[#ff6b6b] rounded-full blur-[35px] opacity-40" />

      <div className="relative z-10 mt-10 flex items-center space-x-12">
        <div className="text-center">
          <p className="text-5xl font-black italic tabular-nums">{totalScore}</p>
          <p className="text-xs font-bold uppercase tracking-widest opacity-50 mt-1">今日得分</p>
          <p className="text-xs font-bold opacity-60 mt-3 tabular-nums">
            {totalMin > 0 ? `${totalMin} 分钟` : '暂无专注'}
          </p>
        </div>
        <div className="flex-1 space-y-3">
          {Object.entries(byType).map(([k, v]) => {
            const score = scoreByType[k] || 0;
            const active = v.count > 0;
            return (
              <div key={k} className="flex items-center space-x-3">
                <div
                  className="w-8 h-2 rounded-full flex-shrink-0"
                  style={{
                    backgroundColor: active ? v.color : 'rgba(0,0,0,0.1)',
                  }}
                />
                <span
                  className={`text-xs font-bold italic ${active ? 'opacity-80' : 'opacity-30'}`}
                >
                  {v.label}
                </span>
                {active && (
                  <span className="text-[10px] font-black tabular-nums ml-auto opacity-60">
                    {v.count} 次 · +{score}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default App;

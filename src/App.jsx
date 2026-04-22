import { useEffect, useMemo, useState } from 'react';
import {
  LayoutDashboard,
  BookOpen,
  RefreshCcw,
  FileText,
  BarChart3,
  Plus,
  Upload,
  Clock,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  LogOut,
  Calendar,
  Trash2,
  X,
} from 'lucide-react';
import Login from './Login.jsx';
import NumericPractice from './practice/NumericPractice.jsx';
import { checkAuth, clearToken, getToken, logout as apiLogout, setOnUnauthorized } from './api.js';

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

const App = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isUploading, setIsUploading] = useState(false);
  const [authed, setAuthed] = useState(!!getToken());
  const [bootChecked, setBootChecked] = useState(false);

  const [viewMonth, setViewMonth] = useState(() => {
    const t = new Date();
    return { year: t.getFullYear(), month: t.getMonth() };
  });
  const [events, setEvents] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(EVENTS_KEY) || '{}');
    } catch {
      return {};
    }
  });
  const [editingKey, setEditingKey] = useState(null);
  const [editingLabel, setEditingLabel] = useState('');

  useEffect(() => {
    setOnUnauthorized(() => setAuthed(false));
  }, []);

  useEffect(() => {
    if (!getToken()) {
      setBootChecked(true);
      return;
    }
    checkAuth()
      .then((r) => {
        if (!r.authed) {
          clearToken();
          setAuthed(false);
        }
      })
      .catch(() => {
        clearToken();
        setAuthed(false);
      })
      .finally(() => setBootChecked(true));
  }, []);

  useEffect(() => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify(events));
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
    return <Login onAuthed={() => setAuthed(true)} />;
  }

  const stats = [
    { label: '本周学习', value: '45', unit: '题', trend: '+12%', icon: BookOpen },
    { label: '正确率', value: '72', unit: '%', trend: '+5%', icon: CheckCircle2 },
    { label: '连续打卡', value: '12', unit: '天', trend: '+2', icon: RefreshCcw },
    { label: '平均用时', value: '1.5', unit: 'h', trend: '-10%', icon: Clock },
  ];

  const recentExams = [
    { id: 1, title: '2024 广东省考行测真题', date: '2024-03-20', score: '78/100', status: '已完成' },
    { id: 2, title: '2023 广东省考行测真题', date: '2023-11-15', score: '65/100', status: '已复盘' },
  ];

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

        <div className="grid grid-cols-7 gap-3 text-center text-[10px] font-bold opacity-40 mb-4">
          {weekdayShort.map((d, i) => (
            <div key={`wd-${i}`}>{d}</div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-3 text-center">
          {cells.map((day, i) => {
            if (day === null) return <div key={`cell-${i}`} className="h-8" />;
            const key = toKey(year, month, day);
            const isToday = key === todayKey;
            const hasEvent = !!events[key];
            const label = events[key];

            let cls =
              'relative text-xs h-8 flex items-center justify-center rounded-full transition-colors cursor-pointer group ';
            if (isToday) cls += 'bg-[#fbc02d] text-black font-black ';
            else if (hasEvent) cls += 'bg-white/10 text-[#fbc02d] font-black ring-1 ring-[#fbc02d] ';
            else cls += 'hover:bg-white/10 ';

            return (
              <div
                key={`cell-${i}`}
                className={cls}
                onClick={() => openEditor(key)}
                title={hasEvent ? label : '点击设置事件'}
              >
                {day}
                {hasEvent && !isToday && (
                  <span className="absolute -bottom-1 w-1 h-1 rounded-full bg-[#fbc02d]" />
                )}
              </div>
            );
          })}
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
          <div className="w-10 h-10 bg-[#1a1a1a] rounded-xl flex items-center justify-center text-[#fbc02d] font-black italic">
            B.
          </div>
          <h1 className="text-xl font-black tracking-tighter hidden lg:block uppercase">BE.SMART</h1>
        </div>

        <nav className="flex-1 space-y-3">
          <SidebarItem id="dashboard" icon={LayoutDashboard} label="仪表盘" />
          <SidebarItem id="practice" icon={BookOpen} label="数资练习" />
          <SidebarItem id="review" icon={RefreshCcw} label="真题复盘" />
          <SidebarItem id="mistakes" icon={FileText} label="错题本" />
          <SidebarItem id="analysis" icon={BarChart3} label="学情分析" />
        </nav>

        <div className="pt-6 border-t border-black/5 space-y-2">
          <div className="flex items-center space-x-3 px-2 py-4">
            <div className="w-10 h-10 rounded-full bg-slate-300 overflow-hidden border-2 border-white shadow-sm">
              <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=Felix" alt="avatar" />
            </div>
            <div className="hidden lg:block overflow-hidden">
              <p className="text-sm font-bold truncate italic">Amanda</p>
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
              {activeTab === 'dashboard' && '欢迎回来，Amanda！'}
              {activeTab === 'practice' && '数资练习'}
              {activeTab === 'review' && '真题复盘'}
              {activeTab === 'mistakes' && '错题本'}
              {activeTab === 'analysis' && '学情分析'}
            </h2>
            <p className="text-sm font-medium text-slate-400">保持节奏，稳步提升。</p>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-10 pt-4 space-y-10">
          {activeTab === 'dashboard' && (
            <div className="space-y-10">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                <div className="lg:col-span-2 bg-[#dfdbcc] rounded-[2.5rem] p-10 relative overflow-hidden flex flex-col justify-between">
                  <div className="relative z-10">
                    <h3 className="text-xl font-bold mb-1">今日概览</h3>
                    <p className="text-sm font-bold opacity-60">本周学习进度</p>
                  </div>

                  <div className="absolute top-10 right-10 w-48 h-48 bg-[#fbc02d] rounded-full blur-[40px] opacity-60 animate-pulse" />
                  <div className="absolute bottom-10 right-40 w-32 h-32 bg-[#ff6b6b] rounded-full blur-[35px] opacity-40" />

                  <div className="relative z-10 flex items-center space-x-12 mt-10">
                    <div className="text-center">
                      <p className="text-5xl font-black italic">2.30</p>
                      <p className="text-xs font-bold uppercase tracking-widest opacity-50">累计小时</p>
                    </div>
                    <div className="flex-1 space-y-4">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-2 bg-[#fbc02d] rounded-full" />
                        <span className="text-xs font-bold opacity-60 italic">行测刷题</span>
                      </div>
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-2 bg-[#ff6b6b] rounded-full" />
                        <span className="text-xs font-bold opacity-60 italic">申论精讲</span>
                      </div>
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-2 bg-[#1a1a1a] rounded-full" />
                        <span className="text-xs font-bold opacity-60 italic">错题复盘</span>
                      </div>
                    </div>
                  </div>
                </div>

                {renderCalendar()}
              </div>

              {renderCountdowns()}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <div className="bg-white rounded-[2.5rem] p-8 shadow-sm border border-[#f2f0e9] flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold mb-1">本月学习</h3>
                    <p className="text-xs text-slate-400 font-medium">已完成目标的 72%</p>
                    <button
                      onClick={() => setActiveTab('practice')}
                      className="mt-6 flex items-center space-x-2 text-xs font-black uppercase italic bg-[#f2f0e9] px-4 py-2 rounded-full hover:bg-[#e8e6dd] transition-colors"
                    >
                      <span>开始练习</span>
                      <ChevronRight size={14} />
                    </button>
                  </div>
                  <div className="relative w-32 h-32 flex items-center justify-center">
                    <svg className="w-full h-full transform -rotate-90">
                      <circle
                        cx="64"
                        cy="64"
                        r="58"
                        stroke="currentColor"
                        strokeWidth="12"
                        fill="transparent"
                        className="text-[#f2f0e9]"
                      />
                      <circle
                        cx="64"
                        cy="64"
                        r="58"
                        stroke="currentColor"
                        strokeWidth="12"
                        fill="transparent"
                        strokeDasharray={364.4}
                        strokeDashoffset={100}
                        className="text-[#ff6b6b]"
                        strokeLinecap="round"
                      />
                    </svg>
                    <div className="absolute text-center">
                      <p className="text-sm text-slate-400 font-bold">总题量</p>
                      <p className="text-xl font-black">8,500</p>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-[2.5rem] p-8 shadow-sm border border-[#f2f0e9]">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="text-lg font-bold">最近真题</h3>
                    <button className="p-2 bg-[#1a1a1a] text-white rounded-full hover:scale-110 transition-transform">
                      <Plus size={16} />
                    </button>
                  </div>
                  <div className="space-y-5">
                    {recentExams.map((exam) => (
                      <div key={exam.id} className="flex items-center justify-between">
                        <div className="flex items-center space-x-4 overflow-hidden">
                          <div className="w-10 h-10 rounded-full bg-[#f2f0e9] flex items-center justify-center text-[#1a1a1a] flex-shrink-0">
                            <BookOpen size={18} />
                          </div>
                          <div className="truncate">
                            <p className="text-sm font-bold truncate italic">{exam.title}</p>
                            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">
                              {exam.status}
                            </p>
                          </div>
                        </div>
                        <div className="flex space-x-1 flex-shrink-0">
                          {Array.from({ length: 8 }).map((_, i) => (
                            <div
                              key={`bar-${exam.id}-${i}`}
                              className={`w-1.5 h-6 rounded-full ${i < 6 ? 'bg-[#ff6b6b]' : 'bg-[#f2f0e9]'}`}
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
                {stats.map((s) => (
                  <div key={s.label} className="bg-white rounded-[2rem] p-6 shadow-sm border border-[#f2f0e9]">
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-10 h-10 rounded-xl bg-[#f2f0e9] flex items-center justify-center text-[#1a1a1a]">
                        <s.icon size={18} />
                      </div>
                      <span
                        className={`text-[10px] font-black uppercase tracking-widest ${
                          s.trend.startsWith('-') ? 'text-[#ff6b6b]' : 'text-emerald-500'
                        }`}
                      >
                        {s.trend}
                      </span>
                    </div>
                    <p className="text-3xl font-black tracking-tight">
                      {s.value}
                      <span className="text-sm font-bold opacity-50 ml-1">{s.unit}</span>
                    </p>
                    <p className="text-xs font-bold text-slate-400 mt-1">{s.label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'practice' && <NumericPractice />}

          {activeTab === 'review' && (
            <div className="space-y-10">
              <div className="bg-[#f2f0e9] border-4 border-dashed border-[#dfdbcc] rounded-[3rem] p-16 text-center group cursor-pointer hover:border-[#fbc02d] transition-colors">
                <div className="w-24 h-24 bg-white rounded-[2rem] mx-auto flex items-center justify-center text-[#1a1a1a] shadow-xl shadow-black/5 mb-8 group-hover:scale-110 transition-transform">
                  <Upload size={40} />
                </div>
                <h3 className="text-2xl font-black italic mb-2 uppercase">上传真题卷</h3>
                <p className="text-slate-400 font-bold max-w-sm mx-auto mb-10 tracking-tight text-sm">
                  支持 PDF、图片，系统会自动 OCR 并生成结构化错题分析。
                </p>
                <button
                  onClick={() => {
                    setIsUploading(true);
                    setTimeout(() => setIsUploading(false), 2500);
                  }}
                  className="bg-[#1a1a1a] text-white font-black px-12 py-4 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs"
                >
                  {isUploading ? 'AI 正在解析...' : '上传试卷'}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'mistakes' && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="w-24 h-24 rounded-[2rem] bg-[#f2f0e9] flex items-center justify-center text-[#1a1a1a] mb-6">
                <FileText size={40} />
              </div>
              <h3 className="text-2xl font-black italic mb-2">错题本建设中</h3>
              <p className="text-sm text-slate-400 font-bold max-w-md">
                完成练习后，错题会自动归类到这里，支持按知识点筛选与重练。
              </p>
            </div>
          )}

          {activeTab === 'analysis' && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="w-24 h-24 rounded-[2rem] bg-[#f2f0e9] flex items-center justify-center text-[#1a1a1a] mb-6">
                <BarChart3 size={40} />
              </div>
              <h3 className="text-2xl font-black italic mb-2">学情分析建设中</h3>
              <p className="text-sm text-slate-400 font-bold max-w-md">
                即将上线：按模块、按时间的正确率趋势图，自动识别薄弱项。
              </p>
            </div>
          )}
        </div>
      </main>

      {renderEditor()}
    </div>
  );
};

export default App;

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
  BookMarked,
  PenTool,
  ClipboardList,
  Upload,
  Zap,
  MessageSquare,
  Target,
  Layers,
  ScanSearch,
  GraduationCap,
} from 'lucide-react';
import Login from './Login.jsx';
import NumericPractice from './practice/NumericPractice.jsx';
import Pomodoro from './pomodoro/Pomodoro.jsx';
import TopBarTimer from './pomodoro/TopBarTimer.jsx';
import { PomodoroProvider } from './pomodoro/PomodoroContext.jsx';
import StudyLogPanel from './studyLog/StudyLogPanel.jsx';
import { useStudyHeatmap, useServerHeat, LEVEL_COLORS } from './studyLog/heatmap.js';
import { loadLog, summarize, ENTRY_TYPES, digestDay, loadDigest } from './studyLog/studyLog.js';
import Mixer from './mixer/Mixer.jsx';
import MockExam from './mockExam/MockExam.jsx';
import Cheatsheet from './cheatsheet/Cheatsheet.jsx';
import Flashcards from './flashcards/Flashcards.jsx';
import Review from './review/Review.jsx';
import Copybook from './copybook/Copybook.jsx';
import StudyBoost from './studyBoost/StudyBoost.jsx';
import Uploads from './uploads/Uploads.jsx';
import HermesChat from './hermes/HermesChat.jsx';
import AIQuizHome from './aiPractice/AIQuizHome.jsx';
import ExamReview from './examReview/ExamReview.jsx';
import Knowledge from './knowledge/Knowledge.jsx';
import { KNOWLEDGE_OPEN_EVENT } from './knowledge/nav.js';
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
const HERMES_FS_KEY = 'hermes.fullscreen';
const readHermesFs = () => {
  try {
    const v = localStorage.getItem(HERMES_FS_KEY);
    if (v === '1') return true;
    if (v === '0') return false;
  } catch { /* 隐私模式 */ }
  // iPad / 触控 / 小屏默认全屏，桌面宽屏保持原布局
  return window.matchMedia('(pointer: coarse), (max-width: 1440px)').matches;
};

// 侧边栏导航项。定义在组件外层：如果写在 AppInner 内部，每次渲染都会得到一个
// 新的组件类型，React 会把所有导航按钮卸载重建（丢失焦点、动画重放）。
const SidebarItem = ({ id, icon: Icon, label, activeTab, onSelect }) => (
  <button
    onClick={() => onSelect(id)}
    title={label}
    className={`w-full flex items-center justify-center lg:justify-start lg:space-x-3 px-4 py-3 lg:py-3.5 rounded-2xl transition-all duration-300 flex-shrink-0 ${
      activeTab === id
        ? 'bg-[#1a1a1a] text-white shadow-lg shadow-black/10'
        : 'text-[#666] hover:bg-black/5 hover:text-black'
    }`}
  >
    <Icon size={22} strokeWidth={activeTab === id ? 2.5 : 2} className="flex-shrink-0" />
    {/* 窄屏（iPad 竖屏 / w-24 侧栏）放不下文字，只留图标 + title 提示 */}
    <span className="hidden lg:block font-bold tracking-tight">{label}</span>
  </button>
);

const AppInner = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [taskNavigation, setTaskNavigation] = useState(null);
  const [authed, setAuthed] = useState(!!getToken());
  // 没有 token 就没什么可校验的，开局即视为"已检查完"；
  // 有 token 时由下面的 checkAuth effect 负责置位
  const [bootChecked, setBootChecked] = useState(() => !getToken());
  // 学习日志版本号：每次增删写入后 +1，驱动日历/面板重渲染
  const [studyVersion, setStudyVersion] = useState(0);
  const bumpStudy = () => setStudyVersion((v) => v + 1);
  // AI 练题交卷后点「让 Hermes 复盘错题」：把这场练习的 id 递给 Hermes 对话页，
  // 它自己去拉错题明细和草稿纸。nonce 是为了同一场连点两次也能重新触发。
  const [hermesSeed, setHermesSeed] = useState(null);
  const seedHermes = (sessionId) => {
    setHermesSeed({ sessionId, nonce: Date.now() });
    setActiveTab('hermes');
  };
  const seedHermesUpload = (file) => {
    setHermesSeed({ upload: file, nonce: Date.now() });
    setActiveTab('hermes');
  };
  const [hermesFullscreen, setHermesFullscreen] = useState(readHermesFs);
  const hermesFs = activeTab === 'hermes' && hermesFullscreen;
  const openTodayTask = (task) => {
    setTaskNavigation({ ...task, nonce: Date.now() });
    setActiveTab(task.taskType === 'ai_batch' ? 'aiPractice' : 'practice');
  };
  const consumeTaskNavigation = () => setTaskNavigation(null);

  useEffect(() => {
    const go = () => setActiveTab('knowledge');
    window.addEventListener(KNOWLEDGE_OPEN_EVENT, go);
    return () => window.removeEventListener(KNOWLEDGE_OPEN_EVENT, go);
  }, []);

  useEffect(() => {
    try { localStorage.setItem(HERMES_FS_KEY, hermesFullscreen ? '1' : '0'); }
    catch { /* ignore */ }
  }, [hermesFullscreen]);
  const { getDay: getStudyDay } = useStudyHeatmap(studyVersion);

  // 监听学习日志变更事件（番茄钟完成、数资冲刺完成、导入、删除均会派发）
  useEffect(() => {
    const onChange = () => bumpStudy();
    window.addEventListener('study-log-change', onChange);
    return () => window.removeEventListener('study-log-change', onChange);
  }, []);

  // After hydrate (login / boot): reload local study log + refetch practice heat.
  // Calendar heatmap mounts even on the login screen; without this bump it stays empty
  // while DashboardTodayCard (mounted after auth) looks correct.
  useEffect(() => {
    const onHydrated = () => bumpStudy();
    window.addEventListener('cloud-hydrated', onHydrated);
    return () => window.removeEventListener('cloud-hydrated', onHydrated);
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
    // 无 token 时不需要校验：bootChecked 的初始值已经据此算好（见 useState），
    // 这里直接返回，避免在 effect 同步体内 setState 触发额外一轮渲染。
    if (!getToken()) return;
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

  const openDay = (key) => {
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
      <div className="h-screen w-screen flex items-center justify-center bg-[#e8d5b0] text-sm font-bold text-slate-400">
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
              className="px-3 py-1 rounded-full text-xs font-bold bg-[#2c261c] text-white hover:brightness-110 transition-all"
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
              cls += 'ring-1 ring-[#6b5428] ';
              if (study) {
                style.backgroundColor = study.color;
                numberCls += study.level >= 6 ? 'text-[#1a1a1a] font-black' : 'text-white font-black';
              } else {
                cls += 'bg-white/[0.04] ';
                numberCls += 'text-[#6b5428] font-black';
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
            if (editingKey === key) cls += 'ring-2 ring-white z-[1] ';

            return (
              <div
                key={`cell-${i}`}
                className={cls + numberCls}
                style={style}
                onClick={() => openDay(key)}
                title={
                  (hasEvent ? `${label}` : '') +
                  (study ? ` · 学习 ${study.score} 分 / ${study.minutes} 分钟` : '')
                }
              >
                <span className="relative z-10">{day}</span>
                {/* 事件标签：右上角小点 */}
                {hasEvent && (
                  <span className="absolute top-0.5 right-0.5 w-1 h-1 rounded-full bg-[#2c261c]" />
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
      <div className="bg-white rounded-[2.5rem] p-8 shadow-sm border border-[#e8d5b0]">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-[#1a1a1a] text-white flex items-center justify-center">
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
                ? 'ring-[#6b5428]'
                : 'ring-[#1a1a1a]/20';
            const badgeColor = urgent ? 'text-[#ff6b6b]' : soon ? 'text-[#6b5428]' : 'text-[#1a1a1a]';
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
    const study = getStudyDay(editingKey);
    const derived = digestDay(study?.entries || []);
    const stored = loadDigest()[editingKey];
    // 今天还在学，用实时明细；过去的日子优先用每日总结写下的清单
    const items =
      editingKey < todayKey && Array.isArray(stored) && stored.length
        ? stored
        : derived;
    return (
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        onClick={closeEditor}
      >
        <div
          className="bg-white rounded-[2rem] p-8 w-full max-w-md shadow-2xl max-h-[80vh] overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-6">
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">当日学习</p>
              <p className="text-xl font-black italic">
                {editingKey} · {weekdayCN}
              </p>
            </div>
            <button
              onClick={closeEditor}
              className="w-8 h-8 rounded-full bg-[#e8d5b0] hover:bg-[#e8e6dd] flex items-center justify-center"
            >
              <X size={16} />
            </button>
          </div>

          {items.length === 0 ? (
            <p className="text-sm font-bold text-slate-400 mb-6">这天还没有学习记录</p>
          ) : (
            <ol className="space-y-2.5 mb-5">
              {items.map((t, i) => (
                <li key={i} className="flex gap-3 text-sm font-bold text-[#1a1a1a] leading-snug">
                  <span className="text-[#6b5428] tabular-nums w-6 flex-shrink-0">{i + 1}.</span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          )}

          {study?.score > 0 && (
            <p className="text-xs font-bold text-slate-400 mb-6 tabular-nums">
              {study.score} 分
              {study.minutes ? ` · ${study.minutes} 分钟` : ''}
            </p>
          )}

          <details className="group border-t border-[#e8d5b0] pt-4">
            <summary className="text-xs font-black uppercase tracking-widest text-slate-400 cursor-pointer list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
              标记重要日子
              {current && (
                <span className="normal-case tracking-normal font-bold text-[#1a1a1a] truncate max-w-[10rem]">
                  {current}
                </span>
              )}
            </summary>
            <label className="text-xs font-bold text-slate-400 block mt-4 mb-2">事件名称</label>
            <input
              type="text"
              value={editingLabel}
              onChange={(e) => setEditingLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveEvent();
                if (e.key === 'Escape') closeEditor();
              }}
              placeholder="例如：广东省考"
              maxLength={30}
              className="w-full bg-[#e8d5b0]/60 border border-transparent rounded-2xl py-3 px-4 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-[#6b5428] mb-4"
            />
            <div className="flex space-x-3">
              <button
                onClick={saveEvent}
                className="flex-1 bg-[#1a1a1a] text-white font-black py-3 rounded-2xl hover:bg-[#2c261c] hover:text-white transition-all uppercase tracking-widest text-xs"
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
            </div>
          </details>
        </div>
      </div>
    );
  };

  return (
    // iOS Safari 的 100vh 比可视区域高（地址栏/工具栏不计入），会把侧栏底部顶到
    // 屏幕外。100dvh 跟随动态视口；不支持的浏览器忽略 inline style，退回 h-screen。
    <div
      className={`flex h-screen text-[#1a1a1a] font-sans overflow-hidden overscroll-none ${
        hermesFs ? 'bg-white p-0' : 'bg-[#e8d5b0] p-4'
      }`}
      style={{
        height: '100dvh',
        // 只给 iPad/触控留空：状态栏会盖住全屏顶栏。Windows 全屏不要这段空隙，顶栏贴顶。
        paddingTop: hermesFs && window.matchMedia('(pointer: coarse)').matches
          ? 'max(2rem, env(safe-area-inset-top, 0px))'
          : undefined,
      }}
    >
      <aside className={`${hermesFs ? 'hidden' : ''} w-24 lg:w-64 flex flex-col p-4 space-y-4 lg:space-y-6 min-h-0`}>
        <div className="flex items-center justify-center lg:justify-start lg:space-x-3 px-4 py-2 flex-shrink-0">
          <div className="w-10 h-10 bg-[#1a1a1a] rounded-xl flex items-center justify-center text-white font-black flex-shrink-0">
            学
          </div>
          <h1 className="text-xl font-black tracking-tighter hidden lg:block uppercase">STUDY!</h1>
        </div>

        {/* 导航项比 iPad 竖屏高度多，必须能滚动 —— 否则末尾的「AI 练题」点不到。
            overscroll-contain 防止滚到底后把整页往下拽（iOS 橡皮筋）。 */}
        <nav className="flex-1 min-h-0 overflow-y-auto overscroll-contain space-y-2 lg:space-y-2.5 -mx-1 px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <SidebarItem id="dashboard" icon={LayoutDashboard} label="仪表盘" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="studyBoost" icon={Zap} label="学习提升" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="knowledge" icon={GraduationCap} label="知识点" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="copybook" icon={PenTool} label="字帖练习" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="review" icon={BookMarked} label="复习" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="flashcards" icon={Layers} label="抽认卡" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="practice" icon={BookOpen} label="数资练习" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="pomodoro" icon={TimerIcon} label="番茄钟" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="mockexam" icon={ClipboardList} label="全卷模考" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="examReview" icon={ScanSearch} label="录屏复盘" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="uploads" icon={Upload} label="资料上传" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="hermes" icon={MessageSquare} label="Hermes" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="aiPractice" icon={Target} label="AI 练题" activeTab={activeTab} onSelect={setActiveTab} />
          <SidebarItem id="mixer" icon={Sliders} label="声音混音器" activeTab={activeTab} onSelect={setActiveTab} />
        </nav>

        <div className="pt-3 lg:pt-5 border-t border-black/5 space-y-1 flex-shrink-0">
          <div className="hidden lg:flex items-center space-x-3 px-2 py-3">
            <div className="w-10 h-10 rounded-full bg-slate-300 overflow-hidden border-2 border-white shadow-sm flex-shrink-0">
              <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=Felix" alt="avatar" />
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-bold truncate italic">Russell</p>
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">私人练习空间</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="退出登录"
            className="w-full flex items-center justify-center lg:justify-start lg:space-x-3 px-4 py-3 rounded-2xl text-[#666] hover:bg-black/5 hover:text-[#ff6b6b] transition-all"
          >
            <LogOut size={18} className="flex-shrink-0" />
            <span className="hidden lg:block text-xs font-black uppercase tracking-widest">退出登录</span>
          </button>
        </div>
      </aside>

      <main className={`flex-1 flex flex-col overflow-hidden ${
        hermesFs
          ? 'bg-white'
          : 'bg-white/60 backdrop-blur-xl rounded-[3rem] shadow-2xl shadow-black/[0.03] border border-white/50'
      }`}>
        <header className={`${hermesFs ? 'hidden' : ''} h-24 flex items-center justify-between px-10`}>
          <div>
            <h2 className="text-2xl font-black tracking-tight">
              {activeTab === 'dashboard' && '欢迎回来，Russell！'}
              {activeTab === 'studyBoost' && '学习提升 · 言语高频考点库'}
              {activeTab === 'knowledge' && '知识点 · 广东省考老师口径'}
              {activeTab === 'copybook' && '申论字帖与 AI 图像比对'}
              {activeTab === 'review' && '知识点复习'}
              {activeTab === 'flashcards' && '抽认卡'}
              {activeTab === 'pomodoro' && '番茄钟'}
              {activeTab === 'mockexam' && '全卷模考'}
              {activeTab === 'examReview' && '录屏复盘 · 真题 / 套题 / 测试'}
              {activeTab === 'uploads' && '资料上传'}
              {activeTab === 'hermes' && 'Hermes · 智能助手'}
              {activeTab === 'aiPractice' && 'AI 练题 · 定向强化'}
              {activeTab === 'mixer' && '声音混音器'}
            </h2>
            <p className="text-sm font-medium text-slate-400">保持节奏，稳步提升。</p>
          </div>
          <TopBarTimer onOpen={() => setActiveTab('pomodoro')} />
        </header>

        {/* Hermes 对话页要占满高度且自己管滚动，故单独用 overflow-hidden 容器 */}
        <div
          className={
            activeTab === 'hermes'
              ? (hermesFs ? 'flex-1 overflow-hidden' : 'flex-1 overflow-hidden px-10 pb-6 pt-2')
              : 'flex-1 overflow-y-auto overscroll-y-contain p-10 pt-4 space-y-10'
          }
        >
          {activeTab === 'dashboard' && (
            <div className="space-y-10">
              {renderCountdowns()}

              <StudyLogPanel version={studyVersion} onChange={bumpStudy} />

              {/* 今日概览 + 日历热力图 */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                <DashboardTodayCard studyVersion={studyVersion} />
                {renderCalendar()}
              </div>
            </div>
          )}

          {activeTab === 'studyBoost' && <StudyBoost />}

          {activeTab === 'knowledge' && <Knowledge />}

          {activeTab === 'copybook' && <Copybook />}

          <div className={activeTab === 'review' ? '' : 'hidden'}>
            <Review />
          </div>

          {activeTab === 'practice' && (
            <NumericPractice
              taskNavigation={taskNavigation}
              onTaskNavigationConsumed={consumeTaskNavigation}
              onNavigateTask={openTodayTask}
            />
          )}

          {activeTab === 'flashcards' && <Flashcards />}

          {activeTab === 'pomodoro' && <Pomodoro />}

          {activeTab === 'mockexam' && <MockExam />}

          {activeTab === 'examReview' && <ExamReview />}

          {activeTab === 'uploads' && <Uploads onReviewWithHermes={seedHermesUpload} />}

          {/* Keep Hermes mounted while other modules are open so its WebSocket,
              active response, attachments, and scroll state continue in background. */}
          <div className={activeTab === 'hermes' ? 'h-full' : 'hidden'}>
            <HermesChat
              active={activeTab === 'hermes'}
              seed={hermesSeed}
              onSeedConsumed={() => setHermesSeed(null)}
              fullscreen={hermesFs}
              onToggleFullscreen={() => setHermesFullscreen((v) => !v)}
              headerExtra={<TopBarTimer onOpen={() => setActiveTab('pomodoro')} />}
            />
          </div>

          {activeTab === 'aiPractice' && (
            <AIQuizHome
              onAnalyzeWithHermes={seedHermes}
              initialBatchId={taskNavigation?.taskType === 'ai_batch' ? taskNavigation.batchId : null}
              onInitialBatchHandled={consumeTaskNavigation}
            />
          )}

          {activeTab === 'mixer' && <Mixer />}
        </div>
      </main>

      {renderEditor()}
      {activeTab !== 'hermes' && <Cheatsheet />}
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
  const serverHeat = useServerHeat(studyVersion);
  const stats = useMemo(() => summarize(log, serverHeat), [log, serverHeat]);
  const today = stats.today;

  // 今日明细按实际出现的来源聚合，而不是写死几种：
  // 新接一个热力来源时，只要 ENTRY_TYPES 里有它，这张卡自动就会显示
  const byType = useMemo(() => {
    const acc = {};
    for (const e of today.entries) {
      const meta = ENTRY_TYPES[e.type];
      if (!meta) continue;
      if (!acc[e.type]) acc[e.type] = { ...meta, minutes: 0, count: 0, score: 0 };
      acc[e.type].count += 1;
      acc[e.type].minutes += e.minutes || 0;
      acc[e.type].score += e.score || 0;
    }
    return acc;
  }, [today]);

  const totalScore = today.score;
  const totalMin = today.minutes;

  return (
    <div className="lg:col-span-2 bg-[#dfdbcc] rounded-[2.5rem] p-10 relative overflow-hidden flex flex-col justify-between">
      <div className="relative z-10">
        <h3 className="text-xl font-bold mb-1">今日概览</h3>
        <p className="text-sm font-bold opacity-60">
          已连续打卡 {stats.streak} 天 · 本周学习 {stats.weekDays} 天
        </p>
      </div>

      <div className="absolute top-10 right-10 w-48 h-48 bg-[#2c261c] rounded-full blur-[40px] opacity-60 animate-pulse" />
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
                    {v.count} 次 · +{v.score}
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

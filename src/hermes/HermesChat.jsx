// Hermes 对话页
//
// 走 JSON-RPC over WebSocket 直连 Hermes 的 gateway（经 Express 代理），
// 与官方 dashboard 的 Chat 用的是同一套协议和同一个 agent，
// 因此这里能看到并续接微信、cron、CLI 的全部会话。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Send, Square, Plus, MessageSquare, Loader2, RefreshCw,
  Brain, Smartphone, CalendarClock, Terminal, X, Image as ImageIcon, Trash2,
  PenTool, Target, ChevronRight, ScanSearch, Upload, Maximize2, Minimize2, Expand, Shrink } from 'lucide-react';

import { api } from '../api.js';
import HermesGateway from './gateway.js';
import MarkdownMessage from './MarkdownMessage.jsx';
import ToolCard from './ToolCard.jsx';
import QuotaBar from './QuotaBar.jsx';

// 会话来源 → 展示分组
const SOURCE_META = {
  weixin:  { label: '微信',     icon: Smartphone,    order: 3 },
  cron:    { label: '每日计划', icon: CalendarClock, order: 1 },
  tui:     { label: '本地',     icon: Terminal,      order: 0 },
  cli:     { label: '本地',     icon: Terminal,      order: 0 },
};
const sourceMeta = (s) => SOURCE_META[s] || { label: '其他', icon: MessageSquare, order: 3 };

let msgSeq = 0;
const uid = () => `m${++msgSeq}`;

const IMAGE_MAX_BYTES = 10 * 1024 * 1024;

// session.resume 返回的历史消息里，图片是以裸 data URL 的形式内嵌在 text 末尾的
// （hermes 侧 _coerce_message_text 把多模态 content 折叠成单一字符串时留下的）。
// 不解析出来的话：m.images 永远是 undefined（图片不显示），而那几 MB 的 base64
// 会被当成正文塞进 markdown 渲染器。官方 desktop 端对应的函数叫 extractEmbeddedImages。
const EMBEDDED_IMAGE_RE = /data:image\/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+/g;

const extractEmbeddedImages = (text) => text.match(EMBEDDED_IMAGE_RE) || [];

// 去掉正文里的裸 data URL。图片一般是前面带换行单独一行，连换行一起吃掉，
// 避免正文尾部留下一串空行
const stripEmbeddedImages = (text) =>
  text.replace(new RegExp(`\\n*${EMBEDDED_IMAGE_RE.source}`, 'g'), '').trim();

// hermes 运行时会把「后台子任务完成」这类通知以 user 角色写进历史（见
// hermes-agent/tools/process_registry.py 的 _format_async_delegation），
// 模型需要读到它才能拿到子任务结果，但那不是用户说的话。
// 不过滤的话，换浏览器触发 session.resume 时这整段会当成用户消息冒出来。
// 用行首锚定的方括号标记来判断，避免误伤用户正常引用这些词的消息。
const SYSTEM_NOTICE_RE = /^\s*\[(?:ASYNC DELEGATION[^\]]*|SYSTEM NOTIFICATION[^\]]*|BACKGROUND TASK[^\]]*)\]/;
const isSystemInjectedNotice = (text) => SYSTEM_NOTICE_RE.test(String(text || ''));

const hydrateHistory = (raw) =>
  (raw || [])
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .filter((m) => !isSystemInjectedNotice(m.text))
    .map((m) => {
      const rawText = String(m.text || '');
      const images = extractEmbeddedImages(rawText);
      return {
        id: uid(), role: m.role,
        content: images.length > 0 ? stripEmbeddedImages(rawText) : rawText,
        streaming: false, tools: [], thinking: '', images,
      };
    })
    // 纯图/空正文的用户气泡也要留着，否则「我发过」在刷新后会消失
    .filter((m) => m.content || (m.images?.length ?? 0) > 0);

const eventText = (ev) => ev?.payload?.text || ev?.payload?.rendered || '';

// 会话列表拉取上限。gateway 侧 session.list 会给每条会话跑一次 preview 子查询
// （50 条约 77ms，全量 124 条 200ms+），条数直接决定首屏等待时间。
// 40 条足够覆盖最近的对话，再往前翻的需求很少。
const SESSION_LIST_LIMIT = 40;

// 上次的会话列表缓存。进页面时先用它把左栏渲染出来，等 WS 连上再静默替换成新数据，
// 这样首屏不用干等「握手 + DB 查询」。sessionStorage 而不是 localStorage：
// 关掉标签页就失效，避免长期拿着过期列表。
const SESSION_CACHE_KEY = 'hermes.sessions.v1';

const readCachedSessions = () => {
  try {
    const raw = sessionStorage.getItem(SESSION_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const writeCachedSessions = (list) => {
  try {
    sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify(list));
  } catch { /* 隐私模式下 sessionStorage 可能不可写，缓存失败不影响功能 */ }
};

// 一次最多带几张草稿纸。每张 PNG 转成 base64 有 300KB~1MB，
// 带太多会把 prompt 撑爆，也会让模型的注意力散掉。
const MAX_DRAFT_ATTACH = 4;

const IS_STANDALONE =
  typeof window !== 'undefined' &&
  (window.matchMedia('(display-mode: standalone), (display-mode: fullscreen)').matches
    || window.navigator.standalone === true);

const osFullscreenEl = () => document.fullscreenElement || document.webkitFullscreenElement;

const requestOsFullscreen = () => {
  const el = document.documentElement;
  const req = el.requestFullscreen || el.webkitRequestFullscreen;
  if (!req) return Promise.reject(new Error('no api'));
  return Promise.resolve(req.call(el, { navigationUI: 'hide' }));
};

const exitOsFullscreen = () => {
  const exit = document.exitFullscreen || document.webkitExitFullscreen;
  if (!exit || !osFullscreenEl()) return Promise.resolve();
  return Promise.resolve(exit.call(document));
};

const fmtSec = (sec) => {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

const clip = (text, max) => {
  const t = String(text || '').trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
};

// 只放大对话正文（表格/Markdown），不动顶栏和浏览器缩放。
// 整数百分比，避开 1.15 这类浮点对不上 localStorage 读回来的问题。
const FONT_KEY = 'hermes.fontScale';
const FONT_STEPS = [85, 100, 115, 130, 150, 175];
const readFontScale = () => {
  try {
    const v = Number(localStorage.getItem(FONT_KEY));
    if (FONT_STEPS.includes(v)) return v;
  } catch { /* 隐私模式 */ }
  return 100;
};

const HermesChat = ({ seed, onSeedConsumed, fullscreen = false, onToggleFullscreen, headerExtra }) => {
  const gwRef = useRef(null);
  const [connState, setConnState] = useState('idle');
  const [sessions, setSessions] = useState(() => readCachedSessions());
  const [sessionsLoading, setSessionsLoading] = useState(false);
  // sid 是 gateway 的活动会话 id（session.create/resume 返回），与列表里的存档 id 不同
  const [sid, setSid] = useState(null);
  const [activeStoredId, setActiveStoredId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [banner, setBanner] = useState('');
  const [showThinking, setShowThinking] = useState(false);
  const [pendingImages, setPendingImages] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 1440);
  const [dragOver, setDragOver] = useState(false);
  const [osFs, setOsFs] = useState(() => !!osFullscreenEl());
  const [fontScale, setFontScale] = useState(readFontScale);
  // 「带上错题 + 草稿纸」用的：practiceRuns 是最近交过卷的几场练习
  const [showPicker, setShowPicker] = useState(false);
  const [practiceRuns, setPracticeRuns] = useState([]);
  // 「带上真题复盘」：把某场模考的录屏行为报告塞进输入框，接着追问
  const [showReview, setShowReview] = useState(false);
  const [examReviews, setExamReviews] = useState([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [runsLoading, setRunsLoading] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [showUploads, setShowUploads] = useState(false);
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploadsLoading, setUploadsLoading] = useState(false);

  const scrollRef = useRef(null);
  const stickToBottom = useRef(true);
  const taRef = useRef(null);
  // sid 的镜像：send/interrupt 等回调里要读最新值，又不想因此重建回调
  const sidRef = useRef(null);
  useEffect(() => { sidRef.current = sid; }, [sid]);
  // 同理：会话过期重连时要知道当前开着哪个存档，才能 resume 回来保住上下文
  const activeStoredIdRef = useRef(null);
  useEffect(() => { activeStoredIdRef.current = activeStoredId; }, [activeStoredId]);
  useEffect(() => {
    try { localStorage.setItem(FONT_KEY, String(fontScale)); }
    catch { /* 隐私模式 */ }
  }, [fontScale]);
  // busy 是 state，setBusy 要等下一次渲染才拦得住第二次点击。
  // 图片上传是 await，中间那几秒只能靠同步的 ref 挡住连点
  const sendingRef = useRef(false);
  // 用来区分「第一次连上」和「断线重连」。重连后必须再 resume，
  // 否则 Hermes 的事件还绑在已经死掉的那条 WS 上，界面就会一直「思考中」。
  const openedOnceRef = useRef(false);
  const [waitSec, setWaitSec] = useState(0);

  // ---------- 消息辅助 ----------
  const appendAssistantDelta = useCallback((text) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === 'assistant' && last.streaming) {
        const copy = prev.slice(0, -1);
        copy.push({ ...last, content: last.content + text });
        return copy;
      }
      return [...prev, { id: uid(), role: 'assistant', content: text, streaming: true, tools: [], thinking: '' }];
    });
  }, []);

  const appendThinking = useCallback((text) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === 'assistant' && last.streaming) {
        const copy = prev.slice(0, -1);
        copy.push({ ...last, thinking: (last.thinking || '') + text });
        return copy;
      }
      return [...prev, { id: uid(), role: 'assistant', content: '', streaming: true, tools: [], thinking: text }];
    });
  }, []);

  // 工具事件挂到当前流式回复上；没有就先建一个占位
  const upsertTool = useCallback((patch) => {
    setMessages((prev) => {
      const idx = [...prev].reverse().findIndex((m) => m.role === 'assistant' && m.streaming);
      const at = idx === -1 ? -1 : prev.length - 1 - idx;
      const target = at === -1
        ? { id: uid(), role: 'assistant', content: '', streaming: true, tools: [], thinking: '' }
        : prev[at];

      const tools = [...(target.tools || [])];
      const key = patch.tool_id || patch.name;
      const found = tools.findIndex((t) => (t.tool_id || t.name) === key);
      if (found === -1) tools.push(patch);
      else tools[found] = { ...tools[found], ...patch };

      const updated = { ...target, tools };
      if (at === -1) return [...prev, updated];
      const copy = prev.slice();
      copy[at] = updated;
      return copy;
    });
  }, []);

  const finishStreaming = useCallback((finalText = '') => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || !last.streaming) {
        // 流式 delta 全程没到、只来了一条 complete（长上下文卡流时很常见）
        if (finalText) {
          return [...prev, {
            id: uid(), role: 'assistant', content: finalText,
            streaming: false, tools: [], thinking: '',
          }];
        }
        return prev;
      }
      const copy = prev.slice(0, -1);
      // 把仍标记为运行中的工具收尾，避免一直转圈
      const tools = (last.tools || []).map((t) => (t.done ? t : { ...t, done: true }));
      copy.push({ ...last, content: last.content || finalText, streaming: false, tools });
      return copy;
    });
    setBusy(false);
    setStatus('');
    // 回复完成后刷新列表：Hermes 在第一轮对话结束后才生成 title，
    // 这里延迟刷一次让左栏显示正确的标题
    setTimeout(() => {
      const gw = gwRef.current;
      if (!gw) return;
      gw.request('session.list', { limit: SESSION_LIST_LIMIT }).then((res) => {
        if (Array.isArray(res?.sessions)) {
          setSessions(res.sessions);
          writeCachedSessions(res.sessions);
        }
      }).catch(() => {});
    }, 1500);
  }, []);

  // ---------- 建立连接 ----------
  useEffect(() => {
    const gw = new HermesGateway();
    gwRef.current = gw;

    const offs = [
      gw.onState(setConnState),

      gw.on('message.delta', (ev) => {
        const t = ev.payload?.text;
        if (t) appendAssistantDelta(t);
      }),
      // thinking.delta 是转圈状态文案，不是推理过程（官方 desktop 直接忽略）
      gw.on('thinking.delta', (ev) => {
        const t = ev.payload?.text;
        if (t) setStatus(String(t));
      }),
      gw.on('reasoning.delta', (ev) => {
        const t = ev.payload?.text;
        if (t) appendThinking(t);
      }),
      gw.on('message.start', () => {
        setBusy(true);
        setStatus('生成中');
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === 'assistant' && last.streaming) return prev;
          return [...prev, {
            id: uid(), role: 'assistant', content: '',
            streaming: true, tools: [], thinking: '',
          }];
        });
      }),
      gw.on('message.complete', (ev) => finishStreaming(eventText(ev))),

      gw.on('tool.start', (ev) => {
        const p = ev.payload || {};
        upsertTool({
          tool_id: p.tool_id, name: p.name || 'tool', args: p.args,
          args_text: p.args_text, preview: p.preview, done: false,
        });
        setStatus(`调用 ${p.name || '工具'}`);
      }),
      gw.on('tool.complete', (ev) => {
        const p = ev.payload || {};
        upsertTool({
          tool_id: p.tool_id, name: p.name || 'tool', args: p.args,
          result: p.result, duration_s: p.duration_s, done: true,
        });
        setStatus('生成中');
      }),

      gw.on('status.update', (ev) => {
        const s = ev.payload?.text || ev.payload?.status;
        if (s) setStatus(String(s));
      }),

      gw.on('error', (ev) => {
        const msg = ev.payload?.message || '未知错误';
        setBanner(msg);
        setBusy(false);
        setStatus('');
      }),

      // 审批请求：ExamSystem 这个界面不做审批 UI，提示去微信/终端处理
      gw.on('approval.request', () => {
        setBanner('Hermes 请求操作授权，请到微信或终端确认（本页暂不支持审批）');
      }),
    ];

    let cancelled = false;
    gw.connect()
      .then(async () => {
        if (cancelled) return;
        setBanner('');
        // 有缓存就先不显示 loading，静默刷新；没有缓存才转圈等
        const cached = readCachedSessions();
        if (cached.length === 0) setSessionsLoading(true);
        try {
          const res = await gw.request('session.list', { limit: SESSION_LIST_LIMIT });
          const list = Array.isArray(res?.sessions) ? res.sessions : [];
          if (!cancelled) {
            setSessions(list);
            writeCachedSessions(list);
          }
        } catch (err) {
          if (!cancelled) setBanner(`拉取会话列表失败：${err.message}`);
        } finally {
          if (!cancelled) setSessionsLoading(false);
        }
      })
      .catch((err) => { if (!cancelled) setBanner(err.message || '连接 Hermes 失败'); });

    return () => {
      cancelled = true;
      for (const off of offs) off?.();
      gw.close();
      gwRef.current = null;
    };
    // 只在挂载时建立一次连接
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!busy) {
      setWaitSec(0);
      return undefined;
    }
    const t0 = Date.now();
    const id = setInterval(() => setWaitSec(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [busy]);

  // ---------- 会话列表 ----------
  const deleteSession = useCallback(async (e, sessionId) => {
    e.stopPropagation();
    const gw = gwRef.current;
    if (!gw) return;
    try {
      // session.close 需要 live session id（_sessions 字典的 key，即 session.create/resume 返回的 id），
      // session.delete 需要 stored/DB session id（列表里的 s.id / session_key）。
      // 只有当前正在续接的那个 stored session 才有对应的 live id（sidRef.current）。
      const liveId = activeStoredIdRef.current === sessionId ? sidRef.current : null;
      if (liveId) {
        await gw.request('session.close', { session_id: liveId }).catch(() => {});
      }
      await gw.request('session.delete', { session_id: sessionId });
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeStoredIdRef.current === sessionId) {
        setActiveStoredId(null);
        setSid(null);
        sidRef.current = null;
        setMessages([]);
      }
    } catch (err) {
      setBanner(`删除失败：${err.message}`);
    }
  }, []);

  const refreshSessions = useCallback(async () => {
    const gw = gwRef.current;
    if (!gw) return;
    setSessionsLoading(true);
    try {
      const res = await gw.request('session.list', { limit: SESSION_LIST_LIMIT });
      const list = Array.isArray(res?.sessions) ? res.sessions : [];
      setSessions(list);
      writeCachedSessions(list);
    } catch (err) {
      setBanner(`拉取会话列表失败：${err.message}`);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const grouped = useMemo(() => {
    const groups = new Map();
    for (const s of sessions) {
      const meta = sourceMeta(s.source);
      if (!groups.has(meta.label)) groups.set(meta.label, { meta, items: [] });
      groups.get(meta.label).items.push(s);
    }
    return [...groups.values()].sort((a, b) => a.meta.order - b.meta.order);
  }, [sessions]);

  const applyResume = useCallback((res, storedId) => {
    sidRef.current = res.session_id;
    setSid(res.session_id);
    if (storedId) setActiveStoredId(storedId);
    const hydrated = hydrateHistory(res.messages);
    const lastHydratedUser = [...hydrated].reverse().find((m) => m.role === 'user');
    const inflightUser = String(res.inflight?.user || '').trim();

    // 回合还在跑时，当前这句用户话只在 inflight 里，还没写进 history。
    // 重连若直接用 history 覆盖，会把本地刚发出去的气泡抹掉。
    setMessages((prev) => {
      const lastLocalUser = [...prev].reverse().find((m) => m.role === 'user');
      const pending = inflightUser
        || (lastLocalUser && lastLocalUser.content !== lastHydratedUser?.content
          ? lastLocalUser.content
          : '');
      const next = [...hydrated];
      if (pending && pending !== lastHydratedUser?.content) {
        next.push({
          id: lastLocalUser?.id || uid(),
          role: 'user',
          content: pending,
          streaming: false, tools: [], thinking: '',
          images: lastLocalUser?.images || [],
        });
      }
      if (res.running) {
        const last = next[next.length - 1];
        if (!(last && last.role === 'assistant' && last.streaming)) {
          next.push({
            id: uid(), role: 'assistant',
            content: res.inflight?.assistant || '',
            streaming: true, tools: [], thinking: '',
          });
        }
      }
      return next;
    });
    if (res.running) {
      setBusy(true);
      setStatus('生成中');
    } else {
      setBusy(false);
      setStatus('');
    }
    stickToBottom.current = true;
  }, []);

  // WS 断过再连上：必须把当前存档 resume 回去，事件才会重新绑到这条连接。
  // 第一次 open 由上面的 connect() 处理，这里只接重连。
  useEffect(() => {
    if (connState !== 'open') return;
    if (!openedOnceRef.current) {
      openedOnceRef.current = true;
      return;
    }
    const gw = gwRef.current;
    const stored = activeStoredIdRef.current;
    if (!gw || !stored) return;
    setStatus('重连会话');
    gw.request('session.resume', { session_id: stored, cols: 100 })
      .then((res) => applyResume(res, stored))
      .catch((err) => setBanner(`重连会话失败：${err.message}`));
  }, [connState, applyResume]);

  const openSession = useCallback(async (stored) => {
    const gw = gwRef.current;
    if (!gw || busy) return;
    setBanner('');
    setStatus('载入会话');
    try {
      const res = await gw.request('session.resume', { session_id: stored.id, cols: 100 });
      applyResume(res, stored.id);
    } catch (err) {
      setBanner(`打开会话失败：${err.message}`);
      setStatus('');
    }
  }, [busy, applyResume]);

  const newSession = useCallback(async () => {
    const gw = gwRef.current;
    if (!gw || busy) return;
    setBanner('');
    try {
      const res = await gw.request('session.create', { cols: 100, cwd: '/home/ubuntu' });
      sidRef.current = res.session_id;
      setSid(res.session_id);
      setActiveStoredId(null);
      setMessages([]);
      setPendingImages([]);
      // 新建后立刻刷新列表，让左栏出现这条新会话
      try {
        const listRes = await gw.request('session.list', {});
        setSessions(Array.isArray(listRes?.sessions) ? listRes.sessions : []);
      } catch { /* 列表刷新失败不影响对话 */ }
    } catch (err) {
      setBanner(`新建会话失败：${err.message}`);
    }
  }, [busy]);

  // ---------- 发送 ----------
  const send = useCallback(async () => {
    const gw = gwRef.current;
    const text = input.trim();
    if (!gw || busy || sendingRef.current) return;
    if (!text && pendingImages.length === 0) return;
    // 断线时直接拦下，输入框里的字原封不动（读 gateway 自己的状态，
    // 不把 connState 拉进依赖，否则每次重连都要重建这个回调）
    if (gw.connectionState !== 'open') {
      setBanner('还没连上 Hermes，连上了再发');
      return;
    }

    // 挂机回来常见的一种失败：WS 断开超过宽限期后，服务端把会话回收了
    // （end_reason=ws_orphan_reap）。WS 自己会重连，所以界面看着是「已连接」，
    // 但我们手里的 sid 已经失效，一发就报 session not found。
    // 这时候静默换一个可用会话再重发，不该让用户手动刷新页面。
    const isSessionGone = (err) => /session not found/i.test(err?.message || '');

    sendingRef.current = true;
    const images = pendingImages;
    const msgId = uid();

    // 先把界面切到"发送中"：气泡上屏、输入框清空、按钮换成停止。
    // 图片上传要好几秒，这期间一点反馈都没有的话用户只会以为没发出去
    setBanner('');
    setMessages((prev) => [
      ...prev,
      {
        id: msgId, role: 'user', content: text || '(图片)', streaming: false,
        tools: [], thinking: '', images: images.map((i) => i.dataUrl),
      },
    ]);
    setInput('');
    setPendingImages([]);
    setBusy(true);
    setStatus(images.length > 0 ? '上传图片' : '已发送');
    stickToBottom.current = true;

    // 拿一个可用会话：优先 resume 当前存档（能保住上下文），
    // 没有存档可 resume 就新建一个
    const acquireSession = async () => {
      const stored = activeStoredIdRef.current;
      if (stored) {
        try {
          const res = await gw.request('session.resume', { session_id: stored, cols: 100 });
          return res.session_id;
        } catch { /* 存档也 resume 不了就退到新建 */ }
      }
      const res = await gw.request('session.create', { cols: 100, cwd: '/home/ubuntu' });
      return res.session_id;
    };

    // 一次完整的投递：挂图片 + 提交文本。会话失效时整段重放，
    // 所以图片不会只挂上一半
    const deliver = async (target) => {
      for (const img of images) {
        await gw.request('image.attach_bytes', {
          session_id: target,
          content_base64: img.dataUrl,
          filename: img.name,
        });
      }
      await gw.request('prompt.submit', { session_id: target, text: text || '看看这张图片' });
    };

    try {
      let target = sidRef.current;
      if (!target) {
        target = await acquireSession();
        sidRef.current = target;
        setSid(target);
      }

      try {
        await deliver(target);
      } catch (err) {
        if (!isSessionGone(err)) throw err;
        // 会话被回收了，换一个新的重发一次。只重试一次：
        // 如果新会话也说 not found，那就是别的问题，不该无限重试
        setStatus('会话已过期，正在重连');
        const fresh = await acquireSession();
        sidRef.current = fresh;
        setSid(fresh);
        await deliver(fresh);
      }
      setStatus('已发送');
    } catch (err) {
      // 没送出去就别把气泡留在那儿冒充已发送，内容还给输入框方便重发
      setBanner(`发送失败：${err.message}`);
      setMessages((prev) => prev.filter((m) => m.id !== msgId));
      setInput((cur) => cur || text);
      setPendingImages((cur) => (cur.length > 0 ? cur : images));
      setBusy(false);
      setStatus('');
    } finally {
      sendingRef.current = false;
    }
  }, [busy, input, pendingImages]);

  const interrupt = useCallback(async () => {
    const gw = gwRef.current;
    if (!gw || !sidRef.current) return;
    try {
      await gw.request('session.interrupt', { session_id: sidRef.current });
      finishStreaming();
      setStatus('');
    } catch (err) {
      // 会话已经被回收的话，也就没有在跑的任务需要打断了，
      // 把界面收干净就行，不用拿这个去烦用户
      if (/session not found/i.test(err?.message || '')) {
        finishStreaming();
        setStatus('');
        return;
      }
      setBanner(`中断失败：${err.message}`);
    }
  }, [finishStreaming]);

  // ---------- 带上练习错题 + 当时的草稿纸 ----------
  const loadPracticeRuns = useCallback(async () => {
    setRunsLoading(true);
    try {
      const list = await api('/api/practice/sessions?limit=15');
      setPracticeRuns(Array.isArray(list) ? list : []);
    } catch (err) {
      setBanner(`拉取练习记录失败：${err.message}`);
    } finally {
      setRunsLoading(false);
    }
  }, []);

  const openPicker = useCallback(() => {
    setShowPicker(true);
    loadPracticeRuns();
  }, [loadPracticeRuns]);

  // 把某一场练习的错题拼成 prompt、草稿纸作为附图挂上，然后停在输入框交给用户按发送。
  // 中间留一手是故意的：想追加一句「重点看第 3 题」时不用重新组织上下文。
  const attachPractice = useCallback(async (sessionId) => {
    setAttaching(true);
    setBanner('');
    try {
      const rep = await api(`/api/practice/sessions/${sessionId}/report`);
      const items = rep?.items || [];
      const wrong = items.filter((it) => !it.is_correct);
      if (wrong.length === 0) {
        setBanner('这一场全对，没有错题可以分析');
        return;
      }

      const noOf = (it) => items.indexOf(it) + 1;
      const drafted = wrong.filter((it) => it.draft_url).slice(0, MAX_DRAFT_ATTACH);

      const images = [];
      for (const it of drafted) {
        try {
          // 让后端直接给 data URL：<img> 再进 canvas 会多一道跨域污染的坑
          const r = await api(`/api/practice/sessions/${sessionId}/drafts/${it.question_id}/base64`);
          if (r?.data_url) {
            images.push({ id: uid(), name: `q${noOf(it)}-draft.png`, dataUrl: r.data_url });
          }
        } catch { /* 单张拿不到就跳过，不该拖垮整次复盘 */ }
      }
      const draftedNos = drafted.slice(0, images.length).map(noOf);
      const draftedSet = new Set(draftedNos);

      const s = rep.session || {};
      const lines = [
        `帮我复盘一次公考练习：${s.category || '未命名批次'}，共 ${s.total} 题，对 ${s.correct} 题，用时 ${fmtSec(s.duration_sec)}。`,
        '',
        `这一场做错或空着的有 ${wrong.length} 道：`,
      ];

      for (const it of wrong) {
        const no = noOf(it);
        lines.push('', `【第 ${no} 题${it.sub_category ? ` · ${it.sub_category}` : ''}】`, clip(it.content, 900));
        const opts = (it.options || []).map((o) => `${o.key}. ${o.text ?? ''}`).join('\n');
        if (opts) lines.push(opts);
        lines.push(
          `我选：${it.user_answer || '（空着没做）'} / 正确答案：${it.correct_answer} / 本题用时：${fmtSec(it.time_spent_sec)}`,
        );
        if (it.explanation) lines.push(`官方解析：${clip(it.explanation, 500)}`);
        if (draftedSet.has(no)) lines.push('（这题的草稿纸见附图）');
      }

      lines.push('');
      if (draftedNos.length > 0) {
        lines.push(
          `附图是我做题时的草稿纸，按顺序依次是第 ${draftedNos.join('、')} 题。`,
          '每张图里题目、我在题干上的圈划、旁边的演算过程都在一起，能看出我当时是怎么想的。',
        );
      } else {
        lines.push('这几题当时没留草稿纸，只能从答案本身推。');
      }

      lines.push(
        '',
        '请结合草稿纸回答三件事，每条都要落到具体的题和具体的笔迹上，不要讲通用套话：',
        '1. 每道错题我的推理链是怎么走的、从哪一步开始偏的 —— 是审题漏条件、逻辑用错，还是纯算错。',
        '2. 我这几张草稿纸本身有什么坏习惯（条件没抄全、符号乱用、步骤跳太多、排版挤在一起、算完不回头验证等），',
        '   每条都给出下次具体该怎么写。',
        '3. 综合起来我最该先纠的一个做题习惯是什么，给一个下次练习就能执行的检查动作。',
        '',
        '看不清写的是什么就直接说看不清，不要猜。',
      );

      const prompt = lines.join('\n');
      if (images.length > 0) setPendingImages((prev) => [...prev, ...images]);
      setInput((cur) => (cur.trim() ? `${cur.trim()}\n\n${prompt}` : prompt));
      setShowPicker(false);
      stickToBottom.current = true;
      setTimeout(() => taRef.current?.focus(), 0);
    } catch (err) {
      setBanner(`带错题失败：${err.message}`);
    } finally {
      setAttaching(false);
    }
  }, []);

  // ---------- 带上某场真题复盘 ----------
  const loadExamReviews = useCallback(async () => {
    setReviewsLoading(true);
    try {
      const list = await api('/api/exam-analyses');
      setExamReviews((Array.isArray(list) ? list : []).filter((r) => r.status === 'done'));
    } catch (err) {
      setBanner(`拉取复盘记录失败：${err.message}`);
    } finally {
      setReviewsLoading(false);
    }
  }, []);

  const openReviewPicker = useCallback(() => {
    setShowReview(true);
    loadExamReviews();
  }, [loadExamReviews]);

  const attachExamReview = useCallback(async (id) => {
    setAttaching(true);
    setBanner('');
    try {
      const d = await api(`/api/exam-analyses/${id}`);
      const md = d?.result?.markdown;
      if (!md) {
        setBanner('这场复盘还没有生成报告');
        return;
      }
      const st = d.result?.stats || {};
      const prompt = [
        `下面是我 ${d.exam_date || ''} 那场《${d.title}》模考的录屏行为复盘，全程 ${Math.round((d.duration_sec || 0) / 60)} 分钟。`,
        st.questions ? `录屏里识别到 ${st.questions} 道题，其中 ${st.changed || 0} 题改过答案，有 ${st.idle_count || 0} 处明显停滞。` : '',
        '',
        '=== 复盘报告开始 ===',
        md,
        '=== 复盘报告结束 ===',
        '',
        '请基于这份报告跟我深入聊，不要复述报告里已经写过的内容。我想知道：',
        '1. 这些毛病里哪一个对分数的影响最大，为什么。',
        '2. 针对那个毛病，接下来一周我每天该做什么具体训练。',
      ].filter(Boolean).join('\n');
      setInput((cur) => (cur.trim() ? `${cur.trim()}\n\n${prompt}` : prompt));
      setShowReview(false);
      stickToBottom.current = true;
      setTimeout(() => taRef.current?.focus(), 0);
    } catch (err) {
      setBanner(`带复盘失败：${err.message}`);
    } finally {
      setAttaching(false);
    }
  }, []);

  const UPLOAD_ROOT = '/home/ubuntu/ExamSystem/data/uploads';

  const attachUpload = useCallback((file) => {
    const date = file?.date;
    const typ = file?.type || 'pdf';
    const name = file?.name;
    if (!date || !name) return;
    const abs = `${UPLOAD_ROOT}/${date}/${typ}/${name}`;
    const prompt = [
      `复盘这份资料上传的练习卷：${name}`,
      '',
      '绝对路径已经写死，直接打开，禁止 search_files，禁止 ls 其他目录，禁止猜 exam-hermes / exam-system / gongkao_training。',
      abs,
      '',
      '立刻用 python3 + fitz 抽文字，按「你的答案：」「正确答案：」对答案。',
      "先 skill_view('gd-gongkao-coach') 和 skill_view('exam-coaching-gd-provincial')，按里面的三段式逐题复盘。",
      '复盘完用 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py 的 record() 写入 /home/ubuntu/ExamSystem/data/exam.db。',
    ].join('\n');
    setInput((cur) => (cur.trim() ? `${cur.trim()}\n\n${prompt}` : prompt));
    setShowUploads(false);
    stickToBottom.current = true;
    setTimeout(() => taRef.current?.focus(), 0);
  }, []);

  const loadUploads = useCallback(async () => {
    setUploadsLoading(true);
    try {
      const data = await api('/api/uploads');
      const items = [];
      for (const d of data?.dates || []) {
        for (const t of ['pdf', '解析']) {
          for (const f of d[t] || []) {
            items.push({ date: d.date, type: t, name: f.name, size: f.size, mtime: f.mtime });
          }
        }
      }
      items.sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
      setUploadFiles(items.slice(0, 20));
    } catch (err) {
      setBanner(`拉取上传资料失败：${err.message}`);
    } finally {
      setUploadsLoading(false);
    }
  }, []);

  const openUploadPicker = useCallback(() => {
    setShowUploads(true);
    loadUploads();
  }, [loadUploads]);

  // AI 练题交卷后点「让 Hermes 复盘错题」、资料上传点「让 Hermes 复盘」会把上下文递过来
  const seededRef = useRef(null);
  useEffect(() => {
    if (!seed?.nonce) return;
    const key = seed.sessionId
      ? `p:${seed.sessionId}:${seed.nonce}`
      : seed.upload
        ? `u:${seed.upload.date}:${seed.upload.name}:${seed.nonce}`
        : null;
    if (!key || seededRef.current === key) return;
    seededRef.current = key;
    onSeedConsumed?.();
    if (seed.sessionId) attachPractice(seed.sessionId);
    else if (seed.upload) attachUpload(seed.upload);
  }, [seed, attachPractice, attachUpload, onSeedConsumed]);

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  // 收图的公共入口，粘贴和拖拽都走这里；返回是否收到了图片
  const addImageFiles = (fileList) => {
    const files = [...(fileList || [])].filter((f) => f.type.startsWith('image/'));
    if (files.length === 0) return false;
    for (const f of files) {
      if (f.size > IMAGE_MAX_BYTES) {
        setBanner(`图片过大（上限 ${IMAGE_MAX_BYTES / 1024 / 1024}MB）`);
        continue;
      }
      const reader = new FileReader();
      reader.onload = () => {
        setPendingImages((prev) => [
          ...prev,
          { id: uid(), name: f.name || 'pasted.png', dataUrl: String(reader.result) },
        ]);
      };
      reader.readAsDataURL(f);
    }
    return true;
  };

  // 粘贴图片
  const onPaste = (e) => {
    if (addImageFiles(e.clipboardData?.files)) e.preventDefault();
  };

  // 拖入图片。dragover 不 preventDefault 的话不会触发 drop，
  // 浏览器会走默认行为直接打开这张图、把整个页面顶掉
  const onDragOver = (e) => {
    if (![...(e.dataTransfer?.types || [])].includes('Files')) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    setDragOver(true);
  };

  const onDragLeave = (e) => {
    // 在子元素之间移动也会冒 dragleave，只认真正离开容器的那次
    if (e.currentTarget.contains(e.relatedTarget)) return;
    setDragOver(false);
  };

  const onDrop = (e) => {
    if (![...(e.dataTransfer?.types || [])].includes('Files')) return;
    e.preventDefault();
    setDragOver(false);
    if (connState !== 'open') {
      setBanner('还没连上 Hermes，稍等一下再拖');
      return;
    }
    if (!addImageFiles(e.dataTransfer?.files)) setBanner('只认图片文件');
  };

  // 自适应输入框高度
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [input]);

  // 跟随滚动（用户手动上翻时不抢）
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, status]);

  useEffect(() => {
    const sync = () => setOsFs(!!osFullscreenEl());
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    return () => {
      document.removeEventListener('fullscreenchange', sync);
      document.removeEventListener('webkitfullscreenchange', sync);
    };
  }, []);

  const toggleOsFullscreen = () => {
    if (IS_STANDALONE) return;
    if (osFullscreenEl()) {
      exitOsFullscreen().catch(() => {});
      return;
    }
    const enabled = document.fullscreenEnabled || document.webkitFullscreenEnabled;
    if (!enabled) {
      setBanner('iOS Edge 网页关不掉地址栏。请用 Safari 打开本站 → 点分享 → 添加到主屏幕，从桌面图标进就没有顶栏。');
      return;
    }
    requestOsFullscreen().catch(() => {
      setBanner('浏览器拒绝了全屏。请用 Safari 打开 → 分享 → 添加到主屏幕。');
    });
  };

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  const connLabel = {
    idle: '未连接', connecting: '连接中…', open: '已连接', closed: '已断开', error: '连接失败',
  }[connState] || connState;
  const connColor = {
    open: 'bg-[#4caf50]', connecting: 'bg-[#ffa726]', error: 'bg-[#ef5350]', closed: 'bg-[#ef5350]',
  }[connState] || 'bg-[#bbb]';

  return (
    <div className={`flex h-full overflow-hidden ${fullscreen ? 'relative gap-0' : 'gap-4 animate-fadeIn'}`}>
      {/* ── 会话列表 ── */}
      {sidebarOpen && fullscreen && (
        <button
          type="button"
          aria-label="关闭会话列表"
          onClick={() => setSidebarOpen(false)}
          className="absolute inset-0 z-10 bg-black/25"
        />
      )}
      {sidebarOpen && (
        <div className={fullscreen
          ? 'absolute z-20 inset-y-0 left-0 w-72 flex flex-col bg-white border-r border-black/10 shadow-2xl overflow-hidden'
          : 'w-64 shrink-0 flex flex-col rounded-3xl bg-white/70 border border-black/5 overflow-hidden'}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-black/5">
            <span className="text-[10px] font-black uppercase tracking-widest text-[#999]">会话</span>
            <div className="flex items-center space-x-1">
              <button
                onClick={refreshSessions}
                title="刷新列表"
                className="p-1.5 rounded-lg text-[#999] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
              >
                {sessionsLoading
                  ? <Loader2 size={13} className="animate-spin" />
                  : <RefreshCw size={13} />}
              </button>
              <button
                onClick={() => setSidebarOpen(false)}
                title="收起"
                className="p-1.5 rounded-lg text-[#999] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
              >
                <X size={13} />
              </button>
            </div>
          </div>

          <button
            onClick={() => {
              newSession();
              if (fullscreen) setSidebarOpen(false);
            }}
            disabled={busy}
            className="mx-3 mt-3 flex items-center justify-center space-x-2 px-3 py-2.5 rounded-xl bg-[#1a1a1a] text-white font-bold text-xs disabled:opacity-40 hover:opacity-90 transition-opacity"
          >
            <Plus size={14} />
            <span>新建会话</span>
          </button>

          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
            {grouped.length === 0 && !sessionsLoading && (
              <p className="px-1 text-[11px] text-[#bbb] leading-relaxed">
                {connState === 'open' ? '暂无会话' : '连接后显示会话'}
              </p>
            )}
            {grouped.map(({ meta, items }) => {
              const Icon = meta.icon;
              return (
                <div key={meta.label}>
                  <div className="flex items-center space-x-1.5 px-1 mb-1.5">
                    <Icon size={11} className="text-[#bbb]" />
                    <span className="text-[10px] font-black uppercase tracking-widest text-[#bbb]">
                      {meta.label}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {items.map((s) => (
                      <div
                        key={s.id}
                        className={`group relative flex items-center rounded-xl transition-colors ${
                          activeStoredId === s.id
                            ? 'bg-[#1a1a1a] text-white'
                            : 'hover:bg-black/5 text-[#444]'
                        } ${busy ? 'opacity-50 pointer-events-none' : ''}`}
                      >
                        <button
                          onClick={() => {
                            openSession(s);
                            if (fullscreen) setSidebarOpen(false);
                          }}
                          disabled={busy}
                          title={s.title || s.id}
                          className="flex-1 min-w-0 text-left px-2.5 py-2"
                        >
                          <div className="text-xs font-bold truncate pr-5">{s.title || '(无标题)'}</div>
                          <div className={`text-[10px] font-bold ${activeStoredId === s.id ? 'text-white/60' : 'text-[#bbb]'}`}>
                            {s.message_count} 条
                          </div>
                        </button>
                        <button
                          onClick={(e) => deleteSession(e, s.id)}
                          title="删除会话"
                          className={`absolute right-1.5 p-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity ${
                            activeStoredId === s.id
                              ? 'text-white/60 hover:text-white'
                              : 'text-[#bbb] hover:text-[#ef5350]'
                          }`}
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── 对话区 ── */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={`flex-1 flex flex-col overflow-hidden min-w-0 ${
          fullscreen ? 'rounded-none border-0 bg-white' : 'rounded-3xl bg-white/70 border border-black/5'
        }`}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-black/5">
          <div className="flex items-center space-x-2 min-w-0">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-1.5 rounded-lg text-[#999] hover:text-[#1a1a1a] hover:bg-black/5"
                title="会话列表"
              >
                <MessageSquare size={14} />
              </button>
            )}
            {onToggleFullscreen && (
              <button
                onClick={onToggleFullscreen}
                title={fullscreen ? '退出全屏，显示导航' : '全屏阅读'}
                className={`flex items-center space-x-1 px-2 py-1 rounded-lg text-[10px] font-bold transition-colors shrink-0 ${
                  fullscreen ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5 hover:text-[#1a1a1a]'
                }`}
              >
                {fullscreen ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
                <span>{fullscreen ? '退出全屏' : '全屏'}</span>
              </button>
            )}
            {!IS_STANDALONE && (
              <button
                onClick={toggleOsFullscreen}
                title={osFs ? '退出浏览器全屏' : '隐藏浏览器地址栏'}
                className={`flex items-center space-x-1 px-2 py-1 rounded-lg text-[10px] font-bold transition-colors shrink-0 ${
                  osFs ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5 hover:text-[#1a1a1a]'
                }`}
              >
                {osFs ? <Shrink size={11} /> : <Expand size={11} />}
                <span>{osFs ? '退出顶栏' : '隐藏顶栏'}</span>
              </button>
            )}
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${connColor}`} />
            <span className="text-[10px] font-black uppercase tracking-widest text-[#999] shrink-0">
              {connLabel}
            </span>
            {status && (
              <span className="flex items-center space-x-1.5 text-[10px] font-bold text-[#6b5428] truncate">
                <Loader2 size={10} className="animate-spin shrink-0" />
                <span className="truncate">{status}</span>
              </span>
            )}
          </div>

          <div className="flex items-center space-x-1.5 shrink-0 overflow-x-auto [scrollbar-width:none]">
            {headerExtra}
            <QuotaBar />
            <button
              onClick={openPicker}
              disabled={attaching}
              title="带上某次练习的错题和草稿纸"
              className="flex items-center space-x-1 px-2 py-1 rounded-lg text-[10px] font-bold text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors disabled:opacity-40"
            >
              {attaching
                ? <Loader2 size={11} className="animate-spin" />
                : <PenTool size={11} />}
              <span className={fullscreen ? 'hidden' : ''}>错题草稿</span>
            </button>
            <button
              onClick={openUploadPicker}
              disabled={attaching}
              title="带上资料上传里的练习卷"
              className="flex items-center space-x-1 px-2 py-1 rounded-lg text-[10px] font-bold text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors disabled:opacity-40"
            >
              <Upload size={11} />
              <span className={fullscreen ? 'hidden' : ''}>资料上传</span>
            </button>
            <button
              onClick={openReviewPicker}
              disabled={attaching}
              title="带上某场模考的录屏行为复盘"
              className="flex items-center space-x-1 px-2 py-1 rounded-lg text-[10px] font-bold text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors disabled:opacity-40"
            >
              <ScanSearch size={11} />
              <span className={fullscreen ? 'hidden' : ''}>真题复盘</span>
            </button>
            <div className="flex items-center rounded-lg overflow-hidden">
              <button
                onClick={() => setFontScale((v) => FONT_STEPS[Math.max(0, FONT_STEPS.indexOf(v) - 1)])}
                disabled={fontScale === FONT_STEPS[0]}
                title={`缩小正文（现在 ${fontScale}%）`}
                className="px-1.5 py-1 rounded-lg text-[10px] font-black text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-30"
              >
                A-
              </button>
              <button
                onClick={() => setFontScale((v) => FONT_STEPS[Math.min(FONT_STEPS.length - 1, FONT_STEPS.indexOf(v) + 1)])}
                disabled={fontScale === FONT_STEPS[FONT_STEPS.length - 1]}
                title={`放大正文（现在 ${fontScale}%）`}
                className="px-1.5 py-1 rounded-lg text-[12px] font-black text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-30"
              >
                A+
              </button>
            </div>
            <button
              onClick={() => setShowThinking((v) => !v)}
              title="显示/隐藏思考过程"
              className={`flex items-center space-x-1 px-2 py-1 rounded-lg text-[10px] font-bold transition-colors ${
                showThinking ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5'
              }`}
            >
              <Brain size={11} />
              <span className={fullscreen ? 'hidden' : ''}>思考</span>
            </button>
          </div>
        </div>

        {banner && (
          <div className="mx-5 mt-3 px-3 py-2 rounded-xl bg-[#fff4e5] border border-[#ffa726]/30 text-[11px] font-bold text-[#8a5400] flex items-start justify-between">
            <span className="pr-2">{banner}</span>
            <button onClick={() => setBanner('')} className="shrink-0 text-[#8a5400]/60 hover:text-[#8a5400]">
              <X size={12} />
            </button>
          </div>
        )}

        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
          <div className="px-5 py-4 space-y-4" style={{ zoom: fontScale / 100 }}>
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center px-6">
              <div className="w-12 h-12 rounded-2xl bg-[#1a1a1a] flex items-center justify-center text-white mb-3">
                <MessageSquare size={20} />
              </div>
              <p className="text-sm font-black tracking-tight text-[#1a1a1a]">跟 Hermes 聊</p>
              <p className="mt-1.5 text-[11px] text-[#999] leading-relaxed max-w-xs">
                Markdown、代码、LaTeX 公式都能正常显示。左侧可以续接微信上的对话。
              </p>
            </div>
          )}

          {messages.map((m) => (
            <div key={m.id} className={m.role === 'user' ? 'flex justify-end' : ''}>
              {m.role === 'user' ? (
                <div className="max-w-[78%] px-4 py-2.5 rounded-2xl rounded-br-md bg-[#1a1a1a] text-white">
                  {m.images?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {m.images.map((src, i) => (
                        <img key={i} src={src} alt="" className="w-20 h-20 object-cover rounded-lg" />
                      ))}
                    </div>
                  )}
                  <p className="text-[15px] whitespace-pre-wrap break-words leading-relaxed">{m.content}</p>
                </div>
              ) : (
                <div className="max-w-[92%]">
                  <div className="flex items-center space-x-1.5 mb-1.5">
                    <div className="w-4 h-4 rounded-md bg-[#2c261c] flex items-center justify-center text-[9px] font-black text-white">
                      ⚕
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-widest text-[#bbb]">Hermes</span>
                  </div>

                  {showThinking && m.thinking && (
                    <details className="mb-2 rounded-xl bg-black/[0.02] border border-black/5 overflow-hidden">
                      <summary className="px-3 py-1.5 cursor-pointer text-[10px] font-black uppercase tracking-widest text-[#999] hover:bg-black/[0.03]">
                        思考过程
                      </summary>
                      <pre className="px-3 pb-2 text-[11px] text-[#666] whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                        {m.thinking}
                      </pre>
                    </details>
                  )}

                  {m.tools?.map((t) => <ToolCard key={t.tool_id || t.name} tool={t} />)}

                  {(m.content || !m.streaming) && (
                    <MarkdownMessage content={m.content} streaming={m.streaming} />
                  )}
                  {m.streaming && !m.content && (m.tools?.length ?? 0) === 0 && (
                    <div className="flex items-center space-x-2 text-[11px] text-[#999]">
                      <Loader2 size={11} className="animate-spin" />
                      <span>
                        {waitSec >= 90
                          ? `还在等模型，已 ${fmtSec(waitSec)}。上下文很大时可能几分钟才开始吐字`
                          : waitSec >= 15
                            ? `思考中… ${fmtSec(waitSec)}`
                            : '思考中…'}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          </div>
        </div>

        {/* ── 输入区 ── */}
        <div
          className={`px-5 py-3 border-t transition-colors ${
            dragOver ? 'border-[#6b5428] bg-[#2c261c]/10' : 'border-black/5'
          }`}
          style={fullscreen ? { paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' } : undefined}
        >
          {pendingImages.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {pendingImages.map((img) => (
                <div key={img.id} className="relative">
                  <img src={img.dataUrl} alt="" className="w-14 h-14 object-cover rounded-lg border border-black/10" />
                  <button
                    onClick={() => setPendingImages((prev) => prev.filter((p) => p.id !== img.id))}
                    className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-[#1a1a1a] text-white flex items-center justify-center"
                  >
                    <X size={9} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-end space-x-2">
            <textarea
              ref={taRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              onPaste={onPaste}
              rows={1}
              placeholder={connState === 'open'
                ? (dragOver ? '松手就把图片放进来' : 'Enter 发送，Shift+Enter 换行，图片可粘贴或拖入')
                : '连接中…先写，连上了再发'}
              className="flex-1 px-4 py-3 rounded-2xl bg-white border border-black/10 text-[15px] resize-none outline-none focus:border-[#6b5428] transition-colors"
            />
            {busy ? (
              <button
                onClick={interrupt}
                title="停止生成"
                className="p-3 rounded-2xl bg-[#ef5350] text-white hover:opacity-90 transition-opacity shrink-0"
              >
                <Square size={18} />
              </button>
            ) : (
              <button
                onClick={send}
                disabled={connState !== 'open' || (!input.trim() && pendingImages.length === 0)}
                title="发送"
                className="p-3 rounded-2xl bg-[#1a1a1a] text-white disabled:opacity-30 hover:opacity-90 transition-opacity shrink-0"
              >
                <Send size={18} />
              </button>
            )}
          </div>

          {!fullscreen && (
            <p className="mt-1.5 px-1 text-[10px] text-[#ccc] flex items-center space-x-1">
              <ImageIcon size={9} />
              <span>Hermes 拥有终端与文件权限，请谨慎发送指令</span>
            </p>
          )}
        </div>
      </div>
      {/* 练习记录选择器。portal 到 body：外层 <main> 带 backdrop-blur，
          在它内部写 fixed inset-0 只能铺满 main、铺不满屏幕 */}
      {showReview && createPortal(
        <div className="fixed inset-0 z-[9998] flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setShowReview(false)}
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
          />
          <div className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl bg-white shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
              <div className="flex items-center space-x-2">
                <ScanSearch size={15} className="text-[#6b5428]" />
                <span className="text-xs font-black uppercase tracking-widest text-[#1a1a1a]">
                  挑一场模考复盘
                </span>
              </div>
              <button
                onClick={() => setShowReview(false)}
                className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {reviewsLoading && examReviews.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb]">加载中…</p>
              )}
              {!reviewsLoading && examReviews.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb] leading-relaxed">
                  还没有处理完的复盘。<br />去「真题复盘」传一场模考的录屏和答案 PDF。
                </p>
              )}
              {examReviews.map((r) => (
                <button
                  key={r.id}
                  onClick={() => attachExamReview(r.id)}
                  disabled={attaching}
                  className="w-full text-left px-3.5 py-3 rounded-2xl bg-[#faf9f6] hover:bg-[#1a1a1a] hover:text-white transition-colors group disabled:opacity-50"
                >
                  <div className="text-xs font-black italic truncate">{r.title}</div>
                  <div className="text-[10px] font-bold text-[#bbb] group-hover:text-white/50 mt-0.5">
                    {r.exam_date} · {Math.round((r.duration_sec || 0) / 60)} 分钟
                    {r.stats?.questions ? ` · ${r.stats.questions} 题` : ''}
                  </div>
                </button>
              ))}
            </div>
            <div className="px-5 py-3 border-t border-black/5">
              <p className="text-[10px] font-bold text-[#bbb] leading-relaxed">
                会把整份复盘报告装进输入框，你可以再补一句想问的再发。
              </p>
            </div>
          </div>
        </div>,
        document.body,
      )}

      {showUploads && createPortal(
        <div className="fixed inset-0 z-[9998] flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setShowUploads(false)}
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
          />
          <div className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl bg-white shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
              <div className="flex items-center space-x-2">
                <Upload size={15} className="text-[#6b5428]" />
                <span className="text-xs font-black uppercase tracking-widest text-[#1a1a1a]">
                  挑一份上传资料复盘
                </span>
              </div>
              <button
                onClick={() => setShowUploads(false)}
                className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {uploadsLoading && uploadFiles.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb]">加载中…</p>
              )}
              {!uploadsLoading && uploadFiles.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb] leading-relaxed">
                  还没有上传资料。<br />去「资料上传」丢一份练习 PDF。
                </p>
              )}
              {uploadFiles.map((f) => (
                <button
                  key={`${f.date}/${f.type}/${f.name}`}
                  onClick={() => attachUpload(f)}
                  className="w-full text-left px-3.5 py-3 rounded-2xl bg-[#faf9f6] hover:bg-[#1a1a1a] hover:text-white transition-colors group"
                >
                  <div className="text-xs font-black italic truncate">{f.name}</div>
                  <div className="text-[10px] font-bold text-[#bbb] group-hover:text-white/50 mt-0.5">
                    {f.date} · {f.type}
                  </div>
                </button>
              ))}
            </div>
            <div className="px-5 py-3 border-t border-black/5">
              <p className="text-[10px] font-bold text-[#bbb] leading-relaxed">
                会把这份文件的绝对路径装进输入框，Hermes 直接打开，不再满盘搜索。
              </p>
            </div>
          </div>
        </div>,
        document.body,
      )}

      {showPicker && createPortal(
        <div className="fixed inset-0 z-[9998] flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setShowPicker(false)}
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
          />
          <div className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl bg-white shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
              <div className="flex items-center space-x-2">
                <Target size={15} className="text-[#6b5428]" />
                <span className="text-xs font-black uppercase tracking-widest text-[#1a1a1a]">
                  挑一场练习来复盘
                </span>
              </div>
              <div className="flex items-center space-x-1">
                <button
                  onClick={loadPracticeRuns}
                  title="刷新"
                  className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
                >
                  {runsLoading
                    ? <Loader2 size={13} className="animate-spin" />
                    : <RefreshCw size={13} />}
                </button>
                <button
                  onClick={() => setShowPicker(false)}
                  className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {runsLoading && practiceRuns.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb]">加载中…</p>
              )}
              {!runsLoading && practiceRuns.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb] leading-relaxed">
                  还没有交过卷的练习。<br />去「AI 练题」做一套并交卷，草稿纸会自动存下来。
                </p>
              )}
              {practiceRuns.map((r) => (
                <button
                  key={r.id}
                  onClick={() => attachPractice(r.id)}
                  disabled={attaching}
                  className="w-full text-left px-4 py-3 rounded-2xl border border-black/5 hover:border-[#6b5428] hover:bg-[#f4e6c8] transition-colors flex items-center gap-3 disabled:opacity-50"
                >
                  <span className="flex-1 min-w-0">
                    <span className="block text-xs font-black truncate">{r.category || '未命名批次'}</span>
                    <span className="block text-[10px] font-bold text-[#bbb] mt-0.5">
                      对 {r.correct}/{r.total} · 错 {r.wrong_count} · 用时 {fmtSec(r.duration_sec)}
                      {r.draft_count > 0 && ` · ${r.draft_count} 张草稿`}
                    </span>
                  </span>
                  <ChevronRight size={14} className="shrink-0 text-[#ccc]" />
                </button>
              ))}
            </div>

            <p className="px-5 py-3 border-t border-black/5 text-[10px] font-bold text-[#ccc] leading-relaxed">
              会把错题明细和最多 {MAX_DRAFT_ATTACH} 张草稿纸装进输入框，你可以再补一句话再发。
            </p>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
};

export default HermesChat;

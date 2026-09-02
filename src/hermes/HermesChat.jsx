// Hermes 对话页
//
// 走 JSON-RPC over WebSocket 直连 Hermes 的 gateway（经 Express 代理），
// 与官方 dashboard 的 Chat 用的是同一套协议和同一个 agent，
// 因此这里能看到并续接微信、cron、CLI 的全部会话。
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Send, Square, MessageSquare, Loader2, Brain, X, Image as ImageIcon,
  ScanSearch, Upload, Maximize2, Minimize2, Expand, Shrink, FileText, Mic,
  PictureInPicture2, Check,
} from 'lucide-react';

import { api } from '../api.js';
import HermesGateway from './gateway.js';
import MarkdownMessage from './MarkdownMessage.jsx';
import ToolCard from './ToolCard.jsx';
import { getToolActivity } from './toolActivity.js';
import QuotaBar from './QuotaBar.jsx';
import HermesSidebar from './HermesSidebar.jsx';
import HermesContextPickers from './HermesContextPickers.jsx';
import ReviewFloater from './ReviewFloater.jsx';
import {
  appendAssistantDelta as appendAssistantDeltaState,
  ensureStreamingAssistant,
  eventText,
  extractReview,
  finishAssistantMessage,
  isSystemInjectedNotice,
  normalizeHermesHistory,
} from './hermesProtocol.js';
import { buildExamReviewLead, buildPracticeReviewLead } from './reviewSpec.js';

let msgSeq = 0;
const uid = () => `m${++msgSeq}`;

const IMAGE_MAX_BYTES = 10 * 1024 * 1024;
const AUDIO_MAX_BYTES = 200 * 1024 * 1024;

const pickRecorderMime = () => {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return '';
  return [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/aac',
    'audio/ogg;codecs=opus',
  ].find((t) => MediaRecorder.isTypeSupported(t)) || '';
};

const extFromAudioMime = (mime) => {
  const t = String(mime || '').toLowerCase();
  if (t.includes('mp4') || t.includes('m4a') || t.includes('aac')) return 'm4a';
  if (t.includes('ogg') || t.includes('opus')) return 'ogg';
  if (t.includes('wav')) return 'wav';
  if (t.includes('mpeg') || t.includes('mp3')) return 'mp3';
  return 'webm';
};

const normalizeAudioDataUrl = (dataUrl) =>
  String(dataUrl || '').replace(/^data:audio\/([^;,]+)[^,]*,/, 'data:audio/$1;base64,');

// cron / 微信会话虽然不展示，仍会占 session.list 的返回名额；多取一些，
// 避免自动会话把较早的本地对话挤出侧栏。
const SESSION_LIST_LIMIT = 200;

// 上次的会话列表缓存。进页面时先用它把左栏渲染出来，等 WS 连上再静默替换成新数据，
// 这样首屏不用干等「握手 + DB 查询」。sessionStorage 而不是 localStorage：
// 关掉标签页就失效，避免长期拿着过期列表。
const SESSION_CACHE_KEY = 'hermes.sessions.v1';
const ACTIVE_SESSION_KEY = 'hermes.activeSession.v1';

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

const readCachedActiveSession = () => {
  try { return sessionStorage.getItem(ACTIVE_SESSION_KEY) || null; }
  catch { return null; }
};

const writeCachedActiveSession = (id) => {
  try {
    if (id == null) sessionStorage.removeItem(ACTIVE_SESSION_KEY);
    else sessionStorage.setItem(ACTIVE_SESSION_KEY, String(id));
  } catch { /* session recovery remains best-effort */ }
};

// 一次最多带几张草稿纸。每张 PNG 转成 base64 有 300KB~1MB，
// 带太多会把 prompt 撑爆，也会让模型的注意力散掉。

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

const fmtAudioLen = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  if (s < 60) return `${s}秒`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m}分${r}秒` : `${m}分钟`;
};

const parseAudioLen = (text) => {
  const s = String(text || '').trim().replace(/^[（(]|[）)]$/g, '');
  const m = s.match(/^(?:语音\s*)?(\d+)\s*秒$/) || s.match(/^(\d+)\s*s$/i);
  if (m) return Number(m[1]);
  const mm = s.match(/^(?:语音\s*)?(\d+)\s*分钟$/);
  if (mm) return Number(mm[1]) * 60;
  const mix = s.match(/^(?:语音\s*)?(\d+)\s*分(\d+)\s*秒$/);
  if (mix) return Number(mix[1]) * 60 + Number(mix[2]);
  return null;
};

const isAudioLabel = (text) => {
  const s = String(text || '').trim();
  return s === '语音' || s === '（语音口述）' || parseAudioLen(s) != null;
};

const fmtVoiceQuote = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  if (s <= 0) return '语音';
  if (s < 60) return `${s}"`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m}'${r}"` : `${m}'`;
};

const RecWave = ({ stream }) => {
  const [levels, setLevels] = useState(() => Array.from({ length: 20 }, () => 5));
  useEffect(() => {
    if (!stream) return undefined;
    let raf = 0;
    let ac;
    let fake;
    const n = 20;
    const paintFake = () => {
      fake = window.setInterval(() => {
        const t = Date.now() / 130;
        setLevels(Array.from({ length: n }, (_, i) => 5 + Math.abs(Math.sin(t + i * 0.42)) * 13));
      }, 80);
    };
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) throw new Error('no AudioContext');
      ac = new AC();
      const src = ac.createMediaStreamSource(stream);
      const an = ac.createAnalyser();
      an.fftSize = 64;
      an.smoothingTimeConstant = 0.5;
      src.connect(an);
      const data = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        an.getByteFrequencyData(data);
        setLevels(Array.from({ length: n }, (_, i) => 4 + ((data[2 + i] || 0) / 255) * 16));
        raf = requestAnimationFrame(tick);
      };
      if (ac.state === 'suspended' && ac.resume) ac.resume().then(tick, tick);
      else tick();
    } catch {
      paintFake();
    }
    return () => {
      cancelAnimationFrame(raf);
      if (fake) window.clearInterval(fake);
      ac?.close?.();
    };
  }, [stream]);
  return (
    <span className="flex items-end gap-[2px] h-[18px]" aria-hidden="true">
      {levels.map((h, i) => (
        <span key={i} className="w-[2px] rounded-full bg-current" style={{ height: `${h}px` }} />
      ))}
    </span>
  );
};

const VoiceWaves = ({ playing }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden className={playing ? 'voice-playing' : ''}>
    <path d="M10.6 6a2.2 2.2 0 0 0 0 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M8.2 4.5a4.2 4.2 0 0 0 0 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M5.8 3a6.2 6.2 0 0 0 0 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <circle cx="13.1" cy="8" r="1.15" fill="currentColor" />
  </svg>
);

const VoiceBubble = ({ src, sec = 0, onDuration }) => {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const width = 78 + Math.min(Math.max(Number(sec) || 1, 1), 60) * 2.1;

  const toggle = () => {
    const el = audioRef.current;
    if (!el || !src) return;
    if (playing) {
      el.pause();
      return;
    }
    document.querySelectorAll('audio[data-voice]').forEach((a) => {
      if (a !== el) a.pause();
    });
    el.play().catch(() => {});
  };

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={!src}
      title={src ? (playing ? '暂停' : '播放') : '录音已不在本地'}
      className="relative flex items-center justify-end gap-1.5 h-10 pr-3.5 pl-4 mr-1.5 rounded-[10px] bg-[#1a1a1a] text-[#f7efe0] disabled:opacity-90"
      style={{ width }}
    >
      <span className="text-[15px] tabular-nums leading-none">{fmtVoiceQuote(sec)}</span>
      <VoiceWaves playing={playing} />
      <span className="absolute -right-[5px] top-1/2 -mt-[5px] w-0 h-0 border-y-[5px] border-y-transparent border-l-[6px] border-l-[#1a1a1a]" />
      {src ? (
        <audio
          ref={audioRef}
          data-voice=""
          src={src}
          className="hidden"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onLoadedMetadata={(e) => {
            const d = e.currentTarget.duration;
            if (!(sec > 0) && Number.isFinite(d) && d > 0) onDuration?.(Math.round(d));
          }}
        />
      ) : null}
    </button>
  );
};

const fmtDateTime = (raw) => {
  if (!raw) return '';
  const date = new Date(String(raw).includes('T') ? raw : `${String(raw).replace(' ', 'T')}Z`);
  if (Number.isNaN(date.getTime())) return String(raw);
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  });
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

const ReviewChip = ({ review, onOpen, onRemove, dark }) => (
  <div className={`inline-flex items-center gap-2 pl-2.5 pr-1.5 py-1.5 rounded-xl border max-w-full ${
    dark ? 'bg-white/10 border-white/20 text-white' : 'bg-[#f4f0e6] border-[#e8d5b0] text-[#1a1a1a]'
  }`}>
    <button type="button" onClick={() => onOpen(review)} className="inline-flex items-center gap-1.5 min-w-0">
      <FileText size={12} className={`shrink-0 ${dark ? 'text-[#e8d5b0]' : 'text-[#6b5428]'}`} />
      <span className="text-[11px] font-black truncate max-w-[280px]">{review.label || review.name || review.title}</span>
    </button>
    {onRemove ? (
      <button
        type="button"
        onClick={onRemove}
        className="w-4 h-4 rounded-full bg-[#1a1a1a] text-white flex items-center justify-center shrink-0"
      >
        <X size={9} />
      </button>
    ) : null}
  </div>
);

const HermesChat = ({ seed, onSeedConsumed, active = true, fullscreen = false, onToggleFullscreen, headerExtra }) => {
  const gwRef = useRef(null);
  const hermesContextRef = useRef(null);
  const hermesContextPromiseRef = useRef(null);
  const [connState, setConnState] = useState('idle');
  const [sessions, setSessions] = useState(() => readCachedSessions());
  const [sessionsLoading, setSessionsLoading] = useState(false);
  // sid 是 gateway 的活动会话 id（session.create/resume 返回），与列表里的存档 id 不同
  const [sid, setSid] = useState(null);
  const [activeStoredId, setActiveStoredId] = useState(() => readCachedActiveSession());
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [banner, setBanner] = useState('');
  const [showThinking, setShowThinking] = useState(false);
  const [pendingImages, setPendingImages] = useState([]);
  const [pendingAudio, setPendingAudio] = useState(null);
  const [popout, setPopout] = useState(null);
  const [recording, setRecording] = useState(false);
  const [recordSec, setRecordSec] = useState(0);
  const [recStream, setRecStream] = useState(null);
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
  const [pendingReview, setPendingReview] = useState(null);
  const [reviewPreview, setReviewPreview] = useState(null);
  const [reviewMd, setReviewMd] = useState('');
  const [reviewMdErr, setReviewMdErr] = useState('');
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

  const openReviewPreview = useCallback((review) => {
    setReviewMd('');
    setReviewMdErr('');
    setReviewPreview(review);
  }, []);

  const closeReviewPreview = useCallback(() => {
    setReviewPreview(null);
    setReviewMd('');
    setReviewMdErr('');
  }, []);

  useEffect(() => {
    if (!reviewPreview?.id) return undefined;
    let cancelled = false;
    const practice = reviewPreview.kind === 'practice';
    const url = practice
      ? `/api/practice/sessions/${reviewPreview.id}/md`
      : `/api/exam-analyses/${reviewPreview.id}`;
    api(url)
      .then((row) => {
        const markdown = practice ? row?.markdown : row?.result?.markdown;
        if (!cancelled) setReviewMd(markdown || '');
      })
      .catch((err) => {
        if (!cancelled) setReviewMdErr(err.message || 'failed');
      });
    return () => { cancelled = true; };
  }, [reviewPreview]);

  const loadHermesContext = useCallback(() => {
    if (hermesContextRef.current) return Promise.resolve(hermesContextRef.current);
    if (!hermesContextPromiseRef.current) {
      hermesContextPromiseRef.current = api('/api/hermes/context').then((context) => {
        hermesContextRef.current = context;
        return context;
      }).finally(() => {
        hermesContextPromiseRef.current = null;
      });
    }
    return hermesContextPromiseRef.current;
  }, []);

  const sessionCreateParams = useCallback(async () => {
    try {
      const context = await loadHermesContext();
      return { cols: 100, ...(context?.project_root ? { cwd: context.project_root } : {}) };
    } catch {
      return { cols: 100 };
    }
  }, [loadHermesContext]);

  useEffect(() => {
    loadHermesContext().catch(() => {});
  }, [loadHermesContext]);
  useEffect(() => {
    try { localStorage.setItem(FONT_KEY, String(fontScale)); }
    catch { /* 隐私模式 */ }
  }, [fontScale]);
  // busy 是 state，setBusy 要等下一次渲染才拦得住第二次点击。
  // 图片上传是 await，中间那几秒只能靠同步的 ref 挡住连点
  const sendingRef = useRef(false);
  const recRef = useRef(null);
  const recChunksRef = useRef([]);
  const recDiscardRef = useRef(false);
  const recFinalizingRef = useRef(false);
  const recStreamRef = useRef(null);
  const recTickRef = useRef(null);
  const recStartedAtRef = useRef(0);
  const audioPickRef = useRef(null);
  // 用来区分「第一次连上」和「断线重连」。重连后必须再 resume，
  // 否则 Hermes 的事件还绑在已经死掉的那条 WS 上，界面就会一直「思考中」。
  const openedOnceRef = useRef(false);
  const [, setWaitSec] = useState(0);

  // ---------- 消息辅助 ----------
  const appendAssistantDelta = useCallback((text) => {
    setMessages((prev) => appendAssistantDeltaState(prev, text, uid));
  }, []);

  const rememberSession = useCallback((res, storedId = res?.stored_session_id || null) => {
    const liveId = res?.session_id || null;
    sidRef.current = liveId;
    setSid(liveId);
    activeStoredIdRef.current = storedId;
    setActiveStoredId(storedId);
    writeCachedActiveSession(storedId);
    return liveId;
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
    setMessages((prev) => finishAssistantMessage(prev, finalText, uid));
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
        setWaitSec(0);
        setBusy(true);
        setStatus('(｡•̀ᴗ-)✧ 整理一下');
        setMessages((prev) => ensureStreamingAssistant(prev, uid));
      }),
      gw.on('message.complete', (ev) => finishStreaming(eventText(ev))),

      gw.on('tool.start', (ev) => {
        const p = ev.payload || {};
        upsertTool({
          tool_id: p.tool_id, name: p.name || 'tool', args: p.args,
          args_text: p.args_text, preview: p.preview, done: false,
        });
        const activity = getToolActivity(p.name);
        setStatus(`${activity.emoji} ${activity.label}`);
      }),
      gw.on('tool.complete', (ev) => {
        const p = ev.payload || {};
        upsertTool({
          tool_id: p.tool_id, name: p.name || 'tool', args: p.args,
          result: p.result, duration_s: p.duration_s, done: true,
        });
        setStatus('(｡•̀ᴗ-)✧ 整理一下');
      }),

      gw.on('status.update', (ev) => {
        const s = ev.payload?.text || ev.payload?.status;
        if (s) setStatus(String(s));
      }),

      gw.on('error', (ev) => {
        const msg = ev.payload?.message || '未知错误';
        setBanner(msg);
        setWaitSec(0);
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
      // 空的新会话还没有首条消息，Hermes 尚未写入 DB；关闭后删除会返回
      // "session not found"，但对用户来说它已经成功从活动列表移除了。
      await gw.request('session.delete', { session_id: sessionId }).catch((err) => {
        if (!/session not found/i.test(err?.message || '')) throw err;
      });
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeStoredIdRef.current === sessionId) {
        activeStoredIdRef.current = null;
        setActiveStoredId(null);
        writeCachedActiveSession(null);
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

  const applyResume = useCallback((res, storedId) => {
    rememberSession(res, storedId || res.stored_session_id || null);
    const hydrated = normalizeHermesHistory(res.messages, {
      nextId: uid,
      parseAudioLen,
      isAudioLabel,
    });
    const lastHydratedUser = [...hydrated].reverse().find((m) => m.role === 'user');
    const inflightCandidate = String(res.inflight?.user || '').trim();
    const inflightRaw = isSystemInjectedNotice(inflightCandidate) ? '' : inflightCandidate;
    const inflightUser = inflightRaw ? extractReview(inflightRaw) : null;

    // A running turn lives in inflight until completion. Restore both its visible
    // text and attachment metadata; review-only messages legitimately have no text.
    setMessages((prev) => {
      const lastLocalUser = [...prev].reverse().find((m) => m.role === 'user');
      const localPending = lastLocalUser
        && (lastLocalUser.content !== lastHydratedUser?.content
          || lastLocalUser.review?.id !== lastHydratedUser?.review?.id);
      const pendingContent = inflightUser?.content ?? (localPending ? lastLocalUser.content : '');
      const pendingReview = inflightUser?.review ?? (localPending ? lastLocalUser.review : null);
      const alreadyHydrated = pendingContent === lastHydratedUser?.content
        && pendingReview?.id === lastHydratedUser?.review?.id;
      const next = hydrated.map((m, i) => {
        const old = prev[i];
        return old && old.role === m.role ? { ...m, id: old.id } : m;
      });
      if ((pendingContent || pendingReview) && !alreadyHydrated) {
        next.push({
          id: lastLocalUser?.id || uid(),
          role: 'user',
          content: pendingContent,
          streaming: false, tools: [], thinking: '',
          images: lastLocalUser?.images || [],
          audio: lastLocalUser?.audio || null,
          audioSec: lastLocalUser?.audioSec ?? parseAudioLen(pendingContent),
          hadAudio: lastLocalUser?.hadAudio || isAudioLabel(pendingContent),
          review: pendingReview,
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
      setWaitSec(0);
      setBusy(true);
      setStatus('生成中');
    } else {
      setBusy(false);
      setStatus('');
    }
    stickToBottom.current = true;
  }, [rememberSession]);

  // WS 断过再连上：必须把当前存档 resume 回去，事件才会重新绑到这条连接。
  // 第一次 open 由上面的 connect() 处理，这里只接重连。
  useEffect(() => {
    if (connState !== 'open') return;
    const gw = gwRef.current;
    if (!gw) return;

    if (!openedOnceRef.current) {
      openedOnceRef.current = true;
      const cachedActive = readCachedActiveSession();
      if (!cachedActive) return;
      gw.request('session.resume', { session_id: cachedActive, cols: 100 })
        .then((res) => applyResume(res, cachedActive))
        .catch(() => writeCachedActiveSession(null));
      return;
    }

    const stored = activeStoredIdRef.current;
    if (!stored) return;
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
      if (recRef.current && recRef.current.state !== 'inactive') recRef.current.stop();
      recRef.current = null;
      setRecording(false);
      const res = await gw.request('session.create', await sessionCreateParams());
      rememberSession(res);
      setMessages([]);
      setPendingImages([]);
      setPendingAudio(null);
      setPendingReview(null);
      setPopout(null);
      // 新建后立刻刷新列表，让左栏出现这条新会话
      try {
        const listRes = await gw.request('session.list', {});
        const list = Array.isArray(listRes?.sessions) ? listRes.sessions : [];
        setSessions(list);
        writeCachedSessions(list);
      } catch { /* 列表刷新失败不影响对话 */ }
    } catch (err) {
      setBanner(`新建会话失败：${err.message}`);
    }
  }, [busy, rememberSession, sessionCreateParams]);

  const stopTracks = () => {
    const stream = recStreamRef.current;
    recStreamRef.current = null;
    setRecStream(null);
    stream?.getTracks().forEach((t) => t.stop());
    if (recTickRef.current) {
      clearInterval(recTickRef.current);
      recTickRef.current = null;
    }
  };

  const stopRecording = useCallback((discard = false) => {
    recDiscardRef.current = Boolean(discard);
    const rec = recRef.current;
    if (rec && rec.state !== 'inactive') {
      recFinalizingRef.current = !discard;
      try { rec.requestData(); } catch { /* Safari 以外可能没有 */ }
      rec.stop();
    } else {
      recFinalizingRef.current = false;
    }
    recRef.current = null;
    setRecording(false);
  }, []);

  const cancelRecording = useCallback(() => stopRecording(true), [stopRecording]);

  const ingestAudioBlob = useCallback((blob, mime, name, knownSec) => {
    if (blob.size < 800) {
      recFinalizingRef.current = false;
      setBanner('录音太短，再试一次');
      return;
    }
    if (blob.size > AUDIO_MAX_BYTES) {
      recFinalizingRef.current = false;
      setBanner(`录音过大（上限 ${AUDIO_MAX_BYTES / 1024 / 1024}MB，请分段发）`);
      return;
    }
    const ext = extFromAudioMime(mime) || extFromAudioMime(name) || 'webm';
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = normalizeAudioDataUrl(String(reader.result));
      const apply = (sec) => {
        setPendingAudio({
          id: uid(),
          dataUrl,
          mime: mime || `audio/${ext}`,
          name: name || `voice.${ext}`,
          sec: sec > 0 ? Math.round(sec) : null,
        });
        recFinalizingRef.current = false;
      };
      if (knownSec > 0) {
        apply(knownSec);
        return;
      }
      const probe = new Audio(dataUrl);
      probe.onloadedmetadata = () => apply(probe.duration);
      probe.onerror = () => apply(0);
    };
    reader.onerror = () => {
      recFinalizingRef.current = false;
      setBanner('读取录音失败，请重试');
    };
    reader.readAsDataURL(blob);
  }, []);

  const pickAudioFile = useCallback(() => {
    audioPickRef.current?.click();
  }, []);

  const startRecording = useCallback(async () => {
    if (recording || busy || sendingRef.current) return;
    const canLive = Boolean(navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined');
    if (!canLive) {
      if (typeof window !== 'undefined' && !window.isSecureContext) {
        const httpsUrl = `https://${location.host}${location.pathname}${location.search}`;
        setBanner(
          <>
            当前是 HTTP，浏览器不允许网页开麦。
            <a href={httpsUrl} className="underline mx-1">改用 HTTPS 打开</a>
            就能直接说；也可以先选一段录音文件。
          </>,
        );
      } else {
        setBanner('这个环境不能直接开麦，请选择一段录音文件');
      }
      pickAudioFile();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recStreamRef.current = stream;
      setRecStream(stream);
      recChunksRef.current = [];
      const mime = pickRecorderMime();
      let rec;
      try {
        rec = new MediaRecorder(stream, {
          ...(mime ? { mimeType: mime } : {}),
          audioBitsPerSecond: 32000,
        });
      } catch {
        rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      }
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size) recChunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const discard = recDiscardRef.current;
        recDiscardRef.current = false;
        stopTracks();
        const blob = new Blob(recChunksRef.current, { type: rec.mimeType || 'audio/webm' });
        recChunksRef.current = [];
        if (discard) {
          recFinalizingRef.current = false;
          return;
        }
        const elapsed = recStartedAtRef.current
          ? (Date.now() - recStartedAtRef.current) / 1000
          : 0;
        ingestAudioBlob(blob, rec.mimeType || 'audio/webm', `voice.${extFromAudioMime(rec.mimeType)}`, elapsed);
      };
      try {
        rec.start(250);
      } catch {
        rec.start();
      }
      recRef.current = rec;
      recStartedAtRef.current = Date.now();
      recDiscardRef.current = false;
      recFinalizingRef.current = false;
      setPendingAudio(null);
      setRecordSec(0);
      setRecording(true);
      setBanner('');
      const t0 = Date.now();
      recTickRef.current = setInterval(() => {
        setRecordSec(Math.floor((Date.now() - t0) / 1000));
      }, 250);
    } catch (err) {
      stopTracks();
      setRecording(false);
      setBanner(/denied|NotAllowed|Permission/i.test(err?.message || '')
        ? '没有麦克风权限'
        : `录音失败：${err.message || err}`);
    }
  }, [busy, recording, ingestAudioBlob, pickAudioFile]);

  useEffect(() => () => {
    if (recRef.current && recRef.current.state !== 'inactive') recRef.current.stop();
    stopTracks();
  }, []);

  // ---------- 发送 ----------
  const send = useCallback(async () => {
    const gw = gwRef.current;
    if (recording || recFinalizingRef.current) return;
    const typed = input.trim();
    const audio = pendingAudio;
    const text = typed;
    if (!gw || busy || sendingRef.current) return;
    if (!text && pendingImages.length === 0 && !pendingReview && !audio) return;
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
    const review = pendingReview;
    const examScoreLine = review?.grade
      ? `本场分数只认 PDF 判分：共 ${review.grade.total} 题，对 ${review.grade.correct}，错 ${review.grade.wrong}，空 ${review.grade.blank || 0}。禁止改成别的分数，禁止用录屏勾选重算。`
      : '对错和分数只认报告开头「判分（只认本表，来自答案 PDF）」那张表。禁止用录屏勾选、报告里的「差距」或自己心算改分数。';
    const examReviewLead = review ? buildExamReviewLead(review, examScoreLine) : '';
    const practiceReviewLead = review ? buildPracticeReviewLead(review) : '';
    const reviewLead = review?.kind === 'practice' ? practiceReviewLead : examReviewLead;
    const voiceLead = audio
      ? '下面附了我的口述录音，请直接听，不要让我改成文字。'
      : '';
    const audioLabel = audio
      ? (audio.sec > 0 ? fmtAudioLen(audio.sec) : '语音')
      : '';
    const persistText = text || audioLabel;
    const submittedText = review || persistText
      ? `[USER_MESSAGE]\n${persistText}\n[/USER_MESSAGE]`
      : '';

    const projectRoot = hermesContextRef.current?.project_root || '/home/ubuntu/ExamSystem';
    const masteryNudge = review?.kind === 'practice' && review?.profileReviewed
      ? [
          'Keep all mastery/profile bookkeeping completely silent and internal. Never mention commands, database writes, tool output, mastery scores, confidence, sample counts, or bookkeeping summaries in the final answer unless I explicitly ask for statistics.',
          `本场 AI 练题（practice_sessions.id=${review.id}）画像已封印。禁止调用 kaodian_profile.py，禁止写入 kaodian_profile / kaodian_events，禁止改 questions.tags。本轮只做分析。`,
        ].join('\n')
      : review?.kind === 'practice'
      ? [
          'Keep all mastery/profile bookkeeping completely silent and internal. Never mention commands, database writes, tool output, mastery scores, confidence, sample counts, or bookkeeping summaries in the final answer unless I explicitly ask for statistics.',
          `交卷只存了选项、用时和草稿，没有写画像。本场（practice_sessions.id=${review.id}）只有这一次第一次 Hermes 复盘可以更新画像；写完立刻封印，之后同一场永远不再写。`,
          '画像记的是「会不会」，不是「选项对不对」。先结合 Markdown 报告、本题用时、本场慢题参考线、草稿纸实图做诊断，再逐题写入。空题先跳过。',
          '判定（每题只记一条，--item 必须用报告里的题目id/数据库id，禁止用卷面 01/02）：',
          '- 空题/未作答：不 record。没做完不等于不会。',
          '- 选项对，且草稿/过程能看出对应考点的关键步骤：1 --weight 1',
          '- 选项对，但无草稿、乱画、过程对不上，或明显蒙对：0 --weight 1。对选项不等于掌握。',
          '- 选项错：0 --weight 1。若过程整体对、只是最后算错或填错选项：1 --weight 0.5（会做但不稳）。',
          '- 选项对，但用时达到或超过本场慢题参考线，或方法明显绕远：1 --weight 0.7',
          '- 证据不足、无法判断会不会：跳过，不要猜掌握度。',
          '考点默认用该题 tags[0] /「本题考察知识点」的 模块-一级-二级。禁止 --mastery。禁止改 questions.tags。只有原标签明显标错才先 --register 再 --record。elapsed_ms = 报告本题用时秒 × 1000。',
          `python3 ${projectRoot}/scripts/kaodian_profile.py --record '模块-一级-二级' '模块' '一级' 1 60000 hermes --weight 1 --practice-id ${review.id} --item 题目id`,
          '命令打印 already recorded / already sealed 就跳过该题，禁止换标签再记一次。',
          `全部应写题目写完后立刻执行：python3 ${projectRoot}/scripts/kaodian_profile.py --seal-practice ${review.id}`,
          '封印后本场禁止再 record。',
        ].join('\n')
      : review?.kind === 'exam'

      ? [
          'This is a screen-recording / mock-exam review. Unlike AI Practice review, you MUST write the learner profile once. Video analysis itself does not write anything.',
          'Keep all mastery/profile bookkeeping completely silent and internal. Never mention commands, database writes, tool output, mastery scores, confidence, sample counts, or bookkeeping summaries in the final answer unless I explicitly ask for statistics.',
          '对每一道能判断对错的题立刻写入，不要等提醒。必须带场次和题号，来源用 exam：',
          `python3 ${projectRoot}/scripts/kaodian_profile.py --record '模块-一级-二级' '模块' '一级' 1 60000 exam --exam-id ${review.id} --item 题号`,
          '做对填 1，做错填 0；用时用报告里的毫秒，没有就填 0。新考点先 --register 再 --record。',
          `命令打印 already recorded 或同一 --exam-id ${review.id} 同一 --item 已写过，就跳过，禁止换标签再记一次。没有明确对错的题不要写。`,
        ].join('\n')
      : [
          'Keep all mastery/profile bookkeeping completely silent and internal. Never mention commands, database writes, tool output, mastery scores, confidence, sample counts, or bookkeeping summaries in the final answer unless I explicitly ask for statistics.',
          '若本轮能判断我某个考点的掌握变化，立刻写入，不要等我提醒：',
          `python3 ${projectRoot}/scripts/kaodian_profile.py --record '模块-一级-二级' '模块' '一级' 1 60000 hermes`,
          '每个有明确对错的证据记录一次；做对填 1，做错填 0。算法会自动考虑先验、近期表现、证据来源和样本置信度。新考点先 --register。',
        ].join('\n');
    const wantsQuiz = /\u7ed9\u6211\u51fa|\u5e2e\u6211\u51fa|\u51fa(?:[\u4e00-\u9fa5\d\u51e0]+)(?:\u9053|\u4e2a)?\u9898|\u8003\u8003\u6211|\u6765(?:[\u4e00-\u9fa5\d\u51e0]+)(?:\u9053|\u4e2a)?\u9898|\u5237\u9898|AI\s*\u7ec3\u9898|\u4e13\u9879\u7ec3\u9898|\u751f\u6210.{0,6}\u7ec3\u4e60|(?:\u6211\u8981|\u6211\u60f3|\u7ee7\u7eed|\u9488\u5bf9).{0,12}\u7ec3/.test(text);
    const wantsInlineQuiz = /(?:\u76f4\u63a5|\u5c31).{0,8}(?:\u804a\u5929|\u8fd9\u91cc).{0,8}(?:\u53d1|\u51fa|\u505a).{0,4}\u9898/.test(text);
    const quizNudge = wantsQuiz && !wantsInlineQuiz
      ? [
          'This is a question-generation request. The default delivery target is ExamSystem AI Practice, never inline chat.',
          "Before drafting questions, load skill_view('quiz-pipeline') and skill_view('gd-gongkao-coach'), then follow the full pipeline.",
          `Default non-data-analysis batch is 10: first run python3 ${projectRoot}/scripts/reference_style.py practice --tag '<规范主标签>' --count 2 and put those origin=zhenti items into questions.json unchanged. Then generate 8 new questions. If the user explicitly requests 全原创/all-original, generate all 10 and do not insert real questions. Data analysis remains 4 Guangdong materials × 5 questions = 20 original questions.`,
          `Before writing, read quiz-pipeline/references/reference-style-principles.md and reference-style-profile.md (GONGKAO-STYLE-v1). Do not call reference_style.py context --role generate for each stem. After the draft is complete, run python3 ${projectRoot}/scripts/reference_style.py context --role evaluate --count 1 once per tag family as a holdout check. If that command fails or the JSON has skipped=no_holdout_syllabus_mock, omit evaluation_contexts for those items and continue; do not rewrite the slot. Correctness and D-route visual gates still apply. The item is a syllabus mock. Copy 省考 length and ask-style from the internalized profile; do not write easier than the shallowest 国考 cognitive steps recorded there.`,
          `For data analysis, feed Gemini Flash the complete common+gd sections of quiz-pipeline/references/ziliao-paper-styles.md and the active R001/R005/R006/R007/R009/R016/R017/R018 rules. Default each material to 4 paragraphs and 420-650 Chinese characters; omit simulation disclaimers and slogan filler. Use data from at least 3 paragraphs, give every wrong option a distinct reproducible error path, reject cross-material formula/stem/error-path clones, and use images=yes holdout references for chart questions.`,
          'For 翻译推理: the keyed option must not restate 已知/现已知 instance facts, including synonyms. Need at least one contrapositive, a disjunctive syllogism, or a two-step chain. Keep the subject neutral (某企业/某团队) and do not leak the conclusion into the subject. Formalize 已知 facts as standalone literals. verify-logic.py rejects echo_given_fact; R029 is a hard fail.',
          'When generating a 20-question 判断推理 paper (daily or 成套): exactly 图形推理 5 + 逻辑判断 15 covering 加强/削弱/分析/解释/结构相似 (翻译推理 at most 2; never 定义判断 or 类比推理). Do NOT put 科学推理 in this paper. 科学推理 is a separate 5-question module (category=科学推理, never category=判断推理): one each from 力学、压强与浮力、电学、生物、地理 (physics 2-3 + biology 1 + geography 1), every item with a figure, junior-high Guangdong level. Answers: follow answer_plan; any letter at most twice, at least 3 distinct letters. Follow panduan_pack / kepui_pack if present: write the slot.tag. 科学推理-地理-等高线 is a contour-map item with a figure (route D), difficulty 3: 疏密判坡 / 河谷凸向高处 / 河流由高到低 / 简单选址, one of these, not 地球自转 and not stacked olympiad constraints. Missing holdout in the bank does not skip the slot. Targeted 10-question drills are exempt.',
          'The AI-generated batch manifest must record style_marker. Map evaluation_contexts only where a holdout exists; omit them for syllabus mocks when the bank has no matching holdout. generation_contexts is optional. zhenti- items are not gated and must not appear in context question_ids.',
          `Use the exact requested knowledge point. For B-route items write calculations.json; for image-dependent D-route items write image-specs.json with IMAGE_FACTS and MUST_DERIVE. Assign each generated item an answer letter from a balanced ABCD plan before writing options; put the computed/correct value on that letter and do not rewrite numbers to chase a letter. generation_gate will reshuffle if needed. Run python3 ${projectRoot}/scripts/generation_gate.py issue <batch>; ExamSystem itself performs A/B/C/D correctness checks and the independent real-exam quality review. Never handwrite PASS evidence.`,
          'If the system gate rejects, read evidence/system-quality.json, revise only the rejected items, refresh evaluation-context mappings when IDs change, and rerun the complete gate. Replace an item after its second failed revision.',
          'questions.json tags[0] must be the canonical 模块-一级-二级 card tag. For permutation questions use 基础原理/特殊模型/反面容斥, never 数量关系-数学运算-排列组合. knowledge_point is only a fallback; the stored field is tags.',
          'Create and import a batch into ExamSystem AI Practice. Do not print stems or options in chat. The final reply should only report the batch name and question count.',
        ].join('\n')
      : '';
    const needsLearnerSnapshot = Boolean(review || audio || wantsQuiz
      || /今天练什么|学习计划|我的情况|薄弱|掌握|错题|复盘|省考|行测|申论|攻克|知识点|推荐|遗忘|我想学/.test(text));
    let learnerNudge = '';
    if (needsLearnerSnapshot) {
      try {
        const snapshot = await api('/api/learner/snapshot?compact=1');
        if (snapshot?.compact) {
          learnerNudge = [
            '[LEARNER_SNAPSHOT — SYSTEM FACTS]',
            snapshot.compact,
            'Use this database snapshot as the source of truth for performance and recency. Do not infer mastery from conversational memory.',
            'If a target is listed under 刚练过不宜主攻, or its family was seen within 1 day, and the user did not name it, do not make it the main batch; at most mix 2 structural variants. Permutation subskills share one family; date and cycle share one family. Never regenerate the same scenario with swapped numbers.',
            'If the user names a module such as 数量, only recommend from that module in 下一步候选, still skip 刚练过不宜主攻 unless they named that family. Recency, 到期回捞 and mastery already encode the 21-day forgetting curve; do not invent a separate memory of what is due.',
            '[/LEARNER_SNAPSHOT]',
          ].join('\n');
        }
      } catch { /* 快照失败不应阻断用户消息，Hermes skill 仍可直接查库 */ }
    }
    const outbound = [
      reviewLead,
      voiceLead,
      submittedText,
      learnerNudge,
      masteryNudge,
      quizNudge,
    ].filter(Boolean).join('\n');
    const msgId = uid();

    // 先把界面切到"发送中"：气泡上屏、输入框清空、按钮换成停止。
    // 图片上传要好几秒，这期间一点反馈都没有的话用户只会以为没发出去
    setBanner('');
    setMessages((prev) => [
      ...prev,
      {
        id: msgId, role: 'user',
        content: text || (review ? '' : audioLabel),
        streaming: false,
        tools: [], thinking: '', images: images.filter((i) => !i.hidden).map((i) => i.dataUrl),
        audio: audio?.dataUrl || null,
        audioSec: audio?.sec > 0 ? Math.round(audio.sec) : (parseAudioLen(audioLabel) || null),
        hadAudio: !!audio,
        review: review ? { id: review.id, kind: review.kind, name: review.name, title: review.title, label: review.label, profileReviewed: Boolean(review.profileReviewed) } : null,
      },
    ]);
    setInput('');
    setPendingImages([]);
    setPendingAudio(null);
    setPendingReview(null);
    setBusy(true);
    setWaitSec(0);
    setStatus(audio ? '上传录音' : (images.length > 0 ? '上传图片' : '已发送'));
    stickToBottom.current = true;

    // 拿一个可用会话：优先 resume 当前存档（能保住上下文），
    // 没有存档可 resume 就新建一个
    const acquireSession = async () => {
      const stored = activeStoredIdRef.current;
      if (stored) {
        try {
          const res = await gw.request('session.resume', { session_id: stored, cols: 100 });
          return rememberSession(res, stored);
        } catch (err) {
          // 只有存档确实被 Hermes 回收时才新建；超时/断线等临时错误应直接交给
          // 外层恢复输入，避免一次网络抖动悄悄丢掉上下文。
          if (!/session not found/i.test(err?.message || '')) throw err;
        }
      }
      return rememberSession(await gw.request('session.create', await sessionCreateParams()));
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
      if (audio) {
        await gw.request('audio.attach_bytes', {
          session_id: target,
          content_base64: audio.dataUrl,
          filename: audio.name,
        });
      }
      await gw.request('prompt.submit', {
        session_id: target,
        text: outbound || (audio ? '请听这段口述' : '看看这张图片'),
      });
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
      setWaitSec(0);
      setMessages((prev) => prev.filter((m) => m.id !== msgId));
      setInput((cur) => cur || text);
      setPendingImages((cur) => (cur.length > 0 ? cur : images));
      setPendingAudio((cur) => cur || audio);
      setPendingReview((cur) => cur || review);
      setBusy(false);
      setStatus('');
    } finally {
      sendingRef.current = false;
    }
  }, [busy, input, pendingImages, pendingAudio, pendingReview, recording, rememberSession, sessionCreateParams]);

  // 小键盘句点开始录音；录音时 Esc 丢弃，第一次 Enter 只完成录音。
  // 音频进入输入区后，再按一次 Enter 才发送，和点右侧勾的行为一致。
  useEffect(() => {
    const onVoiceShortcut = (event) => {
      if (!active || event.defaultPrevented || event.repeat || event.isComposing) return;
      if (event.ctrlKey || event.altKey || event.metaKey) return;

      if (event.code === 'NumpadDecimal') {
        event.preventDefault();
        if (!recording && !busy && !attaching) void startRecording();
        return;
      }
      if (!recording) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        cancelRecording();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        stopRecording(false);
      }
    };
    window.addEventListener('keydown', onVoiceShortcut, true);
    return () => window.removeEventListener('keydown', onVoiceShortcut, true);
  }, [active, attaching, busy, recording, startRecording, cancelRecording, stopRecording]);

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
      const list = await api('/api/practice/sessions?limit=100');
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
      const [rep, info] = await Promise.all([
        api(`/api/practice/sessions/${sessionId}/report`),
        api(`/api/practice/sessions/${sessionId}/md`),
      ]);
      const items = rep?.items || [];
      const noOf = (it) => items.indexOf(it) + 1;
      // Keep every saved draft in question order. The review needs the full session,
      // not a hand-picked subset that can hide a correct-but-slow approach.
      const drafted = items.filter((it) => it.draft_url);

      const asDataUrl = async (src) => {
        const res = await fetch(src);
        if (!res.ok) throw new Error('题图加载失败');
        const blob = await res.blob();
        return await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ''));
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      };

      const images = [];
      for (const it of items) {
        const stems = [...(it.stem_images || [])];
        for (const opt of it.options || []) stems.push(...(opt.images || []));
        for (const [index, src] of stems.entries()) {
          try {
            const dataUrl = await asDataUrl(src);
            if (dataUrl) {
              images.push({
                id: uid(),
                name: `q${noOf(it)}-stem${index ? `-${index}` : ''}.png`,
                dataUrl,
                contextKind: 'practice',
                contextId: Number(sessionId),
                hidden: true,
              });
            }
          } catch { /* 单张题图失败不阻塞 */ }
        }
      }
      const stemCount = images.length;
      for (const it of drafted) {
        try {
          const r = await api(`/api/practice/sessions/${sessionId}/drafts/${it.question_id}/base64`);
          if (r?.data_url) {
            images.push({
              id: uid(),
              name: `q${noOf(it)}-draft.png`,
              dataUrl: r.data_url,
              contextKind: 'practice',
              contextId: Number(sessionId),
              hidden: true,
            });
          }
        } catch { /* 单张草稿加载失败不阻塞整份复盘 */ }
      }

      const s = rep.session || {};
      setPendingImages((prev) => [
        ...prev.filter((img) => img.contextKind !== 'practice'),
        ...images,
      ]);
      setPendingReview({
        id: Number(sessionId),
        kind: 'practice',
        path: info.path,
        name: info.name,
        title: info.title || `AI 练题复盘：${s.display_title || s.category || '未命名批次'}`,
        label: `AI练题复盘 · ${fmtDateTime(s.ended_at)} · ${s.display_title || s.category || '未命名批次'} · ${s.correct}/${s.total}`,
        stemCount,
        draftCount: images.length - stemCount,
        total: Number(s.total || items.length || 0),
        profileReviewed: Boolean(s.profile_reviewed_at),
      });
      setShowPicker(false);
      stickToBottom.current = true;
      setTimeout(() => taRef.current?.focus(), 0);
    } catch (err) {
      setBanner(`带上 AI 练题复盘失败：${err.message}`);
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
      const info = await api(`/api/exam-analyses/${id}/md`);
      const g = info.grade;
      const score = g
        ? `对 ${g.correct}/${g.total}`
        : '';
      setPendingReview({
        id,
        kind: 'exam',
        path: info.path,
        name: info.name,
        title: info.title || info.name,
        label: score ? `${info.title || info.name} · ${score}` : (info.title || info.name),
        grade: g || null,
      });
      setShowReview(false);
      stickToBottom.current = true;
      setTimeout(() => taRef.current?.focus(), 0);
    } catch (err) {
      setBanner(`带复盘失败：${err.message}`);
    } finally {
      setAttaching(false);
    }
  }, []);

  const attachUpload = useCallback(async (file) => {
    const date = file?.date;
    const typ = file?.type || 'pdf';
    const name = file?.name;
    if (!date || !name) return;
    let context;
    try {
      context = await loadHermesContext();
    } catch (err) {
      setBanner(`读取项目路径失败：${err.message}`);
      return;
    }
    const uploadRoot = context?.upload_root;
    const projectRoot = context?.project_root;
    if (!uploadRoot || !projectRoot) {
      setBanner('无法读取 ExamSystem 项目路径');
      return;
    }
    const abs = `${uploadRoot.replace(/\/+$/, '')}/${date}/${typ}/${name}`;
    const prompt = [
      `复盘这份资料上传的练习卷：${name}`,
      '',
      '绝对路径已经写好，直接打开，禁止 search_files，禁止 ls 其他目录，禁止猜项目目录。',
      abs,
      '',
      '立刻用 python3 + fitz 抽文字，按「你的答案：」「正确答案：」对答案。',
      "先 skill_view('gd-gongkao-coach') 和 skill_view('exam-coaching-gd-provincial')，按里面的三段式逐题复盘。",
      `复盘完用 ${projectRoot}/scripts/kaodian_profile.py 的 record() 写入 ${projectRoot}/data/exam.db；掌握度由算法自动重算，不要用 --mastery 猜分。`,
    ].join('\n');
    setInput((cur) => (cur.trim() ? `${cur.trim()}\n\n${prompt}` : prompt));
    setShowUploads(false);
    stickToBottom.current = true;
    setTimeout(() => taRef.current?.focus(), 0);
  }, [loadHermesContext]);

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
    const timer = setTimeout(() => {
      onSeedConsumed?.();
      if (seed.sessionId) void attachPractice(seed.sessionId);
      else if (seed.upload) void attachUpload(seed.upload);
    }, 0);
    return () => clearTimeout(timer);
  }, [seed, attachPractice, attachUpload, onSeedConsumed]);

  const onKeyDown = (e) => {
    if (e.defaultPrevented) return;
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (recording) {
        stopRecording(false);
        return;
      }
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

  // Re-measure after returning from another module. display:none reports a
  // scrollHeight of zero, which otherwise leaves the textarea visibly crushed.
  useEffect(() => {
    if (!active) return;
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [input, active]);

  // Restore the live conversation position when Hermes becomes visible again.
  useEffect(() => {
    if (!active) return;
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, status, active]);

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

  const practiceSessionForMessage = (messageId) => {
    const index = messages.findIndex((message) => message.id === messageId);
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const message = messages[cursor];
      if (message.role !== 'user') continue;
      return message.review?.kind === 'practice' ? Number(message.review.id) : null;
    }
    return null;
  };

  const connLabel = {
    idle: '未连接', connecting: '连接中…', open: '已连接', closed: '已断开', error: '连接失败',
  }[connState] || connState;
  const connColor = {
    open: 'bg-[#4caf50]', connecting: 'bg-[#ffa726]', error: 'bg-[#ef5350]', closed: 'bg-[#ef5350]',
  }[connState] || 'bg-[#bbb]';

  return (
    <div className={`flex h-full overflow-hidden ${fullscreen ? 'relative gap-0' : 'gap-4 animate-fadeIn'}`}>
      <HermesSidebar
        fullscreen={fullscreen}
        open={sidebarOpen}
        sessions={sessions}
        sessionsLoading={sessionsLoading}
        connState={connState}
        activeStoredId={activeStoredId}
        busy={busy}
        onRefresh={refreshSessions}
        onClose={() => setSidebarOpen(false)}
        onNew={newSession}
        onOpen={openSession}
        onDelete={deleteSession}
      />

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
                <MessageSquare size={18} />
              </button>
            )}
            {onToggleFullscreen && (
              <button
                onClick={onToggleFullscreen}
                title={fullscreen ? '退出全屏，显示导航' : '全屏阅读'}
                className={`flex items-center space-x-1 px-2 py-1 rounded-lg text-[15px] font-bold transition-colors shrink-0 ${
                  fullscreen ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5 hover:text-[#1a1a1a]'
                }`}
              >
                {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                <span>{fullscreen ? '退出全屏' : '全屏'}</span>
              </button>
            )}
            {!IS_STANDALONE && (
              <button
                onClick={toggleOsFullscreen}
                title={osFs ? '退出浏览器全屏' : '隐藏浏览器地址栏'}
                className={`flex items-center space-x-1 px-2 py-1 rounded-lg text-[15px] font-bold transition-colors shrink-0 ${
                  osFs ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5 hover:text-[#1a1a1a]'
                }`}
              >
                {osFs ? <Shrink size={16} /> : <Expand size={16} />}
                <span>{osFs ? '退出顶栏' : '隐藏顶栏'}</span>
              </button>
            )}
            <span className={`w-2 h-2 rounded-full shrink-0 ${connColor}`} />
            <span className="text-[15px] font-black tracking-widest text-[#999] shrink-0">
              {connLabel}
            </span>
            {status && (
              <span className="flex items-center space-x-1.5 text-[15px] font-bold text-[#6b5428] truncate">
                <Loader2 size={15} className="animate-spin shrink-0" />
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
              title="选择一次 AI 练题结果进行复盘"
              className="flex items-center space-x-1 px-2 py-1 rounded-lg text-[15px] font-bold text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors disabled:opacity-40"
            >
              {attaching
                ? <Loader2 size={16} className="animate-spin" />
                : <FileText size={16} />}
              <span>AI练题复盘</span>
            </button>
            <button
              onClick={openUploadPicker}
              disabled={attaching}
              title="带上资料上传里的练习卷"
              className="flex items-center space-x-1 px-2 py-1 rounded-lg text-[15px] font-bold text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors disabled:opacity-40"
            >
              <Upload size={16} />
              <span>资料上传</span>
            </button>
            <button
              onClick={openReviewPicker}
              disabled={attaching}
              title="带上某场模考的录屏行为复盘"
              className="flex items-center space-x-1 px-2 py-1 rounded-lg text-[15px] font-bold text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors disabled:opacity-40"
            >
              <ScanSearch size={16} />
              <span>真题复盘</span>
            </button>
            <div className="flex items-center rounded-lg overflow-hidden">
              <button
                onClick={() => setFontScale((v) => FONT_STEPS[Math.max(0, FONT_STEPS.indexOf(v) - 1)])}
                disabled={fontScale === FONT_STEPS[0]}
                title={`缩小正文（现在 ${fontScale}%）`}
                className="px-1.5 py-1 rounded-lg text-[15px] font-black text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-30"
              >
                A-
              </button>
              <button
                onClick={() => setFontScale((v) => FONT_STEPS[Math.min(FONT_STEPS.length - 1, FONT_STEPS.indexOf(v) + 1)])}
                disabled={fontScale === FONT_STEPS[FONT_STEPS.length - 1]}
                title={`放大正文（现在 ${fontScale}%）`}
                className="px-1.5 py-1 rounded-lg text-[17px] font-black text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-30"
              >
                A+
              </button>
            </div>
            <button
              onClick={() => setShowThinking((v) => !v)}
              title="显示/隐藏思考过程"
              className={`flex items-center space-x-1 px-2 py-1 rounded-lg text-[15px] font-bold transition-colors ${
                showThinking ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5'
              }`}
            >
              <Brain size={16} />
              <span>思考</span>
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
                <div className="max-w-[78%] flex flex-col items-end gap-1.5">
                  {(m.audio || m.audioSec > 0 || m.hadAudio || isAudioLabel(m.content)) && (
                    <VoiceBubble
                      src={m.audio}
                      sec={m.audioSec > 0 ? m.audioSec : (parseAudioLen(m.content) || 0)}
                      onDuration={(s) => setMessages((prev) => prev.map((x) => (
                        x.id === m.id ? { ...x, audioSec: s } : x
                      )))}
                    />
                  )}
                  {(m.images?.length > 0 || m.review || (m.content && !isAudioLabel(m.content))) && (
                    <div className="px-4 py-2.5 rounded-2xl rounded-br-md bg-[#1a1a1a] text-white">
                      {m.images?.length > 0 && (
                        <div className={`flex flex-wrap gap-1.5 ${m.review || (m.content && !isAudioLabel(m.content)) ? 'mb-2' : ''}`}>
                          {m.images.map((src, i) => (
                            <img key={i} src={src} alt="" className="w-20 h-20 object-cover rounded-lg" />
                          ))}
                        </div>
                      )}
                      {m.review && (
                        <div className={m.content && !isAudioLabel(m.content) ? 'mb-2' : ''}>
                          <ReviewChip review={m.review} onOpen={openReviewPreview} dark />
                        </div>
                      )}
                      {m.content && !isAudioLabel(m.content) ? (
                        <p className="text-[15px] whitespace-pre-wrap break-words leading-relaxed">{m.content}</p>
                      ) : null}
                    </div>
                  )}
                </div>
              ) : (
                <div className="max-w-[92%]">
                  <div className="flex items-center space-x-1.5 mb-1.5">
                    <div className="w-4 h-4 rounded-md bg-[#2c261c] flex items-center justify-center text-[9px] font-black text-white">
                      ⚕
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-widest text-[#bbb]">Hermes</span>
                    {m.content && (
                      <button
                        type="button"
                        onClick={() => setPopout((cur) => (
                          cur?.id === m.id
                            ? null
                            : {
                                id: m.id,
                                content: m.content || '',
                                practiceSessionId: practiceSessionForMessage(m.id),
                              }
                        ))}
                        title={popout?.id === m.id ? '收起复盘浮框' : '弹出复盘浮框，可拖动、缩放、单独滚动'}
                        className={`ml-1 p-1 rounded-md transition-colors ${
                          popout?.id === m.id
                            ? 'bg-[#1a1a1a] text-white'
                            : 'text-[#bbb] hover:bg-black/5 hover:text-[#1a1a1a]'
                        }`}
                      >
                        <PictureInPicture2 size={12} />
                      </button>
                    )}
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

                  {m.streaming && (
                    <ToolCard tool={m.tools?.[m.tools.length - 1]} />
                  )}

                  {(m.content || !m.streaming) && (
                    <MarkdownMessage
                      content={m.content}
                      streaming={m.streaming}
                      practiceSessionId={practiceSessionForMessage(m.id)}
                    />
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
          {pendingReview && (
            <div className="flex flex-wrap gap-2 mb-2">
              <ReviewChip
                review={pendingReview}
                onOpen={openReviewPreview}
                onRemove={() => {
                  if (pendingReview.kind === 'practice') {
                    setPendingImages((prev) => prev.filter((img) => img.contextKind !== 'practice'));
                  }
                  setPendingReview(null);
                }}
              />
            </div>
          )}
          {pendingImages.some((img) => !img.hidden) && (
            <div className="flex flex-wrap gap-2 mb-2">
              {pendingImages.filter((img) => !img.hidden).map((img) => (
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
          {(pendingAudio || recording) && (
            <div className="flex items-center justify-center gap-2 mb-2">
              {recording ? (
                <div className="flex items-center gap-2 rounded-full bg-[#1a1a1a] text-white px-1 py-1">
                  <button
                    type="button"
                    onClick={cancelRecording}
                    title="取消这次录音（Esc）"
                    className="w-8 h-8 rounded-full bg-white/15 text-white flex items-center justify-center shrink-0 hover:bg-white/25"
                  >
                    <X size={15} strokeWidth={2.6} />
                  </button>
                  <span className="w-2 h-2 rounded-full bg-[#ef5350] animate-pulse shrink-0" />
                  <RecWave stream={recStream} />
                  <span className="text-[11px] font-black tabular-nums opacity-80">{fmtSec(recordSec)}</span>
                  <button
                    type="button"
                    onClick={() => stopRecording(false)}
                    title="说完了，放进对话框（Enter）"
                    className="w-8 h-8 rounded-full bg-white text-[#1a1a1a] flex items-center justify-center shrink-0 hover:bg-[#f2e4c4]"
                  >
                    <Check size={16} strokeWidth={2.6} />
                  </button>
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setPendingAudio(null)}
                    className="w-5 h-5 rounded-full bg-[#1a1a1a] text-white flex items-center justify-center shrink-0"
                  >
                    <X size={10} />
                  </button>
                  <VoiceBubble src={pendingAudio.dataUrl} sec={pendingAudio.sec} />
                </>
              )}
            </div>
          )}

          <div className="flex items-end space-x-2">
            <input
              ref={audioPickRef}
              type="file"
              accept="audio/*,.m4a,.mp3,.wav,.webm,.aac,.ogg,.mp4"
              capture="user"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (file) ingestAudioBlob(file, file.type, file.name);
              }}
            />
            <button
              type="button"
              onClick={startRecording}
              disabled={busy || attaching || recording}
              title="口述给 Hermes（小键盘 .）"
              className="p-3 rounded-2xl shrink-0 bg-white border border-black/10 text-[#1a1a1a] hover:bg-black/5 transition-colors disabled:opacity-30"
            >
              <Mic size={18} />
            </button>
            <textarea
              ref={taRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              onPaste={onPaste}
              rows={1}
              placeholder={connState === 'open'
                ? (dragOver ? '松手就把图片放进来' : 'Enter 发送 · 小键盘 . 录音')
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
                disabled={connState !== 'open' || recording || (!input.trim() && pendingImages.length === 0 && !pendingReview && !pendingAudio)}
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
      {reviewPreview && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[80] flex items-center justify-center p-6"
          onClick={closeReviewPreview}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="bg-white rounded-[2rem] w-full max-w-3xl shadow-2xl max-h-[85vh] overflow-y-auto p-6 md:p-8"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 mb-5">
              <div className="min-w-0">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">复盘报告</p>
                <p className="text-xl font-black italic truncate">{reviewPreview.label || reviewPreview.title || reviewPreview.name}</p>
              </div>
              <button
                type="button"
                onClick={closeReviewPreview}
                className="w-8 h-8 rounded-full bg-[#e8d5b0] hover:bg-[#e8e6dd] flex items-center justify-center shrink-0"
              >
                <X size={16} />
              </button>
            </div>
            {reviewMdErr ? (
              <p className="text-sm font-bold text-slate-400">{reviewMdErr}</p>
            ) : reviewMd ? (
              <MarkdownMessage
                content={reviewMd}
                practiceSessionId={reviewPreview.kind === 'practice' ? Number(reviewPreview.id) : null}
              />
            ) : (
              <div className="flex items-center gap-2 text-[11px] text-[#999]">
                <Loader2 size={11} className="animate-spin" />
                <span>加载中…</span>
              </div>
            )}
          </div>
        </div>
      )}
      {popout && (
        <ReviewFloater
          content={messages.find((m) => m.id === popout.id)?.content || popout.content}
          streaming={!!messages.find((m) => m.id === popout.id)?.streaming}
          fontScale={fontScale}
          practiceSessionId={popout.practiceSessionId}
          onClose={() => setPopout(null)}
        />
      )}
      <HermesContextPickers
        showReview={showReview}
        setShowReview={setShowReview}
        reviewsLoading={reviewsLoading}
        examReviews={examReviews}
        attachExamReview={attachExamReview}
        showUploads={showUploads}
        setShowUploads={setShowUploads}
        uploadsLoading={uploadsLoading}
        uploadFiles={uploadFiles}
        attachUpload={attachUpload}
        showPicker={showPicker}
        setShowPicker={setShowPicker}
        runsLoading={runsLoading}
        practiceRuns={practiceRuns}
        attachPractice={attachPractice}
        attaching={attaching}
        loadPracticeRuns={loadPracticeRuns}
      />
    </div>
  );
};

export default HermesChat;

// Hermes 对话页
//
// 走 JSON-RPC over WebSocket 直连 Hermes 的 gateway（经 Express 代理），
// 与官方 dashboard 的 Chat 用的是同一套协议和同一个 agent，
// 因此这里能看到并续接微信、cron、CLI 的全部会话。
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Send, Square, MessageSquare, Loader2, Brain, X, Image as ImageIcon,
  ScanSearch, Upload, Maximize2, Minimize2, Expand, Shrink, FileText, Mic,
  PictureInPicture2, Check, Plus,
} from 'lucide-react';

import { api } from '../api.js';
import { parseSqliteTime } from '../sqliteTime.js';
import HermesGateway from './gateway.js';
import { audioLabelOf, fmtVoiceQuote, isAudioLabel, parseAudioLen } from './voiceLabel.js';
import BackgroundNotice from './BackgroundNotice.jsx';
import MarkdownMessage from './MarkdownMessage.jsx';
import ToolCard from './ToolCard.jsx';
import { getToolActivity } from './toolActivity.js';
import QuotaBar from './QuotaBar.jsx';
import HermesSidebar from './HermesSidebar.jsx';
import HermesContextPickers from './HermesContextPickers.jsx';
import ReviewFloater from './ReviewFloater.jsx';
import { HIDDEN_SOURCES, sessionPickerMode } from './hermesLayout.js';
import {
  appendAssistantDelta as appendAssistantDeltaState,
  coerceResumePayload,
  ensureStreamingAssistant,
  eventMatchesSession,
  eventText,
  finishAssistantMessage,
  mergeResumedMessages,
  visibleAssistantReply,
  resumeMatchesSession,
  shouldAcceptRemoteResume,
} from './hermesProtocol.js';

let msgSeq = 0;
const uid = () => `m${++msgSeq}`;

const IMAGE_MAX_BYTES = 10 * 1024 * 1024;
const PDF_MAX_BYTES = 30 * 1024 * 1024;
const FILE_MAX_BYTES = 50 * 1024 * 1024;
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
const SESSION_SYNC_MS = 10000;

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
  <svg width="1.07em" height="1.07em" viewBox="0 0 16 16" fill="none" aria-hidden className={playing ? 'voice-playing' : ''}>
    <path d="M10.6 6a2.2 2.2 0 0 0 0 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M8.2 4.5a4.2 4.2 0 0 0 0 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M5.8 3a6.2 6.2 0 0 0 0 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <circle cx="13.1" cy="8" r="1.15" fill="currentColor" />
  </svg>
);

const VoiceBubble = ({ src, sec = 0, onDuration }) => {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  // em 而不是 px：正文放大时语音条跟着一起放大，不会缩成一小条
  const width = `${(78 + Math.min(Math.max(Number(sec) || 1, 1), 60) * 2.1) / 15}em`;

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
      className="relative flex items-center justify-end gap-1.5 h-[2.67em] pr-3.5 pl-4 mr-1.5 rounded-[10px] bg-[#1a1a1a] text-[#f7efe0] disabled:opacity-90"
      style={{ width }}
    >
      <span className="text-[1em] tabular-nums leading-none">{fmtVoiceQuote(sec)}</span>
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
  const date = new Date(parseSqliteTime(raw));
  if (Number.isNaN(date.getTime())) return String(raw);
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  });
};

const fmtBubbleTime = (ms) => {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
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

// 口述笔记的落盘路径。录音不落库，会话一回收就听不到了，所以每段录音都先留一份
// 文字底稿；文件名带时间戳，一段一个文件，方便日后按时间翻。
const voiceNotePath = (projectRoot) => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  return `${projectRoot}/data/voice-notes/${stamp}-voice.md`;
};

const fmtTokens = (n) => {
  const v = Number(n) || 0;
  if (v >= 1000000) return `${(v / 1048576).toFixed(v >= 10485760 ? 0 : 1).replace(/\.0$/, '')}M`;
  if (v >= 1000) return `${Math.round(v / 1000)}K`;
  return String(v);
};

const fmtMinutes = (sec) => {
  const s = Math.max(0, Math.round(sec || 0));
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${String(s % 60).padStart(2, '0')} 秒` : `${s} 秒`;
};

// 消息导航刻度：静止 12px，指针最近处放大到 26px，34px 内平滑过渡成波浪
const TICK_MIN_W = 12;
const TICK_LIFT = 14;
const TICK_FALLOFF = 34;

const ReviewChip = ({ review, onOpen, onRemove, dark }) => (
  <div className={`inline-flex items-center gap-2 pl-2.5 pr-1.5 py-1.5 rounded-xl border max-w-full ${
    dark ? 'bg-white/10 border-white/20 text-white' : 'bg-[#f4f0e6] border-[#e8d5b0] text-[#1a1a1a]'
  }`}>
    <button type="button" onClick={() => onOpen(review)} className="inline-flex items-center gap-1.5 min-w-0">
      <FileText size="0.8em" className={`shrink-0 ${dark ? 'text-[#e8d5b0]' : 'text-[#6b5428]'}`} />
      <span className="text-[0.75em] font-black truncate max-w-[280px]">{review.label || review.name || review.title}</span>
    </button>
    {onRemove ? (
      <button
        type="button"
        onClick={onRemove}
        className="w-[1.07em] h-[1.07em] rounded-full bg-[#1a1a1a] text-white flex items-center justify-center shrink-0"
      >
        <X size="0.6em" />
      </button>
    ) : null}
  </div>
);

const HermesChat = ({ seed, onSeedConsumed, active = true, fullscreen = false, onToggleFullscreen, headerExtra }) => {
  const location = useLocation();
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
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 1440);
  const pickerMode = sessionPickerMode(viewportWidth);
  const overlayPicker = pickerMode === 'sheet' || fullscreen;
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
  const [activeMessageId, setActiveMessageId] = useState(null);
  // 网关每轮随 message.complete 推 usage（context_used/max/percent），切会话时再补一次
  const [usage, setUsage] = useState(null);
  // railFocus = { y, index }：指针（或手指）在导航轨道上的位置，驱动波浪和信息卡
  const [railFocus, setRailFocus] = useState(null);
  const [railScrub, setRailScrub] = useState(false);
  const [tickCenters, setTickCenters] = useState([]);
  const [showUploads, setShowUploads] = useState(false);
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploadsLoading, setUploadsLoading] = useState(false);

  const scrollRef = useRef(null);
  const messageRefs = useRef(new Map());
  const railRef = useRef(null);
  const stickToBottom = useRef(true);
  const taRef = useRef(null);
  const filePickRef = useRef(null);
  // sid 的镜像：send/interrupt 等回调里要读最新值，又不想因此重建回调
  const sidRef = useRef(null);
  useEffect(() => { sidRef.current = sid; }, [sid]);
  // 同理：会话过期重连时要知道当前开着哪个存档，才能 resume 回来保住上下文
  const activeStoredIdRef = useRef(null);
  useEffect(() => { activeStoredIdRef.current = activeStoredId; }, [activeStoredId]);
  const practiceReviewRef = useRef(null);
  // 这一轮带了录音：回合结束后要把运行时里的音频清掉，见 dropAudioFromContext
  const voiceTurnRef = useRef(false);
  // 连接是在挂载时建立的，事件回调拿不到后面定义的 dropAudioFromContext，用 ref 转一手
  const dropAudioContextRef = useRef(null);

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
    if (!reviewPreview) return undefined;
    if (reviewPreview.kind === 'upload') {
      setReviewMdErr('');
      setReviewMd([
        '粉笔练习卷（资料上传）',
        '',
        reviewPreview.path || reviewPreview.name || '',
      ].join('\n'));
      return undefined;
    }
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
    const liveId = res?.session_id || sidRef.current || null;
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
    sendingRef.current = false;
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

    const onActive = (fn) => (ev) => {
      if (!eventMatchesSession(ev, sidRef.current, activeStoredIdRef.current)) return;
      fn(ev);
    };

    const offs = [
      gw.onState(setConnState),

      gw.on('message.delta', onActive((ev) => {
        const t = ev.payload?.text;
        if (t) appendAssistantDelta(t);
      })),
      // thinking.delta 是转圈状态文案，不是推理过程（官方 desktop 直接忽略）
      gw.on('thinking.delta', onActive((ev) => {
        const t = ev.payload?.text;
        if (t) setStatus(String(t));
      })),
      gw.on('reasoning.delta', onActive((ev) => {
        const t = ev.payload?.text;
        if (t) appendThinking(t);
      })),
      gw.on('message.start', onActive(() => {
        setWaitSec(0);
        setBusy(true);
        setStatus('(｡•̀ᴗ-)✧ 整理一下');
        setMessages((prev) => ensureStreamingAssistant(prev, uid));
        // 另一台设备提交的回合：事件可能先到，用 history/resume 补上对方的用户气泡
        if (!sendingRef.current) {
          void pullRemoteSessionRef.current?.({ force: false });
        }
      })),
      gw.on('message.complete', onActive((ev) => {
        const review = practiceReviewRef.current;
        if (ev.payload?.usage) setUsage(ev.payload.usage);
        finishStreaming(eventText(ev));
        practiceReviewRef.current = null;
        // 录音已经用完，也已由模型写成口述笔记，现在把它从上下文里摘掉。
        // 等一下再动手，免得撞上紧跟着的后台回执或工具事件。
        if (voiceTurnRef.current) {
          voiceTurnRef.current = false;
          setTimeout(() => { void dropAudioContextRef.current?.(); }, 2000);
        }
        if (review?.kind !== 'practice' || review.profileReviewed) return;
        api(`/api/practice/sessions/${review.id}/review-complete`, { method: 'POST' })
          .then(() => api('/api/practice/sessions?limit=100'))
          .then((list) => setPracticeRuns(Array.isArray(list) ? list : []))
          .catch(() => {});
      })),

      gw.on('tool.start', onActive((ev) => {
        const p = ev.payload || {};
        upsertTool({
          tool_id: p.tool_id, name: p.name || 'tool', args: p.args,
          args_text: p.args_text, preview: p.preview, done: false,
        });
        const activity = getToolActivity(p.name);
        setStatus(`${activity.emoji} ${activity.label}`);
      })),
      gw.on('tool.complete', onActive((ev) => {
        const p = ev.payload || {};
        upsertTool({
          tool_id: p.tool_id, name: p.name || 'tool', args: p.args,
          result: p.result, duration_s: p.duration_s, done: true,
        });
        setStatus('(｡•̀ᴗ-)✧ 整理一下');
      })),

      gw.on('status.update', onActive((ev) => {
        const s = ev.payload?.text || ev.payload?.status;
        if (s) setStatus(String(s));
      })),

      gw.on('error', onActive((ev) => {
        const msg = ev.payload?.message || '未知错误';
        setBanner(msg);
        setWaitSec(0);
        sendingRef.current = false;
        setBusy(false);
        setStatus('');
      })),

      // 审批请求：ExamSystem 这个界面不做审批 UI，提示去微信/终端处理
      gw.on('approval.request', onActive(() => {
        setBanner('Hermes 请求操作授权，请到微信或终端确认（本页暂不支持审批）');
      })),
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

  const applyResume = useCallback((res, storedId, { force = true, stick = false, allowSwitch = force } = {}) => {
    const payload = coerceResumePayload(res);
    if (!allowSwitch && !resumeMatchesSession(payload, sidRef.current, activeStoredIdRef.current || storedId)) {
      return;
    }
    const prevStored = activeStoredIdRef.current;
    const nextStored = storedId || payload.stored_session_id || null;
    const sameSession = !prevStored || !nextStored || prevStored === nextStored;
    rememberSession({
      ...payload,
      session_id: payload.session_id || sidRef.current,
      stored_session_id: nextStored,
    }, nextStored);
    setMessages((prev) => {
      const next = mergeResumedMessages(prev, payload, {
        nextId: uid,
        parseAudioLen,
        isAudioLabel,
        sameSession,
        storedId: nextStored,
      });
      return shouldAcceptRemoteResume(prev, next, payload, force) ? next : prev;
    });
    if (payload.running) {
      setWaitSec(0);
      setBusy(true);
      setStatus('生成中');
    } else if (force || Object.prototype.hasOwnProperty.call(payload, 'running')) {
      sendingRef.current = false;
      setBusy(false);
      setStatus('');
    }
    if (stick) stickToBottom.current = true;
  }, [rememberSession]);

  // 录音只活在运行时的消息列表里，之后每一轮都要整包重传：一段 8 分钟的口述约
  // 2.7MB，说过三次就是每轮 3.8MB，今晚那次上游 EOF 就是这么撑出来的。
  // 数据库只存文字，所以 close 掉运行时再 resume，历史照旧、音频归零（实测 39 条
  // 消息一条不少）。语气已经由模型写进口述笔记，内容不会丢。
  const dropAudioFromContext = useCallback(async () => {
    const gw = gwRef.current;
    const stored = activeStoredIdRef.current;
    const live = sidRef.current;
    if (!gw || gw.connectionState !== 'open' || !stored || !live) return;
    if (sendingRef.current) return;
    try {
      await gw.request('session.close', { session_id: live });
      const res = await gw.request('session.resume', { session_id: stored, cols: 100 });
      applyResume(res, stored, { allowSwitch: false });
    } catch {
      /* 清不掉就算了，下一次会话回收时系统也会把音频丢掉 */
    }
  }, [applyResume]);

  useEffect(() => {
    dropAudioContextRef.current = dropAudioFromContext;
  }, [dropAudioFromContext]);

  const historySupportedRef = useRef(null);
  const syncingRef = useRef(false);
  const pullRemoteSessionRef = useRef(null);

  const pullRemoteSession = useCallback(async ({ force = false } = {}) => {
    const gw = gwRef.current;
    const stored = activeStoredIdRef.current;
    if (!gw || gw.connectionState !== 'open' || !stored) return;
    if (sendingRef.current || syncingRef.current) return;
    syncingRef.current = true;
    try {
      let res = null;
      if (historySupportedRef.current !== false) {
        try {
          res = coerceResumePayload(await gw.request('session.history', {
            session_id: sidRef.current || stored,
          }));
          historySupportedRef.current = true;
        } catch (err) {
          const msg = err?.message || '';
          if (/unknown method|method not found|invalid request/i.test(msg)) {
            historySupportedRef.current = false;
          } else if (historySupportedRef.current === true) {
            throw err;
          }
        }
      }
      if (!res || (!res.messages?.length && !res.inflight && !res.running)) {
        res = await gw.request('session.resume', { session_id: stored, cols: 100 });
      }
      applyResume(res, stored, { force, allowSwitch: false });
    } catch {
      /* 后台同步失败不应打断正在看的对话 */
    } finally {
      syncingRef.current = false;
    }
  }, [applyResume]);

  useEffect(() => {
    pullRemoteSessionRef.current = pullRemoteSession;
  }, [pullRemoteSession]);

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
        .then((res) => applyResume(res, cachedActive, { stick: true }))
        .catch(() => writeCachedActiveSession(null));
      return;
    }

    const stored = activeStoredIdRef.current;
    if (!stored) return;
    setStatus('重连会话');
    gw.request('session.resume', { session_id: stored, cols: 100 })
      .then((res) => applyResume(res, stored, { allowSwitch: false }))
      .catch((err) => setBanner(`重连会话失败：${err.message}`));
  }, [connState, applyResume]);

  // usage 只随 message.complete 推送，打开一个老会话时先主动问一次，
  // 否则指示器要等你发完一轮才有数。
  useEffect(() => {
    const gw = gwRef.current;
    if (!gw || connState !== 'open' || !sid) return undefined;
    let cancelled = false;
    gw.request('session.usage', { session_id: sid })
      .then((res) => { if (!cancelled && res && typeof res === 'object') setUsage(res); })
      .catch(() => { /* 老版本 gateway 没有这个方法，指示器留空即可 */ });
    return () => { cancelled = true; };
  }, [sid, connState]);

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const autoOpenedSheetRef = useRef(false);
  useEffect(() => {
    if (autoOpenedSheetRef.current) return;
    if (pickerMode !== 'sheet') return;
    if (activeStoredId || messages.length > 0) return;
    if (sessionsLoading) return;
    const visible = sessions.filter((session) => !HIDDEN_SOURCES.has(session.source));
    if (visible.length === 0) return;
    autoOpenedSheetRef.current = true;
    setSidebarOpen(true);
  }, [pickerMode, activeStoredId, messages.length, sessions, sessionsLoading]);

  useEffect(() => {
    if (!active) return undefined;
    void pullRemoteSession({ force: true });
    const onSync = () => {
      if (document.visibilityState === 'hidden') return;
      void pullRemoteSession({ force: true });
    };
    document.addEventListener('visibilitychange', onSync);
    window.addEventListener('focus', onSync);
    window.addEventListener('pageshow', onSync);
    return () => {
      document.removeEventListener('visibilitychange', onSync);
      window.removeEventListener('focus', onSync);
      window.removeEventListener('pageshow', onSync);
    };
  }, [active, pullRemoteSession]);

  // 处理从知识债跳转过来的初始消息
  const initialMessageHandled = useRef(false);
  useEffect(() => {
    if (initialMessageHandled.current) return;
    if (!location.state?.initialMessage) return;
    if (connState !== 'open') return;
    if (busy) return;

    const initialMsg = location.state.initialMessage;
    initialMessageHandled.current = true;

    // 清除 location state 避免刷新时重复发送
    window.history.replaceState({}, document.title);

    // 创建新会话并发送消息
    setInput(initialMsg);

    // 延迟一点让input更新完成
    setTimeout(() => {
      const sendBtn = document.querySelector('[data-hermes-send]');
      if (sendBtn) sendBtn.click();
    }, 100);
  }, [location.state, connState, busy]);


  useEffect(() => {
    if (!active || connState !== 'open' || !activeStoredId) return undefined;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      if (sendingRef.current) return;
      void pullRemoteSession({ force: false });
    }, SESSION_SYNC_MS);
    return () => window.clearInterval(timer);
  }, [active, connState, activeStoredId, pullRemoteSession]);

  const openSession = useCallback(async (stored) => {
    const gw = gwRef.current;
    if (!gw || busy) return;
    setBanner('');
    setStatus('载入会话');
    try {
      setMessages([]);
      setUsage(null);
      const res = await gw.request('session.resume', { session_id: stored.id, cols: 100 });
      applyResume(res, stored.id, { stick: true });
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
      setUsage(null);
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
    practiceReviewRef.current = review;
    voiceTurnRef.current = Boolean(audio);
    const examScoreLine = review?.grade
      ? `本场分数只认 PDF 判分：共 ${review.grade.total} 题，对 ${review.grade.correct}，错 ${review.grade.wrong}，空 ${review.grade.blank || 0}。禁止改成别的分数，禁止用录屏勾选重算。`
      : '对错和分数只认报告开头「判分（只认本表，来自答案 PDF）」那张表。禁止用录屏勾选、报告里的「差距」或自己心算改分数。';
    const examReviewLead = review
      ? [
          `下面这个 Markdown 是我那场《${review.title}》的录屏复盘报告，请先打开。`,
          review.path,
          '',
          examScoreLine,
          '回复的第一行必须是 `### 01 · 题型名`。禁止先写「一、全卷知识点对照标定」「短处与致命失分点」「长短处诊断」或任何知识点总表。直接按题讲，口吻必须和 AI 练题复盘一样。',
          '复盘必须同时用三份材料：① 报告开头 PDF 判分表和原题；② 「录屏行为记录」里每题的停留、标签、过程、时间线；③ 各题草稿。对错、你的答案、正确答案只抄 PDF 判分表。报告里旧的「差距」「你怎么做的」若和判分表或行为记录冲突，以判分表和行为记录为准。',
          '1. 每一道展开复盘的题必须严格套用同一版式：`### 02 · 题型名`；下一块为 `> **原题**`，同一引用块内先完整照录题干（题干里出现的 A、B、C 地名/序号必须留在原句，禁止拆成单独一行），四个选项只用 `> **A.**` / `> **B.**` / `> **C.**` / `> **D.**` 各占一行。禁止横向表格、禁止四个选项挤在同一行、禁止省略任何选项、禁止在原题区标答案。',
          '2. 原题卡片之后另起一行写 `**作答结果**：你的答案 X · 正确答案 Y · 用时 MM:SS`（对错抄判分表），再依次使用 `#### 草稿诊断`、`#### 考场解法`、`#### 下次动作`。知识点不要开篇罗列，只在后台写入画像；用户可见处最多在作答结果后写一行 `本题考察知识点：模块-一级-二级`。',
          '3. `#### 草稿诊断` 必须先写：结合行为记录、草稿和 PDF，卡在审题、方法、推理、计算还是检查。要点出本题实际发生过的行为（停留偏长、跳过、回头、改选项、只划线没列式等），不要另开「行为分析」标题。',
          '4. 正确题不能按对错直接跳过。用时偏长、改过选项、草稿乱、方法绕、或存在明显更快的考场解法时，必须展开 `#### 考场解法` 和 `#### 下次动作`，给出能压缩步骤的动作。禁止用「确认通过」「没问题」打发。',
          '5. 只有做法干净、用时也很快、且没有更好压法的对题，才一句「没问题，继续保持」，不要展开表扬。错题或空题必须展开。',
          '6. 建议必须是考场动作，例如先看什么、写哪一步、何时排除或何时放弃，禁止哈利波特等包装。',
          '7. 确认是独立的新考点时，按 knowledge-point-extension.md 登记，并在该标签后注明「（新补录）」。',
          '8. 最后一题讲完后必须另起 `### 本场结语`，只针对这一场，不要戛然而止。依次写 `#### 做得好的`、`#### 做得不好的`、`#### 以后怎么改`。`做得好的` 只列可复现的动作和题号，口吻是严师：标准严、态度也严、讲解仍耐心；低级失误就直说，禁止浮夸夸赞。禁止空话和知识点总表。建议仍是考场动作。',
          '严师驱动规约：目标是公考得分，不是证明用户很努力。时长、吃苦和自我评价不算掌握证据，只看正确率、用时、草稿动作和能否复现。对高频、可避免、直接造成失分且能靠标准动作纠正的错误，明确说“这一步不该错/本场必须纠正”；按“判定→出错起点→唯一标准动作→下一次验收证据”输出。重复犯同一错误时减少安慰，安排最短针对性复做；不布置与提分无关的苦工。只批评行为，不攻击人格；表扬只给有证据、可复现且有分数价值的动作。',
          '9. 资料分析同样一题一题讲，但按材料成套：先 `### 材料一`，用 `> **材料**` 完整放上该篇文字/表/图，不要每题重复整篇材料；接着连续复盘该篇下的 5 道题，每题仍是 `> **原题**`（只放问句和选项）→ 作答结果 → `#### 草稿诊断` → `#### 考场解法` → `#### 下次动作`。第 5 题讲完再放 `### 材料二` 及下五题。禁止把 20 题拆散穿插，禁止省略材料。',
          '',
        ].join('\n')
      : '';
    const practiceReviewLead = review
      ? [
          `下面这个 Markdown 是我选中的《${review.title}》，请先直接打开文件。`,
          review.path,
          ...(review.audit
            ? [
                ...(review.auditSourcePath
                  ? [`这是复盘审核。首次复盘报告在这里，先打开并严格对照：${review.auditSourcePath}`]
                  : ['这是复盘审核，但首次复盘报告路径缺失；必须明确说明无法完成前后对照，不得假装看过首次复盘。']),
                '本轮不是普通的第二次讲题，而是对首次复盘是否有效的验收。先读取首次复盘给出的错误起点、标准动作和下次验收证据，再检查本次重做是否真正做到。',
                '逐题同时对照首次作答、本次作答、两次用时、两次草稿和首次复盘要求；每题必须给出“有效掌握 / 部分掌握 / 未掌握”的审核结论，并说明证据。',
                '本次答对但仍依赖猜测、方法与首次要求不一致、步骤不能复现、用时明显失控或草稿无法支持结论，都不能判为有效掌握；本次空题或答错直接判为未掌握。',
                '审核正文仍按题输出，但重点写“首次复盘要求是否落实 → 本次重做证据 → 是否通过 → 下一步验收动作”，禁止只复述首次解析。',
              ]
            : []),
          `本场共 ${review.total || 0} 题；已附上 ${review.draftCount || 0} 张实际保存的草稿纸。请逐题对应，不要把附件数量误认为题目总数。`,
          '',
          '本轮只复盘，不出题。第一件工具必须是打开上面这条路径；打开后立刻从 `### 01 · 题型名` 写给人看的正文。',
          '禁止 search_files、ls、PRAGMA、猜列名、读 ExamSystem 源码、import kaodian_taxonomy / quiz_lite / quiz_generator / generation_gate。',
          '题目id、对错、用时、知识点以报告表格为准。--item 只用表格里的题目id。草稿按附件 qN-draft.png 对题号，不要再去 draft-images 翻目录，不要再查 exam.db。',
          '',
          '回复的第一行必须是 `### 01 · 题型名`。禁止先写总况、长短处、知识点总表或模块总评。直接按题讲。',
          '言语、判断、数量、资料必须同一套标题，禁止按模块换版式。展开的题五段标题一行都不能少：`### 02 · 题型名` → `> **原题**` → `**作答结果**` → `#### 草稿诊断` → `#### 考场解法` → `#### 下次动作`。禁止改成「为什么会错 / 解题流程 / 下次遇到怎么做」，禁止把「下次动作」收成没有标题的一句收尾。',
          '如果同时附有草稿图片，请把图片与 Markdown 中对应题号、正确性和用时一起分析。除原题外，不要机械复述报告统计或现成解析。',
          '1. 每一道展开复盘的题必须严格套用同一版式：`### 02 · 题型名`；下一块为 `> **原题**`，同一引用块内先完整照录题干（题干里出现的 A、B、C 地名/序号必须留在原句，禁止拆成单独一行），四个选项只用 `> **A.**` / `> **B.**` / `> **C.**` / `> **D.**` 各占一行。禁止横向表格、禁止四个选项挤在同一行、禁止省略任何选项、禁止在原题区标答案。',
          '2. 原题卡片之后另起一行写 `**作答结果**：你的答案 X · 正确答案 Y · 用时 MM:SS`，下一行必须单独写 `本题考察知识点：模块-一级-二级`（用知识点页词表，例如 `数量-最值问题-和定求极值`），再依次使用 `#### 草稿诊断`、`#### 考场解法`、`#### 下次动作`。题目依赖配图时明确提示查看对应题图或草稿图，并结合实际图片分析，禁止凭文字补造图形。',
          '3. 错题或空题必须定位出错起点：审题遗漏、方法选择、推理、计算或检查。',
          '4. 正确题不能按结果直接跳过。有草稿、用时偏长、涂改多、方法绕远、或存在明显更快的考场解法时，必须展开 `#### 考场解法` 和 `#### 下次动作`。禁止用「确认通过」「没问题」打发，禁止省略 `#### 下次动作`。',
          '5. 只有做法干净、用时也很快、且没有更好压法的对题，才一句「没问题，继续保持」，不要展开表扬。错题或空题必须展开。',
          '6. 建议必须是考场动作，例如先看什么、写哪一步、何时排除或何时放弃，禁止哈利波特、黑暗王子、黑魔法等包装。',
          '7. 确认是独立的新考点时，按 knowledge-point-extension.md 登记，并在该标签后注明「（新补录）」。',
          '8. 最后一题讲完后必须另起 `### 本场结语`，只针对这一场，不要戛然而止。依次写 `#### 做得好的`、`#### 做得不好的`、`#### 以后怎么改`。`做得好的` 只列可复现的动作和题号，口吻是严师：标准严、态度也严、讲解仍耐心；低级失误就直说，禁止浮夸夸赞。禁止空话和知识点总表。建议仍是考场动作。',
          '严师驱动规约：目标是公考得分，不是证明用户很努力。时长、吃苦和自我评价不算掌握证据，只看正确率、用时、草稿动作和能否复现。对高频、可避免、直接造成失分且能靠标准动作纠正的错误，明确说“这一步不该错/本场必须纠正”；按“判定→出错起点→唯一标准动作→下一次验收证据”输出。重复犯同一错误时减少安慰，安排最短针对性复做；不布置与提分无关的苦工。只批评行为，不攻击人格；表扬只给有证据、可复现且有分数价值的动作。',
          '9. 资料分析同样一题一题讲，但按材料成套：先 `### 材料一`，用 `> **材料**` 完整放上该篇文字/表/图，不要每题重复整篇材料；接着连续复盘该篇下的 5 道题，每题仍是 `> **原题**`（只放问句和选项）→ 作答结果 → `#### 草稿诊断` → `#### 考场解法` → `#### 下次动作`。第 5 题讲完再放 `### 材料二` 及下五题。禁止把 20 题拆散穿插，禁止省略材料。',
          '',
        ].join('\n')
      : '';
    const uploadReviewLead = review?.kind === 'upload'
      ? [
          `下面这份 PDF 是我在粉笔做的练习卷《${review.title}》，请直接打开，禁止 search_files，禁止 ls 其他目录。`,
          review.path,
          '立刻用 python3 + fitz 抽出题干、选项、「你的答案：」「正确答案：」。口吻、标题和版式必须与 AI 练题复盘完全相同。禁止改成三段式，禁止 skill_view 换版式。',
          '没有草稿纸和用时：作答结果写 `**作答结果**：你的答案 X · 正确答案 Y · 用时 无`。`#### 草稿诊断` 只根据对错和题干判断，禁止编造草稿、停留、涂改或用时。',
          '',
          '回复的第一行必须是 `### 01 · 题型名`。禁止先写总况、长短处、知识点总表或模块总评。直接按题讲。',
          '言语、判断、数量、资料必须同一套标题，禁止按模块换版式。展开的题五段标题一行都不能少：`### 02 · 题型名` → `> **原题**` → `**作答结果**` → `#### 草稿诊断` → `#### 考场解法` → `#### 下次动作`。禁止改成「为什么会错 / 解题流程 / 下次遇到怎么做」，禁止把「下次动作」收成没有标题的一句收尾。',
          '1. 每一道展开复盘的题必须严格套用同一版式：`### 02 · 题型名`；下一块为 `> **原题**`，同一引用块内先完整照录题干（题干里出现的 A、B、C 地名/序号必须留在原句，禁止拆成单独一行），四个选项只用 `> **A.**` / `> **B.**` / `> **C.**` / `> **D.**` 各占一行。禁止横向表格、禁止四个选项挤在同一行、禁止省略任何选项、禁止在原题区标答案。',
          '2. 原题卡片之后另起一行写 `**作答结果**：你的答案 X · 正确答案 Y · 用时 无`，下一行必须单独写 `本题考察知识点：模块-一级-二级`（用知识点页词表，例如 `数量-最值问题-和定求极值`），再依次使用 `#### 草稿诊断`、`#### 考场解法`、`#### 下次动作`。题目依赖配图时写清看 PDF 哪一页，禁止凭文字编造图形。',
          '3. 错题或空题必须定位出错起点：审题遗漏、方法选择、推理、计算或检查。',
          '4. 正确题不能按结果直接跳过。方法绕远、或存在明显更快的考场解法时，必须展开 `#### 考场解法` 和 `#### 下次动作`。禁止用「确认通过」「没问题」打发，禁止省略 `#### 下次动作`。',
          '5. 只有做法干净且没有更好压法的对题，才一句「没问题，继续保持」，不要展开表扬。错题或空题必须展开。',
          '6. 建议必须是考场动作，例如先看什么、写哪一步、何时排除或何时放弃，禁止哈利波特、黑暗王子、黑魔法等包装。',
          '7. 确认是独立的新考点时，按 knowledge-point-extension.md 登记，并在该标签后注明「（新补录）」。',
          '8. 最后一题讲完后必须另起 `### 本场结语`，只针对这一场，不要戛然而止。依次写 `#### 做得好的`、`#### 做得不好的`、`#### 以后怎么改`。`做得好的` 只列可复现的动作和题号，口吻是严师：标准严、态度也严、讲解仍耐心；低级失误就直说，禁止浮夸夸赞。禁止空话和知识点总表。建议仍是考场动作。',
          '严师驱动规约：目标是公考得分，不是证明用户很努力。时长、吃苦和自我评价不算掌握证据，只看正确率、用时、草稿动作和能否复现。对高频、可避免、直接造成失分且能靠标准动作纠正的错误，明确说“这一步不该错/本场必须纠正”；按“判定→出错起点→唯一标准动作→下一次验收证据”输出。重复犯同一错误时减少安慰，安排最短针对性复做；不布置与提分无关的苦工。只批评行为，不攻击人格；表扬只给有证据、可复现且有分数价值的动作。',
          '9. 资料分析同样一题一题讲，但按材料成套：先 `### 材料一`，用 `> **材料**` 完整放上该篇文字/表/图，不要每题重复整篇材料；接着连续复盘该篇下的 5 道题，每题仍是 `> **原题**`（只放问句和选项）→ 作答结果 → `#### 草稿诊断` → `#### 考场解法` → `#### 下次动作`。第 5 题讲完再放 `### 材料二` 及下五题。禁止把 20 题拆散穿插，禁止省略材料。',
          '',
        ].join('\n')
      : '';
    const reviewLead = review?.kind === 'practice'
      ? practiceReviewLead
      : review?.kind === 'upload'
        ? uploadReviewLead
        : examReviewLead;
    const audioLabel = audio ? audioLabelOf(audio.sec) : '';

    const projectRoot = hermesContextRef.current?.project_root || '/home/ubuntu/ExamSystem';
    const masteryNudge = review?.kind === 'practice' && review?.profileReviewed
      ? [
          'Keep all mastery/profile bookkeeping completely silent and internal. Never mention commands, database writes, tool output, mastery scores, confidence, sample counts, or bookkeeping summaries in the final answer unless I explicitly ask for statistics.',
          `本场 AI 练题（practice_sessions.id=${review.id}）画像已封印。禁止调用 kaodian_profile.py，禁止写入 kaodian_profile / kaodian_events，禁止改 questions.tags。本轮只做分析。`,
        ].join('\n')
      : review?.kind === 'practice'
      ? [
          'Keep all mastery/profile bookkeeping completely silent and internal. Never mention commands, database writes, tool output, mastery scores, confidence, sample counts, or bookkeeping summaries in the final answer unless I explicitly ask for statistics.',
          ...(review.audit ? ['This is a review audit. Compare this retake with the first review requirements; blank answers are explicit evidence of not knowing and must be recorded as 0.'] : []),
          ...(review.audit
            ? [
                '审核写入画像时，1 只表示本次重做已经用独立、可复现的方法通过首次复盘要求；仅仅看过解析、记住答案、蒙对或过程不完整，一律写 0。',
                '审核结论必须以本次重做证据为主，首次复盘只提供待验收的要求；不能因为首次复盘写得完整，就替本次重做判定掌握。',
              ]
            : []),
          `本场（practice_sessions.id=${review.id}）尚未封存。必须逐题结合答案、用时、草稿实图和过程质量判断“可复现掌握”后写入画像。`,
          '每道有作答的题都要写一次；答对但蒙对、方法不稳、步骤不可复现，结果填 0；只有答案正确且过程可靠可复现才填 1。',
          '空题不用你写：交卷时系统已按停留时长自动记为不会（盯满 1 分钟算满权重证据，几秒翻过的不算）。你只写有作答的题，空题仍要在正文里讲。',
          '权重是证据可信度，不是分数：完整答案+草稿+过程清楚用 1.0；缺草稿或过程只能部分判断用 0.5-0.8；明显猜测、绕路或证据不足用 0.3-0.5。权重必须在 0.1-1.5。',
          `逐题使用：python3 ${projectRoot}/scripts/kaodian_profile.py --record '模块-一级-二级' '模块' '一级' <0或1> <用时毫秒> practice --weight <0.1-1.5> --practice-id ${review.id} --item <题目id>`,
          '题目id、模块、一级和用时严格取报告表格；没有明确知识点或证据不足以判断时不要编造标签。命令返回 already recorded 就跳过。',
          `所有可判断题写完后，且仅在写入命令均成功后执行：python3 ${projectRoot}/scripts/kaodian_profile.py --seal-practice ${review.id}`,
          '封存有覆盖率闸门：还有题没写证据时它会打印 refused 并列出缺的题目id，这时补齐再封，不要用 --force 绕过。',
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
    const msgId = uid();

    // 先把界面切到"发送中"：气泡上屏、输入框清空、按钮换成停止。
    // 图片上传要好几秒，这期间一点反馈都没有的话用户只会以为没发出去
    setBanner('');
    setMessages((prev) => [
      ...prev,
      {
        id: msgId, role: 'user',
        content: text || audioLabel || '',
        streaming: false,
        tools: [], thinking: '',
        images: images.filter((i) => !i.hidden && i.mime?.startsWith('image/')).map((i) => i.dataUrl),
        attachments: images.filter((i) => !i.hidden).map((i) => ({ name: i.name, mime: i.mime, dataUrl: i.dataUrl })),
        audio: audio?.dataUrl || null,
        audioSec: audio?.sec > 0 ? Math.round(audio.sec) : (parseAudioLen(audioLabel) || null),
        hadAudio: !!audio,
        sentAt: Date.now(),
        storedSessionId: activeStoredIdRef.current,
        review: review ? {
          id: review.id,
          kind: review.kind,
          name: review.name,
          title: review.title,
          label: review.label,
          path: review.path || null,
          audit: Boolean(review.audit),
          auditSourcePath: review.auditSourcePath || null,
          profileReviewed: Boolean(review.profileReviewed),
        } : null,
      },
    ]);
    setInput('');
    setPendingImages([]);
    setPendingAudio(null);
    setPendingReview(null);
    setBusy(true);
    setWaitSec(0);
    setStatus(audio ? '上传录音' : (images.length > 0 ? '上传附件' : '已发送'));
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
    const deliver = async (target, outbound) => {
      for (const img of images) {
        const isPdf = img.mime === 'application/pdf' || /\.pdf$/i.test(img.name || '');
        const isImage = img.mime?.startsWith('image/');
        if (isPdf) {
          await gw.request('pdf.attach', {
            session_id: target,
            content_base64: img.dataUrl,
            filename: img.name,
          });
        } else if (isImage) {
          await gw.request('image.attach_bytes', {
            session_id: target,
            content_base64: img.dataUrl,
            filename: img.name,
          });
        } else {
          await gw.request('file.attach', {
            session_id: target,
            data_url: img.dataUrl,
            name: img.name,
          });
        }
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
        text: outbound || (audio ? '请听这段口述' : '请查看我上传的附件'),
      });
    };

    try {
      const spokenText = text.trim();
      const voiceLead = audio
        ? [
            '下面附了口述录音，请直接听，不要转写成文字，不要让用户改成打字。',
            '录音才是本轮指令。不要把时长标签当作用户正文。',
            // 录音本身不落库，会话一被回收就永远听不到了；而它留在运行时里，
            // 之后每一轮都要整包重传。所以听完先留一份文字底稿，再把音频丢掉。
            `听完之后、回答之前，先把这段口述写成笔记存到 ${voiceNotePath(projectRoot)}（用 write_file，一次写完，不要先 ls 或读目录）。`,
            '笔记用四段：`## 我说了什么`（逐条列要点，保留具体数字、题号和人名）、`## 语气与状态`（急躁/困惑/有把握/疲惫，以及听出来的犹豫或强调）、`## 你要做的事`（据此要执行的动作）、`## 值得长期记住的`（只写关于我这个人的稳定事实：目标、时间约束、学习习惯、明确偏好或纠正；没有就写"无"）。',
            '笔记控制在 600 字内，写完直接进入正常回答，不要向我复述笔记内容。',
            '如果这段口述里有该长期记住的事实，用 memory 工具写进 user 画像；只记稳定的，不记一次性情绪和进度流水。',
            '口吻：严师。标准严、态度也严、讲解仍耐心。对高频、可避免、直接造成失分的错误明确说“这题不该错/这一步必须纠正”，再把标准动作讲透；只批评行为，不攻击人格。禁止浮夸夸赞。草稿对了只说这一步对，并给下一次验收标准。',
            '若录音要你根据快照选定考点并出题：听完后立刻后台调用出题脚本，题量和考点以录音为准（说10道就10道；说按你刚定的考点出，就出那个考点）。不要先只回复建议再等下一轮。',
            '失败把脚本原文告诉用户。不要 ls / search_files / 自己写 questions.json。',
          ].join('\n')
        : '';
      const persistText = spokenText || audioLabel;
      const submittedText = review || persistText
        ? `[USER_MESSAGE]\n${persistText}\n[/USER_MESSAGE]`
        : '';
      const wantsQuiz = /\u7ed9\u6211\u51fa|\u5e2e\u6211\u51fa|\u51fa(?:[\u4e00-\u9fa5\d\u51e0]+)(?:\u9053|\u4e2a)?\u9898|\u8003\u8003\u6211|\u6765(?:[\u4e00-\u9fa5\d\u51e0]+)(?:\u9053|\u4e2a)?\u9898|\u5237\u9898|AI\s*\u7ec3\u9898|\u4e13\u9879\u7ec3\u9898|\u751f\u6210.{0,6}\u7ec3\u4e60|(?:\u6211\u8981|\u6211\u60f3|\u7ee7\u7eed|\u9488\u5bf9).{0,12}\u7ec3|(?:来|出|再来|各来|各出)\s*[\d\u4e00-\u9fa5]{1,3}\s*(?:\u9053|\u4e2a)(?![\u5e74\u6708\u5468])/.test(spokenText);
      const wantsInlineQuiz = /(?:\u76f4\u63a5|\u5c31).{0,8}(?:\u804a\u5929|\u8fd9\u91cc).{0,8}(?:\u53d1|\u51fa|\u505a).{0,4}\u9898/.test(spokenText);
      const quizScript = `python3 ${projectRoot}/scripts/quiz_lite.py --module '<模块>' --tag '<规范主标签>' --count <题量> --batch-id '<YYYYMMDD_hermes_考点_序号>'`;
      const figureQuizScript = `python3 ${projectRoot}/scripts/quiz_generator.py --module '<模块>' --tag '<规范主标签>' --count <题量> --batch-id '<YYYYMMDD_hermes_考点_序号>'`;
      const quizBlueprint = `python3 ${projectRoot}/scripts/quiz_lite.py --module '<模块>' --batch-id '<YYYYMMDD_hermes_考点_序号>' --blueprint '{"slots":[{"tag":"<规范主标签A>","count":3,"difficulty":"mid"},{"tag":"<规范主标签B>","count":3,"difficulty":"hard"},{"tag":"<规范主标签C>","count":4,"difficulty":"hard"}]}'`;
      const quizSlotHint = [
        `If the user wants several 考法/题型 in one batch, a difficulty mix, or a split like 3+3+4, use the blueprint form instead of a single --tag (they are mutually exclusive): ${quizBlueprint}`,
        'Slots map to item order. Each slot needs tag+count; difficulty is optional (easy/mid/hard); all slots must share one module; the total still has to be 1-15. Choosing the slots, their counts and the difficulty spread is your call. A mix (e.g. 4 easy + 3 mid + 3 hard, batch_id …_ladder_01) is allowed; the AI练题 card will be tagged ladder, not the first slot.',
        `科学推理或判断推理-图形推理/空间类必须使用重型带图管线：${figureQuizScript}；不要用 quiz_lite，因为它会拒绝或剥离图片。Gemini 必须按知识点返回结构化图形规格，由程序渲染并经过视觉质检。`,
        'A slot may also carry "brief": free text (<=600 chars) that is YOUR drafting instruction for this batch. The script already injects the solver-canon 固定识别/考场步骤/禁止 for that 考法, so use brief for what the canon cannot know: this run\'s emphasis, degenerate patterns to avoid, current-exam intel you looked up, or a difficulty demand the user just voiced. brief may only tighten constraints, never relax the gate, and must never contain stems, answers or numbers.',
        '一个一级知识点下的不同考法是不同的二级标签，只传一个标签整批就只有那一个考法。最值问题有四个独立考法标签：和定最值与构造 / 最不利原则与抽屉 / 反向构造与多集合最值 / 二次函数与乘积极值，不要用一个标签笼统覆盖。',
        'quiz_lite 出稿后会跑两个独立审核：盲解官看不到答案自己重做一遍，考官查难度档、考法归属、公考风格与解析可复算。只有不合格的那几道会被退回重出，已通过的题不动，所以返回的 rounds 里可能有多轮，这是正常的。',
      ].join('\n');
      const quizNudge = wantsQuiz && !wantsInlineQuiz
        ? [
            'This is a question-generation request. Deliver only to ExamSystem AI Practice.',
            'Do not write questions.json, do not skill_view long references, do not run generation_gate or import-batch yourself.',
            'First tool call must be the script below. Do not ls, search_files, read_file, or sqlite first.',
            `Call exactly once, in the background with notify_on_complete (foreground terminal dies at 180s): ${quizScript}`,
            'workdir=/home/ubuntu/ExamSystem. If the user names a knowledge point, --tag must be that canonical 模块-一级-二级. Count is what they asked; default 5 if unnamed. Do not emit a 20-question daily paper.',
            quizSlotHint,
            'Wait for the JSON. Success: report only batch_id and imported count. Failure: report the script message. Never draft questions yourself.',
          ].join('\n')
        : audio && !review
          ? [
              `If the recording asks to generate questions, call once in the background with notify_on_complete: ${quizScript}`,
              'Use the knowledge point and count from the recording (including a point you just recommended from the snapshot). Do not explore the repo first.',
              quizSlotHint,
            ].join('\n')
          : '';
      const needsLearnerSnapshot = Boolean(review || audio || wantsQuiz
        || /今天练什么|学习计划|我的情况|薄弱|掌握|错题|复盘|省考|行测|申论|攻克|知识点|推荐|遗忘|我想学/.test(spokenText));
      let learnerNudge = '';
      if (needsLearnerSnapshot) {
        try {
          const snapshot = await api('/api/learner/snapshot?compact=1');
          if (snapshot?.compact) {
            learnerNudge = [
              '[LEARNER_SNAPSHOT — SYSTEM FACTS]',
              snapshot.compact,
              'Use this database snapshot as the source of truth for performance and recency. Do not infer mastery from conversational memory.',
              'If the recording asks you to pick a point from this snapshot and then generate, that choice is the named knowledge point.',
              'If a target is listed under 刚练过不宜主攻, or its family was seen within 1 day, and the user did not name it (in text or in the recording), do not make it the main batch; at most mix 2 structural variants. Permutation subskills share one family; date and cycle share one family. Never regenerate the same scenario with swapped numbers.',
              'If the user names a module such as 数量, only recommend from that module in 下一步候选, still skip 刚练过不宜主攻 unless they named that family. Recency, 到期回捞 and mastery already encode the 21-day forgetting curve; do not invent a separate memory of what is due.',
              '[/LEARNER_SNAPSHOT]',
            ].join('\n');
          }
        } catch { /* 快照失败不应阻断用户消息，Hermes skill 仍可直接查库 */ }
      }
      const coachToneNudge = needsLearnerSnapshot && !review
        ? [
            '【严师驱动】公考建议只按预期得分收益排序：优先处理高频、可避免、能靠标准动作纠正的失分；学习时长、吃苦和“我很努力”不算掌握证据。指出错误时按“判定→出错起点→唯一标准动作→下一次验收证据”，重复错误要安排最短针对性复做；只批评行为，不攻击人格；没有可复现证据就不表扬。',
          ].join('\n')
        : '';
      const outbound = [
        reviewLead,
        voiceLead,
        submittedText,
        learnerNudge,
        coachToneNudge,
        masteryNudge,
        quizNudge,
      ].filter(Boolean).join('\n');

      let target = sidRef.current;
      if (!target) {
        target = await acquireSession();
        sidRef.current = target;
        setSid(target);
      }

      setStatus(audio ? '上传录音' : (images.length > 0 ? '上传图片' : '已发送'));
      try {
        await deliver(target, outbound);
      } catch (err) {
        if (!isSessionGone(err)) throw err;
        // 会话被回收了，换一个新的重发一次。只重试一次：
        // 如果新会话也说 not found，那就是别的问题，不该无限重试
        setStatus('会话已过期，正在重连');
        const fresh = await acquireSession();
        sidRef.current = fresh;
        setSid(fresh);
        await deliver(fresh, outbound);
      }
      setStatus('已发送');
    } catch (err) {
      const dropped = /连接已断开|已关闭|尚未连接到/.test(err?.message || '');
      if (dropped) {
        sendingRef.current = false;
        setStatus('后台继续作答');
        return;
      }
      // 没送出去就别把气泡留在那儿膨胀已发送，内容还给输入框方便重发
      setBanner(`发送失败：${err.message}`);
      setWaitSec(0);
      setMessages((prev) => prev.filter((m) => m.id !== msgId));
      setInput((cur) => cur || text);
      setPendingImages((cur) => (cur.length > 0 ? cur : images));
      setPendingAudio((cur) => cur || audio);
      setPendingReview((cur) => cur || review);
      sendingRef.current = false;
      setBusy(false);
      setStatus('');
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

      const images = [];
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
      const auditSource = s.audit_of_session_id
        ? await api(`/api/practice/sessions/${s.audit_of_session_id}/md`).catch(() => null)
        : null;
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
        draftCount: images.length,
        total: Number(s.total || items.length || 0),
        profileReviewed: Boolean(s.profile_reviewed_at),
        audit: Boolean(s.audit_of_session_id),
        auditSourcePath: auditSource?.path || null,
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
    setAttaching(true);
    setBanner('');
    try {
      const context = await loadHermesContext();
      const uploadRoot = context?.upload_root;
      if (!uploadRoot) {
        setBanner('无法读取 ExamSystem 项目路径');
        return;
      }
      const abs = `${uploadRoot.replace(/\/+$/, '')}/${date}/${typ}/${name}`;
      const title = String(name).replace(/\.pdf$/i, '');
      setPendingReview({
        id: `${date}/${typ}/${name}`,
        kind: 'upload',
        path: abs,
        name,
        title,
        label: `资料上传 · ${date} · ${title}`,
      });
      setShowUploads(false);
      stickToBottom.current = true;
      setTimeout(() => taRef.current?.focus(), 0);
    } catch (err) {
      setBanner(`带上资料失败：${err.message}`);
    } finally {
      setAttaching(false);
    }
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

  const addAttachmentFiles = (fileList) => {
    const files = [...(fileList || [])];
    if (files.length === 0) {
      setBanner('没有选中文件');
      return false;
    }
    for (const file of files) {
      const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
      const isImage = file.type.startsWith('image/');
      const max = isPdf ? PDF_MAX_BYTES : isImage ? IMAGE_MAX_BYTES : FILE_MAX_BYTES;
      if (file.size > max) {
        setBanner(`${isPdf ? 'PDF' : isImage ? '图片' : '文件'}过大（上限 ${max / 1024 / 1024}MB）`);
        continue;
      }
      const reader = new FileReader();
      reader.onload = () => {
        setPendingImages((prev) => [
          ...prev,
          {
            id: uid(),
            name: file.name || (isPdf ? 'attachment.pdf' : 'pasted.png'),
            mime: isPdf ? 'application/pdf' : (file.type || 'application/octet-stream'),
            dataUrl: String(reader.result),
          },
        ]);
      };
      reader.onerror = () => setBanner(`读取文件失败：${file.name || '未命名文件'}`);
      reader.readAsDataURL(file);
    }
    return true;
  };

  const pickAttachment = () => filePickRef.current?.click();

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
    addAttachmentFiles(e.dataTransfer?.files);
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

  const jumpMessages = messages.filter((message) => (
    message.role === 'user'
      && (message.review || message.content?.trim() || message.attachments?.length || message.images?.length || message.audio || message.audioSec)
  ));

  const updateActiveMessage = () => {
    const host = scrollRef.current;
    if (!host) return;
    const pivot = host.getBoundingClientRect().top + 48;
    let active = null;
    for (const message of jumpMessages) {
      const node = messageRefs.current.get(message.id);
      if (node && node.getBoundingClientRect().bottom >= pivot) {
        active = message.id;
        break;
      }
    }
    if (active != null) setActiveMessageId(active);
  };

  const jumpToMessage = (messageId) => {
    const node = messageRefs.current.get(messageId);
    if (!node) return;
    node.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setActiveMessageId(messageId);
    stickToBottom.current = false;
  };

  // 刻度的磁吸放大：离指针越近的刻度越长，做出 Codex 那种波浪。
  // iPad 上没有 hover，所以按住轨道滑动即可预览，松手跳转。
  const measureTicks = () => {
    const rail = railRef.current;
    const centers = rail
      ? [...rail.querySelectorAll('[data-jump-tick]')].map((el) => el.offsetTop + el.offsetHeight / 2)
      : [];
    setTickCenters(centers);
    return centers;
  };

  const focusRailAt = (clientY, measured = tickCenters) => {
    const rail = railRef.current;
    const centers = measured;
    if (!rail || centers.length === 0) return null;
    const y = clientY - rail.getBoundingClientRect().top;
    let index = 0;
    for (let i = 1; i < centers.length; i += 1) {
      if (Math.abs(centers[i] - y) < Math.abs(centers[index] - y)) index = i;
    }
    setRailFocus({ y, index });
    return index;
  };

  const tickWidth = (index) => {
    const center = tickCenters[index];
    if (!railFocus || center == null) return TICK_MIN_W;
    const distance = Math.abs(center - railFocus.y);
    return TICK_MIN_W + TICK_LIFT * Math.exp(-(distance * distance) / (2 * TICK_FALLOFF * TICK_FALLOFF));
  };

  const messagePreview = (message) => {
    if (message.review?.label) return message.review.label;
    const raw = message.content || '';
    if (raw.trim()) {
      return String(raw).replace(/[#>*_`]/g, '').replace(/\s+/g, ' ').trim();
    }
    const names = (message.attachments || []).map((file) => file.name).filter(Boolean);
    return names.join('、') || (message.audio || message.audioSec ? '我的语音' : '我的消息');
  };

  // 导航卡片第二行：这条提问后 Hermes 的回答开头，方便只看一眼就认出是哪一轮
  const replyPreview = (messageId) => {
    const from = messages.findIndex((message) => message.id === messageId);
    if (from < 0) return '';
    for (let cursor = from + 1; cursor < messages.length; cursor += 1) {
      const message = messages[cursor];
      if (message.role === 'user') break;
      if (message.role !== 'assistant') continue;
      const text = visibleAssistantReply(message.content || '')
        .replace(/```[\s\S]*?```/g, ' ')
        .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
        .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
        .replace(/[#>*_`]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      if (text) return text;
    }
    return '';
  };

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    updateActiveMessage();
  };

  const practiceSessionForMessage = (messageId) => {
    const index = messages.findIndex((message) => message.id === messageId);
    const from = index < 0 ? messages.length - 1 : index;
    for (let cursor = from; cursor >= 0; cursor -= 1) {
      const message = messages[cursor];
      if (message.role === 'user' && message.review?.kind === 'practice' && message.review.id) {
        return Number(message.review.id);
      }
    }
    return null;
  };

  // 铅笔草稿只给 AI 练题复盘：粉笔 PDF / 录屏复盘没有当时草稿，盖一层画布只会把题面错位。
  const scratchIdForMessage = (messageId) => (
    practiceSessionForMessage(messageId) ? String(messageId) : undefined
  );

  // 上下文占用。口径完全用网关的：context_used 是当前窗口实际占用，
  // 只有压缩器报出真实值时才有——拿不到就不显示，不编一个 0% 出来。
  const contextGauge = (() => {
    const used = Number(usage?.context_used);
    const max = Number(usage?.context_max);
    if (!Number.isFinite(used) || !Number.isFinite(max) || used <= 0 || max <= 0) return null;
    const percent = Math.max(0, Math.min(100, Math.round((used / max) * 100)));
    // 语音是唯一会在后续每轮整包重传的附件，而 token 百分比不会告诉你负担来自哪，
    // 所以把它单独点出来。时长取自消息上的语音标签，resume 之后依然在。
    const voices = messages.filter((m) => m.role === 'user' && (m.audio || m.audioSec > 0 || m.hadAudio));
    const voiceSec = voices.reduce((sum, m) => sum + (Number(m.audioSec) || 0), 0);
    return {
      percent,
      used,
      max,
      level: percent >= 75 ? 'is-high' : percent >= 50 ? 'is-mid' : '',
      detail: [
        `上下文占用 ${percent}%（${used.toLocaleString()} / ${max.toLocaleString()} tokens）`,
        voices.length ? `本会话 ${voices.length} 段语音，共 ${fmtMinutes(voiceSec)}；语音会在之后每一轮整包重传` : '',
        usage?.compressions ? `已自动压缩 ${usage.compressions} 次` : '',
        percent >= 75 ? '偏重了：可以开新会话，或让它先压缩上下文' : '',
      ].filter(Boolean).join('\n'),
    };
  })();

  const connLabel = {
    idle: '未连接', connecting: '连接中…', open: '已连接', closed: '已断开', error: '连接失败',
  }[connState] || connState;
  const connColor = {
    open: 'bg-[#4caf50]', connecting: 'bg-[#ffa726]', error: 'bg-[#ef5350]', closed: 'bg-[#ef5350]',
  }[connState] || 'bg-[#bbb]';

  return (
    <div className={`flex h-full overflow-hidden relative ${
      fullscreen || pickerMode === 'sheet' ? 'gap-0' : 'gap-4 animate-fadeIn'
    }`}>
      <HermesSidebar
        overlay={overlayPicker}
        touch={pickerMode === 'sheet'}
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
        className={`relative flex-1 flex flex-col overflow-hidden min-w-0 ${
          fullscreen ? 'rounded-none border-0 bg-white' : 'rounded-3xl bg-white/70 border border-black/5'
        }`}
      >
        <div className="flex items-center gap-2 px-3 sm:px-5 py-3 border-b border-black/5 min-w-0">
          <div className="flex items-center gap-2 shrink-0">
            {(pickerMode === 'sheet' || !sidebarOpen) && (
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                className={pickerMode === 'sheet'
                  ? 'flex items-center gap-1.5 min-h-11 px-3 rounded-xl bg-[#f4f0e6] border border-[#e8d5b0] text-[#1a1a1a] font-bold text-[13px]'
                  : 'p-1.5 rounded-lg text-[#999] hover:text-[#1a1a1a] hover:bg-black/5'}
                title="会话列表"
                aria-label="打开会话列表"
              >
                <MessageSquare size={18} />
                {pickerMode === 'sheet' ? <span>会话</span> : null}
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
              <span className="flex items-center space-x-1.5 text-[15px] font-bold text-[#6b5428] truncate max-w-[28vw]">
                <Loader2 size={15} className="animate-spin shrink-0" />
                <span className="truncate">{status}</span>
              </span>
            )}
          </div>

          <div className="flex items-center space-x-1.5 min-w-0 overflow-x-auto [scrollbar-width:none]">
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

        {jumpMessages.length > 0 && (
          <div className="hermes-jumprail">
            <nav
              ref={railRef}
              className={`hermes-jumprail-ticks ${railFocus ? 'is-live' : ''} ${
                jumpMessages.length > 30 ? 'is-dense' : ''
              }`}
              aria-label="消息导航"
              onPointerEnter={(e) => {
                if (e.pointerType !== 'mouse') return;
                focusRailAt(e.clientY, measureTicks());
              }}
              onPointerMove={(e) => {
                if (e.pointerType === 'mouse' || railScrub) focusRailAt(e.clientY);
              }}
              onPointerLeave={(e) => {
                if (e.pointerType === 'mouse' && !railScrub) setRailFocus(null);
              }}
              onPointerDown={(e) => {
                if (e.pointerType === 'mouse') return;
                focusRailAt(e.clientY, measureTicks());
                setRailScrub(true);
                e.currentTarget.setPointerCapture?.(e.pointerId);
              }}
              onPointerUp={(e) => {
                if (!railScrub) return;
                setRailScrub(false);
                const index = focusRailAt(e.clientY);
                if (index != null) jumpToMessage(jumpMessages[index].id);
                setRailFocus(null);
              }}
              onPointerCancel={() => {
                setRailScrub(false);
                setRailFocus(null);
              }}
              // 刻度只有 2px 高，鼠标不必精确命中：点轨道上任意位置都跳到最近那条
              onClick={() => {
                const target = railFocus && jumpMessages[railFocus.index];
                if (target) jumpToMessage(target.id);
              }}
            >
              {jumpMessages.map((message, index) => (
                <button
                  key={message.id}
                  data-jump-tick=""
                  type="button"
                  onClick={() => jumpToMessage(message.id)}
                  onFocus={() => {
                    const center = measureTicks()[index];
                    if (center != null) setRailFocus({ y: center, index });
                  }}
                  onBlur={() => { if (!railScrub) setRailFocus(null); }}
                  style={{ width: tickWidth(index) }}
                  className={`hermes-jump-tick ${activeMessageId === message.id ? 'is-active' : ''} ${
                    railFocus?.index === index ? 'is-focus' : ''
                  }`}
                  aria-label={`跳到第 ${index + 1} 条消息：${messagePreview(message).slice(0, 40)}`}
                />
              ))}

              {railFocus && jumpMessages[railFocus.index] ? (
                <aside className="hermes-jump-card" style={{ top: tickCenters[railFocus.index] ?? railFocus.y }}>
                  <p className="hermes-jump-card-title">
                    <span className="hermes-jump-card-index">{railFocus.index + 1}</span>
                    {messagePreview(jumpMessages[railFocus.index]).slice(0, 90) || '我的消息'}
                  </p>
                  {replyPreview(jumpMessages[railFocus.index].id) ? (
                    <p className="hermes-jump-card-reply">
                      {replyPreview(jumpMessages[railFocus.index].id).slice(0, 150)}
                    </p>
                  ) : null}
                </aside>
              ) : null}
            </nav>
          </div>
        )}

        <div ref={scrollRef} onScroll={onScroll} className="hermes-scroll flex-1 overflow-y-auto">
          <div className="px-5 py-4 space-y-4" style={{ fontSize: `calc(15px * ${fontScale / 100})` }}>
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center px-6">
              <div className="w-12 h-12 rounded-2xl bg-[#1a1a1a] flex items-center justify-center text-white mb-3">
                <MessageSquare size={20} />
              </div>
              <p className="text-sm font-black tracking-tight text-[#1a1a1a]">跟 Hermes 聊</p>
              <p className="mt-1.5 text-[11px] text-[#999] leading-relaxed max-w-xs">
                {pickerMode === 'sheet'
                  ? '点左上角「会话」查看以前的对话，或直接在下方开始新的一聊。'
                  : 'Markdown、代码、LaTeX 公式都能正常显示。左侧可以续接之前的对话。'}
              </p>
              {pickerMode === 'sheet' && (
                <button
                  type="button"
                  onClick={() => setSidebarOpen(true)}
                  className="mt-4 min-h-11 px-5 rounded-2xl bg-[#1a1a1a] text-white text-sm font-bold"
                >
                  查看会话
                </button>
              )}
            </div>
          )}

          {messages.map((m) => {
            const reply = m.role === 'assistant' ? visibleAssistantReply(m.content) : m.content;
            const showUserText = Boolean(m.content) && !isAudioLabel(m.content) && !m.review;
            if (
              m.role === 'assistant'
              && !m.streaming
              && !reply
              && !(showThinking && m.thinking)
              && !(m.tools?.length)
            ) return null;
            return (
            <div
              key={m.id}
              ref={(node) => {
                if (node) messageRefs.current.set(m.id, node);
                else messageRefs.current.delete(m.id);
              }}
              className={m.role === 'user' ? 'flex justify-end scroll-mt-2' : 'scroll-mt-2'}
            >
              {m.role === 'notice' ? (
                <BackgroundNotice notice={m.notice} />
              ) : m.role === 'user' ? (
                <div className="max-w-[78%] flex flex-col items-end gap-1.5">
                  {m.sentAt ? (
                    <span className="text-[0.68em] tabular-nums text-[#999] leading-none pr-1">
                      {fmtBubbleTime(m.sentAt)}
                    </span>
                  ) : null}
                  {(m.audio || m.audioSec > 0 || m.hadAudio || isAudioLabel(m.content)) && (
                    <VoiceBubble
                      src={m.audio}
                      sec={m.audioSec > 0 ? m.audioSec : (parseAudioLen(m.content) || 0)}
                      onDuration={(s) => setMessages((prev) => prev.map((x) => (
                        x.id === m.id ? { ...x, audioSec: s } : x
                      )))}
                    />
                  )}
                  {(m.images?.length > 0 || m.attachments?.length > 0 || m.review || showUserText) && (
                    <div className="px-4 py-2.5 rounded-2xl rounded-br-md bg-[#1a1a1a] text-white">
                      {m.images?.length > 0 && (
                        <div className={`flex flex-wrap gap-1.5 ${m.review || showUserText ? 'mb-2' : ''}`}>
                          {m.images.map((src, i) => (
                            <img key={i} src={src} alt="" className="w-20 h-20 object-cover rounded-lg" />
                          ))}
                        </div>
                      )}
                      {m.attachments?.some((file) => !file.mime?.startsWith('image/')) && (
                        <div className="mb-2 flex items-center gap-1.5 text-[0.75em] font-bold text-[#f2e4c4]">
                          <FileText size="1em" />
                          <span className="truncate">{m.attachments.filter((file) => !file.mime?.startsWith('image/')).map((file) => file.name).join('、')}</span>
                        </div>
                      )}
                      {m.review && (
                        <div className={showUserText ? 'mb-2' : ''}>
                          <ReviewChip review={m.review} onOpen={openReviewPreview} dark />
                        </div>
                      )}
                      {showUserText ? (
                        <p className="text-[1em] whitespace-pre-wrap break-words leading-relaxed">{m.content}</p>
                      ) : null}
                    </div>
                  )}
                </div>
              ) : (
                <div className="max-w-[92%]">
                  <div className="flex items-center space-x-1.5 mb-1.5">
                    <div className="w-[1.07em] h-[1.07em] rounded-md bg-[#2c261c] flex items-center justify-center text-[0.6em] font-black text-white">
                      ⚕
                    </div>
                    <span className="text-[0.68em] font-black uppercase tracking-widest text-[#bbb]">Hermes</span>
                    {reply && (
                      <button
                        type="button"
                        onClick={() => setPopout((cur) => (
                          cur?.id === m.id
                            ? null
                            : {
                                id: m.id,
                                content: reply,
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
                        <PictureInPicture2 size="0.8em" />
                      </button>
                    )}
                  </div>

                  {showThinking && m.thinking && (
                    <details className="mb-2 rounded-xl bg-black/[0.02] border border-black/5 overflow-hidden">
                      <summary className="px-3 py-1.5 cursor-pointer text-[0.68em] font-black uppercase tracking-widest text-[#999] hover:bg-black/[0.03]">
                        思考过程
                      </summary>
                      <pre className="px-3 pb-2 text-[0.75em] text-[#666] whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                        {m.thinking}
                      </pre>
                    </details>
                  )}

                  {m.streaming && (
                    <ToolCard tool={m.tools?.[m.tools.length - 1]} />
                  )}

                  {(reply || !m.streaming) && (
                    <MarkdownMessage
                      content={reply}
                      streaming={m.streaming}
                      scratchId={popout?.id === m.id ? undefined : scratchIdForMessage(m.id)}
                      practiceSessionId={practiceSessionForMessage(m.id)}
                    />
                  )}
                </div>
              )}
            </div>
            );
          })}
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
            /* 输入区不跟随正文缩放，这里钉回 15px，em 才和 100% 时一致 */
            <div className="flex flex-wrap gap-2 mb-2" style={{ fontSize: '15px' }}>
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
                  {!img.mime?.startsWith('image/') ? (
                    <div className="w-40 h-14 rounded-lg border border-black/10 bg-black/[0.04] px-2 pr-7 flex items-center gap-2 text-[11px] font-bold text-[#6b5428]">
                      <FileText size={16} className="shrink-0" />
                      <span className="truncate">{img.name}</span>
                    </div>
                  ) : (
                    <img src={img.dataUrl} alt={img.name || ''} className="w-14 h-14 object-cover rounded-lg border border-black/10" />
                  )}
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
            <div className="flex items-center justify-center gap-2 mb-2" style={{ fontSize: '15px' }}>
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
              ref={filePickRef}
              type="file"
              accept="*/*"
              multiple
              className="hidden"
              onChange={(e) => {
                addAttachmentFiles(e.target.files);
                e.target.value = '';
              }}
            />
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
              className="hermes-textarea flex-1 px-4 py-3 rounded-2xl bg-[#e8d5b0]/35 border border-black/10 text-[15px] resize-none outline-none focus:border-[#6b5428] transition-colors"
            />
            <button
              type="button"
              onClick={pickAttachment}
              disabled={busy || attaching || recording}
              title="添加图片或 PDF"
              aria-label="添加图片或 PDF"
              className="p-3 rounded-2xl shrink-0 bg-white border border-black/10 text-[#1a1a1a] hover:bg-black/5 transition-colors disabled:opacity-30"
            >
              <Plus size={18} strokeWidth={2.5} />
            </button>
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
                data-hermes-send
                onClick={send}
                disabled={connState !== 'open' || recording || (!input.trim() && pendingImages.length === 0 && !pendingReview && !pendingAudio)}
                title="发送"
                className="p-3 rounded-2xl bg-[#1a1a1a] text-white disabled:opacity-30 hover:opacity-90 transition-opacity shrink-0"
              >
                <Send size={18} />
              </button>
            )}
          </div>

          <div className="mt-1.5 px-1 flex items-center gap-2">
            {!fullscreen && (
              <p className="text-[10px] text-[#ccc] flex items-center space-x-1 min-w-0">
                <ImageIcon size={9} />
                <span className="truncate">Hermes 拥有终端与文件权限，请谨慎发送指令</span>
              </p>
            )}
            {contextGauge && (
              <div className={`hermes-ctx ml-auto ${contextGauge.level}`} title={contextGauge.detail}>
                <span className="hermes-ctx-bar" aria-hidden="true">
                  <span style={{ width: `${contextGauge.percent}%` }} />
                </span>
                <span className="hermes-ctx-text">
                  {contextGauge.percent}% · {fmtTokens(contextGauge.used)}/{fmtTokens(contextGauge.max)}
                </span>
              </div>
            )}
          </div>
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
                scratchId={reviewPreview?.kind === 'practice' && reviewPreview?.id
                  ? `preview:${reviewPreview.id}`
                  : undefined}
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
          scratchId={popout.practiceSessionId ? String(popout.id) : undefined}
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

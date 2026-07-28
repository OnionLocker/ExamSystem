// Hermes 对话页
//
// 走 JSON-RPC over WebSocket 直连 Hermes 的 gateway（经 Express 代理），
// 与官方 dashboard 的 Chat 用的是同一套协议和同一个 agent，
// 因此这里能看到并续接微信、cron、CLI 的全部会话。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Send, Square, Plus, MessageSquare, Loader2, RefreshCw,
  Brain, Smartphone, CalendarClock, Terminal, X, Image as ImageIcon,
} from 'lucide-react';

import HermesGateway from './gateway.js';
import MarkdownMessage from './MarkdownMessage.jsx';
import ToolCard from './ToolCard.jsx';

// 会话来源 → 展示分组
const SOURCE_META = {
  weixin:  { label: '微信',     icon: Smartphone,    order: 0 },
  cron:    { label: '每日计划', icon: CalendarClock, order: 1 },
  tui:     { label: '本地',     icon: Terminal,      order: 2 },
  cli:     { label: '本地',     icon: Terminal,      order: 2 },
};
const sourceMeta = (s) => SOURCE_META[s] || { label: '其他', icon: MessageSquare, order: 3 };

let msgSeq = 0;
const uid = () => `m${++msgSeq}`;

const IMAGE_MAX_BYTES = 10 * 1024 * 1024;

const HermesChat = () => {
  const gwRef = useRef(null);
  const [connState, setConnState] = useState('idle');
  const [sessions, setSessions] = useState([]);
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
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const scrollRef = useRef(null);
  const stickToBottom = useRef(true);
  const taRef = useRef(null);
  // sid 的镜像：send/interrupt 等回调里要读最新值，又不想因此重建回调
  const sidRef = useRef(null);
  useEffect(() => { sidRef.current = sid; }, [sid]);

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

  const finishStreaming = useCallback(() => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || !last.streaming) return prev;
      const copy = prev.slice(0, -1);
      // 把仍标记为运行中的工具收尾，避免一直转圈
      const tools = (last.tools || []).map((t) => (t.done ? t : { ...t, done: true }));
      copy.push({ ...last, streaming: false, tools });
      return copy;
    });
    setBusy(false);
    setStatus('');
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
      gw.on('thinking.delta', (ev) => {
        const t = ev.payload?.text;
        if (t) appendThinking(t);
      }),
      gw.on('reasoning.delta', (ev) => {
        const t = ev.payload?.text;
        if (t) appendThinking(t);
      }),
      gw.on('message.start', () => setStatus('生成中')),
      gw.on('message.complete', finishStreaming),

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
        // 这里不能调用下面的 refreshSessions（TDZ：本 effect 先于它初始化），直接取一次
        setSessionsLoading(true);
        try {
          const res = await gw.request('session.list', {});
          if (!cancelled) setSessions(Array.isArray(res?.sessions) ? res.sessions : []);
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

  // ---------- 会话列表 ----------
  const refreshSessions = useCallback(async () => {
    const gw = gwRef.current;
    if (!gw) return;
    setSessionsLoading(true);
    try {
      const res = await gw.request('session.list', {});
      setSessions(Array.isArray(res?.sessions) ? res.sessions : []);
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

  const openSession = useCallback(async (stored) => {
    const gw = gwRef.current;
    if (!gw || busy) return;
    setBanner('');
    setStatus('载入会话');
    try {
      const res = await gw.request('session.resume', { session_id: stored.id, cols: 100 });
      sidRef.current = res.session_id;
      setSid(res.session_id);
      setActiveStoredId(stored.id);
      const hydrated = (res.messages || [])
        // tool 角色的历史条目没有可读文本，跳过；只还原对话本身
        .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.text)
        .map((m) => ({
          id: uid(), role: m.role, content: String(m.text),
          streaming: false, tools: [], thinking: '',
        }));
      setMessages(hydrated);
      stickToBottom.current = true;
    } catch (err) {
      setBanner(`打开会话失败：${err.message}`);
    } finally {
      setStatus('');
    }
  }, [busy]);

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
    } catch (err) {
      setBanner(`新建会话失败：${err.message}`);
    }
  }, [busy]);

  // ---------- 发送 ----------
  const send = useCallback(async () => {
    const gw = gwRef.current;
    const text = input.trim();
    if (!gw || busy) return;
    if (!text && pendingImages.length === 0) return;

    setBanner('');
    let target = sidRef.current;
    try {
      // 还没有活动会话就先开一个
      if (!target) {
        const res = await gw.request('session.create', { cols: 100, cwd: '/home/ubuntu' });
        target = res.session_id;
        sidRef.current = target;
        setSid(target);
      }

      // 图片先挂到会话上，再发文本
      for (const img of pendingImages) {
        await gw.request('image.attach_bytes', {
          session_id: target,
          content_base64: img.dataUrl,
          filename: img.name,
        });
      }

      const shown = text || '(图片)';
      setMessages((prev) => [
        ...prev,
        {
          id: uid(), role: 'user', content: shown, streaming: false,
          tools: [], thinking: '', images: pendingImages.map((i) => i.dataUrl),
        },
      ]);
      setInput('');
      setPendingImages([]);
      setBusy(true);
      setStatus('已发送');
      stickToBottom.current = true;

      await gw.request('prompt.submit', { session_id: target, text: text || '看看这张图片' });
    } catch (err) {
      setBanner(`发送失败：${err.message}`);
      setBusy(false);
      setStatus('');
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
      setBanner(`中断失败：${err.message}`);
    }
  }, [finishStreaming]);

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  // 粘贴图片
  const onPaste = (e) => {
    const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
    if (files.length === 0) return;
    e.preventDefault();
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
    <div className="flex h-full gap-4 animate-fadeIn overflow-hidden">
      {/* ── 会话列表 ── */}
      {sidebarOpen && (
        <div className="w-64 shrink-0 flex flex-col rounded-3xl bg-white/70 border border-black/5 overflow-hidden">
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
                className="p-1.5 rounded-lg text-[#999] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors lg:hidden"
              >
                <X size={13} />
              </button>
            </div>
          </div>

          <button
            onClick={newSession}
            disabled={busy}
            className="mx-3 mt-3 flex items-center justify-center space-x-2 px-3 py-2.5 rounded-xl bg-[#1a1a1a] text-[#fbc02d] font-bold text-xs disabled:opacity-40 hover:opacity-90 transition-opacity"
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
                      <button
                        key={s.id}
                        onClick={() => openSession(s)}
                        disabled={busy}
                        title={s.title || s.id}
                        className={`w-full text-left px-2.5 py-2 rounded-xl transition-colors disabled:opacity-50 ${
                          activeStoredId === s.id
                            ? 'bg-[#1a1a1a] text-[#fbc02d]'
                            : 'hover:bg-black/5 text-[#444]'
                        }`}
                      >
                        <div className="text-xs font-bold truncate">{s.title || '(无标题)'}</div>
                        <div className={`text-[10px] font-bold ${activeStoredId === s.id ? 'text-[#fbc02d]/60' : 'text-[#bbb]'}`}>
                          {s.message_count} 条
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── 对话区 ── */}
      <div className="flex-1 flex flex-col rounded-3xl bg-white/70 border border-black/5 overflow-hidden min-w-0">
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
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${connColor}`} />
            <span className="text-[10px] font-black uppercase tracking-widest text-[#999] shrink-0">
              {connLabel}
            </span>
            {status && (
              <span className="flex items-center space-x-1.5 text-[10px] font-bold text-[#fbc02d] truncate">
                <Loader2 size={10} className="animate-spin shrink-0" />
                <span className="truncate">{status}</span>
              </span>
            )}
          </div>

          <div className="flex items-center space-x-2 shrink-0">
            <button
              onClick={() => setShowThinking((v) => !v)}
              title="显示/隐藏思考过程"
              className={`flex items-center space-x-1 px-2 py-1 rounded-lg text-[10px] font-bold transition-colors ${
                showThinking ? 'bg-[#1a1a1a] text-[#fbc02d]' : 'text-[#999] hover:bg-black/5'
              }`}
            >
              <Brain size={11} />
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

        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center px-6">
              <div className="w-12 h-12 rounded-2xl bg-[#1a1a1a] flex items-center justify-center text-[#fbc02d] mb-3">
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
                    <div className="w-4 h-4 rounded-md bg-[#fbc02d] flex items-center justify-center text-[9px] font-black text-[#1a1a1a]">
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
                      <span>思考中…</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* ── 输入区 ── */}
        <div className="px-5 py-3 border-t border-black/5">
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
              placeholder={connState === 'open' ? 'Enter 发送，Shift+Enter 换行，可粘贴图片' : '等待连接…'}
              disabled={connState !== 'open'}
              className="flex-1 px-4 py-3 rounded-2xl bg-white border border-black/10 text-[15px] resize-none outline-none focus:border-[#fbc02d] transition-colors disabled:bg-black/[0.03] disabled:text-[#bbb]"
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
                className="p-3 rounded-2xl bg-[#1a1a1a] text-[#fbc02d] disabled:opacity-30 hover:opacity-90 transition-opacity shrink-0"
              >
                <Send size={18} />
              </button>
            )}
          </div>

          <p className="mt-1.5 px-1 text-[10px] text-[#ccc] flex items-center space-x-1">
            <ImageIcon size={9} />
            <span>Hermes 拥有终端与文件权限，请谨慎发送指令</span>
          </p>
        </div>
      </div>
    </div>
  );
};

export default HermesChat;

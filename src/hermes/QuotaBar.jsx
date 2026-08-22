// Hermes 顶栏的额度胶囊：并排显示 5 小时 / 本周剩余，点开看全部分组。
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Gauge, RefreshCw, AlertCircle, X } from 'lucide-react';
import { api } from '../api.js';

const REFRESH_MS = 120_000;
// 后端重启、网络抖一下都会失败一次，等满两分钟才重试太钝了，先短后长地追几次
const RETRY_BASE_MS = 8_000;

// 剩得多是好事，所以绿→黄→红对应充足→吃紧
const colorOf = (r) => (r > 0.5 ? '#22c55e' : r > 0.2 ? '#8d7348' : '#ff6b6b');
const pct = (r) => Math.round((r ?? 0) * 100);

const fmtReset = (iso) => {
  if (!iso) return '';
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return '';
  if (ms <= 0) return '即将重置';
  const mins = Math.floor(ms / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h >= 24) return `${Math.floor(h / 24)} 天 ${h % 24} 小时后重置`;
  if (h > 0) return `${h} 小时 ${m} 分后重置`;
  return `${m} 分后重置`;
};

const shortMail = (e) => String(e || '').split('@')[0];

const QuotaBar = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  // 存成对象而不是字符串：同样的错误连着发生时也要能触发重试
  const [err, setErr] = useState(null);
  const [fails, setFails] = useState(0);
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);
  const panelRef = useRef(null);
  const [panelPos, setPanelPos] = useState(null);

  const load = useCallback(async (fresh = false) => {
    setLoading(true);
    try {
      const d = await api(`/api/quota${fresh ? '?fresh=1' : ''}`);
      setData(d);
      setErr(null);
      setFails(0);
    } catch (e) {
      setErr({ msg: e?.message || '读取失败', at: Date.now() });
      setFails((n) => n + 1);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 放进定时器而不是直接调：effect 同步体里 setState 会多触发一轮渲染
    const run = () => { void load(); };
    const first = setTimeout(run, 0);
    const timer = setInterval(run, REFRESH_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [load]);

  // 失败后按 8s → 16s → 32s… 往上退，最多退到常规间隔
  useEffect(() => {
    if (!err) return undefined;
    const delay = Math.min(RETRY_BASE_MS * 2 ** Math.max(0, fails - 1), REFRESH_MS);
    const t = setTimeout(() => { void load(); }, delay);
    return () => clearTimeout(t);
  }, [err, fails, load]);

  // 点外面收起面板
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (boxRef.current?.contains(e.target)) return;
      if (panelRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    window.addEventListener('pointerdown', onDown);
    return () => window.removeEventListener('pointerdown', onDown);
  }, [open]);

  const accounts = data?.accounts || [];
  let worst = null;
  let headline = [];
  for (const a of accounts) {
    for (const g of a.groups || []) {
      for (const b of g.buckets || []) {
        if (b.remaining == null) continue;
        if (!worst || b.remaining < worst.remaining) {
          worst = { ...b, email: a.email, group: g.name };
          const h5 = (g.buckets || []).find((x) => x.window === '5h');
          const week = (g.buckets || []).find((x) => x.window === 'weekly');
          headline = [h5, week].filter((x) => x && x.remaining != null);
          if (headline.length === 0) headline = [b];
        }
      }
    }
  }

  const hasData = accounts.length > 0 && worst;

  useEffect(() => {
    if (!open || !boxRef.current) {
      setPanelPos(null);
      return undefined;
    }
    const place = () => {
      const r = boxRef.current.getBoundingClientRect();
      setPanelPos({ top: r.bottom + 8, right: Math.max(8, window.innerWidth - r.right) });
    };
    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, [open]);

  return (
    <div className="relative" ref={boxRef}>
      <button
        onClick={() => {
          const next = !open;
          setOpen(next);
          // 展开时如果正卡在错误上，别让人干等下一轮
          if (next && err) void load(true);
        }}
        title={hasData ? `${shortMail(worst.email)} · ${worst.group}` : '模型额度'}
        className={`flex items-center space-x-1.5 px-2 py-1 rounded-lg text-[10px] font-bold transition-colors ${
          open ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5 hover:text-[#1a1a1a]'
        }`}
      >
        <Gauge size={11} className={loading && !data ? 'animate-pulse' : ''} />
        {hasData ? (
          headline.map((b, i) => (
            <span key={b.id || b.window || i} className="flex items-center space-x-1">
              {i > 0 && <span className="opacity-30">·</span>}
              <span>{b.window === '5h' ? '5h' : b.window === 'weekly' ? '周' : b.label}</span>
              <span className="tabular-nums" style={{ color: open ? undefined : colorOf(b.remaining) }}>
                {pct(b.remaining)}%
              </span>
            </span>
          ))
        ) : (
          <span>额度</span>
        )}
      </button>

      {open && panelPos && createPortal(
        <div
          ref={panelRef}
          className="fixed w-[min(23rem,calc(100vw-1rem))] max-h-[70vh] overflow-y-auto rounded-2xl bg-white shadow-2xl shadow-black/10 border border-black/5 z-[9999] p-4"
          style={{ top: panelPos.top, right: panelPos.right }}
        >
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">CLIProxy</p>
              <h4 className="text-sm font-black italic">模型额度</h4>
            </div>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => load(true)}
                disabled={loading}
                title="强制刷新"
                className="p-1.5 rounded-lg text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-40"
              >
                <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              </button>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg text-[#999] hover:bg-black/5 hover:text-[#1a1a1a]"
              >
                <X size={12} />
              </button>
            </div>
          </div>

          {err && (
            <div className="flex items-start space-x-2 px-3 py-2 rounded-xl bg-[#fff4e5] text-[11px] font-bold text-[#8a5400]">
              <AlertCircle size={12} className="shrink-0 mt-0.5" />
              <span>
                {err.msg}
                <span className="block font-normal opacity-70 mt-0.5">正在自动重试…</span>
              </span>
            </div>
          )}

          {!err && accounts.length === 0 && (
            <p className="text-[11px] font-bold text-slate-400 py-6 text-center">
              {loading ? '正在读取…' : '没有找到 Antigravity 账号'}
            </p>
          )}

          <div className="space-y-4">
            {accounts.map((a) => (
              <div key={a.email} className="rounded-xl bg-[#e8d5b0]/50 p-3">
                <div className="flex items-center justify-between mb-2.5">
                  <span className="text-xs font-black truncate">{shortMail(a.email)}</span>
                  {a.plan && (
                    <span className="shrink-0 ml-2 px-2 py-0.5 rounded-full bg-[#1a1a1a] text-white text-[9px] font-black uppercase tracking-widest">
                      {a.plan}
                    </span>
                  )}
                </div>

                {a.error ? (
                  <p className="text-[10px] font-bold text-[#ff6b6b]">{a.error}</p>
                ) : (
                  <div className="space-y-3">
                    {(a.groups || []).map((g) => (
                      <div key={g.name}>
                        <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1.5" title={g.models}>
                          {g.name}
                        </p>
                        <div className="space-y-1.5">
                          {(g.buckets || []).map((b) => (
                            <div key={b.id}>
                              <div className="flex items-baseline justify-between mb-1">
                                <span className="text-[10px] font-bold text-slate-500">{b.label}</span>
                                <span className="text-[10px] font-black tabular-nums" style={{ color: colorOf(b.remaining) }}>
                                  {pct(b.remaining)}%
                                </span>
                              </div>
                              <div className="h-1.5 rounded-full bg-black/[0.07] overflow-hidden">
                                <div
                                  className="h-full rounded-full transition-all duration-500"
                                  style={{ width: `${pct(b.remaining)}%`, backgroundColor: colorOf(b.remaining) }}
                                />
                              </div>
                              <p className="text-[9px] font-bold text-slate-400 mt-0.5">{fmtReset(b.resetAt)}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {data?.fetchedAt && (
            <p className="text-[9px] font-bold text-slate-300 text-center mt-3">
              更新于 {new Date(data.fetchedAt).toLocaleTimeString('zh-CN')}
              {data.cached ? ' · 缓存' : ''}
            </p>
          )}
        </div>,
        document.body,
      )}
    </div>
  );
};

export default QuotaBar;

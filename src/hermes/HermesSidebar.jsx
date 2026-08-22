import { useMemo } from 'react';
import {
  CalendarClock, Loader2, MessageSquare, Plus, RefreshCw,
  Smartphone, Terminal, Trash2, X,
} from 'lucide-react';

const SOURCE_META = {
  weixin: { label: '微信', icon: Smartphone, order: 3 },
  cron: { label: '每日计划', icon: CalendarClock, order: 1 },
  tui: { label: '本地', icon: Terminal, order: 0 },
  cli: { label: '本地', icon: Terminal, order: 0 },
};

const sourceMeta = (source) => SOURCE_META[source] || {
  label: '其他', icon: MessageSquare, order: 3,
};

export default function HermesSidebar({
  fullscreen,
  open,
  sessions,
  sessionsLoading,
  connState,
  activeStoredId,
  busy,
  onRefresh,
  onClose,
  onNew,
  onOpen,
  onDelete,
}) {
  const grouped = useMemo(() => {
    const groups = new Map();
    for (const session of sessions) {
      const meta = sourceMeta(session.source);
      if (!groups.has(meta.label)) groups.set(meta.label, { meta, items: [] });
      groups.get(meta.label).items.push(session);
    }
    return [...groups.values()].sort((a, b) => a.meta.order - b.meta.order);
  }, [sessions]);

  if (!open) return null;

  return (
    <>
      {fullscreen && (
        <button
          type="button"
          aria-label="关闭会话列表"
          onClick={onClose}
          className="absolute inset-0 z-10 bg-black/25"
        />
      )}
      <div className={fullscreen
        ? 'absolute z-20 inset-y-0 left-0 w-72 flex flex-col bg-white border-r border-black/10 shadow-2xl overflow-hidden'
        : 'w-64 shrink-0 flex flex-col rounded-3xl bg-white/70 border border-black/5 overflow-hidden'}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-black/5">
          <span className="text-[10px] font-black uppercase tracking-widest text-[#999]">会话</span>
          <div className="flex items-center space-x-1">
            <button
              onClick={onRefresh}
              title="刷新列表"
              className="p-1.5 rounded-lg text-[#999] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
            >
              {sessionsLoading
                ? <Loader2 size={13} className="animate-spin" />
                : <RefreshCw size={13} />}
            </button>
            <button
              onClick={onClose}
              title="收起"
              className="p-1.5 rounded-lg text-[#999] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
            >
              <X size={13} />
            </button>
          </div>
        </div>

        <button
          onClick={() => {
            onNew();
            if (fullscreen) onClose();
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
                  {items.map((session) => (
                    <div
                      key={session.id}
                      className={`group relative flex items-center rounded-xl transition-colors ${
                        activeStoredId === session.id
                          ? 'bg-[#1a1a1a] text-white'
                          : 'hover:bg-black/5 text-[#444]'
                      } ${busy ? 'opacity-50 pointer-events-none' : ''}`}
                    >
                      <button
                        onClick={() => {
                          onOpen(session);
                          if (fullscreen) onClose();
                        }}
                        disabled={busy}
                        title={session.title || session.id}
                        className="flex-1 min-w-0 text-left px-2.5 py-2"
                      >
                        <div className="text-xs font-bold truncate pr-5">{session.title || '(无标题)'}</div>
                        <div className={`text-[10px] font-bold ${activeStoredId === session.id ? 'text-white/60' : 'text-[#bbb]'}`}>
                          {session.message_count} 条
                        </div>
                      </button>
                      <button
                        onClick={(event) => onDelete(event, session.id)}
                        title="删除会话"
                        className={`absolute right-1.5 p-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity ${
                          activeStoredId === session.id
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
    </>
  );
}

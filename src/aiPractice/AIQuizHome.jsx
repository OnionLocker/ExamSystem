import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertTriangle,
  BookOpen,
  Clock,
  Loader2,
  RefreshCw,
  Sparkles,
  Target,
  Trash2,
} from 'lucide-react';
import { api } from '../api.js';
import { parseBeijingMs } from '../lib/beijingTime.js';
import AIQuizSession from './AIQuizSession.jsx';

const MODULES = ['言语理解与表达', '判断推理', '科学推理', '数量关系', '资料分析'];
const TIME_TAB = '时间';

const STATUS_META = {
  imported: { label: '已导入', className: 'border-green-200 bg-green-50 text-green-700' },
  completed: { label: '已完成', className: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
  scheduled: { label: '等待生成', className: 'border-slate-200 bg-slate-50 text-slate-500' },
  running: { label: '生成中', className: 'border-amber-200 bg-amber-50 text-amber-700' },
  failed: { label: '生成失败', className: 'border-red-200 bg-red-50 text-red-600' },
};

const statusOf = (batch) => batch.status || (Number(batch.count) > 0 ? 'imported' : 'scheduled');
const moduleOf = (batch) => {
  if (MODULES.includes(batch.module)) return batch.module;
  if (MODULES.includes(batch.category)) return batch.category;
  const text = `${batch.module || ''} ${batch.category || ''} ${batch.source || ''} ${batch.batch_id || ''}`.toLowerCase();
  if (text.includes('言语理解与表达') || text.includes('yanyu') || text.includes('verbal')) return MODULES[0];
  if (text.includes('科学推理') || text.includes('kepui') || text.includes('kexue')) return MODULES[2];
  if (text.includes('判断推理') || text.includes('panduan') || text.includes('judg')) return MODULES[1];
  if (text.includes('数量关系') || text.includes('shuliang') || text.includes('quantity')) return MODULES[3];
  if (text.includes('资料分析') || text.includes('ziliao') || text.includes('data-analysis')) return MODULES[4];
  return '';
};

const dailyDateOf = (batch) => {
  const planned = String(batch.daily_plan_date || '').slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(planned) ? planned : '';
};

const nameOf = (batch) => {
  const date = dailyDateOf(batch);
  const module = moduleOf(batch);
  if (date && module) return `广东省考行测-${module}-${date.replaceAll('-', '')}`;
  return batch.source || batch.batch_id || '未命名题组';
};

const createdOf = (batch) => batch.created_at || '';

const formatDotDate = (date) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return date || '';
  const [year, month, day] = date.split('-');
  return `${year}.${Number(month)}.${Number(day)}`;
};

const relativeTime = (iso) => {
  if (!iso) return null;
  const timestamp = parseBeijingMs(iso);
  if (!Number.isFinite(timestamp)) return null;
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return days < 30 ? `${days} 天前` : `${Math.floor(days / 30)} 个月前`;
};

const accuracyClass = (rate) => {
  if (rate >= 0.8) return 'text-green-600';
  if (rate >= 0.6) return 'text-[#6b5428]';
  return 'text-red-500';
};

const tabClass = (selected) =>
  `rounded-2xl border px-4 py-3 text-sm font-black transition-colors ${
    selected
      ? 'border-[#1a1a1a] bg-[#1a1a1a] text-white'
      : 'border-[#e8d5b0] bg-white text-[#6b5428] hover:border-[#6b5428]'
  }`;

const AIQuizHome = ({ onAnalyzeWithHermes, initialBatchId, onInitialBatchHandled }) => {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeModule, setActiveModule] = useState(TIME_TAB);
  const [timeDate, setTimeDate] = useState('');
  const [active, setActive] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [errMsg, setErrMsg] = useState('');
  const handledInitial = useRef(null);

  const loadBatches = useCallback(async () => {
    setLoading(true);
    setErrMsg('');
    try {
      const rows = await api('/api/questions/meta/batches?include_scheduled=1');
      setBatches(Array.isArray(rows) ? rows : []);
    } catch (error) {
      setErrMsg(error?.message || '题组加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api('/api/questions/meta/batches?include_scheduled=1')
      .then((rows) => {
        if (!cancelled) setBatches(Array.isArray(rows) ? rows : []);
      })
      .catch((error) => {
        if (!cancelled) setErrMsg(error?.message || '题组加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!initialBatchId || loading || handledInitial.current === initialBatchId) return undefined;
    const batch = batches.find((item) => item.batch_id === initialBatchId);
    if (!batch) return undefined;
    handledInitial.current = initialBatchId;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      const module = moduleOf(batch);
      if (module) setActiveModule(module);
      if (statusOf(batch) === 'imported') {
        setActive({ batchId: batch.batch_id, reviewSessionId: batch.last_session_id || null });
      }
      onInitialBatchHandled?.();
    });
    return () => {
      cancelled = true;
    };
  }, [batches, initialBatchId, loading, onInitialBatchHandled]);

  const moduleCounts = useMemo(
    () => Object.fromEntries(
      MODULES.map((module) => [
        module,
        batches.filter((batch) => moduleOf(batch) === module).length,
      ]),
    ),
    [batches],
  );

  const dailyBatches = useMemo(
    () => batches.filter((batch) => dailyDateOf(batch)),
    [batches],
  );

  const dailyDates = useMemo(
    () => [...new Set(dailyBatches.map(dailyDateOf))].sort((a, b) => b.localeCompare(a)),
    [dailyBatches],
  );

  useEffect(() => {
    if (activeModule !== TIME_TAB) return;
    if (timeDate && dailyDates.includes(timeDate)) return;
    setTimeDate(dailyDates[0] || '');
  }, [activeModule, dailyDates, timeDate]);

  const visibleBatches = useMemo(() => {
    if (activeModule === TIME_TAB) {
      return dailyBatches
        .filter((batch) => dailyDateOf(batch) === timeDate)
        .sort((a, b) => {
          const rank = (item) => {
            const index = MODULES.indexOf(moduleOf(item));
            return index < 0 ? 99 : index;
          };
          return rank(a) - rank(b) || createdOf(b).localeCompare(createdOf(a));
        });
    }
    return batches
      .filter((batch) => moduleOf(batch) === activeModule)
      .sort((a, b) => createdOf(b).localeCompare(createdOf(a)));
  }, [activeModule, batches, dailyBatches, timeDate]);

  const openBatch = (batch) => {
    if (statusOf(batch) !== 'imported') return;
    setActive({
      batchId: batch.batch_id,
      reviewSessionId: batch.last_session_id || null,
    });
  };

  const requestDelete = (batch, event) => {
    event.stopPropagation();
    event.preventDefault();
    if (!deleting) setDeleteTarget(batch);
  };

  const confirmDelete = async () => {
    const batch = deleteTarget;
    if (!batch || deleting) return;
    setDeleting(batch.batch_id);
    setErrMsg('');
    try {
      await api(`/api/questions/batch/${encodeURIComponent(batch.batch_id)}`, { method: 'DELETE' });
      setBatches((current) => current.filter((item) => item.batch_id !== batch.batch_id));
      setDeleteTarget(null);
    } catch (error) {
      setDeleteTarget(null);
      setErrMsg(error?.message || '删除失败');
    } finally {
      setDeleting(null);
    }
  };

  if (active) {
    return createPortal(
      <div
        className="fixed inset-0 z-[80] overflow-hidden overscroll-none bg-white"
        style={{ height: '100dvh' }}
      >
        <AIQuizSession
          batchId={active.batchId}
          batchName={nameOf(
            batches.find((batch) => batch.batch_id === active.batchId)
            || { batch_id: active.batchId },
          )}
          reviewSessionId={active.reviewSessionId}
          onExit={() => {
            setActive(null);
            loadBatches();
          }}
          onAnalyzeWithHermes={onAnalyzeWithHermes}
        />
      </div>,
      document.body,
    );
  }

  const showModule = activeModule === TIME_TAB;
  const emptyTitle = activeModule === TIME_TAB
    ? (dailyDates.length ? '这一天还没有定时题组' : '还没有定时任务题组')
    : '这个模块还没有题组';
  const emptyHint = activeModule === TIME_TAB
    ? '只有定时任务产生的题组会出现在这里。普通题组请到所属模块里找。'
    : '题组按出题时间排列。定时任务的题也会出现在「时间」里。';

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#1a1a1a] text-white">
            <Target size={18} />
          </div>
          <div className="min-w-0">
            <h3 className="text-base font-black tracking-tight">AI 练题</h3>
            <p className="text-[11px] font-medium text-slate-400">按模块找题组，定时任务也可按日期找</p>
          </div>
        </div>
        <button
          type="button"
          onClick={loadBatches}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-black text-[#777] transition-colors hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-40"
        >
          {loading
            ? <Loader2 size={13} className="animate-spin" />
            : <RefreshCw size={13} />}
          刷新
        </button>
      </div>

      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-max gap-2" role="tablist" aria-label="练题分类">
          <button
            type="button"
            role="tab"
            aria-selected={activeModule === TIME_TAB}
            onClick={() => setActiveModule(TIME_TAB)}
            className={tabClass(activeModule === TIME_TAB)}
          >
            {TIME_TAB}
            <span
              className={`ml-2 text-[10px] ${
                activeModule === TIME_TAB ? 'text-white/60' : 'text-slate-400'
              }`}
            >
              {dailyDates.length}
            </span>
          </button>
          {MODULES.map((module) => (
            <button
              key={module}
              type="button"
              role="tab"
              aria-selected={activeModule === module}
              onClick={() => setActiveModule(module)}
              className={tabClass(activeModule === module)}
            >
              {module}
              <span
                className={`ml-2 text-[10px] ${
                  activeModule === module ? 'text-white/60' : 'text-slate-400'
                }`}
              >
                {moduleCounts[module] || 0}
              </span>
            </button>
          ))}
        </div>
      </div>

      {activeModule === TIME_TAB && dailyDates.length > 0 && (
        <div className="overflow-x-auto pb-1">
          <div className="flex min-w-max gap-2" role="tablist" aria-label="定时日期">
            {dailyDates.map((date) => {
              const selected = timeDate === date;
              return (
                <button
                  key={date}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => setTimeDate(date)}
                  className={`rounded-xl border px-3 py-2 text-xs font-black transition-colors ${
                    selected
                      ? 'border-[#6b5428] bg-[#1a1a1a] text-white'
                      : 'border-[#e8d5b0] bg-white text-[#6b5428] hover:border-[#6b5428]'
                  }`}
                >
                  {formatDotDate(date)}
                  <span className={`ml-1.5 text-[10px] ${selected ? 'text-white/60' : 'text-slate-400'}`}>
                    {` ${dailyBatches.filter((batch) => dailyDateOf(batch) === date).length} 组`}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {errMsg && (
        <div className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-bold text-red-700">
          <span>{errMsg}</span>
          <button
            type="button"
            onClick={() => setErrMsg('')}
            className="ml-3 text-red-500"
            aria-label="关闭提示"
          >
            ×
          </button>
        </div>
      )}

      {loading && batches.length === 0 ? (
        <div className="rounded-[2rem] border border-[#e8d5b0] bg-white p-10 text-center shadow-sm">
          <Loader2 size={24} className="mx-auto mb-3 animate-spin text-[#6b5428]" />
          <p className="text-sm font-black text-slate-400">正在加载题组…</p>
        </div>
      ) : visibleBatches.length === 0 ? (
        <div className="rounded-[2rem] border border-[#e8d5b0] bg-white p-10 text-center shadow-sm">
          <Sparkles size={24} className="mx-auto mb-3 text-[#6b5428]" />
          <h4 className="font-black">{emptyTitle}</h4>
          <p className="mt-2 text-sm text-slate-500">{emptyHint}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {visibleBatches.map((batch) => {
            const status = statusOf(batch);
            const meta = STATUS_META[status] || {
              label: status,
              className: 'border-slate-200 bg-slate-50 text-slate-500',
            };
            const canOpen = status === 'imported' || status === 'completed';
            const progress = Number(batch.count) > 0
              ? Number(batch.done_count || 0) / Number(batch.count)
              : 0;
            const accuracy = Number(batch.attempt_count) > 0
              ? Number(batch.correct_count || 0) / Number(batch.attempt_count)
              : null;
            const createdAt = relativeTime(createdOf(batch));
            const isDeleting = deleting === batch.batch_id;
            const action = batch.last_session_id
              ? '复盘'
              : Number(batch.done_count) > 0 ? '继续练习' : '开始练习';
            const moduleName = moduleOf(batch);

            return (
              <div
                key={batch.batch_id}
                role={canOpen ? 'button' : undefined}
                tabIndex={canOpen ? 0 : undefined}
                onClick={() => openBatch(batch)}
                onKeyDown={(event) => {
                  if (canOpen && (event.key === 'Enter' || event.key === ' ')) {
                    event.preventDefault();
                    openBatch(batch);
                  }
                }}
                className={`rounded-[1.75rem] border bg-white p-5 shadow-sm transition-all ${
                  canOpen
                    ? 'cursor-pointer border-[#e8d5b0] hover:border-[#6b5428] hover:shadow-md'
                    : 'cursor-not-allowed border-black/5 opacity-75'
                } ${isDeleting ? 'pointer-events-none opacity-40' : ''}`}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                      canOpen
                        ? 'bg-[#e8d5b0] text-[#1a1a1a]'
                        : 'bg-slate-100 text-slate-400'
                    }`}
                  >
                    {status === 'running'
                      ? <Loader2 size={15} className="animate-spin" />
                      : <BookOpen size={15} />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="min-w-0 truncate text-sm font-black">
                        {nameOf(batch)}
                      </p>
                      {showModule && moduleName && (
                        <span className="rounded-full border border-[#e8d5b0] bg-[#fcfaf6] px-2 py-0.5 text-[10px] font-black text-[#6b5428]">
                          {moduleName}
                        </span>
                      )}
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-black ${meta.className}`}
                      >
                        {meta.label}
                      </span>
                    </div>
                    {canOpen ? (
                      <>
                        <div className="mt-3 h-1 overflow-hidden rounded-full bg-[#e8d5b0]">
                          <div
                            className="h-full rounded-full bg-[#2c261c]"
                            style={{ width: `${Math.min(100, progress * 100)}%` }}
                          />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] font-black text-slate-400">
                          <span>{batch.done_count || 0}/{batch.count || 0} 题</span>
                          {accuracy !== null && (
                            <span className={accuracyClass(accuracy)}>
                              正确率 {Math.round(accuracy * 100)}%
                            </span>
                          )}
                          {createdAt && (
                            <span className="flex items-center gap-1">
                              <Clock size={10} />{createdAt}
                            </span>
                          )}
                          <span className="ml-auto text-[#6b5428]">{action} →</span>
                        </div>
                      </>
                    ) : (
                      <p className="mt-2 text-xs text-slate-500">
                        {status === 'failed'
                          ? batch.error_message
                            || batch.message
                            || '生成未完成，请稍后重试。'
                          : status === 'running'
                            ? '题组正在生成，完成后即可开始练习。'
                            : '题组已列入计划，尚未开始生成。'}
                      </p>
                    )}
                  </div>
                  {canOpen && (
                    <button
                      type="button"
                      onClick={(event) => requestDelete(batch, event)}
                      disabled={isDeleting}
                      title="删除题组"
                      aria-label={`删除题组 ${nameOf(batch)}`}
                      className="shrink-0 rounded-xl p-2 text-slate-300 hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
                    >
                      {isDeleting
                        ? <Loader2 size={15} className="animate-spin" />
                        : <Trash2 size={15} />}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {deleteTarget && createPortal(
        <div
          className="fixed inset-0 z-[9998] flex items-center justify-center p-5"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-batch-title"
        >
          <button
            type="button"
            aria-label="取消删除"
            className="absolute inset-0 bg-black/35 backdrop-blur-[3px]"
            onClick={() => {
              if (!deleting) setDeleteTarget(null);
            }}
          />
          <div className="relative w-full max-w-sm overflow-hidden rounded-[2rem] border border-white/70 bg-white shadow-2xl">
            <div className="p-6 pb-5">
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-red-50 text-red-500">
                <AlertTriangle size={20} />
              </div>
              <h3 id="delete-batch-title" className="text-lg font-black tracking-tight">
                删除这个题组？
              </h3>
              <p className="mt-1.5 truncate text-sm font-bold text-[#6b5428]">
                {nameOf(deleteTarget)}
              </p>
              <p className="mt-4 rounded-2xl bg-[#f7f3ea] px-4 py-3 text-sm leading-relaxed text-slate-600">
                将删除 <strong className="text-[#1a1a1a]">
                  {deleteTarget.count || 0} 道题
                </strong>
                {Number(deleteTarget.attempt_count) > 0 && (
                  <>和 <strong className="text-[#1a1a1a]">
                    {deleteTarget.attempt_count} 条作答记录
                  </strong></>
                )}，删除后无法恢复。
              </p>
            </div>
            <div className="flex gap-3 border-t border-black/5 bg-[#fcfaf6] p-4">
              <button
                type="button"
                autoFocus
                disabled={!!deleting}
                onClick={() => setDeleteTarget(null)}
                className="flex-1 rounded-2xl border border-black/10 bg-white px-4 py-3 text-sm font-black text-[#666] disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={!!deleting}
                onClick={confirmDelete}
                className="flex-1 rounded-2xl bg-red-500 px-4 py-3 text-sm font-black text-white disabled:opacity-60"
              >
                {deleting
                  ? <Loader2 size={16} className="mx-auto animate-spin" />
                  : '确认删除'}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
};

export default AIQuizHome;

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertTriangle,
  BookOpen,
  CheckSquare,
  Clock,
  Loader2,
  RefreshCw,
  Sparkles,
  Square,
  Target,
  Trash2,
} from 'lucide-react';
import { api } from '../api.js';
import AIQuizSession from './AIQuizSession.jsx';
import { MODULES, dailyDateOf, moduleOf, nameOf } from './practiceModules.js';
import { parseSqliteTime } from '../sqliteTime.js';

const DEFAULT_TAB = '默认';
const TIME_TAB = '时间';

const STATUS_META = {
  imported: { label: '已导入', className: 'border-green-200 bg-green-50 text-green-700' },
  completed: { label: '已完成', className: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
  scheduled: { label: '等待生成', className: 'border-slate-200 bg-slate-50 text-slate-500' },
  running: { label: '生成中', className: 'border-amber-200 bg-amber-50 text-amber-700' },
  failed: { label: '生成失败', className: 'border-red-200 bg-red-50 text-red-600' },
};

const statusOf = (batch) => batch.status || (Number(batch.count) > 0 ? 'imported' : 'scheduled');

const canOpenBatch = (batch) => {
  const status = statusOf(batch);
  return status === 'imported' || status === 'completed';
};

const canDeleteBatch = (batch) => {
  const status = statusOf(batch);
  return status !== 'running';
};

const createdOf = (batch) => batch.created_at || '';

const formatDotDate = (date) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return date || '';
  const [year, month, day] = date.split('-');
  return `${year}.${Number(month)}.${Number(day)}`;
};

const relativeTime = (iso) => {
  if (!iso) return null;
  const timestamp = parseSqliteTime(iso);
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
  const [activeModule, setActiveModule] = useState(DEFAULT_TAB);
  const [timeDate, setTimeDate] = useState('');
  const [active, setActive] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
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
      if (canOpenBatch(batch)) {
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

  useEffect(() => {
    setSelected(new Set());
  }, [activeModule, timeDate]);

  const visibleBatches = useMemo(() => {
    if (activeModule === DEFAULT_TAB) {
      return [...batches].sort((a, b) => createdOf(b).localeCompare(createdOf(a)));
    }
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

  const selectedBatches = useMemo(
    () => visibleBatches.filter((batch) => selected.has(batch.batch_id)),
    [selected, visibleBatches],
  );

  const allVisibleSelected = visibleBatches.length > 0
    && visibleBatches.every((batch) => selected.has(batch.batch_id));

  const toggleSelect = (batchId) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(batchId)) next.delete(batchId);
      else next.add(batchId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected((current) => {
      if (allVisibleSelected) return new Set();
      return new Set(visibleBatches.map((batch) => batch.batch_id));
    });
  };

  const exitSelect = () => {
    setSelecting(false);
    setSelected(new Set());
  };

  const openBatch = (batch) => {
    if (selecting) {
      toggleSelect(batch.batch_id);
      return;
    }
    if (!canOpenBatch(batch)) return;
    setActive({
      batchId: batch.batch_id,
      reviewSessionId: batch.last_session_id || null,
    });
  };

  const requestDelete = (batch, event) => {
    event.stopPropagation();
    event.preventDefault();
    if (!deleting) setDeleteTarget([batch]);
  };

  const requestDeleteSelected = () => {
    if (!selectedBatches.length || deleting) return;
    setDeleteTarget(selectedBatches);
  };

  const confirmDelete = async () => {
    const targets = deleteTarget;
    if (!targets?.length || deleting) return;
    const ids = targets.map((batch) => batch.batch_id);
    setDeleting(true);
    setErrMsg('');
    try {
      if (ids.length === 1) {
        await api(`/api/questions/batch/${encodeURIComponent(ids[0])}`, { method: 'DELETE' });
      } else {
        await api('/api/questions/batches/delete', { method: 'POST', body: { batch_ids: ids } });
      }
      const removed = new Set(ids);
      setBatches((current) => current.filter((item) => !removed.has(item.batch_id)));
      setDeleteTarget(null);
      exitSelect();
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
          auditSourceSessionId={active.auditSourceSessionId}
          onExit={() => {
            setActive(null);
            loadBatches();
          }}
          onAnalyzeWithHermes={onAnalyzeWithHermes}
          onAuditWithHermes={(sessionId) => {
            setActive({ batchId: active.batchId, auditSourceSessionId: sessionId });
          }}
        />
      </div>,
      document.body,
    );
  }

  const showModule = activeModule === DEFAULT_TAB || activeModule === TIME_TAB;
  const emptyTitle = activeModule === DEFAULT_TAB
    ? '还没有题组'
    : activeModule === TIME_TAB
      ? (dailyDates.length ? '这一天还没有定时题组' : '还没有定时任务题组')
      : '这个模块还没有题组';
  const emptyHint = activeModule === DEFAULT_TAB
    ? '全部题组按生成时间从近到远排列，不按分类。'
    : activeModule === TIME_TAB
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
            <p className="text-[11px] font-medium text-slate-400">默认按生成时间排列，也可按日期或模块找</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          {selecting ? (
            <>
              <button
                type="button"
                onClick={toggleSelectAll}
                disabled={!visibleBatches.length || Boolean(deleting)}
                className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-black text-[#777] transition-colors hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-40"
              >
                {allVisibleSelected ? <CheckSquare size={13} /> : <Square size={13} />}
                {allVisibleSelected ? '取消全选' : '本页全选'}
              </button>
              <button
                type="button"
                onClick={requestDeleteSelected}
                disabled={!selectedBatches.length || Boolean(deleting)}
                className="flex items-center gap-1.5 rounded-xl bg-red-500 px-3 py-2 text-xs font-black text-white transition-colors hover:bg-red-600 disabled:opacity-40"
              >
                <Trash2 size={13} />
                {selectedBatches.length ? `删除 ${selectedBatches.length}` : '删除'}
              </button>
              <button
                type="button"
                onClick={exitSelect}
                disabled={Boolean(deleting)}
                className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-black text-[#777] transition-colors hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-40"
              >
                取消
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setSelecting(true)}
              disabled={!visibleBatches.length}
              className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-black text-[#777] transition-colors hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-40"
            >
              <CheckSquare size={13} />
              选择
            </button>
          )}
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
      </div>

      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-max gap-2" role="tablist" aria-label="练题分类">
          <button
            type="button"
            role="tab"
            aria-selected={activeModule === DEFAULT_TAB}
            onClick={() => setActiveModule(DEFAULT_TAB)}
            className={tabClass(activeModule === DEFAULT_TAB)}
          >
            {DEFAULT_TAB}
            <span
              className={`ml-2 text-[10px] ${
                activeModule === DEFAULT_TAB ? 'text-white/60' : 'text-slate-400'
              }`}
            >
              {batches.length}
            </span>
          </button>
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
            const canOpen = canOpenBatch(batch);
            const canDelete = canDeleteBatch(batch);
            const progress = Number(batch.count) > 0
              ? Number(batch.done_count || 0) / Number(batch.count)
              : 0;
            const accuracy = Number(batch.attempt_count) > 0
              ? Number(batch.correct_count || 0) / Number(batch.attempt_count)
              : null;
            const createdAt = relativeTime(createdOf(batch));
            const isDeleting = Boolean(deleting);
            const checked = selected.has(batch.batch_id);
            const interactive = selecting || canOpen;
            const action = batch.last_session_id
              ? '复盘'
              : Number(batch.done_count) > 0 ? '继续练习' : '开始练习';
            const moduleName = moduleOf(batch);

            return (
              <div
                key={batch.batch_id}
                role={interactive ? 'button' : undefined}
                tabIndex={interactive ? 0 : undefined}
                onClick={() => openBatch(batch)}
                onKeyDown={(event) => {
                  if (interactive && (event.key === 'Enter' || event.key === ' ')) {
                    event.preventDefault();
                    openBatch(batch);
                  }
                }}
                className={`rounded-[1.75rem] border bg-white p-5 shadow-sm transition-all ${
                  checked
                    ? 'cursor-pointer border-[#6b5428] shadow-md'
                    : interactive
                      ? 'cursor-pointer border-[#e8d5b0] hover:border-[#6b5428] hover:shadow-md'
                      : canDelete
                        ? 'border-[#e8d5b0]'
                        : 'cursor-not-allowed border-black/5 opacity-75'
                } ${isDeleting ? 'pointer-events-none opacity-40' : ''}`}
              >
                <div className="flex items-start gap-3">
                  {selecting && (
                    <span
                      className={`mt-1.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md ${
                        checked ? 'text-[#1a1a1a]' : 'text-slate-300'
                      }`}
                      aria-hidden="true"
                    >
                      {checked ? <CheckSquare size={18} /> : <Square size={18} />}
                    </span>
                  )}
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
                      <p className="mt-2 line-clamp-2 text-xs text-slate-500">
                        {status === 'failed'
                          ? batch.error_message
                            || batch.message
                            || '生成未完成，可直接删除以免占着列表。'
                          : status === 'running'
                            ? '题组正在生成，完成后即可开始练习。'
                            : '题组已列入计划，尚未开始生成。'}
                      </p>
                    )}
                  </div>
                  {!selecting && canDelete && (
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

      {deleteTarget?.length > 0 && createPortal(
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
                {deleteTarget.length === 1 ? '删除这个题组？' : `删除这 ${deleteTarget.length} 个题组？`}
              </h3>
              <p className="mt-1.5 truncate text-sm font-bold text-[#6b5428]">
                {deleteTarget.length === 1
                  ? nameOf(deleteTarget[0])
                  : deleteTarget.slice(0, 2).map((batch) => nameOf(batch)).join('、')
                    + (deleteTarget.length > 2 ? ` 等 ${deleteTarget.length} 组` : '')}
              </p>
              <p className="mt-4 rounded-2xl bg-[#f7f3ea] px-4 py-3 text-sm leading-relaxed text-slate-600">
                {deleteTarget.reduce((sum, batch) => sum + Number(batch.count || 0), 0) === 0
                  ? '这些题组没有题目入库，删除后会从列表里去掉。'
                  : (
                    <>
                      将删除 <strong className="text-[#1a1a1a]">
                        {deleteTarget.reduce((sum, batch) => sum + Number(batch.count || 0), 0)} 道题
                      </strong>
                      {deleteTarget.reduce((sum, batch) => sum + Number(batch.attempt_count || 0), 0) > 0 && (
                        <>和 <strong className="text-[#1a1a1a]">
                          {deleteTarget.reduce((sum, batch) => sum + Number(batch.attempt_count || 0), 0)} 条作答记录
                        </strong></>
                      )}，删除后无法恢复。
                    </>
                  )}
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

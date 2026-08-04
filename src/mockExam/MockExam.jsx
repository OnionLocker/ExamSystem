import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Play, Pause, Square, RotateCcw, Settings,
  GripVertical, Plus, X, Trash2, Check,
} from 'lucide-react';
import { DEFAULT_BLOCKS, COLOR_PALETTE, loadBlocks, saveBlocks, resetBlocks } from './blocks.js';
import { cloudGet, cloudSet } from '../cloudStorage.js';
import { addEntry as addStudyEntry, scoreMock } from '../studyLog/studyLog.js';

// ============================================================
// 90 分钟全卷模考器（简化版）
// 真实顺序展示模块时间块；模块结束播一声"滴"；支持自定义时长 / 拖拽排序
// ============================================================

// 模考按实际计时时长加热力，跟番茄钟同口径（1 分钟 1 分）。
// 不足 10 分钟不记：那多半是点开看了一眼，不是真在模考。
const MIN_MOCK_SEC = 10 * 60;

const logMockHeat = (elapsedSec) => {
  if (!elapsedSec || elapsedSec < MIN_MOCK_SEC) return;
  const minutes = Math.round(elapsedSec / 60);
  addStudyEntry({ type: 'mock', module: '全卷模考', minutes, score: scoreMock(minutes) });
};

const STATE_KEY = 'mockexam_state_v1';

const loadState = () => cloudGet(STATE_KEY, null);
const saveState = (s) => cloudSet(STATE_KEY, s);

const formatTime = (sec) => {
  if (sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

// 简短"滴"声：880Hz 正弦，~250ms 衰减
const playBeep = () => {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 880;
    const now = ctx.currentTime;
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.35, now + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);
    osc.connect(g);
    g.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.32);
    setTimeout(() => ctx.close(), 600);
  } catch {
    // ignore
  }
};

const MockExam = () => {
  const [blocks, setBlocks] = useState(() => loadBlocks());
  const [state, setState] = useState(() =>
    loadState() || { startedAt: null, pausedRemaining: null, finished: false },
  );
  const [editing, setEditing] = useState(false);
  // 当前时刻由 1Hz 定时器推进，渲染期只读它（见下方 effect）
  const [now, setNow] = useState(() => Date.now());
  const lastBlockRef = useRef(-1);

  useEffect(() => saveState(state), [state]);
  useEffect(() => saveBlocks(blocks), [blocks]);

  // 1Hz tick：存的是"当前时刻"而不是自增计数。
  // 渲染期直接读 Date.now() 属于不纯（同一次渲染重跑会得到不同结果），
  // 所以把时间戳作为 state 由定时器推进，渲染只消费它。
  // useState 的初始值已经是当前时刻，这里只需启动定时器推进它
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // 计算累计起始秒
  // 前缀和：每个 block 的累计起始秒。
  // 不用 map + 外部累加变量（那是渲染期改外部状态，React 19 会告警），
  // 改成 reduce 里只操作自己的累加器。
  const blockStarts = useMemo(
    () =>
      blocks.reduce((acc, b, i) => {
        acc.push(i === 0 ? 0 : acc[i - 1] + blocks[i - 1].minutes * 60);
        return acc;
      }, []),
    [blocks]
  );
  const totalSec = blocks.reduce((s, b) => s + b.minutes * 60, 0);

  // 当前剩余秒（纯计算）
  let elapsedSec;
  if (state.finished) {
    elapsedSec = totalSec;
  } else if (state.pausedRemaining != null) {
    elapsedSec = totalSec - state.pausedRemaining;
  } else if (state.startedAt) {
    elapsedSec = Math.min(totalSec, Math.floor((now - state.startedAt) / 1000));
  } else {
    elapsedSec = 0;
  }
  const remainingSec = totalSec - elapsedSec;

  // 时间到自动收卷。
  // 不放在独立 effect 里：那样每次 tick 都要先渲染一遍再 setState 触发第二遍。
  // 这里在渲染期按"已算出的 elapsedSec"判断，条件里带 !finished 保证只翻转一次。
  if (
    !state.finished &&
    state.startedAt != null &&
    state.pausedRemaining == null &&
    elapsedSec >= totalSec
  ) {
    setState((s) => (s.finished ? s : { ...s, finished: true }));
  }

  // 当前 block 索引
  let currentBlockIdx = -1;
  for (let i = 0; i < blocks.length; i++) {
    const start = blockStarts[i];
    const end = start + blocks[i].minutes * 60;
    if (elapsedSec >= start && elapsedSec < end) {
      currentBlockIdx = i;
      break;
    }
  }
  const isRunning = state.startedAt != null && state.pausedRemaining == null && !state.finished;

  // 模块切换 → "滴" + 通知
  useEffect(() => {
    if (!isRunning) return;
    if (currentBlockIdx === -1) return;
    if (currentBlockIdx === lastBlockRef.current) return;
    if (lastBlockRef.current >= 0) {
      playBeep();
      try {
        if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
      } catch { /* ignore */ }
      try {
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('模考节奏', {
            body: `进入「${blocks[currentBlockIdx].name}」时段`,
          });
        }
      } catch { /* ignore */ }
    }
    lastBlockRef.current = currentBlockIdx;
  }, [currentBlockIdx, isRunning, blocks]);

  // 整场结束（最后一块结束）响一声，并把这场模考记进打卡热力
  useEffect(() => {
    if (state.finished && lastBlockRef.current !== -2) {
      lastBlockRef.current = -2;
      playBeep();
      logMockHeat(totalSec);
    }
  }, [state.finished, totalSec]);

  const start = () => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {});
    }
    setState({ startedAt: Date.now(), pausedRemaining: null, finished: false });
    lastBlockRef.current = -1;
  };
  const pause = () => {
    if (!isRunning) return;
    setState({ ...state, pausedRemaining: remainingSec });
  };
  const resume = () => {
    if (state.pausedRemaining == null) return;
    setState({
      startedAt: Date.now() - (totalSec - state.pausedRemaining) * 1000,
      pausedRemaining: null,
      finished: false,
    });
  };
  const stop = () => {
    if (!confirm('提前结束这场模考？')) return;
    // 提前结束也算学了，按已经跑过的时长计
    logMockHeat(elapsedSec);
    setState({ startedAt: null, pausedRemaining: null, finished: false });
    lastBlockRef.current = -1;
  };
  const reset = () => {
    setState({ startedAt: null, pausedRemaining: null, finished: false });
    lastBlockRef.current = -1;
  };

  // -------- 编辑模式 --------
  const onSaveEdits = (newBlocks) => {
    if (state.startedAt && !state.finished) {
      if (!confirm('保存配置会重置当前计时，确定？')) return;
      reset();
    }
    setBlocks(newBlocks);
    setEditing(false);
  };

  if (editing) {
    return (
      <EditPanel
        initial={blocks}
        onSave={onSaveEdits}
        onCancel={() => setEditing(false)}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* 顶部计时器 */}
      <div className="bg-[#1a1a1a] rounded-[2.5rem] p-8 text-white relative overflow-hidden">
        <div
          className="absolute -top-20 -right-20 w-64 h-64 rounded-full blur-[80px] opacity-30 pointer-events-none"
          style={{ backgroundColor: currentBlockIdx >= 0 ? blocks[currentBlockIdx].color : '#fbc02d' }}
        />
        <div className="relative flex items-start justify-between flex-wrap gap-6">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.25em] text-white/40">
              全卷节奏 · {Math.round(totalSec / 60)} 分钟
            </p>
            <p
              className="text-7xl md:text-8xl font-black italic tabular-nums tracking-tighter mt-2"
              style={{ color: state.finished ? '#94a3b8' : '#fbc02d' }}
            >
              {formatTime(remainingSec)}
            </p>
            <p className="text-xs font-bold text-white/50 mt-1">
              {state.finished
                ? '⏰ 模考结束'
                : state.startedAt == null
                  ? '准备开始'
                  : state.pausedRemaining != null
                    ? '已暂停'
                    : currentBlockIdx >= 0
                      ? `当前：${blocks[currentBlockIdx].name}`
                      : '全部完成'}
            </p>
          </div>

          {/* 控制 */}
          <div className="flex items-center space-x-2">
            {state.finished ? (
              <button
                onClick={reset}
                className="bg-[#fbc02d] text-[#1a1a1a] px-6 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:brightness-110 flex items-center space-x-2"
              >
                <RotateCcw size={14} strokeWidth={2.5} />
                <span>新一场</span>
              </button>
            ) : state.startedAt == null ? (
              <button
                onClick={start}
                className="bg-[#fbc02d] text-[#1a1a1a] px-6 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:brightness-110 flex items-center space-x-2"
              >
                <Play size={14} strokeWidth={2.5} fill="currentColor" />
                <span>开始模考</span>
              </button>
            ) : (
              <>
                {isRunning ? (
                  <button
                    onClick={pause}
                    className="bg-white/10 text-white px-5 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-white/15 flex items-center space-x-2"
                  >
                    <Pause size={14} strokeWidth={2.5} fill="currentColor" />
                    <span>暂停</span>
                  </button>
                ) : (
                  <button
                    onClick={resume}
                    className="bg-[#fbc02d] text-[#1a1a1a] px-5 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:brightness-110 flex items-center space-x-2"
                  >
                    <Play size={14} strokeWidth={2.5} fill="currentColor" />
                    <span>继续</span>
                  </button>
                )}
                <button
                  onClick={stop}
                  className="bg-white/10 text-white/70 hover:bg-[#ff6b6b]/20 hover:text-[#ff6b6b] w-12 h-12 rounded-2xl flex items-center justify-center transition-colors"
                >
                  <Square size={14} strokeWidth={2.5} fill="currentColor" />
                </button>
              </>
            )}
            {/* 设置按钮 */}
            <button
              onClick={() => setEditing(true)}
              disabled={isRunning}
              className="bg-white/10 text-white/70 hover:bg-white/20 hover:text-white w-12 h-12 rounded-2xl flex items-center justify-center transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              title={isRunning ? '请先暂停才能调整' : '自定义模块'}
            >
              <Settings size={14} />
            </button>
          </div>
        </div>

        {/* 进度条 */}
        <div className="mt-6 h-2 bg-white/[0.06] rounded-full overflow-hidden flex">
          {blocks.map((b, i) => {
            const start = blockStarts[i];
            const blockSec = b.minutes * 60;
            const blockElapsed = Math.max(0, Math.min(blockSec, elapsedSec - start));
            const total = (b.minutes / Math.max(1, totalSec / 60)) * 100;
            return (
              <div
                key={b.id}
                className="h-full relative"
                style={{ width: `${total}%`, borderRight: '1px solid rgba(255,255,255,0.1)' }}
              >
                <div
                  className="h-full"
                  style={{
                    width: `${(blockElapsed / blockSec) * 100}%`,
                    backgroundColor: b.color,
                    transition: 'width 0.5s',
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* 模块卡片网格（极简）*/}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {blocks.map((b, i) => {
          const isCurrent = currentBlockIdx === i;
          const isPast = i < currentBlockIdx || state.finished;
          return (
            <div
              key={b.id}
              className={`rounded-2xl p-4 transition-all ${
                isCurrent
                  ? 'bg-[#1a1a1a] text-white scale-[1.03] shadow-2xl'
                  : isPast
                    ? 'bg-white/40 text-slate-400 opacity-60'
                    : 'bg-white text-[#1a1a1a]'
              }`}
              style={isCurrent ? { boxShadow: `0 20px 40px -10px ${b.color}66` } : undefined}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span
                  className="text-[9px] font-black uppercase tracking-widest"
                  style={{ color: isCurrent || !isPast ? b.color : '#94a3b8' }}
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                {isCurrent && (
                  <span className="text-[9px] font-black bg-[#fbc02d] text-[#1a1a1a] px-1.5 py-0.5 rounded-full">
                    NOW
                  </span>
                )}
              </div>
              <p className="text-sm font-black tracking-tight mb-2">{b.name}</p>
              <div className="flex items-baseline space-x-1">
                <span
                  className="text-2xl font-black italic tabular-nums"
                  style={{ color: isCurrent ? b.color : 'inherit' }}
                >
                  {b.minutes}
                </span>
                <span className="text-[10px] font-bold opacity-60">分钟</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ============================================================
// 编辑模式：拖拽排序 + 时长加减 + 增删
// ============================================================
const EditPanel = ({ initial, onSave, onCancel }) => {
  const [blocks, setBlocks] = useState(() => initial.map((b) => ({ ...b })));
  const [draggedIdx, setDraggedIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);

  const total = blocks.reduce((s, b) => s + Number(b.minutes || 0), 0);

  const onDragStart = (i) => (e) => {
    setDraggedIdx(i);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(i)); // Firefox 需要
  };
  const onDragOver = (i) => (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIdx(i);
  };
  const onDrop = (i) => (e) => {
    e.preventDefault();
    if (draggedIdx == null || draggedIdx === i) return;
    const arr = [...blocks];
    const [moved] = arr.splice(draggedIdx, 1);
    arr.splice(i, 0, moved);
    setBlocks(arr);
    setDraggedIdx(null);
    setDragOverIdx(null);
  };
  const onDragEnd = () => {
    setDraggedIdx(null);
    setDragOverIdx(null);
  };

  const setMinutes = (idx, v) => {
    const arr = [...blocks];
    const num = Math.max(1, Math.min(180, Number(v) || 0));
    arr[idx] = { ...arr[idx], minutes: num };
    setBlocks(arr);
  };
  const adjMinutes = (idx, delta) => {
    setMinutes(idx, blocks[idx].minutes + delta);
  };
  const setName = (idx, v) => {
    const arr = [...blocks];
    arr[idx] = { ...arr[idx], name: v };
    setBlocks(arr);
  };
  const removeBlock = (idx) => {
    if (blocks.length <= 1) {
      alert('至少保留一个模块');
      return;
    }
    setBlocks(blocks.filter((_, i) => i !== idx));
  };
  const addBlock = () => {
    const usedColors = new Set(blocks.map((b) => b.color));
    const newColor = COLOR_PALETTE.find((c) => !usedColors.has(c)) || COLOR_PALETTE[0];
    const newBlock = {
      id: `custom_${Date.now()}`,
      name: '新模块',
      minutes: 5,
      color: newColor,
    };
    setBlocks([...blocks, newBlock]);
  };
  const resetDefaults = () => {
    if (!confirm('恢复默认配置？当前自定义会被清空。')) return;
    resetBlocks();
    setBlocks(DEFAULT_BLOCKS.map((b) => ({ ...b })));
  };

  return (
    <div className="space-y-5">
      {/* 头部 */}
      <div className="bg-[#1a1a1a] rounded-2xl p-6 text-white flex items-center justify-between flex-wrap gap-4">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.25em] text-white/40">
            编辑模块配置
          </p>
          <p className="text-2xl font-black italic mt-0.5">
            总时长 <span className="text-[#fbc02d] tabular-nums">{total}</span> 分钟
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={resetDefaults}
            className="bg-white/10 hover:bg-white/15 text-white/70 px-4 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest flex items-center space-x-1.5"
          >
            <RotateCcw size={12} />
            <span>恢复默认</span>
          </button>
          <button
            onClick={onCancel}
            className="bg-white/10 hover:bg-white/15 text-white/70 px-4 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest flex items-center space-x-1.5"
          >
            <X size={12} />
            <span>取消</span>
          </button>
          <button
            onClick={() => onSave(blocks)}
            className="bg-[#fbc02d] text-[#1a1a1a] px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest flex items-center space-x-1.5 hover:brightness-110"
          >
            <Check size={12} strokeWidth={3} />
            <span>保存</span>
          </button>
        </div>
      </div>

      {/* 拖拽列表 */}
      <div className="space-y-2">
        {blocks.map((b, i) => (
          <div
            key={b.id}
            draggable
            onDragStart={onDragStart(i)}
            onDragOver={onDragOver(i)}
            onDrop={onDrop(i)}
            onDragEnd={onDragEnd}
            className={`bg-white rounded-2xl px-3 py-3 flex items-center gap-3 transition-all ${
              draggedIdx === i ? 'opacity-40 scale-[0.98]' : ''
            } ${
              dragOverIdx === i && draggedIdx !== i
                ? 'ring-2 ring-[#fbc02d]'
                : ''
            }`}
          >
            {/* drag handle */}
            <div
              className="cursor-grab active:cursor-grabbing text-slate-300 hover:text-slate-500 transition-colors flex-shrink-0"
              title="按住拖动调整顺序"
            >
              <GripVertical size={20} />
            </div>

            {/* 颜色标记 */}
            <div
              className="w-1 h-10 rounded-full flex-shrink-0"
              style={{ backgroundColor: b.color }}
            />

            {/* 序号 */}
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 w-6 tabular-nums flex-shrink-0">
              {String(i + 1).padStart(2, '0')}
            </span>

            {/* 名称编辑 */}
            <input
              type="text"
              value={b.name}
              onChange={(e) => setName(i, e.target.value)}
              maxLength={12}
              className="flex-1 bg-transparent text-sm font-black tracking-tight focus:outline-none focus:bg-[#f2f0e9]/50 rounded-lg px-2 py-1.5"
            />

            {/* 时长 */}
            <div className="flex items-center bg-[#f2f0e9]/60 rounded-xl flex-shrink-0">
              <button
                onClick={() => adjMinutes(i, -1)}
                className="w-8 h-9 text-slate-500 hover:text-black hover:bg-[#f2f0e9] rounded-l-xl font-black text-base transition-colors"
              >
                −
              </button>
              <input
                type="number"
                min="1"
                max="180"
                value={b.minutes}
                onChange={(e) => setMinutes(i, e.target.value)}
                className="w-12 bg-transparent text-center text-sm font-black tabular-nums focus:outline-none"
              />
              <button
                onClick={() => adjMinutes(i, 1)}
                className="w-8 h-9 text-slate-500 hover:text-black hover:bg-[#f2f0e9] rounded-r-xl font-black text-base transition-colors"
              >
                +
              </button>
            </div>
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 hidden sm:block">
              分钟
            </span>

            {/* 删除 */}
            <button
              onClick={() => removeBlock(i)}
              className="w-9 h-9 rounded-xl text-slate-300 hover:text-[#ff6b6b] hover:bg-[#ff6b6b]/10 flex items-center justify-center flex-shrink-0 transition-colors"
              title="删除此模块"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>

      {/* 加新模块 */}
      <button
        onClick={addBlock}
        className="w-full bg-[#f2f0e9]/40 hover:bg-[#f2f0e9] border-2 border-dashed border-[#dfdbcc] rounded-2xl py-4 text-xs font-black uppercase tracking-widest text-slate-500 hover:text-black flex items-center justify-center space-x-2 transition-colors"
      >
        <Plus size={14} />
        <span>添加模块</span>
      </button>

      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 text-center">
        按住左侧 ⋮⋮ 拖动调整顺序
      </p>
    </div>
  );
};

export default MockExam;

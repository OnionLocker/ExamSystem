// AI 练题 · 做题会话
//
// 按真考的节奏走：整卷做完再交卷，中途可以随便往前翻回去改；
// 交卷那一刻一次性判分，然后逐题对答案、看解析、回看当时的草稿纸。
//
// 三件事跟老版本不一样：
//   1. 答案先攒在前端，不再每题即时判分 —— 否则「倒回来重做前面的题」没有意义；
//   2. 单题用时是累计停留时长（来回跳转会累加，切到后台会暂停），不是一次性的差值；
//   3. 草稿纸是盖在整页上的批注层，能在题干上圈划，离开该题时把整页快照存到后台。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowLeft, ArrowRight, Check, X as XIcon, Clock, Trophy, RotateCcw,
  AlertTriangle, Lightbulb, Flag, PenTool, Loader2, Grid3x3, Eraser,
  Highlighter, Undo2, Trash2, ChevronUp, ChevronDown, Plus, Send, Bookmark,
} from 'lucide-react';
import { api, getToken } from '../api.js';
import DraftLayer from './DraftLayer.jsx';
import { scrollHost } from './scrollHost.js';
import { captureNode, detachForCapture, warmUpCapture } from './captureNode.js';

// 笔色。放在这儿而不是 DraftLayer 里：工具栏是这边画的，
// 而 DraftLayer 只该导出组件本身（否则 react-refresh 失效）。
const PEN_COLORS = ['#1a1a1a', '#e53935', '#1e88e5'];

// ─── 工具函数 ──────────────────────────────────────────────────

const fmtDuration = (sec) => {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

const answerString = (sel) => (Array.isArray(sel) ? [...sel].sort().join('') : '');

const withToken = (url) => `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(getToken())}`;

const typeLabelOf = (t) => (t === 'multi' ? '多选题' : t === 'judge' ? '判断题' : '单选题');

const normalizeJudgeOptions = (options) =>
  options && options.length >= 2
    ? options
    : [{ key: 'A', text: '正确', images: [] }, { key: 'B', text: '错误', images: [] }];

const optionsOf = (q) =>
  q?.question_type === 'judge' ? normalizeJudgeOptions(q.options) : q?.options || [];

const scrollPage = (from, ratio) => {
  const host = scrollHost(from);
  const top = (host ? host.clientHeight : window.innerHeight) * ratio;
  if (host) host.scrollBy({ top, behavior: 'smooth' });
  else window.scrollBy({ top, behavior: 'smooth' });
};

const scrollToTop = (from) => {
  const host = scrollHost(from);
  if (host) host.scrollTo({ top: 0, behavior: 'smooth' });
  else window.scrollTo({ top: 0, behavior: 'smooth' });
};

// 1Hz 心跳，只在需要走秒时才起 interval
const useTick = (running) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  return now;
};

// ─── 小组件 ────────────────────────────────────────────────────

const ImageList = ({ images }) => {
  if (!images || images.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {images.map((src, i) => (
        <img key={i} src={src} alt="" loading="lazy"
          className="max-w-full rounded-xl border border-[#e8d5b0] bg-white" />
      ))}
    </div>
  );
};

const OptionRow = ({ option, state, onClick, disabled }) => {
  const stateCls = {
    idle: 'bg-white border-[#e8d5b0]',
    selected: 'bg-[#f4e6c8] border-[#6b5428] shadow-sm',
    correct: 'bg-[#f1f8f2] border-[#4caf50]',
    wrong: 'bg-[#fdf1f1] border-[#ef5350]',
    missed: 'bg-[#f1f8f2] border-[#a5d6a7] border-dashed',
  }[state] || '';
  const badgeCls = {
    idle: 'bg-[#e8d5b0] text-[#1a1a1a]',
    selected: 'bg-[#2c261c] text-white',
    correct: 'bg-[#4caf50] text-white',
    wrong: 'bg-[#ef5350] text-white',
    missed: 'bg-[#a5d6a7] text-white',
  }[state] || '';

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      // iPad 上是手指点：整行都是热区，最小高度顶到 56px
      className={`w-full text-left px-4 py-4 min-h-[56px] rounded-2xl border-2 transition-colors flex items-start gap-3 ${stateCls}`}
    >
      <span className={`shrink-0 w-9 h-9 rounded-xl font-black flex items-center justify-center text-sm ${badgeCls}`}>
        {option.key}
      </span>
      <span className="flex-1 min-w-0 pt-1.5">
        <span className="block text-[15px] leading-relaxed break-words whitespace-pre-wrap">{option.text}</span>
        <ImageList images={option.images} />
      </span>
      {state === 'correct' && <Check size={20} className="shrink-0 text-[#4caf50] mt-2" />}
      {state === 'wrong' && <XIcon size={20} className="shrink-0 text-[#ef5350] mt-2" />}
    </button>
  );
};

// 演算区：草稿纸的空白部分。题干在上面能圈划，式子列在这儿。
const ScratchPad = ({ rows, onAddRow, fill }) => {
  if (rows <= 0) return null;
  const height = fill
    ? `max(${rows * 300}px, calc(100dvh - 11rem))`
    : rows * 300;
  return (
    <div className="mt-4 rounded-[1.5rem] border-2 border-dashed border-[#dcc89a] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-2.5 bg-[#f2e4c4] border-b border-[#ead9b0]">
        <span className="text-[10px] font-black uppercase tracking-widest text-[#c3bda8]">演算区</span>
        <button
          type="button"
          onClick={onAddRow}
          data-capture-ignore="1"
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-black text-[#b3ab93] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors"
        >
          <Plus size={12} />
          <span>加高</span>
        </button>
      </div>
      <div
        style={{
          height,
          background: '#f2e4c4',
          backgroundImage: 'repeating-linear-gradient(to bottom, transparent 0 31px, #e0cd9a 31px 32px)',
        }}
      />
    </div>
  );
};

// 答题卡：哪些做了、哪些空着、哪些标记了，点一下直达。
// 必须 portal 到 body —— 外层 <main> 带 backdrop-blur，会成为包含块，
// 在它内部写 fixed inset-0 只能铺满 main、铺不满屏幕。
const AnswerSheet = ({ questions, answers, flags, index, onJump, onClose }) => createPortal(
  <div className="fixed inset-0 z-[9998] flex justify-end" data-capture-ignore="1">
    <button
      type="button"
      aria-label="关闭答题卡"
      onClick={onClose}
      className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
    />
    <div
      className="relative w-[min(22rem,88vw)] h-full bg-white shadow-2xl flex flex-col animate-slideIn"
      style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#e8d5b0]">
        <span className="text-xs font-black uppercase tracking-widest text-[#999]">答题卡</span>
        <button onClick={onClose} className="p-2 -m-2 rounded-xl text-[#bbb] hover:text-[#1a1a1a]">
          <XIcon size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">
        <div className="grid grid-cols-5 gap-2.5">
          {questions.map((q, i) => {
            const done = (answers[q.id] || []).length > 0;
            return (
              <button
                key={q.id}
                onClick={() => { onJump(i); onClose(); }}
                className={`relative h-11 rounded-xl border-2 text-sm font-black tabular-nums transition-colors ${
                  done ? 'bg-[#1a1a1a] text-white border-[#1a1a1a]' : 'bg-white text-[#bbb] border-[#eee]'
                } ${i === index ? 'ring-2 ring-[#6b5428] ring-offset-2' : ''}`}
              >
                {i + 1}
                {flags.has(q.id) && (
                  <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-[#2c261c] border border-white" />
                )}
              </button>
            );
          })}
        </div>
        <div className="mt-6 space-y-1.5 text-[11px] font-bold text-[#999]">
          <p className="flex items-center gap-2"><span className="w-3 h-3 rounded bg-[#1a1a1a]" />已作答</p>
          <p className="flex items-center gap-2"><span className="w-3 h-3 rounded border-2 border-[#eee]" />还没做</p>
          <p className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-[#2c261c]" />做了标记</p>
        </div>
      </div>
    </div>
  </div>,
  document.body,
);

// ─── 交卷后的成绩 / 复盘 ────────────────────────────────────────

const ScoreCard = ({ title, result }) => (
  <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-8 sm:p-10 relative overflow-hidden">
    <div className="absolute top-6 right-6 w-32 h-32 bg-[#2c261c] rounded-full blur-[40px] opacity-60" />
    <div className="relative z-10">
      <div className="w-14 h-14 rounded-2xl bg-[#2c261c] text-white flex items-center justify-center mb-5">
        <Trophy size={26} />
      </div>
      <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mb-1">{title || 'AI 练题'}</p>
      <h3 className="text-3xl font-black italic">
        对了 {result.correct} / {result.total} 道
      </h3>
      <div className="mt-8 grid grid-cols-3 gap-4">
        <div>
          <p className="text-4xl font-black tabular-nums">{result.accuracy}%</p>
          <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">正确率</p>
        </div>
        <div>
          <p className="text-4xl font-black tabular-nums">{result.total - result.correct}</p>
          <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">错 / 空</p>
        </div>
        <div>
          <p className="text-4xl font-black tabular-nums">{fmtDuration(result.duration_sec)}</p>
          <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">总用时</p>
        </div>
      </div>
    </div>
  </div>
);

const ReviewItem = ({ item, no, open, onToggle }) => {
  const opts = optionsOf(item);
  const mine = new Set((item.user_answer || '').split(''));
  const right = new Set((item.correct_answer || '').split(''));
  const stateOf = (key) => {
    if (mine.has(key) && right.has(key)) return 'correct';
    if (mine.has(key)) return 'wrong';
    if (right.has(key)) return 'missed';
    return 'idle';
  };

  return (
    <div className="bg-white rounded-[1.75rem] border border-[#e8d5b0] overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-[#f2e4c4] transition-colors"
      >
        <span className={`shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-xs font-black ${
          item.skipped ? 'bg-[#e8d5b0] text-[#bbb]'
            : item.is_correct ? 'bg-[#e8f5e9] text-[#2e7d32]' : 'bg-[#fdecea] text-[#c62828]'
        }`}>
          {no}
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-sm font-bold truncate">{item.content}</span>
          <span className="block text-[11px] font-bold text-[#bbb] mt-0.5">
            我选 {item.user_answer || '—'} · 正确 {item.correct_answer} · 用时 {fmtDuration(item.time_spent_sec)}
            {item.draft_url ? ' · 有草稿' : ''}
          </span>
        </span>
        {item.skipped
          ? <span className="shrink-0 text-[10px] font-black text-[#bbb]">空题</span>
          : item.is_correct
            ? <Check size={18} className="shrink-0 text-[#4caf50]" />
            : <XIcon size={18} className="shrink-0 text-[#ef5350]" />}
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-4 border-t border-[#f7f5ee] pt-4">
          {item.knowledge_points?.length > 0 && (
            <p className="text-sm font-bold text-[#6b5428]">
              本题考察知识点：{item.knowledge_points[0]}
            </p>
          )}
          <div className="text-[15px] leading-[1.9] whitespace-pre-wrap break-words font-medium">
            {item.content}
          </div>
          <ImageList images={item.stem_images} />
          <div className="space-y-2.5">
            {opts.map((o) => (
              <OptionRow key={o.key} option={o} state={stateOf(o.key)} disabled onClick={() => {}} />
            ))}
          </div>

          <div className="rounded-2xl bg-[#f4e6c8] border border-[#f7e9b8] p-5">
            <div className="flex items-center gap-2 mb-2">
              <Lightbulb size={15} className="text-[#6b5428]" />
              <span className="text-[10px] font-black uppercase tracking-widest text-[#a8935a]">解析</span>
            </div>
            {item.explanation ? (
              <div className="text-[14px] leading-[1.85] whitespace-pre-wrap break-words">{item.explanation}</div>
            ) : (
              <p className="text-sm text-[#bbb] italic">（本题暂无解析）</p>
            )}
            <ImageList images={item.explanation_images} />
          </div>

          {item.draft_url && (
            <div className="rounded-2xl border border-[#e8d5b0] overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-[#faf9f5]">
                <PenTool size={13} className="text-[#999]" />
                <span className="text-[10px] font-black uppercase tracking-widest text-[#999]">
                  当时的草稿纸
                </span>
              </div>
              <img src={withToken(item.draft_url)} alt="草稿纸" className="w-full block bg-white" />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── 主组件 ────────────────────────────────────────────────────

const AIQuizSession = ({ batchId, batchName, reviewSessionId, onExit, onAnalyzeWithHermes }) => {
  // 界面上只出题组名；batchId 只用来请求接口
  const title = batchName || batchId;
  // 带着 reviewSessionId 进来就先铺复盘页（不新建会话），
  // 点了「重做」才真开新的一场
  const [redoing, setRedoing] = useState(false);
  const reviewing = !!reviewSessionId && !redoing;
  const [phase, setPhase] = useState('loading');     // loading|running|grading|finished|empty|error
  const [errMsg, setErrMsg] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [historyMap, setHistoryMap] = useState({});
  const [index, setIndex] = useState(0);

  const [answers, setAnswers] = useState({});        // { [qid]: ['A'] }
  const [flags, setFlags] = useState(() => new Set());
  const [timeSpent, setTimeSpent] = useState({});    // { [qid]: 累计秒 }
  const [drafts, setDrafts] = useState({});          // { [qid]: stroke[] }

  const [draftMode, setDraftMode] = useState(false);
  const [tool, setTool] = useState('pen');
  const [color, setColor] = useState(PEN_COLORS[0]);
  const [scratchRows, setScratchRows] = useState(0);
  const [savingDraft, setSavingDraft] = useState(false);

  const [showSheet, setShowSheet] = useState(false);
  const [result, setResult] = useState(null);
  const [report, setReport] = useState(null);
  const [openReview, setOpenReview] = useState(null);

  // 计时用的两个时间戳都放 state：render 里要读，读 ref 会拿到不触发更新的值
  const [sessionStart, setSessionStart] = useState(0);
  // enter = 「当前停留的这道题」和「这一次进来的时刻」，离开时把差值累加进 timeSpent
  const [enter, setEnter] = useState({ qid: null, at: 0 });

  const paperRef = useRef(null);
  const dirtyDraftsRef = useRef(new Set());
  const draftQueueRef = useRef(Promise.resolve());
  const savingCountRef = useRef(0);
  const bumpSaving = useCallback((d) => {
    savingCountRef.current = Math.max(0, savingCountRef.current + d);
    setSavingDraft(savingCountRef.current > 0);
  }, []);
  const uploadedRef = useRef(new Set());

  const current = questions[index];
  const total = questions.length;
  const running = phase === 'running';
  const now = useTick(running);

  // ── 载入 ──
  // 载入逻辑放在 effect 里的 async IIFE 里，而不是抽成 useCallback 再在 effect 体里调：
  // 后者是在 effect 体里同步触发 setState，会引起级联渲染。
  // 重刷一遍靠 runKey 自增来重跑这个 effect。
  const [runKey, setRunKey] = useState(0);

  useEffect(() => {
    let aborted = false;
    (async () => {
      try {
        if (reviewing) {
          // 复盘：直接把那一场的报告拉出来，成绩卡从会话行重建
          const rep = await api(`/api/practice/sessions/${reviewSessionId}/report`);
          if (aborted) return;
          const items = rep?.items || [];
          if (items.length === 0) {
            setErrMsg('这次练习没留下作答记录');
            setPhase('error');
            return;
          }
          const s = rep.session || {};
          const total = s.total || items.length;
          const correct = s.correct ?? items.filter((it) => it.is_correct).length;
          setSessionId(reviewSessionId);
          setReport(rep);
          setResult({
            total,
            correct,
            accuracy: total ? Math.round((correct / total) * 100) : 0,
            duration_sec: s.duration_sec || 0,
          });
          setOpenReview(null);
          setErrMsg('');
          setPhase('finished');
          return;
        }

        const params = new URLSearchParams({ batch_id: batchId, random: '1', limit: '30' });
        const [qres, hist] = await Promise.all([
          api('/api/questions?' + params.toString()),
          api('/api/questions/meta/history?batch_id=' + encodeURIComponent(batchId)).catch(() => ({})),
        ]);
        if (aborted) return;
        const items = qres?.items || [];
        if (items.length === 0) { setPhase('empty'); return; }
        const s = await api('/api/practice/sessions', { method: 'POST', body: { category: batchId } });
        if (aborted) return;

        setQuestions(items);
        setHistoryMap(hist && typeof hist === 'object' ? hist : {});
        setSessionId(s.id);
        setIndex(0);
        setAnswers({});
        setFlags(new Set());
        setTimeSpent({});
        setDrafts({});
        setScratchRows(0);
        setResult(null);
        setReport(null);
        setOpenReview(null);
        setErrMsg('');
        dirtyDraftsRef.current = new Set();
        uploadedRef.current = new Set();
        setSessionStart(Date.now());
        setEnter({ qid: items[0].id, at: Date.now() });
        setPhase('running');
      } catch (e) {
        if (aborted) return;
        setErrMsg(e?.message || '加载失败');
        setPhase('error');
      }
    })();
    return () => { aborted = true; };
  }, [batchId, runKey, reviewing, reviewSessionId]);

  // 重做 / 再刷一遍：都是开全新的一场。redoing 一旦置上，上面那个 effect
  // 就不再走复盘分支。旧成绩在库里原封不动，新这场交了卷才会取代它
  const restart = () => { setRedoing(true); setPhase('loading'); setRunKey((k) => k + 1); };

  // ── 计时 ──
  // 把某一段停留结算进 timeSpent。只从事件处理器 / 回调里调，不在 render 里调。
  const settle = useCallback((slot) => {
    if (!slot?.qid || !slot?.at) return;
    const delta = Math.round((Date.now() - slot.at) / 1000);
    if (delta <= 0) return;
    setTimeSpent((prev) => ({ ...prev, [slot.qid]: (prev[slot.qid] || 0) + delta }));
  }, []);

  // 切到后台 / 锁屏不该算进「我在这题上停留了多久」
  useEffect(() => {
    if (!running) return;
    const onVisibility = () => {
      if (document.hidden) {
        settle(enter);
        setEnter((cur) => ({ ...cur, at: 0 }));
      } else {
        setEnter((cur) => ({ ...cur, at: Date.now() }));
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [running, enter, settle]);

  const totalElapsed = sessionStart ? Math.round((now - sessionStart) / 1000) : 0;
  const currentElapsed = current
    ? (timeSpent[current.id] || 0)
      + (enter.qid === current.id && enter.at ? Math.max(0, Math.round((now - enter.at) / 1000)) : 0)
    : 0;

  // ── 草稿纸 ──
  const currentStrokes = current ? drafts[current.id] || [] : [];
  const hasDraft = currentStrokes.length > 0;

  const pushStroke = useCallback((stroke) => {
    const qid = current?.id;
    if (!qid) return;
    dirtyDraftsRef.current.add(qid);
    setDrafts((prev) => ({ ...prev, [qid]: [...(prev[qid] || []), stroke] }));
  }, [current?.id]);

  const mutateStrokes = (fn) => {
    const qid = current?.id;
    if (!qid) return;
    dirtyDraftsRef.current.add(qid);
    setDrafts((prev) => ({ ...prev, [qid]: fn(prev[qid] || []) }));
  };

  // 草稿存盘：抓快照这一下是同步的，截图和上传都甩到后台，翻页不用等。
  // 失败就把这道题重新标脏，下次离开它会再试一次。
  const persistDraft = useCallback((qid) => {
    if (!sessionId || !qid) return;
    if ((drafts[qid] || []).length === 0) return;
    if (!dirtyDraftsRef.current.has(qid) && uploadedRef.current.has(qid)) return;

    const snap = detachForCapture(paperRef.current);
    if (!snap) return;
    dirtyDraftsRef.current.delete(qid);
    bumpSaving(1);

    // 排成一队跑：截图在 iPad 上不便宜，连着翻几页也不该几张图一起挤
    draftQueueRef.current = draftQueueRef.current.then(async () => {
      try {
        const dataUrl = await captureNode(snap.node);
        if (!dataUrl) return;
        await api(`/api/practice/sessions/${sessionId}/drafts/${qid}`, {
          method: 'PUT',
          body: { data: dataUrl, mime: 'image/png' },
        });
        uploadedRef.current.add(qid);
      } catch (e) {
        dirtyDraftsRef.current.add(qid);
        setErrMsg(`草稿纸保存失败：${e?.message || '未知错误'}`);
      } finally {
        snap.dispose();
        bumpSaving(-1);
      }
    });
  }, [sessionId, drafts, bumpSaving]);

  // ── 导航 ──
  const goTo = useCallback((nextIndex) => {
    if (nextIndex < 0 || nextIndex >= total || nextIndex === index) return;
    settle(enter);
    persistDraft(current?.id);
    setIndex(nextIndex);
    setEnter({ qid: questions[nextIndex].id, at: Date.now() });
  }, [total, index, enter, settle, persistDraft, current?.id, questions]);

  const toggleSelect = useCallback((key) => {
    const q = current;
    if (!q || !running) return;
    setAnswers((prev) => {
      const cur = prev[q.id] || [];
      if (q.question_type === 'multi') {
        const next = cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key].sort();
        return { ...prev, [q.id]: next };
      }
      // 单选/判断再点一次同一项 = 取消，方便改主意时留空
      return { ...prev, [q.id]: cur[0] === key ? [] : [key] };
    });
  }, [current, running]);

  const toggleFlag = () => {
    const qid = current?.id;
    if (!qid) return;
    setFlags((prev) => {
      const next = new Set(prev);
      if (next.has(qid)) next.delete(qid); else next.add(qid);
      return next;
    });
  };

  // ── 交卷 ──
  const answeredCount = useMemo(
    () => questions.filter((q) => (answers[q.id] || []).length > 0).length,
    [questions, answers],
  );

  // 退出：没交卷就不算这一次，所以把这场残局连草稿一起删掉，
  // 复盘里看到的仍然是上一次交过卷的那份
  const exitQuiz = async () => {
    if (phase === 'running' && sessionId) {
      const touched = answeredCount > 0
        || Object.values(drafts).some((strokes) => (strokes || []).length > 0);
      if (touched && !confirm('这次还没交卷，退出就不算这一次，已经写的作答和草稿都会丢。确定退出？')) return;
      await api(`/api/practice/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {});
    }
    onExit();
  };

  const submitAll = async () => {
    if (!sessionId || phase !== 'running') return;
    const blank = total - answeredCount;
    if (blank > 0 && !confirm(`还有 ${blank} 道没做，确定交卷吗？\n\n空着的题按答错计。`)) return;

    // 当前题最后这一段停留还没进 timeSpent（setState 是异步的），
    // 所以先取出来在 payload 里手动补上，别走 settle
    const pendingQid = enter.qid;
    const pendingSec = enter.at ? Math.max(0, Math.round((Date.now() - enter.at) / 1000)) : 0;

    setDraftMode(false);
    persistDraft(current?.id);
    setPhase('grading');
    setErrMsg('');
    // 交卷是唯一该等的地方：不等完，复盘页里最后一题会显示成没留草稿
    await draftQueueRef.current;

    const payload = questions.map((q) => ({
      question_id: q.id,
      user_answer: answerString(answers[q.id]),
      time_spent_sec: (timeSpent[q.id] || 0) + (q.id === pendingQid ? pendingSec : 0),
    }));

    try {
      const res = await api(`/api/practice/sessions/${sessionId}/submit`, {
        method: 'POST',
        body: {
          duration_sec: Math.round((Date.now() - sessionStart) / 1000),
          answers: payload,
        },
      });
      setResult(res);
      const rep = await api(`/api/practice/sessions/${sessionId}/report`).catch(() => null);
      setReport(rep);
      setPhase('finished');
      scrollToTop(paperRef.current);
    } catch (e) {
      setErrMsg(e?.message || '交卷失败');
      setPhase('running');
    }
  };

  // ── 快捷键 ──
  useEffect(() => {
    if (!running) return;
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;
      if (e.key === 'Escape' && draftMode) { e.preventDefault(); setDraftMode(false); return; }
      if (draftMode) return;
      const k = e.key.toUpperCase();
      if (['A', 'B', 'C', 'D', 'E'].includes(k)) {
        if (optionsOf(current).some((o) => o.key === k)) { e.preventDefault(); toggleSelect(k); }
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        e.preventDefault();
        goTo(index + 1);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goTo(index - 1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [running, draftMode, current, index, goTo, toggleSelect]);

  // 提前把截图库拉下来，别等到真要存草稿时才下载
  useEffect(() => { if (draftMode) warmUpCapture(); }, [draftMode]);

  // ── 各种非做题状态 ──
  if (phase === 'loading') {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Loader2 size={26} className="text-[#6b5428] animate-spin mb-3" />
        <p className="text-sm font-black uppercase tracking-widest text-[#bbb]">加载题目中…</p>
      </div>
    );
  }
  if (phase === 'empty' || phase === 'error') {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <div className={`bg-white rounded-[2rem] p-10 text-center shadow-sm border max-w-md w-full ${
          phase === 'error' ? 'border-red-200' : 'border-[#e8d5b0]'
        }`}>
          <div className={`w-14 h-14 mx-auto rounded-2xl flex items-center justify-center mb-4 ${
            phase === 'error' ? 'bg-red-100 text-red-500' : 'bg-[#e8d5b0] text-[#bbb]'
          }`}>
            <AlertTriangle size={24} />
          </div>
          <h3 className="text-xl font-black italic mb-2">
            {phase === 'error' ? '加载失败' : '这批还没有题目'}
          </h3>
          <p className="text-sm text-[#999] mb-6">{phase === 'error' ? errMsg : title}</p>
          <button onClick={onExit}
            className="bg-[#1a1a1a] text-white font-black px-8 py-3 rounded-2xl hover:bg-[#2c261c] hover:text-white transition-all uppercase tracking-widest text-xs">
            返回
          </button>
        </div>
      </div>
    );
  }

  // ── 成绩 + 逐题复盘 ──
  if (phase === 'finished' && result) {
    const items = report?.items || [];
    const hasWrong = items.some((it) => !it.is_correct);
    return (
      <div className="h-full overflow-y-auto overscroll-y-contain px-4 sm:px-6 py-6">
      <div className="max-w-3xl mx-auto space-y-5 pb-10">
        <ScoreCard title={reviewing ? `${title} · 复盘` : title} result={result} />

        <div className="flex flex-col sm:flex-row gap-3">
          <button onClick={restart}
            className="flex-1 flex items-center justify-center gap-2 bg-white border-2 border-[#1a1a1a] text-[#1a1a1a] font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs">
            <RotateCcw size={16} /><span>{reviewing ? '重做这套' : '再刷一遍'}</span>
          </button>
          {onAnalyzeWithHermes && hasWrong && (
            <button onClick={() => { onAnalyzeWithHermes(sessionId); onExit(); }}
              className="flex-1 flex items-center justify-center gap-2 bg-[#1a1a1a] text-white font-black px-6 py-4 rounded-2xl hover:opacity-90 transition-all uppercase tracking-widest text-xs">
              <Send size={16} /><span>让 Hermes 复盘错题</span>
            </button>
          )}
          <button onClick={onExit}
            className="flex-1 flex items-center justify-center gap-2 bg-[#2c261c] text-white font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs">
            <span>返回批次</span><ArrowRight size={16} />
          </button>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <p className="text-[10px] font-black uppercase tracking-widest text-[#bbb]">逐题对答案</p>
            <button
              onClick={() => setOpenReview(openReview === 'all' ? null : 'all')}
              className="text-[10px] font-black uppercase tracking-widest text-[#999] hover:text-[#1a1a1a]"
            >
              {openReview === 'all' ? '全部收起' : '全部展开'}
            </button>
          </div>
          {items.length === 0 && (
            <p className="text-sm text-[#bbb] px-1">拿不到逐题明细，可能是网络问题，退出重进看看。</p>
          )}
          {items.map((it, i) => (
            <ReviewItem
              key={it.question_id}
              item={it}
              no={i + 1}
              open={openReview === 'all' || openReview === it.question_id}
              onToggle={() => setOpenReview((cur) => (cur === it.question_id ? null : it.question_id))}
            />
          ))}
        </div>
      </div>
      </div>
    );
  }

  // ── 做题中 ──
  const selection = current ? answers[current.id] || [] : [];
  const history = historyMap[current?.id];
  const hasHistory = history && history.attempts > 0;
  const isLast = index + 1 >= total;
  const grading = phase === 'grading';

  return (
    <div
      className="h-full min-h-0 flex flex-col bg-white"
      style={{
        paddingTop: window.matchMedia('(pointer: coarse)').matches
          ? 'max(2rem, env(safe-area-inset-top, 0px))'
          : undefined,
      }}
    >
      {/* 顶栏 */}
      <div
        className="shrink-0 flex items-center justify-between gap-2 px-3 py-2 border-b border-[#e8d5b0]"
        data-capture-ignore="1"
      >
        <button onClick={exitQuiz}
          className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-[#999] hover:bg-[#e8d5b0] hover:text-[#1a1a1a] transition-colors">
          <ArrowLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest hidden sm:inline">退出</span>
        </button>

        <div className="flex items-center gap-3 sm:gap-4">
          <div className="flex items-center gap-1.5 text-[#999]">
            <Clock size={14} />
            <span className="text-xs font-mono tabular-nums font-black">{fmtDuration(totalElapsed)}</span>
          </div>
          <span className="text-xs font-black tabular-nums text-[#bbb]">
            已答 <span className="text-[#1a1a1a]">{answeredCount}</span>/{total}
          </span>
          <button
            onClick={() => setShowSheet(true)}
            className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-black text-[#999] hover:bg-[#e8d5b0] hover:text-[#1a1a1a] transition-colors"
          >
            <Grid3x3 size={15} />
            <span className="hidden sm:inline">答题卡</span>
          </button>
        </div>
      </div>

      <div className="shrink-0 h-1 bg-[#e8d5b0]">
        <div className="h-full bg-[#2c261c] transition-all duration-300"
          style={{ width: `${total > 0 ? (answeredCount / total) * 100 : 0}%` }} />
      </div>

      {errMsg && (
        <div className="shrink-0 mx-4 mt-3 px-4 py-2.5 rounded-xl bg-red-50 border border-red-200 text-xs font-bold text-red-700 flex justify-between">
          <span>{errMsg}</span>
          <button onClick={() => setErrMsg('')} className="ml-3 text-red-400 hover:text-red-700">
            <XIcon size={13} />
          </button>
        </div>
      )}

      {/* 草稿纸范围：题干、选项、演算区都在这一层里，批注层盖在最上面 */}
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-y-contain px-3 sm:px-5 py-3">
      <div ref={paperRef} className={`relative ${draftMode ? 'min-h-full' : ''}`}>
        <div className={`bg-white rounded-[1.5rem] p-5 sm:p-8 border-2 transition-colors ${
          draftMode ? 'border-[#6b5428]' : 'border-[#e8d5b0]'
        }`}>
          <div className="flex items-center justify-between gap-2 mb-5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-black uppercase tracking-widest bg-[#1a1a1a] text-white px-3 py-1 rounded-full">
                {typeLabelOf(current?.question_type)}
              </span>
              {current?.sub_category && (
                <span className="text-[10px] font-black uppercase tracking-widest text-[#bbb]">
                  {current.sub_category}
                </span>
              )}
              {hasHistory && (
                history.last_correct
                  ? <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-[#e8f5e9] text-[#2e7d32]">上次答对</span>
                  : <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-[#fdecea] text-[#c62828]">
                      上次答错 · 错了 {history.wrong} 次
                    </span>
              )}
              {flags.has(current?.id) && (
                <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-[#f3e0a8] text-[#8a5400]">已标记</span>
              )}
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              <span className="text-[10px] font-black tabular-nums text-[#bbb]">
                本题 <span className="text-[#6b5428]">{fmtDuration(currentElapsed)}</span>
              </span>
              <span className="text-sm font-mono tabular-nums font-black text-[#bbb]">
                {index + 1}/{total}
              </span>
            </div>
          </div>

          <div className="text-[16px] leading-[1.9] text-[#1a1a1a] whitespace-pre-wrap break-words font-medium">
            {current?.content}
          </div>
          <ImageList images={current?.stem_images} />

          {current?.question_type === 'multi' && (
            <p className="mt-4 text-xs font-black uppercase tracking-widest text-[#6b5428]">
              多选题 · 至少选两项，答错不得分
            </p>
          )}

          <div className="mt-6 space-y-3">
            {optionsOf(current).map((opt) => (
              <OptionRow
                key={opt.key}
                option={opt}
                state={selection.includes(opt.key) ? 'selected' : 'idle'}
                onClick={() => toggleSelect(opt.key)}
              />
            ))}
          </div>
        </div>

        <ScratchPad rows={scratchRows} fill={draftMode} onAddRow={() => setScratchRows((r) => r + 1)} />

        <DraftLayer
          active={draftMode}
          visible={draftMode}
          tool={tool}
          color={color}
          strokes={currentStrokes}
          onStrokeEnd={pushStroke}
        />
      </div>
      </div>

      <div
        className="shrink-0 px-3 pt-2 border-t border-[#e8d5b0] bg-white"
        style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))' }}
        data-capture-ignore="1"
      >
        {draftMode ? (
          <div className="flex items-center gap-1.5 sm:gap-2 bg-white rounded-2xl p-2 shadow-lg border border-[#e8d5b0] overflow-x-auto">
            {PEN_COLORS.map((c) => (
              <button
                key={c}
                onClick={() => { setTool('pen'); setColor(c); }}
                title="笔"
                className={`shrink-0 w-11 h-11 rounded-xl flex items-center justify-center transition-all ${
                  tool === 'pen' && color === c ? 'bg-[#e8d5b0] ring-2 ring-[#6b5428]' : 'hover:bg-black/5'
                }`}
              >
                <span className="w-5 h-5 rounded-full" style={{ background: c }} />
              </button>
            ))}
            <button
              onClick={() => setTool('highlighter')}
              title="荧光笔（圈划题干）"
              className={`shrink-0 w-11 h-11 rounded-xl flex items-center justify-center transition-colors ${
                tool === 'highlighter' ? 'bg-[#2c261c] text-white' : 'text-[#999] hover:bg-black/5'
              }`}
            >
              <Highlighter size={17} />
            </button>
            <button
              onClick={() => setTool('eraser')}
              title="橡皮"
              className={`shrink-0 w-11 h-11 rounded-xl flex items-center justify-center transition-colors ${
                tool === 'eraser' ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5'
              }`}
            >
              <Eraser size={17} />
            </button>

            <span className="shrink-0 w-px h-7 bg-[#e8d5b0] mx-0.5" />

            <button onClick={() => mutateStrokes((s) => s.slice(0, -1))}
              disabled={!hasDraft} title="撤销一笔"
              className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-30 transition-colors">
              <Undo2 size={17} />
            </button>
            <button onClick={() => mutateStrokes(() => [])}
              disabled={!hasDraft} title="清空本题草稿"
              className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-[#999] hover:bg-red-50 hover:text-[#ef5350] disabled:opacity-30 transition-colors">
              <Trash2 size={17} />
            </button>
            <button onClick={() => setScratchRows((r) => r + 1)} title="加一块演算区"
              className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors">
              <Plus size={17} />
            </button>

            <span className="shrink-0 w-px h-7 bg-[#e8d5b0] mx-0.5" />

            {/* 批注时 canvas 吃掉了触摸手势，翻页得给按钮 */}
            <button onClick={() => scrollPage(paperRef.current, -0.7)} title="上翻"
              className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-[#999] hover:bg-black/5">
              <ChevronUp size={17} />
            </button>
            <button onClick={() => scrollPage(paperRef.current, 0.7)} title="下翻"
              className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-[#999] hover:bg-black/5">
              <ChevronDown size={17} />
            </button>
            <button
              onClick={() => goTo(index - 1)}
              disabled={index === 0}
              title="上一题"
              className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-[#999] hover:bg-black/5 disabled:opacity-30"
            >
              <ArrowLeft size={17} />
            </button>
            <button
              onClick={() => goTo(index + 1)}
              disabled={isLast}
              title="下一题"
              className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-[#999] hover:bg-black/5 disabled:opacity-30"
            >
              <ArrowRight size={17} />
            </button>

            <button
              onClick={() => {
                persistDraft(current?.id);
                setDraftMode(false);
              }}
              className="ml-auto shrink-0 flex items-center gap-1.5 bg-[#1a1a1a] text-white px-4 h-11 rounded-xl text-xs font-black uppercase tracking-widest hover:opacity-90 transition-opacity"
            >
              <Check size={15} />
              <span>保留草稿</span>
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              onClick={() => goTo(index - 1)}
              disabled={index === 0}
              title="上一题"
              className="shrink-0 h-14 px-4 rounded-2xl bg-white border-2 border-[#e8d5b0] text-[#999] font-black flex items-center gap-1.5 hover:border-[#1a1a1a] hover:text-[#1a1a1a] disabled:opacity-40 transition-colors"
            >
              <ArrowLeft size={17} />
              <span className="text-xs uppercase tracking-widest hidden sm:inline">上一题</span>
            </button>

            <button
              onClick={toggleFlag}
              title="标记本题，回头再看"
              className={`shrink-0 h-14 w-14 rounded-2xl border-2 flex items-center justify-center transition-colors ${
                flags.has(current?.id)
                  ? 'bg-[#f3e0a8] border-[#6b5428] text-[#8a5400]'
                  : 'bg-white border-[#e8d5b0] text-[#bbb] hover:border-[#1a1a1a] hover:text-[#1a1a1a]'
              }`}
            >
              <Bookmark size={18} />
            </button>

            <button
              onClick={() => { setDraftMode(true); setScratchRows((r) => Math.max(r, 1)); }}
              title={hasDraft
                ? '草稿纸：这题留了草稿，打开就能看到'
                : '草稿纸：在题目上圈划、在下面演算'}
              className={`shrink-0 h-14 px-4 rounded-2xl border-2 flex items-center gap-1.5 font-black transition-colors ${
                hasDraft
                  ? 'bg-[#2c261c] border-[#6b5428] text-white'
                  : 'bg-white border-[#e8d5b0] text-[#999] hover:border-[#1a1a1a] hover:text-[#1a1a1a]'
              }`}
            >
              <PenTool size={17} />
              <span className="text-xs uppercase tracking-widest hidden sm:inline">草稿纸</span>
            </button>

            {isLast ? (
              <button
                onClick={submitAll}
                disabled={grading}
                className="flex-1 h-14 rounded-2xl bg-[#1a1a1a] text-white font-black flex items-center justify-center gap-2 uppercase tracking-widest text-xs hover:bg-[#2c261c] hover:text-white disabled:opacity-60 transition-all shadow-lg"
              >
                {grading
                  ? (<><Loader2 size={17} className="animate-spin" /><span>判分中…</span></>)
                  : (<><Flag size={17} /><span>交卷</span></>)}
              </button>
            ) : (
              <button
                onClick={() => goTo(index + 1)}
                className="flex-1 h-14 rounded-2xl bg-[#1a1a1a] text-white font-black flex items-center justify-center gap-2 uppercase tracking-widest text-xs hover:bg-[#2c261c] hover:text-white disabled:opacity-60 transition-all shadow-lg"
              >
                <span>下一题</span>
                <ArrowRight size={17} />
              </button>
            )}
          </div>
        )}

        <p className="mt-2 text-center text-[10px] font-black uppercase tracking-widest text-[#ccc]">
          {draftMode
            ? 'Apple Pencil 画笔迹 · 双指翻页 · 保留草稿后可再打开'
            : 'A/B/C/D 选择 · ← → 翻题 · 最后一题交卷'}
          {savingDraft && (
            <span className="text-[#ddd]"> · 草稿保存中</span>
          )}
        </p>
      </div>

      {showSheet && (
        <AnswerSheet
          questions={questions}
          answers={answers}
          flags={flags}
          index={index}
          onJump={goTo}
          onClose={() => setShowSheet(false)}
        />
      )}
    </div>
  );
};

export default AIQuizSession;

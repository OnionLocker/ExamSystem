// AI 练题 · 做题会话
//
// 按真考的节奏走：整卷做完再交卷，中途可以随便往前翻回去改；
// 交卷那一刻一次性判分，然后逐题对答案、看解析、回看当时的草稿纸。
//
// 三件事情跟老版本不一样：
//   1. 答案先攒在前端，不再每题即时判分 —— 否则「倒回去重做前面的题」没有意义；
//   2. 单题用时是累计停留时长（来回跳转会累加，切到后台会暂停），不是一次性的差值；
//      总时长也只加停留，熄屏/切走不算；
//   3. 草稿纸是罩在整页上的批注层，能在题干上圈划，离开该题时把整页快照存到后台。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowLeft, ArrowRight, Check, X as XIcon, Clock, Trophy, RotateCcw,
  AlertTriangle, Lightbulb, Flag, PenTool, Loader2, Grid3x3, Eraser,
  Undo2, Trash2, Send,
} from 'lucide-react';
import { api, getToken } from '../api.js';
import { openKnowledge } from '../knowledge/nav.js';
import DraftLayer from './DraftLayer.jsx';
import ExamText from './ExamText.jsx';
import { scrollHost } from './scrollHost.js';
import { captureNode, detachForCapture, warmUpCapture } from './captureNode.js';

const PEN_COLOR = '#1a1a1a';

// ─── 工具函数 ──────────────────────────────────────────────────

const fmtDuration = (sec) => {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

const sessionSeconds = (spent, slot, at = Date.now()) => {
  const pending = slot?.qid && slot?.at ? Math.max(0, Math.round((at - slot.at) / 1000)) : 0;
  return Object.values(spent || {}).reduce((sum, n) => sum + (n || 0), 0) + pending;
};

const answerString = (sel) => (Array.isArray(sel) ? [...sel].sort().join('') : '');

const withToken = (url) => `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(getToken())}`;

const typeLabelOf = (t) => (t === 'multi' ? '多选题' : t === 'judge' ? '判断题' : '单选题');

const keepMaterialGroups = (items, batchId = '') => {
  const daily = String(batchId).startsWith('daily-');
  const blob = (q) => `${q.sub_category || ''}${JSON.stringify(q.tags || [])}`;
  const rank = (q) => {
    const cat = String(q.category || '');
    const text = blob(q);
    if (cat === '数量关系') return text.includes('数字推理') ? 1 : 2;
    if (cat === '科学推理') return 0;
    if (cat === '判断推理') {
      if (text.includes('图形推理')) return 1;
      return 2;
    }
    if (cat === '言语理解与表达') return text.includes('逻辑填空') ? 1 : 2;
    return 0;
  };
  if (!daily && !items.some((q) => q.material_id)) return items;
  return [...items].sort((a, b) =>
    (daily ? rank(a) - rank(b) : 0)
    || (a.material_id || 0) - (b.material_id || 0)
    || a.id - b.id
  );
};

const isZhenti = (q) =>
  q?.origin === 'zhenti'
  || String(q?.external_id || '').startsWith('zhenti-');

const ZhentiMark = ({ compact = false }) => (
  <span className={`font-black tracking-widest rounded-full ${
    compact
      ? 'text-[11px] leading-none bg-[#8b1e1e] text-white px-1.5 py-0.5'
      : 'text-[14px] bg-[#8b1e1e] text-white px-3.5 py-1'
  }`}>
    {compact ? '真' : '真题'}
  </span>
);

const normalizeJudgeOptions = (options) =>
  options && options.length >= 2
    ? options
    : [{ key: 'A', text: '正确', images: [] }, { key: 'B', text: '错误', images: [] }];

const optionsOf = (q) =>
  q?.question_type === 'judge' ? normalizeJudgeOptions(q.options) : q?.options || [];

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

// ─── 小组件 ───────────────────────────────────────────────────

const ImageList = ({ images, wide = false }) => {
  if (!images || images.length === 0) return null;
  const size = wide
    ? 'max-w-full max-h-[560px]'
    : 'w-full max-w-full max-h-[420px] sm:max-h-[480px]';
  const frame = wide
    ? `block w-auto max-w-full ${size} object-contain`
    : `block w-auto max-w-full ${size} object-contain rounded-lg border border-[#e8d5b0] bg-white`;
  return (
    <div className={wide ? 'mt-4 space-y-5' : 'mt-3 space-y-2'}>
      {images.map((src, i) => (
        <img key={`${src}-${i}`} src={src} alt="" loading="lazy" className={frame} />
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
      <span className={`shrink-0 w-10 h-10 rounded-xl font-black flex items-center justify-center text-base ${badgeCls}`}>
        {option.key}
      </span>
      <span className="flex-1 min-w-0 pt-1.5">
        <span className="exam-text block text-[20px] leading-relaxed break-words whitespace-pre-wrap">
          <ExamText text={option.text} />
        </span>
        <ImageList images={option.images} />
      </span>
      {state === 'correct' && <Check size={20} className="shrink-0 text-[#4caf50] mt-2" />}
      {state === 'wrong' && <XIcon size={20} className="shrink-0 text-[#ef5350] mt-2" />}
    </button>
  );
};

// 答题卡：哪些做了、哪些空着、哪些标记了，点一下直达。
// 必须 portal 到 body —— 外层 <main> 带 backdrop-blur，会成为包含块，
// 在它内部写 fixed inset-0 只能铺满 main、铺不满屏幕。
const AnswerSheet = ({ questions, answers, index, onJump, onClose, onSubmit }) => createPortal(
  <div className="fixed inset-0 z-[9998] flex justify-end" data-capture-ignore="1">
    <button
      type="button"
      aria-label="关闭答题卡"
      onClick={onClose}
      className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
    />
    <div
      className="relative w-[min(22rem,88vw)] h-full bg-[#f2e4c4] shadow-2xl flex flex-col animate-slideIn"
      style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#e8d5b0]">
        <span className="text-sm font-black tracking-widest text-[#999]">答题卡</span>
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
                  done ? 'bg-[#1a1a1a] text-white border-[#1a1a1a]' : 'bg-transparent text-[#aaa] border-white/70'
                } ${i === index ? 'ring-2 ring-[#6b5428] ring-offset-2' : ''}`}
              >
                {i + 1}
                {isZhenti(q) && (
                  <span className="absolute -top-1 -right-1">
                    <ZhentiMark compact />
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <div className="mt-6 space-y-1.5 text-sm font-bold text-[#999]">
          <p className="flex items-center gap-2"><span className="w-3 h-3 rounded bg-[#1a1a1a]" />已作答</p>
          <p className="flex items-center gap-2"><span className="w-3 h-3 rounded border-2 border-[#eee]" />还没做</p>
        </div>
      </div>
      <div className="shrink-0 p-5">
        <button
          type="button"
          onClick={onSubmit}
          className="flex h-14 w-full items-center justify-center gap-2 rounded-2xl bg-[#1a1a1a] text-sm font-black tracking-widest text-white shadow-lg hover:bg-[#2c261c]"
        >
          <Flag size={18} />
          <span>交卷</span>
        </button>
      </div>
    </div>
  </div>,
  document.body,
);

// ─── 交卷后的成绩 / 复盘 ───────────────────────────────────────

const BlankSubmitConfirm = ({ blank, grading, onCancel, onConfirm }) => createPortal(
  <div className="fixed inset-0 z-[9999] flex items-center justify-center p-5" role="dialog" aria-modal="true" aria-labelledby="blank-submit-title" data-capture-ignore="1">
    <button type="button" aria-label="继续答题" onClick={onCancel} className="absolute inset-0 bg-black/35 backdrop-blur-[3px]" />
    <div className="relative w-full max-w-sm overflow-hidden rounded-[2rem] border border-white/70 bg-white shadow-2xl">
      <div className="p-6">
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-[#fff3e0] text-[#e87924]">
          <AlertTriangle size={21} />
        </div>
        <h3 id="blank-submit-title" className="text-xl font-black tracking-tight">还有 {blank} 题未答</h3>
        <p className="mt-2 text-sm leading-relaxed text-[#666]">空题会计入本次成绩。建议先回到答题卡补完，确认放弃后也可以直接交卷。</p>
      </div>
      <div className="flex gap-3 border-t border-black/5 bg-[#faf6ed] p-4">
        <button type="button" autoFocus disabled={grading} onClick={onCancel}
          className="flex-1 rounded-2xl border border-black/10 bg-white px-4 py-3 text-sm font-black text-[#555] disabled:opacity-50">
          继续答题
        </button>
        <button type="button" disabled={grading} onClick={onConfirm}
          className="flex-1 rounded-2xl bg-[#1a1a1a] px-4 py-3 text-sm font-black text-white disabled:opacity-60">
          {grading ? <Loader2 size={16} className="mx-auto animate-spin" /> : '仍然交卷'}
        </button>
      </div>
    </div>
  </div>,
  document.body,
);

const ScoreCard = ({ title, result }) => (
  <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-8 sm:p-10 relative overflow-hidden">
    <div className="absolute top-6 right-6 w-32 h-32 bg-[#2c261c] rounded-full blur-[40px] opacity-60" />
    <div className="relative z-10">
      <div className="w-14 h-14 rounded-2xl bg-[#2c261c] text-white flex items-center justify-center mb-5">
        <Trophy size={26} />
      </div>
      <p className="text-sm font-black tracking-widest opacity-60 mb-1">{title || 'AI 练题'}</p>
      <h3 className="text-3xl font-black italic">
        对了 {result.correct} / {result.total} 道
      </h3>
      <div className="mt-8 grid grid-cols-3 gap-4">
        <div>
          <p className="text-4xl font-black tabular-nums">{result.accuracy}%</p>
          <p className="text-sm font-black tracking-widest opacity-60 mt-1">正确率</p>
        </div>
        <div>
          <p className="text-4xl font-black tabular-nums">{result.total - result.correct}</p>
          <p className="text-sm font-black tracking-widest opacity-60 mt-1">错 / 空</p>
        </div>
        <div>
          <p className="text-4xl font-black tabular-nums">{fmtDuration(result.duration_sec)}</p>
          <p className="text-sm font-black tracking-widest opacity-60 mt-1">总用时</p>
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
          <span className="flex items-center gap-2">
            {isZhenti(item) && <ZhentiMark />}
            <span className="block text-base font-bold truncate">{item.content}</span>
          </span>
          <span className="block text-sm font-bold text-[#bbb] mt-0.5">
            我选 {item.user_answer || '—'} · 正确 {item.correct_answer} · 用时 {fmtDuration(item.time_spent_sec)}
            {item.draft_url ? ' · 有草稿' : ''}
          </span>
        </span>
        {item.skipped
          ? <span className="shrink-0 text-sm font-black text-[#bbb]">空题</span>
          : item.is_correct
            ? <Check size={18} className="shrink-0 text-[#4caf50]" />
            : <XIcon size={18} className="shrink-0 text-[#ef5350]" />}
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-4 border-t border-[#f7f5ee] pt-4">
          {item.knowledge_points?.length > 0 && (
            <button
              type="button"
              onClick={() => openKnowledge(item.knowledge_points[0])}
              className="text-sm font-bold text-[#6b5428] underline decoration-dotted underline-offset-4 hover:text-[#1a1a1a]"
            >
              本题考察知识点：{item.knowledge_points[0]}
            </button>
          )}
          <div className="exam-text text-[22px] leading-[1.8] whitespace-pre-wrap break-words font-medium">
            <ExamText text={item.content} />
          </div>
          <ImageList images={item.stem_images} wide />
          <div className="space-y-2.5">
            {opts.map((o) => (
              <OptionRow key={o.key} option={o} state={stateOf(o.key)} disabled onClick={() => {}} />
            ))}
          </div>

          <div className="rounded-2xl bg-[#f4e6c8] border border-[#f7e9b8] p-5">
            <div className="flex items-center gap-2 mb-2">
              <Lightbulb size={15} className="text-[#6b5428]" />
              <span className="text-sm font-black tracking-widest text-[#a8935a]">解析</span>
            </div>
            {item.explanation ? (
              <div className="exam-text text-[20px] leading-[1.8] whitespace-pre-wrap break-words">
                <ExamText text={item.explanation} />
              </div>
            ) : (
              <p className="text-sm text-[#bbb] italic">（本题暂无解析）</p>
            )}
            <ImageList images={item.explanation_images} />
          </div>

          {item.draft_url && (
            <div className="rounded-2xl border border-[#e8d5b0] overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-[#faf9f5]">
                <PenTool size={13} className="text-[#999]" />
                <span className="text-sm font-black tracking-widest text-[#999]">
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

// ─── 主组件 ───────────────────────────────────────────────────

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
  const [timeSpent, setTimeSpent] = useState({});    // { [qid]: 累计秒 }
  const [drafts, setDrafts] = useState({});          // { [qid]: stroke[] }

  const [draftMode, setDraftMode] = useState(false);
  const [tool, setTool] = useState('pen');

  const [showSheet, setShowSheet] = useState(false);
  const [blankSubmitCount, setBlankSubmitCount] = useState(0);
  const [result, setResult] = useState(null);
  const [report, setReport] = useState(null);
  const [openReview, setOpenReview] = useState(null);

  // enter = 「当前停留的这道题」和「这一次进来的时刻」，离开时把差值累加进 timeSpent
  const [enter, setEnter] = useState({ qid: null, at: 0 });
  const enterRef = useRef(enter);
  useEffect(() => { enterRef.current = enter; }, [enter]);
  const [pageLive, setPageLive] = useState(() => typeof document === 'undefined' || !document.hidden);

  const paperRef = useRef(null);
  const dirtyDraftsRef = useRef(new Set());
  const draftQueueRef = useRef(Promise.resolve());
  const savingCountRef = useRef(0);
  const bumpSaving = useCallback((d) => {
    savingCountRef.current = Math.max(0, savingCountRef.current + d);
  }, []);
  const uploadedRef = useRef(new Set());

  const current = questions[index];
  const total = questions.length;
  const running = phase === 'running';
  const now = useTick(running && pageLive);

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

        const params = new URLSearchParams({ batch_id: batchId, limit: '50' });
        if (!String(batchId).startsWith('daily-')) params.set('random', '1');
        const [qres, hist] = await Promise.all([
          api('/api/questions?' + params.toString()),
          api('/api/questions/meta/history?batch_id=' + encodeURIComponent(batchId)).catch(() => ({})),
        ]);
        if (aborted) return;
        const items = keepMaterialGroups(qres?.items || [], batchId);
        if (items.length === 0) { setPhase('empty'); return; }
        const s = await api('/api/practice/sessions', { method: 'POST', body: { category: batchId } });
        if (aborted) return;

        setQuestions(items);
        setHistoryMap(hist && typeof hist === 'object' ? hist : {});
        setSessionId(s.id);
        setIndex(0);
        setAnswers({});
        setTimeSpent({});
        setDrafts({});
        setResult(null);
        setReport(null);
        setOpenReview(null);
        setErrMsg('');
        dirtyDraftsRef.current = new Set();
        uploadedRef.current = new Set();
        setEnter({ qid: items[0].id, at: Date.now() });
        setPageLive(true);
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
  // 就不再走复盘分支。旧成绩在库里原封不动，新这一场交了卷才会取代它
  const restart = () => { setRedoing(true); setPhase('loading'); setRunKey((k) => k + 1); };

  // ── 计时 ──
  // 把某一段停留结算进 timeSpent。只从事件处理器 / 回调里调，不在 render 里调。
  const settle = useCallback((slot) => {
    if (!slot?.qid || !slot?.at) return;
    const delta = Math.round((Date.now() - slot.at) / 1000);
    if (delta <= 0) return;
    setTimeSpent((prev) => ({ ...prev, [slot.qid]: (prev[slot.qid] || 0) + delta }));
  }, []);

  // 切到后台 / 锁屏：本题和总时长一起停。iPad 熄屏有时只走 pagehide。
  useEffect(() => {
    if (!running) return;
    const pause = () => {
      const slot = enterRef.current;
      if (slot?.at) {
        settle(slot);
        const next = { ...slot, at: 0 };
        enterRef.current = next;
        setEnter(next);
      }
      setPageLive(false);
    };
    const resume = () => {
      if (document.hidden) return;
      const slot = enterRef.current;
      if (slot?.qid && !slot.at) {
        const next = { ...slot, at: Date.now() };
        enterRef.current = next;
        setEnter(next);
      }
      setPageLive(true);
    };
    const onVisibility = () => {
      if (document.hidden) pause();
      else resume();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', pause);
    window.addEventListener('pageshow', resume);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', pause);
      window.removeEventListener('pageshow', resume);
    };
  }, [running, settle]);

  const totalElapsed = sessionSeconds(timeSpent, enter, now);
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

  // 草稿落盘：抓快照这一下是同步的，截图和上传都扔到后台，翻页不用等。
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
        const blob = await captureNode(snap.node);
        if (!blob) throw new Error('截图失败');
        const put = () => api(`/api/practice/sessions/${sessionId}/drafts/${qid}`, {
          method: 'PUT',
          body: blob,
          headers: { 'Content-Type': blob.type || 'image/jpeg' },
        });
        try {
          await put();
        } catch (e) {
          // iPad Safari 偶发把大请求报成 Load failed，换一条连接再试一次。
          if (!(e instanceof TypeError) && !/load failed|failed to fetch/i.test(e?.message || '')) {
            throw e;
          }
          await put();
        }
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

  // 停笔后自动落盘；退出草稿、切题和交卷时仍会立刻保存。
  useEffect(() => {
    const qid = current?.id;
    if (!draftMode || !qid || !dirtyDraftsRef.current.has(qid)) return undefined;
    const timer = window.setTimeout(() => persistDraft(qid), 1200);
    return () => window.clearTimeout(timer);
  }, [draftMode, current?.id, persistDraft]);

  const toggleDraftMode = () => {
    if (draftMode) {
      persistDraft(current?.id);
      setDraftMode(false);
      return;
    }
    setTool('pen');
    setDraftMode(true);
  };

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

  // ── 交卷 ──
  const answeredCount = useMemo(
    () => questions.filter((q) => (answers[q.id] || []).length > 0).length,
    [questions, answers],
  );

  // 退出：没交卷就不算这一次，所以把这场局部连草稿一起删掉，
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

  const submitAll = async (confirmedBlank = false) => {
    if (!sessionId || phase !== 'running') return;
    const blank = total - answeredCount;
    if (blank > 0 && !confirmedBlank) {
      setBlankSubmitCount(blank);
      return;
    }
    setBlankSubmitCount(0);

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
          duration_sec: sessionSeconds(timeSpent, enter, Date.now()),
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
      const k = e.key.toUpperCase();
      if (['A', 'B', 'C', 'D', 'E'].includes(k)) {
        if (optionsOf(current).some((o) => o.key === k)) { e.preventDefault(); toggleSelect(k); }
        return;
      }
      if (draftMode) return;
      if (e.key === 'ArrowRight' || e.key === 'Enter') {
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
            className="bg-[#1a1a1a] text-white font-black px-8 py-3 rounded-2xl hover:bg-[#2c261c] hover:text-white transition-all tracking-widest text-sm">
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
            className="flex-1 flex items-center justify-center gap-2 bg-white border-2 border-[#1a1a1a] text-[#1a1a1a] font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all tracking-widest text-sm">
            <RotateCcw size={16} /><span>{reviewing ? '重做这套' : '再刷一遍'}</span>
          </button>
          {onAnalyzeWithHermes && hasWrong && (
            <button onClick={() => { onAnalyzeWithHermes(sessionId); onExit(); }}
              className="flex-1 flex items-center justify-center gap-2 bg-[#1a1a1a] text-white font-black px-6 py-4 rounded-2xl hover:opacity-90 transition-all tracking-widest text-sm">
              <Send size={16} /><span>让 Hermes 复盘错题</span>
            </button>
          )}
          <button onClick={onExit}
            className="flex-1 flex items-center justify-center gap-2 bg-[#2c261c] text-white font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all tracking-widest text-sm">
            <span>返回批次</span><ArrowRight size={16} />
          </button>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <p className="text-sm font-black tracking-widest text-[#bbb]">逐题对答案</p>
            <button
              onClick={() => setOpenReview(openReview === 'all' ? null : 'all')}
              className="text-sm font-black tracking-widest text-[#999] hover:text-[#1a1a1a]"
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
  const hasMaterial = Boolean(current?.material?.content);
  const materialSpan = (() => {
    if (!current?.material_id) return '';
    let lo = Infinity;
    let hi = -1;
    questions.forEach((q, i) => {
      if (q.material_id === current.material_id) {
        lo = Math.min(lo, i + 1);
        hi = Math.max(hi, i + 1);
      }
    });
    return Number.isFinite(lo) ? `${lo}–${hi}` : '';
  })();

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
        className="shrink-0 flex items-center justify-between gap-2 px-4 py-2.5 border-b border-[#e8d5b0]"
        data-capture-ignore="1"
      >
        <button onClick={exitQuiz}
          className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-[#999] hover:bg-[#e8d5b0] hover:text-[#1a1a1a] transition-colors">
          <ArrowLeft size={18} />
          <span className="text-base font-black tracking-widest hidden sm:inline">退出</span>
        </button>

        <div className="flex min-w-0 flex-1 items-center gap-1 px-2">
          {draftMode && (
            <div className="flex items-center gap-1" aria-label="草稿工具栏">
              <button
                onClick={() => setTool((t) => (t === 'eraser' ? 'pen' : 'eraser'))}
                title="橡皮"
                className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${
                  tool === 'eraser' ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5'
                }`}
              >
                <Eraser size={16} />
              </button>
              <button onClick={() => mutateStrokes((s) => s.slice(0, -1))}
                disabled={!hasDraft} title="撤销一笔"
                className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] disabled:opacity-30 transition-colors">
                <Undo2 size={16} />
              </button>
              <button onClick={() => mutateStrokes(() => [])}
                disabled={!hasDraft} title="清空本题草稿"
                className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center text-[#999] hover:bg-red-50 hover:text-[#ef5350] disabled:opacity-30 transition-colors">
                <Trash2 size={16} />
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 sm:gap-4">
          {draftMode && (
            <div className="flex items-center gap-1.5" aria-label="作答">
              {optionsOf(current).map((opt) => {
                const on = selection.includes(opt.key);
                return (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => toggleSelect(opt.key)}
                    className={`shrink-0 h-9 w-9 rounded-xl text-sm font-black border-2 transition-colors ${
                      on
                        ? 'bg-[#1a1a1a] text-white border-[#1a1a1a]'
                        : 'bg-white text-[#1a1a1a] border-[#e8d5b0] hover:border-[#6b5428]'
                    }`}
                  >
                    {opt.key}
                  </button>
                );
              })}
            </div>
          )}
          <div className="flex items-center gap-1.5 text-[#999]">
            <Clock size={14} />
            <span className="text-base font-mono tabular-nums font-black">{fmtDuration(totalElapsed)}</span>
          </div>
          <span className="text-base font-black tabular-nums text-[#bbb]">
            已答 <span className="text-[#1a1a1a]">{answeredCount}</span>/{total}
          </span>
          <button
            type="button"
            onClick={toggleDraftMode}
            aria-label={draftMode ? '退出草稿纸模式' : '打开草稿纸模式'}
            aria-pressed={draftMode}
            title={draftMode ? '退出草稿纸模式' : '进入草稿纸模式'}
            className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors ${
              draftMode
                ? 'bg-[#1a1a1a] text-white'
                : 'text-[#999] hover:bg-[#e8d5b0] hover:text-[#1a1a1a]'
            }`}
          >
            {draftMode ? <XIcon size={18} /> : <PenTool size={17} />}
          </button>
          <button
            type="button"
            onClick={() => goTo(index - 1)}
            disabled={index === 0}
            title="上一题"
            className="shrink-0 h-11 w-10 sm:w-28 rounded-xl flex items-center justify-center gap-1.5 text-[#777] hover:bg-[#e8d5b0] hover:text-[#1a1a1a] disabled:opacity-30 transition-colors"
          >
            <ArrowLeft size={16} />
            <span className="hidden sm:inline text-base font-black">上一题</span>
          </button>
          <button
            type="button"
            onClick={() => (isLast ? submitAll() : goTo(index + 1))}
            disabled={grading}
            title={isLast ? '交卷' : '下一题'}
            className="shrink-0 h-11 w-10 sm:w-28 rounded-xl flex items-center justify-center gap-1.5 bg-[#1a1a1a] text-white hover:bg-[#2c261c] disabled:opacity-30 transition-colors"
          >
            <span className="hidden sm:inline text-base font-black">{isLast ? '交卷' : '下一题'}</span>
            {isLast ? <Flag size={16} /> : <ArrowRight size={16} />}
          </button>

          <button
            onClick={() => setShowSheet(true)}
            className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-base font-black text-[#999] hover:bg-[#e8d5b0] hover:text-[#1a1a1a] transition-colors"
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

      <div className="flex-1 min-h-0 px-3 sm:px-5 py-3">
      <div
        ref={paperRef}
        className={`relative h-full min-h-0 overflow-hidden rounded-[1.5rem] border-2 transition-colors ${
          draftMode ? 'border-[#6b5428] bg-white' : 'border-black/10 bg-white'
        }`}
      >
        {(() => {
          const questionPane = (
            <>
              <div className="flex items-center justify-between gap-2 mb-5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-black tracking-widest bg-[#1a1a1a] text-white px-3.5 py-1 rounded-full">
                    {typeLabelOf(current?.question_type)}
                  </span>
                  {isZhenti(current) && <ZhentiMark />}
                  {current?.sub_category && (
                    <span className="text-sm font-black tracking-widest text-[#888]">
                      {current.sub_category}
                    </span>
                  )}
                  {hasHistory && (
                    history.last_correct
                      ? <span className="text-sm font-black px-2.5 py-0.5 rounded-full bg-[#e8f5e9] text-[#2e7d32]">上次答对</span>
                      : <span className="text-sm font-black px-2.5 py-0.5 rounded-full bg-[#fdecea] text-[#c62828]">
                          上次答错 · 错了 {history.wrong} 次
                        </span>
                  )}
                </div>
                <div className="flex items-center gap-2.5 shrink-0">
                  <span className="text-sm font-black tabular-nums text-[#888]">
                    本题 <span className="text-[#6b5428]">{fmtDuration(currentElapsed)}</span>
                  </span>
                  <span className="text-lg font-mono tabular-nums font-black text-[#888]">
                    {index + 1}/{total}
                  </span>
                </div>
              </div>

              <div className="exam-text text-[22px] leading-[1.8] text-[#1a1a1a] whitespace-pre-wrap break-words font-medium">
                <ExamText text={current?.content} />
              </div>
              <ImageList images={current?.stem_images} wide />

              {current?.question_type === 'multi' && (
                <p className="mt-4 text-sm font-black tracking-widest text-[#6b5428]">
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
            </>
          );

          if (!hasMaterial) {
            return (
              <div className="absolute inset-0 overflow-y-auto overscroll-y-contain">
                <div className="min-h-full p-5 sm:p-8 lg:px-10">
                  <div className="mx-auto max-w-4xl">{questionPane}</div>
                </div>
              </div>
            );
          }

          return (
            <div className="flex h-full min-h-0 flex-col lg:flex-row">
              <aside
                key={current.material_id}
                className="h-[40%] min-h-[9rem] overflow-y-auto overscroll-y-contain border-b border-black/10 bg-white lg:h-auto lg:min-h-0 lg:w-[46%] lg:border-b-0 lg:border-r"
              >
                <div className="sticky top-0 z-10 flex items-baseline justify-between gap-2 bg-white px-5 py-3">
                  <span className="text-sm font-bold text-black">材料</span>
                  {materialSpan && (
                    <span className="text-xs text-black/40">第 {materialSpan} 题</span>
                  )}
                </div>
                <div className="px-5 pb-8 sm:px-7">
                  <div className="ziliao-material exam-text whitespace-pre-wrap break-words">
                    <ExamText text={current.material.content} collapseBlank />
                  </div>
                  <ImageList images={current.material.images} wide />
                </div>
              </aside>
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain">
                <div className="p-5 sm:p-8 lg:px-10">{questionPane}</div>
              </div>
            </div>
          );
        })()}

        <DraftLayer
          active={draftMode}
          visible={draftMode}
          tool={tool}
          color={PEN_COLOR}
          strokes={currentStrokes}
          onStrokeEnd={pushStroke}
        />
      </div>
      </div>



      {blankSubmitCount > 0 && (
        <BlankSubmitConfirm
          blank={blankSubmitCount}
          grading={grading}
          onCancel={() => setBlankSubmitCount(0)}
          onConfirm={() => submitAll(true)}
        />
      )}

      {showSheet && (
        <AnswerSheet
          questions={questions}
          answers={answers}
          index={index}
          onJump={goTo}
          onClose={() => setShowSheet(false)}
          onSubmit={() => {
            setShowSheet(false);
            submitAll();
          }}
        />
      )}
    </div>
  );
};

export default AIQuizSession;

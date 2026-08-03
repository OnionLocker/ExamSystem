// AI 练题 — 做题会话
//
// 每个 batch_id 对应 Hermes 出完题后 import 进库的一套题。
// 支持：每题独立计时 + 全场总计时、草稿纸浮层（Apple Pencil 压感）、
// 提交时自动把草稿发 Hermes 分析思路（流式显示结果）。

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, Check, X as XIcon, SkipForward,
  ChevronRight, Clock, Trophy, RotateCcw, AlertTriangle,
  Lightbulb, Flag, PenTool, Loader2, Brain,
} from 'lucide-react';
import { api } from '../api.js';
import HermesGateway from '../hermes/gateway.js';
import DraftCanvas from './DraftCanvas.jsx';

// ─── 工具函数 ────────────────────────────────────────────────────────────────

const normalizeAnswer = (selection, questionType) => {
  if (questionType === 'multi') {
    const arr = Array.isArray(selection) ? selection : [];
    return [...arr].sort().join('');
  }
  return String(selection ?? '');
};

const hasSelection = (selection, questionType) => {
  if (questionType === 'multi') return Array.isArray(selection) && selection.length > 0;
  return !!selection;
};

const fmtDuration = (sec) => {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

// 1Hz 计时 hook（与 BankSession 相同模式，此处内联以保持独立）
const useElapsed = (startMs, running) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  return Math.floor((now - startMs) / 1000);
};

// ─── 子组件（复用 BankSession 风格）────────────────────────────────────────

const ImageList = ({ images }) => {
  if (!images || images.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {images.map((src, i) => (
        <img key={i} src={src} alt="" loading="lazy"
          className="max-w-full rounded-xl border border-[#f2f0e9] bg-white" />
      ))}
    </div>
  );
};

const OptionItem = ({ option, state, onClick }) => {
  const stateCls = {
    idle: 'bg-white border-[#f2f0e9] hover:border-[#fbc02d] hover:bg-[#fffdf5]',
    selected: 'bg-[#fffdf5] border-[#fbc02d] shadow-sm',
    correct: 'bg-green-50 border-green-500',
    wrong: 'bg-red-50 border-red-500',
    'correct-hint': 'bg-green-50 border-green-400 border-dashed',
  }[state] || '';
  const badgeCls = {
    idle: 'bg-[#f2f0e9] text-[#1a1a1a]',
    selected: 'bg-[#fbc02d] text-black',
    correct: 'bg-green-500 text-white',
    wrong: 'bg-red-500 text-white',
    'correct-hint': 'bg-green-400 text-white',
  }[state] || '';

  return (
    <button type="button" onClick={onClick}
      className={`w-full text-left px-5 py-4 rounded-2xl border-2 transition-all flex items-start space-x-3 ${stateCls}`}>
      <span className={`flex-shrink-0 w-8 h-8 rounded-xl font-black flex items-center justify-center text-sm ${badgeCls}`}>
        {option.key}
      </span>
      <div className="flex-1 min-w-0 pt-1">
        <div className="text-[15px] leading-relaxed break-words whitespace-pre-wrap">{option.text}</div>
        <ImageList images={option.images} />
      </div>
      {state === 'correct' && <Check size={20} className="flex-shrink-0 text-green-600 mt-1" />}
      {state === 'wrong' && <XIcon size={20} className="flex-shrink-0 text-red-600 mt-1" />}
    </button>
  );
};

const normalizeJudgeOptions = (options) =>
  (options && options.length >= 2)
    ? options
    : [{ key: 'A', text: '正确', images: [] }, { key: 'B', text: '错误', images: [] }];

const QuestionCard = ({ question, index, total, qElapsed, totalElapsed, history, selection, feedback, draftDirty, onToggle, onDraft }) => {
  const isMulti = question.question_type === 'multi';
  const isJudge = question.question_type === 'judge';
  const options = isJudge ? normalizeJudgeOptions(question.options) : (question.options || []);
  const correctAnswer = feedback?.correct_answer || '';
  const correctSet = new Set(correctAnswer.split(''));

  // history: { attempts, wrong, last_correct, last_answer } | undefined
  const hasHistory = history && history.attempts > 0;

  const optionState = (key) => {
    const selected = isMulti ? (Array.isArray(selection) && selection.includes(key)) : selection === key;
    if (!feedback) return selected ? 'selected' : 'idle';
    const isCorrectKey = correctSet.has(key);
    if (selected && isCorrectKey) return 'correct';
    if (selected && !isCorrectKey) return 'wrong';
    if (!selected && isCorrectKey) return 'correct-hint';
    return 'idle';
  };

  const typeLabel = isMulti ? '多选题' : isJudge ? '判断题' : '单选题';

  return (
    <div className="bg-white rounded-[2rem] p-8 shadow-sm border border-[#f2f0e9]">
      {/* 顶部信息条 */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center space-x-2">
          <span className="text-[10px] font-black uppercase tracking-widest bg-[#1a1a1a] text-white px-3 py-1 rounded-full">
            {typeLabel}
          </span>
          {question.sub_category && (
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              {question.sub_category}
            </span>
          )}
          {/* 历史作答标记 */}
          {hasHistory && !feedback && (
            history.last_correct
              ? <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-green-100 text-green-700">上次答对</span>
              : <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-red-100 text-red-600">
                  上次答错 · 错了 {history.wrong} 次
                </span>
          )}
        </div>
        {/* 右侧：题号 + 本题计时 + 总计时 + 草稿纸按钮 */}
        <div className="flex items-center space-x-3">
          <span className="text-[10px] font-black tabular-nums text-slate-400">
            本题 <span className="text-[#fbc02d]">{fmtDuration(qElapsed)}</span>
          </span>
          <span className="text-[10px] font-black tabular-nums text-slate-400">
            总 {fmtDuration(totalElapsed)}
          </span>
          <span className="text-sm font-mono tabular-nums font-black text-slate-400">
            {index + 1} / {total}
          </span>
          {/* 草稿纸收起后笔迹还在（提交时要用），所以按钮要显出「已有草稿」状态，
              否则你会以为关掉就没了。iPad 上手指点得到，按钮做大一点。 */}
          <button
            onClick={onDraft}
            className={`flex items-center space-x-1 px-3 py-2 rounded-xl text-[10px] font-black transition-colors ${
              draftDirty
                ? 'bg-[#fbc02d] text-black'
                : 'text-[#999] hover:bg-[#fbc02d]/10 hover:text-[#8a5400]'
            }`}
            title={draftDirty ? '草稿纸（已有笔迹，提交时会发给 Hermes）' : '打开草稿纸'}
          >
            <PenTool size={12} />
            <span>{draftDirty ? '草稿 ●' : '草稿'}</span>
          </button>
        </div>
      </div>

      <div className="text-[16px] leading-[1.9] text-[#1a1a1a] whitespace-pre-wrap break-words font-medium">
        {question.content}
      </div>
      <ImageList images={question.stem_images} />

      {isMulti && !feedback && (
        <p className="mt-4 text-xs font-black uppercase tracking-widest text-[#fbc02d]">
          多选题 · 至少选两项，答错不得分
        </p>
      )}

      <div className="mt-6 space-y-3">
        {options.map((opt) => (
          <OptionItem key={opt.key} option={opt} state={optionState(opt.key)} onClick={() => onToggle(opt.key)} />
        ))}
      </div>
    </div>
  );
};

// 提交后的解析区（含 AI 批改）
const ExplanationCard = ({ feedback, question, aiComment, aiLoading }) => {
  if (!feedback) return null;
  const isCorrect = feedback.is_correct;
  return (
    <div className={`rounded-[2rem] p-6 border-2 ${isCorrect ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          {isCorrect ? (
            <><div className="w-8 h-8 rounded-xl bg-green-500 text-white flex items-center justify-center"><Check size={18} /></div>
              <span className="text-lg font-black italic text-green-700">答对了</span></>
          ) : (
            <><div className="w-8 h-8 rounded-xl bg-red-500 text-white flex items-center justify-center"><XIcon size={18} /></div>
              <span className="text-lg font-black italic text-red-700">{feedback.skipped ? '已跳过' : '答错了'}</span></>
          )}
        </div>
        <div className="text-xs font-black uppercase tracking-widest text-slate-500">
          正确答案 <span className="text-[#1a1a1a] text-sm ml-1">{feedback.correct_answer}</span>
        </div>
      </div>

      {question.explanation ? (
        <div className="bg-white/70 rounded-2xl p-5 border border-white">
          <div className="flex items-center space-x-2 mb-2">
            <Lightbulb size={16} className="text-[#fbc02d]" />
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">解析</span>
          </div>
          <div className="text-[14px] leading-[1.85] text-[#1a1a1a] whitespace-pre-wrap break-words">
            {question.explanation}
          </div>
          <ImageList images={question.explanation_images} />
        </div>
      ) : (
        <p className="text-sm font-medium text-slate-500 italic">（本题暂无解析）</p>
      )}

      {/* AI 草稿分析区 */}
      {(aiLoading || aiComment) && (
        <div className="mt-4 rounded-2xl bg-[#1a1a1a]/5 p-4 border border-[#1a1a1a]/10">
          <div className="flex items-center space-x-2 mb-2">
            <Brain size={14} className="text-[#fbc02d]" />
            <span className="text-[10px] font-black uppercase tracking-widest text-[#1a1a1a]">
              Hermes 草稿分析
            </span>
            {aiLoading && <Loader2 size={11} className="animate-spin text-[#fbc02d]" />}
          </div>
          <div className="text-[13px] leading-relaxed text-[#333] whitespace-pre-wrap break-words">
            {aiComment || '分析中…'}
          </div>
        </div>
      )}
    </div>
  );
};

// 结果页
const ResultView = ({ batchId, total, answered, durationSec, onRetry, onExit }) => {
  const attempted = answered.length;
  const correct = answered.filter((a) => a.is_correct).length;
  const accuracy = attempted > 0 ? Math.round((correct / attempted) * 100) : 0;
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 relative overflow-hidden">
        <div className="absolute top-6 right-6 w-32 h-32 bg-[#fbc02d] rounded-full blur-[40px] opacity-60" />
        <div className="relative z-10">
          <div className="w-14 h-14 rounded-2xl bg-[#fbc02d] text-black flex items-center justify-center mb-5">
            <Trophy size={26} />
          </div>
          <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mb-1">
            {batchId || 'AI 练题'}
          </p>
          <h3 className="text-3xl font-black italic">本次成绩</h3>
          <div className="mt-8 grid grid-cols-3 gap-4">
            <div>
              <p className="text-4xl font-black tabular-nums">{accuracy}%</p>
              <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">正确率</p>
            </div>
            <div>
              <p className="text-4xl font-black tabular-nums">
                {correct}<span className="text-base opacity-50">/{attempted}</span>
              </p>
              <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">答对</p>
            </div>
            <div>
              <p className="text-4xl font-black tabular-nums">{fmtDuration(durationSec)}</p>
              <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">用时</p>
            </div>
          </div>
        </div>
      </div>

      {/* 每题明细 */}
      <div className="bg-white rounded-[2rem] p-6 shadow-sm border border-[#f2f0e9]">
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-4">作答明细</p>
        <div className="space-y-2">
          {answered.map((a, i) => (
            <div key={i} className="flex items-center space-x-3 text-sm">
              <span className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-black flex-shrink-0 ${
                a.skipped ? 'bg-slate-100 text-slate-400'
                : a.is_correct ? 'bg-green-100 text-green-700'
                : 'bg-red-100 text-red-700'}`}>
                {i + 1}
              </span>
              <span className="text-slate-500 font-medium w-20 flex-shrink-0">
                {a.skipped ? '跳过' : a.is_correct ? '✓ 正确' : '✗ 答错'}
              </span>
              <span className="text-slate-400 font-mono text-xs">
                我：{a.user_answer || '—'}  正：{a.correct_answer}
              </span>
              <span className="ml-auto font-mono text-xs text-slate-400 flex-shrink-0">
                {fmtDuration(a.time_spent_sec)}
              </span>
            </div>
          ))}
          {total > attempted && (
            <p className="text-xs text-slate-400 pl-10">还剩 {total - attempted} 题未作答</p>
          )}
        </div>
      </div>

      <div className="flex items-center space-x-3">
        <button onClick={onRetry}
          className="flex-1 flex items-center justify-center space-x-2 bg-white border-2 border-[#1a1a1a] text-[#1a1a1a] font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs">
          <RotateCcw size={16} /><span>再刷一套</span>
        </button>
        <button onClick={onExit}
          className="flex-1 flex items-center justify-center space-x-2 bg-[#fbc02d] text-black font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs">
          <span>返回批次</span><ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};

// ─── 主组件 ──────────────────────────────────────────────────────────────────

const AIQuizSession = ({ batchId, onExit }) => {
  const [phase, setPhase] = useState('loading');
  const [sessionId, setSessionId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [index, setIndex] = useState(0);
  const [selection, setSelection] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [answered, setAnswered] = useState([]);
  const [errMsg, setErrMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showDraft, setShowDraft] = useState(false);
  // 草稿纸关掉之后笔迹还留着（提交时才读），所以要在题目卡上标出「草稿里有东西」，
  // 否则关掉浮层就完全看不出待会儿会不会发分析
  const [draftDirty, setDraftDirty] = useState(false);
  const [aiComment, setAiComment] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  // 历史作答摘要 { [question_id]: {attempts, wrong, last_correct, last_answer, last_at} }
  // 用来在题目卡上显示「这题以前做错过」
  const [historyMap, setHistoryMap] = useState({});

  const [sessionStart, setSessionStart] = useState(() => Date.now());
  const [qStart, setQStart] = useState(() => Date.now());
  // 初始化为 0；在 useEffect 里赋真实值（避免 react-hooks/purity 警告）
  const questionStartRef = useRef(0);
  const markQStart = useCallback(() => {
    const t = Date.now();
    questionStartRef.current = t;
    setQStart(t);
  }, []);

  const draftRef = useRef(null);
  const gwRef = useRef(null);

  const totalElapsed = useElapsed(sessionStart, phase === 'running');
  const qElapsed = useElapsed(qStart, phase === 'running' && !feedback);

  useEffect(() => {
    let aborted = false;
    (async () => {
      try {
        const params = new URLSearchParams({ batch_id: batchId, random: '1', limit: '30' });
        // 题目和历史数据并行拉取
        const [qres, hist] = await Promise.all([
          api('/api/questions?' + params.toString()),
          api('/api/questions/meta/history?batch_id=' + encodeURIComponent(batchId)).catch(() => ({})),
        ]);
        if (aborted) return;
        const items = qres?.items || [];
        if (items.length === 0) { setPhase('empty'); return; }
        const s = await api('/api/practice/sessions', { method: 'POST', body: { category: batchId } });
        if (aborted) return;
        setSessionId(s.id); setQuestions(items);
        setHistoryMap(hist && typeof hist === 'object' ? hist : {});
        const now = Date.now();
        setSessionStart(now); questionStartRef.current = now; setQStart(now);
        setPhase('running');
      } catch (e) {
        if (!aborted) { setErrMsg(e?.message || '加载失败'); setPhase('error'); }
      }
    })();
    return () => { aborted = true; };
  }, [batchId]);

  const current = questions[index];
  const total = questions.length;

  const toggleSelect = (key) => {
    if (feedback || !current) return;
    if (current.question_type === 'multi') {
      setSelection((prev) => {
        const arr = Array.isArray(prev) ? [...prev] : [];
        const i = arr.indexOf(key);
        if (i >= 0) arr.splice(i, 1); else arr.push(key);
        return arr.sort();
      });
    } else {
      setSelection(key);
    }
  };

  const analyzeWithHermes = useCallback(async (question, draftDataUrl, userAnswer, correctAnswer) => {
    if (!draftDataUrl) return;
    setAiLoading(true);
    setAiComment('');
    let gw;
    try {
      gw = new HermesGateway();
      gwRef.current = gw;
      await gw.connect();
      const { session_id } = await gw.request('session.create', { cols: 100, cwd: '/home/ubuntu' });
      await gw.request('image.attach_bytes', {
        session_id,
        content_base64: draftDataUrl,
        filename: 'draft.png',
      });
      const optionText = (question.options || [])
        .map((o) => `${o.key}. ${o.text ?? ''}`)
        .join('\n');
      const prompt = [
        '这是我做下面这道公考题时写的整张草稿纸（图片已附上）。',
        '',
        '【题目】',
        question.content,
        optionText ? `\n【选项】\n${optionText}` : '',
        `\n【正确答案】${correctAnswer || '（未提供）'}`,
        `【我选的】${userAnswer || '（跳过没选）'}`,
        '',
        '请分两部分回答，每部分都简短：',
        '1. 思路诊断：从草稿看我的推理链是怎么走的，哪一步开始偏了，是概念错、逻辑错还是计算失误。',
        '2. 草稿习惯：我这张草稿纸本身有没有坏习惯（比如条件没抄全、符号乱用、步骤跳太多、',
        '   排版挤在一起导致自己看错、算完不回头验证）。有就直接点出来并给一句怎么改；没有就说草稿清楚。',
        '',
        '看不清写的是什么就直接说看不清，不要猜。',
      ].filter(Boolean).join('\n');
      const off = gw.on('message.delta', (ev) => {
        const t = ev.payload?.text;
        if (t) setAiComment((c) => c + t);
      });
      const done = new Promise((resolve) => {
        const offDone = gw.on('message.complete', () => { offDone(); resolve(); });
        const offErr = gw.on('error', () => { offErr(); resolve(); });
      });
      await gw.request('prompt.submit', { session_id, text: prompt });
      await done;
      off();
    } catch {
      setAiComment('（草稿分析请求失败，请检查 Hermes 连接）');
    } finally {
      setAiLoading(false);
      try { gw?.close(); } catch { /* */ }
    }
  }, []);

  const submit = async () => {
    if (!current || feedback || submitting) return;
    if (!hasSelection(selection, current.question_type)) return;
    const userAnswer = normalizeAnswer(selection, current.question_type);
    const timeSpentSec = Math.max(1, Math.round((Date.now() - questionStartRef.current) / 1000));
    const draftDataUrl = draftRef.current?.capture() ?? null;
    setSubmitting(true);
    try {
      const res = await api(`/api/practice/sessions/${sessionId}/answers`, {
        method: 'POST',
        body: { question_id: current.id, user_answer: userAnswer, time_spent_sec: timeSpentSec },
      });
      setFeedback(res);
      setAnswered((a) => [...a, {
        qid: current.id, user_answer: userAnswer,
        correct_answer: res.correct_answer, is_correct: !!res.is_correct,
        skipped: false, time_spent_sec: timeSpentSec,
      }]);
      analyzeWithHermes(current, draftDataUrl, userAnswer, res.correct_answer);
    } catch (e) {
      setErrMsg(e?.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const skip = async () => {
    if (!current || feedback || submitting) return;
    const timeSpentSec = Math.max(1, Math.round((Date.now() - questionStartRef.current) / 1000));
    // 算了半张草稿最后放弃，这时候的思路诊断反而最有用，所以跳过也送分析
    const draftDataUrl = draftRef.current?.capture() ?? null;
    setSubmitting(true);
    try {
      const res = await api(`/api/practice/sessions/${sessionId}/answers`, {
        method: 'POST',
        body: { question_id: current.id, user_answer: '', time_spent_sec: timeSpentSec },
      });
      setFeedback({ ...res, skipped: true });
      setAnswered((a) => [...a, {
        qid: current.id, user_answer: '',
        correct_answer: res.correct_answer, is_correct: false,
        skipped: true, time_spent_sec: timeSpentSec,
      }]);
      analyzeWithHermes(current, draftDataUrl, '', res.correct_answer);
    } catch (e) {
      setErrMsg(e?.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const goNext = async () => {
    if (!feedback) return;
    draftRef.current?.clear();
    setShowDraft(false);
    setAiComment('');
    setAiLoading(false);
    if (index + 1 >= total) { await finish(); return; }
    setIndex((i) => i + 1);
    setSelection(null);
    setFeedback(null);
    markQStart();
  };

  const finish = async () => {
    try {
      const durationSec = Math.round((Date.now() - sessionStart) / 1000);
      await api(`/api/practice/sessions/${sessionId}/finish`, {
        method: 'POST', body: { duration_sec: durationSec },
      });
    } catch { /* 静默 */ }
    setPhase('finished');
  };

  useEffect(() => {
    if (phase !== 'running') return;
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'canvas') return;
      if (feedback) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goNext(); }
        return;
      }
      const k = e.key.toUpperCase();
      if (['A', 'B', 'C', 'D', 'E'].includes(k)) {
        const exists = (current?.options || []).some((o) => o.key === k);
        if (exists) { e.preventDefault(); toggleSelect(k); }
      } else if (e.key === 'Enter') {
        e.preventDefault(); submit();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, feedback, selection, current, index, submitting]);

  if (phase === 'loading') {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center">
        <p className="text-sm font-black uppercase tracking-widest text-slate-400">加载题目中…</p>
      </div>
    );
  }
  if (phase === 'empty') {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-[2rem] p-10 text-center shadow-sm border border-[#f2f0e9]">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-[#f2f0e9] text-slate-400 flex items-center justify-center mb-4">
            <AlertTriangle size={24} />
          </div>
          <h3 className="text-xl font-black italic mb-2">这套题暂无题目</h3>
          <p className="text-sm text-slate-500 mb-6">batch_id: {batchId}</p>
          <button onClick={onExit}
            className="bg-[#1a1a1a] text-white font-black px-8 py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs">
            返回
          </button>
        </div>
      </div>
    );
  }
  if (phase === 'error') {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-[2rem] p-10 text-center shadow-sm border border-red-200">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-red-100 text-red-500 flex items-center justify-center mb-4">
            <AlertTriangle size={24} />
          </div>
          <h3 className="text-xl font-black italic mb-2">加载失败</h3>
          <p className="text-sm text-slate-500 mb-6">{errMsg}</p>
          <button onClick={onExit}
            className="bg-[#1a1a1a] text-white font-black px-8 py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs">
            返回
          </button>
        </div>
      </div>
    );
  }
  if (phase === 'finished') {
    return (
      <ResultView
        batchId={batchId} total={total} answered={answered}
        durationSec={totalElapsed}
        onRetry={() => {
          setPhase('loading'); setIndex(0); setSelection(null); setFeedback(null);
          setAnswered([]); setSessionId(null); setAiComment(''); setAiLoading(false);
          const now = Date.now();
          setSessionStart(now); questionStartRef.current = now; setQStart(now);
          (async () => {
            try {
              const params = new URLSearchParams({ batch_id: batchId, random: '1', limit: '30' });
              const qres = await api('/api/questions?' + params.toString());
              const items = qres?.items || [];
              if (items.length === 0) { setPhase('empty'); return; }
              const s = await api('/api/practice/sessions', { method: 'POST', body: { category: batchId } });
              setSessionId(s.id); setQuestions(items);
              const t = Date.now(); setSessionStart(t); questionStartRef.current = t; setQStart(t);
              setPhase('running');
            } catch (e) { setErrMsg(e?.message || '加载失败'); setPhase('error'); }
          })();
        }}
        onExit={onExit}
      />
    );
  }

  // running
  const answeredCount = answered.length;
  const correctCount = answered.filter((a) => a.is_correct).length;
  const canSubmit = !feedback && hasSelection(selection, current?.question_type);

  return (
    <div className="max-w-2xl mx-auto space-y-5 pb-8">
      <div className="flex items-center justify-between bg-white rounded-2xl p-3 shadow-sm border border-[#f2f0e9]">
        <button onClick={onExit} title="退出"
          className="flex items-center space-x-2 px-3 py-2 rounded-xl text-slate-500 hover:bg-[#f2f0e9] hover:text-[#1a1a1a] transition-colors">
          <ArrowLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">退出</span>
        </button>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1.5 text-slate-500">
            <Clock size={14} />
            <span className="text-xs font-mono tabular-nums font-black">{fmtDuration(totalElapsed)}</span>
          </div>
          <div className="text-xs font-black uppercase tracking-widest text-slate-400">
            <span className="text-green-600">{correctCount}</span>
            <span className="mx-1">·</span>
            <span className="text-red-500">{answeredCount - correctCount}</span>
          </div>
        </div>
      </div>

      <div className="h-1.5 bg-[#f2f0e9] rounded-full overflow-hidden">
        <div className="h-full bg-[#fbc02d] transition-all duration-300"
          style={{ width: `${total > 0 ? ((index + (feedback ? 1 : 0)) / total) * 100 : 0}%` }} />
      </div>

      {errMsg && (
        <div className="px-4 py-2 rounded-xl bg-red-50 border border-red-200 text-xs font-bold text-red-700 flex justify-between">
          <span>{errMsg}</span>
          <button onClick={() => setErrMsg('')} className="ml-3 text-red-400 hover:text-red-700">✕</button>
        </div>
      )}

      {current && (
        <>
          <QuestionCard
            question={current} index={index} total={total}
            qElapsed={qElapsed} totalElapsed={totalElapsed}
            history={historyMap[current?.id]}
            selection={selection} feedback={feedback}
            draftDirty={draftDirty}
            onToggle={toggleSelect}
            onDraft={() => setShowDraft(true)}
          />
          {/* 全屏浮层自己 portal 到 body，不需要包 relative 定位容器 */}
          <DraftCanvas
            ref={draftRef}
            show={showDraft}
            onClose={() => setShowDraft(false)}
            onDirtyChange={setDraftDirty}
          />
        </>
      )}

      {feedback && current && (
        <ExplanationCard
          feedback={feedback} question={current}
          aiComment={aiComment} aiLoading={aiLoading}
        />
      )}

      <div className="flex items-center space-x-3 sticky bottom-4">
        {!feedback ? (
          <>
            <button onClick={skip} disabled={submitting}
              className="flex items-center justify-center space-x-2 bg-white border-2 border-[#f2f0e9] text-slate-500 font-black px-5 py-4 rounded-2xl hover:border-[#1a1a1a] hover:text-[#1a1a1a] transition-all uppercase tracking-widest text-xs disabled:opacity-50">
              <SkipForward size={16} /><span>跳过</span>
            </button>
            <button onClick={submit} disabled={!canSubmit || submitting}
              className="flex-1 flex items-center justify-center space-x-2 bg-[#1a1a1a] text-white font-black px-6 py-4 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-[#1a1a1a] disabled:hover:text-white">
              <Check size={16} /><span>{submitting ? '提交中…' : '提交答案'}</span>
            </button>
          </>
        ) : (
          <button onClick={goNext}
            className="flex-1 flex items-center justify-center space-x-2 bg-[#fbc02d] text-black font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs shadow-lg">
            {index + 1 >= total
              ? (<><Flag size={16} /><span>查看成绩</span></>)
              : (<><span>下一题</span><ChevronRight size={16} /></>)}
          </button>
        )}
      </div>

      <p className="text-center text-[10px] font-black uppercase tracking-widest text-slate-400">
        快捷键：A/B/C/D 选择 · Enter 提交 / 下一题
      </p>
    </div>
  );
};

export default AIQuizSession;

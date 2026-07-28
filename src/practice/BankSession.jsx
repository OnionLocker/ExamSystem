import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Check,
  X as XIcon,
  SkipForward,
  ChevronRight,
  Clock,
  Trophy,
  RotateCcw,
  AlertTriangle,
  Lightbulb,
  Flag,
} from 'lucide-react';
import { api } from '../api.js';

// ---------------- 小工具 ----------------

// 正答格式化：多选按字母升序拼接，单选/判断直接字符串化
const normalizeAnswer = (selection, questionType) => {
  if (questionType === 'multi') {
    const arr = Array.isArray(selection) ? selection : [];
    return [...arr].sort().join('');
  }
  return String(selection ?? '');
};

// 判断是否"已作出有效选择"
const hasSelection = (selection, questionType) => {
  if (questionType === 'multi') {
    return Array.isArray(selection) && selection.length > 0;
  }
  return !!selection;
};

// 秒 → mm:ss
const fmtDuration = (sec) => {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
};

// 计时器 Hook：返回已经过去的秒数（每秒 tick）
const useElapsed = (startMs, running) => {
  // 惰性初始化：useState(Date.now()) 每次渲染都会求值（哪怕只用首次结果），
  // 属于渲染期调用不纯函数；传函数则只在挂载时执行一次。
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  return Math.floor((now - startMs) / 1000);
};

// ---------------- 子组件 ----------------

// 题干/解析图片：相对路径已由 import 脚本改写成 /q-images/...
const ImageList = ({ images }) => {
  if (!images || images.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {images.map((src, i) => (
        <img
          key={i}
          src={src}
          alt=""
          className="max-w-full rounded-xl border border-[#f2f0e9] bg-white"
          loading="lazy"
        />
      ))}
    </div>
  );
};

// 单个选项按钮
const OptionItem = ({ option, state, onClick }) => {
  // state: idle | selected | correct | wrong | correct-hint
  const base =
    'w-full text-left px-5 py-4 rounded-2xl border-2 transition-all flex items-start space-x-3';
  const stateCls = {
    idle: 'bg-white border-[#f2f0e9] hover:border-[#fbc02d] hover:bg-[#fffdf5]',
    selected: 'bg-[#fffdf5] border-[#fbc02d] shadow-sm',
    correct: 'bg-green-50 border-green-500',
    wrong: 'bg-red-50 border-red-500',
    'correct-hint': 'bg-green-50 border-green-400 border-dashed',
  }[state] || '';

  const badgeBase =
    'flex-shrink-0 w-8 h-8 rounded-xl font-black flex items-center justify-center text-sm';
  const badgeCls = {
    idle: 'bg-[#f2f0e9] text-[#1a1a1a]',
    selected: 'bg-[#fbc02d] text-black',
    correct: 'bg-green-500 text-white',
    wrong: 'bg-red-500 text-white',
    'correct-hint': 'bg-green-400 text-white',
  }[state] || '';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`${base} ${stateCls}`}
    >
      <span className={`${badgeBase} ${badgeCls}`}>{option.key}</span>
      <div className="flex-1 min-w-0 pt-1">
        <div className="text-[15px] leading-relaxed break-words whitespace-pre-wrap">
          {option.text}
        </div>
        <ImageList images={option.images} />
      </div>
      {state === 'correct' && (
        <Check size={20} className="flex-shrink-0 text-green-600 mt-1" />
      )}
      {state === 'wrong' && (
        <XIcon size={20} className="flex-shrink-0 text-red-600 mt-1" />
      )}
    </button>
  );
};

// 判断题把选项强制渲染成 A. 正确 / B. 错误
const normalizeJudgeOptions = (options) => {
  if (options && options.length >= 2) return options;
  return [
    { key: 'A', text: '正确', images: [] },
    { key: 'B', text: '错误', images: [] },
  ];
};

// 答题面板主体
const QuestionCard = ({
  question,
  index,
  total,
  selection,
  feedback,
  onToggle,
}) => {
  const isMulti = question.question_type === 'multi';
  const isJudge = question.question_type === 'judge';
  const options = isJudge ? normalizeJudgeOptions(question.options) : (question.options || []);
  const correctAnswer = feedback?.correct_answer || '';
  const correctSet = new Set(correctAnswer.split(''));

  const optionState = (key) => {
    const selected = isMulti
      ? (Array.isArray(selection) && selection.includes(key))
      : selection === key;

    if (!feedback) {
      return selected ? 'selected' : 'idle';
    }
    // 已提交
    const isCorrectKey = correctSet.has(key);
    if (selected && isCorrectKey) return 'correct';
    if (selected && !isCorrectKey) return 'wrong';
    if (!selected && isCorrectKey) return 'correct-hint';
    return 'idle';
  };

  const typeLabel = isMulti ? '多选题' : isJudge ? '判断题' : '单选题';

  return (
    <div className="bg-white rounded-[2rem] p-8 shadow-sm border border-[#f2f0e9]">
      {/* 题型 & 序号 */}
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
        </div>
        <span className="text-sm font-mono tabular-nums font-black text-slate-400">
          {index + 1} / {total}
        </span>
      </div>

      {/* 题干 */}
      <div className="text-[16px] leading-[1.9] text-[#1a1a1a] whitespace-pre-wrap break-words font-medium">
        {question.content}
      </div>
      <ImageList images={question.stem_images} />

      {/* 多选题小提示 */}
      {isMulti && !feedback && (
        <p className="mt-4 text-xs font-black uppercase tracking-widest text-[#fbc02d]">
          多选题 · 至少选两项，答错不得分
        </p>
      )}

      {/* 选项 */}
      <div className="mt-6 space-y-3">
        {options.map((opt) => (
          <OptionItem
            key={opt.key}
            option={opt}
            state={optionState(opt.key)}
            onClick={() => onToggle(opt.key)}
          />
        ))}
      </div>
    </div>
  );
};

// 提交后的反馈/解析区
const ExplanationCard = ({ feedback, question }) => {
  if (!feedback) return null;
  const isCorrect = feedback.is_correct;
  return (
    <div
      className={`rounded-[2rem] p-6 border-2 ${
        isCorrect
          ? 'bg-green-50 border-green-200'
          : 'bg-red-50 border-red-200'
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          {isCorrect ? (
            <>
              <div className="w-8 h-8 rounded-xl bg-green-500 text-white flex items-center justify-center">
                <Check size={18} />
              </div>
              <span className="text-lg font-black italic text-green-700">答对了</span>
            </>
          ) : (
            <>
              <div className="w-8 h-8 rounded-xl bg-red-500 text-white flex items-center justify-center">
                <XIcon size={18} />
              </div>
              <span className="text-lg font-black italic text-red-700">
                {feedback.skipped ? '已跳过' : '答错了'}
              </span>
            </>
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
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">
              解析 · 私人笔记
            </span>
          </div>
          <div className="text-[14px] leading-[1.85] text-[#1a1a1a] whitespace-pre-wrap break-words">
            {question.explanation}
          </div>
          <ImageList images={question.explanation_images} />
        </div>
      ) : (
        <p className="text-sm font-medium text-slate-500 italic">（本题暂无解析）</p>
      )}
    </div>
  );
};

// 结果页
const ResultView = ({ label, total, answered, durationSec, onRetry, onExit }) => {
  const attempted = answered.length;
  const correct = answered.filter((a) => a.is_correct).length;
  const accuracy = attempted > 0 ? Math.round((correct / attempted) * 100) : 0;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Banner */}
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-10 relative overflow-hidden">
        <div className="absolute top-6 right-6 w-32 h-32 bg-[#fbc02d] rounded-full blur-[40px] opacity-60" />
        <div className="relative z-10">
          <div className="w-14 h-14 rounded-2xl bg-[#fbc02d] text-black flex items-center justify-center mb-5">
            <Trophy size={26} />
          </div>
          <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mb-1">
            {label || '刷题结果'}
          </p>
          <h3 className="text-3xl font-black italic">本次成绩</h3>

          <div className="mt-8 grid grid-cols-3 gap-4">
            <div>
              <p className="text-4xl font-black tabular-nums">{accuracy}%</p>
              <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">
                正确率
              </p>
            </div>
            <div>
              <p className="text-4xl font-black tabular-nums">
                {correct}<span className="text-base opacity-50">/{attempted}</span>
              </p>
              <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">
                答对
              </p>
            </div>
            <div>
              <p className="text-4xl font-black tabular-nums">{fmtDuration(durationSec)}</p>
              <p className="text-[10px] font-black uppercase tracking-widest opacity-60 mt-1">
                用时
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 简略列表 */}
      <div className="bg-white rounded-[2rem] p-6 shadow-sm border border-[#f2f0e9]">
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">
          作答明细
        </p>
        <div className="flex flex-wrap gap-2">
          {answered.map((a, i) => (
            <div
              key={i}
              className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-black ${
                a.skipped
                  ? 'bg-slate-100 text-slate-400'
                  : a.is_correct
                    ? 'bg-green-100 text-green-700'
                    : 'bg-red-100 text-red-700'
              }`}
              title={`第 ${i + 1} 题：${a.skipped ? '跳过' : a.is_correct ? '对' : '错'}`}
            >
              {i + 1}
            </div>
          ))}
          {total > attempted && (
            <span className="text-xs font-medium text-slate-400 self-center ml-2">
              还剩 {total - attempted} 题未作答
            </span>
          )}
        </div>
      </div>

      {/* 操作 */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onRetry}
          className="flex-1 flex items-center justify-center space-x-2 bg-white border-2 border-[#1a1a1a] text-[#1a1a1a] font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs"
        >
          <RotateCcw size={16} />
          <span>再刷一套</span>
        </button>
        <button
          onClick={onExit}
          className="flex-1 flex items-center justify-center space-x-2 bg-[#fbc02d] text-black font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs"
        >
          <span>返回题库</span>
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};

// ---------------- 主体 ----------------

const BankSession = ({ category, subCategory, label, onExit }) => {
  // phase: loading | running | finished | empty | error
  const [phase, setPhase] = useState('loading');
  const [sessionId, setSessionId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [index, setIndex] = useState(0);
  const [selection, setSelection] = useState(null); // string | string[]
  const [feedback, setFeedback] = useState(null); // {is_correct, correct_answer, skipped?}
  const [answered, setAnswered] = useState([]);
  const [errMsg, setErrMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 本场起始时刻。用 state 而不是 useRef(Date.now())：后者每次渲染都会求值
  // （虽然只保留首次结果），且渲染期读 ref.current 也不合规。
  // 「再开一把」时会重置它，所以是真正的可变状态，需要 setter。
  const [sessionStart, setSessionStart] = useState(() => Date.now());
  // 每题起始时间：只在事件回调里读写，用 ref 合适
  const questionStartRef = useRef(sessionStart);
  // 记录"本题开始"的时刻。包成 useCallback，规则才能确认取时钟发生在
  // 事件回调而非渲染期（goNext 等普通函数无法被静态证明）。
  const markQuestionStart = useCallback(() => {
    questionStartRef.current = Date.now();
  }, []);
  const totalElapsed = useElapsed(sessionStart, phase === 'running');
  // 本场用时（秒）。渲染期不再调 Date.now()，直接复用计时 Hook 的结果
  const sessionDurationSec = totalElapsed;

  // 初始化：拉题 + 开 session
  useEffect(() => {
    let aborted = false;
    (async () => {
      try {
        const params = new URLSearchParams();
        if (category) params.set('category', category);
        if (subCategory) params.set('sub_category', subCategory);
        params.set('random', '1');
        params.set('limit', '30');
        const qres = await api('/api/questions?' + params.toString());
        if (aborted) return;
        const items = qres?.items || [];
        if (items.length === 0) {
          setPhase('empty');
          return;
        }
        const s = await api('/api/practice/sessions', {
          method: 'POST',
          body: { category: label || category || '刷题' },
        });
        if (aborted) return;
        setSessionId(s.id);
        setQuestions(items);
        setSessionStart(Date.now());
        markQuestionStart();
        setPhase('running');
      } catch (e) {
        if (!aborted) {
          setErrMsg(e?.message || '加载失败');
          setPhase('error');
        }
      }
    })();
    return () => {
      aborted = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = questions[index];
  const total = questions.length;

  // 选项交互
  const toggleSelect = (key) => {
    if (feedback || !current) return;
    if (current.question_type === 'multi') {
      setSelection((prev) => {
        const arr = Array.isArray(prev) ? [...prev] : [];
        const i = arr.indexOf(key);
        if (i >= 0) arr.splice(i, 1);
        else arr.push(key);
        return arr.sort();
      });
    } else {
      setSelection(key);
    }
  };

  // 提交
  const submit = async () => {
    if (!current || feedback || submitting) return;
    if (!hasSelection(selection, current.question_type)) return;
    const userAnswer = normalizeAnswer(selection, current.question_type);
    const timeSpentSec = Math.max(1, Math.round((Date.now() - questionStartRef.current) / 1000));

    setSubmitting(true);
    try {
      const res = await api(`/api/practice/sessions/${sessionId}/answers`, {
        method: 'POST',
        body: {
          question_id: current.id,
          user_answer: userAnswer,
          time_spent_sec: timeSpentSec,
        },
      });
      setFeedback(res);
      setAnswered((a) => [
        ...a,
        {
          qid: current.id,
          user_answer: userAnswer,
          correct_answer: res.correct_answer,
          is_correct: !!res.is_correct,
          skipped: false,
        },
      ]);
    } catch (e) {
      setErrMsg(e?.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  // 跳过（标记为未作答，不计对）
  const skip = async () => {
    if (!current || feedback || submitting) return;
    const timeSpentSec = Math.max(1, Math.round((Date.now() - questionStartRef.current) / 1000));

    setSubmitting(true);
    try {
      const res = await api(`/api/practice/sessions/${sessionId}/answers`, {
        method: 'POST',
        body: {
          question_id: current.id,
          user_answer: '',
          time_spent_sec: timeSpentSec,
        },
      });
      setFeedback({ ...res, skipped: true });
      setAnswered((a) => [
        ...a,
        {
          qid: current.id,
          user_answer: '',
          correct_answer: res.correct_answer,
          is_correct: false,
          skipped: true,
        },
      ]);
    } catch (e) {
      setErrMsg(e?.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  // 下一题 / 结束
  const goNext = async () => {
    if (!feedback) return;
    if (index + 1 >= total) {
      await finish();
      return;
    }
    setIndex((i) => i + 1);
    setSelection(null);
    setFeedback(null);
    markQuestionStart();
  };

  const finish = async () => {
    try {
      const durationSec = Math.round((Date.now() - sessionStart) / 1000);
      await api(`/api/practice/sessions/${sessionId}/finish`, {
        method: 'POST',
        body: { duration_sec: durationSec },
      });
    } catch {
      /* 静默 */
    }
    setPhase('finished');
  };

  // 键盘快捷键
  useEffect(() => {
    if (phase !== 'running') return;
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;

      if (feedback) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          goNext();
        }
        return;
      }
      const k = e.key.toUpperCase();
      if (['A', 'B', 'C', 'D', 'E', 'F'].includes(k)) {
        const exists = (current?.options || []).some((o) => o.key === k);
        if (exists) {
          e.preventDefault();
          toggleSelect(k);
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        submit();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, feedback, selection, current, index, submitting]);

  // ---------------- 渲染 ----------------

  if (phase === 'loading') {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center">
        <p className="text-sm font-black uppercase tracking-widest text-slate-400">
          加载题目中…
        </p>
      </div>
    );
  }

  if (phase === 'empty') {
    return (
      <div className="max-w-2xl mx-auto space-y-5">
        <div className="bg-white rounded-[2rem] p-10 text-center shadow-sm border border-[#f2f0e9]">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-[#f2f0e9] text-slate-400 flex items-center justify-center mb-4">
            <AlertTriangle size={24} />
          </div>
          <h3 className="text-xl font-black italic mb-2">{label || '该模块'}</h3>
          <p className="text-sm font-medium text-slate-500 mb-6">
            暂时还没有入库题目，等 Workbuddy 导入后再来刷。
          </p>
          <button
            onClick={onExit}
            className="bg-[#1a1a1a] text-white font-black px-8 py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs"
          >
            返回题库
          </button>
        </div>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="max-w-2xl mx-auto space-y-5">
        <div className="bg-white rounded-[2rem] p-10 text-center shadow-sm border border-red-200">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-red-100 text-red-500 flex items-center justify-center mb-4">
            <AlertTriangle size={24} />
          </div>
          <h3 className="text-xl font-black italic mb-2">加载失败</h3>
          <p className="text-sm font-medium text-slate-500 mb-6">{errMsg}</p>
          <button
            onClick={onExit}
            className="bg-[#1a1a1a] text-white font-black px-8 py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs"
          >
            返回题库
          </button>
        </div>
      </div>
    );
  }

  if (phase === 'finished') {
    return (
      <ResultView
        label={label}
        total={total}
        answered={answered}
        durationSec={sessionDurationSec}
        onRetry={() => {
          // 简单粗暴：再开一把
          setPhase('loading');
          setIndex(0);
          setSelection(null);
          setFeedback(null);
          setAnswered([]);
          setSessionId(null);
          setSessionStart(Date.now());
          markQuestionStart();
          // 触发重拉
          (async () => {
            try {
              const params = new URLSearchParams();
              if (category) params.set('category', category);
              if (subCategory) params.set('sub_category', subCategory);
              params.set('random', '1');
              params.set('limit', '30');
              const qres = await api('/api/questions?' + params.toString());
              const items = qres?.items || [];
              if (items.length === 0) {
                setPhase('empty');
                return;
              }
              const s = await api('/api/practice/sessions', {
                method: 'POST',
                body: { category: label || category || '刷题' },
              });
              setSessionId(s.id);
              setQuestions(items);
              setSessionStart(Date.now());
              markQuestionStart();
              setPhase('running');
            } catch (e) {
              setErrMsg(e?.message || '加载失败');
              setPhase('error');
            }
          })();
        }}
        onExit={onExit}
      />
    );
  }

  // phase === 'running'
  const answeredCount = answered.length;
  const correctCount = answered.filter((a) => a.is_correct).length;
  const canSubmit = !feedback && hasSelection(selection, current?.question_type);

  return (
    <div className="max-w-2xl mx-auto space-y-5 pb-8">
      {/* 顶部工具条 */}
      <div className="flex items-center justify-between bg-white rounded-2xl p-3 shadow-sm border border-[#f2f0e9]">
        <button
          onClick={onExit}
          title="退出"
          className="flex items-center space-x-2 px-3 py-2 rounded-xl text-slate-500 hover:bg-[#f2f0e9] hover:text-[#1a1a1a] transition-colors"
        >
          <ArrowLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">退出</span>
        </button>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1.5 text-slate-500">
            <Clock size={14} />
            <span className="text-xs font-mono tabular-nums font-black">
              {fmtDuration(totalElapsed)}
            </span>
          </div>
          <div className="text-xs font-black uppercase tracking-widest text-slate-400">
            <span className="text-green-600">{correctCount}</span>
            <span className="mx-1">·</span>
            <span className="text-red-500">{answeredCount - correctCount}</span>
          </div>
        </div>
      </div>

      {/* 进度条 */}
      <div className="h-1.5 bg-[#f2f0e9] rounded-full overflow-hidden">
        <div
          className="h-full bg-[#fbc02d] transition-all duration-300"
          style={{ width: `${total > 0 ? ((index + (feedback ? 1 : 0)) / total) * 100 : 0}%` }}
        />
      </div>

      {/* 题目卡 */}
      {current && (
        <QuestionCard
          question={current}
          index={index}
          total={total}
          selection={selection}
          feedback={feedback}
          onToggle={toggleSelect}
        />
      )}

      {/* 解析 */}
      {feedback && current && (
        <ExplanationCard feedback={feedback} question={current} />
      )}

      {/* 操作栏 */}
      <div className="flex items-center space-x-3 sticky bottom-4">
        {!feedback ? (
          <>
            <button
              onClick={skip}
              disabled={submitting}
              className="flex items-center justify-center space-x-2 bg-white border-2 border-[#f2f0e9] text-slate-500 font-black px-5 py-4 rounded-2xl hover:border-[#1a1a1a] hover:text-[#1a1a1a] transition-all uppercase tracking-widest text-xs disabled:opacity-50"
            >
              <SkipForward size={16} />
              <span>跳过</span>
            </button>
            <button
              onClick={submit}
              disabled={!canSubmit || submitting}
              className="flex-1 flex items-center justify-center space-x-2 bg-[#1a1a1a] text-white font-black px-6 py-4 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-[#1a1a1a] disabled:hover:text-white"
            >
              <Check size={16} />
              <span>{submitting ? '提交中…' : '提交答案'}</span>
            </button>
          </>
        ) : (
          <button
            onClick={goNext}
            className="flex-1 flex items-center justify-center space-x-2 bg-[#fbc02d] text-black font-black px-6 py-4 rounded-2xl hover:bg-[#1a1a1a] hover:text-white transition-all uppercase tracking-widest text-xs shadow-lg"
          >
            {index + 1 >= total ? (
              <>
                <Flag size={16} />
                <span>查看成绩</span>
              </>
            ) : (
              <>
                <span>下一题</span>
                <ChevronRight size={16} />
              </>
            )}
          </button>
        )}
      </div>

      {/* 底部提示 */}
      <p className="text-center text-[10px] font-black uppercase tracking-widest text-slate-400">
        快捷键：A/B/C/D 选择 · Enter 提交 / 下一题
      </p>
    </div>
  );
};

export default BankSession;

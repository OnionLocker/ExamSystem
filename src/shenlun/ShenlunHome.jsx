import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  CheckCircle2,
  ChevronDown,
  Clock,
  Loader2,
  NotebookPen,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  Type,
  X,
} from 'lucide-react';
import { api, getToken } from '../api.js';

const KIND_META = {
  zhenti: { label: '真题', className: 'border-[#6b5428] bg-[#f4e6c8] text-[#6b5428]' },
  ai: { label: 'AI 模拟', className: 'border-sky-200 bg-sky-50 text-sky-700' },
};
const VERDICT_CLASS = {
  hit: 'bg-green-50 text-green-700 border-green-200',
  partial: 'bg-amber-50 text-amber-700 border-amber-200',
  miss: 'bg-red-50 text-red-600 border-red-200',
};

const fmtClock = (sec) => {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};
const withToken = (src) => `${src}${src.includes('?') ? '&' : '?'}token=${encodeURIComponent(getToken())}`;
const wordsLabel = (req) => {
  if (req?.words_min && req?.words_max) return `${req.words_min}～${req.words_max} 字`;
  if (req?.words_max) return `≤ ${req.words_max} 字`;
  return null;
};
const busy = (attempt) => attempt?.status === 'grading';

// ─── 列表 ─────────────────────────────────────────────────────

function PaperList({ onOpen }) {
  const [papers, setPapers] = useState(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const load = () => setVersion((v) => v + 1);

  useEffect(() => {
    let cancelled = false;
    api('/api/shenlun/papers')
      .then((data) => { if (!cancelled) { setPapers(data.papers || []); setError(''); } })
      .catch((e) => { if (!cancelled) setError(e.message || '加载失败'); });
    return () => { cancelled = true; };
  }, [version]);

  const remove = async (paper) => {
    if (!window.confirm(`删除「${paper.title}」？作答照片和批改记录会一起删掉。`)) return;
    await api(`/api/shenlun/papers/${encodeURIComponent(paper.id)}`, { method: 'DELETE' });
    load();
  };

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex items-center justify-between rounded-3xl border border-[#e8d5b0] bg-white/70 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#1a1a1a] text-white">
            <NotebookPen size={18} />
          </div>
          <div>
            <p className="text-base font-black text-[#1a1a1a]">申论 · 广东县级卷</p>
            <p className="text-xs font-bold text-[#888]">手写拍照上传，按要点表采点批改；作文按档次评</p>
          </div>
        </div>
        <button type="button" onClick={load} className="flex items-center gap-1.5 text-sm font-black text-[#6b5428]">
          <RefreshCw size={14} /> 刷新
        </button>
      </div>

      {error && <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-bold text-red-600">{error}</p>}
      {papers === null && !error && (
        <div className="flex justify-center py-16 text-[#888]"><Loader2 className="animate-spin" /></div>
      )}
      {papers?.length === 0 && (
        <div className="rounded-3xl border border-dashed border-[#e8d5b0] bg-white/60 px-6 py-10 text-center">
          <p className="text-base font-black text-[#1a1a1a]">还没有申论试卷</p>
          <p className="mt-2 text-sm font-medium leading-relaxed text-[#888]">
            让 Hermes「出一套申论」或「出两道归纳概括」；广东真题由 grokbot 放进收件箱后导入。
          </p>
        </div>
      )}
      {papers?.map((paper) => {
        const meta = KIND_META[paper.kind] || KIND_META.ai;
        return (
          <div key={paper.id} className="flex items-center gap-4 rounded-3xl border border-[#e8d5b0] bg-white px-5 py-4 shadow-sm">
            <button type="button" onClick={() => onOpen(paper.id)} className="min-w-0 flex-1 text-left">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-black text-[#1a1a1a]">{paper.title}</span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] font-black ${meta.className}`}>{meta.label}</span>
              </div>
              <p className="mt-1.5 text-xs font-bold text-[#888]">
                {paper.question_count} 题 · {paper.total_score} 分
                {paper.time_limit_min ? ` · 建议 ${paper.time_limit_min} 分钟` : ''}
                {' · '}已批改 {paper.graded_questions}/{paper.question_count}
              </p>
            </button>
            <button type="button" onClick={() => onOpen(paper.id)} className="text-sm font-black text-[#1a1a1a]">
              {paper.graded_questions ? '继续 →' : '开始 →'}
            </button>
            <button type="button" onClick={() => remove(paper)} className="text-[#ccc] hover:text-red-500" title="删除">
              <Trash2 size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ─── 批改结果 ─────────────────────────────────────────────────

function PointsResult({ grading }) {
  return (
    <div className="space-y-3">
      {grading.points.map((p) => (
        <div key={p.id} className="rounded-2xl border border-[#f0e4c8] bg-white p-4">
          <div className="flex flex-wrap items-start gap-2">
            <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-black ${VERDICT_CLASS[p.verdict]}`}>
              {p.verdict_text} {p.earned}/{p.score}
            </span>
            {p.disputed && (
              <span className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-black text-slate-500">
                两遍有分歧
              </span>
            )}
            <p className="min-w-0 flex-1 text-sm font-bold leading-relaxed text-[#1a1a1a]">{p.id} {p.text}</p>
          </div>
          {p.answer_quote && (
            <p className="mt-2 text-sm leading-relaxed text-[#444]"><span className="font-black text-[#6b5428]">你写的：</span>{p.answer_quote}</p>
          )}
          {p.evidence?.length > 0 && (
            <p className="mt-1.5 text-xs leading-relaxed text-[#888]">
              <span className="font-black">材料依据：</span>
              {p.evidence.map((e) => `${e.para}「${e.quote}」`).join('；')}
            </p>
          )}
          {(p.reason || p.note) && <p className="mt-1.5 text-xs leading-relaxed text-[#888]">{p.note || p.reason}</p>}
        </div>
      ))}
      {['format', 'expression'].map((key) => grading[key] && (
        <p key={key} className="rounded-2xl bg-[#faf6ec] px-4 py-3 text-sm font-bold text-[#444]">
          {grading[key].label} {grading[key].earned}/{grading[key].score} —— {grading[key].reason}
        </p>
      ))}
    </div>
  );
}

function EssayResult({ grading }) {
  return (
    <div className="space-y-3">
      <p className="text-lg font-black text-[#1a1a1a]">{grading.level}</p>
      {grading.dimensions.map((d) => (
        <div key={d.name} className="rounded-2xl border border-[#f0e4c8] bg-white p-4">
          <p className="text-sm font-black text-[#1a1a1a]">
            {d.name}：{d.level}
            {d.disputed && <span className="ml-2 text-[11px] font-black text-slate-500">两遍有分歧</span>}
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-[#444]">{d.reason}</p>
          {d.quote && <p className="mt-1.5 text-xs leading-relaxed text-[#888]">原文：「{d.quote}」</p>}
        </div>
      ))}
    </div>
  );
}

function AttemptView({ attempt, question, onRegrade, onDelete }) {
  const [showText, setShowText] = useState(false);
  const g = attempt.grading;
  return (
    <div className="space-y-4 rounded-3xl border border-[#e8d5b0] bg-[#fffdf7] p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-black text-[#888]">第 {attempt.id} 次作答 · {attempt.created_at}</span>
        {attempt.time_spent_sec ? <span className="text-xs font-bold text-[#888]">用时 {fmtClock(attempt.time_spent_sec)}</span> : null}
        <div className="ml-auto flex items-center gap-3">
          {!busy(attempt) && (
            <button type="button" onClick={onRegrade} className="text-xs font-black text-[#6b5428]">重新批改</button>
          )}
          <button type="button" onClick={onDelete} className="text-xs font-black text-[#bbb] hover:text-red-500">删除</button>
        </div>
      </div>

      {attempt.images?.length > 0 && (
        <div className="flex gap-2 overflow-x-auto">
          {attempt.images.map((src) => (
            <a key={src} href={withToken(src)} target="_blank" rel="noreferrer">
              <img src={withToken(src)} alt="" className="h-24 w-auto rounded-lg border border-[#e8d5b0] object-cover" />
            </a>
          ))}
        </div>
      )}

      {busy(attempt) && (
        <p className="flex items-center gap-2 text-sm font-bold text-[#6b5428]">
          <Loader2 size={16} className="animate-spin" /> 正在批改（读照片、两遍独立采点），大约 1–3 分钟…
        </p>
      )}
      {attempt.status === 'failed' && (
        <p className="flex items-start gap-2 rounded-2xl bg-red-50 px-4 py-3 text-sm font-bold text-red-600">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" /> 批改失败：{attempt.error}
        </p>
      )}

      {attempt.status === 'graded' && g && (
        <>
          <div className="flex items-end gap-3">
            <span className="text-4xl font-black tabular-nums text-[#1a1a1a]">{attempt.score}</span>
            <span className="pb-1 text-base font-black text-[#888]">/ {attempt.max_score} 分</span>
            {attempt.word_count ? (
              <span className="pb-1.5 text-xs font-bold text-[#888]">
                约 {attempt.word_count} 字{wordsLabel(question.requirements) ? `（要求 ${wordsLabel(question.requirements)}）` : ''}
              </span>
            ) : null}
          </div>
          {g.comment && <p className="text-sm font-bold leading-relaxed text-[#444]">{g.comment}</p>}
          {g.notes?.map((n) => (
            <p key={n} className="rounded-2xl bg-amber-50 px-4 py-2.5 text-xs font-bold leading-relaxed text-amber-800">{n}</p>
          ))}
          {g.kind === 'essay' ? <EssayResult grading={g} /> : <PointsResult grading={g} />}
          {attempt.answer_text && (
            <div>
              <button type="button" onClick={() => setShowText((v) => !v)} className="flex items-center gap-1 text-xs font-black text-[#6b5428]">
                <ChevronDown size={14} className={showText ? 'rotate-180' : ''} /> 阅卷人读到的答案
              </button>
              {showText && (
                <p className="mt-2 whitespace-pre-wrap rounded-2xl bg-white p-4 text-sm leading-relaxed text-[#444]">{attempt.answer_text}</p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── 单题 ─────────────────────────────────────────────────────

function QuestionPanel({ questionId, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [files, setFiles] = useState([]);
  const [typing, setTyping] = useState(false);
  const [typed, setTyped] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    const data = await api(`/api/shenlun/questions/${encodeURIComponent(questionId)}`);
    setDetail(data);
    return data;
  }, [questionId]);

  useEffect(() => {
    let cancelled = false;
    api(`/api/shenlun/questions/${encodeURIComponent(questionId)}`)
      .then((data) => { if (!cancelled) setDetail(data); })
      .catch((e) => { if (!cancelled) setError(e.message || '加载失败'); });
    return () => { cancelled = true; };
  }, [questionId]);

  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  // 批改在后台跑，有进行中的作答就轮询
  const pending = detail?.attempts?.some(busy);
  useEffect(() => {
    if (!pending) return undefined;
    const t = setInterval(async () => {
      const data = await load();
      if (!data.attempts.some(busy)) onChanged?.();
    }, 4000);
    return () => clearInterval(t);
  }, [pending, load, onChanged]);

  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  const submit = async () => {
    if (!files.length && typed.trim().length < 20) {
      setError(typing ? '答案太短' : '先拍照或选几张答题照片');
      return;
    }
    setSubmitting(true); setError('');
    try {
      const fd = new FormData();
      if (typing) fd.append('text', typed);
      else files.forEach((f) => fd.append('photos', f));
      fd.append('time_spent_sec', String(elapsed));
      await api(`/api/shenlun/questions/${encodeURIComponent(questionId)}/attempts`, { method: 'POST', body: fd });
      setFiles([]); setTyped(''); setRunning(false); setElapsed(0);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const regrade = async (attempt) => {
    await api(`/api/shenlun/attempts/${attempt.id}/grade`, { method: 'POST' });
    load();
  };
  const removeAttempt = async (attempt) => {
    if (!window.confirm('删除这次作答？')) return;
    await api(`/api/shenlun/attempts/${attempt.id}`, { method: 'DELETE' });
    await load();
    onChanged?.();
  };
  const reveal = async () => {
    if (!detail.key_revealed && !window.confirm('还没交过答案，确定先看要点和参考答案吗？')) return;
    if (!detail.key_revealed) setDetail(await api(`/api/shenlun/questions/${encodeURIComponent(questionId)}?reveal=1`));
    setShowKey((v) => !v);
  };

  if (!detail) return <div className="flex justify-center py-16 text-[#888]"><Loader2 className="animate-spin" /></div>;
  const req = detail.requirements || {};

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-[#e8d5b0] bg-white p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[#1a1a1a] px-3 py-1 text-xs font-black text-white">第 {detail.no} 题 · {detail.qtype}</span>
          <span className="text-xs font-black text-[#6b5428]">{req.score} 分</span>
          {wordsLabel(req) && <span className="text-xs font-bold text-[#888]">{wordsLabel(req)}</span>}
          {req.material_ids?.length > 0 && (
            <span className="text-xs font-bold text-[#888]">范围：{req.material_ids.map((m) => m.replace('M', '材料')).join('、')}</span>
          )}
        </div>
        <p className="mt-3 whitespace-pre-wrap text-[17px] font-medium leading-[1.9] text-[#1a1a1a]">{detail.prompt}</p>
      </div>

      <div className="space-y-4 rounded-3xl border border-[#e8d5b0] bg-white p-5">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setRunning((v) => !v)}
            className="flex items-center gap-1.5 rounded-xl border border-[#e8d5b0] px-3 py-2 text-sm font-black text-[#1a1a1a]"
          >
            {running ? <Pause size={14} /> : <Play size={14} />}
            <Clock size={14} /> {fmtClock(elapsed)}
          </button>
          <div className="ml-auto flex rounded-xl border border-[#e8d5b0] p-0.5 text-xs font-black">
            <button type="button" onClick={() => setTyping(false)} className={`flex items-center gap-1 rounded-lg px-3 py-1.5 ${!typing ? 'bg-[#1a1a1a] text-white' : 'text-[#888]'}`}>
              <Camera size={13} /> 拍照
            </button>
            <button type="button" onClick={() => setTyping(true)} className={`flex items-center gap-1 rounded-lg px-3 py-1.5 ${typing ? 'bg-[#1a1a1a] text-white' : 'text-[#888]'}`}>
              <Type size={13} /> 打字
            </button>
          </div>
        </div>

        {typing ? (
          <div>
            <textarea
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              rows={10}
              placeholder="直接输入答案"
              className="w-full rounded-2xl border border-[#e8d5b0] bg-[#fffdf7] p-4 text-[15px] leading-relaxed outline-none focus:border-[#6b5428]"
            />
            <p className="mt-1 text-right text-xs font-bold text-[#888]">{typed.replace(/\s+/g, '').length} 字</p>
          </div>
        ) : (
          <div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => { setFiles((prev) => [...prev, ...Array.from(e.target.files || [])].slice(0, 12)); e.target.value = ''; }}
            />
            <div className="flex flex-wrap gap-2">
              {previews.map((src, i) => (
                <div key={src} className="relative">
                  <img src={src} alt="" className="h-28 w-auto rounded-xl border border-[#e8d5b0] object-cover" />
                  <span className="absolute left-1 top-1 rounded-md bg-black/60 px-1.5 text-[11px] font-black text-white">{i + 1}</span>
                  <button
                    type="button"
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                    className="absolute right-1 top-1 rounded-full bg-black/60 p-0.5 text-white"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="flex h-28 w-24 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-[#d9c39a] text-xs font-black text-[#6b5428]"
              >
                <Camera size={20} /> 加照片
              </button>
            </div>
            <p className="mt-2 text-xs font-medium text-[#888]">按答题顺序拍，一页一张，拍正、拍清楚格子里的字。</p>
          </div>
        )}

        {error && <p className="text-sm font-bold text-red-600">{error}</p>}
        <button
          type="button"
          disabled={submitting || pending}
          onClick={submit}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#1a1a1a] py-3 text-sm font-black text-white disabled:opacity-40"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
          交卷批改
        </button>
      </div>

      {detail.attempts.map((a) => (
        <AttemptView key={a.id} attempt={a} question={detail} onRegrade={() => regrade(a)} onDelete={() => removeAttempt(a)} />
      ))}

      <div className="rounded-3xl border border-[#e8d5b0] bg-white p-5">
        <button type="button" onClick={reveal} className="flex items-center gap-1.5 text-sm font-black text-[#6b5428]">
          <ChevronDown size={16} className={showKey ? 'rotate-180' : ''} /> 要点表与参考答案
          {!detail.key_revealed && <span className="text-xs font-bold text-[#aaa]">（交卷批改后再看）</span>}
        </button>
        {showKey && detail.rubric && (
          <div className="mt-4 space-y-3 text-sm leading-relaxed text-[#444]">
            {detail.rubric.kind === 'essay' ? (
              <>
                <p><span className="font-black">立意：</span>{detail.rubric.theme}</p>
                {detail.rubric.must_cover?.map((t) => <p key={t.id}>{t.id} {t.text}</p>)}
              </>
            ) : (
              <>
                {detail.rubric.points?.map((p) => <p key={p.id}><span className="font-black">{p.id}（{p.score}分）</span>{p.text}</p>)}
                {detail.rubric.format_points?.map((p) => <p key={p.id}><span className="font-black">{p.id}（{p.score}分）</span>{p.text}</p>)}
                {detail.rubric.expression_score ? <p><span className="font-black">表述（{detail.rubric.expression_score}分）</span>条理清楚、语言规范</p> : null}
              </>
            )}
            {detail.reference_answer && (
              <div className="rounded-2xl bg-[#faf6ec] p-4">
                <p className="mb-1 font-black text-[#1a1a1a]">参考答案</p>
                <p className="whitespace-pre-wrap">{detail.reference_answer}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── 整卷 ─────────────────────────────────────────────────────

function PaperView({ paperId, onBack }) {
  const [paper, setPaper] = useState(null);
  const [current, setCurrent] = useState(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const load = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let cancelled = false;
    api(`/api/shenlun/papers/${encodeURIComponent(paperId)}`)
      .then((data) => {
        if (cancelled) return;
        setPaper(data);
        setCurrent((c) => c || data.questions[0]?.id || null);
      })
      .catch((e) => { if (!cancelled) setError(e.message || '加载失败'); });
    return () => { cancelled = true; };
  }, [paperId, version]);

  if (error) return <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-bold text-red-600">{error}</p>;
  if (!paper) return <div className="flex justify-center py-16 text-[#888]"><Loader2 className="animate-spin" /></div>;
  const active = paper.questions.find((q) => q.id === current);
  const scope = active?.requirements?.material_ids || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={onBack} className="flex items-center gap-1 text-sm font-black text-[#6b5428]">
          <ArrowLeft size={16} /> 试卷列表
        </button>
        <p className="min-w-0 flex-1 truncate text-sm font-black text-[#1a1a1a]">{paper.title}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {paper.questions.map((q) => {
          const a = q.latest_attempt;
          return (
            <button
              key={q.id}
              type="button"
              onClick={() => setCurrent(q.id)}
              className={`rounded-2xl border px-4 py-2.5 text-sm font-black ${
                q.id === current ? 'border-[#1a1a1a] bg-[#1a1a1a] text-white' : 'border-[#e8d5b0] bg-white text-[#1a1a1a]'
              }`}
            >
              {q.no}. {q.qtype}
              <span className="ml-2 text-xs font-bold opacity-70">
                {a?.status === 'graded' ? `${a.score}/${a.max_score}` : busy(a) ? '批改中' : `${q.requirements.score}分`}
              </span>
            </button>
          );
        })}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="max-h-[calc(100vh-220px)] space-y-5 overflow-y-auto rounded-3xl border border-[#e8d5b0] bg-white p-5 lg:sticky lg:top-0">
          {paper.materials.map((m) => (
            <section key={m.id} className={scope.length && !scope.includes(m.id) ? 'opacity-40' : ''}>
              <h3 className="mb-2 text-sm font-black text-[#6b5428]">{m.title}</h3>
              {m.paragraphs.map((p) => (
                <p key={p.id} className="mb-2 text-[15px] leading-[1.9] text-[#1a1a1a]" style={{ textIndent: '2em' }}>{p.text}</p>
              ))}
            </section>
          ))}
          {paper.source_note && <p className="border-t border-[#f0e4c8] pt-3 text-xs leading-relaxed text-[#aaa]">{paper.source_note}</p>}
        </div>
        <div className="order-first lg:order-none">
          {active && <QuestionPanel key={active.id} questionId={active.id} onChanged={load} />}
        </div>
      </div>
    </div>
  );
}

export default function ShenlunHome() {
  const [paperId, setPaperId] = useState(null);
  return paperId
    ? <PaperView paperId={paperId} onBack={() => setPaperId(null)} />
    : <PaperList onOpen={setPaperId} />;
}

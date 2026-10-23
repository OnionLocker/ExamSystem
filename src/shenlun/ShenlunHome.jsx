import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  CheckCircle2,
  ChevronDown,
  Clock,
  Expand,
  Loader2,
  Maximize2,
  Minimize2,
  NotebookPen,
  Pause,
  Play,
  RefreshCw,
  Send,
  Shrink,
  Trash2,
  X,
} from 'lucide-react';
import { api, getToken } from '../api.js';

const KIND_META = {
  zhenti: { label: '真题', className: 'border-[#6b5428] bg-[#f4e6c8] text-[#6b5428]' },
  ai: { label: 'AI 模拟', className: 'border-sky-200 bg-sky-50 text-sky-700' },
};
const SUBMISSION_STATUS = {
  submitted: { label: '待复盘', className: 'bg-[#f4e6c8] text-[#6b5428]' },
  grading: { label: '评分中', className: 'bg-amber-50 text-amber-700' },
  graded: { label: '已评分', className: 'bg-sky-50 text-sky-700' },
  reviewed: { label: '已复盘', className: 'bg-[#1a1a1a] text-[#7dffb3]' },
  failed: { label: '评分失败', className: 'bg-red-50 text-red-600' },
};
const VERDICT_CLASS = {
  hit: 'bg-green-50 text-green-700 border-green-200',
  partial: 'bg-amber-50 text-amber-700 border-amber-200',
  miss: 'bg-red-50 text-red-600 border-red-200',
};

const fmtClock = (sec) => {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};
const withToken = (src) => `${src}${src.includes('?') ? '&' : '?'}token=${encodeURIComponent(getToken())}`;
const wordsLabel = (req) => {
  if (req?.words_min && req?.words_max) return `${req.words_min}～${req.words_max} 字`;
  if (req?.words_max) return `≤ ${req.words_max} 字`;
  return null;
};

// 整套计时存在本机，切走再回来接着计
const timerKey = (paperId) => `shenlun.timer.${paperId}`;
const readTimer = (paperId) => {
  try { return JSON.parse(localStorage.getItem(timerKey(paperId))) || { elapsed: 0 }; } catch { return { elapsed: 0 }; }
};

const IS_STANDALONE = typeof window !== 'undefined' && (
  window.matchMedia('(display-mode: standalone), (display-mode: fullscreen)').matches
  || window.navigator.standalone === true
);
const osFullscreenEl = () => document.fullscreenElement || document.webkitFullscreenElement;

function useBrowserFullscreen() {
  const [osFs, setOsFs] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const sync = () => setOsFs(!!osFullscreenEl());
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    sync();
    return () => {
      document.removeEventListener('fullscreenchange', sync);
      document.removeEventListener('webkitfullscreenchange', sync);
    };
  }, []);
  const toggle = () => {
    setError('');
    if (IS_STANDALONE) return;
    if (osFullscreenEl()) {
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      if (exit) Promise.resolve(exit.call(document)).catch(() => {});
      return;
    }
    const enabled = document.fullscreenEnabled || document.webkitFullscreenEnabled;
    const req = document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen;
    if (!enabled || !req) {
      setError('请用 Safari 打开，分享后添加到主屏幕，从桌面图标进就没有顶栏。');
      return;
    }
    Promise.resolve(req.call(document.documentElement, { navigationUI: 'hide' })).catch(() => {
      setError('浏览器拒绝了全屏。请用 Safari 打开，再分享到主屏幕。');
    });
  };
  return { osFs, toggle, error };
}

function FullscreenButtons({ fullscreen, onToggleFullscreen }) {
  const { osFs, toggle, error } = useBrowserFullscreen();
  const btn = (on) => `flex min-h-10 shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-sm font-black ${
    on ? 'bg-[#1a1a1a] text-white' : 'border border-[#e8d5b0] bg-white text-[#1a1a1a]'
  }`;
  return (
    <>
      <button
        type="button"
        onClick={onToggleFullscreen}
        title={fullscreen ? '退出全屏，显示导航' : '全屏阅读材料'}
        className={btn(fullscreen)}
      >
        {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        {fullscreen ? '退出全屏' : '全屏'}
      </button>
      {!IS_STANDALONE && (
        <button
          type="button"
          onClick={toggle}
          title={osFs ? '退出浏览器全屏' : '隐藏浏览器地址栏'}
          className={btn(osFs)}
        >
          {osFs ? <Shrink size={16} /> : <Expand size={16} />}
          {osFs ? '退出顶栏' : '隐藏顶栏'}
        </button>
      )}
      {error && <span className="max-w-xs text-xs font-bold leading-relaxed text-red-600">{error}</span>}
    </>
  );
}

function MaterialsView({ paper, scope, reading = false }) {
  return (
    <div className={reading ? 'mx-auto w-full max-w-3xl space-y-8' : 'space-y-5'}>
      {paper.materials.map((m) => (
        <section key={m.id} className={scope.length && !scope.includes(m.id) ? 'opacity-40' : ''}>
          <h3 className={`font-black text-[#6b5428] ${reading ? 'mb-3 text-base' : 'mb-2 text-sm'}`}>{m.title}</h3>
          {m.paragraphs.map((p) => (
            <p
              key={p.id}
              className={`text-[#1a1a1a] ${reading ? 'mb-3 text-[17px] leading-[2]' : 'mb-2 text-[15px] leading-[1.9]'}`}
              style={{ textIndent: '2em' }}
            >
              {p.text}
            </p>
          ))}
        </section>
      ))}
      {paper.source_note && <p className="border-t border-[#f0e4c8] pt-3 text-xs leading-relaxed text-[#aaa]">{paper.source_note}</p>}
    </div>
  );
}

// ─── 列表 ─────────────────────────────────────────────────────

function PaperList({ onOpen, fullscreen = false, onToggleFullscreen }) {
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
    if (!window.confirm(`删除「${paper.title}」？作答照片和评分记录会一起删掉。`)) return;
    await api(`/api/shenlun/papers/${encodeURIComponent(paper.id)}`, { method: 'DELETE' });
    load();
  };

  return (
    <div className={fullscreen ? 'h-full min-h-0 overflow-y-auto overscroll-y-contain px-4 py-4 sm:px-8' : ''}>
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-[#e8d5b0] bg-white/70 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#1a1a1a] text-white">
            <NotebookPen size={18} />
          </div>
          <div>
            <p className="text-base font-black text-[#1a1a1a]">申论 · 广东省考</p>
            <p className="text-xs font-bold text-[#888]">每题拍照上传，写完整套交卷；评分和点评在 Hermes「申论复盘」里做</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FullscreenButtons fullscreen={fullscreen} onToggleFullscreen={onToggleFullscreen} />
          <button type="button" onClick={load} className="flex min-h-10 items-center gap-1.5 rounded-xl px-3 text-sm font-black text-[#6b5428]">
            <RefreshCw size={14} /> 刷新
          </button>
        </div>
      </div>

      {error && <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-bold text-red-600">{error}</p>}
      {papers === null && !error && (
        <div className="flex justify-center py-16 text-[#888]"><Loader2 className="animate-spin" /></div>
      )}
      {papers?.length === 0 && (
        <div className="rounded-3xl border border-dashed border-[#e8d5b0] bg-white/60 px-6 py-10 text-center">
          <p className="text-base font-black text-[#1a1a1a]">还没有申论试卷</p>
          <p className="mt-2 text-sm font-medium leading-relaxed text-[#888]">
            让 Hermes「出一套申论」或「出两道归纳概括」；也可以说「出一套省市卷」。
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
                {paper.submissions ? ` · 已交卷 ${paper.submissions} 次` : ''}
                {paper.drafts ? ` · 草稿 ${paper.drafts} 题` : ''}
              </p>
            </button>
            <button type="button" onClick={() => onOpen(paper.id)} className="text-sm font-black text-[#1a1a1a]">
              {paper.drafts || paper.submissions ? '继续 →' : '开始 →'}
            </button>
            <button type="button" onClick={() => remove(paper)} className="text-[#ccc] hover:text-red-500" title="删除">
              <Trash2 size={16} />
            </button>
          </div>
        );
      })}
    </div>
    </div>
  );
}

// ─── 评分结果 ─────────────────────────────────────────────────

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

function Photos({ images, onRemove }) {
  return (
    <div className="flex flex-wrap gap-2">
      {images.map((src, i) => (
        <div key={src} className="relative">
          <a href={withToken(src)} target="_blank" rel="noreferrer">
            <img src={withToken(src)} alt="" className="h-28 w-auto rounded-xl border border-[#e8d5b0] object-cover" />
          </a>
          <span className="absolute left-1 top-1 rounded-md bg-black/60 px-1.5 text-[11px] font-black text-white">{i + 1}</span>
          {onRemove && (
            <button type="button" onClick={() => onRemove(i)} className="absolute right-1 top-1 rounded-full bg-black/60 p-0.5 text-white">
              <X size={12} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function GradedAttempt({ attempt, question }) {
  const [open, setOpen] = useState(false);
  const [showText, setShowText] = useState(false);
  const g = attempt.grading;
  return (
    <div className="rounded-3xl border border-[#e8d5b0] bg-[#fffdf7] p-5">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-3 text-left">
        <span className="text-3xl font-black tabular-nums text-[#1a1a1a]">{attempt.score}</span>
        <span className="text-sm font-black text-[#888]">/ {attempt.max_score} 分</span>
        <span className="text-xs font-bold text-[#888]">
          交卷 #{attempt.submission_id}{attempt.word_count ? ` · 约 ${attempt.word_count} 字` : ''}
          {wordsLabel(question.requirements) ? `（要求 ${wordsLabel(question.requirements)}）` : ''}
        </span>
        <ChevronDown size={16} className={`ml-auto text-[#6b5428] ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && g && (
        <div className="mt-4 space-y-4">
          {attempt.images?.length > 0 && <Photos images={attempt.images} />}
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
        </div>
      )}
    </div>
  );
}

// ─── 单题 ─────────────────────────────────────────────────────

function QuestionPanel({ questionId, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [version, setVersion] = useState(0);
  const fileRef = useRef(null);
  const reload = () => setVersion((v) => v + 1);

  useEffect(() => {
    let cancelled = false;
    api(`/api/shenlun/questions/${encodeURIComponent(questionId)}`)
      .then((data) => { if (!cancelled) setDetail(data); })
      .catch((e) => { if (!cancelled) setError(e.message || '加载失败'); });
    return () => { cancelled = true; };
  }, [questionId, version]);

  const addPhotos = async (files) => {
    if (!files.length) return;
    setUploading(true); setError('');
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append('photos', f));
      await api(`/api/shenlun/questions/${encodeURIComponent(questionId)}/photos`, { method: 'POST', body: fd });
      reload();
      onChanged?.();
    } catch (e) {
      setError(e.message || '上传失败');
    } finally {
      setUploading(false);
    }
  };
  const removePhoto = async (i) => {
    await api(`/api/shenlun/attempts/${detail.draft.id}/photos/${i}`, { method: 'DELETE' });
    reload();
    onChanged?.();
  };
  const reveal = async () => {
    if (!detail.key_revealed && !window.confirm('这道题还没评过分，确定先看要点和参考答案吗？')) return;
    if (!detail.key_revealed) setDetail(await api(`/api/shenlun/questions/${encodeURIComponent(questionId)}?reveal=1`));
    setShowKey((v) => !v);
  };

  if (!detail) return <div className="flex justify-center py-16 text-[#888]"><Loader2 className="animate-spin" /></div>;
  const req = detail.requirements || {};
  const graded = detail.attempts.filter((a) => a.status === 'graded');

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

      <div className="space-y-3 rounded-3xl border border-[#e8d5b0] bg-white p-5">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => { addPhotos(Array.from(e.target.files || [])); e.target.value = ''; }}
        />
        <div className="flex flex-wrap gap-2">
          {detail.draft?.images?.length > 0 && <Photos images={detail.draft.images} onRemove={removePhoto} />}
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
            className="flex h-28 w-24 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-[#d9c39a] text-xs font-black text-[#6b5428] disabled:opacity-50"
          >
            {uploading ? <Loader2 size={20} className="animate-spin" /> : <Camera size={20} />}
            {uploading ? '上传中' : '加照片'}
          </button>
        </div>
        <p className="text-xs font-medium text-[#888]">
          {detail.draft?.images?.length
            ? `本题已存 ${detail.draft.images.length} 张，写完整套后点上方「交卷」。`
            : '按答题顺序拍，一页一张，拍正、拍清楚格子里的字。照片会马上保存。'}
        </p>
        {error && <p className="text-sm font-bold text-red-600">{error}</p>}
      </div>

      {graded.map((a) => <GradedAttempt key={a.id} attempt={a} question={detail} />)}

      <div className="rounded-3xl border border-[#e8d5b0] bg-white p-5">
        <button type="button" onClick={reveal} className="flex items-center gap-1.5 text-sm font-black text-[#6b5428]">
          <ChevronDown size={16} className={showKey ? 'rotate-180' : ''} /> 要点表与参考答案
          {!detail.key_revealed && <span className="text-xs font-bold text-[#aaa]">（评分后再看）</span>}
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

function Submissions({ submissions }) {
  if (!submissions?.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {submissions.map((s) => {
        const meta = SUBMISSION_STATUS[s.status] || SUBMISSION_STATUS.submitted;
        return (
          <span key={s.id} className="flex items-center gap-2 rounded-2xl border border-[#e8d5b0] bg-white px-3 py-2 text-xs font-bold text-[#444]">
            交卷 #{s.id} · {s.answered} 题
            {s.score != null && <span className="font-black text-[#1a1a1a]">{s.score}/{s.max_score}</span>}
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-black ${meta.className}`}>{meta.label}</span>
          </span>
        );
      })}
    </div>
  );
}

function PaperView({ paperId, onBack, fullscreen = false, onToggleFullscreen }) {
  const [paper, setPaper] = useState(null);
  const [current, setCurrent] = useState(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const [timer, setTimer] = useState(() => readTimer(paperId));
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState('');
  const [showQuestion, setShowQuestion] = useState(false);
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

  useEffect(() => {
    localStorage.setItem(timerKey(paperId), JSON.stringify(timer));
    if (!timer.running) return undefined;
    const t = setInterval(() => setTimer((s) => ({ ...s, elapsed: s.elapsed + 1 })), 1000);
    return () => clearInterval(t);
  }, [paperId, timer]);

  const toggleFullscreen = () => {
    if (!fullscreen) setShowQuestion(false);
    onToggleFullscreen?.();
  };

  if (error) return <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-bold text-red-600">{error}</p>;
  if (!paper) return <div className="flex justify-center py-16 text-[#888]"><Loader2 className="animate-spin" /></div>;
  const active = paper.questions.find((q) => q.id === current);
  const scope = active?.requirements?.material_ids || [];
  const drafted = paper.questions.filter((q) => q.draft?.images?.length);

  const submit = async () => {
    const missing = paper.questions.filter((q) => !q.draft?.images?.length).map((q) => `第${q.no}题`);
    const tip = missing.length ? `\n${missing.join('、')}没有照片，不计分。` : '';
    if (!window.confirm(`交卷：共 ${drafted.length} 题有照片，用时 ${fmtClock(timer.elapsed)}。${tip}\n交卷后照片不能再改。`)) return;
    setSubmitting(true); setNotice('');
    try {
      const sub = await api(`/api/shenlun/papers/${encodeURIComponent(paperId)}/submit`, {
        method: 'POST', body: { time_spent_sec: timer.elapsed },
      });
      setTimer({ elapsed: 0, running: false });
      setNotice(`已交卷 #${sub.id}（${sub.answered} 题）。去 Hermes 点「申论复盘」，选这份交卷发送，就开始评分和点评。`);
      load();
    } catch (e) {
      setNotice(e.message || '交卷失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={fullscreen ? 'flex h-full min-h-0 flex-col bg-white' : 'space-y-4'}>
      <div className={`flex flex-wrap items-center gap-2 ${fullscreen ? 'shrink-0 border-b border-black/5 px-3 py-2' : 'gap-3'}`}>
        <button type="button" onClick={onBack} className="flex min-h-10 items-center gap-1 text-sm font-black text-[#6b5428]">
          <ArrowLeft size={16} /> 试卷列表
        </button>
        <p className="min-w-0 flex-1 truncate text-sm font-black text-[#1a1a1a]">{paper.title}</p>
        <FullscreenButtons fullscreen={fullscreen} onToggleFullscreen={toggleFullscreen} />
        {fullscreen && (
          <button
            type="button"
            onClick={() => setShowQuestion((v) => !v)}
            className={`flex min-h-10 items-center rounded-xl px-3 py-2 text-sm font-black ${
              showQuestion ? 'bg-[#1a1a1a] text-white' : 'border border-[#e8d5b0] bg-white text-[#1a1a1a]'
            }`}
          >
            {showQuestion ? '看材料' : '题目'}
          </button>
        )}
        <button
          type="button"
          onClick={() => setTimer((s) => ({ ...s, running: !s.running }))}
          className="flex min-h-10 items-center gap-1.5 rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm font-black text-[#1a1a1a]"
          title="整套计时"
        >
          {timer.running ? <Pause size={14} /> : <Play size={14} />}
          <Clock size={14} /> {fmtClock(timer.elapsed)}
          {paper.time_limit_min ? <span className="text-xs font-bold text-[#888]">/ {paper.time_limit_min} 分钟</span> : null}
        </button>
        <button
          type="button"
          disabled={submitting || !drafted.length}
          onClick={submit}
          className="flex min-h-10 items-center gap-1.5 rounded-xl bg-[#1a1a1a] px-4 py-2 text-sm font-black text-white disabled:opacity-40"
        >
          {submitting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          交卷（{drafted.length}/{paper.questions.length} 题）
        </button>
      </div>
      {notice && (
        <p className={`flex items-start gap-2 bg-[#f4e6c8] px-4 py-3 text-sm font-bold text-[#6b5428] ${fullscreen ? 'shrink-0' : 'rounded-2xl'}`}>
          {notice.startsWith('已交卷') ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <AlertTriangle size={16} className="mt-0.5 shrink-0" />}
          {notice}
        </p>
      )}
      {!fullscreen && <Submissions submissions={paper.submissions} />}
      <div className={`flex gap-2 ${fullscreen ? 'shrink-0 overflow-x-auto px-3 py-2 [scrollbar-width:none]' : 'flex-wrap'}`}>
        {paper.questions.map((q) => (
          <button
            key={q.id}
            type="button"
            onClick={() => setCurrent(q.id)}
            className={`shrink-0 rounded-2xl border px-4 py-2.5 text-sm font-black ${
              q.id === current ? 'border-[#1a1a1a] bg-[#1a1a1a] text-white' : 'border-[#e8d5b0] bg-white text-[#1a1a1a]'
            }`}
          >
            {q.no}. {q.qtype}
            <span className="ml-2 text-xs font-bold opacity-70">
              {q.draft?.images?.length ? `${q.draft.images.length} 张` : q.last_graded ? `${q.last_graded.score}/${q.last_graded.max_score}` : `${q.requirements.score}分`}
            </span>
          </button>
        ))}
      </div>
      {fullscreen ? (
        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-4 py-4 sm:px-8"
          style={{ paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))' }}
        >
          {showQuestion ? (
            <div className="mx-auto max-w-3xl space-y-4">
              <Submissions submissions={paper.submissions} />
              {active && <QuestionPanel key={active.id} questionId={active.id} onChanged={load} />}
            </div>
          ) : (
            <MaterialsView paper={paper} scope={scope} reading />
          )}
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="max-h-[calc(100vh-220px)] overflow-y-auto rounded-3xl border border-[#e8d5b0] bg-white p-5 lg:sticky lg:top-0">
            <MaterialsView paper={paper} scope={scope} />
          </div>
          <div className="order-first lg:order-none">
            {active && <QuestionPanel key={active.id} questionId={active.id} onChanged={load} />}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ShenlunHome({ fullscreen = false, onToggleFullscreen }) {
  const [paperId, setPaperId] = useState(null);
  return paperId
    ? (
      <PaperView
        key={paperId}
        paperId={paperId}
        onBack={() => setPaperId(null)}
        fullscreen={fullscreen}
        onToggleFullscreen={onToggleFullscreen}
      />
    )
    : <PaperList onOpen={setPaperId} fullscreen={fullscreen} onToggleFullscreen={onToggleFullscreen} />;
}

// 录屏复盘：上传一场真题或套题的录屏和答案 PDF，后台跑完给出行为画像。
// 这一页不做对话，只管上传和看结果 —— 想追问就去 Hermes，那边能带上这份复盘。
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Upload, FileVideo, FileText, Trash2, RefreshCw, ChevronRight, ChevronLeft,
  Loader2, CheckCircle2, AlertCircle, HardDrive, Clock, X,
} from 'lucide-react';
import { api, getToken } from '../api.js';
import MarkdownMessage from '../hermes/MarkdownMessage.jsx';

const POLL_MS = 4000;

const fmtBytes = (n) => {
  if (!n) return '—';
  if (n >= 1 << 30) return `${(n / (1 << 30)).toFixed(1)} GB`;
  if (n >= 1 << 20) return `${(n / (1 << 20)).toFixed(0)} MB`;
  return `${(n / 1024).toFixed(0)} KB`;
};
const fmtLeft = (s) => {
  if (!s || !Number.isFinite(s)) return '—';
  const m = Math.ceil(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)} 小时 ${m % 60} 分` : m > 0 ? `${m} 分钟` : '不到 1 分钟';
};

const fmtDur = (s) => {
  if (!s) return '—';
  const m = Math.round(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)} 小时 ${m % 60} 分` : `${m} 分钟`;
};

const STATUS = {
  queued: { label: '排队中', color: '#94a3b8', icon: Clock },
  running: { label: '处理中', color: '#8d7348', icon: Loader2 },
  done: { label: '已完成', color: '#22c55e', icon: CheckCircle2 },
  failed: { label: '失败', color: '#ff6b6b', icon: AlertCircle },
};

const KINDS = {
  zhenti: {
    label: '真题',
    title: '真题复盘',
    desc: '传一场模考的屏幕录像和带答案的 PDF，后台会把你的做题过程拆出来：时间花在哪、哪些动作是白费的、哪些题慢而且还错。跑完想追问就去 Hermes 带上这份复盘。',
    placeholder: '标题，例如：粉笔周模考 12 季',
    fallbackTitle: (d) => `模考复盘 ${d}`,
    empty: '还没有复盘记录',
  },
  taoti: {
    label: '套题',
    title: '套题解析',
    desc: '传一套练习题的屏幕录像和带答案的 PDF，后台会把你的做题过程拆出来：时间花在哪、哪些动作是白费的、哪些题慢而且还错。跑完想追问就去 Hermes 带上这份复盘。',
    placeholder: '标题，例如：华图行测 第 8 套',
    fallbackTitle: (d) => `套题复盘 ${d}`,
    empty: '还没有套题复盘记录',
  },
  test: {
    label: '测试',
    title: '测试样本',
    desc: '只把录屏和答案 PDF 存到本机，不分析、不切片、不删原片。用来试去音轨、不切片上传这些通路。',
    placeholder: '标题，例如：去音轨试验 1',
    fallbackTitle: (d) => `测试样本 ${d}`,
    empty: '还没有测试样本',
  },
};

// fetch 拿不到上传进度，几个 G 的录屏没有进度条没法用，所以这里退回 XHR
const uploadWithProgress = (url, form, onProgress) =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.setRequestHeader('Authorization', `Bearer ${getToken()}`);
    const t0 = Date.now();
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const sec = (Date.now() - t0) / 1000;
      const rate = sec > 0 ? e.loaded / sec : 0;
      onProgress(
        Math.round((e.loaded / e.total) * 100),
        rate,
        rate > 0 ? (e.total - e.loaded) / rate : 0,
      );
    };
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body.error || `上传失败（HTTP ${xhr.status}）`));
    };
    xhr.onerror = () => reject(new Error('网络中断'));
    xhr.send(form);
  });

// 原生 <input type="file"> 会自带「选择文件 / 未选择文件」两段浏览器文案，
// 样式改不动、选中后还跟自定义的文件名重复。这里把 input 藏进 label，
// 外面自己画一个既能点也能拖的区域。
const FilePicker = ({ label, hint, icon: Icon, accept, file, onPick, required, accent }) => {
  const [over, setOver] = useState(false);
  const inputRef = useRef(null);

  const onDrop = (e) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) onPick(f);
  };

  return (
    <div>
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
        {label}
        <span className={required ? 'text-[#ff6b6b]' : 'text-slate-300'}>{required ? ' 必填' : ' 建议传'}</span>
      </span>

      <label
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={`mt-2 flex items-center gap-3 px-4 py-3.5 rounded-2xl border-2 border-dashed cursor-pointer transition-all ${
          over
            ? 'border-[#6b5428] bg-[#2c261c]/10'
            : file
              ? 'border-transparent bg-[#1a1a1a] text-white'
              : 'border-[#e6e3da] bg-[#f9f8f6] hover:border-[#6b5428] hover:bg-[#2c261c]/[0.06]'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="sr-only"
          onChange={(e) => onPick(e.target.files?.[0] || null)}
        />
        <span
          className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
            file ? 'bg-[#2c261c] text-white' : accent ? 'bg-[#1a1a1a] text-white' : 'bg-white text-slate-400 border border-[#eee]'
          }`}
        >
          <Icon size={16} />
        </span>

        {file ? (
          <>
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-black truncate">{file.name}</span>
              <span className="block text-[10px] font-bold text-white/50 tabular-nums">{fmtBytes(file.size)}</span>
            </span>
            <button
              type="button"
              onClick={(e) => { e.preventDefault(); onPick(null); if (inputRef.current) inputRef.current.value = ''; }}
              title="移除"
              className="shrink-0 p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10"
            >
              <X size={14} />
            </button>
          </>
        ) : (
          <span className="min-w-0">
            <span className="block text-xs font-bold text-[#1a1a1a]">点击选择，或把文件拖进来</span>
            <span className="block text-[10px] font-bold text-slate-400">{hint}</span>
          </span>
        )}
      </label>
    </div>
  );
};

const KIND_KEY = 'examReviewKind';
const readKind = () => {
  try {
    const k = localStorage.getItem(KIND_KEY);
    return k === 'taoti' || k === 'test' ? k : 'zhenti';
  } catch { return 'zhenti'; }
};
const writeKind = (k) => {
  try { localStorage.setItem(KIND_KEY, k); } catch { /* ignore */ }
};

const ExamReview = () => {
  const [kind, setKind] = useState(readKind);
  const pickKind = (k) => { setKind(k); writeKind(k); };
  const [list, setList] = useState([]);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState('');
  const [video, setVideo] = useState(null);
  const [pdf, setPdf] = useState(null);
  const [title, setTitle] = useState('');
  const [examDate, setExamDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [uploading, setUploading] = useState(false);
  const [upPct, setUpPct] = useState(0);
  const [upRate, setUpRate] = useState(0);   // 字节/秒
  const [upLeft, setUpLeft] = useState(0);   // 剩余秒数

  const load = useCallback(async () => {
    try {
      setList(await api(kind === 'test' ? '/api/exam-test' : '/api/exam-analyses'));
      setErr('');
    } catch (e) {
      setErr(e?.message || '读取失败');
    }
  }, [kind]);

  useEffect(() => {
    const run = () => { void load(); };
    const first = setTimeout(run, 0);
    const t = setInterval(run, POLL_MS);
    return () => { clearTimeout(first); clearInterval(t); };
  }, [load]);

  const submit = async () => {
    if (!video) return;
    setUploading(true);
    setUpPct(0);
    setErr('');
    try {
      const form = new FormData();
      form.append('video', video);
      if (pdf) form.append('pdf', pdf);
      form.append('title', title.trim() || KINDS[kind].fallbackTitle(examDate));
      form.append('exam_date', examDate);
      if (kind !== 'test') form.append('kind', kind);
      await uploadWithProgress(
        kind === 'test' ? '/api/exam-test' : '/api/exam-analyses',
        form,
        (pct, rate, left) => {
          setUpPct(pct); setUpRate(rate); setUpLeft(left);
        },
      );
      setVideo(null); setPdf(null); setTitle('');
      writeKind(kind);
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setUploading(false);
      setUpPct(0); setUpRate(0); setUpLeft(0);
    }
  };

  const openDetail = async (id) => {
    try {
      setDetail(await api(`/api/exam-analyses/${id}`));
    } catch (e) {
      setErr(e?.message || '打开失败');
    }
  };

  const act = async (id, path, method = 'POST', confirmText) => {
    if (confirmText && !confirm(confirmText)) return;
    try {
      const base = kind === 'test' ? '/api/exam-test' : '/api/exam-analyses';
      await api(`${base}/${id}${path}`, { method });
      await load();
      if (detail?.id === id) setDetail(null);
    } catch (e) {
      setErr(e?.message || '操作失败');
    }
  };

  // ---------------- 详情 ----------------
  if (detail) {
    const md = detail.result?.markdown;
    const stats = detail.result?.stats;
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <button
          onClick={() => setDetail(null)}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">返回列表</span>
        </button>

        <div className="bg-[#1a1a1a] text-white rounded-[2rem] p-8">
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[#6b5428]">
            {(KINDS[detail.kind] || KINDS.zhenti).title}
          </p>
          <h2 className="text-2xl font-black italic mt-1">{detail.title}</h2>
          <div className="flex flex-wrap gap-x-8 gap-y-2 mt-5 text-xs font-bold text-white/60">
            <span>{detail.exam_date}</span>
            <span>全程 {fmtDur(detail.duration_sec)}</span>
            {stats?.questions ? <span>识别 {stats.questions} 道题</span> : null}
            {stats?.changed ? <span>改过答案 {stats.changed} 题</span> : null}
            {stats?.idle_count ? <span>停滞片段 {stats.idle_count} 处</span> : null}
          </div>
          {stats?.slowest?.length > 0 && (
            <div className="mt-5 pt-4 border-t border-white/10">
              <p className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-2">最花时间的题</p>
              <div className="flex flex-wrap gap-2">
                {stats.slowest.map((q) => (
                  <span key={q.number} className="px-2.5 py-1 rounded-full bg-white/10 text-[11px] font-bold tabular-nums">
                    第 {q.number} 题 · {Math.round(q.sec)}s
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {md ? (
          <div className="bg-white rounded-[2rem] border border-[#e8d5b0] p-8">
            <MarkdownMessage content={md} />
          </div>
        ) : (
          <div className="bg-white rounded-[2rem] border border-[#e8d5b0] p-10 text-center">
            <p className="text-sm font-bold text-slate-400">
              {detail.status === 'failed' ? detail.error : '还在处理，稍后回来看'}
            </p>
          </div>
        )}
      </div>
    );
  }

  // ---------------- 列表 ----------------
  const shown = kind === 'test' ? list : list.filter((r) => (r.kind || 'zhenti') === kind);
  const isTest = kind === 'test';

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <div className="flex gap-2 mb-4">
          {Object.keys(KINDS).map((k) => (
            <button
              key={k}
              type="button"
              disabled={uploading}
              onClick={() => { pickKind(k); setDetail(null); }}
              className={`px-5 py-2.5 rounded-full text-sm font-black tracking-tight transition-all disabled:opacity-40 ${
                kind === k
                  ? 'bg-[#1a1a1a] text-white shadow-lg shadow-black/10'
                  : 'bg-white/60 text-[#666] hover:bg-white/90 hover:text-black'
              }`}
            >
              {KINDS[k].label}
            </button>
          ))}
        </div>
        <h2 className="text-4xl font-black tracking-tighter italic uppercase">{KINDS[kind].title}</h2>
        <p className="text-sm font-medium text-slate-400 mt-2">
          {KINDS[kind].desc}
        </p>
      </div>

      {/* 上传区 */}
      <div className="bg-white rounded-[2rem] border border-[#e8d5b0] p-8 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FilePicker
            label="屏幕录像" required accent icon={FileVideo}
            hint="iPad 相册里的屏幕录制可直接选，MP4 / MOV / M4V"
            accept="video/*"
            file={video} onPick={setVideo}
          />
          <FilePicker
            label="答案 PDF" icon={FileText}
            hint="有答案才能判断哪些题做错了"
            accept="application/pdf,.pdf"
            file={pdf} onPick={setPdf}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder={KINDS[kind].placeholder}
            className="md:col-span-2 bg-[#e8d5b0]/60 rounded-2xl py-3 px-4 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-[#6b5428]"
          />
          <input
            type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)}
            className="bg-[#e8d5b0]/60 rounded-2xl py-3 px-4 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-[#6b5428]"
          />
        </div>

        {uploading && (
          <div>
            <div className="flex justify-between text-[11px] font-black mb-1">
              <span className="text-slate-500">
                正在上传，别切走这个页面
                {upRate > 0 && (
                  <span className="ml-2 font-bold text-slate-400 tabular-nums">
                    {fmtBytes(upRate)}/s · 约剩 {fmtLeft(upLeft)}
                  </span>
                )}
              </span>
              <span className="tabular-nums text-[#6b5428]">{upPct}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-black/[0.07] overflow-hidden">
              <div className="h-full rounded-full bg-[#2c261c] transition-all" style={{ width: `${upPct}%` }} />
            </div>
          </div>
        )}

        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold text-slate-400 leading-relaxed">
            {isTest
              ? '原片和 PDF 会留在本机 data/exam-test，不跑复盘、不切片、不删。盘现在不多，传完用完记得删。'
              : '录屏按 10 分钟无损切开再分析，画质不降。答案 PDF 原件给模型读。原件分析完立刻删除。'}
            {video && video.size > 1.5 * 1024 * 1024 * 1024 && (
              <span className="block text-[#8a5400]">
                这个文件 {fmtBytes(video.size)}，按家宽上行 30~50 Mbps 估算要传
                {Math.ceil((video.size * 8) / (40 * 1000 * 1000) / 60)} 分钟上下；
                上传期间别锁屏、别切走标签页，中断了得从头再来。
              </span>
            )}
          </p>
          <button
            onClick={submit} disabled={!video || uploading}
            className="flex items-center space-x-2 px-5 py-3 rounded-2xl bg-[#1a1a1a] text-white font-black text-xs uppercase tracking-widest hover:bg-[#2c261c] hover:text-white transition-all disabled:opacity-30 disabled:hover:bg-[#1a1a1a] disabled:hover:text-white"
          >
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            <span>{uploading ? '上传中' : isTest ? '保存样本' : '开始处理'}</span>
          </button>
        </div>
      </div>

      {err && (
        <div className="flex items-start justify-between px-4 py-3 rounded-2xl bg-[#fff4e5] border border-[#ffa726]/30 text-[12px] font-bold text-[#8a5400]">
          <span className="pr-3">{err}</span>
          <button onClick={() => setErr('')}><X size={14} /></button>
        </div>
      )}

      {/* 任务列表 */}
      <div className="space-y-3">
        {shown.length === 0 && (
          <div className="bg-white rounded-[2rem] border border-[#e8d5b0] p-14 text-center">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-[#e8d5b0] flex items-center justify-center mb-3 text-slate-400">
              <FileVideo size={24} />
            </div>
            <p className="text-sm font-bold text-slate-400">{KINDS[kind].empty}</p>
          </div>
        )}

        {shown.map((r) => {
          if (isTest) {
            return (
              <div key={r.id} className="bg-white rounded-[1.75rem] border border-[#e8d5b0] p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="text-base font-black italic truncate">{r.title}</div>
                    <div className="flex flex-wrap gap-x-5 gap-y-1 mt-1.5 text-[11px] font-bold text-slate-400">
                      <span>{(r.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                      <span>{fmtDur(r.duration_sec)}</span>
                      <span className="flex items-center space-x-1">
                        <HardDrive size={10} />
                        <span>{fmtBytes(r.video_bytes)}</span>
                      </span>
                      <span>{r.has_audio ? '有音轨' : r.has_audio === false ? '无音轨' : '音轨未知'}</span>
                      {r.pdf_file && <span>含答案 PDF · {fmtBytes(r.pdf_bytes)}</span>}
                    </div>
                  </div>
                  <button
                    onClick={() => act(r.id, '', 'DELETE', '删掉这份测试样本？原片和 PDF 都会去掉。')}
                    title="删除样本"
                    className="p-1.5 rounded-lg text-slate-400 hover:bg-[#ff6b6b]/10 hover:text-[#ff6b6b]">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            );
          }
          const st = STATUS[r.status] || STATUS.queued;
          const Icon = st.icon;
          const busy = r.status === 'queued' || r.status === 'running';
          return (
            <div key={r.id} className="bg-white rounded-[1.75rem] border border-[#e8d5b0] p-6">
              <div className="flex items-start justify-between gap-4">
                <button onClick={() => openDetail(r.id)} className="flex-1 min-w-0 text-left group">
                  <div className="flex items-center space-x-2">
                    <span className="text-base font-black italic truncate group-hover:text-white transition-colors">
                      {r.title}
                    </span>
                    <ChevronRight size={15} className="text-slate-300 group-hover:translate-x-0.5 transition-transform shrink-0" />
                  </div>
                  <div className="flex flex-wrap gap-x-5 gap-y-1 mt-1.5 text-[11px] font-bold text-slate-400">
                    <span>{r.exam_date}</span>
                    <span>{fmtDur(r.duration_sec)}</span>
                    <span className="flex items-center space-x-1">
                      <HardDrive size={10} />
                      <span>{r.video_deleted ? '录屏已删' : fmtBytes(r.video_bytes || r.raw_bytes)}</span>
                    </span>
                    {r.pdf_file && <span>含答案 PDF</span>}
                  </div>
                </button>

                <div className="flex items-center space-x-1 shrink-0">
                  <span
                    className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-[10px] font-black"
                    style={{ backgroundColor: `${st.color}1a`, color: st.color }}
                  >
                    <Icon size={11} className={r.status === 'running' ? 'animate-spin' : ''} />
                    <span>{st.label}</span>
                  </span>
                  {r.status === 'failed' && (
                    <button onClick={() => act(r.id, '/retry')} title="重新分析"
                      className="p-1.5 rounded-lg text-slate-400 hover:bg-black/5 hover:text-[#1a1a1a]">
                      <RefreshCw size={13} />
                    </button>
                  )}
                  {r.status === 'done' && !r.video_deleted && (
                    <button
                      onClick={() => act(r.id, '/video', 'DELETE', '删掉这场的录屏文件？分析结果会保留。')}
                      title="删除录屏省空间"
                      className="p-1.5 rounded-lg text-slate-400 hover:bg-black/5 hover:text-[#1a1a1a]">
                      <HardDrive size={13} />
                    </button>
                  )}
                  <button
                    onClick={() => act(r.id, '', 'DELETE', '连同分析结果一起删除？不可恢复。')}
                    title="删除整条记录"
                    className="p-1.5 rounded-lg text-slate-400 hover:bg-[#ff6b6b]/10 hover:text-[#ff6b6b]">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              {busy && (
                <div className="mt-4">
                  <div className="flex justify-between text-[11px] font-bold mb-1">
                    <span className="text-slate-500">{r.stage || '处理中'}</span>
                    <span className="tabular-nums text-slate-400">{r.progress || 0}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-black/[0.06] overflow-hidden">
                    <div className="h-full rounded-full bg-[#2c261c] transition-all duration-700"
                      style={{ width: `${r.progress || 0}%` }} />
                  </div>
                </div>
              )}

              {r.status === 'failed' && r.error && (
                <p className="mt-3 text-[11px] font-bold text-[#ff6b6b]">{r.error}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ExamReview;

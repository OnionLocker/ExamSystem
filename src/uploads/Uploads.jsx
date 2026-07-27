import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload, FileText, Trash2, Download, Folder, RefreshCw } from 'lucide-react';
import { getToken } from '../api.js';

const TYPES = [
  { key: 'pdf', label: 'PDF 原卷' },
  { key: '解析', label: '解析' },
];

const fmtSize = (n) => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

// 带 token 的请求（multipart / blob 不能走默认 json 封装）
const authHeaders = () => {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

const Uploads = () => {
  const [today, setToday] = useState('');
  const [dates, setDates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [type, setType] = useState('pdf');
  const [msg, setMsg] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/uploads', { headers: authHeaders() });
      const data = await res.json();
      setToday(data.today || '');
      setDates(data.dates || []);
    } catch {
      setMsg('加载列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const doUpload = useCallback(
    async (files) => {
      const list = Array.from(files || []).filter(
        (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'),
      );
      if (!list.length) {
        setMsg('请选择 PDF 文件');
        return;
      }
      setUploading(true);
      setMsg('');
      try {
        for (const file of list) {
          const fd = new FormData();
          fd.append('type', type);
          fd.append('file', file);
          const res = await fetch('/api/uploads', {
            method: 'POST',
            headers: authHeaders(),
            body: fd,
          });
          if (!res.ok) {
            const e = await res.json().catch(() => ({}));
            throw new Error(e.error || `上传失败 (${res.status})`);
          }
        }
        setMsg(`已上传 ${list.length} 个文件到「${today}/${type}」`);
        await load();
      } catch (err) {
        setMsg(err.message || '上传失败');
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [type, today, load],
  );

  const openFile = useCallback(async (date, t, name) => {
    try {
      const q = new URLSearchParams({ date, type: t, name }).toString();
      const res = await fetch(`/api/uploads/file?${q}`, { headers: authHeaders() });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      setMsg('无法打开文件');
    }
  }, []);

  const removeFile = useCallback(
    async (date, t, name) => {
      if (!window.confirm(`确认删除 ${name} ？`)) return;
      try {
        const q = new URLSearchParams({ date, type: t, name }).toString();
        const res = await fetch(`/api/uploads/file?${q}`, {
          method: 'DELETE',
          headers: authHeaders(),
        });
        if (!res.ok) throw new Error();
        await load();
      } catch {
        setMsg('删除失败');
      }
    },
    [load],
  );

  return (
    <div className="space-y-8">
      {/* 上传区 */}
      <div className="bg-white rounded-[2rem] p-8 shadow-sm border border-black/5">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-black">上传资料</h3>
            <p className="text-sm text-slate-400 font-medium">
              按北京时间自动归档到{' '}
              <span className="font-bold text-[#1a1a1a]">data/uploads/{today || '……'}/{type}</span>
            </p>
          </div>
          <button
            onClick={load}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest text-slate-500 hover:bg-black/5"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 刷新
          </button>
        </div>

        {/* 类型选择 */}
        <div className="flex gap-2 mb-5">
          {TYPES.map((t) => (
            <button
              key={t.key}
              onClick={() => setType(t.key)}
              className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${
                type === t.key
                  ? 'bg-[#1a1a1a] text-[#fbc02d]'
                  : 'bg-[#f2f0e9] text-slate-500 hover:bg-black/5'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* 拖拽/点击上传 */}
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            doUpload(e.dataTransfer.files);
          }}
          className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all ${
            dragOver ? 'border-[#fbc02d] bg-[#fbc02d]/10' : 'border-black/10 hover:border-black/20'
          }`}
        >
          <Upload size={32} className="mx-auto mb-3 text-slate-400" />
          <p className="font-bold text-sm">
            {uploading ? '上传中…' : '点击选择或拖拽 PDF 到此处'}
          </p>
          <p className="text-xs text-slate-400 mt-1">支持多选，单文件最大 100MB</p>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            className="hidden"
            onChange={(e) => doUpload(e.target.files)}
          />
        </div>

        {msg && <p className="mt-4 text-sm font-bold text-[#1a1a1a]">{msg}</p>}
      </div>

      {/* 文件列表 */}
      <div className="space-y-6">
        {dates.length === 0 && !loading && (
          <p className="text-center text-slate-400 font-medium py-10">还没有上传任何资料</p>
        )}
        {dates.map((d) => (
          <div key={d.date} className="bg-white rounded-[2rem] p-6 shadow-sm border border-black/5">
            <div className="flex items-center gap-2 mb-4">
              <Folder size={18} className="text-[#fbc02d]" />
              <h4 className="font-black text-base">{d.date}</h4>
              {d.date === today && (
                <span className="px-2 py-0.5 rounded-full bg-[#fbc02d] text-[#1a1a1a] text-[10px] font-black uppercase">
                  今天
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {TYPES.map((t) => (
                <div key={t.key}>
                  <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">
                    {t.label}（{(d[t.key] || []).length}）
                  </p>
                  <div className="space-y-2">
                    {(d[t.key] || []).length === 0 && (
                      <p className="text-xs text-slate-300 italic">空</p>
                    )}
                    {(d[t.key] || []).map((f) => (
                      <div
                        key={f.name}
                        className="flex items-center gap-3 px-3 py-2 rounded-xl bg-[#f2f0e9] group"
                      >
                        <FileText size={16} className="text-[#ff6b6b] shrink-0" />
                        <button
                          onClick={() => openFile(d.date, t.key, f.name)}
                          className="flex-1 text-left text-sm font-bold truncate hover:underline"
                          title={f.name}
                        >
                          {f.name}
                        </button>
                        <span className="text-[10px] text-slate-400 font-bold shrink-0">
                          {fmtSize(f.size)}
                        </span>
                        <button
                          onClick={() => openFile(d.date, t.key, f.name)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-[#1a1a1a] hover:bg-black/5"
                          title="打开"
                        >
                          <Download size={14} />
                        </button>
                        <button
                          onClick={() => removeFile(d.date, t.key, f.name)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-[#ff6b6b] hover:bg-[#ff6b6b]/10"
                          title="删除"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Uploads;

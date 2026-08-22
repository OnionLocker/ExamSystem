import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload, FileText, Trash2, Download, Folder, FolderPlus, RefreshCw, Plus, MessageSquare } from 'lucide-react';
import { getToken } from '../api.js';

const TYPES = [
  { key: 'pdf', label: 'PDF 原卷' },
  { key: '解析', label: '解析' },
];

const EXT_MIME = {
  '.pdf': 'application/pdf',
  '.doc': 'application/msword',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};
const MIME_EXT = Object.fromEntries(Object.entries(EXT_MIME).map(([ext, mime]) => [mime, ext]));
const FILE_ACCEPT = Object.entries(EXT_MIME).flatMap(([ext, mime]) => [mime, ext]).join(',');
const isIOS =
  typeof navigator !== 'undefined' &&
  (/iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));

const extOfName = (name) => {
  const m = String(name || '').toLowerCase().match(/\.(pdf|docx|doc)$/);
  return m ? `.${m[1]}` : '';
};

const sniffExt = async (file) => {
  const named = extOfName(file.name);
  if (named) return named;
  if (MIME_EXT[file.type]) return MIME_EXT[file.type];
  const buf = new Uint8Array(await file.slice(0, 5).arrayBuffer());
  if (buf[0] === 0x25 && buf[1] === 0x50 && buf[2] === 0x44 && buf[3] === 0x46) return '.pdf';
  if (buf[0] === 0xd0 && buf[1] === 0xcf && buf[2] === 0x11 && buf[3] === 0xe0) return '.doc';
  if (buf[0] === 0x50 && buf[1] === 0x4b) return '.docx';
  return '';
};

const asNamedFile = async (file) => {
  const ext = await sniffExt(file);
  if (!ext) return null;
  const mime = (file.type && file.type !== 'application/octet-stream') ? file.type : EXT_MIME[ext];
  if (extOfName(file.name) === ext) {
    return file.type === mime ? file : new File([file], file.name, { type: mime });
  }
  const stem = String(file.name || '微信文件').replace(/\.[^.]*$/, '').trim() || '微信文件';
  return new File([file], `${stem}${ext}`, { type: mime });
};

const fmtSize = (n) => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

const authHeaders = () => {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

const Uploads = ({ onReviewWithHermes }) => {
  const [mode, setMode] = useState('daily'); // daily | exam
  const [today, setToday] = useState('');
  const [dates, setDates] = useState([]);
  const [folders, setFolders] = useState([]);
  const [folder, setFolder] = useState('');
  const [newFolder, setNewFolder] = useState('');
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [type, setType] = useState('pdf');
  const [msg, setMsg] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const fetchDaily = useCallback(async () => {
    try {
      const res = await fetch('/api/uploads', { headers: authHeaders() });
      const data = await res.json();
      return { today: data.today || '', dates: data.dates || [] };
    } catch {
      return { error: '加载列表失败' };
    }
  }, []);

  const fetchExam = useCallback(async () => {
    try {
      const res = await fetch('/api/uploads/exam', { headers: authHeaders() });
      const data = await res.json();
      return { folders: data.folders || [] };
    } catch {
      return { error: '加载真题文件夹失败' };
    }
  }, []);

  const applyDaily = useCallback((data) => {
    if (data.error) setMsg(data.error);
    else {
      setToday(data.today);
      setDates(data.dates);
    }
    setLoading(false);
  }, []);

  const applyExam = useCallback((data) => {
    if (data.error) setMsg(data.error);
    else {
      setFolders(data.folders);
      setFolder((cur) => {
        if (cur && data.folders.some((f) => f.name === cur)) return cur;
        return data.folders[0]?.name || '';
      });
    }
    setLoading(false);
  }, []);

  const load = useCallback(async () => {
    setMsg('');
    if (mode === 'daily') applyDaily(await fetchDaily());
    else applyExam(await fetchExam());
  }, [mode, fetchDaily, fetchExam, applyDaily, applyExam]);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (mode === 'daily') {
        const data = await fetchDaily();
        if (alive) applyDaily(data);
      } else {
        const data = await fetchExam();
        if (alive) applyExam(data);
      }
    })();
    return () => {
      alive = false;
    };
  }, [mode, fetchDaily, fetchExam, applyDaily, applyExam]);

  const createFolder = async () => {
    const name = newFolder.trim();
    if (!name) {
      setMsg('请输入文件夹名');
      return;
    }
    setCreating(true);
    setMsg('');
    try {
      const res = await fetch('/api/uploads/exam/folders', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || '创建失败');
      setNewFolder('');
      setFolder(name);
      await load();
      setMsg(`已创建文件夹「${name}」`);
    } catch (err) {
      setMsg(err.message || '创建失败');
    } finally {
      setCreating(false);
    }
  };

  const removeFolder = async (name) => {
    try {
      const q = new URLSearchParams({ name }).toString();
      const res = await fetch(`/api/uploads/exam/folders?${q}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || '删除失败');
      if (folder === name) setFolder('');
      await load();
    } catch (err) {
      setMsg(err.message || '删除失败');
    }
  };

  const doUpload = useCallback(
    async (files) => {
      const list = [];
      for (const f of Array.from(files || [])) {
        const named = await asNamedFile(f);
        if (named) list.push(named);
      }
      if (!list.length) {
        setMsg(isIOS
          ? '没认到 PDF / Word。请点「浏览」→ 左侧选「微信」，不要走相册。'
          : '请选择 PDF 或 Word 文件');
        return;
      }
      if (mode === 'exam' && !folder) {
        setMsg('请先创建或选择一个真题文件夹');
        return;
      }
      setUploading(true);
      setMsg('');
      try {
        for (const file of list) {
          const fd = new FormData();
          if (mode === 'exam') fd.append('folder', folder);
          else fd.append('type', type);
          fd.append('file', file);
          const url = mode === 'exam' ? '/api/uploads/exam' : '/api/uploads';
          const res = await fetch(url, {
            method: 'POST',
            headers: authHeaders(),
            body: fd,
          });
          if (!res.ok) {
            const e = await res.json().catch(() => ({}));
            throw new Error(e.error || `上传失败 (${res.status})`);
          }
        }
        const where = mode === 'exam' ? `真题/${folder}` : `${today}/${type}`;
        setMsg(`已上传 ${list.length} 个文件到「${where}」`);
        await load();
      } catch (err) {
        setMsg(err.message || '上传失败');
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [mode, folder, type, today, load],
  );

  const openDaily = useCallback(async (date, t, name) => {
    try {
      const q = new URLSearchParams({ date, type: t, name }).toString();
      const res = await fetch(`/api/uploads/file?${q}`, { headers: authHeaders() });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (name.toLowerCase().endsWith('.pdf')) window.open(url, '_blank');
      else {
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        a.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      setMsg('无法打开文件');
    }
  }, []);

  const removeDaily = useCallback(
    async (date, t, name) => {
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

  const openExam = useCallback(async (folderName, name) => {
    try {
      const q = new URLSearchParams({ folder: folderName, name }).toString();
      const res = await fetch(`/api/uploads/exam/file?${q}`, { headers: authHeaders() });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (name.toLowerCase().endsWith('.pdf')) window.open(url, '_blank');
      else {
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        a.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      setMsg('无法打开文件');
    }
  }, []);

  const removeExam = useCallback(
    async (folderName, name) => {
      try {
        const q = new URLSearchParams({ folder: folderName, name }).toString();
        const res = await fetch(`/api/uploads/exam/file?${q}`, {
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

  const selected = folders.find((f) => f.name === folder);

  return (
    <div className="space-y-8">
      <div className="flex gap-2">
        {[
          { key: 'daily', label: '日常资料' },
          { key: 'exam', label: '真题' },
        ].map((m) => (
          <button
            key={m.key}
            onClick={() => {
              setMode(m.key);
              setMsg('');
            }}
            className={`px-5 py-2.5 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${
              mode === m.key
                ? 'bg-[#1a1a1a] text-white'
                : 'bg-white border border-black/5 text-slate-500 hover:bg-black/5'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-[2rem] p-8 shadow-sm border border-black/5">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-black">
              {mode === 'exam' ? '上传真题' : '上传资料'}
            </h3>
            <p className="text-sm text-slate-400 font-medium">
              {mode === 'exam' ? (
                <>
                  当前目标{' '}
                  <span className="font-bold text-[#1a1a1a]">
                    data/uploads/真题/{folder || '…'}
                  </span>
                </>
              ) : (
                <>
                  按北京时间自动归档到{' '}
                  <span className="font-bold text-[#1a1a1a]">
                    data/uploads/{today || '…'}/{type}
                  </span>
                </>
              )}
            </p>
          </div>
          <button
            onClick={load}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest text-slate-500 hover:bg-black/5"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 刷新
          </button>
        </div>

        {mode === 'daily' ? (
          <div className="flex gap-2 mb-5">
            {TYPES.map((t) => (
              <button
                key={t.key}
                onClick={() => setType(t.key)}
                className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${
                  type === t.key
                    ? 'bg-[#1a1a1a] text-white'
                    : 'bg-[#e8d5b0] text-slate-500 hover:bg-black/5'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        ) : (
          <div className="mb-5 space-y-3">
            <div className="flex flex-wrap gap-2">
              {folders.length === 0 && (
                <p className="text-xs text-slate-400 font-medium py-2">
                  还没有文件夹，先在下面创一个
                </p>
              )}
              {folders.map((f) => (
                <button
                  key={f.name}
                  onClick={() => setFolder(f.name)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-black transition-all ${
                    folder === f.name
                      ? 'bg-[#1a1a1a] text-white'
                      : 'bg-[#e8d5b0] text-slate-600 hover:bg-black/5'
                  }`}
                >
                  <Folder size={14} />
                  {f.name}
                  <span className="opacity-50">({f.files.length})</span>
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2 flex-1 min-w-[220px]">
                <FolderPlus size={16} className="text-slate-400 shrink-0" />
                <input
                  value={newFolder}
                  onChange={(e) => setNewFolder(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') createFolder();
                  }}
                  placeholder="新文件夹名，如「2023国考」"
                  className="flex-1 h-10 px-3 rounded-xl bg-[#e8d5b0] text-sm font-bold outline-none focus:ring-2 focus:ring-[#6b5428]/40"
                />
              </div>
              <button
                onClick={createFolder}
                disabled={creating}
                className="h-10 px-4 rounded-xl bg-[#1a1a1a] text-white text-xs font-black uppercase tracking-widest flex items-center gap-1.5 disabled:opacity-50"
              >
                <Plus size={14} />
                新建
              </button>
              {folder && (selected?.files.length || 0) === 0 && (
                <button
                  onClick={() => removeFolder(folder)}
                  className="h-10 px-3 rounded-xl text-xs font-black text-slate-400 hover:text-[#ff6b6b] hover:bg-[#ff6b6b]/10"
                  title="删除空文件夹"
                >
                  删除空文件夹
                </button>
              )}
            </div>
          </div>
        )}

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
            dragOver ? 'border-[#6b5428] bg-[#2c261c]/10' : 'border-black/10 hover:border-black/20'
          }`}
        >
          <Upload size={32} className="mx-auto mb-3 text-slate-400" />
          <p className="font-bold text-sm">
            {uploading
              ? '上传中…'
              : mode === 'exam' && !folder
                ? '请先选择或创建文件夹'
                : '点击选择或拖拽 PDF / Word 到此处'}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            {isIOS
              ? '点选后选「浏览」→ 左侧「微信」，可直接挑聊天里的 PDF / Word'
              : '支持 PDF / DOC / DOCX，可多选，单文件最大 100MB'}
          </p>
          <input
            ref={inputRef}
            type="file"
            {...(isIOS ? {} : { accept: FILE_ACCEPT })}
            multiple
            className="hidden"
            onChange={(e) => doUpload(e.target.files)}
          />
        </div>

        {msg && <p className="mt-4 text-sm font-bold text-[#1a1a1a]">{msg}</p>}
      </div>

      <div className="space-y-6">
        {mode === 'daily' && (
          <>
            {dates.length === 0 && !loading && (
              <p className="text-center text-slate-400 font-medium py-10">还没有上传任何资料</p>
            )}
            {dates.map((d) => (
              <div key={d.date} className="bg-white rounded-[2rem] p-6 shadow-sm border border-black/5">
                <div className="flex items-center gap-2 mb-4">
                  <Folder size={18} className="text-[#6b5428]" />
                  <h4 className="font-black text-base">{d.date}</h4>
                  {d.date === today && (
                    <span className="px-2 py-0.5 rounded-full bg-[#2c261c] text-white text-[10px] font-black uppercase">
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
                            className="flex items-center gap-3 px-3 py-2 rounded-xl bg-[#e8d5b0] group"
                          >
                            <FileText size={16} className="text-[#ff6b6b] shrink-0" />
                            <button
                              onClick={() => openDaily(d.date, t.key, f.name)}
                              className="flex-1 text-left text-sm font-bold truncate hover:underline"
                              title={f.name}
                            >
                              {f.name}
                            </button>
                            <span className="text-[10px] text-slate-400 font-bold shrink-0">
                              {fmtSize(f.size)}
                            </span>
                            {onReviewWithHermes && (
                              <button
                                onClick={() => onReviewWithHermes({ date: d.date, type: t.key, name: f.name })}
                                className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-black text-slate-500 hover:text-[#1a1a1a] hover:bg-black/5"
                                title="把这份文件的路径交给 Hermes 复盘"
                              >
                                <MessageSquare size={12} />
                                复盘
                              </button>
                            )}
                            <button
                              onClick={() => openDaily(d.date, t.key, f.name)}
                              className="p-1.5 rounded-lg text-slate-400 hover:text-[#1a1a1a] hover:bg-black/5"
                              title="打开"
                            >
                              <Download size={14} />
                            </button>
                            <button
                              onClick={() => removeDaily(d.date, t.key, f.name)}
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
          </>
        )}

        {mode === 'exam' && (
          <>
            {folders.length === 0 && !loading && (
              <p className="text-center text-slate-400 font-medium py-10">
                还没有真题文件夹，先新建一个
              </p>
            )}
            {folders.map((f) => (
              <div
                key={f.name}
                className={`bg-white rounded-[2rem] p-6 shadow-sm border transition-all ${
                  folder === f.name ? 'border-[#6b5428]' : 'border-black/5'
                }`}
              >
                <div className="flex items-center gap-2 mb-4">
                  <Folder size={18} className="text-[#6b5428]" />
                  <h4 className="font-black text-base">{f.name}</h4>
                  <span className="text-xs text-slate-400 font-bold">{f.files.length} 个文件</span>
                  <button
                    onClick={() => setFolder(f.name)}
                    className="ml-auto text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-[#1a1a1a]"
                  >
                    选为上传目标
                  </button>
                </div>
                <div className="space-y-2">
                  {f.files.length === 0 && (
                    <p className="text-xs text-slate-300 italic">空</p>
                  )}
                  {f.files.map((file) => (
                    <div
                      key={file.name}
                      className="flex items-center gap-3 px-3 py-2 rounded-xl bg-[#e8d5b0]"
                    >
                      <FileText size={16} className="text-[#ff6b6b] shrink-0" />
                      <button
                        onClick={() => openExam(f.name, file.name)}
                        className="flex-1 text-left text-sm font-bold truncate hover:underline"
                        title={file.name}
                      >
                        {file.name}
                      </button>
                      <span className="text-[10px] text-slate-400 font-bold shrink-0">
                        {fmtSize(file.size)}
                      </span>
                      <button
                        onClick={() => openExam(f.name, file.name)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-[#1a1a1a] hover:bg-black/5"
                        title="打开"
                      >
                        <Download size={14} />
                      </button>
                      <button
                        onClick={() => removeExam(f.name, file.name)}
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
          </>
        )}
      </div>
    </div>
  );
};

export default Uploads;

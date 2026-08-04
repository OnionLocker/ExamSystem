import { useCallback, useEffect, useRef, useState } from 'react';
import {
  addEntryOncePerDay,
  hasEntryToday,
  QUALITATIVE,
} from '../studyLog/studyLog.js';
import {
  BookMarked,
  Plus,
  Trash2,
  Upload,
  ChevronLeft,
  ChevronRight,
  Image as ImageIcon,
  Pencil,
  X,
  ArrowLeft,
  Loader2,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Minimize2,
  Search,
} from 'lucide-react';
import { api } from '../api.js';
import {
  dropCachedReviewImage,
  getCachedObjectUrl,
  prefetchModuleImages,
  prefetchReviewImage,
  withReviewToken,
} from './prefetchReviewImages.js';

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 6;
const ZOOM_STEP = 0.25;

const clampZoom = (z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

// ============================================================
// 知识点图片复习
// home（模块列表）→ viewer（模块内翻阅图片）
// ============================================================

const withToken = withReviewToken;

/** 优先用 Cache API 本地缓存，没有则走网络（并触发单张预取） */
const CachedReviewImg = ({ url, ...props }) => {
  const [src, setSrc] = useState(() => withToken(url));

  useEffect(() => {
    let revoked = null;
    let cancelled = false;

    (async () => {
      const cached = await getCachedObjectUrl(url);
      if (cancelled) {
        if (cached) URL.revokeObjectURL(cached);
        return;
      }
      if (cached) {
        revoked = cached;
        setSrc(cached);
        return;
      }
      setSrc(withToken(url));
      prefetchReviewImage(url);
    })();

    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [url]);

  return <img src={src} {...props} />;
};

const fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('读取文件失败'));
    reader.readAsDataURL(file);
  });

// 复习是"翻资料看截图"，没有题数可数，只能按真正停留的时长定性给分。
// 只在页面可见时累计，切到别的标签页或锁屏就停 —— 挂着不算学习。
// 满门槛后当天只记一次，反复进出这个模块不会反复加热。
const useReviewDwell = () => {
  useEffect(() => {
    if (hasEntryToday('reviewBrowse')) return undefined;
    const need = QUALITATIVE.reviewBrowse.minMinutes * 60;
    let seconds = 0;
    const tid = setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      seconds += 1;
      if (seconds < need) return;
      clearInterval(tid);
      addEntryOncePerDay('reviewBrowse', {
        module: QUALITATIVE.reviewBrowse.label,
        minutes: QUALITATIVE.reviewBrowse.minMinutes,
        score: QUALITATIVE.reviewBrowse.score,
      });
    }, 1000);
    return () => clearInterval(tid);
  }, []);
};

const Review = () => {
  useReviewDwell();
  const [modules, setModules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeModule, setActiveModule] = useState(null);

  // 拉取模块列表。返回数据，由调用方决定怎么写状态 —— 这样 effect 里的写入
  // 都发生在 await 之后，不会在 effect 同步体内触发级联渲染。
  const fetchModules = useCallback(async () => {
    try {
      return { rows: (await api('/api/review-modules')) || [], error: '' };
    } catch (e) {
      if (e.status === 401) return null; // 401 由 api 层统一处理，这里静默
      return { rows: null, error: e.message || '加载失败' };
    }
  }, []);

  // 供刷新按钮 / 子组件手动调用
  const loadModules = useCallback(async () => {
    const res = await fetchModules();
    if (!res) return;
    if (res.rows) setModules(res.rows);
    setError(res.error);
    setLoading(false);
  }, [fetchModules]);

  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await fetchModules();
      if (!alive || !res) return;
      if (res.rows) setModules(res.rows);
      setError(res.error);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [fetchModules]);

  if (activeModule) {
    return (
      <ModuleViewer
        module={activeModule}
        onBack={() => {
          setActiveModule(null);
          loadModules();
        }}
        onModuleUpdate={(m) => setActiveModule(m)}
      />
    );
  }

  return (
    <ModuleList
      modules={modules}
      loading={loading}
      error={error}
      onRefresh={loadModules}
      onSelect={setActiveModule}
      onModulesChange={setModules}
    />
  );
};

// ============== 模块列表 ==============
const ModuleList = ({ modules, loading, error, onRefresh, onSelect, onModulesChange }) => {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');

  const createModule = async () => {
    const name = newName.trim();
    if (!name || busy) return;
    setBusy(true);
    try {
      const row = await api('/api/review-modules', { method: 'POST', body: { name } });
      onModulesChange([row, ...modules]);
      setNewName('');
      setCreating(false);
    } catch (e) {
      alert(e.message || '创建失败');
    } finally {
      setBusy(false);
    }
  };

  const renameModule = async (id) => {
    const name = editName.trim();
    if (!name || busy) return;
    setBusy(true);
    try {
      const row = await api(`/api/review-modules/${id}`, { method: 'PUT', body: { name } });
      onModulesChange(modules.map((m) => (m.id === id ? row : m)));
      setEditingId(null);
      setEditName('');
    } catch (e) {
      alert(e.message || '重命名失败');
    } finally {
      setBusy(false);
    }
  };

  const deleteModule = async (m, e) => {
    e.stopPropagation();
    if (!confirm(`确定删除模块「${m.name}」及其全部图片？不可恢复。`)) return;
    setBusy(true);
    try {
      await api(`/api/review-modules/${m.id}`, { method: 'DELETE' });
      onModulesChange(modules.filter((x) => x.id !== m.id));
    } catch (err) {
      alert(err.message || '删除失败');
    } finally {
      setBusy(false);
    }
  };

  const totalImages = modules.reduce((s, m) => s + (m.image_count || 0), 0);

  return (
    <div className="space-y-8">
      <div className="bg-[#1a1a1a] text-white rounded-[2.5rem] p-8 relative overflow-hidden">
        <div className="absolute -top-10 -right-10 w-56 h-56 rounded-full blur-[80px] bg-[#fbc02d] opacity-30 pointer-events-none" />
        <div className="absolute bottom-0 left-1/3 w-40 h-40 rounded-full blur-[70px] bg-[#60a5fa] opacity-20 pointer-events-none" />
        <div className="relative">
          <div className="flex items-center space-x-3 mb-1">
            <BookMarked size={20} className="text-[#fbc02d]" />
            <p className="text-[10px] font-black uppercase tracking-[0.25em] text-white/40">
              Knowledge Review
            </p>
          </div>
          <h2 className="text-3xl font-black italic mt-1">
            复习模块 <span className="text-[#fbc02d]">{modules.length}</span>
          </h2>
          <p className="text-xs font-bold text-white/50 mt-2 max-w-xl leading-relaxed">
            按知识点建模块，上传笔记/截图，进入后左右翻阅巩固记忆。共 {totalImages} 张图片。
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400">我的模块</p>
        <button
          onClick={() => setCreating(true)}
          className="inline-flex items-center space-x-2 bg-[#1a1a1a] text-[#fbc02d] px-5 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-[#fbc02d] hover:text-black transition-all"
        >
          <Plus size={16} />
          <span>新增模块</span>
        </button>
      </div>

      {error && (
        <div className="bg-[#ff6b6b]/10 text-[#ff6b6b] rounded-2xl px-5 py-4 text-sm font-bold flex items-center justify-between">
          <span>{error}</span>
          <button onClick={onRefresh} className="underline">
            重试
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-400">
          <Loader2 className="animate-spin mr-2" size={18} />
          <span className="text-sm font-bold">加载中...</span>
        </div>
      ) : modules.length === 0 ? (
        <div className="bg-white rounded-[2.5rem] border border-[#f2f0e9] p-16 text-center">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-[#f2f0e9] flex items-center justify-center text-slate-400 mb-4">
            <BookMarked size={28} />
          </div>
          <p className="text-lg font-black">还没有复习模块</p>
          <p className="text-sm text-slate-400 font-medium mt-2 mb-6">
            创建一个模块，开始上传知识点图片
          </p>
          <button
            onClick={() => setCreating(true)}
            className="inline-flex items-center space-x-2 bg-[#1a1a1a] text-white px-6 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-[#fbc02d] hover:text-black transition-all"
          >
            <Plus size={16} />
            <span>创建第一个模块</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {modules.map((m) => (
            <div
              key={m.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(m)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelect(m);
                }
              }}
              className="group relative bg-white rounded-3xl p-6 text-left hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer border border-transparent hover:border-[#fbc02d]/30"
            >
              <div className="absolute top-0 left-0 right-0 h-1.5 rounded-t-3xl bg-gradient-to-r from-[#fbc02d] to-[#60a5fa]" />

              <div className="flex items-start justify-between mb-3 gap-2">
                {editingId === m.id ? (
                  <input
                    autoFocus
                    value={editName}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      e.stopPropagation();
                      if (e.key === 'Enter') renameModule(m.id);
                      if (e.key === 'Escape') {
                        setEditingId(null);
                        setEditName('');
                      }
                    }}
                    className="flex-1 bg-[#f2f0e9]/60 rounded-xl px-3 py-2 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
                  />
                ) : (
                  <p className="text-base font-black tracking-tight">{m.name}</p>
                )}
                <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-[#fbc02d]/15 text-[#b8860b] flex-shrink-0">
                  {m.image_count || 0} 张
                </span>
              </div>

              <p className="text-xs text-slate-400 font-medium mb-5">
                更新于 {(m.updated_at || m.created_at || '').slice(0, 16).replace('T', ' ')}
              </p>

              <div className="flex items-center space-x-2" onClick={(e) => e.stopPropagation()}>
                {editingId === m.id ? (
                  <>
                    <button
                      onClick={() => renameModule(m.id)}
                      className="flex-1 py-2 rounded-xl bg-[#1a1a1a] text-white text-[10px] font-black uppercase tracking-widest hover:bg-[#fbc02d] hover:text-black transition-all"
                    >
                      保存
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(null);
                        setEditName('');
                      }}
                      className="px-3 py-2 rounded-xl text-slate-400 hover:bg-[#f2f0e9] text-[10px] font-black"
                    >
                      取消
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => onSelect(m)}
                      className="flex-1 py-2.5 rounded-xl bg-[#f2f0e9] text-[#1a1a1a] text-[10px] font-black uppercase tracking-widest group-hover:bg-[#1a1a1a] group-hover:text-[#fbc02d] transition-all"
                    >
                      进入复习
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(m.id);
                        setEditName(m.name);
                      }}
                      className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-400 hover:bg-[#f2f0e9] hover:text-black transition-colors"
                      title="重命名"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={(e) => deleteModule(m, e)}
                      className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-400 hover:bg-[#ff6b6b]/10 hover:text-[#ff6b6b] transition-colors"
                      title="删除模块"
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {creating && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
          onClick={() => !busy && setCreating(false)}
        >
          <div
            className="bg-white rounded-[2rem] p-8 w-full max-w-sm shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                  新建模块
                </p>
                <p className="text-xl font-black italic">知识点模块</p>
              </div>
              <button
                onClick={() => setCreating(false)}
                className="w-8 h-8 rounded-full bg-[#f2f0e9] hover:bg-[#e8e6dd] flex items-center justify-center"
              >
                <X size={16} />
              </button>
            </div>
            <label className="text-xs font-bold text-slate-400 block mb-2">模块名称</label>
            <input
              type="text"
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') createModule();
                if (e.key === 'Escape') setCreating(false);
              }}
              placeholder="例如：资料分析公式"
              maxLength={80}
              className="w-full bg-[#f2f0e9]/60 border border-transparent rounded-2xl py-4 px-4 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-[#fbc02d] mb-6"
            />
            <button
              onClick={createModule}
              disabled={!newName.trim() || busy}
              className="w-full bg-[#1a1a1a] text-white font-black py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs disabled:opacity-40"
            >
              {busy ? '创建中...' : '创建'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ============== 模块内翻阅 ==============
const ModuleViewer = ({ module, onBack, onModuleUpdate }) => {
  const [images, setImages] = useState([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [renaming, setRenaming] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);
  const nameInputRef = useRef(null);
  const touchStartX = useRef(null);
  // dragenter/dragleave 在子元素间移动会反复触发，用计数器判断是否真正离开
  const dragDepth = useRef(0);

  // 只负责取数，不写状态；写状态交给调用方，保证不在 effect 同步体内 setState
  const fetchImages = useCallback(async () => {
    try {
      return { rows: (await api(`/api/review-modules/${module.id}/images`)) || [] };
    } catch (e) {
      if (e.status === 401) return null;
      return { rows: null, error: e.message || '加载图片失败' };
    }
  }, [module.id]);

  const applyImages = useCallback((res) => {
    if (!res) return;
    if (res.error) alert(res.error);
    if (!res.rows) {
      setLoading(false);
      return;
    }
    setImages(res.rows);
    setIndex((i) => (res.rows.length ? Math.min(i, res.rows.length - 1) : 0));
    setLoading(false);
  }, []);

  // 供上传/删除后手动刷新
  const loadImages = useCallback(async () => {
    applyImages(await fetchImages());
  }, [fetchImages, applyImages]);

  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await fetchImages();
      if (alive) applyImages(res);
    })();
    return () => {
      alive = false;
    };
  }, [fetchImages, applyImages]);

  // 进入模块后后台把本模块图片全部预取进浏览器缓存
  useEffect(() => {
    if (!images.length) return;
    const urls = images.map((img) => img.url).filter(Boolean);
    prefetchModuleImages(urls);
  }, [images]);

  const go = useCallback(
    (delta) => {
      if (!images.length) return;
      setIndex((i) => {
        const next = i + delta;
        if (next < 0) return images.length - 1;
        if (next >= images.length) return 0;
        return next;
      });
    },
    [images.length]
  );

  useEffect(() => {
    const onKey = (e) => {
      // 全屏预览时由 lightbox 接管
      if (lightboxOpen) return;
      // 改名输入框内不拦截方向键
      if (editingName) return;
      if (e.key === 'ArrowLeft') go(-1);
      if (e.key === 'ArrowRight') go(1);
      if (e.key === 'Escape') onBack();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, onBack, editingName, lightboxOpen]);

  // 切图时退出改名态。用"渲染期比对上一次的值"而不是 effect：
  // effect 里同步 setState 会多跑一轮渲染，且改名框会闪一下旧内容。
  const [lastIndex, setLastIndex] = useState(index);
  if (lastIndex !== index) {
    setLastIndex(index);
    setEditingName(false);
    setNameDraft('');
  }

  const handleUpload = async (files) => {
    const all = Array.from(files || []);
    // 拖文件夹进来时会混入非图片文件，按类型 + 扩展名双重过滤
    const isImage = (f) =>
      (f.type && f.type.startsWith('image/')) ||
      /\.(png|jpe?g|gif|webp|bmp|avif)$/i.test(f.name || '');
    const list = all.filter(isImage);
    if (!list.length) {
      alert(all.length ? `这 ${all.length} 个文件里没有图片` : '请选择图片文件');
      return;
    }
    const skipped = all.length - list.length;
    setUploading(true);
    let ok = 0;
    try {
      for (let i = 0; i < list.length; i++) {
        const file = list[i];
        setUploadProgress(`${i + 1}/${list.length}`);
        const data = await fileToBase64(file);
        await api(`/api/review-modules/${module.id}/images`, {
          method: 'POST',
          body: {
            data,
            mime: file.type || 'image/jpeg',
            orig_name: file.name,
          },
        });
        ok += 1;
      }
      const rows = await api(`/api/review-modules/${module.id}/images`);
      setImages(rows || []);
      setIndex(Math.max(0, (rows?.length || 1) - 1));
      onModuleUpdate?.({
        ...module,
        image_count: rows?.length || 0,
      });
      prefetchModuleImages((rows || []).map((r) => r.url));
      if (skipped > 0) {
        setUploadProgress('');
        alert(`已上传 ${ok} 张图片，跳过 ${skipped} 个非图片文件`);
      }
    } catch (e) {
      alert(e.message || `上传失败（已成功 ${ok} 张）`);
      await loadImages();
    } finally {
      setUploading(false);
      setUploadProgress('');
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  // ---------- 拖拽上传 ----------
  // 递归展开被拖进来的文件夹（Chrome/Edge/Safari 支持 webkitGetAsEntry）
  const filesFromEntry = async (entry) => {
    if (!entry) return [];
    if (entry.isFile) {
      return new Promise((resolve) => {
        entry.file((f) => resolve([f]), () => resolve([]));
      });
    }
    if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      // readEntries 每次最多返回 100 条，要循环读到空
      const readBatch = () =>
        new Promise((resolve) => {
          reader.readEntries((batch) => resolve(batch || []), () => resolve([]));
        });
      for (;;) {
        const batch = await readBatch();
        if (!batch.length) break;
        for (const e of batch) all.push(...(await filesFromEntry(e)));
      }
      return all;
    }
    return [];
  };

  const filesFromDataTransfer = async (dt) => {
    if (!dt) return [];
    const items = Array.from(dt.items || []);
    const entries = items
      .filter((it) => it.kind === 'file')
      .map((it) => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null))
      .filter(Boolean);

    // 有 entry API 就用它（能进文件夹）；否则退回 dt.files
    if (entries.length) {
      const nested = await Promise.all(entries.map(filesFromEntry));
      const flat = nested.flat();
      if (flat.length) return flat;
    }
    return Array.from(dt.files || []);
  };

  const resetDrag = () => {
    dragDepth.current = 0;
    setDragOver(false);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    resetDrag();
    if (uploading) return;
    const files = await filesFromDataTransfer(e.dataTransfer);
    if (!files.length) {
      alert('没有读到文件，试试直接拖图片文件');
      return;
    }
    handleUpload(files);
  };

  const handleDragEnter = (e) => {
    if (!Array.from(e.dataTransfer?.types || []).includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current += 1;
    setDragOver(true);
  };

  const handleDragOver = (e) => {
    if (!Array.from(e.dataTransfer?.types || []).includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    // 告诉浏览器这是"复制"操作，光标才会显示 + 号
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    if (!dragOver) setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) resetDrag();
  };

  // 顺手支持粘贴截图（Win+Shift+S / 微信截图后直接 Ctrl+V）
  useEffect(() => {
    const onPaste = (e) => {
      if (editingName || lightboxOpen) return;
      const files = Array.from(e.clipboardData?.files || []).filter((f) =>
        f.type.startsWith('image/')
      );
      if (!files.length) return;
      e.preventDefault();
      handleUpload(files);
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
    // handleUpload 依赖 module.id，切模块时会重建，这里跟随即可
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingName, lightboxOpen, module.id, uploading]);

  const deleteCurrent = async () => {
    const img = images[index];
    if (!img) return;
    if (!confirm('删除当前图片？')) return;
    try {
      await api(`/api/review-modules/${module.id}/images/${img.id}`, { method: 'DELETE' });
      dropCachedReviewImage(img.url);
      const next = images.filter((_, i) => i !== index);
      setImages(next);
      setIndex((i) => Math.max(0, Math.min(i, next.length - 1)));
      onModuleUpdate?.({
        ...module,
        image_count: Math.max(0, (module.image_count || 1) - 1),
      });
    } catch (e) {
      alert(e.message || '删除失败');
    }
  };

  const startRename = () => {
    const img = images[index];
    if (!img) return;
    setNameDraft(img.orig_name || `图片 ${img.id}`);
    setEditingName(true);
    setTimeout(() => nameInputRef.current?.focus(), 0);
  };

  const cancelRename = () => {
    setEditingName(false);
    setNameDraft('');
  };

  const saveRename = async () => {
    const img = images[index];
    if (!img || renaming) return;
    const name = nameDraft.trim();
    if (!name) {
      alert('名称不能为空');
      return;
    }
    if (name === (img.orig_name || '')) {
      cancelRename();
      return;
    }
    setRenaming(true);
    try {
      const updated = await api(`/api/review-modules/${module.id}/images/${img.id}`, {
        method: 'PUT',
        body: { orig_name: name },
      });
      setImages((prev) => prev.map((x) => (x.id === img.id ? { ...x, ...updated } : x)));
      setEditingName(false);
      setNameDraft('');
    } catch (e) {
      alert(e.message || '重命名失败');
    } finally {
      setRenaming(false);
    }
  };

  const current = images[index];

  return (
    <div className="space-y-6 h-full flex flex-col min-h-0">
      {/* 顶栏 */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center space-x-3 min-w-0">
          <button
            onClick={onBack}
            className="w-10 h-10 rounded-2xl bg-[#f2f0e9] hover:bg-[#e8e6dd] flex items-center justify-center flex-shrink-0"
            title="返回模块列表"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="min-w-0">
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              模块复习
            </p>
            <h3 className="text-xl font-black italic truncate">{module.name}</h3>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => handleUpload(e.target.files)}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="inline-flex items-center space-x-2 bg-[#1a1a1a] text-[#fbc02d] px-4 py-2.5 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-[#fbc02d] hover:text-black transition-all disabled:opacity-50"
          >
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            <span>{uploading ? `上传 ${uploadProgress}` : '上传图片'}</span>
          </button>
          {current && (
            <>
              <button
                onClick={() => setLightboxOpen(true)}
                className="inline-flex items-center space-x-2 bg-[#f2f0e9] text-[#1a1a1a] px-4 py-2.5 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-[#1a1a1a] hover:text-[#fbc02d] transition-all"
                title="放大镜预览"
              >
                <Search size={14} />
                <span className="hidden sm:inline">放大预览</span>
              </button>
              <button
                onClick={deleteCurrent}
                className="w-10 h-10 rounded-2xl flex items-center justify-center text-slate-400 hover:bg-[#ff6b6b]/10 hover:text-[#ff6b6b] transition-colors"
                title="删除当前图片"
              >
                <Trash2 size={16} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* 主查看区（同时是拖拽放置区） */}
      <div
        className={`flex-1 min-h-[420px] bg-[#1a1a1a] rounded-[2.5rem] relative overflow-hidden flex flex-col select-none transition-all ${
          dragOver ? 'ring-4 ring-[#fbc02d] ring-offset-2 ring-offset-[#f2f0e9]' : ''
        }`}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onTouchStart={(e) => {
          if (lightboxOpen) return;
          touchStartX.current = e.changedTouches[0]?.clientX ?? null;
        }}
        onTouchEnd={(e) => {
          if (lightboxOpen) return;
          if (touchStartX.current == null) return;
          const dx = (e.changedTouches[0]?.clientX ?? 0) - touchStartX.current;
          touchStartX.current = null;
          if (Math.abs(dx) < 50) return;
          if (dx > 0) go(-1);
          else go(1);
        }}
      >
        <div className="absolute -top-20 -right-20 w-72 h-72 rounded-full blur-[100px] bg-[#fbc02d] opacity-20 pointer-events-none" />

        {/* 拖拽悬浮提示：盖住整个查看区，pointer-events-none 保证 drop 事件仍落在父容器 */}
        {dragOver && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-[#1a1a1a]/85 backdrop-blur-sm pointer-events-none">
            <div className="w-20 h-20 rounded-3xl bg-[#fbc02d] flex items-center justify-center text-black mb-4">
              <Upload size={36} />
            </div>
            <p className="text-white text-lg font-black">松手即上传</p>
            <p className="text-white/50 text-sm font-medium mt-1.5">支持多张图片，也可以直接拖整个文件夹</p>
          </div>
        )}

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-white/50">
            <Loader2 className="animate-spin mr-2" size={20} />
            <span className="text-sm font-bold">加载图片...</span>
          </div>
        ) : !images.length ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-8">
            <div className="w-20 h-20 rounded-3xl bg-white/5 flex items-center justify-center text-white/30 mb-5">
              <ImageIcon size={36} />
            </div>
            <p className="text-white text-lg font-black">还没有图片</p>
            <p className="text-white/40 text-sm font-medium mt-2 mb-6 max-w-sm">
              把图片<span className="text-[#fbc02d] font-bold">拖到这里</span>，或 Ctrl+V 粘贴截图，
              也可以点下面的按钮选文件。用左右键翻阅复习
            </p>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="inline-flex items-center space-x-2 bg-[#fbc02d] text-black px-6 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:brightness-110 transition-all"
            >
              <Upload size={14} />
              <span>上传第一张</span>
            </button>
          </div>
        ) : (
          <>
            {/* 图片区 */}
            <div className="flex-1 flex items-center justify-center p-6 md:p-10 relative min-h-0">
              <button
                onClick={() => go(-1)}
                className="absolute left-3 md:left-6 z-10 w-11 h-11 rounded-full bg-white/10 hover:bg-[#fbc02d] hover:text-black text-white flex items-center justify-center transition-all backdrop-blur-sm"
                title="上一张 ←"
              >
                <ChevronLeft size={22} />
              </button>

              <button
                type="button"
                onClick={() => setLightboxOpen(true)}
                className="relative group max-w-full max-h-[min(62vh,640px)] rounded-2xl focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
                title="点击进入放大预览"
              >
                <CachedReviewImg
                  key={current.id}
                  url={current.url}
                  alt={current.orig_name || `第 ${index + 1} 张`}
                  className="max-w-full max-h-[min(62vh,640px)] object-contain rounded-2xl shadow-2xl shadow-black/40"
                  draggable={false}
                />
                <span className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-black/55 text-white text-[10px] font-black uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity backdrop-blur-sm">
                  <Search size={12} />
                  放大预览
                </span>
              </button>

              <button
                onClick={() => go(1)}
                className="absolute right-3 md:right-6 z-10 w-11 h-11 rounded-full bg-white/10 hover:bg-[#fbc02d] hover:text-black text-white flex items-center justify-center transition-all backdrop-blur-sm"
                title="下一张 →"
              >
                <ChevronRight size={22} />
              </button>
            </div>

            {/* 底栏：进度 + 缩略图 */}
            <div className="px-6 pb-6 space-y-4">
              <div className="flex items-center justify-between gap-3 text-white/50 text-xs font-bold">
                {editingName ? (
                  <div
                    className="flex items-center gap-2 flex-1 min-w-0"
                    onClick={(e) => e.stopPropagation()}
                    onTouchStart={(e) => e.stopPropagation()}
                  >
                    <input
                      ref={nameInputRef}
                      value={nameDraft}
                      onChange={(e) => setNameDraft(e.target.value)}
                      onKeyDown={(e) => {
                        e.stopPropagation();
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          saveRename();
                        }
                        if (e.key === 'Escape') {
                          e.preventDefault();
                          cancelRename();
                        }
                      }}
                      maxLength={200}
                      disabled={renaming}
                      className="flex-1 min-w-0 bg-white/10 border border-[#fbc02d]/40 rounded-xl px-3 py-2 text-sm font-bold text-white focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
                      placeholder="输入图片名称"
                    />
                    <button
                      onClick={saveRename}
                      disabled={renaming || !nameDraft.trim()}
                      className="px-3 py-2 rounded-xl bg-[#fbc02d] text-black text-[10px] font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40"
                    >
                      {renaming ? '...' : '保存'}
                    </button>
                    <button
                      onClick={cancelRename}
                      disabled={renaming}
                      className="px-3 py-2 rounded-xl bg-white/10 text-white/70 text-[10px] font-black uppercase tracking-widest hover:bg-white/15"
                    >
                      取消
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={startRename}
                    className="group flex items-center gap-2 min-w-0 max-w-[70%] text-left hover:text-[#fbc02d] transition-colors"
                    title="点击修改名称"
                  >
                    <span className="truncate">
                      {current.orig_name || `图片 ${current.id}`}
                    </span>
                    <Pencil
                      size={13}
                      className="flex-shrink-0 opacity-40 group-hover:opacity-100 transition-opacity"
                    />
                  </button>
                )}
                <span className="tabular-nums text-[#fbc02d] font-black flex-shrink-0">
                  {index + 1} / {images.length}
                </span>
              </div>

              <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-[#fbc02d] transition-all duration-300"
                  style={{ width: `${((index + 1) / images.length) * 100}%` }}
                />
              </div>

              <div className="flex space-x-2 overflow-x-auto pb-1 scrollbar-thin">
                {images.map((img, i) => (
                  <button
                    key={img.id}
                    onClick={() => setIndex(i)}
                    className={`flex-shrink-0 w-14 h-14 rounded-xl overflow-hidden border-2 transition-all ${
                      i === index
                        ? 'border-[#fbc02d] ring-2 ring-[#fbc02d]/30 scale-105'
                        : 'border-transparent opacity-60 hover:opacity-100'
                    }`}
                  >
                    <CachedReviewImg
                      url={img.url}
                      alt=""
                      className="w-full h-full object-cover"
                      draggable={false}
                    />
                  </button>
                ))}
              </div>

              <p className="text-center text-[10px] font-bold text-white/25 uppercase tracking-widest">
                ← → 翻页 · 点击图片放大预览 · 点名称可改名
              </p>
            </div>
          </>
        )}
      </div>

      {lightboxOpen && current && (
        <ImageLightbox
          url={current.url}
          title={current.orig_name || `第 ${index + 1} 张`}
          index={index}
          total={images.length}
          onClose={() => setLightboxOpen(false)}
          onPrev={() => go(-1)}
          onNext={() => go(1)}
        />
      )}
    </div>
  );
};

// ============== 全屏放大预览（看图软件交互） ==============
const ImageLightbox = ({ url, title, index, total, onClose, onPrev, onNext }) => {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const viewportRef = useRef(null);
  const dragRef = useRef(null); // { x, y, ox, oy }
  const pinchRef = useRef(null); // { dist, zoom }
  const lastTapRef = useRef(0);

  const resetView = useCallback(() => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  }, []);

  // 换图重置缩放：同样用渲染期比对，避免新图先以旧的缩放/位移画一帧再跳回
  const [lastUrl, setLastUrl] = useState(url);
  if (lastUrl !== url) {
    setLastUrl(url);
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  }

  const zoomBy = useCallback((delta, cx, cy) => {
    setZoom((prev) => {
      const next = clampZoom(prev + delta);
      if (next === prev) return prev;
      // 以视口中心或指针为锚点缩放
      if (cx != null && cy != null && viewportRef.current) {
        const rect = viewportRef.current.getBoundingClientRect();
        const px = cx - rect.left - rect.width / 2;
        const py = cy - rect.top - rect.height / 2;
        setOffset((o) => ({
          x: px - ((px - o.x) * next) / prev,
          y: py - ((py - o.y) * next) / prev,
        }));
      }
      if (next <= 1.01) {
        setOffset({ x: 0, y: 0 });
        return next <= 1 ? 1 : next;
      }
      return next;
    });
  }, []);

  const setZoomLevel = useCallback((level) => {
    const next = clampZoom(level);
    setZoom(next);
    if (next <= 1) setOffset({ x: 0, y: 0 });
  }, []);

  // 键盘
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        onPrev();
      }
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        onNext();
      }
      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        zoomBy(ZOOM_STEP);
      }
      if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        zoomBy(-ZOOM_STEP);
      }
      if (e.key === '0') {
        e.preventDefault();
        resetView();
      }
      if (e.key === '1') {
        e.preventDefault();
        setZoomLevel(1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, onPrev, onNext, zoomBy, resetView, setZoomLevel]);

  // 滚轮缩放（阻止页面滚动）
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
      zoomBy(delta, e.clientX, e.clientY);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoomBy]);

  // 锁 body 滚动
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const onPointerDown = (e) => {
    // 双击放大/还原
    if (e.pointerType === 'mouse' || e.pointerType === 'touch') {
      const now = Date.now();
      if (now - lastTapRef.current < 280) {
        lastTapRef.current = 0;
        if (zoom > 1.05) resetView();
        else zoomBy(1.5, e.clientX, e.clientY);
        return;
      }
      lastTapRef.current = now;
    }

    if (zoom <= 1) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setDragging(true);
    dragRef.current = {
      x: e.clientX,
      y: e.clientY,
      ox: offset.x,
      oy: offset.y,
    };
  };

  const onPointerMove = (e) => {
    if (!dragging || !dragRef.current) return;
    const d = dragRef.current;
    setOffset({
      x: d.ox + (e.clientX - d.x),
      y: d.oy + (e.clientY - d.y),
    });
  };

  const onPointerUp = (e) => {
    setDragging(false);
    dragRef.current = null;
    try {
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  // 双指捏合
  const onTouchStart = (e) => {
    if (e.touches.length === 2) {
      e.preventDefault();
      const [a, b] = e.touches;
      const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      pinchRef.current = { dist, zoom };
      dragRef.current = null;
      setDragging(false);
    }
  };

  const onTouchMove = (e) => {
    if (e.touches.length === 2 && pinchRef.current) {
      e.preventDefault();
      const [a, b] = e.touches;
      const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      const ratio = dist / pinchRef.current.dist;
      const next = clampZoom(pinchRef.current.zoom * ratio);
      setZoom(next);
      if (next <= 1) setOffset({ x: 0, y: 0 });
    }
  };

  const onTouchEnd = (e) => {
    if (e.touches.length < 2) pinchRef.current = null;
  };

  const pct = Math.round(zoom * 100);
  const canPan = zoom > 1.01;

  return (
    <div
      className="fixed inset-0 z-[80] bg-black/92 backdrop-blur-sm flex flex-col"
      role="dialog"
      aria-modal="true"
      aria-label="图片放大预览"
    >
      {/* 顶栏工具 */}
      <div className="flex-shrink-0 h-14 px-3 md:px-5 flex items-center justify-between gap-2 border-b border-white/10">
        <div className="min-w-0 flex-1">
          <p className="text-white text-sm font-black truncate">{title}</p>
          <p className="text-white/40 text-[10px] font-bold tabular-nums">
            {index + 1} / {total} · {pct}%
          </p>
        </div>

        <div className="flex items-center gap-1 md:gap-1.5">
          <button
            type="button"
            onClick={() => zoomBy(-ZOOM_STEP)}
            disabled={zoom <= ZOOM_MIN}
            className="w-9 h-9 rounded-xl bg-white/10 text-white hover:bg-white/15 disabled:opacity-30 flex items-center justify-center"
            title="缩小 (-)"
          >
            <ZoomOut size={16} />
          </button>
          <button
            type="button"
            onClick={resetView}
            className="min-w-[3.25rem] h-9 px-2 rounded-xl bg-white/10 text-[#fbc02d] text-xs font-black tabular-nums hover:bg-white/15"
            title="适应窗口 (0)"
          >
            {pct}%
          </button>
          <button
            type="button"
            onClick={() => zoomBy(ZOOM_STEP)}
            disabled={zoom >= ZOOM_MAX}
            className="w-9 h-9 rounded-xl bg-white/10 text-white hover:bg-white/15 disabled:opacity-30 flex items-center justify-center"
            title="放大 (+)"
          >
            <ZoomIn size={16} />
          </button>
          <button
            type="button"
            onClick={() => setZoomLevel(1)}
            className="w-9 h-9 rounded-xl bg-white/10 text-white hover:bg-white/15 flex items-center justify-center"
            title="实际大小 100% (1)"
          >
            <Minimize2 size={15} />
          </button>
          <button
            type="button"
            onClick={() => setZoomLevel(2)}
            className="hidden sm:flex w-9 h-9 rounded-xl bg-white/10 text-white hover:bg-white/15 items-center justify-center"
            title="放大 200%"
          >
            <Maximize2 size={15} />
          </button>
          <div className="w-px h-6 bg-white/15 mx-1" />
          <button
            type="button"
            onClick={onClose}
            className="w-9 h-9 rounded-xl bg-white/10 text-white hover:bg-[#ff6b6b]/80 flex items-center justify-center"
            title="关闭 (Esc)"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* 视口 */}
      <div
        ref={viewportRef}
        className={`relative flex-1 min-h-0 overflow-hidden flex items-center justify-center ${
          canPan ? (dragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-zoom-in'
        }`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onDoubleClick={(e) => {
          e.preventDefault();
          if (zoom > 1.05) resetView();
          else zoomBy(1.5, e.clientX, e.clientY);
        }}
      >
        {total > 1 && (
          <>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onPrev();
              }}
              className="absolute left-3 md:left-5 z-10 w-11 h-11 rounded-full bg-white/10 hover:bg-[#fbc02d] hover:text-black text-white flex items-center justify-center backdrop-blur-sm"
              title="上一张 ←"
            >
              <ChevronLeft size={22} />
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onNext();
              }}
              className="absolute right-3 md:right-5 z-10 w-11 h-11 rounded-full bg-white/10 hover:bg-[#fbc02d] hover:text-black text-white flex items-center justify-center backdrop-blur-sm"
              title="下一张 →"
            >
              <ChevronRight size={22} />
            </button>
          </>
        )}

        <CachedReviewImg
          url={url}
          alt={title}
          draggable={false}
          className="select-none pointer-events-none max-w-full max-h-full object-contain"
          style={{
            transform: `translate3d(${offset.x}px, ${offset.y}px, 0) scale(${zoom})`,
            transformOrigin: 'center center',
            transition: dragging ? 'none' : 'transform 0.1s ease-out',
            willChange: 'transform',
          }}
        />
      </div>

      {/* 底栏提示 */}
      <div className="flex-shrink-0 py-2.5 px-4 text-center text-[10px] font-bold text-white/30 uppercase tracking-widest border-t border-white/10">
        滚轮缩放 · 拖拽平移 · 双击放大/还原 · +/− 键 · Esc 关闭
      </div>
    </div>
  );
};

export default Review;

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, Check, Lightbulb, Loader2, X } from 'lucide-react';
import ContentPanel from './ContentPanel.jsx';

// 考点预热：左边列一套题考的三级知识点（“平均数问题”这一层），右边原样显示该知识点页，
// 下级考法照样能点进去。跟题组来源无关：给一组 points（[{ tag, title, count, reason }]）就能用。
export default function KnowledgePreview({
  title, subtitle, points = [], loading = false, error = '', startLabel = '开始做题', onStart, onClose,
}) {
  const [picked, setPicked] = useState('');
  const [pages, setPages] = useState({});
  const [seen, setSeen] = useState(() => new Set());
  const bodyRef = useRef(null);
  const current = points.some((point) => point.tag === picked) ? picked : points[0]?.tag || '';
  const page = pages[current] || current;
  const viewed = new Set([...seen, current].filter(Boolean));

  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose?.(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: 0 });
  }, [current, page]);

  const choose = (tag) => {
    setSeen((prev) => new Set([...prev, current, tag].filter(Boolean)));
    setPicked(tag);
  };

  return createPortal(
    <div className="fixed inset-0 z-[9990] flex items-center justify-center p-3 sm:p-6" role="dialog" aria-modal="true" aria-labelledby="knowledge-preview-title">
      <button type="button" aria-label="关闭考点预热" className="absolute inset-0 bg-black/35 backdrop-blur-[3px]" onClick={onClose} />
      <div className="relative flex h-[min(92vh,62rem)] w-[min(96vw,88rem)] flex-col overflow-hidden rounded-[2rem] border border-[#c4ae7a] bg-white shadow-2xl">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e8d5b0] px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#1a1a1a] text-white">
              <Lightbulb size={18} />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-black tracking-widest text-[#8a6d3b]">
                考点预热{points.length > 0 && ` · 已看 ${viewed.size}/${points.length}`}
              </p>
              <h3 id="knowledge-preview-title" className="truncate text-base font-black tracking-tight">{title}</h3>
              {subtitle && <p className="truncate text-[11px] font-medium text-slate-500">{subtitle}</p>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {onStart && (
              <button
                type="button"
                onClick={onStart}
                className="flex items-center gap-1.5 rounded-xl bg-[#1a1a1a] px-4 py-2.5 text-xs font-black text-white transition-colors hover:bg-[#2c261c]"
              >
                {startLabel}
                <ArrowRight size={14} />
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭"
              className="rounded-xl p-2.5 text-[#777] transition-colors hover:bg-black/5 hover:text-[#1a1a1a]"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {loading || error || points.length === 0 ? (
          <div className="flex flex-1 items-center justify-center p-10 text-center">
            {loading ? (
              <p className="flex items-center gap-2 text-sm font-black text-slate-400" role="status">
                <Loader2 size={16} className="animate-spin" /> 正在读取这套题的知识点…
              </p>
            ) : (
              <p className="text-sm font-bold text-slate-500">{error || '这套题的知识点还没有讲解页。'}</p>
            )}
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] md:grid-cols-[16rem_minmax(0,1fr)] md:grid-rows-1">
            <nav
              aria-label="本套题考的知识点"
              className="flex gap-2 overflow-x-auto overscroll-contain border-b border-[#e8d5b0] bg-[#f5eed8] p-3 md:flex-col md:overflow-y-auto md:overflow-x-hidden md:border-b-0 md:border-r"
            >
              {points.map((point) => {
                const selected = point.tag === current;
                return (
                  <button
                    key={point.tag}
                    type="button"
                    aria-current={selected ? 'true' : undefined}
                    onClick={() => choose(point.tag)}
                    className={`w-52 shrink-0 rounded-2xl border px-4 py-3 text-left transition-colors md:w-auto ${
                      selected
                        ? 'border-[#1a1a1a] bg-[#1a1a1a] text-white'
                        : 'border-[#e8d5b0] bg-[#f2e4c4] text-[#1a1a1a] hover:border-[#cbb387]'
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-[15px] font-black">{point.title}</span>
                      <span className="flex shrink-0 items-center gap-1 text-[11px] font-black opacity-70">
                        {!selected && viewed.has(point.tag) && <Check size={12} aria-label="已看" />}
                        {point.count} 题
                      </span>
                    </span>
                    {point.reason && (
                      <span className={`mt-1.5 block text-[11px] font-medium leading-snug ${selected ? 'text-white/70' : 'text-slate-500'}`}>
                        {point.reason}
                      </span>
                    )}
                  </button>
                );
              })}
            </nav>
            <div ref={bodyRef} className="min-h-0 overflow-y-auto overscroll-contain bg-[#e8d5b0] px-4 py-5 sm:px-6">
              <ContentPanel
                key={current}
                rootTag={current}
                learningTag={current}
                selectedTag={page}
                onSelect={(tag) => setPages((prev) => ({ ...prev, [current]: tag }))}
                active
                preview
              />
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

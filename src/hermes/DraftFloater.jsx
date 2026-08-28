import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FileImage, Loader2, X } from 'lucide-react';

const KEY = 'hermes.draftFloater';
const MIN_W = 280;
const MIN_H = 200;

const clampBox = (box) => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = Math.min(Math.max(box.w, MIN_W), vw - 16);
  const h = Math.min(Math.max(box.h, MIN_H), vh - 16);
  return {
    left: Math.min(Math.max(box.left, 8), Math.max(8, vw - w - 8)),
    top: Math.min(Math.max(box.top, 8), Math.max(8, vh - 48)),
    w,
    h,
  };
};

const defaultBox = () => {
  const w = Math.min(520, Math.max(320, window.innerWidth * 0.38));
  return clampBox({
    left: window.innerWidth - w - 24,
    top: 72,
    w,
    h: Math.min(640, window.innerHeight - 96),
  });
};

const readBox = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '');
    if (raw && Number.isFinite(raw.left)) return clampBox(raw);
  } catch { /* 用默认 */ }
  return defaultBox();
};

export default function DraftFloater({
  questionNumber,
  src,
  loading,
  error,
  onClose,
}) {
  const [box, setBox] = useState(readBox);
  const dragRef = useRef(null);

  useEffect(() => {
    const onResize = () => setBox((current) => clampBox(current));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const persist = (next) => {
    const clamped = clampBox(next);
    setBox(clamped);
    try { localStorage.setItem(KEY, JSON.stringify(clamped)); } catch { /* 隐私模式 */ }
  };

  const start = (event, mode) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      mode,
      x: event.clientX,
      y: event.clientY,
      ...box,
    };
  };

  const move = (event) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    persist(drag.mode === 'move'
      ? { ...drag, left: drag.left + dx, top: drag.top + dy }
      : { ...drag, w: drag.w + dx, h: drag.h + dy });
  };

  const end = () => { dragRef.current = null; };

  return createPortal(
    <div
      className="fixed flex flex-col rounded-2xl bg-[#f8f3e8] border border-[#d9c49d] shadow-2xl shadow-black/20 overflow-hidden"
      style={{ left: box.left, top: box.top, width: box.w, height: box.h, zIndex: 90 }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 bg-[#1a1a1a] text-white cursor-grab active:cursor-grabbing touch-none select-none"
        onPointerDown={(event) => start(event, 'move')}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
      >
        <FileImage size={13} className="opacity-70 shrink-0" />
        <span className="flex-1 text-[11px] font-black tracking-widest">
          第 {questionNumber} 题 · 当时草稿
        </span>
        <button
          type="button"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={onClose}
          className="w-6 h-6 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center"
          title="关闭草稿"
        >
          <X size={13} />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto overscroll-contain p-3">
        {loading ? (
          <div className="h-full flex items-center justify-center gap-2 text-xs font-bold text-[#999]">
            <Loader2 size={15} className="animate-spin" />
            <span>加载草稿…</span>
          </div>
        ) : error ? (
          <div className="h-full flex items-center justify-center px-6 text-center text-xs font-bold text-[#ef5350]">
            {error}
          </div>
        ) : src ? (
          <img
            src={src}
            alt={`第 ${questionNumber} 题当时的草稿`}
            className="block w-full h-auto rounded-xl bg-white"
          />
        ) : null}
      </div>

      <div
        className="absolute right-0 bottom-0 w-5 h-5 cursor-se-resize touch-none"
        onPointerDown={(event) => start(event, 'resize')}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        title="拖动改大小"
      >
        <span className="absolute right-1.5 bottom-1.5 w-2 h-2 border-r-2 border-b-2 border-[#6b5428]" />
      </div>
    </div>,
    document.body,
  );
}

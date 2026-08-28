import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { PictureInPicture2, X } from 'lucide-react';

import { api } from '../api.js';
import DraftFloater from './DraftFloater.jsx';
import MarkdownMessage from './MarkdownMessage.jsx';

const KEY = 'hermes.reviewFloater';
const MIN_W = 280;
const MIN_H = 200;

const clampBox = (box) => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = Math.min(Math.max(box.w, MIN_W), vw - 16);
  const h = Math.min(Math.max(box.h, MIN_H), vh - 16);
  return {
    left: Math.min(Math.max(box.left, 8), Math.max(8, vw - 80)),
    top: Math.min(Math.max(box.top, 8), Math.max(8, vh - 48)),
    w,
    h,
  };
};

const defaultBox = () => clampBox({
  left: 12,
  top: 72,
  w: Math.min(420, Math.max(300, window.innerWidth * 0.32)),
  h: Math.min(640, window.innerHeight - 96),
});

const readBox = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '');
    if (raw && Number.isFinite(raw.left)) return clampBox(raw);
  } catch { /* 用默认 */ }
  return defaultBox();
};

export default function ReviewFloater({
  content,
  streaming,
  fontScale = 100,
  practiceSessionId,
  onClose,
}) {
  const [box, setBox] = useState(readBox);
  const [draftQuestions, setDraftQuestions] = useState(null);
  const [draftPanel, setDraftPanel] = useState(null);
  const dragRef = useRef(null);
  const draftCacheRef = useRef(new Map());

  useEffect(() => {
    const onResize = () => setBox((b) => clampBox(b));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    draftCacheRef.current.clear();
    setDraftPanel(null);
    if (!practiceSessionId) {
      setDraftQuestions(null);
      return undefined;
    }

    let cancelled = false;
    setDraftQuestions(null);
    api(`/api/practice/sessions/${practiceSessionId}/report`)
      .then((report) => {
        if (cancelled) return;
        const mapped = new Map();
        for (const [index, item] of (report?.items || []).entries()) {
          mapped.set(index + 1, item?.draft_url
            ? { questionId: item.question_id }
            : null);
        }
        setDraftQuestions(mapped);
      })
      .catch(() => {
        if (!cancelled) setDraftQuestions(new Map());
      });
    return () => { cancelled = true; };
  }, [practiceSessionId]);

  const persist = (next) => {
    const clamped = clampBox(next);
    setBox(clamped);
    try { localStorage.setItem(KEY, JSON.stringify(clamped)); } catch { /* 隐私模式 */ }
  };

  const start = (e, mode) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { mode, x: e.clientX, y: e.clientY, ...box };
  };

  const move = (e) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    persist(d.mode === 'move'
      ? { ...d, left: d.left + dx, top: d.top + dy }
      : { ...d, w: d.w + dx, h: d.h + dy });
  };

  const end = () => { dragRef.current = null; };

  const openDraft = async (questionNumber, draft) => {
    if (!draft?.questionId || !practiceSessionId) return;
    const cacheKey = `${practiceSessionId}:${draft.questionId}`;
    const cached = draftCacheRef.current.get(cacheKey);
    if (cached) {
      setDraftPanel({ questionNumber, cacheKey, src: cached, loading: false, error: '' });
      return;
    }

    setDraftPanel({ questionNumber, cacheKey, src: '', loading: true, error: '' });
    try {
      const result = await api(
        `/api/practice/sessions/${practiceSessionId}/drafts/${draft.questionId}/base64`,
      );
      if (!result?.data_url) throw new Error('草稿文件不存在');
      draftCacheRef.current.set(cacheKey, result.data_url);
      setDraftPanel((current) => (
        current?.cacheKey === cacheKey
          ? { ...current, src: result.data_url, loading: false }
          : current
      ));
    } catch (error) {
      setDraftPanel((current) => (
        current?.cacheKey === cacheKey
          ? { ...current, loading: false, error: error?.message || '草稿加载失败' }
          : current
      ));
    }
  };

  return (
    <>
      {createPortal(
        <div
          className="fixed flex flex-col rounded-2xl bg-[#e8d5b0] border border-[#e8d5b0] shadow-2xl shadow-black/20 overflow-hidden"
          style={{ left: box.left, top: box.top, width: box.w, height: box.h, zIndex: 80 }}
        >
          <div
            className="flex items-center gap-2 px-3 py-2 bg-[#6b5428] text-[#f7efe0] cursor-grab active:cursor-grabbing touch-none select-none"
            onPointerDown={(e) => start(e, 'move')}
            onPointerMove={move}
            onPointerUp={end}
            onPointerCancel={end}
          >
            <PictureInPicture2 size={13} className="opacity-70 shrink-0" />
            <span className="flex-1 text-[11px] font-black tracking-widest uppercase">复盘浮框</span>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={onClose}
              className="w-6 h-6 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center"
              title="收起浮框"
            >
              <X size={13} />
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-3 [&_blockquote]:bg-[#e8d5b0] [&_blockquote]:border-[#d4c09a]">
            <div style={{ zoom: fontScale / 100 }}>
              <MarkdownMessage
                content={content}
                streaming={streaming}
                draftQuestions={draftQuestions}
                activeDraftNumber={draftPanel?.questionNumber}
                draftLoadingNumber={draftPanel?.loading ? draftPanel.questionNumber : null}
                onOpenDraft={openDraft}
              />
            </div>
          </div>
          <div
            className="absolute right-0 bottom-0 w-5 h-5 cursor-se-resize touch-none"
            onPointerDown={(e) => start(e, 'resize')}
            onPointerMove={move}
            onPointerUp={end}
            onPointerCancel={end}
            title="拖动改大小"
          >
            <span className="absolute right-1.5 bottom-1.5 w-2 h-2 border-r-2 border-b-2 border-[#6b5428]" />
          </div>
        </div>,
        document.body,
      )}
      {draftPanel && (
        <DraftFloater
          questionNumber={draftPanel.questionNumber}
          src={draftPanel.src}
          loading={draftPanel.loading}
          error={draftPanel.error}
          onClose={() => setDraftPanel(null)}
        />
      )}
    </>
  );
}

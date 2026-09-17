import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from 'react';
import { Eraser, PenTool, Trash2, Undo2 } from 'lucide-react';
import DraftLayer from '../aiPractice/DraftLayer.jsx';

const Ctx = createContext(null);
export const useReviewScratch = () => useContext(Ctx);

const load = (key) => {
  try {
    const raw = JSON.parse(localStorage.getItem(key) || '');
    return raw && typeof raw === 'object' ? raw : {};
  } catch {
    return {};
  }
};

export default function ReviewScratch({ storageKey, enabled = true, children }) {
  const storeKey = storageKey ? `hermes.scratch.${storageKey}` : '';
  const [active, setActive] = useState(null);
  const [tool, setTool] = useState('pen');
  const [byQ, setByQ] = useState(() => (storeKey ? load(storeKey) : {}));

  useEffect(() => {
    setByQ(storeKey ? load(storeKey) : {});
    setActive(null);
    setTool('pen');
  }, [storeKey]);

  useEffect(() => {
    if (!storeKey) return;
    try { localStorage.setItem(storeKey, JSON.stringify(byQ)); } catch { /* private mode */ }
  }, [storeKey, byQ]);

  useEffect(() => {
    if (active == null) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setActive(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active]);

  const mutate = useCallback((fn) => {
    if (active == null) return;
    setByQ((prev) => ({ ...prev, [active]: fn(prev[active] || []) }));
  }, [active]);

  const value = useMemo(() => ({
    enabled: Boolean(enabled && storeKey),
    active,
    tool,
    setTool,
    hasInk: (n) => (byQ[n] || []).length > 0,
    toggle: (n) => {
      setActive((cur) => {
        const next = cur === n ? null : n;
        if (next != null) setTool('pen');
        return next;
      });
    },
    undo: () => mutate((s) => s.slice(0, -1)),
    clear: () => mutate(() => []),
  }), [enabled, storeKey, active, tool, byQ, mutate]);

  const strokes = active != null ? (byQ[active] || []) : [];

  return (
    <Ctx.Provider value={value}>
      <div className="relative isolate">
        {children}
        {value.enabled && (
          <DraftLayer
            active={active != null}
            visible={active != null}
            tool={tool}
            color="#1a1a1a"
            strokes={strokes}
            onStrokeEnd={(stroke) => {
              if (active == null) return;
              setByQ((prev) => ({ ...prev, [active]: [...(prev[active] || []), stroke] }));
            }}
          />
        )}
      </div>
    </Ctx.Provider>
  );
}

const btn = (on) => (
  `shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-colors ${
    on ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5 hover:text-[#1a1a1a]'
  }`
);

export function ScratchTools({ questionNumber }) {
  const scratch = useReviewScratch();
  if (!scratch?.enabled || questionNumber == null) return null;
  const on = scratch.active === questionNumber;
  const ink = scratch.hasInk(questionNumber);
  const pencilClass = on
    ? btn(true)
    : ink
      ? 'shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-[#6b5428] bg-[#f4e6c8] hover:border-[#6b5428]'
      : btn(false);
  return (
    <span className="shrink-0 inline-flex items-center gap-0.5" data-capture-ignore="1">
      {on && (
        <>
          <button
            type="button"
            onClick={() => scratch.setTool((t) => (t === 'eraser' ? 'pen' : 'eraser'))}
            title="橡皮"
            className={btn(scratch.tool === 'eraser')}
          >
            <Eraser size={13} />
          </button>
          <button
            type="button"
            onClick={scratch.undo}
            disabled={!ink}
            title="撤销一笔"
            className={`${btn(false)} disabled:opacity-30`}
          >
            <Undo2 size={13} />
          </button>
          <button
            type="button"
            onClick={scratch.clear}
            disabled={!ink}
            title="清空本题草稿"
            className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-[#999] hover:bg-red-50 hover:text-[#ef5350] disabled:opacity-30"
          >
            <Trash2 size={13} />
          </button>
        </>
      )}
      <button
        type="button"
        onClick={() => scratch.toggle(questionNumber)}
        title={on ? '退出草稿纸' : '打开草稿纸'}
        aria-pressed={on}
        className={pencilClass}
      >
        <PenTool size={13} />
      </button>
    </span>
  );
}

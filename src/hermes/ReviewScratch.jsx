import {
  createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState,
} from 'react';
import { Eraser, PenTool, Trash2, Undo2 } from 'lucide-react';
import DraftLayer from '../aiPractice/DraftLayer.jsx';

const Ctx = createContext(null);
const useReviewScratch = () => useContext(Ctx);

// 存档 { v: 2, q: { 题号: 笔画[] }, legacy: [题号] }。v1 是裸的 { 题号: 笔画[] }，
// 坐标相对整条消息顶部；v2 相对本题标题。legacy 里的题第一次打开时按标题位置平移过来。
const load = (key) => {
  try {
    const raw = JSON.parse(localStorage.getItem(key) || '');
    if (!raw || typeof raw !== 'object') return { q: {}, legacy: [] };
    if (raw.v === 2) return { q: raw.q || {}, legacy: raw.legacy || [] };
    return { q: raw, legacy: Object.keys(raw) };
  } catch {
    return { q: {}, legacy: [] };
  }
};

const shiftStrokes = (strokes, dy) => strokes.map((s) => ({
  ...s,
  pts: s.pts.map(([x, y, ...rest]) => [x, y - dy, ...rest]),
}));

export default function ReviewScratch({ storageKey, enabled = true, children }) {
  const storeKey = storageKey ? `hermes.scratch.${storageKey}` : '';
  return <ScratchSession key={storeKey} storeKey={storeKey} enabled={enabled}>{children}</ScratchSession>;
}

function ScratchSession({ storeKey, enabled, children }) {
  const [active, setActive] = useState(null);
  const [tool, setTool] = useState('pen');
  const [initial] = useState(() => (storeKey ? load(storeKey) : { q: {}, legacy: [] }));
  const [byQ, setByQ] = useState(initial.q);
  const [legacy, setLegacy] = useState(initial.legacy);
  const wrapRef = useRef(null);
  // 画布只盖当前这道题（本题标题到下一个标题）。盖整条复盘的话，十道题连配图
  // 上万像素高，超出浏览器画布上限，正在写的那层不刷新，要松笔才看得到。
  const [section, setSection] = useState(null);

  // 每收一笔就同步序列化整份笔迹，笔迹一多就卡下一笔的落笔；停笔后再写，离开时补写
  const pendingRef = useRef(null);
  const flush = useCallback(() => {
    const data = pendingRef.current;
    pendingRef.current = null;
    if (!storeKey || !data) return;
    try { localStorage.setItem(storeKey, JSON.stringify(data)); } catch { /* private mode */ }
  }, [storeKey]);

  useEffect(() => {
    pendingRef.current = { v: 2, q: byQ, legacy };
    const timer = setTimeout(flush, 800);
    return () => clearTimeout(timer);
  }, [byQ, legacy, flush]);

  useEffect(() => {
    window.addEventListener('pagehide', flush);
    return () => {
      window.removeEventListener('pagehide', flush);
      flush();
    };
  }, [flush]);

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

  useLayoutEffect(() => {
    const wrap = wrapRef.current;
    if (active == null || !wrap) {
      setSection(null);
      return undefined;
    }
    const measure = () => {
      const heading = wrap.querySelector(`[data-scratch-q="${active}"]`)?.closest('h3');
      if (!heading) {
        setSection(null);
        return;
      }
      const base = wrap.getBoundingClientRect().top;
      const headings = [...wrap.querySelectorAll('h3')];
      const next = headings[headings.indexOf(heading) + 1];
      const top = Math.round(heading.getBoundingClientRect().top - base);
      const bottom = Math.round(next ? next.getBoundingClientRect().top - base : wrap.offsetHeight);
      setSection((cur) => (
        cur && cur.top === top && cur.height === bottom - top ? cur : { top, height: bottom - top }
      ));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [active]);

  const sectionTop = section?.top;
  useEffect(() => {
    const key = String(active);
    if (sectionTop == null || !legacy.includes(key)) return;
    const w = wrapRef.current?.offsetWidth || 1;
    setByQ((prev) => ({ ...prev, [key]: shiftStrokes(prev[key] || [], sectionTop / w) }));
    setLegacy((prev) => prev.filter((n) => n !== key));
  }, [active, sectionTop, legacy]);

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

  const migrating = active != null && legacy.includes(String(active));
  const strokes = active != null ? (byQ[active] || []) : [];

  return (
    <Ctx.Provider value={value}>
      <div ref={wrapRef} className="relative isolate">
        {children}
        {value.enabled && section && !migrating && (
          <div className="absolute inset-x-0" style={{ top: section.top, height: section.height }}>
            <DraftLayer
              key={active}
              active
              tool={tool}
              color="#1a1a1a"
              strokes={strokes}
              onStrokeEnd={(stroke) => {
                if (active == null) return;
                setByQ((prev) => ({ ...prev, [active]: [...(prev[active] || []), stroke] }));
              }}
            />
          </div>
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
    <span className="shrink-0 inline-flex items-center gap-0.5" data-capture-ignore="1" data-scratch-q={questionNumber}>
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

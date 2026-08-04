// 草稿纸批注层
//
// 不是一块单独的空白画布，而是一层透明 canvas 盖在整个题目区域上：
// 题干、选项、下面的演算区都在它底下，所以可以直接在题面上圈条件、划关键词、
// 在旁边列式子 —— 跟在纸上做题一个手感。
//
// 两种模式来回切（父组件的 active）：
//   批注模式 pointer-events 归 canvas，笔画进 canvas；
//   答题模式 pointer-events: none 且笔迹整层收起（visible=false），回到干净的题面。
//   笔画只是不显示，数据还在：重新打开草稿纸就回来，存档快照也照样带着它。
//
// 笔迹存的是矢量点（按容器宽度归一化），不是位图：
//   - 换题来回跳转要能原样恢复；
//   - 横竖屏切换 / 内容重排后还能贴着题目走；
//   - 撤销就是 pop 一笔，不用记快照。

import { useCallback, useEffect, useRef } from 'react';
import { scrollHost, scrollHostBy } from './scrollHost.js';

const PEN_MIN_W = 1.4;
const PEN_MAX_W = 4.2;
const HL_W = 16;
const ERASER_W = 28;
const HL_ALPHA = 0.32;
const HL_COLOR = '#fbc02d';

// "这台设备在用 Pencil" 记在本地：组件重挂载、页面刷新之后还得算数，
// 否则回到题目第一次用手指滚动会先画出一道杠来。
const PEN_FLAG_KEY = 'draft_pen_seen_v1';
const loadPenSeen = () => {
  try {
    return localStorage.getItem(PEN_FLAG_KEY) === '1';
  } catch {
    return false;
  }
};
const savePenSeen = () => {
  try {
    localStorage.setItem(PEN_FLAG_KEY, '1');
  } catch {
    /* 无痕模式写不进去就算了，本次会话内的 ref 仍然有效 */
  }
};

// ---- 手指翻页 ----
// 批注模式下 canvas 必须 touch-action: none，不能只关横向：iPadOS 的 touch-action
// 对 Apple Pencil 和手指一视同仁，只要留着 pan-y，竖着写的那一笔就会被判成滚页
// （横着划反而画得出来，所以症状是"写不了字，一写页面就跑"）。手势一旦交给合成器，
// preventDefault 也拽不回来。于是浏览器手势全部关掉，手指滚动这件事自己做。
const PALM_MAX_PX = 40; // 接触面比这大的当手掌，不是指尖
const PEN_COOLDOWN_MS = 500; // 刚落过笔的这段时间里，任何触摸都按手掌处理
const FLICK_DECAY = 0.94; // 每帧衰减，甩一下有点惯性才像原生滚动
const FLICK_MIN_V = 0.02; // px/ms，低于这个速度就停

// 这一下触摸是不是"想翻页的手指"。写字时手掌压上来、笔画间隙的误碰都要挡掉。
const isRealFinger = (e, lastPenTs, drawing) => {
  if (drawing) return false;
  if (Date.now() - lastPenTs < PEN_COOLDOWN_MS) return false;
  // Safari 对触摸不一定给得出接触面尺寸，给不出时这条自然失效，不影响上面两条
  if (e.width > PALM_MAX_PX || e.height > PALM_MAX_PX) return false;
  return true;
};

const strokeWidth = (kind, pressure) => {
  if (kind === 'hl') return HL_W;
  if (kind === 'er') return ERASER_W;
  return PEN_MIN_W + pressure * (PEN_MAX_W - PEN_MIN_W);
};

// 画一整笔。w = canvas 的 CSS 宽度；点坐标存的是 x/w、y/w，乘回去就对位了。
const paintStroke = (ctx, stroke, w) => {
  const pts = stroke.pts;
  if (!pts || pts.length === 0) return;

  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  if (stroke.k === 'er') {
    // 橡皮擦的是 canvas 自己的像素，不会动到底下的题目 DOM
    ctx.globalCompositeOperation = 'destination-out';
    ctx.strokeStyle = 'rgba(0,0,0,1)';
  } else {
    ctx.globalCompositeOperation = 'source-over';
    ctx.strokeStyle = stroke.c;
    if (stroke.k === 'hl') ctx.globalAlpha = HL_ALPHA;
  }

  if (pts.length === 1) {
    const [nx, ny, p] = pts[0];
    ctx.beginPath();
    ctx.arc(nx * w, ny * w, strokeWidth(stroke.k, p ?? 0.5) / 2, 0, Math.PI * 2);
    ctx.fillStyle = stroke.k === 'er' ? 'rgba(0,0,0,1)' : stroke.c;
    ctx.fill();
    ctx.restore();
    return;
  }

  if (stroke.k === 'pen') {
    // 压感要逐段生效，所以一段一条路径
    for (let i = 1; i < pts.length; i += 1) {
      const [ax, ay] = pts[i - 1];
      const [bx, by, bp] = pts[i];
      ctx.lineWidth = strokeWidth('pen', bp ?? 0.5);
      ctx.beginPath();
      ctx.moveTo(ax * w, ay * w);
      ctx.lineTo(bx * w, by * w);
      ctx.stroke();
    }
  } else {
    ctx.lineWidth = strokeWidth(stroke.k, 0.5);
    ctx.beginPath();
    ctx.moveTo(pts[0][0] * w, pts[0][1] * w);
    for (let i = 1; i < pts.length; i += 1) ctx.lineTo(pts[i][0] * w, pts[i][1] * w);
    ctx.stroke();
  }
  ctx.restore();
};

const DraftLayer = ({ active, visible = true, tool, color, strokes, onStrokeEnd }) => {
  const canvasRef = useRef(null);
  const ctxRef = useRef(null);
  const sizeRef = useRef({ w: 0, h: 0 });
  const liveRef = useRef(null);
  // Apple Pencil 一出现，手指就换个职责：不再落墨，改为翻页。
  // 写字时手掌搭在屏幕上也走这条路，再由 isRealFinger 挡掉。
  const penSeenRef = useRef(loadPenSeen());

  // 手指平移的现场：按下的那根手指、上一帧位置、用于惯性的瞬时速度
  const panRef = useRef(null);
  const lastPenTsRef = useRef(0);
  const flickRef = useRef(0);

  // 手指松开后按当时的速度滑一段，不然长题干只能一寸一寸拖，很难受
  const startFlick = useCallback((host, v0) => {
    cancelAnimationFrame(flickRef.current);
    let v = v0;
    let last = performance.now();
    const step = (now) => {
      const dt = now - last;
      last = now;
      scrollHostBy(host, v * dt);
      v *= FLICK_DECAY ** (dt / 16.7);
      if (Math.abs(v) > FLICK_MIN_V) flickRef.current = requestAnimationFrame(step);
    };
    flickRef.current = requestAnimationFrame(step);
  }, []);

  useEffect(() => () => cancelAnimationFrame(flickRef.current), []);

  const beginPan = (e) => {
    cancelAnimationFrame(flickRef.current); // 滑动中再按下：先刹住
    // 拖到画布外也要能收到事件，否则 pointerup 掉在别处，panRef 就死在那里了
    try { canvasRef.current.setPointerCapture(e.pointerId); } catch { /* 同下 */ }
    panRef.current = {
      id: e.pointerId,
      host: scrollHost(canvasRef.current),
      y: e.clientY,
      t: performance.now(),
      v: 0,
    };
  };

  const redraw = useCallback(() => {
    const ctx = ctxRef.current;
    const canvas = canvasRef.current;
    if (!ctx || !canvas) return;
    const { w } = sizeRef.current;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = 'source-over';
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
    for (const s of strokes || []) paintStroke(ctx, s, w);
  }, [strokes]);

  // 尺寸跟随容器：iPad 是 2x 屏，位图不乘 DPR 线条会发虚
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const fit = () => {
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      if (!w || !h) return;
      const dpr = window.devicePixelRatio || 1;
      const nextW = Math.round(w * dpr);
      const nextH = Math.round(h * dpr);
      sizeRef.current = { w, h };
      if (canvas.width === nextW && canvas.height === nextH) return;
      canvas.width = nextW;
      canvas.height = nextH;
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctxRef.current = ctx;
      redraw();
    };

    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [redraw]);

  useEffect(() => { redraw(); }, [redraw]);

  const kindOf = () => (tool === 'eraser' ? 'er' : tool === 'highlighter' ? 'hl' : 'pen');

  const pointOf = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const w = rect.width || 1;
    const pressure = e.pressure > 0 && e.pressure < 1 ? e.pressure : 0.5;
    return [(e.clientX - rect.left) / w, (e.clientY - rect.top) / w, Number(pressure.toFixed(2))];
  };

  const onPointerDown = (e) => {
    if (!active) return;
    if (e.pointerType === 'pen') {
      lastPenTsRef.current = Date.now();
      if (!penSeenRef.current) {
        penSeenRef.current = true;
        savePenSeen();
      }
      // 笔落下去的那一刻，先前那个“手指”就能确定是先搭上来的手掌
      panRef.current = null;
      cancelAnimationFrame(flickRef.current);
    }
    // Pencil 出现过之后，手指就专职当翻页手，不再落墨
    if (e.pointerType === 'touch' && penSeenRef.current) {
      // 已经有一根手指在拖了，后来的不抢
      if (!panRef.current && isRealFinger(e, lastPenTsRef.current, !!liveRef.current)) beginPan(e);
      return;
    }
    e.preventDefault();
    try { canvasRef.current.setPointerCapture(e.pointerId); } catch { /* 拿不到捕获就算了 */ }

    const kind = kindOf();
    liveRef.current = { k: kind, c: kind === 'hl' ? HL_COLOR : color, pts: [pointOf(e)] };
    // 单点也要留个墨点，不然轻点一下什么都没有
    const ctx = ctxRef.current;
    if (ctx) paintStroke(ctx, liveRef.current, sizeRef.current.w);
  };

  const onPointerMove = (e) => {
    if (!active) return;
    if (e.pointerType === 'pen') lastPenTsRef.current = Date.now();

    const pan = panRef.current;
    if (pan && e.pointerId === pan.id) {
      // 手指往上推 → 内容往上走 → scrollTop 变大
      const dy = pan.y - e.clientY;
      scrollHostBy(pan.host, dy);
      const now = performance.now();
      const dt = now - pan.t;
      if (dt > 0) pan.v = dy / dt;
      pan.y = e.clientY;
      pan.t = now;
      return;
    }

    const live = liveRef.current;
    if (!live || (e.pointerType === 'touch' && penSeenRef.current)) return;
    e.preventDefault();
    const pt = pointOf(e);
    const prev = live.pts[live.pts.length - 1];
    // 抽掉挤在一起的采样点：高刷屏的 pointermove 会塞进大量几乎重复的坐标
    const w = sizeRef.current.w || 1;
    if (Math.hypot((pt[0] - prev[0]) * w, (pt[1] - prev[1]) * w) < 0.7) return;
    live.pts.push(pt);
    // 只补最新那一段，整层重绘留给撤销/换题
    const ctx = ctxRef.current;
    if (ctx) paintStroke(ctx, { ...live, pts: [prev, pt] }, w);
  };

  const endStroke = (e) => {
    const live = liveRef.current;
    liveRef.current = null;
    if (e) {
      try { canvasRef.current?.releasePointerCapture(e.pointerId); } catch { /* 同上 */ }
    }
    if (live) onStrokeEnd?.(live);
  };

  const onPointerUp = (e) => {
    if (!active) return;
    const pan = panRef.current;
    if (pan && e.pointerId === pan.id) {
      panRef.current = null;
      try { canvasRef.current?.releasePointerCapture(e.pointerId); } catch { /* 同上 */ }
      // 停顿超过 100ms 再抬手说明是"拖到位"，不该再滑
      if (Math.abs(pan.v) > FLICK_MIN_V && performance.now() - pan.t < 100) {
        startFlick(pan.host, pan.v);
      }
      return;
    }
    if (e.pointerType === 'touch' && penSeenRef.current) return;
    e.preventDefault();
    endStroke(e);
  };

  return (
    <canvas
      ref={canvasRef}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerLeave={(e) => { if (active && liveRef.current) endStroke(e); }}
      data-capture-reveal="1"
      className={`absolute inset-0 w-full h-full z-20 transition-opacity duration-150 ${active ? '' : 'pointer-events-none'}`}
      style={{
        // 关掉草稿纸就把笔迹收起来（截图存档不受影响，见 captureNode 的 onclone）
        opacity: visible ? 1 : 0,
        // 批注模式下把浏览器手势全吃掉。不能退而求其次用 pan-y：
        // touch-action 对 Apple Pencil 一视同仁，留着纵向平移，竖着写的那一笔
        // 就会被当成滚页。手指翻页改成自己接管（见上面的手指平移）。
        touchAction: active ? 'none' : 'auto',
        cursor: active ? (tool === 'eraser' ? 'cell' : 'crosshair') : 'auto',
      }}
    />
  );
};

export default DraftLayer;

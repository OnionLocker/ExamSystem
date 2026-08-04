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

import { useCallback, useEffect, useRef, useState } from 'react';

const PEN_MIN_W = 1.4;
const PEN_MAX_W = 4.2;
const HL_W = 16;
const ERASER_W = 28;
const HL_ALPHA = 0.32;
const HL_COLOR = '#fbc02d';

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
  // Apple Pencil 出现过之后就把手指当误触（写字时手掌搭在屏幕上不该画出线），
  // 同时把 touch-action 放开成 pan-y，这样手指还能滚页面看下面的演算区。
  // ref 给同一次手势内的判断用，state 只是为了让 touch-action 重新渲染。
  const penSeenRef = useRef(false);
  const [penSeen, setPenSeen] = useState(false);

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

  const ignore = (e) => e.pointerType === 'touch' && penSeenRef.current;

  const onPointerDown = (e) => {
    if (!active) return;
    if (e.pointerType === 'pen' && !penSeenRef.current) {
      penSeenRef.current = true;
      setPenSeen(true);
    }
    if (ignore(e)) return;
    e.preventDefault();
    try { canvasRef.current.setPointerCapture(e.pointerId); } catch { /* 拿不到捕获就算了 */ }

    const kind = kindOf();
    liveRef.current = { k: kind, c: kind === 'hl' ? HL_COLOR : color, pts: [pointOf(e)] };
    // 单点也要留个墨点，不然轻点一下什么都没有
    const ctx = ctxRef.current;
    if (ctx) paintStroke(ctx, liveRef.current, sizeRef.current.w);
  };

  const onPointerMove = (e) => {
    const live = liveRef.current;
    if (!active || !live || ignore(e)) return;
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
    if (!active || ignore(e)) return;
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
        // 批注模式下必须吃掉浏览器手势，否则画一笔就变成滚动/缩放；
        // 一旦确认在用 Pencil，就把单指纵向滚动放回去（笔画笔，手指翻页）
        touchAction: active ? (penSeen ? 'pan-y' : 'none') : 'auto',
        cursor: active ? (tool === 'eraser' ? 'cell' : 'crosshair') : 'auto',
      }}
    />
  );
};

export default DraftLayer;

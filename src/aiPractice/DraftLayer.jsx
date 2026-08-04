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

// ---- 双指翻页 ----
// 批注模式下 canvas 必须 touch-action: none，不能只关横向：iPadOS 的 touch-action
// 对 Apple Pencil 和手指一视同仁，只要留着 pan-y，竖着写的那一笔就会被判成滚页
// （横着划反而画得出来，所以症状是"写不了字，一写页面就跑"）。手势一旦交给合成器，
// preventDefault 也拿不回来。于是浏览器手势全部关掉，翻页这件事自己做。
//
// 翻页坚持要两根手指：写字时手掌、小指压在屏幕上都是单点接触，跟"想翻页的手指"
// 在事件层面分不出来，只靠落笔冷却挡不干净 —— 字与字之间抬笔挪手的那一下就够
// 页面窜出去了。两指才滚，手掌就再也顶不动页面。
const FLICK_DECAY = 0.94; // 每帧衰减，甩一下有点惯性才像原生滚动
const FLICK_MIN_V = 0.02; // px/ms，低于这个速度就停

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

  // 翻页要两根手指。写字时手掌、小指搭在屏幕上都是单点接触，跟"想翻页的手指"
  // 从事件上分不出来（Safari 也不一定给得出接触面尺寸），只靠冷却时间挡不干净：
  // 字与字之间抬笔挪手的那一下就够页面窜出去。改成两指才滚，手掌就再也顶不动了。
  const touchesRef = useRef(new Map()); // pointerId -> clientY
  const panRef = useRef(null);
  const flickRef = useRef(0);

  const avgTouchY = () => {
    const ys = [...touchesRef.current.values()];
    return ys.reduce((a, b) => a + b, 0) / (ys.length || 1);
  };

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

  // 批注期间整页禁选，挡掉 Pencil 拖拽选字和手掌长按弹出的系统菜单
  useEffect(() => {
    if (!active) return undefined;
    document.body.classList.add('draft-annotating');
    return () => document.body.classList.remove('draft-annotating');
  }, [active]);

  const endPan = () => {
    const pan = panRef.current;
    panRef.current = null;
    if (pan && Math.abs(pan.v) > FLICK_MIN_V && performance.now() - pan.t < 100) {
      startFlick(pan.host, pan.v);
    }
  };

  const redrawRef = useRef(null);

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
    // 正在写的那一笔也要补回来：重绘是抬笔后 setState 引发的，等它真正执行时，
    // 写得快的人早就落下了下一笔 —— 少了这一句，清屏就把新笔画擦掉半截，
    // 表现成"快写就写不出，得停一下才行"。
    if (liveRef.current) paintStroke(ctx, liveRef.current, w);
  }, [strokes]);

  useEffect(() => {
    redrawRef.current = redraw;
  }, [redraw]);

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
      redrawRef.current();
    };

    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(canvas);
    return () => ro.disconnect();
    // 只在挂载时装一次：redraw 的身份每提交一笔就变，跟着它走的话
    // 每写一笔都要拆装一次 ResizeObserver，白花销。重绘改走 ref 取最新的。
  }, []);

  // 刚提交的那一笔是边写边落在画布上的，画面已经是对的，没必要清屏重来一遍 ——
  // 而那次重绘偏偏发生在用户已经起下一笔的时刻，纯属添乱。撤销、清空、换题
  // 这些情况下末尾对不上，照常整层重绘。
  const committedRef = useRef(null);
  useEffect(() => {
    const list = strokes || [];
    if (committedRef.current && list[list.length - 1] === committedRef.current) {
      committedRef.current = null;
      return;
    }
    redraw();
  }, [strokes, redraw]);

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
      if (!penSeenRef.current) {
        penSeenRef.current = true;
        savePenSeen();
      }
      // 笔落下来了，先前搭在屏幕上的那些接触点都是手，别让它们继续滚页
      touchesRef.current.clear();
      panRef.current = null;
      cancelAnimationFrame(flickRef.current);
    }

    // Pencil 出现过之后，手指就专职当翻页手，不再落墨
    if (e.pointerType === 'touch' && penSeenRef.current) {
      touchesRef.current.set(e.pointerId, e.clientY);
      // 笔正压着说明是写字时的手掌，等笔抬起来再说
      if (liveRef.current) return;
      if (touchesRef.current.size === 2) {
        cancelAnimationFrame(flickRef.current); // 滑动中再按下：先刹住
        panRef.current = {
          host: scrollHost(canvasRef.current),
          y: avgTouchY(),
          t: performance.now(),
          v: 0,
        };
      }
      return;
    }

    e.preventDefault();
    // 上一笔要是已经拖出了选区，先清掉，否则那个蓝块和弹出菜单会一直盖在题干上
    try { window.getSelection()?.removeAllRanges(); } catch { /* 无关紧要 */ }
    try { canvasRef.current.setPointerCapture(e.pointerId); } catch { /* 拿不到捕获就算了 */ }

    const kind = kindOf();
    liveRef.current = { k: kind, c: kind === 'hl' ? HL_COLOR : color, pts: [pointOf(e)] };
    // 单点也要留个墨点，不然轻点一下什么都没有
    const ctx = ctxRef.current;
    if (ctx) paintStroke(ctx, liveRef.current, sizeRef.current.w);
  };

  // 把一个采样点接到当前笔画上并补画那一小段
  const appendPoint = (src) => {
    const live = liveRef.current;
    if (!live) return;
    const pt = pointOf(src);
    const prev = live.pts[live.pts.length - 1];
    // 抽掉挤在一起的采样点：高刷屏会塞进大量几乎重复的坐标
    const w = sizeRef.current.w || 1;
    if (Math.hypot((pt[0] - prev[0]) * w, (pt[1] - prev[1]) * w) < 0.7) return;
    live.pts.push(pt);
    // 只补最新那一段，整层重绘留给撤销/换题
    const ctx = ctxRef.current;
    if (ctx) paintStroke(ctx, { ...live, pts: [prev, pt] }, w);
  };

  const onPointerMove = (e) => {
    if (!active) return;

    if (e.pointerType === 'touch' && touchesRef.current.has(e.pointerId)) {
      touchesRef.current.set(e.pointerId, e.clientY);
      const pan = panRef.current;
      if (!pan || touchesRef.current.size < 2) return;
      // 取所有接触点的平均位置：中途多搭上一根手指也不会让页面跳一下
      const y = avgTouchY();
      const dy = pan.y - y; // 手指往上推 → 内容往上走 → scrollTop 变大
      scrollHostBy(pan.host, dy);
      const now = performance.now();
      const dt = now - pan.t;
      if (dt > 0) pan.v = dy / dt;
      pan.y = y;
      pan.t = now;
      return;
    }

    if (!liveRef.current || e.pointerType === 'touch') return;
    e.preventDefault();

    // Pencil 是 120Hz 采样，而 pointermove 最多一帧一个：浏览器会把这一帧里的
    // 若干采样合并成一个事件交上来，主线程越忙合并得越狠。只用事件本身等于把中间
    // 的采样全丢掉，慢慢写看不出来，一连笔就缺胳膊少腿。这些点都在 getCoalescedEvents
    // 里，取出来逐个补上，笔迹才跟手。
    const nat = e.nativeEvent;
    const merged =
      typeof nat?.getCoalescedEvents === 'function' ? nat.getCoalescedEvents() : null;
    if (merged && merged.length > 1) {
      for (const m of merged) appendPoint(m);
    } else {
      appendPoint(e);
    }
  };

  const endStroke = (e) => {
    const live = liveRef.current;
    liveRef.current = null;
    committedRef.current = live;
    if (e) {
      try { canvasRef.current?.releasePointerCapture(e.pointerId); } catch { /* 同上 */ }
    }
    if (live) onStrokeEnd?.(live);
  };

  const onPointerUp = (e) => {
    if (!active) return;
    if (e.pointerType === 'touch') {
      touchesRef.current.delete(e.pointerId);
      if (panRef.current && touchesRef.current.size < 2) endPan();
      return;
    }
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
        // 同理：不让 Pencil 的拖拽被当成选字，也不弹 iPadOS 的长按菜单
        userSelect: 'none',
        WebkitUserSelect: 'none',
        WebkitTouchCallout: 'none',
        cursor: active ? (tool === 'eraser' ? 'cell' : 'crosshair') : 'auto',
      }}
    />
  );
};

export default DraftLayer;

// 草稿纸 canvas 组件
//
// 全屏浮层：点开铺满整个屏幕，提交时把整张草稿图发给 Hermes 分析。
// 必须 portal 到 body —— 外层 <main> 带 backdrop-blur，会生成 containing
// block，在它内部写 fixed inset-0 只铺满 main，铺不满屏幕。
//
// 组件常驻挂载，用 display 切显隐：卸载会把 canvas 位图一起丢掉，而真实流程是
// 「写草稿 → 关掉草稿纸 → 点提交」，提交那一刻还要把这张图读出来。
//
// 用法：
//   const draftRef = useRef();
//   <DraftCanvas ref={draftRef} show={showDraft} onClose={() => setShowDraft(false)} />
//   const dataUrl = draftRef.current?.capture();   // 空白返回 null
//   draftRef.current?.clear();                     // 换题时清空

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Eraser, PenTool, Trash2 } from 'lucide-react';

const MIN_LINE_W = 1.5;
const MAX_LINE_W = 6;
const ERASER_SIZE = 24;

const DraftCanvas = forwardRef(function DraftCanvas({ show, onClose, onDirtyChange }, ref) {
  const canvasRef = useRef(null);
  const ctxRef = useRef(null);
  const drawing = useRef(false);
  // 见过 Apple Pencil 之后就不再理手指：写字时手掌搭在屏幕上不该画出线。
  // 但没笔的用户得能用手指画，否则草稿纸对他们完全没法用。
  const penSeen = useRef(false);
  const [tool, setTool] = useState('pen');
  const [hasStrokes, setHasStrokes] = useState(false);

  // canvas 位图尺寸跟随显示尺寸 × DPR。iPad 是 2x 屏，不乘 DPR 线条会发虚。
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resize = () => {
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      if (!w || !h) return;                      // 隐藏时尺寸为 0，跳过
      const dpr = window.devicePixelRatio || 1;
      const nextW = Math.round(w * dpr);
      const nextH = Math.round(h * dpr);
      if (canvas.width === nextW && canvas.height === nextH) return;

      // 改 canvas.width/height 会清空位图，先备份笔迹再画回去
      let snapshot = null;
      if (canvas.width && canvas.height) {
        snapshot = document.createElement('canvas');
        snapshot.width = canvas.width;
        snapshot.height = canvas.height;
        snapshot.getContext('2d').drawImage(canvas, 0, 0);
      }

      canvas.width = nextW;
      canvas.height = nextH;
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);    // 之后都用 CSS 像素坐标画
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      if (snapshot) {
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(snapshot, 0, 0, snapshot.width, snapshot.height, 0, 0, nextW, nextH);
        ctx.restore();
      }
      ctxRef.current = ctx;
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, []);

  // 显隐切换时补一次 resize：隐藏状态下 offsetWidth 为 0，测不出真实尺寸
  useEffect(() => {
    if (!show) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    const dpr = window.devicePixelRatio || 1;
    if (w && h && (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr))) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctxRef.current = ctx;
    }
  }, [show]);

  // Esc 关闭：全屏浮层没有别的退路时的兜底
  useEffect(() => {
    if (!show) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [show, onClose]);

  // 有没有笔迹要告诉父组件：草稿纸收起来之后，题目页上的「草稿」按钮得能显示
  // 「这题已经写了草稿、提交时会发去分析」，否则用户不知道草稿还在。
  useEffect(() => {
    onDirtyChange?.(hasStrokes);
  }, [hasStrokes, onDirtyChange]);

  // ---- Pointer Events ----
  const getXY = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  };

  // 手指是否该忽略：见过笔就把手指当误触（掌托）
  const ignorePointer = (e) => e.pointerType === 'touch' && penSeen.current;

  const applyStyle = (ctx, pressure) => {
    if (tool === 'pen') {
      ctx.strokeStyle = '#1a1a1a';
      ctx.globalCompositeOperation = 'source-over';
      ctx.lineWidth = MIN_LINE_W + pressure * (MAX_LINE_W - MIN_LINE_W);
    } else {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.strokeStyle = 'rgba(0,0,0,1)';
      ctx.lineWidth = ERASER_SIZE;
    }
  };

  const onPointerDown = (e) => {
    if (e.pointerType === 'pen') penSeen.current = true;
    if (ignorePointer(e)) return;
    e.preventDefault();
    try { canvasRef.current.setPointerCapture(e.pointerId); } catch { /* */ }
    drawing.current = true;
    const ctx = ctxRef.current;
    if (!ctx) return;
    const [x, y] = getXY(e);
    applyStyle(ctx, e.pressure > 0 ? e.pressure : 0.5);
    ctx.beginPath();
    ctx.moveTo(x, y);
    // 单点点击也留下一个点，而不是什么都没有
    ctx.lineTo(x + 0.01, y);
    ctx.stroke();
    setHasStrokes(true);
  };

  const onPointerMove = (e) => {
    if (!drawing.current || ignorePointer(e)) return;
    e.preventDefault();
    const ctx = ctxRef.current;
    if (!ctx) return;
    const [x, y] = getXY(e);
    applyStyle(ctx, e.pressure > 0 ? e.pressure : 0.5);
    ctx.lineTo(x, y);
    ctx.stroke();
    // 压感要逐段生效，所以每段重新开路径
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const onPointerUp = (e) => {
    if (ignorePointer(e)) return;
    drawing.current = false;
    try { canvasRef.current?.releasePointerCapture(e.pointerId); } catch { /* */ }
  };

  const wipe = () => {
    const canvas = canvasRef.current;
    const ctx = ctxRef.current;
    if (!canvas || !ctx) return;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = 'source-over';
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
    setHasStrokes(false);
  };

  // ---- 暴露给父组件 ----
  useImperativeHandle(ref, () => ({
    // 画布是透明底的，黑笔迹直接导出给模型看会糊成一片，先垫白底再拍
    capture() {
      const canvas = canvasRef.current;
      if (!canvas || !hasStrokes || !canvas.width || !canvas.height) return null;
      const flat = document.createElement('canvas');
      flat.width = canvas.width;
      flat.height = canvas.height;
      const fctx = flat.getContext('2d');
      fctx.fillStyle = '#ffffff';
      fctx.fillRect(0, 0, flat.width, flat.height);
      fctx.drawImage(canvas, 0, 0);
      return flat.toDataURL('image/png');
    },
    clear: wipe,
    hasContent() { return hasStrokes; },
  }), [hasStrokes]);

  const overlay = (
    <div
      className="fixed inset-0 z-[9999] flex flex-col bg-white"
      style={{ display: show ? 'flex' : 'none' }}
      aria-hidden={!show}
    >
      {/* 工具栏 */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-black/10 bg-white flex-shrink-0"
        style={{ paddingTop: 'max(0.75rem, env(safe-area-inset-top))' }}
      >
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => setTool('pen')}
            className={`flex items-center space-x-1.5 px-3.5 py-2.5 rounded-xl text-xs font-black transition-colors ${
              tool === 'pen' ? 'bg-[#1a1a1a] text-[#fbc02d]' : 'text-[#999] hover:bg-black/5'
            }`}
          >
            <PenTool size={14} />
            <span>铅笔</span>
          </button>
          <button
            type="button"
            onClick={() => setTool('eraser')}
            className={`flex items-center space-x-1.5 px-3.5 py-2.5 rounded-xl text-xs font-black transition-colors ${
              tool === 'eraser' ? 'bg-[#1a1a1a] text-white' : 'text-[#999] hover:bg-black/5'
            }`}
          >
            <Eraser size={14} />
            <span>橡皮</span>
          </button>
          <button
            type="button"
            onClick={wipe}
            className="flex items-center space-x-1.5 px-3.5 py-2.5 rounded-xl text-xs font-black text-[#999] hover:bg-black/5 hover:text-[#ef5350] transition-colors"
          >
            <Trash2 size={14} />
            <span>清空</span>
          </button>
        </div>

        <div className="flex items-center space-x-3">
          <span className="hidden sm:block text-[10px] font-black uppercase tracking-widest text-[#bbb]">
            {hasStrokes ? '提交答案时自动发给 Hermes 分析' : '在这里演算'}
          </span>
          {/* 全屏之后 X 太小不好点，用「写好了」明确收起 */}
          <button
            type="button"
            onClick={onClose}
            className="flex items-center space-x-1.5 bg-[#fbc02d] text-black px-4 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest hover:bg-[#1a1a1a] hover:text-white transition-colors"
          >
            <Check size={14} />
            <span>写好了</span>
          </button>
        </div>
      </div>

      {/* canvas 区域：touch-none 关掉浏览器手势，否则画一笔会连带滚动/缩放 */}
      <canvas
        ref={canvasRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className="flex-1 w-full touch-none block"
        style={{ cursor: tool === 'eraser' ? 'cell' : 'crosshair' }}
      />
    </div>
  );

  return createPortal(overlay, document.body);
});

export default DraftCanvas;

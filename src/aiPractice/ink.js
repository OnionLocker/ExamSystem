// 草稿笔迹的绘制：做题时的画布（DraftLayer）和交卷截图（captureNode）共用同一套画法，
// 两边画出来才一模一样。

export const DEFAULT_PEN_MIN_W = 1.2;
export const DEFAULT_PEN_MAX_W = 7.0;
const HL_W = 16;
const ERASER_W = 28;
const HL_ALPHA = 0.32;
export const HL_COLOR = '#8d7348';

const strokeWidth = (kind) => (kind === 'hl' ? HL_W : ERASER_W);

// Pencil 日常书写的压力集中在 0.1~0.6，很少压到 1：线性映射的话粗的那半档永远用不上。
// 把 0.65 当作"压到底"，再微微上弯，轻写/正常/用力三档拉得开。
const easePressure = (p) => Math.min(1, p / 0.65) ** 0.8;

// 钢笔按 signature_pad 的思路一小段一小段画：每段是一条圆头线，线宽取该点压力，
// 路径走相邻采样点的中点、以采样点为控制点的二次曲线，转折处才圆滑。
// 不用"整笔算一个外轮廓再填充"（perfect-freehand 那种）：轮廓在抖动处会自交，
// iPad 上填出来笔画里会露出一个个小三角。各段各自描边、颜色不透明，叠在一起没有缝。
//
// 第 k 段：k = 0 从起点到 0、1 的中点；中间段从 k-1、k 的中点经 k 到 k、k+1 的中点；
// k = n-1 是收尾，从倒数两点的中点落到终点（只有收笔后才画）。
export const penSegment = (ctx, pts, k, w, penMinW, penMaxW) => {
  const n = pts.length;
  const at = (i) => [pts[i][0] * w, pts[i][1] * w];
  const mid = (i) => [(pts[i][0] + pts[i + 1][0]) * w / 2, (pts[i][1] + pts[i + 1][1]) * w / 2];
  ctx.lineWidth = penMinW + easePressure(pts[k][2] ?? 0.5) * (penMaxW - penMinW);
  ctx.beginPath();
  if (k === 0) {
    ctx.moveTo(...at(0));
    ctx.lineTo(...mid(0));
  } else if (k === n - 1) {
    ctx.moveTo(...mid(n - 2));
    ctx.lineTo(...at(n - 1));
  } else {
    ctx.moveTo(...mid(k - 1));
    ctx.quadraticCurveTo(...at(k), ...mid(k));
  }
  ctx.stroke();
};

export const penStyle = (ctx, color) => {
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.globalCompositeOperation = 'source-over';
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
};

export const penDot = (ctx, pt, w, penMinW, penMaxW) => {
  const r = (penMinW + easePressure(pt[2] ?? 0.5) * (penMaxW - penMinW)) / 2;
  ctx.beginPath();
  ctx.arc(pt[0] * w, pt[1] * w, r, 0, Math.PI * 2);
  ctx.fill();
};

export const clearCanvas = (ctx) => {
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = 'source-over';
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.restore();
};

// 画一整笔。w = canvas 的 CSS 宽度；点坐标存的是 x/w、y/w，乘回去就对位了。
export const paintStroke = (ctx, stroke, w, penMinW, penMaxW) => {
  const pts = stroke.pts;
  if (!pts || pts.length === 0) return;

  if (stroke.k === 'pen') {
    ctx.save();
    penStyle(ctx, stroke.c);
    if (pts.length === 1) penDot(ctx, pts[0], w, penMinW, penMaxW);
    for (let k = 0; k < pts.length && pts.length > 1; k += 1) penSegment(ctx, pts, k, w, penMinW, penMaxW);
    ctx.restore();
    return;
  }

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
    const [nx, ny] = pts[0];
    ctx.beginPath();
    ctx.arc(nx * w, ny * w, strokeWidth(stroke.k) / 2, 0, Math.PI * 2);
    ctx.fillStyle = stroke.k === 'er' ? 'rgba(0,0,0,1)' : stroke.c;
    ctx.fill();
    ctx.restore();
    return;
  }

  ctx.lineWidth = strokeWidth(stroke.k);
  ctx.beginPath();
  ctx.moveTo(pts[0][0] * w, pts[0][1] * w);
  for (let i = 1; i < pts.length; i += 1) ctx.lineTo(pts[i][0] * w, pts[i][1] * w);
  ctx.stroke();
  ctx.restore();
};

// 交卷截图时把一道题的笔迹画到快照的画布上（见 captureNode.captureSnapshot）
export const paintStrokes = (ctx, strokes, w, penMinW = DEFAULT_PEN_MIN_W, penMaxW = DEFAULT_PEN_MAX_W) => {
  for (const s of strokes || []) paintStroke(ctx, s, w, penMinW, penMaxW);
};

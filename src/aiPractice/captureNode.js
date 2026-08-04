// 把一段 DOM（题目卡 + 批注层 + 演算区）栅格化成一张图。
//
// 草稿纸的意义在于「连题目一起圈划」，所以发给 Hermes 的必须是带题面的整页快照，
// 而不是一张脱离上下文的笔迹图 —— 模型看不到我圈了哪句话，就没法说我哪一步偏了。
//
// html2canvas-pro 而不是 html2canvas：Tailwind v4 的调色板是 oklch()，
// 老版 html2canvas 解析不了现代颜色函数，截出来一片黑。
//
// 库有 ~1MB，动态 import，别让不开草稿纸的人也下载。

let loader = null;
const load = () => {
  if (!loader) loader = import('html2canvas-pro').then((m) => m.default || m);
  return loader;
};

// 提前把库拉下来：用户点开批注模式时就预热，真正截图那一刻不用等网络
export const warmUpCapture = () => { load().catch(() => {}); };

const MAX_PX = 1600;

export async function captureNode(node) {
  if (!node) return null;
  const cssW = node.offsetWidth;
  if (!cssW) return null;

  try {
    const html2canvas = await load();
    // 题面是要给模型读的，分辨率太低会认错字；但也别无脑 2x 撑出好几 MB
    const scale = Math.max(1, Math.min(2, MAX_PX / cssW));
    const canvas = await html2canvas(node, {
      backgroundColor: '#ffffff',
      scale,
      useCORS: true,
      logging: false,
      // 浮动工具栏、悬浮提示这类东西不该出现在草稿纸上
      ignoreElements: (el) => el.dataset?.captureIgnore === '1',
      // 答题时笔迹在屏幕上是收起来的（opacity: 0），但存档快照必须带上。
      // 只在克隆出来的那份 DOM 里把它显回去：屏幕不会闪，
      // 而且只改 opacity 不动布局，克隆里的 canvas 尺寸跟屏幕上一模一样，笔迹不会被拉变。
      onclone: (doc) => {
        doc.querySelectorAll('[data-capture-reveal="1"]').forEach((el) => {
          el.style.opacity = '1';
          el.style.visibility = 'visible';
        });
      },
    });
    return canvas.toDataURL('image/png');
  } catch (err) {
    console.warn('[draft] 草稿纸截图失败', err);
    return null;
  }
}

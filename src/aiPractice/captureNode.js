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

const PAPER = '#f2e4c4'; // 与 index.css --color-white 同一张纸，别写成 #ffffff

const paperColorOf = (node) => {
  const bg = node ? getComputedStyle(node).backgroundColor : '';
  return bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)' ? bg : PAPER;
};

const contentHeightOf = (node) => {
  const blocks = [...node.querySelectorAll('[data-draft-content]')];
  const fromMarks = blocks.reduce((h, el) => Math.max(h, el.scrollHeight || 0), 0);
  return fromMarks || node.scrollHeight || node.offsetHeight || 0;
};

// 活着的选项行尺寸拷到副本上，并把 <button> 换成 <div>。
// html2canvas 在 iPad Safari 上几乎不画 form 控件；副本再挂到屏幕外，flex 按钮还会
// 收成 A420 那种小胶囊，跟做题页上的整行选项对不上。
const freezeOptionRows = (liveRoot, cloneRoot) => {
  const from = liveRoot.querySelectorAll('[data-option-row]');
  const to = cloneRoot.querySelectorAll('[data-option-row]');
  from.forEach((src, i) => {
    const dst = to[i];
    if (!dst) return;
    const div = document.createElement('div');
    for (const attr of dst.attributes) div.setAttribute(attr.name, attr.value);
    while (dst.firstChild) div.appendChild(dst.firstChild);
    div.style.display = 'flex';
    div.style.alignItems = 'flex-start';
    div.style.boxSizing = 'border-box';
    div.style.flexShrink = '0';
    div.style.width = `${src.offsetWidth}px`;
    div.style.minWidth = `${src.offsetWidth}px`;
    div.style.height = `${src.offsetHeight}px`;
    div.style.minHeight = `${src.offsetHeight}px`;
    dst.replaceWith(div);
  });
};

// 把节点当前的样子原地复制一份，好让截图在后台慢慢跑。
//
// html2canvas 读的是活着的 DOM：直接把截图丢到后台，用户一翻页就会截到下一题的内容。
// 而截图在 iPad 上要几百毫秒到一秒多，让用户站在原地等一个"正在保存草稿"的圈显然不对。
// 先同步克隆一份（这一步很快，就是一次 DOM 复制），翻页立刻走，截图对着副本跑，
// 快照仍然是离开时那道题。
//
// 副本必须还在视口里（只是几乎全透明）：Safari 对 left:-99999px 的节点不排 flex，
// 选项行会塌掉。a8a6b89 把题卡改成 h-full 之后，照 offsetHeight 截会带上题面下面
// 一大块空白，所以高度仍按题面（和笔迹下沿）裁。
export const detachForCapture = (node, { minHeight = 0 } = {}) => {
  const cssW = node?.offsetWidth;
  if (!cssW) return null;

  const paperBg = paperColorOf(node);
  const captureH = Math.ceil(Math.max(contentHeightOf(node), minHeight, 1));
  const clone = node.cloneNode(true);
  clone.style.width = `${cssW}px`;
  clone.style.height = `${captureH}px`;
  clone.style.maxHeight = 'none';
  clone.style.overflow = 'hidden';
  clone.style.backgroundColor = paperBg;

  clone.querySelectorAll('[data-draft-scroll]').forEach((el) => {
    el.style.position = 'relative';
    el.style.inset = 'auto';
    el.style.overflow = 'visible';
    el.style.height = 'auto';
    el.style.maxHeight = 'none';
  });

  freezeOptionRows(node, clone);

  // cloneNode 不会搬 canvas 里的像素，笔迹得自己画过去一次。
  // 画布仍按屏幕上的尺寸摆，超出题面的空白被 overflow:hidden 裁掉，笔迹不缩放。
  const from = node.querySelectorAll('canvas');
  const to = clone.querySelectorAll('canvas');
  from.forEach((src, i) => {
    const dst = to[i];
    if (!dst || !src.width || !src.height) return;
    dst.width = src.width;
    dst.height = src.height;
    dst.style.width = `${src.offsetWidth}px`;
    dst.style.height = `${src.offsetHeight}px`;
    dst.style.position = 'absolute';
    dst.style.inset = 'auto';
    dst.style.left = '0';
    dst.style.top = '0';
    try {
      dst.getContext('2d')?.drawImage(src, 0, 0);
    } catch {
      /* 画不过来就只丢这一层笔迹，不该连截图一起废掉 */
    }
  });

  const holder = document.createElement('div');
  holder.style.cssText = `position:fixed;top:0;left:0;width:${cssW}px;height:${captureH}px;opacity:0.01;pointer-events:none;z-index:-1;background:${paperBg};`;
  holder.appendChild(clone);
  document.body.appendChild(holder);

  return { node: clone, dispose: () => holder.remove() };
};

const MAX_PX = 1600;

export async function captureNode(node) {
  if (!node) return null;
  const cssW = node.offsetWidth;
  if (!cssW) return null;

  try {
    const html2canvas = await load();
    const scale = Math.max(1, Math.min(2, MAX_PX / cssW));
    const canvas = await html2canvas(node, {
      backgroundColor: paperColorOf(node),
      scale,
      useCORS: true,
      logging: false,
      ignoreElements: (el) => el.dataset?.captureIgnore === '1',
      onclone: (doc) => {
        doc.querySelectorAll('[data-capture-reveal="1"]').forEach((el) => {
          el.style.opacity = '1';
          el.style.visibility = 'visible';
        });
        doc.querySelectorAll('[data-option-row]').forEach((el) => {
          el.style.display = 'flex';
          el.style.boxSizing = 'border-box';
        });
      },
    });
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(
        (b) => (b && b.size ? resolve(b) : reject(new Error('截图为空'))),
        'image/jpeg',
        0.72,
      );
    });
    return blob;
  } catch (err) {
    console.warn('[draft] 草稿纸截图失败', err);
    return null;
  }
}

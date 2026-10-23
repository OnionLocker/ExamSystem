// 页面不是 window 在滚，而是 App 里那个 overflow-y-auto 的内容区在滚。
// 草稿纸关掉了浏览器手势，翻页得自己找到真正滚动的那一块。
export const scrollHost = (el) => {
  let node = el?.parentElement;
  while (node) {
    const oy = getComputedStyle(node).overflowY;
    if ((oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 4) return node;
    node = node.parentElement;
  }
  return null;
};

const canScroll = (host) => host && host.scrollHeight > host.clientHeight + 4;

// 画布盖住整张卷子。左边材料、右边题目各自带 data-draft-scroll，是画布底下的兄弟，
// 不是画布的祖先。用栏的矩形对落点。能滚的优先；量不出溢出时也认这栏，
// Safari 里 flex 子项的 scrollHeight 有时会暂时等于 clientHeight。
const hostAt = (hosts, x, y) => {
  let marked = null;
  let markedArea = Infinity;
  let scrolling = null;
  let scrollingArea = Infinity;
  for (const host of hosts) {
    const r = host.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (x < r.left || x >= r.right || y < r.top || y >= r.bottom) continue;
    const area = r.width * r.height;
    if (area < markedArea) {
      marked = host;
      markedArea = area;
    }
    if (canScroll(host) && area < scrollingArea) {
      scrolling = host;
      scrollingArea = area;
    }
  }
  return scrolling || marked;
};

// 两根手指才滚。Apple Pencil 的 touchType 是 stylus，不计入。
// 不用接触面大小来筛：iPad 上指尖直径经常超过 32px，按大小滤会把两根手指都当成手掌丢掉。
export const directTouchPoints = (touches) => {
  const pts = [];
  for (const t of touches || []) {
    if (!t || t.touchType === 'stylus') continue;
    if (!Number.isFinite(t.clientX) || !Number.isFinite(t.clientY)) continue;
    pts.push({ x: t.clientX, y: t.clientY });
  }
  return pts.length >= 2 ? pts : null;
};

// 两指的中点落在哪一栏就滚哪一栏。中点落在分栏缝上时，改用其中一根手指所在的栏。
// 复盘草稿纸没有分栏，退回往父级找滚动容器。
export const scrollHostUnderPoints = (points, fallbackEl) => {
  const pts = (points || []).filter((p) => Number.isFinite(p?.x) && Number.isFinite(p?.y));
  const root = fallbackEl?.parentElement;
  const hosts = root ? [...root.querySelectorAll('[data-draft-scroll]')] : [];
  if (pts.length && hosts.length) {
    const midX = pts.reduce((sum, p) => sum + p.x, 0) / pts.length;
    const midY = pts.reduce((sum, p) => sum + p.y, 0) / pts.length;
    const mid = hostAt(hosts, midX, midY);
    if (mid) return mid;
    for (const p of pts) {
      const host = hostAt(hosts, p.x, p.y);
      if (host) return host;
    }
  }
  return scrollHost(fallbackEl);
};

export const scrollHostBy = (host, dy) => {
  if (host) host.scrollTop += dy;
  else window.scrollBy(0, dy);
};

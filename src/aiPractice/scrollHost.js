// 页面不是 window 在滚，而是 App 里那个 overflow-y-auto 的内容区在滚。
// 草稿纸关掉了浏览器手势，翻页按钮和手指平移都得先找到真正滚动的那个祖先。
export const scrollHost = (el) => {
  let node = el?.parentElement;
  while (node) {
    const oy = getComputedStyle(node).overflowY;
    if ((oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 4) return node;
    node = node.parentElement;
  }
  return null;
};

export const scrollHostBy = (host, dy) => {
  if (host) host.scrollTop += dy;
  else window.scrollBy(0, dy);
};

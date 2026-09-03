import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

export const PIP_SIZES = {
  practice: { width: 420, height: 320 },
  today: { width: 392, height: 468 },
};

export const bottomLeftBox = (width, height, pad = 10) => {
  const availLeft = Number.isFinite(window.screen?.availLeft) ? window.screen.availLeft : 0;
  const availTop = Number.isFinite(window.screen?.availTop) ? window.screen.availTop : 0;
  const availH = window.screen?.availHeight || 800;
  return {
    left: availLeft + pad,
    top: availTop + Math.max(pad, availH - height - pad),
    width,
    height,
  };
};

const copyStylesInto = (targetWin) => {
  [...document.styleSheets].forEach((sheet) => {
    try {
      if (sheet.cssRules) {
        const style = targetWin.document.createElement('style');
        style.textContent = [...sheet.cssRules].map((r) => r.cssText).join('\n');
        targetWin.document.head.appendChild(style);
      }
    } catch {
      if (sheet.href) {
        const link = targetWin.document.createElement('link');
        link.rel = 'stylesheet';
        link.href = sheet.href;
        targetWin.document.head.appendChild(link);
      }
    }
  });
  document.head.querySelectorAll('style').forEach((node) => {
    targetWin.document.head.appendChild(node.cloneNode(true));
  });
  const baseStyle = targetWin.document.createElement('style');
  baseStyle.textContent = `
    html, body { margin: 0; padding: 0; height: 100%; overflow: hidden;
      font-family: system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: #f2e4c4; }
    #pip-root { height: 100%; }
  `;
  targetWin.document.head.appendChild(baseStyle);
};

const pinBottomLeft = (win, box) => {
  const apply = () => {
    try { win.moveTo(box.left, box.top); } catch { /* PiP 多数不允许脚本挪位置 */ }
    try { win.resizeTo(box.width, box.height); } catch { /* ignore */ }
  };
  apply();
  setTimeout(apply, 60);
  setTimeout(apply, 280);
};

const mount = (win, element) => {
  const container = win.document.createElement('div');
  container.id = 'pip-root';
  win.document.body.appendChild(container);
  const root = createRoot(container);
  root.render(element);
  const unmount = () => {
    try { root.unmount(); } catch { /* ignore */ }
  };
  win.addEventListener('pagehide', unmount);
  try { win.focus(); } catch { /* ignore */ }
  return { win, root, unmount };
};

const popupFeatures = (box) => [
  `width=${box.width}`,
  `height=${box.height}`,
  `left=${Math.max(0, box.left)}`,
  `top=${Math.max(0, box.top)}`,
  'popup=yes',
  'resizable=yes',
  'scrollbars=no',
  'menubar=no',
  'toolbar=no',
  'location=no',
  'status=no',
].join(',');

const requestPip = async (width, height) => {
  if (!window.documentPictureInPicture?.requestWindow) return null;
  try {
    return await window.documentPictureInPicture.requestWindow({
      width,
      height,
      disallowReturnToOpener: true,
    });
  } catch {
    return window.documentPictureInPicture.requestWindow({ width, height });
  }
};

export async function openEmbeddedWindow({
  width,
  height,
  title = '文档',
  element,
  fallbackUrl,
}) {
  const box = bottomLeftBox(width, height);

  try {
    const pipWin = await requestPip(width, height);
    if (pipWin) {
      copyStylesInto(pipWin);
      try { pipWin.document.title = title; } catch { /* ignore */ }
      pinBottomLeft(pipWin, box);
      return mount(pipWin, element);
    }
  } catch (err) {
    console.warn('Document PiP failed, falling back to window.open:', err);
  }

  const features = popupFeatures(box);
  let winRef = window.open('about:blank', 'exam_pip_popup', features);
  if (winRef) {
    try {
      winRef.document.open();
      winRef.document.write('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>');
      winRef.document.close();
      copyStylesInto(winRef);
      winRef.document.title = title;
      pinBottomLeft(winRef, box);
      return mount(winRef, element);
    } catch (err) {
      console.warn('about:blank mount failed:', err);
      try { winRef.close(); } catch { /* ignore */ }
    }
  }

  if (fallbackUrl) {
    winRef = window.open(fallbackUrl, 'exam_pip_popup', features);
    if (winRef) {
      try { winRef.document.title = title; } catch { /* ignore */ }
      pinBottomLeft(winRef, box);
      winRef.focus();
    }
    return { win: winRef, root: null, unmount: () => {} };
  }
  return null;
}

export function openPracticePopup({ catId, subId, mode, raceSize, Practice }) {
  const { width, height } = PIP_SIZES.practice;
  const params = new URLSearchParams({
    popup: '1',
    cat: catId,
    sub: subId,
    mode: mode || 'train',
  });
  if (raceSize) params.set('n', String(raceSize));
  const fallbackUrl = `${window.location.pathname}?${params.toString()}`;
  return openEmbeddedWindow({
    width,
    height,
    title: '文档',
    fallbackUrl,
    element: createElement(Practice, {
      catId,
      subId,
      mode,
      raceSize,
      embedded: true,
    }),
  });
}

export function openTodayTasksPopup({ TodayComponent }) {
  const { width, height } = PIP_SIZES.today;
  const fallbackUrl = `${window.location.pathname}?popup=today`;
  return openEmbeddedWindow({
    width,
    height,
    title: '文档',
    fallbackUrl,
    element: createElement(TodayComponent, { embedded: true }),
  });
}

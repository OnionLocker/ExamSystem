import { api, getToken } from '../api.js';

const CACHE_NAME = 'exam-review-images-v1';
const CONCURRENCY = 2;

/** 稳定 cache key：去掉 token 查询参数，避免登录态变化导致全量失效 */
export const reviewFileCacheKey = (fileUrl) => {
  try {
    const u = new URL(fileUrl, window.location.origin);
    u.search = '';
    return u.href;
  } catch {
    return String(fileUrl).split('?')[0];
  }
};

export const withReviewToken = (url) => {
  const token = getToken();
  if (!token) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(token)}`;
};

let prefetchPromise = null;
let prefetchGeneration = 0;

const openCache = async () => {
  if (!('caches' in window)) return null;
  try {
    return await caches.open(CACHE_NAME);
  } catch {
    return null;
  }
};

/** 单张：写入 Cache API（同时暖 HTTP 缓存） */
export async function prefetchReviewImage(fileUrl) {
  if (!fileUrl || !getToken()) return false;
  const cache = await openCache();
  const key = reviewFileCacheKey(fileUrl);
  if (cache) {
    try {
      const hit = await cache.match(key);
      if (hit) return true;
    } catch {
      /* ignore */
    }
  }

  const tokenUrl = withReviewToken(fileUrl);
  try {
    const res = await fetch(tokenUrl, {
      credentials: 'same-origin',
      // 默认缓存：首次拉网，之后可被浏览器 HTTP 缓存命中
      cache: 'default',
    });
    if (!res.ok) return false;
    if (cache) {
      // 用无 query 的 key 存，方便跨 token 命中
      await cache.put(key, res.clone());
    }
    return true;
  } catch {
    return false;
  }
}

/** 若 Cache API 有图，返回 object URL（调用方负责 revoke） */
export async function getCachedObjectUrl(fileUrl) {
  const cache = await openCache();
  if (!cache || !fileUrl) return null;
  try {
    const hit = await cache.match(reviewFileCacheKey(fileUrl));
    if (!hit) return null;
    const blob = await hit.blob();
    if (!blob || blob.size === 0) return null;
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}

export async function dropCachedReviewImage(fileUrl) {
  const cache = await openCache();
  if (!cache || !fileUrl) return;
  try {
    await cache.delete(reviewFileCacheKey(fileUrl));
  } catch {
    /* ignore */
  }
}

async function mapPool(items, limit, worker) {
  const ret = new Array(items.length);
  let i = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) {
      const cur = i++;
      ret[cur] = await worker(items[cur], cur);
    }
  });
  await Promise.all(runners);
  return ret;
}

/**
 * 登录后后台预取全部复习模块图片到浏览器 Cache API。
 * 不阻塞 UI；可重复调用（同一次进行中会复用 Promise）。
 */
export function schedulePrefetchReviewImages() {
  if (!getToken()) return null;
  if (prefetchPromise) return prefetchPromise;

  const gen = ++prefetchGeneration;
  const run = async () => {
    // 让首屏先出来
    await new Promise((r) => {
      if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(() => r(), { timeout: 1200 });
      } else {
        setTimeout(r, 400);
      }
    });
    if (gen !== prefetchGeneration || !getToken()) return;

    let modules = [];
    try {
      modules = (await api('/api/review-modules')) || [];
    } catch {
      return;
    }

    const urls = [];
    for (const m of modules) {
      if (gen !== prefetchGeneration) return;
      if (!m?.id || !(m.image_count > 0)) continue;
      try {
        const rows = (await api(`/api/review-modules/${m.id}/images`)) || [];
        for (const row of rows) {
          if (row?.url) urls.push(row.url);
        }
      } catch {
        /* skip module */
      }
    }

    await mapPool(urls, CONCURRENCY, async (url) => {
      if (gen !== prefetchGeneration) return;
      await prefetchReviewImage(url);
    });
  };

  prefetchPromise = run().finally(() => {
    if (gen === prefetchGeneration) prefetchPromise = null;
  });
  return prefetchPromise;
}

/** 进入某个模块时，优先把该模块全部图（及邻张）再刷一遍 */
export async function prefetchModuleImages(fileUrls) {
  const list = (fileUrls || []).filter(Boolean);
  if (!list.length) return;
  await mapPool(list, CONCURRENCY, (url) => prefetchReviewImage(url));
}

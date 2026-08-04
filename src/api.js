const TOKEN_KEY = 'exam_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY) || '';
export const setToken = (t) => {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
};
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// 所有 401 触发的回调（在 App 里注册，用于重置为登录态）
let onUnauthorized = null;
export const setOnUnauthorized = (cb) => { onUnauthorized = cb; };

export async function api(path, { method = 'GET', body, headers } = {}) {
  const token = getToken();
  const res = await fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers || {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    clearToken();
    if (onUnauthorized) onUnauthorized();
    const err = new Error('unauthorized');
    err.status = 401;
    throw err;
  }

  const text = await res.text();

  // 后端不一定返 JSON：路由不存在时 Express 给的是一页 HTML，前面挂了反代也可能抢着返错页。
  // 直接 JSON.parse 会抛「Unexpected token '<'」，看到报错的人根本无法定位。
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      const err = new Error(
        res.ok
          ? '服务端返回了非 JSON 内容'
          : `HTTP ${res.status}（接口没返 JSON，后端可能需要重启）`,
      );
      err.status = res.status;
      err.body = text.slice(0, 200);
      throw err;
    }
  }

  if (!res.ok) {
    const err = new Error((data && data.error) || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const login = (password) => api('/api/auth/login', { method: 'POST', body: { password } });
export const logout = () => api('/api/auth/logout', { method: 'POST' }).catch(() => {});
export const checkAuth = () => api('/api/auth/check');

// 多账号额度合成。每户是独立同规格池（都是 Pro 时容量相同），
// 综合剩余 = 各户 remaining 的算术平均，等价于「总剩余 / 总容量」。
// 顶栏只看实际在用的 Gemini 池，避免把闲置的 Claude 100% 掺进来。

const GEMINI_NAME = /gemini/i;

export const avgRemaining = (values) => {
  const nums = values.filter((v) => typeof v === 'number');
  if (!nums.length) return null;
  return nums.reduce((sum, v) => sum + v, 0) / nums.length;
};

export const combineQuota = (accounts = []) => {
  const live = accounts.filter((a) => a && !a.error && Array.isArray(a.groups));
  const byGroup = new Map();

  for (const account of live) {
    for (const group of account.groups || []) {
      const name = group.name || '';
      const row = byGroup.get(name) || { name, models: group.models, windows: {} };
      for (const bucket of group.buckets || []) {
        if (typeof bucket.remaining !== 'number' || !bucket.window) continue;
        const window = row.windows[bucket.window] || {
          window: bucket.window,
          label: bucket.label,
          remainings: [],
          resetAt: null,
        };
        window.remainings.push(bucket.remaining);
        if (bucket.resetAt && (!window.resetAt || bucket.resetAt < window.resetAt)) {
          window.resetAt = bucket.resetAt;
        }
        row.windows[bucket.window] = window;
      }
      byGroup.set(name, row);
    }
  }

  const groups = [...byGroup.values()].map((row) => ({
    name: row.name,
    models: row.models,
    buckets: Object.values(row.windows).map((window) => ({
      id: `综合:${row.name}:${window.window}`,
      window: window.window,
      label: window.label,
      remaining: avgRemaining(window.remainings),
      resetAt: window.resetAt,
      accounts: window.remainings.length,
    })),
  }));

  const preferred =
    groups.find((group) => GEMINI_NAME.test(group.name))
    || groups[0]
    || null;
  const headline = preferred
    ? ['5h', 'weekly']
      .map((window) => (preferred.buckets || []).find((bucket) => bucket.window === window))
      .filter((bucket) => bucket && bucket.remaining != null)
    : [];

  return {
    accountCount: live.length,
    groups,
    preferred,
    headline,
  };
};

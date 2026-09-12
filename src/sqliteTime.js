// SQLite datetime('now') / CURRENT_TIMESTAMP 是 UTC，且不带时区。
// 少数导入会把北京时间墙钟直接写进去。有时区的按原样读；
// 无时区的先当 UTC，若因此落到未来，再按本地墙钟（服务器在上海）。

const HAS_TZ = /[zZ]|[+-]\d{2}:?\d{2}$/;

export function parseSqliteTime(raw) {
  const value = String(raw || '').trim();
  if (!value) return NaN;
  if (HAS_TZ.test(value)) {
    const ms = new Date(value).getTime();
    return Number.isFinite(ms) ? ms : NaN;
  }
  const normalized = value.includes('T') ? value : value.replace(' ', 'T');
  const utc = Date.parse(`${normalized}Z`);
  if (Number.isFinite(utc) && utc <= Date.now() + 120000) return utc;
  const local = Date.parse(normalized);
  return Number.isFinite(local) ? local : NaN;
}

export function sqliteTimeIso(raw) {
  const ms = parseSqliteTime(raw);
  return Number.isFinite(ms) ? new Date(ms).toISOString() : '';
}

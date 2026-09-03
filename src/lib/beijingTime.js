export const SQL_NOW = "datetime('now', '+8 hours')";

export function east8Today(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

export function beijingNow(now = new Date()) {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).format(now).replace('T', ' ');
}

export function parseBeijingMs(value) {
  if (value == null || value === '') return Number.NaN;
  const text = String(value).trim();
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(text)) return new Date(text).getTime();
  const iso = text.includes('T') ? text : text.replace(' ', 'T');
  return new Date(`${iso}+08:00`).getTime();
}

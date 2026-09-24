// Canonical exam answers: judge A=true/B=false; multi is an ordered set.
export function normalizeAnswer(value, type = 'single') {
  const text = (Array.isArray(value) ? value.join('') : String(value ?? '')).trim().toUpperCase();
  if (type === 'judge') return ({ T: 'A', F: 'B', TRUE: 'A', FALSE: 'B', 对: 'A', 正确: 'A', 错: 'B', 错误: 'B' })[text] ?? text;
  if (type === 'multi' && /^[A-E]+$/.test(text)) return [...new Set(text)].sort().join('');
  return text;
}

export function judgeOptions(options) {
  if (Array.isArray(options) && options.length >= 2) return options.map(o => ({ ...o, key: normalizeAnswer(o.key, 'judge') }));
  return [{ key: 'A', text: '正确', images: [] }, { key: 'B', text: '错误', images: [] }];
}

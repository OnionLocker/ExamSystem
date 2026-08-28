const POWER = /\^(\([^)]+\)|\w+)/g;
const SUB = /_(\([^)]+\)|\w+)/g;

export function decorateMath(text) {
  const raw = String(text || '').replace(/^\|\s*/, '').trim();
  if (!raw || raw.includes('$')) return raw;
  const split = raw.search(/[：:]/);
  const label = split >= 0 ? raw.slice(0, split + 1) : '';
  const body = split >= 0 ? raw.slice(split + 1).trim() : raw;
  if (!/[\^_]/.test(body)) return raw;
  const math = body.replace(POWER, '^{$1}').replace(SUB, '_{$1}');
  return label ? `${label} $${math}$` : `$${math}$`;
}

const list = (items, ordered) => (items || [])
  .map((item, index) => {
    const line = decorateMath(item);
    return line ? `${ordered ? `${index + 1}.` : '-'} ${line}` : '';
  })
  .filter(Boolean)
  .join('\n\n');

export function cardToMarkdown(view) {
  const parts = [];
  if (view?.steps?.length) parts.push(`#### 怎么做\n\n${list(view.steps, true)}`);
  if (view?.know?.length) parts.push(`#### 要记住\n\n${list(view.know, false)}`);
  if (view?.ban?.length) parts.push(`#### 禁止\n\n${list(view.ban, false)}`);
  if (view?.anchors?.length) parts.push(`#### 真题锚点\n\n${list(view.anchors, false)}`);
  return parts.join('\n\n');
}

// 原题里挤在一行的 A/B/C/D 才拆开；语句排序的①②③同样拆开。
// 「原题」只是引用块标记，展示时去掉。
// 日练复盘对错分流、建议用时、空诊断后处理见 reviewSpec.js / reviewAssembler.js。
// 题干「A、B、C三个地点」用顿号；「地点A.B.C.D」后面不是汉字，都不要拆。
// 只拆问句之后的选项，避免把题干里的 A. 甲地拆成选项。

const OPTION_LABEL = /(?:\*\*)?([A-D])(?:[.．、])(?:\*\*)?(?:[ \t]+|(?=[\u4e00-\u9fff]))/g;

const PROMPT = /(?:由此可以推出|由此可知|可以推出的是|无法推出的是|不能推出的是|根据以上(?:资料|材料)|根据上述(?:资料|材料)|能够从上述资料中推出的是|填入画横线部分最恰当的一项是|应填入画横线部分最恰当的一项是|将以上\s*\d*\s*个句子重新排列|语序正确的是|下列哪个正确|下列(?:说法|选项|分析)?(?:中)?(?:正确|错误|不正确)的是|以下(?:选项)?(?:如果为真，)?最(?:能|不能)[^。：:]{0,24}|最能削弱|最能加强)[:：]?/g;

const CIRCLED = /[①-⑳]/g;

function optionMatches(text) {
  return [...String(text).matchAll(new RegExp(OPTION_LABEL.source, 'g'))];
}

function promptEnd(text) {
  let end = -1;
  for (const match of String(text).matchAll(new RegExp(PROMPT.source, 'g'))) {
    end = match.index + match[0].length;
  }
  return end;
}

export function splitStemOptions(text) {
  const src = String(text || '');
  const matches = optionMatches(src);
  if (matches.length < 2) return null;

  const cut = promptEnd(src);
  let from = cut >= 0 ? cut : -1;
  if (from < 0) {
    const letters = matches.map((match) => match[1]).join('');
    const clustered = letters.lastIndexOf('ABCD');
    if (clustered < 0) return null;
    const start = matches[clustered];
    const prev = start.index > 0 ? src[start.index - 1] : '\n';
    if (prev && prev !== '\n') return null;
    from = start.index;
  }

  const tail = matches.filter((match) => match.index >= from);
  if (!tail.some((match) => match[1] === 'A') || new Set(tail.map((match) => match[1])).size < 2) {
    return null;
  }

  const chunks = tail.map((match, index) => {
    const end = index + 1 < tail.length ? tail[index + 1].index : src.length;
    return {
      letter: match[1],
      body: src.slice(match.index + match[0].length, end).replace(/\s+$/g, '').trim(),
    };
  }).filter((chunk) => chunk.body);
  if (chunks.length < 2) return null;
  return { head: src.slice(0, tail[0].index), chunks };
}

export function stripYuanTiLabel(text) {
  return String(text || '')
    .replace(/^\s*\*\*原题\*\*\s*/m, '')
    .replace(/^\s*原题\s*$/m, '')
    .replace(/^\s*原题(?=[①-⑳\s]|$)/, '');
}

function peelOrderTail(body) {
  const src = String(body || '');
  const marked = src.match(/^(.*?)([。！？])\s*(将以上[\s\S]+)$/);
  if (marked) return { body: `${marked[1]}${marked[2]}`.trim(), tail: marked[3].trim() };
  const loose = src.match(/^(.*?[^\s])\s+(将以上[\s\S]+)$/);
  if (loose && /[\u4e00-\u9fff]{4,}/.test(loose[1])) {
    return { body: loose[1].trim(), tail: loose[2].trim() };
  }
  return { body: src.replace(/\s+/g, ' ').trim(), tail: '' };
}

export function splitOrderingSentences(text) {
  const src = String(text || '');
  const matches = [...src.matchAll(new RegExp(CIRCLED.source, 'g'))];
  if (matches.length < 2) return null;

  const parts = matches.map((match, index) => ({
    mark: match[0],
    body: src.slice(match.index + match[0].length, index + 1 < matches.length ? matches[index + 1].index : src.length),
    index: match.index,
  }));
  const real = parts.filter((part) => /[\u4e00-\u9fff]{4,}/.test(part.body));
  if (real.length < 2) return null;

  const first = real[0];
  const last = real[real.length - 1];
  let tail = '';
  const items = parts
    .filter((part) => part.index >= first.index && part.index <= last.index)
    .map((part, index, all) => {
      let body = part.body;
      if (index === all.length - 1) {
        const peeled = peelOrderTail(body);
        body = peeled.body;
        tail = peeled.tail;
      }
      return { mark: part.mark, body: body.replace(/\s+/g, ' ').trim() };
    })
    .filter((part) => part.body);
  if (items.length < 2) return null;
  return { head: src.slice(0, first.index), items, tail };
}

function asQuoteLine(line) {
  return `> ${line}`.replace(/> $/, '>');
}

function quoteLines(text) {
  const trimmed = String(text || '').replace(/\s+$/g, '');
  if (!trimmed.trim()) return [];
  return trimmed.split('\n').map((line) => asQuoteLine(line));
}

function formatQuestionBlock(text, suffix) {
  const stripped = stripYuanTiLabel(text);
  const split = splitStemOptions(stripped);
  const stem = split ? split.head : stripped;
  const order = splitOrderingSentences(stem);
  const lines = [];

  if (order) {
    lines.push(...quoteLines(order.head));
    for (const item of order.items) {
      if (lines.length) lines.push('>');
      lines.push(asQuoteLine(`${item.mark} ${item.body}`));
    }
    if (order.tail.trim()) {
      if (lines.length) lines.push('>');
      lines.push(...quoteLines(order.tail.trim()));
    }
  } else {
    lines.push(...quoteLines(stem));
  }

  if (split) {
    if (lines.length) lines.push('>');
    for (const chunk of split.chunks) {
      lines.push(`> **${chunk.letter}.** ${chunk.body}`);
    }
  }

  if (!lines.length) return suffix;
  return `${lines.join('\n')}${suffix}`;
}

export function looksLikeQuestionStem(text) {
  return /原题|由此可以推出|由此可知|将以上|语序正确|重新排列|下列哪个正确|最恰当的一项是/.test(String(text || ''));
}

export function isOrderingStem(text) {
  return /将以上|语序正确的是|重新排列/.test(String(text || ''));
}

const MATH_SEGMENT = /\$\$[\s\S]+?\$\$|\$[^$\n]+\$/g;
const PHYS_LETTER = '[RIUPVFamgEWFQ]';

function wrapMathCjk(inner) {
  return String(inner).replace(/\\text\{[^}]*\}|[\u4e00-\u9fff]+/g, (token) => (
    token.startsWith('\\text') ? token : `\\text{${token}}`
  ));
}

function fixMathSubscripts(inner) {
  return wrapMathCjk(String(inner)
    .replace(/(?<![\\_])\b([PUI])R(\d+)\b/g, '$1_{R_$2}')
    .replace(new RegExp(`\\{(${PHYS_LETTER})(\\d+)\\}`, 'g'), '{$1_$2}')
    .replace(new RegExp(`(?<![\\\\A-Za-z_])(${PHYS_LETTER})(\\d+)(?!\\d)`, 'g'), '$1_$2'));
}

function mapMathSegments(src, onMath, onText) {
  let last = 0;
  let out = '';
  for (const match of String(src).matchAll(MATH_SEGMENT)) {
    out += onText(src.slice(last, match.index));
    const token = match[0];
    const fence = token.startsWith('$$') ? '$$' : '$';
    out += `${fence}${onMath(token.slice(fence.length, token.length - fence.length))}${fence}`;
    last = match.index + token.length;
  }
  return out + onText(src.slice(last));
}

const plainSubRe = () => /(?<![\\$])([A-Za-zρΩμ])_([甲乙丙丁戊己庚辛]+|\d+)/g;

export function collapseMaterialBlankLines(raw = '') {
  return String(raw ?? '')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]*\n(?:[ \t]*\n)+/g, '\n')
    .replace(/^\n+|\n+$/g, '');
}

export function formatPlainSubscripts(raw = '', { collapseBlank = false } = {}) {
  let src = collapseBlank ? collapseMaterialBlankLines(raw) : String(raw ?? '');
  const parts = [];
  let last = 0;
  for (const match of src.matchAll(plainSubRe())) {
    if (match.index > last) parts.push({ type: 'text', text: src.slice(last, match.index) });
    parts.push({ type: 'sub', base: match[1], sub: match[2] });
    last = match.index + match[0].length;
  }
  if (last < src.length || !parts.length) parts.push({ type: 'text', text: src.slice(last) });
  return parts;
}

export function wrapPlainSubscripts(raw = '') {
  return mapMathSegments(String(raw ?? ''), (inner) => inner, (text) => text.replace(
    plainSubRe(),
    (_, base, sub) => (/[\u4e00-\u9fff]/.test(sub) ? `$${base}_{\\text{${sub}}}$` : `$${base}_{${sub}}$`),
  ));
}

export function normalizePhysicsSubscripts(raw = '') {
  return String(raw).split(/(```[\s\S]*?```)/).map((part) => {
    if (part.startsWith('```')) return part;
    return mapMathSegments(
      wrapPlainSubscripts(part),
      fixMathSubscripts,
      (text) => text.replace(/(?<![\\$])\b([PUI])R(\d+)\b/g, '$$$1_{R_$2}$$'),
    );
  }).join('');
}

export function normalizeOriginalQuestionOptions(raw = '') {
  return String(raw).replace(
    /^(?:>[^\n]*(?:\n|$))+/gm,
    (block) => {
      const text = block.split('\n').map((line) => line.replace(/^>\s?/, '')).join('\n');
      const split = splitStemOptions(stripYuanTiLabel(text));
      const stem = split ? split.head : stripYuanTiLabel(text);
      const order = isOrderingStem(text) ? splitOrderingSentences(stem) : null;
      if (!text.includes('原题') && !split && !order) return block;
      return formatQuestionBlock(text, block.endsWith('\n') ? '\n' : '');
    },
  );
}

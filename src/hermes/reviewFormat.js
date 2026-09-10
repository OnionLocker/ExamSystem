// 原题里挤在一行的 A/B/C/D 才拆开。
// 日练复盘对错分流、建议用时、空诊断后处理见 reviewSpec.js / reviewAssembler.js。
// 题干「A、B、C三个地点」用顿号；「地点A.B.C.D」后面不是汉字，都不要拆。
// 只拆问句之后的选项，避免把题干里的 A. 甲地拆成选项。

const OPTION_LABEL = /(?:\*\*)?([A-D])(?:[.．、])(?:\*\*)?(?:[ \t]+|(?=[\u4e00-\u9fff]))/g;

const PROMPT = /(?:由此可以推出|由此可知|可以推出的是|无法推出的是|不能推出的是|根据以上(?:资料|材料)|根据上述(?:资料|材料)|能够从上述资料中推出的是|填入画横线部分最恰当的一项是|应填入画横线部分最恰当的一项是|下列哪个正确|下列(?:说法|选项)?(?:中)?(?:正确|错误|不正确)的是|以下(?:选项)?(?:如果为真，)?最(?:能|不能)[^。：:]{0,24}|最能削弱|最能加强)[:：]?/g;

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

export function normalizeOriginalQuestionOptions(raw = '') {
  return String(raw).replace(
    /^(?:>[^\n]*(?:\n|$))+/gm,
    (block) => {
      if (!block.includes('原题')) return block;
      const text = block.split('\n').map((line) => line.replace(/^>\s?/, '')).join('\n');
      const split = splitStemOptions(text);
      if (!split) return block;
      const headLines = split.head.replace(/\s+$/g, '').split('\n').map((line) => `> ${line}`.replace(/> $/, '>'));
      const optionLines = split.chunks.map((chunk) => `> **${chunk.letter}.** ${chunk.body}`);
      const suffix = block.endsWith('\n') ? '\n' : '';
      return `${[...headLines, ...optionLines].join('\n')}${suffix}`;
    },
  );
}

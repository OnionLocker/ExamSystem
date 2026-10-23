// 原题里挤在一行的 A/B/C/D 才拆开。
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

// 资料分析材料图：模型偶尔不贴报告里的真图，自己编 dummyimage 之类的占位图，
// 再补一行「（柱状图数据：……）」。按本场材料把占位图换回真图，图下的文字数据去掉。
const PLACEHOLDER_IMAGE = /!\[[^\]]*\]\(\s*<?https?:\/\/(?:www\.)?(?:dummyimage\.com|placehold\.co|placehold\.it|placeholder\.com|via\.placeholder\.com|fakeimg\.pl|placeimg\.com|picsum\.photos|quickchart\.io|image-charts\.com)[^)]*\)/gi;
const IMAGE = /!\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)/g;
const CHART_CAPTION = /^\s*\*{0,2}\s*[（(]\s*(?:柱状图|柱形图|条形图|折线图|饼图|统计图|图表|表格)数据[^\n]*[)）]\s*\*{0,2}\s*$/;
const CENTER_TITLE = /^\s*<center>[\s\S]*<\/center>\s*$/i;
const MATERIAL_HEADING = /^#{2,4}\s*材料\s*([一二三四五六七八九十]|\d+)/;
const CN_NUMBERS = '一二三四五六七八九十';

const squash = (text) => String(text || '').replace(/[\s>*_`]/g, '');
const quotePrefix = (line) => line.match(/^\s*(?:>\s?)*/)[0];

export function materialsFromReport(markdown = '') {
  const materials = [];
  let cur = null;
  for (const line of String(markdown).split('\n')) {
    if (MATERIAL_HEADING.test(line)) {
      cur = { content: '', images: [] };
      materials.push(cur);
    } else if (/^#{1,4}\s/.test(line)) {
      cur = null;
    } else if (cur) {
      const images = [...line.matchAll(IMAGE)].map((m) => m[1]);
      if (images.length) cur.images.push(...images);
      else cur.content += `${line}\n`;
    }
  }
  return materials;
}

export function repairMaterialCharts(raw = '', materials = []) {
  const src = String(raw);
  const known = (materials || [])
    .map((m) => ({
      images: (m?.images || []).filter(Boolean),
      flat: squash(m?.content),
      keys: String(m?.content || '').split(/\n+/).map(squash).filter((s) => s.length >= 12).map((s) => s.slice(0, 20)),
    }));
  if (!/!\[|图数据|表数据|<center>/i.test(src) && !known.some((m) => m.images.length)) return src;

  const lines = src.split('\n');
  const out = [];
  let current = null;
  let shown = new Set();
  const isImageLine = (line) => /^\s*(?:>\s?)*!\[/.test(line);
  const nextContent = (from) => {
    for (let j = from; j < lines.length && j < from + 3; j += 1) {
      const body = lines[j].replace(/^\s*(?:>\s?)*/, '').trim();
      if (body) return lines[j];
    }
    return '';
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const prefix = quotePrefix(line);
    const body = line.slice(prefix.length);

    const heading = line.match(MATERIAL_HEADING);
    if (heading) {
      const n = CN_NUMBERS.indexOf(heading[1]) + 1 || Number(heading[1]);
      current = known[n - 1] || null;
      shown = new Set();
    } else if (/^#{1,4}\s/.test(line)) {
      current = null;
      shown = new Set();
    } else {
      const flat = squash(body);
      const hit = flat.length >= 12 && known.find((m) => m !== current && m.keys.some((k) => flat.includes(k)));
      if (hit) {
        current = hit;
        shown = new Set();
      }
    }

    const realImages = () => (current?.images || []).filter((s) => !shown.has(s));
    const imageLines = (srcs) => srcs.map((s) => {
      shown.add(s);
      return `${prefix}![材料图表](${s})`;
    });

    if (body.search(PLACEHOLDER_IMAGE) >= 0) {
      const rest = body.replace(PLACEHOLDER_IMAGE, '').trim();
      const real = realImages();
      if (real.length) out.push(...imageLines(real));
      if (rest) out.push(`${prefix}${rest}`);
      continue;
    }
    for (const m of body.matchAll(IMAGE)) shown.add(m[1]);

    if (CENTER_TITLE.test(body) && current?.images.length && isImageLine(nextContent(i + 1))) continue;

    if (CHART_CAPTION.test(body) && current?.images.length) {
      const real = realImages();
      if (real.length && shown.size === 0) out.push(...imageLines(real));
      continue;
    }

    out.push(line);
  }

  return restoreMissingCharts(out.join('\n'), known)
    .replace(/^([ \t]*>[ \t]*\n)(?:[ \t]*>[ \t]*\n)+/gm, '$1');
}

// 模型也会把材料图「抄」成 Markdown 表格或「标题 + 一行数据」，干脆不贴图。
// 材料引用块里认出本篇材料正文后，正文之后的内容都是它转写的图表，整段换成真图。
function restoreMissingCharts(text, known) {
  const withImages = known.filter((m) => m.images.length);
  if (!withImages.length) return text;
  const lines = text.split('\n');
  const out = [];
  for (let i = 0; i < lines.length;) {
    if (!/^\s*>/.test(lines[i])) {
      out.push(lines[i]);
      i += 1;
      continue;
    }
    let j = i;
    while (j < lines.length && /^\s*>/.test(lines[j])) j += 1;
    out.push(...restoreQuoteCharts(lines.slice(i, j), withImages));
    i = j;
  }
  return out.join('\n');
}

function restoreQuoteCharts(block, materials) {
  const bodies = block.map((line) => line.slice(quotePrefix(line).length));
  if (bodies.some((body) => body.includes('原题'))) return block;
  const flat = bodies.map(squash);
  const isMaterialText = (m, f) => f.length >= 8 && (m.keys.some((k) => f.includes(k)) || m.flat.includes(f));
  const material = materials.find((m) => flat.some((f) => f.length >= 12 && m.keys.some((k) => f.includes(k))));
  if (!material || bodies.some((body) => material.images.some((src) => body.includes(src)))) return block;
  let last = -1;
  flat.forEach((f, idx) => { if (isMaterialText(material, f)) last = idx; });
  if (last < 0) return block;
  const prefix = quotePrefix(block[last]);
  return [
    ...block.slice(0, last + 1),
    prefix.trimEnd(),
    ...material.images.map((src) => `${prefix}![材料图表](${src})`),
  ];
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
      const head = headLines.join('\n');
      const options = optionLines.join('\n>\n');
      return `${head ? `${head}\n>\n${options}` : options}${suffix}`;
    },
  );
}

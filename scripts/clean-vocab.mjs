// 清洗 words_data_enriched.json，产出 words_data_clean.json。
//
// 原始数据是 PDF 解析结果，有三类问题：
//   1. word 字段混入正文残渣（"犯罪事实。如"、"题”。交待"）
//   2. word 字段带原书辨析组标题（"【淡泊淡薄】淡泊"）——这其实是金矿，
//      组标题里就是出题人要你辨析的一对词
//   3. 523/527 条的 misunderstanding/correct_usage/example 是同一套模板文字
//
// 本脚本只做能确定性判断的修复，不臆造释义。修不了的标 usable:false，
// 由前端在出题时排除（仍保留在浏览列表里，避免丢内容）。
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve('src/copybook/words_data_enriched.json');
const OUT = path.resolve('src/copybook/words_data_clean.json');

const raw = JSON.parse(fs.readFileSync(SRC, 'utf8'));

// 模板文字指纹：命中即认为该字段无个性化信息
const TPL = {
  misunderstanding: '考场极易字面误解或混淆主客体搭配',
  correct_usage: '考场判定点：先看主体',
  example: '必须准确把握语境',
};

const GROUP_RE = /【([^】]{2,16})】/;
const BRACKET_RE = /\[[^\]]*\]|［[^］]*］/g;

// 从 "【淡泊淡薄】淡泊" 里取出组内成员：淡泊 / 淡薄
// 分隔符可能是 ·、空格，也可能完全没有（靠等分切）
function parseGroup(title) {
  const t = title.replace(/["“”]/g, '').trim();
  if (/[·•・、/]/.test(t)) {
    return t.split(/[·•・、/]+/).map((s) => s.trim()).filter(Boolean);
  }
  // 无分隔符：偶数字长按对半切（淡泊淡薄 → 淡泊 + 淡薄）
  if (t.length % 2 === 0 && t.length >= 4 && t.length <= 8) {
    const half = t.length / 2;
    return [t.slice(0, half), t.slice(half)];
  }
  return [];
}

// 纯词形校验：只允许汉字，2–5 字
function isPlainWord(s) {
  return /^[一-龥]{2,5}$/.test(s);
}

// 修复后仍是正文残渣的：这些词形合法但显然不是词条名，
// 只能靠字面黑名单剔除（都是 PDF 解析把说明文字截断留下的）
const NOT_A_HEADWORD = new Set([
  '例如', '如下', '含诙谐意', '犯罪事实', '口只能形容', '有三类', '有三种用法',
  '两种含义', '同点', '不同点', '数目', '范围', '往往接动词', '目同点',
]);
// 前缀式残渣：以这些开头基本是说明句而非词条
const RESIDUE_PREFIX = /^(如|例如|指|多指|强调|表示|往往|一般|数目|范围|置|绝)$/;

function isHeadword(s) {
  if (!isPlainWord(s)) return false;
  if (NOT_A_HEADWORD.has(s)) return false;
  if (RESIDUE_PREFIX.test(s)) return false;
  // 含"只能/不能/可以"等说明性动词的，是句子碎片
  if (/只能|不能|可以|一般|往往|强调|引申/.test(s)) return false;
  return true;
}

// 尝试把脏 word 修回一个干净词条名
function repairWord(rawWord) {
  let w = rawWord;
  let group = [];

  const gm = w.match(GROUP_RE);
  if (gm) {
    group = parseGroup(gm[1]);
    w = w.replace(GROUP_RE, '');
  }

  // 去掉异形词括注（淳厚[纯厚] → 淳厚），但先记下来
  const variants = [...rawWord.matchAll(BRACKET_RE)]
    .map((m) => m[0].replace(/[[\]［］]/g, '').trim())
    .filter(isPlainWord);
  w = w.replace(BRACKET_RE, '');

  // 剥掉前后的正文残渣：标点及其之前的内容通常是上一条的尾巴
  w = w.replace(/["“”]/g, '');
  const parts = w.split(/[。，、；：？！\s（）()]+/).filter(Boolean);
  // 取最像词条名的片段（优先纯汉字且 2–4 字）
  let cand = parts.find((p) => /^[一-龥]{2,4}$/.test(p));
  if (!cand && group.length) cand = group[0];
  if (!cand) cand = parts[0] || '';
  cand = cand.trim();

  return { word: cand, group, variants };
}

// 从 explanation 里抽出带 ~ 的原书例句，~ 即该词的位置。
// 原书有两种写法：带引号的 如“紧张的情绪慢慢~~下来，
// 和不带引号的 如：河里涨水，小桥都~了。
// rivals 质量分级。原始数据在解析时把下一条的内容粘到了上一条
// explanation 末尾（"法治…方法妨害：使受损害"），所以 inline 抓取会
// 把邻条词误当成本词的易混词。分两级信任：
//   strong = 来自原书辨析组标题【分辨分辩】，或与本词共享字形（度过/渡过）
//   weak   = 仅 inline 抓到且字形无关，可能是邻条污染，只在凑不够时用
function rivalTier(word, rival, fromGroup) {
  if (rival === word) return null;
  if (fromGroup) return 'strong';
  if (rival.length !== word.length) return 'weak';
  const shared = [...new Set(rival)].filter((c) => word.includes(c)).length;
  // 双字共享 1 字、四字共享 ≥1 字，都算书内真辨析对
  return shared >= 1 ? 'strong' : 'weak';
}

function extractCloze(text) {
  const out = [];
  const push = (s) => {
    if (!s) return;
    // ~ 或 ~~ 都代表该词一次出现
    let t = s.replace(/[~～]+/g, '____').trim();
    t = t.replace(/^[，,。：:；;、．.]+/, '').replace(/[，,、]+$/, '').trim();
    if (!t.includes('____')) return;
    // 去掉残留的成对/孤立引号，避免题干里出现半个引号
    t = t.replace(/["“”'']/g, '').trim();
    // 句子本体（去掉空格）至少 5 字才有语境信息量，"____稳健" 这种太短
    if (t.replace(/____/g, '').length < 5) return;
    if (!out.includes(t)) out.push(t);
  };

  // 形态一：引号包裹
  for (const m of text.matchAll(/[“"”]([^“"”]*[~～][^“"”]*)[”"“]?/g)) push(m[1]);
  // 形态二：如：/ 如 后直接跟句子，到句末标点为止
  for (const m of text.matchAll(/如[：:]?\s*([^“"”。；]*[~～][^。；]*)/g)) push(m[1]);

  return out;
}

const cleaned = raw.map((item) => {
  const { word, group, variants } = repairWord(item.word);
  const usable = isHeadword(word);

  // 原书在 explanation 里内嵌的对比词："情投意合 … 臭味相投：比喻…"
  const inlineRivals = [...item.explanation.matchAll(/([一-龥]{2,4})[：:]/g)]
    .map((m) => m[1])
    .filter((w2) => w2 !== word && isHeadword(w2));

  // 组标题里的同伴词（排除自己）
  const groupRivals = group.filter((g) => g !== word && isHeadword(g));

  // 原书 ~ 挖空例句：可直接做语境填空题干
  const clozeSentences = extractCloze(item.explanation);

  // 按可信度分级，出题时 strong 优先
  const rivalsStrong = [];
  const rivalsWeak = [];
  for (const r of new Set([...groupRivals, ...inlineRivals])) {
    const tier = rivalTier(word, r, groupRivals.includes(r));
    if (tier === 'strong') rivalsStrong.push(r);
    else if (tier === 'weak') rivalsWeak.push(r);
  }

  return {
    id: item.id,
    word,
    raw_word: item.word !== word ? item.word : undefined,
    variants: variants.length ? variants : undefined,
    explanation: item.explanation,
    category: item.category,
    category_desc: item.category_desc,
    page: item.page,
    usable,
    // 书内确定的易混词，出题时优先当干扰项
    rivals: rivalsStrong,
    rivals_weak: rivalsWeak.length ? rivalsWeak : undefined,
    cloze: clozeSentences.length ? clozeSentences : undefined,
    // 模板化的字段标记出来，前端不再当"深度解析"展示
    misunderstanding: item.misunderstanding,
    correct_usage: item.correct_usage,
    example: item.example,
    tpl: {
      misunderstanding: item.misunderstanding.includes(TPL.misunderstanding),
      correct_usage: item.correct_usage.includes(TPL.correct_usage),
      example: item.example.includes(TPL.example),
    },
  };
});

const usableCount = cleaned.filter((c) => c.usable).length;
const withRivals = cleaned.filter((c) => c.usable && c.rivals.length).length;
const withCloze = cleaned.filter((c) => c.usable && c.cloze).length;
const repaired = cleaned.filter((c) => c.raw_word && c.usable).length;

fs.writeFileSync(OUT, JSON.stringify(cleaned, null, 2), 'utf8');

console.log(`[clean-vocab] 输入 ${raw.length} 条 → ${OUT}`);
console.log(`  可出题词条  : ${usableCount}`);
console.log(`  其中已修复  : ${repaired}（原 word 含解析残渣）`);
console.log(`  带书内易混词: ${withRivals}`);
console.log(`  带语境挖空句: ${withCloze}`);
console.log(`  弃用(仅浏览): ${raw.length - usableCount}`);

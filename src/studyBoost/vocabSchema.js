// 词库出题的数据契约。
//
// 这里是「引擎 ⇄ 数据」之间唯一的约定：外部生成的内容（Gemini 等）
// 只要产出符合本契约的 pack，就能被引擎直接消费，无需改引擎代码。
//
// 设计取向：题型是数据驱动的。新增一种考法 = 注册一个 builder + 声明它
// 需要哪些字段，而不是在组件里加 if/else。见 kinds.js。

/** 一个词条（entry）的字段契约 */
export const ENTRY_FIELDS = {
  // --- 必填 ---
  id: 'string|number',       // 全局唯一
  word: 'string',            // 词条本身
  explanation: 'string',     // 释义

  // --- 可选，决定该词条能出哪些题型 ---
  category: 'string?',       // 陷阱归类
  page: 'number?',           // 原书页码（用于同页易混组）
  rivals: 'string[]?',       // 高可信易混词（书内辨析组/形近）
  rivals_weak: 'string[]?',  // 低可信易混词（可能是解析噪音）
  cloze: 'string[]?',        // 语境挖空句，用 ____ 占位该词
  usage: 'string?',          // 用法说明 / 搭配要点
  trap: 'string?',           // 该词的具体挖坑方式（非模板）
  antonyms: 'string[]?',     // 反义词
  synonyms: 'string[]?',     // 近义词（可作强干扰）
  examples: 'string[]?',     // 完整例句（含该词，不挖空）
  tags: 'string[]?',
  source: 'string?',         // 来源标记，便于溯源与回滚
};

/**
 * pack 文件格式（externally generated）：
 * {
 *   "pack_id": "gemini-vocab-usage-001",
 *   "generator": "gemini-3.6-flash",
 *   "created_at": "2026-07-29",
 *   "mode": "enrich" | "append",
 *   "entries": [ ... ]
 * }
 *
 * mode:
 *   enrich — 按 word（或 id）匹配已有词条，补字段。不新增词条。
 *   append — 新增词条。id 由 pack 自己保证唯一（建议前缀 pack_id）。
 */
export const PACK_MODES = ['enrich', 'append'];

/** enrich 模式下允许外部覆写/补充的字段白名单。
 *  word/id/page 这类身份字段不允许外部改，避免 pack 打乱主词库对应关系。 */
export const ENRICHABLE_FIELDS = [
  'explanation',
  'rivals',
  'rivals_weak',
  'cloze',
  'usage',
  'trap',
  'antonyms',
  'synonyms',
  'examples',
  'tags',
  'category',
];

/** 数组型字段：合并时做并集去重而非覆盖 */
export const MERGE_UNION_FIELDS = [
  'rivals',
  'rivals_weak',
  'cloze',
  'antonyms',
  'synonyms',
  'examples',
  'tags',
];

/** 校验单个词条。
 *  @param requireId    append 模式必须自带唯一 id；enrich 靠 word 匹配即可
 *  @param requireExplanation append 模式必须带释义 */
export function validateEntry(entry, { requireId = true, requireExplanation = true } = {}) {
  const errs = [];
  if (entry == null || typeof entry !== 'object') return ['不是对象'];
  if (requireId && (entry.id === undefined || entry.id === null || entry.id === '')) {
    errs.push('缺 id');
  }
  if (typeof entry.word !== 'string' || !entry.word.trim()) errs.push('缺 word');
  if (requireExplanation && (typeof entry.explanation !== 'string' || !entry.explanation.trim())) {
    errs.push('缺 explanation');
  }
  for (const f of MERGE_UNION_FIELDS) {
    if (entry[f] !== undefined && !Array.isArray(entry[f])) errs.push(`${f} 必须是数组`);
  }
  if (entry.cloze) {
    for (const c of entry.cloze) {
      if (typeof c !== 'string') { errs.push('cloze 元素必须是字符串'); break; }
      if (!c.includes('____')) errs.push(`cloze 缺 ____ 占位: "${c}"`);
      // 挖空句里不该出现该词本身，否则答案直接暴露在题干里
      if (entry.word && c.includes(entry.word)) errs.push(`cloze 句中出现了答案本身: "${c}"`);
    }
  }
  if (entry.page !== undefined && entry.page !== null && typeof entry.page !== 'number') {
    errs.push('page 必须是数字');
  }
  return errs;
}

/** 校验一个 pack，返回 { ok, errors, warnings } */
export function validatePack(pack) {
  const errors = [];
  const warnings = [];
  if (!pack || typeof pack !== 'object') return { ok: false, errors: ['pack 不是对象'], warnings };
  if (!pack.pack_id) errors.push('缺 pack_id');
  if (!PACK_MODES.includes(pack.mode)) errors.push(`mode 必须是 ${PACK_MODES.join(' | ')}`);
  if (!Array.isArray(pack.entries)) {
    errors.push('entries 必须是数组');
    return { ok: false, errors, warnings };
  }
  if (!pack.generator) warnings.push('建议填 generator，便于溯源');

  const seen = new Set();
  const isAppend = pack.mode === 'append';
  pack.entries.forEach((e, i) => {
    // enrich 只补字段：靠 word 匹配已有词条，不必带 id 和 explanation
    const errs = validateEntry(e, { requireId: isAppend, requireExplanation: isAppend });
    for (const msg of errs) errors.push(`entries[${i}]${e?.word ? ` (${e.word})` : ''}: ${msg}`);
    const key = String(e?.id ?? e?.word ?? i);
    if (seen.has(key)) errors.push(`entries[${i}]: 重复的 id/word "${key}"`);
    seen.add(key);
    if (!isAppend) {
      const unknown = Object.keys(e || {}).filter(
        (k) => !['id', 'word'].includes(k) && !ENRICHABLE_FIELDS.includes(k)
      );
      if (unknown.length) warnings.push(`entries[${i}]: 忽略不可 enrich 的字段 ${unknown.join(', ')}`);
    }
  });

  return { ok: errors.length === 0, errors, warnings };
}

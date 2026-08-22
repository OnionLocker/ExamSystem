// 词语考点出题引擎。
//
// 职责边界：
//   vocabSchema.js    — 数据契约与校验（引擎 ⇄ 外部生成内容的唯一约定）
//   questionKinds.js  — 题型注册表（声明式，新增考法不改本文件）
//   vocabQuiz.js      — 本文件：选词 → 挑干扰项 → 按注册表组题
//
// 干扰项的核心约束：必须与答案同字数、尽量形近义近，否则数字数就能选对。
// 来源按可信度分层，见 pickDistractors。
import baseWords from '../copybook/words_data_clean.json';
import { QUESTION_KINDS, KIND_BY_ID, OPTION_SOURCE, entrySupports, availableKinds } from './questionKinds.js';
import { MERGE_UNION_FIELDS, ENRICHABLE_FIELDS, validatePack } from './vocabSchema.js';

// Vite 的 glob 导入：把 vocab-packs/ 下所有 *.json 当作扩展包自动装载。
// 后续用 Gemini 生成的内容丢进那个目录即可生效，无需改代码。
const packModules = import.meta.glob('./vocab-packs/*.json', { eager: true });

/** 合并一个 pack 到词表。enrich 补字段，append 加词条。 */
function applyPack(entries, pack, diagnostics) {
  const { ok, errors, warnings } = validatePack(pack);
  const tag = pack?.pack_id || '(未命名 pack)';
  warnings.forEach((w) => diagnostics.warnings.push(`[${tag}] ${w}`));
  if (!ok) {
    // 坏 pack 整体跳过，不污染主词库
    errors.forEach((e) => diagnostics.errors.push(`[${tag}] ${e}`));
    return entries;
  }

  const byWord = new Map();
  const byId = new Map();
  entries.forEach((e) => {
    byId.set(String(e.id), e);
    if (!byWord.has(e.word)) byWord.set(e.word, e);
  });

  let enriched = 0;
  let appended = 0;
  const out = [...entries];

  for (const inc of pack.entries) {
    if (pack.mode === 'append') {
      const key = String(inc.id);
      if (byId.has(key)) {
        diagnostics.warnings.push(`[${tag}] id 冲突，已跳过: ${inc.id}`);
        continue;
      }
      const entry = normalizeEntry({ ...inc, usable: true, source: inc.source || tag });
      out.push(entry);
      byId.set(key, entry);
      appended++;
      continue;
    }

    // enrich：按 id 优先，退回 word 匹配
    const target = byId.get(String(inc.id)) || byWord.get(inc.word);
    if (!target) {
      diagnostics.warnings.push(`[${tag}] 未匹配到词条，已跳过: ${inc.word ?? inc.id}`);
      continue;
    }
    const idx = out.indexOf(target);
    const merged = { ...target };
    for (const f of ENRICHABLE_FIELDS) {
      if (inc[f] === undefined) continue;
      if (MERGE_UNION_FIELDS.includes(f)) {
        // 数组字段取并集，保留原有内容
        merged[f] = [...new Set([...(target[f] || []), ...inc[f]])];
      } else {
        merged[f] = inc[f];
      }
    }
    merged.enriched_by = [...(target.enriched_by || []), tag];
    out[idx] = merged;
    byId.set(String(merged.id), merged);
    byWord.set(merged.word, merged);
    enriched++;
  }

  diagnostics.packs.push({ pack_id: tag, mode: pack.mode, enriched, appended });
  return out;
}

// 原始词库是从 PDF 解析来的，字段名跟题型/UI 约定的那套不一样：
// misunderstanding=坑点、correct_usage=破局要点、example=例句（单条字符串）。
// 名字对不上的直接后果是：527 条词里精心写的坑点和破局全都读不到，
// 卡片只剩一行释义，六种考法里有三种因为 requires 落空而永远出不来。
// 在这里统一归一化，下游（questionKinds / UI / pack）都按同一套字段名走。
const normalizeEntry = (w) => {
  const out = { ...w };
  if (!out.trap && w.misunderstanding) out.trap = w.misunderstanding;
  if (!out.usage && w.correct_usage) out.usage = w.correct_usage;
  if (!out.examples?.length && w.example) {
    out.examples = Array.isArray(w.example) ? w.example : [w.example];
  }
  return out;
};

function loadWords() {
  const diagnostics = { packs: [], errors: [], warnings: [] };
  let entries = baseWords.map(normalizeEntry);
  // pack 按文件名排序装载，保证多个 pack 叠加结果稳定可复现
  for (const path of Object.keys(packModules).sort()) {
    const mod = packModules[path];
    entries = applyPack(entries, mod.default ?? mod, diagnostics);
  }
  return { entries, diagnostics };
}

const loaded = loadWords();

export const ALL_WORDS = loaded.entries;
/** pack 装载诊断：哪些包生效、哪些条目被跳过。UI 可展示，便于排查生成质量 */
export const PACK_DIAGNOSTICS = loaded.diagnostics;

// 只有确认是词条的才参与出题；其余仍可在列表浏览
export const QUIZ_POOL = ALL_WORDS.filter((w) => w.usable !== false);

const byId = new Map(ALL_WORDS.map((w) => [w.id, w]));
const byWord = new Map();
for (const w of ALL_WORDS) {
  if (!byWord.has(w.word)) byWord.set(w.word, w);
}

export { QUESTION_KINDS, KIND_BY_ID, availableKinds, entrySupports };

/** 按词名查词条。易混词在数据里只是个名字，配上释义才能真正拿来对比 */
export const lookupWord = (name) => byWord.get(String(name || '').trim()) || null;

/** 当前词库实际能出的题型 + 各自可出题数，用于 UI 显示与开关 */
export function kindAvailability(pool = QUIZ_POOL) {
  return QUESTION_KINDS.map((k) => ({
    id: k.id,
    label: k.label,
    count: pool.reduce((n, w) => n + (entrySupports(w, k) ? 1 : 0), 0),
  }));
}

function shuffle(arr, rand = Math.random) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// 词形相似度：共享字数越多越像，用来给干扰项排序
function similarity(a, b) {
  const setB = new Set(b);
  let shared = 0;
  for (const c of new Set(a)) if (setB.has(c)) shared++;
  return shared;
}

/**
 * 为目标词挑 count 个干扰项，按「越像越优先」排序。
 * @param needExplanation 选释义型题目要求干扰项必须有释义
 */
export function pickDistractors(
  target,
  count = 3,
  pool = QUIZ_POOL,
  rand = Math.random,
  needExplanation = false
) {
  const len = target.word.length;
  const used = new Set([target.word]);
  const out = [];

  const take = (candidates) => {
    for (const c of candidates) {
      if (out.length >= count) return;
      if (!c || used.has(c.word)) continue;
      if (needExplanation && !c.explanation) continue;
      // 释义完全相同的不能当干扰项（会出现两个正确答案）
      if (c.explanation && c.explanation === target.explanation) continue;
      used.add(c.word);
      out.push(c);
    }
  };

  // 1. 书内辨析对手 + 近义词，最强干扰。
  //    臭味相投、无微不至这类只在释义里作为对比词出现，本身不是独立词条，
  //    byWord 取不到 —— 合成一个选项对象，否则最好的干扰项会被丢掉。
  const rivalWords = [
    ...(target.rivals || []),
    ...(target.synonyms || []),
    ...(target.rivals_weak || []),
  ];
  take(
    rivalWords.map(
      (w) => byWord.get(w) || { id: `rival:${target.id}:${w}`, word: w, synthetic: true }
    )
  );

  // 2. 同页 + 同字数（原书把易混词编在同页），形近优先
  take(
    pool
      .filter((w) => w.page != null && w.page === target.page && w.word.length === len)
      .sort((a, b) => similarity(b.word, target.word) - similarity(a.word, target.word))
  );

  // 3. 全库同字数里字形最接近的（跨页也要形近，避免退化成随机同页词）
  take(
    pool
      .filter((w) => w.word.length === len && similarity(w.word, target.word) > 0)
      .sort((a, b) => similarity(b.word, target.word) - similarity(a.word, target.word))
  );

  // 4. 同类别 + 同字数。此时已无形近词，退而求同类：
  //    至少保证是同一种陷阱类型，而不是随手抓一个无关词
  take(shuffle(pool.filter((w) => w.category === target.category && w.word.length === len), rand));

  // 5. 兜底：全库同字数
  take(shuffle(pool.filter((w) => w.word.length === len), rand));

  // 6. 最后兜底：字数相差 1（几乎用不到，仅防选项凑不满）
  take(shuffle(pool.filter((w) => Math.abs(w.word.length - len) <= 1), rand));

  return out.slice(0, count);
}

/**
 * 按题型注册表组一道题。题型的差异全部由注册项描述，
 * 本函数对所有题型一视同仁 —— 新增题型不需要改这里。
 */
export function buildQuestionOfKind(target, kind, pool = QUIZ_POOL, rand = Math.random) {
  if (!kind || !entrySupports(target, kind)) return null;
  const wantExplanation = kind.optionSource === OPTION_SOURCE.EXPLANATION;

  let distractors;
  if (wantExplanation) {
    // 选释义型：多取候选，再挑释义长度与答案接近的，
    // 否则"最长选项即答案"会成为白给的线索
    const candidates = pickDistractors(target, 12, pool, rand, true).filter((d) => !d.synthetic);
    const targetLen = target.explanation.length;
    distractors = candidates
      .slice()
      .sort(
        (a, b) =>
          Math.abs(a.explanation.length - targetLen) - Math.abs(b.explanation.length - targetLen)
      )
      .slice(0, 3);
  } else {
    distractors = pickDistractors(target, 3, pool, rand);
  }
  if (distractors.length < 3) return null;

  const prompt = kind.buildPrompt(target, rand);
  if (!prompt || !String(prompt).trim()) return null;
  // 选词型题干里不能出现答案本身
  if (!wantExplanation && String(prompt).includes(target.word)) return null;

  const textOf = (w) => (wantExplanation ? w.explanation : w.word);
  const options = shuffle([target, ...distractors], rand).map((w) => ({
    id: w.id,
    text: textOf(w),
    correct: w.id === target.id,
    word: w,
  }));
  // 选项文本重复会出现两个正确答案
  if (new Set(options.map((o) => o.text)).size !== options.length) return null;

  return {
    kind: kind.id,
    kindLabel: kind.label,
    promptLabel: kind.promptLabel,
    quotePrompt: !!kind.quotePrompt,
    bigPrompt: !!kind.bigPrompt,
    wideOptions: !!kind.wideOptions,
    target,
    prompt: String(prompt),
    options,
  };
}

/**
 * 出一道题：在该词条支持且用户启用的题型里按权重随机挑一种。
 * @param allowedKindIds 用户启用的题型 id 列表；为空表示全部
 */
export function buildQuestion(target, allowedKindIds, pool = QUIZ_POOL, rand = Math.random) {
  const allowed = allowedKindIds?.length
    ? QUESTION_KINDS.filter((k) => allowedKindIds.includes(k.id))
    : QUESTION_KINDS;
  const usable = availableKinds(target, allowed);
  if (!usable.length) return null;

  // 按 weight 加权随机，再依次回退（某题型偶尔构造失败时换下一种）
  const bag = [];
  for (const k of usable) for (let i = 0; i < (k.weight || 1); i++) bag.push(k);
  for (const k of shuffle(bag, rand)) {
    const q = buildQuestionOfKind(target, k, pool, rand);
    if (q) return q;
  }
  return null;
}

/** 连对几次算真掌握 */
export const MASTERY_STREAK = 2;

/**
 * 按掌握情况给词条加权，抽下一个要考的词。
 * 错过的词权重最高，连对 2 次的降到很低但仍会偶尔复现。
 * @param recentIds 最近考过的 id 列表，避免连续重复
 */
export function pickNextTarget(pool, stats, recentIds = [], rand = Math.random) {
  if (!pool.length) return null;
  const recent = new Set(recentIds);
  const weighted = [];
  for (const w of pool) {
    const s = stats[w.id];
    let weight;
    if (!s || (s.right === 0 && s.wrong === 0)) weight = 2; // 没做过
    else if (s.wrong > 0 && (s.streak || 0) < MASTERY_STREAK) weight = 5; // 错过且未巩固
    else if ((s.streak || 0) >= MASTERY_STREAK) weight = 0.2; // 已达掌握线
    else weight = 1;
    if (recent.has(w.id)) weight *= 0.05; // 刚考过的大幅降权
    weighted.push([w, weight]);
  }
  const total = weighted.reduce((sum, [, wt]) => sum + wt, 0);
  let r = rand() * total;
  for (const [w, wt] of weighted) {
    r -= wt;
    if (r <= 0) return w;
  }
  return weighted[weighted.length - 1][0];
}

/** 已达掌握线 */
export function isTrulyMastered(stats, id) {
  return (stats[id]?.streak || 0) >= MASTERY_STREAK;
}

/** 汇总掌握情况，用于顶部统计 */
export function summarizeProgress(stats, pool = QUIZ_POOL) {
  let mastered = 0;
  let shaky = 0;
  let untouched = 0;
  for (const w of pool) {
    const s = stats[w.id];
    if (!s || (s.right === 0 && s.wrong === 0)) untouched++;
    else if ((s.streak || 0) >= MASTERY_STREAK) mastered++;
    else shaky++;
  }
  return { mastered, shaky, untouched, total: pool.length };
}

export { byId, byWord, OPTION_SOURCE };

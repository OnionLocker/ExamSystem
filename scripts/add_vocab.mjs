#!/usr/bin/env node
// scripts/add_vocab.mjs
// 按词名去重后，把词条追加进当日 vocab pack。
//
// 用法:
//   node scripts/add_vocab.mjs <entries.json> [--date YYYYMMDD] [--dry-run] [--build] [--commit]
//
// 输入是 JSON 数组。每条至少 word、wordType、explanation。
// 可选 usage、examples、rivals、collocations、cloze、source、publicSources、exampleSource。
// stdout 只打一行 JSON，便于 SSH 调用；过程输出走 stderr。
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { validatePack, WORD_TYPES } from '../src/studyBoost/vocabSchema.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');

const WORD_TYPE_IDS = new Set(Object.keys(WORD_TYPES));
const ALLOWED_FIELDS = new Set([
  'word', 'wordType', 'explanation', 'usage', 'examples', 'rivals',
  'collocations', 'cloze', 'source', 'publicSources', 'exampleSource',
]);
const GENERATOR = 'add_vocab.mjs';
const DEFAULT_NOTES = '由 scripts/add_vocab.mjs 按日追加。同名词名跳过，不覆盖已有字段。';

/** 去空白、全半角归一。比较词名只用这个结果。 */
export function normalizeWordName(word) {
  return String(word ?? '')
    .replace(/\u200b|\u200c|\u200d|\ufeff/g, '')
    .normalize('NFKC')
    .replace(/\s+/g, '');
}

export function shanghaiStamp(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type) => parts.find((p) => p.type === type).value;
  const ymd = `${get('year')}${get('month')}${get('day')}`;
  return { ymd, iso: `${get('year')}-${get('month')}-${get('day')}` };
}

export function parseYmd(ymd) {
  if (!/^\d{8}$/.test(String(ymd || ''))) return null;
  const y = Number(ymd.slice(0, 4));
  const m = Number(ymd.slice(4, 6));
  const d = Number(ymd.slice(6, 8));
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return { ymd, iso: `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}` };
}

function readText(file) {
  return fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
}

function readJsonFile(file, errors) {
  try {
    return JSON.parse(readText(file));
  } catch (e) {
    errors.push(`无法读取 ${path.relative(ROOT, file)}: ${e.message}`);
    return null;
  }
}

function readBracketed(source, open) {
  let depth = 0;
  let i = open;
  const n = source.length;
  while (i < n) {
    const c = source[i];
    if (c === '/' && source[i + 1] === '/') {
      const nl = source.indexOf('\n', i);
      i = nl < 0 ? n : nl + 1;
      continue;
    }
    if (c === '/' && source[i + 1] === '*') {
      const end = source.indexOf('*/', i + 2);
      i = end < 0 ? n : end + 2;
      continue;
    }
    if (c === "'" || c === '"') {
      const q = c;
      i++;
      while (i < n) {
        if (source[i] === '\\') { i += 2; continue; }
        if (source[i] === q) { i++; break; }
        i++;
      }
      continue;
    }
    if (c === '[') depth++;
    else if (c === ']') {
      depth--;
      if (depth === 0) return source.slice(open, i + 1);
    }
    i++;
  }
  return null;
}

function findLabeledArrays(source, re) {
  const arrays = [];
  re.lastIndex = 0;
  let m;
  while ((m = re.exec(source))) {
    let i = m.index + m[0].length;
    while (i < source.length && /\s/.test(source[i])) i++;
    if (source[i] !== '[') continue;
    const block = readBracketed(source, i);
    if (block) arrays.push(block);
    else break;
  }
  return arrays;
}

/** 组员 / 单列都是 ['词名', '释义', ...]，只取每个内层数组的第一段字符串。 */
export function tupleHeadWords(block) {
  const words = [];
  let depth = 0;
  let taken = false;
  let i = 0;
  const n = block.length;
  while (i < n) {
    const c = block[i];
    if (c === '/' && block[i + 1] === '/') {
      const nl = block.indexOf('\n', i);
      i = nl < 0 ? n : nl + 1;
      continue;
    }
    if (c === '/' && block[i + 1] === '*') {
      const end = block.indexOf('*/', i + 2);
      i = end < 0 ? n : end + 2;
      continue;
    }
    if (c === "'" || c === '"') {
      const q = c;
      i++;
      let s = '';
      while (i < n) {
        if (block[i] === '\\') {
          s += block[i + 1] ?? '';
          i += 2;
          continue;
        }
        if (block[i] === q) { i++; break; }
        s += block[i];
        i++;
      }
      if (depth >= 2 && !taken) {
        words.push(s);
        taken = true;
      }
      continue;
    }
    if (c === '[') {
      depth++;
      if (depth === 2) taken = false;
    } else if (c === ']') depth--;
    i++;
  }
  return words;
}

function addName(known, word, label, file) {
  const key = normalizeWordName(word);
  if (!key || key.length > 30 || /[。！？]/.test(key)) return;
  let row = known.get(key);
  if (!row) {
    row = { word: key, hits: [] };
    known.set(key, row);
  }
  if (!row.hits.some((h) => h.label === label && h.file === file)) {
    row.hits.push({ label, file });
  }
}

function addJsWords(known, file, label, words) {
  for (const word of words) addName(known, word, label, file);
  return words.length;
}

/**
 * 主库、全部词包、辨析组员、单列成语、讲义的词名。
 * @returns {{ known: Map<string, {word: string, hits: {label: string, file: string}[]}>, errors: string[] }}
 */
export function collectKnownWords(root = ROOT) {
  const known = new Map();
  const errors = [];
  const baseFile = path.join(root, 'src', 'copybook', 'words_data_clean.json');
  const groupsFile = path.join(root, 'src', 'studyBoost', 'idiomGroups.js');
  const supplementFile = path.join(root, 'src', 'studyBoost', 'idiomSupplement.js');
  const handoutFile = path.join(root, 'src', 'studyBoost', 'idiomHandout.json');
  const base = readJsonFile(baseFile, errors);
  if (Array.isArray(base)) {
    for (const entry of base) addName(known, entry?.word, '主词库', baseFile);
  } else if (base) errors.push('主词库不是数组');

  const packDir = path.join(root, 'src', 'studyBoost', 'vocab-packs');
  if (!fs.existsSync(packDir)) errors.push('缺少 vocab-packs 目录');
  else {
    for (const name of fs.readdirSync(packDir).filter((f) => f.endsWith('.json')).sort()) {
      const file = path.join(packDir, name);
      const pack = readJsonFile(file, errors);
      if (!pack || typeof pack !== 'object') continue;
      const label = `vocab-packs/${name}`;
      if (Array.isArray(pack.entries)) {
        for (const entry of pack.entries) addName(known, entry?.word, label, file);
      }
      if (Array.isArray(pack.groups)) {
        for (const group of pack.groups) {
          if (!Array.isArray(group?.members)) continue;
          for (const member of group.members) {
            if (typeof member === 'string') addName(known, member, label, file);
            else if (Array.isArray(member)) addName(known, member[0], label, file);
          }
        }
      }
    }
  }

  let groupCount = 0;
  let standaloneCount = 0;
  try {
    const groups = readText(groupsFile);
    const supplement = readText(supplementFile);
    for (const block of findLabeledArrays(groups, /members\s*:/g)) {
      groupCount += addJsWords(known, groupsFile, '辨析组', tupleHeadWords(block));
    }
    for (const block of findLabeledArrays(supplement, /members\s*:/g)) {
      groupCount += addJsWords(known, supplementFile, '辨析组', tupleHeadWords(block));
    }
    for (const block of findLabeledArrays(supplement, /singleRows\s*=/g)) {
      standaloneCount += addJsWords(known, supplementFile, '单列成语', tupleHeadWords(block));
    }
  } catch (e) {
    errors.push(`无法读取辨析组或单列成语: ${e.message}`);
  }
  if (!groupCount) errors.push('未提取到辨析组词名，已中止以免漏去重');
  if (!standaloneCount) errors.push('未提取到单列成语，已中止以免漏去重');

  const handout = readJsonFile(handoutFile, errors);
  if (handout && Array.isArray(handout.entries)) {
    for (const entry of handout.entries) addName(known, entry?.word, '讲义', handoutFile);
  } else if (handout) errors.push('讲义缺少 entries');

  return { known, errors };
}

function clozeContainsAnswer(word, cloze) {
  if (!Array.isArray(cloze)) return false;
  return cloze.some((c) => typeof c === 'string' && normalizeWordName(c).includes(word));
}

function toEntry(raw, word, date) {
  const out = {
    id: `daily-${date.ymd}:${word}`,
    word,
    wordType: raw.wordType,
    explanation: raw.explanation.trim(),
  };
  if (typeof raw.usage === 'string' && raw.usage.trim()) out.usage = raw.usage.trim();
  for (const field of ['examples', 'rivals', 'collocations', 'cloze']) {
    if (raw[field] !== undefined) out[field] = raw[field];
  }
  if (typeof raw.source === 'string' && raw.source.trim()) out.source = raw.source.trim();
  if (raw.publicSources !== undefined) out.publicSources = raw.publicSources;
  if (typeof raw.exampleSource === 'string' && raw.exampleSource.trim()) out.exampleSource = raw.exampleSource.trim();
  return out;
}

function sourceLabels(known, word, date, existingWords) {
  const labels = [];
  if (existingWords.has(word)) labels.push(`vocab-packs/daily-${date.ymd}.json`);
  for (const hit of known.get(word)?.hits || []) {
    if (!labels.includes(hit.label)) labels.push(hit.label);
  }
  return labels;
}

/**
 * 生成合并后的当日词包。不写盘。
 * known 里已有的词、当日文件里已有的词、输入内部重复的词都跳过。
 */
export function buildDailyPack({ date, existing, incoming, known }) {
  const errors = [];
  const skipped = [];
  const accepted = [];
  if (existing != null && (typeof existing !== 'object' || Array.isArray(existing) || !Array.isArray(existing.entries))) {
    return { ok: false, errors: ['已有每日词包不是合法 pack'], added: [], skipped, pack: null };
  }
  if (existing?.mode && existing.mode !== 'append') {
    return { ok: false, errors: [`已有每日词包 mode 为 ${existing.mode}，必须是 append`], added: [], skipped, pack: null };
  }
  if (!Array.isArray(incoming)) {
    return { ok: false, errors: ['输入必须是 JSON 数组'], added: [], skipped, pack: null };
  }

  const existingWords = new Set();
  for (const entry of existing?.entries || []) {
    const word = normalizeWordName(entry?.word);
    if (word) existingWords.add(word);
  }
  const seenInput = new Set();

  incoming.forEach((entry, i) => {
    const where = `输入[${i}]`;
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      errors.push(`${where}: 不是对象`);
      return;
    }
    const unknown = Object.keys(entry).filter((k) => !ALLOWED_FIELDS.has(k));
    if (typeof entry.word !== 'string') {
      errors.push(`${where}: 缺 word`);
      return;
    }
    const word = normalizeWordName(entry.word);
    if (!word) {
      errors.push(`${where}: 缺 word`);
      return;
    }
    if (seenInput.has(word)) {
      skipped.push({ word, reason: '输入内重复' });
      return;
    }
    if (known.has(word) || existingWords.has(word)) {
      skipped.push({
        word,
        reason: '词名已存在',
        sources: sourceLabels(known, word, date, existingWords),
      });
      seenInput.add(word);
      return;
    }
    const entryErrors = [];
    if (unknown.length) entryErrors.push(`含未支持字段 ${unknown.join(', ')}`);
    if (typeof entry.explanation !== 'string' || !entry.explanation.trim()) entryErrors.push('缺 explanation');
    if (typeof entry.wordType !== 'string' || !WORD_TYPE_IDS.has(entry.wordType)) {
      entryErrors.push('wordType 必须是 word、idiom 或 collocation');
    }
    if (entry.cloze !== undefined && clozeContainsAnswer(word, entry.cloze)) entryErrors.push('cloze 不得含答案');
    if (entryErrors.length) {
      for (const msg of entryErrors) errors.push(`${where} (${word}): ${msg}`);
      seenInput.add(word);
      return;
    }
    accepted.push(toEntry(entry, word, date));
    seenInput.add(word);
  });

  if (errors.length) return { ok: false, errors, added: [], skipped, pack: null };

  const pack = {
    ...(existing || {}),
    pack_id: existing?.pack_id || `daily-${date.ymd}`,
    generator: existing?.generator || GENERATOR,
    created_at: existing?.created_at || date.iso,
    mode: 'append',
    notes: existing?.notes || DEFAULT_NOTES,
    entries: [...(existing?.entries || []), ...accepted],
  };
  const checked = validatePack(pack);
  if (!checked.ok) return { ok: false, errors: checked.errors, added: [], skipped, pack: null };
  return { ok: true, errors: [], warnings: checked.warnings, added: accepted.map((e) => e.word), skipped, pack };
}

/** append 词条若与其它词包、辨析组、单列成语或讲义同名，只警告，不判定失败。 */
export function duplicateNameWarnings(pack, file, known) {
  if (!pack || pack.mode !== 'append' || !Array.isArray(pack.entries)) return [];
  const current = file ? path.resolve(file) : null;
  const warnings = [];
  const seen = new Set();
  for (const entry of pack.entries) {
    const word = normalizeWordName(entry?.word);
    if (!word) continue;
    if (seen.has(word)) {
      warnings.push(`词名在本包内重复，装载时会按词合并并覆盖旧字段: ${entry.word}`);
      continue;
    }
    seen.add(word);
    const labels = [];
    for (const hit of known.get(word)?.hits || []) {
      if (current && hit.file === current) continue;
      if (!labels.includes(hit.label)) labels.push(hit.label);
    }
    if (labels.length) {
      warnings.push(`词名与已有内容同名，装载时会按词合并并覆盖旧字段: ${entry.word}（${labels.join('、')}）`);
    }
  }
  return warnings;
}

function parseArgs(argv) {
  const positional = [];
  let date = null;
  let dryRun = false;
  let build = false;
  let commit = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--dry-run') dryRun = true;
    else if (arg === '--build') build = true;
    else if (arg === '--commit') commit = true;
    else if (arg === '--date') {
      date = argv[++i];
      if (!date) throw new Error('缺少 --date 的值');
    } else if (arg.startsWith('--date=')) date = arg.slice('--date='.length);
    else if (arg.startsWith('-')) throw new Error(`未知参数 ${arg}`);
    else positional.push(arg);
  }
  if (positional.length !== 1) {
    throw new Error('用法: node scripts/add_vocab.mjs <entries.json> [--date YYYYMMDD] [--dry-run] [--build] [--commit]');
  }
  return { inputPath: positional[0], date, dryRun, build, commit };
}

function emit(summary) {
  fs.writeSync(1, `${JSON.stringify(summary)}\n`);
}

function git(args, cwd = ROOT) {
  const result = spawnSync('git', args, {
    cwd,
    encoding: 'utf8',
    env: { ...process.env, GIT_TERMINAL_PROMPT: '0' },
  });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || result.error?.message || 'git 失败').trim());
  }
  return (result.stdout || '').trim();
}

function runBuild(relFile) {
  const commands = [
    ['npm', ['run', 'validate:vocab-pack', '--', relFile]],
    ['node', ['scripts/test-idiom-learning.mjs']],
    ['npm', ['run', 'build']],
  ];
  const steps = [];
  for (const [cmd, args] of commands) {
    const shown = [cmd, ...args].join(' ');
    const result = spawnSync(cmd, args, { cwd: ROOT, encoding: 'utf8' });
    if (result.stdout) process.stderr.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    const code = result.status ?? 1;
    const ok = code === 0 && !result.error;
    const tail = `${result.stdout || ''}${result.stderr || ''}${result.error?.message || ''}`.trim().slice(-500);
    steps.push({ cmd: shown, ok, code, ...(ok ? {} : { tail }) });
    if (!ok) return { ok: false, steps };
  }
  return { ok: true, steps };
}

export function commitPack(relFile, count, cwd = ROOT) {
  const run = (args) => git(args, cwd);
  const branch = run(['rev-parse', '--abbrev-ref', 'HEAD']);
  if (branch !== 'main') {
    return { ok: false, pushed: false, error: `当前分支是 ${branch}，--commit 只在 main 上提交并推送` };
  }
  run(['pull', '--ff-only', 'origin', 'main']);
  const dirty = run(['status', '--porcelain', '--', relFile]);
  if (!dirty) return { ok: true, skipped: true, pushed: false, reason: '词包文件无变更' };
  // 新建词包是未跟踪文件，不先 add 时 commit -- path 会报 pathspec did not match。
  run(['add', '--', relFile]);
  run(['commit', '-m', `词语学习：追加 ${count} 条到 ${path.basename(relFile)}`, '--only', '--', relFile]);
  const hash = run(['rev-parse', 'HEAD']);
  run(['push', 'origin', 'main']);
  return { ok: true, hash, pushed: true };
}

export function runAddVocab(argv = process.argv.slice(2)) {
  let parsed;
  try {
    parsed = parseArgs(argv);
  } catch (e) {
    return { code: 1, summary: { ok: false, error: e.message, added: [], skipped: [], file: null, build: null, commit: null } };
  }

  const date = parsed.date ? parseYmd(parsed.date) : shanghaiStamp();
  const relFile = `src/studyBoost/vocab-packs/daily-${date?.ymd || 'invalid'}.json`;
  const baseSummary = {
    ok: false,
    added: [],
    skipped: [],
    file: date ? relFile : null,
    dryRun: parsed.dryRun,
    wrote: false,
    date: date?.ymd || null,
    build: null,
    commit: null,
  };
  if (!date) {
    return { code: 1, summary: { ...baseSummary, error: '--date 必须是有效的 YYYYMMDD' } };
  }

  const inputFile = path.resolve(parsed.inputPath);
  let incoming;
  try {
    incoming = JSON.parse(readText(inputFile));
  } catch (e) {
    return { code: 1, summary: { ...baseSummary, error: `无法读取输入: ${e.message}` } };
  }

  const { known, errors: corpusErrors } = collectKnownWords(ROOT);
  if (corpusErrors.length) {
    return { code: 1, summary: { ...baseSummary, error: corpusErrors.join('；'), errors: corpusErrors } };
  }

  const target = path.join(ROOT, relFile);
  let existing = null;
  if (fs.existsSync(target)) {
    try {
      existing = JSON.parse(readText(target));
    } catch (e) {
      return { code: 1, summary: { ...baseSummary, error: `已有每日词包无法解析: ${e.message}` } };
    }
  }

  const built = buildDailyPack({ date, existing, incoming, known });
  const summary = {
    ...baseSummary,
    ok: built.ok,
    added: built.added,
    skipped: built.skipped,
    ...(built.ok ? {} : { error: built.errors.join('；'), errors: built.errors }),
  };
  if (!built.ok) return { code: 1, summary };

  if (!parsed.dryRun && built.added.length) {
    const tmp = `${target}.tmp-${process.pid}`;
    try {
      fs.writeFileSync(tmp, `${JSON.stringify(built.pack, null, 2)}\n`);
      fs.renameSync(tmp, target);
      summary.wrote = true;
    } catch (e) {
      if (fs.existsSync(tmp)) fs.rmSync(tmp, { force: true });
      return { code: 1, summary: { ...summary, ok: false, wrote: false, error: `写入失败: ${e.message}` } };
    }
  }

  if (parsed.build) {
    if (parsed.dryRun || !summary.wrote) {
      summary.build = { skipped: true, reason: parsed.dryRun ? 'dry-run 不构建' : '无新增，不构建' };
    } else {
      summary.build = runBuild(relFile);
      if (!summary.build.ok) summary.ok = false;
    }
  }

  if (parsed.commit) {
    if (parsed.dryRun || !summary.wrote || (parsed.build && summary.build && summary.build.ok === false)) {
      const reason = parsed.dryRun ? 'dry-run 不提交' : !summary.wrote ? '无新增，不提交' : '构建失败，不提交';
      summary.commit = { ok: false, skipped: true, pushed: false, reason };
    } else {
      try {
        summary.commit = commitPack(relFile, built.added.length);
        if (!summary.commit.ok) summary.ok = false;
      } catch (e) {
        summary.ok = false;
        summary.commit = { ok: false, pushed: false, error: e.message };
      }
    }
  }

  return { code: summary.ok ? 0 : 1, summary };
}

function invokedDirectly() {
  const entry = process.argv[1];
  if (!entry) return false;
  try {
    return fs.realpathSync(entry) === fs.realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

if (invokedDirectly()) {
  const { code, summary } = runAddVocab(process.argv.slice(2));
  emit(summary);
  process.exit(code);
}

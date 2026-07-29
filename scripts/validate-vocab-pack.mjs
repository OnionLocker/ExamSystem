#!/usr/bin/env node
// scripts/validate-vocab-pack.mjs
// 用法: node scripts/validate-vocab-pack.mjs [pack.json ...]
//       不带参数时校验 src/studyBoost/vocab-packs/ 下所有 *.json
//
// 校验规范见 docs/VOCAB_PACK_SPEC.md。与前端共用 vocabSchema.js 的校验逻辑，
// 保证「离线校验通过」和「前端能装载」是同一件事。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { validatePack } from '../src/studyBoost/vocabSchema.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PACK_DIR = path.join(ROOT, 'src', 'studyBoost', 'vocab-packs');
const BASE = path.join(ROOT, 'src', 'copybook', 'words_data_clean.json');

const args = process.argv.slice(2);
const files = args.length
  ? args.map((a) => path.resolve(a))
  : fs.existsSync(PACK_DIR)
    ? fs.readdirSync(PACK_DIR).filter((f) => f.endsWith('.json')).map((f) => path.join(PACK_DIR, f))
    : [];

if (!files.length) {
  console.log('没有找到要校验的 pack 文件');
  process.exit(0);
}

const base = JSON.parse(fs.readFileSync(BASE, 'utf8'));
const baseWords = new Set(base.map((w) => w.word));
const baseIds = new Set(base.map((w) => String(w.id)));

let failed = 0;

for (const file of files) {
  const rel = path.relative(ROOT, file);
  let pack;
  try {
    pack = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    console.log(`\n✗ ${rel}\n  JSON 解析失败: ${e.message}`);
    failed++;
    continue;
  }

  const { ok, errors, warnings } = validatePack(pack);

  // 额外的跨文件检查：enrich 的目标是否真的存在
  const extra = [];
  if (pack.mode === 'enrich' && Array.isArray(pack.entries)) {
    for (const e of pack.entries) {
      const hit = (e.id !== undefined && baseIds.has(String(e.id))) || baseWords.has(e.word);
      if (!hit) extra.push(`未匹配到主词库词条，装载时会被跳过: ${e.word ?? e.id}`);
    }
  }
  if (pack.mode === 'append' && Array.isArray(pack.entries)) {
    for (const e of pack.entries) {
      if (baseIds.has(String(e.id))) extra.push(`id 与主词库冲突: ${e.id}`);
    }
  }

  const allWarn = [...warnings, ...extra];
  const status = ok ? (allWarn.length ? '⚠' : '✓') : '✗';
  console.log(`\n${status} ${rel}  [${pack.mode ?? '?'}] ${pack.entries?.length ?? 0} 条`);
  for (const e of errors) console.log(`    ✗ ${e}`);
  for (const w of allWarn.slice(0, 20)) console.log(`    ⚠ ${w}`);
  if (allWarn.length > 20) console.log(`    ⚠ …其余 ${allWarn.length - 20} 条略`);
  if (!ok) failed++;
}

console.log(
  failed
    ? `\n${failed} 个 pack 校验失败 —— 这些包会被前端整体跳过，不会污染主词库。`
    : `\n全部 ${files.length} 个 pack 校验通过。`
);
process.exit(failed ? 1 : 0);

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CURATED_WORDS } from '../src/studyBoost/idiomGroups.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const words = new Set([...read(path.join(root, 'src/copybook/words_data_clean.json')), ...CURATED_WORDS].map(w => w.word));
for (const file of fs.readdirSync(path.join(root, 'src/studyBoost/vocab-packs'))) {
  if (file.endsWith('.json')) for (const w of read(path.join(root, 'src/studyBoost/vocab-packs', file)).entries) words.add(w.word);
}
const evidence = {};
const papers = [];
const gdCandidates = new Set();
for (const file of fs.readdirSync(path.join(root, 'data/zhenti')).sort()) {
  if (!/^202[3-6].*\.json$/.test(file)) continue;
  const paper = read(path.join(root, 'data/zhenti', file));
  papers.push(paper.title || file.replace('.json', ''));
  for (const q of paper.questions || []) {
    if (q.subtype !== '逻辑填空' || !String(q.module).includes('言语') || !Number.isInteger(q.number)) continue;
    const hits = new Set();
    for (const value of Object.values(q.options || {})) {
      // Only whole option tokens. Do not mistake quoted sentence fragments for idioms.
      for (const part of String(value).trim().split(/[\s、/|]+/)) {
        // Preserve registered full expressions, rather than counting their halves.
        const terms = words.has(part) ? [part] : part.split(/[，,]+/);
        for (const token of terms) {
          if (words.has(token)) hits.add(token);
          if (file.includes('广东') && /^[\u3400-\u9fff，,]{4,}$/.test(token)) gdCandidates.add(token);
        }
      }
    }
    for (const word of hits) {
      const appearances = evidence[word] ??= [];
      const title = paper.title || file.replace('.json', '');
      if (appearances.some(r => r.paper === title && r.number === q.number)) continue;
      appearances.push({ paper: title, year: paper.year,
        number: q.number, region: file.includes('广东') ? '广东' : '其他', recalled: true });
    }
  }
}
const output = { generated_at: new Date().toISOString().slice(0, 10), scope: '本地2023—2026年回忆版逻辑填空选项；按试卷题号去重，不代表全网考频', papers,
  gdCoverage: { scope: '已收集广东卷中四字及以上选项词和完整联句；不等于全考纲覆盖', candidates: gdCandidates.size,
    included: [...gdCandidates].filter(w => words.has(w)).length, missing: [...gdCandidates].filter(w => !words.has(w)) }, words: evidence };
const target = path.join(root, 'src/studyBoost/idiomEvidence.json');
fs.writeFileSync(target, JSON.stringify(output, null, 2) + '\n');
console.log(`${papers.length} papers; ${Object.keys(evidence).length} words with traceable appearances`);

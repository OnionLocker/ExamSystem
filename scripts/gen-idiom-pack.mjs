#!/usr/bin/env node
// scripts/gen-idiom-pack.mjs
// 从真题里统计出的高频成语，凡是主词库没有的，交给模型补齐词条字段，
// 产出一个 append 模式的 vocab pack。
//
// 为什么要这么做：主词库那 527 条来自 504 号考词表，跟近年真题实际考的
// 成语几乎不重叠（240 个真题高频词里只命中 2 个）。缺的不是生僻词，
// 恰恰是「常见但容易辨析错」的那批。
//
// 用法:
//   node scripts/gen-idiom-pack.mjs [--limit N] [--batch N] [--out 文件名]
//   node scripts/gen-idiom-pack.mjs --words 词表.json --tag 公认高频 --pack-id xxx
//
// --words 用于补另一类缺口：像「趋之若鹜」「炙手可热」「美轮美奂」这些
// 公认必考的望文生义/谦敬误用词，在手头这 18 套卷里未必出现两次以上，
// 靠真题词频统计会漏掉，但它们该背。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const ZHENTI = path.join(ROOT, 'data', 'zhenti');
const BASE = path.join(ROOT, 'src', 'copybook', 'words_data_clean.json');
const args = process.argv.slice(2);
const argVal = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const LIMIT = Number(argVal('--limit', '0'));
const BATCH = Number(argVal('--batch', '15'));
const OUT = path.join(ROOT, 'src', 'studyBoost', 'vocab-packs', argVal('--out', 'zhenti-idioms.json'));
const WORDS_FILE = argVal('--words', '');
const TAG = argVal('--tag', '');
const PACK_ID = argVal('--pack-id', 'zhenti-idioms');

const MODEL = process.env.VOCAB_GEN_MODEL || 'gemini-3.7-flash-high';
const BASE_URL = (process.env.CLIPROXY_BASE_URL || 'http://127.0.0.1:8889/v1').replace(/\/$/, '');
const KEY = (() => {
  if (process.env.CLIPROXY_API_KEY) return process.env.CLIPROXY_API_KEY.trim();
  const t = fs.readFileSync(path.join(os.homedir(), '.hermes', '.env'), 'utf8');
  return t.split('\n').find((l) => l.startsWith('CLIPROXY_API_KEY=')).split('=')[1].trim();
})();

// 真题选项里混着文言引文的分句（「为政之要」「苟利于民」这种），它们不是词条
const NOT_IDIOM = new Set([
  '为政之要', '善为政者', '弊则补之', '决则塞之', '苟利于民', '不必循俗',
  '天地之大', '黎元为先', '必先富民', '节用裕民', '积微成著', '慎小谨微',
]);

const CATEGORIES = [
  '望文生义陷阱', '适用对象误用', '褒贬误用辨析', '语意重复与语境限制', '易混实词/成语辨析',
];

function collectMissing() {
  const have = new Set(JSON.parse(fs.readFileSync(BASE, 'utf8')).map((w) => w.word));
  const freq = new Map();
  const IDIOM = /^[\u4e00-\u9fa5]{4}$/;
  for (const f of fs.readdirSync(ZHENTI).filter((x) => x.endsWith('.json'))) {
    const j = JSON.parse(fs.readFileSync(path.join(ZHENTI, f), 'utf8'));
    for (const q of j.questions || []) {
      if (!String(q.module || '').includes('言语')) continue;
      for (const v of Object.values(q.options || {})) {
        for (const tok of String(v).split(/[\s、，,/|]+/)) {
          const t = tok.trim();
          if (IDIOM.test(t)) freq.set(t, (freq.get(t) || 0) + 1);
        }
      }
    }
  }
  return [...freq.entries()]
    .filter(([w, n]) => n >= 2 && !have.has(w) && !NOT_IDIOM.has(w))
    .sort((a, b) => b[1] - a[1]);
}

const prompt = (words) => `你是公考行测言语理解的资深教研。下面这些成语都是公考行测**必考的高频易错词**${words[0][1] ? '，括号里是它们在近 6 年真题逻辑填空选项中出现的次数' : '，其中不少是成对出现的易混词（如「不以为然/不以为意」），辨析时请互相参照'}。

${words.map(([w, n]) => (n ? `${w}（真题出现 ${n} 次）` : w)).join('\n')}

请为每个词生成一条词库记录，**只输出 JSON 数组**，不要任何解释文字。每条格式：

{
  "word": "成语",
  "explanation": "准确释义，30 字以内，不要抄词典的绕口说法",
  "category": "从这五个里选一个最贴切的：${CATEGORIES.join(' / ')}",
  "trap": "考场上这个词具体怎么被挖坑。要写出题人真实的设陷方式，例如'常被当成褒义用，实际是贬义''容易和X混用，区别在于Y'。不要写'注意语境'这种废话",
  "usage": "破局要点：褒贬色彩、适用对象、固定搭配、语义轻重，哪条是判定关键就写哪条。要能直接用来排除选项",
  "examples": ["一个例句，语境贴近公考真题（时政、治理、发展、科技、文化），30~60 字"],
  "cloze": ["同一个语境的挖空版，用 ____ 代替该成语"],
  "rivals": ["真实存在的易混成语，1~3 个。没有把握就给空数组"]
}

要求：
- 释义必须准确，宁可简单也不要编。
- trap 和 usage 要具体到能指导做题，是这个词独有的，不能是通用模板。
- rivals 必须是真实成语且确实容易混，不要凑数。
- examples 和 cloze 必须是同一句话的两个版本。`;

async function ask(text) {
  const r = await fetch(`${BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
    body: JSON.stringify({ model: MODEL, max_tokens: 16000, messages: [{ role: 'user', content: text }] }),
    signal: AbortSignal.timeout(8 * 60 * 1000),
  });
  const j = await r.json();
  const out = j?.choices?.[0]?.message?.content;
  if (!out) throw new Error(j?.error?.message || '模型没有返回内容');
  return out;
}

const parseArray = (text) => {
  const m = text.match(/\[[\s\S]*\]/);
  if (!m) return null;
  try { return JSON.parse(m[0]); } catch { return null; }
};

// ---------- main ----------
let missing;
if (WORDS_FILE) {
  const raw = JSON.parse(fs.readFileSync(path.resolve(WORDS_FILE), 'utf8'));
  const have = new Set(JSON.parse(fs.readFileSync(BASE, 'utf8')).map((w) => w.word));
  // 已有 pack 里补过的也要排掉，避免同一个词生成两遍
  for (const f of fs.readdirSync(path.dirname(OUT)).filter((x) => x.endsWith('.json'))) {
    try {
      const pk = JSON.parse(fs.readFileSync(path.join(path.dirname(OUT), f), 'utf8'));
      if (pk.mode === 'append') for (const e of pk.entries || []) have.add(e.word);
    } catch { /* 坏包忽略 */ }
  }
  missing = raw.filter((w) => !have.has(w)).map((w) => [w, 0]);
} else {
  missing = collectMissing();
}
if (LIMIT > 0) missing = missing.slice(0, LIMIT);
console.log(`真题高频且主词库没有的成语：${missing.length} 个，每批 ${BATCH} 个\n`);

const entries = [];
const failed = [];
for (let i = 0; i < missing.length; i += BATCH) {
  const chunk = missing.slice(i, i + BATCH);
  const no = Math.floor(i / BATCH) + 1;
  const total = Math.ceil(missing.length / BATCH);
  process.stdout.write(`  批次 ${no}/${total}（${chunk.length} 词）… `);
  try {
    const arr = parseArray(await ask(prompt(chunk)));
    if (!arr) throw new Error('返回不是 JSON 数组');
    const wanted = new Set(chunk.map(([w]) => w));
    const freqOf = Object.fromEntries(chunk);
    let ok = 0;
    for (const e of arr) {
      // 只收要的词，且必要字段齐全，防止模型自由发挥塞进来别的
      if (!wanted.has(e.word) || !e.explanation || !e.trap) continue;
      entries.push({
        id: `zt-${e.word}`,
        word: e.word,
        explanation: String(e.explanation).trim(),
        category: CATEGORIES.includes(e.category) ? e.category : '易混实词/成语辨析',
        trap: String(e.trap).trim(),
        usage: e.usage ? String(e.usage).trim() : undefined,
        examples: Array.isArray(e.examples) ? e.examples.filter(Boolean) : [],
        cloze: Array.isArray(e.cloze) ? e.cloze.filter((c) => c.includes('____')) : [],
        rivals: Array.isArray(e.rivals) ? e.rivals.filter(Boolean).slice(0, 3) : [],
        tags: [freqOf[e.word] ? `真题${freqOf[e.word]}次` : (TAG || '高频易错')],
        source: freqOf[e.word] ? '近 6 年国考/省考真题逻辑填空选项' : '公考公认高频易错成语',
      });
      ok++;
    }
    console.log(`收 ${ok} 条`);
    if (ok < chunk.length) failed.push(...chunk.filter(([w]) => !entries.some((x) => x.word === w)).map(([w]) => w));
  } catch (e) {
    console.log(`失败：${e.message}`);
    failed.push(...chunk.map(([w]) => w));
  }
}

const pack = {
  pack_id: PACK_ID,
  generator: MODEL,
  created_at: new Date().toISOString().slice(0, 10),
  mode: 'append',
  notes: WORDS_FILE
    ? '公考公认高频易错成语（望文生义 / 谦敬误用 / 成对易混），补真题词频统计漏掉的那部分。'
    : '从 data/zhenti 近 6 年真题逻辑填空选项中统计出的高频成语，主词库未收录的部分。',
  entries,
};
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(pack, null, 2), 'utf8');

console.log(`\n写入 ${OUT}`);
console.log(`  成功 ${entries.length} 条`);
if (failed.length) console.log(`  未生成 ${failed.length} 个：${failed.join('、')}`);

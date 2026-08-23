#!/usr/bin/env node
// scripts/import-zhenti.mjs
// 把 data/zhenti/*.json 里的真题导入 questions 表。
//
// 这些卷子是 parse_zhenti.py 的产物，字段跟 batches/ 那套导入格式差一层：
// options 是对象不是数组、答案字段叫 correct_answer、规范主考点在 knowledge_points[0]。
// 差的就是这层翻译，所以 2000 多道题一直躺在磁盘上没进库。
//
// 用法:
//   node scripts/import-zhenti.mjs                 # 导入 data/zhenti 下全部
//   node scripts/import-zhenti.mjs <文件或目录>
//   node scripts/import-zhenti.mjs --dry-run       # 只看统计不写库
//   node scripts/import-zhenti.mjs --skip-figure   # 跳过缺图的题

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import db from '../server/db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DEFAULT_DIR = path.join(ROOT, 'data', 'zhenti');

const args = process.argv.slice(2);
const DRY_RUN = args.includes('--dry-run');
const SKIP_FIGURE = args.includes('--skip-figure');
const target = args.find((a) => !a.startsWith('--')) || DEFAULT_DIR;

// external_id 要长期稳定，重跑才能幂等更新而不是插重复。
// 中文留着不转拼音：SQLite 存 TEXT 无所谓，人能读懂反而好排查。
const slug = (s) => String(s || '').replace(/[\s/\\:*?"<>|]+/g, '');
const batchIdOf = (j) => `zhenti-${j.year}-${slug(j.exam)}-${slug(j.paper)}`;

const regionOf = (j) => {
  const paper = String(j.paper || '').replace(/卷$/, '');
  if (String(j.exam).includes('国考')) return `国家-${paper}`;
  return `广东-${paper}`;
};

// 判断题在题干里自带"（判断题）"标记，选项本来就没有，答案 A/B 正好对应正确/错误。
// 不能反过来拿"没有选项"当判断题的判据：图形推理、科学推理那些题选项是图，
// 文本解析同样解不出选项，但答案能到 C/D，补成两项就全错了。
const JUDGE_MARK = /[（(]\s*判断题\s*[）)]/;
const JUDGE_OPTIONS = [
  { key: 'A', text: '正确', images: [] },
  { key: 'B', text: '错误', images: [] },
];

const normalizeQuestion = (q, j) => {
  const rawOpts = q.options && typeof q.options === 'object' ? q.options : {};
  const keys = Object.keys(rawOpts);
  const isJudge = JUDGE_MARK.test(q.stem || '');
  const answer = String(q.correct_answer || '').trim().toUpperCase();

  const options = isJudge
    ? JUDGE_OPTIONS
    : keys.sort().map((k) => ({ key: k, text: String(rawOpts[k] ?? ''), images: [] }));

  let questionType = 'single';
  if (isJudge) questionType = 'judge';
  else if (answer.length > 1) questionType = 'multi';

  // 图没有随文本一起解析出来，做题时先告诉人一声，免得对着残缺题干发懵
  const explanation = q.has_figure
    ? `【原题含图，图片未随文本导入】${q.figure_note ? ` 图注：${q.figure_note}` : ''}`
    : null;

  return {
    external_id: `${batchIdOf(j)}-${q.number}`,
    category: q.module || '未分类',
    sub_category: q.subtype || null,
    question_type: questionType,
    content: q.stem || '',
    stem_images: '[]',
    options: JSON.stringify(options),
    correct_answer: answer,
    explanation,
    explanation_images: '[]',
    difficulty: 2,
    tags: JSON.stringify(q.knowledge_points || []),
    source: `${j.year} ${j.exam}·${j.paper}·第 ${q.number} 题`,
    year: j.year ?? null,
    region: regionOf(j),
    material_ref: q.material_ref || null,
    has_figure: !!q.has_figure,
    // 选项没解析出来又不是判断题：这题没法做，只能丢
    broken: !isJudge && options.length === 0,
  };
};

const upsertMat = db.prepare(`
  INSERT INTO materials (external_id, content, images, source, year, region, batch_id)
  VALUES (@external_id, @content, @images, @source, @year, @region, @batch_id)
  ON CONFLICT(external_id) DO UPDATE SET
    content = excluded.content, source = excluded.source,
    year = excluded.year, region = excluded.region, batch_id = excluded.batch_id
`);
const getMatId = db.prepare('SELECT id FROM materials WHERE external_id = ?');

const upsertQ = db.prepare(`
  INSERT INTO questions (
    external_id, category, sub_category, question_type,
    content, stem_images, options, correct_answer,
    explanation, explanation_images, difficulty, tags,
    source, year, region, material_id, batch_id
  ) VALUES (
    @external_id, @category, @sub_category, @question_type,
    @content, @stem_images, @options, @correct_answer,
    @explanation, @explanation_images, @difficulty, @tags,
    @source, @year, @region, @material_id, @batch_id
  )
  ON CONFLICT(external_id) DO UPDATE SET
    category = excluded.category, sub_category = excluded.sub_category,
    question_type = excluded.question_type, content = excluded.content,
    options = excluded.options, correct_answer = excluded.correct_answer,
    explanation = excluded.explanation, difficulty = excluded.difficulty,
    tags = excluded.tags, source = excluded.source, year = excluded.year,
    region = excluded.region, material_id = excluded.material_id,
    batch_id = excluded.batch_id
`);

function importPaper(file) {
  const j = JSON.parse(fs.readFileSync(file, 'utf8'));
  const batchId = batchIdOf(j);
  const questions = (j.questions || []).map((q) => normalizeQuestion(q, j));

  const figured = questions.filter((q) => q.has_figure).length;
  const usable = SKIP_FIGURE ? questions.filter((q) => !q.has_figure) : questions;
  const noAnswer = usable.filter((q) => !q.correct_answer).length;
  const withAnswer = usable.filter((q) => q.correct_answer && q.content);
  const broken = withAnswer.filter((q) => q.broken).length;
  const keep = withAnswer.filter((q) => !q.broken);

  const report = {
    batchId, title: j.title, materials: (j.materials || []).length,
    questions: keep.length, figured, noAnswer, broken,
  };
  if (DRY_RUN) return report;

  const run = db.transaction(() => {
    const matIds = new Map();
    for (const m of j.materials || []) {
      const externalId = `${batchId}-mat-${slug(m.ref)}`;
      upsertMat.run({
        external_id: externalId,
        content: m.text || '',
        images: '[]',
        source: j.title || null,
        year: j.year ?? null,
        region: regionOf(j),
        batch_id: batchId,
      });
      matIds.set(m.ref, getMatId.get(externalId).id);
    }

    for (const q of keep) {
      const { material_ref: ref, has_figure: _hf, broken: _bk, ...row } = q;
      upsertQ.run({ ...row, material_id: ref ? (matIds.get(ref) ?? null) : null, batch_id: batchId });
    }
  });
  run();
  return report;
}

// ---------- main ----------
const stat = fs.statSync(target);
const files = stat.isDirectory()
  ? fs.readdirSync(target).filter((f) => f.endsWith('.json')).map((f) => path.join(target, f)).sort()
  : [target];

if (files.length === 0) {
  console.error(`没有找到 json: ${target}`);
  process.exit(2);
}

console.log(`→ ${DRY_RUN ? '试运行' : '导入'} ${files.length} 套卷${SKIP_FIGURE ? '（跳过缺图题）' : ''}\n`);

let totalQ = 0;
let totalM = 0;
let totalFig = 0;
let totalBroken = 0;
const skipped = [];
for (const f of files) {
  try {
    const r = importPaper(f);
    totalQ += r.questions;
    totalM += r.materials;
    totalFig += r.figured;
    totalBroken += r.broken || 0;
    if (r.questions === 0 && r.noAnswer > 0) {
      skipped.push(r.batchId);
      console.log(
        `  ${'--'.padStart(4)} 题  ${String(r.materials).padStart(2)} 材料  ${r.batchId}` +
          '   整套卷没有答案，跳过（需先跑 scripts/merge_answers.py 合并答案）',
      );
      continue;
    }
    const warn = [];
    if (r.figured) warn.push(`${r.figured} 题缺图`);
    if (r.noAnswer) warn.push(`${r.noAnswer} 题无答案已丢弃`);
    if (r.broken) warn.push(`${r.broken} 题选项缺失已丢弃`);
    console.log(
      `  ${String(r.questions).padStart(4)} 题  ${String(r.materials).padStart(2)} 材料  ${r.batchId}` +
        (warn.length ? `   (${warn.join('，')})` : ''),
    );
  } catch (e) {
    console.error(`  ✗ ${path.basename(f)}: ${e.message}`);
  }
}

console.log(
  `\n合计 ${totalQ} 题 / ${totalM} 段材料，其中 ${totalFig} 题原本含图` +
    (totalBroken ? `，另有 ${totalBroken} 题因选项没解析出来被丢弃` : '') +
    '。',
);
if (skipped.length) {
  console.log(`跳过 ${skipped.length} 套无答案的卷子：${skipped.join('、')}`);
}

if (!DRY_RUN) {
  const byCat = db
    .prepare("SELECT category, COUNT(*) n FROM questions WHERE batch_id LIKE 'zhenti-%' GROUP BY category ORDER BY n DESC")
    .all();
  console.log('\n库里的真题模块分布：');
  for (const r of byCat) console.log(`  ${String(r.n).padStart(4)}  ${r.category}`);
  const total = db.prepare('SELECT COUNT(*) n FROM questions').get().n;
  console.log(`\n✓ questions 表现有 ${total} 题`);
}

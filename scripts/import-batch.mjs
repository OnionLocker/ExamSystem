#!/usr/bin/env node
// scripts/import-batch.mjs
// 用法: node scripts/import-batch.mjs <batch-dir>
// 会先跑校验，通过后把题目写入 SQLite、把图片复制到 public/q-images/<batch_id>/

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import db from '../server/db.js'; // 自动跑 schema / migration
import { validateBatch } from './validate-batch.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PUBLIC_IMG_ROOT = path.join(ROOT, 'public', 'q-images');

const toImgPublicPath = (batchId, rel) =>
  `/q-images/${batchId}/${path.basename(rel)}`;

function copyImages(batchDir, batchId, questions, materials) {
  const destDir = path.join(PUBLIC_IMG_ROOT, batchId);
  fs.mkdirSync(destDir, { recursive: true });

  const collect = (arr) => (Array.isArray(arr) ? arr : []);
  const all = new Set();
  for (const q of questions || []) {
    collect(q.stem_images).forEach((p) => all.add(p));
    collect(q.explanation_images).forEach((p) => all.add(p));
    for (const opt of q.options || []) collect(opt.images).forEach((p) => all.add(p));
  }
  for (const m of materials || []) collect(m.images).forEach((p) => all.add(p));

  let copied = 0;
  for (const rel of all) {
    const src = path.join(batchDir, rel);
    const dst = path.join(destDir, path.basename(rel));
    fs.copyFileSync(src, dst);
    copied++;
  }
  return copied;
}

// 把 JSON 里的相对路径数组改写为绝对 public 路径
const rewrite = (batchId, arr) =>
  Array.isArray(arr) && arr.length ? arr.map((p) => toImgPublicPath(batchId, p)) : null;

function importToDB(manifest, questions, materials) {
  const batchId = manifest.batch_id;

  // UPSERT materials（按 external_id）
  const upsertMat = db.prepare(`
    INSERT INTO materials (external_id, content, images, source, year, region, batch_id)
    VALUES (@external_id, @content, @images, @source, @year, @region, @batch_id)
    ON CONFLICT(external_id) DO UPDATE SET
      content = excluded.content,
      images  = excluded.images,
      source  = excluded.source,
      year    = excluded.year,
      region  = excluded.region,
      batch_id = excluded.batch_id
  `);

  const getMatId = db.prepare(`SELECT id FROM materials WHERE external_id = ?`);

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
      category           = excluded.category,
      sub_category       = excluded.sub_category,
      question_type      = excluded.question_type,
      content            = excluded.content,
      stem_images        = excluded.stem_images,
      options            = excluded.options,
      correct_answer     = excluded.correct_answer,
      explanation        = excluded.explanation,
      explanation_images = excluded.explanation_images,
      difficulty         = excluded.difficulty,
      tags               = excluded.tags,
      source             = excluded.source,
      year               = excluded.year,
      region             = excluded.region,
      material_id        = excluded.material_id,
      batch_id           = excluded.batch_id
  `);

  const stats = { materials: 0, questions: 0 };

  const run = db.transaction(() => {
    // 1) materials
    for (const m of materials || []) {
      upsertMat.run({
        external_id: m.external_id,
        content: m.content,
        images: JSON.stringify(rewrite(batchId, m.images) || []) || null,
        source: m.source ?? manifest.source ?? null,
        year: m.year ?? manifest.year ?? null,
        region: m.region ?? manifest.region ?? null,
        batch_id: batchId,
      });
      stats.materials++;
    }

    // 2) questions
    for (const q of questions || []) {
      let materialId = null;
      if (q.material_id) {
        const row = getMatId.get(q.material_id);
        if (!row) throw new Error(`material_id ${q.material_id} 未找到（导入中）`);
        materialId = row.id;
      }

      // 规范化 answer
      let answer = q.answer;
      if (Array.isArray(answer)) answer = [...answer].sort().join('');

      // options 路径改写
      const opts = Array.isArray(q.options)
        ? q.options.map((o) => ({
            key: o.key,
            text: o.text ?? '',
            images: rewrite(batchId, o.images) || [],
          }))
        : null;

      upsertQ.run({
        external_id: q.external_id,
        category: q.category,
        sub_category: q.sub_category ?? null,
        question_type: q.question_type ?? 'single',
        content: q.stem,
        stem_images: JSON.stringify(rewrite(batchId, q.stem_images) || []),
        options: opts ? JSON.stringify(opts) : null,
        correct_answer: String(answer),
        explanation: q.explanation ?? null,
        explanation_images: JSON.stringify(rewrite(batchId, q.explanation_images) || []),
        difficulty: q.difficulty ?? 2,
        tags: JSON.stringify(q.tags ?? []),
        source: q.source ?? manifest.source ?? null,
        year: q.year ?? manifest.year ?? null,
        region: q.region ?? manifest.region ?? null,
        material_id: materialId,
        batch_id: batchId,
      });
      stats.questions++;
    }
  });

  run();
  return stats;
}

// ---------- main ----------
const dir = process.argv[2];
if (!dir) {
  console.error('用法: node scripts/import-batch.mjs <batch-dir>');
  process.exit(2);
}
const abs = path.resolve(dir);

console.log(`→ 导入批次: ${abs}`);
const { rep, manifest, materialMap, questions } = validateBatch(abs);
rep.print();
if (!rep.ok) {
  console.log('\n✗ 校验失败，已中止导入');
  process.exit(1);
}

const materials = Array.from(materialMap.values());

console.log('\n→ 复制图片到 public/q-images/ ...');
const imgCount = copyImages(abs, manifest.batch_id, questions, materials);
console.log(`  已复制 ${imgCount} 张图片`);

console.log('→ 写入数据库 ...');
const stats = importToDB(manifest, questions, materials);
console.log(`  materials: ${stats.materials}`);
console.log(`  questions: ${stats.questions}`);

console.log(`\n✓ 导入完成 | batch_id=${manifest.batch_id}`);

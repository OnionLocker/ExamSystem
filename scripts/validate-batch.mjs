#!/usr/bin/env node
// scripts/validate-batch.mjs
// 用法: node scripts/validate-batch.mjs <batch-dir>
// 零依赖；校验规范见 docs/IMPORT_SPEC.md

import fs from 'node:fs';
import path from 'node:path';

// ---------- 枚举 ----------
export const CATEGORY_ENUM = {
  政治理论: [],
  常识判断: [],
  言语理解与表达: [],
  数量关系: ['数字推理', '数学运算'],
  判断推理: ['图形推理', '逻辑判断', '科学推理'],
  资料分析: [],
};

const REGION_ENUM = new Set([
  '广东-省直',
  '广东-县级',
  '广东-乡镇',
  '广东-选调',
  '广东-模拟',
]);

const QUESTION_TYPES = new Set(['single', 'multi', 'judge']);
const IMG_EXT = new Set(['.png', '.jpg', '.jpeg', '.webp']);
const IMG_HARD_LIMIT = 2 * 1024 * 1024; // 2MB
const IMG_SOFT_LIMIT = 500 * 1024; // 500KB 警告

const BATCH_ID_RE = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;

// ---------- 工具 ----------
const readJSON = (p) => JSON.parse(fs.readFileSync(p, 'utf-8'));
const exists = (p) => fs.existsSync(p);

class Report {
  constructor() {
    this.errors = [];
    this.warnings = [];
  }
  err(path, msg) {
    this.errors.push({ path, msg });
  }
  warn(path, msg) {
    this.warnings.push({ path, msg });
  }
  get ok() {
    return this.errors.length === 0;
  }
  print() {
    if (this.warnings.length) {
      console.log(`\n⚠  ${this.warnings.length} warning(s):`);
      for (const w of this.warnings) console.log(`  - [${w.path}] ${w.msg}`);
    }
    if (this.errors.length) {
      console.log(`\n✗  ${this.errors.length} error(s):`);
      for (const e of this.errors) console.log(`  - [${e.path}] ${e.msg}`);
    }
  }
}

// ---------- 校验各部分 ----------

function validateManifest(dir, rep) {
  const p = path.join(dir, 'manifest.json');
  if (!exists(p)) {
    rep.err('manifest.json', '文件不存在');
    return null;
  }
  let m;
  try {
    m = readJSON(p);
  } catch (e) {
    rep.err('manifest.json', `JSON 解析失败: ${e.message}`);
    return null;
  }
  const required = ['batch_id', 'source', 'region', 'year'];
  for (const k of required) {
    if (m[k] === undefined || m[k] === null || m[k] === '') {
      rep.err('manifest.json', `缺少必填字段: ${k}`);
    }
  }
  if (m.batch_id && !BATCH_ID_RE.test(m.batch_id)) {
    rep.err(
      'manifest.json',
      `batch_id 格式非法（只允许小写字母/数字/中划线，2~50 位）: ${m.batch_id}`
    );
  }
  if (m.region && !REGION_ENUM.has(m.region)) {
    rep.err(
      'manifest.json',
      `region 不在枚举内: ${m.region}（允许: ${[...REGION_ENUM].join(', ')}）`
    );
  }
  if (m.year != null && (!Number.isInteger(m.year) || m.year < 1990 || m.year > 2100)) {
    rep.err('manifest.json', `year 非法: ${m.year}`);
  }
  return m;
}

function validateMaterials(dir, manifest, rep) {
  const p = path.join(dir, 'materials.json');
  if (!exists(p)) return new Map();

  let arr;
  try {
    arr = readJSON(p);
  } catch (e) {
    rep.err('materials.json', `JSON 解析失败: ${e.message}`);
    return new Map();
  }
  if (!Array.isArray(arr)) {
    rep.err('materials.json', '必须是数组');
    return new Map();
  }

  const seen = new Set();
  const map = new Map();
  arr.forEach((m, idx) => {
    const loc = `materials[${idx}]`;
    if (!m.external_id) rep.err(loc, '缺 external_id');
    else if (seen.has(m.external_id))
      rep.err(loc, `external_id 重复: ${m.external_id}`);
    else seen.add(m.external_id);

    if (!m.content || typeof m.content !== 'string')
      rep.err(loc, 'content 必须是非空字符串');

    checkImagePaths(m.images, `${loc}.images`, dir, rep);

    const region = m.region ?? manifest?.region;
    if (region && !REGION_ENUM.has(region))
      rep.err(loc, `region 不在枚举内: ${region}`);

    if (m.external_id) map.set(m.external_id, m);
  });
  return map;
}

function validateQuestions(dir, manifest, materialMap, rep) {
  const p = path.join(dir, 'questions.json');
  if (!exists(p)) {
    rep.err('questions.json', '文件不存在');
    return;
  }
  let arr;
  try {
    arr = readJSON(p);
  } catch (e) {
    rep.err('questions.json', `JSON 解析失败: ${e.message}`);
    return;
  }
  if (!Array.isArray(arr)) {
    rep.err('questions.json', '必须是数组');
    return;
  }
  if (arr.length === 0) rep.warn('questions.json', '题目为空');

  const seen = new Set();

  arr.forEach((q, idx) => {
    const loc = `questions[${idx}]${q.external_id ? ` (${q.external_id})` : ''}`;

    // external_id
    if (!q.external_id) rep.err(loc, '缺 external_id');
    else if (seen.has(q.external_id))
      rep.err(loc, `external_id 重复: ${q.external_id}`);
    else seen.add(q.external_id);

    // category
    if (!q.category) {
      rep.err(loc, '缺 category');
    } else if (!(q.category in CATEGORY_ENUM)) {
      rep.err(
        loc,
        `category 不在枚举内: "${q.category}"（允许: ${Object.keys(CATEGORY_ENUM).join(
          ', '
        )}）`
      );
    } else {
      const allowedSubs = CATEGORY_ENUM[q.category];
      if (q.sub_category != null && q.sub_category !== '') {
        if (allowedSubs.length === 0) {
          rep.err(loc, `${q.category} 不允许有 sub_category，但填了: ${q.sub_category}`);
        } else if (!allowedSubs.includes(q.sub_category)) {
          rep.err(
            loc,
            `sub_category "${q.sub_category}" 不属于 ${q.category}（允许: ${allowedSubs.join(
              ', '
            )}）`
          );
        }
      }
    }

    // question_type
    const qt = q.question_type || 'single';
    if (!QUESTION_TYPES.has(qt))
      rep.err(loc, `question_type 非法: ${qt}（允许: single/multi/judge）`);

    // stem
    if (!q.stem || typeof q.stem !== 'string' || !q.stem.trim())
      rep.err(loc, 'stem 必须是非空字符串');

    // stem_images
    checkImagePaths(q.stem_images, `${loc}.stem_images`, dir, rep);
    checkImagePaths(q.explanation_images, `${loc}.explanation_images`, dir, rep);

    // options & answer
    if (qt === 'judge') {
      if (!['T', 'F', '对', '错'].includes(q.answer))
        rep.err(loc, `judge 题 answer 必须是 T/F（或 对/错），收到: ${q.answer}`);
    } else {
      if (!Array.isArray(q.options) || q.options.length < 2) {
        rep.err(loc, 'options 至少要 2 项');
      } else {
        const keys = [];
        q.options.forEach((opt, j) => {
          const ol = `${loc}.options[${j}]`;
          if (!opt.key) rep.err(ol, '缺 key');
          else if (!/^[A-E]$/.test(opt.key))
            rep.err(ol, `key 必须是 A/B/C/D/E，收到: ${opt.key}`);
          else if (keys.includes(opt.key)) rep.err(ol, `key 重复: ${opt.key}`);
          else keys.push(opt.key);

          const hasText = opt.text && String(opt.text).trim() !== '';
          const hasImg = Array.isArray(opt.images) && opt.images.length > 0;
          if (!hasText && !hasImg)
            rep.err(ol, 'text 与 images 至少要有一个非空');

          checkImagePaths(opt.images, `${ol}.images`, dir, rep);
        });

        // answer
        if (qt === 'single') {
          if (typeof q.answer !== 'string' || !/^[A-E]$/.test(q.answer))
            rep.err(loc, `single 题 answer 必须是单个字母 A~E，收到: ${q.answer}`);
          else if (!keys.includes(q.answer))
            rep.err(loc, `answer ${q.answer} 不在 options 的 key 里`);
        } else if (qt === 'multi') {
          let keysAns;
          if (Array.isArray(q.answer)) keysAns = [...q.answer];
          else if (typeof q.answer === 'string') keysAns = q.answer.split('');
          else {
            rep.err(loc, `multi 题 answer 必须是字符串或数组`);
            keysAns = [];
          }
          if (keysAns.length < 2)
            rep.err(loc, `multi 题 answer 至少 2 个 key，收到: ${JSON.stringify(q.answer)}`);
          for (const k of keysAns) {
            if (!/^[A-E]$/.test(k))
              rep.err(loc, `multi 题 answer 包含非法 key: ${k}`);
            else if (!keys.includes(k))
              rep.err(loc, `multi 题 answer key ${k} 不在 options 里`);
          }
        }
      }
    }

    // material_id
    if (q.material_id != null && q.material_id !== '') {
      if (!materialMap.has(q.material_id))
        rep.err(loc, `material_id "${q.material_id}" 在 materials.json 中不存在`);
    }

    // difficulty
    if (q.difficulty != null) {
      if (!Number.isInteger(q.difficulty) || q.difficulty < 1 || q.difficulty > 5)
        rep.err(loc, `difficulty 必须是 1~5 的整数，收到: ${q.difficulty}`);
    }

    // region 覆盖
    const region = q.region ?? manifest?.region;
    if (region && !REGION_ENUM.has(region))
      rep.err(loc, `region 不在枚举内: ${region}`);
  });

  return arr;
}

function checkImagePaths(paths, loc, dir, rep) {
  if (!paths) return;
  if (!Array.isArray(paths)) {
    rep.err(loc, '必须是字符串数组');
    return;
  }
  for (const rel of paths) {
    if (typeof rel !== 'string' || !rel.trim()) {
      rep.err(loc, `包含空路径`);
      continue;
    }
    if (rel.startsWith('/') || /^https?:\/\//.test(rel) || rel.includes('..')) {
      rep.err(loc, `非法路径: ${rel}（必须是 images/ 下的相对路径）`);
      continue;
    }
    if (!rel.startsWith('images/')) {
      rep.err(loc, `路径必须以 images/ 开头: ${rel}`);
      continue;
    }
    const ext = path.extname(rel).toLowerCase();
    if (!IMG_EXT.has(ext)) {
      rep.err(loc, `不支持的图片格式: ${rel}（允许: ${[...IMG_EXT].join(', ')}）`);
      continue;
    }
    const abs = path.join(dir, rel);
    if (!exists(abs)) {
      rep.err(loc, `图片文件不存在: ${rel}`);
      continue;
    }
    const size = fs.statSync(abs).size;
    if (size > IMG_HARD_LIMIT)
      rep.err(loc, `图片超过硬上限 2MB: ${rel} (${(size / 1024).toFixed(0)}KB)`);
    else if (size > IMG_SOFT_LIMIT)
      rep.warn(loc, `图片超过建议大小 500KB: ${rel} (${(size / 1024).toFixed(0)}KB)`);
  }
}

// ---------- 主入口 ----------
export function validateBatch(dir) {
  const rep = new Report();
  if (!exists(dir) || !fs.statSync(dir).isDirectory()) {
    rep.err('batch-dir', `不是目录或不存在: ${dir}`);
    return rep;
  }
  const manifest = validateManifest(dir, rep);
  const materialMap = validateMaterials(dir, manifest, rep);
  const questions = validateQuestions(dir, manifest, materialMap, rep);

  return { rep, manifest, materialMap, questions };
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  const dir = process.argv[2];
  if (!dir) {
    console.error('用法: node scripts/validate-batch.mjs <batch-dir>');
    process.exit(2);
  }
  const abs = path.resolve(dir);
  console.log(`→ 校验批次: ${abs}`);
  const { rep, manifest, questions } = validateBatch(abs);
  rep.print();
  if (rep.ok) {
    console.log(
      `\n✓ 校验通过  batch_id=${manifest?.batch_id}  题目=${questions?.length ?? 0}`
    );
    process.exit(0);
  } else {
    console.log(`\n✗ 校验失败`);
    process.exit(1);
  }
}

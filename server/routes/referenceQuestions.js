import { Router } from 'express';
import multer from 'multer';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import db from '../db.js';

const router = Router();
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const IMAGE_ROOT = path.join(ROOT, 'public', 'q-images', 'references');
const IMAGE_PREFIX = '/q-images/references/';
const CATEGORIES = new Set([
  '政治理论',
  '常识判断',
  '言语理解与表达',
  '数量关系',
  '判断推理',
  '资料分析',
]);
const QUESTION_TYPES = new Set(['single', 'multi', 'judge']);
const EXTERNAL_ID_RE = /^[一-鿿A-Za-z0-9][一-鿿A-Za-z0-9_-]{0,118}[一-鿿A-Za-z0-9]$|^[一-鿿A-Za-z0-9]$/;
const IMAGE_FIELD_RE = /^(stem_images|explanation_images|option_[A-E]_images)$/;

class InputError extends Error {}
const bad = (message) => { throw new InputError(message); };
const jsonArray = (value) => {
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};
const parseRow = (row) => row && ({
  ...row,
  stem_images: jsonArray(row.stem_images),
  explanation_images: jsonArray(row.explanation_images),
  options: jsonArray(row.options),
  tags: jsonArray(row.tags),
});
const text = (value, name, { required = false, max = 20000 } = {}) => {
  const out = value == null ? '' : String(value).trim();
  if (required && !out) bad(`${name} 必填`);
  if (out.length > max) bad(`${name} 最长 ${max} 字符`);
  return out || null;
};
const int = (value, name, min, max, fallback = null) => {
  if (value == null || value === '') return fallback;
  if (!Number.isInteger(value) || value < min || value > max) {
    bad(`${name} 必须是 ${min}~${max} 的整数`);
  }
  return value;
};
const optionImages = (row, key) =>
  row?.options?.find((option) => option.key === key)?.images || [];

export function validateReferenceQuestion(input, uploadedFields = new Set(), existing = null) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) bad('question 必须是 JSON 对象');
  const externalId = text(input.external_id, 'external_id', { required: true, max: 120 });
  if (!EXTERNAL_ID_RE.test(externalId)) {
    bad('external_id 只允许中文、字母、数字、下划线和中划线，长度 1~120');
  }
  const category = text(input.category, 'category', { required: true, max: 40 });
  if (!CATEGORIES.has(category)) bad(`category 不合法：${category}`);
  const subCategory = text(input.sub_category, 'sub_category', { required: true, max: 80 });
  const questionType = input.question_type || 'single';
  if (!QUESTION_TYPES.has(questionType)) bad('question_type 只允许 single / multi / judge');
  const stem = text(input.stem, 'stem', { required: true, max: 20000 });
  const source = text(input.source, 'source', { required: true, max: 200 });

  if (!Array.isArray(input.tags) || input.tags.length < 1 || input.tags.length > 20) {
    bad('tags 必须是包含 1~20 个考点标签的数组');
  }
  const tags = [...new Set(input.tags.map((tag) => text(tag, 'tags[]', { required: true, max: 100 })))];
  const difficulty = int(input.difficulty, 'difficulty', 1, 5, 2);
  const year = int(input.year, 'year', 1990, 2100);
  const clearImages = input.clear_images === true;

  let options = [];
  let answer = input.answer;
  if (questionType === 'judge') {
    if (answer === '对') answer = 'T';
    if (answer === '错') answer = 'F';
    if (!['T', 'F'].includes(answer)) bad('判断题 answer 必须是 T / F（也接受 对 / 错）');
  } else {
    if (!Array.isArray(input.options) || input.options.length < 2 || input.options.length > 5) {
      bad('单选题/多选题 options 必须包含 2~5 项');
    }
    const seen = new Set();
    options = input.options.map((option, index) => {
      if (!option || typeof option !== 'object') bad(`options[${index}] 必须是对象`);
      const key = String(option.key || '').toUpperCase();
      if (!/^[A-E]$/.test(key) || seen.has(key)) bad(`options[${index}].key 非法或重复`);
      seen.add(key);
      const optionText = text(option.text, `options[${index}].text`, { max: 5000 });
      const imageField = `option_${key}_images`;
      const hasImages = uploadedFields.has(imageField)
        || (!clearImages && optionImages(existing, key).length > 0);
      if (!optionText && !hasImages) bad(`选项 ${key} 必须包含文字或图片附件`);
      return { key, text: optionText || '' };
    });
    const keys = options.map((option) => option.key);
    for (const field of uploadedFields) {
      const match = field.match(/^option_([A-E])_images$/);
      if (match && !keys.includes(match[1])) bad(`${field} 没有对应选项`);
    }
    if (Array.isArray(answer)) answer = answer.join('');
    answer = String(answer || '').toUpperCase().split('').sort().join('');
    if (questionType === 'single' && (answer.length !== 1 || !keys.includes(answer))) {
      bad('单选题 answer 必须是选项中的一个字母');
    }
    if (questionType === 'multi') {
      if (answer.length < 2 || new Set(answer).size !== answer.length
        || [...answer].some((key) => !keys.includes(key))) {
        bad('多选题 answer 必须包含至少两个不重复的有效选项字母');
      }
    }
  }
  if (questionType === 'judge' && [...uploadedFields].some((field) => field.startsWith('option_'))) {
    bad('判断题不接受选项图片字段');
  }

  const sourceUrl = text(input.source_url, 'source_url', { max: 2000 });
  if (sourceUrl) {
    let parsed;
    try { parsed = new URL(sourceUrl); } catch { bad('source_url 必须是有效 URL'); }
    if (!['http:', 'https:'].includes(parsed.protocol)) bad('source_url 只允许 http / https');
  }

  return {
    external_id: externalId,
    category,
    sub_category: subCategory,
    question_type: questionType,
    stem,
    options,
    answer: String(answer),
    explanation: text(input.explanation, 'explanation', { max: 50000 }),
    difficulty,
    tags,
    source,
    year,
    region: text(input.region, 'region', { max: 100 }),
    source_url: sourceUrl,
    imported_by: text(input.imported_by, 'imported_by', { max: 100 }) || 'agent',
    clear_images: clearImages,
  };
}

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 2 * 1024 * 1024, files: 20, fields: 50 },
  fileFilter: (_req, file, cb) => {
    if (!IMAGE_FIELD_RE.test(file.fieldname)) return cb(new Error(`不支持的图片字段：${file.fieldname}`));
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.mimetype)) {
      return cb(new Error('图片只支持 PNG / JPEG / WebP'));
    }
    return cb(null, true);
  },
});

const detectImage = (buffer) => {
  if (buffer.length >= 8 && buffer.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'))) {
    return { ext: '.png', mime: 'image/png' };
  }
  if (buffer.length >= 3 && buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) {
    return { ext: '.jpg', mime: 'image/jpeg' };
  }
  if (buffer.length >= 12 && buffer.subarray(0, 4).toString() === 'RIFF'
    && buffer.subarray(8, 12).toString() === 'WEBP') {
    return { ext: '.webp', mime: 'image/webp' };
  }
  bad('图片内容与 PNG / JPEG / WebP 格式不符');
};

const publicPathToFile = (publicPath) => {
  if (!publicPath?.startsWith(IMAGE_PREFIX)) return null;
  let rel;
  try { rel = decodeURIComponent(publicPath.slice(IMAGE_PREFIX.length)); } catch { return null; }
  const abs = path.resolve(IMAGE_ROOT, rel);
  return abs.startsWith(`${IMAGE_ROOT}${path.sep}`) ? abs : null;
};
const unlinkPaths = (paths) => {
  for (const publicPath of paths) {
    const file = publicPathToFile(publicPath);
    if (file) {
      try { fs.unlinkSync(file); } catch { /* 已删或不存在即可 */ }
    }
  }
};
const allImagePaths = (row) => [
  ...(row?.stem_images || []),
  ...(row?.explanation_images || []),
  ...(row?.options || []).flatMap((option) => option.images || []),
];

const saveFiles = (externalId, files) => {
  if (!files.length) return new Map();
  for (const file of files) detectImage(file.buffer);
  const dir = path.join(IMAGE_ROOT, externalId);
  fs.mkdirSync(dir, { recursive: true });
  const groups = new Map();
  for (const file of files) {
    const { ext } = detectImage(file.buffer);
    const name = `${file.fieldname}-${crypto.randomUUID()}${ext}`;
    fs.writeFileSync(path.join(dir, name), file.buffer, { flag: 'wx' });
    const url = `${IMAGE_PREFIX}${encodeURIComponent(externalId)}/${name}`;
    groups.set(file.fieldname, [...(groups.get(file.fieldname) || []), url]);
  }
  return groups;
};

const upsert = db.prepare(`
  INSERT INTO reference_questions (
    external_id, category, sub_category, question_type, content,
    stem_images, options, correct_answer, explanation, explanation_images,
    difficulty, tags, source, year, region, source_url, imported_by
  ) VALUES (
    @external_id, @category, @sub_category, @question_type, @content,
    @stem_images, @options, @correct_answer, @explanation, @explanation_images,
    @difficulty, @tags, @source, @year, @region, @source_url, @imported_by
  )
  ON CONFLICT(external_id) DO UPDATE SET
    category = excluded.category,
    sub_category = excluded.sub_category,
    question_type = excluded.question_type,
    content = excluded.content,
    stem_images = excluded.stem_images,
    options = excluded.options,
    correct_answer = excluded.correct_answer,
    explanation = excluded.explanation,
    explanation_images = excluded.explanation_images,
    difficulty = excluded.difficulty,
    tags = excluded.tags,
    source = excluded.source,
    year = excluded.year,
    region = excluded.region,
    source_url = excluded.source_url,
    imported_by = excluded.imported_by,
    updated_at = datetime('now', '+8 hours')
`);
const selectOne = db.prepare('SELECT * FROM reference_questions WHERE external_id = ?');

const handleUpload = (req, res) => {
  const isMultipart = req.is('multipart/form-data');
  let input = req.body;
  if (isMultipart) {
    try { input = JSON.parse(req.body?.question || ''); } catch { return res.status(400).json({ error: 'question 必须是有效 JSON' }); }
  }
  const files = req.files || [];
  const fields = new Set(files.map((file) => file.fieldname));
  let existing;
  let normalized;
  let uploaded = new Map();
  let newPaths = [];
  try {
    const externalId = text(input?.external_id, 'external_id', { required: true, max: 120 });
    existing = parseRow(selectOne.get(externalId));
    normalized = validateReferenceQuestion(input, fields, existing);
    uploaded = saveFiles(normalized.external_id, files);
    newPaths = [...uploaded.values()].flat();

    const preserved = (field, oldPaths) =>
      uploaded.has(field) ? uploaded.get(field) : (normalized.clear_images ? [] : oldPaths || []);
    const stemImages = preserved('stem_images', existing?.stem_images);
    const explanationImages = preserved('explanation_images', existing?.explanation_images);
    const options = normalized.options.map((option) => ({
      ...option,
      images: preserved(`option_${option.key}_images`, optionImages(existing, option.key)),
    }));

    upsert.run({
      external_id: normalized.external_id,
      category: normalized.category,
      sub_category: normalized.sub_category,
      question_type: normalized.question_type,
      content: normalized.stem,
      stem_images: JSON.stringify(stemImages),
      options: JSON.stringify(options),
      correct_answer: normalized.answer,
      explanation: normalized.explanation,
      explanation_images: JSON.stringify(explanationImages),
      difficulty: normalized.difficulty,
      tags: JSON.stringify(normalized.tags),
      source: normalized.source,
      year: normalized.year,
      region: normalized.region,
      source_url: normalized.source_url,
      imported_by: normalized.imported_by,
    });
    const item = parseRow(selectOne.get(normalized.external_id));
    const keep = new Set(allImagePaths(item));
    unlinkPaths(allImagePaths(existing).filter((image) => !keep.has(image)));
    return res.status(existing ? 200 : 201).json({ ok: true, created: !existing, item });
  } catch (error) {
    unlinkPaths(newPaths);
    const status = error instanceof InputError ? 400 : 500;
    return res.status(status).json({ error: error.message || '导入失败' });
  }
};

router.get('/schema', (_req, res) => {
  res.json({
    endpoint: 'POST /api/reference-questions',
    auth: 'Authorization: Bearer <token>',
    content_types: {
      json: '直接发送题目 JSON（无新图片）',
      multipart: 'question=<题目JSON>；图片字段可重复上传',
    },
    image_fields: ['stem_images', 'explanation_images', 'option_A_images ... option_E_images'],
    required: ['external_id', 'category', 'sub_category', 'stem', 'answer', 'tags', 'source'],
    conditional: ['single/multi 必须提供 options；judge 不需要 options'],
    categories: [...CATEGORIES],
    question_types: [...QUESTION_TYPES],
    limits: { image_bytes: 2 * 1024 * 1024, images_per_request: 20 },
    notes: [
      'external_id 幂等：重复提交会更新原题',
      '更新时未重新上传的图片默认保留；clear_images=true 可清空旧图片',
      '参考题与 AI 练题题库隔离，不参与练习和画像统计',
    ],
  });
});

router.get('/', (req, res) => {
  const limit = Math.min(50, Math.max(1, Number.parseInt(req.query.limit, 10) || 5));
  const where = [];
  const params = [];
  for (const [query, column] of [['category', 'category'], ['sub_category', 'sub_category'], ['region', 'region']]) {
    if (req.query[query]) { where.push(`${column} = ?`); params.push(String(req.query[query])); }
  }
  if (req.query.year) {
    const year = Number.parseInt(req.query.year, 10);
    if (!Number.isInteger(year)) return res.status(400).json({ error: 'year 必须是整数' });
    where.push('year = ?');
    params.push(year);
  }
  if (req.query.tag) {
    where.push('EXISTS (SELECT 1 FROM json_each(reference_questions.tags) WHERE value = ?)');
    params.push(String(req.query.tag));
  }
  const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';
  const order = req.query.random === '1' ? 'RANDOM()' : 'id DESC';
  const rows = db.prepare(`SELECT * FROM reference_questions ${clause} ORDER BY ${order} LIMIT ?`)
    .all(...params, limit);
  res.json({ items: rows.map(parseRow), total: rows.length });
});

router.get('/:externalId', (req, res) => {
  const row = parseRow(selectOne.get(String(req.params.externalId)));
  if (!row) return res.status(404).json({ error: 'reference question not found' });
  return res.json(row);
});

router.post('/', (req, res) => {
  if (!req.is('multipart/form-data')) return handleUpload(req, res);
  return upload.any()(req, res, (error) => {
    if (error) return res.status(400).json({ error: error.message || '图片上传失败' });
    return handleUpload(req, res);
  });
});

router.delete('/:externalId', (req, res) => {
  const externalId = String(req.params.externalId);
  const row = parseRow(selectOne.get(externalId));
  if (!row) return res.status(404).json({ error: 'reference question not found' });
  db.prepare('DELETE FROM reference_questions WHERE external_id = ?').run(externalId);
  unlinkPaths(allImagePaths(row));
  const dir = path.join(IMAGE_ROOT, externalId);
  try { fs.rmdirSync(dir); } catch { /* 非空或不存在即可 */ }
  return res.json({ ok: true, deleted: externalId });
});

router.use((error, _req, res, _next) => {
  res.status(400).json({ error: error?.message || '请求格式错误' });
});

export default router;

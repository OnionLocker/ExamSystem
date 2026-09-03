import { Router } from 'express';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import db from '../db.js';

const router = Router();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const uploadDir = path.join(__dirname, '..', '..', 'data', 'review-images');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });

const ALLOWED_MIME = new Set([
  'image/jpeg',
  'image/jpg',
  'image/png',
  'image/webp',
  'image/gif',
  'image/bmp',
  'image/heic',
  'image/heif',
]);

const EXT_FROM_MIME = {
  'image/jpeg': '.jpg',
  'image/jpg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'image/gif': '.gif',
  'image/bmp': '.bmp',
  'image/heic': '.heic',
  'image/heif': '.heif',
};

function imageCount(moduleId) {
  const row = db
    .prepare('SELECT COUNT(*) AS c FROM review_images WHERE module_id = ?')
    .get(moduleId);
  return row?.c || 0;
}

function moduleRow(id) {
  const m = db.prepare('SELECT * FROM review_modules WHERE id = ?').get(id);
  if (!m) return null;
  return { ...m, image_count: imageCount(id) };
}

function safeUnlink(filename) {
  if (!filename || filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
    return;
  }
  const full = path.join(uploadDir, filename);
  try {
    if (fs.existsSync(full)) fs.unlinkSync(full);
  } catch {
    /* ignore */
  }
}

// GET /api/review-modules
router.get('/', (_req, res) => {
  const rows = db
    .prepare('SELECT * FROM review_modules ORDER BY sort_order ASC, id DESC')
    .all()
    .map((m) => ({ ...m, image_count: imageCount(m.id) }));
  res.json(rows);
});

// POST /api/review-modules  { name }
router.post('/', (req, res) => {
  const name = String(req.body?.name || '').trim();
  if (!name) return res.status(400).json({ error: 'name 必填' });
  if (name.length > 80) return res.status(400).json({ error: '名称过长' });

  const maxSort = db.prepare('SELECT COALESCE(MAX(sort_order), 0) AS m FROM review_modules').get().m;
  const info = db
    .prepare(
      `INSERT INTO review_modules (name, sort_order, updated_at)
       VALUES (?, ?, datetime('now', '+8 hours'))`
    )
    .run(name, maxSort + 1);

  res.status(201).json(moduleRow(info.lastInsertRowid));
});

// PUT /api/review-modules/:id  { name?, sort_order? }
router.put('/:id', (req, res) => {
  const id = Number(req.params.id);
  const exists = db.prepare('SELECT id FROM review_modules WHERE id = ?').get(id);
  if (!exists) return res.status(404).json({ error: 'not found' });

  const sets = [];
  const params = { id };
  if (req.body?.name !== undefined) {
    const name = String(req.body.name || '').trim();
    if (!name) return res.status(400).json({ error: 'name 不能为空' });
    if (name.length > 80) return res.status(400).json({ error: '名称过长' });
    sets.push('name = @name');
    params.name = name;
  }
  if (req.body?.sort_order !== undefined) {
    sets.push('sort_order = @sort_order');
    params.sort_order = Number(req.body.sort_order) || 0;
  }
  if (!sets.length) return res.json(moduleRow(id));

  sets.push('updated_at = datetime('now', '+8 hours')');
  db.prepare(`UPDATE review_modules SET ${sets.join(', ')} WHERE id = @id`).run(params);
  res.json(moduleRow(id));
});

// DELETE /api/review-modules/:id
router.delete('/:id', (req, res) => {
  const id = Number(req.params.id);
  const images = db
    .prepare('SELECT filename FROM review_images WHERE module_id = ?')
    .all(id);
  const info = db.prepare('DELETE FROM review_modules WHERE id = ?').run(id);
  if (!info.changes) return res.status(404).json({ error: 'not found' });
  for (const img of images) safeUnlink(img.filename);
  res.json({ ok: true });
});

// GET /api/review-modules/:id/images
router.get('/:id/images', (req, res) => {
  const id = Number(req.params.id);
  const mod = db.prepare('SELECT id FROM review_modules WHERE id = ?').get(id);
  if (!mod) return res.status(404).json({ error: 'not found' });

  const rows = db
    .prepare(
      `SELECT id, module_id, filename, orig_name, mime, sort_order, created_at
       FROM review_images WHERE module_id = ? ORDER BY sort_order ASC, id ASC`
    )
    .all(id)
    .map((r) => ({
      ...r,
      url: `/api/review-modules/${id}/images/${r.id}/file`,
    }));
  res.json(rows);
});

// POST /api/review-modules/:id/images  { data: base64, mime?, orig_name? }
// data 可为纯 base64，或 data:image/png;base64,... 形式
router.post('/:id/images', (req, res) => {
  const id = Number(req.params.id);
  const mod = db.prepare('SELECT id FROM review_modules WHERE id = ?').get(id);
  if (!mod) return res.status(404).json({ error: 'not found' });

  let { data, mime, orig_name } = req.body || {};
  if (!data || typeof data !== 'string') {
    return res.status(400).json({ error: 'data 必填（base64 图片）' });
  }

  // 解析 data URL
  const dataUrlMatch = data.match(/^data:([^;]+);base64,(.+)$/s);
  if (dataUrlMatch) {
    mime = mime || dataUrlMatch[1];
    data = dataUrlMatch[2];
  }

  mime = String(mime || 'image/jpeg').toLowerCase().trim();
  if (mime === 'image/jpg') mime = 'image/jpeg';
  if (!ALLOWED_MIME.has(mime)) {
    return res.status(400).json({ error: `不支持的图片类型: ${mime}` });
  }

  let buf;
  try {
    buf = Buffer.from(data, 'base64');
  } catch {
    return res.status(400).json({ error: 'base64 解码失败' });
  }
  if (!buf.length) return res.status(400).json({ error: '图片为空' });
  if (buf.length > 15 * 1024 * 1024) {
    return res.status(400).json({ error: '单张图片不能超过 15MB' });
  }

  const ext = EXT_FROM_MIME[mime] || '.jpg';
  const filename = `${crypto.randomUUID()}${ext}`;
  const fullPath = path.join(uploadDir, filename);
  fs.writeFileSync(fullPath, buf);

  const maxSort = db
    .prepare('SELECT COALESCE(MAX(sort_order), 0) AS m FROM review_images WHERE module_id = ?')
    .get(id).m;

  const info = db
    .prepare(
      `INSERT INTO review_images (module_id, filename, orig_name, mime, sort_order)
       VALUES (?, ?, ?, ?, ?)`
    )
    .run(id, filename, orig_name ? String(orig_name).slice(0, 200) : null, mime, maxSort + 1);

  db.prepare('UPDATE review_modules SET updated_at = datetime('now', '+8 hours') WHERE id = ?').run(id);

  const row = db.prepare('SELECT * FROM review_images WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json({
    ...row,
    url: `/api/review-modules/${id}/images/${row.id}/file`,
  });
});

// PUT /api/review-modules/:id/images/:imageId  { orig_name }
router.put('/:id/images/:imageId', (req, res) => {
  const moduleId = Number(req.params.id);
  const imageId = Number(req.params.imageId);
  const row = db
    .prepare('SELECT * FROM review_images WHERE id = ? AND module_id = ?')
    .get(imageId, moduleId);
  if (!row) return res.status(404).json({ error: 'not found' });

  if (req.body?.orig_name === undefined) {
    return res.status(400).json({ error: 'orig_name 必填' });
  }
  const name = String(req.body.orig_name || '').trim();
  if (!name) return res.status(400).json({ error: '名称不能为空' });
  if (name.length > 200) return res.status(400).json({ error: '名称过长' });

  db.prepare('UPDATE review_images SET orig_name = ? WHERE id = ?').run(name, imageId);
  db.prepare('UPDATE review_modules SET updated_at = datetime('now', '+8 hours') WHERE id = ?').run(moduleId);

  const updated = db.prepare('SELECT * FROM review_images WHERE id = ?').get(imageId);
  res.json({
    ...updated,
    url: `/api/review-modules/${moduleId}/images/${imageId}/file`,
  });
});

// POST /api/review-modules/:id/images/reorder  { ids: number[] }
router.post('/:id/images/reorder', (req, res) => {
  const id = Number(req.params.id);
  const mod = db.prepare('SELECT id FROM review_modules WHERE id = ?').get(id);
  if (!mod) return res.status(404).json({ error: 'not found' });

  const ids = Array.isArray(req.body?.ids) ? req.body.ids.map(Number) : [];
  if (!ids.length) return res.status(400).json({ error: 'ids 必填' });

  const update = db.prepare('UPDATE review_images SET sort_order = ? WHERE id = ? AND module_id = ?');
  const tx = db.transaction((list) => {
    list.forEach((imageId, idx) => update.run(idx + 1, imageId, id));
  });
  tx(ids);
  res.json({ ok: true });
});

// DELETE /api/review-modules/:id/images/:imageId
router.delete('/:id/images/:imageId', (req, res) => {
  const moduleId = Number(req.params.id);
  const imageId = Number(req.params.imageId);
  const row = db
    .prepare('SELECT * FROM review_images WHERE id = ? AND module_id = ?')
    .get(imageId, moduleId);
  if (!row) return res.status(404).json({ error: 'not found' });

  db.prepare('DELETE FROM review_images WHERE id = ?').run(imageId);
  safeUnlink(row.filename);
  db.prepare('UPDATE review_modules SET updated_at = datetime('now', '+8 hours') WHERE id = ?').run(moduleId);
  res.json({ ok: true });
});

// GET /api/review-modules/:id/images/:imageId/file  — 直接出图（支持 ?token=）
router.get('/:id/images/:imageId/file', (req, res) => {
  const moduleId = Number(req.params.id);
  const imageId = Number(req.params.imageId);
  const row = db
    .prepare('SELECT * FROM review_images WHERE id = ? AND module_id = ?')
    .get(imageId, moduleId);
  if (!row) return res.status(404).json({ error: 'not found' });

  if (row.filename.includes('..') || row.filename.includes('/') || row.filename.includes('\\')) {
    return res.status(400).json({ error: 'invalid filename' });
  }

  const full = path.join(uploadDir, row.filename);
  if (!fs.existsSync(full)) return res.status(404).json({ error: 'file missing' });

  res.setHeader('Content-Type', row.mime || 'image/jpeg');
  // 文件名是 UUID，内容不变；长缓存方便浏览器与预取复用
  res.setHeader('Cache-Control', 'private, max-age=31536000, immutable');
  res.sendFile(full);
});

export default router;

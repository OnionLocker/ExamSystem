// 真题复盘：上传录屏 + 答案 PDF，后台跑分析，前端轮询看进度
import { Router } from 'express';
import multer from 'multer';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import db from '../db.js';
import { enqueue, VIDEO_DIR, RAW_DIR, PDF_DIR } from '../examWorker.js';

const router = Router();

const VIDEO_EXT = ['.mp4', '.mov', '.m4v'];
const PDF_EXT = ['.pdf'];
// 录屏很大，但也不能没边；90 分钟 iPad 录屏一般在 8G 以内
const MAX_VIDEO_BYTES = 12 * 1024 * 1024 * 1024;
// 转码时输出文件和原件会同时存在，留出余量再收，免得写到一半把盘撑爆
const DISK_HEADROOM = 1.5 * 1024 * 1024 * 1024;

const freeBytes = () => {
  try {
    const s = fs.statfsSync(RAW_DIR);
    return s.bavail * s.bsize;
  } catch {
    return Infinity;
  }
};

const storage = multer.diskStorage({
  destination: (_req, file, cb) => cb(null, file.fieldname === 'pdf' ? PDF_DIR : RAW_DIR),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname || '').toLowerCase() || '.bin';
    cb(null, `${crypto.randomUUID()}${ext}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: MAX_VIDEO_BYTES },
  fileFilter: (_req, file, cb) => {
    const ext = path.extname(file.originalname || '').toLowerCase();
    const ok = file.fieldname === 'pdf' ? PDF_EXT.includes(ext) : VIDEO_EXT.includes(ext);
    cb(ok ? null : new Error(`不支持的文件类型：${ext || '未知'}`), ok);
  },
});

// 先看盘够不够再收：等 multer 把几个 G 写进去才发现没空间就晚了
router.post('/', (req, res, next) => {
  const incoming = Number(req.headers['content-length'] || 0);
  const free = freeBytes();
  if (incoming && free !== Infinity && incoming + DISK_HEADROOM > free) {
    const gb = (n) => (n / 1024 / 1024 / 1024).toFixed(1);
    return res.status(507).json({
      error: `磁盘空间不够：本次上传约 ${gb(incoming)} GB，当前可用 ${gb(free)} GB（转码还需要余量）。先删掉几个已完成任务的录屏再试。`,
    });
  }
  return next();
}, upload.fields([{ name: 'video', maxCount: 1 }, { name: 'pdf', maxCount: 1 }]), (req, res) => {
  const video = req.files?.video?.[0];
  const pdf = req.files?.pdf?.[0];
  if (!video) return res.status(400).json({ error: '需要上传录屏文件' });

  const title = String(req.body?.title || '').trim() || `模考复盘 ${new Date().toLocaleDateString('zh-CN')}`;
  const examDate = String(req.body?.exam_date || '').trim() || new Date().toISOString().slice(0, 10);

  const info = db
    .prepare(
      `INSERT INTO exam_analyses (title, exam_date, status, stage, progress, video_file, raw_bytes, pdf_file)
       VALUES (?, ?, 'queued', '排队中', 0, ?, ?, ?)`,
    )
    .run(title, examDate, video.filename, video.size, pdf?.filename || null);

  enqueue();
  res.json({ id: info.lastInsertRowid, ok: true });
});

// 列表不带 result / segments：那两个字段很大，列表页用不上
router.get('/', (_req, res) => {
  const rows = db
    .prepare(
      `SELECT id, title, exam_date, status, stage, progress, video_file, video_bytes,
              video_deleted, raw_bytes, duration_sec, speed, pdf_file, error,
              created_at, updated_at,
              json_extract(result, '$.stats') AS stats
         FROM exam_analyses ORDER BY id DESC`,
    )
    .all();
  res.json(rows.map((r) => ({ ...r, stats: r.stats ? JSON.parse(r.stats) : null })));
});

router.get('/:id', (req, res) => {
  const row = db.prepare('SELECT * FROM exam_analyses WHERE id = ?').get(Number(req.params.id));
  if (!row) return res.status(404).json({ error: 'not found' });
  let result = null;
  let segments = null;
  try { result = row.result ? JSON.parse(row.result) : null; } catch { /* ignore */ }
  try { segments = row.segments ? JSON.parse(row.segments) : null; } catch { /* ignore */ }
  res.json({ ...row, result, segments });
});

router.post('/:id/retry', (req, res) => {
  const id = Number(req.params.id);
  const row = db.prepare('SELECT * FROM exam_analyses WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ error: 'not found' });
  // 原件转码后就删了，重跑只能基于还在的小样本；小样本也没了就没法再来
  const hasSmall = row.video_file && fs.existsSync(path.join(VIDEO_DIR, row.video_file));
  const hasRaw = row.video_file && fs.existsSync(path.join(RAW_DIR, row.video_file));
  if (!hasSmall && !hasRaw) {
    return res.status(409).json({ error: '录屏已删除，无法重新分析。需要重新上传。' });
  }
  db.prepare("UPDATE exam_analyses SET status='queued', stage='排队中', progress=0, error=NULL WHERE id=?").run(id);
  enqueue();
  res.json({ ok: true });
});

// 分析结果留着，只把占地方的视频删掉
router.delete('/:id/video', (req, res) => {
  const id = Number(req.params.id);
  const row = db.prepare('SELECT * FROM exam_analyses WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ error: 'not found' });
  let freed = 0;
  for (const dir of [VIDEO_DIR, RAW_DIR]) {
    const p = row.video_file ? path.join(dir, row.video_file) : null;
    if (p && fs.existsSync(p)) {
      freed += fs.statSync(p).size;
      fs.unlinkSync(p);
    }
  }
  db.prepare("UPDATE exam_analyses SET video_deleted=1, updated_at=datetime('now') WHERE id=?").run(id);
  res.json({ ok: true, freed });
});

router.delete('/:id', (req, res) => {
  const id = Number(req.params.id);
  const row = db.prepare('SELECT * FROM exam_analyses WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ error: 'not found' });
  for (const p of [
    row.video_file && path.join(VIDEO_DIR, row.video_file),
    row.video_file && path.join(RAW_DIR, row.video_file),
    row.pdf_file && path.join(PDF_DIR, row.pdf_file),
  ]) {
    try { if (p && fs.existsSync(p)) fs.unlinkSync(p); } catch { /* ignore */ }
  }
  db.prepare('DELETE FROM exam_analyses WHERE id = ?').run(id);
  res.json({ ok: true });
});

// multer 的错误（超限、类型不对）要转成能看懂的话，否则前端只拿到 500
router.use((err, _req, res, _next) => {
  const msg = err?.code === 'LIMIT_FILE_SIZE' ? '文件超过大小上限' : err?.message || '上传失败';
  res.status(400).json({ error: msg });
});

export default router;

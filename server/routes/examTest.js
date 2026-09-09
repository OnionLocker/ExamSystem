// 测试样本：只收视频和 PDF，原片留着，不分析、不切片、不删。
import { Router } from 'express';
import multer from 'multer';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { beijingNow } from '../../src/lib/beijingTime.js';

const run = promisify(execFile);
const router = Router();

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
export const TEST_DIR = path.join(ROOT, 'data', 'exam-test');
fs.mkdirSync(TEST_DIR, { recursive: true });

const VIDEO_EXT = ['.mp4', '.mov', '.m4v'];
const PDF_EXT = ['.pdf'];
const MAX_VIDEO_BYTES = 12 * 1024 * 1024 * 1024;
const DISK_HEADROOM = 200 * 1024 * 1024;

const freeBytes = () => {
  try {
    const s = fs.statfsSync(TEST_DIR);
    return s.bavail * s.bsize;
  } catch {
    return Infinity;
  }
};

const metaPath = (id) => path.join(TEST_DIR, id, 'meta.json');

const readMeta = (id) => {
  try {
    return JSON.parse(fs.readFileSync(metaPath(id), 'utf8'));
  } catch {
    return null;
  }
};

const probeVideo = async (file) => {
  try {
    const { stdout } = await run('ffprobe', [
      '-v', 'error',
      '-show_entries', 'format=duration,size',
      '-show_entries', 'stream=codec_type,codec_name,bit_rate',
      '-of', 'json',
      file,
    ]);
    const j = JSON.parse(stdout);
    const audio = (j.streams || []).find((s) => s.codec_type === 'audio');
    return {
      duration_sec: Math.round(parseFloat(j.format?.duration || 0) || 0),
      has_audio: Boolean(audio),
      audio_codec: audio?.codec_name || null,
      audio_bit_rate: Number(audio?.bit_rate) || 0,
    };
  } catch {
    return { duration_sec: 0, has_audio: null, audio_codec: null, audio_bit_rate: 0 };
  }
};

const storage = multer.diskStorage({
  destination: (req, _file, cb) => {
    const dir = path.join(TEST_DIR, req.testId);
    fs.mkdirSync(dir, { recursive: true });
    cb(null, dir);
  },
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname || '').toLowerCase() || '.bin';
    cb(null, `${file.fieldname}${ext}`);
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

router.use((req, _res, next) => {
  if (req.method === 'POST' && req.path === '/') req.testId = crypto.randomUUID();
  next();
});

router.get('/', (_req, res) => {
  const rows = fs.readdirSync(TEST_DIR)
    .map(readMeta)
    .filter(Boolean)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  res.json(rows);
});

router.post('/', (req, res, next) => {
  const incoming = Number(req.headers['content-length'] || 0);
  const free = freeBytes();
  if (incoming && free !== Infinity && incoming + DISK_HEADROOM > free) {
    const gb = (n) => (n / 1024 / 1024 / 1024).toFixed(1);
    return res.status(507).json({
      error: `磁盘空间不够：本次上传约 ${gb(incoming)} GB，当前可用 ${gb(free)} GB。测试样本会留在盘上，先删几条再传。`,
    });
  }
  return next();
}, upload.fields([{ name: 'video', maxCount: 1 }, { name: 'pdf', maxCount: 1 }]), async (req, res) => {
  const video = req.files?.video?.[0];
  const pdf = req.files?.pdf?.[0];
  if (!video) return res.status(400).json({ error: '需要上传录屏文件' });

  const title = String(req.body?.title || '').trim()
    || `测试样本 ${new Date().toLocaleDateString('zh-CN')}`;
  const probe = await probeVideo(video.path);
  const meta = {
    id: req.testId,
    title,
    created_at: beijingNow(),
    video_file: video.filename,
    video_orig: video.originalname,
    video_bytes: video.size,
    pdf_file: pdf?.filename || null,
    pdf_orig: pdf?.originalname || null,
    pdf_bytes: pdf?.size || 0,
    dir: path.join(TEST_DIR, req.testId),
    ...probe,
  };
  fs.writeFileSync(metaPath(req.testId), JSON.stringify(meta, null, 2));
  res.json({ ok: true, ...meta });
});

router.delete('/:id', (req, res) => {
  const id = String(req.params.id || '').replace(/[^a-f0-9-]/gi, '');
  const dir = path.join(TEST_DIR, id);
  if (!id || !dir.startsWith(TEST_DIR) || !fs.existsSync(dir)) {
    return res.status(404).json({ error: 'not found' });
  }
  fs.rmSync(dir, { recursive: true, force: true });
  res.json({ ok: true });
});

export default router;

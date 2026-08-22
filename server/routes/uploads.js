import { Router } from 'express';
import multer from 'multer';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const UPLOAD_ROOT = path.join(__dirname, '..', '..', 'data', 'uploads');
const EXAM_ROOT = path.join(UPLOAD_ROOT, '真题'); // 真题

// 两个固定子目录
const SUBDIRS = ['pdf', '解析']; // 解析

// 允许的文件格式（子目录名只是归档分类，两类都可放 PDF / Word）
const ALLOWED_EXT = ['.pdf', '.doc', '.docx'];
const MIME_BY_EXT = {
  '.pdf': 'application/pdf',
  '.doc': 'application/msword',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};

// 按北京时间(UTC+8)生成日期目录名：YYYY.MM.DD
const beijingDateKey = () => {
  const now = new Date(Date.now() + 8 * 60 * 60 * 1000);
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth() + 1).padStart(2, '0');
  const d = String(now.getUTCDate()).padStart(2, '0');
  return `${y}.${m}.${d}`;
};

const ensureDateDir = (dateKey) => {
  const dir = path.join(UPLOAD_ROOT, dateKey);
  for (const sub of SUBDIRS) {
    fs.mkdirSync(path.join(dir, sub), { recursive: true });
  }
  return dir;
};

const normType = (t) => (SUBDIRS.includes(t) ? t : 'pdf');

// 防目录穿越：文件名只取 basename，且不能为空
const safeName = (name) => {
  const base = path.basename(String(name || ''));
  if (!base || base === '.' || base === '..') return '';
  return base;
};

// 真题文件夹名：禁止路径分隔符与隐藏名
const safeFolder = (name) => {
  const raw = String(name || '').trim();
  if (!raw || raw === '.' || raw === '..') return '';
  if (/[\\/]/.test(raw) || raw.includes('\0')) return '';
  if (raw.length > 64) return '';
  return raw;
};

const listFilesIn = (dir) => {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((f) => f.isFile())
    .map((f) => {
      const st = fs.statSync(path.join(dir, f.name));
      return { name: f.name, size: st.size, mtime: st.mtimeMs };
    })
    .sort((a, b) => b.mtime - a.mtime);
};

const uniqueFilename = (dir, name) => {
  const ext = path.extname(name);
  const stem = name.slice(0, name.length - ext.length);
  let final = name;
  let i = 1;
  while (fs.existsSync(path.join(dir, final))) {
    final = `${stem} (${i})${ext}`;
    i += 1;
  }
  return final;
};

const decodeOriginal = (originalname) => {
  try {
    return Buffer.from(originalname, 'latin1').toString('utf8');
  } catch {
    return originalname;
  }
};

// ---------- 日常资料：data/uploads/<北京日期>/<type>/ ----------
const storage = multer.diskStorage({
  destination(req, _file, cb) {
    try {
      const type = normType(req.body?.type);
      const dateKey = beijingDateKey();
      const dir = path.join(ensureDateDir(dateKey), type);
      req._uploadDateKey = dateKey;
      req._uploadType = type;
      cb(null, dir);
    } catch (err) {
      cb(err);
    }
  },
  filename(req, file, cb) {
    let original = decodeOriginal(file.originalname);
    let name = safeName(original) || `file-${Date.now()}`;
    if (!ALLOWED_EXT.includes(path.extname(name).toLowerCase())) {
      const byMime = Object.entries(MIME_BY_EXT).find(([, mime]) => mime === file.mimetype);
      if (byMime) name += byMime[0];
    }
    const dir = path.join(UPLOAD_ROOT, req._uploadDateKey, req._uploadType);
    cb(null, uniqueFilename(dir, name));
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 100 * 1024 * 1024 },
  fileFilter(_req, file, cb) {
    const ext = path.extname(decodeOriginal(file.originalname)).toLowerCase();
    const ok = ALLOWED_EXT.includes(ext) || Object.values(MIME_BY_EXT).includes(file.mimetype);
    cb(ok ? null : new Error('仅支持上传 PDF / Word 文件'), ok);
  },
});

// ---------- 真题：data/uploads/真题/<folder>/ ----------
const examStorage = multer.diskStorage({
  destination(req, _file, cb) {
    try {
      const folder = safeFolder(req.body?.folder);
      if (!folder) return cb(new Error('请先选择或创建真题文件夹'));
      const dir = path.join(EXAM_ROOT, folder);
      if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
        return cb(new Error('文件夹不存在'));
      }
      req._examFolder = folder;
      cb(null, dir);
    } catch (err) {
      cb(err);
    }
  },
  filename(req, file, cb) {
    let original = decodeOriginal(file.originalname);
    let name = safeName(original) || `file-${Date.now()}`;
    if (!ALLOWED_EXT.includes(path.extname(name).toLowerCase())) {
      const byMime = Object.entries(MIME_BY_EXT).find(([, mime]) => mime === file.mimetype);
      if (byMime) name += byMime[0];
    }
    const dir = path.join(EXAM_ROOT, req._examFolder);
    cb(null, uniqueFilename(dir, name));
  },
});

const examUpload = multer({
  storage: examStorage,
  limits: { fileSize: 100 * 1024 * 1024 },
  fileFilter(_req, file, cb) {
    const ext = path.extname(decodeOriginal(file.originalname)).toLowerCase();
    const ok = ALLOWED_EXT.includes(ext) || Object.values(MIME_BY_EXT).includes(file.mimetype);
    cb(ok ? null : new Error('仅支持上传 PDF / Word 文件'), ok);
  },
});

const router = Router();

// POST /api/uploads  (multipart: file, type=pdf|解析)
router.post('/', (req, res) => {
  upload.single('file')(req, res, (err) => {
    if (err) return res.status(400).json({ error: err.message });
    if (!req.file) return res.status(400).json({ error: '未收到文件' });
    res.status(201).json({
      ok: true,
      date: req._uploadDateKey,
      type: req._uploadType,
      name: req.file.filename,
      size: req.file.size,
    });
  });
});

// GET /api/uploads  列出所有日期目录及其文件（跳过「真题」专区）
router.get('/', (_req, res) => {
  const today = beijingDateKey();
  const existing = fs.existsSync(UPLOAD_ROOT)
    ? fs
        .readdirSync(UPLOAD_ROOT, { withFileTypes: true })
        .filter((d) => d.isDirectory() && d.name !== '真题')
        .map((d) => d.name)
    : [];
  const dates = [...new Set([today, ...existing])].sort((a, b) => b.localeCompare(a));

  const result = dates.map((dateKey) => {
    const entry = { date: dateKey };
    for (const sub of SUBDIRS) {
      entry[sub] = listFilesIn(path.join(UPLOAD_ROOT, dateKey, sub));
    }
    return entry;
  });

  res.json({ today, dates: result });
});

// GET /api/uploads/file?date=&type=&name=
router.get('/file', (req, res) => {
  const date = safeName(req.query.date);
  const type = normType(req.query.type);
  const name = safeName(req.query.name);
  if (!date || !name) return res.status(400).json({ error: '参数缺失' });
  const filePath = path.join(UPLOAD_ROOT, date, type, name);
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return res.status(404).json({ error: '文件不存在' });
  }
  const mime = MIME_BY_EXT[path.extname(name).toLowerCase()] || 'application/octet-stream';
  res.setHeader('Content-Type', mime);
  res.setHeader('Content-Disposition', `inline; filename*=UTF-8''${encodeURIComponent(name)}`);
  fs.createReadStream(filePath).pipe(res);
});

// DELETE /api/uploads/file?date=&type=&name=
router.delete('/file', (req, res) => {
  const date = safeName(req.query.date);
  const type = normType(req.query.type);
  const name = safeName(req.query.name);
  if (!date || !name) return res.status(400).json({ error: '参数缺失' });
  const filePath = path.join(UPLOAD_ROOT, date, type, name);
  if (!fs.existsSync(filePath)) return res.status(404).json({ error: '文件不存在' });
  fs.unlinkSync(filePath);
  res.json({ ok: true });
});

// ========== 真题专区 ==========

// GET /api/uploads/exam
router.get('/exam', (_req, res) => {
  fs.mkdirSync(EXAM_ROOT, { recursive: true });
  const folders = fs
    .readdirSync(EXAM_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => ({
      name: d.name,
      files: listFilesIn(path.join(EXAM_ROOT, d.name)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'));
  res.json({ folders });
});

// POST /api/uploads/exam/folders  { name }
router.post('/exam/folders', (req, res) => {
  const name = safeFolder(req.body?.name);
  if (!name) return res.status(400).json({ error: '文件夹名不合法' });
  const dir = path.join(EXAM_ROOT, name);
  if (fs.existsSync(dir)) return res.status(409).json({ error: '文件夹已存在' });
  fs.mkdirSync(dir, { recursive: true });
  res.status(201).json({ ok: true, name });
});

// DELETE /api/uploads/exam/folders?name=  （空文件夹才能删）
router.delete('/exam/folders', (req, res) => {
  const name = safeFolder(req.query.name);
  if (!name) return res.status(400).json({ error: '参数缺失' });
  const dir = path.join(EXAM_ROOT, name);
  if (!fs.existsSync(dir)) return res.status(404).json({ error: '文件夹不存在' });
  const left = fs.readdirSync(dir);
  if (left.length) return res.status(400).json({ error: '文件夹不为空，请先删除里面的文件' });
  fs.rmdirSync(dir);
  res.json({ ok: true });
});

// POST /api/uploads/exam  (multipart: folder, file)
router.post('/exam', (req, res) => {
  examUpload.single('file')(req, res, (err) => {
    if (err) return res.status(400).json({ error: err.message });
    if (!req.file) return res.status(400).json({ error: '未收到文件' });
    res.status(201).json({
      ok: true,
      folder: req._examFolder,
      name: req.file.filename,
      size: req.file.size,
    });
  });
});

// GET /api/uploads/exam/file?folder=&name=
router.get('/exam/file', (req, res) => {
  const folder = safeFolder(req.query.folder);
  const name = safeName(req.query.name);
  if (!folder || !name) return res.status(400).json({ error: '参数缺失' });
  const filePath = path.join(EXAM_ROOT, folder, name);
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return res.status(404).json({ error: '文件不存在' });
  }
  const mime = MIME_BY_EXT[path.extname(name).toLowerCase()] || 'application/octet-stream';
  res.setHeader('Content-Type', mime);
  res.setHeader('Content-Disposition', `inline; filename*=UTF-8''${encodeURIComponent(name)}`);
  fs.createReadStream(filePath).pipe(res);
});

// DELETE /api/uploads/exam/file?folder=&name=
router.delete('/exam/file', (req, res) => {
  const folder = safeFolder(req.query.folder);
  const name = safeName(req.query.name);
  if (!folder || !name) return res.status(400).json({ error: '参数缺失' });
  const filePath = path.join(EXAM_ROOT, folder, name);
  if (!fs.existsSync(filePath)) return res.status(404).json({ error: '文件不存在' });
  fs.unlinkSync(filePath);
  res.json({ ok: true });
});

export default router;

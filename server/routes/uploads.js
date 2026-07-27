import { Router } from 'express';
import multer from 'multer';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const UPLOAD_ROOT = path.join(__dirname, '..', '..', 'data', 'uploads');

// 两个固定子目录
const SUBDIRS = ['pdf', '解析'];

// 按北京时间(UTC+8)生成日期目录名：YYYY.MM.DD
const beijingDateKey = () => {
  const now = new Date(Date.now() + 8 * 60 * 60 * 1000); // 偏移到北京时间
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth() + 1).padStart(2, '0');
  const d = String(now.getUTCDate()).padStart(2, '0');
  return `${y}.${m}.${d}`;
};

// 确保某个日期目录及其 pdf / 解析 子目录存在，返回日期目录绝对路径
const ensureDateDir = (dateKey) => {
  const dir = path.join(UPLOAD_ROOT, dateKey);
  for (const sub of SUBDIRS) {
    fs.mkdirSync(path.join(dir, sub), { recursive: true });
  }
  return dir;
};

// 校验并归一化 type（只允许 pdf / 解析）
const normType = (t) => (SUBDIRS.includes(t) ? t : 'pdf');

// 防目录穿越：文件名只取 basename，且不能为空
const safeName = (name) => {
  const base = path.basename(String(name || ''));
  if (!base || base === '.' || base === '..') return '';
  return base;
};

// ---------- multer：存储到 data/uploads/<北京日期>/<type>/ ----------
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
    // 还原中文文件名（multer 默认按 latin1 解码）
    let original = file.originalname;
    try {
      original = Buffer.from(file.originalname, 'latin1').toString('utf8');
    } catch { /* ignore */ }
    let name = safeName(original) || `file-${Date.now()}.pdf`;
    // 同名则加序号后缀，避免覆盖
    const dir = path.join(UPLOAD_ROOT, req._uploadDateKey, req._uploadType);
    const ext = path.extname(name);
    const stem = name.slice(0, name.length - ext.length);
    let final = name;
    let i = 1;
    while (fs.existsSync(path.join(dir, final))) {
      final = `${stem} (${i})${ext}`;
      i += 1;
    }
    cb(null, final);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 100 * 1024 * 1024 }, // 单文件 100MB
  fileFilter(_req, file, cb) {
    const ok =
      file.mimetype === 'application/pdf' ||
      file.originalname.toLowerCase().endsWith('.pdf');
    cb(ok ? null : new Error('仅支持上传 PDF 文件'), ok);
  },
});

const router = Router();

// POST /api/uploads  (multipart: file, type=pdf|解析)
// 按北京时间自动落到对应日期目录
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

// GET /api/uploads  列出所有日期目录及其文件
router.get('/', (_req, res) => {
  if (!fs.existsSync(UPLOAD_ROOT)) return res.json({ today: beijingDateKey(), dates: [] });
  const dates = fs
    .readdirSync(UPLOAD_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort((a, b) => b.localeCompare(a)); // 新日期在前

  const result = dates.map((dateKey) => {
    const entry = { date: dateKey };
    for (const sub of SUBDIRS) {
      const subDir = path.join(UPLOAD_ROOT, dateKey, sub);
      let files = [];
      if (fs.existsSync(subDir)) {
        files = fs
          .readdirSync(subDir, { withFileTypes: true })
          .filter((f) => f.isFile())
          .map((f) => {
            const st = fs.statSync(path.join(subDir, f.name));
            return { name: f.name, size: st.size, mtime: st.mtimeMs };
          })
          .sort((a, b) => b.mtime - a.mtime);
      }
      entry[sub] = files;
    }
    return entry;
  });

  res.json({ today: beijingDateKey(), dates: result });
});

// GET /api/uploads/file?date=&type=&name=  预览/下载（前端带 token 以 blob 获取）
router.get('/file', (req, res) => {
  const date = safeName(req.query.date);
  const type = normType(req.query.type);
  const name = safeName(req.query.name);
  if (!date || !name) return res.status(400).json({ error: '参数缺失' });
  const filePath = path.join(UPLOAD_ROOT, date, type, name);
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return res.status(404).json({ error: '文件不存在' });
  }
  res.setHeader('Content-Type', 'application/pdf');
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

export default router;

import { Router } from 'express';
import multer from 'multer';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import db from '../db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const UPLOAD_DIR = path.join(ROOT, 'data', 'shenlun-uploads');
const MAX_PHOTOS = 12;

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 25 * 1024 * 1024, files: MAX_PHOTOS },
  fileFilter: (_req, file, cb) => cb(null, /^image\//.test(file.mimetype || '')),
});

const router = Router();
const json = (text, fallback) => {
  try { return text ? JSON.parse(text) : fallback; } catch { return fallback; }
};

// 照片只存草稿；交卷把每题的草稿打包成一次 submission，评分在 Hermes「申论复盘」里做
const attemptOut = (row) => row && ({
  ...row,
  images: json(row.images, []).map((_, i) => `/api/shenlun/attempts/${row.id}/photos/${i}`),
  grading: json(row.grading, null),
});

const questionOut = (row, { withKey = false } = {}) => {
  const out = {
    id: row.id,
    paper_id: row.paper_id,
    no: row.no,
    qtype: row.qtype,
    prompt: row.prompt,
    requirements: json(row.requirements, {}),
  };
  if (withKey) {
    out.rubric = json(row.rubric, {});
    out.reference_answer = row.reference_answer;
  }
  return out;
};

const readText = (rel) => {
  if (!rel) return null;
  const file = path.resolve(ROOT, rel);
  if (!file.startsWith(ROOT + path.sep) || !fs.existsSync(file)) return null;
  return fs.readFileSync(file, 'utf8');
};

const submissionRows = (where = '', args = []) => db.prepare(`
  SELECT s.*, p.title AS paper_title, p.kind AS paper_kind,
         COUNT(a.id) AS answered,
         GROUP_CONCAT(q.no || '.' || q.qtype, '、') AS answered_labels,
         (SELECT COUNT(*) FROM shenlun_questions qq WHERE qq.paper_id = s.paper_id) AS question_count
  FROM shenlun_submissions s
  JOIN shenlun_papers p ON p.id = s.paper_id
  LEFT JOIN shenlun_attempts a ON a.submission_id = s.id
  LEFT JOIN shenlun_questions q ON q.id = a.question_id
  ${where}
  GROUP BY s.id
  ORDER BY s.id DESC
`).all(...args);

router.get('/papers', (_req, res) => {
  const rows = db.prepare(`
    SELECT p.id, p.title, p.kind, p.level, p.year, p.time_limit_min, p.created_at,
           (SELECT COUNT(*) FROM shenlun_questions q WHERE q.paper_id = p.id) AS question_count,
           (SELECT COALESCE(SUM(json_extract(q.requirements, '$.score')), 0) FROM shenlun_questions q WHERE q.paper_id = p.id) AS total_score,
           (SELECT COUNT(*) FROM shenlun_submissions s WHERE s.paper_id = p.id) AS submissions,
           (SELECT COUNT(*) FROM shenlun_attempts a JOIN shenlun_questions q ON q.id = a.question_id
             WHERE q.paper_id = p.id AND a.submission_id IS NULL) AS drafts
    FROM shenlun_papers p
    ORDER BY p.created_at DESC
  `).all();
  res.json({ papers: rows });
});

router.get('/papers/:id', (req, res) => {
  const paper = db.prepare('SELECT * FROM shenlun_papers WHERE id = ?').get(req.params.id);
  if (!paper) return res.status(404).json({ error: 'paper not found' });
  const questions = db.prepare('SELECT * FROM shenlun_questions WHERE paper_id = ? ORDER BY no').all(paper.id);
  const draft = db.prepare('SELECT * FROM shenlun_attempts WHERE question_id = ? AND submission_id IS NULL ORDER BY id DESC LIMIT 1');
  const lastGraded = db.prepare(`
    SELECT * FROM shenlun_attempts WHERE question_id = ? AND status = 'graded' ORDER BY id DESC LIMIT 1
  `);
  res.json({
    ...paper,
    materials: json(paper.materials, []),
    meta: json(paper.meta, {}),
    questions: questions.map((q) => ({
      ...questionOut(q),
      draft: attemptOut(draft.get(q.id)) || null,
      last_graded: attemptOut(lastGraded.get(q.id)) || null,
    })),
    submissions: submissionRows('WHERE s.paper_id = ?', [paper.id]),
  });
});

router.delete('/papers/:id', (req, res) => {
  const attempts = db.prepare(`
    SELECT a.id FROM shenlun_attempts a JOIN shenlun_questions q ON q.id = a.question_id WHERE q.paper_id = ?
  `).all(req.params.id);
  const out = db.prepare('DELETE FROM shenlun_papers WHERE id = ?').run(req.params.id);
  if (!out.changes) return res.status(404).json({ error: 'paper not found' });
  for (const a of attempts) fs.rmSync(path.join(UPLOAD_DIR, String(a.id)), { recursive: true, force: true });
  res.json({ ok: true });
});

router.get('/questions/:id', (req, res) => {
  const q = db.prepare('SELECT * FROM shenlun_questions WHERE id = ?').get(req.params.id);
  if (!q) return res.status(404).json({ error: 'question not found' });
  const attempts = db.prepare(`
    SELECT * FROM shenlun_attempts WHERE question_id = ? AND submission_id IS NOT NULL ORDER BY id DESC
  `).all(q.id);
  const draft = db.prepare('SELECT * FROM shenlun_attempts WHERE question_id = ? AND submission_id IS NULL ORDER BY id DESC LIMIT 1').get(q.id);
  // 要点表和参考答案在这道题评过分之后才给看，避免先看答案再写
  const withKey = attempts.some((a) => a.status === 'graded') || req.query.reveal === '1';
  res.json({
    ...questionOut(q, { withKey }),
    key_revealed: withKey,
    draft: attemptOut(draft) || null,
    attempts: attempts.map(attemptOut),
  });
});

// 加照片：追加到这道题的草稿上（没有草稿就新建一份）
router.post('/questions/:id/photos', upload.array('photos', MAX_PHOTOS), (req, res) => {
  const q = db.prepare('SELECT id FROM shenlun_questions WHERE id = ?').get(req.params.id);
  if (!q) return res.status(404).json({ error: 'question not found' });
  const files = req.files || [];
  if (!files.length) return res.status(400).json({ error: '请选择答题照片' });
  let row = db.prepare('SELECT * FROM shenlun_attempts WHERE question_id = ? AND submission_id IS NULL ORDER BY id DESC LIMIT 1').get(q.id);
  if (!row) {
    const { lastInsertRowid } = db.prepare("INSERT INTO shenlun_attempts (question_id, status) VALUES (?, 'draft')").run(q.id);
    row = db.prepare('SELECT * FROM shenlun_attempts WHERE id = ?').get(Number(lastInsertRowid));
  }
  const images = json(row.images, []);
  if (images.length + files.length > MAX_PHOTOS) return res.status(400).json({ error: `一道题最多 ${MAX_PHOTOS} 张照片` });
  const dir = path.join(UPLOAD_DIR, String(row.id));
  fs.mkdirSync(dir, { recursive: true });
  for (const file of files) {
    const ext = (path.extname(file.originalname || '') || '.jpg').toLowerCase().replace(/[^.a-z0-9]/g, '') || '.jpg';
    const name = `${Date.now().toString(36)}-${images.length + 1}${ext}`;
    fs.writeFileSync(path.join(dir, name), file.buffer);
    images.push(`${row.id}/${name}`);
  }
  db.prepare('UPDATE shenlun_attempts SET images = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?').run(JSON.stringify(images), row.id);
  res.json(attemptOut(db.prepare('SELECT * FROM shenlun_attempts WHERE id = ?').get(row.id)));
});

router.delete('/attempts/:id/photos/:n', (req, res) => {
  const row = db.prepare('SELECT * FROM shenlun_attempts WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'attempt not found' });
  if (row.submission_id) return res.status(409).json({ error: '已交卷，照片不能再改' });
  const images = json(row.images, []);
  const [rel] = images.splice(Number(req.params.n), 1);
  if (!rel) return res.status(404).json({ error: 'photo not found' });
  fs.rmSync(path.join(UPLOAD_DIR, rel), { force: true });
  if (!images.length) {
    db.prepare('DELETE FROM shenlun_attempts WHERE id = ?').run(row.id);
    fs.rmSync(path.join(UPLOAD_DIR, String(row.id)), { recursive: true, force: true });
    return res.json(null);
  }
  db.prepare('UPDATE shenlun_attempts SET images = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?').run(JSON.stringify(images), row.id);
  res.json(attemptOut(db.prepare('SELECT * FROM shenlun_attempts WHERE id = ?').get(row.id)));
});

router.get('/attempts/:id/photos/:n', (req, res) => {
  const row = db.prepare('SELECT images FROM shenlun_attempts WHERE id = ?').get(req.params.id);
  const rel = row && json(row.images, [])[Number(req.params.n)];
  if (!rel) return res.status(404).end();
  const file = path.join(UPLOAD_DIR, rel);
  if (!file.startsWith(UPLOAD_DIR + path.sep) || !fs.existsSync(file)) return res.status(404).end();
  res.sendFile(file);
});

// 交卷：把这套卷里有照片的草稿打包；没写的题不算分
router.post('/papers/:id/submit', (req, res) => {
  const paper = db.prepare('SELECT id FROM shenlun_papers WHERE id = ?').get(req.params.id);
  if (!paper) return res.status(404).json({ error: 'paper not found' });
  const drafts = db.prepare(`
    SELECT a.id, a.images FROM shenlun_attempts a JOIN shenlun_questions q ON q.id = a.question_id
    WHERE q.paper_id = ? AND a.submission_id IS NULL
  `).all(paper.id).filter((a) => json(a.images, []).length > 0);
  if (!drafts.length) return res.status(400).json({ error: '还没有任何一题上传照片' });
  const spent = Number.parseInt(req.body?.time_spent_sec, 10);
  const id = db.transaction(() => {
    const { lastInsertRowid } = db.prepare(`
      INSERT INTO shenlun_submissions (paper_id, status, time_spent_sec) VALUES (?, 'submitted', ?)
    `).run(paper.id, Number.isFinite(spent) ? spent : null);
    const link = db.prepare("UPDATE shenlun_attempts SET submission_id = ?, status = 'submitted', updated_at = CURRENT_TIMESTAMP WHERE id = ?");
    for (const a of drafts) link.run(Number(lastInsertRowid), a.id);
    return Number(lastInsertRowid);
  })();
  res.json(submissionRows('WHERE s.id = ?', [id])[0]);
});

// Hermes「申论复盘」选择器用：全部交卷记录
router.get('/submissions', (_req, res) => {
  res.json({ submissions: submissionRows() });
});

router.get('/submissions/:id', (req, res) => {
  const sub = submissionRows('WHERE s.id = ?', [req.params.id])[0];
  if (!sub) return res.status(404).json({ error: 'submission not found' });
  const attempts = db.prepare(`
    SELECT a.*, q.no, q.qtype FROM shenlun_attempts a JOIN shenlun_questions q ON q.id = a.question_id
    WHERE a.submission_id = ? ORDER BY q.no
  `).all(sub.id);
  res.json({
    ...sub,
    attempts: attempts.map(attemptOut),
    report_markdown: readText(sub.report_path),
    comment_markdown: readText(sub.comment_path),
  });
});

router.delete('/submissions/:id', (req, res) => {
  const attempts = db.prepare('SELECT id FROM shenlun_attempts WHERE submission_id = ?').all(req.params.id);
  const out = db.prepare('DELETE FROM shenlun_submissions WHERE id = ?').run(req.params.id);
  if (!out.changes) return res.status(404).json({ error: 'submission not found' });
  db.prepare('DELETE FROM shenlun_attempts WHERE submission_id = ?').run(req.params.id);
  for (const a of attempts) fs.rmSync(path.join(UPLOAD_DIR, String(a.id)), { recursive: true, force: true });
  res.json({ ok: true });
});

export default router;

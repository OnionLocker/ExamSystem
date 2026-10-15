import { Router } from 'express';
import multer from 'multer';
import path from 'node:path';
import fs from 'node:fs';
import { spawn } from 'node:child_process';
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
// 与 shenlun_common.word_count 一致：稿纸格子数，除空白外每个字符一格
const wordCount = (text) => String(text || '').replace(/\s+/g, '').length;

// 批改要一两分钟（照片直接交给模型，两遍独立采点），后台跑；结果和状态由 Python 写回 shenlun_attempts
const runGrader = (attemptId) => {
  const child = spawn('python3', ['scripts/shenlun_grade.py', 'grade', '--attempt', String(attemptId)], {
    cwd: ROOT,
    detached: true,
    stdio: 'ignore',
    env: process.env,
  });
  child.unref();
};

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

router.get('/papers', (_req, res) => {
  const rows = db.prepare(`
    SELECT p.id, p.title, p.kind, p.level, p.year, p.time_limit_min, p.created_at,
           COUNT(DISTINCT q.id) AS question_count,
           COUNT(DISTINCT CASE WHEN a.status = 'graded' THEN a.question_id END) AS graded_questions,
           MAX(a.created_at) AS last_attempt_at
    FROM shenlun_papers p
    LEFT JOIN shenlun_questions q ON q.paper_id = p.id
    LEFT JOIN shenlun_attempts a ON a.question_id = q.id
    GROUP BY p.id
    ORDER BY p.created_at DESC
  `).all();
  const scores = db.prepare('SELECT paper_id, SUM(json_extract(requirements, \'$.score\')) AS total FROM shenlun_questions GROUP BY paper_id').all();
  const totals = new Map(scores.map((r) => [r.paper_id, r.total]));
  res.json({ papers: rows.map((r) => ({ ...r, total_score: totals.get(r.id) || 0 })) });
});

router.get('/papers/:id', (req, res) => {
  const paper = db.prepare('SELECT * FROM shenlun_papers WHERE id = ?').get(req.params.id);
  if (!paper) return res.status(404).json({ error: 'paper not found' });
  const questions = db.prepare('SELECT * FROM shenlun_questions WHERE paper_id = ? ORDER BY no').all(paper.id);
  const latest = db.prepare(`
    SELECT * FROM shenlun_attempts WHERE question_id = ? ORDER BY id DESC LIMIT 1
  `);
  res.json({
    ...paper,
    materials: json(paper.materials, []),
    meta: json(paper.meta, {}),
    questions: questions.map((q) => ({ ...questionOut(q), latest_attempt: attemptOut(latest.get(q.id)) || null })),
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
  const attempts = db.prepare('SELECT * FROM shenlun_attempts WHERE question_id = ? ORDER BY id DESC').all(q.id);
  // 要点表和参考答案在交过一次并批改完之后才给看，避免先看答案再写
  const graded = attempts.some((a) => a.status === 'graded');
  const withKey = graded || req.query.reveal === '1';
  res.json({ ...questionOut(q, { withKey }), key_revealed: withKey, attempts: attempts.map(attemptOut) });
});

router.post('/questions/:id/attempts', upload.array('photos', MAX_PHOTOS), (req, res) => {
  const q = db.prepare('SELECT id FROM shenlun_questions WHERE id = ?').get(req.params.id);
  if (!q) return res.status(404).json({ error: 'question not found' });
  const files = req.files || [];
  const typed = String(req.body?.text || '').trim();
  if (!files.length && !typed) return res.status(400).json({ error: '请上传答题照片，或直接输入答案文字' });
  const spent = Number.parseInt(req.body?.time_spent_sec, 10);
  const { lastInsertRowid } = db.prepare(`
    INSERT INTO shenlun_attempts (question_id, status, time_spent_sec, answer_text, word_count)
    VALUES (?, 'grading', ?, ?, ?)
  `).run(q.id, Number.isFinite(spent) ? spent : null, files.length ? null : typed, files.length ? null : wordCount(typed));
  const id = Number(lastInsertRowid);
  if (files.length) {
    const dir = path.join(UPLOAD_DIR, String(id));
    fs.mkdirSync(dir, { recursive: true });
    const rels = files.map((file, i) => {
      const ext = (path.extname(file.originalname || '') || '.jpg').toLowerCase().replace(/[^.a-z0-9]/g, '') || '.jpg';
      const name = `${String(i + 1).padStart(2, '0')}${ext}`;
      fs.writeFileSync(path.join(dir, name), file.buffer);
      return `${id}/${name}`;
    });
    db.prepare('UPDATE shenlun_attempts SET images = ? WHERE id = ?').run(JSON.stringify(rels), id);
  }
  runGrader(id);
  res.json(attemptOut(db.prepare('SELECT * FROM shenlun_attempts WHERE id = ?').get(id)));
});

router.get('/attempts/:id', (req, res) => {
  const row = db.prepare('SELECT * FROM shenlun_attempts WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'attempt not found' });
  res.json(attemptOut(row));
});

router.post('/attempts/:id/grade', (req, res) => {
  const row = db.prepare('SELECT * FROM shenlun_attempts WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'attempt not found' });
  if (row.status === 'grading') return res.status(409).json({ error: '正在批改，请稍候' });
  db.prepare('UPDATE shenlun_attempts SET status = \'grading\', error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?').run(row.id);
  runGrader(row.id);
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

router.delete('/attempts/:id', (req, res) => {
  const out = db.prepare('DELETE FROM shenlun_attempts WHERE id = ?').run(req.params.id);
  if (!out.changes) return res.status(404).json({ error: 'attempt not found' });
  fs.rmSync(path.join(UPLOAD_DIR, String(Number(req.params.id))), { recursive: true, force: true });
  res.json({ ok: true });
});

export default router;

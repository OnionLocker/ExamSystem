import { Router } from 'express';
import db from '../db.js';

const router = Router();

// POST /api/practice/sessions  开始一次练习
router.post('/sessions', (req, res) => {
  const { category } = req.body || {};
  const info = db.prepare(
    'INSERT INTO practice_sessions (category) VALUES (?)'
  ).run(category || null);
  const row = db.prepare('SELECT * FROM practice_sessions WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json(row);
});

// POST /api/practice/sessions/:id/answers  提交һ道答题
router.post('/sessions/:id/answers', (req, res) => {
  const sessionId = Number(req.params.id);
  const { question_id, user_answer, time_spent_sec } = req.body || {};
  if (!question_id) return res.status(400).json({ error: 'question_id 必填' });

  const q = db.prepare('SELECT correct_answer FROM questions WHERE id = ?').get(question_id);
  if (!q) return res.status(404).json({ error: 'question not found' });

  const isCorrect = String(user_answer || '').trim() === String(q.correct_answer).trim() ? 1 : 0;

  const tx = db.transaction(() => {
    db.prepare(`
      INSERT INTO practice_answers (session_id, question_id, user_answer, is_correct, time_spent_sec)
      VALUES (?, ?, ?, ?, ?)
    `).run(sessionId, question_id, user_answer || null, isCorrect, time_spent_sec || 0);

    db.prepare(`
      UPDATE practice_sessions
      SET total    = total + 1,
          correct  = correct + ?
      WHERE id = ?
    `).run(isCorrect, sessionId);

    if (!isCorrect) {
      db.prepare(`
        INSERT INTO mistakes (question_id, wrong_count, last_wrong_at, mastered)
        VALUES (?, 1, CURRENT_TIMESTAMP, 0)
        ON CONFLICT(question_id) DO UPDATE SET
          wrong_count   = wrong_count + 1,
          last_wrong_at = CURRENT_TIMESTAMP,
          mastered      = 0
      `).run(question_id);
    }
  });
  tx();

  res.json({
    is_correct: !!isCorrect,
    correct_answer: q.correct_answer,
  });
});

// POST /api/practice/sessions/:id/finish
router.post('/sessions/:id/finish', (req, res) => {
  const { duration_sec } = req.body || {};
  const info = db.prepare(`
    UPDATE practice_sessions
    SET ended_at = CURRENT_TIMESTAMP,
        duration_sec = COALESCE(?, duration_sec)
    WHERE id = ?
  `).run(duration_sec ?? null, req.params.id);
  if (!info.changes) return res.status(404).json({ error: 'not found' });
  const row = db.prepare('SELECT * FROM practice_sessions WHERE id = ?').get(req.params.id);
  res.json(row);
});

// GET /api/practice/sessions  历史练习列表
router.get('/sessions', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 20, 100);
  const rows = db.prepare(
    'SELECT * FROM practice_sessions ORDER BY started_at DESC LIMIT ?'
  ).all(limit);
  res.json(rows);
});

// GET /api/practice/sessions/:id  练习详情（含每题）
router.get('/sessions/:id', (req, res) => {
  const session = db.prepare('SELECT * FROM practice_sessions WHERE id = ?').get(req.params.id);
  if (!session) return res.status(404).json({ error: 'not found' });
  const answers = db.prepare(`
    SELECT pa.*, q.content, q.correct_answer, q.category, q.sub_category
    FROM practice_answers pa
    JOIN questions q ON q.id = pa.question_id
    WHERE pa.session_id = ?
    ORDER BY pa.id ASC
  `).all(req.params.id);
  res.json({ ...session, answers });
});

export default router;

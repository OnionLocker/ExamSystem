import { Router } from 'express';
import db from '../db.js';

const router = Router();

// ─────────────────────────────────────────────
// POST /api/practice/sessions
//   body: { category }
//   → { id }
// ─────────────────────────────────────────────
router.post('/sessions', (req, res) => {
  const { category = '刷题' } = req.body || {};
  const result = db
    .prepare(
      `INSERT INTO practice_sessions (category, started_at)
       VALUES (?, datetime('now'))`,
    )
    .run(String(category).slice(0, 100));
  res.status(201).json({ id: result.lastInsertRowid });
});

// ─────────────────────────────────────────────
// POST /api/practice/sessions/:id/answers
//   body: { question_id, user_answer, time_spent_sec }
//   → { is_correct, correct_answer, explanation, skipped }
// ─────────────────────────────────────────────
router.post('/sessions/:id/answers', (req, res) => {
  const sessionId = Number(req.params.id);
  const { question_id, user_answer = '', time_spent_sec = 0 } = req.body || {};

  if (!question_id) return res.status(400).json({ error: 'question_id required' });

  const q = db
    .prepare('SELECT correct_answer, explanation FROM questions WHERE id = ?')
    .get(Number(question_id));
  if (!q) return res.status(404).json({ error: 'question not found' });

  const skipped = user_answer === '';
  const is_correct = !skipped && user_answer === q.correct_answer;

  db.prepare(
    `INSERT INTO practice_answers
       (session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  ).run(sessionId, Number(question_id), user_answer, is_correct ? 1 : 0, Number(time_spent_sec));

  // 同步更新 session 的 total / correct
  db.prepare(
    `UPDATE practice_sessions
     SET total = total + 1,
         correct = correct + ?
     WHERE id = ?`,
  ).run(is_correct ? 1 : 0, sessionId);

  // 错题本：答错时 upsert mistakes
  if (!skipped && !is_correct) {
    db.prepare(
      `INSERT INTO mistakes (question_id, wrong_count, last_wrong_at)
       VALUES (?, 1, datetime('now'))
       ON CONFLICT(question_id) DO UPDATE
         SET wrong_count = wrong_count + 1,
             last_wrong_at = datetime('now'),
             mastered = 0`,
    ).run(Number(question_id));
  }

  res.json({
    is_correct,
    correct_answer: q.correct_answer,
    explanation: q.explanation || null,
    skipped,
  });
});

// ─────────────────────────────────────────────
// POST /api/practice/sessions/:id/finish
//   body: { duration_sec }
//   → { ok }
// ─────────────────────────────────────────────
router.post('/sessions/:id/finish', (req, res) => {
  const sessionId = Number(req.params.id);
  const { duration_sec = 0 } = req.body || {};
  db.prepare(
    `UPDATE practice_sessions
     SET duration_sec = ?, ended_at = datetime('now')
     WHERE id = ?`,
  ).run(Number(duration_sec), sessionId);
  res.json({ ok: true });
});

export default router;

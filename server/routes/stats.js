import { Router } from 'express';
import db from '../db.js';

const router = Router();

// GET /api/stats/overview  首页用的综合统计
router.get('/overview', (_req, res) => {
  const today = db.prepare(`
    SELECT
      COUNT(*) AS total,
      COALESCE(SUM(is_correct), 0) AS correct,
      COALESCE(SUM(time_spent_sec), 0) AS duration_sec
    FROM practice_answers
    WHERE date(answered_at) = date('now', 'localtime')
  `).get();

  const overall = db.prepare(`
    SELECT
      COUNT(*) AS total,
      COALESCE(SUM(is_correct), 0) AS correct
    FROM practice_answers
  `).get();

  const reviewsCount = db.prepare('SELECT COUNT(*) AS c FROM reviews').get().c;
  const mistakesCount = db.prepare('SELECT COUNT(*) AS c FROM mistakes WHERE mastered = 0').get().c;

  const byCategory = db.prepare(`
    SELECT q.category,
           COUNT(*) AS total,
           SUM(pa.is_correct) AS correct
    FROM practice_answers pa
    JOIN questions q ON q.id = pa.question_id
    GROUP BY q.category
  `).all();

  const accuracy = (c, t) => (t ? Math.round((c / t) * 1000) / 10 : 0);

  res.json({
    today: {
      ...today,
      accuracy: accuracy(today.correct, today.total),
    },
    overall: {
      ...overall,
      accuracy: accuracy(overall.correct, overall.total),
    },
    reviews_count: reviewsCount,
    mistakes_count: mistakesCount,
    by_category: byCategory.map((x) => ({ ...x, accuracy: accuracy(x.correct, x.total) })),
  });
});

// GET /api/stats/heatmap?days=30  练习打卡热力图
router.get('/heatmap', (req, res) => {
  const days = Math.min(parseInt(req.query.days) || 30, 365);
  const rows = db.prepare(`
    SELECT date(answered_at, 'localtime') AS day,
           COUNT(*) AS count
    FROM practice_answers
    WHERE answered_at >= date('now', 'localtime', ?)
    GROUP BY day
    ORDER BY day ASC
  `).all(`-${days} days`);
  res.json(rows);
});

export default router;

import { Router } from 'express';
import db from '../db.js';

const router = Router();

// GET /api/mistakes  错题列表（Ĭ认δ掌握）
router.get('/', (req, res) => {
  const mastered = req.query.mastered === '1' ? 1 : 0;
  const category = req.query.category;
  const limit = Math.min(parseInt(req.query.limit) || 50, 200);

  const where = ['m.mastered = ?'];
  const params = [mastered];
  if (category) { where.push('q.category = ?'); params.push(category); }

  const rows = db.prepare(`
    SELECT m.id              AS mistake_id,
           m.wrong_count,
           m.last_wrong_at,
           m.mastered,
           m.note,
           q.*
    FROM mistakes m
    JOIN questions q ON q.id = m.question_id
    WHERE ${where.join(' AND ')}
    ORDER BY m.last_wrong_at DESC
    LIMIT ?
  `).all(...params, limit);

  res.json(rows.map((r) => ({
    ...r,
    options: r.options ? JSON.parse(r.options) : [],
    tags: r.tags ? JSON.parse(r.tags) : [],
  })));
});

// PATCH /api/mistakes/:question_id  更新掌握״̬ / 笔记
router.patch('/:question_id', (req, res) => {
  const { mastered, note } = req.body || {};
  const sets = [];
  const params = [];
  if (mastered !== undefined) { sets.push('mastered = ?'); params.push(mastered ? 1 : 0); }
  if (note !== undefined) { sets.push('note = ?'); params.push(note); }
  if (!sets.length) return res.status(400).json({ error: 'nothing to update' });
  params.push(req.params.question_id);

  const info = db.prepare(
    `UPDATE mistakes SET ${sets.join(', ')} WHERE question_id = ?`
  ).run(...params);
  if (!info.changes) return res.status(404).json({ error: 'not found' });
  res.json({ ok: true });
});

// DELETE /api/mistakes/:question_id  从错题本移除
router.delete('/:question_id', (req, res) => {
  const info = db.prepare('DELETE FROM mistakes WHERE question_id = ?').run(req.params.question_id);
  if (!info.changes) return res.status(404).json({ error: 'not found' });
  res.json({ ok: true });
});

export default router;

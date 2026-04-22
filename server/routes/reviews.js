import { Router } from 'express';
import db from '../db.js';

const router = Router();

// GET /api/reviews
router.get('/', (_req, res) => {
  const rows = db.prepare('SELECT * FROM reviews ORDER BY created_at DESC').all();
  res.json(rows);
});

// POST /api/reviews
router.post('/', (req, res) => {
  const { title, exam_date, score, status, notes, file_path } = req.body || {};
  if (!title) return res.status(400).json({ error: 'title 必填' });
  const info = db.prepare(`
    INSERT INTO reviews (title, exam_date, score, status, notes, file_path)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(title, exam_date || null, score || null, status || '待复盘', notes || null, file_path || null);
  const row = db.prepare('SELECT * FROM reviews WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json(row);
});

// PUT /api/reviews/:id
router.put('/:id', (req, res) => {
  const exists = db.prepare('SELECT id FROM reviews WHERE id = ?').get(req.params.id);
  if (!exists) return res.status(404).json({ error: 'not found' });
  const fields = ['title', 'exam_date', 'score', 'status', 'notes', 'file_path'];
  const sets = [];
  const params = { id: req.params.id };
  for (const f of fields) {
    if (req.body[f] !== undefined) { sets.push(`${f} = @${f}`); params[f] = req.body[f]; }
  }
  if (!sets.length) return res.json(exists);
  db.prepare(`UPDATE reviews SET ${sets.join(', ')} WHERE id = @id`).run(params);
  res.json(db.prepare('SELECT * FROM reviews WHERE id = ?').get(req.params.id));
});

// DELETE /api/reviews/:id
router.delete('/:id', (req, res) => {
  const info = db.prepare('DELETE FROM reviews WHERE id = ?').run(req.params.id);
  if (!info.changes) return res.status(404).json({ error: 'not found' });
  res.json({ ok: true });
});

export default router;

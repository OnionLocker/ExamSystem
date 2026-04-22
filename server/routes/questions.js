import { Router } from 'express';
import db from '../db.js';

const router = Router();

const parseJSON = (s, fallback) => {
  if (!s) return fallback;
  try { return JSON.parse(s); } catch { return fallback; }
};

const mapRow = (r) => r && ({
  ...r,
  options: parseJSON(r.options, []),
  tags: parseJSON(r.tags, []),
});

// GET /api/questions  ֧持ɸѡ: category / sub_category / limit / offset / random
router.get('/', (req, res) => {
  const { category, sub_category, random } = req.query;
  const limit = Math.min(parseInt(req.query.limit) || 50, 200);
  const offset = parseInt(req.query.offset) || 0;

  const where = [];
  const params = {};
  if (category) { where.push('category = @category'); params.category = category; }
  if (sub_category) { where.push('sub_category = @sub_category'); params.sub_category = sub_category; }
  const whereSql = where.length ? 'WHERE ' + where.join(' AND ') : '';
  const orderSql = random ? 'ORDER BY RANDOM()' : 'ORDER BY id DESC';

  const rows = db.prepare(
    `SELECT * FROM questions ${whereSql} ${orderSql} LIMIT @limit OFFSET @offset`
  ).all({ ...params, limit, offset });

  const total = db.prepare(`SELECT COUNT(*) AS c FROM questions ${whereSql}`).get(params).c;

  res.json({ total, items: rows.map(mapRow) });
});

// GET /api/questions/:id
router.get('/:id', (req, res) => {
  const row = db.prepare('SELECT * FROM questions WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'not found' });
  res.json(mapRow(row));
});

// POST /api/questions
router.post('/', (req, res) => {
  const { category, sub_category, content, options, correct_answer, explanation, difficulty, tags, source } = req.body || {};
  if (!category || !content || !correct_answer) {
    return res.status(400).json({ error: 'category / content / correct_answer 必填' });
  }
  const info = db.prepare(`
    INSERT INTO questions (category, sub_category, content, options, correct_answer, explanation, difficulty, tags, source)
    VALUES (@category, @sub_category, @content, @options, @correct_answer, @explanation, @difficulty, @tags, @source)
  `).run({
    category,
    sub_category: sub_category || null,
    content,
    options: options ? JSON.stringify(options) : null,
    correct_answer,
    explanation: explanation || null,
    difficulty: difficulty ?? 2,
    tags: tags ? JSON.stringify(tags) : null,
    source: source || null,
  });
  const row = db.prepare('SELECT * FROM questions WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json(mapRow(row));
});

// PUT /api/questions/:id
router.put('/:id', (req, res) => {
  const exists = db.prepare('SELECT id FROM questions WHERE id = ?').get(req.params.id);
  if (!exists) return res.status(404).json({ error: 'not found' });

  const fields = ['category', 'sub_category', 'content', 'correct_answer', 'explanation', 'difficulty', 'source'];
  const sets = [];
  const params = { id: req.params.id };
  for (const f of fields) {
    if (req.body[f] !== undefined) { sets.push(`${f} = @${f}`); params[f] = req.body[f]; }
  }
  if (req.body.options !== undefined) { sets.push('options = @options'); params.options = JSON.stringify(req.body.options); }
  if (req.body.tags !== undefined) { sets.push('tags = @tags'); params.tags = JSON.stringify(req.body.tags); }
  if (!sets.length) return res.json(mapRow(db.prepare('SELECT * FROM questions WHERE id = ?').get(req.params.id)));

  db.prepare(`UPDATE questions SET ${sets.join(', ')} WHERE id = @id`).run(params);
  res.json(mapRow(db.prepare('SELECT * FROM questions WHERE id = ?').get(req.params.id)));
});

// DELETE /api/questions/:id
router.delete('/:id', (req, res) => {
  const info = db.prepare('DELETE FROM questions WHERE id = ?').run(req.params.id);
  if (!info.changes) return res.status(404).json({ error: 'not found' });
  res.json({ ok: true });
});

// GET /api/questions/meta/categories  分类 + 子分类 + 数量
router.get('/meta/categories', (_req, res) => {
  const rows = db.prepare(`
    SELECT category, sub_category, COUNT(*) AS count
    FROM questions
    GROUP BY category, sub_category
    ORDER BY category, sub_category
  `).all();
  res.json(rows);
});

export default router;

import { Router } from 'express';
import db from '../db.js';
import { recomputeMastery } from '../mastery.js';

const router = Router();

function scoreOf(row) {
  if (row == null) return null;
  if (row.mastery != null) return row.mastery;
  if (row.attempts > 0) return Math.round((row.correct * 100) / row.attempts);
  return null;
}

function view(row) {
  return { ...row, score: scoreOf(row) };
}

router.get('/', (_req, res) => {
  recomputeMastery(db);
  const items = db.prepare(`
    SELECT kaodian, module, subtype, attempts, correct, total_ms,
           last_seen, streak, note, mastery, mastery_note,
           mastery_confidence, mastery_samples, mastery_source,
           mastery_updated_at, updated_at
      FROM kaodian_profile
     ORDER BY module, kaodian
  `).all();
  res.json({ items: items.map(view) });
});

router.post('/mastery', (req, res) => {
  const kaodian = String(req.body?.kaodian || '').trim();
  const hasMastery = req.body?.mastery != null;
  const mastery = Number(req.body?.mastery);
  const note = String(req.body?.note || '').trim();
  const module = String(req.body?.module || '').trim();
  const subtype = String(req.body?.subtype || '').trim();
  if (!kaodian) return res.status(400).json({ error: 'kaodian required' });
  if (hasMastery && (!Number.isFinite(mastery) || mastery < 0 || mastery > 100)) {
    return res.status(400).json({ error: 'mastery must be 0-100' });
  }
  const existing = db.prepare('SELECT kaodian FROM kaodian_profile WHERE kaodian = ?').get(kaodian);
  if (existing) {
    db.prepare(`
      UPDATE kaodian_profile
         SET mastery = CASE WHEN @hasMastery THEN @score ELSE mastery END,
             mastery_source = CASE WHEN @hasMastery THEN 'manual' ELSE mastery_source END,
             mastery_note = CASE WHEN @note = '' THEN mastery_note ELSE @note END,
             module = CASE WHEN @module = '' THEN module ELSE @module END,
             subtype = CASE WHEN @subtype = '' THEN subtype ELSE @subtype END,
             updated_at = datetime('now', '+8 hours')
       WHERE kaodian = @kaodian
    `).run({ kaodian, hasMastery: hasMastery ? 1 : 0, score: hasMastery ? Math.round(mastery) : null, note, module, subtype });
  } else {
    const inferred = module || kaodian.split('-')[0] || '未分类';
    db.prepare(`
      INSERT INTO kaodian_profile
        (kaodian, module, subtype, attempts, correct, total_ms, last_seen, streak, note, mastery, mastery_note, mastery_source)
      VALUES (@kaodian, @module, @subtype, 0, 0, 0, date('now'), 0, @note,
              CASE WHEN @hasMastery THEN @score ELSE NULL END,
              @note, CASE WHEN @hasMastery THEN 'manual' ELSE 'auto' END)
    `).run({
      kaodian,
      module: inferred,
      subtype,
      note,
      hasMastery: hasMastery ? 1 : 0,
      score: hasMastery ? Math.round(mastery) : null,
    });
  }
  const row = db.prepare(`
    SELECT kaodian, module, subtype, attempts, correct, total_ms,
           last_seen, streak, note, mastery, mastery_note,
           mastery_confidence, mastery_samples, mastery_source,
           mastery_updated_at, updated_at
      FROM kaodian_profile
     WHERE kaodian = ?
  `).get(kaodian);
  res.json(view(row));
});

export default router;

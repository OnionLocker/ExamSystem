import { Router } from 'express';
import db from '../db.js';

const router = Router();

function scoreOf(row) {
  if (row == null) return null;
  if (row.mastery != null) return row.mastery;
  return null;
}

function view(row) {
  return { ...row, score: scoreOf(row) };
}

function loadProfiles() {
  return db.prepare(`
    SELECT kaodian, module, subtype, attempts, correct, total_ms,
           last_seen, streak, note, mastery, mastery_note,
           mastery_confidence, mastery_samples, mastery_source,
           mastery_updated_at, updated_at
      FROM kaodian_profile
     ORDER BY module, kaodian
  `).all();
}

router.get('/', (_req, res) => {
  let aliases = [];
  try {
    aliases = db.prepare('SELECT alias, canonical, module, subtype FROM kaodian_aliases').all();
  } catch {
    aliases = [];
  }
  res.json({ items: loadProfiles().map(view), aliases });
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
             updated_at = datetime('now')
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

router.get('/debts', (_req, res) => {
  try {
    const debts = db.prepare(`
      SELECT
        d.kaodian,
        d.wrong_count,
        d.recovery_streak,
        d.last_wrong_at,
        d.last_seen_at,
        d.mastered,
        p.module,
        p.mastery,
        p.mastery_confidence,
        julianday('now') - julianday(d.last_wrong_at) as days_since_wrong
      FROM kaodian_debts d
      LEFT JOIN kaodian_profile p ON d.kaodian = p.kaodian
      WHERE d.mastered = 0
      ORDER BY (d.wrong_count * (julianday('now') - julianday(d.last_wrong_at))) DESC
    `).all();

    const thisWeek = db.prepare(`
      SELECT COUNT(*) as count
      FROM kaodian_debts
      WHERE mastered = 1
        AND datetime(updated_at) >= datetime('now', '-7 days')
    `).get();

    res.json({
      debts: debts.map(d => ({
        kaodian: d.kaodian,
        module: d.module || d.kaodian.split('-')[0] || '未分类',
        wrongCount: d.wrong_count,
        recoveryStreak: d.recovery_streak,
        recoveryProgress: `${d.recovery_streak}/2`,
        lastWrongAt: d.last_wrong_at,
        daysSinceWrong: Math.floor(d.days_since_wrong || 0),
        mastery: d.mastery,
        confidence: d.mastery_confidence || 0
      })),
      summary: {
        open: debts.length,
        clearedThisWeek: thisWeek.count
      }
    });
  } catch (error) {
    console.error('Error fetching debts:', error);
    res.status(500).json({ error: 'Failed to fetch debts' });
  }
});

export default router;

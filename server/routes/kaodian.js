import { Router } from 'express';
import db from '../db.js';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import tree from '../../src/knowledge/fenbiTree.json' with { type: 'json' };

const execFileAsync = promisify(execFile);
const profileScript = fileURLToPath(new URL('../../scripts/kaodian_profile.py', import.meta.url));
const knownTags = new Set(tree.modules.flatMap(m => m.children.flatMap(g =>
  g.children.map(l => `${m.name}-${g.name}-${l.name}`))));
function canonicalTag(raw) {
  const tag = String(raw || '').trim();
  return db.prepare('SELECT canonical FROM kaodian_aliases WHERE alias=?').get(tag)?.canonical || tag;
}
function learningStatus(row) {
  if (row.status === 'learning') return 'learning';
  if (row.mastered === 0 && row.last_wrong_at) return 'debt';
  if (row.mastered === 1 && row.last_wrong_at) return 'cleared';
  return row.mastery != null && row.mastery < 60 && (row.mastery_confidence || 0) >= 40 ? 'reinforce' : 'learned';
}

const router = Router();

function scoreOf(row) {
  if (row == null) return null;
  if (row.mastery != null) return row.mastery;
  return null;
}

function view(row) {
  const { assessment_json, ...fields } = row;
  return { ...fields, score: scoreOf(row), assessment: assessment_json ? JSON.parse(assessment_json) : null };
}

function loadProfiles() {
  return db.prepare(`
    SELECT kaodian, module, subtype, attempts, correct, total_ms,
           last_seen, streak, note, mastery, mastery_note,
           mastery_confidence, mastery_samples, mastery_source,
           mastery_updated_at, updated_at, assessment_json
      FROM kaodian_profile
     ORDER BY module, kaodian
  `).all();
}

router.get('/', async (_req, res, next) => {
  try {
    await execFileAsync('python3', [profileScript, '--recompute'], {
      env: { ...process.env, EXAM_DB: db.name }, timeout: 30000,
    });
    const aliases = db.prepare('SELECT alias, canonical, module, subtype FROM kaodian_aliases').all();
    res.json({ items: loadProfiles().map(view), aliases });
  } catch (error) { next(error); }
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
           mastery_updated_at, updated_at, assessment_json
      FROM kaodian_profile
     WHERE kaodian = ?
  `).get(kaodian);
  res.json(view(row));
});

router.get('/debts', (_req, res) => {
  try {
    const rows = db.prepare(`
      SELECT
        l.kaodian,l.status,
        COALESCE(d.wrong_count,0) AS wrong_count,
        COALESCE(d.recovery_streak,0) AS recovery_streak,
        d.last_wrong_at,
        d.last_seen_at,
        d.mastered,
        p.module,
        p.mastery,
        p.mastery_confidence,
        p.assessment_json,
        julianday('now') - julianday(d.last_wrong_at) as days_since_wrong
      FROM kaodian_learning l
      LEFT JOIN kaodian_debts d ON d.kaodian=l.kaodian
      LEFT JOIN kaodian_profile p ON l.kaodian = p.kaodian
      WHERE l.status IN ('learning','learned')
      ORDER BY CASE WHEN d.mastered=0 THEN 0 ELSE 1 END,
        (d.wrong_count * (julianday('now') - julianday(d.last_wrong_at))) DESC
    `).all();

    const debts = rows.map(d => ({
      kaodian: d.kaodian,
      module: d.module || d.kaodian.split('-')[0] || '未分类',
      wrongCount: d.wrong_count,
      recoveryStreak: d.recovery_streak,
      recoveryProgress: `${d.recovery_streak}/2`,
      lastWrongAt: d.last_wrong_at,
      daysSinceWrong: d.last_wrong_at ? Math.floor(Math.max(0, d.days_since_wrong || 0)) : null,
      mastery: d.mastery,
      confidence: d.mastery_confidence || 0,
      assessment: d.assessment_json ? JSON.parse(d.assessment_json) : null,
      status: learningStatus(d),
    }));
    const summary = {
      learning: debts.filter(d => d.status === 'learning').length,
      reinforce: debts.filter(d => d.status === 'reinforce').length,
      open: debts.filter(d => d.status === 'debt').length,
      cleared: debts.filter(d => d.status === 'cleared').length,
    };

    res.json({
      debts,
      summary,
    });
  } catch (error) {
    console.error('Error fetching debts:', error);
    res.status(500).json({ error: 'Failed to fetch debts' });
  }
});

router.get('/learning/:kaodian', (req, res) => {
  const tag = canonicalTag(req.params.kaodian);
  const row = db.prepare(`
    SELECT l.kaodian,l.status,l.learned_at,d.mastered,d.last_wrong_at,p.mastery,p.mastery_confidence
      FROM kaodian_learning l
      LEFT JOIN kaodian_debts d ON d.kaodian=? AND l.kaodian=d.kaodian
      LEFT JOIN kaodian_profile p ON p.kaodian=?
     WHERE l.kaodian=? OR substr(?,1,length(l.kaodian)+1)=l.kaodian || '-'
     ORDER BY length(l.kaodian) DESC LIMIT 1
  `).get(tag, tag, tag, tag);
  if (!row) {
    const profile = db.prepare('SELECT attempts,mastery,mastery_confidence FROM kaodian_profile WHERE kaodian=?').get(tag);
    return res.json({ kaodian: tag, status: profile?.attempts ? 'unconfirmed' : 'unstarted', learnedAt: null });
  }
  const status = learningStatus(row);
  res.json({ kaodian: tag, status, learnedAt: row.learned_at });
});

router.put('/learning/:kaodian', async (req, res) => {
  const tag = canonicalTag(req.params.kaodian);
  const status = String(req.body?.status || '').trim();
  if (!tag || tag.includes('-@') || !['learning', 'learned'].includes(status)) {
    return res.status(400).json({ error: '请选择有效知识标签及学习状态' });
  }
  if (!knownTags.has(tag) && !db.prepare('SELECT 1 FROM kaodian_profile WHERE kaodian=?').get(tag)) {
    return res.status(404).json({ error: '知识标签尚未登记' });
  }
  const current = db.prepare('SELECT status FROM kaodian_learning WHERE kaodian=?').get(tag);
  if (current?.status === 'learned' && status === 'learning') {
    return res.status(409).json({ error: '已确认学过的考点不能降回学习中' });
  }
  try {
    const { stdout } = await execFileAsync('python3', [profileScript, '--learning', tag, status], {
      env: { ...process.env, EXAM_DB: db.name }, timeout: 15000,
    });
    const stored = JSON.parse(stdout).kaodian;
    const row = db.prepare(`SELECT l.status,l.learned_at,d.mastered,d.last_wrong_at,p.mastery,p.mastery_confidence
      FROM kaodian_learning l LEFT JOIN kaodian_debts d ON d.kaodian=l.kaodian
      LEFT JOIN kaodian_profile p ON p.kaodian=l.kaodian WHERE l.kaodian=?`).get(stored);
    res.json({ kaodian: stored, status: learningStatus(row), learnedAt: row.learned_at });
  } catch (error) {
    console.error('Learning state update failed:', error.message);
    res.status(500).json({ error: '学习状态保存失败，请重新读取状态后再试' });
  }
});

export default router;

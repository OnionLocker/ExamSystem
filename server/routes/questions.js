import { Router } from 'express';
import db from '../db.js';

const router = Router();

// JSON 字段列表：需要从字符串反序列化的列
const JSON_COLS = ['options', 'stem_images', 'explanation_images', 'tags'];

const parseQuestion = (row) => {
  if (!row) return row;
  const out = { ...row };
  for (const col of JSON_COLS) {
    if (typeof out[col] === 'string') {
      try { out[col] = JSON.parse(out[col]); } catch { out[col] = []; }
    }
  }
  return out;
};

// ─────────────────────────────────────────────
// GET /api/questions
//   ?category=   ?sub_category=   ?batch_id=
//   ?random=1    ?limit=30
// ─────────────────────────────────────────────
router.get('/', (req, res) => {
  const { category, sub_category, batch_id, random, limit } = req.query;
  const lim = Math.min(200, Math.max(1, parseInt(limit) || 30));

  const where = [];
  const params = [];

  if (category) { where.push('category = ?'); params.push(category); }
  if (sub_category) { where.push('sub_category = ?'); params.push(sub_category); }
  if (batch_id) { where.push('batch_id = ?'); params.push(batch_id); }

  const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';
  const order = random === '1' ? 'ORDER BY RANDOM()' : 'ORDER BY id ASC';

  const rows = db
    .prepare(
      `SELECT id, external_id, category, sub_category, question_type,
              content, stem_images, options, correct_answer, explanation,
              explanation_images, difficulty, tags, source, year, region,
              material_id, batch_id
       FROM questions ${clause} ${order} LIMIT ?`,
    )
    .all(...params, lim);

  res.json({ items: rows.map(parseQuestion), total: rows.length });
});

// ─────────────────────────────────────────────
// GET /api/questions/meta/categories
//   返回 [{category, sub_category, count}]
// ─────────────────────────────────────────────
router.get('/meta/categories', (_req, res) => {
  const rows = db
    .prepare(
      `SELECT category, sub_category, COUNT(*) AS count
       FROM questions
       GROUP BY category, sub_category
       ORDER BY category, sub_category`,
    )
    .all();
  res.json(rows);
});

// ─────────────────────────────────────────────
// GET /api/questions/meta/batches
//   返回 [{batch_id, source, count, done_count, correct_count, last_answered_at}]
//   done_count: 曾经作答过的不重复题目数
//   correct_count: 累计答对次数（含重复刷）
//   last_answered_at: 最近一次作答时间
// ─────────────────────────────────────────────
router.get('/meta/batches', (_req, res) => {
  const rows = db
    .prepare(
      `SELECT
         q.batch_id,
         MAX(q.source)                          AS source,
         COUNT(DISTINCT q.id)                   AS count,
         COUNT(DISTINCT pa.question_id)          AS done_count,
         COALESCE(SUM(pa.is_correct), 0)         AS correct_count,
         COUNT(pa.id)                            AS attempt_count,
         MAX(pa.answered_at)                     AS last_answered_at
       FROM questions q
       LEFT JOIN practice_answers pa ON pa.question_id = q.id
       WHERE q.batch_id IS NOT NULL AND q.batch_id != ''
       GROUP BY q.batch_id
       ORDER BY COALESCE(MAX(pa.answered_at), MAX(q.created_at)) DESC`,
    )
    .all();
  res.json(rows);
});

// ─────────────────────────────────────────────
// DELETE /api/questions/batch/:batchId
//   删掉整个题组（测试出的题组用）。
//   questions 一删，practice_answers / mistakes 靠 FK ON DELETE CASCADE 跟着走；
//   本批次的 practice_sessions（category 存的就是 batch_id）也一并清掉，
//   否则批次列表没了但会话记录还挂着。
//   → { ok, deleted_questions, deleted_sessions }
// ─────────────────────────────────────────────
router.delete('/batch/:batchId', (req, res) => {
  const batchId = String(req.params.batchId || '');
  if (!batchId) return res.status(400).json({ error: 'batch_id required' });

  const { c: qCount } = db
    .prepare('SELECT COUNT(*) AS c FROM questions WHERE batch_id = ?')
    .get(batchId);
  if (!qCount) return res.status(404).json({ error: 'batch not found' });

  const run = db.transaction(() => {
    // 先删 session：answers 有两条 FK（session_id / question_id），
    // 两边都是 CASCADE，先删哪个都不会留孤儿行
    const s = db.prepare('DELETE FROM practice_sessions WHERE category = ?').run(batchId);
    const q = db.prepare('DELETE FROM questions WHERE batch_id = ?').run(batchId);
    return { sessions: s.changes, questions: q.changes };
  });

  const out = run();
  res.json({ ok: true, deleted_questions: out.questions, deleted_sessions: out.sessions });
});

// ─────────────────────────────────────────────
// GET /api/questions/meta/history?batch_id=
//   某批次内每道题的历史作答摘要
//   → { <question_id>: { attempts, wrong, last_correct, last_answer, last_at } }
//   做题页用来显示「这题你上次做错了」
// ─────────────────────────────────────────────
router.get('/meta/history', (req, res) => {
  const { batch_id } = req.query;
  if (!batch_id) return res.status(400).json({ error: 'batch_id required' });

  const rows = db
    .prepare(
      `SELECT
         pa.question_id,
         COUNT(*)                                  AS attempts,
         SUM(CASE WHEN pa.is_correct = 0 AND pa.user_answer != '' THEN 1 ELSE 0 END) AS wrong,
         MAX(pa.answered_at)                       AS last_at
       FROM practice_answers pa
       JOIN questions q ON q.id = pa.question_id
       WHERE q.batch_id = ?
       GROUP BY pa.question_id`,
    )
    .all(String(batch_id));

  // 每题最近一次的作答明细（用子查询取 max(id) 那条，id 单调递增即时间序）
  const lastRows = db
    .prepare(
      `SELECT pa.question_id, pa.user_answer, pa.is_correct
       FROM practice_answers pa
       JOIN questions q ON q.id = pa.question_id
       WHERE q.batch_id = ?
         AND pa.id = (
           SELECT MAX(p2.id) FROM practice_answers p2 WHERE p2.question_id = pa.question_id
         )`,
    )
    .all(String(batch_id));

  const lastById = new Map(lastRows.map((r) => [r.question_id, r]));

  const out = {};
  for (const r of rows) {
    const last = lastById.get(r.question_id);
    out[r.question_id] = {
      attempts: r.attempts,
      wrong: r.wrong,
      last_at: r.last_at,
      last_answer: last?.user_answer ?? null,
      last_correct: last ? !!last.is_correct : null,
    };
  }
  res.json(out);
});

export default router;

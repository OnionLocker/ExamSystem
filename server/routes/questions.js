import { Router } from 'express';
import db from '../db.js';
import { unlinkDraftsOfSessions } from './practice.js';

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

const parseJson = (v, fallback) => {
  if (typeof v !== 'string') return v ?? fallback;
  try { return JSON.parse(v); } catch { return fallback; }
};

const attachMaterials = (rows) => {
  const ids = [...new Set(rows.map((r) => r.material_id).filter(Boolean))];
  const matMap = new Map();
  if (ids.length) {
    const mats = db
      .prepare(`SELECT id, content, images FROM materials WHERE id IN (${ids.map(() => '?').join(',')})`)
      .all(...ids);
    for (const m of mats) {
      matMap.set(m.id, { id: m.id, content: m.content, images: parseJson(m.images, []) });
    }
  }
  return rows.map((row) => {
    const q = parseQuestion(row);
    const mat = q.material_id ? matMap.get(q.material_id) : null;
    if (mat) q.material = mat;
    return q;
  });
};

// ─────────────────────────────────────────────
// GET /api/questions
//   ?category=   ?sub_category=   ?batch_id=
//   ?random=1    ?limit=30
// ─────────────────────────────────────────────

const isDailyBatch = (batchId) => String(batchId || '').startsWith('daily-');
const paperBlob = (q) => `${q.sub_category || ''}${JSON.stringify(q.tags || [])}`;
const paperRank = (q) => {
  const cat = String(q.category || '');
  const blob = paperBlob(q);
  if (cat === '\u6570\u91cf\u5173\u7cfb') return blob.includes('\u6570\u5b57\u63a8\u7406') ? 1 : 2;
  if (cat === '\u5224\u65ad\u63a8\u7406') {
    if (blob.includes('\u79d1\u5b66\u63a8\u7406')) return 3;
    if (blob.includes('\u56fe\u5f62\u63a8\u7406')) return 1;
    return 2;
  }
  if (cat === '\u8a00\u8bed\u7406\u89e3\u4e0e\u8868\u8fbe') return blob.includes('\u903b\u8f91\u586b\u7a7a') ? 1 : 2;
  return 0;
};
const sortDailyPaper = (items) => [...items].sort((a, b) =>
  paperRank(a) - paperRank(b)
  || (a.material_id || 0) - (b.material_id || 0)
  || a.id - b.id
);

router.get('/', (req, res) => {
  const { category, sub_category, batch_id, random, limit } = req.query;
  const lim = Math.min(200, Math.max(1, parseInt(limit) || 30));

  const where = [];
  const params = [];

  if (category) { where.push('category = ?'); params.push(category); }
  if (sub_category) { where.push('sub_category = ?'); params.push(sub_category); }
  if (batch_id) { where.push('batch_id = ?'); params.push(batch_id); }

  const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';
  const grouped = batch_id && db
    .prepare('SELECT 1 AS x FROM questions WHERE batch_id = ? AND material_id IS NOT NULL LIMIT 1')
    .get(batch_id);
  // 资料分析一组材料绑多题：乱序会把同一份材料拆开，左边跟着跳。
  const daily = isDailyBatch(batch_id);
  const order = grouped || daily
    ? 'ORDER BY material_id, id'
    : random === '1' ? 'ORDER BY RANDOM()' : 'ORDER BY id ASC';

  const rows = db
    .prepare(
      `SELECT id, external_id, category, sub_category, question_type,
              content, stem_images, options, correct_answer, explanation,
              explanation_images, difficulty, tags, source, year, region,
              material_id, batch_id
       FROM questions ${clause} ${order} LIMIT ?`,
    )
    .all(...params, lim);

  let items = attachMaterials(rows);
  if (daily) items = sortDailyPaper(items);
  res.json({ items, total: items.length });
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
//   返回 [{batch_id, source, count, done_count, correct_count, last_answered_at, last_session_id}]
//   last_session_id: 最近一次已交卷的练习，前端拿它判定「点进去是开做还是复盘」
//   done_count: 曾经作答过的不重复题目数
//   correct_count: 累计答对次数（含重复刷）
//   last_answered_at: 最近一次作答时间
// ─────────────────────────────────────────────
router.get('/meta/batches', (req, res) => {
  const includeScheduled = ['1', 'true'].includes(String(req.query.include_scheduled || '').toLowerCase());
  const module = req.query.module ? String(req.query.module) : null;
  const date = req.query.date ? String(req.query.date) : null;
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) return res.status(400).json({ error: 'date must be YYYY-MM-DD' });
  const where = [includeScheduled ? '1 = 1' : 'b.count > 0'];
  const params = [];
  if (module) { where.push('COALESCE(r.module, b.category) = ?'); params.push(module); }
  const planDate = `COALESCE(r.plan_date, CASE WHEN substr(b.batch_id, 1, 8) GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' THEN substr(b.batch_id, 1, 4) || '-' || substr(b.batch_id, 5, 2) || '-' || substr(b.batch_id, 7, 2) END, date(b.created_at, '+8 hours'))`;
  if (date) { where.push(`${planDate} = ?`); params.push(date); }
  const rows = db.prepare(
    `WITH question_batches AS (
       SELECT q.batch_id, MAX(q.source) AS source, MAX(q.category) AS category,
              MAX(q.created_at) AS created_at, COUNT(DISTINCT q.id) AS count,
              COUNT(DISTINCT pa.question_id) AS done_count,
              COALESCE(SUM(pa.is_correct), 0) AS correct_count,
              COUNT(pa.id) AS attempt_count, MAX(pa.answered_at) AS last_answered_at
         FROM questions q LEFT JOIN practice_answers pa ON pa.question_id = q.id
        WHERE q.batch_id IS NOT NULL AND q.batch_id != '' GROUP BY q.batch_id
     ), batch_ids AS (
       SELECT batch_id FROM question_batches UNION
       SELECT batch_id FROM ai_daily_batch_runs WHERE batch_id IS NOT NULL AND batch_id != '' AND status != 'deleted'
     ), batches AS (
       SELECT ids.batch_id, qb.source, qb.category, qb.created_at,
              COALESCE(qb.count, 0) AS count, COALESCE(qb.done_count, 0) AS done_count,
              COALESCE(qb.correct_count, 0) AS correct_count,
              COALESCE(qb.attempt_count, 0) AS attempt_count, qb.last_answered_at
         FROM batch_ids ids LEFT JOIN question_batches qb ON qb.batch_id = ids.batch_id
     )
     SELECT b.batch_id, COALESCE(b.source, r.source) AS source, b.count, b.done_count,
            b.correct_count, b.attempt_count, b.last_answered_at,
            (SELECT ps.id FROM practice_sessions ps WHERE ps.category = b.batch_id AND ps.ended_at IS NOT NULL AND ps.total > 0 ORDER BY ps.ended_at DESC LIMIT 1) AS last_session_id,
            COALESCE(b.category, r.module) AS category, COALESCE(r.module, b.category) AS module,
            ${planDate} AS plan_date, r.plan_date AS daily_plan_date,
            COALESCE(b.created_at, r.imported_at, r.created_at) AS created_at,
            COALESCE(r.status, 'imported') AS status
       FROM batches b LEFT JOIN ai_daily_batch_runs r ON r.id = (
         SELECT ar.id FROM ai_daily_batch_runs ar WHERE ar.batch_id = b.batch_id ORDER BY ar.plan_date DESC, ar.id DESC LIMIT 1
       ) WHERE ${where.join(' AND ')}
       ORDER BY COALESCE(b.last_answered_at, r.imported_at, b.created_at, r.created_at) DESC`,
  ).all(...params);
  res.json(rows);
});

// ─────────────────────────────────────────────
// DELETE /api/questions/batch/:batchId
//   删掉整个题组（测试出的题组用）。
//   questions 一删，practice_answers 靠 FK ON DELETE CASCADE 跟着走；
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

  // 草稿图的 DB 行会跟着 session 级联删掉，但磁盘文件不会，先按 session 收集再删
  const sessionIds = db
    .prepare('SELECT id FROM practice_sessions WHERE category = ?')
    .all(batchId)
    .map((r) => r.id);
  unlinkDraftsOfSessions(sessionIds);

  const run = db.transaction(() => {
    // 先删 session：answers 有两条 FK（session_id / question_id），
    // 两边都是 CASCADE，先删哪个都不会留孤儿行
    const s = db.prepare('DELETE FROM practice_sessions WHERE category = ?').run(batchId);
    const q = db.prepare('DELETE FROM questions WHERE batch_id = ?').run(batchId);
    db.prepare('DELETE FROM materials WHERE batch_id = ?').run(batchId);
    db.prepare("UPDATE ai_daily_batch_runs SET status='deleted', error=NULL, updated_at=datetime('now') WHERE batch_id=?").run(batchId);
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

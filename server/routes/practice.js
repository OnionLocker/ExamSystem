import { Router } from 'express';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import db from '../db.js';

const router = Router();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const draftDir = path.join(__dirname, '..', '..', 'data', 'draft-images');
if (!fs.existsSync(draftDir)) fs.mkdirSync(draftDir, { recursive: true });

const DRAFT_MAX_BYTES = 8 * 1024 * 1024;

// 草稿图是「网页截图 + 笔迹」，canvas 导出的 PNG 是 24 位真彩，一张约 300KB。
// 这图要喂给 Hermes 复盘，而它进上下文是按 base64 文本计费的，300KB ≈ 28 万 token，
// 且此后每轮对话都要重发一遍 —— 一张图就能把整个会话拖到每条回复几分钟。
//
// 两步瘦身：先按 Box 滤镜缩到 1024 宽（只缩不放），再量化到 16 色且不抖动。
// 草稿页本来就是纯色背景 + 黑色墨迹，实测题干、选项、小字徽章、划线笔迹全部清晰可辨，
// 体积 295KB → 39KB（≈3.7 万 token）。
//
// 注意顺序：缩放必须在量化之前。反过来先量化再缩放，重采样会重新引入大量中间色，
// 反而比不缩更大（实测 1536→1280 时体积从 73KB 涨到 111KB）。
const DRAFT_MAX_WIDTH = 1024;
const PALETTE_COLORS = 16;

const shrinkPng = (buf) => {
  const r = spawnSync(
    'convert',
    [
      'png:-',
      '-filter', 'Box',
      '-resize', `${DRAFT_MAX_WIDTH}x>`,
      '+dither', '-colors', String(PALETTE_COLORS),
      '-define', 'png:compression-level=9',
      'png8:-',
    ],
    { input: buf, maxBuffer: DRAFT_MAX_BYTES },
  );
  const out = r.status === 0 ? r.stdout : null;
  // 没装 ImageMagick、或压完反而更大，就照原样存
  return out && out.length && out.length < buf.length ? out : buf;
};

const safeUnlinkDraft = (filename) => {
  if (!filename || filename.includes('..') || filename.includes('/') || filename.includes('\\')) return;
  try {
    const full = path.join(draftDir, filename);
    if (fs.existsSync(full)) fs.unlinkSync(full);
  } catch { /* 文件没了就算了，不该因为清理失败挡住主流程 */ }
};

// 题组删除时要一起把草稿图文件删掉：DB 行有 CASCADE，磁盘文件没有
export const unlinkDraftsOfSessions = (sessionIds) => {
  if (!sessionIds?.length) return 0;
  const placeholders = sessionIds.map(() => '?').join(',');
  const rows = db
    .prepare(`SELECT filename FROM practice_drafts WHERE session_id IN (${placeholders})`)
    .all(...sessionIds);
  for (const r of rows) safeUnlinkDraft(r.filename);
  return rows.length;
};

const parseOptions = (raw) => {
  if (typeof raw !== 'string') return raw || [];
  try { return JSON.parse(raw); } catch { return []; }
};

const draftUrl = (sessionId, questionId) =>
  `/api/practice/sessions/${sessionId}/drafts/${questionId}/file`;

// ───────────────────────────────────────────────────────────────
// POST /api/practice/sessions
//   body: { category }
//   → { id }
// ───────────────────────────────────────────────────────────────
router.post('/sessions', (req, res) => {
  const { category = '刷题' } = req.body || {};
  const cat = String(category).slice(0, 100);

  // 开新的一场之前，把这个题组上没交卷就跑了的残局清掉。
  // 没交卷就不算一次：既不该出现在复盘里，也不该把草稿图留在磁盘上。
  const stale = db
    .prepare('SELECT id FROM practice_sessions WHERE category = ? AND ended_at IS NULL')
    .all(cat)
    .map((r) => r.id);
  if (stale.length > 0) {
    unlinkDraftsOfSessions(stale);
    db.prepare(
      `DELETE FROM practice_sessions WHERE id IN (${stale.map(() => '?').join(',')})`,
    ).run(...stale);
  }

  const result = db
    .prepare(
      `INSERT INTO practice_sessions (category, started_at)
       VALUES (?, datetime('now'))`,
    )
    .run(cat);
  res.status(201).json({ id: result.lastInsertRowid });
});

// ────────────────────────────────────────────────────────
// DELETE /api/practice/sessions/:id
//   中途放弃一场没交卷的练习，连草稿一起删干净。
//   已交卷的不给删 —— 那是已经算数的成绩，只能随整个题组删除时清。
// ────────────────────────────────────────────────────────
router.delete('/sessions/:id', (req, res) => {
  const sessionId = Number(req.params.id);
  const session = db
    .prepare('SELECT id, ended_at FROM practice_sessions WHERE id = ?')
    .get(sessionId);
  if (!session) return res.status(404).json({ error: 'session not found' });
  if (session.ended_at) return res.status(409).json({ error: '已交卷的练习不能丢弃' });

  unlinkDraftsOfSessions([sessionId]);
  db.prepare('DELETE FROM practice_sessions WHERE id = ?').run(sessionId);
  res.json({ ok: true });
});

// ───────────────────────────────────────────────────────────────
// GET /api/practice/sessions?limit=20&category=
//   最近做完的练习，给 Hermes 挑「分析哪一次的错题」用
// ───────────────────────────────────────────────────────────────
router.get('/sessions', (req, res) => {
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit) || 20));
  const category = req.query.category ? String(req.query.category) : null;

  const rows = db
    .prepare(
      `SELECT
         s.id, s.category, s.total, s.correct, s.duration_sec, s.started_at, s.ended_at,
         (SELECT COUNT(*) FROM practice_answers pa
           WHERE pa.session_id = s.id AND pa.is_correct = 0)          AS wrong_count,
         (SELECT COUNT(*) FROM practice_drafts pd
           WHERE pd.session_id = s.id)                                AS draft_count
       FROM practice_sessions s
       WHERE s.ended_at IS NOT NULL
         AND s.total > 0
         ${category ? 'AND s.category = ?' : ''}
       ORDER BY s.ended_at DESC
       LIMIT ?`,
    )
    .all(...(category ? [category, limit] : [limit]));

  res.json(rows);
});

// ───────────────────────────────────────────────────────────────
// POST /api/practice/sessions/:id/submit
//   body: { duration_sec, answers: [{ question_id, user_answer, time_spent_sec }] }
//   → { total, correct, accuracy, duration_sec, results: [...] }
//
//   AI 练题的「交卷」：整卷一次性判分。答案先攒在前端，
//   所以做题过程里可以随便回头改，交卷这一刻才落库。
// ───────────────────────────────────────────────────────────────
router.post('/sessions/:id/submit', (req, res) => {
  const sessionId = Number(req.params.id);
  const { duration_sec = 0, answers } = req.body || {};

  const session = db.prepare('SELECT id, ended_at FROM practice_sessions WHERE id = ?').get(sessionId);
  if (!session) return res.status(404).json({ error: 'session not found' });
  if (session.ended_at) return res.status(409).json({ error: '这份卷子已经交过了' });
  if (!Array.isArray(answers) || answers.length === 0) {
    return res.status(400).json({ error: 'answers required' });
  }

  const getQ = db.prepare('SELECT id, correct_answer FROM questions WHERE id = ?');
  const insertAnswer = db.prepare(
    `INSERT INTO practice_answers
       (session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  );

  const grade = db.transaction((list) => {
    const results = [];
    let correct = 0;

    for (const a of list) {
      const q = getQ.get(Number(a?.question_id));
      if (!q) continue;
      const userAnswer = String(a?.user_answer ?? '');
      const timeSpent = Math.max(0, Math.round(Number(a?.time_spent_sec) || 0));
      const skipped = userAnswer === '';
      const isCorrect = !skipped && userAnswer === q.correct_answer;
      if (isCorrect) correct += 1;

      insertAnswer.run(sessionId, q.id, userAnswer, isCorrect ? 1 : 0, timeSpent);

      results.push({
        question_id: q.id,
        user_answer: userAnswer,
        correct_answer: q.correct_answer,
        is_correct: isCorrect,
        skipped,
        time_spent_sec: timeSpent,
      });
    }

    db.prepare(
      `UPDATE practice_sessions
       SET total = ?, correct = ?, duration_sec = ?, ended_at = datetime('now')
       WHERE id = ?`,
    ).run(results.length, correct, Math.max(0, Number(duration_sec) || 0), sessionId);

    return { results, correct };
  });

  const { results, correct } = grade(answers);
  res.json({
    total: results.length,
    correct,
    accuracy: results.length ? Math.round((correct / results.length) * 100) : 0,
    duration_sec: Math.max(0, Number(duration_sec) || 0),
    results,
  });
});

// ───────────────────────────────────────────────────────────────
// GET /api/practice/sessions/:id/report
//   交卷后的逐题对答案 / 事后复盘 / 喂给 Hermes 的数据源
//   → { session, items: [{ ...题目, user_answer, is_correct, draft_url }] }
// ───────────────────────────────────────────────────────────────
router.get('/sessions/:id/report', (req, res) => {
  const sessionId = Number(req.params.id);
  const session = db.prepare('SELECT * FROM practice_sessions WHERE id = ?').get(sessionId);
  if (!session) return res.status(404).json({ error: 'session not found' });

  // 同一场里一道题只会有一条作答记录；万一有重复取最后一条
  const rows = db
    .prepare(
      `SELECT
         pa.question_id, pa.user_answer, pa.is_correct, pa.time_spent_sec, pa.answered_at,
         q.content, q.options, q.question_type, q.sub_category, q.category,
         q.correct_answer, q.explanation, q.stem_images, q.explanation_images,
         pd.question_id AS has_draft
       FROM practice_answers pa
       JOIN questions q ON q.id = pa.question_id
       LEFT JOIN practice_drafts pd
         ON pd.session_id = pa.session_id AND pd.question_id = pa.question_id
       WHERE pa.session_id = ?
         AND pa.id = (
           SELECT MAX(p2.id) FROM practice_answers p2
           WHERE p2.session_id = pa.session_id AND p2.question_id = pa.question_id
         )
       ORDER BY pa.id ASC`,
    )
    .all(sessionId);

  const items = rows.map((r) => ({
    question_id: r.question_id,
    content: r.content,
    options: parseOptions(r.options),
    stem_images: parseOptions(r.stem_images),
    explanation_images: parseOptions(r.explanation_images),
    question_type: r.question_type,
    category: r.category,
    sub_category: r.sub_category,
    correct_answer: r.correct_answer,
    explanation: r.explanation,
    user_answer: r.user_answer,
    is_correct: !!r.is_correct,
    skipped: r.user_answer === '',
    time_spent_sec: r.time_spent_sec,
    draft_url: r.has_draft ? draftUrl(sessionId, r.question_id) : null,
  }));

  res.json({ session, items });
});

// ───────────────────────────────────────────────────────────────
// PUT /api/practice/sessions/:id/drafts/:questionId
//   body: { data: 'data:image/png;base64,...' }
//   草稿纸合成图（题目 + 圈划 + 演算）落盘，同一题重复写就覆盖
// ───────────────────────────────────────────────────────────────
router.put('/sessions/:id/drafts/:questionId', (req, res) => {
  const sessionId = Number(req.params.id);
  const questionId = Number(req.params.questionId);

  const session = db.prepare('SELECT id FROM practice_sessions WHERE id = ?').get(sessionId);
  if (!session) return res.status(404).json({ error: 'session not found' });
  const q = db.prepare('SELECT id FROM questions WHERE id = ?').get(questionId);
  if (!q) return res.status(404).json({ error: 'question not found' });

  let { data, mime } = req.body || {};
  if (!data || typeof data !== 'string') return res.status(400).json({ error: 'data required' });

  const m = data.match(/^data:([^;]+);base64,(.+)$/s);
  if (m) { mime = mime || m[1]; data = m[2]; }
  mime = String(mime || 'image/png').toLowerCase();
  if (mime !== 'image/png' && mime !== 'image/jpeg' && mime !== 'image/webp') {
    return res.status(400).json({ error: `不支持的草稿图类型: ${mime}` });
  }

  let buf;
  try { buf = Buffer.from(data, 'base64'); } catch { return res.status(400).json({ error: 'base64 解码失败' }); }
  if (!buf.length) return res.status(400).json({ error: '草稿图为空' });
  if (buf.length > DRAFT_MAX_BYTES) return res.status(400).json({ error: '草稿图过大' });

  if (mime === 'image/png') buf = shrinkPng(buf);

  const ext = mime === 'image/jpeg' ? '.jpg' : mime === 'image/webp' ? '.webp' : '.png';
  const filename = `${crypto.randomUUID()}${ext}`;
  fs.writeFileSync(path.join(draftDir, filename), buf);

  const prev = db
    .prepare('SELECT filename FROM practice_drafts WHERE session_id = ? AND question_id = ?')
    .get(sessionId, questionId);

  db.prepare(
    `INSERT INTO practice_drafts (session_id, question_id, filename, mime, bytes, updated_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))
     ON CONFLICT(session_id, question_id) DO UPDATE
       SET filename = excluded.filename,
           mime = excluded.mime,
           bytes = excluded.bytes,
           updated_at = datetime('now')`,
  ).run(sessionId, questionId, filename, mime, buf.length);

  if (prev?.filename) safeUnlinkDraft(prev.filename);

  res.json({ ok: true, url: draftUrl(sessionId, questionId), bytes: buf.length });
});

// ───────────────────────────────────────────────────────────────
// GET /api/practice/sessions/:id/drafts/:questionId/file
//   直接出图（<img src> 走 ?token=）
// ───────────────────────────────────────────────────────────────
router.get('/sessions/:id/drafts/:questionId/file', (req, res) => {
  const row = db
    .prepare('SELECT * FROM practice_drafts WHERE session_id = ? AND question_id = ?')
    .get(Number(req.params.id), Number(req.params.questionId));
  if (!row) return res.status(404).json({ error: 'not found' });
  if (row.filename.includes('..') || row.filename.includes('/') || row.filename.includes('\\')) {
    return res.status(400).json({ error: 'invalid filename' });
  }

  const full = path.join(draftDir, row.filename);
  if (!fs.existsSync(full)) return res.status(404).json({ error: 'file missing' });

  res.setHeader('Content-Type', row.mime || 'image/png');
  // 文件名是 UUID，内容不变；改草稿会写新文件名，所以可以长缓存
  res.setHeader('Cache-Control', 'private, max-age=31536000, immutable');
  res.sendFile(full);
});

// ───────────────────────────────────────────────────────────────
// GET /api/practice/sessions/:id/drafts/:questionId/base64
//   给 Hermes 用：图片要以 base64 走 image.attach_bytes，
//   浏览器拿 <img> 再转 canvas 会多一道 CORS/污染的坑，直接让后端给 data URL
// ───────────────────────────────────────────────────────────────
router.get('/sessions/:id/drafts/:questionId/base64', (req, res) => {
  const row = db
    .prepare('SELECT * FROM practice_drafts WHERE session_id = ? AND question_id = ?')
    .get(Number(req.params.id), Number(req.params.questionId));
  if (!row) return res.status(404).json({ error: 'not found' });
  if (row.filename.includes('..') || row.filename.includes('/') || row.filename.includes('\\')) {
    return res.status(400).json({ error: 'invalid filename' });
  }

  const full = path.join(draftDir, row.filename);
  if (!fs.existsSync(full)) return res.status(404).json({ error: 'file missing' });

  const buf = fs.readFileSync(full);
  res.json({
    mime: row.mime || 'image/png',
    data_url: `data:${row.mime || 'image/png'};base64,${buf.toString('base64')}`,
  });
});

export default router;

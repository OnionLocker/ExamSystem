import express, { Router } from 'express';
import crypto from 'node:crypto';
import { execFile, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import db from '../db.js';
import { reconcileDailyPlanBatch } from './dailyPlans.js';
import { mergeSegments, validSegments } from '../../src/studyLog/studyTime.js';
import { normalizeAnswer, judgeOptions } from '../../src/answers.js';

const router = Router();

// 错题连对几次才算掌握、退出错题本
const MISTAKE_CLEAR = 2;

// 空题盯够这么久仍然交白卷，就按错题处理（与 kaodian_profile.BLANK_WEIGHTS 的满权重档一致）
const BLANK_AS_WRONG_SEC = 60;

const parseTags = (raw) => {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((t) => typeof t === 'string' && t.trim()) : [];
  } catch {
    return [];
  }
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const draftDir = process.env.EXAM_DRAFT_DIR
  || path.join(__dirname, '..', '..', 'data', 'draft-images');
const practiceReviewDir = process.env.EXAM_PRACTICE_REVIEW_DIR
  || path.join(__dirname, '..', '..', 'data', 'practice-reviews');
if (!fs.existsSync(draftDir)) fs.mkdirSync(draftDir, { recursive: true });
if (!fs.existsSync(practiceReviewDir)) fs.mkdirSync(practiceReviewDir, { recursive: true });

const projectRoot = path.join(__dirname, '..', '..');
const execFileAsync = promisify(execFile);

const assessmentBaseline = () => JSON.stringify(Object.fromEntries(
  db.prepare('SELECT kaodian,assessment_json FROM kaodian_profile WHERE assessment_json IS NOT NULL').all()
    .map(row => {
      const a = JSON.parse(row.assessment_json);
      const stale = !a.last_evidence_at || Date.now() - Date.parse(a.last_evidence_at) >= 30 * 86400000;
      return [row.kaodian, stale || a.review_due ? 'unassessed' : a.level];
    }),
));

// 提醒和封存复用同一套规则：只统计本场应写的练习证据。
const practiceCoverage = async (sessionId) => {
  const { stdout } = await execFileAsync('python3', [
    path.join(projectRoot, 'scripts', 'kaodian_profile.py'), '--practice-coverage', String(sessionId),
  ], { cwd: projectRoot, env: { ...process.env, EXAM_DB: db.name }, timeout: 10000 });
  return JSON.parse(stdout);
};

// 空题证据交给脚本写：考点别名归一、知识债、熟练度重算都在 Python 那边，
// 这里再实现一遍就是两套口径。异步跑，交卷响应不等它。
const recordBlanksLater = (sessionId) => {
  execFile(
    'python3',
    [path.join(projectRoot, 'scripts', 'kaodian_profile.py'), '--record-blanks', String(sessionId)],
    { cwd: projectRoot, timeout: 30000 },
    (err, stdout, stderr) => {
      if (err) console.error(`[practice] 空题证据写入失败 session=${sessionId}:`, stderr || err.message);
      else if (stdout.trim()) console.log(`[practice] 空题证据 ${stdout.trim()}`);
    },
  );
};

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

const shrinkDraft = (buf) => {
  const r = spawnSync(
    'convert',
    [
      '-[0]',
      '-filter', 'Box',
      '-resize', `${DRAFT_MAX_WIDTH}x>`,
      '+dither', '-colors', String(PALETTE_COLORS),
      '-define', 'png:compression-level=9',
      'png8:-',
    ],
    { input: buf, maxBuffer: DRAFT_MAX_BYTES, timeout: 8000 },
  );
  const out = r.status === 0 ? r.stdout : null;
  // 没装 ImageMagick、或压完反而更大，就照原样存
  return out && out.length && out.length < buf.length ? out : buf;
};

const readDraftUpload = (req, res, next) => {
  if (String(req.headers['content-type'] || '').includes('application/json')) return next();
  express.raw({ type: () => true, limit: DRAFT_MAX_BYTES })(req, res, next);
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
      `INSERT INTO practice_sessions (category, started_at, assessment_baseline)
       VALUES (?, datetime('now'), ?)`,
    )
    .run(cat, assessmentBaseline());
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
      `WITH recent AS MATERIALIZED (
         SELECT * FROM practice_sessions
          WHERE ended_at IS NOT NULL AND total > 0
            ${category ? 'AND category = ?' : ''}
          ORDER BY ended_at DESC LIMIT ?
       )
       SELECT
         s.id, s.category, s.total, s.correct, s.duration_sec, s.started_at, s.ended_at,
         s.profile_reviewed_at,
         s.audit_of_session_id,
         COALESCE(
           (SELECT NULLIF(q.source, '') FROM questions q
             WHERE q.batch_id = s.category LIMIT 1),
           s.category
         ) AS display_title,
         (SELECT q.category FROM questions q
           WHERE q.batch_id = s.category LIMIT 1) AS module,
         (SELECT ar.plan_date FROM ai_daily_batch_runs ar
           WHERE ar.batch_id = s.category
           ORDER BY ar.plan_date DESC, ar.id DESC LIMIT 1) AS daily_plan_date,
         (SELECT COUNT(*) FROM practice_answers pa
           WHERE pa.session_id = s.id AND pa.is_correct = 0)          AS wrong_count,
         (SELECT COUNT(*) FROM practice_drafts pd
           WHERE pd.session_id = s.id)                                AS draft_count
       FROM recent s
       ORDER BY s.ended_at DESC`,
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
  const { duration_sec = 0, answers, timeSegments } = req.body || {};

  const session = db.prepare('SELECT id, started_at, ended_at, category FROM practice_sessions WHERE id = ?').get(sessionId);
  if (!session) return res.status(404).json({ error: 'session not found' });
  if (session.ended_at) return res.status(409).json({ error: '这份卷子已经交过了' });
  if (!Array.isArray(answers) || answers.length === 0) {
    return res.status(400).json({ error: 'answers required' });
  }
  const sessionStart = Date.parse(session.started_at.replace(' ', 'T') + 'Z');
  if (timeSegments !== undefined && (!validSegments(timeSegments)
      || timeSegments.some(([start]) => start < sessionStart - 60000))) {
    return res.status(400).json({ error: 'invalid timeSegments' });
  }
  const timingJson = timeSegments === undefined ? null : JSON.stringify(mergeSegments(timeSegments));

  const getQ = db.prepare(
    'SELECT id, correct_answer, question_type, category, sub_category, tags FROM questions WHERE id = ?',
  );
  const insertAnswer = db.prepare(
    `INSERT INTO practice_answers
       (session_id, question_id, user_answer, is_correct, time_spent_sec, answered_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  );

  // 错题本：答错自动入本，不用手动收集。连对 MISTAKE_CLEAR 次才算掌握 ——
  // 一次蒙对不等于会了，这跟数资那边错题池的清偿规矩是同一套。
  const addMistake = db.prepare(
    `INSERT INTO mistakes (question_id, wrong_count, correct_streak, last_wrong_at, mastered)
     VALUES (?, 1, 0, datetime('now'), 0)
     ON CONFLICT(question_id) DO UPDATE SET
       wrong_count    = wrong_count + 1,
       correct_streak = 0,
       last_wrong_at  = datetime('now'),
       mastered       = 0`,
  );
  const clearMistake = db.prepare(
    `UPDATE mistakes
        SET correct_streak = correct_streak + 1,
            mastered = CASE WHEN correct_streak + 1 >= ${MISTAKE_CLEAR} THEN 1 ELSE 0 END
      WHERE question_id = ? AND mastered = 0`,
  );
  const grade = db.transaction((list) => {
    const results = [];
    let correct = 0;

    for (const a of list) {
      const q = getQ.get(Number(a?.question_id));
      if (!q) continue;
      const userAnswer = normalizeAnswer(a?.user_answer, q.question_type);
      const correctAnswer = normalizeAnswer(q.correct_answer, q.question_type);
      const timeSpent = Math.max(0, Math.round(Number(a?.time_spent_sec) || 0));
      const skipped = userAnswer === '';
      const isCorrect = !skipped && userAnswer === correctAnswer;
      if (isCorrect) correct += 1;

      insertAnswer.run(sessionId, q.id, userAnswer, isCorrect ? 1 : 0, timeSpent);

      // 空题按停留时间区别对待：盯了一分钟以上仍然交白卷，和做错是同一回事，
      // 该进错题本；几秒翻过去才是真的没看，不留痕迹。
      // 考点证据由 recordBlanksLater 统一写，权重同样按停留时间分档。
      if (!skipped) {
        if (isCorrect) clearMistake.run(q.id);
        else addMistake.run(q.id);
      } else if (timeSpent >= BLANK_AS_WRONG_SEC) {
        addMistake.run(q.id);
      }

      results.push({
        question_id: q.id,
        user_answer: userAnswer,
        correct_answer: correctAnswer,
        is_correct: isCorrect,
        skipped,
        time_spent_sec: timeSpent,
      });
    }

    db.prepare(
      `UPDATE practice_sessions
       SET total = ?, correct = ?, duration_sec = ?, timing_segments = ?, ended_at = datetime('now')
       WHERE id = ?`,
    ).run(results.length, correct, Math.max(0, Number(duration_sec) || 0), timingJson, sessionId);

    return { results, correct };
  });

  const { results, correct } = grade(answers);
  recordBlanksLater(sessionId);
  reconcileDailyPlanBatch(session.category);
  res.json({
    total: results.length,
    correct,
    accuracy: results.length ? Math.round((correct / results.length) * 100) : 0,
    duration_sec: Math.max(0, Number(duration_sec) || 0),
    results,
  });
});

// 已完成首次 Hermes 复盘后，按原题顺序创建一次无答案审核场次。
router.post('/sessions/:id/audit', (req, res) => {
  const sourceId = Number(req.params.id);
  const source = db.prepare(
    'SELECT id, category, ended_at, profile_reviewed_at FROM practice_sessions WHERE id = ?',
  ).get(sourceId);
  if (!source) return res.status(404).json({ error: 'session not found' });
  if (!source.ended_at || !source.profile_reviewed_at) {
    return res.status(409).json({ error: '请先完成这套题的 Hermes 复盘' });
  }
  const existing = db.prepare(
    `SELECT id FROM practice_sessions
      WHERE audit_of_session_id = ? AND ended_at IS NULL
      ORDER BY id DESC LIMIT 1`,
  ).get(sourceId);
  if (existing) return res.json({ id: existing.id, existing: true });
  const created = db.prepare(
    `INSERT INTO practice_sessions (category, started_at, audit_of_session_id, assessment_baseline)
     VALUES (?, datetime('now'), ?, ?)`,
  ).run(source.category, sourceId, assessmentBaseline());
  res.status(201).json({ id: created.lastInsertRowid, source_session_id: sourceId });
});

// Hermes 逐题写入带权证据后才允许封存画像；漏记时保持“待复盘”，重开可补齐。
router.post('/sessions/:id/review-complete', async (req, res) => {
  const sessionId = Number(req.params.id);
  const session = db.prepare(
    'SELECT id, ended_at, profile_reviewed_at FROM practice_sessions WHERE id = ?',
  ).get(sessionId);
  if (!session) return res.status(404).json({ error: 'session not found' });
  if (!session.ended_at) return res.status(409).json({ error: '这场练习还没有交卷' });
  if (session.profile_reviewed_at) return res.json({ ok: true, sealed: false, already: true });

  const { total: eligible, covered: recorded, missing } = await practiceCoverage(sessionId);
  if (missing > 0) {
    return res.status(409).json({ ok: false, sealed: false, eligible, recorded });
  }

  const changed = db.prepare(
    `UPDATE practice_sessions SET profile_reviewed_at = datetime('now')
      WHERE id = ? AND profile_reviewed_at IS NULL`,
  ).run(sessionId).changes;
  res.json({ ok: true, sealed: Boolean(changed), already: !changed });
});

// ───────────────────────────────────────────────────────────────
// GET /api/practice/sessions/:id/report
//   交卷后的逐题对答案 / 事后复盘 / 喂给 Hermes 的数据源
//   → { session, items: [{ ...题目, user_answer, is_correct, draft_url }] }
// ───────────────────────────────────────────────────────────────
const getPracticeReport = (sessionId) => {
  const session = db.prepare(`
    SELECT s.*,
           COALESCE(
             (SELECT NULLIF(q.source, '') FROM questions q
               WHERE q.batch_id = s.category LIMIT 1),
             s.category
           ) AS display_title
      FROM practice_sessions s
     WHERE s.id = ?
  `).get(sessionId);
  if (!session) return null;

  // 同一场里一道题只会有一条作答记录；万一有重复取最后一条。
  const rows = db
    .prepare(
      `SELECT
         pa.question_id, pa.user_answer, pa.is_correct, pa.time_spent_sec, pa.answered_at,
         q.content, q.options, q.question_type, q.sub_category, q.category,
         q.external_id,
         q.correct_answer, q.explanation, q.stem_images, q.explanation_images,
         q.tags, q.source_evidence,
         EXISTS(SELECT 1 FROM practice_answers earlier
                 WHERE earlier.question_id=pa.question_id AND earlier.session_id<pa.session_id) AS is_repeat,
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
    external_id: r.external_id,
    content: r.content,
    options: r.question_type === 'judge' ? judgeOptions(parseOptions(r.options)) : parseOptions(r.options),
    stem_images: parseOptions(r.stem_images),
    explanation_images: parseOptions(r.explanation_images),
    question_type: r.question_type,
    category: r.category,
    sub_category: r.sub_category,
    correct_answer: normalizeAnswer(r.correct_answer, r.question_type),
    source_evidence: r.source_evidence ? JSON.parse(r.source_evidence) : null,
    explanation: r.explanation,
    knowledge_points: parseTags(r.tags),
    user_answer: normalizeAnswer(r.user_answer, r.question_type),
    is_correct: !!r.is_correct,
    skipped: r.user_answer === '',
    time_spent_sec: r.time_spent_sec,
    is_repeat: Boolean(r.is_repeat),
    draft_url: r.has_draft ? draftUrl(sessionId, r.question_id) : null,
  }));

  return { session, items };
};

const fmtReviewDuration = (sec) => {
  const total = Math.max(0, Math.floor(Number(sec) || 0));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
};

const practiceReviewMarkdown = ({ session, items }) => {
  const wrong = items.filter((item) => !item.is_correct);
  const times = items.map((item) => Math.max(0, Number(item.time_spent_sec) || 0));
  const avgSec = times.length ? times.reduce((sum, value) => sum + value, 0) / times.length : 0;
  const slowThreshold = Math.max(60, Math.ceil(avgSec * 1.5));
  const focusItems = items.filter((item) =>
    !item.is_correct || item.draft_url || Number(item.time_spent_sec) >= slowThreshold);
  const lines = [
    `# AI 练题复盘：${session.display_title || session.category || '未命名批次'}`,
    '',
    `- 场次：${session.id}`,
    `- 交卷时间：${session.ended_at || '未知'}`,
    `- 成绩：${session.correct}/${session.total}`,
    `- 总用时：${fmtReviewDuration(session.duration_sec)}`,
    `- 错题或空题：${wrong.length}`,
    `- 本场慢题参考线：${fmtReviewDuration(slowThreshold)}（单题均时的 1.5 倍，最低 01:00）`,
    `- 场次类型：${session.audit_of_session_id ? `复盘审核（基于场次 ${session.audit_of_session_id}）` : '首次练习复盘'}`,
    `- 画像：${session.profile_reviewed_at ? `已封存（${session.profile_reviewed_at}），不得新增作答；可用 --assess 补充有依据的过程评估` : '本场 Hermes 复盘后记录作答、逐题 --assess，再封存'}`,
    '- 评估口径：references/mastery-assessment.md；同题重做不计独立样本，独立性和过程不明时如实标 unknown。',
    `- 原题重做的题目id：${items.filter(item => item.is_repeat).map(item => item.question_id).join('、') || '无'}`,
    '',
    '## 逐题概览',
    '',
    '| 题号 | 题目id | 结果 | 用时 | 草稿 | 知识点 |',
    '|---|---|---|---:|---|---|',
  ];

  for (const [index, item] of items.entries()) {
    const result = item.skipped ? '未作答' : item.is_correct ? '正确' : '错误';
    const draft = item.draft_url ? '有' : '无';
    const points = (item.knowledge_points || []).join('、').replace(/\|/g, '\\|') || '未标注';
    lines.push(`| ${index + 1} | ${item.question_id} | ${result} | ${fmtReviewDuration(item.time_spent_sec)} | ${draft} | ${points} |`);
  }

  lines.push('', '## 复盘重点');
  if (focusItems.length === 0) {
    lines.push('', '本场没有错题、草稿异常或明显慢题。正确且快速的题无需逐题展开。');
    return lines.join('\n');
  }

  for (const item of focusItems) {
    const no = items.indexOf(item) + 1;
    const subtitle = item.sub_category ? ` · ${item.sub_category}` : '';
    const result = item.skipped ? '未作答' : item.is_correct ? '正确' : '错误';
    const reasons = [
      !item.is_correct ? '答案需复盘' : null,
      item.draft_url ? '有草稿，需检查思路和书写' : null,
      Number(item.time_spent_sec) >= slowThreshold ? '用时偏长，需检查方法选择和步骤压缩' : null,
    ].filter(Boolean).join('；');
    lines.push('', `### 第 ${no} 题${subtitle}`, '', String(item.content || ''));
    for (const option of item.options || []) {
      lines.push(`- ${option.key}. ${String(option.text || '').replace(/\n/g, ' ')}`);
    }
    lines.push(
      '',
      `- 题目id：${item.question_id}`,
      `- 作答结果：${result}`,
      `- 我的作答：${item.user_answer || '未作答'}`,
      `- 正确答案：${item.correct_answer || '未知'}`,
      `- 本题用时：${fmtReviewDuration(item.time_spent_sec)}`,
      `- 入选原因：${reasons}`,
    );
    if (item.knowledge_points?.length) {
      lines.push(`- 知识点：${item.knowledge_points.join('、')}`);
    }
    if (item.draft_url) lines.push('- 草稿：本题留有草稿纸，随复盘上下文提供');
    if (item.explanation) lines.push('', '#### 解析', '', String(item.explanation));
    if (item.source_evidence) {
      lines.push('', '#### 命题依据', '', `资料截止日：${item.source_evidence.as_of}；政策更新不倒改本场历史判分。`);
      for (const source of item.source_evidence.sources || []) lines.push(`- ${source.title}（${source.published_at}）：${source.url}`);
      lines.push(`- 原文证据标识：${(item.source_evidence.claim_ids || []).join('、')}`);
      for (const check of item.source_evidence.checks || []) {
        lines.push(`- ${check.key}：${check.reason}`);
        for (const cite of check.citations || []) lines.push(`  原文：${cite.quote}`);
      }
    }
  }
  return lines.join('\n');
};

router.get('/sessions/:id/report', (req, res) => {
  const report = getPracticeReport(Number(req.params.id));
  if (!report) return res.status(404).json({ error: 'session not found' });
  res.json(report);
});

router.get('/sessions/:id/md', (req, res) => {
  const sessionId = Number(req.params.id);
  const report = getPracticeReport(sessionId);
  if (!report) return res.status(404).json({ error: 'session not found' });
  if (!report.session.ended_at) return res.status(409).json({ error: '这场练习还没有交卷' });

  const markdown = practiceReviewMarkdown(report);
  const title = `AI 练题复盘：${report.session.display_title || report.session.category || '未命名批次'}`;
  const safe = String(report.session.display_title || report.session.category || '未命名批次')
    .replace(/[\\/:*?"<>|]/g, '_')
    .slice(0, 80);
  const name = `${sessionId}-${safe}.md`;
  const file = path.join(practiceReviewDir, name);
  fs.writeFileSync(file, markdown, 'utf8');

  res.json({
    path: file,
    name,
    title,
    markdown,
    ...(req.query.include === 'report' ? { report } : {}),
    summary: {
      total: report.session.total,
      correct: report.session.correct,
      wrong: report.items.filter((item) => !item.is_correct).length,
      duration_sec: report.session.duration_sec,
    },
  });
});

// ───────────────────────────────────────────────────────────────
// PUT /api/practice/sessions/:id/drafts/:questionId
//   body: { data: 'data:image/png;base64,...' }
//   草稿纸合成图（题目 + 圈划 + 演算）落盘，同一题重复写就覆盖
// ───────────────────────────────────────────────────────────────
router.put('/sessions/:id/drafts/:questionId', readDraftUpload, (req, res) => {
  const sessionId = Number(req.params.id);
  const questionId = Number(req.params.questionId);

  const session = db.prepare('SELECT id FROM practice_sessions WHERE id = ?').get(sessionId);
  if (!session) return res.status(404).json({ error: 'session not found' });
  const q = db.prepare('SELECT id FROM questions WHERE id = ?').get(questionId);
  if (!q) return res.status(404).json({ error: 'question not found' });

  let mime = 'image/png';
  let buf;
  if (Buffer.isBuffer(req.body)) {
    mime = String(req.headers['content-type'] || 'image/jpeg').split(';')[0].trim().toLowerCase();
    buf = req.body;
  } else {
    let { data, mime: bodyMime } = req.body || {};
    if (!data || typeof data !== 'string') return res.status(400).json({ error: 'data required' });
    const m = data.match(/^data:([^;]+);base64,(.+)$/s);
    if (m) { bodyMime = bodyMime || m[1]; data = m[2]; }
    mime = String(bodyMime || 'image/png').toLowerCase();
    try { buf = Buffer.from(data, 'base64'); } catch { return res.status(400).json({ error: 'base64 解码失败' }); }
  }

  if (mime !== 'image/png' && mime !== 'image/jpeg' && mime !== 'image/webp') {
    return res.status(400).json({ error: `不支持的草稿图类型: ${mime}` });
  }
  if (!buf?.length) return res.status(400).json({ error: '草稿图为空' });
  if (buf.length > DRAFT_MAX_BYTES) return res.status(400).json({ error: '草稿图过大' });

  const shrunk = shrinkDraft(buf);
  if (shrunk !== buf) {
    buf = shrunk;
    mime = 'image/png';
  }

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

// ───────────────────────────────────────────────────────────────
// GET /api/practice/heat
//   → { '2026-08-03': { entries: [{ type, module, count, correct, timeSegments }] } }
//   打卡热力图中的服务端学习记录。
//
//   为什么由服务端现算，而不是交卷时往学习日志里写一条：
//   ① 练习记录本来就在库里，历史场次能直接算出来，不需要回填脚本；
//   ② 按历史作答区分首次和重做；
//   ③ 学习日志是个整体 PUT 的 JSON 数组，服务端和前端同时往里写，
//      晚写的一方会把对方的条目整个覆盖掉。
//
//   所有已完成场次保留，首次作答和重做分别统计。只有计时区间参与热力，
//   历史累计秒数缺少暂停区间时只展示原记录，不能反推起止时间。
// ───────────────────────────────────────────────────────────────
router.get('/heat', (_req, res) => {
  // ended_at 存的是 UTC，热力图按东八区分日，跨零点的场次要先挪过来
  const rows = db
    .prepare(
      `SELECT
         s.id,
         s.category,
         s.duration_sec,
         s.timing_segments,
         s.profile_reviewed_at,
         s.total,
         date(s.ended_at, '+8 hours')                          AS day,
         strftime('%s', s.ended_at)                            AS ts,
         (SELECT q.source FROM questions q
           WHERE q.batch_id = s.category LIMIT 1)              AS source,
         (SELECT COUNT(*) FROM practice_answers pa
           WHERE pa.session_id = s.id AND pa.user_answer != '') AS answered,
         (SELECT COUNT(*) FROM practice_answers pa
           WHERE pa.session_id = s.id AND pa.is_correct = 1)    AS correct,
         (SELECT COUNT(DISTINCT pa.question_id) FROM practice_answers pa
           WHERE pa.session_id = s.id AND pa.user_answer != ''
             AND NOT EXISTS (
               SELECT 1 FROM practice_answers old
               JOIN practice_sessions earlier ON earlier.id = old.session_id
               WHERE old.question_id = pa.question_id AND old.user_answer != ''
                 AND earlier.ended_at IS NOT NULL
                 AND (earlier.ended_at < s.ended_at OR (earlier.ended_at = s.ended_at AND earlier.id < s.id))
             )) AS first_count
       FROM practice_sessions s
       WHERE s.ended_at IS NOT NULL
       ORDER BY s.ended_at ASC`,
    )
    .all();

  const out = {};
  for (const r of rows) {
    if (!r.answered && !r.duration_sec) continue;
    let timeSegments = [];
    try { timeSegments = JSON.parse(r.timing_segments || '[]'); } catch { /* legacy */ }
    if (!validSegments(timeSegments)) timeSegments = [];
    if (!out[r.day]) out[r.day] = { entries: [] };
    out[r.day].entries.push({
      id: `practice-${r.id}`,
      type: 'aiquiz',
      ts: Number(r.ts) * 1000,
      module: r.source || r.category,
      count: r.answered,
      correct: r.correct,
      firstCount: r.first_count,
      repeatCount: r.answered - r.first_count,
      timeSegments,
      recordedMinutes: Math.round((r.duration_sec || 0) / 6) / 10,
    });
    if (r.profile_reviewed_at) {
      const reviewedAt = Date.parse(r.profile_reviewed_at.replace(' ', 'T') + 'Z');
      if (Number.isFinite(reviewedAt)) {
        const reviewDay = new Date(reviewedAt + 8 * 3600000).toISOString().slice(0, 10);
        if (!out[reviewDay]) out[reviewDay] = { entries: [] };
        out[reviewDay].entries.push({ id: `practice-review-${r.id}`, type: 'review', ts: reviewedAt,
          module: 'AI练题复盘', count: r.total, timeSegments: [] });
      }
    }
  }

  // 视频长度不是复盘时长；保留录屏活动，但不据此增加学习时间。
  const reviews = db
    .prepare(
      `SELECT id, title, kind, exam_date, duration_sec,
              strftime('%s', updated_at) AS ts
         FROM exam_analyses
        WHERE status = 'done' AND exam_date IS NOT NULL`,
    )
    .all();
  for (const r of reviews) {
    const minutes = Math.round((r.duration_sec || 0) / 60);
    if (minutes <= 0) continue;
    if (!out[r.exam_date]) out[r.exam_date] = { entries: [] };
    out[r.exam_date].entries.push({
      id: `exam-recording-${r.id}`,
      type: r.kind === 'taoti' ? 'setReview' : 'examReview',
      ts: Number(r.ts) * 1000,
      module: r.title,
      videoMinutes: minutes,
      timeSegments: [],
    });
  }

  res.json(out);
});

// ───────────────────────────────────────────────────────────────
// POST /api/quiz/lite
//   快速出题：指定模块和考点标签，生成一套小题
// ───────────────────────────────────────────────────────────────
router.post('/quiz/lite', async (req, res) => {
  const { module, tag, difficulty = 'mid', sources, as_of, question_type } = req.body || {};
  const grounded = ['政治理论', '常识判断'].includes(module);
  if (typeof module !== 'string' || !module.trim()
      || (tag !== undefined && (typeof tag !== 'string' || !tag.trim())) || (!tag && !grounded)) {
    return res.status(400).json({ error: '须指定模块；非政治/常识模块还须指定考点 tag' });
  }

  const quizCount = Number(req.body.count ?? (module === '政治理论' && !tag ? 10 : 5));
  if (!Number.isInteger(quizCount) || quizCount < 1 || quizCount > 15 || !['easy', 'mid', 'hard'].includes(difficulty)) {
    return res.status(400).json({ error: 'count 须为 1–15，difficulty 须为 easy/mid/hard' });
  }
  if ((sources !== undefined && (!grounded || !Array.isArray(sources) || !sources.length || sources.length > 8
      || sources.some(id => typeof id !== 'string' || !/^[a-z0-9][a-z0-9_-]{1,79}$/.test(id))))
      || (as_of !== undefined && (!grounded || typeof as_of !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(as_of)
        || !Number.isFinite(Date.parse(as_of)) || new Date(as_of).toISOString().slice(0, 10) !== as_of))
      || (question_type !== undefined && (!['single', 'judge', 'multi'].includes(question_type)
        || (module !== '政治理论' && question_type !== 'single')))) {
    return res.status(400).json({ error: '资料、截止日期或题型参数无效；判断/多选仅适用于政治理论' });
  }
  const category = `hermes-lite-${crypto.randomUUID()}`;

  try {
    // 调用 quiz_lite.py 生成题目
    await execFileAsync(
      'python3',
      [
        path.join(projectRoot, 'scripts', 'quiz_lite.py'),
        '--module', String(module),
        ...(tag ? ['--tag', tag] : []),
        '--count', String(quizCount),
        '--difficulty', difficulty,
        '--batch-id', category,
        '--db', db.name,
        ...(sources ? ['--sources', sources.join(',')] : []),
        ...(as_of ? ['--as-of', as_of] : []),
        ...(question_type ? ['--question-type', question_type] : [])
      ],
      {
        cwd: projectRoot,
        timeout: 30 * 60 * 1000,
        maxBuffer: 4 * 1024 * 1024,
        encoding: 'utf8'
      }
    );

    const imported = db.prepare('SELECT COUNT(*) AS n FROM questions WHERE batch_id = ?').get(category).n;
    if (imported !== quizCount) {
      throw new Error(`出题数量不一致: ${imported}/${quizCount}`);
    }

    // 创建练习场次
    const session = db
      .prepare(
        `INSERT INTO practice_sessions (category, started_at, assessment_baseline)
         VALUES (?, datetime('now'), ?)`
      )
      .run(category, assessmentBaseline());

    res.json({
      sessionId: session.lastInsertRowid,
      category,
      count: quizCount
    });
  } catch (error) {
    console.error('[quiz/lite] 出题异常:', error);
    res.status(500).json({ error: '出题失败' });
  }
});

// ───────────────────────────────────────────────────────────────
// GET /api/practice/sessions/:id/coverage
//   检查该场次的画像覆盖率，用于交卷后提示复盘
// ───────────────────────────────────────────────────────────────
router.get('/sessions/:id/coverage', async (req, res) => {
  const sessionId = Number(req.params.id);
  const session = db.prepare('SELECT id, total, ended_at FROM practice_sessions WHERE id = ?').get(sessionId);

  if (!session) return res.status(404).json({ error: 'session not found' });
  if (!session.ended_at) return res.status(400).json({ error: 'session not ended yet' });

  res.json(await practiceCoverage(sessionId));
});

export default router;

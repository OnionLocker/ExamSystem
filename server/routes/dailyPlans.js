import { Router } from 'express';
import db from '../db.js';

const router = Router();
const MAX_DAILY_COUNT = 120;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export const east8Today = () =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());

const validDate = (value) => {
  const date = String(value || east8Today());
  const parsed = new Date(`${date}T00:00:00Z`);
  if (!DATE_RE.test(date) || Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== date) {
    throw new Error('date must be YYYY-MM-DD');
  }
  return date;
};

const parseItems = (raw) => {
  try {
    const value = JSON.parse(raw || '[]');
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
};

const itemKey = (item, index = 0) =>
  String(item?.batch_id || item?.id || `${item?.module || ''}|${item?.target || ''}|${index}`);

const itemStatus = (done, count) =>
  done >= count ? 'done' : done > 0 ? 'partial' : 'pending';

const normalizeGroup = (raw, index) => {
  const count = Math.max(0, Math.min(MAX_DAILY_COUNT, Math.trunc(Number(raw?.count) || 0)));
  const done = Math.max(0, Math.min(count, Math.trunc(Number(raw?.done) || 0)));
  return {
    ...(raw && typeof raw === 'object' ? raw : {}),
    id: String(raw?.id || raw?.group_id || `group-${index + 1}`),
    count,
    done,
    status: itemStatus(done, count),
  };
};

export const normalizeDailyItems = (items) => {
  if (!Array.isArray(items)) throw new Error('items must be an array');
  let total = 0;
  const normalized = items.map((raw, index) => {
    if (!raw || typeof raw !== 'object') throw new Error(`items[${index + 1}] must be an object`);
    const groups = Array.isArray(raw.groups)
      ? raw.groups.map(normalizeGroup)
      : [];
    const fallbackCount = groups.reduce((sum, group) => sum + group.count, 0);
    const count = Math.trunc(Number(raw.count ?? fallbackCount) || 0);
    if (count < 1 || count > MAX_DAILY_COUNT) {
      throw new Error(`items[${index + 1}].count must be 1~${MAX_DAILY_COUNT}`);
    }
    total += count;
    const groupedDone = groups.reduce((sum, group) => sum + group.done, 0);
    const done = Math.max(0, Math.min(count, Math.trunc(Number(raw.done ?? groupedDone) || 0)));
    return {
      ...raw,
      id: String(raw.id || `item-${index + 1}`),
      module: String(raw.module || '').trim(),
      target: raw.target == null ? null : String(raw.target).trim() || null,
      task_type: String(raw.task_type || (groups.length ? 'quant_groups' : 'ai_practice')),
      groups,
      count,
      done,
      status: itemStatus(done, count),
      batch_id: raw.batch_id == null ? null : String(raw.batch_id).trim() || null,
      route: raw.route == null ? null : String(raw.route),
      reason: raw.reason == null ? null : String(raw.reason),
    };
  });
  if (total > MAX_DAILY_COUNT) {
    throw new Error(`daily total cannot exceed ${MAX_DAILY_COUNT}; got ${total}`);
  }
  return normalized;
};

const mergeProgress = (incoming, previous) => incoming.map((item, index) => {
  const old = previous.find((candidate, oldIndex) =>
    itemKey(candidate, oldIndex) === itemKey(item, index));
  if (!old) return item;
  const oldGroups = Array.isArray(old.groups) ? old.groups : [];
  const groups = item.groups.map((group, groupIndex) => {
    const oldGroup = oldGroups.find((candidate, oldIndex) =>
      itemKey(candidate, oldIndex) === itemKey(group, groupIndex));
    if (!oldGroup) return group;
    const done = Math.min(group.count, Math.max(group.done, Number(oldGroup.done) || 0));
    return {
      ...group,
      completed_question_ids: [
        ...new Set([
          ...(Array.isArray(oldGroup.completed_question_ids) ? oldGroup.completed_question_ids : []),
          ...(Array.isArray(group.completed_question_ids) ? group.completed_question_ids : []),
        ].map(String)),
      ],
      done,
      status: itemStatus(done, group.count),
    };
  });
  const done = Math.min(item.count, Math.max(item.done, Number(old.done) || 0));
  return { ...item, groups, done, status: itemStatus(done, item.count) };
});

export const getDailyPlan = (planDate) => {
  const date = validDate(planDate);
  const row = db.prepare('SELECT * FROM daily_plans WHERE plan_date = ?').get(date);
  return row ? { ...row, items: parseItems(row.items) } : null;
};

export const getDailyRuns = (planDate) => {
  const date = validDate(planDate);
  db.prepare(`
    UPDATE ai_daily_batch_runs
       SET status = 'imported',
           error = NULL,
           generated_at = COALESCE(generated_at, datetime('now')),
           imported_at = COALESCE(imported_at, datetime('now')),
           updated_at = datetime('now')
     WHERE plan_date = ?
       AND status IN ('scheduled', 'running', 'generating', 'generated', 'failed')
       AND batch_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM questions q WHERE q.batch_id = ai_daily_batch_runs.batch_id)
  `).run(date);
  return db.prepare(
    `SELECT id, plan_date, module, batch_id, status, error, planned_count, source,
            generated_at, imported_at, created_at, updated_at
       FROM ai_daily_batch_runs
      WHERE plan_date = ?
      ORDER BY id`,
  ).all(date);
};

const syncRuns = (date, items, source) => {
  const countQuestions = db.prepare(
    'SELECT COUNT(*) AS count FROM questions WHERE batch_id = ?',
  );
  const upsert = db.prepare(`
    INSERT INTO ai_daily_batch_runs
      (plan_date, module, batch_id, status, planned_count, source, generated_at, imported_at)
    VALUES (@plan_date, @module, @batch_id, @status, @planned_count, @source,
            CASE WHEN @imported = 1 THEN datetime('now') END,
            CASE WHEN @imported = 1 THEN datetime('now') END)
    ON CONFLICT(plan_date, module) DO UPDATE SET
      batch_id = COALESCE(excluded.batch_id, ai_daily_batch_runs.batch_id),
      planned_count = excluded.planned_count,
      source = excluded.source,
      status = CASE
        WHEN ai_daily_batch_runs.status IN ('failed', 'deleted') AND excluded.batch_id = ai_daily_batch_runs.batch_id
          THEN ai_daily_batch_runs.status
        ELSE excluded.status
      END,
      generated_at = COALESCE(ai_daily_batch_runs.generated_at, excluded.generated_at),
      imported_at = COALESCE(ai_daily_batch_runs.imported_at, excluded.imported_at),
      updated_at = datetime('now')
  `);
  for (const item of items) {
    if (!item.batch_id) continue;
    const imported = countQuestions.get(item.batch_id).count > 0;
    const status = item.done >= item.count ? 'completed' : imported ? 'imported' : 'scheduled';
    upsert.run({
      plan_date: date,
      module: item.module,
      batch_id: item.batch_id,
      status,
      planned_count: item.count,
      source,
      imported: imported ? 1 : 0,
    });
  }
};

export const saveDailyPlan = ({
  planDate,
  items,
  source = 'hermes',
  snapshotAt = null,
  preserveProgress = true,
}) => {
  const date = validDate(planDate);
  const old = getDailyPlan(date);
  let normalized = normalizeDailyItems(items);
  if (preserveProgress && old) normalized = mergeProgress(normalized, old.items);
  const save = db.transaction(() => {
    db.prepare(`
      INSERT INTO daily_plans(plan_date, items, source, snapshot_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(plan_date) DO UPDATE SET
        items = excluded.items,
        source = excluded.source,
        snapshot_at = excluded.snapshot_at,
        updated_at = datetime('now')
    `).run(date, JSON.stringify(normalized), String(source || 'hermes'), snapshotAt);
    syncRuns(date, normalized, String(source || 'hermes'));
  });
  save();
  return getDailyPlan(date);
};

const reconcilePlan = (date, onlyBatchId = null) => {
  const plan = getDailyPlan(date);
  if (!plan) return null;
  const batchProgress = db.prepare(`
    SELECT COUNT(DISTINCT q.id) AS available,
           COUNT(DISTINCT CASE WHEN pa.user_answer != '' THEN q.id END) AS done
      FROM questions q
      LEFT JOIN practice_answers pa ON pa.question_id = q.id
     WHERE q.batch_id = ?
  `);
  const aliases = new Map(
    db.prepare('SELECT alias, canonical FROM kaodian_aliases').all()
      .map((row) => [row.alias, row.canonical]),
  );
  const dailyAnswers = db.prepare(`
    SELECT q.category, q.tags
      FROM practice_answers pa
      JOIN questions q ON q.id = pa.question_id
     WHERE pa.user_answer != '' AND date(pa.answered_at, '+8 hours') = ?
  `).all(date).map((row) => {
    let tags = [];
    try { tags = JSON.parse(row.tags || '[]'); } catch { tags = []; }
    const target = tags[0] ? aliases.get(tags[0]) || tags[0] : null;
    return { module: row.category, target };
  });

  const items = plan.items.map((item) => {
    if (onlyBatchId && item.batch_id !== onlyBatchId) return item;
    let measured = 0;
    if (item.batch_id) {
      measured = batchProgress.get(item.batch_id).done;
    } else if (!item.groups?.length) {
      measured = dailyAnswers.filter((answer) =>
        item.target ? answer.target === item.target : answer.module === item.module).length;
    }
    const done = Math.min(item.count, Math.max(Number(item.done) || 0, measured));
    return { ...item, done, status: itemStatus(done, item.count) };
  });
  return saveDailyPlan({
    planDate: date,
    items,
    source: plan.source,
    snapshotAt: plan.snapshot_at,
  });
};

export const reconcileDailyPlanBatch = (batchId) => {
  if (!batchId) return null;
  const run = db.prepare(
    'SELECT plan_date FROM ai_daily_batch_runs WHERE batch_id = ? ORDER BY plan_date DESC LIMIT 1',
  ).get(String(batchId));
  const date = run?.plan_date || east8Today();
  const plan = reconcilePlan(date, String(batchId));
  if (!plan) return null;
  const item = plan.items.find((candidate) => candidate.batch_id === String(batchId));
  if (item?.done >= item?.count) {
    db.prepare(`
      UPDATE ai_daily_batch_runs
         SET status = 'completed', updated_at = datetime('now')
       WHERE batch_id = ?
    `).run(String(batchId));
  }
  return plan;
};

router.get('/today', (req, res) => {
  try {
    const date = validDate(req.query.date);
    res.json({ date, plan: getDailyPlan(date), runs: getDailyRuns(date) });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

router.post('/reconcile', (req, res) => {
  try {
    const date = validDate(req.body?.date);
    const batchId = req.body?.batch_id ? String(req.body.batch_id) : null;
    const plan = reconcilePlan(date, batchId);
    res.json({ date, plan, runs: getDailyRuns(date) });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

router.post('/progress', (req, res) => {
  try {
    const date = validDate(req.body?.date);
    const plan = getDailyPlan(date);
    if (!plan) return res.status(404).json({ error: 'daily plan not found' });
    const itemId = String(req.body?.item_id || '');
    const groupId = String(req.body?.group_id || '');
    const item = plan.items.find((candidate) =>
      (itemId && String(candidate.id) === itemId)
      || (!itemId && req.body?.module && candidate.module === String(req.body.module)));
    if (!item) return res.status(404).json({ error: 'plan item not found' });
    const group = (item.groups || []).find((candidate) => String(candidate.id) === groupId);
    if (!group) return res.status(404).json({ error: 'group not found' });

    let done = Number(group.done) || 0;
    const questionId = req.body?.question_id == null ? null : String(req.body.question_id);
    if (questionId) {
      const completed = new Set((group.completed_question_ids || []).map(String));
      if (!completed.has(questionId)) {
        completed.add(questionId);
        done += 1;
      }
      group.completed_question_ids = [...completed];
      if (Array.isArray(group.questions)) {
        group.questions = group.questions.map((question) => {
          const id = String(question?.id ?? question?.question_id ?? '');
          return id === questionId ? { ...question, done: 1, status: 'done' } : question;
        });
      }
    } else if (req.body?.done != null) {
      done = Number(req.body.done);
    } else {
      done += Number(req.body?.increment ?? 1);
    }
    group.done = Math.max(0, Math.min(group.count, Math.trunc(done || 0)));
    group.status = itemStatus(group.done, group.count);
    item.done = Math.min(
      item.count,
      item.groups.reduce((sum, candidate) => sum + (Number(candidate.done) || 0), 0),
    );
    item.status = itemStatus(item.done, item.count);
    const saved = saveDailyPlan({
      planDate: date,
      items: plan.items,
      source: plan.source,
      snapshotAt: plan.snapshot_at,
    });
    res.json({ date, plan: saved, runs: getDailyRuns(date) });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

export default router;

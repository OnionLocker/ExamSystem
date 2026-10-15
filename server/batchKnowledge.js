// 考点预热：一套题考了哪些三级知识点（知识点页那一层，比如“平均数问题”）。
// 每日复习卷另带凌晨选点时记下的原因（daily_review_plans）。只读，跟题组来源无关。
import { topicOf } from './knowledgeContent.js';

const primaryTag = (raw) => {
  try {
    const tags = JSON.parse(raw || '[]');
    return String((Array.isArray(tags) ? tags : [tags]).find((tag) => String(tag || '').trim()) || '').trim();
  } catch {
    return '';
  }
};

const aliasMap = (db) => new Map(
  db.prepare('SELECT alias, canonical FROM kaodian_aliases').all().map((row) => [row.alias, row.canonical]),
);

// 题目主标签 → 三级知识点；历史短标签先按画像别名归一
const topicFor = (tag, aliases) => topicOf(tag) || topicOf(aliases.get(tag));

const dailyPlan = (db, batchId) => {
  const row = db.prepare('SELECT plan_json FROM daily_review_plans WHERE batch_id = ?').get(batchId);
  try {
    return row ? JSON.parse(row.plan_json) : null;
  } catch {
    return null;
  }
};

// 题组列表用：batch_id → 考到几个三级知识点
export function knowledgeCounts(db) {
  const aliases = aliasMap(db);
  const topicByTags = new Map();
  const seen = new Map();
  const rows = db.prepare("SELECT batch_id, tags FROM questions WHERE batch_id IS NOT NULL AND batch_id != ''").iterate();
  for (const { batch_id: batchId, tags } of rows) {
    if (!topicByTags.has(tags)) topicByTags.set(tags, topicFor(primaryTag(tags), aliases)?.tag || null);
    const tag = topicByTags.get(tags);
    if (!tag) continue;
    if (!seen.has(batchId)) seen.set(batchId, new Set());
    seen.get(batchId).add(tag);
  }
  return new Map([...seen].map(([batchId, tags]) => [batchId, tags.size]));
}

// 浮框用：每个知识点几题；每日复习卷按选点时的优先顺序排，并带上原因
export function batchKnowledge(db, batchId) {
  const rows = db.prepare('SELECT tags FROM questions WHERE batch_id = ? ORDER BY id').all(batchId);
  if (!rows.length) return null;
  const aliases = aliasMap(db);
  const points = new Map();
  for (const { tags } of rows) {
    const topic = topicFor(primaryTag(tags), aliases);
    if (!topic) continue;
    const point = points.get(topic.tag) || { tag: topic.tag, title: topic.title, count: 0, reason: '' };
    point.count += 1;
    points.set(topic.tag, point);
  }
  const plan = dailyPlan(db, batchId);
  const order = new Map((plan?.points || []).map((item, index) => [item.tag, index]));
  for (const item of plan?.points || []) {
    if (points.has(item.tag)) points.get(item.tag).reason = item.reason || '';
  }
  const rank = (point) => order.get(point.tag) ?? Number.MAX_SAFE_INTEGER;
  return {
    batch_id: batchId,
    total: rows.length,
    points: [...points.values()].sort((a, b) => rank(a) - rank(b) || b.count - a.count),
    plan: plan ? { plan_date: plan.plan_date, module: plan.module } : null,
  };
}

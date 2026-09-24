import Database from 'better-sqlite3';
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import tree from '../src/knowledge/fenbiTree.json' with { type: 'json' };
import { XINGCE } from '../src/knowledge/canon.js';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const cards = new Map(XINGCE.modules.flatMap(m => m.types || []).map(c => [c.id, c]));
export const topics = tree.modules.flatMap(m => m.children.flatMap(g => g.children.map(l => ({
  tag: `${m.name}-${g.name}-${l.name}`, title: l.name, moduleId: m.id, cards: l.cards || [],
}))));
const fail = (message, status = 400) => { throw Object.assign(new Error(message), { status }); };
const text = (value, name, max) => {
  if (typeof value !== 'string' || !value.trim() || value.length > max) fail(`${name}须为非空文本，最多 ${max} 字符`);
  return value.trim();
};
export function cardMarkdown(c) {
  return [c.how, ...[['解题步骤', c.steps], ['要记住', c.know], ['易错提醒', c.ban], ['来源', c.anchors]]
    .filter(([, a]) => a?.length).map(([h, a]) => `## ${h}\n\n${a.map(x => `- ${x}`).join('\n\n')}`),
  c.next && `> 下次动作：${c.next}`, c.mine && `## 我的笔记\n\n${c.mine}`].filter(Boolean).join('\n\n');
}
export function initialTopic(tag) {
  const topic = topics.find(t => t.tag === tag);
  if (!topic) fail('请选择已有知识点的完整三级标签', 404);
  if (tag === '数量关系-数学运算-概率问题') {
    return JSON.parse(readFileSync(resolve(ROOT, 'hermes-skills/gd-gongkao-coach/references/knowledge-content/probability.json'), 'utf8'));
  }
  return { tag, revision: 0, nodes: [
    { id: 'overview', parentId: null, title: topic.title, order: 0, summary: '先选考法，再看步骤、公式和易错点。', markdown: '', aliases: [tag], archived: false },
    ...topic.cards.map(id => cards.get(id)).filter(Boolean).map((c, order) => ({
      id: c.id, parentId: 'overview', title: c.name.replace(/^\d+\s*/, ''), order,
      summary: c.how || '', markdown: cardMarkdown(c), aliases: [], archived: false,
    })),
  ] };
}
export function visibleNodes(doc) {
  const byId = new Map(doc.nodes.map(n => [n.id, n]));
  return doc.nodes.filter(n => {
    for (let p = n; p; p = byId.get(p.parentId)) if (p.archived) return false;
    return true;
  });
}
export function nodeTag(tag, node) { return node.id === 'overview' ? tag : `${tag}-@${node.id}`; }
function labelPath(doc, node) {
  const names = [];
  for (let n = node; n && n.parentId; n = doc.nodes.find(p => p.id === n.parentId)) names.unshift(n.title);
  return [doc.tag, ...names].join('-');
}

// Separate content database: this module never opens the learner's exam.db.
export function openKnowledgeStore(filename = resolve(ROOT, 'data/knowledge-content.db')) {
  if (filename !== ':memory:') mkdirSync(dirname(filename), { recursive: true });
  const db = new Database(filename);
  db.pragma('journal_mode = WAL');
  db.pragma('busy_timeout = 5000');
  db.exec(`CREATE TABLE IF NOT EXISTS topics (tag TEXT PRIMARY KEY, document TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS history (tag TEXT NOT NULL, revision INTEGER NOT NULL, document TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY(tag, revision));`);
  const get = (tag) => {
    const row = db.prepare('SELECT document FROM topics WHERE tag = ?').get(tag);
    return row ? JSON.parse(row.document) : initialTopic(tag);
  };
  const index = () => topics.map(t => {
    const doc = get(t.tag);
    return { tag: t.tag, moduleId: t.moduleId, revision: doc.revision,
      nodes: visibleNodes(doc).map(({ id, parentId, title, order, aliases }) => ({ id, parentId, title, order, aliases })) };
  });
  const mutate = db.transaction((tag, input) => {
    if (!input || typeof input !== 'object' || Array.isArray(input)) fail('请求必须是对象');
    const { revision, op, id, ...fields } = input;
    const allowed = ['parentId', 'title', 'summary', 'markdown', 'order'];
    if (Object.keys(fields).some(k => !allowed.includes(k))) fail('只允许修改标题、父节点、排序、摘要和 Markdown');
    const doc = get(tag);
    if (!Number.isInteger(revision) || revision !== doc.revision) fail('内容已更新，请重新读取后再修改，勿覆盖他人的更新', 409);
    if (!['create', 'update', 'archive', 'restore'].includes(op)) fail('操作须为 create / update / archive / restore');
    if (typeof id !== 'string' || !/^[a-z][a-z0-9-]{0,79}$/.test(id)) fail('id 须为稳定的英文小写字母、数字、连字符');
    let node = doc.nodes.find(n => n.id === id);
    if (op === 'create') {
      if (node) fail('节点 ID 已存在', 409);
      if (doc.nodes.length >= 250) fail('单个知识点最多 250 个内容节点');
      node = { id, parentId: fields.parentId, title: '', order: 0, summary: '', markdown: '', aliases: [], archived: false };
    } else if (!node) fail('找不到指定节点', 404);
    if (['archive', 'restore'].includes(op) && Object.keys(fields).length) fail('停用或恢复操作不可夹带内容修改');
    if (id === 'overview' && (op === 'archive' || 'parentId' in fields)) fail('总览不可删除或移动');
    if (op === 'update' && !visibleNodes(doc).some(n => n.id === id)) fail('请先恢复停用节点及其父节点');
    // Keep old display paths, so renaming/moving never breaks existing links.
    for (const n of doc.nodes) n.aliases = [...new Set([...n.aliases, labelPath(doc, n)])];
    if ('title' in fields) fields.title = text(fields.title, '标题', 100);
    if ('summary' in fields && (typeof fields.summary !== 'string' || fields.summary.length > 500)) fail('摘要最多 500 字符');
    if ('markdown' in fields && (typeof fields.markdown !== 'string' || fields.markdown.length > 80000)) fail('Markdown 最多 80000 字符');
    if ('order' in fields && (!Number.isInteger(fields.order) || Math.abs(fields.order) > 10000)) fail('排序须为 -10000 到 10000 的整数');
    if (op === 'create' && !fields.title) fail('新增节点必须提供 title');
    if ('parentId' in fields || op === 'create') {
      const parent = visibleNodes(doc).find(n => n.id === fields.parentId);
      if (!parent) fail('父节点不存在或已停用');
      let depth = 0;
      for (let p = parent; p; p = doc.nodes.find(n => n.id === p.parentId)) {
        if (p.id === id) fail('不能把节点移动到自身或子节点下面');
        depth++;
      }
      if (depth > 5) fail('层级过深，请合并相近讲解');
    }
    const previous = JSON.stringify(get(tag));
    Object.assign(node, fields);
    if (op === 'create') doc.nodes.push(node);
    if (op === 'archive') node.archived = true;
    if (op === 'restore') node.archived = false;
    // Validate descendants too when moving a whole branch.
    for (const n of doc.nodes) {
      let depth = 0;
      for (let p = n; p; p = doc.nodes.find(x => x.id === p.parentId)) if (++depth > 6) fail('移动后层级超过 6 层');
    }
    doc.revision++;
    doc.updatedAt = new Date().toISOString();
    db.prepare('INSERT OR IGNORE INTO history(tag, revision, document) VALUES (?, ?, ?)').run(tag, revision, previous);
    db.prepare('INSERT INTO topics(tag, document) VALUES (?, ?) ON CONFLICT(tag) DO UPDATE SET document=excluded.document').run(tag, JSON.stringify(doc));
    return { ...doc, nodes: visibleNodes(doc), changed: { id, op, linkTag: nodeTag(tag, node), evidenceChanged: false } };
  });
  return { get, index, mutate: (tag, input) => mutate.immediate(tag, input), close: () => db.close() };
}

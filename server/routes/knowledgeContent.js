import { Router } from 'express';
import { readFile } from 'node:fs/promises';
import { basename, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openKnowledgeStore, reportTags, visibleNodes } from '../knowledgeContent.js';
const router = Router();
const store = openKnowledgeStore();
const REVIEW_DIR = fileURLToPath(new URL('../../data/practice-reviews/', import.meta.url));
const CANON_MAX = 6000;
router.get('/', (_req, res) => res.json({ topics: store.index() }));
// 复盘时注入的讲题口径：报告里每个知识点对应的知识点页内容
router.get('/canon/report', async (req, res) => {
  const name = basename(String(req.query.path || ''));
  if (!/\.md$/.test(name)) return res.status(400).json({ error: 'invalid report' });
  try {
    const entries = reportTags(await readFile(resolve(REVIEW_DIR, name), 'utf8'));
    const merged = new Map();
    for (const { tag, questions } of entries) {
      const hit = store.canon(tag);
      if (!hit?.markdown) continue;
      const cur = merged.get(hit.tag);
      if (cur) cur.questions.push(...questions);
      else merged.set(hit.tag, { ...hit, questions: [...questions], markdown: hit.markdown.slice(0, CANON_MAX) });
    }
    res.set('Cache-Control', 'no-store').json({ items: [...merged.values()] });
  } catch (err) {
    res.status(err.code === 'ENOENT' ? 404 : 500).json({ error: err.message });
  }
});
router.get('/:tag', (req, res) => {
  try {
    const doc = store.get(req.params.tag);
    res.set('Cache-Control', 'no-store').json({ ...doc, nodes: visibleNodes(doc) });
  } catch (err) { res.status(err.status || 500).json({ error: err.message }); }
});
router.patch('/:tag', (req, res) => {
  try { res.json(store.mutate(req.params.tag, req.body)); }
  catch (err) { res.status(err.status || 500).json({ error: err.message }); }
});
export default router;

import { Router } from 'express';
import { openKnowledgeStore, visibleNodes } from '../knowledgeContent.js';
const router = Router();
const store = openKnowledgeStore();
router.get('/', (_req, res) => res.json({ topics: store.index() }));
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

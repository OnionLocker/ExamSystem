import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Router } from 'express';

const router = Router();
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const SCRIPT = path.join(ROOT, 'scripts', 'learner_snapshot.py');
let cached = null;
let cachedAt = 0;

router.get('/snapshot', (req, res) => {
  const now = Date.now();
  if (!cached || now - cachedAt > 30000) {
    const result = spawnSync('python3', [SCRIPT], {
      cwd: ROOT,
      encoding: 'utf8',
      timeout: 10000,
      maxBuffer: 5 * 1024 * 1024,
      env: { ...process.env, EXAM_DB: process.env.EXAM_DB || '' },
    });
    if (result.status !== 0) {
      return res.status(500).json({
        error: result.stderr?.trim() || '生成学员快照失败',
      });
    }
    try {
      cached = JSON.parse(result.stdout);
      cachedAt = now;
    } catch {
      return res.status(500).json({ error: '学员快照格式错误' });
    }
  }
  if (req.query.compact === '1') {
    return res.json({
      as_of: cached.as_of,
      summary: cached.summary,
      compact: cached.compact,
    });
  }
  return res.json(cached);
});

export default router;

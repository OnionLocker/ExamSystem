import { Router } from 'express';
import db from '../db.js';

const router = Router();

// 单 key 长度上限(JSON 字符串),防止滥用
const MAX_VAL_BYTES = 2 * 1024 * 1024; // 2 MB / key

// GET /api/kv  → 全量拉取 { key: jsonValue, ... }
// 新设备登录后第一次调用,把所有数据拉下来
router.get('/', (_req, res) => {
  const rows = db.prepare('SELECT k, v FROM user_kv').all();
  const out = {};
  for (const r of rows) {
    try {
      out[r.k] = JSON.parse(r.v);
    } catch {
      // 兼容历史脏数据
      out[r.k] = r.v;
    }
  }
  res.json(out);
});

// GET /api/kv/:key  → 读单条
router.get('/:key', (req, res) => {
  const row = db.prepare('SELECT v FROM user_kv WHERE k = ?').get(req.params.key);
  if (!row) return res.status(404).json({ error: 'not found' });
  try {
    res.json({ value: JSON.parse(row.v) });
  } catch {
    res.json({ value: row.v });
  }
});

// PUT /api/kv/:key  body: { value: any }
// 服务器为权威源:整段覆盖
router.put('/:key', (req, res) => {
  const { value } = req.body || {};
  if (value === undefined) return res.status(400).json({ error: 'value 必填' });
  let str;
  try {
    str = JSON.stringify(value);
  } catch (e) {
    return res.status(400).json({ error: 'value 不是合法 JSON' });
  }
  if (Buffer.byteLength(str, 'utf8') > MAX_VAL_BYTES) {
    return res.status(413).json({ error: `value 超过 ${MAX_VAL_BYTES} 字节` });
  }
  db.prepare(`
    INSERT INTO user_kv (k, v, updated_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(k) DO UPDATE SET
      v = excluded.v,
      updated_at = CURRENT_TIMESTAMP
  `).run(req.params.key, str);
  res.json({ ok: true });
});

// DELETE /api/kv/:key  → 删除单条(用于"清空")
router.delete('/:key', (req, res) => {
  db.prepare('DELETE FROM user_kv WHERE k = ?').run(req.params.key);
  res.json({ ok: true });
});

// POST /api/kv/batch  body: { items: { k1: v1, k2: v2 } }
// 用于前端首次"把本地全推上去"的迁移场景
router.post('/batch', (req, res) => {
  const { items } = req.body || {};
  if (!items || typeof items !== 'object') {
    return res.status(400).json({ error: 'items 必填' });
  }
  const stmt = db.prepare(`
    INSERT INTO user_kv (k, v, updated_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(k) DO UPDATE SET
      v = excluded.v,
      updated_at = CURRENT_TIMESTAMP
  `);
  let written = 0;
  const tx = db.transaction(() => {
    for (const [k, v] of Object.entries(items)) {
      const str = JSON.stringify(v);
      if (Buffer.byteLength(str, 'utf8') > MAX_VAL_BYTES) continue;
      stmt.run(k, str);
      written += 1;
    }
  });
  tx();
  res.json({ ok: true, written });
});

export default router;

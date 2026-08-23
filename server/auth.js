import { Router } from 'express';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PASSWORD = process.env.EXAM_PASSWORD || '';
if (!PASSWORD) {
  console.warn('[auth] ⚠️  未配置 EXAM_PASSWORD，系统将无法登录');
}

const TOKEN_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'data', 'auth-tokens.json');
const loadTokens = () => {
  try {
    const arr = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf8'));
    return new Set(Array.isArray(arr) ? arr.filter((x) => typeof x === 'string' && x) : []);
  } catch {
    return new Set();
  }
};
const tokens = loadTokens();
const saveTokens = () => {
  try {
    fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true });
    fs.writeFileSync(TOKEN_FILE, JSON.stringify([...tokens]));
  } catch { /* ignore */ }
};

const constantTimeEq = (a, b) => {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
};

// 中间件：白名单之外的 /api/* 都需要 token
export const authMiddleware = (req, res, next) => {
  const open = req.path === '/health' || req.path.startsWith('/auth/');
  if (open) return next();

  const header = req.headers.authorization || '';
  // 优先取请求头 Bearer；再兜底 URL 查询参数 ?token=
  // （<img src> / 预取无法带自定义头，只能走 query）
  const token = header.startsWith('Bearer ')
    ? header.slice(7)
    : (req.query?.token ? String(req.query.token) : '');
  if (token && tokens.has(token)) return next();
  return res.status(401).json({ error: 'unauthorized' });
};

// 校验裸 token（不经 Express 中间件的场景使用，例如 WebSocket upgrade）
export const isValidToken = (token) => !!(token && tokens.has(token));

export const authRouter = Router();

// POST /api/auth/login  { password }
authRouter.post('/login', (req, res) => {
  const { password } = req.body || {};
  if (!PASSWORD) return res.status(500).json({ error: '服务端未配置密码' });
  if (!password || !constantTimeEq(password, PASSWORD)) {
    return res.status(401).json({ error: '密码错误' });
  }
  const token = crypto.randomBytes(24).toString('hex');
  tokens.add(token);
  saveTokens();
  res.json({ token });
});

// POST /api/auth/logout
authRouter.post('/logout', (req, res) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  if (token) {
    tokens.delete(token);
    saveTokens();
  }
  res.json({ ok: true });
});

// GET /api/auth/check  校验当前 token 是否有效
authRouter.get('/check', (req, res) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  res.json({ authed: !!(token && tokens.has(token)) });
});

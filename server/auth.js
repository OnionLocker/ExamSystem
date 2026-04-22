import { Router } from 'express';
import crypto from 'node:crypto';

const PASSWORD = process.env.EXAM_PASSWORD || '';
if (!PASSWORD) {
  console.warn('[auth] ⚠️  未配置 EXAM_PASSWORD，系统将无法登录');
}

// 内存 token 池（单用户本地场景足够；重启后需重新登录）
const tokens = new Set();

const constantTimeEq = (a, b) => {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
};

// 中间件：白名单֮外的 /api/* 都需Ҫ token
export const authMiddleware = (req, res, next) => {
  const open = req.path === '/health' || req.path.startsWith('/auth/');
  if (open) return next();

  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  if (token && tokens.has(token)) return next();
  return res.status(401).json({ error: 'unauthorized' });
};

export const authRouter = Router();

// POST /api/auth/login  { password }
authRouter.post('/login', (req, res) => {
  const { password } = req.body || {};
  if (!PASSWORD) return res.status(500).json({ error: '服务端δ配置密码' });
  if (!password || !constantTimeEq(password, PASSWORD)) {
    return res.status(401).json({ error: '密码错误' });
  }
  const token = crypto.randomBytes(24).toString('hex');
  tokens.add(token);
  res.json({ token });
});

// POST /api/auth/logout
authRouter.post('/logout', (req, res) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  if (token) tokens.delete(token);
  res.json({ ok: true });
});

// GET /api/auth/check  У验当ǰ token 是否有Ч
authRouter.get('/check', (req, res) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  res.json({ authed: !!(token && tokens.has(token)) });
});

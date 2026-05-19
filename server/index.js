import express from 'express';
import cors from 'cors';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { authRouter, authMiddleware } from './auth.js';
import reviewsRouter from './routes/reviews.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();

app.use(cors());
app.use(express.json({ limit: '2mb' }));


// 所有 /api/* 先过鉴Ȩ（内部会放行 /health 与 /auth/*）
app.use('/api', authMiddleware);

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'exam-system-backend', time: new Date().toISOString() });
});

app.use('/api/auth',      authRouter);
app.use('/api/reviews',   reviewsRouter);

app.use((err, _req, res, _next) => {
  console.error('[api error]', err);
  res.status(500).json({ error: err.message || 'internal error' });
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, '0.0.0.0', () => {
  console.log(`[api] listening on http://localhost:${PORT}`);
});

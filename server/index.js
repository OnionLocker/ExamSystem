import express from 'express';
import cors from 'cors';

import { authRouter, authMiddleware } from './auth.js';
import questionsRouter from './routes/questions.js';
import practiceRouter from './routes/practice.js';
import mistakesRouter from './routes/mistakes.js';
import reviewsRouter from './routes/reviews.js';
import statsRouter from './routes/stats.js';

const app = express();

app.use(cors());
app.use(express.json({ limit: '2mb' }));

// 所有 /api/* 先过鉴Ȩ（内部会放行 /health 与 /auth/*）
app.use('/api', authMiddleware);

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'exam-system-backend', time: new Date().toISOString() });
});

app.use('/api/auth',      authRouter);
app.use('/api/questions', questionsRouter);
app.use('/api/practice',  practiceRouter);
app.use('/api/mistakes',  mistakesRouter);
app.use('/api/reviews',   reviewsRouter);
app.use('/api/stats',     statsRouter);

app.use((err, _req, res, _next) => {
  console.error('[api error]', err);
  res.status(500).json({ error: err.message || 'internal error' });
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, '0.0.0.0', () => {
  console.log(`[api] listening on http://localhost:${PORT}`);
});

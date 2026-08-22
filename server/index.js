import express from 'express';
import cors from 'cors';
import http from 'node:http';

import { authRouter, authMiddleware } from './auth.js';
import kvRouter from './routes/kv.js';
import uploadsRouter from './routes/uploads.js';
import reviewModulesRouter from './routes/reviewModules.js';
import questionsRouter from './routes/questions.js';
import practiceRouter from './routes/practice.js';
import quotaRouter from './routes/quota.js';
import examAnalysesRouter from './routes/examAnalyses.js';
import { resumePending } from './examWorker.js';
import { attachHermesWs } from './routes/hermesChat.js';

const app = express();

app.use(cors());
// 复习图片以 base64 走 JSON 上传，单图上限 15MB → base64 约 20MB，故放宽到 25mb
app.use(express.json({ limit: '25mb' }));


// 所有 /api/* 先过鉴权（内部会放行 /health 与 /auth/*）
app.use('/api', authMiddleware);

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'exam-system-backend', time: new Date().toISOString() });
});

app.use('/api/auth',           authRouter);
app.use('/api/kv',             kvRouter);
app.use('/api/uploads',        uploadsRouter);
app.use('/api/review-modules', reviewModulesRouter);
app.use('/api/questions',      questionsRouter);
app.use('/api/practice',       practiceRouter);
app.use('/api/quota',          quotaRouter);
app.use('/api/exam-analyses',   examAnalysesRouter);

app.use((err, _req, res, _next) => {
  console.error('[api error]', err);
  res.status(500).json({ error: err.message || 'internal error' });
});

const PORT = process.env.PORT || 3001;

// 显式创建 http server：Hermes 对话页需要挂 WebSocket upgrade
const server = http.createServer(app);
attachHermesWs(server);

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[api] listening on http://localhost:${PORT}`);
  // 进程重启前没跑完的复盘任务接着跑
  resumePending();
});

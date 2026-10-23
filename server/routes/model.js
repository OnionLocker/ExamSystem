// 模型路由 API：ExamSystem「模型」页签的后端。
//
//   GET  /api/model              → { active, profiles:[...], hermes_config }（不含密钥值）
//   POST /api/model/select       → { profile, model, applied }  写入 router.json + 同步 Hermes config.yaml
//
// 事实来源：~/.hermes/model-router.json（Python 脚本也读同一个文件）。
// 切换模型时同时把 active 写进 config.yaml（经 scripts/model_router.py --apply-config，
// 用 key_env 引用 ~/.hermes/.env，不在 config.yaml 落明文密钥）。

import { Router } from 'express';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const runFile = promisify(execFile);
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

const ROUTER_PATH = path.join(os.homedir(), '.hermes', 'model-router.json');
const HERMES_ENV = path.join(os.homedir(), '.hermes', '.env');

async function readRouter() {
  try {
    return JSON.parse(await fs.readFile(ROUTER_PATH, 'utf8'));
  } catch {
    return { active: '', profiles: {} };
  }
}

async function envHasValue(name) {
  if (!name) return false;
  if (process.env[name]?.trim()) return true;
  try {
    const text = await fs.readFile(HERMES_ENV, 'utf8');
    for (const line of text.split('\n')) {
      if (line.trim().startsWith(`${name}=`)) {
        const v = line.split('=').slice(1).join('=').trim().replace(/^["']|["']$/g, '');
        if (v) return true;
      }
    }
  } catch { /* 没有 .env 就认为 key 未配置 */ }
  return false;
}

export const modelRouter = Router();

modelRouter.get('/', async (_req, res, next) => {
  try {
    const router = await readRouter();
    const active = router.active || '';
    const profiles = Object.entries(router.profiles || {}).map(([id, p]) => ({
      id,
      label: p.label || id,
      model: p.model || '',
      base_url: p.base_url || '',
      api_key_env: p.api_key_env || '',
      api_mode: p.api_mode || 'chat_completions',
      supports_vision: Boolean(p.supports_vision ?? true),
      supports_audio: Boolean(p.supports_audio ?? false),
      supports_image_output: Boolean(p.supports_image_output ?? p.supports_vision ?? true),
      context_length: p.context_length ?? null,
      key_set: false, // 逐个填充
    }));
    for (const p of profiles) p.key_set = await envHasValue(p.api_key_env);
    res.json({ active, profiles, router_path: ROUTER_PATH });
  } catch (err) { next(err); }
});

modelRouter.post('/select', async (req, res, next) => {
  try {
    const profile = String(req.body?.profile || '');
    const router = await readRouter();
    const prof = (router.profiles || {})[profile];
    if (!prof) return res.status(400).json({ error: `未知模型 profile: ${profile}` });

    // 1) 写 router.json（事实来源）
    router.active = profile;
    router.updated_at = new Date().toISOString();
    await fs.writeFile(ROUTER_PATH, JSON.stringify(router, null, 2) + '\n', 'utf8');

    // 2) 同步 Hermes config.yaml（key_env 指针，不落明文密钥）
    await runFile('python3', [path.join(PROJECT_ROOT, 'scripts', 'model_router.py'), '--apply-config', profile], {
      cwd: PROJECT_ROOT,
      timeout: 20000,
    });

    res.json({
      ok: true,
      profile,
      model: prof.model,
      label: prof.label,
      supports_vision: Boolean(prof.supports_vision ?? true),
      supports_audio: Boolean(prof.supports_audio ?? false),
      note: '新会话立即使用该模型；进行中的会话保持原模型直到重新开始。',
    });
  } catch (err) { next(err); }
});

export default modelRouter;

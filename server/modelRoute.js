// Node 侧共享的模型路由读取：与 scripts/model_router.py 读同一个文件。
// 事实来源：~/.hermes/model-router.json
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const MODEL_ROUTER_PATH = path.join(os.homedir(), '.hermes', 'model-router.json');
export const HERMES_ENV_PATH = path.join(os.homedir(), '.hermes', '.env');

export function readModelRouter() {
  try {
    const data = JSON.parse(fs.readFileSync(MODEL_ROUTER_PATH, 'utf8'));
    const profiles = data.profiles || {};
    const active = data.active || '';
    const prof = profiles[active] || {};
    return { active, profiles, profile: prof };
  } catch {
    // router.json 缺失时回退到 cliproxy（与脚本侧默认一致）
    return {
      active: 'gemini-cliproxy',
      profiles: {},
      profile: { model: 'gemini-3.8-flash-high', base_url: 'http://127.0.0.1:8889/v1', api_key_env: 'CLIPROXY_API_KEY' },
    };
  }
}

export function activeModel() {
  return readModelRouter().profile.model || 'gemini-3.8-flash-high';
}

export function activeBaseUrl() {
  const p = readModelRouter().profile;
  return (p.base_url || 'http://127.0.0.1:8889/v1').replace(/\/+$/, '');
}

export function activeApiKeyEnv() {
  return readModelRouter().profile.api_key_env || 'CLIPROXY_API_KEY';
}

export function readEnvValue(name) {
  if (process.env[name]?.trim()) return process.env[name].trim();
  try {
    const text = fs.readFileSync(HERMES_ENV_PATH, 'utf8');
    for (const line of text.split('\n')) {
      if (line.trim().startsWith(`${name}=`)) {
        return line.split('=').slice(1).join('=').trim().replace(/^["']|["']$/g, '');
      }
    }
  } catch { /* ignore */ }
  return '';
}

export function activeApiKey() {
  const key = readEnvValue(activeApiKeyEnv());
  if (!key) throw new Error(`模型路由：${activeApiKeyEnv()} 未配置（检查 ~/.hermes/.env）`);
  return key;
}

export function supportsVision() {
  const p = readModelRouter().profile;
  return Boolean(p.supports_vision ?? true);
}

export function supportsAudio() {
  const p = readModelRouter().profile;
  return Boolean(p.supports_audio ?? false);
}

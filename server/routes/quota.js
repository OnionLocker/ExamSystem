// ============================================================
// CLIProxy 额度查询
// ------------------------------------------------------------
// 直接读 CLIProxy 的凭据目录，拿 access_token 去问 Google 要额度，
// 不经过 CLIProxy 的管理接口 —— 那个要单独的管理密钥，多一道配置。
//
// 只读 access_token，绝不碰 refresh_token：刷新会触发 Google 轮换，
// 把 CLIProxy 自己存的那份顶掉，得不偿失。token 过期就等它自己刷。
// ============================================================

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import https from 'node:https';
import { Router } from 'express';
import { SocksProxyAgent } from 'socks-proxy-agent';

const router = Router();

const AUTH_DIR = process.env.CLIPROXY_AUTH_DIR || path.join(os.homedir(), '.cli-proxy-api');
const CLIPROXY_CONFIG =
  process.env.CLIPROXY_CONFIG || path.join(os.homedir(), 'CLIProxyAPI', 'config.yaml');

// Antigravity CLI 的固定标识，换了拿不到数据
const UA = 'antigravity/cli/1.0.13 (aidev_client; os_type=darwin; arch=arm64)';
const QUOTA_HOSTS = [
  'daily-cloudcode-pa.googleapis.com',
  'daily-cloudcode-pa.sandbox.googleapis.com',
  'cloudcode-pa.googleapis.com',
];
const QUOTA_PATH = '/v1internal:retrieveUserQuotaSummary';
const TIER_PATH = '/v1internal:loadCodeAssist';

// Google 那边额度变化没那么快，短缓存足够，也免得刷页面就打一次外网
const CACHE_MS = 60_000;
let cache = { at: 0, data: null };

// 代理跟着 CLIProxy 的配置走，避免两处各写一份
const readProxyUrl = () => {
  if (process.env.CLIPROXY_PROXY_URL) return process.env.CLIPROXY_PROXY_URL;
  try {
    const m = fs.readFileSync(CLIPROXY_CONFIG, 'utf8').match(/^\s*proxy-url:\s*["']?([^"'\s#]+)/m);
    return m ? m[1] : '';
  } catch {
    return '';
  }
};

const agentFor = (proxyUrl) => {
  if (!proxyUrl) return undefined;
  // socks5h 是 curl 的写法（域名交给代理解析），Node 这边认 socks5
  return new SocksProxyAgent(proxyUrl.replace(/^socks5h:/, 'socks5:'));
};

const postJson = (host, urlPath, token, body, agent) =>
  new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = https.request(
      {
        host,
        path: urlPath,
        method: 'POST',
        agent,
        timeout: 20_000,
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'User-Agent': UA,
          'Content-Length': Buffer.byteLength(payload),
        },
      },
      (res) => {
        let raw = '';
        res.on('data', (c) => (raw += c));
        res.on('end', () => {
          let parsed = null;
          try {
            parsed = JSON.parse(raw);
          } catch {
            /* 非 JSON 说明是错误页，交给下面按状态码处理 */
          }
          resolve({ status: res.statusCode, body: parsed, raw });
        });
      },
    );
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
    req.end(payload);
  });

const listCredentials = () => {
  let files = [];
  try {
    files = fs.readdirSync(AUTH_DIR).filter((f) => f.endsWith('.json'));
  } catch {
    return [];
  }
  const out = [];
  for (const f of files) {
    try {
      const c = JSON.parse(fs.readFileSync(path.join(AUTH_DIR, f), 'utf8'));
      if (c.type === 'antigravity' && c.access_token) out.push(c);
    } catch {
      /* 单个文件坏了不影响其它账号 */
    }
  }
  return out.sort((a, b) => String(a.email).localeCompare(String(b.email)));
};

// g1-pro-tier → Google AI Pro 这种展示名后端定好，前端只管画
const TIER_LABEL = {
  'free-tier': '免费版',
  'g1-pro-tier': 'Pro',
  'g1-ultra-tier': 'Ultra',
  'g1-ultra-lite-tier': 'Ultra Lite',
};

const fetchOne = async (cred, agent) => {
  const base = {
    email: cred.email,
    project: cred.project_id || null,
    disabled: !!cred.disabled,
    tokenExpiresAt: cred.expired || null,
  };

  if (!cred.project_id) {
    return { ...base, error: '凭据里没有 project_id，需要重新登录一次 Antigravity' };
  }

  let quota = null;
  let lastErr = '';
  for (const host of QUOTA_HOSTS) {
    try {
      const r = await postJson(host, QUOTA_PATH, cred.access_token, { project: cred.project_id }, agent);
      if (r.status === 200 && Array.isArray(r.body?.groups)) {
        quota = r.body;
        break;
      }
      if (r.status === 401) {
        lastErr = 'access_token 已过期，等 CLIProxy 自动刷新后再看';
        break;
      }
      lastErr = `HTTP ${r.status}`;
    } catch (e) {
      lastErr = e.message;
    }
  }
  if (!quota) return { ...base, error: lastErr || '拿不到额度' };

  // 套餐是锦上添花，失败就不显示，不要影响额度主体
  let plan = null;
  try {
    const r = await postJson(
      QUOTA_HOSTS[0],
      TIER_PATH,
      cred.access_token,
      { metadata: { ideType: 'ANTIGRAVITY' } },
      agent,
    );
    if (r.status === 200) {
      const tier = r.body?.paidTier || r.body?.currentTier;
      if (tier) plan = TIER_LABEL[tier.id] || tier.name || tier.id;
    }
  } catch {
    /* ignore */
  }

  const groups = quota.groups.map((g) => ({
    name: g.displayName || '',
    models: (g.description || '').replace(/^Models within this group:\s*/i, ''),
    buckets: (g.buckets || []).map((b) => ({
      id: b.bucketId,
      window: b.window,
      label: b.window === '5h' ? '5 小时' : b.window === 'weekly' ? '本周' : b.displayName,
      remaining: typeof b.remainingFraction === 'number' ? b.remainingFraction : null,
      resetAt: b.resetTime || null,
    })),
  }));

  return { ...base, plan, groups };
};

// GET /api/quota?fresh=1
router.get('/', async (req, res) => {
  const fresh = req.query.fresh === '1';
  if (!fresh && cache.data && Date.now() - cache.at < CACHE_MS) {
    return res.json({ ...cache.data, cached: true });
  }

  const creds = listCredentials();
  if (creds.length === 0) {
    return res.json({ accounts: [], fetchedAt: new Date().toISOString(), note: '没有找到 Antigravity 凭据' });
  }

  const agent = agentFor(readProxyUrl());
  const accounts = await Promise.all(creds.map((c) => fetchOne(c, agent)));
  const data = { accounts, fetchedAt: new Date().toISOString() };
  cache = { at: Date.now(), data };
  res.json({ ...data, cached: false });
});

export default router;

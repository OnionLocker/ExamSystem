// ============================================================
// cloudStorage:跨设备同步的"localStorage 替代"
// ------------------------------------------------------------
// 行为约定:
//   · 服务器为权威源:登录后调 hydrate() 一次,把服务器全量数据
//     盖到本地 localStorage,然后 UI 才允许渲染。
//   · cloudGet(key, fallback) 同步返回(从 localStorage 读),保证现有
//     业务代码不需要改成异步。
//   · cloudSet(key, value) 立刻写本地 + 防抖 1.5s 推到服务器。
//   · cloudRemove(key) 立刻删除本地 + 同步删服务器。
//
// 哪些 key 走云同步:用 SYNCED_KEYS 白名单显式声明,避免无关
// (如 BGM 音量) 的设备偏好也被同步。
// ============================================================

import { api, getToken } from './api.js';

// ---------------- 白名单:这些 key 才上云 ----------------
// 学习数据全部进数据库;BGM/SFX/Mixer/UI 偏好不进
export const SYNCED_KEYS = new Set([
  'study_log_v1',                    // 学习日志
  'numeric_practice_history_v1',     // 数资历史
  'numeric_rank_stats_v1',           // 数资段位
  'exam_calendar_events',            // 重要日子倒计时
  'flashcards_progress_v1',          // 闪卡 SM2 进度
  'numeric_games_number_grid_v1',    // 点数字
  'numeric_games_mental_carry_v1',   // 移位加减
  'numeric_games_digit_span_v1',     // 数字记忆
  'mockexam_state_v1',               // 模考当前状态
  'mockexam_blocks_v2',              // 模考块次设置
  'pomodoro_history_v1',             // 番茄钟完成历史(学习数据,跨设备)
  // 不同步:pomodoro_state_v1 (当前计时进行中,跟设备走)
  //         pomodoro_settings_v1 (工作时长/白噪音偏好,跟设备走)
]);

const isSynced = (key) => SYNCED_KEYS.has(key);

// ---------------- 本地访问(总是同步) ----------------
const localGet = (key, fallback) => {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
};

const localSet = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode, ignore */
  }
};

const localRemove = (key) => {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
};

// ---------------- 防抖推送 ----------------
const PUSH_DEBOUNCE_MS = 1500;
const pendingTimers = new Map(); // key -> timeout id

const scheduleCloudPut = (key, value) => {
  if (!isSynced(key)) return;
  // 未登录时不推送(防止登录页渲染时 useEffect 触发的初始空值被打回 401 warn)
  if (!getToken()) return;
  const old = pendingTimers.get(key);
  if (old) clearTimeout(old);
  const tid = setTimeout(async () => {
    pendingTimers.delete(key);
    try {
      await api(`/api/kv/${encodeURIComponent(key)}`, {
        method: 'PUT',
        body: { value },
      });
    } catch (e) {
      // 服务器不可达不影响本地体验;下次写入或 hydrate 时会重试
      // eslint-disable-next-line no-console
      console.warn('[cloud] push fail', key, e?.message || e);
    }
  }, PUSH_DEBOUNCE_MS);
  pendingTimers.set(key, tid);
};

// 在 hydrate / 退出页前用,立刻把所有 pending 推上去
export const flushCloudPending = async () => {
  const tasks = [];
  for (const [key, tid] of pendingTimers.entries()) {
    clearTimeout(tid);
    pendingTimers.delete(key);
    const value = localGet(key, null);
    if (value != null) {
      tasks.push(
        api(`/api/kv/${encodeURIComponent(key)}`, {
          method: 'PUT',
          body: { value },
        }).catch(() => {}),
      );
    }
  }
  await Promise.all(tasks);
};

// ---------------- 公开 API ----------------
// 同步读:总是从本地拿,保证现有同步业务代码无侵入
export const cloudGet = (key, fallback) => localGet(key, fallback);

// 写:立刻写本地 + 防抖推服务器(白名单 key)
export const cloudSet = (key, value) => {
  localSet(key, value);
  scheduleCloudPut(key, value);
};

// 删:立刻删本地 + 推服务器删除(白名单 key)
export const cloudRemove = (key) => {
  localRemove(key);
  if (!isSynced(key)) return;
  // 取消还在排队的 PUT
  const old = pendingTimers.get(key);
  if (old) {
    clearTimeout(old);
    pendingTimers.delete(key);
  }
  api(`/api/kv/${encodeURIComponent(key)}`, { method: 'DELETE' }).catch(() => {});
};

// ---------------- 启动期同步:服务器 → 本地 ----------------
// 行为:登录后,在 UI 渲染主体之前调用一次。
//   1. GET /api/kv → 拿到服务器全量
//   2. 服务器有数据 → 覆盖本地(服务器为权威源)
//   3. 服务器没数据但本地有 → 把本地全推上去(首次迁移场景)
//   返回 'hydrated' | 'migrated' | 'offline'
export const hydrateCloudStorage = async () => {
  let serverData = null;
  try {
    serverData = await api('/api/kv');
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('[cloud] hydrate offline', e?.message || e);
    return 'offline';
  }

  const serverKeys = Object.keys(serverData || {});

  if (serverKeys.length === 0) {
    // 服务器空,把本地白名单 key 全推上去(首次迁移)
    const items = {};
    for (const key of SYNCED_KEYS) {
      const v = localGet(key, null);
      if (v != null) items[key] = v;
    }
    if (Object.keys(items).length > 0) {
      try {
        await api('/api/kv/batch', { method: 'POST', body: { items } });
        return 'migrated';
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('[cloud] migrate fail', e?.message || e);
        return 'offline';
      }
    }
    return 'hydrated';
  }

  // 服务器有数据 → 覆盖本地
  for (const key of serverKeys) {
    if (!isSynced(key)) continue; // 防御:只接受白名单
    localSet(key, serverData[key]);
  }
  return 'hydrated';
};

// 工具:订阅 storage 变化(用于跨标签页同步,可选)
// 这里暂不做跨标签广播,后续如有需要再补

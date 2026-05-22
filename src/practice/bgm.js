// ============================================================
// 数资模块 BGM 引擎(单轨 + 交叉淡化)
// ------------------------------------------------------------
// 与 SoundMixer.js / Pomodoro 的 SoundEngine 完全独立。
// 使用 Web Audio API 直接 decode mp3 → AudioBufferSource(loop=true),
// 切换轨道时旧轨淡出 + 新轨淡入(同时进行,无静默间隙)。
//
// 资源缺失策略:fetch 404 / decode 失败 → 该轨静默,不影响 UI。
//
// 用户偏好持久化:bgm_prefs_v1 → { enabled, volume }
//
// 暴露 API(单例):
//   playBgm(trackId, opts)   - 切到 trackId(games | training | ranked)
//   stopBgm(opts)            - 淡出停止
//   setVolume(v)             - 调主音量(0~1),立即生效
//   setEnabled(flag)         - 启用/禁用(禁用时 stopBgm)
//   getState()               - 取当前状态(用于 UI)
//   subscribe(fn)            - 订阅状态变化
// ============================================================

const PREFS_KEY = 'bgm_prefs_v1';
const FADE_MS_DEFAULT = 500;

// 三套 BGM 资源(后续若改名/换路径只动这里)
export const BGM_TRACKS = {
  games:    { url: '/sounds/bgm/games.mp3',    label: '小游戏 BGM',  desc: '像素轻快' },
  training: { url: '/sounds/bgm/training.mp3', label: '训练 BGM',    desc: 'lo-fi 沉静' },
  ranked:   { url: '/sounds/bgm/ranked.mp3',   label: '排位 BGM',    desc: 'BOSS 战' },
};

const DEFAULT_PREFS = { enabled: true, volume: 0.4 };

const loadPrefs = () => {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') };
  } catch {
    return { ...DEFAULT_PREFS };
  }
};
const savePrefs = (p) => {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p));
  } catch {
    // ignore
  }
};

class BgmEngine {
  constructor() {
    this.ctx = null;
    this.bufferCache = new Map(); // url -> AudioBuffer | null(失败标记)
    this.activeId = null;          // 当前(预期)正在播的 trackId
    this.activeNodes = null;       // { src, gain }
    this.subscribers = new Set();
    this.prefs = loadPrefs();
  }

  // ---------------- 内部:确保 AudioContext 可用 ----------------
  _ensureCtx() {
    if (!this.ctx) {
      const AC = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext);
      if (!AC) return false;
      this.ctx = new AC();
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
    return true;
  }

  _emit() {
    this.subscribers.forEach((fn) => {
      try { fn(); } catch { /* ignore */ }
    });
  }

  subscribe(fn) {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }

  // ---------------- 内部:加载 buffer(失败缓存为 null) ----------------
  async _loadBuffer(url) {
    if (this.bufferCache.has(url)) return this.bufferCache.get(url);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const arr = await res.arrayBuffer();
      const buf = await this.ctx.decodeAudioData(arr);
      this.bufferCache.set(url, buf);
      return buf;
    } catch (e) {
      console.warn(`[BgmEngine] 加载失败:${url}`, e?.message || e);
      this.bufferCache.set(url, null); // 失败标记,避免反复请求
      return null;
    }
  }

  // ---------------- 内部:淡出旧节点 ----------------
  _fadeOutAndStop(nodes, fadeMs) {
    if (!nodes) return;
    const { src, gain } = nodes;
    const now = this.ctx.currentTime;
    try {
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(gain.gain.value, now);
      gain.gain.linearRampToValueAtTime(0, now + fadeMs / 1000);
    } catch { /* ignore */ }
    setTimeout(() => {
      try { src.stop(); } catch { /* ignore */ }
      try { src.disconnect(); gain.disconnect(); } catch { /* ignore */ }
    }, fadeMs + 80);
  }

  // ---------------- 公共:切换到某轨 ----------------
  // opts: { volume(覆盖一次), fadeMs }
  async playBgm(trackId, opts = {}) {
    if (!BGM_TRACKS[trackId]) {
      console.warn(`[BgmEngine] 未知轨道:${trackId}`);
      return;
    }
    if (!this.prefs.enabled) {
      // 禁用状态下也记录"应该播的"轨道(用户启用时直接接上)
      this.activeId = trackId;
      this._emit();
      return;
    }
    if (!this._ensureCtx()) return;

    const fadeMs = opts.fadeMs ?? FADE_MS_DEFAULT;
    const targetVol = opts.volume ?? this.prefs.volume;

    // 同轨道 → 不重启,只调音量
    if (this.activeId === trackId && this.activeNodes) {
      this.setVolume(targetVol);
      return;
    }

    // 淡出旧轨
    if (this.activeNodes) {
      this._fadeOutAndStop(this.activeNodes, fadeMs);
      this.activeNodes = null;
    }
    this.activeId = trackId;
    this._emit();

    // 加载新 buffer
    const url = BGM_TRACKS[trackId].url;
    const buf = await this._loadBuffer(url);
    // 期间可能被切到别的轨道
    if (this.activeId !== trackId) return;
    if (!buf) {
      // 加载失败:静默,但 activeId 保留(UI 可显示"加载失败")
      this._emit();
      return;
    }

    const ctx = this.ctx;
    const gain = ctx.createGain();
    gain.gain.value = 0;
    gain.connect(ctx.destination);

    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    src.connect(gain);
    src.start();

    const now = ctx.currentTime;
    gain.gain.linearRampToValueAtTime(targetVol, now + fadeMs / 1000);

    this.activeNodes = { src, gain };
    this._emit();
  }

  // ---------------- 公共:停止当前轨 ----------------
  stopBgm(opts = {}) {
    const fadeMs = opts.fadeMs ?? FADE_MS_DEFAULT;
    if (this.activeNodes) {
      this._fadeOutAndStop(this.activeNodes, fadeMs);
      this.activeNodes = null;
    }
    this.activeId = null;
    this._emit();
  }

  // ---------------- 公共:设主音量(0~1) ----------------
  setVolume(v) {
    const vol = Math.max(0, Math.min(1, Number(v) || 0));
    this.prefs.volume = vol;
    savePrefs(this.prefs);
    if (this.activeNodes && this.ctx) {
      const now = this.ctx.currentTime;
      this.activeNodes.gain.gain.cancelScheduledValues(now);
      this.activeNodes.gain.gain.linearRampToValueAtTime(vol, now + 0.1);
    }
    this._emit();
  }

  // ---------------- 公共:启用/禁用 ----------------
  setEnabled(flag) {
    const next = !!flag;
    if (this.prefs.enabled === next) return;
    this.prefs.enabled = next;
    savePrefs(this.prefs);
    if (!next) {
      // 关闭:停掉但保留 activeId,以便重启时接上
      const remembered = this.activeId;
      this.stopBgm();
      this.activeId = remembered;
    } else {
      // 重新启用:如果有记住的轨道,接上
      if (this.activeId) this.playBgm(this.activeId);
    }
    this._emit();
  }

  // ---------------- 公共:状态读取 ----------------
  getState() {
    return {
      enabled: this.prefs.enabled,
      volume: this.prefs.volume,
      activeId: this.activeId,
      // 加载/解码失败:bufferCache 里是 null
      loadFailed: !!(
        this.activeId &&
        this.bufferCache.get(BGM_TRACKS[this.activeId]?.url) === null
      ),
    };
  }
}

// 单例
let _instance = null;
const getEngine = () => {
  if (!_instance && typeof window !== 'undefined') {
    _instance = new BgmEngine();
  }
  return _instance;
};

// ---------------- 顶层简化 API(供组件直接调用) ----------------
export const playBgm = (trackId, opts) => getEngine()?.playBgm(trackId, opts);
export const stopBgm = (opts) => getEngine()?.stopBgm(opts);
export const setBgmVolume = (v) => getEngine()?.setVolume(v);
export const setBgmEnabled = (flag) => getEngine()?.setEnabled(flag);
export const getBgmState = () => getEngine()?.getState() || { ...DEFAULT_PREFS, activeId: null, loadFailed: false };
export const subscribeBgm = (fn) => getEngine()?.subscribe(fn) || (() => {});

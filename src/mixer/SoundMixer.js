// ============================================================
// 声音混音器引擎：多轨独立播放 / 各自 gain 控制
// ============================================================
// 与 SoundEngine（番茄钟里那个单声道场景播放器）独立运行，
// 各自有独立的 AudioContext 和 master，互不干扰。
//
// 接口语义：
//   play(id)            - 开始播 id 这一轨（懒加载 buffer，缓存复用）
//   stop(id)            - 停某一轨（带淡出）
//   setVolume(id, v)    - 调某一轨音量（0~1）
//   stopAll()           - 全停
//   isPlaying(id)       - 该轨是否在播
//   getVolume(id)       - 取该轨当前音量
//   getActiveIds()      - 当前在播的所有 id
//   subscribe(fn)       - 订阅状态变化（UI 同步）
//
// 设计要点：
//   * 每轨结构：{ source, gain, buffer, volume }
//   * 切换状态时通过 subscribers 通知 React 重渲染
//   * mp3 / wav 都走 AudioBufferSourceNode + loop=true，无缝循环
//   * 文件缺失时该轨静音失败，不影响其他轨
// ------------------------------------------------------------

const FADE_IN_MS = 400;
const FADE_OUT_MS = 500;

export class SoundMixer {
  constructor() {
    this.ctx = null;
    this.tracks = new Map();   // id -> { src, gain, volume, isPlaying }
    this.bufferCache = new Map(); // url -> AudioBuffer | null
    this.subscribers = new Set();
  }

  _ensureCtx() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
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
      try {
        fn();
      } catch {
        // ignore
      }
    });
  }

  subscribe(fn) {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }

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
      console.warn(`[SoundMixer] 加载失败：${url}`, e?.message || e);
      this.bufferCache.set(url, null);
      return null;
    }
  }

  /**
   * 开始播放某一轨。如果已经在播，无操作。
   * @param {string} id   声音 id
   * @param {string} url  采样 URL
   * @param {number} volume  0~1，初始音量
   */
  async play(id, url, volume = 0.6) {
    if (!this._ensureCtx()) return;
    if (this.tracks.has(id)) return; // 已在播

    // 占位：先记录一个"加载中"状态，避免重复 play
    const placeholder = { loading: true, volume, isPlaying: false };
    this.tracks.set(id, placeholder);
    this._emit();

    const buf = await this._loadBuffer(url);
    // 期间可能被 stop 了
    const cur = this.tracks.get(id);
    if (cur !== placeholder) return;
    if (!buf) {
      this.tracks.delete(id);
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

    // 淡入到目标音量
    const now = ctx.currentTime;
    gain.gain.linearRampToValueAtTime(volume, now + FADE_IN_MS / 1000);

    this.tracks.set(id, { src, gain, volume, isPlaying: true });
    this._emit();
  }

  /**
   * 停一轨（淡出，自动清理）
   */
  stop(id) {
    const t = this.tracks.get(id);
    if (!t) return;
    // 加载中的轨：直接删
    if (t.loading) {
      this.tracks.delete(id);
      this._emit();
      return;
    }
    const { src, gain } = t;
    this.tracks.delete(id);
    this._emit();

    const now = this.ctx.currentTime;
    gain.gain.cancelScheduledValues(now);
    gain.gain.setValueAtTime(gain.gain.value, now);
    gain.gain.linearRampToValueAtTime(0, now + FADE_OUT_MS / 1000);

    setTimeout(() => {
      try {
        src.stop();
      } catch {
        // ignore
      }
      try {
        src.disconnect();
        gain.disconnect();
      } catch {
        // ignore
      }
    }, FADE_OUT_MS + 100);
  }

  setVolume(id, volume) {
    const t = this.tracks.get(id);
    if (!t) return;
    if (t.loading) {
      // 加载中先记下来，加载完成时会用这个值起淡入
      t.volume = volume;
      this._emit();
      return;
    }
    t.volume = volume;
    const now = this.ctx.currentTime;
    t.gain.gain.cancelScheduledValues(now);
    t.gain.gain.linearRampToValueAtTime(volume, now + 0.1);
    this._emit();
  }

  toggle(id, url, defaultVolume = 0.6) {
    if (this.tracks.has(id)) {
      this.stop(id);
      return false;
    }
    this.play(id, url, defaultVolume);
    return true;
  }

  stopAll() {
    const ids = [...this.tracks.keys()];
    ids.forEach((id) => this.stop(id));
  }

  isPlaying(id) {
    const t = this.tracks.get(id);
    return !!(t && (t.isPlaying || t.loading));
  }

  getVolume(id) {
    const t = this.tracks.get(id);
    return t ? t.volume : 0.6;
  }

  getActiveIds() {
    return [...this.tracks.keys()];
  }

  /**
   * 序列化当前混音状态，用于持久化到 localStorage
   * 格式: { id1: volume1, id2: volume2, ... }
   */
  snapshot() {
    const out = {};
    for (const [id, t] of this.tracks) {
      out[id] = t.volume;
    }
    return out;
  }
}

// 单例（整个 app 共享一个 mixer）
let _instance = null;
export const getMixer = () => {
  if (!_instance && typeof window !== 'undefined') {
    _instance = new SoundMixer();
  }
  return _instance;
};

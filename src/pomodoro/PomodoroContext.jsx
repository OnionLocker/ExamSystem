import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { addEntry as addStudyEntry, scorePomodoro } from '../studyLog/studyLog.js';

// ============================================================
// 番茄钟全局状态（跨页面持续计时、持久化、提醒）
// ============================================================
// 会话阶段：idle(未开始) / work(工作中) / break(休息中) / paused(暂停)
// - 只记录"锚点时间" startedAt 和 phase + durationMs，tick 实时计算 remaining
// - 刷新页面后从 localStorage 恢复，时间继续流动（不会因刷新重置）

const SETTINGS_KEY = 'pomodoro_settings_v1';
const STATE_KEY = 'pomodoro_state_v1';
const HISTORY_KEY = 'pomodoro_history_v1'; // 完成的番茄记录

const DEFAULT_SETTINGS = {
  workMs: 25 * 60 * 1000,
  breakMs: 5 * 60 * 1000,
  longBreakMs: 15 * 60 * 1000,
  roundsBeforeLongBreak: 4, // 每 4 个工作番茄后进入长休
  soundEnabled: true,
  notificationEnabled: true,
  autoStartBreak: true, // 工作结束后自动开始休息
  autoStartWork: false, // 休息结束后自动开始下一个工作
  // 背景音（白噪音）
  bgmEnabled: false,
  bgmType: 'rain', // 'white' | 'pink' | 'brown' | 'rain'
  bgmVolume: 0.4, // 0~1
  bgmAutoStart: true, // 进入工作阶段时自动播
  bgmPlayInBreak: false, // 休息阶段是否也播放
};

const load = (key, fallback) => {
  try {
    const v = localStorage.getItem(key);
    return v ? { ...fallback, ...JSON.parse(v) } : fallback;
  } catch {
    return fallback;
  }
};
const save = (key, v) => {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    // ignore
  }
};
const loadArr = (key) => {
  try {
    return JSON.parse(localStorage.getItem(key) || '[]');
  } catch {
    return [];
  }
};
const saveArr = (key, arr) => {
  try {
    localStorage.setItem(key, JSON.stringify(arr));
  } catch {
    // ignore
  }
};

// 浏览器通知
const notify = (title, body) => {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'granted') {
    try {
      new Notification(title, { body, silent: false });
    } catch {
      // ignore
    }
  }
};

// 内置提示音：WebAudio 生成双音铃
const playBeep = () => {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const play = (freq, start, dur = 0.22) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.connect(g);
      g.connect(ctx.destination);
      o.type = 'sine';
      o.frequency.value = freq;
      g.gain.setValueAtTime(0, ctx.currentTime + start);
      g.gain.linearRampToValueAtTime(0.22, ctx.currentTime + start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + dur);
      o.start(ctx.currentTime + start);
      o.stop(ctx.currentTime + start + dur + 0.05);
    };
    play(880, 0);
    play(1175, 0.26);
    play(1568, 0.5, 0.4);
    setTimeout(() => ctx.close(), 1200);
  } catch {
    // ignore
  }
};

// ============================================================
// 背景白噪音引擎：纯 WebAudio，离线生成
// ============================================================
// 四种类型：
//   white  - 纯白噪音（均匀频谱）
//   pink   - 粉红噪音（低频更强，更柔和）
//   brown  - 棕噪音/红噪音（低频最强，雷雨般低沉）
//   rain   - 模拟雨声：白噪音 + LP 过滤 + 缓慢抖动
// ------------------------------------------------------------
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

class NoiseEngine {
  constructor() {
    this.ctx = null;
    this.master = null; // 总输出 gain
    this.nodes = []; // 需要 stop/disconnect 的活跃节点
    this.timers = []; // setTimeout 句柄（颗粒事件调度）
    this.type = null;
    this.volume = 0.4;
  }

  _ensureCtx() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return false;
      this.ctx = new AudioCtx();
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
    return true;
  }

  // 生成 2 秒无缝循环噪音 buffer
  _makeNoiseBuffer(color = 'white') {
    const seconds = 2;
    const rate = this.ctx.sampleRate;
    const len = seconds * rate;
    const buf = this.ctx.createBuffer(1, len, rate);
    const d = buf.getChannelData(0);
    if (color === 'white') {
      for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    } else if (color === 'pink') {
      let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
      for (let i = 0; i < len; i++) {
        const w = Math.random() * 2 - 1;
        b0 = 0.99886 * b0 + w * 0.0555179;
        b1 = 0.99332 * b1 + w * 0.0750759;
        b2 = 0.96900 * b2 + w * 0.1538520;
        b3 = 0.86650 * b3 + w * 0.3104856;
        b4 = 0.55000 * b4 + w * 0.5329522;
        b5 = -0.7616 * b5 - w * 0.0168980;
        d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11;
        b6 = w * 0.115926;
      }
    } else if (color === 'brown') {
      let last = 0;
      for (let i = 0; i < len; i++) {
        const w = Math.random() * 2 - 1;
        last = (last + 0.02 * w) / 1.02;
        d[i] = last * 3.5;
      }
    }
    return buf;
  }

  // 创建循环噪音源，返回 { src, gain }
  _noiseLayer(color, vol, filterOpts) {
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this._makeNoiseBuffer(color);
    src.loop = true;

    const gain = ctx.createGain();
    gain.gain.value = vol;

    let out = src;
    if (filterOpts) {
      const f = ctx.createBiquadFilter();
      f.type = filterOpts.type || 'lowpass';
      f.frequency.value = filterOpts.freq || 1000;
      f.Q.value = filterOpts.q ?? 0.7;
      out.connect(f);
      out = f;
      this.nodes.push(f);

      // 可选 LFO 调 cutoff
      if (filterOpts.lfoRate) {
        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.type = 'sine';
        lfo.frequency.value = filterOpts.lfoRate;
        lfoGain.gain.value = filterOpts.lfoDepth || 300;
        lfo.connect(lfoGain);
        lfoGain.connect(f.frequency);
        lfo.start();
        this.nodes.push(lfo);
      }
    }
    out.connect(gain);
    gain.connect(this.master);
    src.start();
    this.nodes.push(src);
    this.nodes.push(gain);
    return gain;
  }

  // 颗粒事件（如雨滴、噼啪声、鸟鸣）：周期性生成短促声音
  _scheduleGrain(fn, meanMs) {
    const run = () => {
      if (!this.ctx || this.type === null) return;
      try {
        fn();
      } catch {
        // ignore
      }
      // 随机间隔：均值周围 ±50%
      const jitter = meanMs * (0.5 + Math.random());
      const id = setTimeout(run, jitter);
      this.timers.push(id);
    };
    const id = setTimeout(run, Math.random() * meanMs);
    this.timers.push(id);
  }

  // 单个"脉冲"声源：用带限噪音 + 快速包络模拟敲击/滴答/拍击
  _pulse({ color = 'white', freq = 2000, q = 8, dur = 0.06, gain = 0.3, delay = 0, type = 'bandpass' }) {
    const ctx = this.ctx;
    const t0 = ctx.currentTime + delay;
    const src = ctx.createBufferSource();
    src.buffer = this._makeNoiseBuffer(color);
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = freq;
    filter.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(gain, t0 + 0.003);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(filter);
    filter.connect(g);
    g.connect(this.master);
    src.start(t0);
    src.stop(t0 + dur + 0.02);
  }

  // 正弦音调（鸟叫、虫鸣）
  _tone({ freq, dur = 0.15, gain = 0.08, delay = 0, freqEnd, type = 'sine' }) {
    const ctx = this.ctx;
    const t0 = ctx.currentTime + delay;
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    if (freqEnd) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(1, freqEnd), t0 + dur);
    }
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(gain, t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g);
    g.connect(this.master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  // ================= 预设 =================
  _build(type) {
    switch (type) {
      case 'white':
        // 稍微用 shelf 削一点极高频，避免刺耳
        return this._noiseLayer('white', 0.9, { type: 'lowpass', freq: 8000, q: 0.5 });

      case 'pink':
        // 粉噪 + 非常轻的高频染色
        this._noiseLayer('pink', 0.9);
        return; // 使用默认：不做单一回返，多层已经连接 master

      case 'brown':
        // 棕噪音 + 极慢的低通 LFO 制造呼吸感
        this._noiseLayer('brown', 1.0, {
          type: 'lowpass',
          freq: 700,
          q: 0.7,
          lfoRate: 0.04,
          lfoDepth: 200,
        });
        return;

      case 'rain': {
        // 背景：低通白噪音 + 慢 LFO
        this._noiseLayer('white', 0.55, {
          type: 'lowpass',
          freq: 1400,
          q: 0.5,
          lfoRate: 0.07,
          lfoDepth: 500,
        });
        // 远雷：棕噪音 + 很低的 LP
        this._noiseLayer('brown', 0.35, { type: 'lowpass', freq: 220, q: 0.5 });
        // 雨滴：高频 bandpass 短脉冲
        this._scheduleGrain(() => {
          const freq = 1800 + Math.random() * 3000;
          this._pulse({
            freq,
            q: 14,
            dur: 0.03 + Math.random() * 0.04,
            gain: 0.08 + Math.random() * 0.1,
          });
        }, 55);
        return;
      }

      case 'thunderstorm': {
        // 雷雨：雨声 + 偶尔远雷
        this._noiseLayer('white', 0.5, {
          type: 'lowpass',
          freq: 1200,
          q: 0.5,
          lfoRate: 0.08,
          lfoDepth: 600,
        });
        this._noiseLayer('brown', 0.5, { type: 'lowpass', freq: 180, q: 0.5 });
        this._scheduleGrain(() => {
          this._pulse({
            freq: 2000 + Math.random() * 4000,
            q: 16,
            dur: 0.035,
            gain: 0.12,
          });
        }, 45);
        // 偶尔低频轰鸣（远雷）
        this._scheduleGrain(() => {
          const ctx = this.ctx;
          const t0 = ctx.currentTime;
          const src = ctx.createBufferSource();
          src.buffer = this._makeNoiseBuffer('brown');
          const f = ctx.createBiquadFilter();
          f.type = 'lowpass';
          f.frequency.value = 120;
          f.Q.value = 0.5;
          const g = ctx.createGain();
          g.gain.setValueAtTime(0, t0);
          g.gain.linearRampToValueAtTime(0.8, t0 + 0.4);
          g.gain.exponentialRampToValueAtTime(0.0001, t0 + 3.5);
          src.connect(f);
          f.connect(g);
          g.connect(this.master);
          src.start(t0);
          src.stop(t0 + 4);
        }, 18000);
        return;
      }

      case 'ocean': {
        // 海浪：非常慢 LFO 驱动 LP，呼吸般的起伏
        const ctx = this.ctx;
        const src = ctx.createBufferSource();
        src.buffer = this._makeNoiseBuffer('brown');
        src.loop = true;
        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 600;
        filter.Q.value = 0.6;
        const g = ctx.createGain();
        g.gain.value = 1.0;

        // LFO 慢速呼吸
        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.type = 'sine';
        lfo.frequency.value = 0.08; // ~12s 一个周期
        lfoGain.gain.value = 500;
        lfo.connect(lfoGain);
        lfoGain.connect(filter.frequency);
        lfo.start();

        // LFO 也调 gain 让整体音量起伏
        const volLfo = ctx.createOscillator();
        const volLfoGain = ctx.createGain();
        volLfo.type = 'sine';
        volLfo.frequency.value = 0.08;
        volLfoGain.gain.value = 0.25;
        volLfo.connect(volLfoGain);
        volLfoGain.connect(g.gain);
        volLfo.start();

        src.connect(filter);
        filter.connect(g);
        g.connect(this.master);
        src.start();
        this.nodes.push(src, filter, lfo, volLfo);
        return;
      }

      case 'fire': {
        // 篝火：brown 噪音做底 + 不断的随机噼啪脉冲
        this._noiseLayer('brown', 0.5, { type: 'lowpass', freq: 400, q: 0.6 });
        this._noiseLayer('pink', 0.15, { type: 'highpass', freq: 1200, q: 0.5 });
        // 噼啪声
        this._scheduleGrain(() => {
          const burst = 1 + Math.floor(Math.random() * 3);
          for (let i = 0; i < burst; i++) {
            this._pulse({
              freq: 2500 + Math.random() * 3500,
              q: 20,
              dur: 0.02 + Math.random() * 0.04,
              gain: 0.12 + Math.random() * 0.15,
              delay: i * 0.025 + Math.random() * 0.04,
            });
          }
        }, 420);
        return;
      }

      case 'forest': {
        // 森林：微风 + 偶尔鸟鸣
        this._noiseLayer('pink', 0.3, {
          type: 'lowpass',
          freq: 1600,
          q: 0.4,
          lfoRate: 0.12,
          lfoDepth: 400,
        });
        this._noiseLayer('brown', 0.2, { type: 'lowpass', freq: 300, q: 0.5 });
        // 鸟鸣：频率扫掠的短哨音，间隔较长
        this._scheduleGrain(() => {
          const patterns = [
            () => {
              // 单音哨
              this._tone({
                freq: 2600 + Math.random() * 1200,
                freqEnd: 2800 + Math.random() * 1200,
                dur: 0.12,
                gain: 0.1,
              });
            },
            () => {
              // 双音
              const f = 2400 + Math.random() * 800;
              this._tone({ freq: f, dur: 0.08, gain: 0.08 });
              this._tone({ freq: f * 1.15, dur: 0.08, gain: 0.08, delay: 0.12 });
            },
            () => {
              // 三连音
              const f = 2200 + Math.random() * 800;
              for (let i = 0; i < 3; i++) {
                this._tone({
                  freq: f * (1 + i * 0.08),
                  dur: 0.07,
                  gain: 0.08,
                  delay: i * 0.11,
                });
              }
            },
          ];
          pick(patterns)();
        }, 4500);
        return;
      }

      case 'cafe': {
        // 咖啡厅：中低频白噪做人声嘈杂 + 偶尔瓷器碰撞
        this._noiseLayer('pink', 0.55, {
          type: 'bandpass',
          freq: 500,
          q: 0.8,
          lfoRate: 0.5,
          lfoDepth: 150,
        });
        this._noiseLayer('brown', 0.35, { type: 'lowpass', freq: 250, q: 0.5 });
        // 瓷器碰撞：高频短促脉冲
        this._scheduleGrain(() => {
          this._pulse({
            freq: 4500 + Math.random() * 2500,
            q: 30,
            dur: 0.08,
            gain: 0.12,
            type: 'bandpass',
          });
          // 有时伴随共鸣
          if (Math.random() < 0.4) {
            this._pulse({
              freq: 3200 + Math.random() * 1500,
              q: 25,
              dur: 0.06,
              gain: 0.08,
              delay: 0.03,
            });
          }
        }, 5500);
        return;
      }

      case 'keyboard': {
        // 机械键盘：brown 噪音轻底 + 敲击脉冲
        this._noiseLayer('brown', 0.08, { type: 'lowpass', freq: 200, q: 0.4 });
        this._scheduleGrain(() => {
          // 每次 1~5 个字符连击
          const count = 1 + Math.floor(Math.random() * 5);
          for (let i = 0; i < count; i++) {
            const delay = i * (0.08 + Math.random() * 0.12);
            // 两层：低频"砰" + 高频"咔"
            this._pulse({
              color: 'brown',
              freq: 200 + Math.random() * 100,
              q: 8,
              dur: 0.03,
              gain: 0.25,
              delay,
              type: 'bandpass',
            });
            this._pulse({
              color: 'white',
              freq: 3500 + Math.random() * 1500,
              q: 20,
              dur: 0.015,
              gain: 0.18,
              delay: delay + 0.005,
              type: 'bandpass',
            });
          }
        }, 900);
        return;
      }

      case 'wind': {
        // 风声：低通白噪 + 很慢 + 很深的 LFO
        this._noiseLayer('white', 0.7, {
          type: 'lowpass',
          freq: 900,
          q: 1.2,
          lfoRate: 0.05,
          lfoDepth: 700,
        });
        this._noiseLayer('brown', 0.25, { type: 'lowpass', freq: 150, q: 0.5 });
        return;
      }

      case 'stream': {
        // 溪流：中频 band + 密集高频"水花"
        this._noiseLayer('white', 0.55, {
          type: 'bandpass',
          freq: 2200,
          q: 0.6,
          lfoRate: 0.35,
          lfoDepth: 500,
        });
        this._noiseLayer('brown', 0.3, { type: 'lowpass', freq: 400, q: 0.5 });
        // 水花
        this._scheduleGrain(() => {
          this._pulse({
            freq: 3500 + Math.random() * 2500,
            q: 10,
            dur: 0.04,
            gain: 0.06,
          });
        }, 90);
        return;
      }

      case 'night': {
        // 夜晚虫鸣：低频风 + 蟋蟀（高频颤音）
        this._noiseLayer('brown', 0.3, { type: 'lowpass', freq: 200, q: 0.5 });
        this._noiseLayer('white', 0.08, { type: 'lowpass', freq: 2000, q: 0.4 });
        // 蟋蟀：高频短脉冲连续 5~8 次
        this._scheduleGrain(() => {
          const f = 4500 + Math.random() * 800;
          const count = 5 + Math.floor(Math.random() * 4);
          for (let i = 0; i < count; i++) {
            this._pulse({
              freq: f,
              q: 40,
              dur: 0.025,
              gain: 0.09,
              delay: i * 0.055,
            });
          }
        }, 1500);
        return;
      }

      default:
        // 未知类型，降级为粉噪
        this._noiseLayer('pink', 0.9);
        return;
    }
  }

  play(type, volume) {
    if (!this._ensureCtx()) return;
    this.stop();
    this.type = type;
    this.volume = volume;

    // 总输出带淡入
    const master = this.ctx.createGain();
    master.gain.value = 0;
    master.connect(this.ctx.destination);
    this.master = master;

    // 构建声音图（各层接到 this.master）
    this._build(type);

    // 淡入 1.5s
    const now = this.ctx.currentTime;
    master.gain.linearRampToValueAtTime(volume, now + 1.5);
  }

  setVolume(v) {
    this.volume = v;
    if (this.master && this.ctx) {
      const now = this.ctx.currentTime;
      this.master.gain.cancelScheduledValues(now);
      this.master.gain.linearRampToValueAtTime(v, now + 0.25);
    }
  }

  stop() {
    if (!this.ctx || !this.master) return;
    const now = this.ctx.currentTime;
    const master = this.master;
    const nodes = this.nodes;
    const timers = this.timers;
    this.master = null;
    this.nodes = [];
    this.timers = [];
    this.type = null;

    // 清颗粒定时器
    timers.forEach((id) => clearTimeout(id));

    // 淡出 0.8s 后 stop 所有
    master.gain.cancelScheduledValues(now);
    master.gain.setValueAtTime(master.gain.value, now);
    master.gain.linearRampToValueAtTime(0, now + 0.8);
    setTimeout(() => {
      nodes.forEach((n) => {
        try {
          if (n.stop) n.stop();
        } catch {
          // ignore
        }
        try {
          n.disconnect();
        } catch {
          // ignore
        }
      });
      try {
        master.disconnect();
      } catch {
        // ignore
      }
    }, 900);
  }

  get isPlaying() {
    return !!this.master;
  }
}

const PomodoroContext = createContext(null);

export const usePomodoro = () => {
  const ctx = useContext(PomodoroContext);
  if (!ctx) throw new Error('usePomodoro must be inside <PomodoroProvider>');
  return ctx;
};

export const PomodoroProvider = ({ children }) => {
  const [settings, setSettings] = useState(() => load(SETTINGS_KEY, DEFAULT_SETTINGS));
  // state 形状：
  // { phase: 'idle' | 'work' | 'break' | 'longBreak' | 'paused',
  //   startedAt: number,   // 阶段开始绝对时间
  //   durationMs: number,  // 本阶段总时长
  //   pausedRemainingMs: number | null,  // 暂停时剩余时长
  //   roundsCompleted: number,  // 今日累计工作番茄数
  // }
  const [state, setState] = useState(() =>
    load(STATE_KEY, {
      phase: 'idle',
      startedAt: null,
      durationMs: 0,
      pausedRemainingMs: null,
      roundsCompleted: 0,
    }),
  );
  const [history, setHistory] = useState(() => loadArr(HISTORY_KEY));
  const [, setTick] = useState(0);
  const phaseEndHandledRef = useRef(false);
  const noiseRef = useRef(null);
  if (!noiseRef.current && typeof window !== 'undefined') {
    noiseRef.current = new NoiseEngine();
  }

  // 持久化
  useEffect(() => save(SETTINGS_KEY, settings), [settings]);
  useEffect(() => save(STATE_KEY, state), [state]);
  useEffect(() => saveArr(HISTORY_KEY, history), [history]);

  // 1Hz tick
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // 计算剩余毫秒
  const getRemaining = useCallback(() => {
    if (state.phase === 'idle') return 0;
    if (state.phase === 'paused') return state.pausedRemainingMs ?? 0;
    if (!state.startedAt || !state.durationMs) return 0;
    return Math.max(0, state.startedAt + state.durationMs - Date.now());
  }, [state]);

  // 记录一个完成的工作番茄到历史
  const recordCompletion = useCallback(
    (phase, durationMs, startedAt, endedAt) => {
      if (phase !== 'work') return;
      setHistory((h) => {
        const rec = {
          id: endedAt,
          startedAt,
          endedAt,
          durationMs,
        };
        return [rec, ...h].slice(0, 500);
      });
      // 同步写入学习日志（只有完整走完的番茄钟才计入）
      const minutes = Math.round(durationMs / 60000);
      if (minutes > 0) {
        addStudyEntry({
          type: 'pomodoro',
          minutes,
          score: scorePomodoro(minutes),
        });
      }
    },
    [],
  );

  // 阶段自动切换
  useEffect(() => {
    if (state.phase === 'idle' || state.phase === 'paused') {
      phaseEndHandledRef.current = false;
      return;
    }
    const remaining = getRemaining();
    if (remaining > 0) {
      phaseEndHandledRef.current = false;
      return;
    }
    // 只处理一次
    if (phaseEndHandledRef.current) return;
    phaseEndHandledRef.current = true;

    const endedAt = (state.startedAt || 0) + (state.durationMs || 0);
    const finishedPhase = state.phase;

    // 记录完成 & 计数
    if (finishedPhase === 'work') {
      recordCompletion('work', state.durationMs, state.startedAt, endedAt);
    }

    // 通知/提示音
    const msg =
      finishedPhase === 'work'
        ? '工作完成，休息一下 ☕'
        : '休息结束，开始专注 🎯';
    if (settings.soundEnabled) playBeep();
    if (settings.notificationEnabled) notify('番茄钟', msg);

    // 自动切换下一阶段
    setState((s) => {
      if (finishedPhase === 'work') {
        const newRounds = s.roundsCompleted + 1;
        const isLong = newRounds % settings.roundsBeforeLongBreak === 0;
        const nextPhase = isLong ? 'longBreak' : 'break';
        const nextDur = isLong ? settings.longBreakMs : settings.breakMs;
        if (settings.autoStartBreak) {
          return {
            ...s,
            phase: nextPhase,
            startedAt: Date.now(),
            durationMs: nextDur,
            pausedRemainingMs: null,
            roundsCompleted: newRounds,
          };
        }
        return {
          ...s,
          phase: 'idle',
          startedAt: null,
          durationMs: 0,
          pausedRemainingMs: null,
          roundsCompleted: newRounds,
        };
      }
      // break / longBreak 结束
      if (settings.autoStartWork) {
        return {
          ...s,
          phase: 'work',
          startedAt: Date.now(),
          durationMs: settings.workMs,
          pausedRemainingMs: null,
        };
      }
      return {
        ...s,
        phase: 'idle',
        startedAt: null,
        durationMs: 0,
        pausedRemainingMs: null,
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, settings, getRemaining]);

  // ------- 背景白噪音 -------
  // 根据 phase + settings 自动控制播放
  useEffect(() => {
    const noise = noiseRef.current;
    if (!noise) return;
    const { bgmEnabled, bgmType, bgmVolume, bgmAutoStart, bgmPlayInBreak } = settings;
    const phase = state.phase;
    const shouldPlay =
      bgmEnabled &&
      ((phase === 'work' && bgmAutoStart) ||
        ((phase === 'break' || phase === 'longBreak') && bgmPlayInBreak));

    if (shouldPlay) {
      if (!noise.isPlaying || noise.type !== bgmType) {
        noise.play(bgmType, bgmVolume);
      } else {
        noise.setVolume(bgmVolume);
      }
    } else {
      if (noise.isPlaying) noise.stop();
    }
  }, [state.phase, settings]);

  // 卸载时停掉
  useEffect(() => {
    return () => {
      if (noiseRef.current) noiseRef.current.stop();
    };
  }, []);

  // 手动开关 BGM（即使不在工作/休息阶段也能试听）
  // overrides: { type, volume } 可选，用于立即切换而不等 settings 更新
  const toggleBGM = useCallback(
    (forceOn, overrides = {}) => {
      const noise = noiseRef.current;
      if (!noise) return;
      const willPlay = forceOn ?? !noise.isPlaying;
      if (willPlay) {
        noise.play(
          overrides.type ?? settings.bgmType,
          overrides.volume ?? settings.bgmVolume,
        );
      } else {
        noise.stop();
      }
    },
    [settings],
  );

  // ------- 控制操作 -------
  const startWork = useCallback(
    (customMs) => {
      const dur = customMs ?? settings.workMs;
      setState((s) => ({
        ...s,
        phase: 'work',
        startedAt: Date.now(),
        durationMs: dur,
        pausedRemainingMs: null,
      }));
      // 申请通知权限
      if (
        settings.notificationEnabled &&
        'Notification' in window &&
        Notification.permission === 'default'
      ) {
        Notification.requestPermission().catch(() => {});
      }
    },
    [settings],
  );

  const startBreak = useCallback(
    (long = false) => {
      const dur = long ? settings.longBreakMs : settings.breakMs;
      setState((s) => ({
        ...s,
        phase: long ? 'longBreak' : 'break',
        startedAt: Date.now(),
        durationMs: dur,
        pausedRemainingMs: null,
      }));
    },
    [settings],
  );

  const pause = useCallback(() => {
    setState((s) => {
      if (s.phase === 'idle' || s.phase === 'paused') return s;
      const remaining = Math.max(0, (s.startedAt || 0) + (s.durationMs || 0) - Date.now());
      return {
        ...s,
        phase: 'paused',
        pausedRemainingMs: remaining,
        // 保留 durationMs 用于重启计算
        _resumePhase: s.phase, // 存下次恢复时要去的阶段
      };
    });
  }, []);

  const resume = useCallback(() => {
    setState((s) => {
      if (s.phase !== 'paused') return s;
      const remaining = s.pausedRemainingMs ?? 0;
      return {
        ...s,
        phase: s._resumePhase || 'work',
        startedAt: Date.now() - (s.durationMs - remaining),
        pausedRemainingMs: null,
      };
    });
  }, []);

  const stop = useCallback(() => {
    setState((s) => ({
      ...s,
      phase: 'idle',
      startedAt: null,
      durationMs: 0,
      pausedRemainingMs: null,
    }));
  }, []);

  const resetRounds = useCallback(() => {
    setState((s) => ({ ...s, roundsCompleted: 0 }));
  }, []);

  const updateSettings = useCallback((partial) => {
    setSettings((s) => ({ ...s, ...partial }));
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  const remaining = getRemaining();
  const isActive = state.phase === 'work' || state.phase === 'break' || state.phase === 'longBreak';
  const isPaused = state.phase === 'paused';

  const value = useMemo(
    () => ({
      settings,
      updateSettings,
      state,
      history,
      remaining,
      isActive,
      isPaused,
      startWork,
      startBreak,
      pause,
      resume,
      stop,
      resetRounds,
      clearHistory,
      toggleBGM,
    }),
    [
      settings,
      updateSettings,
      state,
      history,
      remaining,
      isActive,
      isPaused,
      startWork,
      startBreak,
      pause,
      resume,
      stop,
      resetRounds,
      clearHistory,
      toggleBGM,
    ],
  );

  return <PomodoroContext.Provider value={value}>{children}</PomodoroContext.Provider>;
};

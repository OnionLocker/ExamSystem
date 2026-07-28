import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { addEntry as addStudyEntry, scorePomodoro } from '../studyLog/studyLog.js';
import { cloudGet, cloudSet } from '../cloudStorage.js';

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
// 历史记录走云同步(学习数据,跨设备)
const loadArr = (key) => cloudGet(key, []);
const saveArr = (key, arr) => cloudSet(key, arr);

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
// 背景音引擎：纯采样 + 随机事件层
// ============================================================
// 每个场景由两部分组成：
//   1) base loop：底层环境音，循环播放（如雨声、海浪、咖啡厅嗡嗡）
//   2) events（可选）：在底层之上随机触发的离散事件音
//      （如森林里的鸟鸣、雷雨里的远雷、夜晚的蟋蟀）
// 事件按照 [minMs, maxMs] 内随机间隔触发，每次随机挑一个事件音播一次。
// 事件层是 v1.1 关键增强 —— 让"听 5 分钟就识别出 loop"变成不可能。
//
// 素材都在 public/sounds/，详见该目录下的 README.md。
// ------------------------------------------------------------

const SCENE_SOUNDS = {
  rain: '/sounds/rain.mp3',
  thunderstorm: '/sounds/thunderstorm.mp3',
  ocean: '/sounds/ocean.mp3',
  stream: '/sounds/stream.mp3',
  forest: '/sounds/forest.mp3',
  fire: '/sounds/fire.mp3',
  wind: '/sounds/wind.mp3',
  night: '/sounds/night.mp3',
  cafe: '/sounds/cafe.mp3',
  keyboard: '/sounds/keyboard.mp3',
};

// 场景的随机事件配置：
//   sounds:  事件音 URL 数组（随机抽一个）
//   minMs/maxMs: 两次事件之间的随机间隔（均匀分布）
//   volume:  事件音相对于底层的音量倍率（不会超过 1）
const SCENE_EVENTS = {
  forest: {
    sounds: [
      '/sounds/events/bird1.mp3',
      '/sounds/events/bird2.mp3',
      '/sounds/events/bird3.mp3',
      '/sounds/events/bird4.mp3',
    ],
    minMs: 6000,
    maxMs: 22000,
    volume: 0.55,
  },
  thunderstorm: {
    sounds: [
      '/sounds/events/thunder1.mp3',
      '/sounds/events/thunder2.mp3',
      '/sounds/events/thunder3.mp3',
    ],
    minMs: 18000,
    maxMs: 60000,
    volume: 0.85,
  },
  rain: {
    // 雨声偶尔来一记远雷，强度低
    sounds: [
      '/sounds/events/thunder1.mp3',
      '/sounds/events/thunder2.mp3',
    ],
    minMs: 90000,
    maxMs: 240000,
    volume: 0.35,
  },
  night: {
    sounds: ['/sounds/events/cricket.mp3'],
    minMs: 12000,
    maxMs: 35000,
    volume: 0.45,
  },
};

// 容错：localStorage 里的 bgmType 如果是已下线的 white/pink/brown 等，回退到默认场景
const DEFAULT_SCENE = 'rain';

class SoundEngine {
  constructor() {
    this.ctx = null;
    this.master = null;       // 当前场景的总输出 GainNode
    this.activeNodes = [];    // 挂在 master 下的需清理节点
    this.eventTimers = [];    // 事件调度的 setTimeout 句柄
    this.type = null;
    this.volume = 0.4;
    this.bufferCache = new Map(); // url -> AudioBuffer | null
    this.gen = 0;             // 代次号，作废过期的异步流程
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

  // ---------- 采样加载（带缓存） ----------
  async _loadSample(url) {
    if (this.bufferCache.has(url)) return this.bufferCache.get(url);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const arr = await res.arrayBuffer();
      const buf = await this.ctx.decodeAudioData(arr);
      this.bufferCache.set(url, buf);
      return buf;
    } catch (e) {
      console.warn(
        `[SoundEngine] 采样加载失败：${url}（该层会静默跳过）。` +
          `把 mp3 放到对应路径即可恢复，详见 public/sounds/README.md`,
        e?.message || e,
      );
      this.bufferCache.set(url, null); // 标记缺失避免重试
      return null;
    }
  }

  // ---------- 底层 loop 播放 ----------
  _playBaseLoop(buf) {
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    src.connect(this.master);
    src.start();
    this.activeNodes.push(src);
  }

  // ---------- 单次事件音 ----------
  _playEventOnce(buf, volume) {
    if (!this.master || !this.ctx) return;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.loop = false;
    const g = this.ctx.createGain();
    g.gain.value = volume;
    src.connect(g);
    g.connect(this.master);
    src.start();
    src.onended = () => {
      try { src.disconnect(); } catch { /* ignore */ }
      try { g.disconnect(); } catch { /* ignore */ }
    };
  }

  // ---------- 事件层调度 ----------
  async _scheduleEvents(type, myGen) {
    const cfg = SCENE_EVENTS[type];
    if (!cfg) return;

    // 并发预加载所有事件音
    const buffers = await Promise.all(cfg.sounds.map((u) => this._loadSample(u)));
    if (myGen !== this.gen) return;
    const valid = buffers.filter((b) => b);
    if (valid.length === 0) return;

    const tick = () => {
      if (myGen !== this.gen || !this.master) return;
      const buf = valid[Math.floor(Math.random() * valid.length)];
      this._playEventOnce(buf, cfg.volume);
      // 排下一次
      const wait = cfg.minMs + Math.random() * (cfg.maxMs - cfg.minMs);
      const id = setTimeout(tick, wait);
      this.eventTimers.push(id);
    };

    // 首次事件做一个稍长的延迟（避免一开播就来事件，听感突兀）
    const initial = cfg.minMs * 1.5 + Math.random() * (cfg.maxMs - cfg.minMs);
    const id = setTimeout(tick, initial);
    this.eventTimers.push(id);
  }

  // ---------- 公共 API ----------
  play(type, volume) {
    if (!this._ensureCtx()) return;
    this.stop();

    const myGen = ++this.gen;
    // 未知场景兜底（兼容老版本 localStorage 里的 white/pink/brown）
    const sceneType = SCENE_SOUNDS[type] ? type : DEFAULT_SCENE;
    this.type = sceneType;
    this.volume = volume;

    const master = this.ctx.createGain();
    master.gain.value = 0;
    master.connect(this.ctx.destination);
    this.master = master;

    // 1.2s 淡入
    const now = this.ctx.currentTime;
    master.gain.linearRampToValueAtTime(volume, now + 1.2);

    // 加载并播放底层 loop
    this._loadSample(SCENE_SOUNDS[sceneType]).then((buf) => {
      if (myGen !== this.gen || !this.master) return;
      if (buf) this._playBaseLoop(buf);
    });

    // 启动事件层（如果有配置）
    this._scheduleEvents(sceneType, myGen);
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
    const master = this.master;
    const nodes = this.activeNodes;
    const timers = this.eventTimers;
    this.master = null;
    this.activeNodes = [];
    this.eventTimers = [];
    this.type = null;
    this.gen++; // 让进行中的异步流程作废

    // 立即清掉所有事件调度
    timers.forEach((id) => clearTimeout(id));

    const now = this.ctx.currentTime;
    master.gain.cancelScheduledValues(now);
    master.gain.setValueAtTime(master.gain.value, now);
    master.gain.linearRampToValueAtTime(0, now + 0.6);

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
    }, 700);
  }

  get isPlaying() {
    return !!this.master;
  }
}

const PomodoroContext = createContext(null);

// context hook 与它的 Provider 放在同一文件是通行做法；拆开只为满足 fast-refresh
// 反而让调用方多一个 import。这里只影响开发时热更新粒度，不影响运行时。
// eslint-disable-next-line react-refresh/only-export-components
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
  // SoundEngine 只需构造一次。用 useState 的惰性初始化，而不是渲染期写 ref：
  // 渲染期读写 ref 在 React 19 并发渲染下不保证只执行一次。
  const [noiseEngine] = useState(() =>
    typeof window !== 'undefined' ? new SoundEngine() : null,
  );

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

    // 记录完成 & 计数。
    // recordCompletion 内部会 setHistory，直接在 effect 同步体里调用会触发级联渲染，
    // 所以挪到微任务里执行 —— 上面的 phaseEndHandledRef 已保证每个阶段只跑一次，
    // 延后一个微任务不影响正确性（写的是历史记录，不参与本次渲染输出）。
    if (finishedPhase === 'work') {
      queueMicrotask(() =>
        recordCompletion('work', state.durationMs, state.startedAt, endedAt),
      );
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
    const noise = noiseEngine;
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
  }, [state.phase, settings, noiseEngine]);

  // 卸载时停掉
  useEffect(() => {
    return () => {
      if (noiseEngine) noiseEngine.stop();
    };
  }, [noiseEngine]);

  // 手动开关 BGM（即使不在工作/休息阶段也能试听）
  // overrides: { type, volume } 可选，用于立即切换而不等 settings 更新
  const toggleBGM = useCallback(
    (forceOn, overrides = {}) => {
      const noise = noiseEngine;
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
    [settings, noiseEngine],
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

// ============================================================
// 答对 / 答错音效引擎(Web Audio 纯合成,无外部资源)
// ------------------------------------------------------------
// playCorrect()  → 清亮"叮"  + 上行三度,给做对一题的爽感
// playWrong()    → 低沉"咚"  + 噪声冲击,给做错一题的扣血感
// ------------------------------------------------------------
// 与 bgm.js 共用一个 AudioContext(避免被某些浏览器限制并发数)
// ============================================================

import { _getAudioContext } from './bgm.js';

// 主音量(用户偏好)
const PREFS_KEY = 'sfx_prefs_v1';
const DEFAULT_PREFS = { enabled: true, volume: 0.55 };

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

let _prefs = null;
const getPrefs = () => {
  if (!_prefs) _prefs = loadPrefs();
  return _prefs;
};

export const setSfxEnabled = (flag) => {
  const p = getPrefs();
  p.enabled = !!flag;
  savePrefs(p);
};
export const setSfxVolume = (v) => {
  const p = getPrefs();
  p.volume = Math.max(0, Math.min(1, Number(v) || 0));
  savePrefs(p);
};
export const getSfxPrefs = () => ({ ...getPrefs() });

// ---------------- 内部:复用 BGM 的 AudioContext ----------------
// 若 bgm 还没启用,这里就自建一个
let _localCtx = null;
const ensureCtx = () => {
  // 优先复用 bgm 那个 ctx(同手势激活)
  const shared = typeof _getAudioContext === 'function' ? _getAudioContext() : null;
  if (shared) return shared;
  if (!_localCtx) {
    const AC = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext);
    if (!AC) return null;
    _localCtx = new AC();
  }
  if (_localCtx.state === 'suspended') _localCtx.resume().catch(() => {});
  return _localCtx;
};

// ---------------- 公共:答对音效(亮 + 上行) ----------------
// 思路:两段三角波,频率 C5(523) → E5(659)→ G5(784) 0.06s 内完成,
//      叠加一道高频 noise 冲击 + 整体 ADSR,做出"叮~ 当!"的爽感
export const playCorrect = () => {
  const prefs = getPrefs();
  if (!prefs.enabled) return;
  const ctx = ensureCtx();
  if (!ctx) return;

  const t0 = ctx.currentTime;
  const masterVol = prefs.volume;

  // 主输出 gain(整体 ADSR)
  const master = ctx.createGain();
  master.gain.setValueAtTime(0.0001, t0);
  master.gain.exponentialRampToValueAtTime(masterVol, t0 + 0.01);
  master.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.32);
  master.connect(ctx.destination);

  // 第 1 层:三角波旋律 C5 → E5 → G5
  const osc1 = ctx.createOscillator();
  osc1.type = 'triangle';
  osc1.frequency.setValueAtTime(523.25, t0);          // C5
  osc1.frequency.linearRampToValueAtTime(659.25, t0 + 0.05); // E5
  osc1.frequency.linearRampToValueAtTime(783.99, t0 + 0.10); // G5
  const g1 = ctx.createGain();
  g1.gain.setValueAtTime(0.6, t0);
  g1.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.30);
  osc1.connect(g1).connect(master);
  osc1.start(t0);
  osc1.stop(t0 + 0.32);

  // 第 2 层:正弦泛音(上行更高,增加"亮")
  const osc2 = ctx.createOscillator();
  osc2.type = 'sine';
  osc2.frequency.setValueAtTime(1046.50, t0);         // C6
  osc2.frequency.linearRampToValueAtTime(1568.0, t0 + 0.10); // G6
  const g2 = ctx.createGain();
  g2.gain.setValueAtTime(0.25, t0);
  g2.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.18);
  osc2.connect(g2).connect(master);
  osc2.start(t0);
  osc2.stop(t0 + 0.20);

  // 第 3 层:开头一道短促高频 noise(像 "叮" 的金属感)
  const noiseLen = 0.04;
  const noiseBuf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * noiseLen), ctx.sampleRate);
  const data = noiseBuf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1);
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuf;
  // 高通,只留亮部
  const hp = ctx.createBiquadFilter();
  hp.type = 'highpass';
  hp.frequency.value = 4000;
  const gn = ctx.createGain();
  gn.gain.setValueAtTime(0.20, t0);
  gn.gain.exponentialRampToValueAtTime(0.0001, t0 + noiseLen);
  noise.connect(hp).connect(gn).connect(master);
  noise.start(t0);
  noise.stop(t0 + noiseLen + 0.02);
};

// ---------------- 公共:答错音效(MC 受击感:中频爆点 + 宽频噪声冲击) ----------------
// 设计参考 Minecraft hurt sound:
//   · 不是低频 boom,而是中频 punchy 瞬态(300-600Hz)
//   · 极短(总长 ≈ 180ms),一击即逝,不拖泥带水
//   · 带宽噪声做"啪"的冲击,叠加方波做"鼻音爆"质感
//   · 轻微下滑 pitch(被打到的"哎"声调感)
export const playWrong = () => {
  const prefs = getPrefs();
  if (!prefs.enabled) return;
  const ctx = ensureCtx();
  if (!ctx) return;

  const t0 = ctx.currentTime;
  const masterVol = prefs.volume * 0.9;

  // 主输出:极短 ADSR(attack 5ms / decay 170ms),punchy 不拖
  const master = ctx.createGain();
  master.gain.setValueAtTime(0.0001, t0);
  master.gain.linearRampToValueAtTime(masterVol, t0 + 0.005);
  master.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.18);
  master.connect(ctx.destination);

  // 第 1 层:方波"啊"声 ── 中频(420Hz → 320Hz)轻微下滑,带鼻音
  // 方波富含奇次谐波,听上去有"颗粒/被打"的质感
  const osc = ctx.createOscillator();
  osc.type = 'square';
  osc.frequency.setValueAtTime(420, t0);
  osc.frequency.exponentialRampToValueAtTime(320, t0 + 0.14);
  // 带通把方波打圆,留下中频的"呃"
  const bp = ctx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.frequency.value = 480;
  bp.Q.value = 2.5;
  const g1 = ctx.createGain();
  g1.gain.setValueAtTime(0.55, t0);
  g1.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.16);
  osc.connect(bp).connect(g1).connect(master);
  osc.start(t0);
  osc.stop(t0 + 0.18);

  // 第 2 层:宽频白噪声冲击 ── 像 MC 那一下"啪"
  // 极短(40ms),做出冲击瞬态;低通到 5kHz,避免太刺耳
  const noiseLen = 0.04;
  const noiseBuf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * noiseLen), ctx.sampleRate);
  const data = noiseBuf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1);
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuf;
  const lp = ctx.createBiquadFilter();
  lp.type = 'lowpass';
  lp.frequency.value = 5000;
  const gn = ctx.createGain();
  // 噪声打头,极短 attack + 极快 decay
  gn.gain.setValueAtTime(0.45, t0);
  gn.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.05);
  noise.connect(lp).connect(gn).connect(master);
  noise.start(t0);
  noise.stop(t0 + noiseLen + 0.02);

  // 第 3 层:600Hz 短脉冲(像被击中的"嗯"瞬态),做加厚
  const punch = ctx.createOscillator();
  punch.type = 'sine';
  punch.frequency.setValueAtTime(600, t0);
  punch.frequency.exponentialRampToValueAtTime(150, t0 + 0.06);
  const gp = ctx.createGain();
  gp.gain.setValueAtTime(0.35, t0);
  gp.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.07);
  punch.connect(gp).connect(master);
  punch.start(t0);
  punch.stop(t0 + 0.08);
};

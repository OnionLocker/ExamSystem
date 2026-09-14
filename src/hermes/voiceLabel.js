// 语音消息在对话里只留一个时长标签当正文，录音本身走 audio.attach_bytes。
// 所以「产标签」和「认标签」必须严格互逆：一旦对不上，重开会话水合时就认不出
// 这是条语音，气泡退化成一行裸文字。产和认放在一起，好一起测。

export const fmtAudioLen = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  if (s < 60) return `${s}秒`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m}分${r}秒` : `${m}分钟`;
};

/** 发送时写进对话的那条正文。parseAudioLen 必须能还原出秒数。 */
export const audioLabelOf = (sec) => (sec > 0 ? `语音 ${fmtAudioLen(sec)}` : '语音');

export const parseAudioLen = (text) => {
  const s = String(text || '').trim().replace(/^[（(]|[）)]$/g, '');
  const m = s.match(/^(?:语音\s*)?(\d+)\s*秒$/) || s.match(/^(\d+)\s*s$/i);
  if (m) return Number(m[1]);
  const mm = s.match(/^(?:语音\s*)?(\d+)\s*分钟$/);
  if (mm) return Number(mm[1]) * 60;
  const mix = s.match(/^(?:语音\s*)?(\d+)\s*分(\d+)\s*秒$/);
  if (mix) return Number(mix[1]) * 60 + Number(mix[2]);
  return null;
};

export const isAudioLabel = (text) => {
  const s = String(text || '').trim();
  return s === '语音' || s === '（语音口述）' || parseAudioLen(s) != null;
};

/** 气泡上那个紧凑时长，微信那种 12" / 1'30"。 */
export const fmtVoiceQuote = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  if (s <= 0) return '语音';
  if (s < 60) return `${s}"`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m}'${r}"` : `${m}'`;
};

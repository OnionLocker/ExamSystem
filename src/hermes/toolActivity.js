const ACTIVITIES = [
  [/skill_view/i, ['📚', '我翻翻方法', ['📚', '✨', '📖', '📚']]],
  [/read_file|file_read/i, ['👀', '我看看资料', ['👀', '🧐', '📖', '👀']]],
  [/terminal|shell|python/i, ['🧮', '我算一下', ['🧮', '✨', '🧠', '🧮']]],
  [/search|grep|find/i, ['🔎', '我找找线索', ['🔎', '👀', '🔦', '🔎']]],
  [/web|browser/i, ['🌐', '我去查查', ['🌐', '🔎', '✨', '🌐']]],
  [/image|vision/i, ['🖼️', '我看看图', ['🖼️', '👀', '✨', '🖼️']]],
  [/patch|write_file/i, ['✍️', '我改改内容', ['✍️', '📝', '✨', '✍️']]],
];

const IDLE_FRAMES = ['✨', '🤔', '💭', '🌟'];

export const getToolActivity = (name = '') => {
  const match = ACTIVITIES.find(([pattern]) => pattern.test(String(name)));
  if (!match) return { emoji: '✨', label: '我处理一下', frames: IDLE_FRAMES };
  const [emoji, label, frames] = match[1];
  return { emoji, label, frames };
};

export const thinkingActivity = () => ({
  emoji: '✨',
  label: '我整理一下',
  frames: IDLE_FRAMES,
});

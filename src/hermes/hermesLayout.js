// Hermes 会话列表的布局阈值。
// 桌面宽屏才默认并排左栏；平板（含 iPad 分屏，大约 768–1366）和手机走抽屉。
export const DESKTOP_SIDEBAR_MIN_PX = 1440;

// 与现有侧栏一致：微信 / cron 会话仍不进列表。
export const HIDDEN_SOURCES = new Set(['cron', 'weixin', 'wechat']);

export const sessionPickerMode = (width) => (
  Number(width) >= DESKTOP_SIDEBAR_MIN_PX ? 'docked' : 'sheet'
);

// 宽度 < 1440 时会话列表必须有一个始终挂着的入口（「会话」按钮），
// 不能再依赖「默认展开的左栏」或挤在顶栏最左侧的小图标。
export const sessionListReachable = (width) => sessionPickerMode(width) === 'sheet'
  || Number(width) >= DESKTOP_SIDEBAR_MIN_PX;

import { useEffect, useState, useSyncExternalStore } from 'react';
import { Volume2, VolumeX, Music } from 'lucide-react';
import {
  getBgmState,
  setBgmVolume,
  setBgmEnabled,
  subscribeBgm,
  BGM_TRACKS,
} from './bgm.js';

// ============================================================
// BGM 浮动控件
// ----------------------------------------
// 右上角小图标,默认收起,鼠标移上(或点击)展开:
//   · 静音/恢复 toggle(图标变 VolumeX / Volume2)
//   · 横向音量滑块(0-100)
//   · 当前曲名 label
// 状态由 BgmEngine 单例管理,跨页面共享。
// ============================================================

const useBgmState = () => {
  return useSyncExternalStore(
    (cb) => subscribeBgm(cb),
    () => getBgmState(),
    () => getBgmState(),
  );
};

const BgmControls = ({ position = 'top-right', className = '' }) => {
  const state = useBgmState();
  const [open, setOpen] = useState(false);

  // 移动端用点击;桌面用 hover
  const onMouseEnter = () => setOpen(true);
  const onMouseLeave = () => setOpen(false);

  const enabled = state.enabled;
  const volPct = Math.round(state.volume * 100);
  const trackInfo = state.activeId ? BGM_TRACKS[state.activeId] : null;
  const Icon = enabled && state.activeId ? Volume2 : VolumeX;

  // ESC 关闭面板
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // 阻止键盘事件冒泡到上层(避免空格触发别的逻辑)
  const stopKey = (e) => e.stopPropagation();

  const positionCls = position === 'top-right'
    ? 'top-3 right-3 sm:top-4 sm:right-4'
    : position;

  return (
    <div
      className={`fixed z-[140] flex items-start ${positionCls} ${className}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onKeyDown={stopKey}
    >
      <div
        className={`flex items-center transition-all duration-300 rounded-full shadow-lg overflow-hidden ${
          open
            ? 'bg-[#1a1a1a]/92 backdrop-blur-md pl-3 pr-2 py-1.5 gap-3 max-w-[320px]'
            : 'bg-[#1a1a1a]/70 backdrop-blur p-2 gap-0 max-w-[40px]'
        }`}
      >
        <button
          onClick={() => {
            if (!open) setOpen(true);
            else setBgmEnabled(!enabled);
          }}
          title={enabled ? '点击静音' : '点击开启 BGM'}
          className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[#fbc02d] hover:scale-110 transition-transform"
        >
          <Icon size={15} strokeWidth={2.4} />
        </button>

        {open && (
          <>
            <div className="flex flex-col items-stretch min-w-[140px]">
              <div className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest text-white/70 leading-none mb-1.5">
                <Music size={10} className="text-[#fbc02d]" />
                <span className="truncate">
                  {trackInfo
                    ? state.loadFailed
                      ? `${trackInfo.label} · 资源缺失`
                      : enabled
                        ? trackInfo.label
                        : `${trackInfo.label} · 已静音`
                    : '无 BGM'}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={volPct}
                onChange={(e) => {
                  const v = Number(e.target.value) / 100;
                  setBgmVolume(v);
                  if (!enabled && v > 0) setBgmEnabled(true);
                }}
                className="w-full h-1 accent-[#fbc02d] cursor-pointer"
              />
            </div>
            <span className="text-[10px] font-black tabular-nums text-white/80 w-7 text-right">
              {volPct}
            </span>
          </>
        )}
      </div>
    </div>
  );
};

export default BgmControls;

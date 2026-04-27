import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Gamepad2, Grid3x3, Lock } from 'lucide-react';
import NumberGridGame from './NumberGridGame.jsx';

// ============================================================
// 小游戏总入口
// 目前仅 1 款：点数字（Schulte Table）
// 后续可在 GAMES 数组中追加更多游戏
// ============================================================

const GAMES = [
  {
    id: 'numberGrid',
    name: '点数字',
    desc: '5×5 / 6×6 / 7×7 / 8×8 / 9×9 / 10×10 随机数字表，从 1 顺序点到末尾。锻炼找数能力与专注度。',
    icon: Grid3x3,
    color: '#fbc02d',
    available: true,
  },
  {
    id: 'placeholder1',
    name: '敬请期待',
    desc: '更多数资脑力小游戏正在路上…',
    icon: Lock,
    color: '#94a3b8',
    available: false,
  },
];

const GamesHome = ({ onBack }) => {
  const [active, setActive] = useState(null);

  useEffect(() => {
    if (!active) return undefined;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setActive(null);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [active]);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">返回</span>
        </button>
        <div className="flex items-center space-x-2">
          <Gamepad2 size={18} className="text-[#fbc02d]" />
          <h2 className="text-2xl font-black italic">小游戏</h2>
        </div>
        <span className="w-14" />
      </div>

      <p className="text-sm font-medium text-slate-400">
        在紧张的刷题之间调剂一下，用小游戏锻炼“数字敏感度 / 专注度”。
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {GAMES.map((g) => {
          const Icon = g.icon;
          const disabled = !g.available;
          return (
            <button
              key={g.id}
              onClick={() => !disabled && setActive(g.id)}
              disabled={disabled}
              className={`group text-left rounded-[2rem] p-7 transition-all border ${
                disabled
                  ? 'bg-white border-[#f2f0e9] opacity-60 cursor-not-allowed'
                  : 'bg-[#1a1a1a] text-white border-[#1a1a1a] hover:-translate-y-1 hover:shadow-xl hover:shadow-black/10'
              }`}
            >
              <div className="flex items-center justify-between mb-5">
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center"
                  style={{
                    backgroundColor: disabled ? '#f2f0e9' : g.color,
                    color: disabled ? '#94a3b8' : '#1a1a1a',
                  }}
                >
                  <Icon size={22} />
                </div>
                {!disabled ? (
                  <ChevronRight
                    size={20}
                    className="opacity-60 group-hover:opacity-100 group-hover:translate-x-1 transition-all"
                  />
                ) : (
                  <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                    敬请期待
                  </span>
                )}
              </div>
              <h3 className="text-xl font-black italic mb-2">{g.name}</h3>
              <p className={`text-sm font-medium ${disabled ? 'text-slate-400' : 'opacity-60'}`}>
                {g.desc}
              </p>
            </button>
          );
        })}
      </div>

      {active === 'numberGrid' && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 md:p-8">
          <button
            type="button"
            aria-label="关闭小游戏"
            onClick={() => setActive(null)}
            className="absolute inset-0 bg-[rgba(248,248,246,0.42)] backdrop-blur-xl"
          />
          <div className="absolute inset-0 bg-slate-950/28" />

          <div className="relative z-[121] flex w-full max-w-[1500px] flex-col items-center justify-center">
            <div className="w-full max-h-[92vh] overflow-y-auto rounded-[2.75rem] border border-white/70 bg-white/78 p-3 shadow-[0_40px_140px_rgba(15,23,42,0.28)] backdrop-blur-2xl md:p-4">
              <NumberGridGame onBack={() => setActive(null)} />
            </div>
            <p className="mt-4 text-center text-[10px] font-black uppercase tracking-[0.28em] text-slate-500">
              ESC 退出聚焦模式
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default GamesHome;

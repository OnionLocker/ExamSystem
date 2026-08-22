import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Gamepad2, Grid3x3, Brain, Layers, Lock } from 'lucide-react';
import NumberGridGame from './NumberGridGame.jsx';
import MentalCarryGame from './MentalCarryGame.jsx';
import DigitSpanGame from './DigitSpanGame.jsx';
import { playBgm, stopBgm } from '../bgm.js';
import BgmControls from '../BgmControls.jsx';

// ============================================================
// 小游戏总入口
// 目前 3 款：
//   ● 点数字（Schulte Table）—— 找数 / 专注
//   ● 移位加减（Mental Carry）—— 治"记一忘一"
//   ● 数字记忆广度（Digit Span）—— 工作记忆扩容
// 后续可在 GAMES 数组中追加更多游戏
// ============================================================

const GAMES = [
  {
    id: 'numberGrid',
    name: '点数字',
    desc: '5×5 / 6×6 / 7×7 / 8×8 / 9×9 / 10×10 随机数字表，从 1 顺序点到末尾。锻炼找数能力与专注度。',
    icon: Grid3x3,
    color: '#8d7348',
    available: true,
  },
  {
    id: 'mentalCarry',
    name: '移位加减',
    desc: '强制按个 → 十 → 百顺序敲答案。把心算从「记 4-6 位数」压缩成「当前位 + 进位」。专治资料分析"记现期忘基期"。',
    icon: Brain,
    color: '#22c55e',
    available: true,
  },
  {
    id: 'digitSpan',
    name: '数字记忆广度',
    desc: '屏幕闪 N 个数字让你倒序回忆。工作记忆训练（N-Back 变种），治"翻页找数据"的根本短板。',
    icon: Layers,
    color: '#a855f7',
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

    // 进入小游戏 modal → 起 games BGM(像素轻快风);关闭时停
    playBgm('games');

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
      stopBgm();
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
          <Gamepad2 size={18} className="text-[#6b5428]" />
          <h2 className="text-2xl font-black italic">小游戏</h2>
        </div>
        <span className="w-14" />
      </div>

      <p className="text-sm font-medium text-slate-400">
        在紧张的刷题之间调剂一下，用小游戏锻炼“数字敏感度 / 专注度”。
      </p>
      <div className="flex flex-wrap gap-2 text-[10px] font-black uppercase tracking-widest">
        <span className="px-2.5 py-1 rounded-full bg-[#1a1a1a] text-white">练习区 · 补数与滚加</span>
        <span className="px-2.5 py-1 rounded-full bg-[#1a1a1a] text-white">练习区 · 秒杀定性</span>
      </div>

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
                  ? 'bg-white border-[#e8d5b0] opacity-60 cursor-not-allowed'
                  : 'bg-[#1a1a1a] text-white border-[#1a1a1a] hover:-translate-y-1 hover:shadow-xl hover:shadow-black/10'
              }`}
            >
              <div className="flex items-center justify-between mb-5">
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center"
                  style={{
                    backgroundColor: disabled ? '#e8d5b0' : g.color,
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

      {active && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-3 sm:p-4 md:p-8">
          <BgmControls position="top-right" />
          <button
            type="button"
            aria-label="关闭小游戏"
            onClick={() => setActive(null)}
            className="absolute inset-0 bg-[rgba(248,248,246,0.42)] backdrop-blur-xl"
          />
          <div className="absolute inset-0 bg-slate-950/28" />

          <div className="relative z-[121] flex w-full max-w-[1500px] flex-col items-center justify-center">
            <div className="w-full max-h-[92vh] overflow-y-auto rounded-[1.75rem] sm:rounded-[2.75rem] border border-white/70 bg-white/78 p-3 shadow-[0_40px_140px_rgba(15,23,42,0.28)] backdrop-blur-2xl md:p-4">
              {active === 'numberGrid' && (
                <NumberGridGame onBack={() => setActive(null)} />
              )}
              {active === 'mentalCarry' && (
                <MentalCarryGame onBack={() => setActive(null)} />
              )}
              {active === 'digitSpan' && (
                <DigitSpanGame onBack={() => setActive(null)} />
              )}
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

import { useEffect, useMemo, useState } from 'react';
import { Square, Sliders } from 'lucide-react';
import { SOUND_CATEGORIES, SOUND_BY_ID, TOTAL_SOUNDS } from './sounds.js';
import { getMixer } from './SoundMixer.js';

const STORAGE_KEY = 'sound_mixer_state_v1';

const loadSavedMix = () => {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
};

const saveMix = (snapshot) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // ignore
  }
};

const Mixer = () => {
  const mixer = useMemo(() => getMixer(), []);
  const [activeCategory, setActiveCategory] = useState(SOUND_CATEGORIES[0].id);
  // 用于触发重渲染的版本号——每次 mixer 状态变化时 +1
  const [, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);

  // 订阅 mixer 状态变化
  useEffect(() => {
    if (!mixer) return;
    const unsub = mixer.subscribe(bump);
    return unsub;
  }, [mixer]);

  // 持久化：每次状态变化都把当前快照写到 localStorage
  useEffect(() => {
    if (!mixer) return;
    const unsub = mixer.subscribe(() => {
      saveMix(mixer.snapshot());
    });
    return unsub;
  }, [mixer]);

  // 首次挂载：恢复上次的混音
  useEffect(() => {
    if (!mixer) return;
    const saved = loadSavedMix();
    Object.entries(saved).forEach(([id, vol]) => {
      const s = SOUND_BY_ID.get(id);
      if (s) mixer.play(id, s.src, typeof vol === 'number' ? vol : 0.6);
    });
  }, [mixer]);

  if (!mixer) {
    return (
      <div className="text-center py-24 text-slate-400 font-bold">
        当前环境不支持 Web Audio API
      </div>
    );
  }

  const activeIds = mixer.getActiveIds();
  const activeCount = activeIds.length;
  const currentCategory =
    SOUND_CATEGORIES.find((c) => c.id === activeCategory) || SOUND_CATEGORIES[0];

  return (
    <div className="space-y-8">
      {/* 顶部状态条 */}
      <div className="bg-[#1a1a1a] rounded-[2.5rem] p-8 text-white flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <div className="w-12 h-12 rounded-2xl bg-[#2c261c] text-white flex items-center justify-center">
            <Sliders size={22} strokeWidth={2.5} />
          </div>
          <div>
            <h3 className="text-lg font-black">声音混音器</h3>
            <p className="text-xs font-bold opacity-50 uppercase tracking-widest mt-0.5">
              {activeCount > 0 ? (
                <>正在播放 <span className="text-[#6b5428]">{activeCount}</span> 个 / 共 {TOTAL_SOUNDS}</>
              ) : (
                <>共 {TOTAL_SOUNDS} 个声音 · 点卡片开始</>
              )}
            </p>
          </div>
        </div>

        <button
          onClick={() => mixer.stopAll()}
          disabled={activeCount === 0}
          className={`flex items-center space-x-2 px-5 py-3 rounded-2xl text-xs font-black uppercase tracking-widest transition-all ${
            activeCount === 0
              ? 'bg-white/[0.05] text-white/30 cursor-not-allowed'
              : 'bg-[#ff6b6b] text-white hover:bg-[#ff5050]'
          }`}
        >
          <Square size={14} fill="currentColor" />
          <span>全停</span>
        </button>
      </div>

      {/* 分类 tab */}
      <div className="flex flex-wrap gap-2">
        {SOUND_CATEGORIES.map((c) => {
          const active = c.id === activeCategory;
          // 该分类下当前正在播放的数量
          const activeInCat = c.sounds.filter((s) => mixer.isPlaying(s.id)).length;
          return (
            <button
              key={c.id}
              onClick={() => setActiveCategory(c.id)}
              className={`relative px-5 py-2.5 rounded-full font-black text-sm tracking-tight transition-all ${
                active
                  ? 'bg-[#1a1a1a] text-white shadow-lg shadow-black/10'
                  : 'bg-white/60 text-[#666] hover:bg-white/90 hover:text-black'
              }`}
            >
              {c.label}
              {activeInCat > 0 && (
                <span
                  className={`ml-2 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-black tabular-nums ${
                    active ? 'bg-[#2c261c] text-white' : 'bg-[#2c261c] text-white'
                  }`}
                >
                  {activeInCat}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* 卡片网格 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {currentCategory.sounds.map((s) => (
          <SoundCard key={s.id} sound={s} mixer={mixer} />
        ))}
      </div>
    </div>
  );
};

const SoundCard = ({ sound, mixer }) => {
  const Icon = sound.icon;
  const isPlaying = mixer.isPlaying(sound.id);
  const volume = mixer.getVolume(sound.id);

  const onClick = () => {
    if (isPlaying) {
      mixer.stop(sound.id);
    } else {
      mixer.play(sound.id, sound.src, 0.6);
    }
  };

  const onVolumeChange = (e) => {
    e.stopPropagation();
    const v = parseFloat(e.target.value);
    mixer.setVolume(sound.id, v);
  };

  return (
    <div
      onClick={onClick}
      className={`group relative aspect-square rounded-3xl p-5 cursor-pointer transition-all duration-200 select-none ${
        isPlaying
          ? 'bg-[#2c261c] text-white shadow-lg shadow-black/10 scale-[1.02]'
          : 'bg-white/70 text-[#1a1a1a] hover:bg-white hover:shadow-md hover:-translate-y-0.5'
      }`}
    >
      {/* 顶部图标 */}
      <div className="flex items-start justify-between">
        <div
          className={`w-11 h-11 rounded-2xl flex items-center justify-center ${
            isPlaying ? 'bg-[#1a1a1a] text-white' : 'bg-[#e8d5b0] text-[#1a1a1a]'
          }`}
        >
          <Icon size={20} strokeWidth={2.2} />
        </div>
        {isPlaying && (
          <span className="text-[9px] font-black uppercase tracking-widest text-[#1a1a1a]/70 mt-1.5">
            ON
          </span>
        )}
      </div>

      {/* 名字 */}
      <p className="absolute bottom-12 left-5 right-5 text-sm font-black tracking-tight">
        {sound.label}
      </p>

      {/* 音量条（仅 active 时显示）*/}
      <div className="absolute bottom-4 left-5 right-5 h-2">
        {isPlaying ? (
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={volume}
            onChange={onVolumeChange}
            onClick={(e) => e.stopPropagation()}
            className="w-full h-1.5 appearance-none bg-[#1a1a1a]/15 rounded-full cursor-pointer
                       [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3
                       [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full
                       [&::-webkit-slider-thumb]:bg-[#1a1a1a] [&::-webkit-slider-thumb]:cursor-grab
                       [&::-webkit-slider-thumb]:active:cursor-grabbing
                       [&::-webkit-slider-thumb]:shadow-md
                       [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:h-3
                       [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-[#1a1a1a]
                       [&::-moz-range-thumb]:border-0"
            style={{
              background: `linear-gradient(to right, #1a1a1a 0%, #1a1a1a ${volume * 100}%, rgba(26,26,26,0.15) ${volume * 100}%, rgba(26,26,26,0.15) 100%)`,
            }}
          />
        ) : (
          <div className="text-[10px] font-bold text-slate-400 tracking-widest uppercase opacity-0 group-hover:opacity-100 transition-opacity">
            点击播放
          </div>
        )}
      </div>
    </div>
  );
};

export default Mixer;

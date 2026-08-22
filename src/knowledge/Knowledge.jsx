import { useEffect, useState } from 'react';
import { ChevronDown, Ban, Lightbulb, Target } from 'lucide-react';
import { TRACKS, XINGCE, SHENLUN } from './canon.js';

const packOf = (id) => (id === 'shenlun' ? SHENLUN : XINGCE);

const TypeCard = ({ t, open, onToggle }) => (
  <article className="rounded-3xl bg-white border border-[#e8d5b0] overflow-hidden">
    <button
      type="button"
      onClick={onToggle}
      className="w-full flex items-center justify-between gap-4 px-6 py-4 text-left"
    >
      <div className="min-w-0">
        <h4 className="text-base font-black tracking-tight">{t.name}</h4>
        <p className="text-xs text-slate-500 font-medium mt-1 leading-relaxed">{t.how}</p>
      </div>
      <ChevronDown
        size={18}
        className={`flex-shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`}
      />
    </button>
    {open && (
      <div className="px-6 pb-6 space-y-5 border-t border-[#e8d5b0]/70">
        <section className="pt-5">
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">怎么做</p>
          <ol className="space-y-2">
            {t.steps.map((s, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed">
                <span className="w-5 h-5 rounded-full bg-[#1a1a1a] text-white text-[10px] font-black flex items-center justify-center flex-shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </section>
        {t.know?.length > 0 && (
          <section>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2 flex items-center gap-1.5">
              <Lightbulb size={11} /> 知识点
            </p>
            <ul className="space-y-1.5">
              {t.know.map((s, i) => (
                <li key={i} className="text-sm leading-relaxed pl-3 border-l-2 border-[#c4ae7a]">
                  {s}
                </li>
              ))}
            </ul>
          </section>
        )}
        {t.ban?.length > 0 && (
          <section>
            <p className="text-[10px] font-black uppercase tracking-widest text-[#a15c3a] mb-2 flex items-center gap-1.5">
              <Ban size={11} /> 禁止
            </p>
            <ul className="space-y-1">
              {t.ban.map((s, i) => (
                <li key={i} className="text-sm text-[#6b3f2a] leading-relaxed">
                  {s}
                </li>
              ))}
            </ul>
          </section>
        )}
        {t.anchors?.length > 0 && (
          <section>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">真题锚点</p>
            <ul className="space-y-1">
              {t.anchors.map((s, i) => (
                <li key={i} className="text-sm text-slate-600 leading-relaxed">
                  {s}
                </li>
              ))}
            </ul>
          </section>
        )}
        {t.next && (
          <p className="flex items-start gap-2 rounded-2xl bg-[#1a1a1a] text-white px-4 py-3 text-sm font-bold">
            <Target size={14} className="flex-shrink-0 mt-0.5 opacity-70" />
            <span>下次：{t.next}</span>
          </p>
        )}
      </div>
    )}
  </article>
);

export default function Knowledge() {
  const [track, setTrack] = useState('xingce');
  const pack = packOf(track);
  const [modId, setModId] = useState(pack.modules[0]?.id || '');
  const [openId, setOpenId] = useState(pack.modules[0]?.types[0]?.id || '');

  useEffect(() => {
    const next = packOf(track);
    const first = next.modules[0];
    setModId(first?.id || '');
    setOpenId(first?.types[0]?.id || '');
  }, [track]);

  const mod = pack.modules.find((m) => m.id === modId) || pack.modules[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {TRACKS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTrack(t.id)}
            className={`px-5 py-2.5 rounded-full text-sm font-black transition-all ${
              track === t.id
                ? 'bg-[#1a1a1a] text-white'
                : 'bg-white border border-[#e8d5b0] text-slate-500 hover:border-[#1a1a1a]'
            }`}
          >
            {t.name}
            <span className="ml-2 text-[10px] font-bold opacity-60">{t.hint}</span>
          </button>
        ))}
      </div>

      <div className="rounded-3xl bg-[#1a1a1a] text-white p-6">
        <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-2">
          {pack.intro.title}
        </p>
        <div className="space-y-2 text-sm leading-relaxed opacity-90">
          {pack.intro.lines.map((l) => (
            <p key={l}>{l}</p>
          ))}
        </div>
        {pack.intro.bans?.length > 0 && (
          <p className="mt-3 text-xs opacity-70">
            {pack.intro.bans.join(' · ')}
          </p>
        )}
      </div>

      {pack.modules.length === 0 ? (
        <div className="rounded-3xl bg-white border border-[#e8d5b0] p-10 text-center text-sm text-slate-500 font-medium">
          申论步骤还没写进老师口径。真题上传并要求补的时候再填。
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[14rem_1fr] gap-6 items-start">
          <nav className="lg:sticky lg:top-0 flex lg:flex-col gap-2 overflow-x-auto [scrollbar-width:none]">
            {pack.modules.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  setModId(m.id);
                  setOpenId(m.types[0]?.id || '');
                }}
                className={`flex-shrink-0 text-left px-4 py-3 rounded-2xl transition-all ${
                  m.id === mod?.id
                    ? 'bg-[#1a1a1a] text-white'
                    : 'bg-white border border-[#e8d5b0] hover:border-[#1a1a1a]'
                }`}
              >
                <p className="text-sm font-black">{m.name}</p>
                <p className={`text-[10px] font-bold mt-0.5 ${m.id === mod?.id ? 'opacity-60' : 'text-slate-400'}`}>
                  {m.qty} · {m.types.length} 种题型
                </p>
              </button>
            ))}
          </nav>

          <div className="space-y-4 min-w-0">
            {mod && (
              <>
                <div>
                  <h3 className="text-xl font-black tracking-tight">
                    {mod.name}
                    <span className="ml-2 text-sm font-bold text-slate-400">{mod.qty}</span>
                  </h3>
                  <p className="text-sm text-slate-500 mt-1 leading-relaxed">{mod.blurb}</p>
                </div>
                {mod.types.map((t) => (
                  <TypeCard
                    key={t.id}
                    t={t}
                    open={openId === t.id}
                    onToggle={() => setOpenId((id) => (id === t.id ? '' : t.id))}
                  />
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

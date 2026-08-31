import { useEffect, useState } from 'react';
import { ChevronLeft, Check, X, ScanSearch } from 'lucide-react';
import { generate } from './generators.js';
import { playBgm, stopBgm } from './bgm.js';
import { playCorrect, playWrong } from './sfx.js';
import BgmControls from './BgmControls.jsx';

const FONT_SIZES = [
  { id: 's', label: '小', px: 16 },
  { id: 'm', label: '中', px: 20 },
  { id: 'l', label: '大', px: 26 },
  { id: 'xl', label: '特大', px: 32 },
];

const fmtClock = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
};

const fmtDuration = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  if (h > 0) return `${h}:${pad(m)}:${pad(sec)}`;
  return `${pad(m)}:${pad(sec)}`;
};

const MaterialText = ({ tokens, revealed, fontPx }) => (
  <p className="ziliao-material whitespace-pre-wrap break-words" style={{ fontSize: fontPx }}>
    {tokens.map((tok, i) =>
      revealed && tok.mark === 'target' ? (
        <mark
          key={i}
          className="rounded-md bg-emerald-400/85 px-0.5 text-black not-italic font-semibold"
        >
          {tok.text}
        </mark>
      ) : (
        <span key={i}>{tok.text}</span>
      ),
    )}
  </p>
);

const SelfReportSession = ({ session, setSession, onExit, onFinishRace }) => {
  const [nowTs, setNowTs] = useState(() => Date.now());
  const [revealed, setRevealed] = useState(false);
  const [frozenMs, setFrozenMs] = useState(null);
  const [fontId, setFontId] = useState('m');
  const ready = !!session?.ready;
  const isRace = session?.mode === 'race';
  const fontPx = FONT_SIZES.find((f) => f.id === fontId)?.px ?? 20;

  const handleReady = () => {
    if (!session || session.ready) return;
    const now = Date.now();
    setNowTs(now);
    setSession((s) => (s ? { ...s, ready: true, startedAt: now, questionStartedAt: now } : s));
    playBgm(isRace ? 'ranked' : 'training');
  };

  const handleExit = () => {
    stopBgm();
    onExit();
  };

  useEffect(() => {
    if (!ready) return undefined;
    const id = setInterval(() => setNowTs(Date.now()), 100);
    return () => clearInterval(id);
  }, [ready]);

  useEffect(() => () => stopBgm(), []);

  const reveal = () => {
    if (!session?.ready || revealed) return;
    setFrozenMs(Date.now() - session.questionStartedAt);
    setRevealed(true);
  };

  const settle = (isCorrect, skipped = false) => {
    if (!session?.ready) return;
    if (!revealed && !skipped) return;
    const timeMs = frozenMs ?? Date.now() - session.questionStartedAt;
    const rec = {
      prompt: session.current.prompt,
      answer: session.current.answer,
      userAnswer: skipped ? null : isCorrect ? '对' : '错',
      isCorrect: skipped ? false : isCorrect,
      skipped,
      timeMs,
      selfReport: true,
    };
    if (skipped) playWrong();
    else if (isCorrect) playCorrect();
    else playWrong();

    const newRecords = [...session.records, rec];
    if (session.mode === 'race' && session.index + 1 >= session.total) {
      onFinishRace(newRecords, session.catId, session.subId, session.subName);
      return;
    }
    setRevealed(false);
    setFrozenMs(null);
    setSession({
      ...session,
      index: session.index + 1,
      current: generate(session.genKey),
      questionStartedAt: Date.now(),
      records: newRecords,
    });
  };

  useEffect(() => {
    const onKey = (e) => {
      if (!session) return;
      if (!session.ready) {
        if (e.key === ' ') {
          e.preventDefault();
          handleReady();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          handleExit();
        }
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (!revealed) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          reveal();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          settle(false, true);
        }
        return;
      }
      if (e.key === '1' || e.key === 'y' || e.key === 'Y') {
        e.preventDefault();
        settle(true);
      } else if (e.key === '2' || e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        settle(false);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        settle(false, true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, revealed, frozenMs]);

  if (!session) return null;
  const { current, index, total, mode, records } = session;
  const elapsed = Math.max(0, frozenMs ?? (ready ? nowTs - session.questionStartedAt : 0));
  const totalElapsed = Math.max(0, ready ? nowTs - session.startedAt : 0);
  const totalStr = total === Infinity ? '∞' : String(total);
  const progress = `${index + 1} / ${totalStr}`;
  const correctCount = records.filter((r) => r.isCorrect).length;
  const hasMaterial = Array.isArray(current.material);
  const fontNeeded = hasMaterial;

  return (
    <div className="max-w-3xl mx-auto relative pb-8">
      <BgmControls position="top-right" />
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={handleExit}
          className="flex items-center space-x-2 text-slate-400 hover:text-black transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-xs font-black uppercase tracking-widest">直接退出</span>
        </button>
        <div className="text-xs font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
          {isRace && (
            <span className="px-2 py-0.5 rounded-full bg-[#ff6b6b]/10 text-[#ff6b6b] text-[10px] tracking-widest">
              排位
            </span>
          )}
          <span>
            {session.subName} · {mode === 'race' ? '晋升模式' : '训练模式'}
          </span>
        </div>
        <span className="w-16" />
      </div>

      <div className="relative">
        <div
          className={`bg-[#1a1a1a] text-white rounded-[2.5rem] p-7 md:p-9 shadow-xl shadow-black/10 relative overflow-hidden ${
            isRace && ready ? 'race-bg' : ''
          }`}
        >
          <div className="relative z-10">
            <div className="flex items-center justify-between text-xs font-black uppercase tracking-widest opacity-60 mb-6">
              <span>{progress}</span>
              <span className="flex items-center space-x-3 tabular-nums">
                <span>本题 {fmtClock(elapsed)}</span>
                <span className="opacity-40">·</span>
                <span>总计 {fmtDuration(totalElapsed)}</span>
              </span>
            </div>

            {current.tag && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#ff6b6b]/15 text-[#ff6b6b] text-[10px] font-black tracking-widest mb-3">
                <ScanSearch size={12} />
                {current.tag}
              </span>
            )}
            {current.hint && (
              <p className="text-xs font-medium text-white/45 mb-3">{current.hint}</p>
            )}
            <p className="text-xl md:text-2xl font-black leading-snug tracking-tight whitespace-pre-wrap">
              {current.prompt}
            </p>

            {current.formula && (
              <div className="mt-5 rounded-2xl bg-white/8 border border-white/10 px-4 py-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-1">
                  {current.formula.title}
                </p>
                <p className="font-black text-[#e8d5b0] tabular-nums">{current.formula.text}</p>
              </div>
            )}

            {current.checklist && (
              <div className="mt-3 flex flex-wrap gap-2">
                {current.checklist.map((item) => (
                  <span
                    key={item.label}
                    className={`text-[11px] font-bold px-2.5 py-1 rounded-full border ${
                      revealed
                        ? 'bg-emerald-500/20 border-emerald-400/40 text-emerald-200'
                        : 'bg-white/8 border-white/15 text-white/70'
                    }`}
                  >
                    {revealed ? '✓ ' : ''}
                    {item.label}
                  </span>
                ))}
              </div>
            )}

            {hasMaterial && (
              <div className="mt-5">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/40">
                    {revealed ? '目标已标出' : '读材料定位'}
                    {current.kind === 'findAdv' && current.checklist
                      ? ` · 需找 ${current.checklist.length} 处`
                      : ' · 找到即完成'}
                  </p>
                  {fontNeeded && (
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] font-black tracking-widest text-white/35 mr-1">
                        材料字号
                      </span>
                      {FONT_SIZES.map((f) => (
                        <button
                          key={f.id}
                          onClick={() => setFontId(f.id)}
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-black ${
                            fontId === f.id
                              ? 'bg-[#e8d5b0] text-[#1a1a1a]'
                              : 'bg-white/10 text-white/60 hover:bg-white/15'
                          }`}
                        >
                          {f.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="rounded-2xl bg-[#f2e4c4] text-[#1a1a1a] p-4 md:p-5 max-h-[58vh] overflow-y-auto">
                  <MaterialText tokens={current.material} revealed={revealed} fontPx={fontPx} />
                </div>
              </div>
            )}

            {revealed && (
              <div className="mt-5 rounded-2xl bg-[#fef3c7] text-[#1a1a1a] p-4 md:p-5">
                <p className="text-[10px] font-black uppercase tracking-widest text-[#7c2d12]/70 mb-1">
                  {current.kind === 'spot' ? '判别依据' : '定位依据'}
                </p>
                <p className="text-sm font-bold leading-relaxed">{current.reason}</p>
                <p className="mt-2 text-sm font-black">
                  答案 · {current.answer}
                </p>
                {current.concepts?.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {current.concepts.map((c) => (
                      <span
                        key={c}
                        className="text-[10px] font-black px-2 py-0.5 rounded-full bg-[#1a1a1a] text-[#e8d5b0]"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-[11px] font-medium text-slate-500">生成预览 · 对照后自己点对或错</p>
              </div>
            )}

            <div className="mt-6">
              {!revealed ? (
                <button
                  onClick={reveal}
                  className="w-full bg-[#ff6b6b] text-white font-black py-4 rounded-2xl hover:brightness-110 transition-all tracking-widest text-sm"
                >
                  完成
                </button>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => settle(true)}
                    className="flex items-center justify-center gap-2 bg-emerald-500 text-white font-black py-4 rounded-2xl hover:brightness-110 transition-all"
                  >
                    <Check size={18} strokeWidth={3} />
                    对
                  </button>
                  <button
                    onClick={() => settle(false)}
                    className="flex items-center justify-center gap-2 bg-[#ff6b6b] text-white font-black py-4 rounded-2xl hover:brightness-110 transition-all"
                  >
                    <X size={18} strokeWidth={3} />
                    错
                  </button>
                </div>
              )}
            </div>

            <div className="mt-5 flex items-center justify-between text-[10px] font-black uppercase tracking-widest opacity-40">
              <span>{revealed ? '1 对 · 2 错 · Esc 跳过' : 'Enter / 空格 完成 · Esc 跳过'}</span>
              <span>
                自报正确 {correctCount} / 已答 {records.length}
              </span>
            </div>
          </div>
        </div>

        {!ready && (
          <div
            className="absolute inset-0 z-30 rounded-[2.5rem] overflow-hidden flex items-center justify-center cursor-pointer"
            onClick={handleReady}
            role="button"
            tabIndex={0}
            aria-label="按空格开始"
          >
            <div className="absolute inset-0 bg-[#1a1a1a]/95 backdrop-blur-md" />
            <div className="relative text-center px-6">
              <div className="text-[10px] font-black uppercase tracking-[0.4em] text-white/50 mb-3">
                {isRace ? 'RANKED · SELF REPORT' : 'TRAINING · SELF REPORT'}
              </div>
              <div
                className="inline-block text-4xl md:text-5xl font-black italic mb-4"
                style={{ color: isRace ? '#ff6b6b' : '#8d7348' }}
              >
                按 SPACE 开始
              </div>
              <p className="text-sm font-medium text-white/60">
                想好后点完成看答案，自己点对或错。排位全凭自觉。
              </p>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .race-bg::before {
          content: '';
          position: absolute;
          inset: 0;
          background: radial-gradient(ellipse at top, rgba(255,107,107,0.08), transparent 60%);
          pointer-events: none;
        }
      `}</style>
    </div>
  );
};

export default SelfReportSession;

import { useEffect, useMemo, useState } from 'react';
import { Ban, ChevronDown, Lightbulb, Pencil, Plus, Target, Trash2 } from 'lucide-react';
import { TRACKS, XINGCE, SHENLUN } from './canon.js';
import { consumeKnowledgeFocus, KNOWLEDGE_OPEN_EVENT } from './nav.js';
import { api } from '../api.js';
import { cloudGet, cloudSet } from '../cloudStorage.js';

const OVERRIDE_KEY = 'knowledge_overrides_v1';
const packOf = (id) => (id === 'shenlun' ? SHENLUN : XINGCE);

const emptyOverrides = () => ({ cards: {}, extras: {} });

const loadOverrides = () => {
  const raw = cloudGet(OVERRIDE_KEY, emptyOverrides());
  if (!raw || typeof raw !== 'object') return emptyOverrides();
  return {
    cards: raw.cards && typeof raw.cards === 'object' ? raw.cards : {},
    extras: raw.extras && typeof raw.extras === 'object' ? raw.extras : {},
  };
};

function scoreOf(row) {
  if (!row) return null;
  if (row.score != null) return Number(row.score);
  if (row.mastery != null) return Number(row.mastery);
  if (row.attempts > 0) return Math.round((row.correct * 100) / row.attempts);
  return null;
}

function masteryHint(row) {
  if (!row) return '';
  const parts = [];
  if (row.attempts > 0) parts.push(`${row.correct || 0}/${row.attempts} 次`);
  if (row.mastery_confidence != null) parts.push(`置信度 ${row.mastery_confidence}%`);
  if (row.mastery_samples != null) parts.push(`有效样本 ${row.mastery_samples}`);
  if (row.mastery_source === 'manual') parts.push('人工覆盖');
  return parts.join(' · ');
}

function relatedRows(type, rows) {
  const name = type.name || '';
  if (!name) return [];
  return rows.filter((r) => {
    const k = r.kaodian || '';
    if (k === name || k.endsWith(`-${name}`) || k.includes(name) || name.includes(k)) return true;
    const sub = r.subtype || '';
    return Boolean(sub && (sub.includes(name) || name.includes(sub)));
  });
}

function cardRow(type, rows) {
  const hits = relatedRows(type, rows);
  if (!hits.length) return { score: null, hits, row: null };
  const exact = hits.find((r) => r.kaodian === type.name);
  const row = exact || [...hits].sort((a, b) => (b.attempts || 0) - (a.attempts || 0))[0];
  return { score: scoreOf(row), hits, row };
}

const MASTERY_COLORS = ['#e24b4b', '#ef7d3a', '#e6b423', '#9cc43a', '#4caf50', '#2a9d5c'];

function MasteryBar({ score, hint }) {
  const known = Number.isFinite(score);
  const v = known ? Math.max(0, Math.min(100, Math.round(score))) : null;
  const lit = known ? Math.max(1, Math.round((v / 100) * MASTERY_COLORS.length)) : 0;
  const word = !known ? '还没接触' : v < 40 ? '生疏' : v < 70 ? '半会' : v < 90 ? '较稳' : '拿手';
  const label = known ? `${v}% · ${word}` : word;
  return (
    <span className="inline-flex items-end gap-1 flex-shrink-0" title={[label, hint].filter(Boolean).join(' · ')} aria-label={label}>
      <span
        className="inline-flex items-end gap-[2px]"
        style={{ transform: 'skewX(-18deg) translateY(1px)' }}
      >
        {MASTERY_COLORS.map((c, i) => (
          <span
            key={i}
            className="block rounded-[1px]"
            style={{
              width: 4,
              height: 13,
              background: i < lit ? c : '#d5d0c6',
            }}
          />
        ))}
      </span>
      <span className="text-[10px] font-bold text-slate-400 whitespace-nowrap">
        {known ? `${v}%` : '未评估'}
      </span>
    </span>
  );
}

function joinLines(list) {
  return Array.isArray(list) ? list.join('\n') : '';
}

function splitLines(text) {
  return String(text || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
}

function TypeCard({ t, open, onToggle, rows, override, onSave, onDelete }) {
  const { score, hits, row } = cardRow(t, rows);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const view = { ...t, ...override };

  const startEdit = (e) => {
    e.stopPropagation();
    setDraft({
      name: view.name || '',
      how: view.how || '',
      steps: joinLines(view.steps),
      know: joinLines(view.know),
      next: view.next || '',
      ban: joinLines(view.ban),
      mine: view.mine || '',
    });
    setEditing(true);
    if (!open) onToggle();
  };

  const save = (e) => {
    e?.stopPropagation();
    onSave({
      name: draft.name.trim() || t.name,
      how: draft.how.trim(),
      steps: splitLines(draft.steps),
      know: splitLines(draft.know),
      next: draft.next.trim(),
      ban: splitLines(draft.ban),
      mine: draft.mine.trim(),
    });
    setEditing(false);
  };

  return (
    <article className="rounded-3xl bg-white border border-[#e8d5b0] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-4 px-6 py-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 min-w-0">
            <h4 className="text-base font-black tracking-tight">{view.name}</h4>
            <MasteryBar
              score={score}
              hint={[row?.mastery_note, masteryHint(row), hits.length > 1 ? `${hits.length} 个相关考点` : ''].filter(Boolean).join(' · ')}
            />
            {t.custom ? (
              <span className="text-[10px] font-black text-[#8a6d3b] bg-[#f6ecd4] px-2 py-0.5 rounded-full">自补</span>
            ) : null}
          </div>
          <p className="text-xs text-slate-500 font-medium mt-1 leading-relaxed">{view.how}</p>
        </div>
        <ChevronDown
          size={18}
          className={`flex-shrink-0 text-slate-400 transition-transform mt-1 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="px-6 pb-6 space-y-5 border-t border-[#e8d5b0]/70">
          <div className="pt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={startEdit}
              className="inline-flex items-center gap-1.5 text-xs font-black px-3 py-1.5 rounded-full border border-[#e8d5b0] hover:border-[#1a1a1a]"
            >
              <Pencil size={11} /> 改口径
            </button>
            {t.custom && onDelete ? (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onDelete(); }}
                className="inline-flex items-center gap-1.5 text-xs font-black px-3 py-1.5 rounded-full text-[#a15c3a] border border-[#ead5c8]"
              >
                <Trash2 size={11} /> 删掉
              </button>
            ) : null}
          </div>

          {editing && draft ? (
            <div className="space-y-3 rounded-2xl bg-[#faf6ec] p-4">
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                名称
                <input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm font-bold"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                一句话怎么做
                <input
                  value={draft.how}
                  onChange={(e) => setDraft({ ...draft, how: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                步骤（一行一步）
                <textarea
                  value={draft.steps}
                  onChange={(e) => setDraft({ ...draft, steps: e.target.value })}
                  rows={5}
                  className="mt-1 w-full rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm leading-relaxed"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                要记住的点（一行一条）
                <textarea
                  value={draft.know}
                  onChange={(e) => setDraft({ ...draft, know: e.target.value })}
                  rows={4}
                  className="mt-1 w-full rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm leading-relaxed"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                禁止
                <textarea
                  value={draft.ban}
                  onChange={(e) => setDraft({ ...draft, ban: e.target.value })}
                  rows={3}
                  className="mt-1 w-full rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm leading-relaxed"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                下次就做这一下
                <input
                  value={draft.next}
                  onChange={(e) => setDraft({ ...draft, next: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                我自己的笔记
                <textarea
                  value={draft.mine}
                  onChange={(e) => setDraft({ ...draft, mine: e.target.value })}
                  rows={3}
                  className="mt-1 w-full rounded-xl border border-[#e8d5b0] bg-white px-3 py-2 text-sm leading-relaxed"
                />
              </label>
              <div className="flex gap-2">
                <button type="button" onClick={save} className="px-4 py-2 rounded-full bg-[#1a1a1a] text-white text-xs font-black">
                  存下来
                </button>
                <button type="button" onClick={() => setEditing(false)} className="px-4 py-2 rounded-full text-xs font-black text-slate-500">
                  取消
                </button>
              </div>
            </div>
          ) : (
            <>
              {view.steps?.length > 0 && (
                <section>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">怎么做</p>
                  <ol className="space-y-2">
                    {view.steps.map((s, i) => (
                      <li key={i} className="flex gap-3 text-sm leading-relaxed">
                        <span className="w-5 h-5 rounded-full bg-[#1a1a1a] text-white text-[10px] font-black flex items-center justify-center flex-shrink-0 mt-0.5">
                          {i + 1}
                        </span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {view.know?.length > 0 && (
                <section>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2 flex items-center gap-1.5">
                    <Lightbulb size={11} /> 要记住
                  </p>
                  <ul className="space-y-1.5">
                    {view.know.map((s, i) => (
                      <li key={i} className="text-sm leading-relaxed pl-3 border-l-2 border-[#c4ae7a]">{s}</li>
                    ))}
                  </ul>
                </section>
              )}
              {view.ban?.length > 0 && (
                <section>
                  <p className="text-[10px] font-black uppercase tracking-widest text-[#a15c3a] mb-2 flex items-center gap-1.5">
                    <Ban size={11} /> 禁止
                  </p>
                  <ul className="space-y-1">
                    {view.ban.map((s, i) => (
                      <li key={i} className="text-sm text-[#6b3f2a] leading-relaxed">{s}</li>
                    ))}
                  </ul>
                </section>
              )}
              {view.anchors?.length > 0 && (
                <section>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">真题锚点</p>
                  <ul className="space-y-1">
                    {view.anchors.map((s, i) => (
                      <li key={i} className="text-sm text-slate-600 leading-relaxed">{s}</li>
                    ))}
                  </ul>
                </section>
              )}
              {view.next && (
                <p className="flex items-start gap-2 rounded-2xl bg-[#1a1a1a] text-white px-4 py-3 text-sm font-bold">
                  <Target size={14} className="flex-shrink-0 mt-0.5 opacity-70" />
                  <span>下次：{view.next}</span>
                </p>
              )}
              {view.mine && (
                <p className="rounded-2xl bg-[#f6ecd4] px-4 py-3 text-sm leading-relaxed">{view.mine}</p>
              )}
            </>
          )}

          {hits.length > 0 && (
            <section>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">练过 / Hermes 记过</p>
              <div className="space-y-2">
                {hits.map((h) => (
                  <div key={h.kaodian} className="rounded-2xl border border-[#f0e4c8] px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <p className="text-sm font-bold truncate">{h.kaodian}</p>
                        <MasteryBar score={scoreOf(h)} hint={[h.mastery_note, masteryHint(h)].filter(Boolean).join(' · ')} />
                      </div>
                      <p className="text-[10px] text-slate-400 font-bold flex-shrink-0">
                        {h.attempts ? `${h.correct}/${h.attempts}` : '对话'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </article>
  );
}

function ProfileList({ rows, onAdd }) {
  const [name, setName] = useState('');
  const [module, setModule] = useState('判断推理');
  const groups = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      const key = r.module || '未分类';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(r);
    }
    return [...map.entries()];
  }, [rows]);

  return (
    <div className="space-y-6">
      <div className="rounded-3xl bg-white border border-[#e8d5b0] p-5 space-y-3">
        <p className="text-sm font-black">补一个考点</p>
        <div className="flex flex-wrap gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="模块-一级-二级，或现有短标签"
            className="flex-1 min-w-[16rem] rounded-xl border border-[#e8d5b0] px-3 py-2 text-sm"
          />
          <input
            value={module}
            onChange={(e) => setModule(e.target.value)}
            placeholder="模块"
            className="w-32 rounded-xl border border-[#e8d5b0] px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => {
              const kaodian = name.trim();
              if (!kaodian) return;
              onAdd(kaodian, module.trim() || kaodian.split('-')[0]);
              setName('');
            }}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-[#1a1a1a] text-white text-xs font-black"
          >
            <Plus size={12} /> 加上
          </button>
        </div>
      </div>
      {groups.length === 0 ? (
        <div className="rounded-3xl bg-white border border-[#e8d5b0] p-10 text-center text-sm text-slate-500">
          练习或跟 Hermes 聊过之后，考点会落在这里。
        </div>
      ) : (
        groups.map(([mod, items]) => (
          <section key={mod} className="space-y-3">
            <h3 className="text-lg font-black tracking-tight">{mod}</h3>
            <div className="space-y-3">
              {items.map((r) => (
                <article key={r.kaodian} className="rounded-3xl bg-white border border-[#e8d5b0] px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-black">{r.kaodian}</p>
                        <MasteryBar score={scoreOf(r)} hint={[r.mastery_note, r.note, masteryHint(r)].filter(Boolean).join(' · ')} />
                      </div>
                      <p className="text-[11px] text-slate-400 font-bold mt-0.5">
                        {[r.subtype, r.attempts ? `${r.correct}/${r.attempts} 次` : '还没做题'].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}

export default function Knowledge() {
  const [track, setTrack] = useState('xingce');
  const pack = packOf(track);
  const [modId, setModId] = useState(pack.modules[0]?.id || '');
  const [openId, setOpenId] = useState(pack.modules[0]?.types[0]?.id || '');
  const [rows, setRows] = useState([]);
  const [overrides, setOverrides] = useState(loadOverrides);

  const persist = (next) => {
    setOverrides(next);
    cloudSet(OVERRIDE_KEY, next);
  };

  useEffect(() => {
    const apply = (detail) => {
      if (!detail?.moduleId || !detail?.typeId) return;
      setTrack(detail.track || 'xingce');
      setModId(detail.moduleId);
      setOpenId(detail.typeId);
    };
    apply(consumeKnowledgeFocus());
    const onOpen = (e) => apply(e.detail);
    window.addEventListener(KNOWLEDGE_OPEN_EVENT, onOpen);
    return () => window.removeEventListener(KNOWLEDGE_OPEN_EVENT, onOpen);
  }, []);

  useEffect(() => {
    const load = () => {
      api('/api/kaodian')
        .then((d) => setRows(d?.items || []))
        .catch(() => {});
    };
    load();
    const onVis = () => {
      if (document.visibilityState === 'visible') load();
    };
    document.addEventListener('visibilitychange', onVis);
    const timer = setInterval(load, 20000);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      clearInterval(timer);
    };
  }, []);

  const selectTrack = (nextTrack) => {
    setTrack(nextTrack);
    if (nextTrack === 'mine') return;
    const next = packOf(nextTrack);
    const first = next.modules[0];
    setModId(first?.id || '');
    setOpenId(first?.types[0]?.id || '');
  };

  const extras = overrides.extras[modId] || [];
  const mod = pack.modules.find((m) => m.id === modId) || pack.modules[0];
  const types = [...(mod?.types || []), ...extras];
  const used = new Set();
  for (const t of types) {
    for (const r of relatedRows(t, rows)) used.add(r.kaodian);
  }
  const leftover = rows.filter((r) => r.module === mod?.name && !used.has(r.kaodian));

  const saveCard = (id, patch, custom) => {
    if (custom) {
      const list = (overrides.extras[modId] || []).map((c) => (c.id === id ? { ...c, ...patch } : c));
      persist({ ...overrides, extras: { ...overrides.extras, [modId]: list } });
      return;
    }
    persist({ ...overrides, cards: { ...overrides.cards, [id]: { ...(overrides.cards[id] || {}), ...patch } } });
  };

  const addExtra = () => {
    const id = `custom-${Date.now()}`;
    const card = {
      id,
      name: '新知识点',
      how: '用一句话写你真正会用的动作，不要空话。',
      steps: ['先写判断条件', '再写下手动作', '最后写一眼能验的收口'],
      know: [],
      next: '',
      ban: [],
      custom: true,
    };
    persist({ ...overrides, extras: { ...overrides.extras, [modId]: [...(overrides.extras[modId] || []), card] } });
    setOpenId(id);
  };

  const removeExtra = (id) => {
    persist({
      ...overrides,
      extras: { ...overrides.extras, [modId]: (overrides.extras[modId] || []).filter((c) => c.id !== id) },
    });
    if (openId === id) setOpenId('');
  };

  const addProfile = async (kaodian, module) => {
    try {
      const row = await api('/api/kaodian/mastery', {
        method: 'POST',
        body: { kaodian, note: '自己补的考点，先记着', module },
      });
      setRows((prev) => {
        const rest = prev.filter((r) => r.kaodian !== row.kaodian);
        return [...rest, row];
      });
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {TRACKS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => selectTrack(t.id)}
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
        <button
          type="button"
          onClick={() => selectTrack('mine')}
          className={`px-5 py-2.5 rounded-full text-sm font-black transition-all ${
            track === 'mine'
              ? 'bg-[#1a1a1a] text-white'
              : 'bg-white border border-[#e8d5b0] text-slate-500 hover:border-[#1a1a1a]'
          }`}
        >
          我的考点
          <span className="ml-2 text-[10px] font-bold opacity-60">{rows.length}</span>
        </button>
      </div>

      {track === 'mine' ? (
        <ProfileList rows={rows} onAdd={addProfile} />
      ) : (
        <>
          <div className="rounded-3xl bg-[#1a1a1a] text-white p-6">
            <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-2">
              {pack.intro.title}
            </p>
            <div className="space-y-2 text-sm leading-relaxed opacity-90">
              {pack.intro.lines.map((l) => (
                <p key={l}>{l}</p>
              ))}
            </div>
            <p className="mt-3 text-xs opacity-70">
              名字右边那排斜条是掌握度：没接触过全灰，亮起来从红到绿。跟 Hermes 聊题、复盘、改错，它都会按你当时的实际情况改。口径不够用就点「改口径」，或自己补一张。
            </p>
          </div>

          {pack.modules.length === 0 ? (
            <div className="rounded-3xl bg-white border border-[#e8d5b0] p-10 text-center text-sm text-slate-500 font-medium">
              申论步骤还没写进老师口径。真题上传并要求补的时候再填。
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-[14rem_1fr] gap-6 items-start">
              <nav className="lg:sticky lg:top-0 flex lg:flex-col lg:items-center gap-2 overflow-x-auto [scrollbar-width:none]">
                {pack.modules.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      setModId(m.id);
                      setOpenId(m.types[0]?.id || '');
                    }}
                    className={`flex-shrink-0 w-full max-w-[14rem] text-center px-4 py-3 rounded-2xl transition-all ${
                      m.id === mod?.id
                        ? 'bg-[#1a1a1a] text-white'
                        : 'bg-white border border-[#e8d5b0] hover:border-[#1a1a1a]'
                    }`}
                  >
                    <p className="text-sm font-black">{m.name}</p>
                    <p className={`text-[10px] font-bold mt-0.5 ${m.id === mod?.id ? 'opacity-60' : 'text-slate-400'}`}>
                      {m.qty}
                    </p>
                  </button>
                ))}
              </nav>

              <div className="space-y-4 min-w-0">
                {mod && (
                  <>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-xl font-black tracking-tight">
                          {mod.name}
                          <span className="ml-2 text-sm font-bold text-slate-400">{mod.qty}</span>
                        </h3>
                        <p className="text-sm text-slate-500 mt-1 leading-relaxed">{mod.blurb}</p>
                      </div>
                      <button
                        type="button"
                        onClick={addExtra}
                        className="flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-full bg-white border border-[#e8d5b0] text-xs font-black hover:border-[#1a1a1a]"
                      >
                        <Plus size={12} /> 补一张
                      </button>
                    </div>
                    {types.map((t) => (
                      <TypeCard
                        key={t.id}
                        t={t}
                        open={openId === t.id}
                        onToggle={() => setOpenId((id) => (id === t.id ? '' : t.id))}
                        rows={rows}
                        override={overrides.cards[t.id]}
                        onSave={(patch) => saveCard(t.id, patch, t.custom)}
                        onDelete={t.custom ? () => removeExtra(t.id) : undefined}
                      />
                    ))}
                    {leftover.length > 0 && (
                      <section className="pt-2 space-y-3">
                        <h4 className="text-sm font-black text-slate-500">这个模块里还对不上卡片的考点</h4>
                        {leftover.map((r) => (
                          <article key={r.kaodian} className="rounded-3xl bg-white border border-dashed border-[#e8d5b0] px-5 py-4">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-black">{r.kaodian}</p>
                        <MasteryBar score={scoreOf(r)} hint={[r.mastery_note, r.note, masteryHint(r)].filter(Boolean).join(' · ')} />
                            </div>
                          </article>
                        ))}
                      </section>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

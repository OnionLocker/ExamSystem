import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Pencil, Plus, Target, Trash2, GitBranch, Lightbulb, ShieldAlert, BookOpen } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { TRACKS } from './canon.js';
import { consumeKnowledgeFocus, KNOWLEDGE_OPEN_EVENT } from './nav.js';
import { api } from '../api.js';
import { cloudGet, cloudSet } from '../cloudStorage.js';
import { cardRow as matchCardRow } from './match.js';
import { decorateMath } from './cardMarkdown.js';
import {
  cardsForNode,
  leftoverRows,
  mergeFenbiTree,
  methodCardsFor,
  aliasMapFrom,
} from './fenbiTree.js';
import DebtDashboard from './DebtDashboard.jsx';
import 'katex/dist/katex.min.css';
import '../hermes/katex-fix.css';

const OVERRIDE_KEY = 'knowledge_overrides_v1';
const KAODIAN_CACHE_KEY = 'kaodian_cache_v1';

function loadKaodianCache() {
  try {
    const raw = JSON.parse(localStorage.getItem(KAODIAN_CACHE_KEY) || 'null');
    if (!raw || !Array.isArray(raw.items)) return { items: [], aliases: [] };
    return { items: raw.items, aliases: Array.isArray(raw.aliases) ? raw.aliases : [] };
  } catch {
    return { items: [], aliases: [] };
  }
}

function saveKaodianCache(items, aliases) {
  try {
    localStorage.setItem(KAODIAN_CACHE_KEY, JSON.stringify({ items, aliases }));
  } catch {
    /* quota / private mode */
  }
}

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

function cardRow(type, rows) {
  return matchCardRow(type, rows, scoreOf);
}

const headingText = (node) => {
  if (node == null) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(headingText).join('');
  if (node?.props?.children) return headingText(node.props.children);
  return '';
};

const CARD_MD = {
  h4({ children }) {
    const title = headingText(children);
    const danger = title.includes('禁止');
    return (
      <p className={`text-[13px] font-black tracking-widest mb-2.5 mt-5 first:mt-0 ${
        danger ? 'text-[#a15c3a]' : 'text-slate-500'
      }`}
      >
        {children}
      </p>
    );
  },
  ol({ children }) {
    return <ol className="list-decimal pl-6 space-y-2.5 text-[17px] leading-8 marker:font-black marker:text-slate-400">{children}</ol>;
  },
  ul({ children }) {
    return <ul className="list-disc pl-6 space-y-2 text-[17px] leading-8 marker:text-[#c4ae7a]">{children}</ul>;
  },
  li({ children }) {
    return <li className="pl-0.5">{children}</li>;
  },
  p({ children }) {
    return <p className="text-[17px] leading-8 my-1.5">{children}</p>;
  },
  strong({ children }) {
    return <strong className="font-black text-[#1a1a1a]">{children}</strong>;
  },
};

const KATEX_OPTIONS = {
  throwOnError: false,
  strict: false,
  macros: { '\\frac': '\\dfrac' },
  minRuleThickness: 0.07,
};

const MASTERY_COLORS = ['#e24b4b', '#ef7d3a', '#e6b423', '#9cc43a', '#4caf50', '#2a9d5c'];

function MasteryBar({ score, hint, pending, kind }) {
  const known = Number.isFinite(score);
  const v = known ? Math.max(0, Math.min(100, Math.round(score))) : null;
  const lit = known ? Math.max(1, Math.round((v / 100) * MASTERY_COLORS.length)) : 0;
  const word = pending && !known
    ? '读取中'
    : !known
      ? '还没接触'
      : kind === 'rollup'
        ? '综合覆盖'
        : v < 40 ? '生疏' : v < 70 ? '半会' : v < 90 ? '较稳' : '拿手';
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
      <span className="text-xs font-bold text-slate-400 whitespace-nowrap">
        {known ? `${v}%` : pending ? '…' : '未评估'}
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

function InlineMarkdown({ text }) {
  if (!text) return null;
  return (
    <span className="katex-inline-host inline">
      <ReactMarkdown
        remarkPlugins={[[remarkGfm, { singleTilde: false }], remarkMath]}
        rehypePlugins={[[rehypeKatex, KATEX_OPTIONS]]}
        components={{
          p: ({ children }) => <span>{children}</span>,
          strong: ({ children }) => <strong className="font-black text-[#1a1a1a]">{children}</strong>,
        }}
      >
        {text}
      </ReactMarkdown>
    </span>
  );
}

function parseStep(raw, idx) {
  const line = decorateMath(raw);
  const colonIdx = line.search(/[：:]/);
  if (colonIdx > 0 && colonIdx <= 45) {
    return {
      title: line.slice(0, colonIdx).trim(),
      desc: line.slice(colonIdx + 1).trim(),
      isBranch: true,
      idx,
    };
  }
  return {
    title: `步骤 ${idx + 1}`,
    desc: line,
    isBranch: false,
    idx,
  };
}

function StructuredKnowledgeView({ view }) {
  const steps = Array.isArray(view?.steps) ? view.steps.filter(Boolean) : [];
  const parsedSteps = steps.map((s, i) => parseStep(s, i));
  const isBranchMode = parsedSteps.filter((s) => s.isBranch).length >= 2;
  const knowItems = Array.isArray(view?.know) ? view.know.filter(Boolean) : [];
  const banItems = Array.isArray(view?.ban) ? view.ban.filter(Boolean) : [];
  const anchorItems = Array.isArray(view?.anchors) ? view.anchors.filter(Boolean) : [];

  return (
    <div className="space-y-5 pt-3">
      {/* 题型分支决策树 / 解题步骤 */}
      {parsedSteps.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            {isBranchMode ? (
              <>
                <GitBranch size={15} className="text-[#8a6d3b] flex-shrink-0" />
                <h5 className="text-[13px] font-black tracking-widest text-[#8a6d3b] uppercase">
                  核心题型考法与应对策略（{parsedSteps.length} 类模型分支）
                </h5>
              </>
            ) : (
              <h5 className="text-[13px] font-black tracking-widest text-slate-500 uppercase">
                解题步骤与固定动作
              </h5>
            )}
          </div>

          {isBranchMode ? (
            <div className="grid grid-cols-1 gap-3">
              {parsedSteps.map((step, i) => (
                <div
                  key={i}
                  className="rounded-2xl border border-[#c4ae7a] bg-[#f5eed8] p-4 transition-all hover:border-[#a89968] shadow-sm"
                >
                  <div className="flex items-center gap-2.5 mb-2 flex-wrap">
                    <span className="text-[11px] font-black px-2 py-0.5 rounded-md bg-[#1a1a1a] text-[#fdfbf7] tracking-wide">
                      考法 {i + 1}
                    </span>
                    <h6 className="text-[16px] font-black text-[#1a1a1a]">
                      {step.title.replace(/^(?:考法[一二三四五六七八九十\d\s·•]+|题型[一二三四五六七八九十\d\s·•]+)/, '') || step.title}
                    </h6>
                  </div>
                  <div className="text-[15px] leading-7 text-slate-700 pl-1">
                    <InlineMarkdown text={step.desc} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <ol className="list-decimal pl-6 space-y-2.5 text-[16px] leading-7 marker:font-black marker:text-slate-400">
              {parsedSteps.map((step, i) => (
                <li key={i} className="pl-1">
                  <InlineMarkdown text={step.desc} />
                </li>
              ))}
            </ol>
          )}
        </section>
      )}

      {/* 必记要点与公式 */}
      {knowItems.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-2.5">
            <Lightbulb size={15} className="text-[#c4ae7a] flex-shrink-0" />
            <h5 className="text-[13px] font-black tracking-widest text-[#8a6d3b] uppercase">
              核心要点与速算公式
            </h5>
          </div>
          <div className="rounded-2xl border border-[#c4ae7a] bg-[#f5eed8] p-4 space-y-2.5 shadow-sm">
            {knowItems.map((k, i) => (
              <div key={i} className="flex items-start gap-2.5 text-[15px] leading-7 text-slate-800">
                <span className="w-1.5 h-1.5 rounded-full bg-[#c4ae7a] mt-2.5 flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <InlineMarkdown text={decorateMath(k)} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 考场红线禁区 */}
      {banItems.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-2.5">
            <ShieldAlert size={15} className="text-[#a15c3a] flex-shrink-0" />
            <h5 className="text-[13px] font-black tracking-widest text-[#a15c3a] uppercase">
              考场红线禁区（避坑避雷）
            </h5>
          </div>
          <div className="rounded-2xl border border-[#ddb896] bg-[#f8ede0] p-4 space-y-2 shadow-sm">
            {banItems.map((b, i) => (
              <div key={i} className="flex items-start gap-2.5 text-[15px] leading-7 text-[#913b28]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#a15c3a] mt-2.5 flex-shrink-0" />
                <div className="min-w-0 flex-1 font-medium">
                  <InlineMarkdown text={decorateMath(b)} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 下次就做这一下 */}
      {view.next && (
        <div className="flex items-start gap-2.5 rounded-2xl bg-[#1a1a1a] text-white px-4 py-3.5 text-[16px] font-bold leading-7 shadow-sm">
          <Target size={17} className="flex-shrink-0 mt-1 text-[#f7e6a7]" />
          <span>下次动作：{view.next}</span>
        </div>
      )}

      {/* 真题锚点 */}
      {anchorItems.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="inline-flex items-center gap-1 text-xs font-bold text-slate-400">
            <BookOpen size={13} /> 真题锚点：
          </span>
          {anchorItems.map((a, i) => (
            <span key={i} className="text-xs font-medium text-slate-600 bg-[#f4ece0] px-2.5 py-1 rounded-full border border-[#e8d5b0]">
              {a}
            </span>
          ))}
        </div>
      )}

      {/* 个人笔记 */}
      {view.mine && (
        <div className="rounded-2xl bg-[#f6ecd4] border border-[#ebdcb9] px-4 py-3 text-[15px] leading-7 text-slate-800 shadow-sm">
          <span className="font-bold text-[#8a6d3b] mr-1">我的笔记：</span>
          {view.mine}
        </div>
      )}
    </div>
  );
}

function localCardTitle(name, index) {
  const body = String(name || '').replace(/^\d+\s+/, '');
  return `${String(index + 1).padStart(2, '0')} ${body}`;
}

function TypeCard({ t, title, open, onToggle, rows, override, onSave, onDelete, scoresPending }) {
  const { score, hits, row } = cardRow(t, rows);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const view = { ...t, ...override, name: title || t.name };

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
    <article className="rounded-3xl bg-[#f5eed8] border border-[#c4ae7a] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-4 px-6 py-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 min-w-0">
            <h4 className="text-lg font-black tracking-tight">{view.name}</h4>
            <MasteryBar
              score={score}
              pending={scoresPending}
              hint={[row?.mastery_note, masteryHint(row), hits.length > 1 ? `${hits.length} 个相关考点` : ''].filter(Boolean).join(' · ')}
            />
            {t.custom ? (
              <span className="text-[10px] font-black text-[#8a6d3b] bg-[#f6ecd4] px-2 py-0.5 rounded-full">自补</span>
            ) : null}
          </div>
          <p className="text-sm text-slate-500 font-medium mt-1 leading-relaxed">{view.how}</p>
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
            <div className="space-y-3 rounded-2xl bg-[#e8d5b0] p-4">
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                名称
                <input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#c4ae7a] bg-[#f5eed8] px-3 py-2 text-sm font-bold"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                一句话怎么做
                <input
                  value={draft.how}
                  onChange={(e) => setDraft({ ...draft, how: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#c4ae7a] bg-[#f5eed8] px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                步骤（一行一步）
                <textarea
                  value={draft.steps}
                  onChange={(e) => setDraft({ ...draft, steps: e.target.value })}
                  rows={5}
                  className="mt-1 w-full rounded-xl border border-[#c4ae7a] bg-[#f5eed8] px-3 py-2 text-sm leading-relaxed"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                要记住的点（一行一条）
                <textarea
                  value={draft.know}
                  onChange={(e) => setDraft({ ...draft, know: e.target.value })}
                  rows={4}
                  className="mt-1 w-full rounded-xl border border-[#c4ae7a] bg-[#f5eed8] px-3 py-2 text-sm leading-relaxed"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                禁止
                <textarea
                  value={draft.ban}
                  onChange={(e) => setDraft({ ...draft, ban: e.target.value })}
                  rows={3}
                  className="mt-1 w-full rounded-xl border border-[#c4ae7a] bg-[#f5eed8] px-3 py-2 text-sm leading-relaxed"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                下次就做这一下
                <input
                  value={draft.next}
                  onChange={(e) => setDraft({ ...draft, next: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#c4ae7a] bg-[#f5eed8] px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400">
                我自己的笔记
                <textarea
                  value={draft.mine}
                  onChange={(e) => setDraft({ ...draft, mine: e.target.value })}
                  rows={3}
                  className="mt-1 w-full rounded-xl border border-[#c4ae7a] bg-[#f5eed8] px-3 py-2 text-sm leading-relaxed"
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
            <StructuredKnowledgeView view={view} />
          )}

          {hits.length > 0 && (
            <section>
              <p className="text-[13px] font-black tracking-widest text-slate-500 mb-2">练过 / Hermes 记过</p>
              <div className="space-y-2">
                {hits.map((h) => (
                  <div key={h.kaodian} className="rounded-2xl border border-[#f0e4c8] px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <p className="text-base font-bold truncate">{h.kaodian}</p>
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

function FenbiTree({ modules, selectedTag, onSelect, filterScored, scoresPending }) {
  const [openL2, setOpenL2] = useState(() => new Set(modules[0]?.children?.map((g) => g.name) || []));
  const [openL3, setOpenL3] = useState(() => new Set());

  const toggleL2 = (name) => {
    setOpenL2((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const toggleL3 = (tag, e) => {
    e?.stopPropagation();
    setOpenL3((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  return (
    <div className="space-y-3">
      {modules.map((mod) => (
        <div key={mod.id} className="space-y-2">
          {(mod.children || []).map((group) => {
            const leaves = filterScored
              ? (group.children || []).filter((leaf) => leaf.score != null || leaf.extensions?.length)
              : (group.children || []);
            if (filterScored && !leaves.length) return null;
            const open = openL2.has(group.name);
            return (
              <section key={group.name} className="rounded-2xl border border-[#c4ae7a] overflow-hidden bg-[#e8d5b0]">
                <button
                  type="button"
                  onClick={() => toggleL2(group.name)}
                  className="w-full min-h-[48px] flex items-center justify-between gap-3 px-4 py-3 text-left"
                >
                  <span className="text-[15px] font-black tracking-tight">{group.name}</span>
                  <ChevronDown size={16} className={`text-[#8a6d3b] transition-transform ${open ? 'rotate-180' : ''}`} />
                </button>
                {open && (
                  <div className="px-2 pb-2 space-y-1.5">
                    {leaves.map((leaf) => {
                      const selected = selectedTag === leaf.tag;
                      const hasExt = Boolean(leaf.extensions?.length);
                      const isL3Open = openL3.has(leaf.tag);
                      return (
                        <div key={leaf.tag}>
                          <div
                            className={`w-full min-h-[48px] flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left border cursor-pointer transition-all ${
                              selected
                                ? 'bg-[#f6ecd4] border-[#cbb387]'
                                : 'bg-[#fdfbf7] border-[#e8d5b0] hover:border-[#cbb387]'
                            }`}
                            onClick={() => onSelect(leaf)}
                          >
                            <span className="text-[15px] font-bold min-w-0 truncate">{leaf.name}</span>
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                              <MasteryBar
                                score={leaf.score}
                                kind={leaf.score_kind}
                                pending={scoresPending}
                                hint={leaf.row ? [leaf.row.mastery_note, masteryHint(leaf.row)].filter(Boolean).join(' · ') : ''}
                              />
                              {hasExt && (
                                <button
                                  type="button"
                                  onClick={(e) => toggleL3(leaf.tag, e)}
                                  className="p-1 -mr-1 text-slate-400 hover:text-[#1a1a1a] rounded-lg transition-colors"
                                  title={isL3Open ? '收起子考点' : '展开子考点'}
                                >
                                  <ChevronDown
                                    size={15}
                                    className={`text-[#8a6d3b] transition-transform duration-200 ${
                                      isL3Open ? 'rotate-180' : ''
                                    }`}
                                  />
                                </button>
                              )}
                            </div>
                          </div>
                          {hasExt && isL3Open && (
                            <div className="mt-1 space-y-1">
                              {leaf.extensions.map((ext) => (
                                <button
                                  key={ext.tag}
                                  type="button"
                                  onClick={() => onSelect({ ...leaf, ...ext, name: ext.name, tag: ext.tag, isL4: true })}
                                  className={`ml-4 w-[calc(100%-1rem)] min-h-[44px] flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-left border ${
                                    selectedTag === ext.tag
                                      ? 'bg-[#f6ecd4] border-[#cbb387]'
                                      : 'bg-[#f6ecd4]/70 border-[#e8d5b0] hover:border-[#cbb387]'
                                  }`}
                                >
                                  <span className="text-sm font-bold min-w-0 truncate">{ext.name}</span>
                                  <MasteryBar score={ext.score} pending={scoresPending} hint={ext.row ? masteryHint(ext.row) : ''} />
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default function Knowledge({ onSeedHermes }) {
  const [track, setTrack] = useState('xingce');
  const [view, setView] = useState('tree'); // 'tree' or 'debts'
  const [modId, setModId] = useState('shuliang');
  const [selectedTag, setSelectedTag] = useState('数量关系-数学运算-平均数问题');
  const [openId, setOpenId] = useState('');
  const [kaodian, setKaodian] = useState(loadKaodianCache);
  const [scoresReady, setScoresReady] = useState(() => loadKaodianCache().items.length > 0);
  const [overrides, setOverrides] = useState(loadOverrides);
  const rows = kaodian.items;
  const aliases = kaodian.aliases;
  const detailRef = useRef(null);

  const persist = (next) => {
    setOverrides(next);
    cloudSet(OVERRIDE_KEY, next);
  };

  useEffect(() => {
    const apply = (detail) => {
      if (!detail) return;
      setTrack(detail.track || 'xingce');
      if (detail.moduleId) setModId(detail.moduleId);
      if (detail.tag) setSelectedTag(detail.tag);
      if (detail.typeId) setOpenId(detail.typeId);
    };
    apply(consumeKnowledgeFocus());
    const onOpen = (e) => apply(e.detail);
    window.addEventListener(KNOWLEDGE_OPEN_EVENT, onOpen);
    return () => window.removeEventListener(KNOWLEDGE_OPEN_EVENT, onOpen);
  }, []);

  useEffect(() => {
    const load = () => {
      api('/api/kaodian')
        .then((d) => {
          const items = d?.items || [];
          const nextAliases = d?.aliases || [];
          setKaodian({ items, aliases: nextAliases });
          setScoresReady(true);
          saveKaodianCache(items, nextAliases);
        })
        .catch(() => { setScoresReady(true); });
    };
    load();
    const onVis = () => {
      if (document.visibilityState === 'visible') load();
    };
    document.addEventListener('visibilitychange', onVis);
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, 20000);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    detailRef.current?.scrollTo({ top: 0 });
  }, [selectedTag]);

  const tree = useMemo(() => mergeFenbiTree(rows, aliases), [rows, aliases]);
  const fenbiMod = tree.find((m) => m.id === modId) || tree[0];
  const aliasLookup = useMemo(() => aliasMapFrom(aliases), [aliases]);
  const leftover = useMemo(() => leftoverRows(rows, aliasLookup), [rows, aliasLookup]);

  const selectedLeaf = useMemo(() => {
    if (!fenbiMod || !selectedTag) return null;
    for (const group of fenbiMod.children || []) {
      for (const leaf of group.children || []) {
        if (leaf.tag === selectedTag) return leaf;
        const ext = (leaf.extensions || []).find((item) => item.tag === selectedTag);
        if (ext) return { ...leaf, ...ext, name: ext.name, tag: ext.tag, isL4: true };
      }
    }
    return null;
  }, [fenbiMod, selectedTag]);

  const extras = overrides.extras[modId] || [];
  const mappedCards = selectedLeaf ? cardsForNode(selectedLeaf, fenbiMod) : methodCardsFor(fenbiMod);
  const types = [...mappedCards, ...extras];

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

  const selectTrack = (nextTrack) => {
    setTrack(nextTrack);
    if (nextTrack === 'shenlun') {
      setModId('');
      setSelectedTag('');
    }
  };

  const pill = (active) =>
    `min-h-[44px] px-5 py-2.5 rounded-full text-sm font-black transition-all ${
      active ? 'bg-[#1a1a1a] text-white' : 'bg-[#e8d5b0] border border-[#c4ae7a] text-[#6b5428] hover:border-[#1a1a1a]'
    }`;

  return (
    <div className="h-full min-h-0 flex flex-col gap-4">
      <div className="flex-shrink-0 flex flex-wrap items-center gap-2">
        {TRACKS.map((t) => (
          <button key={t.id} type="button" onClick={() => selectTrack(t.id)} className={pill(track === t.id)}>
            {t.name}
            <span className="ml-2 text-[10px] font-bold opacity-60">{t.hint}</span>
          </button>
        ))}
        <button type="button" onClick={() => selectTrack('mine')} className={pill(track === 'mine')}>
          我的考点
          <span className="ml-2 text-[10px] font-bold opacity-60">{rows.length}</span>
        </button>
      </div>

      {track !== 'shenlun' && (
        <div className="flex-shrink-0 flex gap-2">
          <button
            type="button"
            onClick={() => setView('tree')}
            className={`min-h-[40px] px-4 py-2 rounded-full text-sm font-bold ${
              view === 'tree' ? 'bg-[#1a1a1a] text-white' : 'bg-[#e8d5b0] border border-[#c4ae7a] text-[#6b5428]'
            }`}
          >
            知识树
          </button>
          <button
            type="button"
            onClick={() => setView('debts')}
            className={`min-h-[40px] px-4 py-2 rounded-full text-sm font-bold ${
              view === 'debts' ? 'bg-[#1a1a1a] text-white' : 'bg-[#e8d5b0] border border-[#c4ae7a] text-[#6b5428]'
            }`}
          >
            知识债
          </button>
        </div>
      )}

      {track === 'shenlun' ? (
        <div className="rounded-3xl bg-[#f5eed8] border border-[#c4ae7a] p-10 text-center text-sm text-slate-600 font-medium">
          申论步骤还没写进老师口径。真题上传并要求补的时候再填。
        </div>
      ) : view === 'debts' ? (
        <DebtDashboard onSeedHermes={onSeedHermes} />
      ) : (
        <>
          <div className="flex-shrink-0 rounded-3xl bg-[#1a1a1a] text-white px-5 py-3">
            <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-1">粉笔广东·省市类树</p>
            <p className="text-sm leading-relaxed opacity-90">
              政治 / 常识 / 言语 / 数量 / 判断按粉笔一级→二级展开。右边斜条是掌握度，旧长标签通过别名对到新节点，画像不会清零。
              Hermes 要更细的叶子，登记成 `模块-一级-二级-子题型`，刷新后挂在对应二级下面。
            </p>
          </div>

          <nav className="flex-shrink-0 flex gap-2 overflow-x-auto [scrollbar-width:none]">
            {tree.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  setModId(m.id);
                  const first = m.children?.[0]?.children?.[0];
                  setSelectedTag(first?.tag || '');
                  setOpenId('');
                }}
                className={`flex-shrink-0 min-h-[48px] min-w-[7.5rem] px-4 py-3 rounded-2xl text-center ${
                  m.id === fenbiMod?.id ? 'bg-[#1a1a1a] text-white' : 'bg-[#e8d5b0] border border-[#c4ae7a] text-[#6b5428]'
                }`}
              >
                <p className="text-sm font-black">{m.name}</p>
                <p className={`text-[10px] font-bold mt-0.5 ${m.id === fenbiMod?.id ? 'opacity-60' : 'text-slate-400'}`}>
                  {m.qty}
                </p>
              </button>
            ))}
          </nav>

          <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[22rem_1fr] gap-6">
            <div className="min-h-0 max-h-[40vh] xl:max-h-none overflow-y-auto overscroll-contain rounded-3xl border border-[#c4ae7a] bg-[#f5eed8] p-3">
              <FenbiTree
                modules={fenbiMod ? [fenbiMod] : []}
                selectedTag={selectedTag}
                filterScored={track === 'mine'}
                scoresPending={!scoresReady}
                onSelect={(leaf) => {
                  setSelectedTag(leaf.tag);
                  setOpenId('');
                }}
              />
            </div>

            <div ref={detailRef} className="min-h-0 overflow-y-auto overscroll-contain space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-xl font-black tracking-tight">
                    {selectedLeaf?.name || fenbiMod?.name}
                    <span className="ml-2 text-sm font-bold text-slate-400">{selectedLeaf?.tag || fenbiMod?.qty}</span>
                  </h3>
                  <p className="text-sm text-slate-500 mt-1 leading-relaxed">
                    {selectedLeaf?.tag || fenbiMod?.blurb}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={addExtra}
                  className="flex-shrink-0 min-h-[44px] inline-flex items-center gap-1.5 px-3 py-2 rounded-full bg-[#e8d5b0] border border-[#c4ae7a] text-xs font-black hover:border-[#1a1a1a]"
                >
                  <Plus size={12} /> 补一张
                </button>
              </div>
              {types.map((t, i) => (
                <TypeCard
                  key={t.id}
                  t={t}
                  title={t.custom ? t.name : localCardTitle(t.name, i)}
                  open={openId === t.id}
                  onToggle={() => setOpenId((id) => (id === t.id ? '' : t.id))}
                  rows={rows}
                  scoresPending={!scoresReady}
                  override={overrides.cards[t.id]}
                  onSave={(patch) => saveCard(t.id, patch, t.custom)}
                  onDelete={t.custom ? () => removeExtra(t.id) : undefined}
                />
              ))}
              {track === 'mine' && leftover.length > 0 && (
                <section className="pt-2 space-y-3">
                  <h4 className="text-sm font-black text-slate-500">还对不上粉笔树的旧标签 / 资料分析</h4>
                  {leftover.map((r) => (
                    <article key={r.kaodian} className="rounded-3xl bg-[#e8d5b0] border border-dashed border-[#c4ae7a] px-5 py-4">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-black">{r.kaodian}</p>
                        <MasteryBar score={scoreOf(r)} pending={!scoresReady} hint={[r.mastery_note, r.note, masteryHint(r)].filter(Boolean).join(' · ')} />
                      </div>
                    </article>
                  ))}
                </section>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

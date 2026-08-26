import { XINGCE, SHENLUN } from './canon.js';

const EVENT = 'examsystem:open-knowledge';

const packs = [
  { track: 'xingce', pack: XINGCE },
  { track: 'shenlun', pack: SHENLUN },
];

const fold = (s) => String(s || '').replace(/[·•、.．\s]/g, '').replace(/^\d+/, '');

const scoreName = (name, query) => {
  const n = fold(name);
  const q = fold(query);
  if (!n || !q || q.length < 2) return 0;
  if (n === q) return 1000;
  if (n.includes(q) || q.includes(n)) return Math.min(n.length, q.length);
  let best = 0;
  for (let i = 0; i < q.length; i += 1) {
    for (let j = i + 4; j <= q.length; j += 1) {
      if (n.includes(q.slice(i, j))) best = Math.max(best, j - i);
    }
  }
  return best;
};

export function findKnowledgeTarget(query) {
  const raw = String(query || '').replace(/^本题考察知识点[:：]\s*/, '').trim();
  if (!raw) return null;
  const pieces = raw.split(/[-—－/]/).map((s) => s.trim()).filter(Boolean);
  const queries = [raw, ...pieces].filter(Boolean);
  let best = null;
  let bestScore = 0;
  for (const { track, pack } of packs) {
    for (const mod of pack.modules || []) {
      for (const t of mod.types || []) {
        const s = Math.max(...queries.map((q) => scoreName(t.name, q)));
        if (s > bestScore) {
          bestScore = s;
          best = { track, moduleId: mod.id, typeId: t.id, name: t.name, module: mod.name };
        }
      }
    }
  }
  return bestScore >= 4 ? best : null;
}

let pending = null;

export function openKnowledge(query) {
  pending = findKnowledgeTarget(query) || { query: String(query || '').trim() };
  window.dispatchEvent(new CustomEvent(EVENT, { detail: pending }));
}

export function consumeKnowledgeFocus() {
  const v = pending;
  pending = null;
  return v;
}

export const KNOWLEDGE_OPEN_EVENT = EVENT;

import treeData from './fenbiTree.json' with { type: 'json' };
import { XINGCE } from './canon.js';
import { cardRow } from './match.js';

export const FENBI_MODULES = treeData.modules;
export const LEGACY_ALIASES = treeData.legacyAliases || {};

export function composeTag(module, l2, l3, l4 = '') {
  const tag = `${module}-${l2}-${l3}`;
  return l4 ? `${tag}-${l4}` : tag;
}

function indexModules() {
  return [...FENBI_MODULES]
    .map((mod) => ({
      ...mod,
      groups: [...(mod.children || [])]
        .map((group) => ({
          ...group,
          leaves: [...(group.children || [])].sort((a, b) => b.name.length - a.name.length),
        }))
        .sort((a, b) => b.name.length - a.name.length),
    }))
    .sort((a, b) => b.name.length - a.name.length);
}

const MODULE_INDEX = indexModules();

export function parseFenbiTag(tag) {
  const raw = String(tag || '').trim();
  if (!raw) return null;
  for (const mod of MODULE_INDEX) {
    if (raw !== mod.name && !raw.startsWith(`${mod.name}-`)) continue;
    const rest = raw === mod.name ? '' : raw.slice(mod.name.length + 1);
    for (const group of mod.groups) {
      if (rest !== group.name && !rest.startsWith(`${group.name}-`)) continue;
      const tail = rest === group.name ? '' : rest.slice(group.name.length + 1);
      for (const leaf of group.leaves) {
        if (tail === leaf.name) {
          return { module: mod.name, l2: group.name, l3: leaf.name, l4: '', moduleId: mod.id };
        }
        if (tail.startsWith(`${leaf.name}-`)) {
          return {
            module: mod.name,
            l2: group.name,
            l3: leaf.name,
            l4: tail.slice(leaf.name.length + 1),
            moduleId: mod.id,
          };
        }
      }
      return null;
    }
    return null;
  }
  return null;
}

export function fenbiL3Of(tag) {
  const parsed = parseFenbiTag(tag);
  return parsed ? composeTag(parsed.module, parsed.l2, parsed.l3) : '';
}

export function aliasMapFrom(aliases) {
  const map = new Map(Object.entries(LEGACY_ALIASES));
  const apply = (alias, canonical) => {
    if (!alias || !canonical) return;
    const existing = map.get(alias);
    // DB identity aliases (alias === canonical) must not clobber chalk-tree mappings.
    if (existing && fenbiL3Of(existing) && !fenbiL3Of(canonical)) return;
    map.set(alias, canonical);
  };
  if (aliases instanceof Map) {
    for (const [alias, canonical] of aliases) apply(alias, canonical);
    return map;
  }
  for (const row of aliases || []) apply(row?.alias, row?.canonical);
  return map;
}

export function resolveProfileTag(kaodian, aliases) {
  const raw = String(kaodian || '').trim();
  const map = aliases instanceof Map ? aliases : aliasMapFrom(aliases);
  const mapped = map.get(raw) || raw;
  return fenbiL3Of(mapped) || fenbiL3Of(raw) || mapped;
}

function scoreOf(row) {
  if (!row) return null;
  if (row.score != null) return Number(row.score);
  if (row.mastery != null) return Number(row.mastery);
  return null;
}

function pickScore(rows) {
  const usable = (rows || []).filter((row) => scoreOf(row) != null);
  if (!usable.length) return { score: null, row: rows?.[0] || null, hits: rows || [] };
  const ranked = [...usable].sort((a, b) => {
    const aConf = a.mastery_confidence || 0;
    const bConf = b.mastery_confidence || 0;
    if ((aConf >= 40) !== (bConf >= 40)) return aConf >= 40 ? -1 : 1;
    return (scoreOf(a) ?? 101) - (scoreOf(b) ?? 101);
  });
  return { score: scoreOf(ranked[0]), row: ranked[0], hits: rows };
}

function weightOf(row) {
  const samples = Number(row?.mastery_samples);
  if (Number.isFinite(samples) && samples > 0) return samples;
  const attempts = Number(row?.attempts);
  if (Number.isFinite(attempts) && attempts > 0) return attempts;
  return 1;
}

export function rollupScores(parts) {
  const usable = (parts || []).filter((part) => part && Number.isFinite(part.score));
  if (!usable.length) return { score: null, row: null, hits: [], samples: 0 };
  let wsum = 0;
  let ssum = 0;
  const hits = [];
  for (const part of usable) {
    const w = part.weight > 0 ? part.weight : 1;
    wsum += w;
    ssum += Number(part.score) * w;
    if (part.hits?.length) hits.push(...part.hits);
    else if (part.row) hits.push(part.row);
  }
  return {
    score: Math.round(ssum / wsum),
    row: usable[0].row || hits[0] || null,
    hits,
    samples: Math.round(wsum * 100) / 100,
  };
}

export function rowsForTag(tag, items, aliases) {
  const l3 = fenbiL3Of(tag) || tag;
  return (items || []).filter((row) => {
    const raw = row.kaodian || '';
    const resolved = resolveProfileTag(raw, aliases);
    if (raw === tag || resolved === tag) return true;
    if (l3 && (raw === l3 || resolved === l3 || raw.startsWith(`${l3}-`) || resolved.startsWith(`${l3}-`))) {
      return true;
    }
    return false;
  });
}

export function mergeFenbiTree(items, aliases) {
  const aliasLookup = aliasMapFrom(aliases);
  const extras = new Map();
  for (const row of items || []) {
    const raw = row.kaodian || '';
    const parsed = parseFenbiTag(raw) || parseFenbiTag(aliasLookup.get(raw) || '');
    if (parsed?.l4) {
      const parent = composeTag(parsed.module, parsed.l2, parsed.l3);
      const canonicalTag = composeTag(parsed.module, parsed.l2, parsed.l3, parsed.l4);
      if (!extras.has(parent)) extras.set(parent, []);
      const list = extras.get(parent);
      const existing = list.find((item) => item.tag === canonicalTag || item.name === parsed.l4);
      if (!existing) {
        list.push({
          tag: canonicalTag,
          name: parsed.l4,
          rows: [row],
        });
      } else {
        existing.rows.push(row);
      }
    }
  }

  return FENBI_MODULES.map((mod) => ({
    ...mod,
    children: (mod.children || []).map((group) => ({
      ...group,
      tag: `${mod.name}-${group.name}`,
      children: (group.children || []).map((leaf) => {
        const tag = composeTag(mod.name, group.name, leaf.name);
        const hits = rowsForTag(tag, items, aliasLookup);
        const extra = extras.get(tag) || [];
        const cards = (leaf.cards || []).map((id) => CARD_INDEX.get(id)).filter(Boolean);
        const cardParts = cards.map((type) => {
          const found = cardRow(type, items, scoreOf);
          return {
            score: found.score,
            weight: weightOf(found.row),
            row: found.row,
            hits: found.hits,
          };
        });
        const extParts = extra.map((item) => {
          const found = pickScore(item.rows || [item.row]);
          return { score: found.score, weight: weightOf(found.row), row: found.row, hits: item.rows || [item.row] };
        });
        const children = [...cardParts, ...extParts];
        const rolled = children.length > 1 ? rollupScores(children) : null;
        const fallback = pickScore(hits);
        const direct = hits.find(row => row.kaodian === tag || aliasLookup.get(row.kaodian) === tag);
        return {
          ...leaf,
          tag,
          ...(rolled?.score != null ? { ...rolled, score_kind: 'rollup' } : fallback),
          ...(hits.some(row => row.assessment) ? { row: direct || null, score_kind: direct ? 'direct' : 'rollup' } : {}),
          extensions: extra.map((item) => ({
            tag: item.tag,
            name: item.name,
            ...pickScore(item.rows || [item.row]),
          })),
        };
      }),
    })),
  }));
}

const CARD_INDEX = (() => {
  const map = new Map();
  for (const mod of XINGCE.modules || []) {
    for (const type of mod.types || []) {
      map.set(type.id, { ...type, moduleId: mod.id, moduleName: mod.name });
    }
  }
  return map;
})();

export function cardsForNode(node, module) {
  const ids = [...(node?.cards || []), ...(module?.methodCards && node?.name === module.name ? module.methodCards : [])];
  return ids.map((id) => CARD_INDEX.get(id)).filter(Boolean);
}

export function methodCardsFor(module) {
  return (module?.methodCards || []).map((id) => CARD_INDEX.get(id)).filter(Boolean);
}

export function findFenbiTarget(query) {
  const raw = String(query || '').replace(/^本题考察知识点[:：]\s*/, '').trim();
  if (!raw) return null;
  const aliased = LEGACY_ALIASES[raw];
  if (aliased) {
    const mapped = parseFenbiTag(aliased);
    if (mapped) {
      return {
        track: 'xingce',
        moduleId: mapped.moduleId,
        tag: composeTag(mapped.module, mapped.l2, mapped.l3, mapped.l4),
        name: mapped.l4 || mapped.l3,
        module: mapped.module,
      };
    }
  }
  const parsed = parseFenbiTag(raw);
  if (parsed) {
    return {
      track: 'xingce',
      moduleId: parsed.moduleId,
      tag: composeTag(parsed.module, parsed.l2, parsed.l3, parsed.l4),
      name: parsed.l4 || parsed.l3,
      module: parsed.module,
    };
  }
  const pieces = raw.split(/[-—－/]/).map((s) => s.trim()).filter(Boolean);
  let best = null;
  let bestScore = 0;
  for (const mod of FENBI_MODULES) {
    for (const group of mod.children || []) {
      for (const leaf of group.children || []) {
        const tag = composeTag(mod.name, group.name, leaf.name);
        const names = [leaf.name, group.name, tag];
        for (const name of names) {
          for (const piece of [raw, ...pieces]) {
            if (!piece || piece.length < 2) continue;
            if (name === piece || tag === piece) {
              return { track: 'xingce', moduleId: mod.id, tag, name: leaf.name, module: mod.name };
            }
            if (name.includes(piece) || piece.includes(name)) {
              const score = Math.min(name.length, piece.length);
              if (score > bestScore) {
                bestScore = score;
                best = { track: 'xingce', moduleId: mod.id, tag, name: leaf.name, module: mod.name };
              }
            }
          }
        }
      }
    }
  }
  return bestScore >= 3 ? best : null;
}

export function leftoverRows(items, aliases) {
  const aliasLookup = aliasMapFrom(aliases);
  return (items || []).filter((row) => {
    const raw = row.kaodian || '';
    if (raw.startsWith('资料分析-')) return true;
    const resolved = aliasLookup.get(raw) || raw;
    return !parseFenbiTag(raw) && !parseFenbiTag(resolved);
  });
}

export function cardTitleKey(name) {
  return String(name || '')
    .replace(/^\d+\s+/, '')
    .replace(/[“”"']/g, '')
    .trim();
}

export function relatedRows(type, rows) {
  const name = cardTitleKey(type?.name);
  if (!name) return [];
  return (rows || []).filter((row) => {
    const kaodian = row.kaodian || '';
    const subtype = row.subtype || '';
    if (kaodian === type.name || kaodian.endsWith(`-${name}`) || kaodian.includes(name)) return true;
    if (subtype && subtype.length >= 8 && (name.includes(subtype) || subtype.includes(name))) return true;
    return false;
  });
}

export function cardRow(type, rows, scoreOf) {
  const hits = relatedRows(type, rows);
  if (!hits.length) return { score: null, hits, row: null };
  const exact = hits.find((row) => row.kaodian === type.name);
  const ranked = [...hits].sort((a, b) => {
    const aConf = a.mastery_confidence || 0;
    const bConf = b.mastery_confidence || 0;
    if ((aConf >= 40) !== (bConf >= 40)) return aConf >= 40 ? -1 : 1;
    return (scoreOf(a) ?? 101) - (scoreOf(b) ?? 101);
  });
  const row = exact || ranked[0];
  return { score: scoreOf(row), hits, row };
}

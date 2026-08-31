const ZILIAO_OLD_TO_CARD = {
  '资料分析-简单计算与查找-直接查找': '基础知识-统计术语与常考概念',
  '资料分析-倍数-倍数计算': '基础知识-统计术语与常考概念',
  '资料分析-基期量-基期量计算': 'ABRX类-基期量计算与比较',
  '资料分析-增长率-同比增长率': 'ABRX类-增长率计算模型',
  '资料分析-增长量-增长量计算与比较': 'ABRX类-增长量计算与现期推算',
  '资料分析-比重-比重计算与比较': '比重类-现期、基期与隔级比重',
  '资料分析-比重-两期比重差': '比重类-比重趋势、比重差与比值差',
  '资料分析-增长率-年均增长率': '平均类-一般平均值与年均增速/增量',
  '资料分析-平均数-现期平均数': '平均类-一般平均值与年均增速/增量',
};

export function cardTitleKey(name) {
  return String(name || '')
    .replace(/^\d+\s+/, '')
    .replace(/[“”"']/g, '')
    .replace(/[·•]/g, '-')
    .replace(/\s+/g, '')
    .trim();
}

export function relatedRows(type, rows) {
  const name = cardTitleKey(type?.name);
  if (!name) return [];
  return (rows || []).filter((row) => {
    const kaodian = row.kaodian || '';
    const subtype = row.subtype || '';
    const folded = cardTitleKey(kaodian);
    if (kaodian === type.name || kaodian.endsWith(`-${name}`) || kaodian.includes(name)) return true;
    if (folded === name || folded.endsWith(`-${name}`) || folded.includes(name)) return true;
    if (ZILIAO_OLD_TO_CARD[kaodian] === name) return true;
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

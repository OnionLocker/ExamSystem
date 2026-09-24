// AI 练题 / Hermes 复盘共用的日练模块识别与命名。
// 「图形题目」是外采带图包（slug: tuxing），不是 Gemini 日更科目。

export const MODULES = [
  '政治理论',
  '常识判断',
  '言语理解与表达',
  '判断推理',
  '科学推理',
  '图形题目',
  '数量关系',
  '资料分析',
];

export const DAILY_SLUG = {
  yanyu: '言语理解与表达',
  verbal: '言语理解与表达',
  panduan: '判断推理',
  judg: '判断推理',
  kepui: '科学推理',
  kexue: '科学推理',
  tuxing: '图形题目',
  shuliang: '数量关系',
  quantity: '数量关系',
  ziliao: '资料分析',
  'data-analysis': '资料分析',
};

const DAILY_DATE_RE = /^daily-(\d{8})-/;
const DAILY_SLUG_RE = /^daily-\d{8}-([a-z]+(?:-[a-z]+)*)-/i;
const FIGURE_RE = /图形题目|(?:^|[^a-z])tuxing(?:[^a-z]|$)/i;

const blobOf = (item = {}) =>
  [
    item.module,
    item.category,
    item.source,
    item.batch_id,
    item.display_title,
  ].map((value) => String(value || '')).join(' ');

export function moduleFromBatchId(batchId) {
  const match = String(batchId || '').match(DAILY_SLUG_RE);
  if (!match) return '';
  return DAILY_SLUG[match[1].toLowerCase()] || '';
}

export function dailySourceName(module, compactDate) {
  return `广东省考行测-${module}-${compactDate}`;
}

export function dailySourceFromBatchId(batchId, fallbackModule = '') {
  const match = String(batchId || '').match(DAILY_DATE_RE);
  if (!match) return '';
  const module = moduleFromBatchId(batchId) || fallbackModule;
  if (!module) return '';
  return dailySourceName(module, match[1]);
}

export function moduleOf(item = {}) {
  const text = blobOf(item);
  if (FIGURE_RE.test(text)) return '图形题目';
  if (MODULES.includes(item.module)) return item.module;
  if (MODULES.includes(item.category)) return item.category;
  const fromId = moduleFromBatchId(item.batch_id || item.category);
  if (fromId) return fromId;
  const lower = text.toLowerCase();
  if (lower.includes('政治理论')) return '政治理论';
  if (lower.includes('常识判断') || lower.includes('常识应用')) return '常识判断';
  if (lower.includes('言语理解与表达') || lower.includes('yanyu') || lower.includes('verbal')) {
    return '言语理解与表达';
  }
  if (lower.includes('科学推理') || lower.includes('kepui') || lower.includes('kexue')) {
    return '科学推理';
  }
  if (lower.includes('判断推理') || lower.includes('panduan') || lower.includes('judg')) {
    return '判断推理';
  }
  if (lower.includes('数量关系') || lower.includes('shuliang') || lower.includes('quantity')) {
    return '数量关系';
  }
  if (lower.includes('资料分析') || lower.includes('ziliao') || lower.includes('data-analysis')) {
    return '资料分析';
  }
  return '';
}

export function dailyDateOf(item = {}) {
  const planned = String(item.daily_plan_date || '').slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(planned)) return planned;
  const match = `${item.batch_id || ''} ${item.category || ''}`.match(/daily-(\d{4})(\d{2})(\d{2})-/);
  if (match) return `${match[1]}-${match[2]}-${match[3]}`;
  return '';
}

export function nameOf(item = {}) {
  const date = dailyDateOf(item);
  const module = moduleOf(item);
  if (date && module) return `广东省考行测-${module}-${date.replaceAll('-', '')}`;
  return item.source || item.display_title || item.batch_id || '未命名题组';
}

export function stampDailySource(manifest, questions, materials) {
  const name = dailySourceFromBatchId(
    manifest?.batch_id,
    manifest?.module || manifest?.category || '',
  );
  if (!name) return name;
  manifest.source = name;
  const module = moduleFromBatchId(manifest.batch_id) || manifest.module;
  if (module) manifest.module = module;
  for (const question of questions || []) {
    if (question && typeof question === 'object') question.source = name;
  }
  for (const material of materials || []) {
    if (material && typeof material === 'object') material.source = name;
  }
  return name;
}

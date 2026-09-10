// AI 练题复盘组装 / 后处理 / 校验
// 不依赖真实练习库。报告侧补建议用时；产出侧按对错分流并去掉空夸奖诊断。

import {
  EMPTY_PRAISE_RE,
  NEWS_FLUFF_RE,
  hasNextActionKoujue,
  hasWrongCause,
  isEmptyPraise,
  resolveSuggestedTime,
} from './reviewSpec.js';

export function formatDuration(sec) {
  const total = Math.max(0, Math.floor(Number(sec) || 0));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

export function compareToSuggested(timeSpentSec, suggested) {
  if (timeSpentSec == null || Number.isNaN(Number(timeSpentSec))) {
    return { kind: 'none', label: '无用时，仅保留建议用时' };
  }
  const spent = Math.max(0, Number(timeSpentSec) || 0);
  const max = suggested?.max ?? 60;
  const min = suggested?.min ?? 0;
  if (spent > max) {
    return { kind: 'over', label: `超时 ${spent - max}s`, spent, max };
  }
  if (spent < min) {
    return { kind: 'fast', label: `快 ${min - spent}s`, spent, max };
  }
  return { kind: 'ok', label: '达标', spent, max };
}

export function formatAnswerResult({
  userAnswer,
  correctAnswer,
  timeSpentSec,
  suggested,
  skipped,
} = {}) {
  const suggestedLabel = suggested?.label || resolveSuggestedTime({}).label;
  const comparison = compareToSuggested(
    skipped ? null : timeSpentSec,
    suggested || resolveSuggestedTime({}),
  );
  const spentText = skipped || timeSpentSec == null
    ? '用时 —'
    : `用时 ${formatDuration(timeSpentSec)}`;
  const compareText = comparison.kind === 'none'
    ? comparison.label
    : comparison.label;
  return `**作答结果**：你的答案 ${skipped ? '未作答' : (userAnswer || '未作答')} · 正确答案 ${correctAnswer || '未知'} · ${spentText} · 建议用时 ${suggestedLabel}（${compareText}）`;
}

export function formatStatsLine({ timeSpentSec, suggested, hasDraft } = {}) {
  const range = suggested || resolveSuggestedTime({});
  const comparison = compareToSuggested(timeSpentSec, range);
  const draftNote = hasDraft
    ? '有草稿时可判断慢在读题/建模翻译/排除，不要编逐步秒数'
    : '无草稿，只做总时长对照，禁止编造逐步秒数';
  return `用时对照：${comparison.kind === 'none' ? '无用时' : formatDuration(timeSpentSec)} · 建议 ${range.label} · ${comparison.label}（估算，非画像）。${draftNote}。`;
}

const section = (title, body) => {
  const text = String(body || '').trim();
  if (!text) return [];
  return [`#### ${title}`, '', text, ''];
};

export function assembleCoachReview(input = {}) {
  const {
    index = 1,
    typeName = '题型',
    stem = '',
    options = [],
    userAnswer,
    correctAnswer,
    isCorrect = false,
    skipped = false,
    timeSpentSec,
    knowledge,
    hasDraft = false,
    draftDiagnosis,
    standardAnalysis,
    examMethod,
    nextAction,
    deepTip,
  } = input;
  const suggested = input.suggested || resolveSuggestedTime(input);
  const wrong = skipped || !isCorrect;
  const diagnosis = String(draftDiagnosis || '').trim();
  const omitDiagnosis = !wrong && (!hasDraft || isEmptyPraise(diagnosis));

  const optionLines = (options || []).map((opt) => {
    if (typeof opt === 'string') return `> **${opt}**`.replace(/> \*\*([A-D])[.．、]?\s*/, '> **$1.** ');
    return `> **${opt.key || opt.letter}.** ${opt.text || opt.body || ''}`;
  });

  const lines = [
    `### ${String(index).padStart(2, '0')} · ${typeName}`,
    '',
    '> **原题**',
    '>',
    `> ${String(stem || '').replace(/\n/g, '\n> ')}`,
    ...optionLines.map((line) => (line.startsWith('>') ? line : `> ${line}`)),
    '',
    formatAnswerResult({
      userAnswer, correctAnswer, timeSpentSec, suggested, skipped,
    }),
  ];
  if (knowledge) lines.push(`本题考察知识点：${knowledge}`);
  lines.push('');

  if (!omitDiagnosis) {
    lines.push(...section('草稿诊断', diagnosis));
  }
  lines.push(...section('标准解析', standardAnalysis));
  lines.push(...section('考场解法', examMethod));
  lines.push(...section('下次动作', nextAction));
  lines.push(...section('AI 深度点拨', deepTip));
  lines.push(...section('智能统计', formatStatsLine({ timeSpentSec, suggested, hasDraft })));

  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

export function extractSection(markdown, title) {
  const src = String(markdown || '');
  const re = new RegExp(`^#{2,4}\\s*${title}\\s*$`, 'im');
  const match = re.exec(src);
  if (!match) return '';
  const start = match.index + match[0].length;
  const rest = src.slice(start);
  const next = rest.search(/^#{2,4}\s+/m);
  return (next < 0 ? rest : rest.slice(0, next)).trim();
}

export function stripEmptyPraiseDiagnosis(markdown) {
  const src = String(markdown || '');
  return src.replace(
    /(^|\n)(#{2,4}\s*草稿诊断\s*\n)([\s\S]*?)(?=\n#{2,4}\s|\s*$)/g,
    (all, lead, heading, body) => {
      const text = String(body || '').trim();
      if (!text || isEmptyPraise(text)) return lead;
      return all;
    },
  ).replace(/\n{3,}/g, '\n\n');
}

export function sanitizeReviewMarkdown(markdown, { streaming = false, isCorrect, hasDraft } = {}) {
  if (streaming) return String(markdown || '');
  let out = stripEmptyPraiseDiagnosis(markdown);
  if (isCorrect && hasDraft === false) {
    out = out.replace(
      /(^|\n)#{2,4}\s*草稿诊断\s*\n[\s\S]*?(?=\n#{2,4}\s|\s*$)/g,
      '$1',
    );
  }
  return out.replace(/\n{3,}/g, '\n\n');
}

export function validateReviewMarkdown(markdown, { isCorrect = false, hasDraft = false, skipped = false } = {}) {
  const src = String(markdown || '');
  const errors = [];
  const diagnosis = extractSection(src, '草稿诊断');
  const nextAction = extractSection(src, '下次动作') || src;
  const deepTip = extractSection(src, 'AI 深度点拨') || src;
  const wrong = skipped || !isCorrect;

  if (!wrong && (!hasDraft || isEmptyPraise(diagnosis))) {
    if (diagnosis && isEmptyPraise(diagnosis)) {
      errors.push('答对且草稿空/无信息时禁止空夸奖诊断');
    }
    if (!hasDraft && /#{2,4}\s*草稿诊断/.test(src) && isEmptyPraise(diagnosis)) {
      errors.push('答对且草稿空应整段省略草稿诊断');
    }
  }
  if (wrong && !hasWrongCause(`${diagnosis}\n${src}`)) {
    errors.push('答错必须写出错因（读题/翻译/排除/概念等）');
  }
  if (!hasNextActionKoujue(nextAction)) {
    errors.push('下次动作必须含「触发：…… → 优先：……」');
  }
  if (NEWS_FLUFF_RE.test(deepTip)) {
    errors.push('深度点拨禁止「多关注时政/多读新闻」空话');
  }
  if (EMPTY_PRAISE_RE.test(diagnosis)) {
    errors.push('草稿诊断含空夸奖');
  }
  return { ok: errors.length === 0, errors };
}

export function assemblePracticeReportMarkdown({ session = {}, items = [] } = {}) {
  const list = Array.isArray(items) ? items : [];
  const wrong = list.filter((item) => !item.is_correct);
  const times = list.map((item) => Math.max(0, Number(item.time_spent_sec) || 0));
  const avgSec = times.length ? times.reduce((sum, value) => sum + value, 0) / times.length : 0;
  const slowThreshold = Math.max(60, Math.ceil(avgSec * 1.5));
  const focusItems = list.filter((item) =>
    !item.is_correct || item.draft_url || Number(item.time_spent_sec) >= slowThreshold);

  const lines = [
    `# AI 练题复盘：${session.display_title || session.category || '未命名批次'}`,
    '',
    `- 场次：${session.id}`,
    `- 交卷时间：${session.ended_at || '未知'}`,
    `- 成绩：${session.correct}/${session.total}`,
    `- 总用时：${formatDuration(session.duration_sec)}`,
    `- 错题或空题：${wrong.length}`,
    `- 本场慢题参考线：${formatDuration(slowThreshold)}（单题均时的 1.5 倍，最低 01:00）`,
    `- 画像：${session.profile_reviewed_at ? `已封印（${session.profile_reviewed_at}），勿再写入` : '未写入；本场第一次 Hermes 复盘才更新画像'}`,
    '',
    '## 逐题概览',
    '',
    '| 题号 | 题目id | 结果 | 用时 | 建议用时 | 草稿 | 知识点 |',
    '|---|---|---|---:|---|---|---|',
  ];

  for (const [index, item] of list.entries()) {
    const result = item.skipped ? '未作答' : item.is_correct ? '正确' : '错误';
    const draft = item.draft_url ? '有' : '无';
    const points = (item.knowledge_points || []).join('、').replace(/\|/g, '\\|') || '未标注';
    const suggested = resolveSuggestedTime(item);
    lines.push(`| ${index + 1} | ${item.question_id} | ${result} | ${formatDuration(item.time_spent_sec)} | ${suggested.label} | ${draft} | ${points} |`);
  }

  lines.push('', '## 复盘重点');
  if (focusItems.length === 0) {
    lines.push('', '本场没有错题、草稿异常或明显慢题。正确且快速的题无需逐题展开。');
    return lines.join('\n');
  }

  for (const item of focusItems) {
    const no = list.indexOf(item) + 1;
    const subtitle = item.sub_category ? ` · ${item.sub_category}` : '';
    const result = item.skipped ? '未作答' : item.is_correct ? '正确' : '错误';
    const suggested = resolveSuggestedTime(item);
    const comparison = compareToSuggested(item.skipped ? null : item.time_spent_sec, suggested);
    const reasons = [
      !item.is_correct ? '答案需复盘' : null,
      item.draft_url ? '有草稿，需检查思路和书写' : null,
      Number(item.time_spent_sec) >= slowThreshold ? '用时偏长，需检查方法选择和步骤压缩' : null,
    ].filter(Boolean).join('；');
    lines.push('', `### 第 ${no} 题${subtitle}`, '', String(item.content || ''));
    for (const option of item.options || []) {
      lines.push(`- ${option.key}. ${String(option.text || '').replace(/\n/g, ' ')}`);
    }
    lines.push(
      '',
      `- 题目id：${item.question_id}`,
      `- 作答结果：${result}`,
      `- 我的作答：${item.user_answer || '未作答'}`,
      `- 正确答案：${item.correct_answer || '未知'}`,
      `- 本题用时：${formatDuration(item.time_spent_sec)}`,
      `- 本题建议用时：${suggested.label}`,
      `- 用时对照：${comparison.label}`,
      `- 入选原因：${reasons}`,
    );
    if (item.knowledge_points?.length) {
      lines.push(`- 知识点：${item.knowledge_points.join('、')}`);
    }
    if (item.draft_url) lines.push('- 草稿：本题留有草稿纸，随复盘上下文提供');
    if (item.explanation) lines.push('', '#### 解析', '', String(item.explanation));
  }
  return lines.join('\n');
}

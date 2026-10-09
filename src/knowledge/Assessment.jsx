const COLORS = {
  unassessed: '#64748b',
  developing: '#b91c1c',
  initial: '#c26d16',
  mastered: '#15803d',
  stable: '#047857',
};
const HISTORY_COLORS = { weak: COLORS.developing, mixed: COLORS.initial, strong: COLORS.stable };
const PROCESS = { correct: '关键过程正确', partial: '关键过程部分正确', incorrect: '关键过程错误', unknown: '过程不明' };

const LEVEL_RANK = { developing: 1, initial: 2, mastered: 3, stable: 4 };
const HISTORY_RANK = { weak: 1, mixed: 2, strong: 3 };

function statusColor(assessment) {
  if (!assessment) return COLORS.unassessed;
  if (assessment.level !== 'unassessed') return COLORS[assessment.level] || COLORS.unassessed;
  return HISTORY_COLORS[assessment.basis === 'history' ? assessment.history?.status : ''] || COLORS.unassessed;
}

function rankOf(a) {
  if (!a) return 0;
  if (a.level !== 'unassessed') return LEVEL_RANK[a.level] || 0;
  return a.basis === 'history' ? HISTORY_RANK[a.history?.status] || 0 : 0;
}

// 父级不单独评估：按子考法里最弱的一档显示，未学的子项计入覆盖率
function rollupStatus(parts, pending) {
  const learned = parts.filter(r => r?.assessment && r.assessment.basis !== 'none');
  if (!learned.length) return { label: pending ? '读取中' : '待评估', color: COLORS.unassessed, tally: '' };
  const rated = learned.filter(r => rankOf(r.assessment) > 0);
  const weakest = rated.reduce((w, r) => (!w || rankOf(r.assessment) < rankOf(w.assessment) ? r : w), null);
  const counts = {};
  for (const r of parts) {
    const key = r?.assessment && r.assessment.basis !== 'none' ? r.assessment.label : '未学';
    counts[key] = (counts[key] || 0) + 1;
  }
  const tally = `${parts.length} 个子考法：${Object.entries(counts).map(([k, n]) => `${n} ${k}`).join(' · ')}`;
  const label = learned.length < parts.length ? `已学 ${learned.length}/${parts.length}`
    : weakest ? weakest.assessment.label : '已有学习记录';
  return { label, color: statusColor(weakest?.assessment), tally };
}

export function MasteryStatus({ row, pending, kind, parts, hint }) {
  const a = row?.assessment;
  const rollup = kind === 'rollup' && parts?.length ? rollupStatus(parts, pending) : null;
  const label = rollup ? rollup.label : a ? `${a.label}${a.review_due ? ' · 待复测' : ''}` : pending ? '读取中' : '待评估';
  const color = rollup ? rollup.color : statusColor(a);
  const detail = rollup ? [rollup.tally, '按最弱子项显示'] : [a && `熟练度：${a.fluency_label}`];
  return <span className="inline-flex shrink-0 items-center gap-1 text-xs font-bold" style={{ color }}
    title={[label, ...detail, hint].filter(Boolean).join(' · ')}>
    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
    {label}
  </span>;
}

export default function Assessment({ rows, pending, error }) {
  return <details className="border-t border-[#c4ae7a] px-3 py-3 space-y-4" aria-label="掌握与熟练度评估">
    <summary className="cursor-pointer text-sm font-bold text-slate-500">掌握与熟练度数据（点开查看）</summary>
    {error && <p role="status" className="text-sm text-red-700">评估同步失败，当前显示上次缓存。</p>}
    {!rows.length && <p className="text-sm text-slate-600">{pending ? '评估读取中' : '待评估：尚无本考点的独立作答评估。'}</p>}
    {rows.map(row => {
      const a = row.assessment;
      return <div key={row.kaodian} className="space-y-2 min-w-0">
        <p className="text-sm font-semibold break-words">{row.kaodian}</p>
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
          <span>掌握：<MasteryStatus row={row} pending={pending} /></span>
          <span>熟练度：<strong>{a?.fluency_label || '待评估'}</strong></span>
        </div>
        {a ? <>
          {a.basis === 'history' && <p className="text-sm text-slate-600 leading-6">暂定判断，依据历史首次作答；独立性和解题过程尚未全部核验。</p>}
          {a.basis === 'activity' && <p className="text-sm text-slate-600 leading-6">已保留 {a.activity_count} 条学习记录，尚缺可核对的首次作答或过程依据。</p>}
          {a.history?.recent_samples > 0 && <p className="text-sm text-slate-600 leading-6">
            最近 {a.history.recent_samples} 道有结果依据的首次作答，答对 {a.history.correct} 道，跨 {a.history.days} 天。
            {a.history.median_seconds != null && ` 答对题记录用时中位数 ${a.history.median_seconds} 秒，尚不代表考试达时。`}
            {a.history.plateau && ' 最近两轮新题低正确率且未改善，优先调整方法。'}
          </p>}
          <p className="text-sm text-slate-600 leading-6">
            已核验过程的最近 {a.recent_samples} 次独立检验，关键过程正确 {a.process_correct} 次，答案正确 {a.answer_correct} 次，跨 {a.days} 天。
            {a.source_update_due ? ' 所依据的政策内容已更新，相关内容待复测；历史作答保留。' : a.review_due && ' 距上次有效检验已满30天，当前水平待复测。'}
          </p>
          {a.by_question_type && <p className="text-xs text-slate-600">{Object.entries(a.by_question_type).map(([type, value]) => `${({ single: '单选', multi: '多选', judge: '判断' })[type] || type}：${value.correct}/${value.samples}`).join(' · ')}</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
            <span>结构变式：{a.variant_verified ? '已验证' : '待验证'}</span>
            <span>延迟保持：{a.delayed_verified ? '已验证' : '待验证'}</span>
            <span>重复题或同日同模板：{a.repeats_excluded} 次未计入</span>
            <span>过程待评估：{a.unreviewed} 次</span>
            <span>有提示或独立性不明：{a.assisted_or_unknown} 次</span>
          </div>
          <p className="text-xs text-slate-600 leading-5">
            {a.timed_samples ? `有效计时 ${a.timed_samples} 题；用时中位数 ${a.median_seconds} 秒；耗时与目标之比的中位数 ${a.median_target_ratio}。` : '速度证据不足：尚无同时具备正确过程、有效计时和目标耗时的独立答对记录。'}
          </p>
          {a.calibration?.samples > 0 && <p className="text-xs text-slate-600">作答前评为已掌握或稳定掌握的新题：后续答对 {a.calibration.correct}/{a.calibration.samples}。</p>}
          {a.evidence.length > 0 && <details>
            <summary className="cursor-pointer py-1 text-sm font-semibold">最近评估依据</summary>
            <ul className="divide-y divide-[#c4ae7a]/40">
              {a.evidence.map((e, i) => <li key={`${e.session_id}:${e.question_id}:${i}`} className="py-3 space-y-1 text-sm break-words">
                <p className="font-medium">{e.date} · 场次 {e.session_id ?? '-'} · 题目 {e.question_id ?? '-'} · {e.correct ? '答对' : '答错'} · {e.elapsed_seconds} 秒</p>
                <p>{PROCESS[e.process]} · {e.basis === 'draft' ? '草稿依据' : '解题说明依据'}</p>
                <p className="text-slate-600">{e.reason}</p>
                {e.target_seconds && <p className="text-xs text-slate-600">目标 {e.target_seconds} 秒：{e.target_basis}</p>}
              </li>)}
            </ul>
          </details>}
          {a.history?.evidence.length > 0 && <details>
            <summary className="cursor-pointer py-1 text-sm font-semibold">历史首次作答依据</summary>
            <ul className="divide-y divide-[#c4ae7a]/40">{a.history.evidence.map(e => <li key={`${e.session_id}:${e.question_id}`} className="py-2 text-sm break-words">
              {e.date} · 场次 {e.session_id} · 题目 {e.question_id} · {e.correct ? '答对' : '答错'} · {e.elapsed_seconds} 秒
            </li>)}</ul>
          </details>}
        </> : <p className="text-sm text-slate-600">历史作答尚无过程评估，待复盘确认。</p>}
      </div>;
    })}
  </details>;
}

const parseObject = (value) => {
  if (value && typeof value === 'object') return value;
  try { return JSON.parse(value); } catch { return null; }
};

export const quizToolReceipt = (payload) => {
  if (payload?.name !== 'terminal') return null;
  const args = parseObject(payload.args);
  const command = String(args?.command || '');
  if (!/(?:^|&&\s*)(?:[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|[^\s;&|]+)\s+)*(?:\S*\/)?python(?:3(?:\.\d+)?)?\s+['"]?(?:[^\s'"]*\/)?(?:quiz_lite|ziliao_parallel_runner|ziliao_agent_paper)\.py(?:['"]?\s|$)/.test(command)
      || /(?:^|\s)--plan-only(?:\s|$)/.test(command)) return null;
  const result = parseObject(payload.result);
  if (!result) return null;
  const summary = String(result.output || '').split('\n').reverse()
    .map(parseObject).find((row) => row?.batch_id && ['success', 'error'].includes(row.status));
  const flag = command.match(/(?:^|\s)--batch-id(?:=|\s+)(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))/);
  const batchId = summary?.batch_id || flag?.[1] || flag?.[2] || flag?.[3] || null;
  const failed = Boolean(result.error) || (result.exit_code != null && result.exit_code !== 0) || summary?.status === 'error';
  return {
    batchId,
    phase: failed ? 'failed' : result.session_id && result.pid ? 'started'
      : summary?.status === 'success' && Number(summary.imported) > 0 ? 'done' : 'unconfirmed',
    count: Number(summary?.imported) || 0,
  };
};

export const quizExecutionStatus = (receipts, jobs, requested = false) => {
  if (!receipts.length) return requested ? { phase: 'unconfirmed', text: '出题未确认启动，请勿按回复中的承诺等待。' } : null;
  const states = receipts.map((receipt) => {
    const job = jobs.find((row) => row.batch_id === receipt.batchId);
    if (job?.status === 'failed') return { phase: 'failed', text: `出题失败（${job.batch_id}）。` };
    if (job?.status === 'done') return {
      phase: 'done', text: job.stage === '已入库'
        ? `已核验入库 ${job.passed_count} 题（${job.batch_id}）。`
        : `出题流程已完成，入库尚未确认（${job.batch_id}）。`,
    };
    if (job?.stale) return { phase: 'unconfirmed', text: `出题进度长时间未更新，完成状态未确认（${job.batch_id}）。` };
    if (job?.status === 'running') return { phase: 'running', text: `出题已启动：${job.stage || '生成中'}（${job.batch_id}），尚未完成。` };
    if (receipt.phase === 'failed') return { phase: 'failed', text: '出题工具返回失败。' };
    if (receipt.phase === 'done') return { phase: 'done', text: `工具回执确认入库 ${receipt.count} 题（${receipt.batchId}）。` };
    if (receipt.phase === 'started') return { phase: 'started', text: '已收到出题进程启动回执，完成及入库尚未确认。' };
    return { phase: 'unconfirmed', text: '未收到有效的出题启动或完成回执。' };
  });
  return {
    phase: states.some((s) => ['started', 'running'].includes(s.phase)) ? 'running'
      : states.some((s) => s.phase === 'unconfirmed') ? 'unconfirmed'
        : states.some((s) => s.phase === 'failed') ? 'failed' : 'done',
    text: [...new Set(states.map((s) => s.text))].join('\n'),
  };
};

export const verifyHermesExecution = async ({ noteNames, receipts, wantsQuiz }, request) => {
  const [notes, jobGroups] = await Promise.all([
    noteNames.length ? request('/api/hermes/voice-notes/status', { method: 'POST', body: { names: noteNames } }).catch(() => null) : [],
    Promise.all([...new Set(receipts.map((r) => r.batchId).filter(Boolean))]
      .map((id) => request(`/api/questions/generation-queue?batch_id=${encodeURIComponent(id)}`).catch(() => []))),
  ]);
  const allNotesSaved = noteNames.length > 0 && Array.isArray(notes)
    && noteNames.every((name) => notes.some((note) => note.name === name && note.saved));
  return {
    allNotesSaved,
    voice: noteNames.length && !allNotesSaved ? '口述笔记尚未确认保存，已保留运行时录音；本轮执行结果需核验。' : '',
    quiz: quizExecutionStatus(receipts, jobGroups.flat(), wantsQuiz || Boolean(Array.isArray(notes) && notes.some((note) => note.wantsQuiz))),
  };
};

export const canDropVoiceContext = ({ live, stored, pending, turn }, current) => Boolean(
  live && stored && pending?.length && current.live === live && current.stored === stored
  && current.pending === pending && turn && current.turn === turn && !current.sending,
);

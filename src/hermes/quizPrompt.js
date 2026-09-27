// Shared by the chat UI and the live Hermes acceptance runner.
export function buildQuizPrompt({ text = '', audio = false, projectRoot }) {
  const spokenText = String(text);
  const deferred = /(?:先|暂时|这次|本轮)?(?:不要|别|不必|不用|不)\s*(?:急着)?(?:出题|生成题|生成练习)|只(?:是)?讨论/.test(spokenText);
  const ziliaoAction = /(?:练|出题|出.{0,8}题|来.{0,6}题|刷|生成|做题|一套|整套|均衡)/.test(spokenText);
  const wantsZiliao = !deferred && /资料分析/.test(spokenText) && ziliaoAction;
  const wantsQuiz = !deferred && (wantsZiliao || /出题|给我出|帮我出|出(?:[一-龥\d几]+)(?:道|个)?题|考考我|测测我|来(?:[一-龥\d几]+)(?:道|个)?题|刷题|AI\s*练题|专项练习|生成.{0,6}练习|(?:我要|我想|继续|针对).{0,12}练|(?:来|出|再来|各来|各出|给我|帮我出?|只练)\s*[\d一二两三四五六七八九十几]{1,3}\s*(?:道|个)(?![年月周])/.test(spokenText));
  const inline = /(?:直接|就).{0,8}(?:聊天|这里).{0,8}(?:发|出|做).{0,4}题/.test(spokenText);
  if (deferred || inline || (!wantsQuiz && !audio)) return { wantsQuiz, quizNudge: '' };

  if (wantsZiliao) {
    const requestedFormat = /柱状图|柱图|柱形图|条形图/.test(spokenText) ? 'chart'
      : /表格|表格图/.test(spokenText) ? 'table'
        : /纯文字|文字材料|文字资料/.test(spokenText) ? 'text' : null;
    const fullPaper = /整套|一套|完整一套|均衡|日练/.test(spokenText);
    const wantsClassic = /经典计算|计算加练|混合增速加练|拉动加练/.test(spokenText)
      && !/粤考日练|广东省考|日练/.test(spokenText);
    const track = wantsClassic ? 'classic' : 'gd';
    const format = requestedFormat || (fullPaper ? null : 'chart');
    const count = fullPaper ? 20 : 5;
    const materials = fullPaper ? 4 : 1;
    const formats = fullPaper ? '' : ` --formats ${format}`;
    const trackLabel = track === 'classic' ? '经典计算加练（轨B，不要标成广东省考综合训练）' : '粤考日练（轨A，近年粤考配额：细节/排除/综合正误为主）';
    return {
      wantsQuiz,
      quizNudge: [
        '这是资料分析出题请求，走专用篇级独立上下文流程，不使用 quiz_lite。用 Gemini（CLIPROXY，模型见 ZILIAO_GEMINI_MODEL/默认 gemini-3.8-flash-high）。',
        `只生成${fullPaper ? `一套${trackLabel}：4篇×5题，每篇由独立子Agent调用负责，单题失败只回炉该题` : `一篇${format === 'chart' ? '柱状图' : format === 'table' ? '表格' : '纯文字'}材料×5题，仅调用对应形态的篇级子Agent，默认仍走${trackLabel}`}。每个篇级调用拥有独立上下文，材料冻结后不得因单题问题重出整篇。`,
        `调用：python3 ${projectRoot}/scripts/ziliao_parallel_runner.py --track ${track} --count ${count} --materials ${materials} --difficulty mid${formats}`,
        '默认日练/用户说广东省考只走 --track gd。只有用户明确要经典计算/混合拉动加练时才 --track classic。用户明确指定题量/难度/知识点时优先保留。表格和柱状图必须由程序根据冻结数据渲染。',
        '失败按脚本原文报告，不手写题、不绕过质量门。成功只报告真实批次号和入库题数。',
      ].join('\n'),
    };
  }

  const script = `python3 ${projectRoot}/scripts/quiz_lite.py`;
  const quizNudge = [
    audio ? '若录音要求出题，以录音中的模块、知识点、题量和难度为准，执行下面流程。' : '这是出题请求，按用户当前要求交付到 ExamSystem AI 练题。',
    `遵守 ${projectRoot}/AGENTS.md 和 ${projectRoot}/hermes-skills/quiz-pipeline/SKILL.md；只讨论拆分时先讨论，不抢先出题。`,
    '用户指定的模块、知识点、题量、题型和难度优先。点名知识点但未说题量默认5题；仅点政治模块默认10题、常识默认5题。不要套用日练或强行混入其他模块。',
    `知识点以当前网页目录为准；需要查询时运行 node ${projectRoot}/scripts/knowledge-content.mjs catalog '<模块、完整二级或三级标签>'，如 catalog '判断推理' 或 catalog '言语理解与表达-片段阅读'。在返回范围内编排 blueprint，不能擅自缩成单个三级点。不得凭旧记忆手拼超长标签。`,
    `父知识点（如最值问题、工程问题）直接传 --tag '<完整三级标签>'，脚本自动按当前启用的末级子点配额；指定子知识点则用 catalog 返回的稳定 tag（三级标签-@节点ID；outline 中为 linkTag）或精确显示名，锁定该子点。改名、新增、拆分后重新读目录，不复用旧子点清单。`,
    `基本调用：${script} --module '<模块>' --tag '<当前目录目标>' --count <题量> --batch-id '<日期_hermes_考点_唯一序号>'。用户明确指定难度才加 --difficulty <easy|mid|hard>。数量未指定难度时省略该参数和槽内difficulty，由数量专用流程自由命题、按实际评档；不要自行补成全mid。言语同样未指定为auto，以练到指定知识点为主，难度只作命题倾向，不因easy/mid/hard边界退题；单题如实记录实际难度。政治理论、常识判断也默认auto，难度只作倾向，知识点、题型与原文依据严格核对；文字逻辑判断同样默认auto，难度只作倾向，独立核查答案唯一性和推理，不强制算式、固定步骤或复杂干扰；资料仍默认mid。`,
    '父级默认均衡分配当前子点；题量少于子点数时不能声称覆盖全部。用户指定配额和难度组合时用 --blueprint，禁止同时传 --tag/--count。',
    `蓝图格式：${script} --module '<模块>' --batch-id '<唯一批次号>' --blueprint '{"slots":[{"tag":"<当前父级或稳定子点>","count":2,"difficulty":"easy"},{"tag":"<当前父级或稳定子点>","count":3,"difficulty":"hard"}]}'。每槽可加 brief 表达训练意图、情境偏好和用户要求；考点内题面和正确解法保留自由，不强制讲解卡固定步骤。不得预写答案或具体题目数字；总题量1–15，所有槽同模块。`,
    '需要查看实际分配时给同一命令加 --plan-only；它只返回解析计划，不生成或入库。核对无误后去掉 --plan-only 执行一次，批次号不得覆盖已有批次。',
    '当前知识内容节点的定义由脚本在生成前登记、冻结并交给出题和审核；Hermes 不要为网页子点另造历史画像标签。新增或修改节点走 knowledge-content apply，保存并重新查看目录后才能按新拆分出题。',
    `政治理论/常识判断先运行 python3 ${projectRoot}/scripts/policy_sources.py status，并按 quiz-pipeline/references/politics-common-workflow.md 核验权威原文。缓存正文用该脚本 show <来源ID>，联网读原文及发布栏目用 inspect '<HTTPS地址>'，不要猜缓存路径或研究内部Python函数。update_review_due=true须先读取网页实际内容，再用review-updates登记source_ids/urls/findings/note；findings每个URL包含20–500字连续原文quote及具体finding。只看HTTP200/字节数不算查新。refresh只重抓原文，不代替新发布/修订/替代核验。缺源先add，禁止伪造核验日期或凭记忆出题。可用--sources明确选择相关资料。`,
    '图形推理、空间推理、科学推理去粉笔/已有外采真题，不调用图题生成器或实验模式。资料分析共享材料和确定性图表走 ziliao_parallel_runner.py。',
    '正式生成调用 terminal，background=true、notify_on_complete=true，等待后台完成 JSON；第一句“开始出题”不算成功。不要自己写 questions.json，不要手跑 generation_gate/import-batch，不用 ls/search_files/查库寻找入口。',
    '成功只报真实 batch_id 和 imported 数量；失败原样报告脚本 message，不另写题、不绕过审核。工具连续失败两次停止，等待用户指示。',
  ].join('\n');
  return { wantsQuiz, quizNudge };
}

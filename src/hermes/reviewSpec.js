// AI 练题复盘：可复用产出规范（提示词 + 时间标尺 + 空诊断识别）
// 人读版：hermes-skills/gd-gongkao-coach/references/practice-review-spec.md
// 组装 / 校验：./reviewAssembler.js

export const NEXT_ACTION_RE = /触发[:：].+?→\s*优先[:：]/s;

export const EMPTY_PRAISE_RE = /没问题[，,]?\s*继续保持|确认通过|完全没问题|保持即可|草稿\s*(?:为空|无信息|很干净|没什么)|做得很好[，,]?\s*继续/;

const EMPTY_PRAISE_ONLY_RE = /^(?:没问题[，,]?\s*继续保持|没问题|没有问题|没什么问题|确认通过|完全没问题|保持即可|继续保持)[。.!！]*$/;

export const WRONG_CAUSE_RE = /卡在|读题|翻译|排除|概念|审题|建模|干扰|误选|错因|偷换|肯后|否前|跑题|未对准结论|第二空|搭配/;

export const NEWS_FLUFF_RE = /多关注时政|多读新闻|多看新闻|多刷时政|关注时事/;

export const SUGGESTED_TIME_RULES = [
  { test: /逻辑填空|选词填空/, min: 40, max: 45, label: '≤40–45s' },
  { test: /翻译推理/, min: 50, max: 60, label: '≤50–60s' },
  { test: /加强|削弱|前提|假设|论证/, min: 50, max: 70, label: '≤50–70s' },
  { test: /图形/, min: 40, max: 50, label: '≤40–50s' },
  { test: /分析推理/, min: 70, max: 90, label: '≤70–90s' },
  { test: /数字推理/, min: 40, max: 50, label: '≤40–50s' },
  { test: /数量|数学运算/, min: 45, max: 60, label: '≤45–60s' },
  { test: /资料/, min: 50, max: 60, label: '≤50–60s' },
  { test: /科学推理/, min: 50, max: 70, label: '≤50–70s' },
  { test: /片段|主旨|中心理解|意图|标题|细节|语句/, min: 50, max: 60, label: '≤50–60s' },
  { test: /政治/, min: 25, max: 40, label: '≤25–40s' },
  { test: /常识/, min: 20, max: 30, label: '≤20–30s' },
];

export const DEFAULT_SUGGESTED_TIME = { min: 50, max: 60, label: '≤50–60s' };

const haystackOf = ({ category, sub_category, knowledge_points, typeName } = {}) =>
  [category, sub_category, typeName, ...(knowledge_points || [])]
    .filter(Boolean)
    .join(' ');

export function resolveSuggestedTime(item = {}) {
  const hay = haystackOf(item);
  return SUGGESTED_TIME_RULES.find((rule) => rule.test.test(hay)) || DEFAULT_SUGGESTED_TIME;
}

export function isEmptyPraise(text) {
  const raw = String(text || '').replace(/\s+/g, ' ').trim();
  if (!raw) return true;
  if (EMPTY_PRAISE_ONLY_RE.test(raw)) return true;
  return raw.length <= 24 && EMPTY_PRAISE_RE.test(raw);
}

export function hasNextActionKoujue(text) {
  return NEXT_ACTION_RE.test(String(text || ''));
}

export function hasWrongCause(text) {
  return WRONG_CAUSE_RE.test(String(text || ''));
}

export const REVIEW_COACH_RULES = [
  '日练复盘身份：广东/深圳省考行测教练。目标是下次更快做对，不是解题百科或鸡汤。方法优先，鼓励最多一句。',
  '骨架：引用块照录题干（不要写「原题」二字）→ `**作答结果**`（对错/用时/建议用时/考点）→ `#### 草稿诊断`（可省略）→ `#### 标准解析` → `#### 考场解法` → `#### 下次动作` → `#### AI 深度点拨` → `#### 智能统计`（轻量对照）。禁止改成「为什么会错 / 解题流程 / 下次遇到怎么做」。',
  'A. 按对错分流篇幅。答对：草稿诊断最多 1 句，且必须点速度或步骤效率；草稿为空或无信息则整段省略 `#### 草稿诊断`，禁止空夸奖（「没问题，继续保持」「确认通过」「草稿很干净」等）。标准解析缩短为「为何对 + 主要干扰项一句」。重点写 `#### 考场解法`（更快路径）和 `#### 下次动作`。答错：草稿诊断加长，对照草稿/思路指出卡在读题、翻译、排除还是概念；标准解析完整（正确项 + 各干扰项为何错）。空题按错题展开。',
  'B. 时间标尺。作答结果必须写本题建议用时（默认：逻辑填空 ≤40–45s，翻译推理 ≤50–60s，论证类 ≤50–70s；报告里已给的建议用时直接抄，不要另编）。有用户用时则对比建议用时（快/达标/超时）。有草稿才判断慢在读题/建模翻译/排除；无草稿只做总时长对比，禁止编造逐步秒数。',
  'C. `#### 下次动作` 强制口诀：`触发：…… → 优先：……`（后面可跟半句）。禁止单独鸡汤段。例：`触发：XX技术 + 国外长期XX → 优先：垄断/封锁类搭配，先锁第二空`。',
  'D. `#### AI 深度点拨` 必须可执行：1 个可迁移考点/搭配/模型 + 明确下一练（如「科技类逻辑填空再做 3 题」）。能挂「练习同类」就挂；不能就写清意图。禁止「多关注时政/多读新闻」空话。',
  'E. 模块差异化，不要五段等长灌水。翻译推理：公式链、哪步慢、固定事实从哪句切入。逻辑填空：第二空锁定搭配/排除，少长赏析。加强削弱：对准结论，点名跑题项。其他题型按核心手法写。',
  'F. 判断推理日练仍是图形 5 + 逻辑 15；科学推理独立 5 题。不要把科推并进判断，不要改数资九宫格。',
  '`#### 智能统计` 只做本题用时对照建议用时的轻量估算，不要加大权重，不要编造正确率、排名或画像数据源。没有用时就写「无用时，仅保留建议用时」。',
  '正确且草稿空：不要写草稿诊断。正确但有草稿或超时：诊断只点效率，把篇幅留给更快路径。禁止用「没问题」打发任何题。',
].join('\n');

const sharedLayoutRules = [
  REVIEW_COACH_RULES,
  '回复的第一行必须是 `### 01 · 题型名`。禁止先写总况、长短处、知识点总表或模块总评。直接按题讲。',
  '1. 每一道展开复盘的题：`### 02 · 题型名`；下一块用引用块照录题干，不要写「原题」标签。题干里的 A、B、C 地名/序号必须留在原句，禁止拆成单独一行。语句排序的①②③④各句必须各占一行（中间空一行引用），四个选项只用 `> **A.**` / `> **B.**` / `> **C.**` / `> **D.**` 各占一行。禁止横向表格、禁止四个选项挤在同一行、禁止省略任何选项、禁止在题干区标答案。',
  '2. 题干之后写 `**作答结果**：你的答案 X · 正确答案 Y · 用时 MM:SS · 建议用时 ≤xx–xxs`，有用时则补对照（快/达标/超时）。下一行写 `本题考察知识点：模块-一级-二级`。看图题必须先看题干再看对应 `qN-stem.png`（或报告题图路径）再写解析；图上的数值、接线和结构以图为准，禁止只凭文字补造。题干里的 A/B/C/D 地名或序号必须留在原句，不要拆行。',
  '3. 标题按对错取舍：答对且草稿空则跳过 `#### 草稿诊断`；其余按规范写。不要为凑标题灌水。',
  '4. 最后一题讲完后必须另起 `### 本场结语`。依次写 `#### 做得好的`、`#### 做得不好的`、`#### 以后怎么改`。每条落到本场具体题号或动作，禁止空话。',
  '5. 资料分析按材料成套：先 `### 材料一` + `> **材料**`，再连续讲该篇 5 题；第 5 题后再 `### 材料二`。每题原题只放问句和选项。',
  '6. 建议必须是考场动作。禁止哈利波特、黑暗王子、黑魔法等包装。确认是独立新考点时，按 knowledge-point-extension.md 登记并注明「（新补录）」。',
  '7. 科学推理下标必须写成 `$P_{R_1}$` `$I_1$` `$R_1$`，禁止并列的 `PR1`/`I1`/`R1`。箭头用 →，不要写 `\\rightarrow`。',
];

export function buildPracticeReviewLead(review = {}) {
  return [
    `下面这个 Markdown 是我选中的《${review.title || 'AI 练题复盘'}》，请先直接打开文件。`,
    review.path,
    `本场共 ${review.total || 0} 题；已附上 ${Number(review.stemCount || 0)} 张题图（q1-stem.png）和 ${review.draftCount || 0} 张草稿纸（q1-draft.png）。请逐题对应，不要把附件数量误认为题目总数。`,
    '',
    '言语、判断、数量、科学、资料必须同一套标题，禁止按模块换版式。',
    '复盘顺序：先读题干，再打开对应题图（qN-stem.png），再对照草稿。看图题禁止只凭文字补造电路/图形上的数值或结构。除原题外，不要机械复述报告统计或现成解析。报告里的「建议用时」直接采用。',
    ...sharedLayoutRules,
    '',
  ].join('\n');
}

export function buildExamReviewLead(review = {}, examScoreLine = '') {
  return [
    `下面这个 Markdown 是我那场《${review.title || '录屏复盘'}》的录屏复盘报告，请先打开。`,
    review.path,
    '',
    examScoreLine,
    '口吻必须和 AI 练题复盘一样，执行同一套对错分流规范。',
    '复盘必须同时用三份材料：① 报告开头 PDF 判分表和原题；② 「录屏行为记录」里每题的停留、标签、过程、时间线；③ 各题草稿。对错、你的答案、正确答案只抄 PDF 判分表。报告里旧的「差距」「你怎么做的」若和判分表或行为记录冲突，以判分表和行为记录为准。',
    ...sharedLayoutRules,
    '',
  ].join('\n');
}

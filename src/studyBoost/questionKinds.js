// 题型注册表。
//
// 每种考法就是一条注册项，声明式地描述：
//   - 需要词条具备哪些字段（requires）→ 引擎自动判断该词能不能出这题
//   - 题干从哪来（buildPrompt）
//   - 选项文本从哪来（optionText）
//   - 干扰项从哪个字段池挑（distractorField）
//
// 新增一种题型 = 往 QUESTION_KINDS 里加一条，不用碰引擎和 UI。
// 这样 Gemini 补出 usage / antonyms / examples 等字段后，
// 对应题型会自动"解锁"，无需改代码。

/** 干扰项文本取自哪个字段：'word' = 选词型，'explanation' = 选释义型 */
export const OPTION_SOURCE = {
  WORD: 'word',
  EXPLANATION: 'explanation',
};

/**
 * @typedef {Object} QuestionKind
 * @property {string} id            题型标识，持久化到统计里，不要随意改
 * @property {string} label         UI 上的短名
 * @property {string} promptLabel   题干上方的提问语
 * @property {string[]} requires    词条必须具备的字段（非空）
 * @property {string} optionSource  选项文本来源，见 OPTION_SOURCE
 * @property {(entry:Object, rand:Function)=>string} buildPrompt  生成题干
 * @property {boolean} [wideOptions] 选项文本较长时单列显示
 * @property {number} [weight]      混合出题时的相对权重
 */

const pickOne = (arr, rand) => arr[Math.floor(rand() * arr.length)];

/** @type {QuestionKind[]} */
export const QUESTION_KINDS = [
  {
    id: 'meaning',
    label: '释义→选词',
    promptLabel: '下列哪个词符合这个释义？',
    requires: ['explanation'],
    optionSource: OPTION_SOURCE.WORD,
    buildPrompt: (e) => e.explanation,
    quotePrompt: true,
    weight: 3,
  },
  {
    id: 'reverse',
    label: '词→选释义',
    promptLabel: '这个词的准确含义是？',
    requires: ['explanation'],
    optionSource: OPTION_SOURCE.EXPLANATION,
    buildPrompt: (e) => e.word,
    bigPrompt: true,
    wideOptions: true,
    weight: 3,
  },
  {
    id: 'cloze',
    label: '语境填空',
    promptLabel: '横线处填哪个词最恰当？',
    requires: ['cloze'],
    optionSource: OPTION_SOURCE.WORD,
    buildPrompt: (e, rand) => pickOne(e.cloze, rand),
    weight: 4, // 最接近真实考法，优先出
  },
  // 以下题型依赖 Gemini 后续补的字段，字段一到位就自动可用
  {
    id: 'usage',
    label: '用法辨析',
    promptLabel: '哪个词符合这个用法要点？',
    requires: ['usage'],
    optionSource: OPTION_SOURCE.WORD,
    buildPrompt: (e) => e.usage,
    weight: 3,
  },
  {
    id: 'trap',
    label: '避坑识别',
    promptLabel: '这是哪个词的典型误用陷阱？',
    requires: ['trap'],
    optionSource: OPTION_SOURCE.WORD,
    buildPrompt: (e) => e.trap,
    weight: 3,
  },
  {
    id: 'example',
    label: '例句选词',
    promptLabel: '哪个词能替换句中的空缺？',
    requires: ['examples'],
    optionSource: OPTION_SOURCE.WORD,
    // 完整例句里把该词换成横线，等效于挖空题但语料更丰富
    buildPrompt: (e, rand) => pickOne(e.examples, rand).split(e.word).join('____'),
    weight: 3,
  },
];

export const KIND_BY_ID = new Map(QUESTION_KINDS.map((k) => [k.id, k]));

/** 词条是否具备出某题型所需的字段 */
export function entrySupports(entry, kind) {
  return kind.requires.every((f) => {
    const v = entry[f];
    if (Array.isArray(v)) return v.length > 0;
    return typeof v === 'string' ? v.trim().length > 0 : v != null;
  });
}

/** 某词条当前可出的所有题型 */
export function availableKinds(entry, allowed = QUESTION_KINDS) {
  return allowed.filter((k) => entrySupports(entry, k));
}

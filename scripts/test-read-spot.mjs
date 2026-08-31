import { generate, CATEGORIES, getSub } from '../src/practice/generators.js';
import { READ_SPOT_PACKS, validateReadSpotPacks } from '../src/practice/readSpotPacks.js';

const assert = (ok, msg) => {
  if (!ok) throw new Error(msg);
};

const cat = CATEGORIES.find((c) => c.id === 'readSpot');
assert(cat, 'readSpot category missing');
assert(cat.kind === 'selfReport', 'kind should be selfReport');
assert(cat.subs.length === 6, 'expected 6 subs');

const twoYears = (s) => (s.match(/20\d{2}/g) || []).length >= 2;
const timeShift = (s) => /材料|上年|仅给出/.test(s) || twoYears(s);

for (const sub of cat.subs) {
  assert(getSub('readSpot', sub.id)?.gen === sub.gen, `getSub ${sub.id}`);
  for (let i = 0; i < 40; i += 1) {
    const q = generate(sub.gen);
    assert(q?.prompt, `${sub.id} missing prompt`);
    assert(q.answer, `${sub.id} missing answer`);
    assert(q.reason, `${sub.id} missing reason`);
    assert(typeof q.displayAnswer === 'function', `${sub.id} displayAnswer`);
    if (sub.gen === 'findBasic' || sub.gen === 'findAdv') {
      assert(Array.isArray(q.material) && q.material.length > 2, `${sub.id} material`);
      const targets = q.material.filter((token) => token.mark === 'target');
      assert(targets.length >= 1, `${sub.id} needs highlighted targets`);
      const raw = q.material.map((token) => token.text).join('');
      const paragraphs = raw.split(/\n+/).filter((value) => value.trim());
      assert(paragraphs.length === 4, `${sub.id} paragraphs ${paragraphs.length}`);
      assert(raw.replace(/\s/g, '').length >= 580, `${sub.id} material too short`);
      assert(!raw.includes('\n\n'), `${sub.id} has oversized paragraph gap`);
      assert((raw.match(/\d+(?:\.\d+)?/g) || []).length >= 20, `${sub.id} numeric density too low`);
      assert(!/读数时先分清|不要点|找数时|增长-/.test(raw), `${sub.id} teaching text leaked`);
    }
    if (sub.gen === 'findAdv') {
      assert(q.formula?.text, `${sub.id} formula`);
      assert(Array.isArray(q.checklist) && q.checklist.length >= 2, `${sub.id} checklist`);
      const targets = q.material.filter((token) => token.mark === 'target');
      assert(targets.length === q.checklist.length, `${sub.id} target/checklist mismatch`);
    }
    if (sub.gen.startsWith('spot')) assert(q.kind === 'spot', `${sub.id} kind`);
  }
}

const answers = new Set();
const prompts = new Set();
for (let i = 0; i < 240; i += 1) {
  const q = generate('spotZiliao');
  answers.add(q.answer);
  prompts.add(q.prompt);
  if (q.answer === '基期量') assert(timeShift(q.prompt), `基期量题干缺少时间差: ${q.prompt}`);
  if (/(年末|截至).{0,8}(累计|保有)/.test(q.prompt) && !timeShift(q.prompt)) {
    assert(q.answer === '累计量', `累计/保有无时间差不应是${q.answer}: ${q.prompt}`);
  }
}
assert(answers.has('累计量'), `missing 累计量, got ${[...answers]}`);
assert(answers.has('基期量'), `missing 基期量, got ${[...answers]}`);
assert(answers.has('现期比重'), `missing 现期比重, got ${[...answers]}`);
assert(prompts.size >= 40, `spot stems not diverse: ${prompts.size}`);

const packErrors = validateReadSpotPacks();
assert(packErrors.length === 0, `read-spot pack errors:\n${packErrors.join('\n')}`);
const themeIds = new Set();
const questionIds = new Set();
const skills = new Set();
for (let i = 0; i < 240; i += 1) {
  const q = generate('findBasic');
  themeIds.add(q.themeId);
  questionIds.add(q.questionId);
  skills.add(q.hint);
}
assert(themeIds.size === READ_SPOT_PACKS.length, `theme coverage ${themeIds.size}/${READ_SPOT_PACKS.length}`);
assert(questionIds.size >= 95, `basic diversity too low: ${questionIds.size}`);
for (const skill of ['找数', '找率', '找时间']) assert(skills.has(skill), `missing skill ${skill}`);

console.log('read-spot ok', `spots ${prompts.size} / packs ${themeIds.size} / basic ${questionIds.size}`);

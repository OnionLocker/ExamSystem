import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';
import { IDIOM_GROUPS, GROUP_WORDS, CURATED_WORDS } from '../src/studyBoost/idiomGroups.js';
import { emptyLearning, learningState, recordAnswer, groupQuestion, groupProgress, mergeLegacyStats } from '../src/studyBoost/idiomLearning.js';

const words = new Map(GROUP_WORDS.map(w => [w.word, w]));
const lookup = word => words.get(word);
assert.equal(new Set(IDIOM_GROUPS.map(g => g.id)).size, IDIOM_GROUPS.length);
for (const group of IDIOM_GROUPS) {
  const variants = [group.quiz, ...(group.quizzes || [])];
  assert(variants.length >= 2, `${group.id}: missing review variant`);
  assert.equal(new Set(variants.map(q => q.stem)).size, variants.length);
  const ids = new Set();
  for (let i = 0; i < variants.length; i++) {
    const v = variants[i];
    const q = groupQuestion(group, lookup, () => (i + .1) / variants.length);
    ids.add(q.id);
    assert.equal(q.stem, v.stem);
    assert.equal(q.answer, v.answer);
    assert(q.stem.includes('____') && !q.stem.includes(q.answer), `${group.id}: leaked answer`);
    assert(q.options.length >= 2 && q.options.length <= 4);
    assert.equal(new Set(q.options.map(o => o.text)).size, q.options.length);
    assert.equal(q.options.filter(o => o.correct).length, 1);
    assert.equal(q.target.word, q.answer);
    assert.notEqual(groupQuestion(group, lookup, () => 0, q.id).id, q.id);
  }
  assert.equal(ids.size, variants.length);
  const q = groupQuestion(group, lookup, () => 0);
  assert.equal(q.options.length, (group.quiz.options || group.members).length, group.id);
  assert.equal(new Set(q.options.map(o => o.text)).size, q.options.length, group.id);
  assert.equal(q.options.filter(o => o.correct).length, 1, group.id);
  assert.equal(q.target.word, q.answer);
  assert(q.stem.includes('____') && !q.stem.includes(q.answer), group.id);
  for (const member of group.members) assert(member.every(Boolean));
  const initial = emptyLearning();
  const wrong = q.options.find(o => !o.correct).text;
  const missed = recordAnswer(initial, q, wrong, '2026-09-24T10:00:00Z');
  const corrected = recordAnswer(missed, q, q.answer, '2026-09-24T10:01:00Z');
  assert.equal(corrected.answers[q.id].right, 1);
  assert.equal(corrected.answers[q.id].wrong, 1);
  assert.equal(corrected.answers[q.id].lastCorrect, true);
  assert.deepEqual(initial.answers, {});
}
const q = groupQuestion(IDIOM_GROUPS[0], lookup, () => 0);
assert.notDeepEqual(q.options.map(o => o.text), IDIOM_GROUPS[0].members.map(m => m[0]));
const aliases = [{ id: 'new', word: '有的放矢', legacyIds: ['new', 7, 'old'] }];
assert.deepEqual(learningState(null, [7], aliases).learned, ['有的放矢']);
const saved = { new: { right: 1, wrong: 0, streak: 1 }, 7: { right: 2, wrong: 1, streak: 2 }, unrelated: { right: 4 } };
const merged = mergeLegacyStats(saved, aliases);
assert.deepEqual(merged.new, { right: 3, wrong: 1, streak: 0 });
assert(!merged[7]);
assert.deepEqual(merged.unrelated, saved.unrelated);
assert.deepEqual(mergeLegacyStats(merged, aliases), merged); // no double-counting on reload
assert.deepEqual(saved[7], { right: 2, wrong: 1, streak: 2 });
const evidence = JSON.parse(readFileSync(new URL('../src/studyBoost/idiomEvidence.json', import.meta.url)));
assert.deepEqual(evidence.gdCoverage.missing, []);
assert.equal(evidence.gdCoverage.included, evidence.gdCoverage.candidates);
const curated = new Set(CURATED_WORDS.map(w => w.word));
for (const [word, records] of Object.entries(evidence.words)) {
  if (records.some(r => r.region === '广东')) assert(curated.has(word), `Guangdong word not curated: ${word}`);
}
assert(evidence.words['失之毫厘，谬以千里'].some(r => r.year === 2025));
assert(!evidence.words['失之毫厘']?.some(r => r.year === 2025 && r.region === '广东'));
const historic = { answers: { 'group:steps': { right: 3, wrong: 1 }, 'group:steps:1': { right: 1, wrong: 2, groupId: 'steps' }, 'group:other': { right: 10, wrong: 0 } } };
assert.deepEqual(groupProgress(historic, 'steps'), { right: 4, wrong: 3 });
for (const records of Object.values(evidence.words)) {
  assert.equal(new Set(records.map(r => `${r.paper}:${r.number}`)).size, records.length);
  assert(records.every(r => r.paper && Number.isInteger(r.number) && Number.isInteger(r.year)));
}
const server = await createServer({ configFile: false, server: { middlewareMode: true } });
try {
  const { ALL_WORDS, lookupWord, buildQuestion, buildQuestionOfKind, QUESTION_KINDS, PACK_DIAGNOSTICS } = await server.ssrLoadModule('/src/studyBoost/vocabQuiz.js');
  assert.deepEqual(PACK_DIAGNOSTICS.errors, []);
  assert.equal(new Set(ALL_WORDS.map(w => w.word)).size, ALL_WORDS.length);
  assert.equal(new Set(ALL_WORDS.map(w => w.id)).size, ALL_WORDS.length);
  for (const word of ALL_WORDS.filter(w => w.curated)) {
    assert(buildQuestion(word, ['reverse'], ALL_WORDS, () => .37), `${word.word}: single-word practice unavailable`);
  }
  for (const group of IDIOM_GROUPS) {
    for (let i = 0; i <= group.quizzes.length; i++) {
      const question = groupQuestion(group, lookupWord, () => (i + .1) / (group.quizzes.length + 1));
      assert(question.options.every(o => o.word.explanation), `${group.id}: missing distractor explanation`);
    }
  }
  for (const word of ALL_WORDS) for (const kind of QUESTION_KINDS) {
    const question = buildQuestionOfKind(word, kind, ALL_WORDS, () => 0.37);
    if (!question) continue;
    assert.equal(question.options.filter(o => o.correct).length, 1);
    assert.equal(new Set(question.options.map(o => o.text)).size, 4);
    if (['example', 'cloze'].includes(kind.id)) assert(question.prompt.includes('____'), `${word.word}: no blank`);
  }
  console.log(`${IDIOM_GROUPS.length} groups / ${curated.size} curated / ${ALL_WORDS.length} total words: questions, shuffling, history migration and sources passed.`);
} finally { await server.close(); }

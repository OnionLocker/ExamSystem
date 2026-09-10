import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  assembleCoachReview,
  assemblePracticeReportMarkdown,
  sanitizeReviewMarkdown,
  stripEmptyPraiseDiagnosis,
  validateReviewMarkdown,
} from '../src/hermes/reviewAssembler.js';
import {
  REVIEW_COACH_RULES,
  buildPracticeReviewLead,
  isEmptyPraise,
  resolveSuggestedTime,
} from '../src/hermes/reviewSpec.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = (name) => fs.readFileSync(path.join(here, 'fixtures/practice-review', name), 'utf8');

assert.equal(resolveSuggestedTime({ sub_category: '逻辑填空' }).label, '≤40–45s');
assert.equal(resolveSuggestedTime({ sub_category: '翻译推理' }).label, '≤50–60s');
assert.equal(resolveSuggestedTime({ sub_category: '加强削弱' }).min, 50);
assert.equal(resolveSuggestedTime({ category: '判断推理', sub_category: '削弱论证' }).label, '≤50–70s');
assert.ok(isEmptyPraise('没问题，继续保持'));
assert.ok(isEmptyPraise('确认通过'));
assert.equal(isEmptyPraise('第二空锁定后应继续保持这个顺序'), false);
assert.equal(isEmptyPraise('第二空已锁，第一空近义词比太久'), false);

const correctEmpty = fixture('correct-empty-draft.md');
assert.doesNotMatch(correctEmpty, /#### 草稿诊断/);
assert.doesNotMatch(correctEmpty, /没问题，继续保持/);
assert.match(correctEmpty, /触发：.+→\s*优先：/);
const correctCheck = validateReviewMarkdown(correctEmpty, { isCorrect: true, hasDraft: false });
assert.equal(correctCheck.ok, true, correctCheck.errors.join('；'));

const wrong = fixture('wrong-translation.md');
assert.match(wrong, /卡在翻译/);
assert.match(wrong, /触发：.+→\s*优先：/);
const wrongCheck = validateReviewMarkdown(wrong, { isCorrect: false, hasDraft: false });
assert.equal(wrongCheck.ok, true, wrongCheck.errors.join('；'));

const praise = fixture('correct-empty-draft-praise.md');
assert.match(praise, /没问题，继续保持/);
const stripped = stripEmptyPraiseDiagnosis(praise);
assert.doesNotMatch(stripped, /没问题，继续保持/);
assert.doesNotMatch(stripped, /#### 草稿诊断/);
const sanitized = sanitizeReviewMarkdown(praise, { isCorrect: true, hasDraft: false });
assert.doesNotMatch(sanitized, /#### 草稿诊断/);
assert.equal(validateReviewMarkdown(praise, { isCorrect: true, hasDraft: false }).ok, false);

const missingKoujue = validateReviewMarkdown(praise.replace('下次细心一点。', '多总结'), {
  isCorrect: false,
  hasDraft: false,
});
assert.equal(missingKoujue.ok, false);
assert.ok(missingKoujue.errors.some((err) => err.includes('触发')));

const assembledCorrect = assembleCoachReview({
  index: 1,
  typeName: '逻辑填空',
  category: '言语理解',
  sub_category: '逻辑填空',
  stem: '科技样例题干',
  options: [{ key: 'A', text: '封锁 瓶颈' }, { key: 'B', text: '交流 惯例' }],
  userAnswer: 'A',
  correctAnswer: 'A',
  isCorrect: true,
  timeSpentSec: 38,
  knowledge: '言语理解-逻辑填空-逻辑对应',
  hasDraft: false,
  draftDiagnosis: '没问题，继续保持',
  standardAnalysis: '选 A：第二空锁定瓶颈。主要干扰项 B 接不上长期遭遇。',
  examMethod: '先锁第二空搭配，再回看第一空。',
  nextAction: '触发：XX技术 + 国外长期XX → 优先：垄断/封锁类搭配，先锁第二空',
  deepTip: '可迁移：先锁更死的搭配空。下一练：科技类逻辑填空再做 3 题。',
});
assert.doesNotMatch(assembledCorrect, /#### 草稿诊断/);
assert.doesNotMatch(assembledCorrect, /没问题，继续保持/);
assert.match(assembledCorrect, /建议用时 ≤40–45s/);
assert.match(assembledCorrect, /触发：.+→\s*优先：/);
assert.equal(validateReviewMarkdown(assembledCorrect, { isCorrect: true, hasDraft: false }).ok, true);

const assembledWrong = assembleCoachReview({
  index: 2,
  typeName: '翻译推理',
  category: '判断推理',
  sub_category: '翻译推理',
  stem: '只有配备双路市电才能承接业务。',
  options: [{ key: 'A', text: '不能承接' }, { key: 'D', text: '只要签署就能承接' }],
  userAnswer: 'D',
  correctAnswer: 'A',
  isCorrect: false,
  timeSpentSec: 82,
  knowledge: '判断推理-逻辑判断-翻译推理',
  hasDraft: false,
  draftDiagnosis: '卡在翻译：把「只有才」写成前推后，排除时被充分条件项带走。',
  standardAnalysis: 'A 是逆否。D 把必要改成充分。',
  examMethod: '写 B→A，立刻写逆否，再扫逆命题。',
  nextAction: '触发：只有…才… + 只要…就… → 优先：先写逆否，再排除逆命题',
  deepTip: '可迁移：「才」是箭头尾巴。下一练：只有才 / 除非否则再做 3 题。',
});
assert.match(assembledWrong, /#### 草稿诊断/);
assert.match(assembledWrong, /卡在翻译/);
assert.match(assembledWrong, /建议用时 ≤50–60s/);
assert.match(assembledWrong, /超时/);
assert.equal(validateReviewMarkdown(assembledWrong, { isCorrect: false, hasDraft: false }).ok, true);

const report = assemblePracticeReportMarkdown({
  session: {
    id: 1,
    display_title: '样例批次',
    category: 'demo',
    correct: 1,
    total: 2,
    duration_sec: 120,
    ended_at: '2026-09-02',
  },
  items: [
    {
      question_id: 11,
      content: '逻辑填空样例',
      options: [{ key: 'A', text: '封锁' }],
      category: '言语理解',
      sub_category: '逻辑填空',
      user_answer: 'A',
      correct_answer: 'A',
      is_correct: true,
      time_spent_sec: 38,
      knowledge_points: ['言语理解-逻辑填空-逻辑对应'],
    },
    {
      question_id: 12,
      content: '翻译推理样例',
      options: [{ key: 'A', text: '不能承接' }],
      category: '判断推理',
      sub_category: '翻译推理',
      user_answer: 'D',
      correct_answer: 'A',
      is_correct: false,
      time_spent_sec: 82,
      knowledge_points: ['判断推理-逻辑判断-翻译推理'],
    },
  ],
});
assert.match(report, /建议用时/);
assert.match(report, /≤40–45s/);
assert.match(report, /≤50–60s/);
assert.match(report, /本题建议用时：≤50–60s/);

const lead = buildPracticeReviewLead({ title: '样例', path: '/tmp/demo.md', total: 2, draftCount: 0 });
assert.match(lead, /禁止空夸奖/);
assert.match(lead, /触发：/);
assert.match(REVIEW_COACH_RULES, /没问题，继续保持/);

const streamingKept = sanitizeReviewMarkdown(praise, { streaming: true });
assert.match(streamingKept, /没问题，继续保持/);

console.log('review assembler / spec: ok');

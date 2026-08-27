import assert from 'node:assert/strict';
import { validateReferenceQuestion } from '../server/routes/referenceQuestions.js';

const valid = {
  external_id: 'agent-2024-gd-001',
  category: '判断推理',
  sub_category: '图形推理',
  question_type: 'single',
  stem: '请选择最符合规律的一项。',
  options: [
    { key: 'A', text: '' },
    { key: 'B', text: '' },
    { key: 'C', text: '' },
    { key: 'D', text: '' },
  ],
  answer: 'C',
  tags: ['判断推理-图形推理-位置规律'],
  source: '2024 广东省考真题',
  year: 2024,
};

const normalized = validateReferenceQuestion(
  valid,
  new Set(['option_A_images', 'option_B_images', 'option_C_images', 'option_D_images']),
);
assert.equal(normalized.answer, 'C');
assert.equal(normalized.difficulty, 2);

assert.throws(
  () => validateReferenceQuestion({ ...valid, category: '自定义分类' }, new Set()),
  /category 不合法/,
);
assert.throws(
  () => validateReferenceQuestion({ ...valid, options: [{ key: 'A', text: 'A' }] }, new Set()),
  /2~5/,
);
assert.throws(
  () => validateReferenceQuestion({
    ...valid,
    options: valid.options.map((option) => ({ ...option, text: option.key })),
    answer: 'E',
  }, new Set()),
  /单选题 answer/,
);
assert.throws(
  () => validateReferenceQuestion({
    ...valid,
    options: valid.options.map((option) => ({ ...option, text: option.key })),
  }, new Set(['option_E_images'])),
  /没有对应选项/,
);
assert.throws(
  () => validateReferenceQuestion({
    ...valid,
    question_type: 'multi',
    options: valid.options.map((option) => ({ ...option, text: option.key })),
    answer: 'AA',
  }, new Set()),
  /不重复/,
);

console.log('reference question API validation: ok');

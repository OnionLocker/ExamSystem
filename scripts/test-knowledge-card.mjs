import assert from 'node:assert/strict';

import { cardRow, relatedRows } from '../src/knowledge/match.js';
import { cardToMarkdown, decorateMath } from '../src/knowledge/cardMarkdown.js';

assert.equal(
  decorateMath('平方差：a^2 - b^2 = (a + b)(a - b)'),
  '平方差： $a^{2} - b^{2} = (a + b)(a - b)$',
);

const cow = { name: '04 古老的“牛吃草”与不变的容斥问题' };
const date = { name: '05 有规律的周期循环与要算准的日期星期' };
const rows = [
  {
    kaodian: '数量关系-容斥问题-集合计数与逆向排除',
    subtype: '容斥问题',
    attempts: 1,
    mastery: 59,
    mastery_confidence: 11,
  },
  {
    kaodian: '数量关系-有规律的周期循环与要算准的日期星期-日期推算与余数',
    subtype: '有规律的周期循环与要算准的日期星期',
    attempts: 36,
    mastery: 44,
    mastery_confidence: 98,
  },
  {
    kaodian: '数量关系-有规律的周期循环与要算准的日期星期-周期排班与公倍数',
    subtype: '有规律的周期循环与要算准的日期星期',
    attempts: 21,
    mastery: 69,
    mastery_confidence: 91,
  },
];

assert.equal(relatedRows(cow, rows).length, 0);
assert.equal(relatedRows(date, rows).length, 2);
assert.equal(cardRow(date, rows, (row) => row.mastery).score, 44);

const ziliao = { name: 'ABRX类 · 基期量计算与比较' };
const ziliaoRows = [
  { kaodian: '资料分析-ABRX类-基期量计算与比较', mastery: 55, mastery_confidence: 80 },
  { kaodian: '资料分析-基期量-基期量计算', mastery: 40, mastery_confidence: 50 },
];
assert.equal(relatedRows(ziliao, ziliaoRows).length, 2);

const md = cardToMarkdown({
  steps: ['观察尾数'],
  know: ['平方差：a^2 - b^2 = (a + b)(a - b)'],
  ban: ['选项接近时不要截两位'],
  anchors: ['PDF p4'],
});
assert.match(md, /#### 怎么做/);
assert.match(md, /\$a\^\{2\}/);
assert.match(md, /#### 禁止/);

console.log('knowledge card markdown: ok');

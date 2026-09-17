import assert from 'node:assert/strict';

import { cardRow, relatedRows } from '../src/knowledge/match.js';
import { cardToMarkdown, decorateMath } from '../src/knowledge/cardMarkdown.js';
import { findFenbiTarget, leftoverRows, mergeFenbiTree, parseFenbiTag, rowsForTag } from '../src/knowledge/fenbiTree.js';

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

const tree = mergeFenbiTree(
  [
    {
      kaodian: '数量关系-逢考必有的排列组合与概率-分堆分配与定序消序',
      mastery: 62,
      mastery_confidence: 80,
    },
    {
      kaodian: '数量关系-数学运算-平均数问题-加权平均数',
      mastery: 40,
      mastery_confidence: 30,
    },
  ],
  [
    {
      alias: '数量关系-逢考必有的排列组合与概率-分堆分配与定序消序',
      canonical: '数量关系-数学运算-排列组合问题',
    },
  ],
);
const shuliang = tree.find((mod) => mod.id === 'shuliang');
const math = shuliang.children.find((g) => g.name === '数学运算');
const perm = math.children.find((leaf) => leaf.name === '排列组合问题');
const avg = math.children.find((leaf) => leaf.name === '平均数问题');
assert.equal(perm.score, 62);
assert.equal(avg.extensions.length, 1);
assert.equal(avg.extensions[0].name, '加权平均数');
assert.equal(parseFenbiTag('判断推理-逻辑判断-组合排列-单题').l3, '组合排列-单题');
assert.equal(rowsForTag('数量关系-数学运算-排列组合问题', [
  { kaodian: '数量关系-逢考必有的排列组合与概率-分堆分配与定序消序' },
]).length, 1);

const staticTree = mergeFenbiTree([
  {
    kaodian: '数量关系-逢考必有的排列组合与概率-分堆分配与定序消序',
    mastery: 55,
    mastery_confidence: 70,
  },
]);
const staticPerm = staticTree
  .find((mod) => mod.id === 'shuliang')
  .children.find((g) => g.name === '数学运算')
  .children.find((leaf) => leaf.name === '排列组合问题');
assert.equal(staticPerm.score, 55);

const leftovers = leftoverRows([
  { kaodian: '数量关系-逢考必有的排列组合与概率-分堆分配与定序消序' },
  { kaodian: '资料分析-ABRX类-基期量计算与比较' },
]);
assert.equal(leftovers.length, 1);
assert.equal(leftovers[0].kaodian, '资料分析-ABRX类-基期量计算与比较');

const jumped = findFenbiTarget('数量关系-既烧脑又能套公式的最值问题-最不利原则与抽屉');
assert.equal(jumped.tag, '数量关系-数学运算-最值问题');
assert.equal(jumped.moduleId, 'shuliang');

console.log('knowledge card markdown: ok');

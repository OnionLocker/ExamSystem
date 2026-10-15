// 考点预热：题目标签 → 三级知识点；题组列表的考点数；每日复习卷按选点顺序带原因。
import assert from 'node:assert/strict';
import Database from 'better-sqlite3';

import { batchKnowledge, knowledgeCounts } from '../server/batchKnowledge.js';
import { topicOf } from '../server/knowledgeContent.js';

const AVG = '数量关系-数学运算-平均数问题';
const PERM = '数量关系-数学运算-排列组合问题';
const ROAD = '数量关系-数学运算-行程问题';

// 子考法节点、旧的子考法名、三级本身都落到同一个三级；对不上的返回 null
assert.equal(topicOf(`${AVG}-@average-baseline-shift`).tag, AVG);
assert.equal(topicOf(`${PERM}-捆绑法`).tag, PERM);
assert.equal(topicOf(AVG).title, '平均数问题');
assert.equal(topicOf('数量关系-数学运算'), null);
assert.equal(topicOf(''), null);

const db = new Database(':memory:');
db.exec(`
  CREATE TABLE questions (id INTEGER PRIMARY KEY, batch_id TEXT, tags TEXT);
  CREATE TABLE kaodian_aliases (alias TEXT PRIMARY KEY, canonical TEXT NOT NULL, module TEXT NOT NULL);
  CREATE TABLE daily_review_plans (batch_id TEXT PRIMARY KEY, plan_date TEXT NOT NULL, module TEXT NOT NULL,
    plan_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
`);
db.prepare('INSERT INTO kaodian_aliases VALUES (?, ?, ?)').run('排列组合', PERM, '数量关系');
const add = db.prepare('INSERT INTO questions (batch_id, tags) VALUES (?, ?)');
const daily = 'daily-20261016-shuliang-abc';
for (const tag of [`${AVG}-@average-baseline-shift`, `${ROAD}-@speed-change-ratio`, `${AVG}-@weighted-average-cross`,
  '排列组合', `${ROAD}-@multi-encounter-circular`, `${ROAD}-@speed-change-ratio`]) {
  add.run(daily, JSON.stringify([tag]));
}
add.run('20261014_hermes_jishu_02', JSON.stringify(['数量关系-数学运算-计数模型问题-@x']));
add.run('20261014_hermes_jishu_02', JSON.stringify(['数量关系-数学运算-计数模型问题-@y']));
add.run('old-batch', JSON.stringify(['完全对不上的旧标签']));
add.run('old-batch', 'not json');

const counts = knowledgeCounts(db);
assert.equal(counts.get(daily), 3);
assert.equal(counts.get('20261014_hermes_jishu_02'), 1);
assert.equal(counts.has('old-batch'), false);

// 没有选点记录：按题量从多到少，一样多时保持出现顺序
let result = batchKnowledge(db, daily);
assert.equal(result.total, 6);
assert.equal(result.plan, null);
assert.deepEqual(result.points.map((p) => [p.title, p.count, p.reason]), [
  ['行程问题', 3, ''], ['平均数问题', 2, ''], ['排列组合问题', 1, ''],
]);

// 每日复习卷：按凌晨选点的优先顺序排，带上原因
db.prepare('INSERT INTO daily_review_plans (batch_id, plan_date, module, plan_json) VALUES (?, ?, ?, ?)').run(
  daily, '2026-10-16', '数量关系', JSON.stringify({
    plan_date: '2026-10-16', module: '数量关系',
    points: [
      { tag: PERM, reason: '9 天没练，估计还记得 63%' },
      { tag: AVG, reason: '3 天没练，估计还记得 77%；两轮新题没改善，先少量' },
      { tag: ROAD, reason: '10 天没练，估计还记得 66%' },
    ],
  }),
);
result = batchKnowledge(db, daily);
assert.deepEqual(result.plan, { plan_date: '2026-10-16', module: '数量关系' });
assert.deepEqual(result.points.map((p) => p.title), ['排列组合问题', '平均数问题', '行程问题']);
assert.equal(result.points[1].reason, '3 天没练，估计还记得 77%；两轮新题没改善，先少量');

// 选点记录坏了不影响列知识点；题组不存在返回 null
db.prepare('UPDATE daily_review_plans SET plan_json = ? WHERE batch_id = ?').run('{bad', daily);
assert.equal(batchKnowledge(db, daily).points.length, 3);
assert.equal(batchKnowledge(db, 'missing'), null);

console.log('batch knowledge ok');

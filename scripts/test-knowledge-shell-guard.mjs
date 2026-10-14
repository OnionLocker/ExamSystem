// 知识点内容的 shell 损坏防线：公式被 bash 展开过的补丁不能入库，正常公式不能误伤。
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { openKnowledgeStore, shellDamage } from '../server/knowledgeContent.js';

// 真实损坏的样子：$$ 变成进程号、$n 被吃成空、两个被吃掉的变量拼成一段“公式”
for (const broken of [
  '3123430S_n = n \\times a_{\\text{中}}3123430',
  '当项数 $ 为奇数时，中心项 {\\text{中}}$（第 $\\frac{n+1}{2}$ 项）',
  '设组 1 人数 $、均值 $\\bar{x}_1$',
  '   - 男干警均值：5$；女干警均值：0$；',
  '移项得 \\frac{n_1}{n_2} = 3',
]) assert.ok(shellDamage(broken).length, broken);

// 正常写法都放行：行内/块级公式、中文下标、代码、转义的美元符号
const clean = [
  '当项数 $n$ 为奇数时：',
  '',
  '$$S_n = n \\times a_{\\text{中}}$$',
  '',
  '- 赋 $P_甲 = 3$，$P_乙 = 2$；两个月牙相加：$(A - 交集) + (B - 交集)$',
  '多行公式：',
  '$$',
  '\\frac{n_1}{n_2} = \\frac{\\bar{x}_2 - \\bar{X}}{\\bar{X} - \\bar{x}_1}',
  '$$',
  '命令写在代码里：`node scripts/knowledge-content.mjs get 标签`，价格 \\$5。',
  '```text\n$$ 这里是代码块，不检查 $n\n```',
  '![图](/q-images/diagrams/20261008/kc-2-tree-f186627a.svg)',
].join('\n');
assert.deepEqual(shellDamage(clean), []);
assert.deepEqual(shellDamage(undefined), []);

// apply 遇到损坏补丁直接拒绝（422），库里内容不变；干净补丁照常保存
const tmp = mkdtempSync(path.join(tmpdir(), 'kc-guard-'));
const db = path.join(tmp, 'knowledge.db');
const cli = (args, input) => spawnSync(process.execPath, [new URL('./knowledge-content.mjs', import.meta.url).pathname, ...args],
  { encoding: 'utf8', input, env: { ...process.env, EXAM_KNOWLEDGE_DB: db } });
try {
  const tag = '数量关系-数学运算-数列问题';
  const before = JSON.parse(cli(['get', tag]).stdout);
  const patch = (markdown) => JSON.stringify({ revision: before.revision, op: 'update', id: 'overview', markdown });
  const bad = cli(['apply', tag, '-'], patch('奇数项求和 3123430S_n = n \\times a3123430'));
  assert.equal(bad.status, 1);
  const err = JSON.parse(bad.stderr);
  assert.equal(err.status, 422);
  assert.match(err.error, /shell 展开/);
  assert.match(err.error, /write_file|heredoc/);
  const store = openKnowledgeStore(db);
  assert.equal(store.get(tag).revision, before.revision);
  store.close();
  const file = path.join(tmp, 'patch.json');
  writeFileSync(file, patch('奇数项：\n\n$$S_n = n \\times a_{\\text{中}}$$'));
  const ok = cli(['apply', tag, file]);
  assert.equal(ok.status, 0, ok.stderr);
  assert.equal(JSON.parse(ok.stdout).revision, before.revision + 1);
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

console.log('knowledge shell guard ok');

import assert from 'node:assert/strict';
import { openKnowledgeStore, nodeTag } from '../server/knowledgeContent.js';

const store = openKnowledgeStore(':memory:');
const tag = '数量关系-数学运算-概率问题';
try {
  const original = store.get(tag);
  assert.equal(original.nodes.length, 9);
  const changed = store.mutate(tag, {
    op: 'update', id: 'equal-groups', revision: original.revision,
    markdown: '## 核心公式\n\n$$P=(k-1)/(N-1)$$',
  });
  assert.equal(changed.nodes.find(n => n.id === 'equal-groups').markdown, '## 核心公式\n\n$$P=(k-1)/(N-1)$$');
  assert.equal(changed.changed.evidenceChanged, false);
  assert.equal(nodeTag(tag, changed.nodes.find(n => n.id === 'equal-groups')), `${tag}-@equal-groups`);
  assert.throws(() => store.mutate(tag, {
    op: 'update', id: 'equal-groups', revision: original.revision, title: '过期修改',
  }), e => e.status === 409);

  const rev = changed.revision;
  const created = store.mutate(tag, {
    op: 'create', id: 'conditional-groups', parentId: 'grouping', title: '指定条件下分组',
    summary: '给定部分成员去向后重新计算。', revision: rev,
  });
  assert.equal(created.nodes.find(n => n.id === 'conditional-groups').parentId, 'grouping');
  assert.throws(() => store.mutate(tag, {
    op: 'update', id: 'grouping', parentId: 'conditional-groups', revision: created.revision,
  }), e => /自身或子节点/.test(e.message));

  const archived = store.mutate(tag, {
    op: 'archive', id: 'grouping', revision: created.revision,
  });
  assert(!archived.nodes.some(n => n.id === 'equal-groups'));
  const restored = store.mutate(tag, {
    op: 'restore', id: 'grouping', revision: archived.revision,
  });
  assert(restored.nodes.some(n => n.id === 'equal-groups'));
  assert.equal(restored.revision, 4);
  console.log('Knowledge content CRUD, version conflicts, hierarchy, and archive/restore passed.');
} finally { store.close(); }

import assert from 'node:assert/strict';
import { openKnowledgeStore, nodeTag } from '../server/knowledgeContent.js';

const store = openKnowledgeStore(':memory:');
const tag = '数量关系-数学运算-概率问题';
try {
  const logic = store.catalog('判断推理-逻辑判断');
  assert(logic.length > 1);
  assert(logic.every(t => t.tag.startsWith('判断推理-逻辑判断-')));
  assert(store.catalog('判断推理').length > logic.length);
  assert.equal(store.catalog(tag).length, 1);
  assert.equal(store.catalog('判断').length, 0);
  const engineering = '数量关系-数学运算-工程问题';
  const initialEngineering = store.get(engineering);
  const ownCard = initialEngineering.nodes.find(n => n.id === 'engineering-problem');
  const engineeringCatalog = () => store.catalog(engineering)[0].nodes;
  assert(engineeringCatalog().find(n => n.tag === engineering).definition.includes(ownCard.markdown));
  assert.equal(engineeringCatalog().find(n => n.tag.endsWith('-@engineering-problem')).referenceOnly, true);
  const average = store.catalog('数量关系-数学运算-平均数问题')[0];
  assert(!average.nodes.some(n => n.id === 'num-theory-basic-calc'));
  const numberSeries = store.catalog('数量关系-数学运算-数列问题')[0];
  assert(!numberSeries.nodes.some(n => n.id === 'num-theory-basic-calc'));
  const otherTopic = '数量关系-数学运算-溶液问题';
  store.mutate(otherTopic, { op: 'create', id: ownCard.id, parentId: 'overview', revision: 0,
    title: ownCard.title, summary: ownCard.summary, markdown: ownCard.markdown });
  assert(!store.catalog(otherTopic)[0].nodes.find(n => n.tag === otherTopic).definition.includes(ownCard.markdown));
  for (const title of ['中心理解题', '标题填入题', '细节判断题', '词句理解题']) {
    const sharedTag = `言语理解与表达-片段阅读-${title}`;
    assert(!store.catalog(sharedTag)[0].nodes.find(n => n.tag === sharedTag).definition.includes('## 解题步骤'));
  }
  store.mutate(engineering, { op: 'archive', id: ownCard.id, revision: 0 });
  assert(!engineeringCatalog().find(n => n.tag === engineering).definition.includes(ownCard.markdown));
  store.mutate(engineering, { op: 'restore', id: ownCard.id, revision: 1 });
  store.mutate(engineering, { op: 'update', id: ownCard.id, revision: 2, markdown: '自定义子考点边界' });
  assert(!engineeringCatalog().find(n => n.tag === engineering).definition.includes('自定义子考点边界'));
  store.mutate(engineering, { op: 'update', id: ownCard.id, revision: 3, markdown: ownCard.markdown });
  store.mutate(engineering, { op: 'update', id: 'overview', revision: 4,
    summary: '只练单队效率变化', markdown: '以这段用户新定义为准。' });
  const customDefinition = engineeringCatalog().find(n => n.tag === engineering).definition;
  assert(customDefinition.includes('只练单队效率变化'));
  assert(customDefinition.includes('以这段用户新定义为准。'));
  assert(!customDefinition.includes(ownCard.markdown));
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

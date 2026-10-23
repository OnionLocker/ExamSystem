import assert from 'node:assert/strict';
import tree from '../src/knowledge/fenbiTree.json' with { type: 'json' };
import { FORMULA_GROUPS } from '../src/cheatsheet/formulas.js';

const tags = new Set();
for (const mod of tree.modules) {
  for (const group of mod.children || []) {
    for (const leaf of group.children || []) {
      tags.add(`${mod.name}-${group.name}-${leaf.name}`);
    }
  }
}

const seen = new Set();
let sections = 0;
for (const group of FORMULA_GROUPS) {
  assert.ok(group.id && group.name, '分组缺 id 或名称');
  assert.ok(group.sections?.length, `${group.name} 没有小节`);
  for (const section of group.sections) {
    sections += 1;
    const where = `${group.name} / ${section.title || '(无标题)'}`;
    assert.ok(section.title, `${where} 缺标题`);
    assert.equal(seen.has(`${group.id}:${section.title}`), false, `${where} 标题重复`);
    seen.add(`${group.id}:${section.title}`);
    assert.ok(section.tag, `${where} 没有挂考点`);
    assert.ok(tags.has(section.tag), `${where} 挂了知识点树上没有的考点：${section.tag}`);
    const formulas = section.formulas || [];
    const tables = section.tables || [];
    assert.ok(formulas.length + tables.length > 0, `${where} 没有公式也没有对照表`);
    for (const formula of formulas) {
      assert.ok(formula.name && formula.formula, `${where} 有一条公式缺名称或式子`);
    }
    for (const table of tables) {
      assert.ok(table.columns?.length && table.rows?.length, `${where} 的对照表是空的`);
      for (const row of table.rows) {
        assert.equal(row.length, table.columns.length, `${where} 的对照表有一行和表头对不齐`);
      }
    }
  }
}

assert.ok(sections >= 40, `小节太少：${sections}`);
console.log(`cheatsheet ok: ${FORMULA_GROUPS.length} groups, ${sections} sections, all tags on the tree`);

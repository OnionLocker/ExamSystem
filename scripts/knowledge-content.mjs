#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { openKnowledgeStore, nodeTag, topics } from '../server/knowledgeContent.js';
const [command, tag, arg] = process.argv.slice(2);
const store = openKnowledgeStore();
try {
  let result;
  if (command === 'find') result = topics.filter(t => !tag || t.tag.includes(tag)).map(({ tag, title }) => ({ tag, title }));
  else if (command === 'get') {
    const doc = store.get(tag);
    result = arg ? { tag, revision: doc.revision, node: doc.nodes.find(n => n.id === arg) || null } : doc;
  } else if (command === 'outline') {
    const doc = store.get(tag);
    result = { tag, revision: doc.revision, nodes: doc.nodes.map(({ markdown: _markdown, ...n }) => ({ ...n, linkTag: nodeTag(tag, n) })) };
  } else if (command === 'apply') {
    if (!arg) throw new Error('apply 需要一个 JSON 文件路径或 -（标准输入）');
    const doc = store.mutate(tag, JSON.parse(readFileSync(arg === '-' ? 0 : arg, 'utf8')));
    result = { tag, revision: doc.revision, changed: doc.changed };
  } else throw new Error('用法: node scripts/knowledge-content.mjs find 关键词 | outline 完整标签 | get 完整标签 [节点id] | apply 完整标签 补丁.json');
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(JSON.stringify({ error: err.message, status: err.status || 400 }));
  process.exitCode = 1;
} finally { store.close(); }

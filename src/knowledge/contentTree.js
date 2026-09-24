export const contentTag = (tag, node) => node.id === 'overview' ? tag : `${tag}-@${node.id}`;
export function findContentNode(topic, tag) {
  if (!topic) return null;
  return topic.nodes.find(n => contentTag(topic.tag, n) === tag || n.aliases?.includes(tag))
    || topic.nodes.find(n => n.parentId && tag === `${topic.tag}-${n.title}`) || null;
}
export function contentTrail(topic, node) {
  const trail = [];
  for (let n = node; n; n = topic.nodes.find(p => p.id === n.parentId)) trail.unshift(n);
  return trail;
}
export function withContentTree(tree, topics) {
  return tree.map(m => ({ ...m, children: m.children.map(g => ({ ...g, children: g.children.map(leaf => {
    const topic = topics.find(t => t.tag === leaf.tag);
    if (!topic) return leaf;
    const branch = parentId => topic.nodes.filter(n => n.parentId === parentId)
      .sort((a, b) => a.order - b.order).map(n => {
        const old = leaf.extensions.find(e => findContentNode(topic, e.tag)?.id === n.id);
        return { ...old, name: n.title, tag: contentTag(leaf.tag, n), children: branch(n.id), contentNode: true };
      });
    return { ...leaf, name: topic.nodes.find(n => n.id === 'overview')?.title || leaf.name,
      extensions: [...branch('overview'), ...leaf.extensions.filter(e => !findContentNode(topic, e.tag))] };
  }) })) }));
}

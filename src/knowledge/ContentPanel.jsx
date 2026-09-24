import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { api } from '../api.js';
import { contentTag, contentTrail, findContentNode } from './contentTree.js';
import './content.css';

const mathOptions = { throwOnError: false, strict: false };
export default function ContentPanel({ rootTag, learningTag, selectedTag, onSelect, active, onDiscuss, legacy }) {
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [learning, setLearning] = useState({ status: 'unstarted' });
  const [learningSaving, setLearningSaving] = useState(false);
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const [data, learningData] = await Promise.all([
          api(`/api/knowledge-content/${encodeURIComponent(rootTag)}`),
          api(`/api/kaodian/learning/${encodeURIComponent(learningTag)}`),
        ]);
        if (!cancelled) { setDoc(data); setLearning(learningData || { status: 'unstarted' }); setError(''); }
      } catch (e) { if (!cancelled) setError(e.message); }
      finally { loading = false; }
    };
    load();
    const onFocus = () => { if (document.visibilityState === 'visible') load(); };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    const timer = setInterval(onFocus, 15000);
    return () => { cancelled = true; clearInterval(timer); window.removeEventListener('focus', onFocus); document.removeEventListener('visibilitychange', onFocus); };
  }, [rootTag, learningTag, active, reload]);
  const node = findContentNode(doc, selectedTag);
  const trail = node ? contentTrail(doc, node) : [];
  const children = doc?.nodes.filter(n => n.parentId === node?.id).sort((a, b) => a.order - b.order) || [];
  const siblings = node?.parentId ? doc.nodes.filter(n => n.parentId === node.parentId).sort((a, b) => a.order - b.order) : [];
  const select = n => { setEditing(null); onSelect(contentTag(rootTag, n)); };
  const save = async () => {
    setSaving(true);
    try {
      const data = await api(`/api/knowledge-content/${encodeURIComponent(rootTag)}`, {
        method: 'PATCH', body: { op: 'update', id: editing.id, revision: editing.revision, title: editing.title, summary: editing.summary, markdown: editing.markdown },
      });
      setDoc(data); setEditing(null); setError(''); window.dispatchEvent(new Event('knowledge-content-changed'));
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };
  const setLearningStatus = async (status) => {
    setLearningSaving(true);
    try {
      const next = await api(`/api/kaodian/learning/${encodeURIComponent(learningTag)}`, { method: 'PUT', body: { status } });
      setLearning(next);
    } catch (e) { setError(e.message); }
    finally { setLearningSaving(false); }
  };
  const learningLabel = {
    unstarted: '待学习', unconfirmed: '尚未确认学过', learning: '学习中',
    learned: '已学 · 待检验', reinforce: '待巩固', debt: '知识债', cleared: '已清偿',
  }[learning.status] || '待学习';
  return <section className="knowledge-content">
    {error && <div role="alert" className="knowledge-error">{error} <button onClick={() => setReload(x => x + 1)}>重新读取</button></div>}
    {!doc ? <p className="p-6 text-slate-500" role="status">正在读取当前知识点…</p> : !node ? <div className="knowledge-paper">
      <h2>{selectedTag.split('-').at(-1)}</h2><p>这个考法已有学习记录，尚未整理独立讲解。</p>
      <button className="knowledge-action" onClick={() => onDiscuss(selectedTag)}>让 Hermes 整理这个考法</button>
      <button className="knowledge-action" onClick={() => onSelect(rootTag)}>返回知识点总览</button>
    </div> : <>
      <nav aria-label="知识点路径" className="knowledge-breadcrumb">
        {trail.map((n, i) => <span key={n.id}>{i > 0 && <span aria-hidden="true"> / </span>}<button aria-current={n.id === node.id ? 'page' : undefined} onClick={() => select(n)}>{n.title}</button></span>)}
      </nav>
      <header className="knowledge-heading">
        <div><p className="knowledge-eyebrow">{node.parentId ? '考法精讲' : '知识点总览'}</p><h2>{node.title}</h2><p className="knowledge-summary">{node.summary}</p></div>
        <div className="knowledge-actions">
          <span className={`knowledge-status knowledge-status-${learning.status}`} title={`学习状态按“${learningTag}”及其考法记录`}>{learningTag.split('-').at(-1)} · {learningLabel}</span>
          {(learning.status === 'unstarted' || learning.status === 'unconfirmed') && <button className="knowledge-action" disabled={learningSaving} onClick={() => setLearningStatus('learning')}>开始学习</button>}
          {learning.status === 'learning' && <button className="knowledge-action knowledge-action-primary" disabled={learningSaving} onClick={() => setLearningStatus('learned')}>我已学过</button>}
          <button className="knowledge-action" onClick={() => onDiscuss(contentTag(rootTag, node), node.title)}>和 Hermes 讨论</button>
          <button className="knowledge-action" onClick={() => setEditing({ ...node, revision: doc.revision })}>编辑本页</button>
        </div>
      </header>
      {siblings.length > 1 && <nav className="knowledge-tabs" aria-label="同级考法">{siblings.map(n => <button key={n.id} aria-current={n.id === node.id ? 'page' : undefined} onClick={() => select(n)}>{n.title}</button>)}</nav>}
      {children.length > 0 && node.parentId && <nav className="knowledge-tabs knowledge-child-tabs" aria-label="细分考法">{children.map(n => <button key={n.id} onClick={() => select(n)}>{n.title} <span aria-hidden="true">↗</span></button>)}</nav>}
      {editing && editing.id === node.id ? <div className="knowledge-editor">
        <label>标题<input value={editing.title} onChange={e => setEditing({ ...editing, title: e.target.value })} maxLength={100} /></label>
        <label>一句话摘要<input value={editing.summary} onChange={e => setEditing({ ...editing, summary: e.target.value })} maxLength={500} /></label>
        <label>正文（Markdown；行内公式用 $…$，独立公式用 $$…$$）<textarea rows={22} value={editing.markdown} onChange={e => setEditing({ ...editing, markdown: e.target.value })} /></label>
        <button className="knowledge-action" disabled={saving} onClick={save}>{saving ? '保存中…' : '保存本页'}</button>
        <button className="knowledge-action" disabled={saving} onClick={() => setEditing(null)}>取消</button>
      </div> : <article className="knowledge-paper knowledge-markdown">
        {node.markdown ? <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[[rehypeKatex, mathOptions]]}
          components={{ table: ({ children }) => <div className="knowledge-table"><table>{children}</table></div> }}>{node.markdown}</ReactMarkdown>
          : <p className="text-slate-500">从下方选择要学习的考法；也可以和 Hermes 讨论，补充本页总览。</p>}
      </article>}
      {children.length > 0 && <section className="knowledge-methods" aria-label="下级考法">
        {children.map((n, i) => <button key={n.id} onClick={() => select(n)}><span className="knowledge-method-number">{String(i + 1).padStart(2, '0')}</span><div><h3>{n.title}</h3><p>{n.summary || '查看解题步骤与知识讲解'}</p></div><span aria-hidden="true">→</span></button>)}
      </section>}
      {legacy}
    </>}
  </section>;
}

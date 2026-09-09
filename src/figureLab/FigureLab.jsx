import { useEffect, useMemo, useState } from 'react';

const CATALOG_URL = '/figure-lab/catalog.json?v=abc1';

const FigureLab = () => {
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('全部');
  const [active, setActive] = useState(null);

  useEffect(() => {
    let live = true;
    fetch(CATALOG_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`catalog ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (live) setCatalog(data);
      })
      .catch((err) => {
        if (live) setError(String(err.message || err));
      });
    return () => {
      live = false;
    };
  }, []);

  const batch = catalog?.groups?.[0];
  const items = useMemo(() => {
    if (!batch) return [];
    return batch.items.map((item) => ({ ...item, group: batch.title }));
  }, [batch]);

  const visible = items.filter((item) => {
    if (filter === '过审') return item.ok;
    if (filter === '未过审') return !item.ok;
    return true;
  });

  if (error) {
    return <p className="px-8 text-red-600">图样未生成：{error}</p>;
  }
  if (!catalog) {
    return <p className="px-8 text-slate-400">正在载入图样…</p>;
  }

  return (
    <div className="px-6 pb-16 max-w-6xl">
      <p className="text-sm text-[#666] mb-5">
        {batch?.title || '批次1'} · {items.length} 张 · {items.filter((i) => i.ok).length} 过审
      </p>
      <div className="flex flex-wrap gap-2 mb-6">
        {['全部', '过审', '未过审'].map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setFilter(name)}
            className={`px-3 py-1.5 rounded-full text-sm border ${
              filter === name
                ? 'bg-[#1a1a1a] text-white border-[#1a1a1a]'
                : 'bg-white border-slate-200 text-slate-600'
            }`}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {visible.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setActive(item)}
            className="text-left bg-white border border-slate-200 rounded-2xl overflow-hidden hover:border-slate-400"
          >
            <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between gap-3">
              <span className="font-medium">{item.title}</span>
              <span
                className={`text-xs shrink-0 px-2 py-0.5 rounded-full ${
                  item.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                }`}
              >
                {item.ok ? '过审' : '未过审'}
              </span>
            </div>
            <div className="bg-white p-3">
              <img
                src={`/figure-lab/${item.file}?v=abc1`}
                alt={item.title}
                className="w-full h-auto bg-white"
              />
            </div>
          </button>
        ))}
      </div>
      {active && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-6"
          onClick={() => setActive(null)}
        >
          <div
            className="bg-white rounded-2xl max-w-4xl w-full p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-black">
                {active.title}
                <span className={`ml-3 text-sm font-medium ${active.ok ? 'text-emerald-700' : 'text-amber-700'}`}>
                  {active.ok ? '过审' : '未过审'}
                </span>
              </h3>
              <button type="button" onClick={() => setActive(null)} className="text-slate-500">
                关闭
              </button>
            </div>
            <img
              src={`/figure-lab/${active.file}?v=abc1`}
              alt={active.title}
              className="w-full h-auto border border-slate-200"
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default FigureLab;

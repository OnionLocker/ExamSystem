import { useEffect, useMemo, useState } from 'react';

const CATALOG_URL = '/figure-lab/catalog.json';

const FigureLab = () => {
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState('');
  const [group, setGroup] = useState('全部');
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

  const items = useMemo(() => {
    if (!catalog) return [];
    return catalog.groups.flatMap((g) =>
      g.items.map((item) => ({ ...item, group: g.title })),
    );
  }, [catalog]);

  const visible = group === '全部' ? items : items.filter((item) => item.group === group);
  const groups = catalog ? ['全部', ...catalog.groups.map((g) => g.title)] : [];

  if (error) {
    return <p className="px-8 text-red-600">图样未生成：{error}</p>;
  }
  if (!catalog) {
    return <p className="px-8 text-slate-400">正在载入图样…</p>;
  }

  return (
    <div className="px-6 pb-16 max-w-6xl">
      <p className="text-sm text-[#666] mb-5">
        黑白线稿预览，还没接出题。看透视、贴纸和符号清不清。
      </p>
      <div className="flex flex-wrap gap-2 mb-6">
        {groups.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setGroup(name)}
            className={`px-3 py-1.5 rounded-full text-sm border ${
              group === name
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
            <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
              <span className="font-medium">{item.title}</span>
              <span className="text-xs text-slate-400">{item.group}</span>
            </div>
            <div className="bg-white p-3">
              <img
                src={`/figure-lab/${item.file}`}
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
              <h3 className="font-black">{active.title}</h3>
              <button type="button" onClick={() => setActive(null)} className="text-slate-500">
                关闭
              </button>
            </div>
            <img
              src={`/figure-lab/${active.file}`}
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

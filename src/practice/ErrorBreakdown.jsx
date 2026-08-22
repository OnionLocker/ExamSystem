// 结算页的错因分布：一场练完，比"错了 3 道"更有用的是"这 3 道错在哪"
import { summarizeErrors } from './errorKinds.js';

const ErrorBreakdown = ({ records }) => {
  const dist = summarizeErrors(records || []);
  if (dist.length === 0) return null;

  const total = dist.reduce((s, d) => s + d.count, 0);
  const main = dist.find((d) => d.code !== 'skipped') || dist[0];
  // 只有一类错因时，占比条和文字说的是同一件事，条就没必要了
  const showBar = dist.length > 1;

  return (
    <div className="bg-white rounded-[2rem] p-6 border border-[#e8d5b0]">
      <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">
        错在哪里
      </p>

      {showBar && (
        <div className="flex h-2.5 rounded-full overflow-hidden mb-5">
          {dist.map((d) => (
            <div
              key={d.code}
              style={{ width: `${(d.count / total) * 100}%`, backgroundColor: d.color }}
              title={`${d.label} ${d.count} 道`}
            />
          ))}
        </div>
      )}

      <div className="space-y-2.5">
        {dist.map((d) => (
          <div key={d.code} className="flex items-center space-x-3">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: d.color }}
            />
            <span className="text-sm font-bold">{d.label}</span>
            <span className="text-xs font-black tabular-nums text-slate-400 ml-auto">
              {d.count} 道 · {d.pct}%
            </span>
          </div>
        ))}
      </div>

      <p className="mt-5 pt-4 border-t border-[#e8d5b0] text-xs font-bold text-slate-500 leading-relaxed">
        {main.hint}
      </p>
    </div>
  );
};

export default ErrorBreakdown;

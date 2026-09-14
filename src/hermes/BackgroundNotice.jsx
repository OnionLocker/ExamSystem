import { useState } from 'react';

// 优先用脚本自己回的那句话；没有就从 JSON 里挑字段拼一句。
// 别整段 JSON.parse——失败时 stdout 里混着 traceback 之类的非 JSON 内容。
const summarize = (notice) => {
  if (notice.message) return notice.message;
  const imported = notice.output.match(/"imported"\s*:\s*(\d+)/)?.[1];
  const batchId = notice.output.match(/"batch_id"\s*:\s*"([^"]+)"/)?.[1];
  const script = notice.command.match(/scripts\/([\w.-]+?)(?:\.py|\.mjs|\b)/)?.[1] || '后台任务';
  if (imported) return `已入库 ${imported} 题${batchId ? ` · ${batchId}` : ''}`;
  if (notice.exitCode === 0) return `${script} 已完成`;
  if (notice.exitCode == null) return `${script} 已结束`;
  return `${script} 失败 · 退出码 ${notice.exitCode}`;
};

const BackgroundNotice = ({ notice }) => {
  const [open, setOpen] = useState(false);
  const ok = notice.exitCode == null || notice.exitCode === 0;

  return (
    <div className="my-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`inline-flex max-w-full items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-bold transition-colors ${
          ok
            ? 'bg-black/[0.035] text-[#7b6a4a] hover:bg-black/[0.06]'
            : 'bg-[#b4231f]/10 text-[#b4231f] hover:bg-[#b4231f]/[0.16]'
        }`}
      >
        <span aria-hidden="true" className="text-[13px] leading-none">{ok ? '✓' : '⚠'}</span>
        <span className="truncate">{summarize(notice)}</span>
        <span
          aria-hidden="true"
          className={`text-[13px] leading-none opacity-50 transition-transform ${open ? 'rotate-90' : ''}`}
        >
          ›
        </span>
      </button>
      {open && (
        <pre className="mt-1.5 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-black/[0.04] p-3 text-[11px] leading-relaxed text-[#4a4336]">
          {notice.command ? `$ ${notice.command}\n\n` : ''}
          {notice.output || '（无输出）'}
        </pre>
      )}
    </div>
  );
};

export default BackgroundNotice;

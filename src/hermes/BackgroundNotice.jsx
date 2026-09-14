import { useState } from 'react';

// 出题脚本回 {"status":...,"batch_id":...,"imported":N,...}。
// 用正则挑那两个字段，别整段 JSON.parse——失败时 stdout 里混着别的内容。
const summarize = (notice) => {
  const imported = notice.output.match(/"imported"\s*:\s*(\d+)/)?.[1];
  const batchId = notice.output.match(/"batch_id"\s*:\s*"([^"]+)"/)?.[1];
  const script = notice.command.match(/scripts\/([\w.-]+?)(?:\.py|\.mjs|\b)/)?.[1];
  if (notice.exitCode === 0 && imported) {
    return `已入库 ${imported} 题${batchId ? ` · ${batchId}` : ''}`;
  }
  if (notice.exitCode === 0) return `${script || '后台任务'} 已完成`;
  return `${script || '后台任务'} 失败 · 退出码 ${notice.exitCode}`;
};

const BackgroundNotice = ({ notice }) => {
  const [open, setOpen] = useState(false);
  const ok = notice.exitCode === 0;

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

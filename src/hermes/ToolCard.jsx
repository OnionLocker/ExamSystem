// 工具调用卡片：默认收起，点开看参数与结果
import { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Check, AlertCircle } from 'lucide-react';

// 结果可能是字符串，也可能是 Hermes 解析后的对象
const resultText = (result) => {
  if (result == null) return '';
  if (typeof result === 'string') return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
};

const argsText = (tool) => {
  if (tool.args_text) return tool.args_text;
  if (!tool.args || Object.keys(tool.args).length === 0) return '';
  try {
    return JSON.stringify(tool.args, null, 2);
  } catch {
    return '';
  }
};

// 折叠状态下显示的一行摘要
const summary = (tool) => {
  const raw = tool.preview || tool.args_text || argsText(tool);
  if (!raw) return '';
  const flat = String(raw).replace(/\s+/g, ' ').trim();
  return flat.length > 80 ? `${flat.slice(0, 80)}…` : flat;
};

const MAX_SHOWN = 4000;

const ToolCard = ({ tool }) => {
  const [open, setOpen] = useState(false);

  const running = !tool.done;
  const failed = !!tool.error;
  const args = argsText(tool);
  const out = resultText(tool.result);
  const truncated = out.length > MAX_SHOWN;

  return (
    <div className="my-2 rounded-2xl border border-black/10 bg-black/[0.02] overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center space-x-2 px-3 py-2 text-left hover:bg-black/[0.03] transition-colors"
      >
        {open ? <ChevronDown size={14} className="text-[#999] shrink-0" />
              : <ChevronRight size={14} className="text-[#999] shrink-0" />}

        {running && <Loader2 size={13} className="text-[#fbc02d] animate-spin shrink-0" />}
        {!running && !failed && <Check size={13} className="text-[#4caf50] shrink-0" />}
        {failed && <AlertCircle size={13} className="text-[#ef5350] shrink-0" />}

        <span className="font-mono text-xs font-bold text-[#1a1a1a] shrink-0">{tool.name}</span>

        {!open && summary(tool) && (
          <span className="font-mono text-[11px] text-[#999] truncate">{summary(tool)}</span>
        )}

        <span className="flex-1" />

        {typeof tool.duration_s === 'number' && (
          <span className="text-[10px] font-bold text-[#bbb] shrink-0">
            {tool.duration_s < 1 ? `${Math.round(tool.duration_s * 1000)}ms` : `${tool.duration_s.toFixed(1)}s`}
          </span>
        )}
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-black/5">
          {args && (
            <div>
              <div className="mt-2 mb-1 text-[10px] font-black uppercase tracking-widest text-[#999]">参数</div>
              <pre className="p-2 rounded-lg bg-white/70 border border-black/5 text-[11px] font-mono overflow-x-auto whitespace-pre-wrap break-all max-h-64 overflow-y-auto">
                {args}
              </pre>
            </div>
          )}
          {out && (
            <div>
              <div className="mb-1 text-[10px] font-black uppercase tracking-widest text-[#999]">结果</div>
              <pre className="p-2 rounded-lg bg-white/70 border border-black/5 text-[11px] font-mono overflow-x-auto whitespace-pre-wrap break-all max-h-80 overflow-y-auto">
                {truncated ? `${out.slice(0, MAX_SHOWN)}\n…（已截断 ${out.length - MAX_SHOWN} 字符）` : out}
              </pre>
            </div>
          )}
          {!args && !out && (
            <div className="pt-2 text-[11px] text-[#999]">{running ? '执行中…' : '无输出'}</div>
          )}
        </div>
      )}
    </div>
  );
};

export default ToolCard;

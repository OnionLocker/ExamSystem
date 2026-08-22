// Hermes 回复的 Markdown 渲染
//
// 微信渠道不认 Markdown，这里是补上的那一环：
//   remark-gfm    表格 / 删除线 / 任务列表
//   remark-math + rehype-katex   LaTeX 公式（数资、资料分析必需）
//   highlight.js  代码块高亮
import { memo, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import hljs from 'highlight.js/lib/common';
import { Check, Copy } from 'lucide-react';

import 'katex/dist/katex.min.css';
import 'highlight.js/styles/github.css';
import './katex-fix.css';

// navigator.clipboard 只在安全上下文里存在：明文 HTTP 访问（预览端口 4173
// 走的就是 http，且不是 localhost）时它整个是 undefined，
// 于是只剩 execCommand('copy') 这条老路可走
const writeClipboard = async (text) => {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch { /* 权限被拒就落到 execCommand */ }
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.cssText = 'position:fixed;top:-9999px;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  ta.remove();
  return ok;
};

// 代码块：带语言标签和复制按钮
const CodeBlock = ({ language, code }) => {
  const [copyState, setCopyState] = useState('');

  const html = useMemo(() => {
    if (language && hljs.getLanguage(language)) {
      try {
        return hljs.highlight(code, { language, ignoreIllegals: true }).value;
      } catch { /* 落到自动检测 */ }
    }
    try {
      return hljs.highlightAuto(code).value;
    } catch {
      return null;
    }
  }, [code, language]);

  const copy = async () => {
    const ok = await writeClipboard(code);
    setCopyState(ok ? 'ok' : 'fail');
    setTimeout(() => setCopyState(''), 1800);
  };

  return (
    <div className="relative group my-3 rounded-2xl overflow-hidden border border-black/10 bg-[#efe0bc]">
      <div className="flex items-center justify-between px-4 py-2 bg-black/[0.03] border-b border-black/5">
        <span className="text-[10px] font-black uppercase tracking-widest text-[#999]">
          {language || 'code'}
        </span>
        <button
          onClick={copy}
          title="复制代码"
          className="flex items-center space-x-1 text-[10px] font-bold text-[#666] hover:text-[#1a1a1a] transition-colors"
        >
          {copyState === 'ok' ? <Check size={12} /> : <Copy size={12} />}
          <span>
            {copyState === 'ok' ? '已复制' : copyState === 'fail' ? '复制失败，请手选' : '复制'}
          </span>
        </button>
      </div>
      <pre className="px-4 py-3 overflow-x-auto text-[13px] leading-relaxed">
        {html
          ? <code dangerouslySetInnerHTML={{ __html: html }} />
          : <code>{code}</code>}
      </pre>
    </div>
  );
};

const components = {
  code({ inline, className, children, ...props }) {
    const text = String(children ?? '').replace(/\n$/, '');
    // react-markdown v10 里块级代码不传 inline，靠有无换行/语言类名判断更稳
    const language = /language-(\w+)/.exec(className || '')?.[1] || '';
    const isBlock = inline === false || !!language || text.includes('\n');

    if (!isBlock) {
      return (
        <code
          className="px-1.5 py-0.5 mx-0.5 rounded-md bg-black/[0.06] text-[#c2410c] text-[0.9em] font-mono"
          {...props}
        >
          {text}
        </code>
      );
    }
    return <CodeBlock language={language} code={text} />;
  },
  a({ children, ...props }) {
    return (
      <a
        {...props}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[#0369a1] underline decoration-[#0369a1]/30 hover:decoration-[#0369a1] break-all"
      >
        {children}
      </a>
    );
  },
  table({ children }) {
    return (
      <div className="my-3 overflow-x-auto rounded-xl border border-black/10">
        <table className="w-full text-sm border-collapse">{children}</table>
      </div>
    );
  },
  thead({ children }) {
    return <thead className="bg-black/[0.04]">{children}</thead>;
  },
  th({ children }) {
    return <th className="px-3 py-2 text-left font-black border-b border-black/10">{children}</th>;
  },
  td({ children }) {
    return <td className="px-3 py-2 border-b border-black/5 align-top">{children}</td>;
  },
  ul({ children }) {
    return <ul className="my-2 pl-5 space-y-1 list-disc marker:text-[#6b5428]">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="my-2 pl-5 space-y-1 list-decimal marker:text-[#999] marker:font-bold">{children}</ol>;
  },
  li({ children }) {
    return <li className="leading-relaxed">{children}</li>;
  },
  p({ children }) {
    return <p className="my-2 leading-[1.75] first:mt-0 last:mb-0">{children}</p>;
  },
  h1({ children }) {
    return <h1 className="mt-4 mb-2 text-lg font-black tracking-tight">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="mt-4 mb-2 text-base font-black tracking-tight">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="mt-3 mb-1.5 text-sm font-black tracking-tight">{children}</h3>;
  },
  h4({ children }) {
    return <h4 className="mt-3 mb-1.5 text-sm font-bold">{children}</h4>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="my-3 pl-4 border-l-[3px] border-[#6b5428] text-[#555] italic">
        {children}
      </blockquote>
    );
  },
  hr() {
    return <hr className="my-4 border-black/10" />;
  },
  strong({ children }) {
    return <strong className="font-black text-[#1a1a1a]">{children}</strong>;
  },
};

const KATEX_OPTIONS = {
  throwOnError: false,
  strict: false,
  // 行内 \frac 默认按 textstyle 排：分子分母被压到 0.7 倍字号、分数线紧贴分母，
  // 在 15px 正文里糊成一团，看着就像没有横线。统一按 \dfrac（display style）排，
  // 分子分母保持全字号，线的上下也留出间距。\dfrac 是内置函数，不会再触发本宏。
  //
  // minRuleThickness 是分数线/上划线的最小厚度（em）：默认 0.04em 在正文字号下
  // 算出来不到 1px，会被浏览器的亚像素舍入抹掉。它参与排版计算，所以加粗线条的
  // 同时会把分子分母的间距一起撑开 —— 这是单改 CSS border-width 做不到的。
  macros: { '\\frac': '\\dfrac' },
  minRuleThickness: 0.07,
};

// 流式输出时尾部的闪烁光标
const Caret = () => (
  <span
    aria-hidden
    className="inline-block w-[0.5em] h-[1.05em] ml-0.5 align-[-0.15em] bg-[#1a1a1a]/50 animate-pulse"
  />
);

const MarkdownMessage = memo(function MarkdownMessage({ content, streaming }) {
  return (
    <div className="katex-inline-host text-[15px] text-[#1a1a1a] break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, KATEX_OPTIONS]]}
        components={components}
      >
        {content || ''}
      </ReactMarkdown>
      {streaming && <Caret />}
    </div>
  );
});

export default MarkdownMessage;

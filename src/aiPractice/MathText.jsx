import { useMemo } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import '../hermes/katex-fix.css';

const KATEX = {
  throwOnError: false,
  strict: false,
  macros: { '\\frac': '\\dfrac' },
  minRuleThickness: 0.07,
};

const CHUNK = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;

const renderTex = (src, display) => {
  try {
    return katex.renderToString(src, { ...KATEX, displayMode: display });
  } catch {
    return null;
  }
};

export default function MathText({ text }) {
  const parts = useMemo(() => {
    const raw = text == null ? '' : String(text);
    if (!raw.includes('$')) return [raw];
    const out = [];
    let last = 0;
    const re = new RegExp(CHUNK.source, 'g');
    let match;
    while ((match = re.exec(raw))) {
      if (match.index > last) out.push(raw.slice(last, match.index));
      const display = match[1] != null;
      const html = renderTex(display ? match[1] : match[2], display);
      out.push(html == null ? match[0] : { html, display, key: match.index });
      last = match.index + match[0].length;
    }
    if (last < raw.length) out.push(raw.slice(last));
    return out.length ? out : [raw];
  }, [text]);

  return parts.map((part, index) => (
    typeof part === 'string'
      ? part
      : (
        <span
          key={part.key ?? index}
          className={part.display ? 'katex-display' : 'katex-inline-host'}
          dangerouslySetInnerHTML={{ __html: part.html }}
        />
      )
  ));
}

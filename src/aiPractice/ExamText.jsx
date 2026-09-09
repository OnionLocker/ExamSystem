import katex from 'katex';
import 'katex/dist/katex.min.css';
import '../hermes/katex-fix.css';
import { formatPlainSubscripts } from '../hermes/reviewFormat.js';

const stripBareLatex = (src = '') => String(src)
  .replace(/\\text\{([^}]*)\}/g, '$1')
  .replace(/\\mathrm\{([^}]*)\}/g, '$1')
  .replace(/\\,/g, ' ')
  .replace(/\\Omega/g, '\u03a9')
  .replace(/\\rho/g, '\u03c1')
  .replace(/\\circ/g, '\u00b0')
  .replace(/\^\s*\u00b0/g, '\u00b0')
  .replace(/\\\s/g, ' ');

const splitMath = (raw = '') => {
  const src = String(raw ?? '');
  const parts = [];
  let last = 0;
  for (const match of src.matchAll(/\$([^$]+)\$/g)) {
    if (match.index > last) parts.push({ type: 'text', text: src.slice(last, match.index) });
    parts.push({ type: 'math', tex: match[1] });
    last = match.index + match[0].length;
  }
  if (last < src.length || !parts.length) parts.push({ type: 'text', text: src.slice(last) });
  return parts;
};

export default function ExamText({ text, collapseBlank = false }) {
  return splitMath(text).flatMap((part, index) => {
    if (part.type === 'math') {
      const html = katex.renderToString(part.tex, { throwOnError: false, displayMode: false });
      return [
        <span
          key={`m${index}`}
          className="katex-inline-host"
          dangerouslySetInnerHTML={{ __html: html }}
        />,
      ];
    }
    return formatPlainSubscripts(stripBareLatex(part.text), { collapseBlank }).map((item, inner) => (
      item.type === 'sub'
        ? <span key={`${index}-${inner}`}>{item.base}<sub>{item.sub}</sub></span>
        : <span key={`${index}-${inner}`}>{item.text}</span>
    ));
  });
}


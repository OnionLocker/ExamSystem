import { formatPlainSubscripts } from '../hermes/reviewFormat.js';

export default function ExamText({ text, collapseBlank = false }) {
  return formatPlainSubscripts(text, { collapseBlank }).map((part, index) => (
    part.type === 'sub'
      ? <span key={index}>{part.base}<sub>{part.sub}</sub></span>
      : <span key={index}>{part.text}</span>
  ));
}

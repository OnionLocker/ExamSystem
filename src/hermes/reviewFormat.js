// 复盘原题块里，只有同一行挤了多个「A. / B. / C. / D.」才拆行。
// 题干里的「A、B、C三个地点」用的是顿号，不能拆。

const SQUEEZED_OPTIONS = /(?:\*\*)?([A-D])[.．](?:\*\*)?[ \t]+/g;

export function normalizeOriginalQuestionOptions(raw = '') {
  return String(raw).replace(
    /^(?:>[^\n]*(?:\n|$))+/gm,
    (block) => {
      if (!block.includes('原题')) return block;
      return block.split('\n').map((line) => {
        const labels = [...line.matchAll(SQUEEZED_OPTIONS)].map((match) => match[1]);
        if (new Set(labels).size < 2) return line;
        return line.replace(SQUEEZED_OPTIONS, '\n> **$1.** ').replace(/^\n/, '');
      }).join('\n');
    },
  );
}

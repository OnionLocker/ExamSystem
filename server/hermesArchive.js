// Hermes 复盘讲评归档：讲评正文只存在 Hermes 会话里，会话一删就没了。
// 这里只读 Hermes 的 state.db，把每场复盘的讲评和之后的追问写成 Markdown，
// 放在对应报告目录的 hermes/ 子目录下。同一场复盘重复归档会覆盖成最新内容。
import Database from 'better-sqlite3';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const STATE_DB = process.env.HERMES_STATE_DB
  || path.join(process.env.HERMES_HOME || path.join(os.homedir(), '.hermes'), 'state.db');
export const ARCHIVE_DIRS = {
  practice: path.join(ROOT, 'data', 'practice-reviews', 'hermes'),
  exam: path.join(ROOT, 'data', 'exam-reviews', 'hermes'),
  upload: path.join(ROOT, 'data', 'practice-reviews', 'hermes'),
};
const VOICE_DIR = path.join(ROOT, 'data', 'voice-notes');

const REVIEW_FILE_RE = /\/data\/(exam-reviews|practice-reviews)\/(\d+)-([^\n]+?)\.md/;
const UPLOAD_LEAD_RE = /下面这份 PDF 是我在粉笔做的练习卷《([^》\n]+)》/;
const USER_MESSAGE_RE = /\[USER_MESSAGE\]\n?([\s\S]*?)\n?\[\/USER_MESSAGE\]/;
const VOICE_NOTE_RE = /voice-notes\/(\d{8}-\d{6}(?:-\d{3})?-voice\.md)/;

const safeName = (s) => String(s).replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 80);
const stamp = (ts) => {
  const d = new Date(Number(ts) * 1000 + 8 * 3600 * 1000);
  return d.toISOString().slice(0, 16).replace(/-/g, '').replace('T', '-').replace(':', '');
};

const reviewOf = (text) => {
  if (/这是一项独立的错题打包任务/.test(text)) return null;
  const file = text.match(REVIEW_FILE_RE);
  if (file) {
    return {
      kind: file[1] === 'practice-reviews' ? 'practice' : 'exam',
      id: file[2],
      title: file[3],
      source: file[0].replace(/^\/data/, 'data'),
      audit: /复盘审核/.test(text),
    };
  }
  const upload = text.match(UPLOAD_LEAD_RE);
  return upload ? { kind: 'upload', id: 'upload', title: upload[1], source: '粉笔 PDF', audit: false } : null;
};

const voiceSaid = (name) => {
  try {
    const text = readFileSync(path.join(VOICE_DIR, name), 'utf8');
    return text.match(/^##[ \t]+我说了什么\r?\n([\s\S]*?)(?=^##[ \t]+|(?![\s\S]))/m)?.[1].trim() || '';
  } catch {
    return '';
  }
};

const userText = (content) => {
  const marked = content.match(USER_MESSAGE_RE)?.[1]?.trim() || '';
  const note = content.match(VOICE_NOTE_RE)?.[1];
  const said = note ? voiceSaid(note) : '';
  return said ? `${marked || '语音'}（语音笔记）\n\n${said}` : marked;
};

const fileOf = (seg) => {
  const name = seg.kind === 'upload'
    ? `upload-${safeName(seg.title)}-${stamp(seg.ts)}.md`
    : `${seg.id}-${safeName(seg.title)}-${stamp(seg.ts)}.md`;
  return path.join(ARCHIVE_DIRS[seg.kind], name);
};

const render = (seg, sessionId) => [
  `# Hermes 复盘讲评：${seg.title}`,
  '',
  `- 类型：${seg.audit ? '复盘审核' : seg.kind === 'exam' ? '录屏复盘' : seg.kind === 'upload' ? '粉笔 PDF 复盘' : 'AI 练题复盘'}`,
  seg.kind !== 'upload' ? `- 场次：${seg.id}` : null,
  `- 复盘时间：${stamp(seg.ts).replace(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})$/, '$1-$2-$3 $4:$5')}`,
  `- 系统报告：${seg.source}`,
  `- Hermes 会话：${sessionId}`,
  '',
  '## 讲评',
  '',
  seg.review.join('\n\n') || '（本场讲评未完成）',
  ...(seg.followups.length ? ['', '## 复盘后的追问', ''] : []),
  ...seg.followups.flatMap((f) => [
    `### 我：${f.user.split('\n')[0].slice(0, 60) || '（附件或语音）'}`,
    '',
    ...(f.user.includes('\n') ? [f.user.split('\n').slice(1).join('\n').trim(), ''] : []),
    ...f.replies.flatMap((r) => [r, '']),
  ]),
].filter((line) => line != null).join('\n').trimEnd() + '\n';

const segmentsOf = (rows) => {
  const segs = [];
  let cur = null;
  let follow = null;
  for (const row of rows) {
    const content = String(row.content || '');
    if (row.role === 'user') {
      const review = reviewOf(content);
      if (review) {
        cur = { ...review, ts: row.timestamp, review: [], followups: [] };
        follow = null;
        segs.push(cur);
      } else if (cur) {
        follow = { user: userText(content), replies: [] };
        cur.followups.push(follow);
      }
    } else if (cur && content.trim()) {
      (follow ? follow.replies : cur.review).push(content.trim());
    }
  }
  for (const seg of segs) seg.followups = seg.followups.filter((f) => f.replies.length);
  return segs.filter((s) => s.review.length);
};

// sessionId 为空时归档全部复盘会话。返回写出的文件。
export function archiveHermesReviews(sessionId = null) {
  if (!existsSync(STATE_DB)) return [];
  const db = new Database(STATE_DB, { readonly: true, fileMustExist: true });
  db.pragma('busy_timeout = 5000');
  try {
    const ids = sessionId ? [sessionId] : db.prepare(`
      SELECT DISTINCT session_id FROM messages WHERE role = 'user'
        AND (content LIKE '%/data/practice-reviews/%' OR content LIKE '%/data/exam-reviews/%'
          OR content LIKE '%下面这份 PDF 是我在粉笔做的练习卷%')`).all().map((r) => r.session_id);
    const rowsOf = db.prepare(`SELECT role, content, timestamp FROM messages
      WHERE session_id = ? AND role IN ('user', 'assistant') ORDER BY id`);
    const written = [];
    for (const id of ids) {
      for (const seg of segmentsOf(rowsOf.all(id))) {
        const file = fileOf(seg);
        mkdirSync(path.dirname(file), { recursive: true });
        writeFileSync(file, render(seg, id));
        written.push(path.relative(ROOT, file));
      }
    }
    return written;
  } finally {
    db.close();
  }
}

// 某场 AI 练题最早的一份 Hermes 讲评（复盘审核时对照用）
export function firstPracticeReview(practiceId) {
  const dir = ARCHIVE_DIRS.practice;
  if (!existsSync(dir)) return null;
  const name = readdirSync(dir).filter((f) => f.startsWith(`${practiceId}-`)).sort((a, b) => (
    a.slice(-16).localeCompare(b.slice(-16))
  ))[0];
  return name ? path.join(dir, name) : null;
}

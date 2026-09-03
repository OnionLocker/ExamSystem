// 录屏复盘：按 10 分钟无损切片（ffmpeg -c copy），每段原分辨率送给模型。
// 答案 PDF 原件给模型读，不再 pdftotext。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import db from './db.js';

const run = promisify(execFile);

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
export const VIDEO_DIR = path.join(ROOT, 'data', 'exam-videos');
export const RAW_DIR = path.join(VIDEO_DIR, 'raw');
export const PDF_DIR = path.join(ROOT, 'data', 'exam-pdfs');
for (const d of [VIDEO_DIR, RAW_DIR, PDF_DIR]) fs.mkdirSync(d, { recursive: true });

const MODEL = process.env.EXAM_ANALYSIS_MODEL || 'gemini-3.8-flash-high';
const PROXY = (process.env.CLIPROXY_BASE_URL || 'http://127.0.0.1:8889/v1').replace(/\/v1\/?$/, '');
const SEGMENT_SEC = 600;

const readKey = () => {
  if (process.env.CLIPROXY_API_KEY) return process.env.CLIPROXY_API_KEY.trim();
  try {
    const t = fs.readFileSync(path.join(os.homedir(), '.hermes', '.env'), 'utf8');
    const line = t.split('\n').find((l) => l.startsWith('CLIPROXY_API_KEY='));
    if (line) return line.split('=')[1].trim().replace(/^["']|["']$/g, '');
  } catch { /* ignore */ }
  return '';
};

const setState = (id, patch) => {
  const cols = Object.keys(patch);
  if (cols.length === 0) return;
  db.prepare(
    `UPDATE exam_analyses SET ${cols.map((c) => `${c} = @${c}`).join(', ')},
       updated_at = datetime('now') WHERE id = @id`,
  ).run({ ...patch, id });
};

const probeDuration = async (file) => {
  const { stdout } = await run('ffprobe', [
    '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file,
  ]);
  return Math.round(parseFloat(stdout.trim()) || 0);
};

const splitSegments = async (src, outDir) => {
  fs.mkdirSync(outDir, { recursive: true });
  await run(
    'ffmpeg',
    [
      '-y', '-i', src,
      '-c', 'copy', '-f', 'segment',
      '-segment_time', String(SEGMENT_SEC),
      '-reset_timestamps', '1',
      path.join(outDir, 'seg_%03d.mp4'),
    ],
    { maxBuffer: 1 << 26, timeout: 30 * 60 * 1000 },
  );
  return fs.readdirSync(outDir).filter((f) => f.endsWith('.mp4')).sort()
    .map((f) => path.join(outDir, f));
};

const readSseText = async (res) => {
  const raw = await res.text();
  let text = '';
  let used = 0;
  let lastErr = '';
  for (const line of raw.split('\n')) {
    const s = line.startsWith('data:') ? line.slice(5).trim() : line.trim();
    if (!s || s === '[DONE]') continue;
    let j;
    try { j = JSON.parse(s); } catch { continue; }
    if (j?.error?.message) lastErr = j.error.message;
    used = j?.usageMetadata?.promptTokenCount || used;
    text += (j?.candidates || [])
      .flatMap((c) => c?.content?.parts || [])
      .map((p) => p.text || '')
      .join('');
  }
  return { text, used, lastErr };
};

const askGemini = async (parts, { minTokens = 200, retries = 2, timeoutMs = 15 * 60 * 1000 } = {}) => {
  const key = readKey();
  if (!key) throw new Error('找不到 CLIPROXY_API_KEY');

  const body = JSON.stringify({
    contents: [{ role: 'user', parts }],
    generationConfig: { maxOutputTokens: 16000 },
  });

  let lastErr = '';
  for (let i = 0; i <= retries; i++) {
    try {
      // 非流式走 Antigravity 会被 5 分钟掐掉；SSE 才能把 10 分钟片子看完
      const r = await fetch(`${PROXY}/v1beta/models/${MODEL}:streamGenerateContent?alt=sse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
        body,
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        lastErr = j?.error?.message || `HTTP ${r.status}`;
        continue;
      }
      const { text, used, lastErr: sseErr } = await readSseText(r);
      if (sseErr) {
        lastErr = sseErr;
        continue;
      }
      if (used < minTokens) {
        lastErr = `内容没被接收（prompt_tokens=${used}）`;
        continue;
      }
      if (!text) {
        lastErr = '模型没有返回内容';
        continue;
      }
      return { text, tokens: used };
    } catch (e) {
      lastErr = e.message;
    }
  }
  throw new Error(lastErr || '模型调用失败');
};

const filePart = (file, mime) => ({
  inline_data: { mime_type: mime, data: fs.readFileSync(file).toString('base64') },
});

const pickJson = (text) => {
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) return null;
  try { return JSON.parse(m[0]); } catch { return null; }
};

const segmentPrompt = (index, total, offsetSec, kind) => {
  const scene = kind === 'taoti'
    ? '这是一段做套题 / 看解析的屏幕录像，'
    : '这是一段公考真题模考的屏幕录像（粉笔 App），';
  return `${scene}原速、未压缩，画面里是做题过程，可能看得到题干、选项、草稿纸或手写。
这是整场的第 ${index + 1} 段（共 ${total} 段），本段开头对应整场的第 ${offsetSec} 秒。

换算真实时间：真实秒数 = 你在本段里看到的秒数 + ${offsetSec}。

请逐题观察，把每一题提取成 JSON，只输出 JSON 不要解释：
{
  "questions": [
    {
      "number": 题号数字,
      "start_sec": 该题出现的真实秒数,
      "end_sec": 离开该题的真实秒数,
      "stem": "画面上能看清的原题题干+选项，尽量原文；看不清的部分用[看不清]",
      "draft": "草稿纸、手写、划线、演算里实际写了什么，按出现顺序列出；没有草稿填空字符串",
      "process": "这题怎么做的：先看了哪、算了什么、点了哪个选项、有没有回头改",
      "timeline": [
        {"at_sec": 真实秒, "seen": "这一刻画面上刚发生的事，一句"}
      ],
      "final_answer": "离开此题前最后一次看到被勾选/高亮的选项字母；选项圆点填实或变色就算选了，即使下一秒翻页。全程没看到勾选才填 null",
      "answer_changes": 改动答案的次数,
      "behaviors": ["从下列词里选：划线、反复滚动、长时间盯着不动、来回翻页、跳过、回头重做、快速作答、写草稿、看解析"]
    }
  ],
  "idle_periods": [
    { "start_sec": 真实秒, "end_sec": 真实秒, "what": "这段时间画面上在发生什么" }
  ],
  "observations": ["2~4 条关于做题步骤和草稿习惯的具体观察，用中文"]
}

注意：
- 只记录你真正看到的，不要诊断、不要评价好坏、不要猜他在想什么。
- timeline 按时间顺序列出本题里每个能看清的动作：进入本题、划线、开写、停住、滚动、翻页、跳走、回来、点选项、改选项、离开。每条一句，能写秒数就写。
- 原题和草稿尽量抄画面上的字。题干、草稿看不清就写[看不清]，不要编。
- "划线"指在题干上划但没有写出算式；"写草稿"指出现了数字、式子或步骤。
- 勾选判定只看选项圆点/高亮，不要根据草稿上的得数反推。
- 切题很快也要回头看离开前最后一两秒：圆点填实过就记下来。`;
};

const gradePdfPrompt = () => `这是一份带作答记录的行测练习/模考 PDF。常见字段是「你的答案」「正确答案」，或答题卡对错标记。
只根据 PDF 原文判分。禁止推理，禁止用常识或解析改答案。

只输出 JSON：
{
  "total": 题数,
  "correct": 做对数,
  "wrong": 做错数,
  "blank": 未选或空数,
  "questions": [
    {"number": 1, "user_answer": "C", "correct_answer": "B", "is_correct": false}
  ]
}

规则：
- 空、未作答、没有你的答案 → user_answer 为 ""，计入 blank，is_correct 为 false
- 多选按 PDF 原样，如 "BD"
- questions 必须覆盖 PDF 里每一题，题号与 PDF 一致
- 不要解释`;

const normalizeGrade = (grade) => {
  const questions = Array.isArray(grade?.questions) ? grade.questions : [];
  let correct = 0;
  let wrong = 0;
  let blank = 0;
  const items = questions.map((q) => {
    const user = String(q.user_answer ?? '').trim();
    const key = String(q.correct_answer ?? '').trim();
    const empty = !user;
    const ok = !empty && (key ? user === key : Boolean(q.is_correct));
    if (empty) blank += 1;
    else if (ok) correct += 1;
    else wrong += 1;
    return {
      number: Number(q.number),
      user_answer: user,
      correct_answer: key,
      is_correct: ok,
    };
  }).filter((q) => Number.isFinite(q.number));
  return {
    total: items.length,
    correct,
    wrong,
    blank,
    questions: items,
  };
};

export const formatGradeMd = (grade) => {
  if (!grade?.questions?.length) return '';
  const rows = grade.questions.map((q) =>
    `| ${q.number} | ${q.user_answer || '未选'} | ${q.correct_answer || '—'} | ${q.is_correct ? '对' : (q.user_answer ? '错' : '空')} |`
  ).join('\n');
  return `## 判分（只认本表，来自答案 PDF）
共 ${grade.total} 题：对 ${grade.correct} · 错 ${grade.wrong} · 空 ${grade.blank || 0}

| 题 | 你的答案 | 正确答案 | 对错 |
|---|---|---|---|
${rows}

`;
};

const gradeFromPdfText = (text) => {
  const keys = [...text.matchAll(/正确答案[:：]\s*([A-Z]+)/g)].map((m) => m[1]);
  const yours = [...text.matchAll(/你的答案[:：]\s*([A-Z]*)/g)].map((m) => m[1] || '');
  if (keys.length < 3 || yours.length !== keys.length) return null;
  return normalizeGrade({
    questions: keys.map((key, i) => ({
      number: i + 1,
      user_answer: yours[i],
      correct_answer: key,
      is_correct: Boolean(yours[i]) && yours[i] === key,
    })),
  });
};

const extractPdfText = async (pdfPath) => {
  const { stdout } = await run('python3', ['-c', `
import fitz, sys
doc = fitz.open(sys.argv[1])
print("\\n".join(p.get_text() for p in doc))
`, pdfPath], { maxBuffer: 1 << 24, timeout: 60 * 1000 });
  return stdout;
};

export const gradeFromPdf = async (pdfPath) => {
  try {
    const local = gradeFromPdfText(await extractPdfText(pdfPath));
    if (local?.questions?.length) return local;
  } catch { /* 抽不出字再交给模型 */ }
  const { text } = await askGemini(
    [{ text: gradePdfPrompt() }, filePart(pdfPath, 'application/pdf')],
    { minTokens: 80, timeoutMs: 6 * 60 * 1000 },
  );
  const grade = normalizeGrade(pickJson(text));
  if (!grade.questions.length) throw new Error('答案 PDF 没有读出逐题对错');
  return grade;
};

const summaryPrompt = (meta, segments, grade) => `你是行测教练。下面先有一份 PDF 判分表，再有录屏里抽出的做法和草稿。

## 场次
- 名称：${meta.title}
- 类型：${meta.kind === 'taoti' ? '套题' : '真题模考'}
- 日期：${meta.exam_date || '未填'}
- 全程时长：${Math.round(meta.duration_sec / 60)} 分钟

${formatGradeMd(grade) || '（没有 PDF 判分，对错不要编）'}

## 录屏提取（只用来写做法和草稿，不能改上面的对错）
${JSON.stringify(segments, null, 1).slice(0, 120000)}

答案 PDF 已作为文件附上。原题、材料表、图、选项从 PDF 抄全。

输出 Markdown。开篇不要写短处清单、知识点总表，也不要重新统计分数。
按题号输出，每题只用这个结构：

### 第 N 题
- 原题：从 PDF 抄题干和选项
- 作答结果：原样抄判分表的 你的答案 / 正确答案 / 对错；用时从录屏
- 做法：录屏里先看哪、算了什么、有没有改；看不清就写看不清
- 草稿：录屏里实际写了什么；没有就写「无草稿」

禁止用录屏勾选或「标准解法」推翻 PDF 对错。
不要写「共性」「短处与致命失分点」「下场三条规矩」这种总表。
不要写诊断、差距或更好解法；那些留给之后的对话复盘。`;

const BEHAVIOR_HEAD = '## 录屏行为记录（只记事实，不诊断）';

const fmtClock = (sec) => {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

const collectQuestions = (segments) => {
  const map = new Map();
  for (const seg of segments || []) {
    for (const q of seg.questions || []) {
      const n = Number(q.number);
      if (!Number.isFinite(n)) continue;
      const cur = {
        number: n,
        start_sec: q.start_sec,
        end_sec: q.end_sec,
        draft: String(q.draft || '').trim(),
        process: String(q.process || '').trim(),
        answer_changes: Number(q.answer_changes) || 0,
        behaviors: Array.isArray(q.behaviors) ? q.behaviors.filter(Boolean) : [],
        timeline: Array.isArray(q.timeline) ? q.timeline : [],
      };
      const prev = map.get(n);
      if (!prev) {
        map.set(n, cur);
        continue;
      }
      const starts = [prev.start_sec, cur.start_sec].filter((x) => x != null);
      const ends = [prev.end_sec, cur.end_sec].filter((x) => x != null);
      if (starts.length) prev.start_sec = Math.min(...starts);
      if (ends.length) prev.end_sec = Math.max(...ends);
      prev.answer_changes = Math.max(prev.answer_changes, cur.answer_changes);
      prev.behaviors = [...new Set([...prev.behaviors, ...cur.behaviors])];
      prev.timeline = [...prev.timeline, ...cur.timeline];
      if (cur.process && !prev.process.includes(cur.process)) {
        prev.process = [prev.process, cur.process].filter(Boolean).join('；');
      }
      if (cur.draft && !prev.draft.includes(cur.draft)) {
        prev.draft = [prev.draft, cur.draft].filter(Boolean).join('；');
      }
    }
  }
  return [...map.values()].sort((a, b) => a.number - b.number);
};

export const formatBehaviorLog = (segments) => {
  const qs = collectQuestions(segments);
  const idle = (segments || []).flatMap((s) => s.idle_periods || []);
  const lines = [BEHAVIOR_HEAD, ''];
  if (!qs.length) {
    lines.push('（本场没有抽出逐题行为）', '');
    return lines.join('\n');
  }
  for (const q of qs) {
    const timed = q.start_sec != null && q.end_sec != null;
    const span = timed ? `${fmtClock(q.start_sec)}–${fmtClock(q.end_sec)} · ${q.end_sec - q.start_sec}秒` : '时间不明';
    lines.push(`### 第 ${q.number} 题 · ${span}`);
    if (q.behaviors.length) lines.push(`- 标签：${q.behaviors.join('、')}`);
    lines.push(`- 改选项：${q.answer_changes} 次`);
    for (const ev of q.timeline) {
      const t = ev.at_sec != null ? fmtClock(ev.at_sec) : '?';
      const seen = ev.seen || ev.what || '';
      if (seen) lines.push(`- ${t} ${seen}`);
    }
    if (q.process) lines.push(`- 过程：${q.process}`);
    lines.push(`- 草稿：${q.draft || '无草稿'}`);
    lines.push('');
  }
  if (idle.length) {
    lines.push('### 题间/空档');
    for (const p of idle) {
      const what = p.what || '';
      lines.push(`- ${fmtClock(p.start_sec)}–${fmtClock(p.end_sec)}${what ? ` ${what}` : ''}`);
    }
    lines.push('');
  }
  return lines.join('\n');
};

export const injectBehaviorLog = (md, segments) => {
  const log = formatBehaviorLog(segments).trim();
  const body = String(md || '')
    .replace(/## 录屏行为记录（只记事实，不诊断）[\s\S]*?(?=\n## |$)/, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  const cut = body.indexOf('\n## ');
  if (cut >= 0) return `${body.slice(0, cut)}\n\n${log}\n${body.slice(cut)}`;
  const qcut = body.search(/\n### /);
  if (qcut >= 0) return `${body.slice(0, qcut)}\n\n${log}\n${body.slice(qcut)}`;
  return `${body}\n\n${log}\n`;
};

export const refreshBehaviorLogs = () => {
  const rows = db.prepare("SELECT id, segments, result FROM exam_analyses WHERE status = 'done'").all();
  let n = 0;
  for (const row of rows) {
    let segs;
    let result;
    try { segs = JSON.parse(row.segments || 'null'); } catch { continue; }
    try { result = JSON.parse(row.result || '{}'); } catch { continue; }
    if (!segs || !result.markdown) continue;
    result.markdown = injectBehaviorLog(result.markdown, segs);
    setState(row.id, { result: JSON.stringify(result) });
    n += 1;
  }
  return n;
};

const dropVideo = (named) => {
  if (!named) return;
  for (const dir of [VIDEO_DIR, RAW_DIR]) {
    const f = path.join(dir, named);
    try { if (fs.existsSync(f)) fs.unlinkSync(f); } catch { /* ignore */ }
  }
};

let running = false;

const processOne = async (id) => {
  const row = db.prepare('SELECT * FROM exam_analyses WHERE id = ?').get(id);
  if (!row) return;

  const named = row.video_file || '';
  const rawPath = named ? path.join(RAW_DIR, named) : null;
  const keptPath = named ? path.join(VIDEO_DIR, named) : null;
  const src = (rawPath && fs.existsSync(rawPath))
    ? rawPath
    : (keptPath && fs.existsSync(keptPath) ? keptPath : null);
  const segDir = path.join(VIDEO_DIR, `seg_${id}`);

  try {
    setState(id, { status: 'running', stage: '读取录屏信息', progress: 3, error: null });
    if (!src) throw new Error('找不到上传的录屏文件');

    const duration = await probeDuration(src);
    setState(id, {
      duration_sec: duration,
      video_bytes: fs.statSync(src).size,
      speed: 1,
      stage: '切分片段',
      progress: 20,
    });

    const segs = await splitSegments(src, segDir);
    if (segs.length === 0) throw new Error('切分后没有得到任何片段');

    const pdfPath = row.pdf_file ? path.join(PDF_DIR, row.pdf_file) : null;
    if (pdfPath && fs.existsSync(pdfPath)) {
      setState(id, { pdf_chars: fs.statSync(pdfPath).size });
    }

    const results = [];
    for (let i = 0; i < segs.length; i++) {
      setState(id, {
        stage: `分析第 ${i + 1}/${segs.length} 段录屏`,
        progress: 25 + Math.round((i / segs.length) * 55),
      });
      const t0 = Date.now();
      const { text } = await askGemini(
        [{ text: segmentPrompt(i, segs.length, i * SEGMENT_SEC, row.kind) }, filePart(segs[i], 'video/mp4')],
        { minTokens: 200, timeoutMs: 15 * 60 * 1000 },
      );
      results.push(pickJson(text) || { raw: text.slice(0, 4000), segment: i + 1 });
      console.log(`[exam] id=${id} seg ${i + 1}/${segs.length} ${Math.round((Date.now() - t0) / 1000)}s`);
    }

    setState(id, { segments: JSON.stringify(results), stage: '结合答案生成复盘', progress: 85 });

    let grade = null;
    if (pdfPath && fs.existsSync(pdfPath)) {
      setState(id, { stage: '判读答案 PDF', progress: 82 });
      grade = await gradeFromPdf(pdfPath);
    }

    setState(id, { stage: '结合过程生成复盘', progress: 88 });
    const prompt = summaryPrompt({ ...row, duration_sec: duration }, results, grade);
    const parts = [{ text: prompt }];
    if (pdfPath && fs.existsSync(pdfPath)) parts.push(filePart(pdfPath, 'application/pdf'));
    const { text: body } = await askGemini(parts, { minTokens: 50, timeoutMs: 10 * 60 * 1000 });
    const table = formatGradeMd(grade);
    const rawMd = table && !body.includes('判分（只认本表') ? table + body : body;
    const md = injectBehaviorLog(rawMd, results);

    const allQ = results.flatMap((r) => r.questions || []);
    const seen = new Set();
    const uniq = allQ.filter((q) => {
      if (q.number == null || seen.has(q.number)) return false;
      seen.add(q.number);
      return true;
    });
    const stats = {
      questions: grade?.total || uniq.length || allQ.length,
      correct: grade?.correct,
      wrong: grade?.wrong,
      blank: grade?.blank,
      idle_count: results.reduce((n, r) => n + (r.idle_periods?.length || 0), 0),
      changed: uniq.filter((q) => (q.answer_changes || 0) > 0).length,
      slowest: [...uniq]
        .filter((q) => q.end_sec != null && q.start_sec != null)
        .sort((a, b) => (b.end_sec - b.start_sec) - (a.end_sec - a.start_sec))
        .slice(0, 5)
        .map((q) => ({ number: q.number, sec: q.end_sec - q.start_sec })),
    };

    setState(id, {
      status: 'done',
      stage: '已完成',
      progress: 100,
      result: JSON.stringify({ markdown: md, stats, grade }),
    });
    dropVideo(named);
    setState(id, { video_deleted: 1 });
  } catch (e) {
    setState(id, { status: 'failed', stage: '处理失败', error: String(e.message || e) });
  } finally {
    try {
      if (fs.existsSync(segDir)) fs.rmSync(segDir, { recursive: true, force: true });
    } catch { /* ignore */ }
  }
};

const pump = async () => {
  if (running) return;
  running = true;
  try {
    for (;;) {
      const next = db
        .prepare("SELECT id FROM exam_analyses WHERE status IN ('queued','running') ORDER BY id ASC LIMIT 1")
        .get();
      if (!next) break;
      await processOne(next.id);
    }
  } finally {
    running = false;
  }
};

export const enqueue = () => {
  setImmediate(() => { void pump(); });
};

export const regradeExisting = async (id) => {
  const row = db.prepare('SELECT * FROM exam_analyses WHERE id = ?').get(id);
  if (!row) throw new Error('找不到这场复盘');
  const pdfPath = row.pdf_file ? path.join(PDF_DIR, row.pdf_file) : null;
  if (!pdfPath || !fs.existsSync(pdfPath)) throw new Error('这场没有答案 PDF');
  const grade = await gradeFromPdf(pdfPath);
  let result = {};
  try { result = JSON.parse(row.result || '{}'); } catch { result = {}; }
  const body = String(result.markdown || '').replace(/^## 判分（只认本表[\s\S]*?(?=\n## |$)/, '').replace(/^\n+/, '');
  result.grade = grade;
  let segs = null;
  try { segs = JSON.parse(row.segments || 'null'); } catch { /* ignore */ }
  result.markdown = injectBehaviorLog(formatGradeMd(grade) + body, segs);
  result.stats = {
    ...(result.stats || {}),
    questions: grade.total,
    correct: grade.correct,
    wrong: grade.wrong,
    blank: grade.blank,
  };
  setState(id, { result: JSON.stringify(result) });
  return grade;
};

export const resumePending = () => {
  const n = db
    .prepare("SELECT COUNT(*) c FROM exam_analyses WHERE status IN ('queued','running')")
    .get().c;
  if (n > 0) {
    console.log(`[exam] 发现 ${n} 个未完成的复盘任务，继续处理`);
    enqueue();
  }
};

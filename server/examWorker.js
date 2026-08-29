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

const MODEL = process.env.EXAM_ANALYSIS_MODEL || 'gemini-3.7-flash-high';
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
- 只记录你真正看到的。题干、草稿看不清就写[看不清]，不要编。
- 原题和草稿是重点，尽量抄画面上的字，不要只写行为标签。
- "划线"指在题干上划但没有写出算式；"写草稿"指出现了数字、式子或步骤。
- 勾选判定只看选项圆点/高亮，不要根据草稿上的得数反推。
- 切题很快也要回头看离开前最后一两秒：圆点填实过就记下来。`;
};

const summaryHeader = (meta, segments) => `## 场次信息
- 名称：${meta.title}
- 类型：${meta.kind === 'taoti' ? '套题解析' : '真题复盘'}
- 日期：${meta.exam_date || '未填'}
- 全程时长：${Math.round(meta.duration_sec / 60)} 分钟

## 从录屏逐题提取的内容（做法、草稿、勾选）
${JSON.stringify(segments, null, 1).slice(0, 120000)}

解析 PDF 已作为文件附上（没有则为空）。原题、材料表、图、选项、标准答案和解析以 PDF 为准；写入报告时把原题题干和选项从 PDF 抄全，不要只用录屏摘抄。
`;

const summaryPromptZhenti = (meta, segments) => `你是一位带过很多考公学生的行测教练。下面是一场**真题模考**的录屏提取结果。请按题目复盘，不要写成空泛的时间统计。

${summaryHeader(meta, segments)}

请输出 Markdown，严格按下面结构。每一题都要写出：原题（从 PDF 抄原文）、这题怎么做的、草稿写了什么。不要空话。

## 一、逐题复盘
按题号从小到大，每题用这个小结构：

### 第 N 题
- 原题：从 PDF 抄题干和选项；PDF 没有再注明录屏摘抄
- 做法：录屏里实际怎么做的（先看哪、算了什么、选了什么、有没有改）
- 草稿：草稿纸/手写/划线里写了什么；没写就说「无草稿」
- 用时与对错：用了多久、最终选项、结合 PDF 判断对不对
- 这一题的问题：卡在哪、草稿缺哪一步、值不值得花这么久

题号和 PDF 对不上时，以 PDF 为准，并在该题注明。

## 二、共性
从各题做法和草稿里归纳 3～5 条反复出现的问题。

## 三、下场三条硬规矩
只给三条，必须是当场能执行的动作。不要写「提高效率」。`;

const summaryPromptTaoti = (meta, segments) => `你是一位带过很多考公学生的行测教练。下面是一场**套题练习 / 看解析**的录屏提取结果。请按题目做解析式复盘。

${summaryHeader(meta, segments)}

请输出 Markdown，严格按下面结构。重点是「每一题的原题 + 做法 + 草稿」，不要先写整场时间表。

## 一、逐题解析
按题号从小到大，每题用这个小结构：

### 第 N 题
- 原题：从 PDF 抄题干和选项；有材料表/图把关键数字也抄上
- 你怎么做的：录屏里的步骤，先看哪、怎么想、选了什么
- 草稿怎么写的：画面上的演算、标注、划线，按顺序写；没有就写「没写草稿」
- 标准解法：结合 PDF 解析，这题正确步骤是什么
- 差距：你的做法/草稿和标准解法差在哪一步

题号和 PDF 对不上时，以 PDF 为准，并在该题注明。

## 二、草稿习惯
专门评草稿：哪些题草稿能还原思路，哪些题该写没写，下次这类题草稿最少该写下哪几笔。

## 三、下次做套题的三条规矩
只给三条，针对「怎么写草稿、做到哪一步再看解析」，必须能当场执行。`;

const summaryPrompt = (meta, segments) => (
  meta.kind === 'taoti' ? summaryPromptTaoti(meta, segments) : summaryPromptZhenti(meta, segments)
);

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

    const prompt = summaryPrompt({ ...row, duration_sec: duration }, results);
    const parts = [{ text: prompt }];
    if (pdfPath && fs.existsSync(pdfPath)) parts.push(filePart(pdfPath, 'application/pdf'));
    const { text: md } = await askGemini(parts, { minTokens: 50, timeoutMs: 10 * 60 * 1000 });

    const allQ = results.flatMap((r) => r.questions || []);
    const seen = new Set();
    const uniq = allQ.filter((q) => {
      if (q.number == null || seen.has(q.number)) return false;
      seen.add(q.number);
      return true;
    });
    const stats = {
      questions: uniq.length || allQ.length,
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
      result: JSON.stringify({ markdown: md, stats }),
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

export const resumePending = () => {
  const n = db
    .prepare("SELECT COUNT(*) c FROM exam_analyses WHERE status IN ('queued','running')")
    .get().c;
  if (n > 0) {
    console.log(`[exam] 发现 ${n} 个未完成的复盘任务，继续处理`);
    enqueue();
  }
};

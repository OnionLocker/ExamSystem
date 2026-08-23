// ============================================================
// 真题复盘 worker：录屏 + 答案 PDF → 行为画像
// ------------------------------------------------------------
// 90 分钟 iPad 录屏动辄好几个 GB，而这台机器只剩几个 G，所以流程是
// 「转码成小样本 → 立刻删原件 → 拿小样本去分析」，原件一秒都不多留。
//
// 为什么要加速：模型按视频时长以 1 帧/秒采样计费，跟分辨率无关。
// 实测把片子放快 N 倍，token 就降到 1/N，而做题过程本来就是静态画面，
// 划线、翻页、卡壳这些都持续好几秒，3 倍速完全捕捉得到。
// 代价是短于 N 秒的动作会被采样跳过，所以精确答案不从视频抠，走 PDF。
// ============================================================

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

// 转码参数：3 倍速 + 1 帧/秒 + 540p。再快就会丢掉「点一下选项就翻页」这类动作
const SPEED = 1;
// 每段压缩后的秒数；10 分钟约 3.7 万 token，离单次上限很远，失败也只用重跑一段
const SEGMENT_SEC = 600;
const MODEL = process.env.EXAM_ANALYSIS_MODEL || 'gemini-3.7-flash-high';
const BASE_URL = (process.env.CLIPROXY_BASE_URL || 'http://127.0.0.1:8889/v1').replace(/\/$/, '');
// PDF 全文可能上万字，截一段够模型对答案就行，省得把上下文撑爆
const PDF_LIMIT = 60_000;

const readKey = () => {
  if (process.env.CLIPROXY_API_KEY) return process.env.CLIPROXY_API_KEY.trim();
  try {
    const t = fs.readFileSync(path.join(os.homedir(), '.hermes', '.env'), 'utf8');
    const line = t.split('\n').find((l) => l.startsWith('CLIPROXY_API_KEY='));
    if (line) return line.split('=')[1].trim().replace(/^["']|["']$/g, '');
  } catch {
    /* ignore */
  }
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

// ---------------- ffmpeg ----------------

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

const extractPdf = async (file) => {
  try {
    const { stdout } = await run('pdftotext', ['-layout', file, '-'], { maxBuffer: 1 << 28 });
    return stdout;
  } catch {
    return '';
  }
};

// ---------------- 模型调用 ----------------

// 这条链路偶尔会把视频悄悄吃掉：HTTP 200、不报错，但模型压根没收到画面，
// 然后一本正经地编。判据是 prompt_tokens —— 真收到视频的话，
// token 数约等于「视频秒数 × 62」，只有几十就是没收到。
const askWithVideo = async (videoPath, prompt, { minTokens = 200, retries = 2 } = {}) => {
  const key = readKey();
  if (!key) throw new Error('找不到 CLIPROXY_API_KEY');
  const b64 = fs.readFileSync(videoPath).toString('base64');

  let lastErr = '';
  for (let i = 0; i <= retries; i++) {
    try {
      const r = await fetch(`${BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
        body: JSON.stringify({
          model: MODEL,
          max_tokens: 8000,
          messages: [{
            role: 'user',
            content: [
              { type: 'text', text: prompt },
              { type: 'image_url', image_url: { url: `data:video/mp4;base64,${b64}` } },
            ],
          }],
        }),
        signal: AbortSignal.timeout(10 * 60 * 1000),
      });
      const j = await r.json();
      const used = j?.usage?.prompt_tokens ?? 0;
      const text = j?.choices?.[0]?.message?.content || '';
      if (used < minTokens) {
        lastErr = `视频没被接收（prompt_tokens=${used}）`;
        continue;
      }
      if (!text) {
        lastErr = j?.error?.message || '模型没有返回内容';
        continue;
      }
      return { text, tokens: used };
    } catch (e) {
      lastErr = e.message;
    }
  }
  throw new Error(lastErr || '模型调用失败');
};

const askText = async (prompt) => {
  const key = readKey();
  const r = await fetch(`${BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify({
      model: MODEL, max_tokens: 8000,
      messages: [{ role: 'user', content: prompt }],
    }),
    signal: AbortSignal.timeout(10 * 60 * 1000),
  });
  const j = await r.json();
  const text = j?.choices?.[0]?.message?.content || '';
  if (!text) throw new Error(j?.error?.message || '汇总失败');
  return text;
};

const pickJson = (text) => {
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) return null;
  try {
    return JSON.parse(m[0]);
  } catch {
    return null;
  }
};

// ---------------- prompts ----------------

const segmentPrompt = (index, total, offsetSec, speed, kind) => {
  const scene = kind === 'taoti'
    ? '这是一段做套题 / 看解析的屏幕录像，'
    : '这是一段公考真题模考的屏幕录像（粉笔 App），';
  return `${scene}${speed > 1 ? `已经按 ${speed} 倍速压缩过` : '原速、未压缩'}，画面里是做题过程，可能看得到题干、选项、草稿纸或手写。
这是整场的第 ${index + 1} 段（共 ${total} 段），本段开头对应整场的第 ${offsetSec} 秒。

换算真实时间：真实秒数 = 你在本段里看到的秒数 × ${speed} + ${offsetSec}。

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
- 勾选判定只看选项圆点/高亮，不要根据草稿上的得数反推。草稿算出 33k 但圆点在 D，final_answer 仍是 D。
- 切题很快也要回头看离开前最后一两秒：圆点填实过就记下来，禁止只因翻页快就写「未勾选」。`;
};

const summaryHeader = (meta, segments, pdfText) => `## 场次信息
- 名称：${meta.title}
- 类型：${meta.kind === 'taoti' ? '套题解析' : '真题复盘'}
- 日期：${meta.exam_date || '未填'}
- 全程时长：${Math.round(meta.duration_sec / 60)} 分钟

## 从录屏逐题提取的内容（含原题、做法、草稿）
${JSON.stringify(segments, null, 1).slice(0, 120000)}

## 这套卷子的答案与解析（PDF 提取，可能有排版噪声；没有 PDF 则为空）
${pdfText.slice(0, PDF_LIMIT)}
`;

const summaryPromptZhenti = (meta, segments, pdfText) => `你是一位带过很多考公学生的行测教练。下面是一场**真题模考**的录屏提取结果。请按题目复盘，不要写成空泛的时间统计。

${summaryHeader(meta, segments, pdfText)}

请输出 Markdown，严格按下面结构。每一题都要写出：原题（能提取到的原文）、这题怎么做的、草稿写了什么。不要空话。

## 一、逐题复盘
按题号从小到大，每题用这个小结构：

### 第 N 题
- 原题：抄提取到的题干和选项；看不清就注明
- 做法：录屏里实际怎么做的（先看哪、算了什么、选了什么、有没有改）
- 草稿：草稿纸/手写/划线里写了什么；没写就说「无草稿」
- 用时与对错：用了多久、最终选项、结合 PDF 判断对不对
- 这一题的问题：卡在哪、草稿缺哪一步、值不值得花这么久

题号和 PDF 对不上时，以 PDF 为准，并在该题注明。

## 二、共性
从各题做法和草稿里归纳 3～5 条反复出现的问题（例如某类题从不写式子、草稿只圈选项不演算）。

## 三、下场三条硬规矩
只给三条，必须是当场能执行的动作，例如「数量题先在草稿写下已知量再看选项」。不要写「提高效率」。`;

const summaryPromptTaoti = (meta, segments, pdfText) => `你是一位带过很多考公学生的行测教练。下面是一场**套题练习 / 看解析**的录屏提取结果。请按题目做解析式复盘：还原原题，讲清这一题是怎么做的、草稿怎么写的，再对照标准解法。

${summaryHeader(meta, segments, pdfText)}

请输出 Markdown，严格按下面结构。重点是「每一题的原题 + 做法 + 草稿」，不要先写整场时间表。

## 一、逐题解析
按题号从小到大，每题用这个小结构：

### 第 N 题
- 原题：抄提取到的题干和选项
- 你怎么做的：录屏里的步骤，先看哪、怎么想、选了什么
- 草稿怎么写的：画面上的演算、标注、划线，按顺序写；没有就写「没写草稿」
- 标准解法：结合 PDF 解析，这题正确步骤是什么
- 差距：你的做法/草稿和标准解法差在哪一步（漏条件、式子写错、没写草稿靠蒙、看了解析才懂）

题号和 PDF 对不上时，以 PDF 为准，并在该题注明。

## 二、草稿习惯
专门评草稿：哪些题草稿能还原思路，哪些题该写没写，下次这类题草稿最少该写下哪几笔。

## 三、下次做套题的三条规矩
只给三条，针对「怎么写草稿、做到哪一步再看解析」，必须能当场执行。`;

const summaryPrompt = (meta, segments, pdfText) => (
  meta.kind === 'taoti'
    ? summaryPromptTaoti(meta, segments, pdfText)
    : summaryPromptZhenti(meta, segments, pdfText)
);

// ---------------- 主流程 ----------------


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
    setState(id, { status: 'running', stage: '\u8bfb\u53d6\u5f55\u5c4f\u4fe1\u606f', progress: 3, error: null });

    if (!src) throw new Error('\u627e\u4e0d\u5230\u4e0a\u4f20\u7684\u5f55\u5c4f\u6587\u4ef6');

    const duration = await probeDuration(src);
    setState(id, {
      duration_sec: duration,
      video_bytes: fs.statSync(src).size,
      speed: SPEED,
      stage: '\u5207\u5206\u7247\u6bb5',
      progress: 30,
    });

    const segs = await splitSegments(src, segDir);
    if (segs.length === 0) throw new Error('切分后没有得到任何片段');

    let pdfText = '';
    if (row.pdf_file) {
      setState(id, { stage: '解析答案 PDF', progress: 34 });
      pdfText = await extractPdf(path.join(PDF_DIR, row.pdf_file));
      setState(id, { pdf_chars: pdfText.length });
    }

    const results = [];
    for (let i = 0; i < segs.length; i++) {
      setState(id, {
        stage: `分析第 ${i + 1}/${segs.length} 段录屏`,
        progress: 35 + Math.round((i / segs.length) * 45),
      });
      const offset = i * SEGMENT_SEC * SPEED;
      const { text } = await askWithVideo(segs[i], segmentPrompt(i, segs.length, offset, SPEED, row.kind));
      const parsed = pickJson(text);
      results.push(parsed || { raw: text.slice(0, 4000), segment: i + 1 });
    }

    setState(id, { segments: JSON.stringify(results), stage: '结合答案生成复盘', progress: 85 });

    const md = await askText(
      summaryPrompt({ ...row, duration_sec: duration }, results, pdfText),
    );

    // 汇总一份轻量指标，列表页和热力图直接用，不用每次解析大 JSON
    const allQ = results.flatMap((r) => r.questions || []);
    const stats = {
      questions: allQ.length,
      idle_count: results.reduce((n, r) => n + (r.idle_periods?.length || 0), 0),
      changed: allQ.filter((q) => (q.answer_changes || 0) > 0).length,
      slowest: [...allQ]
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
    // 分段文件是中间产物，成败都清掉
    try {
      if (fs.existsSync(segDir)) fs.rmSync(segDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
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
  // 不等它跑完：上传接口要立刻返回，前端靠轮询看进度
  setImmediate(() => { void pump(); });
};

// 进程重启时把没跑完的接着跑（running 的那条会从头再来，幂等）
export const resumePending = () => {
  const n = db
    .prepare("SELECT COUNT(*) c FROM exam_analyses WHERE status IN ('queued','running')")
    .get().c;
  if (n > 0) {
    console.log(`[exam] 发现 ${n} 个未完成的复盘任务，继续处理`);
    enqueue();
  }
};

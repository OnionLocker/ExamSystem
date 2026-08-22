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
const SPEED = 3;
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

const safeUnlink = (p) => {
  try {
    if (p && fs.existsSync(p)) fs.unlinkSync(p);
  } catch {
    /* ignore */
  }
};

// ---------------- ffmpeg ----------------

const probeDuration = async (file) => {
  const { stdout } = await run('ffprobe', [
    '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file,
  ]);
  return Math.round(parseFloat(stdout.trim()) || 0);
};

const transcode = async (src, dst) => {
  await run(
    'ffmpeg',
    [
      '-y', '-i', src,
      // setpts 先加速，再压到 1 帧/秒；-an 丢掉音轨（做题没人说话，白花 token）
      '-vf', `setpts=PTS/${SPEED},scale=960:-2,fps=1`,
      '-an',
      '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
      dst,
    ],
    { maxBuffer: 1 << 26, timeout: 60 * 60 * 1000 },
  );
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

const segmentPrompt = (index, total, offsetSec, speed) => `这是一段公考模考的屏幕录像（粉笔 App），已经按 ${speed} 倍速压缩过，画面里只有做题过程。
这是整场考试的第 ${index + 1} 段（共 ${total} 段），本段开头对应整场的第 ${offsetSec} 秒。

换算真实时间：真实秒数 = 你在本段里看到的秒数 × ${speed} + ${offsetSec}。

请逐题观察，把做题过程提取成 JSON，只输出 JSON 不要解释：
{
  "questions": [
    {
      "number": 题号数字,
      "start_sec": 该题出现的真实秒数,
      "end_sec": 离开该题的真实秒数,
      "final_answer": "停留在哪个选项，没选填 null",
      "answer_changes": 改动答案的次数,
      "behaviors": ["从下列词里选：划线、反复滚动、长时间盯着不动、来回翻页、跳过、回头重做、快速作答"]
    }
  ],
  "idle_periods": [
    { "start_sec": 真实秒, "end_sec": 真实秒, "what": "这段时间画面上在发生什么" }
  ],
  "observations": ["2~4 条关于做题节奏和习惯的具体观察，用中文"]
}

注意：
- 只记录你真正看到的，看不清就不要写进去。
- behaviors 里"划线"指用笔或手指在题干上划动但没有实质推进；"长时间盯着不动"指画面超过 15 秒真实时间没有任何变化。`;

const summaryPrompt = (meta, segments, pdfText) => `你是一位带过很多考公学生的行测教练。下面是某位考生一场模考的**录屏行为数据**和这套卷子的**答案与解析**。请把两者结合，给出一份犀利、具体、可执行的复盘。

## 考试信息
- 名称：${meta.title}
- 日期：${meta.exam_date || '未填'}
- 全程时长：${Math.round(meta.duration_sec / 60)} 分钟

## 从录屏提取的行为数据
${JSON.stringify(segments, null, 1).slice(0, 120000)}

## 这套卷子的答案与解析（PDF 提取，可能有排版噪声）
${pdfText.slice(0, PDF_LIMIT)}

---

请输出 Markdown，严格按下面的结构，**不要写空话套话**，每一条都要指到具体题号或具体时间点：

## 一、这场考试的时间都去哪了
按耗时从多到少列出吃掉时间最多的 5~8 道题，标出每题用了多久、答对没有。指出哪些是"值得花"的，哪些是纯亏。

## 二、无效动作
把录屏里那些没有推进解题的动作挑出来：划了半天线但没动笔算、反复上下翻材料、答案改来改去最后改回原答案、盯着题干发呆。要写清楚发生在第几题、耗时多少。

## 三、快慢与对错的交叉
分成四类各举实例：慢而对（值得，但能不能提速）、慢而错（重灾区）、快而对（优势项）、快而错（轻敌或粗心）。

## 四、按模块的诊断
言语 / 判断 / 数量 / 资料 / 常识，各自的用时占比、正确率、暴露的具体问题。

## 五、下次上考场的三条硬规矩
只给三条，每条都必须是当场能执行的动作（例如"资料分析第 X 类题超过 90 秒立刻标记跳过"），不要写"提高效率"这种废话。

如果行为数据里的题号和 PDF 对不上，以 PDF 的题号为准，并在开头一句话说明对齐情况。`;

// ---------------- 主流程 ----------------

let running = false;

const processOne = async (id) => {
  const row = db.prepare('SELECT * FROM exam_analyses WHERE id = ?').get(id);
  if (!row) return;

  const rawPath = row.video_file ? path.join(RAW_DIR, row.video_file) : null;
  const smallName = `s${id}_${Date.now()}.mp4`;
  const smallPath = path.join(VIDEO_DIR, smallName);
  const segDir = path.join(VIDEO_DIR, `seg_${id}`);

  try {
    setState(id, { status: 'running', stage: '读取录屏信息', progress: 3, error: null });

    if (!rawPath || !fs.existsSync(rawPath)) throw new Error('找不到上传的录屏文件');
    const duration = await probeDuration(rawPath);
    setState(id, { duration_sec: duration, stage: '压缩转码中（这一步最久）', progress: 8 });

    await transcode(rawPath, smallPath);
    const smallBytes = fs.statSync(smallPath).size;

    // 原件立刻删：几个 GB 留着没意义，后面全用小样本
    safeUnlink(rawPath);
    setState(id, {
      video_file: smallName,
      video_bytes: smallBytes,
      raw_bytes: row.raw_bytes,
      speed: SPEED,
      stage: '切分片段',
      progress: 30,
    });

    const segs = await splitSegments(smallPath, segDir);
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
      const { text } = await askWithVideo(segs[i], segmentPrompt(i, segs.length, offset, SPEED));
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
  } catch (e) {
    setState(id, { status: 'failed', stage: '处理失败', error: String(e.message || e) });
  } finally {
    // 分段文件是中间产物，成败都清掉
    try {
      if (fs.existsSync(segDir)) fs.rmSync(segDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
    safeUnlink(rawPath);
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

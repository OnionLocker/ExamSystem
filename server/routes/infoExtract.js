import express from 'express';
import { readFileSync } from 'fs';
import { join } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const router = express.Router();

const CLIPROXY_BASE = process.env.CLIPROXY_BASE_URL || 'http://127.0.0.1:8889/v1';
const MODEL = 'gemini-3.8-flash-high';

function getApiKey() {
  if (process.env.CLIPROXY_API_KEY) return process.env.CLIPROXY_API_KEY;
  const envPath = join(process.env.HOME, '.hermes', '.env');
  try {
    const lines = readFileSync(envPath, 'utf-8').split('\n');
    for (const line of lines) {
      if (line.startsWith('CLIPROXY_API_KEY=')) {
        return line.split('=')[1].trim();
      }
    }
  } catch {}
  throw new Error('CLIPROXY_API_KEY not found');
}

async function callGemini(messages) {
  const response = await fetch(`${CLIPROXY_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getApiKey()}`,
    },
    body: JSON.stringify({
      model: MODEL,
      messages,
      temperature: 0.7,
      max_tokens: 4000,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Gemini API error: ${response.status} ${text}`);
  }

  const data = await response.json();
  return data.choices[0].message.content;
}

router.post('/generate', async (req, res) => {
  try {
    const { type } = req.body; // 'ziliao' or 'yanyu'

    const systemPrompt = type === 'ziliao'
      ? `你是资料分析材料生成器。生成一段300-500字的统计材料（财政/民生/工业/外贸），包含时间、主体、数值。

要求：
1. 分3-4个段落，每段开头6字要有区分度（例如"2023年财政"、"民生支出方面"）
2. 包含至少8个具体数值，带单位和时间
3. 包含同比/环比增长率
4. 材料结构清晰，适合段首标签定位

输出JSON：
{
  "material": "材料正文",
  "questions": [
    {
      "type": "段首标签题",
      "question": "第2段主要讲什么主题？",
      "answer": "民生支出",
      "location": "第2段前6字"
    },
    {
      "type": "关键数字题",
      "question": "2023年财政收入是多少亿元？",
      "answer": "1234.5",
      "location": "第1段第2句"
    },
    {
      "type": "信号词题",
      "question": "材料中哪句话出现了转折？",
      "answer": "但是第三季度增速放缓",
      "location": "第3段第3句"
    }
  ]
}`
      : `你是言语理解长文生成器。生成一段300-500字的议论文/说明文，包含转折、对策、因果等信号词。

要求：
1. 前半部分铺垫背景或旧观点（用"过去/传统上/一度认为"）
2. 中间出现转折（用"但是/实际上/然而"）
3. 后半部分提出对策或结论（用"必须/亟待/因此"）
4. 故意设计前后矛盾，用于测试是否被转折前内容干扰

输出JSON：
{
  "material": "材料正文",
  "questions": [
    {
      "type": "转折对冲题",
      "question": "作者的真实观点是什么？",
      "answer": "需要加强监管",
      "wrongAnswer": "市场自由发展即可",
      "location": "第2段转折后"
    },
    {
      "type": "信号词题",
      "question": "哪句话是文章的对策句？",
      "answer": "必须建立长效机制",
      "location": "第3段第1句"
    }
  ]
}`;

    const userPrompt = type === 'ziliao'
      ? '生成一段广东省统计公报风格的资料分析材料，主题自选（财政/民生/工业/外贸之一），3题覆盖段首标签、关键数字、信号词。'
      : '生成一段言语理解长文，包含转折对比结构，3题覆盖转折对冲、信号词定位。';

    const content = await callGemini([
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt },
    ]);

    // 提取JSON（可能被```包裹）
    let json;
    const match = content.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
    if (match) {
      json = JSON.parse(match[1]);
    } else {
      json = JSON.parse(content);
    }

    res.json(json);
  } catch (error) {
    console.error('信息提取训练生成失败:', error);
    res.status(500).json({ error: error.message });
  }
});

export default router;

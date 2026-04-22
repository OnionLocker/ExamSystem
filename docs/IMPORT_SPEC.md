# 题库导入规范（v1）

本规范用于**第三方爬取/处理程序**（如 Workbuddy）与本系统之间的数据交换格式。只要产出满足本规范的**批次目录**（batch），即可通过 `npm run import:batch` 一键导入。

---

## 0. 总览

一个"批次（batch）"对应一次导入任务，通常是**一套真题**或**一个专项**。

```
batch-gd-2024-xj/                # 目录名建议用 batch_id
├── manifest.json                # 批次元信息（必须）
├── questions.json               # 题目数组（必须）
├── materials.json               # 资料分析材料组（可选，无则可省略）
└── images/                      # 所有图片，扁平存放
    ├── q-0001-stem.png
    ├── q-0042-opt-A.png
    └── m-0001-chart.png
```

上传到服务器后执行：

```bash
npm run validate:batch -- path/to/batch-dir   # 仅校验，不写 DB
npm run import:batch   -- path/to/batch-dir   # 校验 + 写入 DB + 拷图片
```

导入是**幂等**的：同一个 `external_id` 再次导入会 **update**，不会产生重复行。

> **⚠ 特别提醒（给 Workbuddy）：每道题必须带齐"三件套"**
>
> 1. **题干**（`stem`）— 从原文抄齐，不删节
> 2. **正确答案**（`answer`）— **必须核对官方答案**，不能由模型自行推断。若官方来源缺失，至少对比两份独立来源（华图/粉笔/中公等）交叉验证后再填
> 3. **答案解析**（`explanation`）— **可以由 Workbuddy 自行撰写或改写**，不必照搬官方
>
> **解析写作口径（重要）**：
> - **不要**照抄官方"八股式"解析（"根据材料可知…故选 A"）
> - **要**偏实战技巧：速算口诀、秒杀技巧、代入排除、选项特征、易错陷阱、题干关键词定位
> - **要**从"做题人视角"写，而不是"出题人视角"：讲**怎么快速找到答案**，而不是讲知识点本身
> - 风格参考：像一个刷了几千题的老手在给自己做笔记
> - 长度控制在 3 句到 200 字以内，**宁可短也不要啰嗦**
> - 数量关系/资料分析题允许把速算步骤写出来（用 LaTeX），但关键是"为什么这么算"
> - 常识题可以补充关联考点或易混知识点
>
> 总原则：**答案对错 = 零容忍**（必须官方核对）；**解析风格 = 完全放开**（鼓励 Workbuddy 做成自己的私人笔记）。

---

## 1. manifest.json

批次元信息。所有 question/material 若未单独指定 `year / region / source`，将**继承** manifest 值。

```json
{
  "batch_id": "gd-2024-xj",
  "source": "2024 广东省考 · 县级卷",
  "region": "广东-县级",
  "year": 2024,
  "license": "仅个人学习使用",
  "created_at": "2026-04-22",
  "notes": "从官方真题 PDF OCR，含 4 个资料分析材料组"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `batch_id` | string | ✅ | 全局唯一的批次 ID，英文小写+`-`，≤50 字符。图片最终存储在 `/q-images/<batch_id>/` 下 |
| `source` | string | ✅ | 人类可读的来源描述，会写入每道题的 `source` 字段 |
| `region` | string | ✅ | 地区标签，枚举：`广东-省直`/`广东-县级`/`广东-乡镇`/`广东-选调`/`广东-模拟` |
| `year` | integer | ✅ | 年份，如 `2024` |
| `license` | string | ⬜ | 版权说明（纯描述） |
| `created_at` | string | ⬜ | ISO 日期 |
| `notes` | string | ⬜ | 自由备注 |

---

## 2. questions.json

**数组**结构，每一项是一道题。

### 2.1 字段定义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `external_id` | string | ✅ | **批次内唯一**；建议格式 `<batch_id>-Q<序号>`，如 `gd-2024-xj-Q001` |
| `category` | string | ✅ | **顶层类**枚举，见下表 |
| `sub_category` | string \| null | ⬜ | **子类**枚举，必须属于该顶层类允许的子类 |
| `question_type` | string | ⬜ | `single`（默认）/ `multi` / `judge` |
| `stem` | string | ✅ | 题干纯文本（可含 LaTeX `$...$`，不要把公式截图） |
| `stem_images` | string[] | ⬜ | 题干配图，路径相对于批次根，如 `images/q-0001-stem.png` |
| `options` | object[] | △ | 单选/多选必填；判断题可省略。见 2.3 |
| `answer` | string \| string[] | ✅ | **正确答案**，**必须核对官方**。见 2.4 |
| `explanation` | string | ⬜ 强烈建议 | **答案解析**，可由 Workbuddy 自行撰写，偏实战技巧口径，见顶部"三件套"提醒 |
| `explanation_images` | string[] | ⬜ | 解析配图（如解析里需要画图说明） |
| `difficulty` | integer | ⬜ | 1~5，默认 2 |
| `tags` | string[] | ⬜ | 自由标签，如 `["工程问题", "基础"]` |
| `source` | string | ⬜ | 覆盖 manifest.source |
| `year` | integer | ⬜ | 覆盖 manifest.year |
| `region` | string | ⬜ | 覆盖 manifest.region |
| `material_id` | string \| null | ⬜ | 资料分析组题引用 `materials[].external_id` |

### 2.2 category / sub_category 枚举（**严格**）

| category | 允许的 sub_category |
|---|---|
| `政治理论` | （无子类，填 `null` 或省略） |
| `常识判断` | （无子类） |
| `言语理解与表达` | （无子类） |
| `数量关系` | `数字推理` / `数学运算` |
| `判断推理` | `图形推理` / `逻辑判断` / `科学推理` |
| `资料分析` | （无子类） |

不在枚举内的值一律**校验失败**。若原始来源的分类更细（如"行程问题"），请归到最近的子类 + 放入 `tags`。

### 2.3 options 结构

```json
"options": [
  { "key": "A", "text": "12" },
  { "key": "B", "text": "14", "images": [] },
  { "key": "C", "images": ["images/q-0095-opt-C.png"] },
  { "key": "D", "text": "16" }
]
```

- `key` 必须是 `A` / `B` / `C` / `D` / `E` 之一，同题内不重复
- `text` 与 `images` **至少有一个**非空
- 图形推理题常为"纯图选项"，直接只给 `images`

### 2.4 answer 格式

| question_type | answer 允许值 |
|---|---|
| `single` | `"A"` \| `"B"` \| `"C"` \| `"D"` \| `"E"`（必须在 options 的 key 中） |
| `multi` | `"AC"`（按字母升序拼接）**或** `["A", "C"]`，至少 2 个 key |
| `judge` | `"T"` / `"F"`（对 / 错） |

### 2.5 示例

**纯文字单选**

```json
{
  "external_id": "gd-2024-xj-Q005",
  "category": "数量关系",
  "sub_category": "数学运算",
  "question_type": "single",
  "stem": "某车间有男工 24 人，女工 18 人，随机抽 2 人恰为 1 男 1 女的概率是？",
  "options": [
    { "key": "A", "text": "24/41" },
    { "key": "B", "text": "16/41" },
    { "key": "C", "text": "8/41" },
    { "key": "D", "text": "32/41" }
  ],
  "answer": "A",
  "explanation": "C(24,1)·C(18,1) / C(42,2) = 432/861 = 24/41。",
  "difficulty": 2,
  "tags": ["排列组合", "概率"]
}
```

**纯图形推理**

```json
{
  "external_id": "gd-2024-xj-Q095",
  "category": "判断推理",
  "sub_category": "图形推理",
  "stem": "请找出最符合变化规律的一项。",
  "stem_images": ["images/q-0095-stem.png"],
  "options": [
    { "key": "A", "images": ["images/q-0095-opt-A.png"] },
    { "key": "B", "images": ["images/q-0095-opt-B.png"] },
    { "key": "C", "images": ["images/q-0095-opt-C.png"] },
    { "key": "D", "images": ["images/q-0095-opt-D.png"] }
  ],
  "answer": "C"
}
```

**资料分析组题**

```json
{
  "external_id": "gd-2024-xj-Q111",
  "category": "资料分析",
  "material_id": "gd-2024-xj-M01",
  "stem": "2023 年 A 省社会消费品零售总额约为多少亿元？",
  "options": [
    { "key": "A", "text": "12500" },
    { "key": "B", "text": "13800" },
    { "key": "C", "text": "14200" },
    { "key": "D", "text": "15600" }
  ],
  "answer": "B"
}
```

---

## 3. materials.json（资料分析专用）

数组结构。若批次不含资料分析，可省略此文件。

```json
[
  {
    "external_id": "gd-2024-xj-M01",
    "content": "根据以下资料，回答 111~115 题。\n\n2023 年，A 省社会消费品零售总额 xx 亿元，同比增长 5.2% ……",
    "images": ["images/m-0001-chart.png"]
  }
]
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `external_id` | string | ✅ | 批次内唯一，被 questions[].material_id 引用 |
| `content` | string | ✅ | 材料正文（可含 LaTeX） |
| `images` | string[] | ⬜ | 图表 |
| `source` / `year` / `region` | - | ⬜ | 同 question，可覆盖 manifest |

---

## 4. 图片规范

- **格式**：`.png` / `.jpg` / `.jpeg` / `.webp`
- **大小**：单张 ≤ 500 KB；超过请压缩/降分辨率
- **命名**：扁平存放在 `images/`，建议格式 `<type>-<序号>-<用途>.<ext>`
  - `q-0001-stem.png` / `q-0001-opt-A.png` / `q-0042-expl.png`
  - `m-0001-chart.png`
- **引用**：在 JSON 中永远用**相对路径** `images/xxx.png`；**不要**使用绝对路径或 URL
- **公式**：优先用 LaTeX 文本，**不要**把公式截图（OCR 公式识别用 Mathpix/MinerU 等多模态工具）
- **表格**：能写 Markdown 表格就写（`| a | b |`），无法表达时再用图片

导入时系统会把 `images/` 下的文件复制到 `public/q-images/<batch_id>/`，JSON 里的路径被改写成 `/q-images/<batch_id>/xxx.png`（前端可直接访问）。

---

## 5. 校验规则摘要

校验器会拒绝以下情况：

1. `manifest.json` 缺失或缺必填字段
2. `batch_id` 含非法字符（只允许 `[a-z0-9-]`）
3. `questions.json` 不是数组；或任一题缺必填字段
4. `category` / `sub_category` 不在枚举表内
5. `external_id` 在批次内重复
6. `answer` 不合法（如 single 题的 answer 不在 options key 中）
7. 引用的图片文件不存在
8. 引用的 `material_id` 在 `materials.json` 中不存在
9. 图片单张 > 2 MB（硬上限）

---

## 6. 工作流（推荐给 Workbuddy）

1. **确定批次**：例如"2024 广东省考县级卷" → `batch_id = gd-2024-xj`
2. **解析 PDF/Word**：按题号拆分，保留原文
3. **OCR + 公式/图表**：中文用 PaddleOCR / MinerU，数学公式输出 LaTeX
4. **结构化**：每道题按 [2.1 字段定义](#21-字段定义) 输出 JSON 对象
5. **切图**：题干/选项/解析各占一张或多张，命名按 [4. 图片规范](#4-图片规范)
6. **生成 `manifest.json`**
7. **本地跑校验**：`node scripts/validate-batch.mjs path/to/batch-dir`（零依赖）
8. **打包上传**：`zip -r gd-2024-xj.zip batch-gd-2024-xj/`
9. **服务器导入**：`npm run import:batch -- /path/to/batch-gd-2024-xj`

---

## 7. 常见问题

**Q: 题干里有复杂表格怎么办？**  
A: 能用 Markdown 表达就写成 Markdown（前端会渲染）；否则截图放 `stem_images`，题干写"（见图）"。

**Q: 多选和不定项怎么区分？**  
A: 统一用 `question_type = "multi"`。不定项的 answer 也是 2~N 个字母的组合。

**Q: 一道题跨页/有续题怎么办？**  
A: 合并为一个 JSON 对象，用 `\n\n` 分段。

**Q: 扫描件质量差，答案不明确？**  
A: `answer` 填**最可能值**，`tags` 加 `"待核对"`，`difficulty` 填 `5`。导入后在错题/复盘界面人工二次校对。

**Q: 重新导入会冲掉之前的错题记录吗？**  
A: 不会。导入以 `external_id` 为键做 **UPSERT**，只更新题目本体；`mistakes` / `practice_answers` 通过内部数字 `id` 关联，不受影响。

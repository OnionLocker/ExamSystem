# 词库扩展包（Vocab Pack）规范

给外部模型（Gemini 等）批量丰富词库用。**产出符合本规范的 JSON 文件，丢进
`src/studyBoost/vocab-packs/`，前端自动装载，无需改任何代码。**

配套命令：

```bash
npm run validate:vocab-pack                 # 校验目录下所有 pack
npm run validate:vocab-pack path/to/x.json  # 校验单个文件
```

校验逻辑与前端装载逻辑共用 `src/studyBoost/vocabSchema.js`，所以
「离线校验通过」等价于「前端能装载」。校验失败的包会被前端**整体跳过**，
不会污染主词库。

---

## 1. 文件结构

```json
{
  "pack_id": "gemini-usage-batch-001",
  "generator": "gemini-3.6-flash",
  "created_at": "2026-07-30",
  "mode": "enrich",
  "notes": "给 500 个常考词补 trap / usage / cloze",
  "entries": [ /* 见下 */ ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `pack_id` | ✅ | 唯一标识，建议 `<生成器>-<主题>-<序号>` |
| `mode` | ✅ | `enrich`（补字段）或 `append`（新增词条） |
| `generator` | ⬜ 建议 | 生成来源，便于溯源与回滚 |
| `created_at` | ⬜ | 生成日期 |
| `notes` | ⬜ | 这批做了什么 |
| `entries` | ✅ | 词条数组 |

### mode 的区别

| mode | 用途 | 匹配方式 | 必填字段 |
|---|---|---|---|
| `enrich` | 给**已有词条**补字段（最常用） | 按 `word` 匹配（也可用 `id`） | `word` |
| `append` | 新增**词库里没有的词** | 按 `id` 去重 | `id` `word` `explanation` |

`enrich` 不需要知道内部 id，写 `word` 即可。匹配不到的条目会被跳过并在
UI 上提示，不会报错中断。

---

## 2. entries 字段

### 2.1 身份字段（enrich 时不可修改）

| 字段 | 类型 | 说明 |
|---|---|---|
| `word` | string | 词条本身，enrich 的匹配键 |
| `id` | string \| number | append 必填，需全局唯一（建议加 pack_id 前缀） |

### 2.2 可补充字段（enrich 白名单）

| 字段 | 类型 | 解锁题型 | 说明 |
|---|---|---|---|
| `explanation` | string | 释义→选词 / 词→选释义 | 释义。enrich 时会**覆盖**原释义，慎用 |
| `cloze` | string[] | **语境填空** | 挖空句，用 `____` 占位该词。见 3.1 |
| `usage` | string | **用法辨析** | 用法要点／搭配限制／语体色彩 |
| `trap` | string | **避坑识别** | 该词**具体**的误用方式（不要写通用套话） |
| `examples` | string[] | **例句选词** | 完整例句（含该词，不挖空） |
| `synonyms` | string[] | — | 近义词，**会被用作强干扰项** |
| `rivals` | string[] | — | 易混词，**优先用作干扰项** |
| `antonyms` | string[] | — | 反义词，展示在解析里 |
| `tags` | string[] | — | 自由标签 |
| `category` | string | — | 陷阱归类 |

数组字段（`cloze` / `examples` / `synonyms` / `rivals` / `antonyms` / `tags`）
在合并时取**并集去重**，不会覆盖已有内容。多个 pack 可以叠加。

字符串字段（`usage` / `trap` / `explanation` / `category`）会**覆盖**。

### 2.3 未列出的字段会被忽略并给出警告

---

## 3. 硬性规则（校验会拦）

### 3.1 cloze 挖空句

- 必须包含 `____`（4 个下划线）作为该词的位置
- **句中不能出现该词本身**，否则答案直接暴露在题干里 → 校验报错
- 句子去掉占位后建议至少 5 个字，否则语境信息不足

```json
"cloze": ["这项技术三年前还是标杆，如今已成____，被更高效的方案取代。"]
```

❌ 错误示例：

```json
"cloze": ["明日黄花指的是____的事物。"]   // 句中出现了答案「明日黄花」
"cloze": ["他____了。"]                   // 语境太短，无法判断
"cloze": ["请填空：___"]                  // 占位符不是 4 个下划线
```

### 3.2 其他

- 数组字段必须是数组，不能是字符串
- `page` 必须是数字
- 同一个 pack 内 `id`/`word` 不能重复
- `append` 的 `id` 不能与主词库冲突

---

## 4. 内容质量要求

引擎负责选项构造（干扰项一律取同字数形近词），**内容质量决定题目质量**：

1. **`trap` 要具体**。主词库里 523/527 条的原始解析是同一套模板文字
   （"考场极易字面误解或混淆主客体搭配"），这种没有信息量，等于没写。
   要写清这个词**具体**被怎么误用。

2. **`usage` 写判定点**，不要复述释义。好的用法要点能让人直接判题：
   适用对象是人还是物、褒义还是贬义、能否带宾语、固定搭配是什么。

3. **`cloze` 语境要有区分度**。句子应当让易混词填进去明显不对，
   而不是随便哪个近义词都能填。

4. **`synonyms` / `rivals` 填真正易混的**，它们会直接变成干扰项。
   填得越准，题目越难、越有练习价值。

---

## 5. 完整示例

```json
{
  "pack_id": "gemini-idiom-trap-001",
  "generator": "gemini-3.6-flash",
  "created_at": "2026-07-30",
  "mode": "enrich",
  "entries": [
    {
      "word": "火中取栗",
      "trap": "易误解为「勇敢冒险、敢闯敢干」而作褒义使用；实为贬义，强调被人利用、自己白吃苦头。",
      "usage": "贬义。主体通常是被利用的一方，句中常有「替人／被人」的意味。",
      "cloze": ["他没看清对方的算盘，稀里糊涂替人____，最后落得两手空空。"],
      "rivals": ["趁火打劫"],
      "tags": ["望文生义", "褒贬误用"]
    }
  ]
}
```

新增词条（`append`）：

```json
{
  "pack_id": "gemini-new-words-001",
  "generator": "gemini-3.6-flash",
  "mode": "append",
  "entries": [
    {
      "id": "gemini-new-words-001-0001",
      "word": "筚路蓝缕",
      "explanation": "形容创业的艰辛。",
      "trap": "易因「蓝缕」误解为衣着华美或形容道路蓝色；实指衣服破烂，强调创业艰苦。",
      "usage": "褒义。用于形容开创事业的艰难历程，不能形容个人穿着。",
      "cloze": ["回望这段____的创业史，才明白今天的规模来得多不容易。"],
      "category": "望文生义陷阱"
    }
  ]
}
```

---

## 6. 建议的批次划分

一个 pack 别做太大，按主题切分便于回滚和排查：

- 按题型目的：`...-trap-001`（补陷阱）、`...-cloze-001`（补语境句）
- 按词表分片：每 100–200 条一个包
- 出问题时删掉对应 json 文件即可完全回滚，主词库不受影响

主词库本身由 `npm run clean:vocab` 从原始 PDF 解析结果生成，
**不要手改 `words_data_clean.json`**——它会被重新生成覆盖。
所有外部内容都走 pack。

---

## 7. 新增题型

如果需要一种本规范里没有的考法，在
`src/studyBoost/questionKinds.js` 的 `QUESTION_KINDS` 数组里加一条即可，
声明它需要哪些字段、题干怎么拼、选项文本取 `word` 还是 `explanation`。
引擎和 UI 都不需要改动，题型开关会自动出现。

# 词库扩展包（Vocab Pack）规范

给外部模型（Gemini 等）批量丰富词库用。**产出符合本规范的 JSON 文件，丢进
`src/studyBoost/vocab-packs/`，前端自动装载，无需改任何代码。**

配套命令：

```bash
npm run validate:vocab-pack                 # 校验目录下所有 pack
npm run validate:vocab-pack path/to/x.json  # 校验单个文件
node scripts/add_vocab.mjs entries.json --dry-run   # 按词名去重，预览当日追加
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
| `append` | 新增**词库里没有的词** | 按 `id` 去重；同词名仍会合并 | `id` `word` `explanation` |

`enrich` 不需要知道内部 id，写 `word` 即可。匹配不到的条目会被跳过并在
UI 上提示，不会报错中断。

装载时如果两条词的 `id` 不同、词名相同，仍按词名合成一条：保留旧 `id`，
释义等标量字段用后加载的词条覆盖，数组字段取并集。所以换一个 id 再 append
同名词，不会新增一条，还会改掉已有字段。每日追加必须按词名跳过，见第 8 节。

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
| `wordType` | string | 类型筛选 | `word` 实词（含双音及三字词）、`idiom` 成语熟语、`collocation` 固定搭配；未核定的不填，显示为其他积累。不能按四字长度判断成语 |
| `collocations` | string[] | 学习卡展示 | 常见搭配，不宣称唯一合法搭配 |
| `publicSources` | object[] | 来源展示 | `{title, url, kind?}`；链接仅接受 http(s)，明确词义参考还是选词参考 |
| `exampleSource` | string | 来源展示 | 原创例句须标为 `原创例句`，不得标为原书例句或真题 |
| `quizKinds` | string[] | 限制自动组题 | 使用已有题型 id；如 `['meaning', 'reverse']`。容易互换的近义词不要直接把例句转成随机语境单选 |

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
- `append` 的词名若与主词库、其它词包、辨析组、单列成语或讲义相同，`npm run validate:vocab-pack` 只给警告，不因此判定失败。旧包仍可装载；警告用来挡住「换 id 再追加同名词」

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

### 第一期词语学习（2026-09-28）

`word-foundation.json` 包含 72 个实词和 16 个固定搭配；与旧词按词名合并并保留旧 ID。
词条资料可继续使用现有 append/enrich 机制。新增 `collocations` 合并时取并集；
`publicSources`、`quizKinds` 等整体覆盖，不改动历史记录键。

本包另有 27 个 `groups`，通过 `idiomGroups.js` 的显式导入接入原有成组学习。
组格式为 `{id, title, axis, members: ['词名', ...], quiz, quizzes: [...]}`；
每个小测含 `{stem, answer, reason, options?}`，词名必须属于本包。
新增组要提供至少两道不同侧重的小测，运行 `node scripts/test-idiom-learning.mjs`。
其他新包目前自动加载词条；如要新增辨析组，须同时在 `idiomGroups.js` 接入，不能只放文件后假定组已生效。

词典释义取自实际读取的公开资料，参考记录保存在 `data/manual-vocabulary-20260928/sources.json`。
搭配、释义概括、例句和小测均属于教研整理，广东标签只来自本地真题文件的试卷和题号证据。
更新证据用 `node scripts/build-idiom-evidence.mjs`；`wordCoverage` 统计两字及以上选项词，
保留旧 `gdCoverage` 的四字以上口径，避免把实词和成语覆盖数混为一谈。

### 第二批扩展（2026-09-28）

同一词包新增 132 个实词、49 组辨析，累计 204 个实词、16 个固定搭配、76 组辨析。
每组有两道原创小测；题干只允许一个 `____`，且不能包含答案本身。
新增词条的词典查询记录保存在 `data/manual-vocabulary-expansion-20260928/sources.json`：
130 条附已读取的词典链接；“趋缓”“激活”未在该词典查到独立词条，只标为教研整理。
“做客／作客”在词典中有交叉义项，已从单选题库移除。
例句、搭配、小测仍为教研整理，不表示真题原文或唯一合法搭配。

---

## 7. 新增题型

如果需要一种本规范里没有的考法，在
`src/studyBoost/questionKinds.js` 的 `QUESTION_KINDS` 数组里加一条即可，
声明它需要哪些字段、题干怎么拼、选项文本取 `word` 还是 `explanation`。
引擎和 UI 都不需要改动，题型开关会自动出现。

---

## 8. 每日追加

新词不要手改 `src/copybook/words_data_clean.json`，也不要往旧包里换一个 id
再塞同名词。用 `scripts/add_vocab.mjs` 按词名去重后写入当日词包。前端通过
`import.meta.glob` 自动装载 `src/studyBoost/vocab-packs/*.json`，构建时打进
`dist/`，`npm run build` 会原子替换页面，不用重启服务。

```bash
node scripts/add_vocab.mjs entries.json [--date YYYYMMDD] [--dry-run] [--build] [--commit]
```

| 参数 | 说明 |
|---|---|
| `entries.json` | 输入路径。内容是 JSON 数组 |
| `--date YYYYMMDD` | 写入 `daily-YYYYMMDD.json`。省略时用 Asia/Shanghai 的今天 |
| `--dry-run` | 只打印会新增和会跳过的词，不写文件 |
| `--build` | 写入成功后依次跑 `npm run validate:vocab-pack <该文件>`、`node scripts/test-idiom-learning.mjs`、`npm run build` |
| `--commit` | 只提交这一份词包并 `git pull --ff-only` 后推送 `main`。不带走工作区里其他人未提交的改动 |

输入每条至少有 `word`、`wordType`、`explanation`。`wordType` 只能是 `word`、`idiom`、`collocation`。可选 `usage`、`examples`、`rivals`、`collocations`、`cloze`、`source`、`publicSources`、`exampleSource`。`cloze` 用 `____` 占位，句中不能含该词。其它字段会报错，并且整批不落盘。

词名先去掉空白、再做全半角归一，然后和下面几处已有词名比对：

- 主库 `src/copybook/words_data_clean.json`
- `src/studyBoost/vocab-packs/*.json` 的词条，以及辨析组 `groups.members`
- `idiomGroups.js`、`idiomSupplement.js` 里的组员和单列成语
- `idiomHandout.json` 讲义

输入内部同样去重。重名的跳过并列入 `skipped`，不覆盖旧字段。通过的词写入
`src/studyBoost/vocab-packs/daily-YYYYMMDD.json`：`mode` 为 `append`，`pack_id`
为 `daily-YYYYMMDD`，并带上 `generator`、`created_at`、`notes`。`id` 自动生成
`daily-YYYYMMDD:词名`。当天文件已在就合并追加，仍然按词名去重。写入前调用
`validatePack`，失败则不落盘。

标准输出只有一行 JSON，供外部程序经 SSH 读取。`added` 是本次新词，`skipped`
是跳过的词和原因，另外有文件路径、`build` 和 `commit` 的结果。

```json
[
  {
    "word": "日追加自测甲",
    "wordType": "word",
    "explanation": "仅作格式示例，不是正式词条。",
    "usage": "写清适用对象或搭配限制。",
    "examples": ["会议上用日追加自测甲说明了这项安排。"],
    "cloze": ["他把这项安排____了一遍，大家才明白下一步。"],
    "exampleSource": "原创例句"
  },
  {
    "word": "日追加自测乙",
    "wordType": "idiom",
    "explanation": "仅作格式示例，不是正式词条。"
  }
]
```

```bash
node scripts/add_vocab.mjs entries.json --dry-run
node scripts/add_vocab.mjs entries.json --build --commit
```

# 真题参考库 API

这套 API 只保存出题参考样本，不会把真题放进「AI 练题」，也不会产生错题或学习画像记录。

## 鉴权

所有接口沿用系统鉴权：

```http
Authorization: Bearer <token>
```

Agent 可先调用 `POST /api/auth/login` 获取 token。接口自描述可通过：

```http
GET /api/reference-questions/schema
```

## 写入无图片题目

`external_id` 是幂等键。重复提交相同 ID 会更新，不会生成重复题。

```bash
curl -X POST http://127.0.0.1:3001/api/reference-questions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "fenbi-2024-gd-judge-001",
    "category": "判断推理",
    "sub_category": "逻辑判断",
    "question_type": "single",
    "stem": "题干全文",
    "options": [
      {"key": "A", "text": "选项 A"},
      {"key": "B", "text": "选项 B"},
      {"key": "C", "text": "选项 C"},
      {"key": "D", "text": "选项 D"}
    ],
    "answer": "B",
    "explanation": "可选；仅保存有权使用的解析",
    "difficulty": 3,
    "tags": ["判断推理-逻辑判断-加强论证"],
    "source": "2024 广东省考真题",
    "year": 2024,
    "region": "广东-县级",
    "source_url": "https://example.com/source",
    "imported_by": "hermes"
  }'
```

必填字段：`external_id`、`category`、`sub_category`、`stem`、`answer`、`tags`、`source`；非判断题还必须有 `options`。

`category` 只允许：政治理论、常识判断、言语理解与表达、数量关系、判断推理、资料分析。

`question_type` 只允许：`single`、`multi`、`judge`。判断题答案使用 `T/F`，也接受“对/错”。

## 写入带图片题目

请求使用 `multipart/form-data`：

- `question`：完整题目 JSON 字符串。
- `stem_images`：题干图片，可重复。
- `explanation_images`：解析图片，可重复。
- `option_A_images` 至 `option_E_images`：对应选项图片，可重复。

```bash
curl -X POST http://127.0.0.1:3001/api/reference-questions \
  -H "Authorization: Bearer $TOKEN" \
  -F 'question={
    "external_id":"fenbi-2024-gd-figure-001",
    "category":"判断推理",
    "sub_category":"图形推理",
    "question_type":"single",
    "stem":"请选择最符合规律的一项。",
    "options":[
      {"key":"A","text":""},
      {"key":"B","text":""},
      {"key":"C","text":""},
      {"key":"D","text":""}
    ],
    "answer":"C",
    "difficulty":3,
    "tags":["判断推理-图形推理-位置规律"],
    "source":"2024 广东省考真题",
    "year":2024,
    "region":"广东-县级"
  };type=application/json' \
  -F "stem_images=@./stem.png" \
  -F "option_A_images=@./a.png" \
  -F "option_B_images=@./b.png" \
  -F "option_C_images=@./c.png" \
  -F "option_D_images=@./d.png"
```

图片只允许 PNG、JPEG、WebP；单张不超过 2 MB；一次最多 20 张。服务端会检查文件真实格式，不只相信扩展名。

更新已有题目时，未重新上传的图片默认保留。传入 `"clear_images": true` 可清除未重新上传的旧图片。

## 检索

出题前按分类和考点取少量同类真题：

```http
GET /api/reference-questions?category=判断推理&sub_category=逻辑判断&tag=判断推理-逻辑判断-加强论证&random=1&limit=5
```

还支持 `year`、`region`；`limit` 最大为 50。

查询单题：

```http
GET /api/reference-questions/<external_id>
```

## AI 练题风格内化

参考题写入后保持在 `reference_questions`，不会直接进入练题库。已解析的省考/国考
可用 `python3 scripts/promote_zhenti_references.py` 升进此表。Hermes 出题通过
`scripts/reference_style.py` 使用这些题（省考定题面，国考垫高）：

```bash
# 把新增/修改题纳入 GONGKAO-STYLE 提纲并写逐题内容哈希标记
npm run reference:build

# 查看已内化、待处理、生成引用与评测引用数量
npm run reference:status

# 按目标考点取 3~5 道生成参考题；新题存在时会先自动增量内化
npm run reference:context -- \
  --role generate \
  --category 判断推理 \
  --sub-category 逻辑判断 \
  --tag 判断推理-逻辑判断-加强论证 \
  --count 5
```

持久化结果位于 Hermes `quiz-pipeline/references/`：

- `reference-style-principles.md`：逐模块定性命题提纲和硬性禁忌。
- `reference-style-profile.md`：按当前题库自动重建的长度分位、来源、设问和图片统计。
- `reference-style-status.json`：版本、语料哈希及已处理/留出/排除数量。

逐题状态保存在 `reference_digest_items`：

- `accepted`：只供生成阶段检索。
- `holdout`：只供独立质量审查，防止生成和评测看同一批样本。
- `excluded`：结构不可用或整题重复。
- 没有记录、内容哈希变化或版本过期：视为待处理；下次 `build/context` 自动重新处理。

每次选择都会写入 `reference_context_runs` 并累计实际使用次数。AI 生成批次必须在
`manifest.json` 分别记录 `generation_contexts` 与 `evaluation_contexts`，并把每次 context
映射到实际生成题的 `external_id`；`evaluation_contexts` 覆盖有 holdout 的生成题，无 holdout 的考纲模拟题可省略。`generation_contexts` 可省略。`import:batch` 会反查已填写的包；缺失、漏绑已有 holdout 的题、
复用或伪造时拒绝导入。

## 删除

```http
DELETE /api/reference-questions/<external_id>
```

删除时会同时清理该题上传的图片。

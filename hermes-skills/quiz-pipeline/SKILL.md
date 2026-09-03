---
name: quiz-pipeline
description: >
  出题流水线（已外部化）。Hermes 识别出题意图后，调用外部工具 quiz_generator.py，
  不再在 session 内加载大量提示词和自己写草稿。工具自动完成：生成 + 双闸门验证 + 导入。
version: 3.0.0
author: local
license: MIT
metadata:
  hermes:
    tags: [kaogong, 出题, 验证, 外部工具]
    related_skills: []
---

# 出题验证流水线 v3（外部化版本）

## 核心改变

**v2 → v3 的本质区别：**
- **v2**：Hermes 在 session 内加载 1584 行提示词 → 写草稿 → 调多个工具验证 → 导入
- **v3**：Hermes 识别意图 → **调用外部统一工具** → 工具返回结果（成功/失败）

**优势：**
- Hermes session 不再膨胀（从 ~10K tokens 降至 ~500 tokens）
- 出题逻辑与 daily_batch_scheduler 统一，质量标准一致
- 外部进程可显示进度，Hermes 不阻塞
- 规则内化在工具里，无需每次重新加载

---

## 铁律（不变）

1. **没过双闸门的题，一道都不许发给用户。**
2. **脚本说不通过，就是不通过。**
3. **能形式化的题型必须形式化。**

---

## 出题流程（精简到 3 步）

### Step 1：识别用户意图，提取参数

用户说：
- "出 5 道翻译推理"
- "来几道资料分析"
- "测测我判断推理"

你需要提取：
1. **模块名**：判断推理 / 资料分析 / 数量关系 / 言语理解与表达 / 科学推理
2. **题量**：用户指定的数量，默认值：
   - 资料分析：20（4材料×5题）
   - 判断推理：20（5图形+15逻辑）
   - 科学推理：5
   - 数量关系：15（5数推+10运算）
   - 言语理解：15
3. **考点**（可选）：用户点名的三级考点，如"翻译推理"
4. **批次 ID**：生成格式 `YYYYMMDD_hermes_<模块或考点>_<序号>`

**特殊规则：**
- 资料分析：用户说"4 篇"或"1 篇" → 自动转换为 20 题或 5 题
- 考点画像优先：如果用户没点名考点，先读取画像薄弱点
  ```bash
  python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --compact
  ```
  输出中的 `weaknesses[0]` 即当前最薄弱考点

### Step 2：调用外部工具

前台 `terminal` 最多 600 秒，出题经常要 5–40 分钟。必须后台跑，禁止前台超时后自己写题。

```
terminal({
  command: "python3 /home/ubuntu/ExamSystem/scripts/quiz_generator.py --module '判断推理' --tag '判断推理-逻辑判断-翻译推理' --count 5 --batch-id 'YYYYMMDD_hermes_翻译推理_01' --interactive",
  workdir: "/home/ubuntu/ExamSystem",
  background: true,
  notify_on_complete: true
})
```

等价命令：

```bash
python3 /home/ubuntu/ExamSystem/scripts/quiz_generator.py \
  --module "判断推理" \
  --tag "判断推理-逻辑判断-翻译推理" \
  --count 5 \
  --batch-id "20260903_hermes_翻译推理_01" \
  --interactive
```

**参数说明：**
- `--module`：必填，模块名
- `--tag`：可选，用户点名的三级考点（不点名则工具根据画像自动选择）
- `--count`：必填，题量
- `--batch-id`：必填，批次 ID（确保唯一）
- `--interactive`：必填，让工具输出简洁 JSON 供你解析

**工具会自动完成：**
1. 加载学员画像快照
2. 构建完整 prompt（含内化规则、质量要求、反克隆检测）
3. 调用 Gemini 生成题目
4. 渲染图像（判断推理/科学推理的图，并行生成）
5. 运行双闸门验证（正确性 + 质量 + 反克隆）
6. 导入数据库

**工具返回 JSON（成功）：**
```json
{
  "status": "success",
  "batch_id": "20260903_hermes_翻译推理_01",
  "imported": 5,
  "batch_dir": "/home/ubuntu/ExamSystem/data/hermes-batches/2026-09-03/20260903_hermes_翻译推理_01",
  "message": "已入库 5 题，批次 20260903_hermes_翻译推理_01"
}
```

**工具返回 JSON（失败）：**
```json
{
  "status": "error",
  "batch_id": "20260903_hermes_翻译推理_01",
  "error": "反克隆检测未通过：发现 2 道疑似克隆题...",
  "message": "出题失败：反克隆检测未通过..."
}
```

### Step 3：告知用户结果

**成功时：**
```
已入库 5 道翻译推理，批次 20260903_hermes_翻译推理_01。
可在 ExamSystem 「AI 练题」查看。
```

**失败时：**
```
出题失败：反克隆检测未通过，发现 2 道疑似克隆参考题结构的题目。
已重试但仍未通过质量闸门，建议换个考点或降低题量重试。
```

---

## 常见场景示例

### 场景 1：用户点名考点
```
用户：来 5 道翻译推理
```

你的动作：
```bash
python3 /home/ubuntu/ExamSystem/scripts/quiz_generator.py \
  --module "判断推理" \
  --tag "判断推理-逻辑判断-翻译推理" \
  --count 5 \
  --batch-id "20260903_hermes_翻译推理_01" \
  --interactive
```

### 场景 2：用户没点名考点
```
用户：出几道判断推理
```

你的动作：
1. 先读画像薄弱点：
   ```bash
   python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --compact
   ```
2. 假设输出 `weaknesses: ["判断推理-逻辑判断-逻辑论证-加强", ...]`
3. 调用工具（可以不传 `--tag`，工具会自动根据画像选择）：
   ```bash
   python3 /home/ubuntu/ExamSystem/scripts/quiz_generator.py \
     --module "判断推理" \
     --count 20 \
     --batch-id "20260903_hermes_判断_01" \
     --interactive
   ```

### 场景 3：资料分析
```
用户：来 4 篇资料分析
```

你的动作：
```bash
python3 /home/ubuntu/ExamSystem/scripts/quiz_generator.py \
  --module "资料分析" \
  --count 20 \
  --batch-id "20260903_hermes_资料_01" \
  --interactive
```
（20 题 = 4 材料×5 题，工具会自动调用 `learner_snapshot.py --ziliao-pack` 分配槽位）

### 场景 4：科学推理
```
用户：出 5 道科学推理
```

你的动作：
```bash
python3 /home/ubuntu/ExamSystem/scripts/quiz_generator.py \
  --module "科学推理" \
  --count 5 \
  --batch-id "20260903_hermes_科推_01" \
  --interactive
```

---

## 禁止事项（v3 强化）

1. **禁止在 Hermes session 内写草稿**：
   - 不要加载 `reference-style-principles.md`（已内化到工具）
   - 不要加载 `quality-feedback.md`（已内化到工具）
   - 不要自己写 `questions.json`
   
2. **禁止绕过工具自己调闸门**：
   - 不要直接调 `generation_gate.py`
   - 不要直接调 `import-batch.mjs`

3. **禁止修改工具返回的失败结果**：
   - 工具说"反克隆检测未通过" → 就是未通过，不要自己重写题目
   - 工具重试 2 次都失败 → 告知用户失败原因，建议换考点

---

## 回退

脚本报 `status=error`：把错误原话告诉用户。禁止自己写 `questions.json`、禁止手调闸门、禁止用 MEMORY.md 里的旧「写题→闸门」流程顶上。

---

## 质量保证（自动）

工具已集成以下质量保证措施（你无需关心细节）：
1. ✅ 反克隆检测：防止照搬参考题结构
2. ✅ 正确性闸门：答案唯一、逻辑自洽、计算正确
3. ✅ 质量闸门：考点明确、干扰项有诊断价值、贴近真题
4. ✅ 硬性规则：广东卷面配比、禁课纲词、脏数字≥40%
5. ✅ 图像并行生成：判断推理 5 张图 + 科学推理 5 张图同时生成
6. ✅ 增量修复：首次失败后只修复失败题，不全批重来

**你的职责只是：**
- 识别用户意图
- 调用工具
- 告知结果

---

## 附录：考点词表位置

需要时参考，但不要每次都加载：
- 判断推理/数量关系：`gd-gongkao-coach/references/solver-canon/05-panduan.md` / `06-shuliang.md`
- 资料分析：`gd-gongkao-coach/references/solver-canon/07-ziliao.md`
- 政治/常识：`01-zhengzhi.md` / `02-changshi.md`
- 言语理解：`03-yanyu.md`

新考点登记：`gd-gongkao-coach/references/knowledge-point-extension.md`

---

## 总结

**v3 的核心哲学：Hermes 是意图识别器，不是出题引擎。**

生成 → 验证 → 导入的复杂流程已外部化，你只需：
1. 理解用户要什么
2. 调 `quiz_generator.py`
3. 转述结果

质量由工具保证，你不背锅。

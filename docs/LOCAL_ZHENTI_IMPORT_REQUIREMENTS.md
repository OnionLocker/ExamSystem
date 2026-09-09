# 本地真题 PDF 导入与结构化需求

> **前置说明**：本文档针对用户**本地已有**公考真题 PDF 的场景（网友回忆版），需要将其解析、结构化并导入系统作为出题参考。不涉及任何在线数据获取。

---

## 一、现状盘点

### 1.1 当前已有素材

```
data/uploads/真题/
├── 国考/           # 8 个 PDF
├── 国考答案/
├── 省考/           # 13 个 PDF
└── 省考答案/       # 10 个 PDF
```

**已解析**：18 个 JSON 文件（`data/zhenti/*.json`）

样例：`2024年广东省公务员录用考试《行测》题（网友回忆版）.json` 含 91 道题。

### 1.2 当前工作流

1. **PDF → JSON**：`scripts/parse_zhenti.py` 调用 gemini-flash 切题 + 打标
2. **JSON → reference_questions 表**：`scripts/promote_zhenti_references.py` 写入参考库
3. **出题时引用**：`scripts/reference_style.py` 按模块/考点检索真题作为风格参考
4. **反克隆检测**：`scripts/anti_clone_checker.py` 防止生成题照搬真题结构

---

## 二、接入需求清单

### 2.1 优先级排序

#### P0（核心需求，立即执行）

1. **补全缺失答案**
   - **现状**：部分解析 JSON 缺 `answer` 字段，导致无法入库
   - **要求**：从本地答案 PDF 中提取，或交叉验证多份来源后补全
   - **零容忍**：答案错误直接污染出题质量，必须严格核对

2. **补全官方解析**（可改写）
   - **现状**：部分题无 `explanation` 字段
   - **要求**：
     - **可以由 Claude/Workbuddy 自行撰写**，不必照抄官方
     - **口径**：实战技巧优先（速算/秒杀/排除法），不要八股式（"根据材料可知…"）
     - **风格**：做题人视角，宁可短也不要啰嗦（3 句到 200 字）
     - 数量关系/资料分析可写步骤（LaTeX），关键是"为什么这么算"

3. **完成剩余 PDF 解析**
   - 国考：8 个 PDF（2024-2026，副省级/地市级/行政执法卷）
   - 省考：13 个 PDF（广东 2020-2026 各卷 + 深圳市考）
   - **目标**：全部转成结构化 JSON（`data/zhenti/`）

4. **知识点标签规范化**
   - **现状**：`parse_zhenti.py` 的 prompt 已要求三级标签，但部分历史数据可能不规范
   - **要求**：
     - 第一个标签必须是 `模块-一级知识点-二级知识点`
     - 数量关系必须用知识卡片三级名，禁止粗标签（如"数量关系-数学运算-排列组合"）
     - 参考 `IMPORT_SPEC.md` 第 2.1 节的 `tags` 字段要求

#### P1（质量提升，2 周内）

5. **图片题补全**
   - **现状**：图形推理题被标记 `has_figure: true` 但实际图片未切出
   - **要求**：
     - 从原始 PDF 按题号切图，命名规范 `q-<题号>-stem.png` / `q-<题号>-opt-A.png`
     - 单张 ≤ 500 KB，格式 PNG/JPG
     - 能用 LaTeX 的公式**不要**截图
   - **优先级**：判断推理 > 资料分析 > 数量关系

6. **资料分析材料组补全**
   - **现状**：部分题标记了 `material_ref` 但 `materials` 数组为空
   - **要求**：按 `IMPORT_SPEC.md` 第 3 节规范补全 `materials.json`

7. **题目去重与质量校验**
   - **工具**：`scripts/promote_zhenti_references.py --dry-run` 可预览重复题
   - **要求**：
     - 删除题干签名完全相同的重复题
     - 修正 `category` / `sub_category` 不在枚举表内的题

#### P2（长期运营）

8. **新卷持续接入**
   - 2027 年及之后的广东省考/深圳市考/国考卷
   - 按 `IMPORT_SPEC.md` 批次规范（`batch_id` + `manifest.json`）

9. **错题订正反馈循环**
   - 用户做题时发现答案错误 → 标记"待核对" → 二次核对后更新参考库

---

## 三、数据质量标准（必须满足）

### 3.1 必备"三件套"

| 字段 | 来源 | 容错度 |
|-----|------|--------|
| **题干（stem）** | 原文照抄 | 零容忍（缺字/错字直接打回） |
| **正确答案（answer）** | 官方答案或交叉验证 | **零容忍**（必须核对） |
| **解析（explanation）** | 可自行撰写或改写 | 宽容（可以缺，但有比没有好） |

### 3.2 字段完整性检查清单

```bash
# 跑这个命令检查哪些 JSON 缺字段
jq -r '.questions[] | select(.answer == null or .answer == "") | {number, module, subtype}' data/zhenti/*.json
```

**必须通过**：
- `category` / `sub_category` 在枚举表内（见 `IMPORT_SPEC.md` 第 2.2 节）
- `answer` 非空且在选项 key 中（单选题）
- `tags[0]` 是规范三级标签
- 引用的图片路径存在（`has_figure: true` 的题）

---

## 四、技术实施路径

### 4.1 现有工具链复用

```bash
# 1. 解析 PDF → JSON
python3 scripts/parse_zhenti.py --only 省考

# 2. 校验 JSON 格式（可选，用于批次导入）
node scripts/validate-batch.mjs data/zhenti/batch-gd-2024-xj/

# 3. 写入参考库（去重 + 跳过无答案/有图题）
python3 scripts/promote_zhenti_references.py --dry-run  # 预览
python3 scripts/promote_zhenti_references.py             # 实际写入

# 4. 重建风格内化（更新命题提纲）
npm run reference:build
npm run reference:status
```

### 4.2 新增工具需求

#### 4.2.1 答案核对助手（建议 Claude 自动化）

**功能**：
- 读取 `data/zhenti/*.json`，找出缺 `answer` 的题
- 读取对应的答案 PDF（`data/uploads/真题/*答案/`）
- 提取答案并写回 JSON

**实现**：
```bash
# 可复用 parse_zhenti.py 的 OCR 逻辑
python3 scripts/merge_answers.py --source data/uploads/真题/省考答案/ --target data/zhenti/
```

#### 4.2.2 图片批量切割工具

**功能**：
- 读取 PDF，按 `has_figure: true` 的题号定位页面
- 调用 PDF 渲染库（`fitz.Pixmap`）切出对应区域
- 按规范命名存入 `images/`

**实现**：参考 `parse_zhenti.py` 的 `fitz` 用法，新增 `scripts/extract_figures.py`

---

## 五、数据规模预估

### 5.1 当前已解析题量

- 18 个 JSON，按样本估算每个 60-100 题
- **预估总量**：~1200 道题

### 5.2 目标题量

- 国考 8 卷 × ~135 题/卷 = 1080 题
- 省考 13 卷 × ~90 题/卷 = 1170 题
- **合计**：~2250 道真题

### 5.3 按模块分布（参考 2024 广东省考 91 题样本）

| 模块 | 题量占比 | 预估题量（2250 题） |
|-----|---------|---------------------|
| 言语理解 | 35% | 788 |
| 判断推理 | 35% | 788 |
| 数量关系 | 10% | 225 |
| 资料分析 | 15% | 338 |
| 常识判断 | 5% | 113 |

---

## 六、质量门控（已有机制）

### 6.1 反克隆检测（`anti_clone_checker.py`）

**检查点**：
1. 连续 8 汉字重合（排除固定设问）
2. 特有实体复用（甲公司/乙部门）
3. 数字关系链克隆（A 比 B 多 20%，B 是 C 的 1.5 倍）
4. 罕见术语组合复用

**触发时机**：`generation_gate.py` 双闸门第二道

### 6.2 生成闸门（`generation_gate.py`）

**第一道**：硬规则机械校验（选项长度/数量/格式）
**第二道**：反克隆检测 + 质量评测

---

## 七、风险与缓解

### 7.1 答案错误风险

**风险**：网友回忆版可能有错
**缓解**：
- 交叉验证至少两家机构答案
- 用户做题时发现错误 → `tags` 加"待核对" → 二次人工确认

### 7.2 版权合规

**风险**：真题资料有版权
**缓解**：
- 仅作为**出题风格参考**，不直接给用户做（`reference_questions` 表）
- AI 生成题经过反克隆检测，不是简单换数字
- `manifest.json` 标注 `license: "仅个人学习使用"`

### 7.3 图片缺失影响

**风险**：图形推理题无图无法入库
**缓解**：
- P0 优先解决文字题（数量关系/言语理解/逻辑判断）
- 图形推理题标记 `has_figure: true` 但暂时不入参考库，等图片补全后再处理

---

## 八、验收标准

### 阶段一（P0 完成）

- [ ] 所有已解析 JSON 的文字题（无图题）均有答案
- [ ] 至少 80% 的题有解析（可自行撰写）
- [ ] `promote_zhenti_references.py` 成功写入 ≥800 道参考题
- [ ] `npm run reference:build` 无报错，`reference-style-principles.md` 更新

### 阶段二（P1 完成）

- [ ] 剩余 PDF 全部解析完成（国考 8 + 省考 13）
- [ ] 判断推理模块的图形推理题图片补全率 ≥50%
- [ ] 资料分析题材料组补全率 100%
- [ ] 去重后参考库题量 ≥1800 道

### 阶段三（P2 运营）

- [ ] 建立新卷接入流程文档
- [ ] 错题订正反馈机制上线

---

## 九、时间与人力估算

| 任务 | 预估工时 | 负责方 |
|-----|---------|--------|
| 补全已解析题答案（~200 题缺答案） | 4 小时 | Claude + 人工核对 |
| 补全解析（~600 题缺解析） | 12 小时 | Claude 批量生成 |
| 解析剩余 PDF（13 个） | 6 小时 | `parse_zhenti.py` 自动 + 人工校对 |
| 知识点标签规范化 | 3 小时 | 脚本批量修正 |
| 图形推理题切图（~200 题） | 8 小时 | 半自动脚本 + 人工确认 |
| 资料分析材料补全（~100 组） | 4 小时 | 脚本提取 |
| **合计（P0+P1）** | **37 小时** | - |

---

## 十、立即行动项（优先级排序）

1. **运行诊断脚本**，生成缺失清单：
   ```bash
   python3 scripts/diagnose_zhenti_gaps.py > data/reports/zhenti-gaps-$(date +%F).md
   ```

2. **批量补全答案**（调用答案 PDF）：
   ```bash
   python3 scripts/merge_answers.py --dry-run
   ```

3. **Claude 批量生成解析**（针对无解析题）：
   ```bash
   python3 scripts/batch_generate_explanations.py --style 实战技巧 --max-length 200
   ```

4. **完成剩余 PDF 解析**：
   ```bash
   python3 scripts/parse_zhenti.py --force
   ```

5. **写入参考库**：
   ```bash
   python3 scripts/promote_zhenti_references.py
   npm run reference:build
   ```

---

## 附录 A：字段映射表（真题 PDF → 系统）

| 真题原始字段 | 系统字段 | 转换规则 |
|------------|---------|---------|
| `module` | `category` | 科学推理 → 判断推理；其他直接映射 |
| `subtype` | `sub_category` | 见 `promote_zhenti_references.py` 第 68 行映射表 |
| `knowledge_points[0]` | `tags[0]` | 必须是三级标签，不足三级需补全 |
| `stem` | `stem` | 去除 `[依托材料]` 前缀（内部字段） |
| `options` | `options` | `{"A": "text"} → [{"key": "A", "text": "text"}]` |
| `has_figure` | 图片文件存在性 | `true` 但无图 → 暂不入库 |

---

## 附录 B：相关文档索引

- **批次导入规范**：`docs/IMPORT_SPEC.md`
- **参考库 API**：`docs/REFERENCE_QUESTION_API.md`
- **现有解析脚本**：`scripts/parse_zhenti.py`
- **参考库写入脚本**：`scripts/promote_zhenti_references.py`
- **反克隆检测**：`scripts/anti_clone_checker.py`
- **出题工具**：`scripts/quiz_generator.py`

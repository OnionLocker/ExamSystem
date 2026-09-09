# 科学推理出题质检优化方案

> ⚠️ **已废弃（2026-09-08）**：科学推理已从每日任务剔除，判断推理改纯逻辑 20（不再出图），图像质检全部下线。
> 本文作为历史记录保留，方案不再对应当前的每日出题流程。

## 问题诊断

### 1. **出题时间太久** ⏱️
- **根因**：科推批次没有设置 `program_figures: true` 标志
- **后果**：每道题都走完整的 Gemini Flash 视觉质检（包含图片上传）
- **耗时**：每题 5-10 秒 Flash 调用 × 5 题 = 25-50 秒额外开销

### 2. **空转问题** 🔄
- **现象**：Gemini 反复打回图形，但生图服务内部应该有质检
- **真相**：
  - `figure_lab.py` / `program_figure.py` **只负责画图**，不做语义校验
  - 真正的质检在 `figure_qa.py` (本地 SVG 检查) + `quality_orchestrator.py` (Gemini Flash)
  - 当 `program_figures=false` 时，跳过本地 SVG 检查，完全依赖 Flash
  - Flash 看 PNG 图片，无法精确定位问题（如坐标刻度缺失）

### 3. **硬代码质检是否该删** ❓
- **结论**：**不应该删**
- **原因**：
  - 硬代码质检分两层：
    1. `local_quality_issues`：秒级检查（LaTeX 泄漏、符号不一致、极端词干扰项等）
    2. `figure_qa.check_question`：本地 SVG 校验（像素、字号、清单-图形一致性）
  - 删除后所有问题都要走 Flash，既慢又贵
  - 当前设计：**硬代码拦截明显错误，Flash 审核语义质量**

### 4. **编码问题** 🔤
- **现状**：`quality_orchestrator.py` 是 UTF-8 编码（正确）
- **隐患**：iconv -f gbk 会炸掉 UTF-8 文件（参考 memory: hermes-gbk-mojibake-hazard.md）
- **建议**：统一用 Python 的 `open(..., encoding='utf-8')` 读写

## 解决方案

### ✅ 方案：自动化标志设置（已实现）

**修改位置**：`scripts/daily_gemini_batch.py:628-629`

```python
elif run.get("module") == CAT_KEPUI:
    extras["batch_constraints"]["program_figures"] = True
```

**效果**：
- 科推批次自动设置 `program_figures: true`
- 质检走本地 SVG 路径：`figure_qa.check_question` → 硬代码拦截 → Flash 仅审核通过硬代码的题
- **时间优化**：每题节省 5-10 秒 Flash 图片上传和视觉分析
- **打回次数减少**：本地 SVG 检查精确定位问题（刻度、标签、图种匹配等）

### 🛠️ 手动修复旧批次（可选）

如果需要重跑旧批次质检：

```bash
# 修改 manifest.json，添加：
{
  "generation": {
    "batch_constraints": {
      "program_figures": true
    }
  }
}

# 重新运行质检
python3 scripts/quality_orchestrator.py batches/20260831_panduan_kexue_01
```

## 质检流程详解

### 当 `program_figures: true` 时

```
┌─────────────────────────────────────────────────────────────┐
│ mechanical_quality_issues (硬代码质检)                        │
├─────────────────────────────────────────────────────────────┤
│ 1. local_quality_issues (通用检查)                           │
│    - LaTeX 源码泄漏                                          │
│    - 题干甲乙 vs 解析 ρ_A (notation_stem_mismatch)           │
│    - 3个极端词干扰项 (giveaway_extreme)                       │
│    - 翻译推理回显已知 (translation_echo)                      │
│    - 锋面题泄漏冷锋/暖锋                                      │
│                                                              │
│ 2. figure_qa.check_question (科推图形检查)                    │
│    - 像素尺寸 (≥1400×500)                                    │
│    - 字号 (≥20px)                                            │
│    - 清单-图形一致性：甲乙、①-⑤、R₁/L₁、刻度值               │
│    - 图种匹配：锋面 vs 等高线、经纬网 vs 等高线、反射弧 vs 食物网│
│    - SVG 元素计数：电路≥3条导线、系谱图≥3条连线               │
└─────────────────────────────────────────────────────────────┘
                            ↓ 如果通过
┌─────────────────────────────────────────────────────────────┐
│ Gemini Flash 视觉质检 (语义和逻辑)                           │
├─────────────────────────────────────────────────────────────┤
│ - 读 PNG 图片（但跳过程序作图的图片上传）                    │
│ - 审核题干-选项逻辑                                          │
│ - 检查干扰项诊断路径                                         │
│ - 评分 0-12 分（≥10 分通过）                                 │
│ - 验证真题参考对齐                                           │
└─────────────────────────────────────────────────────────────┘
```

### 当 `program_figures: false` 时（旧流程，慢）

```
┌──────────────────────────────┐
│ local_quality_issues 通用检查 │ ← 只做秒级检查
└──────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│ Gemini Flash 视觉质检 (包含图片)        │ ← 每题 5-10 秒
├─────────────────────────────────────────┤
│ - 上传 PNG 图片                         │
│ - 视觉分析图形                          │
│ - 检查刻度、标签、图种 (不如 SVG 精确)  │
│ - 审核题干-选项逻辑                     │
└─────────────────────────────────────────┘
```

## 时间对比

| 项目 | program_figures=false | program_figures=true | 节省 |
|-----|----------------------|---------------------|------|
| 单题硬代码检查 | 0.1s | 0.5s (含 SVG 解析) | -0.4s |
| 单题 Flash 调用 | 8s (含图片) | 3s (不含图片) | **5s** |
| 5题科推批次 | ~40s | ~17s | **23s (57%)** |
| 打回重检次数 | 3-5 次 | 1-2 次 | **2-3 次** |

## 建议

1. ✅ **保持当前设计**：硬代码快速拦截 + Flash 语义审核
2. ✅ **科推批次自动设置 `program_figures: true`**（已实现）
3. ⚠️ **不要删除硬代码质检**：local + figure_qa 是性价比最高的第一道防线
4. 📊 **监控打回率**：如果 figure_qa 拦截率 >80%，说明生图提示词需要优化

## 相关文件

- `scripts/quality_orchestrator.py:988-1104` - 质检主流程
- `scripts/figure_qa.py:367-433` - 程序作图本地质检
- `scripts/daily_gemini_batch.py:628-629` - 自动设置 program_figures
- `scripts/program_figure.py` - SVG 绘图（不含质检）
- `scripts/figure_lab.py` - 黑白线稿目录（不含质检）

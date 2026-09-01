# 用户本地脚本和工作流参考（2026-08-06 重写）

> ⚠️ **旧版本引用了不存在的脚本（parse_pdf_workflow.py、gd_gongkao_plan.py）均已废弃，全部删除。**

## 真题库维护

```bash
# 新 PDF 入库（增量，已完成的跳过；--force 重跑）
python3 scripts/parse_zhenti.py

# 合并答案版 PDF（先 --check 试跑，确认全覆盖后再写）
python3 scripts/merge_answers.py --check
python3 scripts/merge_answers.py

# 重建考点地图（改过 JSON 后必跑）
python3 scripts/build_kaodian_map.py
```

真题库：`/home/ubuntu/ExamSystem/data/zhenti/*.json`（18份，2025题，1835答案）
考点地图：`~/.hermes/skills/productivity/gd-gongkao-coach/references/zhenti-kaodian-map.md`

## 用户画像写入（复盘后必做）

```python
import sqlite3, sys
sys.path.insert(0, '/home/ubuntu/ExamSystem/scripts')
from kaodian_profile import record, weak_points

conn = sqlite3.connect('/home/ubuntu/ExamSystem/data/exam.db')
record(conn, '假言命题逆否', '判断推理', '逻辑判断-翻译推理', is_correct=False, elapsed_ms=90000)
conn.commit()
for row in weak_points(conn): print(row)  # 查薄弱点
```

## 题目落库

```bash
cd /home/ubuntu/ExamSystem
npm run validate:batch -- batches/<batch_id>   # 格式校验
npm run import:batch  -- batches/<batch_id>    # 写入 DB
```

## 每日练习 PDF 解析

用户把粉笔 PDF 上传到 `data/uploads/YYYY.MM.DD/pdf/`，把路径发给 hermes 即可自动触发
`~/.hermes/agent-hooks/pdf-gemini-parse.py` 钩子解析，无需手动跑脚本。

## flash 评测（测模型应试能力）

```bash
python3 scripts/eval_flash.py --all-sheng   # 跑全部省考卷
python3 scripts/eval_flash.py --report      # 只看报告
```


# 广东省考每日PDF归档与分析工作流

> ⚠️ **复盘不要走这个目录。** 用户现在把练习卷传到 ExamSystem「资料上传」：
> `/home/ubuntu/ExamSystem/data/uploads/YYYY.MM.DD/pdf/`
> 下面的 `~/.hermes/gongkao_training/` 是旧归档，禁止为了复盘去搜它。

用户每天按导师要求完成练习后，会把练习题/模考 PDF 或截图发给 Hermes。处理原则：**先本地开源解析，再交给 LLM 总结**，不要直接把原始 PDF 当成最终输入。

## 目录结构

总目录（旧，仅历史归档）：

```text
/home/ubuntu/.hermes/gongkao_training/
```

每天一个日期目录：

```text
/home/ubuntu/.hermes/gongkao_training/YYYY-MM-DD/
├── raw/                 # 原始 PDF / 图片
├── parsed/              # 开源工具解析后的 JSON
├── summary.md           # 当日训练总结
└── next_day_plan.md     # 次日调整计划
```

长期总表：

```text
/home/ubuntu/.hermes/gongkao_training/master_progress.csv
```

建议字段：

```text
日期,政治理论,常识,言语正确数,数量正确数,判断正确数,科推正确数,资料正确数,行测总正确数,申论任务,今日问题,明日重点
```

## 处理步骤

1. 识别用户发送的 PDF / 图片属于哪一天；默认用当天日期，用户指定日期时以用户为准。
2. 创建日期目录与 `raw/`、`parsed/` 子目录。
3. 将原始文件放入 `raw/`。
4. 对每个文件运行：

```bash
python3 /home/ubuntu/.hermes/hermes-agent/scripts/parse_pdf_workflow.py <pdf_or_image_path>
```

5. 将 stdout JSON 保存到 `parsed/<原文件名>.json`。
6. LLM 读取 JSON 的 `scores`、`wrong_questions`、`extracted_text`，再做诊断。
7. 生成 `summary.md` 和 `next_day_plan.md`。
8. 必要时更新 `master_progress.csv`。

## 每日总结格式

```text
YYYY-MM-DD 训练总结

一、今日完成
- 政治理论：/10 或 完成情况
- 常识：/5
- 言语：/15
- 数量：/15
- 判断：/25
- 科推：/5
- 资料：/15
- 行测总计：/90
- 申论：完成内容

二、问题诊断
1. ...

三、明日调整
1. ...

四、导师要求
必须明确指出一个最该改的问题，给出硬性补救任务。
```

## 注意事项

- 用户要求题量用明确数字，不说“约”。固定：政治理论10、常识5、言语15、数量15、判断25、科推5、资料15，总计90题。
- 用户是在职备考但上班较清闲，次日计划要拆成上班前/上午/下午/晚上/睡前。
- 口吻按“必须上岸”的导师标准，简洁、严格、可执行。

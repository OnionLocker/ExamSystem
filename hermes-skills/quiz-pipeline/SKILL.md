---
name: quiz-pipeline
description: >
  出题只调外部脚本 quiz_generator.py。禁止在会话里写 questions.json、
  禁止手跑 generation_gate / import-batch。触发词：出题、来几题、测测我、刷题、专项。
version: 3.4.0
author: local
license: MIT
metadata:
  hermes:
    tags: [kaogong, 出题, 外部工具]
    related_skills: [gd-gongkao-coach]
---

# 出题流水线 v3.2

Hermes 只认意图。出题、闸门、入库全部由脚本完成。

## 铁律

1. **不要自己写题。** 不要 `write_file` `questions.json`，不要 `search_files` / `ls` / 查库找生成器。
2. **脚本不存在或失败，就报失败。** 禁止回退到自己出题，禁止手跑闸门。
3. **对话里不要打印题干、选项、答案。** 成功只报批次名和题量。
4. **前台 terminal 只有 180 秒。** 出题要几分钟，必须后台跑。
5. **录音请直接听，不要先转写再当用户正文。** 录音说根据快照选定考点并出 N 道，就出那个考点、那个题量。失败报原文，不要翻仓库。

## 三步

### 1. 抽出参数

- 模块：判断推理 / 数量关系 / 言语理解与表达
- 考点 `--tag`：用户或录音点名则写成规范主标签
  - 排列组合特殊模型 → `数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）`
  - 翻译推理 → `判断推理-逻辑判断-翻译推理`
- 题量：用户说几道就几道；点名考点没说数量则 **5**；不要擅自出 10 题或成套 20 题
- `batch_id`：`YYYYMMDD_hermes_<考点或模块>_<两位序号>`，不得复用已有批次

科学推理、图形推理、资料分析成套卷：告诉用户走日练，不要硬调本脚本。

### 2. 第一个工具就必须是这段后台调用

```
terminal({
  command: "python3 /home/ubuntu/ExamSystem/scripts/quiz_generator.py --module '数量关系' --tag '数量关系-逢考必有的排列组合与概率-特殊模型（八大情形与同组概率）' --count 5 --batch-id 'YYYYMMDD_hermes_排列组合特殊模型_01' --interactive",
  workdir: "/home/ubuntu/ExamSystem",
  background: true,
  notify_on_complete: true
})
```

等 JSON。成功：`status=success`。失败：把 `message` 原样告诉用户。

### 3. 回复

```
已入库 5 题，批次 20260910_hermes_排列组合特殊模型_01
去 ExamSystem → AI 练题。
```

## 禁止

- skill_view 长参考、自己拼草稿、自己跑闸门
- 工具失败后改写题目再发
- 把日练 图形5+逻辑15 套进专项小卷
- 没听清录音就改出快照里的「下一步候选」

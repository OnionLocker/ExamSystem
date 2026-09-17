# 知识点动态补录接口

## 用途

固定词表覆盖的是已确认的高频考点，不是封闭字典。复盘或讲新题时，如果题目确实考查了现有词表没有的、可独立复习的新概念，Hermes 必须把它登记下来，后续沿用同一个标签。

## 判断是否真的是新考点

1. 先查对应 `solver-canon` 的固定词表和 `data/zhenti/*.json` 的历史标签。
2. 如果只是同义叫法、题型不同但知识相同，合并到已有标签，不新增。
3. 只有当它有独立定义、独立解题动作，或连续真题中形成稳定考法时，才登记新点。

## 命名规则

- 浏览树与新一代主标签以粉笔广东·省市类为准：`模块-一级-二级`，例如 `数量关系-数学运算-平均数问题`。
- 更细的叶子必须挂在已有 L3 下：`模块-一级-二级-子题型`，例如 `数量关系-数学运算-平均数问题-加权平均数`。
- 子题型用短而具体的复习词，不写“综合”“其他”“理解能力”，也不加“临时”。
- 解析中第一次出现时写：`本题考察知识点：<标签>（新补录）`；确认后只写标签本身。
- 旧的超长连字符标签（如 `数量关系-逢考必有的排列组合与概率-分堆分配与定序消序`）继续留在画像里，靠 `kaodian_aliases` 对到最近的粉笔路径，**不要清零掌握度**。

## 登记动作（Hermes 一行）

```bash
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --register \
  '数量关系-数学运算-平均数问题-加权平均数' '数量关系' '数学运算' \
  '来源题号；权不同先乘再除；与简单算术平均区分'
```

登记后 `canonicalize` 收下这个 L4，`quiz_lite.py --tag` 立刻能用，Knowledge 树刷新后挂在「平均数问题」下面，不用重部署静态树。不要另造第二套画像表。

```python
import sqlite3
import sys
sys.path.insert(0, '/home/ubuntu/ExamSystem/scripts')
from kaodian_profile import register_knowledge_point

conn = sqlite3.connect('/home/ubuntu/ExamSystem/data/exam.db')
register_knowledge_point(
    conn,
    '数量关系-数学运算-平均数问题-加权平均数',
    '数量关系',
    '数学运算',
    '来源题号；一句定义；与相邻旧考点的区别；固定解题动作',
)
conn.commit()
```

登记后，仅当该作答证据尚未由 AI练题交卷接口自动写入时，才调用一次 `record()`；AI练题复盘不得补写或重复写。录屏/真题复盘登记后立刻用 `exam --exam-id --item` 记本题，同一场同一题不得再记。不要另造标签。下一次出题先查 `kaodian_profile`，新点达到稳定频次后再回填到对应 `solver-canon` 词表和前端 `canon.js`。

## 登记之后立刻可用

`--register` 只收下挂在粉笔 L3 下的叶子（或已有 L3 本身）。L4 按原样进画像，
不会被关键词兜底并进相邻考点。登记完成后：

- `canonicalize` 以登记的标签为准，`validate_ai_primary_tag` 直接放行；
- `quiz_generator.py --tag`／`--blueprint` 立刻能拿它出题，不用改任何代码；
- 新点以 attempts=0 进画像，不会污染 `learner_snapshot`（快照只取 attempts>0）。

两条例外：**资料分析是封闭词表**，旧标签仍会被归一到白名单，不能靠 `--register` 扩；
图形推理、科学推理不走专项出题入口。

扩完顺手在 `solver-canon` 对应卡片的那条考法 bullet 后面加 `（主标签 \`模块-一级-二级\`）`，
出题时该考法的「固定识别／考场步骤／禁止」就会被自动切片注入生成器。

## 复盘输出

新点不隐藏：在题目标签后加一行简短说明“新补录原因”和“下次复习动作”，不要把整套知识库改写成百科。一次复盘最多补录真正独立的新点，疑似同义项先记入 note 等待确认。


## 掌握度

登记或复盘后，只记录明确的对错证据；掌握度由统计脚本自动重算，不要凭一次回答手填 0–100：

```bash
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --list
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --record \
  '模块-一级知识点-二级知识点' '模块' '一级知识点' 0 60000 hermes
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --recompute
```

算法会综合 Beta(2,2) 先验、21 天时间衰减、正式练习/复盘证据权重和有效样本置信度。只“聊到过”但没有明确对错，不得写入事件；`--mastery` 仅保留给用户明确要求的人工覆盖。

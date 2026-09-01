# 知识点动态补录接口

## 用途

固定词表覆盖的是已确认的高频考点，不是封闭字典。复盘或讲新题时，如果题目确实考查了现有词表没有的、可独立复习的新概念，Hermes 必须把它登记下来，后续沿用同一个标签。

## 判断是否真的是新考点

1. 先查对应 `solver-canon` 的固定词表和 `data/zhenti/*.json` 的历史标签。
2. 如果只是同义叫法、题型不同但知识相同，合并到已有标签，不新增。
3. 只有当它有独立定义、独立解题动作，或连续真题中形成稳定考法时，才登记新点。

## 命名规则

- 格式固定：`模块-一级知识点-二级知识点`。
- 二级名称用短而具体的复习词，不写“综合”“其他”“理解能力”。
- 新点先标为临时扩展，但标签本身不要加“临时”字样，避免以后再次改名。
- 解析中第一次出现时写：`本题考察知识点：<标签>（新补录）`；确认后只写标签本身。

## 登记动作

```python
import sqlite3
import sys
sys.path.insert(0, '/home/ubuntu/ExamSystem/scripts')
from kaodian_profile import register_knowledge_point

conn = sqlite3.connect('/home/ubuntu/ExamSystem/data/exam.db')
register_knowledge_point(
    conn,
    '模块-一级知识点-二级知识点',
    '模块',
    '题型或一级知识点',
    '来源题号；一句定义；与相邻旧考点的区别；固定解题动作',
)
conn.commit()
```

登记后，仅当该作答证据尚未由 AI练题交卷接口自动写入时，才调用一次 `record()`；AI练题复盘不得补写或重复写。录屏/真题复盘登记后立刻用 `exam --exam-id --item` 记本题，同一场同一题不得再记。不要另造标签。下一次出题先查 `kaodian_profile`，新点达到稳定频次后再回填到对应 `solver-canon` 词表和前端 `canon.js`。

也可以直接调用命令行接口：

```bash
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --register \
  '模块-一级知识点-二级知识点' '模块' '题型或一级知识点' \
  '来源题号；一句定义；与旧考点区别；固定动作'
```

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

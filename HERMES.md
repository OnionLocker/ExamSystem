# 掌握度

任何对话里，只要能判断 Russell 某个考点的真实掌握变化，立刻写入，不要等他提醒：

```bash
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --list
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --mastery '现有标签或模块-一级-二级' 0到100 '一句依据'
```

- 0 = 完全不会，100 = 稳定会做。
- 有依据才改：讲得清但自己做会停、草稿走偏、连续做对、自己说不会，这些才动分数。
- 不要每轮因为聊到了就加减几分。
- 确认是独立新考点时，先 `--register`，再 `--mastery`。

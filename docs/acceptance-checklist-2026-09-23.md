# 落地验收清单

## 🎯 核心交付物

### 代码实现

| 功能 | 文件 | 状态 | 说明 |
|------|------|------|------|
| **知识债看板** | `src/knowledge/DebtDashboard.jsx` | ✅ | 130行，完整组件 |
| **债务API** | `server/routes/kaodian.js` | ✅ | GET /api/kaodian/debts |
| **快速出题API** | `server/routes/practice.js` | ✅ | POST /api/quiz/lite |
| **页签集成** | `src/knowledge/Knowledge.jsx` | ✅ | 知识树/知识债切换 |
| **快照增强** | `scripts/learner_snapshot.py` | ✅ | render_compact 增加债务段落 |
| **样式** | `src/index.css` | ✅ | 170行债务看板样式 |
| **行为规范** | `AGENTS.md` | ✅ | 完整的 Agent 边界定义 |

### 文档交付

| 文档 | 位置 | 状态 | 用途 |
|------|------|------|------|
| **实施详细文档** | `docs/implementation-2026-09-23.md` | ✅ | 完整技术实现和验收标准 |
| **执行摘要** | `docs/summary-2026-09-23.md` | ✅ | 快速了解成果和操作流程 |
| **行为规范** | `AGENTS.md` | ✅ | Hermes 必读的操作边界 |

---

## 📋 功能验收

### A1 - 知识债看板

#### 后端验收
```bash
# 测试债务接口
curl http://localhost:5173/api/kaodian/debts | jq

# 预期输出：
# {
#   "debts": [
#     {
#       "kaodian": "数量关系-数学运算-工程问题",
#       "module": "数量关系",
#       "wrongCount": 32,
#       "recoveryStreak": 0,
#       "recoveryProgress": "0/2",
#       "lastWrongAt": "2026-09-18",
#       "daysSinceWrong": 5,
#       "mastery": 35,
#       "confidence": 68
#     },
#     ...
#   ],
#   "summary": {
#     "open": 87,
#     "clearedThisWeek": 3
#   }
# }
```

**验收点：**
- [ ] 返回 87 笔未清债务
- [ ] 按 `wrongCount × daysSinceWrong` 降序排列
- [ ] 每笔债包含完整字段
- [ ] summary 汇总正确

#### 前端验收
```
操作步骤：
1. 启动服务：npm run dev
2. 打开知识点页
3. 点击「知识债」页签

预期效果：
✓ 显示债务列表，按紧急度排序
✓ 顶部显示「未清 87 笔 / 本周清掉 N 笔」
✓ 每行显示：考点名、模块徽章、4个统计项
✓ 连对进度显示 0/2 或 1/2，有进度条
✓ 每行有「出这个考点的变式卷」按钮
```

**验收点：**
- [ ] 页签切换正常
- [ ] 债务列表渲染正确
- [ ] 进度条宽度匹配 recoveryStreak
- [ ] 样式符合设计（暖纸色调）

#### 出题功能验收
```
操作步骤：
1. 在债务看板点击任意「出变式卷」按钮
2. 观察按钮状态变为「出题中...」
3. 等待跳转到练题页

预期效果：
✓ 按钮禁用，显示加载状态
✓ 自动跳转到新练习场次
✓ 题目标签匹配该考点
✓ 题目数量为 5 道
```

**验收点：**
- [ ] API 调用成功（检查 Network 面板）
- [ ] 返回 sessionId
- [ ] 页面跳转到 `/practice/{sessionId}`
- [ ] 题目加载正常

---

### A4 - learner_snapshot 增强

#### 快照输出验收
```bash
python3 scripts/learner_snapshot.py --compact

# 预期输出包含：
# 知识债（连对2次才算清偿；连对为0且错次高的，优先安排同考法变式卷，不要开新考点）：
#   - 数量关系-数学运算-工程问题｜累计错32次｜连对0/2 距上次错5天
#   - 数量关系-数学运算-行程问题｜累计错28次｜连对0/2 距上次错3天
#   ...（最多6笔）
```

**验收点：**
- [ ] 输出包含「知识债」段落
- [ ] 显示最多 6 笔债务
- [ ] 每笔显示：考点、错次、连对进度、天数
- [ ] 包含口径说明

#### Hermes 策略验收
```
操作步骤：
1. 启动 Hermes
2. 新建会话
3. 问「现在该练什么」或「给个学习计划」

预期效果：
✓ Hermes 提到具体债务考点
✓ 说明「先清这几笔债」
✓ 不再只说「低置信待测」
✓ 给出清偿策略（变式卷、连对2次）
```

**验收点：**
- [ ] Hermes 读取到快照中的债务信息
- [ ] 建议具体到考点名称
- [ ] 策略符合 AGENTS.md 纪律

---

### C2/C3/C4 - AGENTS.md 行为边界

#### 文档完整性验收
```bash
# 检查文件存在
ls -lh AGENTS.md

# 确认包含所有章节
grep -E "^## " AGENTS.md
```

**预期章节：**
- [ ] 写操作权限
- [ ] 知识点管理权限
- [ ] 工具使用纪律
- [ ] 复盘与审核流程
- [ ] 出题纪律
- [ ] 输出上限处理
- [ ] 会话管理
- [ ] 记忆与画像

#### Hermes 可见性验证
```
操作步骤：
1. 在 Hermes 会话中要求读取 AGENTS.md
2. 问「我的操作边界是什么」

预期效果：
✓ Hermes 能读取到 AGENTS.md
✓ 能总结写操作白名单和禁区
✓ 能说明工具使用纪律
```

**验收点：**
- [ ] 文档在仓库根目录可见
- [ ] Hermes 能访问并理解内容
- [ ] 边界描述清晰无歧义

---

## 🔍 集成测试场景

### 场景 1：完整清债流程

```
步骤：
1. 打开知识债看板
2. 找到连对进度为 0/2 的债务
3. 点击「出变式卷」
4. 做题 5 道，全部做对
5. 交卷
6. 刷新知识债看板

预期结果：
✓ 该债务的 recoveryStreak 变为 1
✓ recoveryProgress 显示 1/2
✓ 进度条宽度 50%

再做一次：
7. 再次出该考点变式卷
8. 全部做对，交卷
9. 刷新知识债看板

预期结果：
✓ 该债务从列表消失（或移到「已清偿」区）
✓ summary 中 open 数量 -1
✓ summary 中 clearedThisWeek +1
```

**验收点：**
- [ ] 连对进度正确更新
- [ ] 清偿后债务消失
- [ ] 汇总数字正确

### 场景 2：Hermes 策略闭环

```
步骤：
1. 运行快照：python3 scripts/learner_snapshot.py --compact
2. 复制输出中的债务信息
3. 在 Hermes 中问「现在该练什么」
4. 确认 Hermes 提到这些债务
5. 按 Hermes 建议清偿 1-2 笔债
6. 再次运行快照
7. 再次问 Hermes

预期结果：
✓ 第一次：Hermes 列出 top 债务
✓ 清偿后：快照中该债务消失
✓ 第二次：Hermes 策略更新，不再提该债务
```

**验收点：**
- [ ] 快照数据实时反映清偿状态
- [ ] Hermes 策略基于最新快照
- [ ] 形成「查债→出题→清偿→策略更新」闭环

### 场景 3：边界测试

```
步骤：
1. 在 Hermes 中随便聊天（非任务对话）
2. 观察是否触发工具调用

预期结果：
✓ 不调用任何工具
✓ 纯文本回复

步骤：
3. 要求 Hermes 修改 src/App.jsx
4. 观察响应

预期结果（理想）：
✓ 说明需要先解释为什么改、影响什么
✓ 等待确认
（注：需配合钩子才能强制拦截）

步骤：
5. 要求 Hermes 写复盘报告到 data/practice-reviews/
6. 观察响应

预期结果：
✓ 直接写入，无需确认
✓ 文件正常创建
```

**验收点：**
- [ ] 闲聊不触发工具
- [ ] 知道禁区需确认（需口头提示或钩子强制）
- [ ] 白名单路径畅通

---

## 📊 数据验证

### 债务数据准确性

```sql
-- 在数据库中验证
sqlite3 data/exam.db

-- 检查未清债务数
SELECT COUNT(*) FROM kaodian_debts WHERE mastered = 0;
-- 预期：87

-- 检查 top 5 债务
SELECT kaodian, wrong_count, recovery_streak, last_wrong_at
FROM kaodian_debts
WHERE mastered = 0
ORDER BY wrong_count * (julianday('now') - julianday(last_wrong_at)) DESC
LIMIT 5;
-- 预期：top 5 错次高、天数久

-- 检查本周清偿数
SELECT COUNT(*) FROM kaodian_debts
WHERE mastered = 1
  AND datetime(updated_at) >= datetime('now', '-7 days');
```

**验收点：**
- [ ] 债务总数匹配
- [ ] 排序逻辑正确
- [ ] 清偿记录准确

---

## ⚙️ 配置验证（手动）

### ~/.hermes/config.yaml

```yaml
# 需手动调整的项
tool_loop_guardrails:
  hard_stop_enabled: true          # ← 改这里
  hard_stop_after:
    exact_failure: 3               # ← 改这里
    same_tool_failure: 4           # ← 改这里
agent:
  max_turns: 30                    # ← 改这里
```

**验收点：**
- [ ] 配置文件存在
- [ ] 护栏参数已调整
- [ ] Hermes 重启后生效

### ~/.hermes/agent-hooks/pre-write.sh

```bash
#!/bin/bash
# 示例钩子脚本

FILE="$1"

# 白名单
if [[ "$FILE" =~ ^data/(practice-reviews|exam-reviews|voice-notes|manual-) ]] || \
   [[ "$FILE" =~ ^hermes-skills/ ]] || \
   [[ "$FILE" =~ /.hermes/memories/ ]]; then
  exit 0
fi

# 禁区
if [[ "$FILE" =~ ^(src|server|scripts)/ ]] || \
   [[ "$FILE" =~ \.(lock|json)$ ]]; then
  echo "❌ 禁止写入 $FILE，需先说明并确认"
  exit 1
fi

exit 0
```

**验收点：**
- [ ] 钩子脚本存在且可执行
- [ ] 白名单路径放行
- [ ] 禁区路径拦截

---

## 🐛 已知问题和限制

### 1. 清偿后不自动刷新

**现象：** 清偿一笔债后，债务看板不会自动更新，需手动刷新页面

**影响：** 用户体验略打折扣

**解决方案（可选）：**
- 方案 A：交卷后自动触发前端刷新债务列表
- 方案 B：WebSocket 推送债务状态变化
- 方案 C：定时轮询（10秒一次）

### 2. quiz_lite.py 假设存在

**现象：** 代码假设 `scripts/quiz_lite.py` 已存在，但可能尚未实现

**影响：** 出题按钮可能 500 错误

**验证：**
```bash
ls scripts/quiz_lite.py
# 如不存在，需补充实现
```

**解决方案：**
- 参考 `docs/implementation-2026-09-23.md` 中的实现示例
- 或复用现有的 `quiz_generator.py` 逻辑

### 3. 配置和钩子不在 git

**现象：** `~/.hermes/config.yaml` 和钩子脚本在用户目录，不随代码提交

**影响：** 需手动配置才能启用护栏

**解决方案：**
- 在 `docs/` 下提供模板文件
- 部署时自动复制到用户目录

---

## ✅ 最终检查清单

### 代码质量
- [ ] 无 ESLint 错误
- [ ] 无 Python 语法错误
- [ ] API 接口有错误处理
- [ ] 前端组件有加载和空态

### 功能完整性
- [ ] A1 知识债看板 100% 实现
- [ ] A4 快照增强 100% 实现
- [ ] C2/C3/C4 文档 100% 实现
- [ ] API 路由可用

### 文档完整性
- [ ] 实施文档详细
- [ ] 执行摘要清晰
- [ ] AGENTS.md 规范完整
- [ ] 验收标准明确

### 可部署性
- [ ] 代码已提交
- [ ] 依赖无变化（无需 npm install）
- [ ] 数据库 schema 无变化
- [ ] 可热部署（重启服务即可）

---

## 🚀 部署步骤

### 1. 拉取代码
```bash
cd /home/ubuntu/ExamSystem
git pull origin main
```

### 2. 重启服务
```bash
# 前端
npm run dev

# 后端（如单独运行）
# pm2 restart exam-server
```

### 3. 验证功能
```bash
# 检查 API
curl http://localhost:5173/api/kaodian/debts

# 检查快照
python3 scripts/learner_snapshot.py --compact

# 打开浏览器测试前端
```

### 4. 配置调整（可选）
```bash
# 编辑 Hermes 配置
vim ~/.hermes/config.yaml

# 创建钩子脚本
vim ~/.hermes/agent-hooks/pre-write.sh
chmod +x ~/.hermes/agent-hooks/pre-write.sh
```

---

## 📞 问题排查

### 前端报错
```bash
# 检查浏览器控制台
# 常见问题：
# - API 404 → 后端路由未生效，检查 server/routes/kaodian.js
# - 样式错乱 → CSS 未加载，检查 src/index.css
# - 组件不显示 → 检查 Knowledge.jsx import
```

### 后端报错
```bash
# 检查服务日志
# 常见问题：
# - quiz_lite.py not found → 脚本不存在或路径错误
# - DB locked → sqlite3 并发访问，稍后重试
# - 500 错误 → 检查 server 日志，可能是数据格式问题
```

### 快照输出异常
```bash
# 检查数据库
sqlite3 data/exam.db "SELECT COUNT(*) FROM kaodian_debts WHERE mastered = 0"

# 如果为 0，可能是：
# - 债务数据未生成 → 需做题产生错误
# - 脚本逻辑问题 → 检查 kaodian_profile.py 的 apply_debt
```

---

**验收负责人：** _______  
**验收日期：** _______  
**验收结果：** [ ] 通过  [ ] 有条件通过  [ ] 不通过  
**备注：** _________________________________

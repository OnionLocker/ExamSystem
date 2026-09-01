# 微信每日计划/定时任务投递排查

适用场景：用户要求创建广东省考每日学习计划、微信测试消息、或问为什么定时任务/消息出现 `Cronjob Response`、`job_id`、`To stop or manage this job`、`No home channel set for weixin` 等提示。

## 用户偏好
- 每日计划只发计划正文，不要附带 Hermes cron 包装头尾。
- 不要把 `Cronjob Response: ...`、`(job_id: ...)`、`To stop or manage this job...` 发给用户。
- 解释故障时保持简短，说明“当时为什么发生、现在是否已修好、以后怎么避免”。

## 去掉 cron 包装尾巴
Hermes cron 默认会包装定时任务输出，包含任务名、job_id 和管理提示。若用户要求不要发这些：

```bash
hermes config set cron.wrap_response false
```

如普通网关回复也带运行元信息 footer，可一并关闭：

```bash
hermes config set gateway.runtime_metadata.enabled false
```

配置通常需要 gateway 重启或新会话才完全生效；但 cron 包装设置会在调度投递时读取配置。

## Weixin home channel 与裸目标
- `send_message(target="weixin")` 是“发到 Weixin home channel”。如果 home channel 未配置，会报：`No home channel set for weixin...`。
- 更稳做法：直接使用完整目标 `weixin:<chat_id>`，尤其是测试消息和定时任务投递，不要依赖裸 `weixin`。
- 用户当前微信 DM target 可从 `send_message(action="list")` 验证；创建 cron 时 `deliver` 应写完整目标，避免 home channel 缺失影响。

## 排查步骤
1. 先 `send_message(action="list")` 查看可用 Weixin 目标。
2. 若要解释 home channel 报错，查日志/任务历史确认是否发生在设置 home channel 之前；不要断言当前仍坏。
3. 检查配置是否已有 `WEIXIN_HOME_CHANNEL` 或 `platforms.weixin.home_channel.chat_id`。
4. 若缺失，可让用户在当前微信聊天发送 `/sethome`，或用配置命令设置（需要知道 chat_id）：
   ```bash
   hermes config set WEIXIN_HOME_CHANNEL <chat_id>
   hermes config set WEIXIN_HOME_CHANNEL_NAME <display_name>
   ```
5. 创建/更新 cron 时优先指定完整 `deliver="weixin:<chat_id>"`。

## 回复模板
- 包装尾巴：`可以，已经关掉 cron 包装。以后每日计划只发正文，不再带 job_id 和 stop reminder。`
- home channel：`这是因为当时用了裸目标 weixin，它需要默认 home channel；当时还没写入，所以报错。现在已有完整 weixin:<chat_id>/home channel，后续我会直接用完整目标，避免再触发。`

## 阶段感知型 Cron Prompt 策略（重要）
每日 cron prompt 需要能根据当前日期自动切换阶段输出，避免每次手动更新 cron prompt。

### 实战模式：用 date 命令获取当天日期
在 cron 的 prompt 中写一段指令，让 AI agent 先执行 `date` 命令（Asia/Shanghai 时区）获取真实日期，再根据日期选择对应阶段。示例如下：

```
## 日期判断逻辑

先用 date 命令获取今天的日期（Asia/Shanghai时区），然后：

### 如果当前日期 < YYYY-MM-DD：发「康复训练」
...
### 如果当前日期 >= YYYY-MM-DD：发「正式训练」
...
```

### 推荐提示词结构
在 cron prompt 开头加日期判断逻辑：

```
你是一个日期感知的备考导师。根据今天的日期，选择对应的阶段输出计划。

日期规则：
- 若 当前日期 < 2026-07-20 → 输出「康复训练计划」（轻量找回状态，50-60%负荷）
- 若 当前日期 >= 2026-07-20 → 按下面的正式阶段规划输出

正式阶段划分：
- 专项突破（7/20→9/6）：主攻弱项，每天按模块刷题
- 刷题强化（9/7→11/1）：大量刷题+套卷训练
- 冲刺模考（11/2→12/9）：全真模考+查漏补缺
```

这样同一个 cron prompt 可以在整个备考周期复用，日期到了自动切换阶段，不需要反复手动修改 cron。

### 完整模板
参见 `templates/date-aware-cron-prompt.md`，包含完整的备考计划 cron prompt 模板（含 ExamSystem 段位目标、用户画像、各阶段详细安排）。创建/更新 cron 时直接复制使用，替换 `YYYY-MM-DD` 为康复截止日期即可。

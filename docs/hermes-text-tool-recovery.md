# Hermes 文本工具调用恢复补丁

`scripts/hermes-text-tool-recovery.patch` 保存 ExamSystem 使用的外部 Hermes 修复及回归测试。当前已应用到 `/home/ubuntu/.hermes/hermes-agent-v2026.8.27`。

模型将 `call:default_api:…{…}` 或 `call:functions:…{…}` 当作普通最终回复时，最多要求两次正式工具调用；仍异常则明确失败。补丁不会解析或执行文本里的命令。前端另外隐藏裸调用文本，并通过工具回执、批次状态和笔记文件核验实际执行结果。

升级 Hermes 后，在新运行时源码目录先检查兼容性再应用：

```bash
git apply --check /home/ubuntu/ExamSystem/scripts/hermes-text-tool-recovery.patch
git apply /home/ubuntu/ExamSystem/scripts/hermes-text-tool-recovery.patch
scripts/run_tests.sh tests/agent/test_dropped_tool_call_recovery.py -q --file-retries 0
```

若检查提示已应用或上下文不匹配，应检查上游是否已包含等效修复，勿强行覆盖现有改动。完成测试、确认无运行中会话后重启 `examsystem-hermes.service`。此补丁不自动随 Hermes 升级安装。

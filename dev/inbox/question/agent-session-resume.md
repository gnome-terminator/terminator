# 重开时是否恢复 agent 会话

状态：待分诊。来源：[终端对接 agent harness 的调研](../../research/agent-harness-integration.md)，2026-11-06，agent:cursor。需要用户决定。

## 观察到的事实

- cmux 和 agent-deck 用 hook 拿到的 `session_id` 记录每个窗格里的 agent 会话，重开时执行 harness 自己的恢复命令，例如 `claude --resume <id>`、`codex resume <id>`。cmux 记录时会去掉启动命令里的 prompt 和密钥，并提供关闭项。
- 各 harness 都有恢复命令：Claude Code `--resume`、Codex `codex resume`、Gemini CLI `--resume`、Cursor CLI `--resume`、OpenCode `-s`、Qwen Code `--resume`。
- 现行决定是会话恢复不恢复正在运行的程序，见 [AGENTS.md](../../../AGENTS.md) 和[锁定标签](../../../docs/decisions/locked-tabs.md)。

## 推测

- 恢复 agent 会话等于在窗格里重新启动程序，与现行决定冲突。若采用，要补一份新的决策记录，并更新需求、架构和 AGENTS.md。
- 这项功能依赖 [agent-state-dbus](../../../archive/dev/inbox/idea/agent-state-dbus.md) 先拿到 `session_id`。

## 怎样核实

- 由用户决定是否要这项功能，以及默认开还是关。

## 去向

未定。2026-11-12 实现 TX-11 时没有做这一条。它和「不恢复正在运行的程序」冲突，仍要用户决定。未决定前不写进需求。

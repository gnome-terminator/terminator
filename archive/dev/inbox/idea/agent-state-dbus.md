# 给 harness hook 一个 DBus 状态入口

状态：已完成。来源：[终端对接 agent harness 的调研](../../../../dev/research/agent-harness-integration.md)，2026-11-06，agent:cursor。

## 观察到的事实

- cmux、iTerm2、Warp、Superset、Sculptor 都以 hooks 上报为主路径：harness 的 hook 调用终端提供的命令，按环境变量定位窗格，报告忙碌、等待批准、完成、出错。
- TerminatorX 的子进程环境已经导出 `TERMINATOR_UUID`、`TERMINATOR_DBUS_NAME`、`TERMINATOR_DBUS_PATH`。DBus 服务 `net.tenshu.Terminator2`（`terminatorlib/ipc.py`）和 `remotinator` 只有建窗、分屏、查询、标题、配置类方法，没有提醒或状态方法。
- 各 harness 的 hook：Claude Code、Qwen Code 有 `PermissionRequest`、`Stop`、`Notification`；Codex 有 `PermissionRequest`、`Stop`；Gemini CLI 有 `Notification`、`AfterAgent`；Cursor CLI 有 `stop`，并兼容 Claude 的 hooks 格式；OpenCode 只有 JS 插件事件。
- 不改用户全局配置的注入方式：cmux 在 PATH 前放包装脚本，给 `claude` 追加 `--settings <hooks.json>`（与用户 `settings.json` 叠加合并），给 `codex` 追加 `-c hooks.*`；不在 cmux 里运行时直接透传。
- 事件到状态的映射可参考 Sculptor 和 Superset，见调研报告的“多 agent 编排器”一节。

## 推测

- 最小实现是一个 DBus 方法（例如按 UUID 设置状态和一段消息）加一个 `remotinator` 子命令，状态显示复用 [agent-attention-bell](agent-attention-bell.md) 的窗格和标签提醒。
- 包装脚本单次注入可以做成可选项，持久写入用户配置需要像 iTerm2 那样先列出改动、可卸载。
- 风险：ssh、容器里没有本机 DBus；在 tmux 里 `TERMINATOR_UUID` 是启动 tmux 服务器那个窗格的值；同一会话总线上的进程能伪造状态，需要限速并标明来源窗格；hooks 和 BEL 两路信号要去重，又不能让一路失败吞掉另一路（cmux#2322 的教训）。
- Codex 的 hook 需要用户信任，或者带 `--dangerously-bypass-hook-trust`，后者不宜默认使用。

## 怎样核实

- 先手写一段 Claude Code hooks JSON，用 `dbus-send` 调一个临时方法，确认 hook 进程里能拿到 `TERMINATOR_UUID` 并定位到窗格。
- 确认 `--settings` 叠加合并在当前 Claude Code 版本上仍成立。
- 决定后写需求条目和设计；DBus 接口是跨模块约定，要更新[架构](../../../../docs/design/architecture.md)。

## 去向

已实现为需求 TX-11 的 DBus 方法 `set_agent_state` 和 `remotinator set_agent_state`。只按 UUID 写入状态和一段短消息，不发按键、不读屏幕。没有做包装脚本，也不改用户的 harness 配置。同一窗格 1 秒内超过 8 次写入会被拒绝。DBus 关闭时这条路径不存在。

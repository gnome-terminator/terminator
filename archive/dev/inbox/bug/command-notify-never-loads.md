# command_notify 插件在上游 VTE 上永远不加载

状态：已完成。来源：[终端对接 agent harness 的调研](../../../../dev/research/agent-harness-integration.md)，2026-11-06，agent:cursor。

## 观察到的事实

- `terminatorlib/plugins/command_notify.py` 只在 `GObject.signal_lookup('notification-received', Vte.Terminal)` 成立时把 `CommandNotify` 放进 `AVAILABLE`，否则 `AVAILABLE = []`。
- `notification-received` 来自 Fedora 的下游 VTE 补丁，从未进入上游；Fedora 41 已删除这批补丁。VTE 0.68 到 0.84 的发布标签里都没有这个信号。
- 本机 VTE 0.68 上插件不会出现在首选项的插件列表里。
- `terminatorlib/plugins/README.md` 和 `doc/` 手册都没有提到这个插件；`tests/run_tests.sh` 只在缺少 libnotify 时跳过收集它。
- VTE 0.78 起用 termprop 重新提供了同类信号：`termprop-changed::vte.shell.precmd`、`vte.shell.preexec`、`vte.shell.postexec`（值为退出码），由新版 `vte.sh` 通过 OSC 666 发送。Ptyxis 就用它做命令完成通知。

## 推测

- 代码随包发布却在任何上游 VTE 上都不会运行，属于失效功能。
- 可选处理：在 VTE 0.78 以上改用 termprop 信号重写，旧版本继续不加载；或者在模块说明里写明依赖已不存在的下游补丁；或者删除。

## 怎样核实

- 在装有 VTE 0.78 以上的环境里确认 `termprop-changed::vte.shell.precmd` 能从 PyGObject 连接，并且新版 `vte.sh` 确实发出 OSC 666。
- 确认上游 Terminator 是否仍保留这个插件，决定改写还是删除时一并考虑与上游的差异。

## 去向

在 `terminatorlib/plugins/command_notify.py` 的模块说明里写明：`notification-received` 没有进入上游 VTE，插件因此不加载。不改写成 termprop，也不删除，以免和上游插件分叉。这项和 TX-11 的 agent 状态无关。

# 把 BEL 变成持续的窗格和标签提醒

状态：已完成。来源：[终端对接 agent harness 的调研](../../../../dev/research/agent-harness-integration.md)，2026-11-06，agent:cursor。

## 观察到的事实

- 在 VTE 上，Codex 和 Qwen Code 默认在失焦时发 BEL；Claude Code 设置 `preferredNotifChannel: "terminal_bell"` 后发 BEL；Aider 找不到 notify-send 时发 BEL。BEL 是现有 VTE 上唯一能零配置收到的 agent 提醒。
- `Terminal.on_bell` 只做三件事：`urgent_bell` 设置窗口紧急提示（默认关），`icon_bell` 让标题栏铃铛显示 1 秒（默认开），`visible_bell` 闪屏 100 毫秒（默认关）。
- 没有持续的窗格或标签“需要注意”状态，左侧标签列表和标签页上没有任何高亮。窗格不在视野里时，1 秒的铃铛图标很容易错过。
- 其他终端的通行做法：窗格标题栏或外圈着色，标签取所含窗格中最紧急的状态，聚焦或按键才清除，窗口失焦时发桌面通知并限频（cmux、Wave、Ptyxis、GNOME Console）。

## 推测

- 单靠 BEL 分不出“在等授权”和“已完成”，其他程序的 BEL 也会触发，所以提醒应可配置，并且语义上只表示“这个窗格要你看一眼”。
- 这项状态以后可以由 hook 或 OSC 7501 提供更细的值，见 [agent-state-dbus](agent-state-dbus.md) 和 [osc7501-program-status](osc7501-program-status.md)。状态模型最好一开始就留出这些值。

## 怎样核实

- 在 TerminatorX 里分别运行 Codex 和设置了 `terminal_bell` 的 Claude Code，切到别的标签，确认 `bell` 信号确实到达。
- 确认 GTK3 窗口紧急提示在 Wayland 和 X11 下各自的表现。
- 决定后按仓库规则：写需求条目，加配置键并同步首选项和 `doc/terminator_config.adoc`，写 `CHANGELOG.md`。默认值要单独决定：[默认开启](../../../../docs/decisions/defaults-on.md)只覆盖它列出的几项能力。

## 去向

已实现为需求 TX-11。`attention_on_bell` 默认关闭。响铃只点亮「要看」；完成和「要看」在该窗格获得焦点或按键后清除。等待批准和出错不因焦点清除。桌面通知只在窗口失焦时发，并限频。没有把这项写进默认开启的那几项。

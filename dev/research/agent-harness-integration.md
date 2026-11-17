# 终端对接 agent harness 的调研

状态：待分诊。范围：其他终端和多 agent 工具怎样对接 Claude Code、Codex CLI 等 agent harness，以及 TerminatorX 在现有 VTE 上能做什么。负责：agent:cursor。

资料核对日期为 2026-11-06。调研分五路进行：agent 原生终端、harness 一侧的扩展点、多 agent 编排器、协议与 IDE 集成、VTE 与 GNOME 终端。开源项目读了源码，闭源产品只看了文档。外部产品和协议变化很快，引用本页结论前先复核版本。由本页产生的待处理项列在[可选方向](#可选方向)。

## 结论

- 终端获取 agent 状态的主流做法是 **hooks 上报**：harness 在关键节点运行 hook，hook 调用终端提供的命令或 socket，把状态报给终端。cmux、iTerm2、Warp、Superset 和微软 Intelligent Terminal 都以此为主路径。
- 2026-10 出现的 **OSC 7501 Program Status Protocol** 让程序直接在输出流里报告状态，Claude Code、Codex、OpenCode、Qwen Code 已经发送，iTerm2、Kitty、cmux 已经显示。它很可能成为通用的带内状态通道。
- 解析屏幕文本的做法维护成本高，正在退居兜底。
- headless 结构化输出（`stream-json`、Codex app-server、ACP）最可靠，但用户看不到原生 TUI，等于另做一个聊天界面，不适合终端模拟器。
- 对 TerminatorX 的主要限制：本机 VTE 是 0.68。VTE 上游不处理 OSC 9、OSC 99、通用 OSC 777 和 OSC 7501，也不把未登记的 OSC 交给嵌入程序。所以在现有 VTE 上可用的信号只有 BEL、窗口标题、前台进程，以及 hook 从带外送来的状态。

## OSC 7501

规范见 [rev 0.4（2026-10-10）](https://www.superlogical.com/rex/docs/build/program-status)，背景见 [Mitchell Hashimoto 的文章（2026-10-06）](https://mitchellh.com/writing/program-status-osc7501)。

- 格式为 `ESC ] 7501 ; state=…:kind=…:progress=…:app=…:msg=<base64> ST`。状态有 `idle`、`working`、`blocked`、`done`、`error`、`clear`；`blocked` 可附带 `kind=permission|question|auth`。支持分层的 `id`，可以报告子任务。
- 生命周期挂在终端已有的事件上：`working`、`blocked` 在进程退出或遇到 OSC 133 `A`（新提示符）时清除；`done`、`error` 保留到用户回到窗格。
- 特性探测：程序发 `OSC 7501;?`，紧跟 `CSI c`。设备属性的回复先到就视为不支持。
- 规范要求终端限制由状态触发的通知频率，并标明状态来自哪个窗格。
- tmux 维护者认为为时过早，会丢弃这个序列（[tmux#5713](https://github.com/tmux/tmux/issues/5713)）。Kitty 维护者的评审促成了 0.4 版（[kitty#10638](https://github.com/kovidgoyal/kitty/issues/10638)）。

发送方（据 [areweosc7501yet](https://areweosc7501yet.com/) 和各项目源码）：

| harness | 行为 |
|---|---|
| Claude Code 2.1.295 起 | 先探测，终端不回应就不发。终端回应后，标题里不再加状态字形 |
| Codex | 不探测，stdout 是终端就发；VTE 版本低于 0.54 时跳过（[codex#57612](https://upd.dev/openai/codex/commit/c0e88f3c04219aaa032aaf4b20a8c3284cc81449)）。0.167.0 源码里确认会发；最早进入哪个正式版，两路调研说法不一致 |
| OpenCode 2.2.0 起 | 经 OpenTUI 发送，不等探测结果；每个会话一条子记录 |
| Qwen Code 0.26.8 | 不探测，直接发 |
| Gemini CLI、Cursor CLI、Aider、Amp | 不发 |

显示方：iTerm2 3.7.5 起、Kitty 0.50.0（2026-11-03）、cmux 0.65.1 起。Ghostty 1.4.0 能解析，界面上忽略。VTE 没有实现。

## harness 一侧的扩展点

| harness | 等待输入相关的 hook | 在 VTE 上默认收到什么 | 会话恢复 | ACP |
|---|---|---|---|---|
| Claude Code 2.1.318 | `PermissionRequest`、`Stop`、`Notification` | OSC 0 标题字形；不发通知 | `--resume`、`--continue` | 适配器 `claude-agent-acp` |
| Codex 0.167.0 | `PermissionRequest`、`Stop`；`notify` 只有 turn-complete | 失焦时 BEL，加 OSC 7501 | `codex resume`、`fork` | 适配器 `codex-acp` |
| Gemini CLI 0.67.0 | `Notification`（ToolPermission）、`AfterAgent` | 默认不通知；开启后发 OSC 777 | `--resume`、`--session-id` | `gemini --acp` |
| Cursor CLI 2026.11.05 | `stop`、`beforeShellExecution`，兼容 Claude 的 hooks 格式 | 什么都不发 | `--resume`、`--continue` | `agent acp` |
| OpenCode 1.19.5 | 插件事件 `session.idle`、`permission.asked` | OSC 7501；通知默认关 | `-c`、`-s`、`--fork` | `opencode acp` |
| Qwen Code 0.26.8 | `Notification`、`Stop` | 失焦时 BEL，加 OSC 7501 | `--continue`、`--resume` | `qwen --acp` |
| Aider 0.86.0 | 没有 hook，只有 `--notifications-command` | 开启后用 notify-send，找不到才发 BEL | 只恢复聊天记录 | 无 |

细节：

- **Claude Code**（[hooks](https://code.claude.com/docs/en/hooks)、[terminal-config](https://code.claude.com/docs/en/terminal-config)）
  - hook payload 公共字段有 `session_id`、`transcript_path`、`cwd`、`hook_event_name`。
  - `Notification` 有延迟：`permission_prompt` 在用户约 6 秒没输入后才触发，`idle_prompt` 在回答结束约 60 秒后触发。需要立即得到信号时用 `PermissionRequest` 和 `Stop`。
  - hook 输出可以带 `terminalSequence`，由 Claude Code 代写到终端，只允许 OSC 0/1/2/9/99/777 和 BEL。
  - 只在 Ghostty、Kitty、iTerm2 里自动发桌面通知。设置 `preferredNotifChannel: "terminal_bell"` 后改发 BEL。
  - `--settings <文件>` 会与用户的 `settings.json` 叠加合并，可以只对单次启动注入 hooks。
- **Codex**
  - hooks 配置在 `~/.codex/hooks.json` 或 `config.toml` 的 `[hooks]`，没有 Notification 事件。新增的 hook 要用户在 `/hooks` 里信任，或者带 `--dangerously-bypass-hook-trust`。
  - `tui.notification_method=auto` 只对 Ghostty、iTerm2、Kitty、Warp、WezTerm 发 OSC 9，VTE、GNOME Terminal、Konsole 都发 BEL（[notifications/mod.rs](https://github.com/openai/codex/blob/main/codex-rs/tui/src/notifications/mod.rs)）。通知默认只在失焦时发，依赖 DEC 1004 焦点事件。
- **Cursor CLI**：终端识别表里有 `TERMINATOR_UUID`，但排在 `VTE_VERSION` 之后，所以 TerminatorX 被识别成 gnome-terminal，走不发通知的分支。

跨 harness 最通用的提醒信号依次是：OSC 7501 的 `blocked`/`done`、BEL、各家 hook。BEL 在 VTE 上已经能收到，但分不出“在等授权”和“已完成”。

## 终端产品的做法

| 产品 | 状态来源 | 是否改 harness 配置 |
|---|---|---|
| cmux（基于 libghostty） | PATH 包装脚本给每次启动注入 hooks，hook 调 `cmux claude-hook` 经 Unix socket 上报；另认 OSC 9/99/777 和 7501 | 单次注入为主；`cmux hooks setup` 可持久写入约 19 种 harness |
| iTerm2 3.7 | hook 调 `it2 handle-agent-hook`；自家 OSC 21337；OSC 7501 | 菜单安装，先列出全部改动，可卸载，被 Claude 覆盖后提示重装 |
| Warp | 按命令名识别 agent；插件发 `OSC 777;notify;warp://cli-agent;<JSON>` | 识别到 agent 且未装插件时弹出提示条，一键安装 |
| Wave | 自家 OSC 16162 报告命令行；用户自配的 hook 调 `wsh badge` | 不改，文档给 JSON 让用户合并 |
| Kitty 0.50 | 只读 OSC 7501、OSC 99、OSC 9;4 | 不改 |
| Ghostty 1.4 | OSC 9/777 转桌面通知，OSC 9;4 进度条 | 不改 |
| WezTerm | 用户自建：hook 发 `OSC 1337 SetUserVar`，Lua 处理 | 不改 |
| Intelligent Terminal 0.3 | hooks；没装 hook 时读会话 JSONL；再退到每 3 秒扫进程名 | `wt-agent-hooks` 插件 |
| Superset | 包装启动命令，hook 调 `notify.sh` 发 HTTP | 写全局配置 |

来源：[cmux agent-hooks](https://github.com/manaflow-ai/cmux/blob/main/docs/agent-hooks.md)、[cmux notifications](https://github.com/manaflow-ai/cmux/blob/main/docs/notifications.md)、[iTerm2 Claude Code 集成](https://iterm2.com/claude-code-integration.html)、[Warp cli_agent.rs](https://github.com/warpdotdev/warp/blob/2b4a66f8/app/src/terminal/cli_agent.rs)、[Warp 通知](https://docs.warp.dev/agents/capabilities/agent-notifications/)、[Wave Claude Code 集成](https://docs.waveterm.dev/claude-code)、[Kitty 协议说明](https://sw.kovidgoyal.net/kitty/misc-protocol/)、[Ghostty 1.4.0](https://ghostty.org/docs/install/release-notes/1-4-0)、[Intelligent Terminal 0.3](https://devblogs.microsoft.com/commandline/intelligent-terminal-v0-3-a-new-way-to-see-and-manage-your-tabs-and-agents/)、[Superset add-agent-support](https://github.com/superset-sh/superset/blob/main/apps/docs/content/docs/add-agent-support.mdx)。

共同的界面做法：

- 窗格外圈或标题栏着色，标签和侧栏的标记取最紧急的状态（等待批准 > 出错 > 忙碌 > 完成）。
- 聚焦或按键后才清除，鼠标经过不算。
- 一个快捷键跳到最近一个等待中的窗格（cmux 用 ⌘⇧U）。
- 桌面通知只在窗口失焦时发，并限制频率。

值得注意的教训：

- cmux 对接入 hooks 的窗格屏蔽原始 OSC 通知以免重复，结果 hook 失败时通知延迟或丢失（[cmux#2322](https://github.com/manaflow-ai/cmux/issues/2322)）。多路信号要去重，但不能让一路的失败吞掉另一路。
- cmux 删掉了“终端标题加按修改时间取最新 JSONL”的兜底，原则是检测只依赖终端自己能控制的东西：包装脚本、注入的环境变量、自己生成的进程（[codex-agent-detection-plan.md](https://github.com/manaflow-ai/cmux/blob/main/docs/codex-agent-detection-plan.md)）。
- cmux 维护者明确不内建自动 worktree，只提供自定义动作示例（[cmux#3414](https://github.com/manaflow-ai/cmux/issues/3414)）。
- 持久改写用户的 `~/.claude/settings.json` 时，iTerm2 早期版本覆盖过用户的其他设置。

## 多 agent 编排器的状态检测路线

| 路线 | 代表 | 优点 | 缺点 |
|---|---|---|---|
| 屏幕解析 | Claude Squad（tmux 快照哈希加固定字符串）、ccmanager（无头 xterm，每个 harness 一个检测器类）、Agent of Empires（TOML 规则引擎） | 不需要 harness 配合 | 与界面文案绑死，Claude 改版就失效；spinner 停顿会误判为空闲；基本识别不了出错 |
| 读窗口标题 | Agent of Empires、Herdr | 成本低，VTE 有 `window-title-changed` | Claude 的字形近几个月改过多次；终端回应 7501 后 Claude 不再写字形 |
| hooks | agent-deck、Superset、cmux、Sculptor、workmux | 语义明确，能拿到 `session_id` | 回答权限提示后没有 hook；长工具调用期间无事件，需要新鲜度窗口（agent-deck 用 2 分钟） |
| 读 transcript | agent-deck 读 Codex rollout | 能补全标题和最后一条消息 | 文件与会话难对应，格式不公开 |
| 结构化输出 | Crystal、Vibe Kanban、Terragon、Conductor | 最可靠，审批能在 GUI 里完成 | 不是原生 TUI |

与 TerminatorX 形态最接近的是 cmux、Superset 和 Sculptor 的终端型 agent。Sculptor 用一个 TOML 描述每个 harness（`launch_command`、`resume_command_template`、hooks 片段），hook 调 `sculpt signal busy|idle|waiting`（[claude-code.toml](https://github.com/imbue-ai/sculptor/blob/main/samples/terminal_agents/claude-code/claude-code.toml)、[claude-code-hooks.json](https://github.com/imbue-ai/sculptor/blob/main/samples/terminal_agents/claude-code/claude-code-hooks.json)）。Sculptor 和 Superset 的事件映射可以直接参考：

| 事件 | 状态 |
|---|---|
| `UserPromptSubmit`、`PostToolUse` | 忙碌 |
| `PermissionRequest`；`Notification` 的 `permission_prompt`；`PreToolUse` 的 `AskUserQuestion` | 等待批准 |
| `Stop` | 完成 |
| `StopFailure` | 出错 |
| `SessionEnd` | 清除 |

## 协议与 IDE 集成

- **ACP**（[规范](https://agentclientprotocol.com/)）：JSON-RPC 2.0 走 stdio。v1 允许 agent 请求客户端代为执行命令（`terminal/*`）。2026-07 的 v2 草案删除了客户端文件系统和终端执行接口，终端改为 agent 推送的只读字节流（[v2 迁移](https://agentclientprotocol.com/protocol/v2/migration.md)）。终端类客户端已有微软 Intelligent Terminal、WispTerm、Alas。实现 ACP 客户端等于另写一个聊天应用，而且 v1 到 v2 正在破坏性迁移。
- **Claude Code 的 IDE 集成**：扩展在 `127.0.0.1` 开 WebSocket，把 token 写进 `~/.claude/ide/<port>.lock`，CLI 连上后通过 MCP 调 `openDiff`、读选区等（[文档](https://code.claude.com/docs/en/vs-code)、[claudecode.nvim PROTOCOL.md](https://raw.githubusercontent.com/coder/claudecode.nvim/main/PROTOCOL.md)）。这套协议面向编辑器，纯终端用处不大。
- **VS Code shell integration**：OSC 633 报告命令起止和退出码。Copilot 的终端工具在 2026 年多次因完成判定出错而杀掉仍在运行的命令（[PR #313589](https://github.com/microsoft/vscode/pull/313589)）。只凭 OSC 133 `D` 判断命令完成并不可靠。
- **JetBrains** 2026.3 起终端改用 libghostty，主要为了 kitty 键盘协议和颜色查询，以支持 Claude Code、Codex 这类 TUI（[博客](https://blog.jetbrains.com/platform/2026/10/jetbrains-terminal-now-uses-ghostty/)）。
- **让 agent 控制终端的 MCP**：sideshell、it2mcp、weztermcp、kitty-mcp-server 等，通过终端的远程控制接口读屏、发按键、分屏。it2mcp 默认只读，会话要先打标签才对 MCP 可见。安全面明显扩大。

## VTE 能力与版本

依据 VTE master `1db464a7`（2026-10-31）源码和 0.68 到 0.84 的发布标签。

| 能力 | 起始版本 | 暴露方式 |
|---|---|---|
| OSC 0/2 标题 | 很早 | `window-title-changed`；0.78 起另有 termprop `xterm.title` |
| OSC 7 工作目录 | 很早 | `current-directory-uri-changed`；0.78 起另有 termprop `vte.cwd`，旧信号弃用但仍发出 |
| BEL | 很早 | `bell` 信号 |
| OSC 8 超链接 | 0.50 | `allow-hyperlink` |
| OSC 133 | 0.76 | 只在内部给单元格打标记，没有信号；`D` 和退出码被忽略 |
| termprop 机制 | 0.78 | `termprop-changed::<名称>`、`get_termprop_*`；`vte_install_termprop()` 注册 `vte.ext.*` 自定义项，必须在创建第一个 `VteTerminal` 之前调用 |
| shell precmd/preexec/postexec | 0.78 | termprop `vte.shell.*`，由 OSC 666 设置，新版 `vte.sh` 会发 |
| OSC 777 | 0.78 | `enable-legacy-osc777`，默认关；只映射 `precmd`、`preexec`、`notify;Command completed`，任意文本通知被丢弃 |
| OSC 9;4 进度 | 0.80 | termprop `vte.progress.*`；必须用 ST 结尾 |
| OSC 9 文本通知、OSC 99、OSC 7501 | 未实现 | — |
| kitty 键盘协议 | 未合入 | [vte!14](https://gitlab.gnome.org/GNOME/vte/-/merge_requests/14) |
| DEC 2026 同步输出 | 未实现 | 模式只登记，不可写 |

- termprop 接口在 GTK3 版本同样可用，只有取图像的接口分 pixbuf 和 texture。
- VTE 文档禁止用 termprop 传递文本类用户通知，值一律按不可信处理。
- Fedora 的 `notification-received` 补丁从未进入上游，Fedora 41 已删除这批下游补丁（[讨论](https://discussion.fedoraproject.org/t/how-is-the-terminals-notify-when-shell-command-finishes-feature-implemented/145835)）。
- Ptyxis 用 `termprop-changed::vte.shell.precmd/preexec` 做命令完成通知和标签 needs-attention；GNOME Console 和 Black Box 轮询前台进程。四个 VTE 系终端的源码里都没有针对 Claude Code 或 Codex 的适配。

## TerminatorX 现状

- **已连接的 VTE 信号**（`terminatorlib/terminal.py`）：`window-title-changed` 驱动标题栏；`current-directory-uri-changed` 标记会话需要保存，找不到这个信号时退到不带名称的 `termprop-changed`；`contents-changed` 用于工作目录探测和回滚缓存；`bell` 只在 `urgent_bell`、`icon_bell`、`visible_bell` 任一开启时连接。
- **`Terminal.on_bell`**：`urgent_bell` 设置窗口紧急提示，按键、点击或获得焦点时清除；`icon_bell`（默认开）让标题栏铃铛只显示 1 秒；`visible_bell` 闪屏 100 毫秒。没有持续的窗格或标签“需要注意”状态，标签上也没有高亮。
- **插件**：`activitywatch.py` 用 libnotify 做活动和静默提醒。`command_notify.py` 只在存在 `notification-received` 信号时加载，在上游 VTE 上永远不加载。
- **DBus**：`net.tenshu.Terminator2`（`terminatorlib/ipc.py`）只有建窗、分屏、查询、标题、配置之类的方法，没有提醒类方法。子进程环境已导出 `TERMINATOR_UUID`、`TERMINATOR_DBUS_NAME`、`TERMINATOR_DBUS_PATH`，hook 可以用来定位窗格。
- **可复用的前台进程探测**：`altscreen.foreground_busy`、`scrollback._foreground_basename`、`close_confirm` 扫描 `/proc`。
- **已经具备的 agent 相关适配**：`send_newline` 默认绑在 Shift+Enter 上，通过 `feed_child` 向程序发送 LF（等同 Ctrl+J），Claude Code 把它当作换行；只有图片的剪贴板会粘贴成文件路径。这两项与 Wave 的做法一致，不需要另做。
- **版本兼容**：本机 VTE 是 0.68.0（`libvte-2.91-0 0.68.0-1ubuntu0.1`）。依赖 termprop 的功能需要 0.78 以上，必须用 `GObject.signal_lookup` 检测后降级。其他发行版带的 VTE 版本未逐一核实。

## 可选方向

按投入从小到大。每条一个待处理项，结论写在各条的去向里。

2026-11-12：持续提醒和 DBus 状态入口已实现为需求 TX-11，默认关闭。`command_notify` 只在插件说明里写明上游 VTE 不会加载它。OSC 7501 不单独立项，状态名已用于 TX-11。重开时恢复 agent 会话仍待决定。

| 方向 | 待处理项 | 依赖 |
|---|---|---|
| 把 BEL 变成持续的窗格和标签提醒，失焦时发桌面通知 | [agent-attention-bell](../../archive/dev/inbox/idea/agent-attention-bell.md) | 任意 VTE |
| 给 hook 一个 DBus 和 `remotinator` 状态入口，可选包装脚本单次注入 | [agent-state-dbus](../../archive/dev/inbox/idea/agent-state-dbus.md) | 任意 VTE |
| 状态模型对齐 OSC 7501，跟进 VTE 上游 | [osc7501-program-status](../../archive/dev/inbox/idea/osc7501-program-status.md) | VTE 上游实现，或 PTY 中继 |
| `command_notify` 插件在上游 VTE 上永远不加载 | [command-notify-never-loads](../../archive/dev/inbox/bug/command-notify-never-loads.md) | VTE 0.78 才有替代信号 |
| 重开时用 harness 的 resume 命令恢复 agent 会话 | [agent-session-resume](../inbox/question/agent-session-resume.md) | 与现行恢复决定冲突，需用户决定 |

暂不建议：

- 实现 ACP 客户端：等于另写聊天应用，协议正在破坏性迁移。
- 对外开放读屏、发按键的 MCP 或 DBus 方法：同一会话总线上的任何进程都能操控终端，需要逐窗格授权，目前没有需求。
- 解析 `contents-changed` 后的屏幕文本判断状态：维护成本高，只适合作为可配置的最后一层兜底。
- 用 harness 的 headless 模式替代 TUI：偏离多窗格终端的定位。

## 未证实

- Copilot CLI 1.0.106 的“reports program status to supporting terminals”是否就是 OSC 7501。
- Codex 的 OSC 7501 最早进入哪个正式版。
- `Vte.install_termprop` 和 `get_termprop_value` 能否从 PyGObject 调用：本机 0.68 无法实测。
- hook 进程能否打开 `/dev/tty`，决定 hook 能否向终端写 BEL 或 OSC 666。
- GTK3 窗口紧急提示在 Wayland 下是否有效。
- VTE 上游是否已有 OSC 7501 相关 issue。
- Ubuntu 24.04、Debian 13 等发行版带的 VTE 版本。

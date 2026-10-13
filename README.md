TerminatorX
===========

![TerminatorX](data/screenshots/terminator.png)

Terminator 由 Chris Jones 在 2007 年写出，2014 到 2020 年由 Stephen Boddy 维护，上游目前由 Matt Rose 维护。其余贡献者见 [AUTHORS](AUTHORS)。TerminatorX 基于 Terminator 2.1.6。

## 简介

TerminatorX 在一个窗口里放多个终端。标签和窗格排在左侧，拖动可以重排、把一个标签嵌到另一个下面，或把窗格拉成自己的标签。一个窗格可以盖住其余窗格，再退回来。底下的终端是 VTE，和 GNOME Terminal 用的是同一个组件，shell、回滚和转义序列都走那套实现。窗口本身很薄：白色标题栏、窗格之间一条 1px 的线，只有在分割之后才出现窗格标题栏。

## 功能

下面这些都默认开着。细节见 [CHANGELOG.md](CHANGELOG.md) 和 `man terminator_config`。

| 功能 | 怎么关掉 |
|---|---|
| 自动保存并恢复布局、标签和工作目录；关掉仍在运行的程序前会询问 | 首选项 > 会话，`restore_last_session = False`，或单次启动加 `terminator --no-restore` |
| 回滚缓存在 `~/.cache/terminator/scrollback/`，恢复后再放出来 | 首选项 > 会话，`scrollback_cache = False` |
| 窗格标题栏上的菜单、最大化和关闭 | 首选项 > 窗格，`titlebar_buttons = False` |
| 单个窗格盖住其余窗格（Ctrl+Shift+Return，Shift+Esc 收回，或双击标题栏） | 首选项 > 窗格，`pane_overlay_maximise = False` |
| 窗格变窄时，字体按 100% / 90% / 80% 缩小 | 首选项 > 窗格，`auto_font_scale = False`，或点标题栏上的比例 |
| 全屏程序（vim、less、htop、tmux）运行时藏起滚动条 | 首选项 > 配置文件 > 滚动，`scrollbar_hide_in_alt_screen = False` |

## 安装

命令名仍是 `terminator`。发行版仓库里的包是上游 Terminator。从这份源码构建见 [INSTALL.md](INSTALL.md)。

仓库：https://github.com/TIIEHenry/TerminatorX

### 快捷键

再开一个终端：

- 水平分割：`Ctrl-Shift-o`
- 垂直分割：`Ctrl-Shift-e`

切换焦点：

- 下一个：`Ctrl-Shift-n`
- 上一个：`Ctrl-Shift-p`

新标签：`Ctrl-Shift-t`

新窗口：`Ctrl-Shift-i`

关闭终端或标签：`Ctrl-Shift-w`，或右键后选关闭。

关掉整个窗口：`Ctrl-Shift-q`

重置缩放：`Ctrl-0`

首选项在窗口标题栏的菜单里；没有标题栏时，在终端上右键。其余快捷键在首选项的键盘绑定里改。

手册：`man terminator`、`man terminator_config`。按 `F1` 打开上游文档：https://gnome-terminator.readthedocs.io/en/latest/

## 参与

问题与改动请发到 https://github.com/TIIEHenry/TerminatorX/issues 。翻译说明见 [TRANSLATION.md](TRANSLATION.md)。

## 许可

GPL v2 only。gedit 终端插件来自 gedit-plugins，许可证为 GPL v2 或更高版本。VTE 的 `vte-demo.py` 版权归原作者，VTE 本身为 LGPL v2。旧图标由 Cristian Grada 以同一许可证提供，新图标由 Cory Kontros 以 CC-by-SA 提供。其余署名见 `debian/copyright`。

## English

TerminatorX keeps several terminals in one window. Tabs and panes are a list on the left: drag to reorder, nest a tab under another, or lift a pane out into its own tab. A pane can open over the others and come back. The terminal is VTE, the widget GNOME Terminal uses. The frame is thin: a white header bar, a 1px line between panes, and a pane titlebar only when the window is split.

It is based on Terminator 2.1.6. The command is still `terminator`. Build instructions are in [INSTALL.md](INSTALL.md). The features in the table above are on by default; the right-hand column is how to turn each one off.

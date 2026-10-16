TerminatorX
===========

![TerminatorX](data/screenshots/terminator.png)

## 简介

TerminatorX 在一个窗口里放多个终端。标签和窗格排在左侧，拖动可以重排、把一个标签嵌到另一个下面，或把窗格拉成自己的标签。一个窗格可以盖住其余窗格，左侧的标签列表还留在外面，再退回来。底下的终端是 VTE，和 GNOME Terminal 用的是同一个组件，shell、回滚和转义序列都走那套实现。窗口本身很薄：白色标题栏、窗格之间一条 1px 的线，只有在分割之后才出现窗格标题栏。

命令名仍是 `terminator`。问题与改动请发到 https://github.com/TIIEHenry/TerminatorX/issues 。

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

完整菜单里可以勾选「下次启动不恢复」：先退出，再启动，下一次普通启动会开一个新窗口。外接屏拔掉以后，落在已经不存在的屏幕上的窗口会回到主显示器。

## 原项目

TerminatorX 基于 [gnome-terminator/terminator](https://github.com/gnome-terminator/terminator) 2.1.6。下面这些是上游的说明：

- [上游仓库](https://github.com/gnome-terminator/terminator)
- [由来、快捷键与参与方式](https://github.com/gnome-terminator/terminator/blob/master/README.md)
- [文档](https://gnome-terminator.readthedocs.io/en/latest/)
- [从源码安装](INSTALL.md)
- [翻译](TRANSLATION.md)
- [许可与署名](debian/copyright)（本仓库 GPL v2 only）

## English

TerminatorX keeps several terminals in one window. Tabs and panes are a list on the left: drag to reorder, nest a tab under another, or lift a pane out into its own tab. A pane can open over the others and come back. The tab list stays where it is. The terminal is VTE, the widget GNOME Terminal uses. The frame is thin: a white header bar, a 1px line between panes, and a pane titlebar only when the window is split.

The command is still `terminator`. The table above lists what this fork adds. The full menu can skip the next plain launch once ("Don't restore next launch"). On X11, a window restored onto a monitor that is no longer connected moves to the primary display. Upstream history, shortcuts and licensing are in the links under 原项目.

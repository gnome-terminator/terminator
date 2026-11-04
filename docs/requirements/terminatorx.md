# TerminatorX 需求

范围：本仓库相对上游 Terminator 2.1.6 保持的行为。状态：当前有效。

命令名是 `terminator`。界面上的产品名是 TerminatorX。底下的终端是 VTE。下面每条都是已经在代码里的行为，默认开启，可以在首选项或配置里关掉。

不恢复正在运行的程序，不自动重连 ssh，也不自动重跑命令。多套命名会话仍用原有的「布局」，不另做一套会话管理。

## 功能要求

### TX-01 普通启动恢复上次的布局

状态：已验证。

会话保存窗口、标签、分屏、比例、工作目录、用户设置过的窗口标题，以及当时最大化的窗格。文件默认在 `$XDG_STATE_HOME/terminator/session.json`，未设置该变量时是 `~/.local/state/terminator/session.json`。

- TX-01.1 当 `restore_last_session` 为真、本次是拿到会话锁的普通启动（没有 `-l`、`-e`、`-x`、`--working-directory`、`--configjson`），并且没有 `--no-restore`、也没有「下次启动不恢复」标记时，启动从 `session.json` 恢复上述布局。
- TX-01.2 `--no-restore` 或 `restore_last_session` 为假时，这次启动不恢复。持有会话锁的进程之后仍可以写会话。
- TX-01.3 用 `-e`、`-x`、非默认的 `-l` 或 `--configjson` 打开的窗口不进入被保存的布局。同一进程里后来开的普通窗口仍可以保存。单独的 `--working-directory` 这次不恢复上次会话，但该窗口仍写入会话。
- TX-01.4 正常退出写入的会话只保留锁定的标签。没有标签列表的窗口仍保留。这次若什么都没留下，下次普通启动开一个新窗口，不回退到 `[layouts][default]`。
- TX-01.5 进程被杀死或崩溃时，不把磁盘上的完整布局收成「只剩锁定标签」。崩溃标记存在时，恢复改读 `.prev` 或 `.prev2`。

证据：[启动判断](../../tests/test_session.py)、[布局往返](../../tests/test_m21_session_roundtrip.py)、[排除窗口](../../tests/test_m21_persist_fixes.py)、[锁定标签](../../tests/test_tab_lock.py)、[崩溃回退](../../tests/test_m31_crash_fallback_restore.py)。

### TX-02 关闭仍在运行的程序前询问

状态：已验证。

- TX-02.1 关闭终端、标签或窗口时，只有除 shell 以外的程序仍在运行才询问，并在对话框里写出该程序。几个空闲 shell 一起关，不询问。
- TX-02.2 `ask_before_closing` 为 `always` 时，即使每个终端都只是 shell 也询问。为 `never` 时不询问。
- TX-02.3 关闭子窗格或布局、且能确定触发控件时，确认框锚在该控件上。关闭窗口或标签、没有锚点时，用模态对话框。

证据：[关闭确认](../../tests/test_close_confirm.py)。

### TX-03 恢复后能看到上次的输出

状态：已验证。

- TX-03.1 `scrollback_cache` 为真时，每个终端最近的输出（含颜色）写入 `~/.cache/terminator/scrollback/`，会话恢复后再放出来。行数默认 2000。
- TX-03.2 使用备用屏幕的全屏程序（vim、less、htop、tmux）不写入这份缓存。
- TX-03.3 缓存里只有 shell 提示符和以往的「上次会话」分隔线时，恢复时不再放出来。

证据：[颜色回放](../../tests/test_scrollback_color.py)、[备用屏幕不写入](../../tests/test_scrollback_fairness.py)、[空提示符不回放](../../tests/test_scrollback_text.py)。

### TX-04 分割后才出现窗格标题栏

状态：已验证。

- TX-04.1 窗口只有一个窗格时不显示窗格标题栏。分割之后每个窗格有一条标题栏，带齿轮菜单、最大化和关闭。`show_titlebar` 为假时始终不显示。
- TX-04.2 `titlebar_buttons` 为假时不显示这些按钮。
- TX-04.3 多个窗格同时可见时，焦点窗格有一圈描边。只有一个可见窗格时不画这圈描边。

证据：[单窗格隐藏标题栏与焦点描边](../../tests/test_terminal_popup_menu.py)、[标题栏按钮](../../tests/test_titlebar_chrome.py)。

### TX-05 单个窗格可以盖住其余窗格

状态：已验证。

- TX-05.1 `pane_overlay_maximise` 为真时，Ctrl+Shift+Return 或 Ctrl+Shift+X 把当前窗格以浮层盖住其余窗格。左侧标签列表仍留在外面，可以点击。Shift+Esc 只在有窗格处于这种状态时收回。
- TX-05.2 浮层只在最大化期间插入。布局遍历看到的父节点是占位槽所在的容器，不是 `Gtk.Overlay`。

证据：[快捷键](../../tests/test_m4_followups.py)、[标签条留在浮层外](../../tests/test_m23_ui_fixes.py)、[逻辑父节点](../../tests/test_paneoverlay.py)。

### TX-06 窄窗格自动缩小字号

状态：已验证。

- TX-06.1 `auto_font_scale` 为真时，窗格按 100%、90%、80% 三档缩放。先看是否达到约 60 列的阅读宽度，再看是否至少有 8 行。占所属窗口或标签至少 45% 的窗格保持 100%。上下对半的两个窗格因此不缩字。
- TX-06.2 标题栏可以锁定该终端的字号。锁定之后不再自动降档，锁定状态写入布局。

证据：[档位与 45% 规则](../../tests/test_autofont.py)、[锁定写入布局](../../tests/test_m25_font_state.py)。

### TX-07 全屏程序隐藏滚动条

状态：已验证。

- TX-07.1 配置文件里 `scrollbar_hide_in_alt_screen` 为真（默认）且程序使用备用屏幕时，隐藏滚动条，并保留同宽的隐藏槽，避免进入或退出 TUI 时改变列数、触发 SIGWINCH 和画面跳动。
- TX-07.2 该项为假时，备用屏幕期间仍按原来的滚动条设置显示。

证据：[备用屏幕滚动条](../../tests/test_altscreen.py)。

### TX-08 窗口标题跟随焦点窗格

状态：已验证。

- TX-08.1 `window_title_mode` 为 `focused`（默认）时，窗口标题取当前焦点窗格。其他窗格的标题变化不覆盖它。
- TX-08.2 `window_title_mode` 为 `fixed` 时，窗口标题使用 `window_title_fixed`，不随焦点窗格改变。

证据：[窗口标题](../../tests/test_window_title.py)。

### TX-09 标签默认是左侧的树

状态：已验证。

- TX-09.1 `tab_position` 为 `left`（默认）时，标签是窗口左侧的一列。每个标签一行，名字来自该标签里焦点窗格的目录，除非用户改过名。标签内部有分屏时，每个窗格是这一行下面的子行。
- TX-09.2 `tab_position` 为 `top` 时，改用顶部标签条。

证据：[左侧列表](../../tests/test_notebook_split.py)、[顶部标签条](../../tests/test_m23_ui_fixes.py)。

## 当前边界

Wayland 上不保存、不恢复窗口位置，因为合成器负责摆放窗口。尺寸、最大化、全屏、布局和最大化的窗格仍然恢复。X11 上，恢复到已经不存在的屏幕时，窗口回到主显示器的工作区。

# 启动和窗格不符合预期时

核对：agent:grok，2026-11-12；agent:grok，2026-11-17。复核期限：2027-04-30。

范围：本机上 TerminatorX 的会话、标签、字号、滚动位置和关闭确认。状态：当前有效。

先看配置和会话文件，再看代码。会话文件默认是 `~/.local/state/terminator/session.json`。配置在 `~/.config/terminator/config`。

## 普通启动是一个新窗口，不是上次的布局

先看这次启动是不是普通启动。带了 `-l`、`-e`、`-x`、`--working-directory` 或 `--no-restore` 就不会恢复。配置里 `restore_last_session` 为假也一样。

若上次是正常退出，未锁定的标签不会留下。一个标签都没锁、窗口又是标签列表时，下次就是新窗口，而且不会改用 `[layouts][default]`。完整菜单里的「下次启动不恢复」只作用于下一次普通启动。

若 `~/.local/state/terminator/restoring` 还在，上次恢复中途崩过，这次会改读 `session.json.prev`。证据在启动脚本 `terminator` 的恢复判断，以及 `SessionManager.load`。

## 昨天开的标签不见了，窗口还在

正常退出只保留锁定的标签。标签行上的锁，或标签菜单里的「下次启动保留」，决定它会不会留下。杀死进程则仍恢复当时打开的全部标签。规则见 [锁定标签](../decisions/locked-tabs.md)。

## 窄窗格里的字变小了

`auto_font_scale` 默认真。窗格窄于约 60 列时会降到 90% 或 80%。占窗口或标签至少 45% 的窗格保持 100%。标题栏上的比例可以锁定这个终端。终端右键和完整菜单里的「自动字号」可以关掉，也可以重新打开；关掉之后这项勾选仍在。首选项的窗格页用同一个名字，配置键是 `auto_font_scale = False`。

## TUI 只画在窗格左上角

标题栏如果是 80% 或 90%，程序多半还在用换档前的行列数。字号变小之后格子变多，旧画面只占左上角，右边和下边是空的。当前版本在窗格尺寸变化的同一次分配里换档。全屏程序占着前台时，定时器不再另改一次字号。已经画成这样的程序要重新打开一次，或者拖一下分隔条，让它收到和格子一致的尺寸。先确认运行的是当前工作树里的 `terminator`。

## 进入 vim 或 less 时终端闪一下、列数跳动

备用屏幕滚动条默认自动隐藏。隐藏 GTK 滚动条时，终端保留同宽的空槽，VTE 的列数应在整个 TUI 期间保持不变。画面若在上下跳，是纵向滚动位置被写回去：备用屏幕已经把调整值收成 0，隐藏前的偏移不能再写回；滚动条自动消失时，字号也不把让出来的宽度当成窗格变宽。若仍看到闪动，先确认运行的是当前工作树的 `terminator`，再用下面的聚焦回归复现：

```bash
tests/run_tests.sh tests/test_altscreen.py -q
```

代码入口是 `terminatorlib/altscreen.py`，滚动条槽位和 VTE 尺寸接线在 `terminatorlib/terminal.py`。不要在这里通过反复 `show()`/`hide()` 让滚动条抢回布局；备用屏幕的一次会话由 `AltScreenScrollbar` 锁存，退出后再统一恢复。

## 往上翻之后视口又回到最旧的一行

回滚顶到行数上限（默认 500 行）之后，窗格变窄、字号换档或滚动条占掉几列，VTE 会把视口放到最旧的一行，上面的历史还在。这不是备用屏幕把隐藏前的偏移写回去。当前版本按离最新一行的距离放回去。自己用滚动条或键盘滚到顶部，仍然停在顶部。清屏和备用屏幕把范围收成一页时，也不把旧位置写回去。

## 一个窗格盖住其他窗格之后，分割或旋转不对

先看是不是还处在浮层最大化。Shift+Esc 收回。布局父节点必须走 `logical_parent`。若新代码用 `get_parent()` 走到了 `Gtk.Overlay`，保存会丢掉其他窗格。见 [逻辑父节点](../decisions/logical-parent.md)。

## 关掉终端时没有询问，里面的程序直接没了

默认只在 shell 以外的程序还在跑时询问。`ask_before_closing = never` 时从不询问。`close_confirm_ignore` 里的程序名会被当成不需要询问。确认框只有一条路径，在 `terminatorlib/close_confirm.py`。

## 验证修复

改了 `terminatorlib/` 之后运行 `python3 scripts/wiki/wiki.py verify --root .`。命令登记在 [开发规范](../standards/development.md)。会话相关的失败优先看 `tests/test_session.py`。

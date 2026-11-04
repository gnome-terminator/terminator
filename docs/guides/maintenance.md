# 启动和窗格不符合预期时

核对：agent:grok，2026-10-30。复核期限：2027-04-30。

范围：本机上 TerminatorX 的会话、标签、字号和关闭确认。状态：当前有效。

先看配置和会话文件，再看代码。会话文件默认是 `~/.local/state/terminator/session.json`。配置在 `~/.config/terminator/config`。

## 普通启动是一个新窗口，不是上次的布局

先看这次启动是不是普通启动。带了 `-l`、`-e`、`-x`、`--working-directory` 或 `--no-restore` 就不会恢复。配置里 `restore_last_session` 为假也一样。

若上次是正常退出，未锁定的标签不会留下。一个标签都没锁、窗口又是标签列表时，下次就是新窗口，而且不会改用 `[layouts][default]`。完整菜单里的「下次启动不恢复」只作用于下一次普通启动。

若 `~/.local/state/terminator/restoring` 还在，上次恢复中途崩过，这次会改读 `session.json.prev`。证据在启动脚本 `terminator` 的恢复判断，以及 `SessionManager.load`。

## 昨天开的标签不见了，窗口还在

正常退出只保留锁定的标签。标签行上的锁，或标签菜单里的「下次启动保留」，决定它会不会留下。杀死进程则仍恢复当时打开的全部标签。规则见 [锁定标签](../decisions/locked-tabs.md)。

## 窄窗格里的字变小了

`auto_font_scale` 默认真。窗格窄于约 60 列时会降到 90% 或 80%。占窗口或标签至少 45% 的窗格保持 100%。标题栏上的比例可以锁定这个终端。关掉该项用首选项里的窗格页，或配置 `auto_font_scale = False`。

## 进入 vim 或 less 时终端闪一下、列数跳动

备用屏幕滚动条默认自动隐藏。隐藏 GTK 滚动条时，终端保留同宽的空槽，VTE 的列数应在整个 TUI 期间保持不变。若仍看到闪动，先确认运行的是当前工作树的 `terminator`，再用下面的聚焦回归复现：

```bash
tests/run_tests.sh tests/test_altscreen.py -q
```

代码入口是 `terminatorlib/altscreen.py`，滚动条槽位和 VTE 尺寸接线在 `terminatorlib/terminal.py`。不要在这里通过反复 `show()`/`hide()` 让滚动条抢回布局；备用屏幕的一次会话由 `AltScreenScrollbar` 锁存，退出后再统一恢复。

## 一个窗格盖住其他窗格之后，分割或旋转不对

先看是不是还处在浮层最大化。Shift+Esc 收回。布局父节点必须走 `logical_parent`。若新代码用 `get_parent()` 走到了 `Gtk.Overlay`，保存会丢掉其他窗格。见 [逻辑父节点](../decisions/logical-parent.md)。

## 关掉终端时没有询问，里面的程序直接没了

默认只在 shell 以外的程序还在跑时询问。`ask_before_closing = never` 时从不询问。`close_confirm_ignore` 里的程序名会被当成不需要询问。确认框只有一条路径，在 `terminatorlib/close_confirm.py`。

## 验证修复

改了 `terminatorlib/` 之后运行 `python3 scripts/wiki/wiki.py verify --root .`。命令登记在 [开发规范](../standards/development.md)。会话相关的失败优先看 `tests/test_session.py`。

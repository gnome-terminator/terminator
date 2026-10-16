---
title: "r09 app-core 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "五条均保留：无窗口布局挂起、坏 size 中断并加窗、关组确认失败仍关闭、编号被树外终端打断、布局启动器加载失败挂起。"
---

# r09 app-core 方案

核对结论：hold 5，weaken 0，drop 0。发现稿引用的行为与磁盘活码一致，行号未偏移。drop 无。本方案只描述改法，不附可合入补丁。

本路不改 `terminatorlib/factory.py`、`terminatorlib/borg.py`、`terminatorlib/signalman.py`、`terminatorlib/cwd.py`、`terminatorlib/version.py`、`terminatorlib/__init__.py`。工作区里已有的 `terminatorlib/altscreen.py` 与 `tests/test_altscreen.py` 不碰。

## r09-1 hold

问题类：布局展开后若层次里没有 Window，`create_layout` 正常返回，进程零窗口停在 `Gtk.main()`；父节点永远挂不上的条目要空转到循环上限才被丢掉。

不变量：

- `layout_get_config` 得到空结果时，仍在 `if not layout` 里 `new_window()` 后立刻返回（现于约 254–258 行）。
- 展开结束时 `hierarchy` 里没有任何 Window：同样 `new_window()` 后返回。不把 `layoutname` 写成这份布局。启动脚本随后的 `layout_done()` 与 `Gtk.main()` 保持原样，因为此时已经有窗口。
- 没有 `parent` 键的非 Window 条目仍立刻删除并 `err('Invalid object: ...')`（约 284–287 行）。删完之后若没有 Window，走上面的补窗。
- `parent` 写了但这一轮没有任何节点被挂上（父节点不在 `objects` 里，或父节点成环）：结束 while，对剩余每个键 `err`，内容至少包含键名和 `parent`。然后照常创建已经挂上的 Window。至少有一个 Window 时不再额外 `new_window()`。
- 合法的深链仍按轮次挂上：每一轮只要消费了至少一个节点就继续。1000 次上限可以留着，但零进展时不再靠它转满才打一行 `hit maximum loop boundary`。

要动的符号：`Terminator.create_layout`（`terminatorlib/terminator.py`）。while 在约 265–301 行，`layout = hierarchy` 在约 303 行，`for windef` 在约 305 行。补窗放在进入 `for windef` 之前。

明确不改：畸形条目的预清理（约 234–242 行）、`remap_layout_uuids`、`window.create_layout` 的递归实现、仓库根脚本 `terminator` 的异常分支、`terminatorlib/ipc.py` 的 `new_window_cmdline`。补窗做在 `create_layout` 里，dbus 路径跟着得到窗口。

本地验证：`tests/test_m21_session_roundtrip.py::test_create_layout_ignores_malformed_entries` 仍得到 1 个窗口。应新增断言：只有互为 `parent` 的非 Window，或 `parent` 指向不存在的键时，`create_layout` 返回后 `Terminator.windows` 非空，且剩余键被点名，循环不会为了同一个挂不上的键再跑满 1000 次。再断言：一个合法 Window 加一个 `parent` 不存在的 Terminal 时，窗口数等于布局里的 Window 数，那个 Terminal 键出现在错误里，`new_window` 的调用次数不多出一次。可用 `tests/test_m34_wayland_hidpi.py` 的 `_run_create_layout` 替换 `new_window` 来计数。测完恢复 Borg 上的 `doing_layout` 等字段。

## r09-2 hold

问题类：某个窗口的 `size` 无法按两个整数读出时，该次布局在这个窗口处中断；抛出的 `ValueError` 还会让启动脚本再开一个窗口。

不变量：

- `size` 是长度至少为 2 的序列，且 `int(parts[0])`、`int(parts[1])` 都成功，并且两个值都大于 1 时，仍 `window.resize`。`tests/test_m34_wayland_hidpi.py` 里的 `[700, 500]` 仍 resize 一次。
- `size` 缺失时不 resize。长度不足、不能取下标、或元素不能 `int()`（`IndexError` / `TypeError` / `ValueError`）时跳过 resize，本窗口的 title、maximised、fullscreen 和 `window.create_layout`，以及后面的 `windef`，继续做完。
- `position` 的解析与容错保持（约 314–321 行）。
- 窗口在 `new_window()` 里就已经 `register_window`（`Window.__init__` 约 89 行），发生在读 `size` 之前。仓库根脚本 `terminator` 的 `except (KeyError, ValueError)`（约 218–222 行）在本次已经有新窗口时不得再 `new_window()`。一个窗口都没建成时仍补一个。条件与下面的 `except Exception`（约 228–229 行）相同：`TERMINATOR.windows` 相对 `windows_before` 没有新增。`restoring` 时的 `sess.restore_failed(ex)` 保持。错误仍要记下来。

要动的符号：

- `Terminator.create_layout` 里 `if 'size' in layout[windef]`（约 322–327 行）。
- 仓库根脚本 `terminator` 的 `except (KeyError, ValueError)` 分支。

明确不改：`window.create_layout`、`paned` / `notebook` 的布局递归、maximised 与 fullscreen 的字符串比较、`ipc.new_window_cmdline` 的调用形状。`size` 在 `create_layout` 内被接住后，dbus 路径不会再被坏 `size` 打断。`describe_layout` 写出的 `get_size()` 二元组（`container.py` 约 441–442 行）保持。能被 `int()` 接受的两元素序列沿用今天的 resize 条件，包括值不大于 1 时不 resize。

本地验证：`test_restore_skips_move_on_wayland` 与 `test_restore_moves_on_x11_and_tolerates_junk` 对合法 size 与坏 position 的断言保持。应新增：同一 `_run_create_layout` 下两个 Window，第一个 `size` 分别为 `['x', 'y']`、`[1]`、`12`，第二个为 `[700, 500]`。`create_layout` 不抛，第一个不出现在 resize 记录里，第二个 resize 为 `(700, 500)`。脚本分支现无直接测试（`tests/test_m21_persist_fixes.py::test_script_finalizes_after_main_loop` 只检查 `finally`）。应新增断言：`KeyError` 或 `ValueError` 且已有新窗口时 `new_window` 不再被调用；`windows` 相对 `windows_before` 没有新增时仍调用一次。

## r09-3 hold

问题类：关闭一组终端时，确认步骤抛错只记调试日志，随后仍会保存并 `emit('close-term')`。

不变量：

- `confirm_close_terminals` 返回假：仍 `return False`，终端保持不动（`tests/test_bulk_close.py::test_group_close_cancel_keeps_terms`）。
- 返回真：仍逐个 `emit('close-term')`。组成员覆盖全部终端时，仍先 `SessionManager().finalize()` 再关闭（`tests/test_m25_round2_fixes.py::test_p2_7_close_group_of_all_terminals_saves_whole_layout`、`tests/test_m25_round2_ordering.py::test_closegroup_all_then_destroy_single_final_save`）。
- 不需要确认时仍直接关闭（`test_group_close_idle_no_dialog`）。
- 导入失败、`confirm_close_terminals` 或确认对话框抛 `Exception`：不调用 `finalize`，不 `emit('close-term')`，函数返回 `False`。用户通过 `util.gerr` 看到失败（模态对话框，确定后才返回）。`gerr` 自己再抛时，用 `err` 记下原来的异常，然后仍然 `return False`。`dbg` 单独不够：桌面启动时用户看不到 stderr。`except` 的类型仍是 `Exception`。

要动的符号：`Terminator.closegroupedterms`（约 937–968 行）。确认失败的返回放在 `leave_legacy_zoom_all`、`finalize` 和 `emit('close-term')` 之前。

明确不改：`confirm_close_terminals` 与 `request_close_terminal` 的判定，`Container.closeterm` 的移除与 `close()`，确认成功之后的 `leave_legacy_zoom_all`。空组今天会得到 `confirm_close_terminals` 的 `True`（`close_confirm.py` 约 418–419 行）并返回 `True`，保持。

本地验证：上面列出的现有测试在确认返回假、返回真、以及无需确认时保持。应新增：把 `confirm_close_terminals` 换成抛 `RuntimeError` 的桩，`closegroupedterms` 返回 `False`，组成员的 `close-term` 未发出；组成员就是 `self.terminals` 全部时，`SessionManager.finalize` 未被调用。`gerr` 换成计数桩，确认失败时调用一次。

## r09-4 hold

问题类：对一组或全部终端插入编号时，不在窗口树里的目标让 `list.index` 抛 `ValueError`，后面的终端写不进数字。

不变量：

- 在各 `self.windows` 上 `enumerate_descendants` 得到的终端，序号仍是该列表中的 `index + 1`，`feed` 的格式串保持（`pad` 为真时用终端总数补零，否则 `'%d'`）。
- `groupsend` 为 off，或为 group 但当前终端 `group` 为 `None` 时，仍只处理 `[widget]`（`get_target_terms` 约 1037–1044 行）。
- `groupsend` 为 all，或为 group 且目标来自 `get_sibling_terms` 时：不在上述列表里的终端（旧式缩放把其余窗格从窗口上拆下，它们仍在 `self.terminals` 里；`Window._legacy_zoom` 约 1256–1258 行）跳过，不调用 `feed`。一次缺失不得让函数抛出，也不得挡住列表里其余终端。已经 `feed` 过的终端保持已写入的内容。
- overlay 放大的终端仍经 placeholder 进入 `enumerate_descendants`，本项不把它们当成树外终端。

要动的符号：`Terminator.do_enumerate`（约 1004–1018 行）。在 `index` 之前判断目标是否在收集到的列表里，不在则继续下一个。

明确不改：`get_target_terms`、`get_sibling_terms`、`enumerate_descendants`、`Window._legacy_zoom` / `_legacy_unzoom`、关闭组时的 `leave_legacy_zoom_all`。`do_insert_term_name`（约 1020–1028 行）不调用 `index`，本项不改。

本地验证：现无 `do_enumerate` 测试。`tests/test_paneoverlay.py::test_enumerate_descendants_counts_placeholder_once` 保持。应新增：`self.terminals` 里有两个终端，`enumerate_descendants` 只返回前一个，`groupsend` 为 all，调用 `do_enumerate`。函数不抛；在树上的那个 `feed` 收到 `b'1'`（`pad` 为假）；不在树上的那个没有 `feed`。同一组里再放一个树外终端且 `groupsend` 为 group 时，树上的同组终端仍收到原序号，函数不抛。

## r09-5 hold

问题类：布局启动器找不到或读不出 glade 时，已登记的启动器不注销，进程没有窗口并停在 `Gtk.main()`。

不变量：

- glade 读成功时，仍 `add_from_string`、取出 `layoutlauncherwin`、连接 `destroy`、`show_all`、`update_layouts`（约 48–65 行）。
- 打开或读出失败（约 37–46 行的 `except`）：在离开构造函数之前 `deregister_launcher_window(self)`，`Terminator.launcher_windows` 不再包含该实例。失败文本仍在退出前打印。
- 这次注销若走到 `Gtk.main_quit()`，不能当成进程会退出。主循环还没开始时，`gtk_main_quit` 因 `main_loops != NULL` 失败并直接返回，随后的 `Gtk.main()` 仍会跑起来。本机 GTK 3 上已看到该 CRITICAL，并且 300ms 超时回调证明主循环确实进入了。
- 因此失败路径在 `terminator` 调用 `Gtk.main()`（约 249–250 行）之前以非零状态结束。`--select` 分支（约 80–82 行）不获得会话锁，也不 `create_layout`。构造函数里不要调用 `SessionManager.finalize`。用 `SystemExit(1)` 从 `__init__` 的失败分支退出，这样仓库根脚本和本文件底部的 `Gtk.main()` 都走不到。

要动的符号：`LayoutLauncher.__init__` 的 `except`（`terminatorlib/layoutlauncher.py` 约 43–46 行）。`register_launcher_window(self)` 今天在打开文件之前（约 31 行），失败时必须成对注销。

明确不改：成功路径上的 `builder`、图标、`on_destroy_event`、`launch_layout`。读成功之后的 `add_from_string` 仍留在 try 外面。不改 `deregister_launcher_window` 在主循环之中、两个列表都空时调用 `Gtk.main_quit()` 的行为。不改 `layoutlauncher.py` 底部 `__main__` 的三行，也不改 `terminator` 里 `Gtk.main()` 的 `finally`。`tests/test_m35_source_locale.py` 里 glade 文件名列表的含义不改。

本地验证：现无 `LayoutLauncher` 行为测试。应新增：把 `open` 换成抛 `FileNotFoundError` 的桩，构造 `LayoutLauncher` 得到 `SystemExit`，退出码为 1；`Terminator().launcher_windows` 不含该实例；`add_from_string` 未被调用。构造前把 `Gtk.main_quit` 换成计数桩，确认失败路径即使触发了它，测试也不进入真正的 `Gtk.main()`。

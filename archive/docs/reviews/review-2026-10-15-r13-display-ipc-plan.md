---
title: "r13 display-ipc 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "五条均保留：短命令留下的折叠计时让随后的全屏不再藏滚动条；remotinator 多打印 None、改错标签、丢掉 -x；dbus 开窗换掉进程内选项且不恢复。"
---

# r13 display-ipc 方案

核对结论：hold 5，weaken 0，drop 0。drop 无。本方案只描述改法，不附可合入补丁。

发现稿对 `AltScreenDetector.update` 的引用块与磁盘不符（磁盘在未折叠且已经 `active` 时有 `UNCOLLAPSE_HOLD_S`）。按活码判定，该差异不推翻 r13-1，见该条。`remotinator` 与 `ipc.py` 的引用行为仍在。`autofont.py`、`zoomguard.py` 发现稿未列条目，本方案不改这两处。

## r13-1 hold

问题类：空历史或刚清屏后，一条仍在前台的普通命令先把滚动历史刷出来，再进 vim / less / htop 时，这次全屏的滚动条不再自动隐藏。

活码：`_on_change`（约 348–359 行）在检测器未 `active`、调整区已可滚动时只把 `had_history` 设真并返回，不调用 `update()`，也不 `schedule()`。`update()` 只在被调用且未折叠时清 `episode_start`（约 253–265 行）；其中 `UNCOLLAPSE_HOLD_S` 仅当已经 `active` 且 `busy is True`。本条场景 `active` 仍为假，发现稿所写的「起点留在对象上」成立。宽限内结束的命令停在提示符时，`_latched()` 为假，`_on_contents`（约 376–393 行）见未折叠直接返回。之后全屏再次折叠时，过期的 `episode_start` 使约 285–287 行不再把 `active` 置真。

不变量：

- 检测器未 `active`、调整区从折叠变为可滚动时，这次折叠观察结束：`episode_start` 为 `None`，`_uncollapse_since` 为 `None`，`had_history` 仍为真，`active` 仍为假。此路径不 `schedule()`。
- 下一次折叠、前台非 shell、原始模式、且有内容证据时，从新的宽限起点重新决定；宽限内 `active` 可以为真。
- 已经 `active` 的全屏重绘不走这条快速路径，`UNCOLLAPSE_HOLD_S` 保持原样。
- 去抖时调整区已经可滚动的那次 `evaluate()` 仍由 `update()` 自己清起点；本条不改变该路径。

要动的符号：`AltScreenScrollbar._on_change` 的未折叠快速返回。在记下 `had_history` 的同时做未激活时的收尾（清 `episode_start` 与 `_uncollapse_since`）。不要在这里探测 PTY，也不要为了收尾去 `schedule()`。

明确不改：`GRACE_S`、`UNCOLLAPSE_HOLD_S`、`update()` 的宽限判断、`_latched`、`_on_contents` 在未锁定且未折叠时直接返回。不改 `autofont.py`、`zoomguard.py`。

本地验证：`tests/test_altscreen.py` 的 `test_on_change_fast_path_skips_timer` 仍须成立（可滚动时不排定时器，且 `had_history` 为真）。应在该测试或紧邻的新断言中补上：先以折叠、`busy` 真、`raw` 假走过 `update()`，使 `episode_start` 非空且 `active` 为假；再对可滚动调整区调用 `_on_change`，断言 `episode_start` 为 `None` 且仍不排定时器；把时钟拨过原来的宽限后，再以折叠、`raw` 真、已有历史调用 `update()`，`active` 为真。`test_detector_grace_then_latch`、`test_detector_redraw_does_not_end_episode`、`test_on_contents_only_schedules_when_collapsed` 保持通过。

## r13-2 hold

问题类：`remotinator` 的分屏和若干查询在正常结果之后多打印一行 `None`。

不变量：

- 每条命令的标准输出只含 dbus 结果本身，不多一行 `None`。
- `get_terminals` 仍是每行一个 uuid，不是列表的 `repr`。字符串（uuid、标题）原样一行。
- 今天包装函数不打印、只由 `remotinator` 打印一次 `None` 的命令（`set_tab_title`、`switch_profile`、`switch_profile_all`、`bg_img`、`bg_img_all`）仍只有这一行 `None`。
- `get_focused_terminal` 继续把 uuid 返回给调用方，由 `remotinator` 打印，不在包装里再打印。

要动的符号：

- `terminatorlib/ipc.py` 里自己 `print` 的客户端包装：`new_window`、`new_tab`、`hsplit`、`vsplit`、`get_terminals`、`get_window`、`get_window_title`、`get_tab`、`get_tab_title`。改为返回 dbus 结果，包装内不再 `print`。
- `remotinator` 约 108、113 行仍是唯一打印点。打印前区分类型：`str` 原样；列表、元组以及 dbus 字符串数组按行拼接；不要对字符串做按字符拼接。`None` 仍打印为 `None`。

明确不改：服务端 dbus 方法的返回值语义。不改 `get_focused_terminal` 的 `return`。不改上面列出的那些本来就不打印的包装。

本地验证：仓库没有 ipc / remotinator 客户端测试。应新增：替掉会话总线，让代理方法返回固定 uuid 或 uuid 列表；调用 `hsplit`、`get_terminals`、`get_window`、`get_tab_title`、`new_window`，断言包装的返回值等于代理返回值，且包装自身不写标准输出；再走 `remotinator` 的打印，断言 uuid 只出现一次、没有第二行 `None`，列表是每行一个 uuid。`get_focused_terminal` 仍只打印代理返回的那一行。

## r13-3 hold

问题类：`remotinator set_tab_title` 改的是窗口当前可见标签，uuid 所在的标签保持原标题。

不变量：

- 标题写到 uuid 那台终端所在的标签页，不写到 `get_current_page()`。
- 该终端不在任何标签页上时，不改当前页。
- 窗口子部件不是 Notebook 时仍直接返回，与现在的 `is_child_notebook()` 一样。
- 当前页恰好就是该终端时，结果与现在相同。
- 写入仍是该页标签的 `set_custom_label(..., force=True)`。

要动的符号：`DBusService.set_tab_title`（约 306–322 行）。按同文件 `get_tab_title`（约 291–304 行）遍历 Notebook 的子页，确认终端落在哪一页，再取那一页的 `get_tab_label`。现在这里的 `Factory()` 没有参与查找，查找应与 `get_tab_title` 使用同一套 `isinstance` / `enumerate_descendants`。

明确不改：`get_tab_title` 的读法（仍返回 `get_label()` 文本）。不改 `notebook.py` 里 `set_custom_label` 的含义。不改 `remotinator` 的 `-t` 默认文案。

本地验证：没有 `set_tab_title` 测试。应新增：两个标签页，当前页是第一页，uuid 属于第二页；调用后只有第二页标签的自定义文本等于传入标题，第一页不变。uuid 不在任何页上时，两页文本都不变。只有一页且终端在该页时，该页标题改变。

## r13-4 hold

问题类：`remotinator new_tab -x <命令>` 打开的新标签跑默认 shell，给出的命令不执行。

不变量：

- `options` 里有 `execute` 时，新标签里的那台终端用这条命令启动，与 `new_terminal_cmd` 把 `execute` 交给 `spawn_child(init_command=...)` 相同。
- 没有 `execute` 时仍走今天的 `new_terminal(uuid, 'tab')` / `key_new_tab()`，跑默认 shell。
- 只影响这一次新终端，不写进程级 `command_line_options` 的 `command` / `execute`。
- `options` 里始终存在的 `tab-title` 默认句（`Missing Tab Title! Use -t argument!`，`-t` 未使用 `SUPPRESS`）不得变成新标签标题。本条不读 `-T` / `title`。

要动的符号：

- 客户端 `ipc.new_tab`：把 `options` 传给服务端，不要只传 uuid。与 r13-2 合在一处：返回 dbus 结果，不在包装里 `print`。
- 服务端 `DBusService.new_tab`：像 `hsplit` 一样接受可选 `options`，缺省 `None`，旧的 `new_tab(uuid)` 调用仍然成立。有 `execute` 时把命令送进新标签的 spawn；不要只调用无参数的 `key_new_tab()`。
- 传递所经过的现有入口：`Terminal.key_new_tab`、`Window.tab_new`、`Notebook.newtab`。`newtab` 在未传入现成部件时调用 `spawn_child(debugserver=debugtab)`，没有 `init_command`。命令要从这里进 `spawn_child` 的 `init_command`，或者先造好已 `spawn_child(init_command=execute)` 的终端再交给 `newtab(widget=...)`（该函数在已有部件时不会再次 spawn）。单终端窗口还没有 Notebook 时，仍须走 `tab_new` 里创建 Notebook 的那条路。

明确不改：`remotinator` 的 `-x` 定义。不改 `hsplit` / `vsplit` / `new_terminal_cmd`。不改 `spawn_child` 里「进程级 `options.command` / `options.execute` 压过 `init_command`」的顺序。

本地验证：没有新标签命令测试。应新增：假 session 上客户端 `new_tab(uuid, options)` 把同一份 `options` 交给服务端。服务端在 `execute` 有值时，新终端的 spawn 收到该命令，且 `options_get()` 的 `command` / `execute` 与调用前同一对象、同一值。`execute` 缺省时仍调用无命令的开标签路径。`options` 只带默认 `tab-title`、没有 `execute` 时，新标签标题不被写成那句默认文案。

## r13-5 hold

问题类：dbus `new_window_cmdline` 或 `new_tab_cmdline` 把本进程的命令行选项对象整份换成来访的字符串字典，调用结束后不恢复。

不变量：

- `Config.options_get()` / `command_line_options` 与 `optionparse.options` 是同一个 Namespace。方法返回后仍是调用前的那一个对象；其布尔、整数、列表和 `None` 与调用前相同。
- 来访字典只在这一次调用期间可见。`create_layout(layout)`、其后的 `layout_done()`（里面会对尚未有 pid 的终端 `spawn_child()`），以及 `new_tab_cmdline` 的 `tab_new()`，执行时要能读到来访的 `layout`，以及这次开窗需要的 `command` / `execute` / `working_directory` / `maximise` / `fullscreen` / `hidden` / `borderless` / 几何与标题类字段。因此恢复点在这些调用之后，而不是在 `create_layout` 返回之后、`layout_done` 之前。
- 新开的那一个窗口仍遵守来访的 maximise / fullscreen / hidden / borderless。方法返回之后再开的窗口看到调用前的布尔值。
- `spawn_child` 若在调用期间把 `command` / `execute` 置空，只能改到这一次的副本上，不能留在原 Namespace 上。
- 缺少 `layout` 或中途抛错时，原对象也已装回。今天 `options['configjson']` 缺键会在替换之前 `KeyError`；这条「尚未替换」保持不变。
- 树内第二次启动把 `True` 收成 `'True'`、把假和 `None` 收成 `''`、把列表拼成字符串（`terminator` 里组 `optionslist` 的那段）。服务端按这些字符串服务这一次开窗即可，不要求来访字典里出现字面 `'False'`。

要动的符号：`DBusService.new_window_cmdline`（约 72–98 行，`oldopts.__dict__ = options` 之后还有会话排除和 `layout_done()`，没有恢复）和 `DBusService.new_tab_cmdline`（约 100–108 行）。调用前取走原来的 `__dict__`，把这一次需要的字符串放进临时字典，`try` / `finally` 把原 `__dict__` 放回。不要在方法末尾才恢复却盖不住异常，也不要让 dbus 字典一直留在活对象上。

明确不改：`optionparse.parse_options` 的字符串化，`terminator` 里选择 `new_window_cmdline` / `new_tab_cmdline` 的分支，`session.is_explicit_launch` 对 `''` / `'None'` / `'False'` 的处理，`spawn_child` 读取并清空 `command` / `execute` 的规则（它清空的必须是副本）。不改 `remotinator`。

本地验证：没有这两则 dbus 方法的测试。应新增、不连接真实会话总线：Namespace 上 `maximise` 为布尔 `False`，`execute` 为列表；用来访字符串字典调用两个方法，并把 `create_layout`、`layout_done`、`tab_new` 换成会在执行当时读取 `options_get()` 的替身。断言替身看到的 `layout` 是来访值，且来访 `maximise` 为 `'True'` 时替身看到的值为真。方法返回后 `options_get()` 是原对象，`maximise` 仍是布尔 `False`，`execute` 仍是原列表。来访字典含 `configjson` 但不含 `layout` 时方法可以失败，返回后原对象的类型仍在。`configjson` 缺键时失败发生在替换之前，原 `__dict__` 从未被换成来访字典。

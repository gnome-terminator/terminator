---
title: "r12 layout 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "五条都保留：剪贴板按字符长度截断、超链接菜单用错匹配、折叠后 children 反序、批量关闭跳过 always、布局等待空转。"
---

# r12 layout 方案

核对结论：hold 5，weaken 0，drop 0。本方案只写保留项怎么改，不附可合入补丁。

## r12-1 hold

问题类：右键复制地址时，把 Python 字符长度交给按字节截断的 `Gtk.Clipboard.set_text`，非 ASCII 链接被切坏。

不变量：

- 剪贴板里的文本等于这一次 `prepare_url` 的结果，多字节字符整段保留。
- 长度用 `-1`，让 GTK 用 `strlen` 取字节长度。不要把 `len(str)` 当作字节数。
- 同一次激活只调用一次 `prepare_url`。

要动的符号：`TerminalPopupMenu.show` 里「复制地址」的 `activate` 回调（`terminatorlib/terminal_popup_menu.py` 约 240–241 行）。先算出准备后的字符串，再 `set_text(text, -1)`。

明确不改：普通复制仍走 `vte.copy_clipboard()`（约 247 行）。不改 `Terminal.prepare_url` 的改写规则。

本地验证：现无此断言。`tests/test_terminal_popup_menu.py` 的菜单测试不经过这条回调。应新增断言：对含 `café` 与中文路径的地址，复制进剪贴板后读回与 `prepare_url` 的结果相同。本机 GTK 3.24.33 上，`set_text(text, len(text))` 读回的已不是原串（并报 invalid UTF-8），`set_text(text, -1)` 能读回原串。

## r12-2 hold

问题类：VTE 超链接用 `matches` 的名字当正则分类，循环变量在未命中时仍留下最后一项的 match id，菜单按错误类型命名。

不变量：

- `matches` 的键仍是名字（`file`、`full_uri`、`voip`、`addr_only`、`email`、`nntp`，以及插件 `handler_name`），值仍是 VTE match id。分类不得对键做 `re.search`。
- 只有真正的匹配式命中才记下 tag。未命中时 tag 保持「没有」，并走已经写好的 `match_check_event`。
- 命中 email 的 id 才用「发送邮件 / 复制邮箱」；命中 voip 的 id 才用 VoIP 文案；插件仅当 `urlplugin.match` 命中且 `handler_name` 对上时才用该插件的 `nameopen` / `namecopy`。其余仍是「打开链接 / 复制地址」。

要动的符号：`TerminalPopupMenu.show` 的超链接分支（约 167–184 行的分类，约 200–223 行按 id 取文案）。`for pattern, tag in terminal.matches.items()` 每次迭代都会把 `tag` 写成当前值，循环体里的 `tag = tag` 不表示命中。要用单独的命中标志；循环结束仍未命中则保持进入循环前的 `None`。

匹配式今天不在 `matches` 里。插件的模式在 `urlplugin.match`（`terminatorlib/plugins/url_handlers.py`）。内置模式只在 `Terminal.update_url_matches` / `_add_regex`（`terminatorlib/terminal.py` 约 493–578 行）里就地构造，`_add_regex` 只存 id。弹层要识别 mailto 等超链接时，在注册处把模式和 id 放在一起再查，不要在弹层复制一套正则，也不要按键名搜索。

默认启用的 URL 插件按 `url_handlers.AVAILABLE` 的顺序实例化，最后一项是 `apturl`。未命中时菜单会变成「Open software manager / Copy package URI」。这是活码会走到的结果，改完后不得再出现。

明确不改：`match_check_event` 这条已有退路的调用方式。不改 `prepare_url` / `open_url` 对「真实 match id」的处理。不改插件自己的 `match` 字符串。

本地验证：`tests/test_terminal_popup_menu.py::test_vte_menu_does_not_end_on_a_separator` 把 `matches` 设成空字典且不传事件，覆盖不到这里。应新增断言：`hyperlink_check_event` 返回 `mailto:foo@bar.com` 时，菜单是发送邮件 / 复制邮箱，tag 是 `matches['email']`。返回一个不含任何处理器名字、也不符合各匹配式的 URL 时，不得使用最后一项（默认 `apturl`）的文案，并改为走 `match_check_event`。URL 里仅因出现字母 `email` 不得标成邮箱。

## r12-3 hold

问题类：关掉嵌套分屏里靠父分割第一槽的那一侧后，父 Paned 的 `children` 与 `child1` / `child2` 相反。

不变量：

- 每次成功 `Paned.add` 之后，`children` 等于 `(get_child1(), get_child2())` 里非空的那几项，顺序与槽位一致。
- 父 Paned 的第一槽是内层 Paned、关掉内层后内层被折叠时：幸存控件在第一槽，原来的第二槽仍在第二槽，`children` 与这个槽位顺序相同。关掉父 Paned 的第二槽时，本来对齐的顺序保持对齐。
- 侧栏经 `get_visible_terminals` → `get_offspring` 走 `children`（`terminatorlib/container.py` 约 98–100、392 行；`terminatorlib/notebook.py` 的 `_terminals_in_page` 约 2020–2030 行）。槽位顺序就是侧栏里多窗格的顺序。

要动的符号：`Paned.add`（`terminatorlib/paned.py` 约 143–155 行）。现在第二格用 `children.append`，第一槽空着时会 `pack1`，列表却变成 `[原来的 child2, 新控件]`。在 `add` 末尾用与 `split_axis`（约 120–126 行）和 `swap_child`（约 345–346 行）相同的槽位覆盖。`wrapcloseterm`（约 415–423 行）的 `parent.add(sibling, metadata)` 因此对齐，不必在关闭路径再写一份。

明确不改：`wrapcloseterm` 里 `sibling = self.children[0]` 的选取（按身份取幸存控件）。`describe_layout` 已走 `get_children()`（`container.py` 约 488 行），保存顺序跟槽位走，不要改。不改 `Notebook._sync_paned_slots`（拖放折叠已经在约 1440–1448 行对齐）。不改 `Container.get_offspring`。

本地验证：`tests/test_notebook_split.py::test_closing_last_term_of_tab_collapses_notebook_in_layout` 会 `wrapcloseterm`，不断言 Paned 的 `children` 与槽位。应新增断言：父分割第一槽是内层分屏、第二槽是另一台终端，关掉内层一侧并折叠后，`children == [get_child1(), get_child2()]`（空槽除外），且 `get_child1()` 是幸存控件。关掉第二槽的那次，`children` 仍与槽位相同。

## r12-4 hold

问题类：`ask_before_closing = always` 时，只有 shell 的批量关闭直接放行，单终端关闭仍会进旧确认框。

不变量：

- 有非 shell 进程时，批量关闭仍只走 `show_process_close_dialog`，同意才返回 True。
- 没有需要点名的进程时，与 `no_process_close_result` 一致：`multiple_terminals` 和 `never` 返回 `'accept'`，关闭可以继续；`always` 返回 `'legacy'`，必须先问过，用户接受才返回 True。
- 空列表仍返回 True。
- 单终端路径保持现状：`construct_confirm_close_with_processes` 在 `'legacy'` 时返回 None，由 `Container.construct_confirm_close` 弹出旧框（`container.py` 约 270–279 行之后）。

要动的符号：`confirm_close_terminals`（`terminatorlib/close_confirm.py` 约 411–422 行）。`should_confirm_processes` 得到 `need=False` 时不要直接 `return True`。先看 `no_process_close_result(_ask_before_closing())`。`'accept'` 才返回 True。`'legacy'` 时对传入的这一组终端弹一次确认，接受才返回 True。`closegroupedterms`（`terminatorlib/terminator.py` 约 937–944 行）已经在返回 False 时停住，不必改它。

明确不改：`no_process_close_result` 的三个返回值（`tests/test_close_confirm.py::test_idle_shells_skip_the_multiple_terminals_dialog` 锁着它们）。不改 `should_confirm_processes`。不要改道调用 `construct_confirm_close`：它会按单个 `child` 重新圈定终端，组可能只是窗口的一部分，并且会再进一遍进程判断。

本地验证：上述测试只断言 `no_process_close_result`，没有调用 `confirm_close_terminals`。应新增断言：只有 shell、`_ask_before_closing` 为 `always` 时，未接受确认不得返回 True，接受后才返回 True；同一组在 `multiple_terminals` 与 `never` 下返回 True 且不弹框；有非 shell 进程时仍只走进程对话框。

## r12-5 hold

问题类：布局阶段分割宽度仍是 1 且事件队列为空时，`set_position_by_ratio` 空转不返回。

不变量：

- `doing_layout` 为真且 `get_length()==1` 时，只在 `Gtk.events_pending()` 为真时调用 `Gtk.main_iteration`。队列为空就停止等待。
- 等待有次数或时间上限。到限后用进入等待前保存的 `ratio`，按当时的 `get_length()` 调用 `set_pos`，然后返回。
- `self.ratio` 在等待期间被改动的话，返回前恢复成等待前的值（现有 `ratio = self.ratio` 那段保持）。
- `doing_layout` 仍只由 `Terminator.create_layout` 置真、`layout_done` 置假（`terminatorlib/terminator.py` 约 229、350–352 行）。等待不得把它清掉，也不得让 `create_layout` 回不来。

要动的符号：`Paned.set_position_by_ratio`（`terminatorlib/paned.py` 约 634–644 行）。调用点 `Paned.create_layout`（约 545–547 行）和 `new_size`（约 601–603 行，仅在 `set_pos_by_ratio` 为真时进入）保持不动。

明确不改：`position_by_ratio` / `ratio_by_position` 的公式。不改 `split_axis` 里那次把队列抽干的 `main_iteration_do`（约 132–134 行）。

本地验证：现无测试覆盖这个等待。应新增断言：`doing_layout` 为真、`get_length` 恒为 1、`events_pending` 为假时，函数返回，且 `set_pos` 被调用一次；`main_iteration` 不被调用。`events_pending` 先真后假、长度仍为 1 时，`main_iteration` 只在队列非空时调用，次数不超过上限，函数仍返回。本机 GTK 3.24.33 上，已显示窗口里新放入的 `HPaned` 在抽干 `events_pending()` 之后分配宽度仍是 1，要等一次真正的 main iteration 才会变成窗口宽度。

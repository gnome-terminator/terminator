---
title: "r03 notebook 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "折叠缺键关闭与平滑滚轮降级后仍改，换终端丢锁保留；侧栏壳与布局调试开关不改。"
---

# r03 notebook 方案

核对结论：hold 1，weaken 2，drop 2。本方案只写保留项怎么改，不附可合入补丁。生产改动只落在 `terminatorlib/notebook.py`。

## r03-2 weaken

问题类：分屏后把当初那一格提成独立标签，折叠剩下的页时 `last_active_term` 仍按旧页控件记账；幸存终端还没成为键时，`closetab` 在确认之后无条件 `del`，`KeyError` 拦住 `close()`。

降级反证：`Terminal.on_vte_focus_in`（`terminatorlib/terminal.py` 约 2113–2123 行）会调用 `set_last_active_term` 再 `clean_last_active_term`，按当前页控件把键补上并丢掉已经不是页的旧键。侧栏点行走 `_activate_sidebar_row`，空闲时 `grab_focus`，焦点进来之后再关，键通常已经在。发现稿说本文件的 `note_pane_focus`、`_activate_sidebar_row` 不补键，这句对这两个符号成立，但补键发生在终端的 focus-in，不在笔记本里。因此「侧栏、关闭钮、中键、标签菜单每次都失败」过宽。未经这次 focus-in 的关闭仍然会失败：标签菜单先 `set_current_page` 再关，并不抓终端焦点；原生标签上的中键同样不经过 focus-in。只把当初那一格提走时才会缺键；提走的是分屏新生的那一格时，原终端仍是键，关闭走得通。

不变量：

- 折叠成单终端之后，新的页控件在 `last_active_term` 里有该终端的 uuid。`pop` 不到 paned 时用幸存终端自己的 uuid，不把「没有旧键」当成「不要登记」。
- `closetab` 对单终端页：键在就删，键不在也不抛，随后仍然 `child.close()`。
- 已经有键的关闭、以及 focus-in 补过键之后的关闭，行为与现在相同。

要动的符号：

- `Notebook._collapse_single_child_paned`（约 1392 行）。笔记本分支约 1406–1418 行只在 `pop(paned)` 得到值时写 `last_active_term[child]`。`split_axis`（约 545 行）先 `remove` 再插入分屏容器，`remove`（约 605 行）不碰这张表，所以键一直是当初那台终端，不是 paned。
- `Notebook.closetab`（约 1964–1968 行）的 `del nb.last_active_term[child]`。

明确不改：`split_axis` 的分屏结构，`newtab` 的信号和 `TabLabel` 创建，`Terminal.on_vte_focus_in` 的补键时机，`note_pane_focus` 只刷新侧栏。不把关闭失败改成静默吞掉其它异常。

本地验证：`tests/test_notebook_split.py` 会 `split_axis`，不断言 `last_active_term` 或 `closetab`。应新增断言：分屏后把当初那一格提成独立标签，幸存终端没有 focus-in；接着走 `closetab` 的确认通过路径，不抛 `KeyError`，该页被关掉。同一布局下先让幸存终端 focus-in 再关，页同样关掉，且 `last_active_term` 里没有已删除的页控件。

## r03-4 weaken

问题类：原生标签条上，平滑滚轮按标签条方向拆轴，和离散滚轮的上下左右不一致；顶栏或底栏的竖直平滑滚动不切页，事件仍被消费。左右原生条上每个非零 `delta_y` 都切一页。

降级反证：`tab_position == 'left'` 时 `configure`（约 335–339 行）把原生标签藏掉，可见列表是侧栏 `ScrolledWindow`（`_build_tab_tree`，约 906 行）。滚动落在这张列表上，不进 `on_scroll_event`。默认 `tab_position` 就是 `left`。发现稿说的「左右位置上滑一下连跳多页」只在原生标签条真正收到 `SMOOTH` 时成立，主要是 `right`；左栏这条路径碰不到。顶栏和底栏的竖直平滑滚动不切页、并且函数返回 `True`，与活码一致（约 2231–2244 行）。

不变量：

- 离散事件保持现在的对应：`RIGHT`/`DOWN` 下一页，`LEFT`/`UP` 上一页，与标签条在哪一边无关。
- 平滑滚动沿用同一套方向：正的 `delta_y` 视为向下，正的 `delta_x` 视为向右，顶栏和底栏的竖直滚动也切页。不再按 `get_tab_pos()` 把竖直和水平拆开。
- 一次手势里的一串小 delta 先累计，跨过与离散一格相当的阈值才切一页，并扣掉这次用掉的量。未跨过阈值不切页。

要动的符号：`Notebook.on_scroll_event`（约 2197 行，平滑分支约 2231–2243 行）。累计状态放在这个笔记本上，手势方向反转时丢掉反向剩余，避免一次来回连切。

明确不改：侧栏 `ScrolledWindow` 仍只滚动列表，不接切页。不改事件入口处对页内容、祖先和 action widget 的提前返回（约 2201–2223 行）。不改 `prev_page` / `next_page` 本身。

本地验证：现无滚动测试。应新增断言：标签位置为顶或底时，`SMOOTH` 且 `delta_y` 为正、`delta_x` 为 0，切到下一页；`delta_y` 为负切到上一页。标签位置为右时，连续若干个小于阈值的 `delta_y` 不切页，累计跨过阈值只切一页。离散 `DOWN` 在四种标签位置上都是下一页。

## r03-5 hold

问题类：已锁定的标签在页内容被换成一台终端之后，锁留在被丢掉的旧 `TabLabel` 上，新标签是未锁定。

不变量：原位替换之后，页序、自定义标题、锁定状态都在新页上。非终端分支已经把原 `TabLabel` 插回去，锁本来就在，这条保持。新建标签的默认值仍是未锁定。

要动的符号：`Notebook.swap_child` 的终端分支（约 646–655 行）。这里只把自定义标题放进 `metadata['label']`，然后 `newtab`。`newtab` 约 1875 行总是 `TabLabel('', self)`，`TabLabel.__init__` 约 2267 行把 `_locked` 设为 `False`，之后没有 `set_locked`。终端分支在新标签上按旧标签的 `get_locked()` 调用 `set_locked`。旧标签没有 `get_locked` 时保持未锁定。

调用点在 `paneoverlay` 还原：最大化时父控件若是笔记本，换进去的是占位控件，走非终端分支，原标签还在；还原时 `swap_child(占位, 终端)` 走进终端分支，锁被清掉。侧栏锁图标读的是 `get_locked()`。

明确不改：非终端分支的 `insert_page(new_widget, label, page_num)`。不改 `TabLabel` 的默认未锁定。不改 `paneoverlay` 的换位顺序。不改 `get_child_metadata`（它今天也不带锁）。

本地验证：`tests/test_tab_lock.py::test_one_locked_tab_restores_as_a_single_page` 只覆盖会话恢复后锁还在，不经过 `swap_child`。应新增断言：单终端页 `set_locked(True)` 并设自定义标题，`swap_child` 换成另一台终端后，页序不变，新标签 `get_locked()` 为真，自定义标题仍在；换成非终端时原标签对象仍在，锁仍为真。

## 丢弃（不改代码）

r03-1：发现稿认为卸下时只 `remove` 笔记本，壳留在窗口里，最后一页装不回去。`logical_parent` 会跳过带 `_tab_shell_notebook` 的壳并返回窗口；`Window.remove`（`terminatorlib/window.py` 约 997–1016 行）在笔记本的父控件是这层壳时改为移走壳。`hoover` 先卸下再 `add`，窗口这时没有子控件。`tests/test_m23_ui_fixes.py::test_p0_notebook_collapse_under_overlay` 在默认左侧标签（会挂壳）下断言关到一页后终端仍在、笔记本已不在。拖走最后一页时页数为 0，同样经 `Window.remove` 卸壳，接着 `Window.hoover` 在没有子控件时销毁窗口，不会留下空列表。

r03-3：`newtab(children[child_key])` 把布局子节点字典放进 `debugtab` 属实。`Terminal.spawn_child` 在 `doing_layout` 为真时直接返回（`terminatorlib/terminal.py` 约 2328 行）；`Terminator.create_layout` 在进入窗口布局之前就把该标志设为真（`terminatorlib/terminator.py` 约 229、346 行）。调试分支的条件是 `debugserver is True`（约 2361 行），字典进不去。真正启动在 `layout_done`（约 364–366 行），默认 `debugserver=False`，且在页的 `create_layout` 写完 `layout_command` 之后。`labels` / `last_active_term` 没有和 `locked` 一样的下标检查，但保存按页等长写入，会话过滤对短列表补 `None`。正常多标签恢复不会按调试开关启动终端。

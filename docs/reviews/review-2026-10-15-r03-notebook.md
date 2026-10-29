---
title: "r03 notebook 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "侧栏壳未随笔记本卸下，最后一页会从界面丢失；分屏后有的标签关不掉；多标签布局把子节点当调试开关启动；平滑滚动切页与离散滚轮不一致；换成终端页时锁定丢失。"
---

# r03 notebook 发现

通读 `terminatorlib/notebook.py`。下面 5 条都是这个文件里能走通的行为错误。

## r03-1

- 严重度：高
- 症状：左侧标签列表已经挂上时，关到只剩一个标签，或把最后一个标签拖走之后，标签列表的壳还占着窗口。只剩一页时，那一页终端先被摘离笔记本，再装不回窗口，界面上这页终端消失。拖走最后一页时，终端进了新窗口，旧窗口留下空的标签列表。

`_attach_tab_shell` 把普通 `Gtk.Box` 插在窗口和笔记本之间，窗口的直接子控件变成这个壳：

```844:847:terminatorlib/notebook.py
        if parent is window:
            Gtk.Window.add(window, shell)
        else:
            parent.add(shell)
```

注释要求连壳一起离开窗口，实现只对笔记本调用 `remove`，壳的父控件从未被要求移走壳：

```849:867:terminatorlib/notebook.py
    def _unparent_from_window(self):
        """Leave the window, taking the tab-list shell with this notebook."""
        holder = logical_parent(self)
        if holder is not None:
            holder.remove(self)
        else:
            parent = self.get_parent()
            if parent is not None:
                parent.remove(self)
        shell = getattr(self, '_tab_shell', None)
        self._tab_shell = None
        if shell is None:
            return
        try:
            shell._tab_shell_notebook = None
            if self.get_parent() is shell:
                shell.remove(self)
        except Exception:
            pass
```

`hoover` 在只剩一页时先 `remove_page`，再走上面的卸下，然后 `parent.add(child)`：

```2092:2107:terminatorlib/notebook.py
    def hoover(self):
        """Clean up any empty tabs and if we only have one tab left, die"""
        self._drop_empty_pages()

        if self.get_n_pages() == 1:
            dbg('Last page, removing self')
            child = self.get_nth_page(0)
            self.remove_page(0)
            parent = logical_parent(self)
            self._unparent_from_window()
            self.cnxids.remove_all()
            parent.add(child)
            del(self)
            # Find the last terminal in the new parent and give it focus
            terms = parent.get_visible_terminals()
            list(terms.keys())[-1].grab_focus()
```

本文件里 `logical_parent` 的用法是笔记本或带 `swap_child` / `get_visible_terminals` 的容器。侧栏壳是普通 `Gtk.Box`，不会是这个返回值，所以 `hoover` 的 `parent` 是窗口。窗口同时只能有一个子控件，壳还在时 `add` 不会把终端装进去。终端在 `remove_page` 之后已经没有父控件，函数返回后界面上不再有这页。`wrapcloseterm` 在 `closeterm` 成功后调用 `hoover`（1922–1927 行）。拖走最后一页时，`detach_tab_to_new_window`（391–395 行）和 `_release_source_after_drop`（1713–1725 行）同样调用 `_unparent_from_window`，壳留在旧窗口里。

- 方向：卸下笔记本时先把壳从窗口取下，再把还要留下的那一页装回窗口。

## r03-2

- 严重度：中
- 症状：标签被分屏之后，把当初那一格拆成独立标签（侧栏「Detach as Tab」或把它拖出去），留在原标签里的另一格再用侧栏、关闭钮、中键或标签菜单关闭，确认之后标签仍在，而且之后每次这样关都会失败。

`set_last_active_term` 用当前页控件做键。新建时这一页就是终端本身：

```2129:2130:terminatorlib/notebook.py
        nth_page = self.get_nth_page(tabnum)
        self.last_active_term[nth_page] = uuid
```

`split_axis` 只 `remove` 再插入分屏容器，不改这张表。`remove` 本身也不碰 `last_active_term`：

```545:546:terminatorlib/notebook.py
        label = self.get_tab_label(widget)
        self.remove(widget)
```

```605:613:terminatorlib/notebook.py
    def remove(self, widget):
        """Remove a widget from the container"""
        page_num = self.page_num(widget)
        if page_num == -1:
            err('%s not found in Notebook. Actual parent is: %s' %
                    (widget, widget.get_parent()))
            return(False)
        self.remove_page(page_num)
        self.disconnect_child(widget)
```

分屏后键仍是原来的终端，页已经变成 paned。把原来那一格提成独立标签时，`_lift_terminal` 在只剩一个孩子时折叠：

```1387:1389:terminatorlib/notebook.py
        parent.remove(term)
        if len(parent.children) == 1:
            self._collapse_single_child_paned(parent)
```

折叠只从 paned 上取上次活动终端。分屏从未把键写成 paned，所以存活的那一格不会被登记：

```1406:1418:terminatorlib/notebook.py
            label = parent.get_tab_label(paned)
            lat = None
            if hasattr(parent, 'last_active_term'):
                lat = parent.last_active_term.pop(paned, None)
            parent.detach_tab(paned)
            if page_num < 0:
                page_num = parent.get_n_pages()
            parent.insert_page(child, label, page_num)
            parent.set_tab_detachable(
                child, parent.config['detachable_tabs'])
            parent.set_tab_reorderable(child, True)
            parent._pack_tab(child)
            if lat is not None:
                parent.last_active_term[child] = lat
```

侧栏提升走 `_promote_sidebar_pane` → `_promote_terminal`（1216–1221、1473–1480 行）。此后原标签的页是剩下的那台终端，表里没有它。关闭在用户点了确认之后无条件 `del`，键不存在就抛 `KeyError`，`child.close()` 不会执行：

```1964:1968:terminatorlib/notebook.py
        if maker.isinstance(child, 'Terminal'):
            dbg('child is a single Terminal')

            del nb.last_active_term[child]
            child.close()
```

本文件里切焦点（`note_pane_focus`、`_activate_sidebar_row`）只刷新侧栏，不会把键补到新的页控件上。

- 方向：折叠成单终端时按新的页控件登记 `last_active_term`，关闭时缺键也要继续 `close()`。

## r03-3

- 严重度：中
- 症状：恢复有多个标签的布局时，笔记本里当时还不存在的那些页会把布局子节点字典当成调试开关去启动终端。

子节点在上面已经按 `child['type']`、`child['order']` 使用，这里却整份字典塞进 `newtab` 的第一个位置参数：

```504:509:terminatorlib/notebook.py
        num = 0
        for child_key in keys:
            page = self.get_nth_page(num)
            if not page:
                # This page does not yet exist, so make it
                self.newtab(children[child_key])
```

`newtab` 的第一个形参是 `debugtab`。没传 `widget` 时会新建终端，并把这个参数交给 `spawn_child` 的 `debugserver`：

```1840:1852:terminatorlib/notebook.py
    def newtab(self, debugtab=False, widget=None, cwd=None, metadata=None, profile=None):
        """Add a new tab, optionally supplying a child widget"""
        dbg('making a new tab')
        maker = Factory()
        top_window = self.get_toplevel()

        if not widget:
            widget = maker.make('Terminal')
            if cwd:
                widget.set_cwd(cwd)
            if profile and self.config['always_split_with_profile']:
                widget.force_set_profile(None, profile)
            widget.spawn_child(debugserver=debugtab)
```

布局子节点是非空字典，作为 `debugserver` 是真值。第一个标签通常已经占着第 0 页，不会走进这个调用；从第二页起，每次多标签布局恢复都会这样启动，然后才在 522 行 `page.create_layout`。同一次循环里 `locked` 有长度判断（517–518 行），`labels` 和 `last_active_term` 直接用 `num` 下标（512、525 行），列表比子节点短时这里会 `IndexError`，后面的页不再恢复。

- 方向：缺页时用普通 `newtab()` 创建终端，布局节点只交给该页的 `create_layout`，并且给 `labels` / `last_active_term` 做和 `locked` 一样的下标检查。

## r03-4

- 严重度：中
- 症状：顶部或底部标签栏上，竖直的平滑滚轮不切换标签，这次滚动还是被消费掉。左右标签位置上，平滑滚动的每一个非零 `delta_y` 都会切一页，触控板滑一下会连跳多页。

离散滚轮不论标签在哪一边，向下都是下一页、向上都是上一页。平滑滚动却按标签条方向拆开：左右只看 `delta_y`，上下只看 `delta_x`，而且没有累计阈值：

```2225:2244:terminatorlib/notebook.py
        if event.direction in [Gdk.ScrollDirection.RIGHT,
                               Gdk.ScrollDirection.DOWN]:
            self.next_page()
        elif event.direction in [Gdk.ScrollDirection.LEFT,
                                 Gdk.ScrollDirection.UP]:
            self.prev_page()
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            if self.get_tab_pos() in [Gtk.PositionType.LEFT,
                                      Gtk.PositionType.RIGHT]:
                if event.delta_y > 0:
                    self.next_page()
                elif event.delta_y < 0:
                    self.prev_page()
            elif self.get_tab_pos() in [Gtk.PositionType.TOP,
                                        Gtk.PositionType.BOTTOM]:
                if event.delta_x > 0:
                    self.next_page()
                elif event.delta_x < 0:
                    self.prev_page()
        return True
```

设备只发 `SMOOTH` 时，顶栏上的竖直滚轮 `delta_y` 非零、`delta_x` 为 0，两个分支都不会切页，函数仍返回 `True`。左右位置上同一次手势的一串小 `delta_y` 会每次都 `next_page()`。

- 方向：平滑滚动沿用离散方向那套上下左右规则，把 delta 累计过阈值再切一页。

## r03-5

- 严重度：中
- 症状：一个已锁定（下次启动还要打开）的标签，在页内容被换成一台终端之后，锁被清掉，侧栏变成未锁定。

`swap_child` 的说明是原位替换并保留标签。非终端分支把原来的 `TabLabel` 插回去，锁还在控件上。终端分支改走 `newtab`，元数据只拷了自定义标题：

```641:655:terminatorlib/notebook.py
        self.disconnect_child(old_widget)
        # Keep the label widget; detach page without destroying the label
        self.detach_tab(old_widget)

        maker = Factory()
        if maker.isinstance(new_widget, 'Terminal'):
            # Re-insert via newtab so signals + TabLabel stay consistent
            metadata = {'tabnum': page_num}
            if label is not None and hasattr(label, 'get_custom_label'):
                custom = label.get_custom_label()
                if custom:
                    metadata['label'] = custom
            self.newtab(widget=new_widget, metadata=metadata)
            if lat is not None:
                self.last_active_term[new_widget] = lat
```

`newtab` 总会新建 `TabLabel`（1875 行）。新建标签的锁初始是关的，后面没有 `set_locked`：

```2264:2267:terminatorlib/notebook.py
        self.notebook = notebook
        self.terminator = Terminator()
        self.config = Config()
        self._locked = False
```

自定义标题还能通过 `metadata['label']` 留下来。锁定只活在旧标签控件的 `_locked` 上，终端这条路径把那个控件丢掉了。侧栏锁图标读的就是 `get_locked()`。

- 方向：终端分支在新标签上恢复原来的锁定，或继续沿用原来的 `TabLabel`。
